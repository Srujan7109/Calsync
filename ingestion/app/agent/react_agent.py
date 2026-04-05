from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any

from ingestion.app.agent.prompts import AGENT_ANALYSIS_PROMPT
from ingestion.app.agent.tools import CalsyncTools
from ingestion.app.config import get_settings
from ingestion.app.models.agent_models import AgentProcessResponse, AgentResult
from ingestion.app.models.email_models import AgentProcessPayload
from ingestion.app.services.participant_utils import dedupe_emails, exclude_emails, parse_email_addresses
from ingestion.app.services.thread_state_service import ThreadSessionState, ThreadStateService


logger = logging.getLogger("uvicorn.error")


def _looks_like_new_meeting(subject: str, body_text: str) -> bool:
    text = f"{subject} {body_text}".lower()
    return any(word in text for word in ["meeting", "schedule", "available", "sync", "call"])


def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
    left = raw_text.find("{")
    right = raw_text.rfind("}")
    if left < 0 or right < left:
        return None
    try:
        return json.loads(raw_text[left : right + 1])
    except json.JSONDecodeError:
        return None


def _normalize_recipients(payload: AgentProcessPayload) -> list[str]:
    recipients = [p.strip() for p in payload.participants if p and p.strip()]
    if not recipients and payload.from_email:
        recipients = [payload.from_email]

    deduped: list[str] = []
    seen: set[str] = set()
    for recipient in recipients:
        key = recipient.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(recipient)
    return deduped


def _collect_participants_from_thread_payload(thread_payload: dict[str, object], excluded: list[str]) -> tuple[list[str], list[str]]:
    emails = thread_payload.get("emails")
    if not isinstance(emails, list):
        return [], []

    participants: list[str] = []
    replied: list[str] = []
    for item in emails:
        if not isinstance(item, dict):
            continue

        from_email = str(item.get("from_email") or "")
        to_emails = item.get("to_emails") if isinstance(item.get("to_emails"), list) else []
        cc_emails = item.get("cc_emails") if isinstance(item.get("cc_emails"), list) else []

        participants.extend(parse_email_addresses(from_email))
        participants.extend(parse_email_addresses(",".join(str(v) for v in to_emails)))
        participants.extend(parse_email_addresses(",".join(str(v) for v in cc_emails)))

        sender = parse_email_addresses(from_email)
        if sender:
            replied.extend(sender)

    participants = exclude_emails(dedupe_emails(participants), excluded)
    replied = exclude_emails(dedupe_emails(replied), excluded)
    return participants, replied


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _should_send_reminder(last_reminder_at: str | None, cooldown_minutes: int) -> bool:
    last = _parse_iso_timestamp(last_reminder_at)
    if not last:
        return True
    return datetime.now(timezone.utc) - last >= timedelta(minutes=max(cooldown_minutes, 1))


