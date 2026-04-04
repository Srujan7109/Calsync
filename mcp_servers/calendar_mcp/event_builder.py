"""
event_builder.py — CalSync.ai Calendar MCP

Builds Google Calendar API event body dicts and extracts Meet links.
No external API calls — pure data construction utilities.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import uuid4

from models import TimeSlot

logger = logging.getLogger(__name__)

AI_DISCLAIMER = """

---
This meeting was autonomously coordinated by CalSync.ai,
an AI-powered email scheduling assistant.
To modify or cancel, reply to the original scheduling email.
---"""


def build_event_body(
    title: str,
    slot: TimeSlot,
    participants: List[str],
    description: str = "",
    session_id: Optional[str] = None,
    organizer_email: Optional[str] = None,
) -> dict:
    """
    Build a complete Google Calendar API event dict ready for events().insert().

    Includes:
    - Conference data request to auto-generate a Google Meet link.
    - Email reminder (24 h before) and popup reminder (15 min before).
    - Extended private properties for CalSync traceability.
    - The CalSync.ai AI disclaimer appended to the description.

    Args:
        title: The meeting title (used as `summary`).
        slot: TimeSlot with ISO 8601 UTC start and end strings.
        participants: List of all attendee email addresses.
        description: Optional base description text.
        session_id: CalSync session UUID for traceability.
        organizer_email: Email of the meeting organiser.

    Returns:
        dict: A fully-formed Google Calendar event body.
    """
    request_id = f"calsync-{session_id or uuid4().hex[:8]}"
    full_description = description + AI_DISCLAIMER

    event = {
        "summary": title,
        "description": full_description,
        "start": {
            "dateTime": slot.start,
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": slot.end,
            "timeZone": "UTC",
        },
        "attendees": [{"email": p} for p in participants],
        "conferenceData": {
            "createRequest": {
                "requestId": request_id,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 1440},   # 24 hours
                {"method": "popup", "minutes": 15},
            ],
        },
        "guestsCanInviteOthers": False,
        "extendedProperties": {
            "private": {
                "coordinated_by": "calsync_ai",
                "session_id": session_id or "",
            }
        },
    }

    return event


def extract_meet_link(event: dict) -> Optional[str]:
    """
    Extract the Google Meet video call URL from a Google Calendar event dict.

    Navigates: event → conferenceData → entryPoints → [type == 'video'] → uri.

    Args:
        event: A Google Calendar event resource dict (as returned by the API).

    Returns:
        str | None: The Google Meet URL, or None if not present.
    """
    conference_data = event.get("conferenceData", {})
    entry_points = conference_data.get("entryPoints", [])

    for entry in entry_points:
        if entry.get("entryPointType") == "video":
            uri = entry.get("uri")
            if uri:
                return uri

    return None
