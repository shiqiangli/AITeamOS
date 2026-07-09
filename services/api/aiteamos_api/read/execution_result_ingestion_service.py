"""Normalize runtime execution results back into AITeamOS governance facts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .asset_candidate_service import upsert_asset_candidate_from_memory_candidate
from .execution_approval_service import record_execution_approval_requests
from .execution_contract import ExecutionRequest, ExecutionResult
from .execution_session_store import save_execution_session
from .knowledge_service import search_knowledge_sync
from .memory_service import create_memory_candidates_from_execution_result, record_memory_recall_usage
from .repository_service import CodeRepository, list_code_repositories
from .ticket_service import (
    TicketCreateRequest,
    TicketHandoffRequest,
    TicketReportRequest,
    TicketValidationRequest,
    add_ticket_report,
    create_ticket,
    get_ticket,
    record_ticket_handoff,
    request_ticket_validation,
)


_DURABLE_CANDIDATE_KIND_TO_MEMORY_TYPE = {
    "memory_candidate": "fact",
    "decision_candidate": "decision",
    "doc_candidate": "doc",
    "skill_candidate": "skill",
    "tool_call_candidate": "tool_call",
    "capability_candidate": "capability",
    "validated_ticket_summary_candidate": "summary",
    "durable_asset_candidate": "fact",
}


class ExecutionResultIngestionService:
    def __init__(self, *, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir
        self.approval_workspace_dir = workspace_dir.parent if workspace_dir.name == ".aiteamos" else workspace_dir
        self._ingestion_path = workspace_dir / "execution_ingestions.json"
        self._artifact_path = workspace_dir / "execution_artifacts.json"

    def ingest(self, request: ExecutionRequest, result: ExecutionResult) -> ExecutionResult:
        if self._already_ingested(request.request_id):
            return self._rehydrate_already_ingested_result(request, result)
        if result.status not in {"completed", "partial", "needs_approval"}:
            self._record_execution_artifacts(request, result)
            self._record_execution_session(request, result)
            self._record(request.request_id, result.status, {"skipped": True})
            return result

        action = request.action_plan.action
        details: dict[str, Any] = {"action": action, "executor_id": result.executor_id}
        try:
            if result.approval_requests:
                result = self._ingest_approval_requests(request, result, details)
            handoff_artifact = self._employee_handoff_artifact(result)
            if handoff_artifact:
                result = self._ingest_employee_handoff(request, result, details, handoff_artifact)
            if action == "create_ticket":
                result = self._ingest_create_ticket(request, result, details)
            elif action in {"append_report", "record_validation", "record_failure"}:
                result = self._ingest_report(request, result, details)
            elif action == "request_validation":
                result = self._ingest_validation_request(request, result, details)
            elif action == "request_human_review":
                result = self._ingest_human_review_request(request, result, details)
            elif action == "inspect_code_repository":
                result = self._ingest_repository_inspection(request, result, details)
            elif self._is_repo_mutation_action(action):
                result = self._ingest_external_runtime_repo_mutation(request, result, details)
        except Exception as exc:
            result = result.model_copy(
                update={
                    "status": "blocked",
                    "errors": [*result.errors, {"reason": "ingestion_blocked", "detail": str(exc)}],
                    "report": f"{result.report}\n\nAITeamOS ingestion blocker: {exc}",
                }
            )
            details["error"] = str(exc)
        if result.status in {"completed", "partial", "needs_approval"}:
            result = self._ingest_memory_recall_usage(request, result, details)
            result = self._ingest_memory_candidates(request, result, details)
        self._record_execution_artifacts(request, result)
        self._record_execution_session(request, result)
        self._record(request.request_id, result.status, details)
        return result

    def _employee_handoff_artifact(self, result: ExecutionResult) -> dict[str, Any]:
        return next(
            (
                item
                for item in result.artifacts
                if isinstance(item, dict) and item.get("kind") == "employee_handoff_request"
            ),
            {},
        )

    def _rehydrate_already_ingested_result(self, request: ExecutionRequest, result: ExecutionResult) -> ExecutionResult:
        artifact = self._employee_handoff_artifact(result)
        if not artifact or self._has_command_event(result, "tickets.manage:handoff"):
            return result
        ticket_id = str(artifact.get("ticket_id") or result.output_ticket_id or request.ticket_id or request.ticket_binding.ticket_id)
        if not ticket_id:
            return result
        ticket = get_ticket(ticket_id)
        if ticket is None:
            return result
        report_id = self._latest_handoff_report_id(ticket)
        payload = {
            "ticket": ticket.model_dump(mode="json"),
            "handoff": artifact,
            "report_id": report_id,
            "rehydrated": True,
        }
        return result.model_copy(
            update={
                "output_ticket_id": ticket_id,
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("tickets.manage:handoff", payload),
                ],
                "learning_delta": {
                    **result.learning_delta,
                    "employee_handoff": artifact,
                    "idempotent_ingestion_rehydrated": True,
                },
            }
        )

    def _has_command_event(self, result: ExecutionResult, command_id: str) -> bool:
        for event in result.tool_events:
            data = event.get("data") if isinstance(event, dict) else {}
            command = data.get("command") if isinstance(data, dict) else {}
            if isinstance(command, dict) and command.get("id") == command_id:
                return True
        return False

    def _latest_handoff_report_id(self, ticket: Any) -> str:
        for report in reversed(getattr(ticket, "reports", []) or []):
            if getattr(report, "report_type", "") == "employee_handoff":
                return str(getattr(report, "id", "") or "")
        return ""

    def _record_execution_session(self, request: ExecutionRequest, result: ExecutionResult) -> None:
        run_id = str(request.trace_context.get("run_id") or request.request_id)
        save_execution_session(
            self.workspace_dir,
            employee_id=request.employee_id,
            thread_id=str(request.trace_context.get("thread_id") or "runtime"),
            ticket_id=result.output_ticket_id or request.ticket_id or request.ticket_binding.ticket_id,
            executor_id=result.executor_id,
            executor_session_ref=result.executor_session_ref,
            checkpoint_ref=result.checkpoint_ref,
            last_request_id=request.request_id,
            updated_at=result.finished_at or result.started_at,
            status=result.status,
            trace_ref=result.trace_ref or str(request.trace_context.get("trace_ref") or ""),
            current_graph_node=self._session_current_graph_node(result),
            source_state_ref=self._session_source_state_ref(result),
            tool_event_count=len(result.tool_events),
            tool_events=self._session_tool_events(result),
            ticket_refs=self._session_ticket_refs(request, result),
            memory_refs=self._session_memory_refs(request, result),
            context_refs=self._session_context_refs(request, result),
            approval_refs=self._session_approval_refs(request, result),
        )

    def _session_current_graph_node(self, result: ExecutionResult) -> str:
        interrupt = result.learning_delta.get("approval_interrupt") if isinstance(result.learning_delta, dict) else {}
        if isinstance(interrupt, dict) and interrupt.get("current_graph_node"):
            return str(interrupt.get("current_graph_node") or "")
        for approval in result.approval_requests:
            if isinstance(approval, dict) and approval.get("current_graph_node"):
                return str(approval.get("current_graph_node") or "")
        return str(result.learning_delta.get("current_graph_node") or "") if isinstance(result.learning_delta, dict) else ""

    def _session_source_state_ref(self, result: ExecutionResult) -> str:
        interrupt = result.learning_delta.get("approval_interrupt") if isinstance(result.learning_delta, dict) else {}
        if isinstance(interrupt, dict) and interrupt.get("source_state_ref"):
            return str(interrupt.get("source_state_ref") or "")
        for approval in result.approval_requests:
            if isinstance(approval, dict) and approval.get("source_state_ref"):
                return str(approval.get("source_state_ref") or "")
        return str(result.learning_delta.get("source_state_ref") or "") if isinstance(result.learning_delta, dict) else ""

    def _session_tool_events(self, result: ExecutionResult) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for index, event in enumerate(result.tool_events[:20]):
            if not isinstance(event, dict):
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            command = data.get("command") if isinstance(data.get("command"), dict) else {}
            events.append(
                {
                    "index": index,
                    "event": str(event.get("event") or ""),
                    "detail": str(event.get("detail") or event.get("summary") or ""),
                    "tool_name": str(data.get("tool_name") or command.get("id") or ""),
                    "output_refs": data.get("output_refs") if isinstance(data.get("output_refs"), list) else [],
                    "provenance": data.get("provenance") if isinstance(data.get("provenance"), list) else [],
                    "errors": data.get("errors") if isinstance(data.get("errors"), list) else [],
                }
            )
        return events

    def _session_ticket_refs(self, request: ExecutionRequest, result: ExecutionResult) -> list[str]:
        refs = [
            result.output_ticket_id,
            request.ticket_id,
            request.ticket_binding.ticket_id,
        ]
        ticket = request.task_context.get("ticket") if isinstance(request.task_context.get("ticket"), dict) else {}
        refs.append(str(ticket.get("id") or ""))
        for event in result.tool_events:
            data = event.get("data") if isinstance(event, dict) and isinstance(event.get("data"), dict) else {}
            for item in data.get("output_refs") or []:
                if isinstance(item, dict) and item.get("kind") == "ticket":
                    refs.append(str(item.get("ref") or ""))
        return [ref for ref in refs if ref]

    def _session_memory_refs(self, request: ExecutionRequest, result: ExecutionResult) -> list[str]:
        refs: list[str] = []
        for item in request.task_context.get("recalled_memories", []):
            if isinstance(item, dict):
                refs.append(str(item.get("memory_id") or item.get("asset_id") or ""))
        for item in result.memory_candidates:
            if isinstance(item, dict):
                refs.append(str(item.get("id") or item.get("memory_id") or ""))
        for event in result.tool_events:
            data = event.get("data") if isinstance(event, dict) and isinstance(event.get("data"), dict) else {}
            for item in data.get("output_refs") or []:
                if isinstance(item, dict) and item.get("kind") == "memory":
                    refs.append(str(item.get("ref") or ""))
        return [ref for ref in refs if ref]

    def _session_context_refs(self, request: ExecutionRequest, result: ExecutionResult) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        universal_context = request.task_context.get("universal_context") if isinstance(request.task_context.get("universal_context"), dict) else {}
        provenance = universal_context.get("provenance_summary") if isinstance(universal_context.get("provenance_summary"), list) else []
        refs.extend(item for item in provenance if isinstance(item, dict))
        for event in result.tool_events:
            data = event.get("data") if isinstance(event, dict) and isinstance(event.get("data"), dict) else {}
            tool_provenance = data.get("provenance") if isinstance(data.get("provenance"), list) else []
            refs.extend(item for item in tool_provenance if isinstance(item, dict))
        return refs[:20]

    def _session_approval_refs(self, request: ExecutionRequest, result: ExecutionResult) -> list[str]:
        refs = [str(item) for item in request.approval_policy.get("approval_refs", []) if str(item).strip()] if isinstance(request.approval_policy.get("approval_refs"), list) else []
        learning_delta = result.learning_delta if isinstance(result.learning_delta, dict) else {}
        records = learning_delta.get("approval_records") if isinstance(learning_delta.get("approval_records"), list) else []
        for item in records:
            if isinstance(item, dict):
                refs.append(str(item.get("id") or ""))
        return [ref for ref in refs if ref]

    def _ingest_approval_requests(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        records = record_execution_approval_requests(workspace_dir=self.approval_workspace_dir, request=request, result=result)
        if not records:
            return result
        payload = [record.model_dump(mode="json") for record in records]
        details["approval_record_ids"] = [record.id for record in records]
        return result.model_copy(
            update={
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("runtime.approvals:record", {"approvals": payload}),
                ],
                "learning_delta": {
                    **result.learning_delta,
                    "approval_records": payload,
                },
            }
        )

    def _ingest_employee_handoff(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        details: dict[str, Any],
        artifact: dict[str, Any],
    ) -> ExecutionResult:
        ticket_id = str(artifact.get("ticket_id") or request.ticket_id or request.ticket_binding.ticket_id)
        updated = record_ticket_handoff(
            ticket_id,
            TicketHandoffRequest(
                to_employee_id=str(artifact.get("to_employee_id") or ""),
                to_role=str(artifact.get("to_role") or ""),
                from_employee_id=str(artifact.get("from_employee_id") or request.employee_id),
                from_role=str(artifact.get("from_role") or self._employee_role(request)),
                content=str(artifact.get("content") or result.report),
                actor_employee_id=request.employee_id,
                actor_role=self._employee_role(request),
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        report = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                reporter_role=self._employee_role(request),
                content=(
                    f"Employee handoff requested: {artifact.get('from_employee_id') or request.employee_id} "
                    f"-> {artifact.get('to_employee_id') or artifact.get('to_role') or 'target Employee'}.\n\n"
                    f"{artifact.get('content') or result.report}"
                ),
                evidence=[str(result.trace_ref or request.trace_context.get("trace_ref") or "")],
                report_type="employee_handoff",
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        payload = {
            "ticket": updated.model_dump(mode="json"),
            "handoff": artifact,
            "report_id": report.reports[-1].id if report.reports else "",
        }
        details["handoff_ticket_id"] = ticket_id
        details["handoff_to_employee_id"] = str(artifact.get("to_employee_id") or "")
        return result.model_copy(
            update={
                "output_ticket_id": ticket_id,
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("tickets.manage:handoff", payload),
                ],
                "learning_delta": {
                    **result.learning_delta,
                    "employee_handoff": artifact,
                },
            }
        )

    def _ingest_create_ticket(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        artifact = next((item for item in result.artifacts if item.get("kind") == "ticket_create_request"), {})
        arguments = request.action_plan.arguments
        item = create_ticket(
            TicketCreateRequest(
                title=str(artifact.get("title") or arguments.get("title") or request.task_context.get("task_summary") or "New Ticket"),
                description=str(artifact.get("description") or arguments.get("description") or request.task_context.get("task_summary") or ""),
                ticket_type=str(artifact.get("ticket_type") or arguments.get("ticket_type") or ""),
                assigned_employee_id=str(artifact.get("assigned_employee_id") or arguments.get("assigned_employee_id") or request.employee_id),
                assigned_role=self._assigned_role(request, artifact),
                validation_employee_id=str(artifact.get("validation_employee_id") or arguments.get("validation_employee_id") or ""),
                validation_role=str(artifact.get("validation_role") or arguments.get("validation_role") or ""),
                knowledge_refs=self._knowledge_refs(request, artifact),
                code_repository_ids=self._code_repository_ids(request, artifact),
                source_thread_id=str(request.trace_context.get("thread_id") or ""),
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
                actor_employee_id="clara",
                actor_role="AI Team OS Manager",
            )
        )
        details["output_ticket_id"] = item.id
        report = f"已创建 Ticket {item.id}: {item.title}"
        if item.external_url:
            report += f"\n- Provider: {item.external_url}"
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": report,
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("tickets.manage:create", {"ticket": item.model_dump(mode="json")}),
                ],
            }
        )

    def _assigned_role(self, request: ExecutionRequest, artifact: dict[str, Any]) -> str:
        arguments = request.action_plan.arguments
        explicit = str(artifact.get("assigned_role") or arguments.get("assigned_role") or "").strip()
        if explicit:
            return explicit
        assigned_employee_id = str(artifact.get("assigned_employee_id") or arguments.get("assigned_employee_id") or request.employee_id).strip()
        for profile in request.task_context.get("employee_profiles") or []:
            if isinstance(profile, dict) and str(profile.get("id") or "").strip() == assigned_employee_id:
                return str(profile.get("role") or "").strip()
        if assigned_employee_id == "alex":
            return "AI RD / Implementer"
        if assigned_employee_id == "peter":
            return "AI PV"
        return ""

    def _knowledge_refs(self, request: ExecutionRequest, artifact: dict[str, Any]) -> list[str]:
        arguments = request.action_plan.arguments
        explicit = self._string_list(artifact.get("knowledge_refs")) or self._string_list(arguments.get("knowledge_refs"))
        if explicit:
            return sorted(set(explicit))
        query = str(arguments.get("description") or arguments.get("message") or request.task_context.get("task_summary") or "").strip()
        if not query:
            return []
        response = search_knowledge_sync(query, limit=5)
        return [f"{item.source_type}:{item.id}" for item in response.results]

    def _code_repository_ids(self, request: ExecutionRequest, artifact: dict[str, Any]) -> list[str]:
        arguments = request.action_plan.arguments
        explicit = (
            self._string_list(artifact.get("code_repository_ids"))
            or self._string_list(arguments.get("code_repository_ids"))
            or self._string_list(arguments.get("repository_ids"))
            or self._string_list(arguments.get("repo_ids"))
        )
        if explicit:
            return sorted(set(explicit))
        message = str(arguments.get("description") or arguments.get("message") or request.task_context.get("task_summary") or "")
        repositories = list_code_repositories()
        enabled = [repository for repository in repositories if repository.enabled]
        matched: list[str] = []

        def add(repository: CodeRepository | None) -> None:
            if repository is not None and repository.id not in matched:
                matched.append(repository.id)

        for key in ("code_repository_id", "repository_id", "repo_id", "code_repository_name", "repository_name", "repo_name"):
            add(self._match_repository(str(arguments.get(key) or ""), repositories))
        lowered = message.lower()
        for repository in enabled:
            if repository.id.lower() in lowered or repository.name.lower() in lowered:
                add(repository)
        for repository in enabled:
            if repository.id not in matched and repository.location and repository.location.lower() in lowered:
                add(repository)
        if not matched and self._message_mentions_repo_context(message) and len(enabled) == 1:
            add(enabled[0])
        return matched

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in re.split(r"[,，\s]+", value) if item.strip()]
        return []

    def _match_repository(self, value: str, repositories: list[CodeRepository]) -> CodeRepository | None:
        lookup = value.strip().lower()
        if not lookup:
            return None
        for repository in repositories:
            if lookup in {repository.id.lower(), repository.name.lower()}:
                return repository
        for repository in repositories:
            if lookup in repository.location.lower() or lookup in repository.name.lower():
                return repository
        return None

    def _message_mentions_repo_context(self, message: str) -> bool:
        lower = message.strip().lower()
        compact = re.sub(r"\s+", "", lower)
        if any(token in compact for token in ("代码仓库", "代码库", "仓库")):
            return True
        return bool(re.search(r"\b(repos?|repositories|repository|codebase)\b", lower))

    def _ingest_report(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        artifact = next(
            (
                item
                for item in result.artifacts
                if isinstance(item, dict) and item.get("kind") == "ticket_report_request"
            ),
            {},
        )
        ticket_id = str(artifact.get("ticket_id") or request.ticket_id or request.ticket_binding.ticket_id)
        artifact_evidence = artifact.get("evidence_refs") if isinstance(artifact.get("evidence_refs"), list) else []
        evidence = [
            str(item).strip()
            for item in artifact_evidence
            if str(item).strip()
        ] or [
            str(item.get("ref") or item.get("evidence_ref") or item.get("summary") or item.get("kind"))
            for item in result.evidence
            if isinstance(item, dict)
        ]
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=str(artifact.get("reporter_employee_id") or request.employee_id),
                reporter_role=str(artifact.get("reporter_role") or self._employee_role(request)),
                content=str(artifact.get("content") or result.report),
                evidence=[entry for entry in evidence if entry],
                report_type=str(artifact.get("report_type") or self._report_type(request)),
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("tickets.manage:report", {"ticket": item.model_dump(mode="json")}),
                ],
            }
        )

    def _report_type(self, request: ExecutionRequest) -> str:
        if request.action_plan.action == "record_validation":
            return "validation"
        if request.action_plan.action == "record_failure":
            return "validation_failed"
        return str(request.action_plan.arguments.get("report_type") or "progress")

    def _ingest_validation_request(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        artifact = next(
            (
                item
                for item in result.artifacts
                if isinstance(item, dict) and item.get("kind") == "validation_request"
            ),
            {},
        )
        ticket_id = str(artifact.get("ticket_id") or request.ticket_id or request.ticket_binding.ticket_id)
        arguments = request.action_plan.arguments
        item = request_ticket_validation(
            ticket_id,
            TicketValidationRequest(
                validation_employee_id=str(artifact.get("validation_employee_id") or arguments.get("validation_employee_id") or ""),
                validation_role=str(artifact.get("validation_role") or arguments.get("validation_role") or "PV Validation"),
                content=str(artifact.get("content") or result.report),
                actor_employee_id=str(artifact.get("actor_employee_id") or request.employee_id),
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        validator = item.validation_employee_id or item.validation_role or "PV"
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": f"已请求 Ticket 验证: {item.id} -> {validator}",
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("tickets.manage:request_validation", {"ticket": item.model_dump(mode="json")}),
                ],
            }
        )

    def _ingest_human_review_request(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        ticket_id = request.ticket_id or request.ticket_binding.ticket_id
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                content=str(request.action_plan.arguments.get("content") or result.report),
                evidence=[],
                report_type="human_review_requested",
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": f"已请求 Human Review: {item.id}",
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("tickets.manage:request_human_review", {"ticket": item.model_dump(mode="json")}),
                ],
            }
        )

    def _ingest_repository_inspection(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        handoff_artifact = next(
            (
                item
                for item in result.artifacts
                if isinstance(item, dict) and item.get("kind") == "external_runtime_inspect_handoff"
            ),
            {},
        )
        if handoff_artifact:
            return self._ingest_external_runtime_handoff(request, result, details, handoff_artifact)
        cli_artifact = next(
            (
                item
                for item in result.artifacts
                if isinstance(item, dict) and item.get("kind") == "external_runtime_cli_execution"
            ),
            {},
        )
        if cli_artifact:
            return self._ingest_external_runtime_cli_report(request, result, details, cli_artifact)
        http_artifact = next(
            (
                item
                for item in result.artifacts
                if isinstance(item, dict) and item.get("kind") == "external_runtime_http_execution"
            ),
            {},
        )
        if http_artifact:
            return self._ingest_external_runtime_http_report(request, result, details, http_artifact)

        ticket_id = request.ticket_id or request.ticket_binding.ticket_id
        artifact = next((item for item in result.artifacts if isinstance(item, dict) and item.get("kind") == "repository_inspection"), {})
        repository = artifact.get("repository") if isinstance(artifact.get("repository"), dict) else {}
        evidence_refs = [
            str(item.get("ref") or item.get("evidence_ref") or "").strip()
            for item in result.evidence
            if isinstance(item, dict) and str(item.get("ref") or item.get("evidence_ref") or "").strip()
        ]
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                reporter_role=self._employee_role(request),
                content=self._inspection_report_content(artifact),
                evidence=evidence_refs,
                report_type="repo_inspection",
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        payload = {
            "ticket": item.model_dump(mode="json"),
            "repository": repository,
            "query": artifact.get("query") or "",
            "matches": artifact.get("matches") or [],
            "files": artifact.get("files") or [],
            "status": "completed",
            "detail": "Repository inspection report was written to the Ticket ledger.",
        }
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": f"{result.report}\n\n已写回 Ticket report: {item.id}",
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("repositories.inspect:inspect", payload),
                ],
            }
        )

    def _ingest_external_runtime_handoff(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        details: dict[str, Any],
        artifact: dict[str, Any],
    ) -> ExecutionResult:
        ticket_id = request.ticket_id or request.ticket_binding.ticket_id
        evidence_refs = [
            str(item.get("ref") or item.get("evidence_ref") or "").strip()
            for item in result.evidence
            if isinstance(item, dict) and str(item.get("ref") or item.get("evidence_ref") or "").strip()
        ]
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                reporter_role=self._employee_role(request),
                content=self._external_runtime_handoff_report_content(artifact),
                evidence=evidence_refs,
                report_type="external_runtime_handoff",
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        payload = {
            "ticket": item.model_dump(mode="json"),
            "executor_id": artifact.get("executor_id") or result.executor_id,
            "external_execution_status": artifact.get("external_execution_status") or "not_started",
            "status": "partial",
            "detail": "External runtime handoff was recorded without claiming external execution completion.",
        }
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": f"{result.report}\n\n已写回 external runtime handoff report: {item.id}",
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("runtime.external:inspect_handoff", payload),
                ],
            }
        )

    def _ingest_external_runtime_cli_report(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        details: dict[str, Any],
        artifact: dict[str, Any],
    ) -> ExecutionResult:
        ticket_id = request.ticket_id or request.ticket_binding.ticket_id
        evidence_refs = [
            str(item.get("ref") or item.get("evidence_ref") or "").strip()
            for item in result.evidence
            if isinstance(item, dict) and str(item.get("ref") or item.get("evidence_ref") or "").strip()
        ]
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                reporter_role=self._employee_role(request),
                content=self._external_runtime_cli_report_content(result, artifact),
                evidence=evidence_refs,
                report_type="external_runtime_report",
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        payload = {
            "ticket": item.model_dump(mode="json"),
            "executor_id": artifact.get("executor_id") or result.executor_id,
            "mode": artifact.get("mode") or "",
            "status": result.status,
            "detail": "External runtime CLI inspect-and-report output was written to the Ticket ledger.",
        }
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": f"{result.report}\n\n已写回 external runtime report: {item.id}",
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("runtime.external:cli_report", payload),
                ],
            }
        )

    def _ingest_external_runtime_http_report(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        details: dict[str, Any],
        artifact: dict[str, Any],
    ) -> ExecutionResult:
        ticket_id = request.ticket_id or request.ticket_binding.ticket_id
        evidence_refs = [
            str(item.get("ref") or item.get("evidence_ref") or "").strip()
            for item in result.evidence
            if isinstance(item, dict) and str(item.get("ref") or item.get("evidence_ref") or "").strip()
        ]
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                reporter_role=self._employee_role(request),
                content=self._external_runtime_http_report_content(result, artifact),
                evidence=evidence_refs,
                report_type="external_runtime_report",
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        payload = {
            "ticket": item.model_dump(mode="json"),
            "executor_id": artifact.get("executor_id") or result.executor_id,
            "mode": artifact.get("mode") or "",
            "status": result.status,
            "detail": "External runtime HTTP inspect-and-report output was written to the Ticket ledger.",
        }
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": f"{result.report}\n\n已写回 external runtime report: {item.id}",
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("runtime.external:http_report", payload),
                ],
            }
        )

    def _ingest_external_runtime_repo_mutation(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        details: dict[str, Any],
    ) -> ExecutionResult:
        artifact = next(
            (
                item
                for item in result.artifacts
                if isinstance(item, dict)
                and item.get("kind") in {"external_runtime_cli_execution", "external_runtime_http_execution"}
                and item.get("repo_mutation") is True
            ),
            {},
        )
        if not artifact:
            return result
        blocker = self._external_runtime_repo_mutation_ingestion_blocker(result)
        if blocker:
            reason, detail = blocker
            return result.model_copy(
                update={
                    "status": "blocked",
                    "report": f"{result.report}\n\nAITeamOS ingestion blocker: {detail}",
                    "errors": [
                        *result.errors,
                        {"reason": reason, "detail": detail},
                    ],
                }
            )
        ticket_id = request.ticket_id or request.ticket_binding.ticket_id
        evidence_refs = [
            str(item.get("ref") or item.get("evidence_ref") or item.get("summary") or "").strip()
            for item in result.evidence
            if isinstance(item, dict) and str(item.get("ref") or item.get("evidence_ref") or item.get("summary") or "").strip()
        ]
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                reporter_role=self._employee_role(request),
                content=self._external_runtime_repo_mutation_report_content(result, artifact),
                evidence=evidence_refs,
                report_type="external_runtime_repo_mutation",
                source_run_id=str(request.trace_context.get("run_id") or request.request_id),
            ),
        )
        details["output_ticket_id"] = item.id
        details["repo_mutation_artifact_count"] = len(result.artifacts)
        payload = {
            "ticket": item.model_dump(mode="json"),
            "executor_id": artifact.get("executor_id") or result.executor_id,
            "mode": artifact.get("mode") or "",
            "status": result.status,
            "artifacts": result.artifacts,
            "evidence": result.evidence,
            "detail": "Approved external runtime repo mutation output was written to the Ticket ledger.",
        }
        return result.model_copy(
            update={
                "output_ticket_id": item.id,
                "report": f"{result.report}\n\n已写回 approved external runtime repo mutation report: {item.id}",
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("runtime.external:repo_mutation", payload),
                ],
            }
        )

    def _external_runtime_repo_mutation_ingestion_blocker(self, result: ExecutionResult) -> tuple[str, str] | None:
        if not self._has_patch_or_changed_files(result.artifacts):
            return (
                "repo_mutation_patch_required",
                "Approved external runtime repo mutation must include patch, diff, diff_ref, or changed_files artifact before Ticket ledger ingestion.",
            )
        if not self._has_runtime_test_or_validation_evidence(result.evidence):
            return (
                "repo_mutation_test_evidence_required",
                "Approved external runtime repo mutation must include runtime test evidence or validation evidence before Ticket ledger ingestion.",
            )
        return None

    def _has_patch_or_changed_files(self, artifacts: list[dict[str, Any]]) -> bool:
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("kind") in {"repo_patch", "code_patch", "patch", "changed_files"}:
                return True
            if artifact.get("patch") or artifact.get("diff") or artifact.get("diff_ref"):
                return True
            changed_files = artifact.get("changed_files")
            if isinstance(changed_files, list) and any(str(item).strip() for item in changed_files):
                return True
        return False

    def _has_runtime_test_or_validation_evidence(self, evidence_items: list[dict[str, Any]]) -> bool:
        for evidence in evidence_items:
            if not isinstance(evidence, dict):
                continue
            kind = str(evidence.get("kind") or "").lower()
            ref = str(evidence.get("ref") or evidence.get("evidence_ref") or "").lower()
            summary = str(evidence.get("summary") or "").lower()
            evidence_text = f"{kind} {ref} {summary}"
            if "test" in evidence_text or "validation" in evidence_text:
                return True
        return False

    def _external_runtime_repo_mutation_report_content(self, result: ExecutionResult, artifact: dict[str, Any]) -> str:
        executor_id = str(artifact.get("executor_id") or result.executor_id)
        mode = str(artifact.get("mode") or "")
        changed_files = self._changed_files_from_artifacts(result.artifacts)
        approval_refs = [str(item).strip() for item in artifact.get("approval_refs", []) if str(item).strip()] if isinstance(artifact.get("approval_refs"), list) else []
        trace_ref = str(artifact.get("trace_ref") or result.trace_ref or "").strip()
        lines = [
            f"Approved external runtime repo mutation from {executor_id}.",
            f"Mode: {mode or 'unspecified'}.",
            "Repo mutation was Ticket-bound, approval-bound, and evidence-bound.",
        ]
        if approval_refs:
            lines.append(f"Approval refs: {', '.join(approval_refs)}.")
        if trace_ref:
            lines.append(f"Trace ref: {trace_ref}.")
        lines.extend(["", result.report])
        if changed_files:
            lines.extend(["", "Changed files:"])
            lines.extend(f"- {path}" for path in changed_files[:20])
        return "\n".join(lines)

    def _changed_files_from_artifacts(self, artifacts: list[dict[str, Any]]) -> list[str]:
        files: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            changed_files = artifact.get("changed_files")
            if isinstance(changed_files, list):
                files.extend(str(path).strip() for path in changed_files if str(path).strip())
            changed_file = str(artifact.get("changed_file") or artifact.get("path") or "").strip()
            if changed_file:
                files.append(changed_file)
        return sorted(dict.fromkeys(files))

    def _is_repo_mutation_action(self, action: str) -> bool:
        return bool(re.search(r"repo[_:-]?write|code[_:-]?(change|edit|mutation)|apply[_:-]?patch|implement|modify|delete", action, re.IGNORECASE))

    def _external_runtime_cli_report_content(self, result: ExecutionResult, artifact: dict[str, Any]) -> str:
        executor_id = str(artifact.get("executor_id") or result.executor_id)
        mode = str(artifact.get("mode") or "")
        lines = [
            f"External runtime CLI report from {executor_id}.",
            f"Mode: {mode or 'unspecified'}.",
            "Repo mutation was not executed by AITeamOS; governance approval remains authoritative.",
            "",
            result.report,
        ]
        stderr_summary = str(artifact.get("stderr_summary") or "").strip()
        if stderr_summary:
            lines.extend(["", f"Runtime stderr summary: {stderr_summary}"])
        return "\n".join(lines)

    def _external_runtime_http_report_content(self, result: ExecutionResult, artifact: dict[str, Any]) -> str:
        executor_id = str(artifact.get("executor_id") or result.executor_id)
        mode = str(artifact.get("mode") or "")
        endpoint_path = str(artifact.get("http_endpoint_path") or "")
        lines = [
            f"External runtime HTTP report from {executor_id}.",
            f"Mode: {mode or 'unspecified'}.",
            f"HTTP endpoint: {endpoint_path or 'unspecified'}.",
            "Repo mutation was not executed by AITeamOS; governance approval remains authoritative.",
            "",
            result.report,
        ]
        return "\n".join(lines)

    def _external_runtime_handoff_report_content(self, artifact: dict[str, Any]) -> str:
        executor_id = str(artifact.get("executor_id") or "")
        task_summary = str(artifact.get("task_summary") or "")
        status = str(artifact.get("external_execution_status") or "not_started")
        lines = [
            f"External runtime inspect-and-report handoff prepared for {executor_id}.",
            f"External execution status: {status}.",
            "No repo mutation was executed by AITeamOS.",
        ]
        if task_summary:
            lines.extend(["", f"Task: {task_summary}"])
        return "\n".join(lines)

    def _employee_role(self, request: ExecutionRequest) -> str:
        employee = request.task_context.get("employee") if isinstance(request.task_context.get("employee"), dict) else {}
        return str(employee.get("role") or "").strip()

    def _inspection_report_content(self, artifact: dict[str, Any]) -> str:
        repository = artifact.get("repository") if isinstance(artifact.get("repository"), dict) else {}
        repository_id = str(repository.get("id") or "")
        query = str(artifact.get("query") or "")
        matches = artifact.get("matches") if isinstance(artifact.get("matches"), list) else []
        files = artifact.get("files") if isinstance(artifact.get("files"), list) else []
        lines = [
            f"Repository inspection completed for {repository_id}.",
            f"Query: {query}",
            "",
            "Evidence:",
        ]
        if matches:
            for match in matches[:8]:
                lines.append(f"- {match.get('path')}:{match.get('line')} {match.get('excerpt')}")
        if files:
            for file in files[:3]:
                lines.append(f"- Read file: {file.get('path')}")
        if not matches and not files:
            lines.append("- No matching text files found.")
        return "\n".join(lines)

    def _ingest_memory_recall_usage(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        memory_refs = [
            item
            for item in request.task_context.get("recalled_memories", [])
            if isinstance(item, dict)
        ]
        if not memory_refs:
            return result
        ticket_id = result.output_ticket_id or request.ticket_id or request.ticket_binding.ticket_id
        if not ticket_id:
            return result
        run_id = str(request.trace_context.get("run_id") or request.request_id)
        usage_refs = record_memory_recall_usage(
            memory_refs=memory_refs,
            run_id=run_id,
            employee_id=request.employee_id,
            ticket_keys=[ticket_id],
            query=str(request.task_context.get("task_summary") or request.trace_context.get("source_message") or ""),
            trace_path=result.trace_ref or str(request.trace_context.get("trace_ref") or ""),
        )
        if not usage_refs:
            return result
        details["memory_recall_usage_ids"] = [item["usage_id"] for item in usage_refs]
        return result.model_copy(
            update={
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("memory.recall:record_usage", {"memory_recall_usages": usage_refs}),
                ],
                "learning_delta": {
                    **result.learning_delta,
                    "memory_recall_usage_refs": usage_refs,
                },
            }
        )

    def _ingest_memory_candidates(self, request: ExecutionRequest, result: ExecutionResult, details: dict[str, Any]) -> ExecutionResult:
        normalized_candidates = [
            *result.memory_candidates,
            *self._durable_asset_candidates_from_result(request, result),
        ]
        if not normalized_candidates:
            return result
        ticket_id = result.output_ticket_id or request.ticket_id or request.ticket_binding.ticket_id
        source_report_id, evidence_id = self._latest_report_and_evidence_refs(result)
        created = create_memory_candidates_from_execution_result(
            memory_candidates=normalized_candidates,
            request_id=request.request_id,
            run_id=str(request.trace_context.get("run_id") or request.request_id),
            thread_id=str(request.trace_context.get("thread_id") or ""),
            ticket_id=ticket_id,
            employee_id=request.employee_id,
            action=request.action_plan.action,
            executor_id=result.executor_id,
            trace_ref=result.trace_ref or str(request.trace_context.get("trace_ref") or ""),
            provider_refs=self._provider_refs_from_result(result),
            source_report_id=source_report_id,
            evidence_id=evidence_id,
        )
        if not created:
            return result
        created_payload = [candidate.model_dump(mode="json") for candidate in created]
        asset_candidates = [upsert_asset_candidate_from_memory_candidate(candidate) for candidate in created]
        asset_candidate_payload = [candidate.model_dump(mode="json") for candidate in asset_candidates]
        details["memory_candidate_ids"] = [candidate.id for candidate in created]
        details["asset_candidate_ids"] = [candidate.id for candidate in asset_candidates]
        return result.model_copy(
            update={
                "memory_candidates": [
                    *result.memory_candidates,
                    *[
                        {
                            "id": candidate.id,
                            "status": candidate.status,
                            "content": candidate.content,
                            "source_kind": candidate.source_kind,
                            "source_ref": candidate.source_ref,
                            "scope_kind": candidate.scope_kind,
                            "scope_ref": candidate.scope_ref,
                            "provenance": candidate.provenance,
                        }
                        for candidate in created
                    ],
                ],
                "tool_events": [
                    *result.tool_events,
                    self._command_completed("memory.candidates:propose", {"memory_candidates": created_payload}),
                    self._command_completed("asset.candidates:propose", {"asset_candidates": asset_candidate_payload}),
                ],
                "learning_delta": {
                    **result.learning_delta,
                    "asset_candidates": asset_candidate_payload,
                },
            }
        )

    def _durable_asset_candidates_from_result(self, request: ExecutionRequest, result: ExecutionResult) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for index, artifact in enumerate(result.artifacts):
            if not isinstance(artifact, dict):
                continue
            normalized = self._durable_candidate_from_item(
                artifact,
                request=request,
                result=result,
                source=f"artifact:{index}",
            )
            if normalized:
                candidates.append(normalized)
        learning_delta = result.learning_delta if isinstance(result.learning_delta, dict) else {}
        for key in (
            "durable_asset_candidates",
            "decision_candidates",
            "doc_candidates",
            "skill_candidates",
            "tool_call_candidates",
            "capability_candidates",
            "validated_ticket_summary_candidates",
        ):
            items = learning_delta.get(key)
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                normalized = self._durable_candidate_from_item(
                    {**item, "kind": item.get("kind") or self._kind_from_learning_delta_key(key)},
                    request=request,
                    result=result,
                    source=f"learning_delta:{key}:{index}",
                )
                if normalized:
                    candidates.append(normalized)
        candidates.extend(self._tool_call_candidates_from_result(request, result))
        return candidates

    def _tool_call_candidates_from_result(self, request: ExecutionRequest, result: ExecutionResult) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        ticket_id = result.output_ticket_id or request.ticket_id or request.ticket_binding.ticket_id
        run_id = str(request.trace_context.get("run_id") or request.request_id)
        for index, event in enumerate(result.tool_events):
            if not isinstance(event, dict) or self._is_ingestion_tool_event(event):
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            command = data.get("command") if isinstance(data.get("command"), dict) else {}
            command_id = self._first_string(
                command.get("id") if isinstance(command, dict) else "",
                data.get("tool_name"),
                event.get("tool_name"),
                event.get("event"),
            )
            event_name = self._first_string(event.get("event"))
            if not command_id:
                continue
            if not command and not any(token in event_name.lower() for token in ("command", "tool")):
                continue
            if not self._tool_event_should_be_asset(event):
                continue
            public_event = self._public_tool_event(event)
            content = self._compact_text(
                "\n".join(
                    [
                        f"Tool call: {command_id}",
                        f"Event: {event_name or '-'}",
                        f"Status: {self._first_string(data.get('status'), event.get('status'), result.status)}",
                        f"Ticket: {ticket_id or '-'}",
                        "Payload:",
                        json.dumps(public_event, ensure_ascii=False, sort_keys=True),
                    ]
                ),
                1800,
            )
            candidates.append(
                {
                    "kind": "tool_call_candidate",
                    "asset_type": "tool_call",
                    "memory_type": "tool_call",
                    "title": f"Tool call {command_id}",
                    "content": content,
                    "source_kind": "execution_tool_event",
                    "source_ref": f"{result.trace_ref or request.trace_context.get('trace_ref') or run_id}#tool-event-{index}",
                    "scope_kind": "ticket" if ticket_id else "employee",
                    "scope_ref": ticket_id or request.employee_id,
                    "confidence": 0.8,
                    "employee_ids": [request.employee_id],
                    "tags": ["tool-call", result.executor_id, command_id.split(":", 1)[0]],
                    "future_recall_query_hints": [command_id, event_name, ticket_id, request.action_plan.action],
                    "relationships": [{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket_id}] if ticket_id else [],
                    "provenance": {
                        "asset_type": "tool_call",
                        "title": f"Tool call {command_id}",
                        "source_ticket_id": ticket_id,
                        "source_employee_id": request.employee_id,
                        "source_run_id": run_id,
                        "source_trace_path": result.trace_ref or str(request.trace_context.get("trace_ref") or ""),
                        "tool_event_index": index,
                        "tool_event_name": event_name,
                        "command_id": command_id,
                        "executor_id": result.executor_id,
                        "relationships": [{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket_id}] if ticket_id else [],
                    },
                }
            )
        return candidates

    def _tool_event_should_be_asset(self, event: dict[str, Any]) -> bool:
        if event.get("record_as_asset") is True:
            return True
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        command = data.get("command") if isinstance(data.get("command"), dict) else {}
        return data.get("record_as_asset") is True or command.get("record_as_asset") is True

    def _is_ingestion_tool_event(self, event: dict[str, Any]) -> bool:
        detail = str(event.get("detail") or "")
        if "through result ingestion" in detail:
            return True
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        command = data.get("command") if isinstance(data.get("command"), dict) else {}
        command_id = str(command.get("id") or "")
        return command_id in {"memory.candidates:propose", "asset.candidates:propose", "memory.recall:record_usage"}

    def _public_tool_event(self, value: Any) -> Any:
        if isinstance(value, dict):
            public: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if any(token in key_text.lower() for token in ("secret", "token", "password", "api_key", "apikey", "authorization")):
                    public[key_text] = "[redacted]"
                else:
                    public[key_text] = self._public_tool_event(item)
            return public
        if isinstance(value, list):
            return [self._public_tool_event(item) for item in value[:20]]
        if isinstance(value, str):
            return self._compact_text(value, 500)
        return value

    def _compact_text(self, value: str, limit: int = 1200) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 1].rstrip()}..."

    def _durable_candidate_from_item(
        self,
        item: dict[str, Any],
        *,
        request: ExecutionRequest,
        result: ExecutionResult,
        source: str,
    ) -> dict[str, Any] | None:
        raw_kind = str(item.get("kind") or item.get("candidate_kind") or item.get("asset_type") or "").strip()
        candidate_kind = self._normalize_candidate_kind(raw_kind)
        if not candidate_kind:
            return None
        content = self._first_string(item.get("content"), item.get("summary"), item.get("text"), item.get("memory"))
        if not content:
            return None
        title = self._first_string(item.get("title"), item.get("name"))
        asset_type = self._first_string(item.get("asset_type"), candidate_kind.replace("_candidate", ""))
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        ticket_id = result.output_ticket_id or request.ticket_id or request.ticket_binding.ticket_id
        scope_kind = self._first_string(item.get("scope_kind"), scope.get("kind"), "ticket" if ticket_id else "employee")
        scope_ref = self._first_string(item.get("scope_ref"), scope.get("ref"), ticket_id, request.employee_id, "aiteamos")
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        return {
            "index": source,
            "content": self._candidate_content(title, content),
            "memory_type": self._first_string(item.get("memory_type"), _DURABLE_CANDIDATE_KIND_TO_MEMORY_TYPE[candidate_kind]),
            "source_kind": self._first_string(item.get("source_kind"), f"external_runtime_{candidate_kind}"),
            "source_ref": self._first_string(item.get("source_ref"), result.trace_ref, str(request.trace_context.get("run_id") or request.request_id)),
            "scope_kind": scope_kind,
            "scope_ref": scope_ref,
            "confidence": item.get("confidence", 0.7),
            "employee_ids": self._string_items(item.get("employee_ids")),
            "tags": sorted(
                {
                    "external-runtime",
                    "durable-asset-candidate",
                    candidate_kind.replace("_candidate", ""),
                    result.executor_id,
                    *self._string_items(item.get("tags")),
                }
                - {""}
            ),
            "future_recall_query_hints": self._string_items(item.get("future_recall_query_hints"))
            or sorted({ticket_id, request.action_plan.action, title, asset_type} - {""}),
            "provenance": {
                **provenance,
                "candidate_source": source,
                "artifact_kind": raw_kind,
                "asset_type": asset_type,
                "title": title,
                "external_runtime": True,
                "executor_id": result.executor_id,
                "executor_session_ref": result.executor_session_ref,
                "checkpoint_ref": result.checkpoint_ref,
                "relationships": item.get("relationships") if isinstance(item.get("relationships"), list) else [],
                "provider_refs": item.get("provider_refs") if isinstance(item.get("provider_refs"), list) else [],
            },
        }

    def _normalize_candidate_kind(self, kind: str) -> str:
        normalized = kind.strip().lower().replace("-", "_").replace(".", "_").replace(":", "_")
        if normalized in _DURABLE_CANDIDATE_KIND_TO_MEMORY_TYPE:
            return normalized
        if normalized in {"decision", "doc", "skill", "capability", "memory", "tool_call"}:
            return f"{normalized}_candidate"
        if normalized in {"ticket_summary", "validated_ticket_summary"}:
            return "validated_ticket_summary_candidate"
        if normalized.endswith("_candidate") and normalized in _DURABLE_CANDIDATE_KIND_TO_MEMORY_TYPE:
            return normalized
        return ""

    def _kind_from_learning_delta_key(self, key: str) -> str:
        if key == "durable_asset_candidates":
            return "durable_asset_candidate"
        return key.removesuffix("s")

    def _candidate_content(self, title: str, content: str) -> str:
        text = str(content).strip()
        if not title:
            return text
        if title.lower() in text[:160].lower():
            return text
        return f"{title.strip()}\n\n{text}"

    def _first_string(self, *values: Any) -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _string_items(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _provider_refs_from_result(self, result: ExecutionResult) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for event in result.tool_events:
            data = event.get("data") if isinstance(event, dict) else {}
            if not isinstance(data, dict):
                continue
            ticket = data.get("ticket")
            if not isinstance(ticket, dict):
                continue
            provider_ref = ticket.get("provider_ref")
            if isinstance(provider_ref, dict) and provider_ref:
                refs.append(provider_ref)
        return refs

    def _latest_report_and_evidence_refs(self, result: ExecutionResult) -> tuple[str, str]:
        for event in reversed(result.tool_events):
            data = event.get("data") if isinstance(event, dict) else {}
            ticket = data.get("ticket") if isinstance(data, dict) else {}
            reports = ticket.get("reports") if isinstance(ticket, dict) else []
            if not isinstance(reports, list) or not reports:
                continue
            report = reports[-1]
            if not isinstance(report, dict):
                continue
            evidence = report.get("evidence") if isinstance(report.get("evidence"), list) else []
            return str(report.get("id") or "").strip(), str(evidence[0] if evidence else "").strip()
        return "", ""

    def _command_completed(self, command_id: str, data: dict[str, Any]) -> dict[str, Any]:
        capability, operation = command_id.split(":", 1) if ":" in command_id else (command_id, "")
        return {
            "event": "command.completed",
            "detail": f"{command_id} completed through result ingestion.",
            "data": {
                "command": {"id": command_id, "capability": capability, "operation": operation},
                "status": "completed",
                **data,
            },
        }

    def _load(self) -> dict[str, Any]:
        if not self._ingestion_path.exists():
            return {}
        try:
            payload = json.loads(self._ingestion_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _already_ingested(self, request_id: str) -> bool:
        return request_id in self._load()

    def _record(self, request_id: str, status: str, details: dict[str, Any]) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        payload = self._load()
        payload[request_id] = {"status": status, "details": details}
        self._ingestion_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load_artifacts(self) -> dict[str, Any]:
        if not self._artifact_path.exists():
            return {}
        try:
            payload = json.loads(self._artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _record_execution_artifacts(self, request: ExecutionRequest, result: ExecutionResult) -> None:
        ticket_id = result.output_ticket_id or request.ticket_id or request.ticket_binding.ticket_id
        if not ticket_id:
            return
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        payload = self._load_artifacts()
        thread_id = str(request.trace_context.get("thread_id") or "")
        session_key = f"{request.employee_id}::{thread_id or 'runtime'}::{ticket_id or 'none'}"
        payload[request.request_id] = {
            "request_id": request.request_id,
            "run_id": str(request.trace_context.get("run_id") or request.request_id),
            "thread_id": thread_id,
            "session_key": session_key,
            "ticket_id": ticket_id,
            "employee_id": request.employee_id,
            "action": request.action_plan.action,
            "executor_id": result.executor_id,
            "status": result.status,
            "trace_ref": result.trace_ref,
            "executor_session_ref": result.executor_session_ref,
            "checkpoint_ref": result.checkpoint_ref,
            "artifacts": result.artifacts,
            "evidence": result.evidence,
            "tool_events": result.tool_events,
            "approval_requests": result.approval_requests,
            "learning_delta": result.learning_delta,
            "memory_candidates": result.memory_candidates,
            "usage": result.usage,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
        }
        self._artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
