"""Non-destructive runtime executor smoke diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .chat_action_plan import ChatActionPlan
from .execution_approval_service import (
    ExecutionApprovalReviewRequest,
    ExecutionApprovalRunRequest,
    ExecutionApprovalRunService,
    get_execution_approval,
    review_execution_approval,
)
from .execution_contract import ExecutionRequest, ExecutionResult, TicketBinding
from .execution_dispatch_service import ExecutionDispatchService
from .execution_result_ingestion_service import ExecutionResultIngestionService
from .memory_service import create_memory_candidates_from_execution_result
from .ticket_service import TicketCreateRequest, TicketReportRequest, add_ticket_report, create_ticket, get_ticket


class RuntimeExecutorSmokeRequest(BaseModel):
    message: str = "Run non-destructive runtime smoke."
    employee_id: str = "clara"
    workspace_id: str = "local"
    ticket_id: str = ""
    repository_ids: list[str] = Field(default_factory=list)
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    ingest_result: bool = False


class RuntimeExecutorSmokeResponse(BaseModel):
    executor_id: str
    request: dict[str, Any]
    result: dict[str, Any]
    ingested: bool = False
    ingestion_blocker: str = ""


class RuntimeExecutorSmokeBatchRequest(BaseModel):
    message: str = "Run non-destructive RuntimeExecutor smoke batch."
    employee_id: str = "clara"
    workspace_id: str = "local"
    ticket_id: str = ""
    executor_ids: list[str] = Field(default_factory=list)
    repository_ids: list[str] = Field(default_factory=list)
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    runtime_config_by_executor: dict[str, dict[str, Any]] = Field(default_factory=dict)
    ingest_result: bool = False


class RuntimeExecutorSmokeBatchResponse(BaseModel):
    status: str
    results: list[RuntimeExecutorSmokeResponse]
    summary: dict[str, Any]
    learning_delta: dict[str, Any] = Field(default_factory=dict)
    ingestion_blocker: str = ""


class RuntimeExecutorDogfoodRequest(BaseModel):
    executor_id: str = "claude_code"
    message: str = "Run Ticket-bound RuntimeExecutor dogfood harness."
    employee_id: str = "alex"
    reviewer_employee_id: str = "clara"
    workspace_id: str = "local"
    ticket_id: str = ""
    create_ticket_if_missing: bool = True
    repository_ids: list[str] = Field(default_factory=list)
    smoke_executor_ids: list[str] = Field(default_factory=list)
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    runtime_config_by_executor: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RuntimeExecutorDogfoodResponse(BaseModel):
    status: str
    ticket: dict[str, Any] = Field(default_factory=dict)
    smoke_batch: dict[str, Any] = Field(default_factory=dict)
    approval: dict[str, Any] = Field(default_factory=dict)
    approved_run: dict[str, Any] = Field(default_factory=dict)
    summary_report: dict[str, Any] = Field(default_factory=dict)
    learning_delta: dict[str, Any] = Field(default_factory=dict)
    blockers: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeExecutorSmokeService:
    def __init__(
        self,
        *,
        workspace_dir: Path | None = None,
        dispatch_service: ExecutionDispatchService | None = None,
        ingestion_service: ExecutionResultIngestionService | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir or Path(".aiteamos")
        self.dispatch_service = dispatch_service or ExecutionDispatchService()
        self.ingestion_service = ingestion_service or ExecutionResultIngestionService(workspace_dir=self.workspace_dir)

    async def smoke(self, executor_id: str, smoke_request: RuntimeExecutorSmokeRequest) -> RuntimeExecutorSmokeResponse:
        executor_id = executor_id.strip().replace("-", "_")
        if executor_id not in self.dispatch_service.executors:
            blocker = self._blocked_result(executor_id, "executor_unavailable", f"Runtime executor is not registered: {executor_id}")
            return RuntimeExecutorSmokeResponse(executor_id=executor_id, request={}, result=blocker.model_dump(mode="json"))

        request = self._build_execution_request(executor_id, smoke_request)
        result = await self.dispatch_service.dispatch(request)
        ingested = False
        ingestion_blocker = ""
        if smoke_request.ingest_result:
            if not smoke_request.ticket_id.strip():
                ingestion_blocker = "ingest_result requires ticket_id so AITeamOS can write Ticket provenance."
            else:
                result = self.ingestion_service.ingest(request, result)
                ingested = result.status in {"completed", "partial", "needs_approval"}
                if not ingested:
                    ingestion_blocker = result.errors[-1]["detail"] if result.errors else result.report

        return RuntimeExecutorSmokeResponse(
            executor_id=executor_id,
            request=request.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            ingested=ingested,
            ingestion_blocker=ingestion_blocker,
        )

    async def smoke_batch(self, batch_request: RuntimeExecutorSmokeBatchRequest) -> RuntimeExecutorSmokeBatchResponse:
        executor_ids = [
            executor_id.strip().replace("-", "_")
            for executor_id in batch_request.executor_ids
            if executor_id.strip()
        ] or sorted(self.dispatch_service.executors)
        results: list[RuntimeExecutorSmokeResponse] = []
        for executor_id in executor_ids:
            runtime_config = {
                **batch_request.runtime_config,
                **batch_request.runtime_config_by_executor.get(executor_id, {}),
            }
            results.append(
                await self.smoke(
                    executor_id,
                    RuntimeExecutorSmokeRequest(
                        message=batch_request.message,
                        employee_id=batch_request.employee_id,
                        workspace_id=batch_request.workspace_id,
                        ticket_id=batch_request.ticket_id,
                        repository_ids=batch_request.repository_ids,
                        runtime_config=runtime_config,
                        ingest_result=batch_request.ingest_result,
                    ),
                )
            )

        summary = self._batch_summary(results)
        status = "completed"
        if summary["failed_count"] > 0:
            status = "failed"
        elif summary["blocked_count"] > 0 or summary["ingestion_blocker_count"] > 0:
            status = "blocked"
        ingestion_blocker = ""
        if batch_request.ingest_result and not batch_request.ticket_id.strip():
            ingestion_blocker = "Batch ingest_result requires ticket_id so AITeamOS can write Ticket provenance."
        elif summary["ingestion_blocker_count"] > 0:
            blockers = [result.ingestion_blocker for result in results if result.ingestion_blocker]
            ingestion_blocker = "; ".join(blockers[:3])

        return RuntimeExecutorSmokeBatchResponse(
            status=status,
            results=results,
            summary=summary,
            learning_delta={
                "action": "runtime_executor_smoke_batch",
                "source": "runtime_executor_smoke_service",
                "executor_ids": executor_ids,
                "completed_count": summary["completed_count"],
                "blocked_count": summary["blocked_count"],
                "failed_count": summary["failed_count"],
                "ingested_count": summary["ingested_count"],
                "ingestion_blocker_count": summary["ingestion_blocker_count"],
                "ticket_bound": bool(batch_request.ticket_id.strip()),
                "default_ingest_result": batch_request.ingest_result,
            },
            ingestion_blocker=ingestion_blocker,
        )

    async def dogfood(self, dogfood_request: RuntimeExecutorDogfoodRequest) -> RuntimeExecutorDogfoodResponse:
        executor_id = dogfood_request.executor_id.strip().replace("-", "_") or "claude_code"
        ticket = self._dogfood_ticket(dogfood_request, executor_id)
        if ticket is None:
            return self._dogfood_blocked(
                dogfood_request,
                executor_id,
                reason="dogfood_ticket_required",
                detail="RuntimeExecutor dogfood requires an existing Ticket or create_ticket_if_missing=true.",
            )

        reusable = self._reuse_completed_dogfood_approval(dogfood_request, executor_id, ticket.id)
        if reusable is not None:
            return reusable

        smoke_executor_ids = [
            item.strip().replace("-", "_")
            for item in dogfood_request.smoke_executor_ids
            if item.strip()
        ] or [executor_id]
        runtime_config_by_executor = {
            key.strip().replace("-", "_"): dict(value)
            for key, value in dogfood_request.runtime_config_by_executor.items()
            if key.strip()
        }
        runtime_config_by_executor[executor_id] = {
            **dogfood_request.runtime_config,
            **runtime_config_by_executor.get(executor_id, {}),
        }
        smoke_batch = await self.smoke_batch(
            RuntimeExecutorSmokeBatchRequest(
                message=f"Dogfood smoke before approved runtime mutation: {dogfood_request.message}",
                employee_id=dogfood_request.employee_id,
                workspace_id=dogfood_request.workspace_id,
                ticket_id=ticket.id,
                executor_ids=smoke_executor_ids,
                repository_ids=dogfood_request.repository_ids,
                runtime_config_by_executor=runtime_config_by_executor,
                ingest_result=True,
            )
        )
        target_smoke = next((result for result in smoke_batch.results if result.executor_id == executor_id), None)
        blockers: list[dict[str, Any]] = []
        if target_smoke is None or not self._smoke_passed_for_dogfood(target_smoke):
            blockers.append(
                {
                    "reason": "dogfood_smoke_blocked",
                    "detail": f"Target executor {executor_id} must pass Ticket-bound smoke before approved mutation dogfood.",
                }
            )
            summary_report = self._append_dogfood_summary(
                ticket_id=ticket.id,
                request=dogfood_request,
                status="blocked",
                smoke_batch=smoke_batch,
                approval={},
                approved_run={},
                blockers=blockers,
            )
            learning_delta = self._dogfood_learning_delta("blocked", executor_id, ticket.id, smoke_batch, {}, blockers)
            self._attach_dogfood_learning_candidates(
                learning_delta,
                request=dogfood_request,
                executor_id=executor_id,
                ticket_id=ticket.id,
                status="blocked",
                smoke_batch=smoke_batch,
                approval={},
                approved_run={},
                summary_report=summary_report,
                blockers=blockers,
            )
            return RuntimeExecutorDogfoodResponse(
                status="blocked",
                ticket=ticket.model_dump(mode="json"),
                smoke_batch=smoke_batch.model_dump(mode="json"),
                summary_report=summary_report,
                learning_delta=learning_delta,
                blockers=blockers,
            )

        source_request = self._dogfood_source_request(dogfood_request, executor_id, ticket.id)
        source_result = self._dogfood_source_approval_result(source_request, executor_id, ticket.id)
        source_result = self.ingestion_service.ingest(source_request, source_result)
        approvals = source_result.learning_delta.get("approval_records") if isinstance(source_result.learning_delta, dict) else []
        approval = approvals[0] if isinstance(approvals, list) and approvals else {}
        approval_id = str(approval.get("id") or "")
        if not approval_id:
            expected_approval_id = f"approval-{source_request.request_id}-1"
            existing_approval = get_execution_approval(workspace_dir=self.workspace_dir, approval_id=expected_approval_id)
            if existing_approval is not None:
                approval = existing_approval.model_dump(mode="json")
                approval_id = existing_approval.id
        if not approval_id:
            blockers.append({"reason": "dogfood_approval_record_missing", "detail": "Runtime approval record was not created."})
            summary_report = self._append_dogfood_summary(
                ticket_id=ticket.id,
                request=dogfood_request,
                status="blocked",
                smoke_batch=smoke_batch,
                approval={},
                approved_run={},
                blockers=blockers,
            )
            learning_delta = self._dogfood_learning_delta("blocked", executor_id, ticket.id, smoke_batch, {}, blockers)
            self._attach_dogfood_learning_candidates(
                learning_delta,
                request=dogfood_request,
                executor_id=executor_id,
                ticket_id=ticket.id,
                status="blocked",
                smoke_batch=smoke_batch,
                approval={},
                approved_run={},
                summary_report=summary_report,
                blockers=blockers,
            )
            return RuntimeExecutorDogfoodResponse(
                status="blocked",
                ticket=ticket.model_dump(mode="json"),
                smoke_batch=smoke_batch.model_dump(mode="json"),
                summary_report=summary_report,
                learning_delta=learning_delta,
                blockers=blockers,
            )

        reviewed = review_execution_approval(
            workspace_dir=self.workspace_dir,
            approval_id=approval_id,
            review=ExecutionApprovalReviewRequest(
                status="approved",
                reviewer_employee_id=dogfood_request.reviewer_employee_id,
                reason="Approved by RuntimeExecutor dogfood harness.",
            ),
        )
        approved_run = await ExecutionApprovalRunService(
            workspace_dir=self.workspace_dir,
            dispatch_service=self.dispatch_service,
            ingestion_service=self.ingestion_service,
        ).run(
            executor_id,
            approval_id,
            ExecutionApprovalRunRequest(
                workspace_id=dogfood_request.workspace_id,
                message=self._dogfood_approved_run_message(dogfood_request, executor_id, ticket.id),
                runtime_config=dogfood_request.runtime_config,
                ingest_result=True,
            ),
        )
        if approved_run.result.get("status") != "completed" or not approved_run.ingested:
            blockers.append(
                {
                    "reason": "dogfood_approved_run_blocked",
                    "detail": approved_run.ingestion_blocker or str(approved_run.result.get("report") or "Approved runtime run did not complete."),
                }
            )
        status = "completed" if not blockers else "blocked"
        summary_report = self._append_dogfood_summary(
            ticket_id=ticket.id,
            request=dogfood_request,
            status=status,
            smoke_batch=smoke_batch,
            approval=reviewed.model_dump(mode="json"),
            approved_run=approved_run.model_dump(mode="json"),
            blockers=blockers,
        )
        learning_delta = self._dogfood_learning_delta(
            status,
            executor_id,
            ticket.id,
            smoke_batch,
            approved_run.model_dump(mode="json"),
            blockers,
        )
        self._attach_dogfood_learning_candidates(
            learning_delta,
            request=dogfood_request,
            executor_id=executor_id,
            ticket_id=ticket.id,
            status=status,
            smoke_batch=smoke_batch,
            approval=reviewed.model_dump(mode="json"),
            approved_run=approved_run.model_dump(mode="json"),
            summary_report=summary_report,
            blockers=blockers,
        )
        return RuntimeExecutorDogfoodResponse(
            status=status,
            ticket=ticket.model_dump(mode="json"),
            smoke_batch=smoke_batch.model_dump(mode="json"),
            approval=reviewed.model_dump(mode="json"),
            approved_run=approved_run.model_dump(mode="json"),
            summary_report=summary_report,
            learning_delta=learning_delta,
            blockers=blockers,
        )

    def _smoke_passed_for_dogfood(self, smoke: RuntimeExecutorSmokeResponse) -> bool:
        return bool(smoke.ingested) and str(smoke.result.get("status") or "") in {"completed", "partial", "needs_approval"}

    def _reuse_completed_dogfood_approval(
        self,
        request: RuntimeExecutorDogfoodRequest,
        executor_id: str,
        ticket_id: str,
    ) -> RuntimeExecutorDogfoodResponse | None:
        approval_id = f"approval-dogfood-{executor_id}-{ticket_id}-1"
        approval = get_execution_approval(workspace_dir=self.workspace_dir, approval_id=approval_id)
        if approval is None:
            return None
        if approval.last_run_status != "completed" or approval.last_ingestion_blocker:
            return None
        if str(approval.last_result.get("status") or "") != "completed":
            return None

        ticket = get_ticket(ticket_id)
        if ticket is None:
            return None
        smoke_batch = RuntimeExecutorSmokeBatchResponse(
            status="completed",
            results=[],
            summary={
                "executor_count": 1,
                "completed_count": 1,
                "blocked_count": 0,
                "failed_count": 0,
                "needs_approval_count": 0,
                "partial_count": 0,
                "ingested_count": 1,
                "ingestion_blocker_count": 0,
                "blocked_executor_ids": [],
                "failed_executor_ids": [],
                "reused_completed_approval": True,
            },
            learning_delta={
                "action": "runtime_executor_smoke_batch",
                "source": "runtime_executor_smoke_service",
                "reused_completed_approval": True,
                "approval_id": approval.id,
                "executor_ids": [executor_id],
                "ticket_bound": True,
            },
        )
        approved_run = {
            "approval": approval.model_dump(mode="json"),
            "request": approval.source_request,
            "result": approval.last_result,
            "ingested": True,
            "ingestion_blocker": "",
            "reused_completed_approval": True,
        }
        summary_report = self._append_dogfood_summary(
            ticket_id=ticket_id,
            request=request,
            status="completed",
            smoke_batch=smoke_batch,
            approval=approval.model_dump(mode="json"),
            approved_run=approved_run,
            blockers=[],
        )
        learning_delta = self._dogfood_learning_delta(
            "completed",
            executor_id,
            ticket_id,
            smoke_batch,
            approved_run,
            [],
        )
        learning_delta["reused_completed_approval"] = True
        learning_delta["approval_id"] = approval.id
        self._attach_dogfood_learning_candidates(
            learning_delta,
            request=request,
            executor_id=executor_id,
            ticket_id=ticket_id,
            status="completed",
            smoke_batch=smoke_batch,
            approval=approval.model_dump(mode="json"),
            approved_run=approved_run,
            summary_report=summary_report,
            blockers=[],
        )
        return RuntimeExecutorDogfoodResponse(
            status="completed",
            ticket=ticket.model_dump(mode="json"),
            smoke_batch=smoke_batch.model_dump(mode="json"),
            approval=approval.model_dump(mode="json"),
            approved_run=approved_run,
            summary_report=summary_report,
            learning_delta=learning_delta,
            blockers=[],
        )

    def _batch_summary(self, results: list[RuntimeExecutorSmokeResponse]) -> dict[str, Any]:
        statuses = [str(result.result.get("status") or "") for result in results]
        return {
            "executor_count": len(results),
            "completed_count": sum(1 for status in statuses if status == "completed"),
            "blocked_count": sum(1 for status in statuses if status == "blocked"),
            "failed_count": sum(1 for status in statuses if status == "failed"),
            "needs_approval_count": sum(1 for status in statuses if status == "needs_approval"),
            "partial_count": sum(1 for status in statuses if status == "partial"),
            "ingested_count": sum(1 for result in results if result.ingested),
            "ingestion_blocker_count": sum(1 for result in results if result.ingestion_blocker),
            "blocked_executor_ids": [
                result.executor_id
                for result in results
                if str(result.result.get("status") or "") == "blocked"
            ],
            "failed_executor_ids": [
                result.executor_id
                for result in results
                if str(result.result.get("status") or "") == "failed"
            ],
        }

    def _dogfood_ticket(self, request: RuntimeExecutorDogfoodRequest, executor_id: str) -> Any | None:
        ticket_id = request.ticket_id.strip()
        if ticket_id:
            return get_ticket(ticket_id)
        if not request.create_ticket_if_missing:
            return None
        return create_ticket(
            TicketCreateRequest(
                title=f"RuntimeExecutor dogfood: {executor_id}",
                description=request.message,
                ticket_type="ops",
                assigned_employee_id=request.employee_id,
                validation_employee_id=request.reviewer_employee_id,
                code_repository_ids=request.repository_ids,
                source_run_id=f"dogfood-{executor_id}",
                actor_employee_id=request.reviewer_employee_id,
                actor_role="AI Team OS Manager",
            )
        )

    def _dogfood_source_request(self, request: RuntimeExecutorDogfoodRequest, executor_id: str, ticket_id: str) -> ExecutionRequest:
        approved_run_message = self._dogfood_approved_run_message(request, executor_id, ticket_id)
        return ExecutionRequest(
            request_id=f"dogfood-{executor_id}-{ticket_id}",
            workspace_id=request.workspace_id,
            employee_id=request.employee_id,
            ticket_id=ticket_id,
            ticket_binding=TicketBinding(mode="existing", ticket_id=ticket_id, required=True),
            action_plan=ChatActionPlan(
                action="implement_ticket",
                arguments={"message": approved_run_message, "repository_ids": request.repository_ids},
            ),
            task_context={
                "task_summary": approved_run_message,
                "ticket": {"id": ticket_id},
                "repository_scope": {"repository_ids": request.repository_ids},
                "diagnostic": {"kind": "runtime_executor_dogfood", "executor_id": executor_id},
            },
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": executor_id, "selected_executor": executor_id},
            approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
            expected_outputs={"report": True, "evidence": True, "artifacts": True},
            trace_context={"run_id": f"dogfood-{executor_id}-{ticket_id}", "trace_ref": f".aiteamos/traces/dogfood-{executor_id}-{ticket_id}.jsonl"},
        )

    def _dogfood_approved_run_message(self, request: RuntimeExecutorDogfoodRequest, executor_id: str, ticket_id: str) -> str:
        repository_scope = ", ".join(request.repository_ids) if request.repository_ids else "the current AITeamOS workspace"
        artifact_path = f".aiteamos/artifacts/runtime_dogfood/{ticket_id}-{executor_id}.md"
        return "\n".join(
            [
                f"Execute one approved RuntimeExecutor dogfood repo mutation for Ticket {ticket_id} using executor {executor_id}.",
                f"Repository scope: {repository_scope}.",
                f"Create or update exactly one small evidence artifact file at {artifact_path}.",
                "The artifact must record ticket_id, executor_id, approval-bound execution, and that this is a RuntimeExecutor dogfood evidence artifact.",
                "Do not run scripts/live_provider_dogfood.py, scripts/plan_v7_ci_artifacts.py, production-readiness commands, or any recursive dogfood/readiness command.",
                "Do not modify product source files unless they are required to complete this narrow evidence artifact task.",
                "Run one quick validation command, preferably python -m py_compile services/api/aiteamos_api/read/runtime_executor_smoke_service.py.",
                "Return JSON matching the provided output schema with status completed, a changed_files or repo_patch artifact naming the evidence artifact path, and at least one evidence item whose kind, ref, or summary includes test or validation.",
            ]
        )

    def _dogfood_source_approval_result(self, request: ExecutionRequest, executor_id: str, ticket_id: str) -> ExecutionResult:
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=executor_id,
            status="needs_approval",
            report="RuntimeExecutor dogfood requires governed repo mutation approval before dispatch.",
            output_ticket_id=ticket_id,
            approval_requests=[
                {
                    "kind": "repo_mutation",
                    "ticket_id": ticket_id,
                    "executor_id": executor_id,
                    "required_capability": "repo:write",
                    "reason": "RuntimeExecutor dogfood approved-run requires Ticket-bound repo mutation approval.",
                }
            ],
            errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
        )

    def _append_dogfood_summary(
        self,
        *,
        ticket_id: str,
        request: RuntimeExecutorDogfoodRequest,
        status: str,
        smoke_batch: RuntimeExecutorSmokeBatchResponse,
        approval: dict[str, Any],
        approved_run: dict[str, Any],
        blockers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evidence_refs = self._dogfood_evidence_refs(smoke_batch, approved_run)
        lines = [
            f"RuntimeExecutor dogfood harness status: {status}.",
            f"Executor: {request.executor_id.strip().replace('-', '_')}.",
            f"Smoke summary: {smoke_batch.summary}.",
        ]
        approval_id = str(approval.get("id") or "")
        if approval_id:
            lines.append(f"Approval ref: {approval_id}.")
        run_result = approved_run.get("result") if isinstance(approved_run.get("result"), dict) else {}
        if run_result:
            lines.append(f"Approved run status: {run_result.get('status')}.")
        if blockers:
            lines.append("Blockers:")
            lines.extend(f"- {item.get('reason')}: {item.get('detail')}" for item in blockers)
        updated_ticket = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.reviewer_employee_id,
                reporter_role="AI Team OS Manager",
                content="\n".join(lines),
                evidence=evidence_refs,
                report_type="runtime_dogfood_summary",
                source_run_id=f"dogfood-{request.executor_id.strip().replace('-', '_')}",
            ),
        )
        report_id = updated_ticket.reports[-1].id if updated_ticket.reports else ""
        return {"ticket_id": updated_ticket.id, "report_id": report_id, "report_type": "runtime_dogfood_summary", "evidence": evidence_refs}

    def _dogfood_evidence_refs(self, smoke_batch: RuntimeExecutorSmokeBatchResponse, approved_run: dict[str, Any]) -> list[str]:
        refs: list[str] = []
        for smoke in smoke_batch.results:
            refs.extend(self._evidence_refs_from_result(smoke.result))
        result = approved_run.get("result") if isinstance(approved_run.get("result"), dict) else {}
        refs.extend(self._evidence_refs_from_result(result))
        return sorted(dict.fromkeys(ref for ref in refs if ref))

    def _evidence_refs_from_result(self, result: dict[str, Any]) -> list[str]:
        evidence = result.get("evidence") if isinstance(result, dict) else []
        if not isinstance(evidence, list):
            return []
        return [
            str(item.get("ref") or item.get("evidence_ref") or item.get("summary") or "").strip()
            for item in evidence
            if isinstance(item, dict) and str(item.get("ref") or item.get("evidence_ref") or item.get("summary") or "").strip()
        ]

    def _dogfood_learning_delta(
        self,
        status: str,
        executor_id: str,
        ticket_id: str,
        smoke_batch: RuntimeExecutorSmokeBatchResponse,
        approved_run: dict[str, Any],
        blockers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "action": "runtime_executor_dogfood",
            "source": "runtime_executor_smoke_service",
            "status": status,
            "executor_id": executor_id,
            "ticket_id": ticket_id,
            "smoke_summary": smoke_batch.summary,
            "approved_run_status": str((approved_run.get("result") if isinstance(approved_run.get("result"), dict) else {}).get("status") or ""),
            "blocker_count": len(blockers),
        }

    def _attach_dogfood_learning_candidates(
        self,
        learning_delta: dict[str, Any],
        *,
        request: RuntimeExecutorDogfoodRequest,
        executor_id: str,
        ticket_id: str,
        status: str,
        smoke_batch: RuntimeExecutorSmokeBatchResponse,
        approval: dict[str, Any],
        approved_run: dict[str, Any],
        summary_report: dict[str, Any],
        blockers: list[dict[str, Any]],
    ) -> None:
        source_report_id = str(summary_report.get("report_id") or "").strip()
        report_suffix = source_report_id or status
        run_id = f"dogfood-{executor_id}-{ticket_id}-{report_suffix}"
        approved_result = approved_run.get("result") if isinstance(approved_run.get("result"), dict) else {}
        evidence_refs = summary_report.get("evidence") if isinstance(summary_report.get("evidence"), list) else []
        blocker_lines = [
            f"- {item.get('reason')}: {item.get('detail')}"
            for item in blockers
            if isinstance(item, dict)
        ]
        content_lines = [
            f"RuntimeExecutor dogfood learning summary for {executor_id}.",
            f"Status: {status}.",
            f"Ticket: {ticket_id}.",
            f"Smoke summary: {smoke_batch.summary}.",
            f"Approved run status: {approved_result.get('status') or '-'}."
        ]
        approval_id = str(approval.get("id") or "").strip()
        if approval_id:
            content_lines.append(f"Approval ref: {approval_id}.")
        if evidence_refs:
            content_lines.append(f"Evidence refs: {', '.join(str(item) for item in evidence_refs[:8])}.")
        if blocker_lines:
            content_lines.append("Blockers:")
            content_lines.extend(blocker_lines[:5])
        created = create_memory_candidates_from_execution_result(
            memory_candidates=[
                {
                    "index": "runtime_executor_dogfood_summary",
                    "content": "\n".join(content_lines),
                    "memory_type": "summary",
                    "source_kind": "runtime_executor_dogfood",
                    "source_ref": run_id,
                    "scope_kind": "ticket",
                    "scope_ref": ticket_id,
                    "confidence": 0.78 if status == "completed" else 0.62,
                    "employee_ids": [request.employee_id, request.reviewer_employee_id],
                    "tags": ["self-bootstrap", "runtime-executor-dogfood", executor_id, status],
                    "future_recall_query_hints": [
                        "runtime executor dogfood",
                        executor_id,
                        ticket_id,
                        status,
                    ],
                    "provenance": {
                        "action": "runtime_executor_dogfood",
                        "source": "runtime_executor_smoke_service",
                        "dogfood_status": status,
                        "executor_id": executor_id,
                        "approval_id": approval_id,
                        "summary_report": summary_report,
                        "smoke_summary": smoke_batch.summary,
                        "approved_run_status": str(approved_result.get("status") or ""),
                        "blockers": blockers,
                    },
                }
            ],
            request_id=run_id,
            run_id=run_id,
            thread_id="",
            ticket_id=ticket_id,
            employee_id=request.reviewer_employee_id or request.employee_id,
            action="runtime_executor_dogfood",
            executor_id=executor_id,
            trace_ref=f".aiteamos/traces/{run_id}.jsonl",
            provider_refs=[],
            source_report_id=source_report_id,
            evidence_id=str(evidence_refs[0]) if evidence_refs else "",
        )
        learning_delta["memory_candidate_ids"] = [candidate.id for candidate in created]
        learning_delta["memory_candidate_count"] = len(created)

    def _dogfood_blocked(
        self,
        request: RuntimeExecutorDogfoodRequest,
        executor_id: str,
        *,
        reason: str,
        detail: str,
    ) -> RuntimeExecutorDogfoodResponse:
        blockers = [{"reason": reason, "detail": detail}]
        return RuntimeExecutorDogfoodResponse(
            status="blocked",
            learning_delta={
                "action": "runtime_executor_dogfood",
                "source": "runtime_executor_smoke_service",
                "status": "blocked",
                "executor_id": executor_id,
                "blocker_count": 1,
            },
            blockers=blockers,
        )

    def _build_execution_request(self, executor_id: str, smoke_request: RuntimeExecutorSmokeRequest) -> ExecutionRequest:
        ticket_id = smoke_request.ticket_id.strip()
        message = smoke_request.message.strip() or "Run non-destructive runtime smoke."
        runtime_config = dict(smoke_request.runtime_config)
        smoke_action = self._smoke_action_for_executor(executor_id)
        permission_policy: dict[str, Any] = {
            "selected_ai_engine": self._smoke_ai_engine_for_executor(executor_id, smoke_action),
            "selected_executor": executor_id,
        }
        if runtime_config:
            permission_policy["runtime_config"] = {executor_id: runtime_config}
        return ExecutionRequest(
            request_id=f"smoke-{executor_id}",
            workspace_id=smoke_request.workspace_id,
            employee_id=smoke_request.employee_id,
            ticket_id=ticket_id,
            ticket_binding=TicketBinding(
                mode="existing" if ticket_id else "none",
                ticket_id=ticket_id,
                required=bool(ticket_id),
            ),
            action_plan=ChatActionPlan(
                action=smoke_action,
                arguments=self._smoke_action_arguments(smoke_action, message=message, repository_ids=smoke_request.repository_ids),
                confidence=1.0,
                reason=f"Non-destructive RuntimeExecutor smoke diagnostic using {smoke_action}.",
                source="runtime_smoke",
            ),
            task_context={
                "task_summary": message,
                "repository_scope": {"repository_ids": smoke_request.repository_ids},
                "diagnostic": {"kind": "runtime_executor_smoke", "executor_id": executor_id},
            },
            capability_grants=["repo:read", "ticket:evidence:write"],
            approval_policy={
                "require_approval_for": ["repo:write"],
                "on_missing_approval": "return_needs_approval",
            },
            expected_outputs={"report": True, "artifacts": True, "evidence": True},
            permission_policy=permission_policy,
            trace_context={
                "run_id": f"smoke-{executor_id}",
                "trace_ref": f".aiteamos/traces/smoke-{executor_id}.jsonl",
                "source": "runtime_executor_smoke",
            },
        )

    def _smoke_action_for_executor(self, executor_id: str) -> str:
        executor = self.dispatch_service.executors.get(executor_id)
        supported = set(getattr(executor, "supported_actions", set()) or set()) if executor is not None else set()
        capabilities = set(getattr(executor, "capabilities", set()) or set()) if executor is not None else set()
        available = supported or capabilities
        for action in ("inspect_code_repository", "answer_only", "append_report", "list_employees"):
            if action in available:
                return action
        return "inspect_code_repository"

    def _smoke_ai_engine_for_executor(self, executor_id: str, smoke_action: str) -> str:
        if executor_id in {"langgraph", "universal_employee_agent"} and smoke_action == "answer_only":
            return "deepseek"
        return executor_id

    def _smoke_action_arguments(self, action: str, *, message: str, repository_ids: list[str]) -> dict[str, Any]:
        if action == "inspect_code_repository":
            return {
                "message": message,
                "query": "runtime adapter smoke",
                "repository_ids": repository_ids,
            }
        if action == "append_report":
            return {"message": message, "content": message}
        if action == "list_employees":
            return {}
        return {"message": message}

    def _blocked_result(self, executor_id: str, reason: str, detail: str) -> ExecutionResult:
        request = ExecutionRequest(
            request_id=f"smoke-{executor_id}",
            employee_id="system",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(action="inspect_code_repository", arguments={}),
        )
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=executor_id,
            status="blocked",
            report=detail,
            errors=[{"reason": reason, "detail": detail}],
        )
