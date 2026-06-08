"""Kernel command execution boundary helpers for Chat."""

from __future__ import annotations

from .chat_action_plan import ChatKernelCommandPlan
from .chat_kernel_catalog import HANDLER_TO_COMMAND_ID, KERNEL_COMMAND_SPECS
from .kernel_command_service import KernelCommand, KernelCommandSpec, KernelPolicyDecision


def _bounded_confidence(value: object) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def kernel_command_from_plan(plan: ChatKernelCommandPlan, *, ticket_keys: list[str]) -> KernelCommand | None:
    if plan.command == "none":
        return None
    spec = KERNEL_COMMAND_SPECS.get(plan.command)
    if spec is None:
        return None
    return KernelCommand(
        id=plan.command,
        capability=spec.capability,
        operation=spec.operation,
        arguments=dict(plan.arguments),
        confidence=plan.confidence,
        reason=plan.reason,
        source=plan.source,
        ticket_keys=ticket_keys,
    )


def kernel_command_from_handler_result(
    *,
    handler_name: str,
    result: dict[str, object],
    ticket_keys: list[str],
) -> tuple[KernelCommand, KernelCommandSpec]:
    command_id = HANDLER_TO_COMMAND_ID[handler_name]
    spec = KERNEL_COMMAND_SPECS[command_id]
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    arguments = plan.get("arguments") if isinstance(plan.get("arguments"), dict) else {}
    return (
        KernelCommand(
            id=command_id,
            capability=spec.capability,
            operation=spec.operation,
            arguments=dict(arguments),
            confidence=_bounded_confidence(plan.get("confidence", 0)),
            reason=str(plan.get("reason") or ""),
            source=str(plan.get("source") or "handler"),
            ticket_keys=ticket_keys,
        ),
        spec,
    )


def kernel_policy_blocked_reply(command: KernelCommand, policy: KernelPolicyDecision) -> str:
    missing = ", ".join(policy.missing_permissions) if policy.missing_permissions else "unknown"
    return (
        "Kernel policy 阻止了这次 command。\n\n"
        f"- Command: {command.id}\n"
        f"- Missing permissions: {missing}\n\n"
        "请先给当前 Employee 明确授权，或让 Clara 重新路由 Ticket。"
    )


def kernel_policy_blocked_result(command: KernelCommand, policy: KernelPolicyDecision) -> dict[str, object]:
    return {
        "status": "blocked",
        "detail": "Kernel policy denied command execution.",
        "reason": policy.reason,
        "command": command.model_dump(),
        "kernel_policy": policy.model_dump(),
    }
