from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.services.background_tasks import process_email_task
from app.services.imap_ingestion import collect_imap_payloads


logger = logging.getLogger(__name__)


async def run_imap_poller() -> None:
    settings = get_settings()

    while True:
        try:
            result = await collect_imap_payloads(limit=settings.imap_poll_batch_size)
            for payload in result.payloads:
                asyncio.create_task(process_email_task(payload.model_dump()))

            if result.fetched:
                logger.info(
                    "IMAP poll fetched=%s accepted=%s duplicates=%s filtered=%s",
                    result.fetched,
                    result.accepted,
                    result.duplicates,
                    result.filtered_out,
                )
        except ValueError:
            logger.debug("IMAP credentials not fully set. Auto-poller waiting for configuration.")
        except Exception as exc:  # pragma: no cover - operational safety
            logger.exception("IMAP auto-poller iteration failed: %s", exc)

        await asyncio.sleep(max(settings.imap_poll_interval_seconds, 1))
