"""Memory governance routes for AITeamOS."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .memory_service import (
    CapabilityDurableAssetBatchProjectionResponse,
    CapabilityDurableAssetProjectionResponse,
    DecisionDurableAssetBatchProjectionResponse,
    DecisionDurableAssetProjectionResponse,
    DocDurableAssetBatchProjectionResponse,
    DocDurableAssetProjectionResponse,
    DurableAssetIngestRequest,
    DurableAssetIngestResponse,
    DurableAssetRelationshipIngestRequest,
    DurableAssetRelationshipIngestResponse,
    EmployeeDurableAssetBatchProjectionResponse,
    EmployeeDurableAssetProjectionResponse,
    GraphitiSettingsResponse,
    GraphitiSettingsUpdateRequest,
    MemoryCandidate,
    MemoryCandidateCreateRequest,
    MemoryCandidateReviewRequest,
    MemoryRecallUsefulnessReviewRequest,
    MemorySearchResponse,
    MemoryStatusResponse,
    SkillDurableAssetBatchProjectionResponse,
    SkillDurableAssetProjectionResponse,
    TicketDurableAssetProjectionResponse,
    approve_memory_candidate,
    create_memory_candidate,
    graphiti_settings_response,
    ingest_accepted_decision_durable_asset,
    ingest_accepted_decision_durable_assets,
    ingest_approved_capability_durable_asset,
    ingest_approved_capability_durable_assets,
    ingest_approved_employee_profile_durable_asset,
    ingest_approved_employee_profile_durable_assets,
    ingest_approved_doc_durable_asset,
    ingest_approved_doc_durable_assets,
    ingest_approved_skill_durable_asset,
    ingest_approved_skill_durable_assets,
    ingest_durable_asset_relationship_to_graphiti,
    ingest_durable_asset_to_graphiti,
    ingest_validated_ticket_durable_assets,
    list_approved_memories,
    list_memory_candidates,
    memory_status,
    review_memory_recall_usage,
    review_memory_candidate,
    search_memory,
    update_graphiti_settings,
)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.get("/status", response_model=MemoryStatusResponse)
async def get_memory_status() -> MemoryStatusResponse:
    return memory_status()


@router.get("/graphiti/settings", response_model=GraphitiSettingsResponse)
async def get_graphiti_settings() -> GraphitiSettingsResponse:
    return graphiti_settings_response()


@router.put("/graphiti/settings", response_model=GraphitiSettingsResponse)
async def put_graphiti_settings(request: GraphitiSettingsUpdateRequest) -> GraphitiSettingsResponse:
    try:
        return update_graphiti_settings(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/durable-assets", response_model=DurableAssetIngestResponse)
async def post_graphiti_durable_asset(request: DurableAssetIngestRequest) -> DurableAssetIngestResponse:
    try:
        return await ingest_durable_asset_to_graphiti(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/asset-relationships", response_model=DurableAssetRelationshipIngestResponse)
async def post_graphiti_durable_asset_relationship(
    request: DurableAssetRelationshipIngestRequest,
) -> DurableAssetRelationshipIngestResponse:
    try:
        return await ingest_durable_asset_relationship_to_graphiti(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/tickets/{ticket_id}/durable-assets", response_model=TicketDurableAssetProjectionResponse)
async def post_graphiti_ticket_durable_assets(
    ticket_id: str,
    max_assets: int = Query(20, ge=1, le=50),
) -> TicketDurableAssetProjectionResponse:
    try:
        return await ingest_validated_ticket_durable_assets(ticket_id, max_assets=max_assets)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/decisions/{decision_id}/durable-asset", response_model=DecisionDurableAssetProjectionResponse)
async def post_graphiti_decision_durable_asset(decision_id: str) -> DecisionDurableAssetProjectionResponse:
    try:
        return await ingest_accepted_decision_durable_asset(decision_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Decision not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/decisions/durable-assets", response_model=DecisionDurableAssetBatchProjectionResponse)
async def post_graphiti_decision_durable_assets(
    max_assets: int = Query(20, ge=1, le=50),
) -> DecisionDurableAssetBatchProjectionResponse:
    try:
        return await ingest_accepted_decision_durable_assets(max_assets=max_assets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/skills/{skill_id}/durable-asset", response_model=SkillDurableAssetProjectionResponse)
async def post_graphiti_skill_durable_asset(skill_id: str) -> SkillDurableAssetProjectionResponse:
    try:
        return await ingest_approved_skill_durable_asset(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Skill not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/skills/durable-assets", response_model=SkillDurableAssetBatchProjectionResponse)
async def post_graphiti_skill_durable_assets(
    max_assets: int = Query(20, ge=1, le=50),
) -> SkillDurableAssetBatchProjectionResponse:
    try:
        return await ingest_approved_skill_durable_assets(max_assets=max_assets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/docs/{doc_id}/durable-asset", response_model=DocDurableAssetProjectionResponse)
async def post_graphiti_doc_durable_asset(doc_id: str) -> DocDurableAssetProjectionResponse:
    try:
        return await ingest_approved_doc_durable_asset(doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Doc not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/docs/durable-assets", response_model=DocDurableAssetBatchProjectionResponse)
async def post_graphiti_doc_durable_assets(
    max_assets: int = Query(20, ge=1, le=50),
) -> DocDurableAssetBatchProjectionResponse:
    try:
        return await ingest_approved_doc_durable_assets(max_assets=max_assets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/capabilities/{capability_id}/durable-asset", response_model=CapabilityDurableAssetProjectionResponse)
async def post_graphiti_capability_durable_asset(capability_id: str) -> CapabilityDurableAssetProjectionResponse:
    try:
        return await ingest_approved_capability_durable_asset(capability_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Capability not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/capabilities/durable-assets", response_model=CapabilityDurableAssetBatchProjectionResponse)
async def post_graphiti_capability_durable_assets(
    max_assets: int = Query(20, ge=1, le=50),
) -> CapabilityDurableAssetBatchProjectionResponse:
    try:
        return await ingest_approved_capability_durable_assets(max_assets=max_assets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/employees/{employee_id}/durable-asset", response_model=EmployeeDurableAssetProjectionResponse)
async def post_graphiti_employee_profile_durable_asset(employee_id: str) -> EmployeeDurableAssetProjectionResponse:
    try:
        return await ingest_approved_employee_profile_durable_asset(employee_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Employee not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphiti/employees/durable-assets", response_model=EmployeeDurableAssetBatchProjectionResponse)
async def post_graphiti_employee_profile_durable_assets(
    max_assets: int = Query(20, ge=1, le=50),
) -> EmployeeDurableAssetBatchProjectionResponse:
    try:
        return await ingest_approved_employee_profile_durable_assets(max_assets=max_assets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/candidates", response_model=list[MemoryCandidate])
async def get_memory_candidates(status: str | None = None) -> list[MemoryCandidate]:
    return list_memory_candidates(status=status)


@router.post("/candidates", response_model=MemoryCandidate)
async def post_memory_candidate(request: MemoryCandidateCreateRequest) -> MemoryCandidate:
    return create_memory_candidate(request)


@router.post("/candidates/{candidate_id}/approve", response_model=MemoryCandidate)
async def post_memory_candidate_approval(candidate_id: str) -> MemoryCandidate:
    try:
        return await approve_memory_candidate(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Memory candidate not found: {candidate_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/review", response_model=MemoryCandidate)
async def post_memory_candidate_review(candidate_id: str, request: MemoryCandidateReviewRequest) -> MemoryCandidate:
    try:
        return review_memory_candidate(candidate_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Memory candidate not found: {candidate_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/usage/{usage_id}/review", response_model=MemoryCandidate)
async def post_memory_usage_review(
    candidate_id: str,
    usage_id: str,
    request: MemoryRecallUsefulnessReviewRequest,
) -> MemoryCandidate:
    try:
        return review_memory_recall_usage(candidate_id, usage_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Memory usage record not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/approved", response_model=list[MemoryCandidate])
async def get_approved_memory() -> list[MemoryCandidate]:
    return list_approved_memories()


@router.get("/search", response_model=MemorySearchResponse)
async def get_memory_search(
    q: str = Query("", alias="q"),
    employee_id: str | None = None,
    ticket_key: str | None = None,
    project: str | None = None,
    limit: int = 10,
    include_graphiti: bool = True,
) -> MemorySearchResponse:
    return await search_memory(
        query=q,
        employee_id=employee_id,
        ticket_key=ticket_key,
        project=project,
        limit=limit,
        include_graphiti=include_graphiti,
    )
