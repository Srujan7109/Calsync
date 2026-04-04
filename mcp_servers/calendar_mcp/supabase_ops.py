"""
supabase_ops.py — CalSync.ai Calendar MCP

All Supabase database operations for the Calendar MCP.
Uses the service role key to bypass Row Level Security.
Supabase writes are best-effort — failures are logged but do NOT crash callers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from supabase import Client, create_client

from config import settings
from models import LogRequest

logger = logging.getLogger(__name__)

# ── Supabase client (singleton) ───────────────────────────────────────────────
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)


def _utcnow() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── booked_meetings table ─────────────────────────────────────────────────────


def store_booked_meeting(
    session_id: str,
    event_id: str,
    event_link: str,
    meet_link: Optional[str],
    title: str,
    description: str,
    start_time: str,
    end_time: str,
    organizer_email: str,
    attendee_emails: List[str],
    slot_index_used: int,
    fallback_used: bool,
) -> str:
    """
    Upsert a booked meeting record into the `booked_meetings` table.

    Uses ON CONFLICT session_id to handle retries safely. Initialises
    attendee_statuses as {email: 'needsAction'} for all attendees.

    Args:
        session_id: Scheduling session UUID linking this booking to the session.
        event_id: Google Calendar event ID.
        event_link: URL to the Google Calendar event.
        meet_link: Google Meet video URL (None if not generated).
        title: Meeting title.
        description: Meeting description.
        start_time: ISO 8601 UTC start time string.
        end_time: ISO 8601 UTC end time string.
        organizer_email: Email of the meeting organiser.
        attendee_emails: All attendee email addresses.
        slot_index_used: Index of the slot that was booked (0 = primary).
        fallback_used: True if a fallback slot was used.

    Returns:
        str: Supabase UUID `id` of the stored record.

    Raises:
        RuntimeError: If the Supabase upsert fails.
    """
    now = _utcnow()
    attendee_statuses = {email: "needsAction" for email in attendee_emails}

    payload = {
        "session_id": session_id,
        "event_id": event_id,
        "event_link": event_link,
        "meet_link": meet_link,
        "title": title,
        "description": description,
        "start_time": start_time,
        "end_time": end_time,
        "organizer_email": organizer_email,
        "attendee_emails": attendee_emails,
        "attendee_statuses": attendee_statuses,
        "slot_index_used": slot_index_used,
        "fallback_used": fallback_used,
        "is_cancelled": False,
        "is_rescheduled": False,
        "created_at": now,
        "updated_at": now,
    }

    try:
        response = (
            supabase.table("booked_meetings")
            .upsert(payload, on_conflict="session_id")
            .execute()
        )
        if response.data:
            return response.data[0]["id"]
        raise RuntimeError("Supabase returned empty data after upsert.")
    except Exception as exc:
        logger.error("store_booked_meeting failed: %s", exc)
        raise RuntimeError(f"store_booked_meeting failed: {exc}") from exc


def store_meeting_attendees(
    meeting_id: str,
    attendees: List[str],
    organizer_email: str,
) -> None:
    """
    Insert attendee rows into the `meeting_attendees` table.

    Uses ON CONFLICT (meeting_id, email) DO NOTHING to prevent duplicate rows
    on retries. Sets is_organizer = True for the organizer_email.

    Args:
        meeting_id: Supabase UUID of the booked_meetings record.
        attendees: All attendee email addresses (including organiser).
        organizer_email: The organiser's email address.
    """
    now = _utcnow()
    rows = [
        {
            "meeting_id": meeting_id,
            "email": email,
            "rsvp_status": "needsAction",
            "is_organizer": email.lower() == organizer_email.lower(),
            "updated_at": now,
        }
        for email in attendees
    ]
    try:
        supabase.table("meeting_attendees").upsert(
            rows, on_conflict="meeting_id,email", ignore_duplicates=True
        ).execute()
    except Exception as exc:
        logger.warning("store_meeting_attendees failed (non-fatal): %s", exc)


def update_meeting_cancelled(event_id: str, reason: str) -> None:
    """
    Mark a booked meeting as cancelled in Supabase.

    Sets is_cancelled = True, cancelled_at = now(), and stores the reason.

    Args:
        event_id: Google Calendar event ID of the meeting to cancel.
        reason: Human-readable cancellation reason.
    """
    try:
        supabase.table("booked_meetings").update(
            {
                "is_cancelled": True,
                "cancelled_at": _utcnow(),
                "cancellation_reason": reason,
                "updated_at": _utcnow(),
            }
        ).eq("event_id", event_id).execute()
    except Exception as exc:
        logger.warning("update_meeting_cancelled failed (non-fatal): %s", exc)


def update_meeting_rescheduled(old_event_id: str, new_meeting_id: str) -> None:
    """
    Mark an old meeting as rescheduled and link it to the new one.

    Updates is_rescheduled = True and rescheduled_to = new_meeting_id.

    Args:
        old_event_id: Google Calendar event ID of the original meeting.
        new_meeting_id: Supabase UUID of the replacement booked_meetings record.
    """
    try:
        supabase.table("booked_meetings").update(
            {
                "is_rescheduled": True,
                "rescheduled_to": new_meeting_id,
                "updated_at": _utcnow(),
            }
        ).eq("event_id", old_event_id).execute()
    except Exception as exc:
        logger.warning("update_meeting_rescheduled failed (non-fatal): %s", exc)


def update_session_booking(
    session_id: str,
    event_id: str,
    event_link: str,
    meet_link: Optional[str],
    booked_slot: dict,
) -> None:
    """
    Update the sessions table after a successful booking.

    Sets status = 'BOOKED' and persists all booking details.

    Args:
        session_id: The scheduling session to update.
        event_id: Google Calendar event ID.
        event_link: URL to the Google Calendar event.
        meet_link: Google Meet video link (may be None).
        booked_slot: Dict with 'start' and 'end' ISO 8601 strings.
    """
    try:
        supabase.table("sessions").update(
            {
                "status": "BOOKED",
                "booked_event_id": event_id,
                "booked_event_link": event_link,
                "meet_link": meet_link,
                "booked_slot": booked_slot,
                "updated_at": _utcnow(),
            }
        ).eq("session_id", session_id).execute()
    except Exception as exc:
        logger.warning("update_session_booking failed (non-fatal): %s", exc)


def update_rsvp_statuses(event_id: str, attendee_statuses: dict) -> None:
    """
    Sync RSVP statuses from Google Calendar back into Supabase.

    Updates attendee_statuses JSONB in booked_meetings and individual rows
    in meeting_attendees.

    Args:
        event_id: Google Calendar event ID.
        attendee_statuses: {email: responseStatus} dict from Calendar API.
    """
    try:
        # Update the jsonb column on booked_meetings
        response = (
            supabase.table("booked_meetings")
            .update({"attendee_statuses": attendee_statuses, "updated_at": _utcnow()})
            .eq("event_id", event_id)
            .execute()
        )

        # Get the meeting UUID so we can update individual attendee rows
        if not response.data:
            return
        meeting_id = response.data[0].get("id")
        if not meeting_id:
            return

        now = _utcnow()
        for email, status in attendee_statuses.items():
            try:
                supabase.table("meeting_attendees").update(
                    {"rsvp_status": status, "updated_at": now}
                ).eq("meeting_id", meeting_id).eq("email", email).execute()
            except Exception as inner_exc:
                logger.warning(
                    "update_rsvp_statuses: attendee row update failed for %s: %s",
                    email,
                    inner_exc,
                )
    except Exception as exc:
        logger.warning("update_rsvp_statuses failed (non-fatal): %s", exc)


def get_booked_meeting(event_id: str) -> Optional[dict]:
    """
    Retrieve a booked meeting record by Google Calendar event ID.

    Args:
        event_id: Google Calendar event ID.

    Returns:
        dict | None: The booked_meetings record, or None if not found.
    """
    try:
        response = (
            supabase.table("booked_meetings")
            .select("*")
            .eq("event_id", event_id)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as exc:
        logger.warning("get_booked_meeting failed: %s", exc)
        return None


def get_participant_preferences(email: str) -> Optional[dict]:
    """
    Retrieve scheduling preferences for a participant.

    Args:
        email: The participant's email address.

    Returns:
        dict | None: The participant_preferences record, or None if not found.
    """
    try:
        response = (
            supabase.table("participant_preferences")
            .select("*")
            .eq("email", email)
            .maybe_single()
            .execute()
        )
        return response.data
    except Exception as exc:
        logger.warning("get_participant_preferences failed: %s", exc)
        return None


def update_session_status(session_id: str, status: str) -> None:
    """
    Update the status field of a scheduling session.

    Args:
        session_id: The session to update.
        status: New status string (e.g. 'CANCELLED', 'RESCHEDULED').
    """
    try:
        supabase.table("sessions").update(
            {"status": status, "updated_at": _utcnow()}
        ).eq("session_id", session_id).execute()
    except Exception as exc:
        logger.warning("update_session_status failed (non-fatal): %s", exc)


def write_activity_log(log: LogRequest) -> None:
    """
    Append an entry to the `activity_logs` table.

    Non-fatal: any Supabase error is printed/logged but never raised.

    Args:
        log: LogRequest — the activity log entry to write.
    """
    payload = {
        "session_id": log.session_id,
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
        logger.warning("write_activity_log failed (non-fatal): %s", exc)
