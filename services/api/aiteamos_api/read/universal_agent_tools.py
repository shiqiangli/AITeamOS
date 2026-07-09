"""Read-only AITeamOS tools for the LangGraph universal employee agent."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field

from .capability_service import CapabilityRecord, list_capabilities
from .execution_contract import ExecutionRequest
from .memory_service import graphiti_backend_status, search_memory as search_memory_records
from .ticket_service import (
    asset_graph_status,
    get_ticket,
    get_ticket_events,
    list_tickets,
    ticket_asset_records,
    ticket_assets_for_ticket,
    ticket_backend_status,
)


_TOOL_CAPABILITY_IDS: dict[str, str] = {
    "get_employee_context": "universal_agent.get_employee_context",
    "search_tickets": "universal_agent.search_tickets",
    "get_ticket_context": "universal_agent.get_ticket_context",
    "search_assets": "universal_agent.search_assets",
    "search_memory": "universal_agent.search_memory",
    "inspect_system_status": "universal_agent.inspect_system_status",
}

_EXPOSABLE_STATUSES = {"ready", "active", "configured", "local"}


class UniversalAgentToolResult(BaseModel):
    tool_name: str
    status: str = "completed"
    capability: dict[str, Any] = Field(default_factory=dict)
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    output_refs: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0

    def event(self) -> dict[str, Any]:
        capability_id = str(self.capability.get("id") or "")
        output_asset_policy = self.capability.get("output_asset_policy") if isinstance(self.capability.get("output_asset_policy"), dict) else {}
        record_as_asset = bool(output_asset_policy.get("record_tool_call", False))
        command = (
            {
                "id": f"{capability_id}:run",
                "capability": capability_id,
                "operation": "run",
                "record_as_asset": record_as_asset,
            }
            if capability_id
            else {}
        )
        return {
            "event": f"universal_agent.tool.{self.status}",
            "detail": f"Universal Agent read-only tool {self.tool_name} {self.status}.",
            "data": {
                "tool_name": self.tool_name,
                "read_only": True,
                "capability": self.capability,
                "command": command,
                "record_as_asset": record_as_asset,
                "input_summary": self.input_summary,
                "output_refs": self.output_refs,
                "duration_ms": self.duration_ms,
                "provenance": self.provenance,
                "errors": self.errors,
            },
        }


class UniversalAgentToolRegistry:
    """Service-boundary registry for LangGraph tools projected from capabilities."""

    tool_names = set(_TOOL_CAPABILITY_IDS)

    def available_tools(self) -> list[dict[str, Any]]:
        capabilities = {item.id: item for item in list_capabilities()}
        tools: list[dict[str, Any]] = []
        for tool_name, capability_id in _TOOL_CAPABILITY_IDS.items():
            capability = capabilities.get(capability_id)
            if capability is None or not self._capability_is_exposable(capability):
                continue
            tools.append(self._capability_manifest(tool_name, capability))
        return tools

    async def run(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        *,
        request: ExecutionRequest,
    ) -> UniversalAgentToolResult:
        started_at = time.perf_counter()
        normalized_input = tool_input if isinstance(tool_input, dict) else {}
        input_summary = self._input_summary(normalized_input)
        capability = await asyncio.to_thread(self._capability_for_tool, tool_name)
        try:
            if capability is None:
                raise ValueError(f"Universal Agent tool is not exposed by capability registry: {tool_name}")
            if tool_name == "get_employee_context":
                output = await asyncio.to_thread(self._get_employee_context, request, normalized_input)
            elif tool_name == "search_tickets":
                output = await asyncio.to_thread(self._search_tickets, normalized_input)
            elif tool_name == "get_ticket_context":
                output = await asyncio.to_thread(self._get_ticket_context, normalized_input)
            elif tool_name == "search_assets":
                output = await asyncio.to_thread(self._search_assets, normalized_input)
            elif tool_name == "search_memory":
                output = await self._search_memory(request, normalized_input)
            elif tool_name == "inspect_system_status":
                output = await asyncio.to_thread(self._inspect_system_status)
            else:
                raise ValueError(f"Unknown Universal Agent tool: {tool_name}")
            status = "completed"
            errors: list[dict[str, Any]] = []
        except Exception as exc:
            output = {}
            status = "failed"
            errors = [
                {
                    "reason": "universal_agent_tool_failed",
                    "detail": str(exc),
                    "tool_name": tool_name,
                }
            ]
        duration_ms = max(0, int(round((time.perf_counter() - started_at) * 1000)))
        return UniversalAgentToolResult(
            tool_name=tool_name,
            status=status,
            capability=self._capability_manifest(tool_name, capability) if capability is not None else {},
            input_summary=input_summary,
            output=output,
            output_refs=self._output_refs(tool_name, output),
            provenance=self._provenance(tool_name, output),
            errors=errors,
            duration_ms=duration_ms,
        )

    def _capability_for_tool(self, tool_name: str) -> CapabilityRecord | None:
        capability_id = _TOOL_CAPABILITY_IDS.get(tool_name)
        if not capability_id:
            return None
        for capability in list_capabilities():
            if capability.id == capability_id and self._capability_is_exposable(capability):
                return capability
        return None

    def _capability_is_exposable(self, capability: CapabilityRecord) -> bool:
        if capability.kind != "tool" or capability.status not in _EXPOSABLE_STATUSES:
            return False
        if not capability.enabled or not capability.configured:
            return False
        if capability.access != "read" or capability.destructive:
            return False
        return not capability.required_approval

    def _capability_manifest(self, tool_name: str, capability: CapabilityRecord) -> dict[str, Any]:
        payload = capability.model_dump(mode="json", by_alias=True)
        return {
            "tool_name": tool_name,
            "id": capability.id,
            "name": capability.name,
            "source_kind": capability.source_kind,
            "provider": capability.provider,
            "domain": capability.domain,
            "access": capability.access,
            "destructive": capability.destructive,
            "required_approval": list(capability.required_approval),
            "schema": payload.get("schema") if isinstance(payload.get("schema"), dict) else {},
            "output_asset_policy": capability.output_asset_policy,
        }

    def _get_employee_context(self, request: ExecutionRequest, tool_input: dict[str, Any]) -> dict[str, Any]:
        context = request.task_context.get("universal_context") if isinstance(request.task_context.get("universal_context"), dict) else {}
        employee_context = context.get("employee_context") if isinstance(context.get("employee_context"), dict) else {}
        selected = employee_context.get("selected_employee") if isinstance(employee_context.get("selected_employee"), dict) else {}
        requested_employee_id = self._text(tool_input.get("employee_id")) or request.employee_id
        return {
            "employee_id": requested_employee_id,
            "selected_employee": selected,
            "work_history": employee_context.get("work_history") if isinstance(employee_context.get("work_history"), dict) else {},
            "available_employee_refs": employee_context.get("available_employee_refs") if isinstance(employee_context.get("available_employee_refs"), list) else [],
        }

    def _search_tickets(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        query = self._text(tool_input.get("query"))
        status = self._text(tool_input.get("status")) or None
        employee_id = self._text(tool_input.get("employee_id"))
        limit = self._limit(tool_input.get("limit"), default=5)
        tickets = list_tickets(status=status)
        refs = [
            self._ticket_ref(ticket)
            for ticket in tickets
            if self._matches_ticket(ticket.model_dump(mode="json"), query=query, employee_id=employee_id)
        ][:limit]
        return {
            "query": query,
            "tickets": refs,
            "count": len(refs),
        }

    def _get_ticket_context(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        ticket_id = self._text(tool_input.get("ticket_id"))
        if not ticket_id:
            raise ValueError("ticket_id is required.")
        ticket = get_ticket(ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket not found: {ticket_id}")
        events = get_ticket_events(ticket.id)
        assets = ticket_assets_for_ticket(ticket.id)
        return {
            "ticket": self._ticket_ref(ticket),
            "events": [
                {
                    "id": self._text(getattr(event, "id", "")),
                    "event_type": self._text(getattr(event, "event_type", "")),
                    "actor_employee_id": self._text(getattr(event, "actor_employee_id", "")),
                    "created_at": self._text(getattr(event, "created_at", "")),
                }
                for event in events[:8]
            ],
            "assets": [self._asset_ref(asset) for asset in assets[:8]],
        }

    def _search_assets(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        query = self._text(tool_input.get("query"))
        ticket_id = self._text(tool_input.get("ticket_id"))
        employee_id = self._text(tool_input.get("employee_id"))
        kind = self._text(tool_input.get("kind"))
        limit = self._limit(tool_input.get("limit"), default=8)
        assets = ticket_assets_for_ticket(ticket_id) if ticket_id else ticket_asset_records()
        refs = [
            self._asset_ref(asset)
            for asset in assets
            if self._matches_asset(asset.model_dump(mode="json"), query=query, employee_id=employee_id, kind=kind)
        ][:limit]
        return {"query": query, "assets": refs, "count": len(refs)}

    async def _search_memory(self, request: ExecutionRequest, tool_input: dict[str, Any]) -> dict[str, Any]:
        query = self._text(tool_input.get("query")) or self._text(request.task_context.get("task_summary"))
        ticket_key = self._text(tool_input.get("ticket_key")) or request.ticket_id
        employee_id = self._text(tool_input.get("employee_id")) or request.employee_id
        limit = self._limit(tool_input.get("limit"), default=5)
        include_graphiti = bool(tool_input.get("include_graphiti", True))
        response = await search_memory_records(
            query=query,
            employee_id=employee_id,
            ticket_key=ticket_key or None,
            limit=limit,
            include_graphiti=include_graphiti,
        )
        return {
            "query": response.query,
            "backend": response.backend.model_dump(mode="json"),
            "memories": [
                {
                    "memory_id": result.id,
                    "content": result.content[:240],
                    "source": result.source,
                    "source_kind": result.source_kind,
                    "source_ref": result.source_ref,
                    "scope_kind": result.scope_kind,
                    "scope_ref": result.scope_ref,
                    "memory_type": result.memory_type,
                    "score": result.score,
                    "tags": result.tags,
                    "graphiti_episode_id": result.graphiti_episode_id or "",
                }
                for result in response.results[:limit]
            ],
            "count": len(response.results[:limit]),
        }

    def _inspect_system_status(self) -> dict[str, Any]:
        return {
            "ticket_backend": ticket_backend_status().model_dump(mode="json"),
            "asset_graph": asset_graph_status().model_dump(mode="json"),
            "memory_backend": graphiti_backend_status().model_dump(mode="json"),
        }

    def _output_refs(self, tool_name: str, output: dict[str, Any]) -> list[dict[str, Any]]:
        if tool_name == "get_employee_context":
            employee = output.get("selected_employee") if isinstance(output.get("selected_employee"), dict) else {}
            employee_id = self._text(employee.get("employee_id")) or self._text(output.get("employee_id"))
            return [{"kind": "employee", "ref": employee_id}] if employee_id else []
        if tool_name == "search_tickets":
            return [{"kind": "ticket", "ref": self._text(item.get("ticket_id"))} for item in self._items(output.get("tickets")) if self._text(item.get("ticket_id"))]
        if tool_name == "get_ticket_context":
            ticket = output.get("ticket") if isinstance(output.get("ticket"), dict) else {}
            ticket_id = self._text(ticket.get("ticket_id"))
            return [{"kind": "ticket", "ref": ticket_id}] if ticket_id else []
        if tool_name == "search_assets":
            return [{"kind": self._text(item.get("kind")) or "asset", "ref": self._text(item.get("asset_id"))} for item in self._items(output.get("assets")) if self._text(item.get("asset_id"))]
        if tool_name == "search_memory":
            return [{"kind": "memory", "ref": self._text(item.get("memory_id"))} for item in self._items(output.get("memories")) if self._text(item.get("memory_id"))]
        if tool_name == "inspect_system_status":
            return [{"kind": "system_status", "ref": "aiteamos"}]
        return []

    def _provenance(self, tool_name: str, output: dict[str, Any]) -> list[dict[str, Any]]:
        if tool_name == "search_memory":
            backend = output.get("backend") if isinstance(output.get("backend"), dict) else {}
            return [
                {
                    "source_kind": "memory_service",
                    "source_ref": "search_memory",
                    "scope_kind": "workspace",
                    "scope_ref": "aiteamos",
                    "source_confidence": 0.85,
                },
                {
                    "source_kind": "graphiti_backend_status",
                    "source_ref": self._text(backend.get("mode")) or "memory_backend",
                    "scope_kind": "workspace",
                    "scope_ref": "aiteamos",
                    "source_confidence": 1.0,
                },
            ]
        source_ref = {
            "get_employee_context": "execution_request.task_context.universal_context",
            "search_tickets": "list_tickets",
            "get_ticket_context": "get_ticket",
            "search_assets": "ticket_asset_records",
            "inspect_system_status": "system_status_services",
        }.get(tool_name, tool_name)
        return [
            {
                "source_kind": "aiteamos_service",
                "source_ref": source_ref,
                "scope_kind": "workspace",
                "scope_ref": "aiteamos",
                "source_confidence": 0.9,
            }
        ]

    def _input_summary(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        allowed = ("query", "ticket_id", "ticket_key", "employee_id", "status", "kind", "limit", "include_graphiti")
        return {key: self._text(value) if isinstance(value, str) else value for key, value in tool_input.items() if key in allowed}

    def _ticket_ref(self, ticket: Any) -> dict[str, Any]:
        payload = ticket.model_dump(mode="json") if hasattr(ticket, "model_dump") else dict(ticket)
        reports = payload.get("reports") if isinstance(payload.get("reports"), list) else []
        evidence_count = sum(len(report.get("evidence") or []) for report in reports if isinstance(report, dict))
        return {
            "ticket_id": self._text(payload.get("id")),
            "title": self._text(payload.get("title")),
            "status": self._text(payload.get("status")),
            "ticket_type": self._text(payload.get("ticket_type")),
            "assigned_employee_id": self._text(payload.get("assigned_employee_id")),
            "report_count": len(reports),
            "evidence_count": evidence_count,
            "provenance": {
                "source_kind": "ticket",
                "source_ref": self._text(payload.get("id")),
                "scope_kind": "ticket",
                "scope_ref": self._text(payload.get("id")),
            },
            "source_confidence": 0.9,
        }

    def _asset_ref(self, asset: Any) -> dict[str, Any]:
        payload = asset.model_dump(mode="json") if hasattr(asset, "model_dump") else dict(asset)
        asset_id = self._text(payload.get("metadata", {}).get("asset_id")) if isinstance(payload.get("metadata"), dict) else ""
        return {
            "asset_id": asset_id or self._text(payload.get("id")),
            "kind": self._text(payload.get("kind")),
            "title": self._text(payload.get("title")),
            "status": self._text(payload.get("status")),
            "source_ticket_id": self._text(payload.get("source_ticket_id")),
            "source_employee_id": self._text(payload.get("source_employee_id")),
            "provenance": {
                "source_kind": "ticket_asset_record",
                "source_ref": self._text(payload.get("id")),
                "scope_kind": "ticket" if self._text(payload.get("source_ticket_id")) else "asset",
                "scope_ref": self._text(payload.get("source_ticket_id")) or self._text(payload.get("id")),
            },
            "source_confidence": 0.85,
        }

    def _matches_ticket(self, ticket: dict[str, Any], *, query: str, employee_id: str) -> bool:
        haystack = " ".join(
            self._text(ticket.get(key))
            for key in ("id", "title", "description", "status", "ticket_type", "assigned_employee_id", "assigned_role")
        ).lower()
        if employee_id and employee_id.lower() not in haystack:
            return False
        if not query:
            return True
        return any(token in haystack for token in self._tokens(query))

    def _matches_asset(self, asset: dict[str, Any], *, query: str, employee_id: str, kind: str) -> bool:
        if kind and self._text(asset.get("kind")).lower() != kind.lower():
            return False
        assigned = asset.get("assigned_employees") if isinstance(asset.get("assigned_employees"), list) else []
        if employee_id and employee_id != self._text(asset.get("source_employee_id")) and employee_id not in [self._text(item) for item in assigned]:
            return False
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        haystack = " ".join(
            [
                self._text(asset.get("id")),
                self._text(asset.get("kind")),
                self._text(asset.get("title")),
                self._text(asset.get("status")),
                self._text(asset.get("source_ticket_id")),
                " ".join(self._text(value) for value in metadata.values() if isinstance(value, str)),
            ]
        ).lower()
        if not query:
            return True
        return any(token in haystack for token in self._tokens(query))

    def _items(self, value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def _tokens(self, value: str) -> list[str]:
        return [token for token in value.lower().replace(":", " ").replace("/", " ").split() if len(token) >= 2]

    def _limit(self, value: Any, *, default: int) -> int:
        try:
            return max(1, min(int(value or default), 20))
        except (TypeError, ValueError):
            return default

    def _text(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else str(value).strip() if value is not None else ""
