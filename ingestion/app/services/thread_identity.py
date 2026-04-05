from __future__ import annotations

import email
import re


_MESSAGE_ID_PATTERN = re.compile(r"<([^>]+)>|([^\s<>]+)")


def normalize_message_id(value: str | None) -> str:
    if not value:
        return ""

    cleaned = value.strip()
    if not cleaned:
        return ""

    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1].strip()

    return cleaned


def extract_header_value(raw_headers: str | None, header_name: str) -> str:
    if not raw_headers:
        return ""

    parsed_headers = email.message_from_string(raw_headers)
    return normalize_message_id(parsed_headers.get(header_name))


def extract_reference_chain(references: str | None) -> list[str]:
    if not references:
        return []

    chain: list[str] = []
    for match in _MESSAGE_ID_PATTERN.finditer(references):
        token = match.group(1) or match.group(2) or ""
        normalized = normalize_message_id(token)
        if normalized:
            chain.append(normalized)
    return chain


def derive_thread_id(message_id: str | None, in_reply_to: str | None = None, references: str | None = None) -> str:
    reference_chain = extract_reference_chain(references)
    if reference_chain:
        return reference_chain[0]

    normalized_reply_to = normalize_message_id(in_reply_to)
    if normalized_reply_to:
        return normalized_reply_to

    return normalize_message_id(message_id)