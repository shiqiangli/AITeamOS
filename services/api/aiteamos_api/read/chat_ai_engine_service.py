"""AI Engine settings helpers for Chat API routes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .ai_engine_catalog import AI_ENGINE_CATALOG, SUPPORTED_AI_ENGINE_IDS
from .ai_engine_config_store import (
    ai_engine_file_payload,
    ai_engine_secrets,
    field_value,
    load_ai_engine_config,
    normalize_int_setting,
    normalize_openai_reasoning_effort,
    normalize_openai_speed,
    normalize_thinking,
    secret_configured,
    write_json_file,
)
from .ai_engine_runtime_config import AiEngineRuntimeConfig
from .ai_engine_selection import (
    RUNTIME_EXECUTOR_AI_ENGINE_ALIASES,
    SUPPORTED_RUNTIME_EXECUTOR_IDS,
    normalize_ai_engine,
    normalize_employee_default_ai_engine,
)
from .chat_models import (
    ChatAiEngineConfigField,
    ChatAiEngineRecord,
    ChatAiEngineSettings,
    ChatAiEngineSettingsRequest,
    ChatAiEngineUpdateRequest,
)
from .execution_contract import ExecutionResult


class ChatAiEngineSettingsService:
    def __init__(self, *, workspace_root: Path, workspace_dir: Path, now: Callable[[], str]) -> None:
        self.workspace_root = workspace_root
        self.workspace_dir = workspace_dir
        self.now = now

    @property
    def settings_path(self) -> Path:
        return self.workspace_dir / "ai_engines.json"

    def require_employee_default_ai_engine(self, value: str) -> str:
        raw = (value or "").strip().lower()
        engine = normalize_employee_default_ai_engine(value)
        allowed = {
            "",
            "active",
            "default",
            "global",
            "settings",
            "system",
            "system_default",
            "fallback",
            "file_stub",
            "file-stub",
            *SUPPORTED_AI_ENGINE_IDS,
            *SUPPORTED_RUNTIME_EXECUTOR_IDS,
            *RUNTIME_EXECUTOR_AI_ENGINE_ALIASES,
        }
        if raw in allowed:
            return engine
        raise HTTPException(status_code=400, detail=f"Unsupported Employee default AI Engine: {value}")

    def require_ai_engine(self, value: str) -> str:
        engine = normalize_ai_engine(value)
        if engine not in AI_ENGINE_CATALOG:
            raise HTTPException(status_code=400, detail=f"Unsupported AI Engine: {value}")
        if engine not in SUPPORTED_AI_ENGINE_IDS:
            raise HTTPException(status_code=400, detail=f"AI Engine is not configurable yet: {value}")
        return engine

    def config(self) -> dict[str, Any]:
        return load_ai_engine_config(self.settings_path)

    def secrets(self) -> dict[str, str]:
        return ai_engine_secrets(self.config())

    def runtime(self) -> AiEngineRuntimeConfig:
        return AiEngineRuntimeConfig(config=self.config(), secrets=self.secrets())

    def selected_model(self, engine: str) -> str | None:
        config = self.config()
        if engine == "deepseek":
            return str(config["deepseek_model"])
        if engine == "openai":
            return str(config["openai_model"])
        return None

    def execution_engine_state(
        self,
        *,
        employee_id: str,
        current_state: dict[str, Any],
        result: ExecutionResult,
    ) -> dict[str, Any] | None:
        for event in result.tool_events:
            event_name = str(event.get("event") or "")
            event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
            provider_ref = event_data.get("provider_ref") if isinstance(event_data.get("provider_ref"), dict) else {}
            if event_name.startswith("ai_engine.deepseek."):
                response_id = str(provider_ref.get("response_id") or event_data.get("response_id") or "")
                if not response_id:
                    continue
                return {
                    **current_state,
                    "ai_engine": "deepseek_chat_completions",
                    "engine_thread_id": current_state.get("engine_thread_id") or f"deepseek-{employee_id}-{uuid4().hex[:8]}",
                    "assumed_agent_session": True,
                    "deepseek_last_response_id": response_id,
                    "model": provider_ref.get("model") or event_data.get("model"),
                    "updated_at": self.now(),
                }
            if event_name.startswith("ai_engine.openai."):
                response_id = str(provider_ref.get("response_id") or event_data.get("response_id") or "")
                if not response_id:
                    continue
                return {
                    **current_state,
                    "ai_engine": "openai_responses",
                    "engine_thread_id": current_state.get("engine_thread_id") or f"openai-{employee_id}-{uuid4().hex[:8]}",
                    "openai_previous_response_id": response_id,
                    "last_response_id": response_id,
                    "model": provider_ref.get("model") or event_data.get("model"),
                    "updated_at": self.now(),
                }
        return None

    def response(self) -> ChatAiEngineSettings:
        config = self.config()
        secrets = self.secrets()
        records = self.records(config, secrets)
        return ChatAiEngineSettings(
            **config,
            engines=records,
            api_keys_configured={
                engine_id: record.api_key_configured
                for engine_id, record in records.items()
            },
            catalog_order=list(AI_ENGINE_CATALOG.keys()),
            saved_paths={
                "ai_engines": str(self.settings_path.relative_to(self.workspace_root)),
            },
        )

    def update_legacy_settings(self, request: ChatAiEngineSettingsRequest) -> ChatAiEngineSettings:
        current = self.config()
        engine_configs = dict(current.get("engine_configs") or {})
        engine_configs["deepseek"] = {
            **dict(engine_configs.get("deepseek") or {}),
            "model": request.deepseek_model.strip() or "deepseek-v4-flash",
            "thinking": normalize_thinking(request.deepseek_thinking),
        }
        engine_configs["openai"] = {
            **dict(engine_configs.get("openai") or {}),
            "model": request.openai_model.strip() or "gpt-5.5",
        }
        config: dict[str, Any] = {
            "active_engine": normalize_ai_engine(request.active_engine),
            "fallback_on_error": request.fallback_on_error,
            "engine_configs": engine_configs,
        }
        write_json_file(self.settings_path, self.file_payload(config))
        return self.response()

    def update_engine(self, engine_id: str, request: ChatAiEngineUpdateRequest) -> ChatAiEngineSettings:
        engine = self.require_ai_engine(engine_id)
        current = self.config()
        next_config = dict(current)
        engine_configs = dict(current.get("engine_configs") or {})
        engine_config = dict(engine_configs.get(engine) or {})
        catalog = AI_ENGINE_CATALOG[engine]

        if request.activate:
            next_config["active_engine"] = engine

        if request.model is not None:
            engine_config["model"] = request.model.strip() or str(catalog.get("default_model") or "")
        if request.thinking is not None:
            if engine == "deepseek":
                engine_config["thinking"] = normalize_thinking(request.thinking)
            elif engine == "openai":
                engine_config["thinking"] = normalize_openai_reasoning_effort(request.thinking)
        if request.speed is not None and engine == "openai":
            engine_config["speed"] = normalize_openai_speed(request.speed)

        has_token_config = bool(catalog.get("default_context_window") or catalog.get("default_max_tokens"))
        if request.context_window is not None and has_token_config:
            engine_config["context_window"] = normalize_int_setting(
                request.context_window,
                default=int(catalog.get("default_context_window") or 1_000_000),
                min_value=1024,
                max_value=int(catalog.get("default_context_window") or 1_000_000),
            )
        if request.max_tokens is not None and has_token_config:
            context_window = int(engine_config.get("context_window") or catalog.get("default_context_window") or 1_000_000)
            engine_config["max_tokens"] = min(
                normalize_int_setting(
                    request.max_tokens,
                    default=int(catalog.get("default_max_tokens") or 4096),
                    min_value=64,
                    max_value=int(catalog.get("max_output_tokens") or catalog.get("default_max_tokens") or 4096),
                ),
                context_window,
            )
        if request.base_url is not None:
            engine_config["base_url"] = request.base_url.strip() or str(catalog.get("default_base_url") or "")
        if request.api_key_env is not None:
            engine_config["api_key_env"] = request.api_key_env.strip() or str(catalog.get("default_api_key_env") or "")
        if request.enabled is not None:
            engine_config["enabled"] = bool(request.enabled)

        if has_token_config:
            context_window = normalize_int_setting(
                engine_config.get("context_window"),
                default=int(catalog.get("default_context_window") or 1_000_000),
                min_value=1024,
                max_value=int(catalog.get("default_context_window") or 1_000_000),
            )
            engine_config["context_window"] = context_window
            engine_config["max_tokens"] = min(
                normalize_int_setting(
                    engine_config.get("max_tokens"),
                    default=int(catalog.get("default_max_tokens") or 4096),
                    min_value=64,
                    max_value=int(catalog.get("max_output_tokens") or catalog.get("default_max_tokens") or 4096),
                ),
                context_window,
            )

        engine_configs[engine] = engine_config
        next_config["engine_configs"] = engine_configs
        if engine == "deepseek":
            next_config["deepseek_model"] = str(engine_config.get("model") or "deepseek-v4-flash")
            next_config["deepseek_thinking"] = normalize_thinking(str(engine_config.get("thinking") or "enabled"))
        elif engine == "openai":
            next_config["openai_model"] = str(engine_config.get("model") or "gpt-5.5")

        write_json_file(self.settings_path, self.file_payload(next_config))
        return self.response()

    def records(self, config: dict[str, Any], secrets: dict[str, str]) -> dict[str, ChatAiEngineRecord]:
        active_engine = str(config["active_engine"])
        engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}
        records: dict[str, ChatAiEngineRecord] = {}
        for engine_id, catalog in AI_ENGINE_CATALOG.items():
            engine_config = engine_configs.get(engine_id) if isinstance(engine_configs.get(engine_id), dict) else {}
            support_status = str(catalog.get("support_status") or "planned")
            editable = support_status == "supported"
            api_key_configured = secret_configured(engine_config)
            if support_status == "planned":
                config_status = "planned"
            elif api_key_configured:
                config_status = "configured"
            else:
                config_status = "missing_secret"
            secret_env_vars = [str(engine_config["api_key_env"])] if engine_config.get("api_key_env") else []
            health_detail = {
                "configured": "Ready for Chat selection.",
                "missing_secret": "Configuration is saved, but the referenced API key environment variable is missing.",
                "planned": "Catalog entry is visible for planning, but the adapter is not enabled yet.",
            }.get(config_status, "Status has not been checked.")
            records[engine_id] = ChatAiEngineRecord(
                id=engine_id,
                display_name=str(catalog.get("display_name") or engine_id),
                kind=str(catalog.get("kind") or "llm_api"),
                description=str(catalog.get("description") or ""),
                support_status=support_status,
                config_status=config_status,
                auth_kind=str(catalog.get("auth_kind") or "none"),
                base_url=str(engine_config.get("base_url") or "") or None,
                api_key_env=str(engine_config.get("api_key_env") or "") or None,
                model=str(engine_config.get("model") or "") or None,
                thinking=str(engine_config.get("thinking") or "") or None,
                speed=str(engine_config.get("speed") or "") or None,
                context_window=int(engine_config["context_window"]) if engine_config.get("context_window") is not None else None,
                max_tokens=int(engine_config["max_tokens"]) if engine_config.get("max_tokens") is not None else None,
                enabled=bool(engine_config.get("enabled", True)),
                editable=editable,
                active=active_engine == engine_id,
                api_key_configured=api_key_configured,
                status=config_status,
                secret_env_vars=secret_env_vars,
                capabilities=[str(capability) for capability in catalog.get("capabilities", [])],
                model_options=[str(option) for option in catalog.get("model_options", [])],
                thinking_options=[str(option) for option in catalog.get("thinking_options", [])],
                config_fields=self.config_fields(catalog=catalog, engine_config=engine_config, editable=editable, field_key="config_fields"),
                chat_options=self.config_fields(catalog=catalog, engine_config=engine_config, editable=editable, field_key="chat_options"),
                health_detail=health_detail,
            )
        return records

    def config_fields(
        self,
        *,
        catalog: dict[str, Any],
        engine_config: dict[str, Any],
        editable: bool,
        field_key: str,
    ) -> list[ChatAiEngineConfigField]:
        fields = catalog.get(field_key) if isinstance(catalog.get(field_key), list) else []
        result: list[ChatAiEngineConfigField] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("id") or "")
            if not field_id:
                continue
            result.append(
                ChatAiEngineConfigField(
                    id=field_id,
                    label=str(field.get("label") or field_id.replace("_", " ").title()),
                    kind=str(field.get("kind") or "text"),
                    value=field_value(engine_config, field_id),
                    placeholder=str(field.get("placeholder") or ""),
                    options=[str(option) for option in field.get("options", [])],
                    required=bool(field.get("required", False)),
                    secret=bool(field.get("secret", False)),
                    read_only=bool(field.get("read_only", False)) or not editable,
                    help=str(field.get("help") or ""),
                )
            )
        return result

    def file_payload(self, config: dict[str, Any]) -> dict[str, Any]:
        return ai_engine_file_payload(config, updated_at=self.now())
