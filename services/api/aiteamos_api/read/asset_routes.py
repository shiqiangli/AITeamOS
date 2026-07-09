"""All Assets routes."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .asset_candidate_service import (
    AssetCandidateBatchReviewRequest,
    AssetCandidateBatchReviewResponse,
    AssetCandidateRecord,
    AssetCandidateReviewRequest,
    AssetCandidateReviewResponse,
    AssetRetrievalEvaluationRecord,
    AssetRetrievalEvaluationRequest,
    AssetRetrievalEvaluationResponse,
    AssetRecord as AssetRegistryRecord,
    AssetRecordRelationshipProjectionResponse,
    AssetRecordProjectionResponse,
    AssetReviewRecord,
    list_asset_candidates,
    list_asset_records,
    list_asset_retrieval_evaluations,
    list_asset_reviews,
    project_asset_record_relationships_to_graphiti,
    project_asset_record_to_graphiti,
    review_asset_candidate,
    review_asset_candidates,
    record_asset_retrieval_evaluation,
)
from .knowledge_service import AssetRecord as KnowledgeAssetRecord, asset_items
from .skill_usage_service import SkillUsageReviewRequest, SkillUsageReviewResponse, review_skill_usage
from .ticket_service import AssetGraphProjection, asset_graph_projection

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.get("", response_model=list[KnowledgeAssetRecord])
async def get_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return _combined_asset_items(query=q, include_candidates=bool(q.strip()))


@router.get("/all", response_model=list[KnowledgeAssetRecord])
async def get_all_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return _combined_asset_items(query=q, include_candidates=bool(q.strip()))


@router.get("/search", response_model=list[KnowledgeAssetRecord])
async def search_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return _combined_asset_items(query=q, include_candidates=True)


@router.get("/candidates", response_model=list[AssetCandidateRecord])
async def get_asset_candidates(
    status: str = "",
    asset_type: str = "",
    q: str = Query("", alias="q"),
) -> list[AssetCandidateRecord]:
    return list_asset_candidates(status=status, asset_type=asset_type, query=q)


@router.post("/candidates/{candidate_id}/review", response_model=AssetCandidateReviewResponse)
async def post_asset_candidate_review(candidate_id: str, request: AssetCandidateReviewRequest) -> AssetCandidateReviewResponse:
    try:
        return review_asset_candidate(candidate_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Asset candidate not found: {candidate_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/candidates/review-batch", response_model=AssetCandidateBatchReviewResponse)
async def post_asset_candidate_batch_review(request: AssetCandidateBatchReviewRequest) -> AssetCandidateBatchReviewResponse:
    try:
        return review_asset_candidates(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/records", response_model=list[AssetRegistryRecord])
async def get_asset_records(
    status: str = "",
    asset_type: str = "",
    q: str = Query("", alias="q"),
) -> list[AssetRegistryRecord]:
    return list_asset_records(status=status, asset_type=asset_type, query=q)


@router.get("/reviews", response_model=list[AssetReviewRecord])
async def get_asset_reviews(candidate_id: str = "") -> list[AssetReviewRecord]:
    return list_asset_reviews(candidate_id=candidate_id)


@router.get("/retrieval-evaluations", response_model=list[AssetRetrievalEvaluationRecord])
async def get_asset_retrieval_evaluations() -> list[AssetRetrievalEvaluationRecord]:
    return list_asset_retrieval_evaluations()


@router.post("/retrieval-evaluations", response_model=AssetRetrievalEvaluationResponse)
async def post_asset_retrieval_evaluation(request: AssetRetrievalEvaluationRequest) -> AssetRetrievalEvaluationResponse:
    retrieved_assets = _combined_asset_items(query=request.query, include_candidates=True)[: request.top_k]
    return record_asset_retrieval_evaluation(
        request,
        [item.model_dump(mode="json") for item in retrieved_assets],
    )


@router.post("/records/{asset_id}/project/graphiti", response_model=AssetRecordProjectionResponse)
async def post_asset_record_graphiti_projection(asset_id: str) -> AssetRecordProjectionResponse:
    try:
        return await project_asset_record_to_graphiti(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Asset record not found: {asset_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/records/{asset_id}/relationships/project/graphiti", response_model=AssetRecordRelationshipProjectionResponse)
async def post_asset_record_relationships_graphiti_projection(asset_id: str) -> AssetRecordRelationshipProjectionResponse:
    try:
        return await project_asset_record_relationships_to_graphiti(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Asset record not found: {asset_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/capabilities/skills/usage/{usage_id}/review", response_model=SkillUsageReviewResponse)
async def post_skill_usage_review(usage_id: str, request: SkillUsageReviewRequest) -> SkillUsageReviewResponse:
    try:
        return review_skill_usage(workspace_dir=_workspace_dir(), usage_id=usage_id, request=request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Skill usage record not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{asset_id}/graph", response_model=AssetGraphProjection)
async def get_asset_graph(asset_id: str) -> AssetGraphProjection:
    try:
        projection = asset_graph_projection(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if projection is None:
        raise HTTPException(status_code=404, detail=f"Asset graph not found: {asset_id}")
    return projection


@router.get("/knowledge", response_model=list[KnowledgeAssetRecord])
async def get_knowledge_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="knowledge", query=q)


@router.get("/knowledge/docs", response_model=list[KnowledgeAssetRecord])
async def get_doc_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="knowledge", asset_type="docs", query=q)


@router.get("/knowledge/memories", response_model=list[KnowledgeAssetRecord])
async def get_memory_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="knowledge", asset_type="memories", query=q)


@router.get("/knowledge/decisions", response_model=list[KnowledgeAssetRecord])
async def get_decision_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="knowledge", asset_type="decisions", query=q)


@router.get("/capabilities", response_model=list[KnowledgeAssetRecord])
async def get_capability_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="capabilities", query=q)


@router.get("/capabilities/skills", response_model=list[KnowledgeAssetRecord])
async def get_skill_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="capabilities", asset_type="skills", query=q)


@router.get("/capabilities/kernel-commands", response_model=list[KnowledgeAssetRecord])
async def get_kernel_command_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="capabilities", asset_type="kernel-commands", query=q)


@router.get("/capabilities/mcp-tools", response_model=list[KnowledgeAssetRecord])
async def get_mcp_tool_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="capabilities", asset_type="mcp-tools", query=q)


@router.get("/review", response_model=list[KnowledgeAssetRecord])
async def get_review_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="review", query=q)


@router.get("/review/memories", response_model=list[KnowledgeAssetRecord])
async def get_memory_review_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="review", asset_type="memories", query=q)


@router.get("/review/decisions", response_model=list[KnowledgeAssetRecord])
async def get_decision_review_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="review", asset_type="decisions", query=q)


@router.get("/review/skills", response_model=list[KnowledgeAssetRecord])
async def get_skill_review_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="review", asset_type="skills", query=q)


@router.get("/review/tools", response_model=list[KnowledgeAssetRecord])
async def get_tool_review_assets(q: str = Query("", alias="q")) -> list[KnowledgeAssetRecord]:
    return asset_items(domain="review", asset_type="tools", query=q)


def _combined_asset_items(*, query: str = "", include_candidates: bool = False) -> list[KnowledgeAssetRecord]:
    items = [
        *asset_items(query=query),
        *[_registry_asset_item(record) for record in list_asset_records(query=query)],
    ]
    if include_candidates:
        items.extend(_candidate_asset_item(record) for record in list_asset_candidates(query=query))
    items = sorted(items, key=lambda item: item.updated_at or item.created_at, reverse=True)
    return sorted(items, key=_asset_usefulness_ranking_penalty)


def _registry_asset_item(record: AssetRegistryRecord) -> KnowledgeAssetRecord:
    return KnowledgeAssetRecord(
        id=f"asset-registry:{record.id}",
        kind=record.asset_type,
        title=record.title,
        status=record.status,
        source_ticket=record.scope_ref if record.scope_kind == "ticket" else "",
        source_employee=record.owner_employee_id,
        assigned_employees=[record.owner_employee_id] if record.owner_employee_id else [],
        scopes=[f"{record.scope_kind}:{record.scope_ref}", record.asset_type],
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata={
            "asset_domain": "assets",
            "asset_type": record.asset_type,
            "asset_registry_id": record.id,
            "content": record.content,
            "content_ref": record.content_ref,
            "source_kind": record.source_kind,
            "source_ref": record.source_ref,
            "provider": record.provider,
            "provider_ref": record.provider_ref,
            "relationships": record.relationships,
            "provenance": record.provenance,
            "usefulness_stats": record.usefulness_stats,
        },
    )


def _candidate_asset_item(record: AssetCandidateRecord) -> KnowledgeAssetRecord:
    return KnowledgeAssetRecord(
        id=f"asset-candidate:{record.id}",
        kind=record.asset_type,
        title=record.title,
        status=record.status,
        source_ticket=record.scope_ref if record.scope_kind == "ticket" else "",
        source_employee=record.owner_employee_id,
        assigned_employees=[record.owner_employee_id] if record.owner_employee_id else [],
        scopes=[f"{record.scope_kind}:{record.scope_ref}", record.asset_type, "candidate"],
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata={
            "asset_domain": "review",
            "asset_type": record.asset_type,
            "asset_candidate_id": record.id,
            "content": record.content,
            "content_ref": record.content_ref,
            "source_kind": record.source_kind,
            "source_ref": record.source_ref,
            "provider": record.provider,
            "provider_ref": record.provider_ref,
            "relationships": record.relationships,
            "provenance": record.provenance,
            "usefulness_stats": record.usefulness_stats,
        },
    )


def _asset_usefulness_ranking_penalty(item: KnowledgeAssetRecord) -> int:
    stats = item.metadata.get("usefulness_stats")
    if not isinstance(stats, dict):
        provenance = item.metadata.get("provenance") if isinstance(item.metadata.get("provenance"), dict) else {}
        stats = provenance.get("usage_summary") if isinstance(provenance.get("usage_summary"), dict) else {}
    harmful = _int_stat(stats, "harmful_count")
    irrelevant = _int_stat(stats, "irrelevant_count")
    promoted = _int_stat(stats, "promoted_count")
    used = _int_stat(stats, "used_count") + _int_stat(stats, "useful_count")
    return harmful * 10 + irrelevant * 4 - promoted * 2 - min(used, 3)


def _int_stat(stats: dict[str, object], key: str) -> int:
    value = stats.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _workspace_dir() -> Path:
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    root = Path(configured).resolve() if configured else Path.cwd().resolve()
    return root / ".aiteamos"
