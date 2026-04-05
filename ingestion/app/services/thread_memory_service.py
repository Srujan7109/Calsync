from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ingestion.app.config import get_settings


logger = logging.getLogger("uvicorn.error")


class ThreadMemoryService:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = (settings.supabase_url or "").rstrip("/")
        self.service_key = settings.supabase_service_key

    def _enabled(self) -> bool:
        return bool(self.base_url and self.service_key)

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.service_key or "",
            "Authorization": f"Bearer {self.service_key or ''}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def store_email(
        self,
        *,
        message_id: str,
        thread_id: str,
        from_email: str,
        to_emails: list[str],
        cc_emails: list[str],
        subject: str,
        body_text: str,
        received_at: str,
        email_hash: str,
        in_reply_to: str | None = None,
        references_header: str | None = None,
        body_html: str | None = None,
        session_id: str | None = None,
        direction: str = "INBOUND",
        processing_status: str = "PENDING",
        is_read: bool = True,
    ) -> None:
        if not self._enabled():
            return

        now = datetime.now(timezone.utc).isoformat()
        payload: dict[str, object] = {
            "message_id": message_id,
            "thread_id": thread_id,
            "session_id": session_id,
            "direction": direction,
            "from_email": from_email,
            "to_emails": to_emails,
            "cc_emails": cc_emails,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "in_reply_to": in_reply_to,
            "references_header": references_header,
            "labels": [],
            "processing_status": processing_status,
            "email_hash": email_hash,
            "is_read": is_read,
            "has_attachments": False,
            "received_at": received_at,
            "ingested_at": now,
            "processed_at": None,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/rest/v1/emails",
                    headers=self._headers(prefer="return=minimal"),
                    json=payload,
                )
                response.raise_for_status()
        except Exception as exc:  # pragma: no cover - operational safety
            logger.warning("store_email skipped: %s", exc)

    async def get_thread_emails(self, thread_id: str, limit: int = 20) -> list[dict[str, object]]:
        if not self._enabled():
            return []

        params = {
            "select": "message_id,thread_id,session_id,direction,from_email,to_emails,cc_emails,subject,body_text,body_html,in_reply_to,references_header,received_at,ingested_at",
            "thread_id": f"eq.{thread_id}",
            "order": "received_at.asc",
            "limit": str(max(limit, 1)),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/rest/v1/emails",
                    headers=self._headers(),
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, list) else []
        except Exception as exc:  # pragma: no cover - operational safety
            logger.warning("get_thread_emails skipped: %s", exc)
            return []