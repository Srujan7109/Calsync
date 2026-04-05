"""
thread_service.py — CalSync.ai Gmail MCP

Orchestrates Gmail thread fetching, Supabase storage, and AI-powered
thread summarisation.

Changes from v1:
  - _gmail_msg_to_email_record() now persists in_reply_to and
    references_header (RFC 2822 headers) to the emails table.
  - _generate_thread_summary() uses Gemini Flash to produce a 1–2 sentence
    plain-English summary of the thread.
  - fetch_and_store_thread() calls the summariser after storing all messages
    and writes the result to sessions.thread_summary via update_thread_summary().
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from gmail_client import get_thread
from models import EmailRecord, ThreadResponse
from supabase_ops import get_thread_emails, get_session_by_thread, store_email, update_thread_summary

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
    sender address (OUTBOUND). Now also maps in_reply_to and references_header
    from the parsed Gmail headers.

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
        # ── RFC 2822 threading headers (new) ──────────────────────────────
        in_reply_to=msg.get("in_reply_to") or None,
        references_header=msg.get("references") or None,
        # ─────────────────────────────────────────────────────────────────
        labels=msg.get("label_ids", []),
        processing_status="PENDING",
        email_hash=email_hash,
        is_read="UNREAD" not in msg.get("label_ids", []),
        has_attachments=msg.get("has_attachments", False),
        received_at=received_at,
        ingested_at=_utcnow(),
    )


def _generate_thread_summary(emails: List[EmailRecord]) -> Optional[str]:
    """
    Generate a 1–2 sentence plain-English thread summary using Gemini Flash.

    Builds a compact transcript from the stored email records (subject + first
    400 chars of body, per message) and sends it to Gemini with a tight
    instruction prompt. Falls back gracefully — returns None on any error
    (missing API key, quota exceeded, network failure, etc.) so the caller
    can continue without a summary.

    Args:
        emails: Chronologically ordered list of EmailRecord objects in the thread.

    Returns:
        str | None: 1–2 sentence summary, or None if generation failed.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("_generate_thread_summary: GEMINI_API_KEY not set — skipping.")
        return None

    if not emails:
        return None

    # Build a compact transcript (subject + truncated body per message)
    lines: List[str] = []
    for i, email in enumerate(emails, 1):
        role = "Participant → CalSync" if email.direction == "INBOUND" else "CalSync → Participant"
        body_preview = (email.body_text or "").strip()[:400]
        lines.append(
            f"[{i}] {role}\n"
            f"    From: {email.from_email}\n"
            f"    Subject: {email.subject}\n"
            f"    Body: {body_preview}"
        )
    transcript = "\n\n".join(lines)

    prompt = (
        "You are summarizing an email thread for a scheduling assistant dashboard.\n"
        "Write exactly 1–2 sentences. Be concrete — mention who, what meeting, "
        "current status, and any blockers. Do not use filler phrases.\n\n"
        f"Thread ({len(emails)} messages):\n{transcript}"
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=120,
            ),
        )
        summary = response.text.strip() if response.text else None
        logger.info("_generate_thread_summary: generated %d chars.", len(summary or ""))
        return summary
    except Exception as exc:
        logger.warning("_generate_thread_summary: Gemini call failed (non-fatal): %s", exc)
        return None


def fetch_and_store_thread(
    thread_id: str, session_id: Optional[str] = None
) -> ThreadResponse:
    """
    Fetch a Gmail thread, store all messages in Supabase, and generate a summary.

    Steps:
      1. Retrieve all messages via Gmail API (gmail_client.get_thread).
      2. Upsert each message into the `emails` table, including RFC 2822
         threading headers (in_reply_to, references_header).
      3. Generate a 1–2 sentence AI summary via Gemini Flash.
      4. If a session_id is provided (or can be looked up from thread_id),
         write the summary to sessions.thread_summary.
      5. Return a ThreadResponse with the summary populated.

    Args:
        thread_id: Gmail thread ID to fetch and store.
        session_id: Optional scheduling session UUID to associate with emails
            and for writing the summary. If not provided, the function
            attempts to look up the session from the sessions table.

    Returns:
        ThreadResponse: Contains thread_id, all stored EmailRecords, count,
        and the AI-generated summary (or None if generation failed).

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
                "fetch_and_store_thread: failed to store email %s in thread %s: %s",
                record.message_id,
                thread_id,
                exc,
            )
        email_records.append(record)

    # ── Generate thread summary ───────────────────────────────────────────────
    summary: Optional[str] = None
    if email_records:
        summary = _generate_thread_summary(email_records)

    # ── Persist summary to sessions.thread_summary ────────────────────────────
    if summary:
        # Resolve session_id if not passed directly
        resolved_session_id = session_id
        if not resolved_session_id:
            try:
                session = get_session_by_thread(thread_id)
                if session:
                    resolved_session_id = session.get("session_id")
            except Exception as exc:
                logger.warning(
                    "fetch_and_store_thread: could not look up session for thread %s: %s",
                    thread_id,
                    exc,
                )

        if resolved_session_id:
            try:
                update_thread_summary(resolved_session_id, summary)
            except Exception as exc:
                logger.warning(
                    "fetch_and_store_thread: update_thread_summary failed (non-fatal): %s",
                    exc,
                )
        else:
            logger.info(
                "fetch_and_store_thread: no session found for thread %s — "
                "summary generated but not persisted.",
                thread_id,
            )

    return ThreadResponse(
        thread_id=thread_id,
        emails=email_records,
        count=len(email_records),
        summary=summary,
    )


def get_thread_from_db(thread_id: str) -> ThreadResponse:
    """
    Retrieve all emails for a thread from Supabase (no Gmail API call).

    Also returns the thread summary from sessions.thread_summary if a session
    exists for this thread, so callers get the persisted summary without
    needing a separate query.

    Args:
        thread_id: Gmail thread ID to look up in Supabase.

    Returns:
        ThreadResponse: Contains stored emails and the persisted summary
        (or None if not yet generated).

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    rows = get_thread_emails(thread_id)
    email_records = [EmailRecord(**row) for row in rows]

    # Pull persisted summary from sessions table
    summary: Optional[str] = None
    try:
        session = get_session_by_thread(thread_id)
        if session:
            summary = session.get("thread_summary")
    except Exception as exc:
        logger.warning(
            "get_thread_from_db: could not fetch summary for thread %s: %s",
            thread_id,
            exc,
        )

    return ThreadResponse(
        thread_id=thread_id,
        emails=email_records,
        count=len(email_records),
        summary=summary,
    )


def detect_scheduling_keywords(subject: str, body: str) -> bool:
    """
    Fast keyword-based check to determine if an email is scheduling-related.

    Runs in < 1ms — no LLM call.

    Args:
        subject: Email subject line.
        body: Email body text. Only the first 200 characters are checked.

    Returns:
        bool: True if any scheduling keyword is found; False otherwise.
    """
    KEYWORDS = {
        "schedule", "meeting", "available", "availability", "sync",
        "call", "calendar", "time", "slot", "discuss", "standup",
        "stand-up", "touch base", "catch up", "invite", "appointment",
        "book", "confirm", "reschedule", "cancel",
    }
    combined = (subject + " " + body[:200]).lower()
    return any(kw in combined for kw in KEYWORDS)
