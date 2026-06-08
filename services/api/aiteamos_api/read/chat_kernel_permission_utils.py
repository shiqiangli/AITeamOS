"""Permission-inspection helpers for Chat Kernel commands."""

from __future__ import annotations

from typing import Any

from .chat_kernel_catalog import KERNEL_COMMAND_SPECS
from .kernel_command_service import KernelCommand, evaluate_kernel_policy


def command_access_rows(raw_permissions: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for command_id, spec in KERNEL_COMMAND_SPECS.items():
        command = KernelCommand(id=command_id, capability=spec.capability, operation=spec.operation)
        decision = evaluate_kernel_policy(command, spec=spec, actor_permissions=raw_permissions)
        rows.append(
            {
                "id": command_id,
                "capability": spec.capability,
                "operation": spec.operation,
                "risk": spec.risk,
                "description": spec.description,
                "status": "allowed" if decision.status == "allowed" else "blocked",
                "required_permissions": list(spec.permissions),
                "missing_permissions": decision.missing_permissions,
            }
        )
    return rows


def build_permissions_reply(
    *,
    employee_display_name: str,
    employee_id: str,
    employee_role: str,
    raw_permissions: list[str],
    expanded_permissions: list[str],
    commands: list[dict[str, Any]],
    prefers_chinese: bool,
) -> str:
    allowed = [item for item in commands if item["status"] == "allowed"]
    blocked = [item for item in commands if item["status"] == "blocked"]
    high_risk = [item for item in allowed if item["risk"] in {"destructive", "execution"}]
    if prefers_chinese:
        lines = [
            f"这是 Kernel 根据 {employee_display_name} 当前 profile 生成的权限事实，不是模型猜测。",
            "",
            f"- 员工：{employee_display_name} ({employee_id})",
            f"- 角色：{employee_role}",
            f"- Profile 原始权限：{', '.join(raw_permissions) if raw_permissions else '无'}",
            f"- Kernel 展开权限：{', '.join(expanded_permissions) if expanded_permissions else '无'}",
            "",
            "可执行 Kernel Commands：",
        ]
        if not allowed:
            lines.append("- 无")
        for item in allowed:
            risk = f"；风险={item['risk']}" if item["risk"] != "low" else ""
            lines.append(f"- {item['id']}{risk}")

        if high_risk:
            lines.extend([
                "",
                "高风险说明：",
                "- destructive / execution command 表示 Kernel 已授权，但仍应绑定 Ticket、保留 trace/evidence，并在需要时取得人类确认。",
            ])

        lines.extend(["", "未授权 Kernel Commands："])
        if not blocked:
            lines.append("- 无")
        for item in blocked:
            missing = ", ".join(item["missing_permissions"]) if item["missing_permissions"] else "未知"
            lines.append(f"- {item['id']}；缺失权限={missing}")
        return "\n".join(lines)

    lines = [
        f"这是 Kernel 根据 {employee_display_name} 当前 profile 生成的权限事实，不是模型猜测。",
        "",
        f"- Employee: {employee_display_name} ({employee_id})",
        f"- Role: {employee_role}",
        f"- Raw permissions: {', '.join(raw_permissions) if raw_permissions else 'none'}",
        f"- Expanded Kernel permissions: {', '.join(expanded_permissions) if expanded_permissions else 'none'}",
        "",
        "可执行 Kernel Commands：",
    ]
    if not allowed:
        lines.append("- none")
    for item in allowed:
        risk = f"；risk={item['risk']}" if item["risk"] != "low" else ""
        lines.append(f"- {item['id']}{risk}")

    if high_risk:
        lines.extend([
            "",
            "高风险说明：",
            "- destructive / execution command 代表 Kernel 已授权，但仍应绑定 Ticket、保留 trace/evidence，并在需要时取得人类确认。",
        ])

    lines.extend(["", "未授权 Kernel Commands："])
    if not blocked:
        lines.append("- none")
    for item in blocked:
        missing = ", ".join(item["missing_permissions"]) if item["missing_permissions"] else "unknown"
        lines.append(f"- {item['id']}；missing={missing}")
    return "\n".join(lines)
