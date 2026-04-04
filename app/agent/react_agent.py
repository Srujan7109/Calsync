from __future__ import annotations

import asyncio
import json
import logging
import uuid
from importlib import import_module
from typing import Any

from app.agent.prompts import AGENT_ANALYSIS_PROMPT
from app.agent.tools import CalsyncTools
from app.config import get_settings
from app.models.agent_models import AgentProcessResponse, AgentResult
from app.models.email_models import AgentProcessPayload


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
        body=payload.body_text[:2000],
    )
    client = gemini_module.Client(api_key=settings.gemini_api_key)
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=settings.gemini_model,
        contents=prompt,
    )
    output_text = getattr(response, "text", "") or ""
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

    analysis = await _analyze_email_with_gemini(payload)
    action = str(analysis.get("action") or "NO_ACTION")
    reasoning_trace = str(analysis.get("reasoning_trace") or "Thought: no-op.")
    meeting_title = str(analysis.get("title") or payload.subject or "Meeting coordination")
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    recipients = payload.participants

    logger.info(
        "Agent execution session_id=%s action=%s subject=%s recipients=%s",
        session_id,
        action,
        payload.subject,
        len(recipients),
    )

    if action == "SENT_AVAILABILITY_REQUEST":
        request_body = str(
            analysis.get("request_email_body")
            or "Thanks for reaching out. Please share your preferred time slots and timezone so I can coordinate."
        )
        gmail_outcome = await tools.send_gmail_message(
            recipients=recipients,
            subject=f"Re: {payload.subject}" if payload.subject else "Meeting coordination",
            body_text=request_body,
            thread_id=payload.thread_id,
        )
        reasoning_trace = f"{reasoning_trace} Tool: send_gmail_message={gmail_outcome.status}."

    elif action == "BOOKED_CALENDAR":
        slot = analysis.get("slot") if isinstance(analysis.get("slot"), dict) else {}
        calendar_slot = {
            "start": str(slot.get("start_iso") or ""),
            "end": str(slot.get("end_iso") or ""),
            "timezone": str(slot.get("timezone") or "UTC"),
        }
        calendar_outcome = await tools.book_calendar(
            title=meeting_title,
            participants=recipients,
            slot=calendar_slot,
        )
        reasoning_trace = f"{reasoning_trace} Tool: book_calendar={calendar_outcome.status}."

        confirmation_body = (
            "Your meeting has been coordinated and added to the calendar. "
            f"Slot: {calendar_slot['start']} to {calendar_slot['end']} ({calendar_slot['timezone']})."
        )
        gmail_outcome = await tools.send_gmail_message(
            recipients=recipients,
            subject=f"Calendar confirmed: {meeting_title}",
            body_text=confirmation_body,
            thread_id=payload.thread_id,
        )
        reasoning_trace = f"{reasoning_trace} Tool: send_gmail_message={gmail_outcome.status}."

    return AgentProcessResponse(
        agent_result=AgentResult(
            action_taken=action,
            session_id=session_id,
            emails_sent_to=recipients,
            reasoning_trace=reasoning_trace,
        )
    )
