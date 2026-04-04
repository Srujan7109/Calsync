"""
llm_client.py — CalSync.ai Gmail MCP

Single LLM abstraction layer. All AI calls go through this file.
Currently backed by Ollama (DeepSeek-R1:14b).

SWAPPING TO GEMINI LATER:
  - Replace _call_ollama() with a Gemini SDK call.
  - Add GEMINI_API_KEY to .env and config.py.
  - No other files need changes.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ── Internal: LLM backend call ───────────────────────────────────────────────


def _call_ollama(prompt: str, system: str) -> str:
    """
    Send a prompt to the Ollama API and return the generated text.

    Uses the model specified in settings.OLLAMA_MODEL (default: deepseek-r1:14b).
    Response is non-streaming; the full text is returned as a single string.

    Args:
        prompt: The user-facing prompt to send to the model.
        system: The system instruction that sets the model's behaviour.

    Returns:
        str: The model's generated text response.

    Raises:
        RuntimeError: If the Ollama server is unreachable or returns an error.
    """
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot connect to Ollama at {settings.OLLAMA_BASE_URL}. "
            "Is Ollama running? Try: ollama serve"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama call failed unexpectedly: {exc}") from exc


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


# ── Public LLM functions ──────────────────────────────────────────────────────


def summarise_thread(emails: List[dict]) -> str:
    """
    Generate a 2-3 sentence plain-English summary of an email thread.

    Focuses on scheduling status: who requested the meeting, who replied,
    what times were proposed, and what is still pending.

    Args:
        emails: List of parsed email dicts (each with from_email, subject,
                body_text, and date fields).

    Returns:
        str: A concise thread summary.

    Raises:
        RuntimeError: If the LLM call fails.
    """
    system = (
        "You are CalSync.ai, an AI scheduling assistant. "
        "Summarise this email thread in 2-3 sentences focusing on "
        "scheduling status: who requested the meeting, who has replied, "
        "what times were proposed, and what is still pending."
    )

    lines = []
    for i, email in enumerate(emails, start=1):
        preview = (email.get("body_text") or "")[:400].replace("\n", " ")
        lines.append(
            f"Email {i}:\n"
            f"  From: {email.get('from_email', 'unknown')}\n"
            f"  Subject: {email.get('subject', '(no subject)')}\n"
            f"  Body preview: {preview}"
        )
    prompt = "Please summarise this email thread:\n\n" + "\n\n".join(lines)

    try:
        return _call_ollama(prompt, system)
    except RuntimeError:
        logger.warning("LLM summarise_thread failed; returning fallback summary.")
        return f"{len(emails)} email(s) in thread. Unable to generate AI summary."


def detect_intent(subject: str, body_text: str) -> dict:
    """
    Classify the intent of an incoming email using the LLM.

    Returns a structured dict with intent type, confidence, reasoning,
    and any extracted scheduling data (proposed times, participants, etc.).

    Args:
        subject: Email subject line.
        body_text: Plain-text email body.

    Returns:
        dict: {
            intent: str (one of the IntentType values),
            confidence: float 0.0-1.0,
            reasoning: str,
            extracted_data: {
                proposed_times: List[str],
                mentioned_participants: List[str],
                requested_date_range: str | null
            }
        }

    On parse failure: returns AMBIGUOUS intent with 0.0 confidence.
    """
    system = (
        "You are an email intent classifier for CalSync.ai, an AI scheduling "
        "assistant. Classify the email intent and return ONLY valid JSON. "
        "Do not include any explanation outside the JSON."
    )
    prompt = f"""Classify this email and return valid JSON only:

Subject: {subject}
Body: {body_text[:1000]}

Return exactly this JSON structure:
{{
  "intent": "<one of: SCHEDULING_REQUEST | AVAILABILITY_REPLY | STATUS_QUERY | CANCELLATION_REQUEST | RESCHEDULE_REQUEST | AMBIGUOUS | OTHER>",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<one sentence explanation>",
  "extracted_data": {{
    "proposed_times": [],
    "mentioned_participants": [],
    "requested_date_range": null
  }}
}}"""

    fallback = {
        "intent": "AMBIGUOUS",
        "confidence": 0.0,
        "reasoning": "Failed to parse LLM response",
        "extracted_data": None,
    }

    try:
        raw = _call_ollama(prompt, system)
        cleaned = _strip_json_fences(raw)
        # Find the first JSON object in the response
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            logger.warning("detect_intent: no JSON object found in LLM response.")
            return fallback
        return json.loads(match.group())
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("detect_intent: JSON parse failed: %s", exc)
        return fallback
    except RuntimeError as exc:
        logger.error("detect_intent: LLM call failed: %s", exc)
        return fallback


def generate_availability_request_email(
    organizer: str,
    participants: List[str],
    meeting_title: str,
    deadline_hours: int = 48,
) -> dict:
    """
    Generate a professional availability request email using the LLM.

    The email asks participants to share their available time slots
    for a meeting, and includes a response deadline.

    Args:
        organizer: Name or email of the meeting organiser.
        participants: List of participant emails/names.
        meeting_title: Title or purpose of the meeting.
        deadline_hours: Hours within which participants should respond.

    Returns:
        dict: {subject: str, body_text: str, body_html: str}

    Raises:
        RuntimeError: If the LLM call fails.
    """
    system = (
        "You are CalSync.ai, a professional AI scheduling assistant. "
        "Write clear, polite, and concise scheduling emails."
    )
    participants_str = ", ".join(participants)
    prompt = f"""Write an availability request email for a meeting.

