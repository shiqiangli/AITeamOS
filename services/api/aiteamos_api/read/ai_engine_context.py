"""Context bundle formatting for remote AI Engine chat turns."""

from __future__ import annotations

import re
from typing import Any


def message_prefers_chinese(message: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", message))


def response_language_instruction(message: str) -> str:
    if message_prefers_chinese(message):
        return "Language: Reply in concise Simplified Chinese because the user's latest message contains Chinese."
    return "Language: Reply in the same language as the user's latest message."


def trim_context_text(value: str, *, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def format_context_list(items: list[Any]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return "\n".join(f"- {item}" for item in values) or "- none"


def build_employee_agent_context_bundle(
    *,
    memory_scope_text: str,
    ticket_text: str,
    skill_context: str,
    memory_text: str,
    capability_context: str,
) -> str:
    return (
        "Agent context bundle:\n"
        f"- Memory scopes: {memory_scope_text}\n"
        f"- Ticket keys bound to this turn: {ticket_text}\n\n"
        "Skill context:\n"
        f"{skill_context}\n\n"
        "Memory and Knowledge snippets:\n"
        f"{memory_text}\n\n"
        "Capability and permission context:\n"
        f"{capability_context}\n\n"
        "Runtime policy:\n"
        "- This chat turn is answer-first: the selected AI Engine receives the bundled context before answering.\n"
        "- Treat Kernel commands as capability facts and execution boundaries, not as proof that work was already done.\n"
        "- If the user asks what you can do, answer naturally from the bundle instead of dumping raw lists.\n"
        "- If the user asks for an action that requires a Kernel command, describe the intended action and any needed confirmation; "
        "do not claim the command actually ran unless trace evidence is present in the conversation."
    )


def build_ai_engine_context_gate(
    *,
    employee_id: str,
    display_name: str,
    role: str,
    summary: str,
    personality: str,
    responsibilities_text: str,
    skill_text: str,
    agent_bundle: str,
    handoff_text: str,
    user_message: str,
) -> str:
    return (
        "You are an AI Employee inside AITeamOS. Answer as the addressed employee, "
        "not as a generic assistant. Be concise, truthful, and explicit about what "
        "you can and cannot do in this P0 AI Engine setup. Use the bundled profile, "
        "memory, knowledge, capability, permission, and skill facts below to answer "
        "naturally.\n\n"
        f"Employee id: {employee_id}\n"
        f"Display name: {display_name}\n"
        f"Role: {role}\n"
        f"Summary: {summary}\n"
        f"Personality: {personality}\n"
        f"Responsibilities:\n{responsibilities_text}\n\n"
        f"Skill names available through AITeamOS context gate: {skill_text}\n\n"
        f"{agent_bundle}\n\n"
        f"Handoff rules:\n{handoff_text}\n\n"
        f"{response_language_instruction(user_message)}\n\n"
        "AITeamOS currently gates your profile, skills, memory, Ticket context, "
        "permissions, and trace capture before sending this turn to the AI Engine. "
        "Do not claim that Ticket, Harness, repository edits, or external tools were "
        "actually invoked unless the user provided evidence in this conversation."
    )
