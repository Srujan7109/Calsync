from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from importlib import import_module

import httpx

from ingestion.app.config import get_settings


_memory_store: dict[str, datetime] = {}


def build_email_hash(sender: str, message_id: str) -> str:
    return hashlib.sha256(f"{sender}:{message_id}".encode("utf-8")).hexdigest()


def _memory_check_and_mark(email_hash: str, ttl_seconds: int, now: datetime) -> bool:
    expired_keys = [key for key, expires_at in _memory_store.items() if expires_at <= now]
    for key in expired_keys:
        _memory_store.pop(key, None)

    if email_hash in _memory_store:
        return True

    _memory_store[email_hash] = now + timedelta(seconds=ttl_seconds)
    return False


async def _redis_check_and_mark(email_hash: str, redis_url: str, ttl_seconds: int) -> bool:
    redis_module = import_module("redis.asyncio")
    client = redis_module.from_url(redis_url, encoding="utf-8", decode_responses=True)

    is_duplicate = await client.exists(email_hash)
    if is_duplicate:
        await client.expire(email_hash, ttl_seconds)
        return True

    await client.set(email_hash, "1", ex=ttl_seconds)
    return False


async def _supabase_check_and_mark(
    email_hash: str,
    supabase_url: str,
    service_key: str,
    table_name: str,
    ttl_seconds: int,
    now: datetime,
) -> bool:
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    base_url = supabase_url.rstrip("/")
    table_url = f"{base_url}/rest/v1/{table_name}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        check_response = await client.get(
            table_url,
            headers={**headers, "Accept": "application/json"},
            params={"select": "email_hash", "email_hash": f"eq.{email_hash}", "limit": "1"},
        )
        check_response.raise_for_status()
        existing = check_response.json()

        if existing:
            patch_response = await client.patch(
                table_url,
                headers={**headers, "Prefer": "return=minimal"},
                params={"email_hash": f"eq.{email_hash}"},
                json={"expires_at": expires_at},
            )
            patch_response.raise_for_status()
            return True

        insert_response = await client.post(
            table_url,
            headers={**headers, "Prefer": "return=minimal"},
            json={"email_hash": email_hash, "expires_at": expires_at},
        )

        if insert_response.status_code == 409:
            return True

        insert_response.raise_for_status()
        return False


async def check_and_mark_duplicate(email_hash: str) -> bool:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    backend = settings.dedup_backend
    if backend == "auto":
        if settings.redis_url:
            backend = "redis"
        elif settings.supabase_url and settings.supabase_service_key:
            backend = "supabase"
        else:
            backend = "memory"

    if backend == "redis":
        if not settings.redis_url:
            raise RuntimeError("DEDUP_BACKEND=redis requires REDIS_URL")
        return await _redis_check_and_mark(email_hash, settings.redis_url, settings.dedup_ttl_seconds)

    if backend == "supabase":
        if not settings.supabase_url or not settings.supabase_service_key:
            raise RuntimeError("DEDUP_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SERVICE_KEY")
        return await _supabase_check_and_mark(
            email_hash=email_hash,
            supabase_url=settings.supabase_url,
            service_key=settings.supabase_service_key,
            table_name=settings.supabase_dedup_table,
            ttl_seconds=settings.dedup_ttl_seconds,
            now=now,
        )

    return _memory_check_and_mark(email_hash, settings.dedup_ttl_seconds, now)
