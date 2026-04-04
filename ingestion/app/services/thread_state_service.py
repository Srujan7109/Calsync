from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ingestion.app.config import get_settings


@dataclass(slots=True)
class ThreadSessionState:
    session_id: str
    thread_id: str
    status: str
    organizer_email: str
    meeting_title: str
    participants: list[str]
    replied_participants: list[str]
    last_reminder_at: str | None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ThreadStateService:
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

    async def get_or_create_session(
        self,
        thread_id: str,
        organizer_email: str,
        meeting_title: str,
        participants: list[str] | None = None,
    ) -> ThreadSessionState:
        initial_participants = participants or []
        if not self._enabled():
            return ThreadSessionState(
                session_id=f"sess_{uuid.uuid4().hex[:8]}",
                thread_id=thread_id,
                status="AWAITING_REPLIES",
                organizer_email=organizer_email,
                meeting_title=meeting_title,
                participants=initial_participants,
                replied_participants=[],
                last_reminder_at=None,
            )

        session_row = await self._get_session_by_thread(thread_id)
        if not session_row:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"
            await self._upsert_session_row(
                session_id=session_id,
                thread_id=thread_id,
                status="AWAITING_REPLIES",
                organizer_email=organizer_email,
                meeting_title=meeting_title,
                participants=initial_participants,
            )
            return ThreadSessionState(
                session_id=session_id,
                thread_id=thread_id,
                status="AWAITING_REPLIES",
                organizer_email=organizer_email,
                meeting_title=meeting_title,
                participants=initial_participants,
                replied_participants=[],
                last_reminder_at=None,
            )

        session_id = str(session_row.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}")
        state = await self._get_app_setting_json(f"session_state:{session_id}")
        return ThreadSessionState(
            session_id=session_id,
            thread_id=thread_id,
            status=str(session_row.get("status") or "AWAITING_REPLIES"),
            organizer_email=str(session_row.get("organizer_email") or organizer_email),
            meeting_title=str(session_row.get("meeting_title") or meeting_title),
            participants=list(state.get("participants") or session_row.get("participants") or initial_participants),
            replied_participants=list(state.get("replied_participants") or []),
            last_reminder_at=state.get("last_reminder_at"),
        )

    async def persist_state(self, state: ThreadSessionState) -> None:
        if not self._enabled():
            return

        await self._upsert_session_row(
            session_id=state.session_id,
            thread_id=state.thread_id,
            status=state.status,
            organizer_email=state.organizer_email,
            meeting_title=state.meeting_title,
            participants=state.participants,
        )
        payload = {
            "participants": state.participants,
            "replied_participants": state.replied_participants,
            "last_reminder_at": state.last_reminder_at,
            "status": state.status,
            "thread_id": state.thread_id,
            "updated_at": _utcnow_iso(),
        }
        await self._upsert_app_setting_json(f"session_state:{state.session_id}", payload)

    async def _get_session_by_thread(self, thread_id: str) -> dict[str, object] | None:
        table_url = f"{self.base_url}/rest/v1/sessions"
        params = {
            "select": "session_id,thread_id,status,organizer_email,meeting_title,participants",
            "thread_id": f"eq.{thread_id}",
            "limit": "1",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(table_url, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()
            return data[0] if data else None

    async def _upsert_session_row(
        self,
        session_id: str,
        thread_id: str,
        status: str,
        organizer_email: str,
        meeting_title: str,
        participants: list[str],
    ) -> None:
        table_url = f"{self.base_url}/rest/v1/sessions"
        payload = {
            "session_id": session_id,
            "thread_id": thread_id,
            "status": status,
            "organizer_email": organizer_email,
            "meeting_title": meeting_title or "Meeting",
            "participants": participants,
            "updated_at": _utcnow_iso(),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            patch_response = await client.patch(
                table_url,
                headers=self._headers(prefer="return=representation"),
                params={"session_id": f"eq.{session_id}"},
                json={
                    "thread_id": thread_id,
                    "status": status,
                    "organizer_email": organizer_email,
                    "meeting_title": meeting_title or "Meeting",
                    "participants": participants,
                    "updated_at": payload["updated_at"],
                },
            )
            patch_response.raise_for_status()
            updated_rows = patch_response.json()
            if isinstance(updated_rows, list) and updated_rows:
                return

            insert_payload = {
                "session_id": session_id,
                "thread_id": thread_id,
                "status": status,
                "organizer_email": organizer_email,
                "meeting_title": meeting_title or "Meeting",
                "participants": participants,
                "collected_slots": {},
                "created_at": _utcnow_iso(),
                "updated_at": payload["updated_at"],
            }
            insert_response = await client.post(
                table_url,
                headers=self._headers(prefer="return=minimal"),
                json=insert_payload,
            )
            insert_response.raise_for_status()

    async def _get_app_setting_json(self, key: str) -> dict[str, object]:
        table_url = f"{self.base_url}/rest/v1/app_settings"
        params = {"select": "value", "key": f"eq.{key}", "limit": "1"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(table_url, headers=self._headers(), params=params)
            response.raise_for_status()
            rows = response.json()
            if not rows:
                return {}
            value = rows[0].get("value")
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    return {}
            return {}

    async def _upsert_app_setting_json(self, key: str, value: dict[str, object]) -> None:
        table_url = f"{self.base_url}/rest/v1/app_settings"
        payload = {"key": key, "value": value}
        async with httpx.AsyncClient(timeout=10.0) as client:
            patch_response = await client.patch(
                table_url,
                headers=self._headers(prefer="return=representation"),
                params={"key": f"eq.{key}"},
                json={"value": value},
            )
            patch_response.raise_for_status()
            updated_rows = patch_response.json()
            if isinstance(updated_rows, list) and updated_rows:
                return

            insert_response = await client.post(
                table_url,
                headers=self._headers(prefer="return=minimal"),
                json=payload,
            )
            insert_response.raise_for_status()
