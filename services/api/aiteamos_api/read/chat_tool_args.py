"""Tool argument normalization helpers for Chat action plans."""

from __future__ import annotations

import re
from typing import Any


def clean_extracted_value(value: str) -> str:
    return value.strip().strip("\"'`“”‘’").strip()


def split_list_value(value: str) -> list[str]:
    normalized = re.sub(r"\s+(and|和)\s+", ",", value, flags=re.IGNORECASE)
    normalized = normalized.replace("、", ",").replace("，", ",").replace("；", ",").replace(";", ",")
    return [clean_extracted_value(item) for item in normalized.split(",") if clean_extracted_value(item)]


def stringify_tool_arg(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = clean_extracted_value(value)
        return cleaned or None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return None


def listify_tool_arg(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [clean_extracted_value(str(item)) for item in value if clean_extracted_value(str(item))]
    if isinstance(value, str):
        return split_list_value(value)
    return None


def tool_arg(arguments: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in arguments:
            return arguments[name]
    return None


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