Meeting title: {meeting_title}
Organizer: {organizer}
Participants: {participants_str}
Response deadline: within {deadline_hours} hours

Requirements:
- Professional and friendly tone
- Clearly explain that CalSync.ai is coordinating this meeting on behalf of the organizer
- Ask recipients to reply with their available dates and times
- Mention the response deadline
- Keep it concise (under 150 words)

Return ONLY valid JSON with this structure:
{{
  "subject": "<email subject>",
  "body_text": "<plain text email body>",
  "body_html": "<HTML email body with basic formatting>"
}}"""

    try:
        raw = _call_ollama(prompt, system)
        cleaned = _strip_json_fences(raw)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("generate_availability_request_email LLM failed: %s", exc)

    # Fallback: static template
    subject = f"Scheduling Request: {meeting_title}"
    body_text = (
        f"Hi,\n\n"
        f"I'm CalSync.ai, an AI scheduling assistant coordinating on behalf of {organizer}.\n\n"
        f"We'd like to schedule a meeting: **{meeting_title}**.\n"
        f"Please reply with your available dates and times within the next {deadline_hours} hours.\n\n"
        f"Thank you!"
    )
    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_text.replace("\n", "<br>"),
    }


def generate_clarification_email(
    participant: str,
    original_text: str,
    ambiguous_part: str,
) -> dict:
    """
    Generate a polite clarification email for an ambiguous availability reply.

    Args:
        participant: Name or email of the participant to contact.
        original_text: The original reply text that needs clarification.
        ambiguous_part: The specific part of the reply that is unclear.

    Returns:
        dict: {subject: str, body_text: str}

    Raises:
        RuntimeError: If the LLM call fails.
    """
    system = (
        "You are CalSync.ai, a polite and professional AI scheduling assistant. "
        "Write concise clarification emails."
    )
    prompt = f"""Write a short, polite clarification email.

Participant: {participant}
Their original message: {original_text[:500]}
What needs clarification: {ambiguous_part}

Requirements:
- Be concise and friendly
- Quote the ambiguous part
- Ask specifically what is unclear
- Under 80 words

Return ONLY valid JSON:
{{
  "subject": "<subject line>",
  "body_text": "<plain text body>"
}}"""

    try:
        raw = _call_ollama(prompt, system)
        cleaned = _strip_json_fences(raw)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("generate_clarification_email LLM failed: %s", exc)

    # Fallback
    return {
        "subject": "Quick Clarification Needed",
        "body_text": (
            f"Hi {participant},\n\nThank you for your reply! "
            f"Could you please clarify: {ambiguous_part}\n\n"
            f"Your original message: \"{original_text[:200]}\"\n\n"
            "CalSync.ai"
        ),
    }


def generate_booking_confirmation_email(
    participants: List[str],
    meeting_title: str,
    booked_slot: dict,
    event_link: str,
    meet_link: Optional[str],
    organizer_timezone: str = "UTC",
) -> dict:
    """
    Generate a meeting booking confirmation email with full event details.

    Args:
        participants: List of participant emails.
        meeting_title: Title of the meeting.
        booked_slot: Dict with 'start' and 'end' ISO 8601 UTC strings.
        event_link: Google Calendar event URL.
        meet_link: Google Meet video call link (optional).
        organizer_timezone: Timezone label to display (default "UTC").

    Returns:
        dict: {subject: str, body_text: str, body_html: str}

    Raises:
        RuntimeError: If the LLM call fails.
    """
    system = (
        "You are CalSync.ai, an AI scheduling assistant. "
        "Write professional meeting confirmation emails."
    )
    participants_str = ", ".join(participants)
    start = booked_slot.get("start", "TBD")
    end = booked_slot.get("end", "TBD")

    prompt = f"""Write a meeting confirmation email.

Meeting title: {meeting_title}
Participants: {participants_str}
Start time (UTC): {start}
End time (UTC): {end}
Timezone displayed: {organizer_timezone}
Google Calendar event: {event_link}
Google Meet link: {meet_link or "Not provided"}

Requirements:
- Warm, professional tone
- Include all meeting details clearly
- Mention the calendar event link and Meet link if available
- Under 200 words

Return ONLY valid JSON:
{{
  "subject": "<subject>",
  "body_text": "<plain text body>",
  "body_html": "<HTML body with formatting>"
}}"""

    try:
        raw = _call_ollama(prompt, system)
        cleaned = _strip_json_fences(raw)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("generate_booking_confirmation_email LLM failed: %s", exc)

    # Fallback
    subject = f"Meeting Confirmed: {meeting_title}"
    body_text = (
        f"Hi,\n\nYour meeting has been confirmed!\n\n"
        f"📅 {meeting_title}\n"
        f"🕐 {start} → {end} ({organizer_timezone})\n"
        f"📅 Calendar Event: {event_link}\n"
    )
    if meet_link:
        body_text += f"🎥 Google Meet: {meet_link}\n"
    body_text += "\nSee you then!\n\nCalSync.ai"

    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_text.replace("\n", "<br>"),
    }
