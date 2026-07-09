"""Conversation and thread-index persistence helpers for Employee Chat."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable


def ensure_run_dirs(workspace_dir: Path) -> dict[str, Path]:
    paths = {
        "conversations": workspace_dir / "conversations",
        "traces": workspace_dir / "traces",
        "threads": workspace_dir / "threads",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def threads_dir(workspace_dir: Path) -> Path:
    return workspace_dir / "threads"


def thread_index_path(workspace_dir: Path) -> Path:
    return threads_dir(workspace_dir) / "index.json"


def conversation_path(
    workspace_dir: Path,
    thread_id: str,
    *,
    require_safe_id: Callable[[str], str],
) -> Path:
    safe_thread_id = require_safe_id(thread_id)
    return workspace_dir / "conversations" / f"{safe_thread_id}.jsonl"


def load_conversation_messages(
    workspace_dir: Path,
    thread_id: str,
    *,
    message_model: Any,
    require_safe_id: Callable[[str], str],
    limit: int | None = None,
) -> list[Any]:
    path = conversation_path(workspace_dir, thread_id, require_safe_id=require_safe_id)
    messages: list[Any] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            messages.append(message_model.model_validate_json(line))
    return messages[-limit:] if limit and limit > 0 else messages


def load_thread_index(workspace_dir: Path) -> dict[str, Any]:
    path = thread_index_path(workspace_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    threads = payload.get("threads") if isinstance(payload.get("threads"), dict) else {}
    active_by_employee = (
        payload.get("active_by_employee")
        if isinstance(payload.get("active_by_employee"), dict)
        else {}
    )
    return {
        "threads": {str(key): value for key, value in threads.items() if isinstance(value, dict)},
        "active_by_employee": {
            str(key): str(value)
            for key, value in active_by_employee.items()
            if isinstance(value, str)
        },
    }


def write_thread_index(workspace_dir: Path, index: dict[str, Any], *, updated_at: str) -> None:
    payload = {
        "threads": index.get("threads") if isinstance(index.get("threads"), dict) else {},
        "active_by_employee": (
            index.get("active_by_employee")
            if isinstance(index.get("active_by_employee"), dict)
            else {}
        ),
        "updated_at": updated_at,
    }
    path = thread_index_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def thread_index_saved_path(workspace_dir: Path, workspace_root: Path) -> str:
    return str(thread_index_path(workspace_dir).relative_to(workspace_root))


def conversation_saved_path(
    workspace_dir: Path,
    workspace_root: Path,
    thread_id: str,
    *,
    require_safe_id: Callable[[str], str],
) -> str:
    return str(
        conversation_path(
            workspace_dir,
            thread_id,
            require_safe_id=require_safe_id,
        ).relative_to(workspace_root)
    )


def thread_title_from_message(content: str) -> str:
    text = re.sub(r"\s+", " ", content).strip()
    if not text:
        return "New thread"
    return text[:56] + ("..." if len(text) > 56 else "")
