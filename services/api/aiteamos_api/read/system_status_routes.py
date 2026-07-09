"""System Status read routes."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .execution_dispatch_service import ExecutionDispatchService
from .live_provider_dogfood_service import (
    LiveProviderDogfoodReadinessResponse,
    LiveProviderDogfoodRequest,
    LiveProviderDogfoodService,
    live_provider_readiness_projection,
)
from .live_provider_soak_evidence_service import LiveProviderSoakEvidenceResponse, live_provider_soak_evidence_report
from .live_provider_soak_plan_service import LiveProviderSoakPlanResponse, live_provider_soak_plan_report
from .memory_service import GRAPHITI_NEO4J_PASSWORD_SETUP_LABEL, GraphitiBackendStatus, graphiti_backend_status
from .plan_v8_artifact_service import PlanV8ArtifactSummary, plan_v8_artifact_summary
from .plan_v8_readiness_service import PlanV8ReadinessResponse, plan_v8_readiness_report
from .provider_conformance_service import (
    EnvironmentSmokeResponse,
    ProviderConformanceCheckResponse,
    ProviderConformanceResponse,
    ProviderConformanceSmokeResponse,
    provider_environment_smoke,
    provider_conformance_checks,
    provider_conformance_report,
    provider_conformance_smoke,
)
from .release_hygiene_service import ReleaseHygieneResponse, release_hygiene_report
from .schema_registry_service import SchemaRegistryResponse, schema_registry_report
from .ticket_service import TicketBackendStatus, ticket_backend_settings, ticket_backend_status

router = APIRouter(prefix="/api/v1/system-status", tags=["system-status"])


class SystemStatusSecretItem(BaseModel):
    id: str
    scope: str
    purpose: str
    env_vars: list[str] = Field(default_factory=list)
    required_for: str
    configured: bool
    how_to_configure: str


class SystemStatusBlocker(BaseModel):
    id: str
    scope: str
    status: str
    detail: str
    setup_required: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    related_blockers: list[dict[str, Any]] = Field(default_factory=list)
    related_candidates: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class SystemStatusResponse(BaseModel):
    secrets: list[SystemStatusSecretItem]
    ticket_backend: TicketBackendStatus | None = None
    memory_backend: GraphitiBackendStatus | None = None
    runtime_executors: list[dict[str, Any]] = Field(default_factory=list)
    live_provider_dogfood: LiveProviderDogfoodReadinessResponse | None = None
    live_provider_soak_plan: LiveProviderSoakPlanResponse | None = None
    live_provider_soak_evidence: LiveProviderSoakEvidenceResponse | None = None
    provider_conformance: ProviderConformanceResponse | None = None
    schema_registry: SchemaRegistryResponse | None = None
    plan_v8_artifacts: PlanV8ArtifactSummary | None = None
    plan_v8_readiness: PlanV8ReadinessResponse | None = None
    release_hygiene: ReleaseHygieneResponse | None = None
    blockers: list[SystemStatusBlocker] = Field(default_factory=list)


def _configured(env_vars: list[str]) -> bool:
    return any(bool(os.environ.get(name)) for name in env_vars)


def _secret_item(
    *,
    item_id: str,
    scope: str,
    purpose: str,
    env_vars: list[str],
    required_for: str,
) -> SystemStatusSecretItem:
    return SystemStatusSecretItem(
        id=item_id,
        scope=scope,
        purpose=purpose,
        env_vars=env_vars,
        required_for=required_for,
        configured=_configured(env_vars),
        how_to_configure=f"Set {' or '.join(env_vars)} in the server environment before starting AITeamOS.",
    )


def _runtime_setup_required(executor_status: dict[str, Any]) -> list[str]:
    missing_env = executor_status.get("missing_env")
    if isinstance(missing_env, list) and missing_env:
        return [str(item).strip() for item in missing_env if str(item).strip()]
    configured = executor_status.get("configured")
    if not isinstance(configured, dict):
        return []
    required = [
        str(key).replace("_", " ")
        for key, value in configured.items()
        if value is False
    ]
    return required[:6]


def _runtime_diagnostics(executor_status: dict[str, Any]) -> dict[str, Any]:
    executor_id = str(executor_status.get("executor_id") or "runtime_executor").strip()
    diagnostics: dict[str, Any] = {
        "smoke": {
            "endpoint": f"/api/v1/runtime-executors/{executor_id}/smoke",
            "method": "POST",
            "default_ingest_result": False,
            "ingest_requires_ticket": True,
            "mode": "non_destructive_inspect_and_report",
            "dispatch_boundary": "RuntimeExecutor",
        }
    }
    capabilities = executor_status.get("capabilities")
    if isinstance(capabilities, list) and "repo:write" in capabilities:
        diagnostics["dogfood"] = {
            "endpoint": "/api/v1/runtime-executors/dogfood",
            "method": "POST",
            "creates_ticket_if_missing": True,
            "approval_required": True,
            "ingest_requires_ticket": True,
            "repo_mutation_guard": ["ticket_bound", "approval_bound", "evidence_bound"],
            "dispatch_boundary": "RuntimeExecutor",
        }
    return diagnostics


@router.get("", response_model=SystemStatusResponse)
async def get_system_status() -> SystemStatusResponse:
    ticket_settings = ticket_backend_settings()
    ticket_status = ticket_backend_status()
    memory_status = graphiti_backend_status()
    plane_api_key_env = ticket_settings.plane_api_key_env.strip() or "PLANE_API_KEY"
    dispatch_service = ExecutionDispatchService()
    try:
        runtime_executors = [
            {
                **(executor_status := await executor.health()),
                "diagnostics": _runtime_diagnostics(executor_status),
            }
            for executor in dispatch_service.executors.values()
        ]
    finally:
        await dispatch_service.aclose()
    live_provider_dogfood = await LiveProviderDogfoodService().readiness(LiveProviderDogfoodRequest(execute=True))
    provider_conformance = await provider_conformance_report(runtime_statuses=runtime_executors)
    schema_registry = schema_registry_report()
    plan_v8_artifacts = plan_v8_artifact_summary()
    release_hygiene = release_hygiene_report()
    live_provider_soak_plan = await live_provider_soak_plan_report(
        readiness=live_provider_dogfood,
        artifacts=plan_v8_artifacts,
    )
    live_provider_soak_evidence = await live_provider_soak_evidence_report(plan=live_provider_soak_plan)
    plan_v8_readiness = await plan_v8_readiness_report(
        artifacts=plan_v8_artifacts,
        release_hygiene=release_hygiene,
        schema_registry=schema_registry,
        provider_conformance=provider_conformance,
        live_provider_dogfood=live_provider_dogfood,
    )
    blockers: list[SystemStatusBlocker] = []
    if ticket_status.status != "ready":
        blockers.append(
            SystemStatusBlocker(
                id="ticket_backend",
                scope="Ticket Backend",
                status=ticket_status.status,
                detail=ticket_status.detail,
                setup_required=ticket_status.setup_required,
            )
        )
    if memory_status.status != "ready":
        blockers.append(
            SystemStatusBlocker(
                id="memory_asset_graph_backend",
                scope="Memory / Asset Graph Backend",
                status=memory_status.status,
                detail=memory_status.detail,
                setup_required=[
                    name
                    for name, configured in (
                        ("Graphiti URI/user", memory_status.graph_configured),
                        (GRAPHITI_NEO4J_PASSWORD_SETUP_LABEL, memory_status.password_configured),
                        (memory_status.llm_api_key_env or "selected Graphiti LLM API key", memory_status.llm_api_key_configured),
                    )
                    if not configured
                ],
            )
        )
    for executor_status in runtime_executors:
        status = str(executor_status.get("status") or "")
        if status in {"ready", "unknown"}:
            continue
        executor_id = str(executor_status.get("executor_id") or "runtime_executor").strip()
        blockers.append(
            SystemStatusBlocker(
                id=f"runtime_executor:{executor_id}",
                scope=f"Runtime Executor: {executor_id.replace('_', ' ')}",
                status=status,
                detail=str(executor_status.get("detail") or "Runtime executor setup is incomplete."),
                setup_required=_runtime_setup_required(executor_status),
            )
        )
    if live_provider_dogfood.status != "ready":
        readiness_projection = live_provider_readiness_projection(live_provider_dogfood)
        blockers.append(
            SystemStatusBlocker(
                id="live_provider_dogfood",
                scope="Live Provider Dogfood",
                status=live_provider_dogfood.status,
                detail=(
                    "The full Chat -> Employee -> Ticket -> Approval -> Assets -> Graphiti -> Recall "
                    f"loop is not executable yet ({len(live_provider_dogfood.blockers)} blockers)."
                ),
                setup_required=[str(item) for item in readiness_projection.get("setup_required", [])][:10],
                reasons=[str(item) for item in readiness_projection.get("reasons", [])],
                related_blockers=[
                    item for item in readiness_projection.get("blockers", [])
                    if isinstance(item, dict)
                ],
                related_candidates=[
                    item for item in readiness_projection.get("repo_write_candidates", [])
                    if isinstance(item, dict)
                ],
                summary={
                    "profile": readiness_projection.get("profile"),
                    "selected_executor_id": readiness_projection.get("selected_executor_id"),
                    "repo_write_ready_count": readiness_projection.get("summary", {}).get("repo_write_ready_count")
                    if isinstance(readiness_projection.get("summary"), dict)
                    else None,
                    "repo_write_candidate_count": readiness_projection.get("summary", {}).get("repo_write_candidate_count")
                    if isinstance(readiness_projection.get("summary"), dict)
                    else None,
                    "mutation_gate_open": readiness_projection.get("mutation_gate", {}).get("open")
                    if isinstance(readiness_projection.get("mutation_gate"), dict)
                    else None,
                    "provider_smoke_status": readiness_projection.get("provider_prerequisites", {}).get("provider_smoke_status")
                    if isinstance(readiness_projection.get("provider_prerequisites"), dict)
                    else None,
                    "plane_ticket_scope_status": readiness_projection.get("provider_prerequisites", {}).get("plane_ticket_scope_status")
                    if isinstance(readiness_projection.get("provider_prerequisites"), dict)
                    else None,
                    "plane_ticket_scope_candidate_count": readiness_projection.get("provider_prerequisites", {}).get("plane_ticket_scope_candidate_count")
                    if isinstance(readiness_projection.get("provider_prerequisites"), dict)
                    else None,
                    "plane_ticket_scope_missing_count": readiness_projection.get("provider_prerequisites", {}).get("plane_ticket_scope_missing_count")
                    if isinstance(readiness_projection.get("provider_prerequisites"), dict)
                    else None,
                },
            )
        )
    return SystemStatusResponse(
        ticket_backend=ticket_status,
        memory_backend=memory_status,
        runtime_executors=runtime_executors,
        live_provider_dogfood=live_provider_dogfood,
        live_provider_soak_plan=live_provider_soak_plan,
        live_provider_soak_evidence=live_provider_soak_evidence,
        provider_conformance=provider_conformance,
        schema_registry=schema_registry,
        plan_v8_artifacts=plan_v8_artifacts,
        plan_v8_readiness=plan_v8_readiness,
        release_hygiene=release_hygiene,
        blockers=blockers,
        secrets=[
            _secret_item(
                item_id="deepseek_api_key",
                scope="AI Engines",
                purpose="DeepSeek LLM API key.",
                env_vars=["DEEPSEEK_API_KEY"],
                required_for="DeepSeek AI Engine execution.",
            ),
            _secret_item(
                item_id="openai_api_key",
                scope="AI Engines / Memory / Asset Graph Backend",
                purpose="OpenAI API key for the OpenAI AI Engine; Graphiti uses this env when that AI Engine is selected.",
                env_vars=["OPENAI_API_KEY"],
                required_for="OpenAI AI Engine execution and Graphiti ingestion when OpenAI is selected.",
            ),
            _secret_item(
                item_id="graphiti_neo4j_password",
                scope="Memory / Asset Graph Backend",
                purpose="Neo4j password for Graphiti Memory / Asset Graph Backend.",
                env_vars=["AITEAMOS_GRAPHITI_PASSWORD", "NEO4J_PASSWORD", "AITEAMOS_NEO4J_PASSWORD"],
                required_for="Graphiti graph database connection.",
            ),
            _secret_item(
                item_id="plane_api_key",
                scope="Ticket Backend",
                purpose="Plane API key when Plane is selected as the Ticket Backend.",
                env_vars=[plane_api_key_env],
                required_for="Plane-backed ticket sync.",
            ),
            _secret_item(
                item_id="jira_api_token",
                scope="Ticket Backend",
                purpose="Jira API token when Jira is selected as a Ticket Backend.",
                env_vars=["AITEAMOS_JIRA_API_TOKEN"],
                required_for="Jira-backed ticket sync.",
            ),
            _secret_item(
                item_id="github_token",
                scope="Tool Connectors / Code Repositories",
                purpose="GitHub token for repository, issue, and pull request connectors.",
                env_vars=["AITEAMOS_GITHUB_TOKEN", "GITHUB_TOKEN"],
                required_for="GitHub connector calls.",
            ),
            _secret_item(
                item_id="ci_harness_token",
                scope="Tool Connectors",
                purpose="Token for external CI or harness connector calls.",
                env_vars=["AITEAMOS_CI_HARNESS_TOKEN"],
                required_for="CI or harness connector execution.",
            ),
            _secret_item(
                item_id="anthropic_api_key",
                scope="Runtime Executors",
                purpose="Anthropic API key for Claude Agent SDK handoff.",
                env_vars=["ANTHROPIC_API_KEY"],
                required_for="Claude Agent SDK runtime adapter.",
            ),
            _secret_item(
                item_id="claude_code_bin",
                scope="Runtime Executors",
                purpose="Local Claude Code-compatible CLI binary path.",
                env_vars=["CLAUDE_CODE_BIN"],
                required_for="Claude Code-compatible local RuntimeExecutor handoff.",
            ),
            _secret_item(
                item_id="cursor_api_key",
                scope="Runtime Executors",
                purpose="Cursor commercial agent backend API key.",
                env_vars=["CURSOR_API_KEY"],
                required_for="Cursor RuntimeExecutor handoff.",
            ),
            _secret_item(
                item_id="openhands_base_url",
                scope="Runtime Executors",
                purpose="OpenHands runtime service URL.",
                env_vars=["OPENHANDS_BASE_URL"],
                required_for="OpenHands RuntimeExecutor handoff.",
            ),
            _secret_item(
                item_id="opencode_bin",
                scope="Runtime Executors",
                purpose="OpenCode official/local CLI binary path.",
                env_vars=["OPENCODE_BIN"],
                required_for="OpenCode RuntimeExecutor handoff.",
            ),
        ]
    )


@router.get("/providers", response_model=ProviderConformanceResponse)
async def get_provider_conformance() -> ProviderConformanceResponse:
    """Return read-only provider adapter conformance across Ticket, Asset, Memory, Employee, and Runtime providers."""

    return await provider_conformance_report()


@router.get("/providers/checks", response_model=ProviderConformanceCheckResponse)
async def get_provider_conformance_checks() -> ProviderConformanceCheckResponse:
    """Evaluate provider adapter conformance metadata without calling external providers."""

    return await provider_conformance_checks()


@router.get("/providers/smoke", response_model=ProviderConformanceSmokeResponse)
async def get_provider_conformance_smoke(include_external: bool = False) -> ProviderConformanceSmokeResponse:
    """Run non-destructive provider adapter smoke checks without mutating AITeamOS facts."""

    return await provider_conformance_smoke(include_external=include_external)


@router.get("/environment-smoke", response_model=EnvironmentSmokeResponse)
async def get_environment_smoke(include_external: bool = False) -> EnvironmentSmokeResponse:
    """Run read-only environment readiness smoke across AI Engine, providers, fallback, and LangGraph runtime."""

    return await provider_environment_smoke(include_external=include_external)


@router.get("/schema", response_model=SchemaRegistryResponse)
async def get_schema_registry() -> SchemaRegistryResponse:
    """Return read-only schema and migration readiness for AITeamOS local ledgers."""

    return schema_registry_report()


@router.get("/plan-v8-artifacts", response_model=PlanV8ArtifactSummary)
async def get_plan_v8_artifacts() -> PlanV8ArtifactSummary:
    """Return read-only v8 artifact evidence summary."""

    return plan_v8_artifact_summary()


@router.get("/plan-v8-readiness", response_model=PlanV8ReadinessResponse)
async def get_plan_v8_readiness() -> PlanV8ReadinessResponse:
    """Return the aggregate Plan v8 release readiness checklist."""

    return await plan_v8_readiness_report()


@router.get("/live-provider-soak-plan", response_model=LiveProviderSoakPlanResponse)
async def get_live_provider_soak_plan() -> LiveProviderSoakPlanResponse:
    """Return the read-only repeated live-provider soak plan for Plan v8."""

    return await live_provider_soak_plan_report()


@router.get("/live-provider-soak-evidence", response_model=LiveProviderSoakEvidenceResponse)
async def get_live_provider_soak_evidence() -> LiveProviderSoakEvidenceResponse:
    """Return the read-only repeated live-provider soak evidence coverage for Plan v8."""

    return await live_provider_soak_evidence_report()


@router.get("/release-hygiene", response_model=ReleaseHygieneResponse)
async def get_release_hygiene() -> ReleaseHygieneResponse:
    """Return read-only release hygiene classification for the current git worktree."""

    return release_hygiene_report()
