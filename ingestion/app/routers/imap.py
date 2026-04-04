from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ingestion.app.models.email_models import ImapPollResponse
from ingestion.app.services.background_tasks import process_email_task
from ingestion.app.services.imap_ingestion import collect_imap_payloads


router = APIRouter(prefix="/api/v1/imap", tags=["imap"])


@router.post(
    "/poll",
    response_model=ImapPollResponse,
    summary="Poll IMAP inbox now",
    description="Fetches emails from configured IMAP mailbox, deduplicates, filters, and queues accepted emails.",
    responses={
        200: {
            "description": "Polling completed",
            "content": {
                "application/json": {
                    "example": {"status": "ok", "fetched": 20, "accepted": 3, "duplicates": 14, "filtered_out": 3}
                }
            },
        },
        400: {
            "description": "Invalid or missing IMAP configuration",
            "content": {"application/json": {"example": {"detail": "IMAP credentials are incomplete."}}},
        },
    },
)
async def poll_imap_inbox(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=20, ge=1, le=100),
) -> ImapPollResponse:
    try:
        result = await collect_imap_payloads(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for payload in result.payloads:
        background_tasks.add_task(process_email_task, payload.model_dump())

    return ImapPollResponse(
        fetched=result.fetched,
        accepted=result.accepted,
        duplicates=result.duplicates,
        filtered_out=result.filtered_out,
    )
