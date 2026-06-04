"""AITeamOS Kernel command model and policy checks.

The Kernel command layer is intentionally thin: it validates that an Employee
may invoke a medium-grained capability operation before Chat hands execution to
the local handler. It is not an agent framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class KernelCommandSpec:
    id: str
    capability: str
    operation: str
    permissions: tuple[str, ...]
    risk: str = "low"
    streaming: bool = False
    description: str = ""


class KernelCommand(BaseModel):
    id: str
    capability: str
    operation: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    source: str = "heuristic"
    ticket_keys: list[str] = Field(default_factory=list)


class KernelPolicyDecision(BaseModel):
    status: str
    reason: str = ""
    risk: str = "low"
    required_permissions: list[str] = Field(default_factory=list)
    granted_permissions: list[str] = Field(default_factory=list)
    missing_permissions: list[str] = Field(default_factory=list)


def expand_employee_permissions(permissions: list[str]) -> set[str]:
    expanded = {permission.strip() for permission in permissions if permission.strip()}
    aliases = {
        "manage_employees": {"employees:read", "employees:write", "employees:delete"},
        "manage_skills": {"skills:read", "skills:write", "skills:delete", "assets:assign"},
        "manage_memory": {"memory:read", "memory:propose", "memory:approve", "assets:assign"},
        "manage_knowledge": {"knowledge:read", "knowledge:write"},
        "manage_tickets": {"tickets:read", "tickets:write"},
        "read_local_assets": {"employees:read", "skills:read", "knowledge:read", "tickets:read", "repositories:read"},
        "propose_code_change": {"repo:read"},
        "read_validation_evidence": {"repo:read"},
        "write_trace": {"trace:write"},
        "run_terminal": {"terminal:run"},
    }
    for permission in list(expanded):
        expanded.update(aliases.get(permission, set()))
    return expanded


def evaluate_kernel_policy(
    command: KernelCommand,
    *,
    spec: KernelCommandSpec,
    actor_permissions: list[str],
) -> KernelPolicyDecision:
    granted = expand_employee_permissions(actor_permissions)
    required = set(spec.permissions)
    missing = sorted(required - granted)
    if missing:
        return KernelPolicyDecision(
            status="blocked",
            reason="missing_permissions",
            risk=spec.risk,
            required_permissions=sorted(required),
            granted_permissions=sorted(granted),
            missing_permissions=missing,
        )
    return KernelPolicyDecision(
        status="allowed",
        reason="allowed_by_kernel_policy",
        risk=spec.risk,
        required_permissions=sorted(required),
        granted_permissions=sorted(granted),
        missing_permissions=[],
    )
