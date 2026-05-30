"""
API Gateway — Memory Write Routes (plan.md §1.5.3).

POST   /api/v1/memories                       — 创建
PUT    /api/v1/memories/{id}                  — 更新
POST   /api/v1/memories/{id}/versions         — 追加版本
PATCH  /api/v1/memories/{id}/lifecycle        — 状态变更
POST   /api/v1/memories/edges                 — 创建关系
DELETE /api/v1/memories/edges/{edge_id}       — 删除关系
POST   /api/v1/memories/{id}/deprecate        — 废弃
POST   /api/v1/memories/{id}/merge            — 合并
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aiteamos_knowledge.application.handlers import (
    AppendMemoryVersionHandler,
    ChangeLifecycleHandler,
    CreateMemoryEdgeHandler,
    CreateMemoryNodeHandler,
    DeprecateMemoryNodeHandler,
    MergeMemoryNodesHandler,
    RemoveMemoryEdgeHandler,
    UpdateMemoryContentHandler,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/memories", tags=["memory-write"])

_create_handler: CreateMemoryNodeHandler | None = None
_update_handler: UpdateMemoryContentHandler | None = None
_version_handler: AppendMemoryVersionHandler | None = None
_lifecycle_handler: ChangeLifecycleHandler | None = None
_edge_handler: CreateMemoryEdgeHandler | None = None
_remove_edge_handler: RemoveMemoryEdgeHandler | None = None
_deprecate_handler: DeprecateMemoryNodeHandler | None = None
_merge_handler: MergeMemoryNodesHandler | None = None


def init_routes(
    *,
    create_handler: CreateMemoryNodeHandler,
    update_handler: UpdateMemoryContentHandler,
    version_handler: AppendMemoryVersionHandler,
    lifecycle_handler: ChangeLifecycleHandler,
    edge_handler: CreateMemoryEdgeHandler,
    remove_edge_handler: RemoveMemoryEdgeHandler | None = None,
    deprecate_handler: DeprecateMemoryNodeHandler | None = None,
    merge_handler: MergeMemoryNodesHandler | None = None,
) -> None:
    global _create_handler, _update_handler, _version_handler, _lifecycle_handler
    global _edge_handler, _remove_edge_handler, _deprecate_handler, _merge_handler
    _create_handler = create_handler
    _update_handler = update_handler
    _version_handler = version_handler
    _lifecycle_handler = lifecycle_handler
    _edge_handler = edge_handler
    _remove_edge_handler = remove_edge_handler
    _deprecate_handler = deprecate_handler
    _merge_handler = merge_handler


# --- Request Bodies ---


class CreateMemoryRequest(BaseModel):
    tier: str
    scope_kind: str
    scope_ref: Optional[str] = None
    title: str
    statement: str
    applicable_when: str = ""
    counter_example: str = ""
    tags: list[str] = Field(default_factory=list)
    source_kind: str = "human"
    initial_confidence: float = 0.5


class UpdateMemoryRequest(BaseModel):
    statement: str
    applicable_when: str = ""
    counter_example: str = ""
    tags: list[str] = Field(default_factory=list)
    reason: str = ""
    author_member_id: str = ""


class AppendVersionRequest(BaseModel):
    diff: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    author_member_id: str = ""


class ChangeLifecycleRequest(BaseModel):
    new_state: str  # active | quarantined | deprecated


class CreateEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    created_by: str = ""


class MergeMemoryRequest(BaseModel):
    source_ids: list[str]
    reason: str = ""
    author_member_id: str = ""


@router.post("", status_code=201, response_model=dict[str, Any])
async def create_memory(
    body: CreateMemoryRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _create_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import CreateMemoryNodeCommand
    from aiteamos_knowledge.domain.models import ScopeKind, SourceKind, Tier

    cmd = CreateMemoryNodeCommand(
        tier=Tier(body.tier),
        scope_kind=ScopeKind(body.scope_kind),
        scope_ref=UUID(body.scope_ref) if body.scope_ref else None,
        title=body.title,
        statement=body.statement,
        applicable_when=body.applicable_when,
        counter_example=body.counter_example,
        tags=body.tags,
        source_kind=SourceKind(body.source_kind),
        initial_confidence=Decimal(str(body.initial_confidence)),
    )
    node = await _create_handler.handle(cmd)
    return {"id": str(node.id), "status": "created"}


@router.put("/{memory_id}", response_model=dict[str, Any])
async def update_memory(
    memory_id: UUID,
    body: UpdateMemoryRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _update_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import UpdateMemoryContentCommand

    cmd = UpdateMemoryContentCommand(
        memory_id=memory_id,  # type: ignore[arg-type]
        statement=body.statement,
        applicable_when=body.applicable_when,
        counter_example=body.counter_example,
        tags=body.tags,
        reason=body.reason,
        author_member_id=UUID(body.author_member_id) if body.author_member_id else None,  # type: ignore[arg-type]
    )
    node = await _update_handler.handle(cmd)
    return {"id": str(node.id), "status": "updated"}


@router.post("/{memory_id}/versions", status_code=201, response_model=dict[str, Any])
async def append_version(
    memory_id: UUID,
    body: AppendVersionRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _version_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import AppendMemoryVersionCommand

    cmd = AppendMemoryVersionCommand(
        memory_id=memory_id,  # type: ignore[arg-type]
        diff=body.diff,
        reason=body.reason,
        author_member_id=UUID(body.author_member_id) if body.author_member_id else None,  # type: ignore[arg-type]
    )
    node = await _version_handler.handle(cmd)
    return {"id": str(node.id), "status": "version_appended"}


@router.patch("/{memory_id}/lifecycle", response_model=dict[str, Any])
async def change_lifecycle(
    memory_id: UUID,
    body: ChangeLifecycleRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _lifecycle_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import ChangeLifecycleCommand
    from aiteamos_knowledge.domain.models import LifecycleState

    cmd = ChangeLifecycleCommand(
        memory_id=memory_id,  # type: ignore[arg-type]
        new_state=LifecycleState(body.new_state),
    )
    node = await _lifecycle_handler.handle(cmd)
    return {"id": str(node.id), "lifecycle_state": body.new_state}


@router.post("/edges", status_code=201, response_model=dict[str, Any])
async def create_edge(
    body: CreateEdgeRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _edge_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import CreateMemoryEdgeCommand
    from aiteamos_knowledge.domain.models import RelationType

    cmd = CreateMemoryEdgeCommand(
        source_id=UUID(body.source_id),  # type: ignore[arg-type]
        target_id=UUID(body.target_id),  # type: ignore[arg-type]
        relation_type=RelationType(body.relation_type),
        weight=Decimal(str(body.weight)),
        created_by=UUID(body.created_by) if body.created_by else None,  # type: ignore[arg-type]
    )
    edge = await _edge_handler.handle(cmd)
    return {"id": str(edge.edge_id), "status": "created"}


@router.delete("/edges/{edge_id}", status_code=200, response_model=dict[str, Any])
async def delete_edge(
    edge_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _remove_edge_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import RemoveMemoryEdgeCommand

    cmd = RemoveMemoryEdgeCommand(edge_id=edge_id)
    await _remove_edge_handler.handle(cmd)
    return {"id": str(edge_id), "status": "deleted"}


@router.post("/{memory_id}/deprecate", status_code=200, response_model=dict[str, Any])
async def deprecate_memory(
    memory_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _deprecate_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import DeprecateMemoryNodeCommand

    cmd = DeprecateMemoryNodeCommand(memory_id=memory_id)  # type: ignore[arg-type]
    node = await _deprecate_handler.handle(cmd)
    return {"id": str(node.id), "status": "deprecated"}


@router.post("/{memory_id}/merge", status_code=200, response_model=dict[str, Any])
async def merge_memories(
    memory_id: UUID,
    body: MergeMemoryRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _merge_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_knowledge.application.commands import MergeMemoryNodesCommand

    cmd = MergeMemoryNodesCommand(
        target_id=memory_id,  # type: ignore[arg-type]
        source_ids=[UUID(sid) for sid in body.source_ids],
        reason=body.reason,
        author_member_id=UUID(body.author_member_id) if body.author_member_id else None,  # type: ignore[arg-type]
    )
    node = await _merge_handler.handle(cmd)
    return {"id": str(node.id), "status": "merged"}
