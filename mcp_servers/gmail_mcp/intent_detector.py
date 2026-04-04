"""
intent_detector.py — CalSync.ai Gmail MCP

Orchestrates intent detection with a two-stage pipeline:
  Stage 1: Fast keyword check (< 1ms, no LLM)
  Stage 2: LLM classification via llm_client.detect_intent()
"""

from __future__ import annotations

import logging
import re

import llm_client
from models import IntentDetectionRequest, IntentDetectionResponse
from thread_service import detect_scheduling_keywords

logger = logging.getLogger(__name__)


def detect_email_intent(req: IntentDetectionRequest) -> IntentDetectionResponse:
    """
    Classify the intent of an incoming email using a two-stage pipeline.

    Stage 1 (fast): Run keyword detection on subject + body. If no
    scheduling keywords are found, immediately return intent=OTHER
    with high confidence — no LLM call needed.

    Stage 2 (LLM): Call llm_client.detect_intent() to classify the
    email and extract structured scheduling data.

    Args:
        req: IntentDetectionRequest with subject and body_text.

    Returns:
        IntentDetectionResponse: Intent type, confidence, reasoning,
        and any extracted scheduling data.
    """
    # Stage 1: keyword guard
    has_keywords = detect_scheduling_keywords(req.subject, req.body_text)
    if not has_keywords:
        logger.debug("intent: no keywords found → returning OTHER")
        return IntentDetectionResponse(
            intent="OTHER",
            confidence=0.99,
            reasoning="No scheduling keywords found in subject or body.",
            extracted_data=None,
        )

    # Stage 2: LLM classification
    try:
        result = llm_client.detect_intent(req.subject, req.body_text)
        return IntentDetectionResponse(
            intent=result.get("intent", "AMBIGUOUS"),
            confidence=float(result.get("confidence", 0.5)),
            reasoning=result.get("reasoning", ""),
            extracted_data=result.get("extracted_data"),
        )
    except Exception as exc:
        logger.error("detect_email_intent LLM stage failed: %s", exc)
        return IntentDetectionResponse(
            intent="AMBIGUOUS",
            confidence=0.0,
            reasoning=f"LLM intent detection failed: {exc}",
            extracted_data=None,
        )


def is_availability_reply(body_text: str) -> bool:
    """
    Quick heuristic check to determine if an email is an availability reply.

    Detects common patterns like time expressions (9am, 14:00), day names,
    and phrases like "I'm free", "works for me", etc. Used to shortcut the
    LLM call when the reply is obviously an availability response.

    Args:
        body_text: Plain-text email body to analyse.

    Returns:
        bool: True if the body matches common availability reply patterns.
    """
    text = body_text.lower()

    # Time patterns: 9am, 2pm, 14:00, 9:30am, etc.
    time_pattern = re.compile(
        r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b",
        re.IGNORECASE,
    )

    # Day name patterns
    day_pattern = re.compile(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|wed|thu|fri|sat|sun)\b",
        re.IGNORECASE,
    )

    # Availability phrases
    availability_phrases = [
        "free",
        "available",
        "works for me",
        "can do",
        "how about",
        "i'm open",
        "i am open",
        "let's do",
        "let me know",
        "suits me",
        "that works",
        "sounds good",
        "anytime",
        "prefer",
        "would work",
    ]

    has_time = bool(time_pattern.search(text))
    has_day = bool(day_pattern.search(text))
    has_phrase = any(phrase in text for phrase in availability_phrases)

    # Must have at least two signals to be considered an availability reply
    signal_count = sum([has_time, has_day, has_phrase])
    return signal_count >= 2
