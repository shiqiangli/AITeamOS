"""Provider adapter conformance read model for AITeamOS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .ai_engine_config_store import ai_engine_secrets, load_ai_engine_config
from .ai_engine_runtime_config import AiEngineRuntimeConfig
from .execution_dispatch_service import ExecutionDispatchService
from .memory_service import GRAPHITI_NEO4J_PASSWORD_SETUP_LABEL, graphiti_backend_status, graphiti_provider_external_smoke
from .runtime_boundary_audit_service import runtime_boundary_audit_report
from .ticket_service import ticket_backend_status, ticket_provider_external_smoke


PROVIDER_CONFORMANCE_VERSION = "provider_conformance.v1"


class ProviderSetupBlocker(BaseModel):
    id: str
    status: str
    detail: str
    setup_required: list[str] = Field(default_factory=list)


class ProviderContractExpectation(BaseModel):
    id: str
    category: str
    required: list[str] = Field(default_factory=list)
    satisfied: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    status: str = "passed"


class ProviderProductionEvaluation(BaseModel):
    schema_version: str = PROVIDER_CONFORMANCE_VERSION
    migration_status: str = "schema_current"
    required_for_core: bool = False
    production_ready: bool = False
    readiness_level: str = "unknown"
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProviderConformanceRecord(BaseModel):
    provider_id: str
    provider_kind: str
    implementation: str
    display_name: str
    selected: bool = True
    status: str
    detail: str = ""
    setup_blockers: list[ProviderSetupBlocker] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    conformance_smoke: dict[str, Any] = Field(default_factory=dict)
    projection_direction: list[str] = Field(default_factory=list)
    failure_semantics: list[str] = Field(default_factory=list)
    domain_boundary: list[str] = Field(default_factory=list)
    contract_expectations: list[ProviderContractExpectation] = Field(default_factory=list)
    production_evaluation: ProviderProductionEvaluation = Field(default_factory=ProviderProductionEvaluation)
    fallback_provider: str = ""
    provider_ref: dict[str, Any] = Field(default_factory=dict)


class ProviderConformanceSummary(BaseModel):
    provider_count: int = 0
    ready_count: int = 0
    blocked_count: int = 0
    selected_provider_count: int = 0
    core_required_count: int = 0
    production_ready_count: int = 0
    core_blocked_count: int = 0
    optional_warning_count: int = 0
    runtime_boundary_status: str = ""
    runtime_boundary_checks: list[str] = Field(default_factory=list)
    runtime_boundary_warnings: list[str] = Field(default_factory=list)
    runtime_boundary_blockers: list[str] = Field(default_factory=list)
    contract_version: str = PROVIDER_CONFORMANCE_VERSION
    core_model_boundary: str = "Ticket / Employee / Asset models remain AITeamOS-owned; providers are projections or execution adapters."


class ProviderConformanceResponse(BaseModel):
    contract_version: str = PROVIDER_CONFORMANCE_VERSION
    providers: list[ProviderConformanceRecord] = Field(default_factory=list)
    summary: ProviderConformanceSummary = Field(default_factory=ProviderConformanceSummary)


class ProviderConformanceCheckRecord(BaseModel):
    provider_id: str
    provider_kind: str
    status: str
    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class ProviderConformanceCheckResponse(BaseModel):
    contract_version: str = PROVIDER_CONFORMANCE_VERSION
    status: str
    checks: list[ProviderConformanceCheckRecord] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class ProviderConformanceSmokeRecord(BaseModel):
    provider_id: str
    provider_kind: str
    implementation: str
    status: str
    detail: str = ""
    smoke_kind: str = ""
    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    external_calls: bool = False


class ProviderConformanceSmokeResponse(BaseModel):
    contract_version: str = PROVIDER_CONFORMANCE_VERSION
    status: str
    results: list[ProviderConformanceSmokeRecord] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class EnvironmentSmokeCheckRecord(BaseModel):
    id: str
    scope: str
    status: str
    detail: str = ""
    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    external_calls: bool = False


class EnvironmentSmokeResponse(BaseModel):
    contract_version: str = PROVIDER_CONFORMANCE_VERSION
    status: str
    checks: list[EnvironmentSmokeCheckRecord] = Field(default_factory=list)
    provider_smoke: ProviderConformanceSmokeResponse | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


async def provider_conformance_report(
    *,
    runtime_statuses: list[dict[str, Any]] | None = None,
) -> ProviderConformanceResponse:
    """Build a safe, read-only conformance view across active provider adapters."""

    providers = [
        _ticket_provider_record(),
        _asset_provider_record(),
        _employee_provider_record(),
        _memory_provider_record(),
    ]
    statuses = runtime_statuses if runtime_statuses is not None else await _runtime_statuses()
    runtime_boundary_audit = runtime_boundary_audit_report()
    providers.extend(_runtime_provider_records(statuses))
    providers = [_with_production_evaluation(provider) for provider in providers]
    ready_count = sum(1 for provider in providers if provider.status == "ready")
    blocked_count = sum(1 for provider in providers if provider.setup_blockers or _is_blocked_status(provider.status))
    production_ready_count = sum(1 for provider in providers if provider.production_evaluation.production_ready)
    core_blocked_count = sum(1 for provider in providers if provider.production_evaluation.required_for_core and not provider.production_evaluation.production_ready)
    optional_warning_count = sum(1 for provider in providers if not provider.production_evaluation.required_for_core and provider.production_evaluation.warnings)
    return ProviderConformanceResponse(
        providers=providers,
        summary=ProviderConformanceSummary(
            provider_count=len(providers),
            ready_count=ready_count,
            blocked_count=blocked_count,
            selected_provider_count=sum(1 for provider in providers if provider.selected),
            core_required_count=sum(1 for provider in providers if provider.production_evaluation.required_for_core),
            production_ready_count=production_ready_count,
            core_blocked_count=core_blocked_count,
            optional_warning_count=optional_warning_count,
            runtime_boundary_status=runtime_boundary_audit.status,
            runtime_boundary_checks=runtime_boundary_audit.summary.passed_checks,
            runtime_boundary_warnings=runtime_boundary_audit.warnings,
            runtime_boundary_blockers=runtime_boundary_audit.blockers,
        ),
    )


async def provider_conformance_checks() -> ProviderConformanceCheckResponse:
    """Evaluate provider conformance metadata without calling external providers."""

    report = await provider_conformance_report()
    checks = [_provider_check(provider) for provider in report.providers]
    failed = [item for item in checks if item.status == "failed"]
    warned = [item for item in checks if item.status == "warning"]
    status = "failed" if failed else "warning" if warned else "passed"
    return ProviderConformanceCheckResponse(
        status=status,
        checks=checks,
        summary={
            "provider_count": len(checks),
            "passed_count": len([item for item in checks if item.status == "passed"]),
            "warning_count": len(warned),
            "failed_count": len(failed),
            "contract_version": PROVIDER_CONFORMANCE_VERSION,
            "external_calls": False,
            "evaluation_scope": "metadata_contract_only",
        },
    )


async def provider_conformance_smoke(*, include_external: bool = False) -> ProviderConformanceSmokeResponse:
    """Run a non-destructive provider smoke harness without mutating AITeamOS facts."""

    report = await provider_conformance_report()
    results = [await _provider_smoke(provider, include_external=include_external) for provider in report.providers]
    failed = [item for item in results if item.status == "failed"]
    blocked = [item for item in results if item.blockers or _is_blocked_status(item.status)]
    warned = [item for item in results if item.warnings]
    return ProviderConformanceSmokeResponse(
        status="failed" if failed else "passed",
        results=results,
        summary={
            "provider_count": len(results),
            "passed_count": len([item for item in results if item.status == "passed"]),
            "blocked_count": len(blocked),
            "warning_count": len(warned),
            "failed_count": len(failed),
            "contract_version": PROVIDER_CONFORMANCE_VERSION,
            "external_calls": any(item.external_calls for item in results),
            "include_external": include_external,
            "evaluation_scope": "provider_status_and_adapter_health",
            "non_destructive": True,
        },
    )


async def provider_environment_smoke(*, include_external: bool = False) -> EnvironmentSmokeResponse:
    """Run a read-only environment readiness smoke over the core autonomous loop boundary."""

    report = await provider_conformance_report()
    provider_smoke = await provider_conformance_smoke(include_external=include_external)
    checks = [
        await _ai_engine_environment_smoke(),
        _provider_environment_smoke(provider_smoke),
        _local_fallback_environment_smoke(report),
        _agent_loop_environment_smoke(report),
    ]
    failed = [item for item in checks if item.failures or item.status == "failed"]
    blocked = [item for item in checks if item.blockers or item.status in {"setup_blocked", "disabled", "not_configured", "llm_not_configured"}]
    warned = [item for item in checks if item.warnings or item.status == "warning"]
    status = "failed" if failed else "setup_blocked" if blocked else "warning" if warned else "passed"
    return EnvironmentSmokeResponse(
        status=status,
        checks=checks,
        provider_smoke=provider_smoke,
        summary={
            "check_count": len(checks),
            "passed_count": len([item for item in checks if item.status == "passed"]),
            "blocked_count": len(blocked),
            "warning_count": len(warned),
            "failed_count": len(failed),
            "contract_version": PROVIDER_CONFORMANCE_VERSION,
            "external_calls": any(item.external_calls for item in checks) or bool(provider_smoke.summary.get("external_calls")),
            "include_external": include_external,
            "evaluation_scope": "environment_readiness_with_provider_smoke",
            "non_destructive": True,
            "core_boundary": "DeepSeek provider configuration, Ticket provider, Memory provider, local fallback, and LangGraph runtime readiness.",
        },
    )


async def _ai_engine_environment_smoke() -> EnvironmentSmokeCheckRecord:
    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).resolve()
    config = load_ai_engine_config(workspace_dir / ".aiteamos" / "ai_engines.json")
    runtime = AiEngineRuntimeConfig(config=config, secrets=ai_engine_secrets(config))
    configured = {
        "deepseek": runtime.remote_ai_engine_available("deepseek"),
        "openai": runtime.remote_ai_engine_available("openai"),
    }
    checks = ["langchain_model_provider_config_inspected", "deepseek_configuration_inspected", "no_external_llm_call"]
    blockers: list[dict[str, Any]] = []
    warnings: list[str] = []
    if configured.get("deepseek") is True:
        checks.append("deepseek_api_key_configured")
    else:
        blockers.append(
            {
                "id": "ai_engine:deepseek:setup",
                "status": "setup_blocked",
                "detail": "DeepSeek API key is not configured for the LangChain model provider.",
                "setup_required": ["DEEPSEEK_API_KEY"],
            }
        )
    if configured.get("openai") is True:
        checks.append("openai_api_key_configured")
    else:
        warnings.append("openai_api_key_not_configured")

    return EnvironmentSmokeCheckRecord(
        id="ai_engine:deepseek",
        scope="AI Engines",
        status="setup_blocked" if blockers else "passed",
        detail="Read-only DeepSeek LangChain model-provider readiness check. No model API call is made by this smoke.",
        checks=checks,
        warnings=warnings,
        blockers=blockers,
        evidence={
            "langchain_model_provider": {
                "selected_provider": "deepseek",
                "deepseek_model": runtime.deepseek_model(),
                "openai_model": runtime.openai_model(),
                "configured": {str(key): bool(value) for key, value in configured.items()},
                "missing_env": [
                    name
                    for name, ready in (("DEEPSEEK_API_KEY", configured["deepseek"]), ("OPENAI_API_KEY", configured["openai"]))
                    if not ready
                ],
                "provider_packages_required": ["langchain-deepseek", "langchain-openai"],
            }
        },
        external_calls=False,
    )


def _provider_environment_smoke(provider_smoke: ProviderConformanceSmokeResponse) -> EnvironmentSmokeCheckRecord:
    checks = ["provider_conformance_smoke_run", f"provider_smoke_status:{provider_smoke.status}"]
    warnings: list[str] = []
    failures: list[str] = []
    blockers: list[dict[str, Any]] = []
    provider_results: list[dict[str, Any]] = []
    for result in provider_smoke.results:
        provider_results.append(
            {
                "provider_id": result.provider_id,
                "provider_kind": result.provider_kind,
                "implementation": result.implementation,
                "status": result.status,
                "external_calls": result.external_calls,
            }
        )
        checks.append(f"provider:{result.provider_id}:{result.status}")
        failures.extend([f"{result.provider_id}:{failure}" for failure in result.failures])
        warnings.extend([f"{result.provider_id}:{warning}" for warning in result.warnings])
        if result.blockers or _provider_smoke_status_is_blocked(result.status):
            if _provider_smoke_blocks_core_readiness(result):
                blockers.extend(
                    {
                        **blocker,
                        "provider_id": result.provider_id,
                        "provider_kind": result.provider_kind,
                    }
                    for blocker in result.blockers
                )
                if not result.blockers:
                    blockers.append(
                        {
                            "id": f"{result.provider_id}:status",
                            "status": result.status,
                            "detail": result.detail or "Provider is not ready.",
                            "setup_required": [],
                            "provider_id": result.provider_id,
                            "provider_kind": result.provider_kind,
                        }
                    )
            else:
                warnings.append(f"optional_provider_setup_blocked:{result.provider_id}")
    if bool(provider_smoke.summary.get("include_external")):
        checks.append("external_provider_smoke_requested")
    else:
        checks.append("external_provider_smoke_not_requested")

    return EnvironmentSmokeCheckRecord(
        id="providers:core",
        scope="Provider Adapters",
        status="failed" if failures else "setup_blocked" if blockers else "warning" if warnings else "passed",
        detail="Aggregates provider adapter smoke while treating optional commercial runtimes as warnings.",
        checks=checks,
        warnings=warnings,
        failures=failures,
        blockers=blockers,
        evidence={
            "provider_summary": provider_smoke.summary,
            "provider_results": provider_results,
        },
        external_calls=any(result.external_calls for result in provider_smoke.results),
    )


def _local_fallback_environment_smoke(report: ProviderConformanceResponse) -> EnvironmentSmokeCheckRecord:
    providers = {provider.provider_id: provider for provider in report.providers}
    ticket_provider = next((provider for provider in report.providers if provider.provider_kind == "ticket"), None)
    memory_provider = providers.get("memory:graphiti")
    asset_provider = providers.get("asset:local_registry")
    employee_provider = providers.get("employee:local_profiles")
    checks = ["provider_conformance_report_read"]
    blockers: list[dict[str, Any]] = []

    if asset_provider is not None and asset_provider.status == "ready":
        checks.append("local_asset_registry_ready")
    else:
        blockers.append(_environment_blocker("fallback:asset_registry", "Local Asset Registry fallback is not ready.", ["asset:local_registry"]))

    if employee_provider is not None and employee_provider.status == "ready":
        checks.append("local_employee_profiles_ready")
    else:
        blockers.append(_environment_blocker("fallback:employee_profiles", "Local Employee profile provider is not ready.", ["employee:local_profiles"]))

    if ticket_provider is None:
        blockers.append(_environment_blocker("fallback:ticket_provider", "No Ticket provider is registered.", ["ticket provider"]))
    elif ticket_provider.implementation == "local_file" and ticket_provider.status == "ready":
        checks.append("local_ticket_provider_active")
    elif ticket_provider.fallback_provider == "ticket:local_file":
        checks.append("ticket_local_file_fallback_declared")
    else:
        blockers.append(_environment_blocker("fallback:ticket_local_file", "Ticket provider does not declare a local_file fallback.", ["ticket:local_file"]))

    if memory_provider is None:
        blockers.append(_environment_blocker("fallback:memory_provider", "No Memory provider is registered.", ["memory provider"]))
    elif memory_provider.status == "ready":
        checks.append("graphiti_memory_provider_ready")
    elif memory_provider.fallback_provider == "asset:local_registry" and asset_provider is not None and asset_provider.status == "ready":
        checks.append("memory_local_asset_fallback_available")
    else:
        blockers.append(_environment_blocker("fallback:memory_asset_registry", "Memory provider does not have a ready local Asset fallback.", ["asset:local_registry"]))

    return EnvironmentSmokeCheckRecord(
        id="fallback:local",
        scope="Local Fallback",
        status="setup_blocked" if blockers else "passed",
        detail="Verifies local AITeamOS-owned Ticket/Employee/Asset fallback paths remain available.",
        checks=checks,
        blockers=blockers,
        evidence={
            "ticket_provider": ticket_provider.provider_id if ticket_provider is not None else "",
            "memory_provider": memory_provider.provider_id if memory_provider is not None else "",
            "asset_provider": asset_provider.provider_id if asset_provider is not None else "",
            "employee_provider": employee_provider.provider_id if employee_provider is not None else "",
        },
        external_calls=False,
    )


def _agent_loop_environment_smoke(report: ProviderConformanceResponse) -> EnvironmentSmokeCheckRecord:
    providers = {provider.provider_id: provider for provider in report.providers}
    primary = providers.get("runtime:universal_employee_agent")
    fallback = providers.get("runtime:langgraph")
    selected = primary if primary is not None and primary.status == "ready" else fallback
    runtime_boundary_audit = runtime_boundary_audit_report()
    checks = [
        "runtime_provider_contract_read",
        "chat_route_bridge_boundary",
        "runtime_boundary_source_audited",
        *runtime_boundary_audit.summary.passed_checks,
    ]
    blockers: list[dict[str, Any]] = []
    warnings = list(runtime_boundary_audit.warnings)
    if runtime_boundary_audit.blockers:
        blockers.extend(
            _environment_blocker(
                f"runtime_boundary:{index}",
                blocker,
                ["Track B runtime boundary cleanup"],
            )
            for index, blocker in enumerate(runtime_boundary_audit.blockers, start=1)
        )
    if selected is not None and selected.status == "ready":
        checks.append(f"{selected.provider_id}_ready")
    elif primary is not None:
        blockers.extend(
            {
                **blocker.model_dump(mode="json"),
                "provider_id": primary.provider_id,
            }
            for blocker in primary.setup_blockers
        )
        if not blockers:
            blockers.append(_environment_blocker("runtime:universal_employee_agent:setup", "Universal Employee Agent runtime is not ready.", ["runtime:universal_employee_agent"]))
    elif fallback is not None:
        blockers.extend(
            {
                **blocker.model_dump(mode="json"),
                "provider_id": fallback.provider_id,
            }
            for blocker in fallback.setup_blockers
        )
        if not blockers:
            blockers.append(_environment_blocker("runtime:langgraph:setup", "LangGraph runtime is not ready.", ["runtime:langgraph"]))
    else:
        blockers.append(_environment_blocker("runtime:langgraph:missing", "LangGraph / Universal Employee Agent runtime provider is not registered.", ["runtime:universal_employee_agent", "runtime:langgraph"]))

    return EnvironmentSmokeCheckRecord(
        id="runtime:agent_loop",
        scope="LangGraph Agent Loop",
        status="setup_blocked" if blockers else "passed",
        detail="Verifies the core agent loop remains behind RuntimeExecutor/LangGraph instead of Chat route logic.",
        checks=checks,
        warnings=warnings,
        blockers=blockers,
        evidence={
            "universal_employee_agent": _runtime_provider_evidence(primary),
            "langgraph": _runtime_provider_evidence(fallback),
            "runtime_boundary_audit": runtime_boundary_audit.model_dump(mode="json"),
        },
        external_calls=False,
    )


def _environment_blocker(blocker_id: str, detail: str, setup_required: list[str]) -> dict[str, Any]:
    return {
        "id": blocker_id,
        "status": "setup_blocked",
        "detail": detail,
        "setup_required": setup_required,
    }


def _runtime_provider_evidence(provider: ProviderConformanceRecord | None) -> dict[str, Any]:
    if provider is None:
        return {}
    return {
        "provider_id": provider.provider_id,
        "status": provider.status,
        "implementation": provider.implementation,
        "capabilities": provider.capabilities,
        "setup_blocker_count": len(provider.setup_blockers),
    }


def _provider_smoke_status_is_blocked(status: str) -> bool:
    return status in {"setup_blocked", "disabled", "not_configured", "llm_not_configured", "blocked"}


def _provider_smoke_blocks_core_readiness(result: ProviderConformanceSmokeRecord) -> bool:
    if result.provider_kind != "runtime":
        return True
    return result.provider_id in {"runtime:universal_employee_agent", "runtime:langgraph"}


async def _runtime_statuses() -> list[dict[str, Any]]:
    dispatch_service = ExecutionDispatchService()
    try:
        statuses: list[dict[str, Any]] = []
        for executor in dispatch_service.executors.values():
            statuses.append(await executor.health())
        return statuses
    finally:
        await dispatch_service.aclose()


def _ticket_provider_record() -> ProviderConformanceRecord:
    status = ticket_backend_status()
    mode = status.mode.strip() or status.provider or "local_file"
    setup_required = _clean_string_list(status.setup_required)
    provider_id = f"ticket:{mode}"
    capabilities = _merge_capabilities(
        status.capabilities,
        ["create_ticket", "update_ticket", "append_report", "handoff", "validation_projection"],
    )
    projection_direction = [
        "AITeamOS Ticket -> provider issue/task",
        "AITeamOS Ticket report -> provider comment",
        "AITeamOS validation/handoff -> provider metadata/comment projection",
    ]
    failure_semantics = [
        "missing_config_reports_setup_blocker",
        "provider_error_must_not_mark_ticket_completed",
        "local_file_fallback_preserves_AITeamOS_ticket_model",
    ]
    domain_boundary = [
        "Ticket is the AITeamOS source language",
        "provider_ref is a projection pointer, not the domain object",
        "reports/evidence/validation remain Ticket-ledger facts",
    ]
    return ProviderConformanceRecord(
        provider_id=provider_id,
        provider_kind="ticket",
        implementation=mode,
        display_name="Plane Ticket Provider" if mode == "plane" else "Local File Ticket Provider",
        status=status.status,
        detail=status.detail,
        setup_blockers=_setup_blockers(
            provider_id=provider_id,
            status=status.status,
            detail=status.detail,
            setup_required=setup_required,
        ),
        capabilities=capabilities,
        conformance_smoke={
            "kind": "status_check",
            "endpoint": "/api/v1/tickets/status",
            "method": "GET",
            "write_policy": "ticket_writes_must_use_ticket_service_adapter",
            "non_destructive": True,
        },
        projection_direction=projection_direction,
        failure_semantics=failure_semantics,
        domain_boundary=domain_boundary,
        contract_expectations=[
            _contract_expectation("ticket.required_capabilities", "capabilities", ["create_ticket", "append_report", "handoff", "validation_projection"], capabilities),
            _contract_expectation("ticket.failure_semantics", "failure_semantics", ["missing_config_reports_setup_blocker", "provider_error_must_not_mark_ticket_completed"], failure_semantics),
            _contract_expectation("ticket.domain_boundary", "domain_boundary", ["Ticket is the AITeamOS source language", "provider_ref is a projection pointer, not the domain object"], domain_boundary),
        ],
        fallback_provider="ticket:local_file" if mode != "local_file" else "",
        provider_ref={
            "provider": status.provider or mode,
            "local_file_path": status.local_file_path,
            "provider_ref_count": status.provider_ref_count,
            "mapping": status.mapping,
            "saved_paths": status.saved_paths,
        },
    )


def _asset_provider_record() -> ProviderConformanceRecord:
    capabilities = [
        "asset_candidate_registry",
        "memory_candidate_projection",
        "review_state_tracking",
        "provenance_retention",
        "local_fallback",
    ]
    projection_direction = [
        "governed artifact -> AssetCandidate",
        "approved AssetCandidate -> external asset graph projection",
    ]
    failure_semantics = [
        "external_asset_graph_disabled_keeps_local_registry_available",
        "unreviewed_candidates_must_not_be_projected_as_durable_facts",
    ]
    domain_boundary = [
        "Assets are AITeamOS-owned long-term records",
        "Graph providers receive projections after review",
    ]
    return ProviderConformanceRecord(
        provider_id="asset:local_registry",
        provider_kind="asset",
        implementation="local_registry",
        display_name="Local Asset Registry",
        status="ready",
        detail="Local Asset Candidate registry is the fallback source for durable Assets before provider projection.",
        capabilities=capabilities,
        conformance_smoke={
            "kind": "status_check",
            "endpoint": "/api/v1/assets/candidates",
            "method": "GET",
            "write_policy": "writes_flow_through_governed_ingestion_or_memory_review",
            "non_destructive": True,
        },
        projection_direction=projection_direction,
        failure_semantics=failure_semantics,
        domain_boundary=domain_boundary,
        contract_expectations=[
            _contract_expectation("asset.required_capabilities", "capabilities", ["asset_candidate_registry", "review_state_tracking", "provenance_retention"], capabilities),
            _contract_expectation("asset.failure_semantics", "failure_semantics", ["external_asset_graph_disabled_keeps_local_registry_available", "unreviewed_candidates_must_not_be_projected_as_durable_facts"], failure_semantics),
            _contract_expectation("asset.domain_boundary", "domain_boundary", ["Assets are AITeamOS-owned long-term records", "Graph providers receive projections after review"], domain_boundary),
        ],
        provider_ref={"provider": "local_file", "candidates_endpoint": "/api/v1/assets/candidates"},
    )


def _employee_provider_record() -> ProviderConformanceRecord:
    capabilities = [
        "fixed_employee_identity",
        "capability_tags",
        "personality_tags",
        "permission_policy",
        "memory_scopes",
        "work_ledger_projection",
    ]
    projection_direction = [
        "Employee profile -> runtime context",
        "Ticket reports/handoffs/validations -> Employee work ledger",
    ]
    failure_semantics = [
        "unknown_employee_returns_not_found_or_context_blocker",
        "permission_policy_controls_tool_and_runtime_access",
    ]
    domain_boundary = [
        "Employee is a fixed AITeamOS identity",
        "provider runtime may execute for an Employee but cannot redefine the Employee",
    ]
    return ProviderConformanceRecord(
        provider_id="employee:local_profiles",
        provider_kind="employee",
        implementation="local_profiles",
        display_name="Local Employee Profiles",
        status="ready",
        detail="Employee identities, v2 profile fields, and work-ledger projections are currently local AITeamOS records.",
        capabilities=capabilities,
        conformance_smoke={
            "kind": "status_check",
            "endpoint": "/api/v1/chat/employees",
            "method": "GET",
            "write_policy": "employee_profile_writes_use_chat_employee_profile_service",
            "non_destructive": True,
        },
        projection_direction=projection_direction,
        failure_semantics=failure_semantics,
        domain_boundary=domain_boundary,
        contract_expectations=[
            _contract_expectation("employee.required_capabilities", "capabilities", ["fixed_employee_identity", "permission_policy", "work_ledger_projection"], capabilities),
            _contract_expectation("employee.failure_semantics", "failure_semantics", ["unknown_employee_returns_not_found_or_context_blocker", "permission_policy_controls_tool_and_runtime_access"], failure_semantics),
            _contract_expectation("employee.domain_boundary", "domain_boundary", ["Employee is a fixed AITeamOS identity", "provider runtime may execute for an Employee but cannot redefine the Employee"], domain_boundary),
        ],
        provider_ref={"provider": "local_file", "employees_endpoint": "/api/v1/chat/employees"},
    )


def _memory_provider_record() -> ProviderConformanceRecord:
    status = graphiti_backend_status()
    setup_required = [
        item
        for item, configured in (
            ("Graphiti enabled", status.enabled),
            ("Graphiti URI/user", status.graph_configured),
            (GRAPHITI_NEO4J_PASSWORD_SETUP_LABEL, status.password_configured),
            (status.llm_api_key_env or "selected Graphiti LLM API key", status.llm_api_key_configured),
            ("graphiti optional dependency", status.package_installed),
        )
        if not configured
    ]
    capabilities = [
        "approved_asset_projection",
        "memory_recall",
        "relationship_search",
        "durable_asset_projection",
    ]
    projection_direction = [
        "approved AITeamOS Asset/Memory -> Graphiti episode",
        "Graphiti search result -> AITeamOS memory recall result",
    ]
    failure_semantics = [
        "disabled_graphiti_keeps_local_asset_and_memory_registry_available",
        "projection_requires_reviewed_or_validated_asset",
        "missing_config_reports_setup_blocker",
    ]
    domain_boundary = [
        "Graphiti is a projection/search provider, not the source of truth",
        "raw chat transcripts must not become durable memory directly",
    ]
    return ProviderConformanceRecord(
        provider_id="memory:graphiti",
        provider_kind="memory",
        implementation="graphiti",
        display_name="Graphiti Memory / Asset Graph Provider",
        selected=status.enabled,
        status=status.status,
        detail=status.detail,
        setup_blockers=_setup_blockers(
            provider_id="memory:graphiti",
            status=status.status,
            detail=status.detail,
            setup_required=setup_required,
        ),
        capabilities=capabilities,
        conformance_smoke={
            "kind": "status_check",
            "endpoint": "/api/v1/memory/status",
            "method": "GET",
            "projection_endpoints": [
                "/api/v1/memory/graphiti/durable-assets",
                "/api/v1/memory/graphiti/asset-relationships",
            ],
            "write_policy": "approved_assets_only",
            "non_destructive": True,
        },
        projection_direction=projection_direction,
        failure_semantics=failure_semantics,
        domain_boundary=domain_boundary,
        contract_expectations=[
            _contract_expectation("memory.required_capabilities", "capabilities", ["approved_asset_projection", "memory_recall", "relationship_search"], capabilities),
            _contract_expectation("memory.failure_semantics", "failure_semantics", ["disabled_graphiti_keeps_local_asset_and_memory_registry_available", "projection_requires_reviewed_or_validated_asset"], failure_semantics),
            _contract_expectation("memory.domain_boundary", "domain_boundary", ["Graphiti is a projection/search provider, not the source of truth", "raw chat transcripts must not become durable memory directly"], domain_boundary),
        ],
        fallback_provider="asset:local_registry",
        provider_ref={
            "provider": "graphiti",
            "group_id": status.group_id,
            "graph_database": status.graph_database,
            "llm_ai_engine": status.llm_ai_engine,
            "llm_api_key_env": status.llm_api_key_env,
        },
    )


def _runtime_provider_records(runtime_statuses: list[dict[str, Any]]) -> list[ProviderConformanceRecord]:
    records: list[ProviderConformanceRecord] = []
    for health in runtime_statuses:
        executor_id = str(health.get("executor_id") or "").strip() or "runtime_executor"
        capabilities = _clean_string_list(health.get("capabilities"))
        setup_required = _runtime_setup_required(health)
        status = str(health.get("status") or "unknown")
        detail = str(health.get("detail") or "")
        provider_id = f"runtime:{executor_id}"
        projection_direction = [
            "ExecutionRequest -> RuntimeProvider",
            "RuntimeProvider result -> ExecutionResult",
            "ExecutionResult -> Ticket report / evidence / Asset candidates through ingestion",
        ]
        failure_semantics = _runtime_failure_semantics(capabilities)
        domain_boundary = [
            "RuntimeProvider executes agent/tool work behind ExecutionRequest/ExecutionResult",
            "Chat route remains entry/bridge, not an agent loop",
            "writes return governed artifacts and pass through ingestion",
        ]
        runtime_expectations = [
            _contract_expectation(
                "runtime.failure_semantics",
                "failure_semantics",
                [
                    "setup_blocked_returns_blocked_execution_result",
                    "runtime_errors_enter_replay_and_ticket_report_as_blockers",
                    "external_runtime_completion_must_not_be_faked",
                ],
                failure_semantics,
            ),
            _contract_expectation(
                "runtime.domain_boundary",
                "domain_boundary",
                [
                    "RuntimeProvider executes agent/tool work behind ExecutionRequest/ExecutionResult",
                    "Chat route remains entry/bridge, not an agent loop",
                    "writes return governed artifacts and pass through ingestion",
                ],
                domain_boundary,
            ),
            _contract_expectation(
                "runtime.projection_direction",
                "projection_direction",
                ["RuntimeProvider result -> ExecutionResult", "ExecutionResult -> Ticket report / evidence / Asset candidates through ingestion"],
                projection_direction,
            ),
        ]
        if "repo:write" in capabilities:
            runtime_expectations.append(
                _contract_expectation(
                    "runtime.repo_write_guard",
                    "failure_semantics",
                    ["repo_write_requires_ticket_binding", "repo_write_requires_approval", "repo_write_requires_evidence_before_completion"],
                    failure_semantics,
                )
            )
        records.append(
            ProviderConformanceRecord(
                provider_id=provider_id,
                provider_kind="runtime",
                implementation=executor_id,
                display_name=str(health.get("display_name") or executor_id.replace("_", " ").title()),
                selected=executor_id in {"universal_employee_agent", "langgraph"}
                or "runtime_executor" in capabilities
                or "repo:write" in capabilities,
                status=status,
                detail=detail,
                setup_blockers=_setup_blockers(
                    provider_id=provider_id,
                    status=status,
                    detail=detail or "Runtime executor setup is incomplete.",
                    setup_required=setup_required,
                ),
                capabilities=capabilities,
                conformance_smoke={
                    "kind": "runtime_executor_smoke",
                    "endpoint": f"/api/v1/runtime-executors/{executor_id}/smoke",
                    "method": "POST",
                    "batch_endpoint": "/api/v1/runtime-executors/smoke-batch",
                    "default_ingest_result": False,
                    "ingest_requires_ticket": True,
                    "non_destructive": True,
                    "dispatch_boundary": "RuntimeExecutor",
                },
                projection_direction=projection_direction,
                failure_semantics=failure_semantics,
                domain_boundary=domain_boundary,
                contract_expectations=runtime_expectations,
                fallback_provider="runtime:universal_employee_agent" if executor_id != "universal_employee_agent" else "",
                provider_ref={
                    "executor_id": executor_id,
                    "supported_actions": _clean_string_list(health.get("supported_actions")),
                    "delivery": health.get("delivery") if isinstance(health.get("delivery"), dict) else {},
                    "expected_output_schema": health.get("expected_output_schema")
                    if isinstance(health.get("expected_output_schema"), dict)
                    else {},
                },
            )
        )
    return records


def _with_production_evaluation(provider: ProviderConformanceRecord) -> ProviderConformanceRecord:
    return provider.model_copy(update={"production_evaluation": _provider_production_evaluation(provider)})


def _provider_production_evaluation(provider: ProviderConformanceRecord) -> ProviderProductionEvaluation:
    required_for_core = _provider_required_for_core(provider)
    contract_missing = [
        f"contract_missing:{expectation.id}"
        for expectation in provider.contract_expectations
        if expectation.missing
    ]
    setup_blockers = [blocker.id for blocker in provider.setup_blockers]
    blocked_status = _is_blocked_status(provider.status)
    blockers: list[str] = []
    warnings: list[str] = []

    if contract_missing:
        (blockers if required_for_core else warnings).extend(contract_missing)
    if blocked_status or setup_blockers:
        target = blockers if required_for_core else warnings
        target.extend(setup_blockers or [f"{provider.provider_id}:status:{provider.status}"])

    if blockers and provider.fallback_provider:
        readiness_level = "degraded_with_fallback"
    elif blockers:
        readiness_level = "blocked"
    elif warnings:
        readiness_level = "optional_unconfigured"
    elif provider.status == "ready":
        readiness_level = "production_ready"
    else:
        readiness_level = "ready_for_evaluation"

    production_ready = provider.status == "ready" and not blockers and not contract_missing
    return ProviderProductionEvaluation(
        required_for_core=required_for_core,
        production_ready=production_ready,
        readiness_level=readiness_level,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def _provider_required_for_core(provider: ProviderConformanceRecord) -> bool:
    if provider.provider_kind in {"ticket", "asset", "employee", "memory"}:
        return True
    return provider.provider_id in {"runtime:universal_employee_agent", "runtime:langgraph"}


def _setup_blockers(
    *,
    provider_id: str,
    status: str,
    detail: str,
    setup_required: list[str],
) -> list[ProviderSetupBlocker]:
    if status.strip().lower() == "ready":
        return []
    if not _is_blocked_status(status) and not setup_required:
        return []
    if status in {"ready", "unknown"} and not setup_required:
        return []
    return [
        ProviderSetupBlocker(
            id=f"{provider_id}:setup",
            status=status,
            detail=detail or "Provider setup is incomplete.",
            setup_required=setup_required,
        )
    ]


def _contract_expectation(
    expectation_id: str,
    category: str,
    required: list[str],
    actual: list[str],
) -> ProviderContractExpectation:
    required_items = _clean_string_list(required)
    actual_items = _clean_string_list(actual)
    actual_set = set(actual_items)
    satisfied = [item for item in required_items if item in actual_set]
    missing = [item for item in required_items if item not in actual_set]
    return ProviderContractExpectation(
        id=expectation_id,
        category=category,
        required=required_items,
        satisfied=satisfied,
        missing=missing,
        status="failed" if missing else "passed",
    )


def _provider_check(provider: ProviderConformanceRecord) -> ProviderConformanceCheckRecord:
    checks: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    if provider.provider_id and provider.provider_kind and provider.implementation:
        checks.append("identity")
    else:
        failures.append("missing_provider_identity")

    if provider.capabilities:
        checks.append("capabilities")
    else:
        failures.append("missing_capabilities")

    smoke_kind = str(provider.conformance_smoke.get("kind") or "").strip()
    smoke_endpoint = str(provider.conformance_smoke.get("endpoint") or "").strip()
    smoke_method = str(provider.conformance_smoke.get("method") or "").strip()
    if smoke_kind and smoke_endpoint and smoke_method:
        checks.append("conformance_smoke")
    else:
        failures.append("missing_conformance_smoke")

    if provider.projection_direction:
        checks.append("projection_direction")
    else:
        failures.append("missing_projection_direction")

    if provider.failure_semantics:
        checks.append("failure_semantics")
    else:
        failures.append("missing_failure_semantics")

    if provider.domain_boundary:
        checks.append("domain_boundary")
    else:
        failures.append("missing_domain_boundary")

    if provider.status == "ready" and provider.setup_blockers:
        failures.append("ready_provider_has_setup_blockers")
    if _is_blocked_status(provider.status) and not provider.setup_blockers:
        failures.append("blocked_provider_missing_setup_blockers")
    if provider.setup_blockers:
        checks.append("setup_blocker_reported")

    if provider.contract_expectations:
        checks.append("contract_expectations")
        for expectation in provider.contract_expectations:
            if expectation.missing:
                failures.append(f"contract_missing:{expectation.id}")
            else:
                checks.append(f"contract:{expectation.id}")
    else:
        failures.append("missing_contract_expectations")

    if provider.production_evaluation.schema_version == PROVIDER_CONFORMANCE_VERSION:
        checks.append("production_evaluation")
        checks.append(f"readiness:{provider.production_evaluation.readiness_level}")
        if provider.production_evaluation.migration_status == "schema_current":
            checks.append("contract_schema_current")
        if provider.production_evaluation.required_for_core:
            checks.append("core_provider")
    else:
        failures.append("production_evaluation_schema_mismatch")

    if provider.provider_kind in {"ticket", "memory"} and provider.implementation not in {"local_file", "local_registry"}:
        if provider.fallback_provider:
            checks.append("fallback_provider")
        else:
            warnings.append("external_provider_missing_fallback_provider")

    if provider.provider_kind == "runtime" and "repo:write" in provider.capabilities:
        required = {"repo_write_requires_ticket_binding", "repo_write_requires_approval", "repo_write_requires_evidence_before_completion"}
        if required.issubset(set(provider.failure_semantics)):
            checks.append("repo_write_guard")
        else:
            failures.append("repo_write_runtime_missing_guard_semantics")

    status = "failed" if failures else "warning" if warnings else "passed"
    return ProviderConformanceCheckRecord(
        provider_id=provider.provider_id,
        provider_kind=provider.provider_kind,
        status=status,
        checks=checks,
        warnings=warnings,
        failures=failures,
    )


async def _provider_smoke(provider: ProviderConformanceRecord, *, include_external: bool) -> ProviderConformanceSmokeRecord:
    contract = _provider_check(provider)
    checks = ["provider_record_loaded", f"provider_kind:{provider.provider_kind}", f"smoke_kind:{_smoke_kind(provider)}"]
    warnings = list(contract.warnings)
    failures = list(contract.failures)
    blockers = [blocker.model_dump(mode="json") for blocker in provider.setup_blockers]
    evidence: dict[str, Any] = {
        "provider_ref": _redacted_provider_ref(provider.provider_ref),
        "contract_check_status": contract.status,
        "contract_checks": contract.checks,
        "selected": provider.selected,
        "conformance_smoke": provider.conformance_smoke,
    }
    status = "failed" if failures else "passed"
    external_calls = False

    if provider.setup_blockers:
        status = provider.status or "setup_blocked"
        checks.append("setup_blocker_reported")
        checks.append("no_fake_success_for_blocked_provider")
    elif _is_blocked_status(provider.status):
        status = provider.status
        blockers.append(
            {
                "id": f"{provider.provider_id}:status",
                "status": provider.status,
                "detail": provider.detail or "Provider is not ready.",
                "setup_required": [],
            }
        )
        checks.append("blocked_status_preserved")

    if provider.provider_kind == "ticket":
        current = ticket_backend_status()
        evidence["ticket_backend_status"] = current.model_dump(mode="json")
        checks.append("ticket_backend_status_read")
        if current.status == "ready" and provider.status != "ready":
            failures.append("ticket_status_mismatch")
            status = "failed"
        if include_external and provider.implementation == "plane":
            external = ticket_provider_external_smoke()
            checks.append("external_smoke_requested")
            checks.extend(_clean_string_list(external.get("checks")))
            warnings.extend(_clean_string_list(external.get("warnings")))
            failures.extend(_clean_string_list(external.get("failures")))
            blockers.extend(_dict_list(external.get("blockers")))
            evidence["external_smoke"] = external.get("evidence") if isinstance(external.get("evidence"), dict) else {}
            status = "failed" if failures else str(external.get("status") or status)
            external_calls = bool(external.get("external_calls"))
    elif provider.provider_kind == "asset":
        checks.append("asset_registry_contract_read")
        evidence["asset_registry"] = {
            "provider": provider.provider_ref.get("provider") or "local_file",
            "candidates_endpoint": provider.provider_ref.get("candidates_endpoint") or "",
        }
    elif provider.provider_kind == "employee":
        checks.append("employee_provider_contract_read")
        evidence["employee_provider"] = {
            "provider": provider.provider_ref.get("provider") or "local_file",
            "employees_endpoint": provider.provider_ref.get("employees_endpoint") or "",
        }
    elif provider.provider_kind == "memory":
        current = graphiti_backend_status()
        evidence["memory_backend_status"] = current.model_dump(mode="json")
        checks.append("memory_backend_status_read")
        if current.status == "ready" and provider.status != "ready":
            failures.append("memory_status_mismatch")
            status = "failed"
        if include_external and provider.implementation == "graphiti":
            external = await graphiti_provider_external_smoke()
            checks.append("external_smoke_requested")
            checks.extend(_clean_string_list(external.get("checks")))
            warnings.extend(_clean_string_list(external.get("warnings")))
            failures.extend(_clean_string_list(external.get("failures")))
            blockers.extend(_dict_list(external.get("blockers")))
            evidence["external_smoke"] = external.get("evidence") if isinstance(external.get("evidence"), dict) else {}
            status = "failed" if failures else str(external.get("status") or status)
            external_calls = bool(external.get("external_calls"))
    elif provider.provider_kind == "runtime":
        checks.append("runtime_executor_health_read")
        evidence["runtime_executor"] = {
            "executor_id": provider.provider_ref.get("executor_id") or provider.implementation,
            "supported_actions": provider.provider_ref.get("supported_actions") or [],
            "delivery": provider.provider_ref.get("delivery") or {},
        }

    if provider.provider_kind in {"ticket", "memory", "runtime"} and provider.fallback_provider:
        checks.append("fallback_provider_declared")
    if provider.provider_kind in {"ticket", "memory"} and provider.implementation not in {"local_file", "local_registry"} and not include_external:
        warnings.append("external_provider_smoke_skipped")
        checks.append("external_calls_disabled")

    return ProviderConformanceSmokeRecord(
        provider_id=provider.provider_id,
        provider_kind=provider.provider_kind,
        implementation=provider.implementation,
        status="failed" if failures else status,
        detail=provider.detail,
        smoke_kind=_smoke_kind(provider),
        checks=checks,
        warnings=warnings,
        failures=failures,
        blockers=blockers,
        evidence=evidence,
        external_calls=external_calls,
    )


def _smoke_kind(provider: ProviderConformanceRecord) -> str:
    if provider.provider_kind == "runtime":
        return "runtime_executor_health"
    if provider.provider_kind == "ticket":
        return "ticket_backend_status"
    if provider.provider_kind == "memory":
        return "memory_backend_status"
    if provider.provider_kind == "asset":
        return "asset_registry_contract"
    if provider.provider_kind == "employee":
        return "employee_provider_contract"
    return "provider_contract"


def _redacted_provider_ref(provider_ref: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in provider_ref.items():
        lowered = str(key).lower()
        if any(token in lowered for token in ("token", "secret", "password", "api_key")):
            redacted[str(key)] = "[redacted]"
        else:
            redacted[str(key)] = value
    return redacted


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _is_blocked_status(status: str) -> bool:
    normalized = status.strip().lower()
    return normalized not in {"", "ready", "unknown"}


def _runtime_setup_required(executor_status: dict[str, Any]) -> list[str]:
    missing_env = executor_status.get("missing_env")
    if isinstance(missing_env, list) and missing_env:
        return _clean_string_list(missing_env)
    configured = executor_status.get("configured")
    if not isinstance(configured, dict):
        return []
    return [
        str(key).replace("_", " ")
        for key, value in configured.items()
        if value is False
    ][:8]


def _runtime_failure_semantics(capabilities: list[str]) -> list[str]:
    semantics = [
        "setup_blocked_returns_blocked_execution_result",
        "runtime_errors_enter_replay_and_ticket_report_as_blockers",
        "external_runtime_completion_must_not_be_faked",
    ]
    if "repo:write" in capabilities:
        semantics.extend(
            [
                "repo_write_requires_ticket_binding",
                "repo_write_requires_approval",
                "repo_write_requires_evidence_before_completion",
            ]
        )
    return semantics


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _merge_capabilities(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _clean_string_list(value):
            if item not in seen:
                merged.append(item)
                seen.add(item)
    return merged
