from __future__ import annotations

import base64
import binascii
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile

from ingestion.app.config import get_settings
from ingestion.app.models.email_models import (
    AgentProcessPayload,
    DuplicateResponse,
    EmailWebhookPayload,
    NotSchedulingResponse,
    WebhookAcceptedResponse,
)
from ingestion.app.services.participant_utils import dedupe_emails, exclude_emails, parse_email_addresses
from ingestion.app.services.background_tasks import process_email_task
from ingestion.app.services.dedup_service import build_email_hash, check_and_mark_duplicate
from ingestion.app.services.gmail_push_handler import schedule_push_ingestion


router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])
logger = logging.getLogger("uvicorn.error")


def _decode_pubsub_data(encoded_data: str) -> dict[str, Any]:
    padded = encoded_data + "=" * (-len(encoded_data) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


@router.get("/health", summary="Webhook health check", description="Returns service health for webhook ingress.")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/email",
    response_model=WebhookAcceptedResponse | DuplicateResponse | NotSchedulingResponse,
    summary="Receive inbound scheduling email",
    description=(
        "Accepts SendGrid-style multipart form payload, computes idempotency hash, "
        "applies keyword edge filter, and queues async processing."
    ),
    responses={
        200: {
            "description": "Email accepted, deduplicated, or filtered",
            "content": {
                "application/json": {
                    "examples": {
                        "accepted": {"summary": "Accepted", "value": {"status": "accepted", "task_id": "bg_task_abc123"}},
                        "duplicate": {"summary": "Duplicate", "value": {"status": "duplicate_discarded"}},
                        "filtered": {"summary": "Not scheduling related", "value": {"status": "not_scheduling_related"}},
                    }
                }
            },
        }
    },
)
async def receive_email(
    background_tasks: BackgroundTasks,
    sender: str = Form(default="", alias="from"),
    to: str = Form(default=""),
    cc: str = Form(default=""),
    subject: str = Form(default=""),
    text: str = Form(default=""),
    html: str | None = Form(default=None),
    message_id: str = Form(default=""),
    headers: str | None = Form(default=None),
    spam_score: str | None = Form(default=None),
    attachments: list[UploadFile] | None = File(default=None),
):
    settings = get_settings()
    _ = attachments

    payload = EmailWebhookPayload(
        sender=sender,
        to=to,
        subject=subject,
        text=text,
        html=html,
        message_id=message_id,
        headers=headers,
        spam_score=spam_score,
    )

    email_hash = build_email_hash(payload.sender, payload.message_id)

    if await check_and_mark_duplicate(email_hash):
        return DuplicateResponse()

    text_lower = f"{payload.subject} {payload.text[:200]}".lower()
    if not any(keyword in text_lower for keyword in settings.accepted_keywords):
        return NotSchedulingResponse()

    task_id = f"bg_task_{uuid.uuid4().hex[:8]}"
    participants = dedupe_emails(parse_email_addresses(payload.to) + parse_email_addresses(payload.sender)+parse_email_addresses(payload.cc))
    participants = exclude_emails(participants, [settings.gmail_sender_email or ""])
    thread_id = payload.message_id.strip()

    background_payload = AgentProcessPayload(
        email_hash=email_hash,
        message_id=payload.message_id,
        from_email=payload.sender,
        subject=payload.subject,
        body_text=payload.text,
        thread_id=thread_id,
        participants=participants,
        received_at=datetime.now(timezone.utc).isoformat(),
    )
    background_tasks.add_task(process_email_task, background_payload.model_dump())

    return WebhookAcceptedResponse(task_id=task_id)


@router.post(
    "/gmail/push",
    summary="Receive Gmail Pub/Sub push notifications",
    description=(
        "Accepts Pub/Sub push notifications from Gmail watch and triggers a "
        "debounced immediate inbox fetch for low-latency processing."
    ),
)
async def receive_gmail_push(request: Request) -> dict[str, str | bool]:
    settings = get_settings()

    if not settings.gmail_push_enabled:
        return {"status": "ignored", "reason": "gmail_push_disabled"}

    body = await request.json()
    message = body.get("message") if isinstance(body, dict) else None
    data = message.get("data") if isinstance(message, dict) else None

    if not isinstance(data, str) or not data.strip():
        return {"status": "ignored", "reason": "missing_pubsub_data"}

    try:
        payload = _decode_pubsub_data(data)
    except (ValueError, json.JSONDecodeError, binascii.Error) as exc:
        logger.warning("Invalid Gmail push payload: %s", exc)
        return {"status": "ignored", "reason": "invalid_pubsub_payload"}

    scheduled = await schedule_push_ingestion(
        limit=settings.gmail_push_fetch_limit,
        debounce_ms=settings.gmail_push_debounce_ms,
    )
    logger.info(
        "Gmail push received email=%s history_id=%s scheduled=%s",
        payload.get("emailAddress", ""),
        payload.get("historyId", ""),
        scheduled,
    )

    return {
        "status": "accepted",
        "scheduled": scheduled,
    }
