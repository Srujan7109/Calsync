from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from ingestion.app.config import get_settings
from ingestion.app.models.email_models import AgentProcessPayload
from ingestion.app.services.background_tasks import process_email_task
from ingestion.app.services.dedup_service import build_email_hash, check_and_mark_duplicate
from ingestion.app.services.participant_utils import dedupe_emails, exclude_emails, parse_email_addresses

logger = logging.getLogger("uvicorn.error")


async def fetch_and_queue_gmail_messages(
    client: httpx.AsyncClient,
    *,
    limit: int,
    source: str,
) -> dict[str, int]:
    settings = get_settings()

    response = await client.get(
        f"{settings.gmail_mcp_url.rstrip('/')}/messages/unread",
        params={"limit": limit},
    )
    response.raise_for_status()
    messages: list[dict] = response.json()

    accepted = 0
    duplicates = 0
    filtered = 0

    for message in messages:
        raw_from = str(message.get("from_email") or "")
        parsed_from = parse_email_addresses(raw_from)
        from_email = parsed_from[0] if parsed_from else raw_from.strip()

        message_id = str(message.get("message_id_header") or message.get("gmail_message_id") or "")
        gmail_message_id = str(message.get("gmail_message_id") or "")
        subject = str(message.get("subject") or "")
        body_text = str(message.get("body_text") or "")
        thread_id = str(message.get("thread_id") or "")

        email_hash = build_email_hash(from_email, message_id)

        if await check_and_mark_duplicate(email_hash):
            duplicates += 1
            continue

        text_lower = f"{subject} {body_text[:200]}".lower()
        if not any(keyword in text_lower for keyword in settings.accepted_keywords):
            filtered += 1
            continue

        to_raw = ", ".join(str(v) for v in message.get("to_emails", []))
        cc_raw = ", ".join(str(v) for v in message.get("cc_emails", []))

        participants = exclude_emails(
            dedupe_emails(
                parse_email_addresses(to_raw)
                + parse_email_addresses(from_email)
                + parse_email_addresses(cc_raw)
            ),
            [settings.gmail_sender_email or ""],
        )

        payload = AgentProcessPayload(
            email_hash=email_hash,
            message_id=message_id,
            from_email=from_email,
            subject=subject,
            body_text=body_text,
            thread_id=thread_id,
            participants=participants,
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        asyncio.create_task(process_email_task(payload.model_dump()))
        await _mark_read(client, settings.gmail_mcp_url, gmail_message_id)
        accepted += 1
        logger.info("Gmail API %s queued from=%s subject=%s", source, from_email, subject)

    stats = {
        "fetched": len(messages),
        "accepted": accepted,
        "duplicates": duplicates,
        "filtered": filtered,
    }
    logger.info(
        "Gmail API %s fetched=%s accepted=%s duplicates=%s filtered=%s",
        source,
        stats["fetched"],
        stats["accepted"],
        stats["duplicates"],
        stats["filtered"],
    )
    return stats


async def run_gmail_api_poller() -> None:
    settings = get_settings()
    if not settings.gmail_mcp_url:
        logger.warning("Gmail API poller disabled: GMAIL_MCP_URL not set")
        return

    logger.info("Gmail API poller started interval=%s seconds", settings.imap_poll_interval_seconds)

    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            loop_start = time.monotonic()
            try:
                await fetch_and_queue_gmail_messages(
                    client,
                    limit=settings.imap_poll_batch_size,
                    source="poll",
                )
            except Exception as exc:
                logger.exception("Gmail API poller iteration failed: %s", exc)

            elapsed = time.monotonic() - loop_start
            target_interval = max(settings.imap_poll_interval_seconds, 1)
            sleep_for = max(target_interval - elapsed, 0.0)
            logger.debug(
                "Gmail API poll loop elapsed=%.3fs target_interval=%ss sleep=%.3fs",
                elapsed,
                target_interval,
                sleep_for,
            )
            await asyncio.sleep(sleep_for)


async def _mark_read(client: httpx.AsyncClient, gmail_mcp_url: str, gmail_message_id: str) -> None:
    if not gmail_message_id:
        return
    try:
        await client.post(f"{gmail_mcp_url.rstrip('/')}/messages/{gmail_message_id}/mark-read")
    except Exception:
        pass