"""
gmail_client.py — CalSync.ai Gmail MCP

Core Gmail API operations using the authenticated service from auth.py.
All outbound emails automatically receive the CalSync.ai AI disclaimer.
"""

from __future__ import annotations

import base64
import logging
import quopri
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import List, Optional

from googleapiclient.errors import HttpError

from auth import get_gmail_service
from config import settings
from models import DraftCreateRequest, SendEmailRequest

logger = logging.getLogger(__name__)

# ── AI disclaimer appended to every outbound email ───────────────────────────
_DISCLAIMER_TEXT = (
    "\n\n---\n"
    "This email was sent by CalSync.ai, an AI scheduling assistant. "
    "To modify or cancel, reply to this thread.\n"
    "---"
)
_DISCLAIMER_HTML = (
    "<br><br><hr>"
    "<p style='color:#888;font-size:12px;'>"
    "This email was sent by <strong>CalSync.ai</strong>, an AI scheduling assistant. "
    "To modify or cancel, reply to this thread."
    "</p>"
)


def _decode_base64_url(data: str) -> str:
    """Decode a base64url-encoded string to a UTF-8 string."""
    # Gmail uses base64url (RFC 4648 §5) — replace chars and add padding
    data = data.replace("-", "+").replace("_", "/")
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    try:
        return base64.b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: dict) -> tuple[str, Optional[str]]:
    """
    Recursively extract plain-text and HTML body from a Gmail message payload.

    Args:
        payload: The `payload` dict from a Gmail message object.

    Returns:
        Tuple[str, Optional[str]]: (plain_text, html_text)
    """
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")
    parts = payload.get("parts", [])

    if mime_type == "text/plain" and body_data:
        return _decode_base64_url(body_data), None

    if mime_type == "text/html" and body_data:
        return "", _decode_base64_url(body_data)

    if mime_type.startswith("multipart/") and parts:
        plain_text = ""
        html_text: Optional[str] = None
        for part in parts:
            p, h = _extract_body(part)
            if p:
                plain_text = p
            if h:
                html_text = h
        return plain_text, html_text

    return "", None


def _parse_header(headers: list, name: str) -> str:
    """Extract a named header value from a list of Gmail header objects."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _build_mime(
    req: SendEmailRequest,
    from_addr: str,
) -> MIMEMultipart:
    """
    Construct a MIME email message from a SendEmailRequest.

    Appends the CalSync.ai AI disclaimer to both plain-text and HTML bodies.
    Sets In-Reply-To and References headers when present to maintain threading.

    Args:
        req: The send email request.
        from_addr: The From address (CalSync inbox).

    Returns:
        MIMEMultipart: The assembled MIME message.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = req.subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(req.to_emails)
    msg["Reply-To"] = from_addr
    if req.cc_emails:
        msg["Cc"] = ", ".join(req.cc_emails)
    if req.in_reply_to:
        msg["In-Reply-To"] = req.in_reply_to
    if req.references:
        msg["References"] = req.references

    # Plain text with disclaimer
    plain_with_disclaimer = (req.body_text or "") + _DISCLAIMER_TEXT
    msg.attach(MIMEText(plain_with_disclaimer, "plain", "utf-8"))

    # HTML with disclaimer (if provided)
    if req.body_html:
        html_with_disclaimer = req.body_html + _DISCLAIMER_HTML
    else:
        html_with_disclaimer = (
            plain_with_disclaimer.replace("\n", "<br>")
        ) + _DISCLAIMER_HTML
    msg.attach(MIMEText(html_with_disclaimer, "html", "utf-8"))

    return msg


# ── Public API ────────────────────────────────────────────────────────────────


