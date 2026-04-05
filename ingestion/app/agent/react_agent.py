from __future__ import annotations

import asyncio
import httpx
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any

from ingestion.app.agent.tools import CalsyncTools
from ingestion.app.config import get_settings
from ingestion.app.models.agent_models import AgentProcessResponse, AgentResult
from ingestion.app.models.email_models import AgentProcessPayload
from ingestion.app.services.participant_utils import dedupe_emails, exclude_emails, parse_email_addresses
from ingestion.app.services.thread_state_service import ThreadSessionState, ThreadStateService

logger = logging.getLogger("uvicorn.error")
IST = timezone(timedelta(hours=5, minutes=30))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_ist(utc_iso: str) -> str:
    try:
        return datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(IST).strftime("%d %b %Y %I:%M %p IST")
    except Exception:
        return utc_iso


def _extract_ref(text: str) -> str | None:
    m = re.search(r'\[calsync-ref:([a-z0-9_]+)\]', text or "", re.IGNORECASE)
    return m.group(1) if m else None


def _cooldown_ok(last: str | None, minutes: int) -> bool:
    if not last:
        return True
    try:
        ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts >= timedelta(minutes=max(minutes, 1))
    except Exception:
        return True


def _compute_overlap(slots_by_participant: dict, duration_minutes: int = 60) -> list[dict]:
    """Pure Python overlap computation — no external service needed."""
    if not slots_by_participant:
        return []

    participants = list(slots_by_participant.keys())
    duration = timedelta(minutes=duration_minutes)

    def parse_dt(s: str) -> datetime:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # Start with first participant's slots
    overlaps = []
    for slot in slots_by_participant[participants[0]]:
        try:
            overlaps.append({"start": parse_dt(slot["start"]), "end": parse_dt(slot["end"])})
        except Exception:
            pass

    # Intersect with each subsequent participant
    for p in participants[1:]:
        new_overlaps = []
        for candidate in overlaps:
            for p_slot in slots_by_participant.get(p, []):
                try:
                    p_start = parse_dt(p_slot["start"])
                    p_end = parse_dt(p_slot["end"])
                    overlap_start = max(candidate["start"], p_start)
                    overlap_end = min(candidate["end"], p_end)
                    if overlap_end - overlap_start >= duration:
                        new_overlaps.append({"start": overlap_start, "end": overlap_end})
                except Exception:
                    pass
        overlaps = new_overlaps

    # Return as ISO strings, trimmed to exact duration
    result = []
    for ov in overlaps[:3]:  # top 3
        end = ov["start"] + duration
        result.append({
            "start": ov["start"].isoformat(),
            "end": end.isoformat(),
        })
    return result


