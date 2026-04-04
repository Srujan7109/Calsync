"""
intent_detector.py — CalSync.ai Gmail MCP (no LLM)

Pure keyword-based intent classifier.
No Ollama, no external calls — fast deterministic string matching only.
"""

from __future__ import annotations

import logging
import re

from models import IntentDetectionRequest, IntentDetectionResponse
from thread_service import detect_scheduling_keywords

logger = logging.getLogger(__name__)

# ── Keyword sets per intent ────────────────────────────────────────────────────

_SCHEDULING_KEYWORDS = [
    "schedule", "meeting", "set up", "arrange", "book", "sync",
    "let's meet", "lets meet", "set a meeting", "plan a call",
]

_AVAILABILITY_KEYWORDS = [
    "available", "free", "works for me", "can do", "how about",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "am free", "not free", "i'm free",
    "works", "that works", "any time", "anytime", "open",
    "i can do", "would work", "suits me", "prefer",
]

_STATUS_KEYWORDS = [
    "status", "update", "booked", "confirmed", "scheduled yet",
    "any update", "has it been", "did you", "have you",
]

_CANCELLATION_KEYWORDS = [
    "cancel", "cancelling", "canceling", "cannot make it",
    "can't make it", "wont be able", "won't be able", "unable to attend",
    "need to cancel", "pulling out",
]

_RESCHEDULE_KEYWORDS = [
    "reschedule", "move the meeting", "change the time", "different time",
    "push the meeting", "postpone", "delay", "shift",
]

# Time patterns like 9am, 9:30am, 14:00, 2pm etc.
_TIME_PATTERN = re.compile(
    r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b",
    re.IGNORECASE,
)


def _keyword_classify(subject: str, body_text: str) -> str:
    """
    Classify intent using ordered keyword matching.

    Priority order: CANCELLATION → RESCHEDULE → AVAILABILITY_REPLY →
    STATUS_QUERY → SCHEDULING_REQUEST → AMBIGUOUS

    Args:
        subject: Email subject line.
        body_text: Plain-text email body.

    Returns:
        str: One of the IntentType literal values.
    """
    combined = (subject + " " + body_text).lower()

    if any(kw in combined for kw in _CANCELLATION_KEYWORDS):
        return "CANCELLATION_REQUEST"

    if any(kw in combined for kw in _RESCHEDULE_KEYWORDS):
        return "RESCHEDULE_REQUEST"

    if any(kw in combined for kw in _STATUS_KEYWORDS):
        return "STATUS_QUERY"

    # AVAILABILITY_REPLY: needs at least 2 signals (a keyword + time/day OR two keywords)
    av_hits = sum(1 for kw in _AVAILABILITY_KEYWORDS if kw in combined)
    has_time = bool(_TIME_PATTERN.search(combined))
    if av_hits >= 2 or (av_hits >= 1 and has_time):
        return "AVAILABILITY_REPLY"

    if any(kw in combined for kw in _SCHEDULING_KEYWORDS):
        return "SCHEDULING_REQUEST"

    return "AMBIGUOUS"


def detect_email_intent(req: IntentDetectionRequest) -> IntentDetectionResponse:
    """
    Classify the intent of an incoming email using pure keyword matching.

    No LLM calls. Two-stage guard:
      Stage 1: quick scheduling keyword check — if none found, return OTHER.
      Stage 2: ordered keyword classifier for specific intents.

    Args:
        req: IntentDetectionRequest with subject and body_text.

    Returns:
        IntentDetectionResponse: {intent, confidence=0.90, reasoning, extracted_data=None}
    """
    # Stage 1: broad scheduling guard
    if not detect_scheduling_keywords(req.subject, req.body_text):
        return IntentDetectionResponse(
            intent="OTHER",
            confidence=0.99,
            reasoning="No scheduling keywords found in subject or body.",
            extracted_data=None,
        )

    # Stage 2: specific intent classification
    intent = _keyword_classify(req.subject, req.body_text)

    return IntentDetectionResponse(
        intent=intent,
        confidence=0.90,
        reasoning="keyword match",
        extracted_data=None,
    )


def is_availability_reply(body_text: str) -> bool:
    """
    Quick heuristic check to determine if an email is an availability reply.

    Args:
        body_text: Plain-text email body to analyse.

    Returns:
        bool: True if the body matches common availability reply patterns.
    """
    text = body_text.lower()
    has_time = bool(_TIME_PATTERN.search(text))

    day_pattern = re.compile(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|wed|thu|fri|sat|sun)\b",
        re.IGNORECASE,
    )
    has_day = bool(day_pattern.search(text))
    has_phrase = any(kw in text for kw in _AVAILABILITY_KEYWORDS)

    signal_count = sum([has_time, has_day, has_phrase])
    return signal_count >= 2
