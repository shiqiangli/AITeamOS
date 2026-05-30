"""
API Gateway — Memory Read Routes (plan.md §1.5.2).

GET /api/v1/memories           — 分页列表
GET /api/v1/memories/{id}      — 详情
GET /api/v1/memories/{id}/versions — 版本历史
GET /api/v1/memories/search    — 关键词搜索
GET /api/v1/memories/proposals/pending — 待审核 Memory 候选队列
GET /api/v1/memories/health    — Memory 健康概览
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from aiteamos_knowledge.application.queries import (
    GetMemoryNodeDetailExecutor,
    GetMemoryNodeDetailQuery,
    ListMemoryNodesExecutor,
    ListMemoryNodesQuery,
    SearchMemoryByKeywordExecutor,
    SearchMemoryByKeywordQuery,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/memories", tags=["memory-read"])


# Module-level references set by composition root
_list_executor: ListMemoryNodesExecutor | None = None
_detail_executor: GetMemoryNodeDetailExecutor | None = None
_search_executor: SearchMemoryByKeywordExecutor | None = None
_proposal_repo: Any = None
_db: Any = None


def init_routes(
    *,
    list_executor: ListMemoryNodesExecutor,
    detail_executor: GetMemoryNodeDetailExecutor,
    search_executor: SearchMemoryByKeywordExecutor,
    proposal_repo: Any = None,
    db: Any = None,
) -> None:
    global _list_executor, _detail_executor, _search_executor, _proposal_repo, _db
    _list_executor = list_executor
    _detail_executor = detail_executor
    _search_executor = search_executor
    _proposal_repo = proposal_repo
    _db = db


@router.get("", response_model=list[dict[str, Any]])
async def list_memories(
    tier: Optional[str] = Query(None),
    scope_kind: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _list_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.domain.models import LifecycleState, ScopeKind, Tier

    query = ListMemoryNodesQuery(
        tier=Tier(tier) if tier else None,
        scope_kind=ScopeKind(scope_kind) if scope_kind else None,
        lifecycle=LifecycleState(lifecycle) if lifecycle else None,
        offset=offset,
        limit=limit,
    )
    results = await _list_executor.execute(query)
    return [
        {
            "id": str(r.id),
            "tier": r.tier,
            "title": r.title,
            "lifecycle_state": r.lifecycle_state,
            "confidence_value": r.confidence_value,
            "scope_kind": r.scope_kind,
            "tags": r.tags,
            "current_version": r.current_version,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in results
    ]


@router.get("/search", response_model=list[dict[str, Any]])
async def search_memories(
    keyword: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    limit: int = Query(20, ge=1, le=100),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _search_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    query = SearchMemoryByKeywordQuery(keyword=keyword, tags=tag_list, limit=limit)
    results = await _search_executor.execute(query)
    return [
        {
            "id": str(r.id),
            "tier": r.tier,
            "title": r.title,
            "lifecycle_state": r.lifecycle_state,
            "confidence_value": r.confidence_value,
            "scope_kind": r.scope_kind,
            "tags": r.tags,
            "current_version": r.current_version,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in results
    ]


@router.get("/proposals/pending", response_model=list[dict[str, Any]])
async def list_pending_proposals(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List Memory candidates pending review (lifecycle=candidate)."""
    if _list_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.domain.models import LifecycleState

    query = ListMemoryNodesQuery(
        lifecycle=LifecycleState.CANDIDATE,
        offset=offset,
        limit=limit,
    )
    results = await _list_executor.execute(query)
    return [
        {
            "id": str(r.id),
            "tier": r.tier,
            "title": r.title,
            "lifecycle_state": r.lifecycle_state,
            "confidence_value": r.confidence_value,
            "scope_kind": r.scope_kind,
            "tags": r.tags,
            "current_version": r.current_version,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in results
    ]


@router.get("/health", response_model=dict[str, Any])
async def memory_health(
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Memory health overview: counts by lifecycle, tier, conflict stats."""
    if _list_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Gather counts per lifecycle state
    from aiteamos_knowledge.domain.models import LifecycleState

    health: dict[str, Any] = {}
    total = 0
    for state in ("active", "candidate", "deprecated", "needs_verify"):
        query = ListMemoryNodesQuery(
            lifecycle=LifecycleState(state),
            offset=0,
            limit=200,
        )
        results = await _list_executor.execute(query)
        health[state] = len(results)
        total += len(results)

    health["total"] = total
    health["candidate_ratio"] = round(health.get("candidate", 0) / max(total, 1), 3)
    health["deprecated_ratio"] = round(health.get("deprecated", 0) / max(total, 1), 3)
    health["needs_verify_ratio"] = round(health.get("needs_verify", 0) / max(total, 1), 3)
    return health


@router.get("/{memory_id}", response_model=dict[str, Any])
async def get_memory_detail(
    memory_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _detail_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_shared.types import MemoryId

    query = GetMemoryNodeDetailQuery(memory_id=memory_id)  # type: ignore[arg-type]
    result = await _detail_executor.execute(query)
    if result is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Memory {memory_id} not found")
    node = result.node
    return {
        "id": str(node.id),
        "tier": node.tier.value if hasattr(node.tier, "value") else str(node.tier),
        "title": node.title,
        "statement": node.content.statement,
        "lifecycle_state": node.lifecycle.value if hasattr(node.lifecycle, "value") else str(node.lifecycle),
        "confidence_value": float(node.confidence.value),
        "versions": result.versions,
        "created_at": str(node.created_at),
    }


@router.get("/{memory_id}/versions", response_model=list[dict[str, Any]])
async def get_memory_versions(
    memory_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _detail_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    query = GetMemoryNodeDetailQuery(memory_id=memory_id)  # type: ignore[arg-type]
    result = await _detail_executor.execute(query)
    if result is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Memory {memory_id} not found")
    return result.versions
