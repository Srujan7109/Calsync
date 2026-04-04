from __future__ import annotations

import asyncio
import logging

from ingestion.app.config import get_settings
from ingestion.app.services.background_tasks import process_email_task
from ingestion.app.services.imap_ingestion import collect_imap_payloads


logger = logging.getLogger("uvicorn.error")


async def run_imap_poller() -> None:
    settings = get_settings()
    logger.info("IMAP auto-poller started interval=%s seconds", settings.imap_poll_interval_seconds)

    while True:
        try:
            result = await collect_imap_payloads(limit=settings.imap_poll_batch_size)

            logger.info(
                "🔄 IMAP poll fetched=%s accepted=%s duplicates=%s filtered=%s",
                result.fetched,
                result.accepted,
                result.duplicates,
                result.filtered_out,
            )

            for payload in result.payloads:
                logger.info(
                    "Email received from=%s subject=%s",
                    payload.from_email,
                    payload.subject,
                )
                logger.debug(
                    "Email body preview=%s",
                    payload.body_text[:300] if payload.body_text else "No body content",
                )
                asyncio.create_task(process_email_task(payload.model_dump()))

        except ValueError as exc:
            logger.warning("IMAP credentials not fully set: %s", exc)
        except Exception as exc:  # pragma: no cover - operational safety
            logger.exception("IMAP auto-poller iteration failed: %s", exc)

        await asyncio.sleep(max(settings.imap_poll_interval_seconds, 1))
