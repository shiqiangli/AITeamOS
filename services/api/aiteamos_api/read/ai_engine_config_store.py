"""AI Engine settings file loading and normalization."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .ai_engine_catalog import AI_ENGINE_CATALOG, SUPPORTED_AI_ENGINE_IDS
from .ai_engine_selection import default_ai_engine, normalize_ai_engine


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def normalize_thinking(value: str | None) -> str:
    thinking = (value or "enabled").strip().lower()
    return "enabled" if thinking in {"1", "true", "yes", "on", "enabled"} else "disabled"


def normalize_openai_reasoning_effort(value: Any) -> str:
    effort = str(value or "medium").strip().lower()
    aliases = {
        "0": "none",
        "off": "none",
        "disabled": "none",
        "none": "none",
        "fast": "low",
        "quick": "low",
        "low": "low",
        "balanced": "medium",
        "default": "medium",
        "medium": "medium",
        "hard": "high",
        "high": "high",
        "deep": "xhigh",
        "x-high": "xhigh",
        "xhigh": "xhigh",
    }
    return aliases.get(effort, "medium")


def normalize_openai_speed(value: Any) -> str:
    speed = str(value or "standard").strip().lower()
    aliases = {
        "auto": "standard",
        "default": "standard",
        "normal": "standard",
        "standard": "standard",
        "fast": "priority",
        "priority": "priority",
        "slow": "flex",
        "cheap": "flex",
        "cost": "flex",
        "flex": "flex",
    }
    return aliases.get(speed, "standard")


def normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def normalize_int_setting(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(parsed, max_value))


def engine_file_config(engine_id: str, file_config: dict[str, Any]) -> dict[str, Any]:
    engines = file_config.get("engines") if isinstance(file_config.get("engines"), dict) else {}
    engine_config = engines.get(engine_id) if isinstance(engines.get(engine_id), dict) else {}
    return dict(engine_config)


def engine_config(engine_id: str, file_config: dict[str, Any]) -> dict[str, Any]:
    catalog = AI_ENGINE_CATALOG[engine_id]
    engine_file = engine_file_config(engine_id, file_config)
    env_prefix = engine_id.upper().replace("-", "_")
    model = (
        engine_file.get("model")
        or file_config.get(f"{engine_id}_model")
        or os.environ.get(f"AITEAMOS_{env_prefix}_MODEL")
        or catalog.get("default_model")
        or ""
    )
    thinking = (
        engine_file.get("thinking")
        or file_config.get(f"{engine_id}_thinking")
        or os.environ.get(f"AITEAMOS_{env_prefix}_THINKING")
        or catalog.get("default_thinking")
        or ""
    )
    speed = (
        engine_file.get("speed")
        or file_config.get(f"{engine_id}_speed")
        or os.environ.get(f"AITEAMOS_{env_prefix}_SPEED")
        or catalog.get("default_speed")
        or ""
    )
    base_url = (
        engine_file.get("base_url")
        or file_config.get(f"{engine_id}_base_url")
        or os.environ.get(f"AITEAMOS_{env_prefix}_BASE_URL")
        or catalog.get("default_base_url")
        or ""
    )
    api_key_env = (
        engine_file.get("api_key_env")
        or file_config.get(f"{engine_id}_api_key_env")
        or catalog.get("default_api_key_env")
        or ""
    )
    if engine_id == "deepseek":
        normalized_thinking = normalize_thinking(str(thinking))
    elif engine_id == "openai":
        normalized_thinking = normalize_openai_reasoning_effort(thinking)
    else:
        normalized_thinking = str(thinking)

    config = {
        **engine_file,
        "model": str(model),
        "thinking": normalized_thinking,
        "speed": normalize_openai_speed(speed) if engine_id == "openai" else str(speed),
        "base_url": str(base_url),
        "api_key_env": str(api_key_env),
        "enabled": normalize_bool(engine_file.get("enabled"), True),
    }
    if catalog.get("default_context_window") or catalog.get("default_max_tokens"):
        default_context_window = int(catalog.get("default_context_window") or 1_000_000)
        default_max_tokens = int(catalog.get("default_max_tokens") or 4096)
        max_supported_tokens = int(catalog.get("max_output_tokens") or default_max_tokens)
        context_window = normalize_int_setting(
            engine_file.get("context_window")
            or file_config.get(f"{engine_id}_context_window")
            or os.environ.get(f"AITEAMOS_{env_prefix}_CONTEXT_WINDOW")
            or default_context_window,
            default=default_context_window,
            min_value=1024,
            max_value=default_context_window,
        )
        max_tokens = normalize_int_setting(
            engine_file.get("max_tokens")
            or file_config.get(f"{engine_id}_max_tokens")
            or os.environ.get(f"AITEAMOS_{env_prefix}_MAX_OUTPUT_TOKENS")
            or os.environ.get(f"AITEAMOS_{env_prefix}_MAX_TOKENS")
            or default_max_tokens,
            default=default_max_tokens,
            min_value=64,
            max_value=max_supported_tokens,
        )
        config["context_window"] = context_window
        config["max_tokens"] = min(max_tokens, context_window)
    return config


def load_ai_engine_config(settings_path: Path) -> dict[str, Any]:
    file_config = read_json_file(settings_path)
    engine_configs = {
        engine_id: engine_config(engine_id, file_config)
        for engine_id in AI_ENGINE_CATALOG
    }
    configured_active_engine = file_config.get("active_engine") or os.environ.get("AITEAMOS_AI_ENGINE")
    return {
        "active_engine": (
            normalize_ai_engine(str(configured_active_engine))
            if str(configured_active_engine or "").strip()
            else default_ai_engine(engine_configs)
        ),
        "deepseek_model": str(engine_configs["deepseek"]["model"] or "deepseek-v4-flash"),
        "deepseek_thinking": normalize_thinking(str(engine_configs["deepseek"]["thinking"] or "enabled")),
        "openai_model": str(engine_configs["openai"]["model"] or "gpt-5.5"),
        "fallback_on_error": normalize_bool(
            file_config.get(
                "fallback_on_error",
                os.environ.get("AITEAMOS_AI_ENGINE_FALLBACK_ON_ERROR", "1").lower() in {"1", "true", "yes", "on"},
            ),
            True,
        ),
        "engine_configs": engine_configs,
    }


def ai_engine_secrets(config: dict[str, Any]) -> dict[str, str]:
    engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}

    def env_value(engine_id: str) -> str:
        engine_config_data = engine_configs.get(engine_id) if isinstance(engine_configs.get(engine_id), dict) else {}
        env_name = str(engine_config_data.get("api_key_env") or AI_ENGINE_CATALOG[engine_id].get("default_api_key_env") or "")
        return str(os.environ.get(env_name) or "") if env_name else ""

    return {
        "deepseek_api_key": env_value("deepseek"),
        "openai_api_key": env_value("openai"),
    }


def secret_configured(engine_config: dict[str, Any]) -> bool:
    api_key_env = str(engine_config.get("api_key_env") or "")
    if not api_key_env:
        return True
    return bool(os.environ.get(api_key_env))


def field_value(engine_config: dict[str, Any], field_id: str) -> str | bool | None:
    if field_id == "enabled":
        return bool(engine_config.get("enabled", True))
    value = engine_config.get(field_id)
    return str(value) if value is not None else ""


def ai_engine_file_payload(config: dict[str, Any], *, updated_at: str) -> dict[str, Any]:
    engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}
    if "deepseek_model" in config or "deepseek_thinking" in config or "openai_model" in config:
        engine_configs = dict(engine_configs)
        engine_configs["deepseek"] = {
            **dict(engine_configs.get("deepseek") or {}),
            "model": str(config.get("deepseek_model") or "deepseek-v4-flash"),
            "thinking": normalize_thinking(str(config.get("deepseek_thinking") or "enabled")),
        }
        engine_configs["openai"] = {
            **dict(engine_configs.get("openai") or {}),
            "model": str(config.get("openai_model") or "gpt-5.5"),
        }

    persisted_engines: dict[str, dict[str, Any]] = {}
    for engine_id in AI_ENGINE_CATALOG:
        if engine_id not in SUPPORTED_AI_ENGINE_IDS:
            continue
        engine_data = engine_configs.get(engine_id) if isinstance(engine_configs.get(engine_id), dict) else {}
        persisted: dict[str, Any] = {}
        for key in ("model", "thinking", "speed", "context_window", "max_tokens", "base_url", "api_key_env", "enabled", "command", "workspace", "profile"):
            value = engine_data.get(key)
            if value is not None and value != "":
                persisted[key] = value
        if persisted:
            persisted_engines[engine_id] = persisted

    return {
        "active_engine": normalize_ai_engine(str(config.get("active_engine"))),
        "fallback_on_error": bool(config.get("fallback_on_error", True)),
        "engines": persisted_engines,
        "updated_at": updated_at,
    }
