from __future__ import annotations

import asyncio
import logging

import httpx

from ingestion.app.services.gmail_api_poller import fetch_and_queue_gmail_messages


logger = logging.getLogger("uvicorn.error")


_push_lock = asyncio.Lock()
_pending_push_task: asyncio.Task[None] | None = None


async def schedule_push_ingestion(*, limit: int, debounce_ms: int) -> bool:
    """Schedule a debounced Gmail fetch on push notification.

    Returns True when a new ingestion task is created, or False when an
    existing scheduled task is already pending.
    """
    global _pending_push_task

    if _pending_push_task and not _pending_push_task.done():
        return False

    async def _run() -> None:
        delay = max(debounce_ms, 0) / 1000
        if delay:
            await asyncio.sleep(delay)

        async with _push_lock:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    await fetch_and_queue_gmail_messages(
                        client,
                        limit=max(limit, 1),
                        source="push",
                    )
            except Exception as exc:  # pragma: no cover - operational safety
                logger.exception("Gmail push ingestion failed: %s", exc)

    _pending_push_task = asyncio.create_task(_run())
    return True
