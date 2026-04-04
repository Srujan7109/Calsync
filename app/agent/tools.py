from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings


@dataclass(slots=True)
class ToolCallOutcome:
    name: str
    status: str
    payload: dict[str, object]


class CalsyncTools:
    def __init__(self) -> None:
        settings = get_settings()
        self.compute_url = settings.compute_mcp_url
        self.state_url = settings.state_mcp_url
        self.calendar_url = settings.calendar_mcp_url

    async def parse_availability(self, text: str, timezone: str = "Asia/Kolkata") -> ToolCallOutcome:
        if not self.compute_url:
            return ToolCallOutcome(name="parse_availability", status="SKIPPED", payload={"reason": "compute_mcp_not_configured"})

        endpoint = f"{self.compute_url.rstrip('/')}/mcp/compute/parse_availability"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(endpoint, json={"text": text, "timezone": timezone})
            response.raise_for_status()
            return ToolCallOutcome(name="parse_availability", status="OK", payload=response.json())

    async def create_session(self, thread_id: str, organizer: str, participants: list[str]) -> ToolCallOutcome:
        if not self.state_url:
            return ToolCallOutcome(name="create_session", status="SKIPPED", payload={"reason": "state_mcp_not_configured"})

        endpoint = f"{self.state_url.rstrip('/')}/mcp/state/session"
        body = {
            "action": "CREATE",
            "thread_id": thread_id,
            "organizer": organizer,
            "participants": participants,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(endpoint, json=body)
            response.raise_for_status()
            return ToolCallOutcome(name="create_session", status="OK", payload=response.json())

    async def book_calendar(self, title: str, participants: list[str], slot: dict[str, str]) -> ToolCallOutcome:
        if not self.calendar_url:
            return ToolCallOutcome(name="book_calendar", status="SKIPPED", payload={"reason": "calendar_mcp_not_configured"})

        endpoint = f"{self.calendar_url.rstrip('/')}/mcp/calendar/book"
        body = {
            "action": "BOOK_MEETING",
            "title": title,
            "slot": slot,
            "participants": participants,
            "description": "Coordinated by CalSync.ai",
            "fallback_slots": [],
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(endpoint, json=body)
            response.raise_for_status()
            return ToolCallOutcome(name="book_calendar", status="OK", payload=response.json())
