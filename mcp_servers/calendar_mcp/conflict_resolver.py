"""
conflict_resolver.py — CalSync.ai Calendar MCP

Handles free/busy checking and slot selection logic.
Uses a fail-open policy: API errors return no conflicts so booking can proceed.
No LLM calls — pure Calendar API business logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from models import FreeBusySlotResult, TimeSlot

logger = logging.getLogger(__name__)


def check_slot_conflicts(
    service,
    participants: List[str],
    slot: TimeSlot,
) -> List[dict]:
    """
    Check whether any participants are busy during the given time slot.

    Calls the Google Calendar FreeBusy API for all participants simultaneously.
    Uses a fail-open policy: if the API throws any exception, the slot is
    considered free and an empty conflict list is returned.

    Args:
        service: Authenticated Google Calendar API service resource.
        participants: List of participant email addresses to check.
        slot: TimeSlot to check availability for.

    Returns:
        List[dict]: List of {participant, conflict_count} dicts for busy
        participants. Empty list means all participants are free.
    """
    try:
        body = {
            "timeMin": slot.start,
            "timeMax": slot.end,
            "items": [{"id": p} for p in participants],
            "timeZone": "UTC",
        }
        response = service.freebusy().query(body=body).execute()
        calendars = response.get("calendars", {})

        conflicts = []
        for participant in participants:
            busy_periods = calendars.get(participant, {}).get("busy", [])
            if busy_periods:
                conflicts.append(
                    {
                        "participant": participant,
                        "conflict_count": len(busy_periods),
                    }
                )
        return conflicts

    except Exception as exc:
        logger.warning(
            "check_slot_conflicts: FreeBusy API error (fail-open, treating as free): %s",
            exc,
        )
        return []  # Fail-open: allow booking to proceed


def find_available_slot(
    service,
    participants: List[str],
    slots: List[TimeSlot],
) -> tuple[Optional[TimeSlot], int, Optional[str]]:
    """
    Iterate through a list of slots and return the first one with no conflicts.

    Tries slots in order (index 0 = primary, index 1+ = fallbacks). Stops at
    the first free slot.

    Args:
        service: Authenticated Google Calendar API service resource.
        participants: List of participant email addresses.
        slots: Ordered list of candidate TimeSlots.

    Returns:
        Tuple of (available_slot, slot_index, conflict_reason):
          - available_slot: The first conflict-free TimeSlot, or None.
          - slot_index: Index of the chosen slot, or -1 if all conflicted.
          - conflict_reason: Descriptive string if all conflicted, else None.
    """
    if not slots:
        return None, -1, "No slots provided."

    for index, slot in enumerate(slots):
        conflicts = check_slot_conflicts(service, participants, slot)
        if not conflicts:
            return slot, index, None

        logger.info(
            "Slot %d (%s → %s) has %d conflict(s): %s",
            index,
            slot.start,
            slot.end,
            len(conflicts),
            [c["participant"] for c in conflicts],
        )

    return None, -1, "All slots conflicted."


def check_all_slots(
    service,
    participants: List[str],
    slots: List[TimeSlot],
) -> List[FreeBusySlotResult]:
    """
    Check free/busy status for ALL provided slots (does not stop at first free one).

    Used by the /freebusy endpoint to return a comprehensive availability
    overview for the caller to inspect.

    Args:
        service: Authenticated Google Calendar API service resource.
        participants: List of participant email addresses.
        slots: List of TimeSlots to check.

    Returns:
        List[FreeBusySlotResult]: One result per slot with is_free and conflicts.
    """
    results: List[FreeBusySlotResult] = []
    for slot in slots:
        conflicts = check_slot_conflicts(service, participants, slot)
        results.append(
            FreeBusySlotResult(
                slot=slot,
                is_free=(len(conflicts) == 0),
                conflicts=conflicts,
            )
        )
    return results


def generate_heatmap(
    service,
    participants: List[str],
    from_date: str,
    to_date: str,
    slot_duration_minutes: int,
) -> dict:
    """
    Generate a free/busy heatmap across a date range for all participants.

    Divides the date range into time slots of `slot_duration_minutes` length
    and checks each slot's availability. The result is a dict keyed by slot
    start time showing how many participants are free.

    Args:
        service: Authenticated Google Calendar API service resource.
        participants: List of participant email addresses.
        from_date: Start date string in YYYY-MM-DD format.
        to_date: End date string in YYYY-MM-DD format (inclusive).
        slot_duration_minutes: Duration of each slot in minutes.

    Returns:
        dict: {
            "<ISO 8601 UTC slot start>": {
                "free_count": int,
                "total": int,
                "all_free": bool,
                "participants_free": List[str]
            },
            ...
        }

    Example result key:
        "2025-01-06T08:00:00+00:00": {"free_count": 2, "total": 3, ...}
    """
    heatmap: dict = {}
    duration = timedelta(minutes=slot_duration_minutes)
    total = len(participants)

    # Parse date range boundaries (UTC midnight to UTC midnight)
    try:
        start_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ) + timedelta(days=1)  # inclusive of to_date
    except ValueError as exc:
        logger.error("generate_heatmap: invalid date format: %s", exc)
        return {}

    current = start_dt
    while current + duration <= end_dt:
        slot_end = current + duration
        slot = TimeSlot(start=current.isoformat(), end=slot_end.isoformat())
        conflicts = check_slot_conflicts(service, participants, slot)

        conflicted_participants = {c["participant"] for c in conflicts}
        free_participants = [p for p in participants if p not in conflicted_participants]

        heatmap[current.isoformat()] = {
            "free_count": len(free_participants),
            "total": total,
            "all_free": len(free_participants) == total,
            "participants_free": free_participants,
        }
        current += duration

    return heatmap
