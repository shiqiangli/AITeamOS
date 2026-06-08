"""Persistence helpers for external AI Engine thread mappings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def engine_threads_path(workspace_dir: Path) -> Path:
    return workspace_dir / "engine_threads.json"


def engine_thread_id(workspace_dir: Path, employee_id: str, thread_id: str) -> str:
    path = engine_threads_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        mapping = {}

    key = f"{employee_id}::{thread_id}"
    if key not in mapping:
        mapping[key] = f"engine-{employee_id}-{thread_id[:8]}"
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return str(mapping[key])


def load_engine_threads(workspace_dir: Path) -> tuple[Path, dict[str, Any]]:
    path = engine_threads_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        mapping = {}
    return path, mapping if isinstance(mapping, dict) else {}


def engine_thread_state(workspace_dir: Path, employee_id: str, thread_id: str) -> dict[str, Any]:
    path, mapping = load_engine_threads(workspace_dir)
    key = f"{employee_id}::{thread_id}"
    existing = mapping.get(key)
    if isinstance(existing, dict):
        return existing
    if isinstance(existing, str):
        return {"ai_engine": "file_stub", "engine_thread_id": existing}

    state = {
        "ai_engine": "file_stub",
        "engine_thread_id": f"engine-{employee_id}-{thread_id[:8]}",
    }
    mapping[key] = state["engine_thread_id"]
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return state


def save_engine_thread_state(workspace_dir: Path, employee_id: str, thread_id: str, state: dict[str, Any]) -> None:
    path, mapping = load_engine_threads(workspace_dir)
    mapping[f"{employee_id}::{thread_id}"] = state
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")


def delete_engine_thread_states(workspace_dir: Path, employee_id: str) -> list[str]:
    path, mapping = load_engine_threads(workspace_dir)
    removed_keys = [key for key in mapping if key.startswith(f"{employee_id}::")]
    if removed_keys:
        for key in removed_keys:
            mapping.pop(key, None)
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return removed_keys


def delete_thread_engine_state_mappings(workspace_dir: Path, employee_id: str, thread_id: str) -> list[str]:
    path = engine_threads_path(workspace_dir)
    if not path.exists():
        return []
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(mapping, dict):
        return []

    removed_keys = [
        key
        for key in mapping
        if key.endswith(f"-{thread_id[:8]}") or key == f"{employee_id}:{thread_id}"
    ]
    for key in removed_keys:
        mapping.pop(key, None)
    if removed_keys:
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return removed_keys
