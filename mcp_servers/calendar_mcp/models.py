"""
models.py — CalSync.ai Calendar MCP

All Pydantic v2 request/response/data models.
Imported by server.py, calendar_client.py, and all service modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Shared primitives ─────────────────────────────────────────────────────────


class TimeSlot(BaseModel):
    """A time interval represented as ISO 8601 UTC strings."""

    start: str = Field(..., description="Start datetime in ISO 8601 UTC format")
    end: str = Field(..., description="End datetime in ISO 8601 UTC format")


# ── Booking ───────────────────────────────────────────────────────────────────


class BookMeetingRequest(BaseModel):
    """Request body for POST /book — book a meeting with optional fallback slots."""

    action: str = "BOOK_MEETING"
    title: str
    slot: TimeSlot
    participants: List[str] = Field(..., min_length=1)
    description: str = ""
    fallback_slots: List[TimeSlot] = []
    session_id: Optional[str] = None
    organizer_email: str


class BookMeetingResponse(BaseModel):
    """Response for a booking attempt — success or all-slots-conflicted."""

    status: str  # BOOKED | ALL_SLOTS_CONFLICTED
    event_id: Optional[str] = None
    event_link: Optional[str] = None
    meet_link: Optional[str] = None
    booked_slot: Optional[TimeSlot] = None
    slot_index_used: int = 0
    fallback_used: bool = False
    primary_conflict_reason: Optional[str] = None
    invites_sent_to: List[str] = []
    message: Optional[str] = None


# ── Free/Busy ─────────────────────────────────────────────────────────────────


class FreeBusyRequest(BaseModel):
    """Request body for POST /freebusy."""

    participants: List[str] = Field(..., min_length=1)
    slots: List[TimeSlot] = Field(..., min_length=1)


class FreeBusySlotResult(BaseModel):
    """Free/busy result for a single time slot."""

    slot: TimeSlot
    is_free: bool
    conflicts: List[Dict[str, Any]] = []


class FreeBusyResponse(BaseModel):
    """Response for POST /freebusy — results for every requested slot."""

    results: List[FreeBusySlotResult]


class HeatmapRequest(BaseModel):
    """Request body for POST /freebusy/heatmap."""

    participants: List[str] = Field(..., min_length=1)
    from_date: str = Field(..., description="Start date YYYY-MM-DD (ISO)")
    to_date: str = Field(..., description="End date YYYY-MM-DD (ISO)")
    slot_duration_minutes: int = 60


# ── Cancellation ──────────────────────────────────────────────────────────────


class CancelRequest(BaseModel):
    """Request body for POST /cancel."""

    event_id: str
    reason: str = ""
    notify_attendees: bool = True
    session_id: Optional[str] = None


class CancelResponse(BaseModel):
    """Response for a cancellation request."""

    status: str  # CANCELLED | NOT_FOUND
    event_id: str
    notified: bool


# ── Rescheduling ──────────────────────────────────────────────────────────────


class RescheduleRequest(BaseModel):
    """Request body for POST /reschedule."""

    event_id: str
    new_slot: TimeSlot
    participants: List[str] = Field(..., min_length=1)
    title: Optional[str] = None
    session_id: Optional[str] = None


class RescheduleResponse(BaseModel):
    """Response for a successful reschedule operation."""

    status: str  # RESCHEDULED
    old_event_id: str
    new_event_id: str
    new_event_link: str
    new_slot: TimeSlot
    meet_link: Optional[str] = None


# ── Force Book ────────────────────────────────────────────────────────────────


class ForceBookRequest(BaseModel):
    """Request body for POST /force-book (skips conflict check, human override)."""

    title: str
    slot: TimeSlot
    participants: List[str] = Field(..., min_length=1)
    description: str = ""
    session_id: Optional[str] = None
    organizer_email: str
    override_reason: str


# ── RSVP ─────────────────────────────────────────────────────────────────────


class RSVPSyncRequest(BaseModel):
    """Request body for POST /rsvp/sync."""

    event_id: str
    session_id: Optional[str] = None


class RSVPSyncResponse(BaseModel):
    """Response after syncing attendee RSVP statuses from Google Calendar."""

    event_id: str
    attendee_statuses: Dict[str, str]  # {email: responseStatus}
    synced_at: str  # ISO 8601 UTC


class MeetLinkResponse(BaseModel):
    """Response for GET /events/{event_id}/meet-link."""

    event_id: str
    meet_link: Optional[str] = None


# ── Activity Logging ──────────────────────────────────────────────────────────


class LogRequest(BaseModel):
    """Internal model for writing activity log entries to Supabase."""

    session_id: Optional[str] = None
    event_type: str
    severity: str  # INFO | SUCCESS | WARNING | ERROR
    description: str
    payload: Optional[Dict[str, Any]] = None
    actor: str = "AGENT"
