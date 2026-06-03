"""Unified capability registry for AITeamOS P0.

This module keeps executable capabilities visible without turning them into a
user-facing execution surface. Chat remains the primary operation surface; the
registry is for planning, permissions, health, and debugging.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .mcp_service import list_mcp_connectors, mcp_registry_status


class CapabilityRecord(BaseModel):
    id: str
    name: str
    kind: str
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
    local_tool_count: int
    mcp_capability_count: int
    agent_executor_count: int
    saved_paths: dict[str, str] = Field(default_factory=dict)


class CapabilityRegistryResponse(BaseModel):
    status: CapabilityRegistryStatus
    capabilities: list[CapabilityRecord]
    model: dict[str, str]


_LOCAL_CHAT_TOOLS: list[CapabilityRecord] = [
    CapabilityRecord(
        id="list_employees",
        name="List employees",
        kind="local_tool",
        domain="employees",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="List file-backed AI and human employees for chat replies and employee inspection.",
        owner_scope="Clara and authorized employees",
        permissions=["employees:read"],
        produces=["chat_result", "trace_event"],
        boundary="Read-only employee inventory.",
        deep_link="#/employees",
    ),
    CapabilityRecord(
        id="create_employee",
        name="Create employee",
        kind="local_tool",
        domain="employees",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Create a local employee profile under .aiteamos/employees.",
        owner_scope="Clara",
        permissions=["employees:write"],
        arguments=["display_name", "employee_id", "kind", "role", "summary", "skills"],
        produces=["employee_profile", "trace_event"],
        boundary="Creates local profile metadata; it does not provision an external runtime account.",
        deep_link="#/employees",
    ),
    CapabilityRecord(
        id="edit_employee_profile",
        name="Edit employee profile",
        kind="local_tool",
        domain="employees",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Update safe local employee profile fields.",
        owner_scope="Clara",
        permissions=["employees:write"],
        arguments=["target_employee_id", "target_employee_name", "display_name", "role", "summary", "skills", "runtime_mode"],
        produces=["employee_profile", "trace_event"],
        boundary="Only supported profile fields are editable in P0.",
        deep_link="#/employees",
    ),
    CapabilityRecord(
        id="delete_employee",
        name="Delete employee",
        kind="local_tool",
        domain="employees",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Remove a local employee profile after intent is planned and confirmed by policy.",
        owner_scope="Clara",
        permissions=["employees:delete"],
        arguments=["target_employee_id", "target_employee_name"],
        produces=["trace_event"],
        boundary="Deletes only the local employee profile, not external accounts or provider state.",
        deep_link="#/employees",
    ),
    CapabilityRecord(
        id="list_skills",
        name="List skills",
        kind="local_tool",
        domain="skills",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="List local SKILL.md assets.",
        owner_scope="Clara and authorized employees",
        permissions=["skills:read"],
        produces=["chat_result", "trace_event"],
        boundary="Read-only local skill inventory.",
        deep_link="#/assets/skills",
    ),
    CapabilityRecord(
        id="create_skill",
        name="Create skill",
        kind="local_tool",
        domain="skills",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Create a local file-backed skill.",
        owner_scope="Clara",
        permissions=["skills:write"],
        arguments=["skill_id", "title", "description", "body"],
        produces=["skill_file", "trace_event"],
        boundary="Creates method/context assets; it does not execute the method by itself.",
        deep_link="#/assets/skills",
    ),
    CapabilityRecord(
        id="assign_skill_to_employee",
        name="Assign skill to employee",
        kind="local_tool",
        domain="skills",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Attach a local skill id to a employee profile.",
        owner_scope="Clara",
        permissions=["employees:write", "skills:read"],
        arguments=["skill_id", "skill_name", "target_employee_id", "target_employee_name"],
        produces=["employee_profile", "trace_event"],
        boundary="Records availability; execution still depends on the employee runtime and tool permissions.",
        deep_link="#/assets/skills",
    ),
    CapabilityRecord(
        id="delete_skill",
        name="Delete skill",
        kind="local_tool",
        domain="skills",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Remove a local skill directory and detach it from employee profiles.",
        owner_scope="Clara",
        permissions=["skills:delete", "employees:write"],
        arguments=["skill_id", "skill_name"],
        produces=["trace_event"],
        boundary="Deletes local skill files only.",
        deep_link="#/assets/skills",
    ),
    CapabilityRecord(
        id="search_knowledge",
        name="Search knowledge",
        kind="local_tool",
        domain="knowledge",
        source="AITeamOS Kernel",
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
        id="create_ticket",
        name="Create ticket",
        kind="local_tool",
        domain="tickets",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Create a local P0 Ticket and attach employee/repo context for delegation.",
        owner_scope="Clara",
        permissions=["tickets:write"],
        arguments=[
            "title",
            "description",
            "target_employee_id",
            "assigned_role",
            "validation_employee_id",
            "validation_role",
            "code_repository_ids",
        ],
        produces=["ticket", "trace_event"],
        boundary="Plane remains the long-term Ticket fact source; this local tool proves the flow.",
        deep_link="#/tickets/tickets",
    ),
    CapabilityRecord(
        id="record_ticket_report",
        name="Record ticket report",
        kind="local_tool",
        domain="tickets",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Append a employee, PV, or validation report to a Ticket.",
        owner_scope="Clara and assigned employees",
        permissions=["tickets:write"],
        arguments=["ticket_id", "reporter_employee_id", "reporter_role", "content", "report_type", "evidence"],
        produces=["ticket_report", "trace_event"],
        boundary="Persists evidence/report text; Clara still summarizes through the LLM.",
        deep_link="#/tickets/reports",
    ),
    CapabilityRecord(
        id="list_tickets",
        name="List tickets",
        kind="local_tool",
        domain="tickets",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="List local P0 Tickets for Chat and Tickets page inspection.",
        owner_scope="Clara and authorized employees",
        permissions=["tickets:read"],
        produces=["chat_result", "trace_event"],
        boundary="Read-only local Ticket inventory.",
        deep_link="#/tickets/tickets",
    ),
    CapabilityRecord(
        id="list_code_repositories",
        name="List code repositories",
        kind="local_tool",
        domain="repositories",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="List configured repository mappings for Plane project context.",
        owner_scope="Clara and authorized employees",
        permissions=["repositories:read"],
        produces=["chat_result", "trace_event"],
        boundary="Reads repository registry only; it does not inspect code contents.",
        deep_link="#/settings/code-repositories",
    ),
    CapabilityRecord(
        id="inspect_code_repository",
        name="Inspect code repository",
        kind="local_tool",
        domain="repositories",
        source="AITeamOS Kernel",
        status="ready",
        enabled=True,
        configured=True,
        description="Bounded text search/read for configured local repositories.",
        owner_scope="Non-Clara technical employees",
        permissions=["repositories:read", "repo:read"],
        arguments=["ticket_id", "code_repository_id", "code_repository_name", "query", "file_paths"],
        produces=["repo_evidence", "ticket_report", "trace_event"],
        boundary="Clara should delegate repo inspection to RD/PV/Architect employees; remote repos need connectors or executors.",
        deep_link="#/settings/code-repositories",
    ),
]

_AGENT_EXECUTORS: list[CapabilityRecord] = [
    CapabilityRecord(
        id="executor:codex",
        name="Codex",
        kind="agent_executor",
        domain="runtime",
        source="AITeamOS Settings",
        status="planned",
        description="Planned coding executor for repo edits, tests, and implementation reports.",
        owner_scope="RD/PV/Architect employees",
        permissions=["repo:read", "repo:write", "tests:run"],
        required_settings=["executor_profile", "workspace_scope"],
        produces=["patch", "test_result", "ticket_report"],
        boundary="Executor integration should reuse mature agent behavior instead of rebuilding an IDE.",
        deep_link="#/settings/agent-executors",
    ),
    CapabilityRecord(
        id="executor:cursor",
        name="Cursor",
        kind="agent_executor",
        domain="runtime",
        source="AITeamOS Settings",
        status="planned",
        description="Planned IDE agent executor when a stable external API or CLI is available.",
        owner_scope="RD/PV/Architect employees",
        permissions=["repo:read", "repo:write"],
        required_settings=["api_or_cli_access"],
        produces=["implementation_report"],
        boundary="AITeamOS should call Cursor as an executor, not clone Cursor features.",
        deep_link="#/settings/agent-executors",
    ),
    CapabilityRecord(
        id="executor:qoder",
        name="Qoder",
        kind="agent_executor",
        domain="runtime",
        source="AITeamOS Settings",
        status="planned",
        description="Planned external coding-agent runtime candidate.",
        owner_scope="RD/PV/Architect employees",
        permissions=["repo:read", "repo:write"],
        required_settings=["api_or_cli_access"],
        produces=["implementation_report"],
        boundary="Kept behind EmployeeRuntimeAdapter.",
        deep_link="#/settings/agent-executors",
    ),
    CapabilityRecord(
        id="executor:claude-code",
        name="Claude Code",
        kind="agent_executor",
        domain="runtime",
        source="AITeamOS Settings",
        status="planned",
        description="Planned CLI coding executor candidate.",
        owner_scope="RD/PV/Architect employees",
        permissions=["repo:read", "repo:write", "tests:run"],
        required_settings=["cli_auth", "workspace_scope"],
        produces=["patch", "test_result", "ticket_report"],
        boundary="Kept behind EmployeeRuntimeAdapter.",
        deep_link="#/settings/agent-executors",
    ),
]


def local_chat_tools() -> list[CapabilityRecord]:
    return [tool.model_copy(deep=True) for tool in _LOCAL_CHAT_TOOLS]


def local_chat_tool_ids() -> list[str]:
    return [tool.id for tool in _LOCAL_CHAT_TOOLS]


def local_chat_tool_union(*, include_none: bool = False) -> str:
    ids = local_chat_tool_ids()
    if include_none:
        ids = ["none", *ids]
    return "|".join(ids)


def local_chat_tool_prompt() -> str:
    lines = ["- none"]
    lines.extend(f"- {tool.id}" for tool in _LOCAL_CHAT_TOOLS)
    return "\n".join(lines)


def _connector_status(enabled: bool, configured: bool, status: str) -> str:
    if enabled and configured:
        return "ready"
    if not enabled and status not in {"planned", "local"}:
        return "disabled"
    return status


def _mcp_capabilities() -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    for connector in list_mcp_connectors():
        status = _connector_status(connector.enabled, connector.configured, connector.status)
        records.append(
            CapabilityRecord(
                id=f"mcp:{connector.id}",
                name=connector.name,
                kind="mcp_connector",
                domain="external",
                source="MCP Registry",
                status=status,
                enabled=connector.enabled,
                configured=connector.configured,
                description=connector.description,
                owner_scope="Connector adapter",
                permissions=connector.permissions,
                required_settings=connector.required_settings,
                produces=["external_capabilities"],
                boundary="Connector exposes external capabilities; AI Employees consume AITeamOS-normalized actions.",
                deep_link="#/settings/mcp-connectors",
                connector_id=connector.id,
            )
        )
        for capability in connector.capabilities:
            records.append(
                CapabilityRecord(
                    id=f"mcp:{connector.id}:{capability}",
                    name=capability,
                    kind="mcp_capability",
                    domain=capability.split(".", maxsplit=1)[0],
                    source=f"MCP connector: {connector.name}",
                    status=status,
                    enabled=connector.enabled,
                    configured=connector.configured,
                    description=f"{connector.name} exposes {capability}.",
                    owner_scope="Authorized employees through connector adapter",
                    permissions=connector.permissions,
                    required_settings=connector.required_settings,
                    produces=["external_result", "trace_event"],
                    boundary="External system semantics stay behind the connector adapter.",
                    deep_link="#/settings/mcp-connectors",
                    connector_id=connector.id,
                )
            )
    return records


def list_capabilities() -> list[CapabilityRecord]:
    records = [
        *local_chat_tools(),
        *_mcp_capabilities(),
        *[executor.model_copy(deep=True) for executor in _AGENT_EXECUTORS],
    ]
    return sorted(records, key=lambda item: (item.kind, item.domain, item.id))


def capability_registry_status() -> CapabilityRegistryStatus:
    capabilities = list_capabilities()
    mcp_status = mcp_registry_status()
    return CapabilityRegistryStatus(
        capability_count=len(capabilities),
        enabled_count=sum(1 for item in capabilities if item.enabled),
        configured_count=sum(1 for item in capabilities if item.configured),
        ready_count=sum(1 for item in capabilities if item.status in {"ready", "active", "configured", "local"}),
        local_tool_count=sum(1 for item in capabilities if item.kind == "local_tool"),
        mcp_capability_count=sum(1 for item in capabilities if item.kind == "mcp_capability"),
        agent_executor_count=sum(1 for item in capabilities if item.kind == "agent_executor"),
        saved_paths=mcp_status.saved_paths,
    )


def capability_registry() -> CapabilityRegistryResponse:
    return CapabilityRegistryResponse(
        status=capability_registry_status(),
        capabilities=list_capabilities(),
        model={
            "knowledge": "facts and history that ground reasoning; does not execute actions",
            "skill": "method, workflow, and role-specific know-how assigned to employees",
            "tool": "deterministic executable action owned by AITeamOS Kernel or a connector",
            "mcp": "standard connector layer for external tools and resources",
            "executor": "mature agent runtime used by employees for deeper Ticket execution",
        },
    )
