"""AI Engine selection helpers for Employee Chat."""

from __future__ import annotations

import os
from typing import Any

from .ai_engine_catalog import AI_ENGINE_CATALOG, SUPPORTED_AI_ENGINE_IDS

REMOTE_AI_ENGINE_PRIORITY = ("deepseek", "openai")
SUPPORTED_RUNTIME_EXECUTOR_IDS = {
    "claude_agent_sdk",
    "claude_code",
    "codex_cli",
    "cursor",
    "openhands",
    "opencode",
}
RUNTIME_EXECUTOR_AI_ENGINE_ALIASES = {
    "claude-agent-sdk": "claude_agent_sdk",
    "claude_agent": "claude_agent_sdk",
    "claude-code": "claude_code",
    "codex": "codex_cli",
    "codex-cli": "codex_cli",
    "open-hands": "openhands",
    "open-code": "opencode",
}


def normalize_ai_engine(value: str | None) -> str:
    engine = (value or "deepseek").strip().lower()
    if engine in {"fallback", "file_stub", "file-stub"}:
        return "stub"
    return engine if engine in SUPPORTED_AI_ENGINE_IDS else "deepseek"


def normalize_employee_default_ai_engine(value: str | None) -> str:
    engine = (value or "system").strip().lower()
    if engine in {"", "active", "default", "global", "settings", "system_default"}:
        return "system"
    if engine in {"fallback", "file_stub", "file-stub"}:
        return "stub"
    engine = RUNTIME_EXECUTOR_AI_ENGINE_ALIASES.get(engine, engine)
    return engine if engine in {"system", *SUPPORTED_AI_ENGINE_IDS, *SUPPORTED_RUNTIME_EXECUTOR_IDS} else "system"


def api_key_configured_for_engine(engine_id: str, engine_config: dict[str, Any]) -> bool:
    api_key_env = str(engine_config.get("api_key_env") or AI_ENGINE_CATALOG[engine_id].get("default_api_key_env") or "")
    return bool(api_key_env and os.environ.get(api_key_env))


def default_ai_engine(engine_configs: dict[str, dict[str, Any]]) -> str:
    for engine_id in REMOTE_AI_ENGINE_PRIORITY:
        engine_config = engine_configs.get(engine_id, {})
        if bool(engine_config.get("enabled", True)) and api_key_configured_for_engine(engine_id, engine_config):
            return engine_id
    for engine_id in REMOTE_AI_ENGINE_PRIORITY:
        engine_config = engine_configs.get(engine_id, {})
        if bool(engine_config.get("enabled", True)):
            return engine_id
    return "deepseek"
