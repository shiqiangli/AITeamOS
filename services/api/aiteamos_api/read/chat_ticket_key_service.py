"""Ticket key detection shared by Chat routes and runtime execution."""

from __future__ import annotations

import re


LOCAL_TICKET_ID_RE = re.compile(
    r"\b(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})\b",
    re.IGNORECASE,
)
TICKET_KEY_RE = re.compile(
    r"\b[A-Z][A-Z0-9]+-\d+\b|\b(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})\b",
    re.IGNORECASE,
)


def normalize_ticket_key(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    if LOCAL_TICKET_ID_RE.fullmatch(candidate):
        return candidate.lower()
    return candidate.upper()


def extract_ticket_keys(message: str, explicit: str | None) -> list[str]:
    keys: list[str] = []
    if explicit:
        keys.append(normalize_ticket_key(explicit))
    keys.extend(normalize_ticket_key(match) for match in TICKET_KEY_RE.findall(message))
    return sorted(set(filter(None, keys)))
