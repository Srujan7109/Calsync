from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import logging as logger

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
            # Brand new thread — create session with initial participants
            session_id = f"sess_{uuid.uuid4().hex[:8]}"
            await self._upsert_session_row(
                session_id=session_id,
                thread_id=thread_id,
                status="AWAITING_REPLIES",
                organizer_email=organizer_email,
                meeting_title=meeting_title,
                participants=initial_participants,
                replied_participants=[],
                last_reminder_at=None,
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

        # Existing session — restore full state from sessions row
        session_id = str(session_row.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}")
        raw_participants = session_row.get("participants") or []
        raw_replied = session_row.get("replied_participants") or []

        # Merge persisted participants with any new ones from current email
        merged_participants = list(
            dict.fromkeys(
                [p for p in raw_participants if p] +
                [p for p in initial_participants if p]
            )
        )

        return ThreadSessionState(
            session_id=session_id,
            thread_id=thread_id,
            status=str(session_row.get("status") or "AWAITING_REPLIES"),
            organizer_email=str(session_row.get("organizer_email") or organizer_email),
            meeting_title=str(session_row.get("meeting_title") or meeting_title),
            participants=merged_participants,
            replied_participants=list(raw_replied) if isinstance(raw_replied, list) else [],
            last_reminder_at=session_row.get("last_reminder_at"),
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
            replied_participants=state.replied_participants,
            last_reminder_at=state.last_reminder_at,
        )

    async def _get_session_by_thread(self, thread_id: str) -> dict[str, object] | None:
        table_url = f"{self.base_url}/rest/v1/sessions"
        params = {
            "select": "session_id,thread_id,status,organizer_email,meeting_title,participants,replied_participants,last_reminder_at",
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
        replied_participants: list[str],
        last_reminder_at: str | None,
    ) -> None:
        table_url = f"{self.base_url}/rest/v1/sessions"
        now = _utcnow_iso()
        update_body = {
            "thread_id": thread_id,
            "status": status,
            "organizer_email": organizer_email,
            "meeting_title": meeting_title or "Meeting",
            "participants": participants,
            "replied_participants": replied_participants,
            "last_reminder_at": last_reminder_at,
            "updated_at": now,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            patch_response = await client.patch(
                table_url,
                headers=self._headers(prefer="return=representation"),
                params={"session_id": f"eq.{session_id}"},
                json=update_body,
            )
            patch_response.raise_for_status()
            updated_rows = patch_response.json()
            if isinstance(updated_rows, list) and updated_rows:
                return

            # Row doesn't exist yet — insert fresh
            insert_payload = {
                "session_id": session_id,
                "thread_id": thread_id,
                "status": status,
                "organizer_email": organizer_email,
                "meeting_title": meeting_title or "Meeting",
                "participants": participants,
                "replied_participants": replied_participants,
                "last_reminder_at": last_reminder_at,
                "collected_slots": {},
                "created_at": now,
                "updated_at": now,
            }
            insert_response = await client.post(
                table_url,
                headers=self._headers(prefer="return=minimal"),
                json=insert_payload,
            )
            insert_response.raise_for_status()
    
    async def update_participant_slots(self, session_id: str, participant_email: str, slots: list) -> None:
        """Append parsed slots to collected_slots JSONB for a participant."""
        if not self._enabled():
            return
        try:
            # Read current collected_slots
            table_url = f"{self.base_url}/rest/v1/sessions"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    table_url,
                    headers=self._headers(),
                    params={"select": "collected_slots", "session_id": f"eq.{session_id}", "limit": "1"},
                )
                rows = r.json() if r.status_code == 200 else []
                current = (rows[0].get("collected_slots") or {}) if rows else {}
                current[participant_email] = slots
                await client.patch(
                    table_url,
                    headers=self._headers(prefer="return=minimal"),
                    params={"session_id": f"eq.{session_id}"},
                    json={"collected_slots": current, "updated_at": _utcnow_iso()},
                )
        except Exception as exc:
            logger.warning("update_participant_slots failed: %s", exc)

    async def get_collected_slots(self, session_id: str) -> dict:
        """Return collected_slots JSONB for a session."""
        if not self._enabled():
            return {}
        try:
            table_url = f"{self.base_url}/rest/v1/sessions"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    table_url,
                    headers=self._headers(),
                    params={"select": "collected_slots", "session_id": f"eq.{session_id}", "limit": "1"},
                )
                rows = r.json() if r.status_code == 200 else []
                return (rows[0].get("collected_slots") or {}) if rows else {}
        except Exception as exc:
            logger.warning("get_collected_slots failed: %s", exc)
            return {}
