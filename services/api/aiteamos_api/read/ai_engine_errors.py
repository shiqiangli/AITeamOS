"""AI Engine error classification and blocker replies."""

from __future__ import annotations

import re

from fastapi import HTTPException


def ai_engine_error_text(exc: HTTPException | RuntimeError) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


def is_ai_engine_configuration_error(exc: HTTPException | RuntimeError) -> bool:
    text = ai_engine_error_text(exc).lower()
    return any(
        token in text
        for token in (
            "401",
            "403",
            "429",
            "api key",
            "apikey",
            "authentication",
            "authorization",
            "billing",
            "invalid_api_key",
            "invalid api key",
            "incorrect api key",
            "insufficient_quota",
            "missing_secret",
            "not enabled",
            "not configured",
            "quota",
            "rate limit",
            "rate_limit",
        )
    )


def safe_ai_engine_error_summary(exc: HTTPException | RuntimeError) -> str:
    text = ai_engine_error_text(exc)
    if not text.strip():
        return "unknown AI Engine configuration error"
    text = re.sub(r"sk-[A-Za-z0-9_*.-]+", "sk-***", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:360]


def build_ai_engine_configuration_reply(
    *,
    user_message: str,
    ai_engine_id: str,
    error: HTTPException | RuntimeError,
) -> str:
    reason = safe_ai_engine_error_summary(error)
    if _message_prefers_chinese(user_message):
        return (
            "这次没有进入本地 file stub，也没有让 Kernel 抢答；我已经把对话路由到选中的远程 AI Engine，"
            "但远程调用被配置问题阻止了。\n\n"
            f"- 选中的 AI Engine：{ai_engine_id}\n"
            f"- 问题：{reason}\n\n"
            "请更新对应的 API key 并重启后端，或临时把 Chat AI Engine 切回 stub。"
        )

    return (
        "This turn was not answered by the local file stub and was not intercepted by Kernel commands. "
        "AITeamOS routed it to the selected remote AI Engine, but the remote call was blocked by configuration.\n\n"
        f"- Selected AI Engine: {ai_engine_id}\n"
        f"- Problem: {reason}\n\n"
        "Update the API key and restart the backend, or temporarily switch Chat AI Engine back to stub."
    )


def _message_prefers_chinese(message: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", message))
