"""
calendar_client.py — CalSync.ai Calendar MCP

Core Google Calendar API operations.
Handles booking, cancellation, rescheduling, force-book, RSVP sync,
and Meet link retrieval.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from googleapiclient.errors import HttpError

from auth import get_calendar_service
from config import settings
from conflict_resolver import check_all_slots, check_slot_conflicts, find_available_slot
from event_builder import build_event_body, extract_meet_link
from models import FreeBusySlotResult, TimeSlot

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── Core operations ────────────────────────────────────────────────────────────


def book_meeting(
    title: str,
    slot: TimeSlot,
    participants: List[str],
    description: str = "",
    fallback_slots: Optional[List[TimeSlot]] = None,
    session_id: Optional[str] = None,
    organizer_email: str = "",
) -> dict:
    """
    Book a meeting in Google Calendar, with automatic fallback slot resolution.

    Builds the candidate slot list as [primary_slot] + fallback_slots, then
    calls find_available_slot() to pick the first conflict-free option.
    If no slot is available, returns ALL_SLOTS_CONFLICTED without creating
    any Calendar event.

    Creates the event with conferenceDataVersion=1 to generate a Google Meet
    link and sendUpdates="all" so Google sends invite emails automatically.

    Args:
        title: Meeting title.
        slot: Primary time slot to attempt.
        participants: All attendee emails (including organiser).
        description: Optional meeting description.
        fallback_slots: Ordered list of fallback slots to try if primary conflicts.
        session_id: CalSync session UUID for traceability.
        organizer_email: Organiser's email (included in attendees).

    Returns:
        dict: On success:
            {status, event_id, event_link, meet_link, booked_slot,
             slot_index_used, fallback_used, primary_conflict_reason,
             invites_sent_to}
        On all-slots-conflicted:
            {status: "ALL_SLOTS_CONFLICTED", message: str}

    Raises:
        HTTPException 500: If the Calendar API insert fails.
    """
    service = get_calendar_service()
    all_slots = [slot] + (fallback_slots or [])

    available_slot, slot_index, conflict_reason = find_available_slot(
        service, participants, all_slots
    )

    if available_slot is None:
        logger.warning(
            "book_meeting: all %d slot(s) conflicted for '%s'.", len(all_slots), title
        )
        return {
            "status": "ALL_SLOTS_CONFLICTED",
            "message": "No available slots. Collect more availability.",
        }

    event_body = build_event_body(
        title=title,
        slot=available_slot,
        participants=participants,
        description=description,
        session_id=session_id,
        organizer_email=organizer_email,
    )

    try:
        event = (
            service.events()
            .insert(
                calendarId=settings.CALENDAR_ID,
                body=event_body,
                conferenceDataVersion=1,
                # sendUpdates="none" — CalSync agent sends its own confirmation
                # email via Gmail MCP after booking, so we suppress the
                # automatic Google Calendar invite to avoid double-emailing.
                sendUpdates="none",
            )
            .execute()
        )
    except HttpError as exc:
        logger.error("book_meeting: Calendar API insert failed: %s", exc)
        raise HTTPException(
            status_code=exc.resp.status,
            detail=f"Google Calendar API error: {exc}",
        )

    meet_link = extract_meet_link(event)
    fallback_used = slot_index > 0

    logger.info(
        "book_meeting: booked '%s' on slot %d (%s → %s). Event ID: %s",
        title,
        slot_index,
        available_slot.start,
        available_slot.end,
        event["id"],
    )

    return {
        "status": "BOOKED",
        "event_id": event["id"],
        "event_link": event.get("htmlLink", ""),
        "meet_link": meet_link,
        "booked_slot": available_slot,
        "slot_index_used": slot_index,
        "fallback_used": fallback_used,
        "primary_conflict_reason": conflict_reason if fallback_used else None,
        "invites_sent_to": participants,
    }


def cancel_event(
    event_id: str,
    reason: str = "",
    notify_attendees: bool = True,
) -> dict:
    """
    Cancel a Google Calendar event and optionally notify attendees.

    Calls events().delete() with sendUpdates="all" (or "none") so Google
    Calendar sends cancellation emails when notify_attendees is True.

    Args:
        event_id: The Google Calendar event ID to cancel.
        reason: Human-readable cancellation reason (stored in Supabase).
        notify_attendees: If True, Google sends cancellation emails.

    Returns:
        dict: {status: "CANCELLED" | "NOT_FOUND", event_id, notified}

    Raises:
        HTTPException 500: If the API fails with a non-404 error.
    """
    service = get_calendar_service()
    send_updates = "all" if notify_attendees else "none"

    try:
        service.events().delete(
            calendarId=settings.CALENDAR_ID,
            eventId=event_id,
            sendUpdates=send_updates,
        ).execute()
        logger.info("cancel_event: cancelled event %s. Notified: %s", event_id, notify_attendees)
        return {
            "status": "CANCELLED",
            "event_id": event_id,
            "notified": notify_attendees,
        }
    except HttpError as exc:
        if exc.resp.status == 404:
            logger.warning("cancel_event: event %s not found.", event_id)
            return {"status": "NOT_FOUND", "event_id": event_id, "notified": False}
        logger.error("cancel_event: Calendar API error: %s", exc)
        raise HTTPException(
            status_code=exc.resp.status,
            detail=f"Google Calendar API error on cancel: {exc}",
        )


def reschedule_event(
    event_id: str,
    new_slot: TimeSlot,
    participants: List[str],
    title: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Atomically reschedule a Google Calendar event to a new time slot.

    Execution order (abort-safe):
      1. Fetch existing event to preserve title if not provided.
      2. Check new_slot for conflicts — ABORT with 409 if any found.
      3. Cancel old event (sendUpdates="all").
      4. Create new event with conferenceDataVersion=1.
      5. Extract Meet link from new event.

    If step 2 fails (conflicts detected), the old event is untouched.

    Args:
        event_id: Google Calendar event ID of the meeting to reschedule.
        new_slot: The new TimeSlot to book.
        participants: All attendee emails for the new event.
        title: Optional override title. If None, preserves the old event's title.
        session_id: CalSync session UUID for traceability.

    Returns:
        dict: {status, old_event_id, new_event_id, new_event_link, new_slot, meet_link}

    Raises:
        HTTPException 409: If new_slot has conflicts.
        HTTPException 4xx/5xx: On Calendar API errors.
    """
    service = get_calendar_service()

    # Step 1: get existing event
    try:
        old_event = (
            service.events()
            .get(calendarId=settings.CALENDAR_ID, eventId=event_id)
            .execute()
        )
    except HttpError as exc:
        logger.error("reschedule_event: failed to fetch old event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=exc.resp.status,
            detail=f"Could not fetch event {event_id}: {exc}",
        )

    meeting_title = title or old_event.get("summary", "CalSync Meeting")

    # Step 2: conflict check on new slot (abort-safe — old event still exists)
    conflicts = check_slot_conflicts(service, participants, new_slot)
    if conflicts:
        conflicted = [c["participant"] for c in conflicts]
        logger.warning(
            "reschedule_event: new slot conflicts for %s — aborting. Conflicts: %s",
            event_id,
            conflicted,
        )
        raise HTTPException(
            status_code=409,
            detail=f"New slot has conflicts for: {conflicted}. Reschedule aborted.",
        )

    # Step 3: cancel old event
    try:
        service.events().delete(
            calendarId=settings.CALENDAR_ID,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
    except HttpError as exc:
        logger.error("reschedule_event: failed to cancel old event: %s", exc)
        raise HTTPException(
            status_code=exc.resp.status,
            detail=f"Failed to cancel old event: {exc}",
        )

    # Step 4: create new event
    event_body = build_event_body(
        title=meeting_title,
        slot=new_slot,
        participants=participants,
        session_id=session_id,
    )

    try:
        new_event = (
            service.events()
            .insert(
                calendarId=settings.CALENDAR_ID,
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates="all",
            )
            .execute()
        )
    except HttpError as exc:
        logger.error("reschedule_event: failed to create new event: %s", exc)
        raise HTTPException(
            status_code=exc.resp.status,
            detail=f"Old event cancelled but new event creation failed: {exc}",
        )

    # Step 5: extract Meet link
    meet_link = extract_meet_link(new_event)

    logger.info(
        "reschedule_event: rescheduled %s → %s (%s)",
        event_id,
        new_event["id"],
        new_slot.start,
    )

    return {
        "status": "RESCHEDULED",
        "old_event_id": event_id,
        "new_event_id": new_event["id"],
        "new_event_link": new_event.get("htmlLink", ""),
        "new_slot": new_slot,
        "meet_link": meet_link,
    }


def force_book(
    title: str,
    slot: TimeSlot,
    participants: List[str],
    description: str = "",
    session_id: Optional[str] = None,
    organizer_email: str = "",
    override_reason: str = "",
) -> dict:
    """
    Book a meeting WITHOUT performing any free/busy conflict check.

    Used for human operator overrides. The override_reason is prepended to
    the meeting description so it is visible to attendees.

    Creates the event with conferenceDataVersion=1 and sendUpdates="all".

    Args:
        title: Meeting title.
        slot: TimeSlot to book unconditionally.
        participants: All attendee emails.
        description: Optional base description.
        session_id: CalSync session UUID.
        organizer_email: Organiser's email address.
        override_reason: Explanation for bypassing conflict checks.

    Returns:
        dict: Same shape as book_meeting success response, plus
              {override_applied: True}.

    Raises:
        HTTPException 500: If the Calendar API insert fails.
    """
    service = get_calendar_service()

    full_description = f"[FORCE BOOK] Override reason: {override_reason}\n\n{description}"

    event_body = build_event_body(
        title=title,
        slot=slot,
        participants=participants,
        description=full_description,
        session_id=session_id,
        organizer_email=organizer_email,
    )

    try:
        event = (
            service.events()
            .insert(
                calendarId=settings.CALENDAR_ID,
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates="all",
            )
            .execute()
        )
    except HttpError as exc:
        logger.error("force_book: Calendar API insert failed: %s", exc)
        raise HTTPException(
            status_code=exc.resp.status,
            detail=f"Google Calendar API error on force-book: {exc}",
        )

    meet_link = extract_meet_link(event)
    logger.warning(
        "force_book: OVERRIDE applied for '%s'. Reason: %s. Event: %s",
        title,
        override_reason,
        event["id"],
    )

    return {
        "status": "BOOKED",
        "event_id": event["id"],
        "event_link": event.get("htmlLink", ""),
        "meet_link": meet_link,
        "booked_slot": slot,
        "slot_index_used": 0,
        "fallback_used": False,
        "primary_conflict_reason": None,
        "invites_sent_to": participants,
        "override_applied": True,
    }


def get_freebusy(
    participants: List[str],
    slots: List[TimeSlot],
) -> List[FreeBusySlotResult]:
    """
    Check free/busy status for all provided slots across all participants.

    Delegates to conflict_resolver.check_all_slots(). All slots are checked;
    the function does not stop at the first free one.

    Args:
        participants: List of participant email addresses.
        slots: List of TimeSlots to check.

    Returns:
        List[FreeBusySlotResult]: One result per slot.
    """
    service = get_calendar_service()
    return check_all_slots(service, participants, slots)


def get_event(event_id: str) -> dict:
    """
    Fetch a raw Google Calendar event resource by ID.

    Args:
        event_id: The Google Calendar event ID to retrieve.

    Returns:
        dict: The full event resource as returned by the Calendar API.

    Raises:
        HTTPException 404: If the event does not exist.
        HTTPException 5xx: On other API errors.
    """
    service = get_calendar_service()
    try:
        return (
            service.events()
            .get(calendarId=settings.CALENDAR_ID, eventId=event_id)
            .execute()
        )
    except HttpError as exc:
        logger.error("get_event: Calendar API error for event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=exc.resp.status,
            detail=f"Calendar API error fetching event {event_id}: {exc}",
        )


def sync_rsvp_statuses(event_id: str) -> dict:
    """
    Fetch current RSVP statuses from Google Calendar for a booked event.

    Retrieves the live attendee list and maps each attendee's responseStatus
    (accepted/declined/tentative/needsAction) into a dict.

    Args:
        event_id: The Google Calendar event ID to sync.

    Returns:
        dict: {event_id, attendee_statuses, synced_at}
              attendee_statuses: {email: responseStatus}

    Raises:
        HTTPException: If the Calendar API call fails.
    """
    event = get_event(event_id)
    attendees = event.get("attendees", [])

    statuses = {a["email"]: a.get("responseStatus", "needsAction") for a in attendees}

    return {
        "event_id": event_id,
        "attendee_statuses": statuses,
        "synced_at": _utcnow(),
    }


def get_meet_link(event_id: str) -> Optional[str]:
    """
    Retrieve the Google Meet link for a specific Calendar event.

    Args:
        event_id: The Google Calendar event ID.

    Returns:
        str | None: The Google Meet URL, or None if the event has no Meet link.

    Raises:
        HTTPException: If the Calendar API call fails.
    """
    event = get_event(event_id)
    return extract_meet_link(event)
