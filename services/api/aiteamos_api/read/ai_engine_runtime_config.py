"""Runtime AI Engine configuration accessors."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from .ai_engine_catalog import AI_ENGINE_CATALOG
from .ai_engine_config_store import (
    normalize_int_setting,
    normalize_openai_reasoning_effort,
    normalize_openai_speed,
)
from .ai_engine_selection import normalize_employee_default_ai_engine


@dataclass(frozen=True)
class AiEngineRuntimeConfig:
    config: Mapping[str, Any]
    secrets: Mapping[str, str]

    def active_engine(self) -> str:
        return str(self.config["active_engine"])

    def selected_engine_for_employee(self, default_ai_engine: str) -> str:
        default_engine = normalize_employee_default_ai_engine(default_ai_engine)
        return self.active_engine() if default_engine == "system" else default_engine

    def ai_engine_fallback_on_error(self) -> bool:
        return bool(self.config["fallback_on_error"])

    def remote_ai_engine_available(self, engine: str) -> bool:
        if engine == "deepseek":
            return bool(self.secrets.get("deepseek_api_key"))
        if engine == "openai":
            return bool(self.secrets.get("openai_api_key"))
        return False

    def _engine_config(self, engine_id: str) -> Mapping[str, Any]:
        engine_configs = self.config.get("engine_configs") if isinstance(self.config.get("engine_configs"), dict) else {}
        engine_config = engine_configs.get(engine_id) if isinstance(engine_configs.get(engine_id), dict) else {}
        return engine_config

    def openai_enabled(self, engine: str | None = None) -> bool:
        return (engine or self.active_engine()) == "openai"

    def openai_model(self) -> str:
        return str(self.config["openai_model"])

    def openai_base_url(self) -> str:
        return str(self._engine_config("openai").get("base_url") or "https://api.openai.com/v1").rstrip("/")

    def openai_reasoning_effort(self) -> str:
        return normalize_openai_reasoning_effort(self._engine_config("openai").get("thinking"))

    def openai_speed(self) -> str:
        return normalize_openai_speed(self._engine_config("openai").get("speed"))

    def openai_service_tier(self) -> str | None:
        speed = self.openai_speed()
        return speed if speed in {"priority", "flex"} else None

    def openai_max_output_tokens(self) -> int:
        openai_config = self._engine_config("openai")
        default_max_tokens = int(AI_ENGINE_CATALOG["openai"].get("default_max_tokens") or 4096)
        max_supported_tokens = int(AI_ENGINE_CATALOG["openai"].get("max_output_tokens") or 128_000)
        raw_value = openai_config.get("max_tokens") or os.environ.get("AITEAMOS_OPENAI_MAX_OUTPUT_TOKENS") or default_max_tokens
        return normalize_int_setting(raw_value, default=default_max_tokens, min_value=64, max_value=max_supported_tokens)

    def openai_fallback_on_error(self) -> bool:
        return self.ai_engine_fallback_on_error()

    def deepseek_enabled(self, engine: str | None = None) -> bool:
        return (engine or self.active_engine()) == "deepseek"

    def deepseek_model(self) -> str:
        return str(self.config["deepseek_model"])

    def deepseek_base_url(self) -> str:
        return str(self._engine_config("deepseek").get("base_url") or "https://api.deepseek.com").rstrip("/")

    def deepseek_max_tokens(self) -> int:
        return int(self._engine_config("deepseek").get("max_tokens") or 384_000)

    def deepseek_context_window(self) -> int:
        return int(self._engine_config("deepseek").get("context_window") or 1_000_000)

    def deepseek_thinking_type(self) -> str:
        return str(self.config["deepseek_thinking"])