def send_email(req: SendEmailRequest) -> dict:
    """
    Send an email via the Gmail API.

    Builds a properly threaded RFC 2822 MIME message (sets In-Reply-To /
    References headers when replying). Appends the CalSync.ai AI disclaimer
    to the body. Stores the message in the correct thread when thread_id
    is provided.

    Args:
        req: SendEmailRequest — recipient list, subject, body, threading info.

    Returns:
        dict: {message_id, thread_id, gmail_message_id}

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    from_addr = formataddr(("CalSync.ai", settings.CALSYNC_EMAIL))
    mime_msg = _build_mime(req, from_addr)

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
    body: dict = {"raw": raw}
    if req.thread_id:
        body["threadId"] = req.thread_id

    try:
        result = service.users().messages().send(userId="me", body=body).execute()
        return {
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "gmail_message_id": result.get("id"),
        }
    except HttpError as exc:
        logger.error("send_email HttpError: %s", exc)
        raise RuntimeError(f"Gmail send_email failed: {exc}") from exc


def get_message(message_id: str) -> dict:
    """
    Fetch and parse a single Gmail message.

    Retrieves the full message including headers and body. Decodes base64url
    body parts and handles both plain-text and HTML multipart messages.

    Args:
        message_id: The Gmail message ID to fetch.

    Returns:
        dict: {
            gmail_message_id, thread_id, from_email, to_emails, cc_emails,
            subject, date, in_reply_to, references, body_text, body_html,
            label_ids, has_attachments, internal_date
        }

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
    except HttpError as exc:
        logger.error("get_message HttpError: %s", exc)
        raise RuntimeError(f"Gmail get_message failed: {exc}") from exc

    headers = msg.get("payload", {}).get("headers", [])
    body_text, body_html = _extract_body(msg.get("payload", {}))

    # Detect attachments (non-inline parts with a filename)
    has_attachments = False
    for part in msg.get("payload", {}).get("parts", []):
        if part.get("filename"):
            has_attachments = True
            break

    to_raw = _parse_header(headers, "To")
    cc_raw = _parse_header(headers, "Cc")

    to_emails = [e.strip() for e in to_raw.split(",") if e.strip()]
    cc_emails = [e.strip() for e in cc_raw.split(",") if e.strip()]

    return {
        "gmail_message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from_email": _parse_header(headers, "From"),
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "subject": _parse_header(headers, "Subject"),
        "date": _parse_header(headers, "Date"),
        "message_id_header": _parse_header(headers, "Message-ID"),
        "in_reply_to": _parse_header(headers, "In-Reply-To"),
        "references": _parse_header(headers, "References"),
        "body_text": body_text,
        "body_html": body_html,
        "label_ids": msg.get("labelIds", []),
        "has_attachments": has_attachments,
        "internal_date": msg.get("internalDate"),
    }


def list_unread_inbox(max_results: int = 20) -> list[dict]:
    """Fetch recent INBOX messages (last 24h) regardless of read status."""
    service = get_gmail_service()
    try:
        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=["INBOX"],
                q="in:inbox newer_than:2d",          # last 24 hours, read OR unread
                maxResults=max_results,
            )
            .execute()
        )
        return [get_message(ref["id"]) for ref in result.get("messages", [])]
    except HttpError as exc:
        logger.error("list_unread_inbox HttpError: %s", exc)
        raise RuntimeError(f"Gmail list_unread_inbox failed: {exc}") from exc


def mark_message_read(message_id: str) -> None:
    """Remove the UNREAD label from a message."""
    try:
        mark_as_read(message_id)
    except RuntimeError as exc:
        logger.error("mark_message_read failed: %s", exc)
        raise


def get_thread(thread_id: str, max_messages: int = 50) -> List[dict]:
    """
    Fetch and parse all messages in a Gmail thread.

    Retrieves messages in chronological order (oldest first). Each message
    is parsed with get_message() logic to extract headers and body.

    Args:
        thread_id: The Gmail thread ID to fetch.
        max_messages: Maximum number of messages to return (default 50).

    Returns:
        List[dict]: Chronologically ordered list of parsed message dicts.

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        thread = (
            service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
    except HttpError as exc:
        logger.error("get_thread HttpError: %s", exc)
        raise RuntimeError(f"Gmail get_thread failed: {exc}") from exc

    messages = thread.get("messages", [])[:max_messages]
    results = []
    for msg in messages:
        headers = msg.get("payload", {}).get("headers", [])
        body_text, body_html = _extract_body(msg.get("payload", {}))

        has_attachments = any(
            part.get("filename")
            for part in msg.get("payload", {}).get("parts", [])
        )
        to_raw = _parse_header(headers, "To")
        cc_raw = _parse_header(headers, "Cc")

        results.append(
            {
                "gmail_message_id": msg.get("id"),
                "thread_id": msg.get("threadId"),
                "from_email": _parse_header(headers, "From"),
                "to_emails": [e.strip() for e in to_raw.split(",") if e.strip()],
                "cc_emails": [e.strip() for e in cc_raw.split(",") if e.strip()],
                "subject": _parse_header(headers, "Subject"),
                "date": _parse_header(headers, "Date"),
                "message_id_header": _parse_header(headers, "Message-ID"),
                "in_reply_to": _parse_header(headers, "In-Reply-To"),
                "references": _parse_header(headers, "References"),
                "body_text": body_text,
                "body_html": body_html,
                "label_ids": msg.get("labelIds", []),
                "has_attachments": has_attachments,
                "internal_date": msg.get("internalDate"),
            }
        )

    return results


def create_draft(req: DraftCreateRequest) -> str:
    """
    Create a Gmail draft from a DraftCreateRequest.

    Builds a MIME message (with disclaimer) and saves it as a draft
    in the CalSync Gmail account.

    Args:
        req: DraftCreateRequest — draft metadata.

    Returns:
        str: The Gmail draft ID (e.g. "r1234567890").

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()

    # Reuse MIME builder via a stub SendEmailRequest
    send_req = SendEmailRequest(
        to_emails=req.to_emails,
        subject=req.subject,
        body_text=req.body_text,
        body_html=req.body_html,
        thread_id=req.thread_id,
    )
    from_addr = formataddr(("CalSync.ai", settings.CALSYNC_EMAIL))
    mime_msg = _build_mime(send_req, from_addr)
    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

    body: dict = {"message": {"raw": raw}}
    if req.thread_id:
        body["message"]["threadId"] = req.thread_id

    try:
        result = service.users().drafts().create(userId="me", body=body).execute()
        return result["id"]
    except HttpError as exc:
        logger.error("create_draft HttpError: %s", exc)
        raise RuntimeError(f"Gmail create_draft failed: {exc}") from exc


