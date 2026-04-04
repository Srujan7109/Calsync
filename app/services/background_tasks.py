from __future__ import annotations

from app.agent.react_agent import run_react_agent
from app.models.email_models import AgentProcessPayload


async def process_email_task(payload: dict[str, object]) -> None:
    validated_payload = AgentProcessPayload(**payload)
    await run_react_agent(validated_payload)

