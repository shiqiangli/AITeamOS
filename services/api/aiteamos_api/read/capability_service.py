"""Unified capability registry for AITeamOS P0.

This module keeps executable capabilities visible without turning them into a
user-facing execution surface. Chat remains the primary operation surface; the
registry is for planning, permissions, health, and debugging.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .tool_connector_service import list_tool_connectors, tool_connector_registry_status


class CapabilityRecord(BaseModel):
    id: str
    name: str
    kind: str = "tool"
    source_kind: str = "kernel_command"
    domain: str
    source: str
    status: str = "planned"
    enabled: bool = False
    configured: bool = False
    description: str = ""
    owner_scope: str = ""
    permissions: list[str] = Field(default_factory=list)
    required_settings: list[str] = Field(default_factory=list)
    arguments: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    boundary: str = ""
    deep_link: str = ""
    connector_id: str = ""


class CapabilityRegistryStatus(BaseModel):
    capability_count: int
    enabled_count: int
    configured_count: int
    ready_count: int
    tool_count: int
    kernel_command_count: int
    mcp_tool_count: int
    native_api_tool_count: int = 0
    cli_tool_count: int = 0
    ci_tool_count: int = 0
    saved_paths: dict[str, str] = Field(default_factory=dict)


class CapabilityRegistryResponse(BaseModel):
    status: CapabilityRegistryStatus
    capabilities: list[CapabilityRecord]
    model: dict[str, str]


_LOCAL_KERNEL_CAPABILITIES: list[CapabilityRecord] = [
    CapabilityRecord(
        id="employees.manage",
        name="Manage employees",
        kind="tool",
        source_kind="kernel_command",
        domain="employees",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="List, create, update, and delete local workforce records through Kernel policy.",
        owner_scope="Clara with Kernel policy checks",
        permissions=["employees:read", "employees:write", "employees:delete"],
        arguments=["operation", "employee_id", "display_name", "kind", "role", "summary", "skills"],
        produces=["employee_profile", "chat_result", "trace_event"],
        boundary="Manages file-backed workforce records only; external accounts are not provisioned or removed.",
        deep_link="#/employees",
    ),
    CapabilityRecord(
        id="assets.manage",
        name="Manage assets",
        kind="tool",
        source_kind="kernel_command",
        domain="assets",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="List, create, assign, and delete Ticket-flow assets such as Skills.",
        owner_scope="Clara with Kernel policy checks",
        permissions=["skills:read", "skills:write", "skills:delete", "assets:assign"],
        arguments=["operation", "skill_id", "title", "description", "target_employee_id"],
        produces=["skill_file", "employee_profile", "trace_event"],
        boundary="Assets are reusable Ticket-flow records with provenance; Skill execution is separate.",
        deep_link="#/assets/capabilities/skills",
    ),
    CapabilityRecord(
        id="knowledge.search",
        name="Search knowledge",
        kind="tool",
        source_kind="kernel_command",
        domain="knowledge",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="Search approved Knowledge across Docs, Memories, and Decisions.",
        owner_scope="Clara and authorized employees",
        permissions=["knowledge:read"],
        arguments=["query"],
        produces=["knowledge_refs", "trace_event"],
        boundary="Retrieval only; Knowledge does not execute actions.",
        deep_link="#/assets/knowledge/docs",
    ),
    CapabilityRecord(
        id="tickets.manage",
        name="Manage tickets",
        kind="tool",
        source_kind="kernel_command",
        domain="tickets",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="Create, list, append reports, request validation, and request human review for Tickets in the configured Ticket Backend.",
        owner_scope="Clara and assigned employees",
        permissions=["tickets:read", "tickets:write"],
        arguments=["operation", "ticket_id", "title", "assignee", "validator", "reviewer", "report", "evidence"],
        produces=["ticket", "ticket_report", "validation_request", "human_review_request", "trace_event"],
        boundary="AITeamOS keeps the domain object named Ticket; provider-native names stay inside adapter metadata and provider refs.",
        deep_link="#/tickets/tickets",
    ),
    CapabilityRecord(
        id="repositories.list",
        name="List code repositories",
        kind="tool",
        source_kind="kernel_command",
        domain="repositories",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="List configured repository mappings for Ticket evidence context.",
        owner_scope="Clara and authorized employees",
        permissions=["repositories:read"],
        produces=["chat_result", "trace_event"],
        boundary="Reads repository registry only; it does not inspect code contents.",
        deep_link="#/settings/code-repositories",
    ),
    CapabilityRecord(
        id="repositories.inspect",
        name="Inspect code repository",
        kind="tool",
        source_kind="kernel_command",
        domain="repositories",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="Bounded text search/read for configured local repositories.",
        owner_scope="Non-Clara technical employees",
        permissions=["repositories:read", "repo:read"],
        arguments=["ticket_id", "code_repository_id", "code_repository_name", "query", "file_paths"],
        produces=["repo_evidence", "ticket_report", "trace_event"],
        boundary="Clara should delegate repo inspection to RD/PV/Architect employees; remote repos need connectors or AI Engines.",
        deep_link="#/settings/code-repositories",
    ),
    CapabilityRecord(
        id="terminal.run",
        name="Run terminal command",
        kind="tool",
        source_kind="kernel_command",
        domain="terminal",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="Run approved non-interactive workspace commands and stream output as Ticket evidence.",
        owner_scope="Clara and authorized technical employees",
        permissions=["terminal:run"],
        arguments=["command", "cwd", "ticket_id"],
        produces=["terminal_output", "ticket_report", "evidence_ref", "trace_event"],
        boundary="Not a general IDE terminal: no shell expansion, no interactive PTY, workspace-only cwd, allowlisted commands, and a Ticket binding is required.",
        deep_link="#/chat",
    ),
    CapabilityRecord(
        id="kernel.permissions",
        name="Inspect Kernel permissions",
        kind="tool",
        source_kind="kernel_command",
        domain="kernel",
        source="AITeamOS Kernel Command Executor",
        status="ready",
        enabled=True,
        configured=True,
        description="Inspect an Employee's raw profile permissions, expanded Kernel permissions, and command access.",
        owner_scope="Clara and authorized employees",
        permissions=["employees:read"],
        arguments=["target_employee_id", "target_employee_name"],
        produces=["permission_report", "trace_event"],
        boundary="Read-only introspection; it cannot grant or mutate permissions.",
        deep_link="#/chat",
    ),
]

_LOCAL_KERNEL_COMMANDS: dict[str, str] = {
    "employees.manage:list": "List file-backed employees.",
    "employees.manage:create": "Create a local Employee workforce record.",
    "employees.manage:update": "Update supported Employee profile fields.",
    "employees.manage:delete": "Delete a non-protected local Employee workforce record.",
    "assets.manage:list_skills": "List local SKILL.md assets.",
    "assets.manage:create_skill": "Create a local SKILL.md asset.",
    "assets.manage:assign_skill": "Assign a Skill asset to an Employee.",
    "assets.manage:delete_skill": "Delete a local Skill asset and detach it from Employees.",
    "knowledge.search:search": "Search approved Docs, Memories, and Decisions.",
    "tickets.manage:create": "Create a Ticket and route it to an assignee.",
    "tickets.manage:list": "List Tickets.",
    "tickets.manage:self_bootstrap_summary": "Summarize self-bootstrap learning facts from Tickets and recalled assets.",
    "tickets.manage:report": "Append a Ticket report or validation report.",
    "tickets.manage:request_validation": "Request PV or validator review for an existing Ticket.",
    "tickets.manage:request_human_review": "Request human review for a blocked or high-risk Ticket.",
    "repositories.list:list": "List configured code repositories.",
    "repositories.inspect:inspect": "Inspect a configured local repository for Ticket evidence.",
    "terminal.run:run": "Run an approved non-interactive terminal command as Ticket-bound evidence.",
    "kernel.permissions:inspect": "Inspect raw and expanded Employee permissions plus command access.",
}

def local_kernel_capabilities() -> list[CapabilityRecord]:
    return [tool.model_copy(deep=True) for tool in _LOCAL_KERNEL_CAPABILITIES]


def local_kernel_command_ids() -> list[str]:
    return list(_LOCAL_KERNEL_COMMANDS)


def local_kernel_command_union(*, include_none: bool = False) -> str:
    ids = local_kernel_command_ids()
    if include_none:
        ids = ["none", *ids]
    return "|".join(ids)


def local_kernel_command_prompt() -> str:
    lines = ["- none"]
    lines.extend(f"- {command}: {description}" for command, description in _LOCAL_KERNEL_COMMANDS.items())
    return "\n".join(lines)


def _connector_status(enabled: bool, configured: bool, status: str) -> str:
    if enabled and configured:
        return "ready"
    if not enabled and status not in {"planned", "local"}:
        return "disabled"
    return status


def _tool_connector_capabilities() -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    for connector in list_tool_connectors():
        status = _connector_status(connector.enabled, connector.configured, connector.status)
        for capability in connector.capabilities:
            records.append(
                CapabilityRecord(
                    id=f"mcp:{connector.id}:{capability}",
                    name=capability,
                    kind="tool",
                    source_kind="mcp_server",
                    domain=capability.split(".", maxsplit=1)[0],
                    source=f"MCP server: {connector.name}",
                    status=status,
                    enabled=connector.enabled,
                    configured=connector.configured,
                    description=f"{connector.name} exposes {capability}.",
                    owner_scope="Authorized employees through connector adapter",
                    permissions=connector.permissions,
                    required_settings=connector.required_settings,
                    produces=["external_result", "trace_event"],
                    boundary="External system semantics stay behind the connector adapter.",
                    deep_link="#/settings/tool-connectors",
                    connector_id=connector.id,
                )
            )
    return records


def list_capabilities() -> list[CapabilityRecord]:
    records = [
        *local_kernel_capabilities(),
        *_tool_connector_capabilities(),
    ]
    return sorted(records, key=lambda item: (item.kind, item.source_kind, item.domain, item.id))


def capability_registry_status() -> CapabilityRegistryStatus:
    capabilities = list_capabilities()
    connector_status = tool_connector_registry_status()
    return CapabilityRegistryStatus(
        capability_count=len(capabilities),
        enabled_count=sum(1 for item in capabilities if item.enabled),
        configured_count=sum(1 for item in capabilities if item.configured),
        ready_count=sum(1 for item in capabilities if item.status in {"ready", "active", "configured", "local"}),
        tool_count=sum(1 for item in capabilities if item.kind == "tool"),
        kernel_command_count=sum(1 for item in capabilities if item.kind == "tool" and item.source_kind == "kernel_command"),
        mcp_tool_count=sum(1 for item in capabilities if item.kind == "tool" and item.source_kind == "mcp_server"),
        saved_paths=connector_status.saved_paths,
    )


def capability_registry() -> CapabilityRegistryResponse:
    return CapabilityRegistryResponse(
        status=capability_registry_status(),
        capabilities=list_capabilities(),
        model={
            "knowledge": "facts and history that ground reasoning; does not execute actions",
            "capability": "reusable team capability asset; currently includes Skills, Kernel Commands, and MCP Tools",
            "skill": "method, workflow, and role-specific know-how assigned to employees",
            "tool": "executable action exposed through Kernel commands, MCP servers, native APIs, CLIs, CI, or AI engine bridges",
            "connector": "settings-side external capability source; not itself a capability asset",
            "ai_engine": "settings-side model or agent backend used for thinking or execution; not listed as a capability asset",
        },
    )