def send_draft(gmail_draft_id: str) -> dict:
    """
    Send a Gmail draft that was previously created.

    Args:
        gmail_draft_id: The Gmail draft ID to send.

    Returns:
        dict: {message_id, thread_id}

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        result = (
            service.users()
            .drafts()
            .send(userId="me", body={"id": gmail_draft_id})
            .execute()
        )
        return {
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
        }
    except HttpError as exc:
        logger.error("send_draft HttpError: %s", exc)
        raise RuntimeError(f"Gmail send_draft failed: {exc}") from exc


def delete_draft(gmail_draft_id: str) -> None:
    """
    Permanently delete a Gmail draft.

    Args:
        gmail_draft_id: The Gmail draft ID to delete.

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        service.users().drafts().delete(userId="me", id=gmail_draft_id).execute()
    except HttpError as exc:
        logger.error("delete_draft HttpError: %s", exc)
        raise RuntimeError(f"Gmail delete_draft failed: {exc}") from exc


def get_or_create_label(label_name: str) -> str:
    """
    Get the Gmail label ID for a given label name, creating it if it doesn't exist.

    Args:
        label_name: Human-readable label name (e.g. "CalSync/Processed").

    Returns:
        str: Gmail label ID.

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        existing = service.users().labels().list(userId="me").execute()
        for label in existing.get("labels", []):
            if label.get("name") == label_name:
                return label["id"]

        # Create it
        created = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": label_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        logger.info("Created Gmail label '%s' with ID %s", label_name, created["id"])
        return created["id"]
    except HttpError as exc:
        logger.error("get_or_create_label HttpError: %s", exc)
        raise RuntimeError(f"Gmail get_or_create_label failed: {exc}") from exc


def modify_labels(
    message_id: str, add_labels: List[str], remove_labels: List[str]
) -> None:
    """
    Add and/or remove Gmail label IDs from a message.

    Label names are resolved to IDs automatically if needed.
    If a label name starts with 'CalSync/', it will be created if missing.

    Args:
        message_id: Gmail message ID to modify.
        add_labels: List of label IDs to add.
        remove_labels: List of label IDs to remove.

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()

    def _resolve(labels: List[str]) -> List[str]:
        """Resolve label names to IDs (pass-through if already an ID)."""
        resolved = []
        for label in labels:
            # Gmail-system labels are uppercase (INBOX, UNREAD, etc.)
            if label.isupper() or label.startswith("Label_"):
                resolved.append(label)
            else:
                resolved.append(get_or_create_label(label))
        return resolved

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={
                "addLabelIds": _resolve(add_labels),
                "removeLabelIds": _resolve(remove_labels),
            },
        ).execute()
    except HttpError as exc:
        logger.error("modify_labels HttpError: %s", exc)
        raise RuntimeError(f"Gmail modify_labels failed: {exc}") from exc


def mark_as_read(message_id: str) -> None:
    """
    Mark a Gmail message as read by removing the UNREAD label.

    Args:
        message_id: Gmail message ID to mark as read.

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except HttpError as exc:
        logger.error("mark_as_read HttpError: %s", exc)
        raise RuntimeError(f"Gmail mark_as_read failed: {exc}") from exc


def setup_watch(pubsub_topic: str) -> dict:
    """
    Set up Gmail push notifications via Google Cloud Pub/Sub.

    Registers a watch that will push notifications to the given Pub/Sub
    topic whenever a new message arrives in the INBOX.

    Args:
        pubsub_topic: The Cloud Pub/Sub topic name
            (e.g. "projects/myproject/topics/calsync-email-topic").

    Returns:
        dict: {historyId, expiration} as returned by the Gmail API.

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        result = (
            service.users()
            .watch(
                userId="me",
                body={
                    "topicName": pubsub_topic,
                    "labelIds": ["INBOX"],
                    "labelFilterAction": "include",
                },
            )
            .execute()
        )
        return {
            "historyId": result.get("historyId"),
            "expiration": result.get("expiration"),
        }
    except HttpError as exc:
        logger.error("setup_watch HttpError: %s", exc)
        raise RuntimeError(f"Gmail setup_watch failed: {exc}") from exc


def stop_watch() -> None:
    """
    Stop Gmail push notifications for the CalSync inbox.

    Cancels an existing watch subscription. Safe to call even if no watch
    is currently active.

    Raises:
        RuntimeError: On Gmail API failure.
    """
    service = get_gmail_service()
    try:
        service.users().stop(userId="me").execute()
        logger.info("Gmail watch stopped for %s", settings.CALSYNC_EMAIL)
    except HttpError as exc:
        logger.error("stop_watch HttpError: %s", exc)
        raise RuntimeError(f"Gmail stop_watch failed: {exc}") from exc
