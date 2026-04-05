"""
auth.py — CalSync.ai Gmail MCP

Google OAuth 2.0 credential management.
Provides get_credentials(), get_gmail_service(), get_calendar_service().
Run this file directly (python auth.py) once to generate the refresh token.
"""

import os
import logging
from typing import Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

# Scopes required for CalSync.ai
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]

TOKEN_URI = "https://oauth2.googleapis.com/token"


_CREDS_CACHE: Optional[Credentials] = None
_GMAIL_SERVICE_CACHE = None
_CALENDAR_SERVICE_CACHE = None


def get_credentials() -> Credentials:
    """
    Build and return valid Google OAuth 2.0 credentials.

    Constructs a Credentials object from environment variables
    (GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET).
    If the credentials are expired, automatically refreshes them using
    the refresh token.

    Returns:
        google.oauth2.credentials.Credentials: Valid, non-expired credentials.

    Raises:
        RuntimeError: If credential variables are not set or refresh fails.
    """
    if not settings.GOOGLE_REFRESH_TOKEN:
        raise RuntimeError(
            "GOOGLE_REFRESH_TOKEN is not set. "
            "Run `python auth.py` to generate it."
        )
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is not set. "
            "Run `python auth.py` to generate them."
        )

    global _CREDS_CACHE

    if _CREDS_CACHE is None:
        _CREDS_CACHE = Credentials(
            token=None,
            refresh_token=settings.GOOGLE_REFRESH_TOKEN,
            token_uri=TOKEN_URI,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=SCOPES,
        )

    # Refresh if expired (or token is None — first call)
    if not _CREDS_CACHE.valid:
        try:
            _CREDS_CACHE.refresh(Request())
            logger.debug("Google credentials refreshed successfully.")
        except Exception as exc:
            logger.error("Failed to refresh Google credentials: %s", exc)
            raise RuntimeError(f"Credential refresh failed: {exc}") from exc

    return _CREDS_CACHE


def get_gmail_service():
    """
    Build and return an authenticated Gmail API service client (v1).

    Returns:
        googleapiclient.discovery.Resource: Gmail API service resource.

    Raises:
        RuntimeError: If credentials cannot be obtained.
    """
    global _GMAIL_SERVICE_CACHE
    if _GMAIL_SERVICE_CACHE is None:
        creds = get_credentials()
        _GMAIL_SERVICE_CACHE = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _GMAIL_SERVICE_CACHE


def get_calendar_service():
    """
    Build and return an authenticated Google Calendar API service client (v3).

    Returns:
        googleapiclient.discovery.Resource: Calendar API service resource.

    Raises:
        RuntimeError: If credentials cannot be obtained.
    """
    global _CALENDAR_SERVICE_CACHE
    if _CALENDAR_SERVICE_CACHE is None:
        creds = get_credentials()
        _CALENDAR_SERVICE_CACHE = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _CALENDAR_SERVICE_CACHE


def run_initial_oauth_flow() -> None:
    """
    Run the OAuth 2.0 installed-app flow to generate a refresh token.

    This function should be called ONCE manually on a machine with a browser.
    It will open the Google consent screen, and upon authorisation, print the
    GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, and GOOGLE_CLIENT_SECRET values
    that must be added to your .env file.

    Requires: credentials.json (Desktop app type) in the path defined by
    GOOGLE_CREDENTIALS_JSON.
    """
    credentials_path = settings.GOOGLE_CREDENTIALS_JSON
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"credentials.json not found at: {credentials_path}. "
            "Download it from Google Cloud Console → APIs & Services → Credentials."
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
