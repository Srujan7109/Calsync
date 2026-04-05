"""
models.py — CalSync.ai Gmail MCP

All Pydantic v2 request/response/data models.
Imported by server.py and all service modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# ── Literal type aliases ────────────────────────────────────────────────────

EmailDirection = Literal["INBOUND", "OUTBOUND"]

ProcessingStatus = Literal[
    "PENDING", "PROCESSING", "DONE", "FAILED", "DUPLICATE", "IGNORED"
]

DraftStatus = Literal[
    "PENDING_REVIEW", "APPROVED", "SENT", "DISCARDED"
]

IntentType = Literal[
    "SCHEDULING_REQUEST",
    "AVAILABILITY_REPLY",
    "STATUS_QUERY",
    "CANCELLATION_REQUEST",
    "RESCHEDULE_REQUEST",
    "AMBIGUOUS",
    "OTHER",
]

Severity = Literal["INFO", "SUCCESS", "WARNING", "ERROR"]


# ── Data Records ────────────────────────────────────────────────────────────


class EmailRecord(BaseModel):
    """
    Represents a single email stored in the `emails` Supabase table.
    Used for both INBOUND and OUTBOUND messages.
    """

    id: Optional[str] = None
    message_id: str
    thread_id: str
    session_id: Optional[str] = None
    direction: EmailDirection
    from_email: str
    to_emails: List[str]
    cc_emails: List[str] = []
    subject: str
    body_text: str
    body_html: Optional[str] = None
    in_reply_to: Optional[str] = None       # RFC 2822 In-Reply-To header
    references_header: Optional[str] = None  # RFC 2822 References header chain
    labels: List[str] = []
    processing_status: ProcessingStatus = "PENDING"
    processing_error: Optional[str] = None
    email_hash: str
    is_read: bool = False
    has_attachments: bool = False
    received_at: str  # ISO 8601 UTC
    ingested_at: str  # ISO 8601 UTC
    processed_at: Optional[str] = None  # ISO 8601 UTC


# ── Outbound Email ───────────────────────────────────────────────────────────


class SendEmailRequest(BaseModel):
    """Request body for POST /send — send a single email."""

    to_emails: List[str] = Field(..., min_length=1)
    subject: str
    body_text: str
    body_html: Optional[str] = None
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    session_id: Optional[str] = None
    cc_emails: List[str] = []


class SendEmailResponse(BaseModel):
    """Response for a successful email send operation."""

    status: str
    message_id: str
    thread_id: str
    email_id: str  # Supabase uuid


# ── Thread ───────────────────────────────────────────────────────────────────


class ThreadRequest(BaseModel):
    """Request body for POST /thread/fetch."""

    thread_id: str
    max_messages: int = 50


class ThreadResponse(BaseModel):
    """Response containing all emails in a thread and an AI-generated summary."""

    thread_id: str
    emails: List[EmailRecord]
    count: int
    summary: Optional[str] = None


# ── Draft Management ─────────────────────────────────────────────────────────


class DraftCreateRequest(BaseModel):
    """Request body for POST /drafts — create a new email draft."""

    to_emails: List[str] = Field(..., min_length=1)
    subject: str
    body_text: str
    body_html: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    draft_reason: Optional[str] = None


class DraftActionRequest(BaseModel):
    """Request body for draft approve/discard actions."""

    draft_id: str
    action: DraftStatus
    reviewed_by: Optional[str] = None


# ── Labels ───────────────────────────────────────────────────────────────────


class LabelRequest(BaseModel):
    """Request body for POST /labels/apply."""

    message_id: str
    labels_to_add: List[str] = []
    labels_to_remove: List[str] = []


# ── Intent Detection ─────────────────────────────────────────────────────────


class IntentDetectionRequest(BaseModel):
    """Request body for POST /intent/detect."""

    subject: str
    body_text: str
    thread_id: Optional[str] = None


class IntentDetectionResponse(BaseModel):
    """Response from the intent detection pipeline."""

    intent: IntentType
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    extracted_data: Optional[Dict[str, Any]] = None


# ── Gmail Watch (Push Notifications) ─────────────────────────────────────────


class WatchRequest(BaseModel):
    """Request body for POST /watch/setup."""

    profile_id: str


# ── Activity Logging ─────────────────────────────────────────────────────────


class LogRequest(BaseModel):
    """Request body for writing an activity log entry."""

    session_id: Optional[str] = None
    email_id: Optional[str] = None
    event_type: str
    severity: Severity
    description: str
    payload: Optional[Dict[str, Any]] = None
    actor: str = "AGENT"


# ── Bulk Send Requests ───────────────────────────────────────────────────────


class AvailabilityRequestBody(BaseModel):
    """Request body for POST /send/availability-request."""

    organizer: str
    participants: List[str] = Field(..., min_length=1)
    meeting_title: str
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    deadline_hours: int = 48


class ConfirmationRequestBody(BaseModel):
    """Request body for POST /send/confirmation."""

    participants: List[str] = Field(..., min_length=1)
    meeting_title: str
    booked_slot: Dict[str, Any]
    event_link: str
    meet_link: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    organizer_timezone: str = "UTC"


class ClarificationRequestBody(BaseModel):
    """Request body for POST /send/clarification."""

    participant: str
    original_text: str
    ambiguous_part: str
    session_id: Optional[str] = None
    thread_id: Optional[str] = None


class GenerateAvailabilityBody(BaseModel):
    """Request body for POST /generate/availability-request (preview only)."""

    organizer: str
    participants: List[str]
    meeting_title: str
    deadline_hours: int = 48


class GenerateConfirmationBody(BaseModel):
    """Request body for POST /generate/confirmation (preview only)."""

    participants: List[str]
    meeting_title: str
    booked_slot: Dict[str, Any]
    event_link: str
    meet_link: Optional[str] = None
    organizer_timezone: str = "UTC"


class ApproveBody(BaseModel):
    """Request body for POST /drafts/{draft_id}/approve."""

    reviewed_by: str


class DiscardBody(BaseModel):
    """Request body for POST /drafts/{draft_id}/discard."""

    reviewed_by: str


class MarkProcessedBody(BaseModel):
    """Request body for POST /labels/mark-processed."""

    message_id: str


class ApplyLabelBody(BaseModel):
    """Request body for POST /labels/apply (extends LabelRequest with label_key)."""

    message_id: str
    label_key: str
    labels_to_add: List[str] = []
    labels_to_remove: List[str] = []
