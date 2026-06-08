"""Kernel command planning policy helpers for Chat."""

from __future__ import annotations

from .chat_kernel_catalog import COMMAND_PLANNING_SIGNAL_RE

_COMMAND_INTERCEPT_OFF_MODES = {"0", "false", "no", "off", "disabled", "never", "llm"}
_COMMAND_INTERCEPT_ON_MODES = {"1", "true", "yes", "on", "enabled", "always", "legacy"}


def should_use_llm_command_planner(
    *,
    message: str,
    selected_ai_engine: str,
    has_deepseek_api_key: bool,
) -> bool:
    if not COMMAND_PLANNING_SIGNAL_RE.search(message):
        return False
    if selected_ai_engine != "deepseek":
        return False
    return has_deepseek_api_key


def local_kernel_heuristics_allowed(*, mode: str, selected_ai_engine: str) -> bool:
    normalized_mode = mode.strip().lower()
    if normalized_mode in _COMMAND_INTERCEPT_ON_MODES:
        return True
    return selected_ai_engine == "stub"


def chat_kernel_command_intercept_enabled(
    *,
    mode: str,
    selected_ai_engine: str,
    is_remote_kernel_action: bool,
) -> bool:
    normalized_mode = mode.strip().lower()
    if normalized_mode in _COMMAND_INTERCEPT_OFF_MODES:
        return False
    if normalized_mode in _COMMAND_INTERCEPT_ON_MODES:
        return True
    if selected_ai_engine == "stub":
        return True
    return is_remote_kernel_action
