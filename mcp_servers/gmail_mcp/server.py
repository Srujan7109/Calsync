"""
server.py — CalSync.ai Gmail MCP

Main FastAPI application. Runs on port 8006.
Exposes all Gmail MCP endpoints for outbound email, thread intelligence,
draft management, label operations, Gmail watch, and utilities.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware

import draft_service
import gmail_client
import intent_detector
import label_service
import llm_client
import supabase_ops
import thread_service as thread_svc
from auth import get_credentials
from config import settings
from models import (
    ApplyLabelBody,
    ApproveBody,
    AvailabilityRequestBody,
    ClarificationRequestBody,
    ConfirmationRequestBody,
    DiscardBody,
    DraftCreateRequest,
    GenerateAvailabilityBody,
    GenerateConfirmationBody,
    IntentDetectionRequest,
    LogRequest,
    MarkProcessedBody,
    SendEmailRequest,
    ThreadRequest,
    WatchRequest,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    On startup:
      - Ensures all CalSync Gmail labels exist.
      - Writes a startup activity log entry to Supabase.
    On shutdown: no-op (connections are managed per-request).
    """
    logger.info("CalSync Gmail MCP starting on port %s…", settings.PORT)
    try:
        label_service.ensure_calsync_labels_exist()
        logger.info("CalSync Gmail labels initialised.")
    except Exception as exc:
        logger.error("Label initialisation failed (non-fatal on startup): %s", exc)

    try:
        supabase_ops.write_activity_log(
            LogRequest(
                event_type="AUTH_REFRESHED",
                severity="INFO",
                description=f"Gmail MCP started on port {settings.PORT}.",
                actor="SYSTEM",
            )
        )
    except Exception as exc:
        logger.warning("Startup activity log failed: %s", exc)

    yield
    logger.info("CalSync Gmail MCP shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="CalSync.ai Gmail MCP",
    description="Gmail microservice for the CalSync.ai AI scheduling assistant.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # permissive for hackathon
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# OUTBOUND EMAIL
# =============================================================================


@app.post("/send", tags=["Email"])
async def send_email(req: SendEmailRequest) -> Dict[str, Any]:
    """
    Send a single email via Gmail.

    Sends the email, stores it in Supabase (direction=OUTBOUND), and logs
    the activity. The AI disclaimer is appended automatically by gmail_client.

    Body: SendEmailRequest
    Returns: {status, message_id, thread_id, email_id}
    """
    import hashlib

    try:
        result = gmail_client.send_email(req)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Build and store the OUTBOUND email record
    now = _utcnow()
    email_hash = hashlib.md5(
        f"{result['message_id']}:{settings.CALSYNC_EMAIL}:{req.subject}".encode()
    ).hexdigest()

    from models import EmailRecord

    record = EmailRecord(
        message_id=result["message_id"],
        thread_id=result["thread_id"],
        session_id=req.session_id,
        direction="OUTBOUND",
        from_email=settings.CALSYNC_EMAIL,
        to_emails=req.to_emails,
        cc_emails=req.cc_emails,
        subject=req.subject,
        body_text=req.body_text,
        body_html=req.body_html,
        email_hash=email_hash,
        is_read=True,
        processing_status="DONE",
        received_at=now,
        ingested_at=now,
        processed_at=now,
    )

    email_id = ""
    try:
        email_id = supabase_ops.store_email(record)
    except RuntimeError as exc:
        logger.warning("send_email: Supabase store failed (non-fatal): %s", exc)

    supabase_ops.write_activity_log(
        LogRequest(
            session_id=req.session_id,
            event_type="EMAIL_SENT",
            severity="SUCCESS",
            description=f"Email sent to {req.to_emails}: '{req.subject}'",
            payload=result,
            actor="AGENT",
        )
    )

    return {
        "status": "sent",
        "message_id": result["message_id"],
        "thread_id": result["thread_id"],
        "email_id": email_id,
    }


@app.post("/send/availability-request", tags=["Email"])
async def send_availability_request(body: AvailabilityRequestBody) -> Dict[str, Any]:
    """
    Generate and send an availability request email to each participant.

    Uses the LLM to generate a personalised email, then sends one copy
    per participant and stores each in Supabase.

    Body: {organizer, participants, meeting_title, session_id, thread_id, deadline_hours}
    Returns: {status, emails_sent, message_ids}
    """
    try:
        generated = llm_client.generate_availability_request_email(
            organizer=body.organizer,
            participants=body.participants,
            meeting_title=body.meeting_title,
            deadline_hours=body.deadline_hours,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {exc}")

    message_ids: List[str] = []
    for participant in body.participants:
        req = SendEmailRequest(
            to_emails=[participant],
            subject=generated["subject"],
            body_text=generated["body_text"],
            body_html=generated.get("body_html"),
            session_id=body.session_id,
            thread_id=body.thread_id,
        )
        try:
            result = gmail_client.send_email(req)
            message_ids.append(result["message_id"])
            # Store outbound record
            import hashlib
            from models import EmailRecord
            now = _utcnow()
            email_hash = hashlib.md5(
                f"{result['message_id']}:{settings.CALSYNC_EMAIL}:{generated['subject']}".encode()
            ).hexdigest()
            record = EmailRecord(
                message_id=result["message_id"],
                thread_id=result["thread_id"],
                session_id=body.session_id,
                direction="OUTBOUND",
                from_email=settings.CALSYNC_EMAIL,
                to_emails=[participant],
                subject=generated["subject"],
                body_text=generated["body_text"],
                body_html=generated.get("body_html"),
                email_hash=email_hash,
                is_read=True,
                processing_status="DONE",
                received_at=now,
                ingested_at=now,
                processed_at=now,
            )
            try:
                supabase_ops.store_email(record)
            except RuntimeError:
                pass
        except RuntimeError as exc:
            logger.error("send_availability_request: failed for %s: %s", participant, exc)

    return {
        "status": "sent",
        "emails_sent": len(message_ids),
        "message_ids": message_ids,
    }


@app.post("/send/confirmation", tags=["Email"])
async def send_confirmation(body: ConfirmationRequestBody) -> Dict[str, Any]:
    """
    Generate and send a booking confirmation email to all participants.

    Body: {participants, meeting_title, booked_slot, event_link, meet_link, session_id, …}
    Returns: {status, emails_sent}
    """
    try:
        generated = llm_client.generate_booking_confirmation_email(
            participants=body.participants,
            meeting_title=body.meeting_title,
            booked_slot=body.booked_slot,
            event_link=body.event_link,
            meet_link=body.meet_link,
            organizer_timezone=body.organizer_timezone,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Confirmation generation failed: {exc}")

    count = 0
    for participant in body.participants:
        req = SendEmailRequest(
            to_emails=[participant],
            subject=generated["subject"],
            body_text=generated["body_text"],
            body_html=generated.get("body_html"),
            session_id=body.session_id,
            thread_id=body.thread_id,
        )
        try:
            gmail_client.send_email(req)
            count += 1
        except RuntimeError as exc:
            logger.error("send_confirmation: failed for %s: %s", participant, exc)

    supabase_ops.write_activity_log(
        LogRequest(
            session_id=body.session_id,
            event_type="CONFIRMATION_SENT",
            severity="SUCCESS",
            description=f"Confirmation sent for '{body.meeting_title}' to {count} participant(s).",
            actor="AGENT",
        )
    )

    return {"status": "sent", "emails_sent": count}


@app.post("/send/clarification", tags=["Email"])
async def send_clarification(body: ClarificationRequestBody) -> Dict[str, Any]:
    """
    Generate and send a clarification email to a participant.

    Body: {participant, original_text, ambiguous_part, session_id, thread_id}
    Returns: {status, message_id}
    """
    try:
        generated = llm_client.generate_clarification_email(
            participant=body.participant,
            original_text=body.original_text,
            ambiguous_part=body.ambiguous_part,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Clarification generation failed: {exc}")

    req = SendEmailRequest(
        to_emails=[body.participant],
        subject=generated["subject"],
        body_text=generated["body_text"],
        session_id=body.session_id,
        thread_id=body.thread_id,
    )
    try:
        result = gmail_client.send_email(req)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Send failed: {exc}")

    return {"status": "sent", "message_id": result["message_id"]}


# =============================================================================
# THREAD INTELLIGENCE
# =============================================================================


@app.post("/thread/fetch", tags=["Thread"])
async def fetch_thread(req: ThreadRequest):
    """
    Fetch a Gmail thread, store all messages in Supabase, and summarise it.

    Body: ThreadRequest {thread_id, max_messages}
    Returns: ThreadResponse {thread_id, emails, count, summary}
    """
    try:
        return thread_svc.fetch_and_store_thread(req.thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/thread/{thread_id}", tags=["Thread"])
async def get_thread(thread_id: str = Path(..., description="Gmail thread ID")):
    """
    Retrieve a thread's emails from Supabase (no Gmail API call).

    Returns: ThreadResponse {thread_id, emails, count, summary}
    """
    try:
        return thread_svc.get_thread_from_db(thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/intent/detect", tags=["Thread"])
async def detect_intent(req: IntentDetectionRequest):
    """
    Classify the intent of an incoming email using keyword + LLM pipeline.

    Body: IntentDetectionRequest {subject, body_text, thread_id}
    Returns: IntentDetectionResponse {intent, confidence, reasoning, extracted_data}
    """
    return intent_detector.detect_email_intent(req)


# =============================================================================
# DRAFT MANAGEMENT
# =============================================================================


@app.post("/drafts", tags=["Drafts"])
async def create_draft(req: DraftCreateRequest) -> Dict[str, Any]:
    """
    Create an email draft in Gmail and persist it to Supabase.

    Body: DraftCreateRequest
    Returns: {draft_id, gmail_draft_id, status}
    """
    return draft_service.create_draft(req)


@app.get("/drafts/pending", tags=["Drafts"])
async def list_pending_drafts() -> List[Dict[str, Any]]:
    """
    Return all drafts that are awaiting human review.

    Returns: List of draft records
    """
    return draft_service.get_pending_drafts()


@app.post("/drafts/{draft_id}/approve", tags=["Drafts"])
async def approve_draft(
    draft_id: str = Path(..., description="Supabase UUID of the draft"),
    body: ApproveBody = ...,
) -> Dict[str, Any]:
    """
    Approve and send a pending draft.

    Body: {reviewed_by: str}
    Returns: {status, message_id, thread_id}
    """
    return draft_service.approve_and_send_draft(draft_id, body.reviewed_by)


@app.post("/drafts/{draft_id}/discard", tags=["Drafts"])
async def discard_draft(
    draft_id: str = Path(..., description="Supabase UUID of the draft"),
    body: DiscardBody = ...,
) -> Dict[str, Any]:
    """
    Discard a pending draft (deletes from Gmail and marks as DISCARDED).

    Body: {reviewed_by: str}
    Returns: {status}
    """
    return draft_service.discard_draft(draft_id, body.reviewed_by)


# =============================================================================
# LABELS
# =============================================================================


@app.post("/labels/apply", tags=["Labels"])
async def apply_label(body: ApplyLabelBody) -> Dict[str, str]:
    """
    Apply a CalSync label to a Gmail message.

    Body: {message_id, label_key}
    Returns: {status: "ok"}
    """
    try:
        label_service.apply_label(body.message_id, body.label_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


@app.post("/labels/mark-processed", tags=["Labels"])
async def mark_processed(body: MarkProcessedBody) -> Dict[str, str]:
    """
    Mark a message as processed by CalSync (adds PROCESSED label, marks read).

    Body: {message_id}
    Returns: {status: "ok"}
    """
    try:
        label_service.mark_processed(body.message_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


# =============================================================================
# GMAIL WATCH (PUSH NOTIFICATIONS)
# =============================================================================


@app.post("/watch/setup", tags=["Watch"])
async def setup_watch(req: WatchRequest) -> Dict[str, Any]:
    """
    Set up Gmail push notifications via Google Cloud Pub/Sub.

    Body: WatchRequest {profile_id}
    Returns: {status, expires_at, history_id}
    """
    try:
        watch_result = gmail_client.setup_watch(settings.GMAIL_PUBSUB_TOPIC)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Convert expiration (Unix ms string) to ISO 8601 UTC
    expiration_ms = watch_result.get("expiration")
    if expiration_ms:
        try:
            expires_at = datetime.fromtimestamp(
                int(expiration_ms) / 1000, tz=timezone.utc
            ).isoformat()
        except (ValueError, TypeError):
            expires_at = expiration_ms
    else:
        expires_at = ""

    history_id = watch_result.get("historyId", "")

    try:
        supabase_ops.upsert_gmail_watch(
            profile_id=req.profile_id,
            gmail_address=settings.CALSYNC_EMAIL,
            pubsub_topic=settings.GMAIL_PUBSUB_TOPIC,
            history_id=str(history_id),
            expires_at=expires_at,
        )
    except RuntimeError as exc:
        logger.warning("setup_watch: Supabase upsert failed: %s", exc)

    return {
        "status": "active",
        "expires_at": expires_at,
        "history_id": str(history_id),
    }


@app.post("/watch/stop", tags=["Watch"])
async def stop_watch() -> Dict[str, str]:
    """
    Stop Gmail push notifications.

    Returns: {status: "stopped"}
    """
    try:
        gmail_client.stop_watch()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "stopped"}


@app.get("/watch/status", tags=["Watch"])
async def watch_status() -> Dict[str, Any]:
    """
    Return the current Gmail watch subscription status from Supabase.

    Returns: watch record dict or {status: "no_active_watch"}
    """
    try:
        watch = supabase_ops.get_active_watch()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not watch:
        return {"status": "no_active_watch"}
    return watch


# =============================================================================
# EMAIL GENERATION UTILITIES (preview — does NOT send)
# =============================================================================


@app.post("/generate/availability-request", tags=["Generate"])
async def generate_availability_request(body: GenerateAvailabilityBody) -> Dict[str, Any]:
    """
    Generate an availability request email preview (does NOT send).

    Body: {organizer, participants, meeting_title, deadline_hours}
    Returns: {subject, body_text, body_html}
    """
    try:
        return llm_client.generate_availability_request_email(
            organizer=body.organizer,
            participants=body.participants,
            meeting_title=body.meeting_title,
            deadline_hours=body.deadline_hours,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/generate/confirmation", tags=["Generate"])
async def generate_confirmation(body: GenerateConfirmationBody) -> Dict[str, Any]:
    """
    Generate a booking confirmation email preview (does NOT send).

    Body: {participants, meeting_title, booked_slot, event_link, meet_link, …}
    Returns: {subject, body_text, body_html}
    """
    try:
        return llm_client.generate_booking_confirmation_email(
            participants=body.participants,
            meeting_title=body.meeting_title,
            booked_slot=body.booked_slot,
            event_link=body.event_link,
            meet_link=body.meet_link,
            organizer_timezone=body.organizer_timezone,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """
    Perform live health checks on all three external dependencies.

    Checks:
      - Supabase: executes a simple SELECT on app_settings.
      - Ollama: HTTP GET to the Ollama server root.
      - Gmail auth: calls get_credentials() and verifies validity.

    Returns:
        {
          status: "ok" | "degraded",
          service: "gmail_mcp",
          port: 8006,
          checks: {supabase: bool, ollama: bool, gmail_auth: bool}
        }
    """
    checks: Dict[str, bool] = {
        "supabase": False,
        "ollama": False,
        "gmail_auth": False,
    }

    # ── Supabase check ───────────────────────────────────────────────────────
    try:
        supabase_ops.supabase.table("app_settings").select("key").limit(1).execute()
        checks["supabase"] = True
    except Exception as exc:
        logger.warning("Health: Supabase check failed: %s", exc)

    # ── Ollama check ─────────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.OLLAMA_BASE_URL)
            checks["ollama"] = resp.status_code == 200
    except Exception as exc:
        logger.warning("Health: Ollama check failed: %s", exc)

    # ── Gmail auth check ─────────────────────────────────────────────────────
    try:
        creds = get_credentials()
        checks["gmail_auth"] = creds.valid
    except Exception as exc:
        logger.warning("Health: Gmail auth check failed: %s", exc)

    all_ok = all(checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "gmail_mcp",
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
