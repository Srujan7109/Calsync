"""
server.py — CalSync.ai Calendar MCP

Main FastAPI application. Runs on port 8002.
Exposes all Calendar MCP endpoints: booking, free/busy, cancellation,
rescheduling, force-book, RSVP sync, and health check.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path as FilePath
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware

MODULE_DIR = FilePath(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.append(str(MODULE_DIR))

import calendar_client
import conflict_resolver
import supabase_ops
from auth import get_calendar_service
from config import settings
from models import (
    BookMeetingRequest,
    BookMeetingResponse,
    CancelRequest,
    CancelResponse,
    ForceBookRequest,
    FreeBusyRequest,
    FreeBusyResponse,
    HeatmapRequest,
    LogRequest,
    MeetLinkResponse,
    RSVPSyncRequest,
    RSVPSyncResponse,
    RescheduleRequest,
    RescheduleResponse,
    TimeSlot,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    On startup:
      - Logs that the service is starting.
      - Tests calendar auth by calling get_calendar_service().
      - Writes a startup log to activity_logs in Supabase.
    On shutdown: no-op.
    """
    logger.info("CalSync Calendar MCP starting on port %s…", settings.PORT)

    try:
        get_calendar_service()
        logger.info("Calendar auth OK — service cached.")
    except Exception as exc:
        logger.error("Calendar auth test failed on startup: %s", exc)

    try:
        supabase_ops.write_activity_log(
            LogRequest(
                event_type="SERVER_STARTUP",
                severity="INFO",
                description=f"Calendar MCP started on port {settings.PORT}.",
                actor="SYSTEM",
            )
        )
    except Exception as exc:
        logger.warning("Startup activity log failed: %s", exc)

    logger.info("Calendar MCP ready.")
    yield
    logger.info("CalSync Calendar MCP shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="CalSync.ai Calendar MCP",
    description=(
        "Google Calendar microservice for the CalSync.ai AI scheduling assistant. "
        "Handles booking, conflict resolution, cancellation, rescheduling, and RSVP sync."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# BOOKING
# =============================================================================


@app.post("/book", tags=["Booking"], response_model=BookMeetingResponse)
async def book_meeting(req: BookMeetingRequest) -> BookMeetingResponse:
    """
    Book a meeting with automatic fallback slot resolution.

    Tries the primary slot first, then fallback_slots in order. Creates a
    Google Meet link and sends invite emails automatically via Google Calendar.

    Body: BookMeetingRequest
    Returns: BookMeetingResponse (status BOOKED or ALL_SLOTS_CONFLICTED)
    """
    result = calendar_client.book_meeting(
        title=req.title,
        slot=req.slot,
        participants=req.participants,
        description=req.description,
        fallback_slots=req.fallback_slots,
        session_id=req.session_id,
        organizer_email=req.organizer_email,
    )

    if result["status"] == "ALL_SLOTS_CONFLICTED":
        supabase_ops.write_activity_log(
            LogRequest(
                session_id=req.session_id,
                event_type="BOOKING_FAILED_ALL_CONFLICTED",
                severity="WARNING",
                description=(
                    f"All {1 + len(req.fallback_slots)} slot(s) conflicted "
                    f"for '{req.title}'."
                ),
                payload={"participants": req.participants},
                actor="AGENT",
            )
        )
        return BookMeetingResponse(
            status="ALL_SLOTS_CONFLICTED",
            message=result.get("message"),
        )

    # BOOKED — persist to Supabase
    booked_slot: TimeSlot = result["booked_slot"]
    meeting_id = ""
    try:
        meeting_id = supabase_ops.store_booked_meeting(
            session_id=req.session_id or result["event_id"],
            event_id=result["event_id"],
            event_link=result["event_link"],
            meet_link=result.get("meet_link"),
            title=req.title,
            description=req.description,
            start_time=booked_slot.start,
            end_time=booked_slot.end,
            organizer_email=req.organizer_email,
            attendee_emails=req.participants,
            slot_index_used=result["slot_index_used"],
            fallback_used=result["fallback_used"],
        )
    except RuntimeError as exc:
        logger.warning("/book: Supabase store_booked_meeting failed (non-fatal): %s", exc)

    if meeting_id:
        try:
            supabase_ops.store_meeting_attendees(
                meeting_id=meeting_id,
                attendees=req.participants,
                organizer_email=req.organizer_email,
            )
        except Exception as exc:
            logger.warning("/book: store_meeting_attendees failed (non-fatal): %s", exc)

    if req.session_id:
        supabase_ops.update_session_booking(
            session_id=req.session_id,
            event_id=result["event_id"],
            event_link=result["event_link"],
            meet_link=result.get("meet_link"),
            booked_slot={"start": booked_slot.start, "end": booked_slot.end},
        )

    supabase_ops.write_activity_log(
        LogRequest(
            session_id=req.session_id,
            event_type="MEETING_BOOKED",
            severity="SUCCESS",
            description=(
                f'Meeting "{req.title}" booked for {req.participants} '
                f"at {booked_slot.start}"
            ),
            payload={
                "event_id": result["event_id"],
                "slot_index_used": result["slot_index_used"],
                "meet_link": result.get("meet_link"),
            },
            actor="AGENT",
        )
    )

    return BookMeetingResponse(
        status="BOOKED",
        event_id=result["event_id"],
        event_link=result["event_link"],
        meet_link=result.get("meet_link"),
        booked_slot=booked_slot,
        slot_index_used=result["slot_index_used"],
        fallback_used=result["fallback_used"],
        primary_conflict_reason=result.get("primary_conflict_reason"),
        invites_sent_to=result.get("invites_sent_to", []),
    )


@app.post("/force-book", tags=["Booking"])
async def force_book(req: ForceBookRequest) -> Dict[str, Any]:
    """
    Book a meeting unconditionally, bypassing all conflict checks.

    Used for human operator overrides. The override_reason is logged at WARNING
    severity and prepended to the meeting description.

    Body: ForceBookRequest
    Returns: BookMeetingResponse shape + override_applied: True
    """
    result = calendar_client.force_book(
        title=req.title,
        slot=req.slot,
        participants=req.participants,
        description=req.description,
        session_id=req.session_id,
        organizer_email=req.organizer_email,
        override_reason=req.override_reason,
    )

    # Persist to Supabase (best-effort)
    meeting_id = ""
    try:
        meeting_id = supabase_ops.store_booked_meeting(
            session_id=req.session_id or result["event_id"],
            event_id=result["event_id"],
            event_link=result["event_link"],
            meet_link=result.get("meet_link"),
            title=req.title,
            description=req.description,
            start_time=req.slot.start,
            end_time=req.slot.end,
            organizer_email=req.organizer_email,
            attendee_emails=req.participants,
            slot_index_used=0,
            fallback_used=False,
        )
    except RuntimeError as exc:
        logger.warning("/force-book: Supabase store failed (non-fatal): %s", exc)

    if meeting_id:
        supabase_ops.store_meeting_attendees(
            meeting_id=meeting_id,
            attendees=req.participants,
            organizer_email=req.organizer_email,
        )

    if req.session_id:
        supabase_ops.update_session_booking(
            session_id=req.session_id,
            event_id=result["event_id"],
            event_link=result["event_link"],
            meet_link=result.get("meet_link"),
            booked_slot={"start": req.slot.start, "end": req.slot.end},
        )

    supabase_ops.write_activity_log(
        LogRequest(
            session_id=req.session_id,
            event_type="FORCE_BOOK_APPLIED",
            severity="WARNING",
            description=f"FORCE BOOK applied: {req.override_reason}",
            payload={
                "event_id": result["event_id"],
                "participants": req.participants,
                "override_reason": req.override_reason,
            },
            actor="AGENT",
        )
    )

    return result


# =============================================================================
# AVAILABILITY
# =============================================================================


@app.post("/freebusy", tags=["Availability"], response_model=FreeBusyResponse)
async def freebusy(req: FreeBusyRequest) -> FreeBusyResponse:
    """
    Check free/busy status for all provided slots across all participants.

    Body: FreeBusyRequest {participants, slots}
    Returns: FreeBusyResponse with one result per slot
    """
    results = calendar_client.get_freebusy(req.participants, req.slots)
    return FreeBusyResponse(results=results)


@app.post("/freebusy/heatmap", tags=["Availability"])
async def freebusy_heatmap(req: HeatmapRequest) -> Dict[str, Any]:
    """
    Generate a free/busy heatmap over a date range.

    Splits the date range into slots of `slot_duration_minutes` and checks
    participant availability for each. Useful for finding best meeting windows.

    Body: HeatmapRequest {participants, from_date, to_date, slot_duration_minutes}
    Returns: {heatmap, participants, from_date, to_date}
    """
    service = calendar_client.get_calendar_service() if False else None

    from auth import get_calendar_service as _get_svc
    service = _get_svc()

    heatmap = conflict_resolver.generate_heatmap(
        service=service,
        participants=req.participants,
        from_date=req.from_date,
        to_date=req.to_date,
        slot_duration_minutes=req.slot_duration_minutes,
    )
    return {
        "heatmap": heatmap,
        "participants": req.participants,
        "from_date": req.from_date,
        "to_date": req.to_date,
    }


# =============================================================================
# CANCELLATION & RESCHEDULING
# =============================================================================


@app.post("/cancel", tags=["Scheduling"], response_model=CancelResponse)
async def cancel_meeting(req: CancelRequest) -> CancelResponse:
    """
    Cancel a Google Calendar event and update Supabase records.

    Body: CancelRequest {event_id, reason, notify_attendees, session_id}
    Returns: CancelResponse {status, event_id, notified}
    """
    result = calendar_client.cancel_event(
        event_id=req.event_id,
        reason=req.reason,
        notify_attendees=req.notify_attendees,
    )

    # Update Supabase (best-effort)
    supabase_ops.update_meeting_cancelled(req.event_id, req.reason)

    if req.session_id:
        supabase_ops.update_session_status(req.session_id, "CANCELLED")

    supabase_ops.write_activity_log(
        LogRequest(
            session_id=req.session_id,
            event_type="MEETING_CANCELLED",
            severity="INFO",
            description=f"Event {req.event_id} cancelled. Reason: {req.reason}",
            payload={"event_id": req.event_id, "notified": result.get("notified")},
            actor="AGENT",
        )
    )

    return CancelResponse(
        status=result["status"],
        event_id=result["event_id"],
        notified=result.get("notified", False),
    )


@app.post("/reschedule", tags=["Scheduling"], response_model=RescheduleResponse)
async def reschedule_meeting(req: RescheduleRequest) -> RescheduleResponse:
    """
    Atomically reschedule a Calendar event to a new time slot.

    Aborts with 409 if the new slot has conflicts (old event is preserved).
    Creates a new event with Meet link and sends update emails.

    Body: RescheduleRequest {event_id, new_slot, participants, title, session_id}
    Returns: RescheduleResponse
    """
    # May raise HTTPException 409 on conflicts — let it propagate
    result = calendar_client.reschedule_event(
        event_id=req.event_id,
        new_slot=req.new_slot,
        participants=req.participants,
        title=req.title,
        session_id=req.session_id,
    )

    new_slot = result["new_slot"]
    new_meeting_id = ""
    try:
        new_meeting_id = supabase_ops.store_booked_meeting(
            session_id=req.session_id or result["new_event_id"],
            event_id=result["new_event_id"],
            event_link=result["new_event_link"],
            meet_link=result.get("meet_link"),
            title=req.title or "",
            description="",
            start_time=new_slot.start,
            end_time=new_slot.end,
            organizer_email="",
            attendee_emails=req.participants,
            slot_index_used=0,
            fallback_used=False,
        )
    except RuntimeError as exc:
        logger.warning("/reschedule: Supabase store_booked_meeting failed (non-fatal): %s", exc)

    # Mark old booking as rescheduled
    if new_meeting_id:
        supabase_ops.update_meeting_rescheduled(req.event_id, new_meeting_id)

    if req.session_id and new_meeting_id:
        supabase_ops.update_session_booking(
            session_id=req.session_id,
            event_id=result["new_event_id"],
            event_link=result["new_event_link"],
            meet_link=result.get("meet_link"),
            booked_slot={"start": new_slot.start, "end": new_slot.end},
        )

    supabase_ops.write_activity_log(
        LogRequest(
            session_id=req.session_id,
            event_type="MEETING_RESCHEDULED",
            severity="SUCCESS",
            description=(
                f"Event {req.event_id} rescheduled to {new_slot.start}. "
                f"New event: {result['new_event_id']}"
            ),
            payload=result,
            actor="AGENT",
        )
    )

    return RescheduleResponse(
        status="RESCHEDULED",
        old_event_id=result["old_event_id"],
        new_event_id=result["new_event_id"],
        new_event_link=result["new_event_link"],
        new_slot=new_slot,
        meet_link=result.get("meet_link"),
    )


# =============================================================================
# RSVP
# =============================================================================


@app.post("/rsvp/sync", tags=["RSVP"], response_model=RSVPSyncResponse)
async def sync_rsvp(req: RSVPSyncRequest) -> RSVPSyncResponse:
    """
    Sync attendee RSVP statuses from Google Calendar to Supabase.

    Body: RSVPSyncRequest {event_id, session_id}
    Returns: RSVPSyncResponse {event_id, attendee_statuses, synced_at}
    """
    result = calendar_client.sync_rsvp_statuses(req.event_id)

    supabase_ops.update_rsvp_statuses(req.event_id, result["attendee_statuses"])

    return RSVPSyncResponse(
        event_id=result["event_id"],
        attendee_statuses=result["attendee_statuses"],
        synced_at=result["synced_at"],
    )


@app.get("/events/{event_id}/meet-link", tags=["RSVP"], response_model=MeetLinkResponse)
async def get_meet_link(
    event_id: str = Path(..., description="Google Calendar event ID")
) -> MeetLinkResponse:
    """
    Retrieve the Google Meet link for a Calendar event.

    Returns: MeetLinkResponse {event_id, meet_link}
    """
    meet_link = calendar_client.get_meet_link(event_id)
    return MeetLinkResponse(event_id=event_id, meet_link=meet_link)


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """
    Perform live health checks on both external dependencies.

    Checks:
      - Supabase: SELECT limit 1 from booked_meetings.
      - Calendar auth: call get_calendar_service() and verify credentials valid.

    Returns:
        {status: "ok"|"degraded", service, port, checks: {supabase, calendar_auth}}
    """
    checks: Dict[str, bool] = {
        "supabase": False,
        "calendar_auth": False,
    }

    # Supabase check
    try:
        supabase_ops.supabase.table("booked_meetings").select("id").limit(1).execute()
        checks["supabase"] = True
    except Exception as exc:
        logger.warning("Health: Supabase check failed: %s", exc)

    # Calendar auth check
    try:
        svc = get_calendar_service()
        # Verify the cached service is usable by checking credentials
        from auth import get_credentials
        creds = get_credentials()
        checks["calendar_auth"] = creds.valid
    except Exception as exc:
        logger.warning("Health: Calendar auth check failed: %s", exc)

    all_ok = all(checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "calendar_mcp",
        "port": settings.PORT,
        "checks": checks,
    }


# =============================================================================
# ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