async def _analyze_email_with_gemini(payload: AgentProcessPayload) -> dict[str, Any]:
    settings = get_settings()
    default_action = "SENT_AVAILABILITY_REQUEST" if _looks_like_new_meeting(payload.subject, payload.body_text) else "NO_ACTION"
    default_reasoning = "Thought: deterministic scheduling intent check. Action: fallback pipeline."

    if not settings.gemini_api_key:
        logger.info(
            "Agent decision source=fallback reason=missing_gemini_api_key subject=%s from=%s action=%s",
            payload.subject,
            payload.from_email,
            default_action,
        )
        return {
            "action": default_action,
            "title": payload.subject.strip() or "Meeting coordination",
            "reasoning_trace": default_reasoning,
            "request_email_body": "Could you please share your preferred time slots and timezone?",
            "slot": None,
        }

    try:
        gemini_module = import_module("google.genai")
    except ModuleNotFoundError:
        logger.info(
            "Agent decision source=fallback reason=missing_google_genai subject=%s from=%s action=%s",
            payload.subject,
            payload.from_email,
            default_action,
        )
        return {
            "action": default_action,
            "title": payload.subject.strip() or "Meeting coordination",
            "reasoning_trace": default_reasoning,
            "request_email_body": "Could you please share your preferred time slots and timezone?",
            "slot": None,
        }

    prompt = AGENT_ANALYSIS_PROMPT.format(
        subject=payload.subject,
        from_email=payload.from_email,
        participants=", ".join(payload.participants),
        current_time=datetime.now(timezone.utc).isoformat(),
        body=payload.body_text[:2000],
    )
    client = gemini_module.Client(api_key=settings.gemini_api_key)

    # Retry with exponential backoff on 429 rate-limit errors
    max_retries = 4
    response = None
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=settings.gemini_model,
                contents=prompt,
            )
            break  # success — exit retry loop
        except Exception as exc:
            error_str = str(exc)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
            if is_rate_limit and attempt < max_retries - 1:
                wait_seconds = 2 ** (attempt + 1) * 15  # 30s, 60s, 120s
                logger.warning(
                    "Gemini rate limited (attempt %d/%d) — retrying in %ds",
                    attempt + 1, max_retries, wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue
            logger.warning("Gemini call failed after %d attempts: %s", attempt + 1, exc)
            return {
                "action": default_action,
                "title": payload.subject.strip() or "Meeting coordination",
                "reasoning_trace": f"Thought: Gemini unavailable ({exc}). Action: deterministic fallback.",
                "request_email_body": "Could you please share your preferred time slot?",
                "slot": None,
            }

    output_text = getattr(response, "text", "") or "" if response else ""
    parsed = _extract_json_payload(output_text)
    if parsed is None:
        logger.info(
            "Agent decision source=fallback reason=invalid_gemini_json subject=%s from=%s action=%s",
            payload.subject,
            payload.from_email,
            default_action,
        )
        return {
            "action": default_action,
            "title": payload.subject.strip() or "Meeting coordination",
            "reasoning_trace": "Thought: invalid Gemini JSON response. Action: deterministic fallback.",
            "request_email_body": "Could you please share your preferred time slots and timezone?",
            "slot": None,
        }
    logger.info(
        "Agent decision source=gemini subject=%s from=%s action=%s",
        payload.subject,
        payload.from_email,
        str(parsed.get("action") or "NO_ACTION"),
    )
    return parsed


async def run_react_agent(payload: AgentProcessPayload) -> AgentProcessResponse:
    tools = CalsyncTools()
    settings = get_settings()
    thread_service = ThreadStateService()

    thread_id = payload.thread_id.strip() or payload.message_id
    excluded = dedupe_emails([settings.gmail_sender_email or "", payload.from_email])
    recipients = _normalize_recipients(payload)

    session = ThreadSessionState(
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        status="AWAITING_REPLIES",
        organizer_email=payload.from_email,
        meeting_title=payload.subject or "Meeting",
        participants=[],
        replied_participants=[],
        last_reminder_at=None,
    )
    if settings.thread_intelligence_enabled:
        try:
            session = await thread_service.get_or_create_session(
                thread_id=thread_id,
                organizer_email=payload.from_email,
                meeting_title=payload.subject or "Meeting",
                participants=recipients,
            )
        except Exception as exc:  # pragma: no cover - external dependency safety
            logger.warning("Thread session restore skipped: %s", exc)

    analysis = await _analyze_email_with_gemini(payload)
    action = str(analysis.get("action") or "NO_ACTION")
    reasoning_trace = str(analysis.get("reasoning_trace") or "Thought: no-op.")
    meeting_title = str(analysis.get("title") or payload.subject or "Meeting coordination")
    session_id = session.session_id or f"sess_{uuid.uuid4().hex[:8]}"

    session.meeting_title = meeting_title
    session.organizer_email = payload.from_email

    # Build participant pool: always restore full list from persisted session state
    participant_pool = dedupe_emails(session.participants + recipients + [payload.from_email])
    participant_pool = exclude_emails(participant_pool, [settings.gmail_sender_email or ""])

    # Mark the sender of the current email as having replied
    replied_pool = dedupe_emails(session.replied_participants + [payload.from_email])
    replied_pool = exclude_emails(replied_pool, [settings.gmail_sender_email or ""])

    if settings.thread_intelligence_enabled and thread_id and thread_id != payload.message_id:
        thread_outcome = await tools.fetch_thread(thread_id=thread_id)
        reasoning_trace = f"{reasoning_trace} Tool: fetch_thread={thread_outcome.status}."
        if thread_outcome.status == "OK":
            thread_participants, thread_replied = _collect_participants_from_thread_payload(thread_outcome.payload, excluded)
            previous_count = len(set(email.lower() for email in participant_pool))
            participant_pool = dedupe_emails(participant_pool + thread_participants)
            replied_pool = dedupe_emails(replied_pool + thread_replied)
            if len(set(email.lower() for email in participant_pool)) > previous_count:
                reasoning_trace = f"{reasoning_trace} Observation: late_joiner_detected."

    pending_participants = [
        participant
        for participant in participant_pool
        if participant.lower() not in {email.lower() for email in replied_pool}
    ]

    is_new_session = not session.replied_participants and session.last_reminder_at is None

    reminders_sent = False

    logger.info(
        "Agent execution session_id=%s action=%s subject=%s is_new=%s pending=%s",
        session_id,
        action,
        payload.subject,
        is_new_session,
        len(pending_participants),
    )

    if action == "SENT_AVAILABILITY_REQUEST":
        request_body = str(
            analysis.get("request_email_body")
            or "Thanks for reaching out. Please share your preferred time slot so I can coordinate the meeting."
        )

        send_to = participant_pool if is_new_session else (pending_participants or participant_pool)
        send_thread_id = thread_id if is_new_session else None

        if send_to:
            gmail_outcome = await tools.send_gmail_message(
                recipients=send_to,
                subject=f"Re: {payload.subject}" if payload.subject else "Meeting coordination",
                body_text=request_body,
                thread_id=send_thread_id,
                session_id=session_id,
            )
            reasoning_trace = f"{reasoning_trace} Tool: send_gmail_message={gmail_outcome.status}."

            if gmail_outcome.status == "OK" and is_new_session:
                session.last_reminder_at = datetime.now(timezone.utc).isoformat()

        if (
            settings.thread_intelligence_enabled
            and not is_new_session
            and session.status == "AWAITING_REPLIES"
            and pending_participants
            and _should_send_reminder(session.last_reminder_at, settings.reminder_cooldown_minutes)
        ):
            reminder_body = (
                f"Quick reminder: we are still waiting on your availability to finalise '{meeting_title}'.\n\n"
                "Please reply with specific dates and times (IST) that work for you."
            )
            reminder_outcome = await tools.send_gmail_message(
                recipients=pending_participants,
                subject=f"Reminder: availability needed for {meeting_title}",
                body_text=reminder_body,
                thread_id=None,
                session_id=session_id,
            )
            reminders_sent = reminder_outcome.status == "OK"
            reasoning_trace = f"{reasoning_trace} Tool: reminder_email={reminder_outcome.status}."

    elif action == "BOOKED_CALENDAR":
        # Guard: don't book if session is already BOOKED
        if settings.thread_intelligence_enabled and session.status == "BOOKED":
            logger.info(
                "Session %s already BOOKED — skipping duplicate booking for thread %s",
                session_id, thread_id
            )
            return AgentProcessResponse(
                agent_result=AgentResult(
                    action_taken="NO_ACTION",
                    session_id=session_id,
                    emails_sent_to=[],
                    reasoning_trace="Session already BOOKED. Duplicate agent run suppressed.",
                )
            )

        # FIX 2: Gate booking — all participants must have replied before we book
        if pending_participants:
            logger.info(
                "Session %s waiting for replies from: %s — overriding BOOKED_CALENDAR to SENT_AVAILABILITY_REQUEST",
                session_id, pending_participants
            )
            action = "SENT_AVAILABILITY_REQUEST"
            wait_body = (
                f"We're still waiting to hear from {len(pending_participants)} participant(s). "
                "Please reply with a time slot that works for you."
            )
            gmail_outcome = await tools.send_gmail_message(
                recipients=pending_participants,
                subject=f"Re: {payload.subject}" if payload.subject else "Meeting coordination",
                body_text=wait_body,
                thread_id=None,
                session_id=session_id,
            )
            reasoning_trace = f"{reasoning_trace} Tool: waiting_for_participants={gmail_outcome.status}."
        else:
            slot = analysis.get("slot") if isinstance(analysis.get("slot"), dict) else {}
            calendar_slot = {"start": str(slot.get("start_iso") or ""), "end": str(slot.get("end_iso") or "")}

            if not calendar_slot["start"] or not calendar_slot["end"]:
                action = "SENT_AVAILABILITY_REQUEST"
                request_body = "Please let me know a time slot so I can book the meeting."
                gmail_outcome = await tools.send_gmail_message(
                    recipients=participant_pool,
                    subject=f"Re: {payload.subject}" if payload.subject else "Meeting coordination",
                    body_text=request_body,
                    thread_id=None,
                    session_id=session_id,
                )
                reasoning_trace = (
                    f"{reasoning_trace} Tool: missing_slot_data. Tool: send_gmail_message={gmail_outcome.status}."
                )
            else:
                freebusy_outcome = await tools.check_freebusy(participants=participant_pool, slot=calendar_slot)
                reasoning_trace = f"{reasoning_trace} Tool: check_freebusy={freebusy_outcome.status}."

                freebusy_results = freebusy_outcome.payload.get("results")
                slot_is_free = bool(
                    isinstance(freebusy_results, list)
                    and freebusy_results
                    and isinstance(freebusy_results[0], dict)
                    and freebusy_results[0].get("is_free") is True
                )

                if not slot_is_free:
                    action = "SENT_AVAILABILITY_REQUEST"
                    request_body = "The suggested slot appears busy for at least one participant. Please share alternatives."
                    gmail_outcome = await tools.send_gmail_message(
                        recipients=participant_pool,
                        subject=f"Re: {payload.subject}" if payload.subject else "Meeting coordination",
                        body_text=request_body,
                        thread_id=None,
                        session_id=session_id,
                    )
                    reasoning_trace = (
                        f"{reasoning_trace} Tool: slot_conflicted. Tool: send_gmail_message={gmail_outcome.status}."
                    )
                else:
                    all_booking_participants = dedupe_emails(session.participants + participant_pool)
                    all_booking_participants = exclude_emails(all_booking_participants, [settings.gmail_sender_email or ""])

                    calendar_outcome = await tools.book_calendar(
                        title=meeting_title,
                        participants=all_booking_participants,
                        slot=calendar_slot,
                        organizer_email=session.organizer_email or payload.from_email,
                        session_id=session_id,
                    )
                    reasoning_trace = f"{reasoning_trace} Tool: book_calendar={calendar_outcome.status}."

                    if calendar_outcome.status == "OK":
                        session.status = "BOOKED"

                    booked = calendar_outcome.payload
                    meet_link = str(booked.get("meet_link") or "")
                    event_link = str(booked.get("event_link") or "")
                    booked_slot = booked.get("booked_slot", calendar_slot)

                    try:
                        ist = timezone(timedelta(hours=5, minutes=30))
                        start_ist = datetime.fromisoformat(
                            str(booked_slot.get("start", calendar_slot["start"])) .replace("Z", "+00:00")
                        ).astimezone(ist).strftime("%d %b %Y, %I:%M %p IST")
                        end_ist = datetime.fromisoformat(
                            str(booked_slot.get("end", calendar_slot["end"])) .replace("Z", "+00:00")
                        ).astimezone(ist).strftime("%I:%M %p IST")
                        slot_display = f"{start_ist} - {end_ist}"
                    except Exception:
                        slot_display = f"{calendar_slot['start']} - {calendar_slot['end']} (UTC)"

                    confirmation_body = (
                        f"Great news! Your meeting '{meeting_title}' has been confirmed.\n\n"
                        f"Time: {slot_display}\n"
                        f"Google Meet: {meet_link or 'See calendar invite'}\n"
                        f"Calendar: {event_link or 'See calendar invite'}\n\n"
                        "You will receive a Google Calendar invite shortly."
                    )
                    gmail_outcome = await tools.send_gmail_message(
                        recipients=all_booking_participants,
                        subject=f"Meeting confirmed: {meeting_title}",
                        body_text=confirmation_body,
                        thread_id=None,
                        session_id=session_id,
                    )
                    reasoning_trace = f"{reasoning_trace} Tool: send_gmail_message={gmail_outcome.status}."

    if session.status != "BOOKED":
        if pending_participants:
            session.status = "AWAITING_REPLIES"
        else:
            session.status = "READY_TO_COMPUTE"

    session.participants = participant_pool
    session.replied_participants = replied_pool
    if reminders_sent:
        session.last_reminder_at = datetime.now(timezone.utc).isoformat()

    if settings.thread_intelligence_enabled:
        try:
            await thread_service.persist_state(session)
        except Exception as exc:  # pragma: no cover - external dependency safety
            logger.warning("Thread session persistence skipped: %s", exc)

    return AgentProcessResponse(
        agent_result=AgentResult(
            action_taken=action,
            session_id=session_id,
            emails_sent_to=recipients,
            reasoning_trace=reasoning_trace,
        )
    )
