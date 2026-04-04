from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_v1_prefix: str = "/api/v1"
    dedup_ttl_seconds: int = 24 * 60 * 60
    accepted_keywords: list[str] = Field(
        default_factory=lambda: ["meeting", "schedule", "available", "call", "sync", "time", "slot"]
    )
    dedup_backend: Literal["auto", "redis", "supabase", "memory"] = "auto"
    redis_url: str | None = None
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_dedup_table: str = "idempotency_keys"

    imap_host: str | None = None
    imap_port: int = 993
    imap_username: str | None = None
    imap_app_password: str | None = None
    imap_mailbox: str = "INBOX"
    imap_search_criteria: str = "UNSEEN"
    imap_poll_interval_seconds: int = 10
    imap_poll_batch_size: int = 20
    imap_auto_poll_enabled: bool = True

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    gmail_sender_email: str | None = None
    gmail_mcp_url: str | None = None
    gmail_mcp_send_path: str = "/mcp/gmail/send"
    calendar_mcp_url: str | None = None
    calendar_mcp_book_path: str = "/mcp/calendar/book"


@lru_cache
def get_settings() -> Settings:
    return Settings()
