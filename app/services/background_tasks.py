from __future__ import annotations

from app.models.email_models import AgentProcessPayload


async def process_email_task(payload: dict[str, object]) -> None:
    _ = AgentProcessPayload(**payload)

