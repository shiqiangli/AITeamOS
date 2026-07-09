"""LangChain model-provider adapter for AITeamOS LangGraph runtimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from .ai_engine_runtime_config import AiEngineRuntimeConfig


InitChatModelFactory = Callable[..., Any]


@dataclass(frozen=True)
class LangChainModelResult:
    provider: str
    content: str
    model: str
    response_id: str
    usage: dict[str, Any]
    response_metadata: dict[str, Any]
    provider_ref: dict[str, Any]


class LangChainModelProvider:
    """Thin adapter around LangChain's provider integrations.

    AITeamOS owns runtime governance and provenance. LangChain owns the model
    provider integration boundary.
    """

    def __init__(self, *, init_chat_model_factory: InitChatModelFactory | None = None) -> None:
        self._init_chat_model_factory = init_chat_model_factory

    async def ainvoke(
        self,
        *,
        selected_engine: str,
        runtime: AiEngineRuntimeConfig,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> LangChainModelResult:
        engine = selected_engine.strip().lower()
        kwargs = self._model_kwargs(engine, runtime, max_tokens=max_tokens)
        model = self._init_chat_model(**kwargs)
        response = await model.ainvoke(_to_langchain_messages(messages))
        return self._normalize_response(engine, response, model_hint=str(kwargs.get("model") or ""))

    def _init_chat_model(self, **kwargs: Any) -> Any:
        factory = self._init_chat_model_factory or _default_init_chat_model
        return factory(**kwargs)

    def _model_kwargs(self, engine: str, runtime: AiEngineRuntimeConfig, *, max_tokens: int | None) -> dict[str, Any]:
        if engine == "deepseek":
            kwargs: dict[str, Any] = {
                "model": runtime.deepseek_model(),
                "model_provider": "deepseek",
                "api_key": str(runtime.secrets.get("deepseek_api_key") or ""),
                "base_url": runtime.deepseek_base_url(),
                "max_tokens": int(max_tokens or runtime.deepseek_max_tokens()),
            }
            return {key: value for key, value in kwargs.items() if value not in {"", None}}
        if engine == "openai":
            kwargs = {
                "model": runtime.openai_model(),
                "model_provider": "openai",
                "api_key": str(runtime.secrets.get("openai_api_key") or ""),
                "base_url": runtime.openai_base_url(),
                "max_tokens": int(max_tokens or runtime.openai_max_output_tokens()),
            }
            return {key: value for key, value in kwargs.items() if value not in {"", None}}
        raise ValueError(f"Unsupported LangChain model provider: {engine}")

    def _normalize_response(self, engine: str, response: Any, *, model_hint: str) -> LangChainModelResult:
        metadata = _dict_attr(response, "response_metadata")
        usage = _dict_attr(response, "usage_metadata") or _usage_from_metadata(metadata)
        model = (
            str(metadata.get("model_name") or metadata.get("model") or metadata.get("model_id") or "").strip()
            or model_hint
        )
        response_id = str(metadata.get("id") or metadata.get("response_id") or metadata.get("request_id") or "").strip()
        provider_ref = {
            "provider": engine,
            "response_id": response_id,
            "model": model,
            "model_provider_boundary": "langchain",
        }
        return LangChainModelResult(
            provider=engine,
            content=_message_content(response),
            model=model,
            response_id=response_id,
            usage=usage,
            response_metadata=metadata,
            provider_ref=provider_ref,
        )


def _default_init_chat_model(**kwargs: Any) -> Any:
    from langchain.chat_models import init_chat_model

    return init_chat_model(**kwargs)


def _to_langchain_messages(messages: list[dict[str, str]]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []
    for item in messages:
        role = str(item.get("role") or "user").strip().lower()
        content = str(item.get("content") or "")
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def _message_content(response: Any) -> str:
    content = getattr(response, "content", "")
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
    return str(content or "").strip()


def _dict_attr(value: Any, attr: str) -> dict[str, Any]:
    data = getattr(value, attr, {})
    return dict(data) if isinstance(data, dict) else {}


def _usage_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    for key in ("token_usage", "usage", "usage_metadata"):
        value = metadata.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}
