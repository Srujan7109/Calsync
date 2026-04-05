"""
label_service.py — CalSync.ai Gmail MCP

Manages CalSync-specific Gmail labels.
Ensures all required labels exist at startup and provides
helper functions for applying/removing them.
"""

from __future__ import annotations

import logging
from typing import Dict

from gmail_client import get_or_create_label, mark_as_read, modify_labels

logger = logging.getLogger(__name__)

# ── CalSync label name mapping ────────────────────────────────────────────────
CALSYNC_LABELS: Dict[str, str] = {
    "PROCESSED": "CalSync/Processed",
    "PENDING": "CalSync/Pending",
    "BOOKED": "CalSync/Booked",
    "NO_OVERLAP": "CalSync/NoOverlap",
    "CLARIFICATION": "CalSync/Clarification",
    "FAILED": "CalSync/Failed",
}

# Cache: {label_name → label_id}
_label_id_cache: Dict[str, str] = {}


def ensure_calsync_labels_exist() -> Dict[str, str]:
    """
    Ensure all CalSync classification labels exist in Gmail.

    Called once during server startup. Creates any missing labels and
    caches the label_name → label_id mapping in memory for fast lookups.

    Returns:
        dict: {label_key → gmail_label_id} for all CALSYNC_LABELS.

    Raises:
        RuntimeError: If the Gmail API call fails for any label.
    """
    global _label_id_cache
    result: Dict[str, str] = {}

    for key, label_name in CALSYNC_LABELS.items():
        try:
            label_id = get_or_create_label(label_name)
            _label_id_cache[label_name] = label_id
            result[key] = label_id
            logger.info("Label ready: '%s' → %s", label_name, label_id)
        except RuntimeError as exc:
            logger.error(
                "Failed to ensure label '%s' exists: %s", label_name, exc
            )
            raise

    return result


def _resolve_label_id(label_key: str) -> str:
    """
    Resolve a CALSYNC_LABELS key to a Gmail label ID.

    Uses the in-memory cache set by ensure_calsync_labels_exist().
    Falls back to the Gmail API if the cache is cold.

    Args:
        label_key: A key from CALSYNC_LABELS (e.g. "PROCESSED").

    Returns:
        str: The Gmail label ID.

    Raises:
        ValueError: If the label_key is not in CALSYNC_LABELS.
        RuntimeError: If the Gmail API call fails.
    """
    if label_key not in CALSYNC_LABELS:
        raise ValueError(
            f"Unknown label key: '{label_key}'. "
            f"Valid keys: {list(CALSYNC_LABELS.keys())}"
        )
    label_name = CALSYNC_LABELS[label_key]
    if label_name in _label_id_cache:
        return _label_id_cache[label_name]

    # Cache miss — resolve via Gmail API
    label_id = get_or_create_label(label_name)
    _label_id_cache[label_name] = label_id
    return label_id


def apply_label(message_id: str, label_key: str) -> None:
    """
    Apply a CalSync classification label to a Gmail message.

    Args:
        message_id: Gmail message ID to label.
        label_key: CALSYNC_LABELS key (e.g. "PROCESSED", "FAILED").

    Raises:
        ValueError: If label_key is not recognised.
        RuntimeError: If the Gmail API call fails.
    """
    label_id = _resolve_label_id(label_key)
    modify_labels(message_id, add_labels=[label_id], remove_labels=[])
    logger.debug("Applied label '%s' to message %s", label_key, message_id)


def remove_label(message_id: str, label_key: str) -> None:
    """
    Remove a CalSync classification label from a Gmail message.

    Args:
        message_id: Gmail message ID to update.
        label_key: CALSYNC_LABELS key to remove (e.g. "PENDING").

    Raises:
        ValueError: If label_key is not recognised.
        RuntimeError: If the Gmail API call fails.
    """
    label_id = _resolve_label_id(label_key)
    modify_labels(message_id, add_labels=[], remove_labels=[label_id])
    logger.debug("Removed label '%s' from message %s", label_key, message_id)


def mark_processed(message_id: str) -> None:
    """
    Mark a Gmail message as fully processed by CalSync.

    Applies the PROCESSED label, removes the PENDING label (if present),
    and marks the message as read.

    Args:
        message_id: Gmail message ID to mark as processed.

    Raises:
        RuntimeError: If any Gmail API call fails.
    """
    processed_id = _resolve_label_id("PROCESSED")
    pending_id = _label_id_cache.get(CALSYNC_LABELS["PENDING"])

    add = [processed_id]
    remove = [pending_id] if pending_id else []

    modify_labels(message_id, add_labels=add, remove_labels=remove)
    mark_as_read(message_id)
    logger.info("Marked message %s as processed and read.", message_id)


def mark_failed(message_id: str) -> None:
    """
    Apply the FAILED label to a Gmail message that could not be processed.

    Args:
        message_id: Gmail message ID to label as failed.

    Raises:
        RuntimeError: If the Gmail API call fails.
    """
    apply_label(message_id, "FAILED")
    logger.info("Marked message %s as failed.", message_id)
