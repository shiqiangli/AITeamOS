"""Local ticket routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .asset_candidate_service import (
    TicketCloseoutAssetCandidateRequest,
    TicketCloseoutAssetCandidateResponse,
    TicketCloseoutSettlementRequest,
    TicketCloseoutSettlementResponse,
    TicketFailureRetrospectiveAssetCandidateRequest,
    TicketFailureRetrospectiveAssetCandidateResponse,
    propose_ticket_failure_retrospective_asset_candidates,
    propose_ticket_closeout_asset_candidates,
    settle_ticket_closeout_assets,
)
from .ticket_service import (
    EmployeeWorkLedger,
    Ticket,
    TicketAssetRecord,
    TicketBackendPlaneScopeDiscovery,
    TicketBackendSettings,
    TicketBackendSettingsUpdateRequest,
    TicketBackendStatus,
    TicketCreateRequest,
    TicketEvent,
    TicketEvidenceRequirements,
    TicketGraphProjection,
    TicketPerformance,
    TicketReportRequest,
    TicketRuntimeEvidence,
    SelfBootstrapLearningSummary,
    TicketStateTransitionRequest,
    TicketValidationRequest,
    add_ticket_report,
    create_ticket,
    discover_ticket_backend_plane_scope,
    employee_work_ledger,
    get_ticket,
    get_ticket_events,
    list_tickets,
    ticket_asset_records,
    ticket_assets_for_ticket,
    ticket_backend_settings,
    ticket_backend_status,
    ticket_evidence_requirements,
    ticket_graph_projection,
    ticket_performance,
    ticket_runtime_evidence,
    request_ticket_validation,
    self_bootstrap_learning_summary,
    transition_ticket_state,
    update_ticket_backend_settings,
)
from .ticket_loop_service import (
    TicketAutonomousLoopService,
    TicketLoopEnqueueRequest,
    TicketLoopControlRequest,
    TicketLoopControlResponse,
    TicketLoopPolicy,
    TicketLoopPolicyUpdateRequest,
    TicketLoopQueueItem,
    TicketLoopQueuePumpRequest,
    TicketLoopQueuePumpResponse,
    TicketLoopQueueStatus,
    TicketLoopQueueWorkerControlRequest,
    TicketLoopQueueWorkerStatus,
    TicketLoopQueueWorkerTickResponse,
    TicketLoopResumeRequest,
    TicketLoopResumeResponse,
    TicketLoopRunRecord,
    TicketLoopRunRequest,
    TicketLoopRunResponse,
    TicketLoopStepRequest,
    TicketLoopStepResponse,
    TicketLoopTimelineResponse,
    control_ticket_loop,
    enqueue_ticket_loop,
    get_ticket_loop_run,
    list_ticket_loop_queue,
    list_ticket_loop_runs,
    pump_ticket_loop_queue,
    start_ticket_loop_queue_worker,
    stop_ticket_loop_queue_worker,
    ticket_loop_policy,
    ticket_loop_queue_status,
    ticket_loop_queue_worker_status,
    ticket_loop_timeline,
    tick_ticket_loop_queue_worker,
    resume_ticket_loop,
    update_ticket_loop_policy,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


@router.get("", response_model=list[Ticket])
async def get_tickets(status: str | None = None) -> list[Ticket]:
    try:
        return list_tickets(status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=Ticket)
async def post_ticket(request: TicketCreateRequest) -> Ticket:
    try:
        return create_ticket(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backend", response_model=TicketBackendSettings)
async def get_ticket_backend() -> TicketBackendSettings:
    return ticket_backend_settings()


@router.put("/backend", response_model=TicketBackendSettings)
async def put_ticket_backend(request: TicketBackendSettingsUpdateRequest) -> TicketBackendSettings:
    try:
        return update_ticket_backend_settings(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status", response_model=TicketBackendStatus)
async def get_ticket_backend_status() -> TicketBackendStatus:
    return ticket_backend_status()


@router.get("/backend/plane-scope/discovery", response_model=TicketBackendPlaneScopeDiscovery)
async def get_ticket_backend_plane_scope_discovery() -> TicketBackendPlaneScopeDiscovery:
    return discover_ticket_backend_plane_scope()


@router.get("/assets", response_model=list[TicketAssetRecord])
async def get_ticket_assets() -> list[TicketAssetRecord]:
    try:
        return ticket_asset_records()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/self-bootstrap/summary", response_model=SelfBootstrapLearningSummary)
async def get_self_bootstrap_summary() -> SelfBootstrapLearningSummary:
    try:
        return self_bootstrap_learning_summary()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/employees/{employee_id}/work", response_model=EmployeeWorkLedger)
async def get_employee_work_ledger(employee_id: str) -> EmployeeWorkLedger:
    try:
        return employee_work_ledger(employee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{ticket_id}/events", response_model=list[TicketEvent])
async def get_ticket_event_log(ticket_id: str) -> list[TicketEvent]:
    try:
        events = get_ticket_events(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not events:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return events


@router.get("/{ticket_id}/graph", response_model=TicketGraphProjection)
async def get_ticket_graph(ticket_id: str) -> TicketGraphProjection:
    try:
        projection = ticket_graph_projection(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if projection is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return projection


@router.get("/{ticket_id}/assets", response_model=list[TicketAssetRecord])
async def get_ticket_asset_records(ticket_id: str) -> list[TicketAssetRecord]:
    try:
        item = next((ticket for ticket in list_tickets() if ticket.id == ticket_id.strip()), None)
        if item is None:
            item = get_ticket(ticket_id)
        assets = ticket_assets_for_ticket(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return assets


@router.get("/{ticket_id}/performance", response_model=TicketPerformance)
async def get_ticket_performance(ticket_id: str) -> TicketPerformance:
    try:
        performance = ticket_performance(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if performance is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return performance


@router.get("/{ticket_id}/runtime-evidence", response_model=TicketRuntimeEvidence)
async def get_ticket_runtime_evidence(ticket_id: str) -> TicketRuntimeEvidence:
    try:
        evidence = ticket_runtime_evidence(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return evidence


@router.get("/{ticket_id}/evidence-requirements", response_model=TicketEvidenceRequirements)
async def get_ticket_evidence_requirements(ticket_id: str) -> TicketEvidenceRequirements:
    try:
        requirements = ticket_evidence_requirements(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if requirements is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return requirements


@router.get("/{ticket_id}", response_model=Ticket)
async def get_ticket_detail(ticket_id: str) -> Ticket:
    try:
        item = get_ticket(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return item


@router.post("/{ticket_id}/loop/step", response_model=TicketLoopStepResponse)
async def post_ticket_loop_step(ticket_id: str, request: TicketLoopStepRequest) -> TicketLoopStepResponse:
    try:
        return await TicketAutonomousLoopService().run_step(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/loop/run", response_model=TicketLoopRunResponse)
async def post_ticket_loop_run(ticket_id: str, request: TicketLoopRunRequest) -> TicketLoopRunResponse:
    try:
        return await TicketAutonomousLoopService().run_loop(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/loop/queue", response_model=TicketLoopQueueItem)
async def post_ticket_loop_queue(ticket_id: str, request: TicketLoopEnqueueRequest) -> TicketLoopQueueItem:
    try:
        return enqueue_ticket_loop(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/loop/queue", response_model=list[TicketLoopQueueItem])
async def get_ticket_loop_queue(status: str = "") -> list[TicketLoopQueueItem]:
    try:
        return list_ticket_loop_queue(status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/loop/queue/status", response_model=TicketLoopQueueStatus)
async def get_ticket_loop_queue_status() -> TicketLoopQueueStatus:
    try:
        return ticket_loop_queue_status()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/loop/queue/pump", response_model=TicketLoopQueuePumpResponse)
async def post_ticket_loop_queue_pump(request: TicketLoopQueuePumpRequest) -> TicketLoopQueuePumpResponse:
    try:
        return await pump_ticket_loop_queue(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/loop/queue/worker/status", response_model=TicketLoopQueueWorkerStatus)
async def get_ticket_loop_queue_worker_status() -> TicketLoopQueueWorkerStatus:
    try:
        return ticket_loop_queue_worker_status()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/loop/queue/worker/start", response_model=TicketLoopQueueWorkerStatus)
async def post_ticket_loop_queue_worker_start(request: TicketLoopQueueWorkerControlRequest) -> TicketLoopQueueWorkerStatus:
    try:
        return await start_ticket_loop_queue_worker(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/loop/queue/worker/stop", response_model=TicketLoopQueueWorkerStatus)
async def post_ticket_loop_queue_worker_stop() -> TicketLoopQueueWorkerStatus:
    try:
        return await stop_ticket_loop_queue_worker(reason="Ticket loop queue worker stopped from API.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/loop/queue/worker/tick", response_model=TicketLoopQueueWorkerTickResponse)
async def post_ticket_loop_queue_worker_tick(request: TicketLoopQueueWorkerControlRequest) -> TicketLoopQueueWorkerTickResponse:
    try:
        return await tick_ticket_loop_queue_worker(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{ticket_id}/loop/runs", response_model=list[TicketLoopRunRecord])
async def get_ticket_loop_runs(ticket_id: str) -> list[TicketLoopRunRecord]:
    try:
        return list_ticket_loop_runs(ticket_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{ticket_id}/loop/runs/{run_id}", response_model=TicketLoopRunRecord)
async def get_ticket_loop_run_detail(ticket_id: str, run_id: str) -> TicketLoopRunRecord:
    try:
        item = get_ticket_loop_run(ticket_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=f"Ticket loop run not found: {run_id}")
    return item


@router.get("/{ticket_id}/loop/timeline", response_model=TicketLoopTimelineResponse)
async def get_ticket_loop_timeline(ticket_id: str) -> TicketLoopTimelineResponse:
    try:
        return ticket_loop_timeline(ticket_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/loop/resume", response_model=TicketLoopResumeResponse)
async def post_ticket_loop_resume(ticket_id: str, request: TicketLoopResumeRequest) -> TicketLoopResumeResponse:
    try:
        return resume_ticket_loop(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{ticket_id}/loop/policy", response_model=TicketLoopPolicy)
async def get_ticket_loop_policy(ticket_id: str) -> TicketLoopPolicy:
    try:
        return ticket_loop_policy(ticket_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{ticket_id}/loop/policy", response_model=TicketLoopPolicy)
async def put_ticket_loop_policy(ticket_id: str, request: TicketLoopPolicyUpdateRequest) -> TicketLoopPolicy:
    try:
        return update_ticket_loop_policy(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/loop/control", response_model=TicketLoopControlResponse)
async def post_ticket_loop_control(ticket_id: str, request: TicketLoopControlRequest) -> TicketLoopControlResponse:
    try:
        return control_ticket_loop(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/closeout-candidates", response_model=TicketCloseoutAssetCandidateResponse)
async def post_ticket_closeout_candidates(
    ticket_id: str,
    request: TicketCloseoutAssetCandidateRequest,
) -> TicketCloseoutAssetCandidateResponse:
    try:
        return propose_ticket_closeout_asset_candidates(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/closeout-settlement", response_model=TicketCloseoutSettlementResponse)
async def post_ticket_closeout_settlement(
    ticket_id: str,
    request: TicketCloseoutSettlementRequest,
) -> TicketCloseoutSettlementResponse:
    try:
        return await settle_ticket_closeout_assets(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/failure-retrospective-candidates", response_model=TicketFailureRetrospectiveAssetCandidateResponse)
async def post_ticket_failure_retrospective_candidates(
    ticket_id: str,
    request: TicketFailureRetrospectiveAssetCandidateRequest,
) -> TicketFailureRetrospectiveAssetCandidateResponse:
    try:
        return propose_ticket_failure_retrospective_asset_candidates(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/reports", response_model=Ticket)
async def post_ticket_report(ticket_id: str, request: TicketReportRequest) -> Ticket:
    try:
        return add_ticket_report(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/validation-requests", response_model=Ticket)
async def post_ticket_validation_request(ticket_id: str, request: TicketValidationRequest) -> Ticket:
    try:
        return request_ticket_validation(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/state", response_model=Ticket)
async def post_ticket_state(ticket_id: str, request: TicketStateTransitionRequest) -> Ticket:
    try:
        return transition_ticket_state(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