async def _gemini(prompt: str, settings) -> str:
    """Raw Gemini call, returns text."""
    try:
        genai = import_module("google.genai")
    except ModuleNotFoundError:
        return ""
    client = genai.Client(api_key=settings.gemini_api_key)
    for attempt in range(3):
        try:
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model=settings.gemini_model,
                contents=prompt,
            )
            return getattr(resp, "text", "") or ""
        except Exception as exc:
            if ("429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)) and attempt < 2:
                await asyncio.sleep(30 * (attempt + 1))
                continue
            logger.warning("Gemini call failed: %s", exc)
            return ""
    return ""


async def _extract_slots_with_gemini(body_text: str, settings) -> list[dict]:
    """Ask Gemini to extract time slots from availability reply text."""
    if not settings.gemini_api_key:
        return []

    prompt = f"""Extract ALL time slots from this availability email. 
Return ONLY a JSON array of objects with "start" and "end" keys in ISO 8601 UTC format.
Assume all times are IST (UTC+5:30) unless stated otherwise.
If no clear time slots, return [].

Email:
{body_text[:1000]}

Return only the JSON array, nothing else. Example: [{{"start":"2026-04-06T09:30:00Z","end":"2026-04-06T10:30:00Z"}}]"""

    raw = await _gemini(prompt, settings)
    raw = raw.strip()
    l, r = raw.find("["), raw.rfind("]")
    if l < 0 or r < l:
        return []
    try:
        slots = json.loads(raw[l:r + 1])
        return [s for s in slots if s.get("start") and s.get("end")]
    except Exception:
        return []


async def _classify_email(body_text: str, subject: str, settings) -> str:
    """Classify email as NEW_REQUEST, AVAILABILITY_REPLY, or OTHER."""
    text = f"{subject} {body_text}".lower()

    # Quick keyword checks
    availability_words = ["available", "free", "i can", "works for me", "how about", "3pm", "4pm", "am", "pm", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday"]
    request_words = ["schedule", "meeting", "arrange", "set up", "sync", "please coordinate", "calsync"]

    has_availability = sum(1 for w in availability_words if w in text)
    has_request = any(w in text for w in request_words)

    if has_availability >= 2:
        return "AVAILABILITY_REPLY"
    if has_request:
        return "NEW_REQUEST"
    return "OTHER"


async def _lookup_session(thread_service: ThreadStateService, session_id: str) -> ThreadSessionState | None:
    if not thread_service._enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(
                f"{thread_service.base_url}/rest/v1/sessions",
                headers=thread_service._headers(),
                params={"select": "*", "session_id": f"eq.{session_id}", "limit": "1"},
            )
            rows = r.json() if r.status_code == 200 else []
        if not rows:
            return None
        row = rows[0]
        return ThreadSessionState(
            session_id=row["session_id"],
            thread_id=row["thread_id"],
            status=row.get("status", "AWAITING_REPLIES"),
            organizer_email=row.get("organizer_email", ""),
            meeting_title=row.get("meeting_title", "Meeting"),
            participants=list(row.get("participants") or []),
            replied_participants=list(row.get("replied_participants") or []),
            last_reminder_at=row.get("last_reminder_at"),
        )
    except Exception as exc:
        logger.warning("_lookup_session failed: %s", exc)
        return None


# ── Main agent ────────────────────────────────────────────────────────────────

async def run_react_agent(payload: AgentProcessPayload) -> AgentProcessResponse:
    tools = CalsyncTools()
    settings = get_settings()
    thread_service = ThreadStateService()
    calsync = (settings.gmail_sender_email or "calsync1.ai@gmail.com").lower()

    thread_id = payload.thread_id.strip() or payload.message_id
    sender = payload.from_email.lower()

    # Skip emails from CalSync itself to avoid loops
    if sender == calsync:
        return AgentProcessResponse(agent_result=AgentResult(
            action_taken="NO_ACTION", session_id="", emails_sent_to=[],
            reasoning_trace="Skipped own outbound email.",
        ))

    inbound_people = exclude_emails(
        dedupe_emails(payload.participants + [payload.from_email]), [calsync]
    )

    # ── Restore or create session ─────────────────────────────────────────────
    session: ThreadSessionState | None = None
    try:
        session = await thread_service.get_or_create_session(
            thread_id=thread_id,
            organizer_email=payload.from_email,
            meeting_title=payload.subject or "Meeting",
            participants=inbound_people,
        )
    except Exception as exc:
        logger.warning("Session restore by thread_id failed: %s", exc)

    # Try body ref for replies to our individual emails
    ref = _extract_ref(payload.body_text)
    is_new = session is None or (not session.replied_participants and session.last_reminder_at is None)

    if ref and is_new:
        recovered = await _lookup_session(thread_service, ref)
        if recovered:
            session = recovered
            is_new = False
            logger.info("Session recovered via body ref=%s", recovered.session_id)

    if session is None:
        session = ThreadSessionState(
            session_id=f"sess_{uuid.uuid4().hex[:8]}",
            thread_id=thread_id,
            status="AWAITING_REPLIES",
            organizer_email=payload.from_email,
            meeting_title=payload.subject or "Meeting",
            participants=inbound_people,
            replied_participants=[],
            last_reminder_at=None,
        )
        is_new = True

    session_id = session.session_id
    is_new = not session.replied_participants and session.last_reminder_at is None
    all_p = exclude_emails(dedupe_emails(session.participants + inbound_people), [calsync])
    replied_seed = session.replied_participants if is_new else (session.replied_participants + [payload.from_email])
    replied = exclude_emails(dedupe_emails(replied_seed), [calsync])
    replied_set = {e.lower() for e in replied}
    organizer = (session.organizer_email or payload.from_email).lower()
    pending = [p for p in all_p if p.lower() not in replied_set]
    meeting_title = session.meeting_title or payload.subject or "Meeting"

    logger.info(
        "Agent session=%s is_new=%s all=%s replied=%s pending=%s",
        session_id, is_new, all_p, replied, pending
    )

    trace = ""
    action_taken = "NO_ACTION"
    notified_recipients = list(inbound_people)

    # ══════════════════════════════════════════════════════════════════════════
    # NEW SESSION — organizer CC'd CalSync requesting a meeting
    # ══════════════════════════════════════════════════════════════════════════
    if is_new and session.status != "BOOKED":
        # Extract meeting title from Gemini if possible
        if settings.gemini_api_key:
            title_prompt = f"Extract a short 3-5 word meeting title from this email subject/body. Return ONLY the title text.\nSubject: {payload.subject}\nBody: {payload.body_text[:500]}"
            title = await _gemini(title_prompt, settings)
            if title.strip():
                meeting_title = title.strip().strip('"').strip("'")
                session.meeting_title = meeting_title

        availability_body = (
            f"Hi,\n\n"
            f"I'm CalSync.ai, helping {session.organizer_email} schedule '{meeting_title}'.\n\n"
            f"Please reply to this email with your available dates and times (IST). "
            f"For example: 'I'm free tomorrow 3pm-5pm IST and Monday 10am-12pm IST'.\n\n"
            f"Thank you!\n\nCalSync.ai\n\n[calsync-ref:{session_id}]"
        )

        for p in all_p:
            result = await tools.send_gmail_message(
                recipients=[p],
                subject=f"When are you free? — {meeting_title}",
                body_text=availability_body,
                thread_id="",
                session_id=session_id,
            )
            logger.info("Availability request sent to %s status=%s", p, result.status)

        session.last_reminder_at = _now_iso()
        session.status = "AWAITING_REPLIES"
        action_taken = "SENT_AVAILABILITY_REQUEST"
        trace = f"New session. Sent availability requests to {all_p}."

    # ══════════════════════════════════════════════════════════════════════════
    # EXISTING SESSION — participant sent their availability
    # ══════════════════════════════════════════════════════════════════════════
    elif not is_new and session.status not in ("BOOKED", "CANCELLED"):

        email_type = await _classify_email(payload.body_text, payload.subject, settings)
        action_taken = "AVAILABILITY_REPLY"

        if email_type == "AVAILABILITY_REPLY":
            # Extract slots from this reply
            slots = await _extract_slots_with_gemini(payload.body_text, settings)
            logger.info("Extracted %d slots from %s: %s", len(slots), payload.from_email, slots)

            # Persist slots to collected_slots in DB
            if slots:
                await thread_service.update_participant_slots(session_id, payload.from_email, slots)
            else:
                # Store empty list to mark as replied even without parsed slots
                await thread_service.update_participant_slots(session_id, payload.from_email, [])

            trace = f"Received availability from {payload.from_email} ({len(slots)} slots)."

        # Rebuild replied/pending from persisted collected_slots so simultaneous replies don't get lost
        collected_now = await thread_service.get_collected_slots(session_id)
        collected_responders = {str(p).lower() for p in (collected_now or {}).keys()}
        persisted_replied = {str(p).lower() for p in (session.replied_participants or [])}
        merged_replied = persisted_replied | collected_responders
        replied = [p for p in all_p if p.lower() in merged_replied]
        replied_set = {e.lower() for e in replied}
        pending = [p for p in all_p if p.lower() not in replied_set]
        replied_count = len(replied)
        total_count = len(all_p)
        all_replied = replied_count == total_count

        # Hard guard: once a session has reached READY_TO_COMPUTE/BOOKED, don't allow
        # reply progress to regress unless we explicitly reset status to AWAITING_REPLIES.
        reached_all_replied_before = session.status in ("READY_TO_COMPUTE", "BOOKED")
        if reached_all_replied_before and not all_replied:
            logger.warning(
                "Reply regression prevented session=%s status=%s replied=%d total=%d",
                session_id,
                session.status,
                replied_count,
                total_count,
            )
            replied = list(all_p)
            replied_set = {e.lower() for e in replied}
            pending = []
            replied_count = total_count
            all_replied = True

        logger.info(
            "Reply progress session=%s replied=%d total=%d all_replied=%s pending=%s",
            session_id,
            replied_count,
            total_count,
            all_replied,
            pending,
        )

        # Compute only when every participant (including organizer) has replied.
        if all_replied:
            collected = collected_now
            logger.info("All %d participants replied. Collected: %s", len(all_p), collected)

            # Require slots from every participant (including organizer) before overlap.
            # Use case-insensitive matching because incoming emails may differ in casing.
            by_lower = {
                str(email).lower(): slots
                for email, slots in (collected or {}).items()
                if isinstance(slots, list)
            }
            slots_by_participant = {p: by_lower.get(p.lower(), []) for p in all_p}
            missing_slots = [p for p, slots in slots_by_participant.items() if not slots]

            if missing_slots:
                # Some participants replied but we could not extract clear slots yet.
                await tools.send_gmail_message(
                    recipients=[session.organizer_email],
                    subject=f"Need more availability details — {meeting_title}",
                    body_text=(
                        f"All participants have responded for '{meeting_title}', but I couldn't extract "
                        f"specific time slots for: {', '.join(missing_slots)}.\n\n"
                        "Could you ask them to reply with explicit dates/times in IST?\n\n"
                        f"[calsync-ref:{session_id}]"
                    ),
                    thread_id="", session_id=session_id,
                )
                trace += f" Missing/unclear slots for {missing_slots}. Asked organizer to clarify."
            else:
                # Compute overlap
                overlapping = _compute_overlap(slots_by_participant, duration_minutes=60)
                logger.info("Overlap result: %s", overlapping)

                if overlapping:
                    # Check calendar availability for best slot
                    best = overlapping[0]
                    fb = await tools.check_freebusy(participants=all_p, slot=best)
                    fb_results = fb.payload.get("results", [])
                    slot_free = bool(fb_results and fb_results[0].get("is_free"))

                    if slot_free:
                        # BOOK IT
                        cal = await tools.book_calendar(
                            title=meeting_title,
                            participants=all_p,
                            slot=best,
                            organizer_email=organizer,
                            session_id=session_id,
                        )
                        if cal.status == "OK":
                            session.status = "BOOKED"
                            booked = cal.payload
                            bslot = booked.get("booked_slot", best)
                            meet_link = booked.get("meet_link", "")
                            event_link = booked.get("event_link", "")
                            calendar_invites = booked.get("invites_sent_to", [])
                            invite_set = {str(e).lower() for e in calendar_invites}
                            expected_set = {str(e).lower() for e in all_p}
                            missing_calendar_invites = [p for p in all_p if p.lower() not in invite_set]
                            start_str = _fmt_ist(str(bslot.get("start", "")))
                            end_str = _fmt_ist(str(bslot.get("end", "")))

                            confirm = (
                                f"Great news! '{meeting_title}' has been scheduled!\n\n"
                                f"📅 {start_str} – {end_str}\n"
                                f"🎥 Google Meet: {meet_link or 'See calendar invite'}\n"
                                f"📆 Calendar: {event_link or 'See calendar invite'}\n\n"
                                "You'll receive a Google Calendar invite shortly.\n\nCalSync.ai"
                            )
                            confirm_ok: list[str] = []
                            confirm_failed: list[str] = []
                            for p in all_p:
                                send_result = await tools.send_gmail_message(
                                    recipients=[p],
                                    subject=f"Meeting Confirmed: {meeting_title}",
                                    body_text=confirm,
                                    thread_id="", session_id=session_id,
                                )
                                if send_result.status == "OK":
                                    confirm_ok.append(p)
                                else:
                                    confirm_failed.append(p)

                            notified_recipients = list(confirm_ok)
                            logger.info(
                                "Post-book delivery session=%s calendar_invites=%s confirmations_ok=%s confirmations_failed=%s",
                                session_id,
                                calendar_invites,
                                confirm_ok,
                                confirm_failed,
                            )
                            if missing_calendar_invites:
                                logger.warning(
                                    "Calendar invite verification session=%s expected=%s got=%s missing=%s",
                                    session_id,
                                    sorted(expected_set),
                                    sorted(invite_set),
                                    missing_calendar_invites,
                                )

                            if confirm_failed:
                                trace += (
                                    f" Booked at {start_str}. Calendar invites: {calendar_invites}. "
                                    f"Confirmation emails OK for {confirm_ok}, failed for {confirm_failed}."
                                )
                            elif missing_calendar_invites:
                                trace += (
                                    f" Booked at {start_str}. Calendar invites missing for {missing_calendar_invites}. "
                                    "Confirmation emails sent to all participants."
                                )
                            else:
                                trace += (
                                    f" Booked at {start_str}. Calendar invites: {calendar_invites}. "
                                    f"Confirmation emails sent to all participants."
                                )
                        else:
                            trace += " Booking API failed."
                    else:
                        # Calendar busy despite overlap — ask for more
                        await _ask_for_more_slots(tools, all_p, session_id, meeting_title,
                            "The best overlapping time is already blocked on the calendar.")
                        session.status = "AWAITING_REPLIES"
                        replied = []
                        session.last_reminder_at = _now_iso()
                        trace += " Calendar conflict on best slot. Asked for alternatives."

                else:
                    # NO OVERLAP — ask everyone for more slots
                    collected_summary = "\n".join(
                        f"• {p}: " + (", ".join(
                            f"{_fmt_ist(s['start'])}–{_fmt_ist(s['end'])}" for s in slots
                        ) if slots else "no clear times provided")
                        for p, slots in collected.items()
                    )
                    no_overlap_msg = (
                        f"Hi,\n\nI wasn't able to find a common time for '{meeting_title}'.\n\n"
                        f"Availability received:\n{collected_summary}\n\n"
                        "Could everyone please share more available times? "
                        "Even 30 minutes of flexibility would help!\n\nCalSync.ai\n\n"
                        f"[calsync-ref:{session_id}]"
                    )
                    for p in all_p:
                        await tools.send_gmail_message(
                            recipients=[p],
                            subject=f"More Availability Needed — {meeting_title}",
                            body_text=no_overlap_msg,
                            thread_id="", session_id=session_id,
                        )
                    # Reset so everyone must reply again
                    replied = []
                    session.last_reminder_at = _now_iso()
                    session.status = "AWAITING_REPLIES"
                    trace += " No overlap. Asked all for more availability."

        else:
            # Some still pending — send reminder if cooldown passed
            if _cooldown_ok(session.last_reminder_at, settings.reminder_cooldown_minutes):
                replied_names = [r for r in replied if r.lower() != organizer]
                replied_str = ", ".join(replied_names) if replied_names else "no one yet"
                for p in pending:
                    await tools.send_gmail_message(
                        recipients=[p],
                        subject=f"Reminder: Share your availability — {meeting_title}",
                        body_text=(
                            f"Hi,\n\nThis is a reminder to share your availability for '{meeting_title}'.\n\n"
                            f"Already responded: {replied_str}\n\n"
                            "Please reply with your available dates and times (IST).\n\nCalSync.ai\n\n"
                            f"[calsync-ref:{session_id}]"
                        ),
                        thread_id="", session_id=session_id,
                    )
                session.last_reminder_at = _now_iso()
                trace += f" Reminder sent to {pending}."
            else:
                trace += " Cooldown active. No reminder."

    # ── Persist ───────────────────────────────────────────────────────────────
    if session.status != "BOOKED":
        session.status = "AWAITING_REPLIES" if pending else "READY_TO_COMPUTE"
    session.participants = all_p
    session.replied_participants = replied

    try:
        await thread_service.persist_state(session)
    except Exception as exc:
        logger.warning("Session persist failed: %s", exc)

    return AgentProcessResponse(agent_result=AgentResult(
        action_taken=action_taken,
        session_id=session_id,
        emails_sent_to=notified_recipients,
        reasoning_trace=trace,
    ))


async def _ask_for_more_slots(
    tools: CalsyncTools, participants: list, session_id: str, meeting_title: str, reason: str
) -> None:
    body = (
        f"Hi,\n\n{reason}\n\n"
        f"Could you please share additional available times for '{meeting_title}'?\n\nCalSync.ai\n\n"
        f"[calsync-ref:{session_id}]"
    )
    for p in participants:
        await tools.send_gmail_message(
            recipients=[p],
            subject=f"Alternative Times Needed — {meeting_title}",
            body_text=body,
            thread_id="", session_id=session_id,
        )