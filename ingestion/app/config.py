from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_v1_prefix: str = "/api/v1"
    dedup_ttl_seconds: int = 24 * 60 * 60
    accepted_keywords: list[str] = Field(
        default_factory=lambda: ["meeting", "schedule", "available", "call", "sync", "time", "slot", "meet"]
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
    use_gmail_api_polling: bool = True

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    thread_intelligence_enabled: bool = True
    reminder_cooldown_minutes: int = 120

    gmail_sender_email: str | None = None
    gmail_mcp_url: str | None = None
    gmail_mcp_send_path: str = "/send"
    calendar_mcp_url: str | None = None
    calendar_mcp_book_path: str = "/book"
    calendar_mcp_freebusy_path: str = "/freebusy"


@lru_cache
def get_settings() -> Settings:
    return Settings()
