"""Source-backed runtime boundary audit for Plan v8 Track B."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

RUNTIME_BOUNDARY_AUDIT_VERSION = "aiteamos_runtime_boundary_audit.v1"


class RuntimeBoundaryAuditCheck(BaseModel):
    id: str
    status: str
    detail: str
    path: str = ""
    expected: list[str] = Field(default_factory=list)
    observed: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    forbidden_hits: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RuntimeBoundaryAuditSummary(BaseModel):
    check_count: int = 0
    passed_count: int = 0
    warning_count: int = 0
    blocked_count: int = 0
    chat_route_line_count: int = 0
    chat_runtime_factory_line_count: int = 0
    workbench_context_line_count: int = 0
    workbench_context_node_line_count: int = 0
    workbench_governance_node_line_count: int = 0
    passed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    contract_version: str = RUNTIME_BOUNDARY_AUDIT_VERSION


class RuntimeBoundaryAuditResponse(BaseModel):
    contract_version: str = RUNTIME_BOUNDARY_AUDIT_VERSION
    status: str
    detail: str
    summary: RuntimeBoundaryAuditSummary = Field(default_factory=RuntimeBoundaryAuditSummary)
    checks: list[RuntimeBoundaryAuditCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


def runtime_boundary_audit_report(*, source_root: Path | None = None) -> RuntimeBoundaryAuditResponse:
    """Inspect source files for hard route/runtime ownership violations."""

    root = (source_root or Path(__file__).resolve().parent).resolve()
    chat_route = root / "chat_routes.py"
    runtime_factory = root / "chat_runtime_factory.py"
    execution_service = root / "chat_execution_service.py"
    memory_service = root / "memory_service.py"
    workbench_context = root / "workbench_runtime_context_service.py"
    workbench_context_node = root.parent / "agents" / "workbench" / "nodes" / "context.py"
    workbench_governance_node = root.parent / "agents" / "workbench" / "nodes" / "governance.py"
    checks = [
        _source_check(
            check_id="chat_route_transport_adapter",
            path=chat_route,
            detail="Chat route delegates execution to the runtime factory and does not own runtime dispatch/model calls.",
            expected=[
                'APIRouter(prefix="/api/v1/chat"',
                "build_chat_execution_runtime",
                "StreamingResponse",
            ],
            forbidden=[
                "ExecutionDispatchService",
                "ChatGovernanceService",
                "ChatActionPlanningService",
                "ExecutionRequest",
                "ExecutionResult",
                "httpx.AsyncClient",
                "OpenAI(",
                "AsyncOpenAI",
                "responses.create",
                "chat.completions",
                "completions.create",
                "langchain_openai",
                "langchain_deepseek",
            ],
            warnings=_line_count_warnings(chat_route, limit=350, warning="chat_route_helper_surface_large"),
        ),
        _source_check(
            check_id="chat_runtime_factory_route_free",
            path=runtime_factory,
            detail="Chat runtime factory remains importable by LangGraph/Agent Server without FastAPI route transport.",
            expected=[
                "ChatExecutionRuntime",
                "ChatGovernanceService",
                "ExecutionDispatchService",
                "ChatActionPlanningService",
            ],
            forbidden=[
                "APIRouter",
                "HTTPException",
                "StreamingResponse",
                "from fastapi",
                "chat_routes",
            ],
            warnings=[],
        ),
        _source_check(
            check_id="chat_execution_service_contract_boundary",
            path=execution_service,
            detail="Chat execution service converts runtime results through ExecutionResult before transcript persistence.",
            expected=[
                "ExecutionResult",
                "governance.handle_message",
                "dispatch_service.stream",
                "_persist_chat_response",
            ],
            forbidden=[
                "APIRouter",
                "HTTPException",
                "OpenAI(",
                "AsyncOpenAI",
                "responses.create",
                "chat.completions",
            ],
            warnings=[],
        ),
        _source_check(
            check_id="workbench_runtime_context_contract_boundary",
            path=workbench_context,
            detail="Workbench graph context delegates preparation and persistence through route-free runtime services.",
            expected=[
                "WorkbenchRuntimeContextService",
                "ExecutionRequest",
                "ExecutionResult",
                "ChatRunPreparationService",
                "build_execution_trace_events",
                "save_execution_session",
                "persist_chat_response",
            ],
            forbidden=[
                "APIRouter",
                "HTTPException",
                "StreamingResponse",
                "from fastapi",
                "chat_routes",
                "chat_runtime_factory",
                "runtime_factory.",
                "OpenAI(",
                "AsyncOpenAI",
                "responses.create",
                "chat.completions",
                "completions.create",
                "langchain_openai",
                "langchain_deepseek",
            ],
            warnings=[],
        ),
        _source_check(
            check_id="workbench_context_node_route_free_services",
            path=workbench_context_node,
            detail="Workbench context graph node uses route-free preparation/context services instead of the compatibility runtime factory.",
            expected=[
                "ChatRunPreparationService",
                "ChatMessageRequest",
                "load_employee_profiles",
                "ExecutionContextService",
                "search_memory",
            ],
            forbidden=[
                "APIRouter",
                "HTTPException",
                "StreamingResponse",
                "from fastapi",
                "chat_routes",
                "chat_runtime_factory",
                "runtime_factory.",
                "OpenAI(",
                "AsyncOpenAI",
                "responses.create",
                "chat.completions",
                "completions.create",
                "langchain_openai",
                "langchain_deepseek",
            ],
            warnings=[],
        ),
        _source_check(
            check_id="workbench_governance_node_route_free_services",
            path=workbench_governance_node,
            detail="Workbench governance graph node builds governance and dispatch services directly behind the ExecutionRequest/ExecutionResult contract.",
            expected=[
                "ChatGovernanceService",
                "ChatActionPlanningService",
                "ExecutionDispatchService",
                "ChatRunPreparationService.require_safe_id",
                "ExecutionRequest",
                "ExecutionResult",
            ],
            forbidden=[
                "APIRouter",
                "HTTPException",
                "StreamingResponse",
                "from fastapi",
                "chat_routes",
                "chat_runtime_factory",
                "runtime_factory.",
                "OpenAI(",
                "AsyncOpenAI",
                "responses.create",
                "chat.completions",
                "completions.create",
                "langchain_openai",
                "langchain_deepseek",
            ],
            warnings=[],
        ),
        _source_check(
            check_id="graphiti_memory_provider_langchain_boundary",
            path=memory_service,
            detail="Graphiti Asset projection/recall uses LangChain model-provider wiring for its LLM client instead of a native direct model call.",
            expected=[
                "LangChainModelProvider",
                "AiEngineRuntimeConfig",
                "_AiteamosLangChainGraphitiClient",
                "LLMClient",
                "model_provider.ainvoke",
            ],
            forbidden=[
                "client.chat.completions.create",
                "chat.completions",
                "responses.create",
                "completions.create",
                "OpenAIGenericClient",
            ],
            warnings=[],
        ),
    ]
    blockers = _unique([f"{check.id}:{hit}" for check in checks for hit in [*check.missing, *check.forbidden_hits]])
    warnings = _unique([warning for check in checks for warning in check.warnings])
    status = "blocked" if blockers else "warning" if warnings else "passed"
    summary = RuntimeBoundaryAuditSummary(
        check_count=len(checks),
        passed_count=sum(1 for check in checks if check.status == "passed"),
        warning_count=len([check for check in checks if check.warnings]),
        blocked_count=len([check for check in checks if check.status == "blocked"]),
        chat_route_line_count=_line_count(chat_route),
        chat_runtime_factory_line_count=_line_count(runtime_factory),
        workbench_context_line_count=_line_count(workbench_context),
        workbench_context_node_line_count=_line_count(workbench_context_node),
        workbench_governance_node_line_count=_line_count(workbench_governance_node),
        passed_checks=[check.id for check in checks if check.status == "passed"],
        warnings=warnings,
        blockers=blockers,
    )
    return RuntimeBoundaryAuditResponse(
        status=status,
        detail=(
            "Runtime boundary source audit passed with non-blocking cleanup signals."
            if status == "warning"
            else "Runtime boundary source audit passed."
            if status == "passed"
            else "Runtime boundary source audit found route/runtime ownership violations."
        ),
        summary=summary,
        checks=checks,
        warnings=warnings,
        blockers=blockers,
    )


def _source_check(
    *,
    check_id: str,
    path: Path,
    detail: str,
    expected: list[str],
    forbidden: list[str],
    warnings: list[str],
) -> RuntimeBoundaryAuditCheck:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return RuntimeBoundaryAuditCheck(
            id=check_id,
            status="blocked",
            detail=detail,
            path=str(path),
            expected=expected,
            missing=expected,
            warnings=warnings,
        )
    missing = [item for item in expected if item not in source]
    forbidden_hits = [item for item in forbidden if item in source]
    return RuntimeBoundaryAuditCheck(
        id=check_id,
        status="blocked" if missing or forbidden_hits else "passed",
        detail=detail,
        path=str(path),
        expected=expected,
        observed=[item for item in expected if item in source],
        missing=missing,
        forbidden_hits=forbidden_hits,
        warnings=warnings,
    )


def _line_count_warnings(path: Path, *, limit: int, warning: str) -> list[str]:
    return [warning] if _line_count(path) > limit else []


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
