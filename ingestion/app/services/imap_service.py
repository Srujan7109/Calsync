from __future__ import annotations

import email
import imaplib
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message
from typing import Iterable

from ingestion.app.config import Settings
from ingestion.app.services.thread_identity import derive_thread_id, normalize_message_id


@dataclass(slots=True)
class ImapEmail:
    sender: str
    to: str
    cc: str
    subject: str
    body_text: str
    message_id: str
    thread_id: str
    in_reply_to: str
    references: str


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""

    decoded_parts = decode_header(value)
    parts: list[str] = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            parts.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(part)

    return "".join(parts).strip()


def _extract_text_from_message(message: Message) -> str:
    if message.is_multipart():
        collected: list[str] = []
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = (part.get("Content-Disposition") or "").lower()
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    collected.append(payload.decode(charset, errors="replace"))
        return "\n".join(collected).strip()

    payload = message.get_payload(decode=True)
    if not payload:
        return ""

    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip()


def _extract_sender(header_value: str) -> str:
    if "<" in header_value and ">" in header_value:
        return header_value.split("<", 1)[1].split(">", 1)[0].strip()
    return header_value.strip()


def _ids_from_search_result(data: Iterable[bytes]) -> list[bytes]:
    ids: list[bytes] = []
    for item in data:
        ids.extend(item.split())
    return ids


def fetch_emails(settings: Settings, limit: int = 20) -> list[ImapEmail]:
    if not settings.imap_host or not settings.imap_username or not settings.imap_app_password:
        raise ValueError("IMAP credentials are incomplete. Set IMAP_HOST, IMAP_USERNAME, and IMAP_APP_PASSWORD.")

    mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    try:
        mail.login(settings.imap_username, settings.imap_app_password)
        mail.select(settings.imap_mailbox)

        status, data = mail.search(None, settings.imap_search_criteria)
        if status != "OK":
            return []

        message_ids = _ids_from_search_result(data)
        selected_ids = message_ids[-max(limit, 1) :]

        emails: list[ImapEmail] = []
        for uid in selected_ids:
            fetch_status, msg_data = mail.fetch(uid, "(RFC822)")
            if fetch_status != "OK" or not msg_data:
                continue

            raw_email = msg_data[0][1]
            if not isinstance(raw_email, (bytes, bytearray)):
                continue

            parsed = email.message_from_bytes(raw_email)
            sender_raw = _decode_header_value(parsed.get("From"))
            to_value = _decode_header_value(parsed.get("To"))
            cc_value = _decode_header_value(parsed.get("Cc"))
            subject_value = _decode_header_value(parsed.get("Subject"))
            message_id = _decode_header_value(parsed.get("Message-ID"))
            in_reply_to = _decode_header_value(parsed.get("In-Reply-To"))
            references = _decode_header_value(parsed.get("References"))
            body_text = _extract_text_from_message(parsed)

            emails.append(
                ImapEmail(
                    sender=_extract_sender(sender_raw),
                    to=to_value,
                    cc=cc_value,
                    subject=subject_value,
                    body_text=body_text,
                    message_id=normalize_message_id(message_id),
                    thread_id=derive_thread_id(message_id, in_reply_to, references),
                    in_reply_to=normalize_message_id(in_reply_to),
                    references=references,
                )
            )

            try:
                mail.store(uid, "+FLAGS", "\\Seen")
            except Exception:
                pass

        return emails
    finally:
        try:
            mail.close()
        except Exception:
            pass
        mail.logout()
