"""Small streaming helpers for Chat HTTP transports."""

from __future__ import annotations

import json
import re
from typing import Any


def sse_payload(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def reply_chunks(reply: str) -> list[str]:
    chunks = re.split(r"(\s+)", reply)
    merged: list[str] = []
    current = ""
    for chunk in chunks:
        if not chunk:
            continue
        current += chunk
        if len(current) >= 16 or "\n" in current:
            merged.append(current)
            current = ""
    if current:
        merged.append(current)
    return merged or [reply]
