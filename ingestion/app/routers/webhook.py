from __future__ import annotations

import uuid
from datetime import datetime, timezone
from email import message_from_string

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

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
from ingestion.app.services.thread_identity import derive_thread_id, normalize_message_id
from ingestion.app.services.thread_memory_service import ThreadMemoryService


router = APIRouter(tags=["webhook"])


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
    thread_memory = ThreadMemoryService()
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

    parsed_headers = message_from_string(headers or "") if headers else message_from_string("")
    in_reply_to = normalize_message_id(parsed_headers.get("In-Reply-To"))
    references = parsed_headers.get("References") or ""
    thread_id = derive_thread_id(payload.message_id, in_reply_to, references)

    participants = dedupe_emails(parse_email_addresses(payload.to) + parse_email_addresses(payload.sender) + parse_email_addresses(payload.cc))
    participants = exclude_emails(participants, [settings.gmail_sender_email or ""])

    text_lower = f"{payload.subject} {payload.text[:200]}".lower()
    accepted = any(keyword in text_lower for keyword in settings.accepted_keywords)

    await thread_memory.store_email(
        message_id=normalize_message_id(payload.message_id),
        thread_id=thread_id,
        from_email=payload.sender,
        to_emails=parse_email_addresses(payload.to),
        cc_emails=parse_email_addresses(payload.cc),
        subject=payload.subject,
        body_text=payload.text,
        body_html=payload.html,
        received_at=datetime.now(timezone.utc).isoformat(),
        email_hash=email_hash,
        in_reply_to=in_reply_to,
        references_header=references,
        processing_status="PENDING" if accepted else "IGNORED",
        is_read=True,
    )

    if not accepted:
        return NotSchedulingResponse()

    task_id = f"bg_task_{uuid.uuid4().hex[:8]}"

    background_payload = AgentProcessPayload(
        email_hash=email_hash,
        message_id=payload.message_id,
        from_email=payload.sender,
        subject=payload.subject,
        body_text=payload.text,
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=references,
        participants=participants,
        received_at=datetime.now(timezone.utc).isoformat(),
    )
    background_tasks.add_task(process_email_task, background_payload.model_dump())

    return WebhookAcceptedResponse(task_id=task_id)
