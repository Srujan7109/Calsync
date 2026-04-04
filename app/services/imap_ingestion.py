from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import get_settings
from app.models.email_models import AgentProcessPayload
from app.services.dedup_service import build_email_hash, check_and_mark_duplicate
from app.services.imap_service import fetch_emails


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

        if await check_and_mark_duplicate(email_hash):
            duplicates += 1
            continue

        text_lower = f"{email_item.subject} {email_item.body_text[:200]}".lower()
        if not any(keyword in text_lower for keyword in settings.accepted_keywords):
            filtered_out += 1
            continue

        payloads.append(
            AgentProcessPayload(
                email_hash=email_hash,
                message_id=email_item.message_id,
                from_email=email_item.sender,
                subject=email_item.subject,
                body_text=email_item.body_text,
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
