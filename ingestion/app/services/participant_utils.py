from __future__ import annotations

import re


EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def parse_email_addresses(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    found = EMAIL_PATTERN.findall(raw_value)
    return dedupe_emails(found)


def dedupe_emails(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped


def exclude_emails(values: list[str], excluded: list[str]) -> list[str]:
    blocked = {item.strip().lower() for item in excluded if item and item.strip()}
    return [item for item in values if item.lower() not in blocked]
