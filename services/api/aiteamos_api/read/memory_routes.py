"""Memory governance routes for AITeamOS."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .memory_service import (
    GraphitiSettingsResponse,
    GraphitiSettingsUpdateRequest,
    MemoryCandidate,
    MemoryCandidateCreateRequest,
    MemorySearchResponse,
    MemoryStatusResponse,
    approve_memory_candidate,
    create_memory_candidate,
    graphiti_settings_response,
    list_approved_memories,
    list_memory_candidates,
    memory_status,
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


@router.get("/approved", response_model=list[MemoryCandidate])
async def get_approved_memory() -> list[MemoryCandidate]:
    return list_approved_memories()


@router.get("/search", response_model=MemorySearchResponse)
async def get_memory_search(
    q: str = Query("", alias="q"),
    member_id: str | None = None,
    jira_key: str | None = None,
    project: str | None = None,
    limit: int = 10,
    include_graphiti: bool = True,
) -> MemorySearchResponse:
    return await search_memory(
        query=q,
        member_id=member_id,
        jira_key=jira_key,
        project=project,
        limit=limit,
        include_graphiti=include_graphiti,
    )
