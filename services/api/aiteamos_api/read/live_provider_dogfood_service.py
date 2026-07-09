"""Opt-in live provider dogfood runner for the Plan v7 Workbench loop.

The runner composes existing AITeamOS boundaries instead of creating a new
agent loop: LangGraph Workbench for the Chat entry, Ticket service for Plane,
Assets Review Queue for durable memory, and Graphiti for projection/recall.
Optional repo-write adapter dogfood still goes through RuntimeExecutor.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .asset_candidate_service import (
    AssetCandidateReviewRequest,
    list_asset_candidates,
    project_asset_record_to_graphiti,
    review_asset_candidate,
)
from .memory_service import (
    MemoryCandidateCreateRequest,
    approve_memory_candidate,
    create_memory_candidate,
    graphiti_backend_status,
    search_memory,
)
from .provider_conformance_service import provider_environment_smoke
from .repository_service import list_code_repositories
from .execution_dispatch_service import ExecutionDispatchService
from .runtime_executor_smoke_service import (
    RuntimeExecutorDogfoodRequest,
    RuntimeExecutorDogfoodResponse,
    RuntimeExecutorSmokeService,
)
from .ticket_service import (
    Ticket,
    TicketCreateRequest,
    TicketReportRequest,
    TicketBackendSettings,
    TicketBackendStatus,
    add_ticket_report,
    create_ticket,
    get_ticket,
    ticket_backend_settings,
    ticket_backend_status,
)


CORE_LOOP_PROFILE = "core_loop"
REPO_WRITE_ADAPTER_PROFILE = "repo_write_adapter"
SUPPORTED_LIVE_DOGFOOD_PROFILES = {CORE_LOOP_PROFILE, REPO_WRITE_ADAPTER_PROFILE}


WorkbenchRunner = Callable[["LiveProviderDogfoodRequest", Ticket], Awaitable[dict[str, Any]]]
RuntimeDogfoodRunner = Callable[["LiveProviderDogfoodRequest", Ticket], Awaitable[RuntimeExecutorDogfoodResponse]]
ProviderSmokeRunner = Callable[[], Awaitable[Any]]


class LiveProviderDogfoodRequest(BaseModel):
    execute: bool = False
    profile: str = CORE_LOOP_PROFILE
    confirm_env_var: str = "AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    langgraph_url: str = "http://127.0.0.1:2024"
    assistant_id: str = "aiteamos_workbench"
    employee_id: str = "clara"
    worker_employee_id: str = "alex"
    reviewer_employee_id: str = "clara"
    executor_id: str = "langgraph"
    ticket_id: str = ""
    create_ticket_if_missing: bool = True
    repository_ids: list[str] = Field(default_factory=list)
    message: str = "Run the AITeamOS plan_v7 LangGraph core-loop dogfood."
    recall_query: str = "AITeamOS live provider dogfood approved asset recall"
    require_provider_smoke: bool = True
    provider_smoke_timeout_seconds: float = 60.0
    require_repo_write_executor: bool | None = None
    require_natural_handoff: bool = False
    expected_handoff_target_employee_id: str = ""


class LiveProviderDogfoodResponse(BaseModel):
    status: str
    profile: str = CORE_LOOP_PROFILE
    dry_run: bool = False
    mutation_gate: dict[str, Any] = Field(default_factory=dict)
    ticket: dict[str, Any] = Field(default_factory=dict)
    workbench: dict[str, Any] = Field(default_factory=dict)
    runtime_dogfood: dict[str, Any] = Field(default_factory=dict)
    asset_reviews: list[dict[str, Any]] = Field(default_factory=list)
    graphiti_projections: list[dict[str, Any]] = Field(default_factory=list)
    recall: dict[str, Any] = Field(default_factory=dict)
    provider_smoke: dict[str, Any] = Field(default_factory=dict)
    executor_preflight: dict[str, Any] = Field(default_factory=dict)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class LiveProviderDogfoodReadinessResponse(BaseModel):
    status: str
    profile: str = CORE_LOOP_PROFILE
    selected_executor_id: str
    require_repo_write_executor: bool = True
    mutation_gate: dict[str, Any] = Field(default_factory=dict)
    selected_executor_preflight: dict[str, Any] = Field(default_factory=dict)
    repo_write_executor_candidates: list[dict[str, Any]] = Field(default_factory=list)
    provider_prerequisites: dict[str, Any] = Field(default_factory=dict)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class LiveProviderDogfoodService:
    def __init__(
        self,
        *,
        workspace_dir: Path | None = None,
        provider_smoke_runner: ProviderSmokeRunner | None = None,
        workbench_runner: WorkbenchRunner | None = None,
        runtime_dogfood_runner: RuntimeDogfoodRunner | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).resolve()
        self.provider_smoke_runner = provider_smoke_runner or self._provider_smoke
        self.workbench_runner = workbench_runner or self._run_langgraph_workbench
        self.runtime_dogfood_runner = runtime_dogfood_runner or self._run_runtime_dogfood

    async def readiness(self, request: LiveProviderDogfoodRequest | None = None) -> LiveProviderDogfoodReadinessResponse:
        request = request or LiveProviderDogfoodRequest(execute=True)
        profile = normalize_live_dogfood_profile(request.profile)
        require_repo_write = _effective_require_repo_write(request)
        executor_preflight = await self._executor_preflight(request)
        repo_write_candidates = await self._repo_write_executor_candidates()
        ticket_settings = ticket_backend_settings()
        ticket_status = ticket_backend_status()
        plane_ticket_backend_selected = ticket_status.mode == "plane" and (ticket_status.provider in {"", "plane"})
        plane_ticket_setup = _plane_ticket_backend_setup_summary(ticket_settings, ticket_status)
        ticket_release_target = ticket_status.release_target if isinstance(ticket_status.release_target, dict) else {}
        memory_status = graphiti_backend_status()
        mutation_gate = self._mutation_gate(request)

        blockers: list[dict[str, Any]] = []
        if profile not in SUPPORTED_LIVE_DOGFOOD_PROFILES:
            blockers.append(_unsupported_profile_blocker(profile))
        for item in executor_preflight.get("blockers", []):
            if isinstance(item, dict):
                blockers.append({**item, "scope": "selected_runtime_executor"})

        repo_write_ready_count = sum(1 for item in repo_write_candidates if item.get("status") == "ready")
        if require_repo_write and repo_write_ready_count == 0:
            blockers.append(
                {
                    "reason": "no_ready_repo_write_runtime_executor",
                    "scope": "runtime_executors",
                    "detail": "No RuntimeExecutor with repo:write capability is ready for the live provider dogfood loop.",
                    "setup_required": _unique_setup_required(repo_write_candidates),
                }
            )

        if ticket_status.status != "ready":
            blockers.append(
                {
                    "reason": "ticket_provider_not_ready",
                    "scope": "ticket_backend",
                    "status": ticket_status.status,
                    "detail": ticket_status.detail,
                    "setup_required": ticket_status.setup_required,
                }
            )
        elif not plane_ticket_backend_selected:
            blockers.append(
                {
                    "reason": "plane_ticket_backend_not_selected",
                    "scope": "ticket_backend",
                    "status": "setup_blocked",
                    "detail": (
                        "Live Plane / Graphiti dogfood requires the Plane Ticket backend, "
                        f"but the selected Ticket backend mode is {ticket_status.mode}."
                    ),
                    "setup_required": plane_ticket_setup["setup_required"],
                    "current_mode": ticket_status.mode,
                    "current_provider": ticket_status.provider,
                    "required_mode": "plane",
                    "required_provider": "plane",
                    "plane_setup": plane_ticket_setup,
                }
            )

        if memory_status.status != "ready":
            blockers.append(
                {
                    "reason": "memory_provider_not_ready",
                    "scope": "memory_backend",
                    "status": memory_status.status,
                    "detail": memory_status.detail,
                    "setup_required": [
                        name
                        for name, configured in (
                            ("Graphiti URI/user", memory_status.graph_configured),
                            ("Graphiti Neo4j password", memory_status.password_configured),
                            (memory_status.llm_api_key_env or "Graphiti LLM API key", memory_status.llm_api_key_configured),
                        )
                        if not configured
                    ],
                }
            )

        if not mutation_gate.get("open"):
            blockers.append(
                {
                    **mutation_gate.get("blocker", {}),
                    "scope": "mutation_gate",
                    "status": "confirmation_required",
                }
            )

        status = "ready" if not blockers else "blocked"
        return LiveProviderDogfoodReadinessResponse(
            status=status,
            profile=profile,
            selected_executor_id=_effective_executor_id(request),
            require_repo_write_executor=require_repo_write,
            mutation_gate=mutation_gate,
            selected_executor_preflight=executor_preflight,
            repo_write_executor_candidates=repo_write_candidates,
            provider_prerequisites={
                "ticket_backend": ticket_status.model_dump(mode="json"),
                "plane_ticket_backend_setup": plane_ticket_setup,
                "memory_backend": memory_status.model_dump(mode="json"),
                "provider_smoke": {
                    "status": "not_run",
                    "reason": "readiness is read-only and does not call external provider smoke",
                },
            },
            blockers=blockers,
            summary={
                "profile": profile,
                "blocker_count": len(blockers),
                "repo_write_candidate_count": len(repo_write_candidates),
                "repo_write_ready_count": repo_write_ready_count,
                "ticket_backend_status": ticket_status.status,
                "ticket_backend_mode": ticket_status.mode,
                "ticket_backend_provider": ticket_status.provider,
                "plane_ticket_backend_selected": plane_ticket_backend_selected,
                "plane_ticket_backend_setup_status": plane_ticket_setup["status"],
                "plane_ticket_backend_setup_required": plane_ticket_setup["setup_required"],
                "plane_ticket_backend_configured": plane_ticket_setup["configured"],
                "plane_ticket_workspace_configured": plane_ticket_setup["workspace_configured"],
                "plane_ticket_project_configured": plane_ticket_setup["project_configured"],
                "plane_ticket_api_key_configured": plane_ticket_setup["api_key_configured"],
                "plane_ticket_scope_status": plane_ticket_setup["code_repository_scope_status"],
                "plane_ticket_scope_candidate_count": plane_ticket_setup["code_repository_scope_candidate_count"],
                "plane_ticket_scope_missing_count": plane_ticket_setup["code_repository_scope_missing_count"],
                "plane_ticket_scope_setup_action": plane_ticket_setup["code_repository_scope_setup_action"],
                "ticket_backend_release_target_status": str(ticket_release_target.get("status") or ""),
                "ticket_backend_release_target_ready": bool(ticket_release_target.get("ready")),
                "ticket_backend_release_target_blockers": _string_list(ticket_release_target.get("blockers")),
                "ticket_backend_release_target_setup_action": str(ticket_release_target.get("setup_action") or ""),
                "memory_backend_status": memory_status.status,
                "anti_wheel_boundary": "readiness reuses RuntimeExecutor health plus Ticket and Graphiti provider status",
            },
        )

    async def run(self, request: LiveProviderDogfoodRequest) -> LiveProviderDogfoodResponse:
        profile = normalize_live_dogfood_profile(request.profile)
        executor_preflight = await self._executor_preflight(request)
        gate = self._mutation_gate(request)
        if not gate["open"]:
            return LiveProviderDogfoodResponse(
                status="dry_run",
                profile=profile,
                dry_run=True,
                mutation_gate=gate,
                executor_preflight=executor_preflight,
                blockers=[gate["blocker"]],
                summary={
                    "would_mutate": [
                        "Plane Ticket",
                        "LangGraph Workbench thread/run",
                        "Runtime approval record",
                        "Ticket report/evidence",
                        "Asset candidate review",
                        "Graphiti projection and recall",
                    ],
                    "anti_wheel_boundary": "reuses LangGraph, RuntimeExecutor, Ticket, Assets, and Graphiti services",
                    "profile": profile,
                    "executor_preflight": executor_preflight,
                },
            )

        executor_blockers = executor_preflight.get("blockers") if isinstance(executor_preflight.get("blockers"), list) else []
        if executor_blockers:
            return LiveProviderDogfoodResponse(
                status="blocked",
                profile=profile,
                mutation_gate=gate,
                executor_preflight=executor_preflight,
                blockers=[item for item in executor_blockers if isinstance(item, dict)],
                summary={"blocked_before_mutation": True, "profile": profile, "executor_preflight": executor_preflight},
            )

        provider_smoke_payload: dict[str, Any] = {}
        if request.require_provider_smoke:
            provider_smoke_payload = await self._provider_smoke_payload(request)

        provider_blockers = self._provider_blockers(provider_smoke_payload) if request.require_provider_smoke else []
        if provider_blockers:
            return LiveProviderDogfoodResponse(
                status="blocked",
                profile=profile,
                mutation_gate=gate,
                provider_smoke=provider_smoke_payload,
                executor_preflight=executor_preflight,
                blockers=provider_blockers,
                summary={"blocked_before_mutation": True, "profile": profile},
            )

        blockers: list[dict[str, Any]] = []
        ticket = self._ensure_ticket(request)
        workbench_state = await self.workbench_runner(request, ticket)
        runtime_dogfood = await self._run_profile_dogfood(request, ticket, workbench_state)
        runtime_payload = runtime_dogfood.model_dump(mode="json")
        natural_handoff_blockers = _natural_handoff_blockers(
            request,
            _workbench_handoff_evidence(workbench_state, runtime_payload, request),
        )
        if runtime_dogfood.status != "completed":
            blockers.append(
                {
                    "reason": "runtime_dogfood_not_completed",
                    "detail": "RuntimeExecutor dogfood did not complete; no Asset review or Graphiti projection was attempted.",
                    "status": runtime_dogfood.status,
                    "dogfood_blockers": runtime_payload.get("blockers", []),
                }
            )
            return LiveProviderDogfoodResponse(
                status="blocked",
                profile=profile,
                mutation_gate=gate,
                ticket=ticket.model_dump(mode="json"),
                workbench=workbench_state,
                runtime_dogfood=runtime_payload,
                provider_smoke=provider_smoke_payload,
                executor_preflight=executor_preflight,
                blockers=blockers,
                summary=self._summary(ticket, workbench_state, runtime_payload, [], [], {}, blockers),
            )
        if natural_handoff_blockers:
            blockers.extend(natural_handoff_blockers)
            return LiveProviderDogfoodResponse(
                status="blocked",
                profile=profile,
                mutation_gate=gate,
                ticket=ticket.model_dump(mode="json"),
                workbench=workbench_state,
                runtime_dogfood=runtime_payload,
                provider_smoke=provider_smoke_payload,
                executor_preflight=executor_preflight,
                blockers=blockers,
                summary=self._summary(ticket, workbench_state, runtime_payload, [], [], {}, blockers),
            )

        memory_candidate_ids = _string_list(runtime_payload.get("learning_delta", {}).get("memory_candidate_ids"))
        if not memory_candidate_ids:
            blockers.append(
                {
                    "reason": "memory_candidate_missing",
                    "detail": "Completed runtime dogfood did not produce governed MemoryCandidate ids.",
                }
            )
            return LiveProviderDogfoodResponse(
                status="blocked",
                profile=profile,
                mutation_gate=gate,
                ticket=ticket.model_dump(mode="json"),
                workbench=workbench_state,
                runtime_dogfood=runtime_payload,
                provider_smoke=provider_smoke_payload,
                executor_preflight=executor_preflight,
                blockers=blockers,
                summary=self._summary(ticket, workbench_state, runtime_payload, [], [], {}, blockers),
            )

        asset_reviews: list[dict[str, Any]] = []
        graphiti_projections: list[dict[str, Any]] = []
        for memory_candidate_id in memory_candidate_ids:
            candidates = self._asset_candidates_for_memory(memory_candidate_id)
            if not candidates:
                blockers.append(
                    {
                        "reason": "asset_candidate_missing",
                        "detail": f"No Asset candidate was found for MemoryCandidate {memory_candidate_id}.",
                    }
                )
                continue
            candidate = candidates[0]
            reviewed = review_asset_candidate(
                candidate.id,
                AssetCandidateReviewRequest(
                    status="approved",
                    reviewer_employee_id=request.reviewer_employee_id,
                    reason="Live provider dogfood approved the governed memory candidate.",
                ),
            )
            review_payload = reviewed.model_dump(mode="json")
            asset_reviews.append(review_payload)
            try:
                approved_memory = await approve_memory_candidate(memory_candidate_id)
                review_payload["approved_memory"] = approved_memory.model_dump(mode="json")
            except Exception as exc:
                blockers.append(
                    {
                        "reason": "memory_candidate_approval_failed",
                        "detail": str(exc),
                        "memory_candidate_id": memory_candidate_id,
                    }
                )
                continue
            if reviewed.asset is None:
                blockers.append(
                    {
                        "reason": "asset_record_missing_after_review",
                        "detail": f"Asset candidate {candidate.id} did not produce an AssetRecord.",
                    }
                )
                continue
            try:
                projected = await project_asset_record_to_graphiti(reviewed.asset.id)
                graphiti_projections.append(projected.model_dump(mode="json"))
            except Exception as exc:
                blockers.append(
                    {
                        "reason": "graphiti_projection_failed",
                        "detail": str(exc),
                        "asset_id": reviewed.asset.id,
                    }
                )

        recall_payload = await self._recall(request, ticket, asset_reviews=asset_reviews)
        recalled_asset_ids = _recalled_asset_ids(recall_payload)
        graphiti_recalled_asset_ids = _recalled_asset_ids(recall_payload, source="graphiti")
        projected_asset_ids = {
            str(item.get("asset_id") or "")
            for item in graphiti_projections
            if isinstance(item, dict) and item.get("status") in {"ingested", "skipped"}
        }
        if projected_asset_ids and not (projected_asset_ids & graphiti_recalled_asset_ids):
            blockers.append(
                {
                    "reason": "graphiti_recall_missing_projected_asset",
                    "detail": "Graphiti recall did not return the projected AssetRecord.",
                    "projected_asset_ids": sorted(projected_asset_ids),
                    "recalled_asset_ids": sorted(recalled_asset_ids),
                    "graphiti_recalled_asset_ids": sorted(graphiti_recalled_asset_ids),
                }
            )

        status = "completed" if not blockers else "blocked"
        return LiveProviderDogfoodResponse(
            status=status,
            profile=profile,
            mutation_gate=gate,
            ticket=ticket.model_dump(mode="json"),
            workbench=workbench_state,
            runtime_dogfood=runtime_payload,
            asset_reviews=asset_reviews,
            graphiti_projections=graphiti_projections,
            recall=recall_payload,
            provider_smoke=provider_smoke_payload,
            executor_preflight=executor_preflight,
            blockers=blockers,
            summary=self._summary(ticket, workbench_state, runtime_payload, asset_reviews, graphiti_projections, recall_payload, blockers),
        )

    async def _provider_smoke(self) -> Any:
        return await provider_environment_smoke(include_external=True)

    async def _executor_preflight(self, request: LiveProviderDogfoodRequest) -> dict[str, Any]:
        profile = normalize_live_dogfood_profile(request.profile)
        executor_id = _effective_executor_id(request)
        require_repo_write = _effective_require_repo_write(request)
        dispatch = ExecutionDispatchService()
        try:
            executor = dispatch.executors.get(executor_id)
            if executor is None:
                return {
                    "profile": profile,
                    "executor_id": executor_id,
                    "status": "blocked",
                    "blockers": [
                        {
                            "reason": "runtime_executor_not_registered",
                            "detail": f"RuntimeExecutor is not registered: {executor_id}",
                        }
                    ],
                }
            capabilities = sorted(str(item) for item in getattr(executor, "capabilities", set()))
            if require_repo_write and "repo:write" not in capabilities:
                return {
                    "profile": profile,
                    "executor_id": executor_id,
                    "status": "blocked",
                    "capabilities": capabilities,
                    "health": {"status": "not_checked", "reason": "repo_write_capability_missing"},
                    "blockers": [
                        {
                            "reason": "runtime_executor_lacks_repo_write",
                            "detail": (
                                f"Live provider dogfood requires a repo:write RuntimeExecutor; "
                                f"{executor_id} capabilities do not include repo:write."
                            ),
                            "setup_required": ["select a ready RuntimeExecutor with repo:write"],
                        }
                    ],
                }
            health = await executor.health()
            status = str(health.get("status") or "unknown")
            blockers = []
            if status != "ready":
                blockers.append(
                    {
                        "reason": "runtime_executor_not_ready",
                        "detail": str(health.get("detail") or f"RuntimeExecutor {executor_id} is not ready."),
                        "status": status,
                        "setup_required": [str(item) for item in health.get("missing_env", []) if str(item).strip()]
                        if isinstance(health.get("missing_env"), list)
                        else [],
                    }
                )
            return {
                "executor_id": executor_id,
                "profile": profile,
                "status": "passed" if not blockers else "blocked",
                "capabilities": capabilities,
                "health": _dump(health),
                "require_repo_write_executor": require_repo_write,
                "blockers": blockers,
            }
        finally:
            await dispatch.aclose()

    async def _repo_write_executor_candidates(self) -> list[dict[str, Any]]:
        dispatch = ExecutionDispatchService()
        try:
            candidates: list[dict[str, Any]] = []
            for executor_id, executor in sorted(dispatch.executors.items()):
                capabilities = sorted(str(item) for item in getattr(executor, "capabilities", set()))
                if "repo:write" not in capabilities:
                    continue
                try:
                    health = await executor.health()
                except Exception as exc:  # pragma: no cover - defensive status read.
                    health = {
                        "executor_id": executor_id,
                        "display_name": getattr(executor, "display_name", executor_id),
                        "status": "error",
                        "detail": str(exc),
                        "capabilities": capabilities,
                    }
                status = str(health.get("status") or "unknown")
                setup_required = _setup_required_from_health(health)
                candidates.append(
                    {
                        "executor_id": str(health.get("executor_id") or executor_id),
                        "display_name": str(health.get("display_name") or getattr(executor, "display_name", executor_id)),
                        "status": status,
                        "detail": str(health.get("detail") or ""),
                        "capabilities": [str(item) for item in health.get("capabilities", capabilities)],
                        "setup_required": setup_required,
                        "ready": status == "ready",
                        "health": _dump(health),
                    }
                )
            return candidates
        finally:
            await dispatch.aclose()

    async def _provider_smoke_payload(self, request: LiveProviderDogfoodRequest) -> dict[str, Any]:
        timeout = max(1.0, float(request.provider_smoke_timeout_seconds or 60.0))
        try:
            return _dump(await asyncio.wait_for(self.provider_smoke_runner(), timeout=timeout))
        except TimeoutError:
            return {
                "status": "timeout",
                "blockers": [
                    {
                        "reason": "provider_smoke_timeout",
                        "detail": f"Read-only provider smoke did not finish within {timeout:.0f}s.",
                    }
                ],
                "provider_smoke": {"results": []},
            }

    def _mutation_gate(self, request: LiveProviderDogfoodRequest) -> dict[str, Any]:
        env_value = os.environ.get(request.confirm_env_var, "")
        open_gate = bool(request.execute and env_value == "1")
        blocker = {
            "reason": "live_provider_dogfood_not_confirmed",
            "detail": f"Pass --execute and set {request.confirm_env_var}=1 to mutate live Plane / Graphiti provider state.",
            "setup_required": ["--execute", f"{request.confirm_env_var}=1"],
        }
        return {
            "open": open_gate,
            "execute_flag": request.execute,
            "confirm_env_var": request.confirm_env_var,
            "confirm_env_configured": env_value == "1",
            "blocker": {} if open_gate else blocker,
        }

    def _provider_blockers(self, provider_smoke_payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not provider_smoke_payload:
            return []
        direct_blockers = provider_smoke_payload.get("blockers")
        if provider_smoke_payload.get("status") == "timeout" and isinstance(direct_blockers, list):
            return [item for item in direct_blockers if isinstance(item, dict)]
        provider_smoke = provider_smoke_payload.get("provider_smoke")
        results = provider_smoke.get("results") if isinstance(provider_smoke, dict) else []
        by_provider = {
            str(item.get("provider_id") or ""): item
            for item in results
            if isinstance(item, dict)
        }
        blockers: list[dict[str, Any]] = []
        for provider_id in ("ticket:plane", "memory:graphiti"):
            item = by_provider.get(provider_id)
            if not item:
                blockers.append(
                    {
                        "reason": "provider_smoke_missing",
                        "detail": f"Provider smoke result missing for {provider_id}.",
                    }
                )
                continue
            if item.get("status") != "passed":
                blockers.append(
                    {
                        "reason": "provider_smoke_not_passed",
                        "provider_id": provider_id,
                        "status": item.get("status"),
                        "detail": item.get("detail") or item.get("blockers") or item.get("failures") or "Provider smoke did not pass.",
                    }
                )
        return blockers

    def _ensure_ticket(self, request: LiveProviderDogfoodRequest) -> Ticket:
        if request.ticket_id.strip():
            ticket = get_ticket(request.ticket_id.strip())
            if ticket is None:
                raise ValueError(f"Ticket not found for live provider dogfood: {request.ticket_id}")
            return ticket
        if not request.create_ticket_if_missing:
            raise ValueError("ticket_id is required when create_ticket_if_missing=false.")
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return create_ticket(
            TicketCreateRequest(
                title=f"AITeamOS live provider dogfood {timestamp}",
                description=(
                    "Opt-in plan_v7 live provider dogfood Ticket. This Ticket records the "
                    "LangGraph core loop or explicit repo-write adapter evidence through "
                    "Chat -> Employee -> Ticket -> Approval -> Assets -> Graphiti -> Recall."
                ),
                ticket_type="ops",
                assigned_employee_id=request.worker_employee_id,
                assigned_role="AI RD / Implementer",
                validation_employee_id="peter",
                validation_role="AI PV",
                code_repository_ids=self._repository_ids(request),
                source_thread_id=f"live-provider-dogfood-{timestamp}",
                source_run_id=f"live-provider-dogfood-{timestamp}",
                actor_employee_id=request.employee_id,
                actor_role="AI Team OS Manager",
            )
        )

    async def _run_langgraph_workbench(self, request: LiveProviderDogfoodRequest, ticket: Ticket) -> dict[str, Any]:
        def run_sync() -> dict[str, Any]:
            from langgraph_sdk import get_sync_client

            client = get_sync_client(url=request.langgraph_url)
            try:
                thread = client.threads.create(metadata={"source": "aiteamos_live_provider_dogfood", "ticket_id": ticket.id})
                thread_id = _thread_id(thread)
                state = client.runs.wait(
                    thread_id,
                    request.assistant_id,
                    input={
                        "messages": [{"role": "user", "content": request.message}],
                        "ticket_key": ticket.id,
                        "employee_id": request.employee_id,
                    },
                    config={
                        "configurable": {
                            "thread_id": f"live-provider-dogfood-{ticket.id}",
                            "target_employee_id": request.employee_id,
                            "employee_id": request.employee_id,
                            "ticket_key": ticket.id,
                        }
                    },
                )
                payload = _dump(state)
                handoff_evidence = _workbench_handoff_evidence(payload)
                return {
                    "thread_id": thread_id,
                    "assistant_id": request.assistant_id,
                    "langgraph_url": request.langgraph_url,
                    "state": payload,
                    "active_ticket": payload.get("active_ticket") if isinstance(payload, dict) else {},
                    "runtime_status": payload.get("runtime_status") if isinstance(payload, dict) else {},
                    "handoff_decision": handoff_evidence.get("decision", {}),
                    "handoff_summary": handoff_evidence.get("summary", {}),
                    "ticket_handoff_refs": handoff_evidence.get("ticket_handoff_refs", []),
                }
            finally:
                close = getattr(client, "close", None)
                if close is not None:
                    close()

        return await asyncio.to_thread(run_sync)

    async def _run_profile_dogfood(
        self,
        request: LiveProviderDogfoodRequest,
        ticket: Ticket,
        workbench_state: dict[str, Any],
    ) -> RuntimeExecutorDogfoodResponse:
        profile = normalize_live_dogfood_profile(request.profile)
        if profile == CORE_LOOP_PROFILE:
            return await self._run_core_loop_dogfood(request, ticket, workbench_state)
        if profile not in SUPPORTED_LIVE_DOGFOOD_PROFILES:
            return RuntimeExecutorDogfoodResponse(
                status="blocked",
                ticket=ticket.model_dump(mode="json"),
                blockers=[_unsupported_profile_blocker(profile)],
            )
        return await self.runtime_dogfood_runner(request, ticket)

    async def _run_core_loop_dogfood(
        self,
        request: LiveProviderDogfoodRequest,
        ticket: Ticket,
        workbench_state: dict[str, Any],
    ) -> RuntimeExecutorDogfoodResponse:
        runtime_status = workbench_state.get("runtime_status") if isinstance(workbench_state.get("runtime_status"), dict) else {}
        status = str(runtime_status.get("status") or "").strip().lower()
        workbench_error = _workbench_error_evidence(workbench_state)
        if workbench_error or not status:
            return RuntimeExecutorDogfoodResponse(
                status="blocked",
                ticket=ticket.model_dump(mode="json"),
                blockers=[
                    {
                        "reason": "core_loop_workbench_not_completed",
                        "detail": "LangGraph Workbench did not provide completed runtime evidence for the core-loop dogfood run.",
                        "workbench_runtime_status": runtime_status,
                        "workbench_error": workbench_error,
                    }
                ],
            )
        if status and status != "completed":
            return RuntimeExecutorDogfoodResponse(
                status="blocked",
                ticket=ticket.model_dump(mode="json"),
                blockers=[
                    {
                        "reason": "core_loop_workbench_not_completed",
                        "detail": "LangGraph Workbench did not complete the core-loop dogfood run.",
                        "workbench_runtime_status": runtime_status,
                    }
                ],
            )

        execution_evidence = _workbench_execution_evidence(workbench_state)
        execution_status = str(execution_evidence.get("status") or "").strip().lower()
        if execution_status and execution_status not in {"completed", "partial"}:
            handoff_evidence = _workbench_handoff_evidence(workbench_state, request=request)
            return RuntimeExecutorDogfoodResponse(
                status="blocked",
                ticket=ticket.model_dump(mode="json"),
                blockers=[
                    {
                        "reason": "core_loop_execution_not_completed",
                        "detail": "LangGraph Workbench reached a final node, but the governed execution result did not complete.",
                        "workbench_execution_status": execution_status,
                        "workbench_execution_errors": execution_evidence.get("errors", []),
                        "natural_handoff": handoff_evidence,
                    }
                ],
                learning_delta={
                    "dogfood_profile": CORE_LOOP_PROFILE,
                    "natural_handoff": handoff_evidence,
                },
            )

        thread_id = str(workbench_state.get("thread_id") or runtime_status.get("thread_id") or "").strip()
        source_run_id = str(runtime_status.get("run_id") or thread_id or f"core-loop-dogfood-{ticket.id}").strip()
        report = add_ticket_report(
            ticket.id,
            TicketReportRequest(
                reporter_employee_id=request.employee_id,
                reporter_role="AI Team OS Manager",
                report_type="core_loop_dogfood",
                source_run_id=source_run_id,
                content=(
                    "LangGraph core-loop dogfood completed through the AITeamOS Workbench. "
                    "This report records the Ticket-bound core-loop evidence before Asset review and Graphiti projection."
                ),
                evidence=[
                    value
                    for value in [
                        f"langgraph_thread:{thread_id}" if thread_id else "",
                        f"langgraph_assistant:{request.assistant_id}",
                        "llm_provider:deepseek",
                        f"workbench_runtime_status:{status or 'unknown'}",
                    ]
                    if value
                ],
            ),
        )
        source_report_id = report.reports[-1].id if report.reports else ""
        evidence_id = report.reports[-1].evidence[0] if report.reports and report.reports[-1].evidence else ""
        handoff_evidence = _workbench_handoff_evidence(workbench_state, request=request)
        candidate = create_memory_candidate(
            MemoryCandidateCreateRequest(
                content=_core_loop_memory_content(request, ticket, workbench_state),
                source_kind="langgraph_core_loop_dogfood",
                source_ref=thread_id or source_run_id,
                scope_kind="ticket",
                scope_ref=ticket.id,
                memory_type="summary",
                confidence=0.9,
                employee_ids=[request.employee_id, request.worker_employee_id, request.reviewer_employee_id],
                tags=["plan-v7", "core-loop", "langgraph", "deepseek", "live-provider-dogfood"],
                provenance={
                    "source_ticket_id": ticket.id,
                    "source_employee_id": request.employee_id,
                    "source_run_id": source_run_id,
                    "source_report_id": source_report_id,
                    "evidence_id": evidence_id,
                    "thread_id": thread_id,
                    "assistant_id": request.assistant_id,
                    "dogfood_profile": CORE_LOOP_PROFILE,
                    "executor_id": _effective_executor_id(request),
                    "llm_provider": "deepseek",
                    "provider_refs": [
                        {"provider": "langgraph", "thread_id": thread_id, "assistant_id": request.assistant_id},
                        {"provider": "deepseek", "role": "model_provider"},
                    ],
                    "natural_handoff": handoff_evidence,
                    "why_should_be_remembered": (
                        "Plan v7 core-loop dogfood proved LangGraph, not a repo-write adapter, "
                        "as the autonomous team-loop entrypoint."
                    ),
                    "future_recall_query_hints": [
                        "plan v7 core loop",
                        "langgraph deepseek dogfood",
                        "natural employee handoff",
                        ticket.id,
                    ],
                },
            )
        )
        return RuntimeExecutorDogfoodResponse(
            status="completed",
            ticket=report.model_dump(mode="json"),
            approval={"status": "not_required", "reason": "core-loop dogfood is non-repo-write evidence"},
            approved_run={
                "profile": CORE_LOOP_PROFILE,
                "executor_id": _effective_executor_id(request),
                "thread_id": thread_id,
                "assistant_id": request.assistant_id,
                "llm_provider": "deepseek",
            },
            summary_report={
                "ticket_id": ticket.id,
                "report_id": source_report_id,
                "evidence": report.reports[-1].evidence if report.reports else [],
            },
            learning_delta={
                "dogfood_profile": CORE_LOOP_PROFILE,
                "memory_candidate_ids": [candidate.id],
                "core_loop": {
                    "langgraph_thread_id": thread_id,
                    "assistant_id": request.assistant_id,
                    "llm_provider": "deepseek",
                },
                "natural_handoff": handoff_evidence,
            },
        )

    async def _run_runtime_dogfood(self, request: LiveProviderDogfoodRequest, ticket: Ticket) -> RuntimeExecutorDogfoodResponse:
        service = RuntimeExecutorSmokeService(workspace_dir=self.workspace_dir)
        return await service.dogfood(
            RuntimeExecutorDogfoodRequest(
                executor_id=_effective_executor_id(request),
                message=request.message,
                employee_id=request.worker_employee_id,
                reviewer_employee_id=request.reviewer_employee_id,
                workspace_id=str(self.workspace_dir),
                ticket_id=ticket.id,
                create_ticket_if_missing=False,
                repository_ids=self._repository_ids(request),
                smoke_executor_ids=[_effective_executor_id(request)],
            )
        )

    def _repository_ids(self, request: LiveProviderDogfoodRequest) -> list[str]:
        if request.repository_ids:
            return request.repository_ids
        return [repo.id for repo in list_code_repositories() if repo.enabled and repo.status == "ready"][:3]

    def _asset_candidates_for_memory(self, memory_candidate_id: str) -> list[Any]:
        return [
            candidate
            for candidate in list_asset_candidates(status="proposed")
            if candidate.source_candidate_id == memory_candidate_id
            or candidate.asset_id == memory_candidate_id
            or candidate.provenance.get("source_memory_candidate_id") == memory_candidate_id
        ]

    async def _recall(
        self,
        request: LiveProviderDogfoodRequest,
        ticket: Ticket,
        *,
        asset_reviews: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        asset_reviews = asset_reviews or []
        expected_asset_ids = {
            str(item.get("asset", {}).get("id") or "")
            for item in asset_reviews
            if isinstance(item.get("asset"), dict)
        }
        queries = _unique_strings(
            [
                request.recall_query,
                request.message,
                *self._targeted_recall_queries(asset_reviews),
            ]
        )
        attempts: list[dict[str, Any]] = []
        selected_payload: dict[str, Any] = {}
        for query in queries:
            recalled = await search_memory(
                query=query,
                employee_id=request.employee_id,
                ticket_key=ticket.id,
                limit=10,
                include_graphiti=True,
            )
            payload = recalled.model_dump(mode="json")
            graphiti_matches = sorted(expected_asset_ids & _recalled_asset_ids(payload, source="graphiti"))
            attempts.append(
                {
                    "query": query,
                    "result_count": len(payload.get("results", [])) if isinstance(payload.get("results"), list) else 0,
                    "graphiti_projected_asset_matches": graphiti_matches,
                }
            )
            selected_payload = payload
            if not expected_asset_ids or graphiti_matches:
                break
        selected_payload["attempts"] = attempts
        selected_payload["expected_asset_ids"] = sorted(expected_asset_ids)
        return selected_payload

    def _targeted_recall_queries(self, asset_reviews: list[dict[str, Any]]) -> list[str]:
        queries: list[str] = []
        for item in asset_reviews:
            asset = item.get("asset") if isinstance(item.get("asset"), dict) else {}
            candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            provenance = asset.get("provenance") if isinstance(asset.get("provenance"), dict) else {}
            for value in (
                asset.get("content"),
                asset.get("title"),
                asset.get("id"),
                provenance.get("approval_id"),
                provenance.get("source_report_id"),
                candidate.get("content"),
                candidate.get("title"),
            ):
                text = str(value or "").strip()
                if text:
                    queries.append(text[:240])
        return queries

    def _summary(
        self,
        ticket: Ticket,
        workbench_state: dict[str, Any],
        runtime_payload: dict[str, Any],
        asset_reviews: list[dict[str, Any]],
        graphiti_projections: list[dict[str, Any]],
        recall_payload: dict[str, Any],
        blockers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        handoff_evidence = _workbench_handoff_evidence(workbench_state, runtime_payload)
        return {
            "dogfood_profile": str(runtime_payload.get("learning_delta", {}).get("dogfood_profile") or REPO_WRITE_ADAPTER_PROFILE),
            "ticket_id": ticket.id,
            "provider": ticket.provider_ref.provider if ticket.provider_ref else "local_file",
            "provider_record_id": ticket.provider_ref.provider_record_id if ticket.provider_ref else "",
            "langgraph_thread_id": workbench_state.get("thread_id", ""),
            "workbench_runtime_status": workbench_state.get("runtime_status", {}),
            "runtime_dogfood_status": runtime_payload.get("status", ""),
            "approval_id": runtime_payload.get("approval", {}).get("id", ""),
            "memory_candidate_ids": _string_list(runtime_payload.get("learning_delta", {}).get("memory_candidate_ids")),
            "asset_record_ids": [
                str(item.get("asset", {}).get("id") or "")
                for item in asset_reviews
                if isinstance(item.get("asset"), dict)
            ],
            "graphiti_projection_statuses": [str(item.get("status") or "") for item in graphiti_projections],
            "recall_result_count": len(recall_payload.get("results", [])) if isinstance(recall_payload.get("results"), list) else 0,
            "graphiti_recall_count": len(
                [
                    item
                    for item in recall_payload.get("results", [])
                    if isinstance(item, dict) and item.get("source") == "graphiti"
                ]
            )
            if isinstance(recall_payload.get("results"), list)
            else 0,
            "natural_handoff": bool(handoff_evidence.get("complete")),
            "natural_handoff_required": bool(handoff_evidence.get("required")),
            "expected_handoff_target_employee_id": str(handoff_evidence.get("expected_target_employee_id") or ""),
            "handoff_status": str(handoff_evidence.get("status") or ""),
            "handoff_target_employee_id": str(handoff_evidence.get("target_employee_id") or ""),
            "handoff_lane": str(handoff_evidence.get("lane") or ""),
            "handoff_reason": str(handoff_evidence.get("reason") or ""),
            "handoff_ref_count": int(handoff_evidence.get("ref_count") or 0),
            "handoff_refs": handoff_evidence.get("ticket_handoff_refs", []),
            "blocker_count": len(blockers),
        }


def normalize_live_dogfood_profile(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"", "core", "core_loop", "langgraph", "langgraph_core_loop"}:
        return CORE_LOOP_PROFILE
    if normalized in {"repo", "repo_write", "repo_write_adapter", "runtime_executor", "external_runtime"}:
        return REPO_WRITE_ADAPTER_PROFILE
    return normalized


def _unsupported_profile_blocker(profile: str) -> dict[str, Any]:
    return {
        "reason": "unsupported_live_dogfood_profile",
        "detail": f"Unsupported live dogfood profile: {profile}",
        "setup_required": [f"select one of: {', '.join(sorted(SUPPORTED_LIVE_DOGFOOD_PROFILES))}"],
    }


def _effective_executor_id(request: LiveProviderDogfoodRequest) -> str:
    profile = normalize_live_dogfood_profile(request.profile)
    executor_id = request.executor_id.strip().replace("-", "_")
    if executor_id:
        return executor_id
    if profile == REPO_WRITE_ADAPTER_PROFILE:
        return "codex_cli"
    return "langgraph"


def _effective_require_repo_write(request: LiveProviderDogfoodRequest) -> bool:
    if request.require_repo_write_executor is not None:
        return bool(request.require_repo_write_executor)
    return normalize_live_dogfood_profile(request.profile) == REPO_WRITE_ADAPTER_PROFILE


def _core_loop_memory_content(
    request: LiveProviderDogfoodRequest,
    ticket: Ticket,
    workbench_state: dict[str, Any],
) -> str:
    runtime_status = workbench_state.get("runtime_status") if isinstance(workbench_state.get("runtime_status"), dict) else {}
    active_ticket = workbench_state.get("active_ticket") if isinstance(workbench_state.get("active_ticket"), dict) else {}
    handoff_evidence = _workbench_handoff_evidence(workbench_state)
    lines = [
        "Plan v7 LangGraph core-loop dogfood completed.",
        f"Ticket: {ticket.id} - {ticket.title}",
        f"Employee entrypoint: {request.employee_id}",
        "Default LLM provider: DeepSeek through LangGraph / LangChain model-provider wiring.",
        f"LangGraph assistant: {request.assistant_id}",
        f"LangGraph thread: {str(workbench_state.get('thread_id') or runtime_status.get('thread_id') or '').strip()}",
        f"Workbench runtime status: {runtime_status.get('status') or 'unknown'}",
        f"Workbench active ticket: {active_ticket.get('id') or ticket.id}",
        f"Natural handoff: {handoff_evidence.get('status') or 'not_applicable'} -> {handoff_evidence.get('target_employee_id') or 'none'}",
        "Codex CLI and other repo-write adapters were not used as the core-loop proof.",
        f"User dogfood message: {_compact_text(request.message, 400)}",
    ]
    return "\n".join(line for line in lines if line.strip())


def _workbench_handoff_evidence(
    workbench_state: dict[str, Any],
    runtime_payload: dict[str, Any] | None = None,
    request: LiveProviderDogfoodRequest | None = None,
) -> dict[str, Any]:
    runtime_payload = runtime_payload or {}
    learning_delta = runtime_payload.get("learning_delta") if isinstance(runtime_payload.get("learning_delta"), dict) else {}
    learned = learning_delta.get("natural_handoff") if isinstance(learning_delta.get("natural_handoff"), dict) else {}
    containers = [
        learned,
        workbench_state,
        workbench_state.get("state") if isinstance(workbench_state.get("state"), dict) else {},
    ]
    decision: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    refs: list[dict[str, Any]] = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        if not decision:
            decision = _dict_value(container.get("handoff_decision")) or _dict_value(container.get("decision"))
        if not summary:
            summary = _dict_value(container.get("handoff_summary")) or _dict_value(container.get("summary"))
        if not refs:
            refs = _dict_list(container.get("ticket_handoff_refs")) or _dict_list(container.get("handoff_refs"))
    status = str(summary.get("status") or learned.get("status") or "").strip()
    target = str(
        decision.get("target_employee_id")
        or summary.get("to_employee_id")
        or summary.get("target_employee_id")
        or learned.get("target_employee_id")
        or ""
    ).strip()
    lane = str(decision.get("lane") or summary.get("lane") or learned.get("lane") or "").strip()
    reason = str(decision.get("reason") or learned.get("reason") or "").strip()
    ref_count = _safe_int(summary.get("handoff_ref_count") or learned.get("ref_count")) or len(refs)
    expected_target = str(
        (request.expected_handoff_target_employee_id if request is not None else "")
        or learned.get("expected_target_employee_id")
        or ""
    ).strip()
    complete = status == "durable_handoff_recorded" and bool(target) and ref_count >= 1
    if expected_target:
        complete = complete and target == expected_target
    if not complete:
        ledger = _ticket_ledger_handoff_evidence(
            containers=containers,
            source_run_id=_workbench_source_run_id(containers),
            expected_target=expected_target or target,
        )
        if ledger:
            decision = decision or ledger.get("decision", {})
            summary = {**summary, **ledger.get("summary", {})}
            refs = refs or _dict_list(ledger.get("ticket_handoff_refs"))
            status = str(summary.get("status") or status).strip()
            target = str(summary.get("to_employee_id") or summary.get("target_employee_id") or target).strip()
            lane = str(summary.get("lane") or lane).strip()
            reason = str(decision.get("reason") or reason).strip()
            ref_count = len(refs) or _safe_int(summary.get("handoff_ref_count"))
            complete = status == "durable_handoff_recorded" and bool(target) and ref_count >= 1
            if expected_target:
                complete = complete and target == expected_target
    return {
        "status": status,
        "target_employee_id": target,
        "expected_target_employee_id": expected_target,
        "lane": lane,
        "reason": reason,
        "ref_count": ref_count,
        "ticket_handoff_refs": refs,
        "decision": decision,
        "summary": summary,
        "required": bool(request.require_natural_handoff) if request is not None else bool(learned.get("required")),
        "complete": complete,
    }


def _workbench_execution_evidence(workbench_state: dict[str, Any]) -> dict[str, Any]:
    containers = [
        workbench_state,
        workbench_state.get("state") if isinstance(workbench_state.get("state"), dict) else {},
    ]
    response: dict[str, Any] = {}
    for container in containers:
        response = _dict_value(container.get("aiteamos_chat_response"))
        if response:
            break
    metadata = _dict_value(response.get("run_metadata"))
    execution = _dict_value(metadata.get("execution"))
    result = _dict_value(execution.get("result"))
    return {
        "status": str(execution.get("status") or "").strip(),
        "request_id": str(execution.get("request_id") or "").strip(),
        "executor_id": str(execution.get("executor_id") or "").strip(),
        "errors": _dict_list(result.get("errors")),
        "error_count": _safe_int(result.get("error_count")),
        "artifact_refs": _dict_list(result.get("artifact_refs")),
        "ticket_report_refs": _dict_list(result.get("ticket_report_refs")),
    }


def _workbench_error_evidence(workbench_state: dict[str, Any]) -> dict[str, Any]:
    containers = [
        workbench_state,
        workbench_state.get("state") if isinstance(workbench_state.get("state"), dict) else {},
    ]
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in ("__error__", "error"):
            value = container.get(key)
            if isinstance(value, dict):
                return value
            if value:
                return {"message": str(value)}
    return {}


def _workbench_source_run_id(containers: list[dict[str, Any]]) -> str:
    for container in containers:
        if not isinstance(container, dict):
            continue
        runtime_status = _dict_value(container.get("runtime_status"))
        response = _dict_value(container.get("aiteamos_chat_response"))
        execution = _dict_value(_dict_value(response.get("run_metadata")).get("execution"))
        for value in (
            runtime_status.get("run_id"),
            runtime_status.get("request_id"),
            execution.get("request_id"),
        ):
            text = str(value or "").strip()
            if text:
                return text
    return ""


def _ticket_ledger_handoff_evidence(
    *,
    containers: list[dict[str, Any]],
    source_run_id: str,
    expected_target: str,
) -> dict[str, Any]:
    ticket_id = ""
    for container in containers:
        if not isinstance(container, dict):
            continue
        summary = _dict_value(container.get("handoff_summary")) or _dict_value(container.get("summary"))
        runtime_status = _dict_value(container.get("runtime_status"))
        active_ticket = _dict_value(container.get("active_ticket"))
        for value in (
            summary.get("ticket_id"),
            runtime_status.get("ticket_id"),
            active_ticket.get("id"),
        ):
            ticket_id = str(value or "").strip()
            if ticket_id:
                break
        if ticket_id:
            break
    if not ticket_id:
        return {}
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return {}
    expected = expected_target.strip()
    for event in reversed(ticket.events):
        if event.type != "handoff_requested":
            continue
        data = event.data if isinstance(event.data, dict) else {}
        if source_run_id and str(data.get("source_run_id") or "").strip() != source_run_id:
            continue
        target = str(data.get("to_employee_id") or "").strip()
        if expected and target and target != expected:
            continue
        ref = {
            "kind": "ticket_handoff",
            "ticket_id": ticket.id,
            "event_id": event.event_id,
            "to_employee_id": target,
            "to_role": str(data.get("to_role") or "").strip(),
            "source_run_id": str(data.get("source_run_id") or "").strip(),
            "source": "ticket_ledger",
        }
        return {
            "decision": {
                "target_employee_id": target,
                "target_role": ref["to_role"],
                "reason": str(data.get("content") or "").strip(),
                "source": "ticket_ledger",
            },
            "summary": {
                "status": "durable_handoff_recorded",
                "ticket_id": ticket.id,
                "from_employee_id": str(data.get("from_employee_id") or "").strip(),
                "to_employee_id": target,
                "to_role": ref["to_role"],
                "handoff_ref_count": 1,
                "source": "ticket_ledger",
            },
            "ticket_handoff_refs": [ref],
        }
    return {}


def _natural_handoff_blockers(
    request: LiveProviderDogfoodRequest,
    handoff_evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    if not request.require_natural_handoff:
        return []
    target = str(handoff_evidence.get("target_employee_id") or "")
    expected = str(handoff_evidence.get("expected_target_employee_id") or "")
    status = str(handoff_evidence.get("status") or "")
    ref_count = int(handoff_evidence.get("ref_count") or 0)
    if status != "durable_handoff_recorded" or not target or ref_count < 1:
        return [
            {
                "reason": "live_provider_natural_handoff_missing",
                "detail": "Core-loop live dogfood did not produce a durable Ticket-backed Employee handoff.",
                "handoff_status": status,
                "handoff_target_employee_id": target,
                "handoff_ref_count": ref_count,
            }
        ]
    if expected and target != expected:
        return [
            {
                "reason": "live_provider_natural_handoff_target_mismatch",
                "detail": f"Core-loop live dogfood handed off to {target}, expected {expected}.",
                "handoff_status": status,
                "handoff_target_employee_id": target,
                "expected_handoff_target_employee_id": expected,
                "handoff_ref_count": ref_count,
            }
        ]
    return []


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return _unique_strings([str(item).strip() for item in value if str(item).strip()]) if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _plane_ticket_backend_setup_summary(
    settings: TicketBackendSettings,
    status: TicketBackendStatus,
) -> dict[str, Any]:
    scope_summary = _plane_ticket_repository_scope_summary()
    api_key_env = settings.plane_api_key_env.strip() or "PLANE_API_KEY"
    selected = status.mode == "plane" and status.provider in {"", "plane"}
    workspace_configured = bool(settings.plane_workspace_slug.strip())
    project_configured = bool(settings.plane_project_id.strip())
    api_key_configured = bool(os.environ.get(api_key_env))
    setup_required: list[str] = []
    if not selected:
        setup_required.extend(["PUT /api/v1/tickets/backend mode=plane", ".aiteamos/tickets/backend.json mode=plane"])
    if not workspace_configured:
        setup_required.append("plane_workspace_slug")
    if not project_configured:
        setup_required.append("plane_project_id")
    if not api_key_configured:
        setup_required.append(api_key_env)
    configured = workspace_configured and project_configured and api_key_configured
    detail = "Plane Ticket backend is selected and configured."
    if not selected and not configured:
        detail = "Plane Ticket backend is not selected and Plane workspace/project setup is incomplete."
    elif not selected:
        detail = "Plane Ticket backend setup is configured, but the active Ticket backend mode is not Plane."
    elif not configured:
        detail = "Plane Ticket backend is selected, but Plane workspace/project setup is incomplete."
    return {
        "status": "ready" if selected and configured else "setup_blocked",
        "detail": detail,
        "selected": selected,
        "configured": configured,
        "active_mode": status.mode,
        "active_provider": status.provider,
        "required_mode": "plane",
        "workspace_configured": workspace_configured,
        "project_configured": project_configured,
        "api_key_env": api_key_env,
        "api_key_configured": api_key_configured,
        "setup_required": setup_required,
        "settings_path": settings.saved_paths.get("settings", ".aiteamos/tickets/backend.json"),
        "setup_endpoint": "/api/v1/tickets/backend",
        **scope_summary,
    }


def _plane_ticket_repository_scope_summary() -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for repository in list_code_repositories():
        if not repository.enabled:
            continue
        workspace = repository.plane_workspace_slug.strip()
        project = repository.plane_project_id.strip()
        status = repository.status.strip() or "unknown"
        base = {
            "source": "code_repository",
            "repository_id": repository.id,
            "repository_name": repository.name,
            "provider": repository.provider,
            "status": status,
            "workspace_configured": bool(workspace),
            "project_configured": bool(project),
            "deep_link": "#/settings/code-repositories",
        }
        if workspace and project:
            candidates.append(
                {
                    **base,
                    "plane_workspace_slug": workspace,
                    "plane_project_id": project,
                }
            )
        elif status in {"ready", "configured", "available"} or workspace or project:
            missing.append(base)
    candidate_count = len(candidates)
    missing_count = len(missing)
    candidate_status = "available" if candidate_count else "incomplete" if missing_count else "missing"
    if candidate_count:
        detail = "Code Repository registry has Plane workspace/project scope candidates."
        setup_action = "apply_code_repository_plane_scope_to_ticket_backend"
    elif missing_count:
        detail = "Code Repository registry has repositories, but none has both Plane workspace and project configured."
        setup_action = "add_plane_scope_to_code_repository_or_ticket_backend"
    else:
        detail = "No enabled Code Repository can provide a Plane workspace/project scope candidate."
        setup_action = "configure_plane_scope_in_ticket_backend"
    return {
        "code_repository_scope_status": candidate_status,
        "code_repository_scope_detail": detail,
        "code_repository_scope_candidate_count": candidate_count,
        "code_repository_scope_missing_count": missing_count,
        "code_repository_scope_candidates": candidates[:5],
        "code_repository_scope_missing": missing[:5],
        "code_repository_scope_setup_action": setup_action,
    }


def live_provider_readiness_projection(readiness: LiveProviderDogfoodReadinessResponse) -> dict[str, Any]:
    """Compact readiness evidence for UI/API surfaces without exposing provider secrets."""

    blockers = _compact_readiness_blockers(readiness.blockers)
    repo_write_candidates = _compact_repo_write_candidates(readiness.repo_write_executor_candidates)
    provider_prerequisites = readiness.provider_prerequisites if isinstance(readiness.provider_prerequisites, dict) else {}
    provider_smoke = provider_prerequisites.get("provider_smoke") if isinstance(provider_prerequisites.get("provider_smoke"), dict) else {}
    ticket_backend = provider_prerequisites.get("ticket_backend") if isinstance(provider_prerequisites.get("ticket_backend"), dict) else {}
    release_target = ticket_backend.get("release_target") if isinstance(ticket_backend.get("release_target"), dict) else {}
    plane_ticket_setup = (
        provider_prerequisites.get("plane_ticket_backend_setup")
        if isinstance(provider_prerequisites.get("plane_ticket_backend_setup"), dict)
        else {}
    )
    memory_backend = provider_prerequisites.get("memory_backend") if isinstance(provider_prerequisites.get("memory_backend"), dict) else {}
    return {
        "status": readiness.status,
        "profile": readiness.profile,
        "selected_executor_id": readiness.selected_executor_id,
        "require_repo_write_executor": readiness.require_repo_write_executor,
        "mutation_gate": {
            "open": bool(readiness.mutation_gate.get("open")),
            "confirm_env_var": str(readiness.mutation_gate.get("confirm_env_var") or ""),
            "confirm_env_configured": bool(readiness.mutation_gate.get("confirm_env_configured")),
        },
        "provider_prerequisites": {
            "ticket_backend_status": str(ticket_backend.get("status") or ""),
            "ticket_backend_mode": str(ticket_backend.get("mode") or ""),
            "ticket_backend_provider": str(ticket_backend.get("provider") or ""),
            "plane_ticket_backend_selected": bool(readiness.summary.get("plane_ticket_backend_selected")),
            "plane_ticket_backend_setup_status": str(plane_ticket_setup.get("status") or ""),
            "plane_ticket_backend_setup_required": _string_list(plane_ticket_setup.get("setup_required")),
            "plane_ticket_scope_status": str(plane_ticket_setup.get("code_repository_scope_status") or ""),
            "plane_ticket_scope_candidate_count": _safe_int(plane_ticket_setup.get("code_repository_scope_candidate_count")),
            "plane_ticket_scope_missing_count": _safe_int(plane_ticket_setup.get("code_repository_scope_missing_count")),
            "ticket_backend_release_target_status": str(release_target.get("status") or ""),
            "ticket_backend_release_target_ready": bool(release_target.get("ready")),
            "ticket_backend_release_target_blockers": _string_list(release_target.get("blockers")),
            "ticket_backend_release_target_setup_action": str(release_target.get("setup_action") or ""),
            "memory_backend_status": str(memory_backend.get("status") or ""),
            "provider_smoke_status": str(provider_smoke.get("status") or ""),
        },
        "reasons": _unique_reasons(readiness.blockers),
        "setup_required": _unique_setup_required(readiness.blockers),
        "blockers": blockers,
        "repo_write_candidates": repo_write_candidates,
        "summary": {
            "blocker_count": len(blockers),
            "repo_write_ready_count": readiness.summary.get("repo_write_ready_count"),
            "repo_write_candidate_count": readiness.summary.get("repo_write_candidate_count"),
            "ticket_backend_status": readiness.summary.get("ticket_backend_status"),
            "ticket_backend_mode": readiness.summary.get("ticket_backend_mode"),
            "ticket_backend_provider": readiness.summary.get("ticket_backend_provider"),
            "plane_ticket_backend_selected": readiness.summary.get("plane_ticket_backend_selected"),
            "plane_ticket_backend_setup_status": readiness.summary.get("plane_ticket_backend_setup_status"),
            "plane_ticket_backend_setup_required": readiness.summary.get("plane_ticket_backend_setup_required"),
            "plane_ticket_backend_configured": readiness.summary.get("plane_ticket_backend_configured"),
            "plane_ticket_workspace_configured": readiness.summary.get("plane_ticket_workspace_configured"),
            "plane_ticket_project_configured": readiness.summary.get("plane_ticket_project_configured"),
            "plane_ticket_api_key_configured": readiness.summary.get("plane_ticket_api_key_configured"),
            "plane_ticket_scope_status": readiness.summary.get("plane_ticket_scope_status"),
            "plane_ticket_scope_candidate_count": readiness.summary.get("plane_ticket_scope_candidate_count"),
            "plane_ticket_scope_missing_count": readiness.summary.get("plane_ticket_scope_missing_count"),
            "ticket_backend_release_target_status": readiness.summary.get("ticket_backend_release_target_status"),
            "ticket_backend_release_target_ready": readiness.summary.get("ticket_backend_release_target_ready"),
            "ticket_backend_release_target_blockers": readiness.summary.get("ticket_backend_release_target_blockers"),
            "ticket_backend_release_target_setup_action": readiness.summary.get("ticket_backend_release_target_setup_action"),
            "memory_backend_status": readiness.summary.get("memory_backend_status"),
            "anti_wheel_boundary": readiness.summary.get("anti_wheel_boundary"),
        },
    }


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    return value if isinstance(value, dict) else {"value": value}


def _thread_id(thread: Any) -> str:
    if isinstance(thread, dict):
        return str(thread.get("thread_id") or thread.get("id") or "")
    return str(getattr(thread, "thread_id", "") or getattr(thread, "id", ""))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _compact_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _recalled_asset_ids(recall_payload: dict[str, Any], *, source: str = "") -> set[str]:
    results = recall_payload.get("results")
    if not isinstance(results, list):
        return set()
    normalized_source = source.strip()
    ids: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        if normalized_source and str(result.get("source") or "") != normalized_source:
            continue
        provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
        value = str(provenance.get("asset_id") or result.get("id") or "").strip()
        if value:
            ids.add(value)
    return ids


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _compact_readiness_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for index, blocker in enumerate(blockers):
        if not isinstance(blocker, dict):
            continue
        reason = str(blocker.get("reason") or blocker.get("id") or f"blocker_{index + 1}").strip()
        compact.append(
            {
                "reason": reason,
                "scope": str(blocker.get("scope") or "").strip(),
                "status": str(blocker.get("status") or "blocked").strip(),
                "detail": str(blocker.get("detail") or "").strip(),
                "setup_required": _unique_strings(_string_list(blocker.get("setup_required")))[:6],
            }
        )
        if len(compact) >= 8:
            break
    return compact


def _compact_repo_write_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        compact.append(
            {
                "executor_id": str(candidate.get("executor_id") or "").strip(),
                "display_name": str(candidate.get("display_name") or "").strip(),
                "status": str(candidate.get("status") or "unknown").strip(),
                "ready": bool(candidate.get("ready")),
                "setup_required": _unique_strings(_string_list(candidate.get("setup_required")))[:6],
            }
        )
        if len(compact) >= 8:
            break
    return compact


def _unique_reasons(blockers: list[dict[str, Any]]) -> list[str]:
    return _unique_strings([blocker.get("reason") for blocker in blockers if isinstance(blocker, dict)])


def _setup_required_from_health(health: dict[str, Any]) -> list[str]:
    if str(health.get("status") or "").strip() == "ready":
        return []
    missing_env = health.get("missing_env")
    if isinstance(missing_env, list) and missing_env:
        return [str(item).strip() for item in missing_env if str(item).strip()]
    configured = health.get("configured")
    if not isinstance(configured, dict):
        return []
    return [
        str(key).replace("_", " ")
        for key, value in configured.items()
        if value is False
    ][:8]


def _unique_setup_required(items: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    required: list[str] = []
    for item in items:
        setup_required = item.get("setup_required")
        if not isinstance(setup_required, list):
            continue
        for setup_item in setup_required:
            value = str(setup_item).strip()
            if value and value not in seen:
                seen.add(value)
                required.append(value)
    return required
