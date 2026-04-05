"""
supabase_ops.py — CalSync.ai Gmail MCP

All Supabase database operations.
Uses the service role key to bypass Row Level Security.
This is the single access layer between the application and Supabase.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from supabase import create_client, Client

from config import settings
from models import DraftCreateRequest, EmailRecord, LogRequest

logger = logging.getLogger(__name__)

# ── Supabase client (singleton) ──────────────────────────────────────────────
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utcnow() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── emails table ─────────────────────────────────────────────────────────────


def store_email(email: EmailRecord) -> str:
    """
    Upsert an email record into the `emails` table.

    Uses conflict resolution on `email_hash` to prevent duplicates on retries.

    Args:
        email: EmailRecord — the email to store.

    Returns:
        str: The UUID `id` of the stored (inserted or updated) record.

    Raises:
        RuntimeError: If the Supabase operation fails.
    """
    payload = email.model_dump(exclude={"id"})

    try:
        response = (
            supabase.table("emails")
            .upsert(payload, on_conflict="email_hash")
            .execute()
        )
        if response.data:
            return response.data[0]["id"]
        raise RuntimeError("Supabase returned empty data after upsert.")
    except Exception as exc:
        logger.error("store_email failed: %s", exc)
        raise RuntimeError(f"store_email failed: {exc}") from exc


def get_email_by_message_id(message_id: str) -> Optional[dict]:
    """
    Retrieve a single email record by its Gmail message ID.

    Args:
        message_id: The Gmail message ID (not the Supabase UUID).

    Returns:
        dict | None: The email record dict, or None if not found.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        response = (
            supabase.table("emails")
            .select("*")
            .eq("message_id", message_id)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as exc:
        logger.error("get_email_by_message_id failed: %s", exc)
        raise RuntimeError(f"get_email_by_message_id failed: {exc}") from exc


def get_thread_emails(thread_id: str) -> List[dict]:
    """
    Retrieve all emails belonging to a Gmail thread, sorted chronologically.

    Args:
        thread_id: The Gmail thread ID.

    Returns:
        List[dict]: List of email records ordered by `received_at` ASC.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        response = (
            supabase.table("emails")
            .select("*")
            .eq("thread_id", thread_id)
            .order("received_at", desc=False)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        logger.error("get_thread_emails failed: %s", exc)
        raise RuntimeError(f"get_thread_emails failed: {exc}") from exc


def get_outbound_emails_for_session(
    session_id: str,
    intent_type: Optional[str] = None,
) -> List[dict]:
    """
    Return OUTBOUND emails already sent for this scheduling session.

    Used to deduplicate — if the agent is called twice for the same session
    (e.g. a webhook fires twice), we skip re-sending the same email.

    Args:
        session_id: The CalSync session UUID.
        intent_type: Optional keyword to match in the subject for a finer
            check ('confirm', 'available', 'clarif'). If None, returns all
            outbound emails for the session.

    Returns:
        List[dict]: Matching OUTBOUND email records (empty list = none sent yet).

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        query = (
            supabase.table("emails")
            .select("id, subject, received_at")
            .eq("session_id", session_id)
            .eq("direction", "OUTBOUND")
        )
        if intent_type:
            query = query.ilike("subject", f"%{intent_type}%")
        response = query.order("received_at", desc=False).execute()
        return response.data or []
    except Exception as exc:
        logger.error("get_outbound_emails_for_session failed: %s", exc)
        raise RuntimeError(f"get_outbound_emails_for_session failed: {exc}") from exc



def update_email_status(
    message_id: str,
    status: str,
    error: Optional[str] = None,
    processed_at: Optional[str] = None,
) -> None:
    """
    Update the processing status of an email record.

    Args:
        message_id: The Gmail message ID of the email to update.
        status: New processing status (PENDING/PROCESSING/DONE/FAILED/…).
        error: Optional error description if status is FAILED.
        processed_at: ISO 8601 UTC timestamp when processing completed.

    Raises:
        RuntimeError: If the Supabase update fails.
    """
    payload: dict = {
        "processing_status": status,
        "processing_error": error,
        "processed_at": processed_at or (_utcnow() if status == "DONE" else None),
    }
    # Don't send None for processed_at when status is not terminal
    if status not in ("DONE", "FAILED"):
        payload.pop("processed_at", None)

    try:
        supabase.table("emails").update(payload).eq(
            "message_id", message_id
        ).execute()
    except Exception as exc:
        logger.error("update_email_status failed: %s", exc)
        raise RuntimeError(f"update_email_status failed: {exc}") from exc


# ── email_drafts table ───────────────────────────────────────────────────────


def store_draft(
    draft: DraftCreateRequest, gmail_draft_id: Optional[str]
) -> str:
    """
    Insert a new email draft record into the `email_drafts` table.

    Args:
        draft: DraftCreateRequest — the draft metadata to store.
        gmail_draft_id: The draft ID returned by the Gmail API (may be None).

    Returns:
        str: The UUID `id` of the newly inserted draft record.

    Raises:
        RuntimeError: If the Supabase insert fails.
    """
    now = _utcnow()
    payload = {
        "gmail_draft_id": gmail_draft_id,
        "session_id": draft.session_id,
        "thread_id": draft.thread_id,
        "to_emails": draft.to_emails,
        "subject": draft.subject,
        "body_text": draft.body_text,
        "body_html": draft.body_html,
        "draft_reason": draft.draft_reason,
        "status": "PENDING_REVIEW",
        "created_at": now,
        "updated_at": now,
    }

    try:
        response = supabase.table("email_drafts").insert(payload).execute()
        if response.data:
            return response.data[0]["id"]
        raise RuntimeError("Supabase returned empty data after draft insert.")
    except Exception as exc:
        logger.error("store_draft failed: %s", exc)
        raise RuntimeError(f"store_draft failed: {exc}") from exc


def update_draft_status(
    draft_id: str, action: str, reviewed_by: Optional[str]
) -> None:
    """
    Update the status of an email draft after a review action.

    Args:
        draft_id: Supabase UUID of the draft to update.
        action: New status — one of APPROVED / SENT / DISCARDED.
        reviewed_by: Identifier of the person/agent who reviewed the draft.

    Raises:
        RuntimeError: If the Supabase update fails.
    """
    payload = {
        "status": action,
        "reviewed_by": reviewed_by,
        "reviewed_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    if action == "SENT":
        payload["sent_at"] = _utcnow()

    try:
        supabase.table("email_drafts").update(payload).eq("id", draft_id).execute()
    except Exception as exc:
        logger.error("update_draft_status failed: %s", exc)
        raise RuntimeError(f"update_draft_status failed: {exc}") from exc


def get_pending_drafts() -> List[dict]:
    """
    Retrieve all draft records with status PENDING_REVIEW.

    Returns:
        List[dict]: List of pending draft records.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        response = (
            supabase.table("email_drafts")
            .select("*")
            .eq("status", "PENDING_REVIEW")
            .order("created_at", desc=False)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        logger.error("get_pending_drafts failed: %s", exc)
        raise RuntimeError(f"get_pending_drafts failed: {exc}") from exc


def get_draft_by_id(draft_id: str) -> Optional[dict]:
    """
    Retrieve a single draft record by Supabase UUID.

    Args:
        draft_id: Supabase UUID of the draft.

    Returns:
        dict | None: Draft record or None if not found.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        response = (
            supabase.table("email_drafts")
            .select("*")
            .eq("id", draft_id)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as exc:
        logger.error("get_draft_by_id failed: %s", exc)
        raise RuntimeError(f"get_draft_by_id failed: {exc}") from exc


# ── sessions table ───────────────────────────────────────────────────────────


def get_session_by_thread(thread_id: str) -> Optional[dict]:
    """
    Retrieve the scheduling session associated with a Gmail thread.

    Args:
        thread_id: The Gmail thread ID to look up.

    Returns:
        dict | None: Session record or None if not found.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        response = (
            supabase.table("sessions")
            .select("*")
            .eq("thread_id", thread_id)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as exc:
        logger.error("get_session_by_thread failed: %s", exc)
        raise RuntimeError(f"get_session_by_thread failed: {exc}") from exc


def update_thread_summary(session_id: str, summary: str) -> None:
    """
    Write an AI-generated thread summary to sessions.thread_summary.

    Also appends a THREAD_SUMMARISED entry to activity_logs so the dashboard
    can show when the summary was last generated.

    Args:
        session_id: The CalSync session UUID whose summary should be updated.
        summary: Plain-English summary produced by the LLM.

    Raises:
        RuntimeError: If the Supabase update fails.
    """
    try:
        supabase.table("sessions").update(
            {"thread_summary": summary, "updated_at": _utcnow()}
        ).eq("session_id", session_id).execute()
        logger.info("update_thread_summary: session %s summary written.", session_id)
    except Exception as exc:
        logger.error("update_thread_summary failed: %s", exc)
        raise RuntimeError(f"update_thread_summary failed: {exc}") from exc

    # Log the event — non-fatal if it fails
    try:
        write_activity_log(
            LogRequest(
                session_id=session_id,
                event_type="THREAD_SUMMARISED",
                severity="INFO",
                description="Thread summary generated and stored.",
                payload={"summary_length": len(summary)},
                actor="AGENT",
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("update_thread_summary: activity log write failed (non-fatal): %s", exc)



# ── activity_logs table ──────────────────────────────────────────────────────


def write_activity_log(log: LogRequest) -> None:
    """
    Append an entry to the `activity_logs` table.

    Args:
        log: LogRequest — the log entry to write.

    Raises:
        RuntimeError: If the Supabase insert fails.
    """
    payload = {
        "session_id": log.session_id,
        "email_id": log.email_id,
        "event_type": log.event_type,
        "severity": log.severity,
        "description": log.description,
        "payload": log.payload,
        "actor": log.actor,
        "created_at": _utcnow(),
    }
    try:
        supabase.table("activity_logs").insert(payload).execute()
    except Exception as exc:
        # Logs must never crash the caller — just log locally
        logger.error("write_activity_log failed (non-fatal): %s", exc)


# ── app_settings table ───────────────────────────────────────────────────────


def get_app_setting(key: str) -> Optional[Any]:
    """
    Retrieve a setting value from the `app_settings` table.

    Args:
        key: The setting key to look up.

    Returns:
        The parsed jsonb value, or None if the key is not found.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        response = (
            supabase.table("app_settings")
            .select("value")
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        if response.data:
            return response.data.get("value")
        return None
    except Exception as exc:
        logger.error("get_app_setting failed: %s", exc)
        raise RuntimeError(f"get_app_setting failed: {exc}") from exc


# ── gmail_watch_subscriptions table ──────────────────────────────────────────


def upsert_gmail_watch(
    profile_id: str,
    gmail_address: str,
    pubsub_topic: str,
    history_id: str,
    expires_at: str,
) -> None:
    """
    Upsert a Gmail watch subscription record.

    Args:
        profile_id: UUID of the profile that owns this watch.
        gmail_address: The Gmail address being watched.
        pubsub_topic: The Pub/Sub topic receiving push notifications.
        history_id: The Gmail historyId returned by watch().
        expires_at: ISO 8601 UTC expiry time of the watch subscription.

    Raises:
        RuntimeError: If the Supabase upsert fails.
    """
    now = _utcnow()
    payload = {
        "profile_id": profile_id,
        "gmail_address": gmail_address,
        "pubsub_topic": pubsub_topic,
        "history_id": history_id,
        "expires_at": expires_at,
        "is_active": True,
        "last_renewed_at": now,
        "created_at": now,
    }
    try:
        supabase.table("gmail_watch_subscriptions").upsert(
            payload, on_conflict="gmail_address"
        ).execute()
    except Exception as exc:
        logger.error("upsert_gmail_watch failed: %s", exc)
        raise RuntimeError(f"upsert_gmail_watch failed: {exc}") from exc


def get_active_watch() -> Optional[dict]:
    """
    Retrieve the active Gmail watch subscription for the CalSync email address.

    Returns:
        dict | None: The active watch record, or None if no active watch exists.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        response = (
            supabase.table("gmail_watch_subscriptions")
            .select("*")
            .eq("gmail_address", settings.CALSYNC_EMAIL)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as exc:
        logger.error("get_active_watch failed: %s", exc)
        raise RuntimeError(f"get_active_watch failed: {exc}") from exc
