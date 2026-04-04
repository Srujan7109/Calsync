from __future__ import annotations

from dataclasses import dataclass
import re

import httpx

from ingestion.app.config import get_settings


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
        self.calendar_freebusy_path = settings.calendar_mcp_freebusy_path

    async def _post_json(self, endpoint: str, body: dict[str, object], tool_name: str) -> ToolCallOutcome:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(endpoint, json=body)
                response.raise_for_status()
                return ToolCallOutcome(name=tool_name, status="OK", payload=response.json())
        except Exception as exc:  # pragma: no cover - network/runtime safety
            return ToolCallOutcome(name=tool_name, status="ERROR", payload={"error": str(exc)})

    async def send_gmail_message(
        self,
        recipients: list[str],
        subject: str,
        body_text: str,
        thread_id: str = "",
        session_id: str | None = None,
    ) -> ToolCallOutcome:
        if not self.gmail_url:
            return ToolCallOutcome(name="send_gmail_message", status="SKIPPED", payload={"reason": "gmail_mcp_not_configured"})

        sanitized_thread_id = thread_id.strip() if thread_id else ""
        # Gmail thread ids are opaque alphanumeric ids; RFC message-id values are not valid here.
        if not re.fullmatch(r"[A-Za-z0-9]{8,}", sanitized_thread_id):
            sanitized_thread_id = ""

        endpoint = f"{self.gmail_url.rstrip('/')}/{self.gmail_send_path.lstrip('/')}"
        body = {
            "to_emails": recipients,
            "subject": subject,
            "body_text": body_text,
            "thread_id": sanitized_thread_id or None,
            "session_id": session_id,
        }
        if self.gmail_sender_email:
            body["from_email"] = self.gmail_sender_email
        return await self._post_json(endpoint, body, "send_gmail_message")

    async def check_freebusy(self, participants: list[str], slot: dict[str, str]) -> ToolCallOutcome:
        if not self.calendar_url:
            return ToolCallOutcome(name="check_freebusy", status="SKIPPED", payload={"reason": "calendar_mcp_not_configured"})

        endpoint = f"{self.calendar_url.rstrip('/')}/{self.calendar_freebusy_path.lstrip('/')}"
        body = {
            "participants": participants,
            "slots": [{"start": slot.get("start", ""), "end": slot.get("end", "")}],
        }
        return await self._post_json(endpoint, body, "check_freebusy")

    async def fetch_thread(self, thread_id: str, max_messages: int = 50) -> ToolCallOutcome:
        if not self.gmail_url:
            return ToolCallOutcome(name="fetch_thread", status="SKIPPED", payload={"reason": "gmail_mcp_not_configured"})

        endpoint = f"{self.gmail_url.rstrip('/')}/thread/fetch"
        body = {"thread_id": thread_id, "max_messages": max_messages}
        return await self._post_json(endpoint, body, "fetch_thread")

    async def book_calendar(
        self,
        title: str,
        participants: list[str],
        slot: dict[str, str],
        organizer_email: str,
        session_id: str,
    ) -> ToolCallOutcome:
        if not self.calendar_url:
            return ToolCallOutcome(name="book_calendar", status="SKIPPED", payload={"reason": "calendar_mcp_not_configured"})

        endpoint = f"{self.calendar_url.rstrip('/')}/{self.calendar_book_path.lstrip('/')}"
        body = {
            "action": "BOOK_MEETING",
            "title": title,
            "slot": {"start": slot.get("start", ""), "end": slot.get("end", "")},
            "participants": participants,
            "organizer_email": organizer_email,
            "description": "Coordinated by CalSync.ai",
            "fallback_slots": [],
            "session_id": session_id,
        }
        return await self._post_json(endpoint, body, "book_calendar")
