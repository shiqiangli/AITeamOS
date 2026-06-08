"""Small AG-UI/LangGraph bridge helpers used by chat routes."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage


def message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
        return "".join(chunks).strip()
    return str(content).strip() if content is not None else ""


def latest_human_message_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message_content_to_text(message.content)
    return ""


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


def agui_message_payload(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        data = message.model_dump(by_alias=True, exclude_none=True)
        return data if isinstance(data, dict) else {}
    if isinstance(message, dict):
        return {key: value for key, value in message.items() if value is not None}
    return {}


def latest_agui_user_message_payload(messages: list[Any]) -> dict[str, Any] | None:
    for message in reversed(messages):
        payload = agui_message_payload(message)
        if payload.get("role") == "user":
            return payload
    return None


def latest_agui_user_message_text(messages: list[Any]) -> str:
    payload = latest_agui_user_message_payload(messages)
    if payload is None:
        return ""
    return message_content_to_text(payload.get("content"))


def checkpoint_id_from_config(config: dict[str, Any]) -> str | None:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    checkpoint_id = configurable.get("checkpoint_id") if isinstance(configurable, dict) else None
    return str(checkpoint_id) if checkpoint_id else None
