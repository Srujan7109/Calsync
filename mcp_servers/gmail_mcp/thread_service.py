"""
thread_service.py — CalSync.ai Gmail MCP

Orchestrates Gmail thread fetching, Supabase storage, and AI summarisation.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional

from gmail_client import get_thread
from models import EmailRecord, ThreadResponse
from supabase_ops import get_thread_emails, store_email
import llm_client

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _compute_email_hash(message_id: str, from_email: str, subject: str) -> str:
    """
    Compute a stable content hash for deduplication.

    Args:
        message_id: Gmail message ID.
        from_email: Sender email address.
        subject: Email subject line.

    Returns:
        str: MD5 hex digest used as the unique email_hash.
    """
    content = f"{message_id}:{from_email}:{subject}"
    return hashlib.md5(content.encode()).hexdigest()


def _gmail_msg_to_email_record(
    msg: dict, session_id: Optional[str] = None
) -> EmailRecord:
    """
    Convert a parsed Gmail message dict into an EmailRecord for Supabase storage.

    Infers direction as INBOUND unless the from_email matches the CalSync
    sender address (in which case it is OUTBOUND).

    Args:
        msg: Parsed message dict from gmail_client.get_thread().
        session_id: Optional scheduling session UUID to link.

    Returns:
        EmailRecord: Ready to pass to supabase_ops.store_email().
    """
    from config import settings

    direction = (
        "OUTBOUND"
        if settings.CALSYNC_EMAIL.lower() in msg.get("from_email", "").lower()
        else "INBOUND"
    )

    # Convert internalDate (millis epoch) to ISO 8601 UTC
    internal_date = msg.get("internal_date") or msg.get("internalDate")
    if internal_date:
        try:
            received_at = datetime.fromtimestamp(
                int(internal_date) / 1000, tz=timezone.utc
            ).isoformat()
        except (ValueError, TypeError):
            received_at = _utcnow()
    else:
        received_at = _utcnow()

    email_hash = _compute_email_hash(
        msg.get("gmail_message_id", ""),
        msg.get("from_email", ""),
        msg.get("subject", ""),
    )

    return EmailRecord(
        message_id=msg.get("gmail_message_id", ""),
        thread_id=msg.get("thread_id", ""),
        session_id=session_id,
        direction=direction,
        from_email=msg.get("from_email", ""),
        to_emails=msg.get("to_emails", []),
        cc_emails=msg.get("cc_emails", []),
        subject=msg.get("subject", ""),
        body_text=msg.get("body_text", ""),
        body_html=msg.get("body_html"),
        labels=msg.get("label_ids", []),
        processing_status="PENDING",
        email_hash=email_hash,
        is_read="UNREAD" not in msg.get("label_ids", []),
        has_attachments=msg.get("has_attachments", False),
        received_at=received_at,
        ingested_at=_utcnow(),
    )


def generate_thread_summary(emails: List[dict]) -> str:
    """
    Generate a short AI summary of a list of email dicts.

    Delegates to llm_client.summarise_thread() and wraps any failure
    with a fallback string.

    Args:
        emails: List of parsed email message dicts.

    Returns:
        str: 2-3 sentence plain-English summary of the scheduling thread.
    """
    try:
        return llm_client.summarise_thread(emails)
    except Exception as exc:
        logger.warning("generate_thread_summary failed: %s", exc)
        return f"{len(emails)} email(s) in thread. Summary unavailable."


def fetch_and_store_thread(
    thread_id: str, session_id: Optional[str] = None
) -> ThreadResponse:
    """
    Fetch a Gmail thread, store all messages in Supabase, and summarise it.

    Steps:
      1. Call gmail_client.get_thread() to retrieve all messages.
      2. Convert each message to an EmailRecord and upsert into Supabase.
      3. Generate an AI thread summary via llm_client.
      4. Return a ThreadResponse with all emails and the summary.

    Args:
        thread_id: Gmail thread ID to fetch and store.
        session_id: Optional scheduling session UUID to associate with the emails.

    Returns:
        ThreadResponse: Contains the thread_id, all stored EmailRecords,
        count, and an AI-generated summary.

    Raises:
        RuntimeError: If the Gmail API call or Supabase write fails.
    """
    messages = get_thread(thread_id)
    email_records: List[EmailRecord] = []

    for msg in messages:
        record = _gmail_msg_to_email_record(msg, session_id)
        try:
            stored_id = store_email(record)
            record.id = stored_id
        except Exception as exc:
            logger.error(
                "Failed to store email %s in thread %s: %s",
                record.message_id,
                thread_id,
                exc,
            )
        email_records.append(record)

    summary = generate_thread_summary(messages)

    return ThreadResponse(
        thread_id=thread_id,
        emails=email_records,
        count=len(email_records),
        summary=summary,
    )


def get_thread_from_db(thread_id: str) -> ThreadResponse:
    """
    Retrieve all emails for a thread from Supabase (no Gmail API call).

    Uses the locally stored data to build a ThreadResponse. Useful for
    fast lookups after the thread has already been fetched and stored.

    Args:
        thread_id: Gmail thread ID to look up in Supabase.

    Returns:
        ThreadResponse: Contains stored emails and a regenerated summary.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    rows = get_thread_emails(thread_id)
    email_records = [EmailRecord(**row) for row in rows]

    # Convert Supabase rows to the dict format expected by llm_client
    email_dicts = [
        {
            "from_email": r.from_email,
            "subject": r.subject,
            "body_text": r.body_text,
        }
        for r in email_records
    ]
    summary = generate_thread_summary(email_dicts) if email_dicts else None

    return ThreadResponse(
        thread_id=thread_id,
        emails=email_records,
        count=len(email_records),
        summary=summary,
    )


def detect_scheduling_keywords(subject: str, body: str) -> bool:
    """
    Fast keyword-based check to determine if an email is scheduling-related.

    Runs in < 1ms — no LLM call. Acts as the first-pass edge filter before
    running the more expensive LLM-based intent detection.

    Args:
        subject: Email subject line.
        body: Email body text. Only the first 200 characters are checked.

    Returns:
        bool: True if any scheduling keyword is found; False otherwise.
    """
    KEYWORDS = {
        "schedule",
        "meeting",
        "available",
        "availability",
        "sync",
        "call",
        "calendar",
        "time",
        "slot",
        "discuss",
        "standup",
        "stand-up",
        "touch base",
        "catch up",
        "invite",
        "appointment",
        "book",
        "confirm",
        "reschedule",
        "cancel",
    }
    # Search subject + first 200 chars of body, case-insensitive
    combined = (subject + " " + body[:200]).lower()
    return any(kw in combined for kw in KEYWORDS)
