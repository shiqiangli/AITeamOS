"""File-backed RuntimeExecutor adapter configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


_CONFIG_KEYS = {
    "enabled",
    "binary_path",
    "working_dir",
    "command_template",
    "model",
    "api_base_url",
    "api_key_env",
    "http_endpoint_path",
    "mode",
    "timeout_seconds",
}


class RuntimeExecutorConfigRecord(BaseModel):
    executor_id: str
    enabled: bool = True
    binary_path: str = ""
    working_dir: str = ""
    command_template: str = ""
    model: str = ""
    api_base_url: str = ""
    api_key_env: str = ""
    http_endpoint_path: str = ""
    mode: str = ""
    timeout_seconds: int | None = None
    saved_path: str = ""


class RuntimeExecutorConfigUpdateRequest(BaseModel):
    enabled: bool | None = None
    binary_path: str | None = None
    working_dir: str | None = None
    command_template: str | None = None
    model: str | None = None
    api_base_url: str | None = None
    api_key_env: str | None = None
    http_endpoint_path: str | None = None
    mode: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=1800)


class RuntimeExecutorConfigListResponse(BaseModel):
    executors: dict[str, RuntimeExecutorConfigRecord] = Field(default_factory=dict)
    saved_paths: dict[str, str] = Field(default_factory=dict)


def _workspace_dir(workspace_dir: Path | None = None) -> Path:
    return workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()


def runtime_executor_config_path(workspace_dir: Path | None = None) -> Path:
    return _workspace_dir(workspace_dir) / "runtime_executors.json"


def _relative_saved_path(path: Path, workspace_dir: Path) -> str:
    try:
        return str(path.relative_to(workspace_dir.parent))
    except ValueError:
        return str(path)


def _load_raw(workspace_dir: Path | None = None) -> dict[str, Any]:
    path = runtime_executor_config_path(workspace_dir)
    if not path.exists():
        return {"executors": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"executors": {}}
    return data if isinstance(data, dict) else {"executors": {}}


def _write_raw(data: dict[str, Any], workspace_dir: Path | None = None) -> None:
    path = runtime_executor_config_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_executor_id(executor_id: str) -> str:
    return executor_id.strip().replace("-", "_")


def _record_from_raw(executor_id: str, raw: dict[str, Any], workspace_dir: Path | None = None) -> RuntimeExecutorConfigRecord:
    workspace = _workspace_dir(workspace_dir)
    payload: dict[str, Any] = {
        key: raw.get(key)
        for key in _CONFIG_KEYS
        if key in raw
    }
    payload["executor_id"] = executor_id
    payload["saved_path"] = _relative_saved_path(runtime_executor_config_path(workspace), workspace)
    return RuntimeExecutorConfigRecord.model_validate(payload)


def list_runtime_executor_configs(workspace_dir: Path | None = None) -> RuntimeExecutorConfigListResponse:
    raw = _load_raw(workspace_dir)
    executors_raw = raw.get("executors") if isinstance(raw.get("executors"), dict) else {}
    executors = {
        _normalize_executor_id(str(executor_id)): _record_from_raw(
            _normalize_executor_id(str(executor_id)),
            data if isinstance(data, dict) else {},
            workspace_dir,
        )
        for executor_id, data in executors_raw.items()
    }
    path = runtime_executor_config_path(workspace_dir)
    workspace = _workspace_dir(workspace_dir)
    return RuntimeExecutorConfigListResponse(
        executors=executors,
        saved_paths={"runtime_executors": _relative_saved_path(path, workspace)},
    )


def get_runtime_executor_config(executor_id: str, workspace_dir: Path | None = None) -> RuntimeExecutorConfigRecord:
    normalized = _normalize_executor_id(executor_id)
    raw = _load_raw(workspace_dir)
    executors = raw.get("executors") if isinstance(raw.get("executors"), dict) else {}
    data = executors.get(normalized) if isinstance(executors.get(normalized), dict) else {}
    return _record_from_raw(normalized, data, workspace_dir)


def runtime_executor_config_for(executor_id: str, workspace_dir: Path | None = None) -> dict[str, Any]:
    record = get_runtime_executor_config(executor_id, workspace_dir)
    return {
        key: value
        for key, value in record.model_dump().items()
        if key in _CONFIG_KEYS and value not in (None, "")
    }


def update_runtime_executor_config(
    executor_id: str,
    request: RuntimeExecutorConfigUpdateRequest,
    workspace_dir: Path | None = None,
) -> RuntimeExecutorConfigRecord:
    normalized = _normalize_executor_id(executor_id)
    raw = _load_raw(workspace_dir)
    executors = raw.setdefault("executors", {})
    if not isinstance(executors, dict):
        raw["executors"] = executors = {}
    current = executors.get(normalized) if isinstance(executors.get(normalized), dict) else {}
    update = request.model_dump(exclude_unset=True)
    next_record = {
        **current,
        **{
            key: (value.strip() if isinstance(value, str) else value)
            for key, value in update.items()
            if key in _CONFIG_KEYS
        },
    }
    executors[normalized] = {
        key: value
        for key, value in next_record.items()
        if key in _CONFIG_KEYS and value not in (None, "")
    }
    _write_raw(raw, workspace_dir)
    return get_runtime_executor_config(normalized, workspace_dir)
