"""
auth.py — CalSync.ai Calendar MCP

Google OAuth 2.0 credential management for the Calendar API.
Provides get_credentials() and a cached get_calendar_service().
Run this file directly (python auth.py) once to generate the refresh token.
"""

import logging
import os
import threading

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"

# ── Service cache ─────────────────────────────────────────────────────────────
_service_cache = None
_service_lock = threading.Lock()


def get_credentials() -> Credentials:
    """
    Build and return valid Google OAuth 2.0 credentials for the Calendar API.

    Constructs a Credentials object from environment variables
    (GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET).
    If the credentials are expired or have no access token, automatically
    refreshes them using the stored refresh token.

    Returns:
        google.oauth2.credentials.Credentials: Valid, non-expired credentials.

    Raises:
        RuntimeError: If env vars are missing or the refresh fails.
    """
    if not settings.GOOGLE_REFRESH_TOKEN:
        raise RuntimeError(
            "GOOGLE_REFRESH_TOKEN is not set. Run `python auth.py` to generate it."
        )
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is not set. "
            "Run `python auth.py` to generate them."
        )

    creds = Credentials(
        token=None,
        refresh_token=settings.GOOGLE_REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )

    if not creds.valid:
        try:
            creds.refresh(Request())
            logger.info("Google credentials refreshed successfully.")
        except Exception as exc:
            logger.error("Failed to refresh Google credentials: %s", exc)
            raise RuntimeError(f"Credential refresh failed: {exc}") from exc

    return creds


def get_calendar_service():
    """
    Return an authenticated Google Calendar API service client (v3).

    The service object is cached in-process. Only the first call builds it;
    subsequent calls return the cached instance. Thread-safe via a lock.

    Returns:
        googleapiclient.discovery.Resource: Calendar v3 API service.

    Raises:
        RuntimeError: If credentials cannot be obtained.
    """
    global _service_cache
    with _service_lock:
        if _service_cache is None:
            creds = get_credentials()
            _service_cache = build("calendar", "v3", credentials=creds)
            logger.debug("Calendar service built and cached.")
        return _service_cache


def run_initial_oauth_flow() -> None:
    """
    Run the OAuth 2.0 installed-app consent flow to generate a refresh token.

    Call this ONCE manually on a machine with a browser. Opens the Google
    consent screen; on success, prints the tokens that must be added to .env.

    Requires: credentials.json (Desktop app type) at the path in
    GOOGLE_CREDENTIALS_JSON.
    """
    credentials_path = settings.GOOGLE_CREDENTIALS_JSON
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"credentials.json not found at: {credentials_path}. "
            "Download from Google Cloud Console → APIs & Services → Credentials."
        )

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n" + "=" * 60)
    print("OAuth flow complete. Add these to your .env file:")
    print("=" * 60)
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_initial_oauth_flow()
