from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from ingestion.app.config import get_settings
from ingestion.app.models.email_models import AgentProcessPayload
from ingestion.app.services.participant_utils import dedupe_emails, exclude_emails, parse_email_addresses
from ingestion.app.services.dedup_service import build_email_hash, check_and_mark_duplicate
from ingestion.app.services.imap_service import fetch_emails


logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True)
class ImapIngestionResult:
    fetched: int
    accepted: int
    duplicates: int
    filtered_out: int
    payloads: list[AgentProcessPayload]


async def collect_imap_payloads(limit: int) -> ImapIngestionResult:
    settings = get_settings()
    emails = await asyncio.to_thread(fetch_emails, settings, limit)

    payloads: list[AgentProcessPayload] = []
    duplicates = 0
    filtered_out = 0

    for email_item in emails:
        email_hash = build_email_hash(email_item.sender, email_item.message_id)
        body_preview = (email_item.body_text or "").replace("\n", " ").strip()[:300] or "No body content"

        logger.info(
            "📥 IMAP fetched from=%s subject=%s body_preview=%s",
            email_item.sender,
            email_item.subject,
            body_preview,
        )

        if await check_and_mark_duplicate(email_hash):
            duplicates += 1
            logger.info("♻️ IMAP skipped duplicate message_id=%s", email_item.message_id)
            continue

        text_lower = f"{email_item.subject} {email_item.body_text[:200]}".lower()
        if not any(keyword in text_lower for keyword in settings.accepted_keywords):
            filtered_out += 1
            logger.info("🧹 IMAP filtered by keywords subject=%s", email_item.subject)
            continue

        payloads.append(
            AgentProcessPayload(
                email_hash=email_hash,
                message_id=email_item.message_id,
                from_email=email_item.sender,
                subject=email_item.subject,
                body_text=email_item.body_text,
                thread_id=email_item.message_id,
                participants=exclude_emails(
                    dedupe_emails(
                        parse_email_addresses(email_item.to) + parse_email_addresses(email_item.sender)
                    ),
                    [settings.gmail_sender_email or "", settings.imap_username or ""],
                ),
                received_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    return ImapIngestionResult(
        fetched=len(emails),
        accepted=len(payloads),
        duplicates=duplicates,
        filtered_out=filtered_out,
        payloads=payloads,
    )
