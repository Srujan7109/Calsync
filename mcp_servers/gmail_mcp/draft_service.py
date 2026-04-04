"""
draft_service.py — CalSync.ai Gmail MCP

Manages the full lifecycle of email drafts:
  create → pending_review → (approve & send) | discard
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import HTTPException

import gmail_client
import supabase_ops
from models import DraftCreateRequest, LogRequest

logger = logging.getLogger(__name__)


def create_draft(req: DraftCreateRequest) -> dict:
    """
    Create an email draft and persist it to both Gmail and Supabase.

    Steps:
      1. Create the draft in Gmail via gmail_client.create_draft().
      2. Store the draft metadata in Supabase with status PENDING_REVIEW.
      3. Write an activity log entry.

    Args:
        req: DraftCreateRequest — recipient list, subject, body, and metadata.

    Returns:
        dict: {draft_id (Supabase UUID), gmail_draft_id, status}

    Raises:
        HTTPException 500: If Gmail or Supabase operations fail.
    """
    # Step 1: create in Gmail
    try:
        gmail_draft_id = gmail_client.create_draft(req)
    except RuntimeError as exc:
        logger.error("create_draft: Gmail draft creation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Gmail draft creation failed: {exc}")

    # Step 2: persist to Supabase
    try:
        draft_id = supabase_ops.store_draft(req, gmail_draft_id)
    except RuntimeError as exc:
        logger.error("create_draft: Supabase store failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Draft storage failed: {exc}")

    # Step 3: activity log
    supabase_ops.write_activity_log(
        LogRequest(
            session_id=req.session_id,
            event_type="DRAFT_CREATED",
            severity="INFO",
            description=f"Draft created: '{req.subject}' → {', '.join(req.to_emails)}",
            payload={"draft_id": draft_id, "gmail_draft_id": gmail_draft_id},
            actor="AGENT",
        )
    )

    return {
        "draft_id": draft_id,
        "gmail_draft_id": gmail_draft_id,
        "status": "PENDING_REVIEW",
    }


def approve_and_send_draft(draft_id: str, reviewed_by: str) -> dict:
    """
    Approve a pending draft and send it via Gmail.

    Steps:
      1. Fetch draft from Supabase.
      2. Send the draft via Gmail.
      3. Update the draft status to SENT in Supabase.
      4. Write an activity log entry.

    Args:
        draft_id: Supabase UUID of the draft to approve and send.
        reviewed_by: Identifier of the reviewer (email, user ID, etc.).

    Returns:
        dict: {status: "SENT", message_id, thread_id}

    Raises:
        HTTPException 404: If the draft is not found.
        HTTPException 400: If the draft is not in PENDING_REVIEW status.
        HTTPException 500: If sending or Supabase update fails.
    """
    # Step 1: fetch from Supabase
    try:
        draft = supabase_ops.get_draft_by_id(draft_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Supabase fetch failed: {exc}")

    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
    if draft.get("status") != "PENDING_REVIEW":
        raise HTTPException(
            status_code=400,
            detail=f"Draft is in status '{draft['status']}', expected PENDING_REVIEW.",
        )

    gmail_draft_id = draft.get("gmail_draft_id")
    if not gmail_draft_id:
        raise HTTPException(
            status_code=400, detail="Draft has no associated Gmail draft ID."
        )

    # Step 2: send via Gmail
    try:
        send_result = gmail_client.send_draft(gmail_draft_id)
    except RuntimeError as exc:
        logger.error("approve_and_send_draft: Gmail send failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Gmail draft send failed: {exc}")

    # Step 3: update Supabase
    try:
        supabase_ops.update_draft_status(draft_id, "SENT", reviewed_by)
    except RuntimeError as exc:
        logger.error("approve_and_send_draft: Supabase update failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Status update failed: {exc}")

    # Step 4: activity log
    supabase_ops.write_activity_log(
        LogRequest(
            session_id=draft.get("session_id"),
            event_type="DRAFT_SENT",
            severity="SUCCESS",
            description=f"Draft {draft_id} approved and sent by {reviewed_by}.",
            payload=send_result,
            actor=reviewed_by,
        )
    )

    return {
        "status": "SENT",
        "message_id": send_result.get("message_id"),
        "thread_id": send_result.get("thread_id"),
    }


def discard_draft(draft_id: str, reviewed_by: str) -> dict:
    """
    Discard a pending draft by deleting it from Gmail and marking it discarded.

    Steps:
      1. Fetch draft from Supabase.
      2. Delete the draft from Gmail.
      3. Update the draft status to DISCARDED in Supabase.

    Args:
        draft_id: Supabase UUID of the draft to discard.
        reviewed_by: Identifier of the reviewer making the discard decision.

    Returns:
        dict: {status: "DISCARDED"}

    Raises:
        HTTPException 404: If the draft is not found.
        HTTPException 500: If Gmail delete or Supabase update fails.
    """
    # Step 1: fetch from Supabase
    try:
        draft = supabase_ops.get_draft_by_id(draft_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Supabase fetch failed: {exc}")

    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")

    gmail_draft_id = draft.get("gmail_draft_id")

    # Step 2: delete from Gmail (best-effort — may already be gone)
    if gmail_draft_id:
        try:
            gmail_client.delete_draft(gmail_draft_id)
        except RuntimeError as exc:
            logger.warning(
                "discard_draft: Gmail delete failed (continuing): %s", exc
            )

    # Step 3: update Supabase
    try:
        supabase_ops.update_draft_status(draft_id, "DISCARDED", reviewed_by)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Status update failed: {exc}")

    supabase_ops.write_activity_log(
        LogRequest(
            session_id=draft.get("session_id"),
            event_type="DRAFT_DISCARDED",
            severity="INFO",
            description=f"Draft {draft_id} discarded by {reviewed_by}.",
            payload={"draft_id": draft_id},
            actor=reviewed_by,
        )
    )

    return {"status": "DISCARDED"}


def get_pending_drafts() -> List[dict]:
    """
    Return all email drafts awaiting human review.

    Returns:
        List[dict]: List of draft records with status PENDING_REVIEW.

    Raises:
        HTTPException 500: If the Supabase query fails.
    """
    try:
        return supabase_ops.get_pending_drafts()
    except RuntimeError as exc:
        logger.error("get_pending_drafts failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending drafts: {exc}")
