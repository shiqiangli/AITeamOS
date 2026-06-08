"""Reply formatting helpers for Chat Kernel commands."""

from __future__ import annotations


def build_blocked_command_reply(command_label: str, reason: str, hint: str) -> str:
    return (
        f"{command_label} 暂时没有执行。\n\n"
        f"原因：{reason}\n\n"
        f"你可以这样说：{hint}"
    )
