"""
config.py — CalSync.ai Gmail MCP

Central configuration using pydantic-settings.
All environment variables are loaded from .env.
Import `settings` from this module everywhere config is needed.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=str(MODULE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Supabase ────────────────────────────────────────────────────────────
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ...,
        description="Supabase service role key — bypasses RLS",
        validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"),
    )

    # ── Google OAuth 2.0 ─────────────────────────────────────────────────────
    GOOGLE_CREDENTIALS_JSON: str = Field(
        default=str(MODULE_DIR / "credentials.json"),
        description="Path to Google Desktop-app credentials.json",
    )
    GOOGLE_REFRESH_TOKEN: str = Field(
        default="", description="OAuth refresh token (generated via auth.py)"
    )
    GOOGLE_CLIENT_ID: str = Field(
        default="", description="Google OAuth client ID"
    )
    GOOGLE_CLIENT_SECRET: str = Field(
        default="", description="Google OAuth client secret"
    )

    # ── CalSync Inbox ────────────────────────────────────────────────────────
    CALSYNC_EMAIL: str = Field(
        default="calsync1.ai@gmail.com",
        description="The central CalSync.ai Gmail address",
    )

    # ── Gmail Push Notifications ─────────────────────────────────────────────
    GMAIL_PUBSUB_TOPIC: str = Field(
        default="",
        description="Google Cloud Pub/Sub topic for Gmail push notifications",
    )

    # ── Server ───────────────────────────────────────────────────────────────

    PORT: int = Field(default=8006, description="Port for the FastAPI server")
    LOG_LEVEL: str = Field(
        default="INFO", description="Logging level (DEBUG/INFO/WARNING/ERROR)"
    )


# Singleton — import this everywhere
settings = Settings()
