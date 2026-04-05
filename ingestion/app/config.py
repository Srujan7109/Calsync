from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_v1_prefix: str
    dedup_ttl_seconds: int
    accepted_keywords: list[str]
    dedup_backend: Literal["auto", "redis", "supabase", "memory"]
    redis_url: str
    supabase_url: str
    supabase_service_key: str
    supabase_dedup_table: str

    imap_host: str
    imap_port: int
    imap_username: str
    imap_app_password: str
    imap_mailbox: str
    imap_search_criteria: str
    imap_poll_interval_seconds: int
    imap_poll_batch_size: int
    imap_auto_poll_enabled: bool

    gemini_api_key: str
    gemini_model: str
    reminder_cooldown_minutes: int

    gmail_sender_email: str
    gmail_mcp_url: str
    gmail_mcp_send_path: str
    calendar_mcp_url: str
    calendar_mcp_book_path: str
    calendar_mcp_freebusy_path: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
