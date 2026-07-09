"""Unified capability registry for AITeamOS P0.

This module keeps executable capabilities visible without turning them into a
user-facing execution surface. Chat remains the primary operation surface; the
registry is for planning, permissions, health, and debugging.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .tool_connector_service import list_tool_connectors, tool_connector_registry_status


class CapabilityRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    kind: str = "tool"
    source_kind: str = "kernel_command"
    domain: str
    source: str
    status: str = "planned"
    enabled: bool = False
    configured: bool = False
    access: str = "read"
    destructive: bool = False
    required_approval: list[str] = Field(default_factory=list)
    provider: str = ""
    tool_schema: dict[str, object] = Field(default_factory=dict, alias="schema")
    output_asset_policy: dict[str, object] = Field(default_factory=dict)
    operation_policies: dict[str, dict[str, object]] = Field(default_factory=dict)
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
        description="Create, list, append reports, request validation, request human review, and close self-bootstrap learning loops for Tickets in the configured Ticket Backend.",
        owner_scope="Clara and assigned employees",
        permissions=["tickets:read", "tickets:write"],
        arguments=["operation", "ticket_id", "title", "assignee", "validator", "reviewer", "report", "evidence", "usefulness_status"],
        produces=["ticket", "ticket_report", "validation_request", "human_review_request", "learning_summary", "trace_event"],
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

_UNIVERSAL_AGENT_CONTEXT_CAPABILITIES: list[CapabilityRecord] = [
    CapabilityRecord(
        id="universal_agent.get_employee_context",
        name="Get Employee context",
        kind="tool",
        source_kind="native_api",
        domain="employees",
        source="AITeamOS LangGraph Universal Employee Agent",
        status="ready",
        enabled=True,
        configured=True,
        description="Read the selected Employee profile and available Employee references already assembled for a LangGraph execution request.",
        owner_scope="LangGraph Universal Employee Agent through runtime governance",
        permissions=["employees:read"],
        arguments=["employee_id"],
        produces=["employee_context", "tool_call", "trace_event"],
        boundary="Read-only projection from the governed execution context; it does not mutate Employee records.",
        deep_link="#/employees",
        provider="aiteamos_langgraph",
    ),
    CapabilityRecord(
        id="universal_agent.search_tickets",
        name="Search Tickets",
        kind="tool",
        source_kind="native_api",
        domain="tickets",
        source="AITeamOS LangGraph Universal Employee Agent",
        status="ready",
        enabled=True,
        configured=True,
        description="Search Ticket records for relevant collaboration, handoff, evidence, and closeout context.",
        owner_scope="LangGraph Universal Employee Agent through runtime governance",
        permissions=["tickets:read"],
        arguments=["query", "status", "employee_id", "limit"],
        produces=["ticket_refs", "tool_call", "trace_event"],
        boundary="Read-only Ticket lookup; Ticket creation, reports, validation, and closeout remain separate governed actions.",
        deep_link="#/tickets/tickets",
        provider="aiteamos_langgraph",
    ),
    CapabilityRecord(
        id="universal_agent.get_ticket_context",
        name="Get Ticket context",
        kind="tool",
        source_kind="native_api",
        domain="tickets",
        source="AITeamOS LangGraph Universal Employee Agent",
        status="ready",
        enabled=True,
        configured=True,
        description="Read one Ticket with recent events and linked Assets for Ticket-bound execution.",
        owner_scope="LangGraph Universal Employee Agent through runtime governance",
        permissions=["tickets:read", "assets:read"],
        arguments=["ticket_id"],
        produces=["ticket_context", "asset_refs", "tool_call", "trace_event"],
        boundary="Read-only Ticket and Asset context; it cannot append reports or change assignments.",
        deep_link="#/tickets/tickets",
        provider="aiteamos_langgraph",
    ),
    CapabilityRecord(
        id="universal_agent.search_assets",
        name="Search Assets",
        kind="tool",
        source_kind="native_api",
        domain="assets",
        source="AITeamOS LangGraph Universal Employee Agent",
        status="ready",
        enabled=True,
        configured=True,
        description="Search governed Assets such as Memories, Docs, Skills, Tool calls, decisions, and validation records.",
        owner_scope="LangGraph Universal Employee Agent through runtime governance",
        permissions=["assets:read", "knowledge:read"],
        arguments=["query", "ticket_id", "employee_id", "kind", "limit"],
        produces=["asset_refs", "tool_call", "trace_event"],
        boundary="Read-only Asset lookup; Asset candidate creation and approval remain in ingestion/review services.",
        deep_link="#/assets",
        provider="aiteamos_langgraph",
    ),
    CapabilityRecord(
        id="universal_agent.search_memory",
        name="Search Memory",
        kind="tool",
        source_kind="native_api",
        domain="memory",
        source="AITeamOS LangGraph Universal Employee Agent",
        status="ready",
        enabled=True,
        configured=True,
        description="Search local and configured Graphiti memory for Ticket-, Employee-, and workspace-scoped facts.",
        owner_scope="LangGraph Universal Employee Agent through runtime governance",
        permissions=["knowledge:read", "memory:read"],
        arguments=["query", "ticket_key", "employee_id", "limit", "include_graphiti"],
        produces=["memory_refs", "tool_call", "trace_event"],
        boundary="Read-only memory recall; new memories are proposed through governed execution ingestion.",
        deep_link="#/assets/knowledge/memories",
        provider="aiteamos_langgraph",
    ),
    CapabilityRecord(
        id="universal_agent.inspect_system_status",
        name="Inspect System status",
        kind="tool",
        source_kind="native_api",
        domain="system",
        source="AITeamOS LangGraph Universal Employee Agent",
        status="ready",
        enabled=True,
        configured=True,
        description="Inspect configured Ticket, Asset graph, and Memory backend status for runtime grounding.",
        owner_scope="LangGraph Universal Employee Agent through runtime governance",
        permissions=["system:read"],
        arguments=[],
        produces=["system_status", "tool_call", "trace_event"],
        boundary="Read-only system status projection; it does not change provider settings.",
        deep_link="#/system-status",
        provider="aiteamos_langgraph",
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
    "tickets.manage:self_bootstrap_close": "Close a self-bootstrap Ticket with learning summary and recall usefulness feedback.",
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


def universal_agent_context_capabilities() -> list[CapabilityRecord]:
    return [tool.model_copy(deep=True) for tool in _UNIVERSAL_AGENT_CONTEXT_CAPABILITIES]


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
        *universal_agent_context_capabilities(),
        *_tool_connector_capabilities(),
    ]
    governed = [_with_governance_policy(record) for record in records]
    return sorted(governed, key=lambda item: (item.kind, item.source_kind, item.domain, item.id))


def capability_operation_policy(capability_id: str, operation: str) -> dict[str, object]:
    normalized_capability_id = capability_id.strip()
    normalized_operation = operation.strip()
    if not normalized_capability_id or not normalized_operation:
        return {}
    capability = next((item for item in list_capabilities() if item.id == normalized_capability_id), None)
    if capability is None:
        return {}
    policy = capability.operation_policies.get(normalized_operation)
    return dict(policy) if isinstance(policy, dict) else {}


def capability_operation_policy_for_command(command_id: str) -> dict[str, object]:
    normalized = command_id.strip()
    if ":" not in normalized:
        return {}
    capability_id, operation = normalized.rsplit(":", maxsplit=1)
    return capability_operation_policy(capability_id, operation)


def capability_required_approval_for_operation(capability_id: str, operation: str) -> list[str]:
    policy = capability_operation_policy(capability_id, operation)
    values = policy.get("required_approval")
    return [str(item) for item in values if str(item).strip()] if isinstance(values, list) else []


def capability_required_approval_for_command(command_id: str) -> list[str]:
    policy = capability_operation_policy_for_command(command_id)
    values = policy.get("required_approval")
    return [str(item) for item in values if str(item).strip()] if isinstance(values, list) else []


def _with_governance_policy(record: CapabilityRecord) -> CapabilityRecord:
    permissions = set(record.permissions)
    access = record.access if record.access != "read" else _access_from_permissions(permissions)
    destructive = record.destructive or access == "destructive"
    required_approval = record.required_approval or _required_approval(permissions, access)
    provider = record.provider or ("aiteamos_kernel" if record.source_kind == "kernel_command" else record.connector_id or record.source_kind)
    schema = record.tool_schema or _argument_schema(record.arguments)
    output_asset_policy = record.output_asset_policy or _output_asset_policy(record)
    operation_policies = record.operation_policies or _operation_policies(record)
    return record.model_copy(
        update={
            "access": access,
            "destructive": destructive,
            "required_approval": required_approval,
            "provider": provider,
            "tool_schema": schema,
            "output_asset_policy": output_asset_policy,
            "operation_policies": operation_policies,
        }
    )


def _operation_policies(record: CapabilityRecord) -> dict[str, dict[str, object]]:
    if record.source_kind != "kernel_command":
        return {}
    from .chat_kernel_catalog import KERNEL_COMMAND_SPECS

    policies: dict[str, dict[str, object]] = {}
    for spec in sorted(KERNEL_COMMAND_SPECS.values(), key=lambda item: item.id):
        if spec.capability != record.id:
            continue
        permissions = set(spec.permissions)
        access = _access_from_operation(risk=spec.risk, permissions=permissions)
        policies[spec.operation] = {
            "command_id": spec.id,
            "access": access,
            "destructive": access == "destructive",
            "required_approval": _required_approval(permissions, access),
            "permissions": sorted(permissions),
            "risk": spec.risk,
            "streaming": spec.streaming,
            "description": spec.description,
        }
    return policies


def _access_from_permissions(permissions: set[str]) -> str:
    if any("delete" in permission or "terminal:run" == permission for permission in permissions):
        return "destructive"
    if any(token in permission for permission in permissions for token in (":write", ":run", ":assign")):
        return "write"
    return "read"


def _access_from_operation(*, risk: str, permissions: set[str]) -> str:
    if risk in {"destructive", "execution"}:
        return "destructive"
    return _access_from_permissions(permissions)


def _required_approval(permissions: set[str], access: str) -> list[str]:
    approvals: list[str] = []
    if "repo:write" in permissions:
        approvals.append("repo:write")
    if "terminal:run" in permissions:
        approvals.append("terminal:run")
    if access == "destructive":
        approvals.append("destructive_tool_call")
    return sorted(set(approvals))


def _argument_schema(arguments: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {argument: {"type": "string"} for argument in arguments},
        "additionalProperties": True,
    }


def _output_asset_policy(record: CapabilityRecord) -> dict[str, object]:
    candidate_types = []
    for produced in record.produces:
        if produced in {"ticket_report", "validation_request", "human_review_request"}:
            candidate_types.append("ticket_event")
        elif produced in {
            "asset_refs",
            "employee_context",
            "knowledge_refs",
            "memory_refs",
            "permission_report",
            "repo_evidence",
            "system_status",
            "terminal_output",
            "ticket_context",
            "ticket_refs",
            "tool_call",
        }:
            candidate_types.append("tool_call")
        elif produced in {"skill_file", "employee_profile"}:
            candidate_types.append(produced)
    return {
        "record_tool_call": True,
        "produces": list(record.produces),
        "candidate_asset_types": sorted(set(candidate_types)),
    }


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
        native_api_tool_count=sum(1 for item in capabilities if item.kind == "tool" and item.source_kind == "native_api"),
        cli_tool_count=sum(1 for item in capabilities if item.kind == "tool" and item.source_kind == "cli"),
        ci_tool_count=sum(1 for item in capabilities if item.kind == "tool" and item.source_kind == "ci"),
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
