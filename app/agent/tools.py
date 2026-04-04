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
        self.gmail_url = settings.gmail_mcp_url
        self.gmail_sender_email = settings.gmail_sender_email
        self.gmail_send_path = settings.gmail_mcp_send_path
        self.calendar_url = settings.calendar_mcp_url
        self.calendar_book_path = settings.calendar_mcp_book_path

    async def send_gmail_message(
        self,
        recipients: list[str],
        subject: str,
        body_text: str,
        thread_id: str = "",
    ) -> ToolCallOutcome:
        if not self.gmail_url:
            return ToolCallOutcome(name="send_gmail_message", status="SKIPPED", payload={"reason": "gmail_mcp_not_configured"})

        endpoint = f"{self.gmail_url.rstrip('/')}/{self.gmail_send_path.lstrip('/')}"
        body = {
            "action": "SEND_EMAIL",
            "from": self.gmail_sender_email,
            "to": recipients,
            "subject": subject,
            "body_text": body_text,
            "thread_id": thread_id,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(endpoint, json=body)
            response.raise_for_status()
            return ToolCallOutcome(name="send_gmail_message", status="OK", payload=response.json())

    async def book_calendar(self, title: str, participants: list[str], slot: dict[str, str]) -> ToolCallOutcome:
        if not self.calendar_url:
            return ToolCallOutcome(name="book_calendar", status="SKIPPED", payload={"reason": "calendar_mcp_not_configured"})

        endpoint = f"{self.calendar_url.rstrip('/')}/{self.calendar_book_path.lstrip('/')}"
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
