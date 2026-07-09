"""Local Asset Candidate registry for governed durable assets."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AssetCandidateRecord(BaseModel):
    id: str
    source_candidate_id: str = ""
    asset_id: str = ""
    asset_type: str
    title: str
    content: str
    content_ref: str = ""
    status: str = "proposed"
    scope_kind: str = "project"
    scope_ref: str = "aiteamos"
    owner_employee_id: str = ""
    source_kind: str = ""
    source_ref: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    provider: str = "local_file"
    provider_ref: str = ""
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    review_state: str = "proposed"
    usefulness_stats: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class AssetRecord(BaseModel):
    id: str
    asset_type: str
    title: str
    content: str
    content_ref: str = ""
    status: str = "approved"
    scope_kind: str = "project"
    scope_ref: str = "aiteamos"
    owner_employee_id: str = ""
    source_kind: str = ""
    source_ref: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    provider: str = "local_file"
    provider_ref: str = ""
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    review_state: str = "approved"
    usefulness_stats: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class AssetReviewRecord(BaseModel):
    id: str
    candidate_id: str
    asset_id: str = ""
    status: str
    reviewer_employee_id: str = "clara"
    reason: str = ""
    merge_target_asset_id: str = ""
    link_relationships: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class AssetCandidateReviewRequest(BaseModel):
    status: str = "approved"
    reviewer_employee_id: str = "clara"
    reason: str = ""
    merge_target_asset_id: str = ""
    link_relationships: list[dict[str, Any]] = Field(default_factory=list)


class AssetCandidateReviewResponse(BaseModel):
    candidate: AssetCandidateRecord
    review: AssetReviewRecord
    asset: AssetRecord | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class AssetCandidateBatchReviewRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    status: str = "approved"
    reviewer_employee_id: str = "clara"
    reason: str = ""
    merge_target_asset_id: str = ""
    link_relationships: list[dict[str, Any]] = Field(default_factory=list)


class AssetCandidateBatchReviewItem(BaseModel):
    candidate_id: str
    status: str
    response: AssetCandidateReviewResponse | None = None
    error: str = ""


class AssetCandidateBatchReviewResponse(BaseModel):
    status: str
    requested_count: int
    reviewed_count: int
    failed_count: int
    results: list[AssetCandidateBatchReviewItem] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class AssetRetrievalEvaluationRequest(BaseModel):
    query: str = Field(min_length=1)
    expected_asset_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=10, ge=1, le=50)
    source_ticket_id: str = ""
    source_run_id: str = ""
    evaluator_employee_id: str = "clara"
    usefulness_status: str = "unreviewed"


class AssetRetrievalEvaluationRecord(BaseModel):
    id: str
    query: str
    expected_asset_ids: list[str] = Field(default_factory=list)
    retrieved_asset_ids: list[str] = Field(default_factory=list)
    matched_asset_ids: list[str] = Field(default_factory=list)
    missing_asset_ids: list[str] = Field(default_factory=list)
    precision: float = 0.0
    recall: float = 0.0
    top_k: int = 10
    source_ticket_id: str = ""
    source_run_id: str = ""
    evaluator_employee_id: str = "clara"
    usefulness_status: str = "unreviewed"
    created_at: str = ""


class AssetRetrievalEvaluationResponse(BaseModel):
    record: AssetRetrievalEvaluationRecord
    retrieved_assets: list[dict[str, Any]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class AssetRecordProjectionResponse(BaseModel):
    asset_id: str
    status: str
    detail: str
    ingested_asset: dict[str, Any] | None = None
    skipped_asset: dict[str, str] | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class AssetRecordRelationshipProjectionResponse(BaseModel):
    asset_id: str
    status: str
    detail: str
    ingested_relationships: list[dict[str, Any]] = Field(default_factory=list)
    skipped_relationships: list[dict[str, str]] = Field(default_factory=list)
    unsupported_relationships: list[dict[str, str]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketCloseoutAssetCandidateRequest(BaseModel):
    actor_employee_id: str = "clara"
    actor_role: str = "AI Team OS Manager"
    reason: str = ""


class TicketCloseoutAssetCandidateResponse(BaseModel):
    ticket_id: str
    status: str
    detail: str
    candidates: list[AssetCandidateRecord] = Field(default_factory=list)
    report_id: str = ""
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketCloseoutSettlementRequest(BaseModel):
    actor_employee_id: str = "clara"
    actor_role: str = "AI Team OS Manager"
    reviewer_employee_id: str = ""
    reason: str = ""
    approve_candidates: bool = False
    project_graphiti: bool = False
    project_relationships: bool = False
    asset_types: list[str] = Field(default_factory=list)


class TicketCloseoutSettlementProjection(BaseModel):
    asset_id: str
    status: str
    projection: AssetRecordProjectionResponse | None = None
    relationship_projection: AssetRecordRelationshipProjectionResponse | None = None
    error: str = ""


class TicketCloseoutSettlementResponse(BaseModel):
    ticket_id: str
    status: str
    detail: str
    proposal: TicketCloseoutAssetCandidateResponse
    review: AssetCandidateBatchReviewResponse | None = None
    candidates: list[AssetCandidateRecord] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    projections: list[TicketCloseoutSettlementProjection] = Field(default_factory=list)
    report_id: str = ""
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketFailureRetrospectiveAssetCandidateRequest(BaseModel):
    actor_employee_id: str = "clara"
    actor_role: str = "AI Team OS Manager"
    reason: str = ""
    min_failed_items: int = Field(default=2, ge=1, le=20)


class TicketFailureRetrospectiveAssetCandidateResponse(BaseModel):
    ticket_id: str
    status: str
    detail: str
    candidates: list[AssetCandidateRecord] = Field(default_factory=list)
    report_id: str = ""
    failed_item_count: int = 0
    saved_paths: dict[str, str] = Field(default_factory=dict)


def asset_candidates_path(workspace_dir: Path | None = None) -> Path:
    return _workspace_dir(workspace_dir) / "assets" / "candidates.json"


def asset_records_path(workspace_dir: Path | None = None) -> Path:
    return _workspace_dir(workspace_dir) / "assets" / "index.json"


def asset_reviews_path(workspace_dir: Path | None = None) -> Path:
    return _workspace_dir(workspace_dir) / "assets" / "reviews.json"


def graphiti_state_path(workspace_dir: Path | None = None) -> Path:
    return _workspace_dir(workspace_dir) / "memory" / "graphiti_state.json"


def asset_retrieval_evaluations_path(workspace_dir: Path | None = None) -> Path:
    return _workspace_dir(workspace_dir) / "assets" / "retrieval_evaluations.json"


def list_asset_candidates(
    *,
    status: str = "",
    asset_type: str = "",
    query: str = "",
    workspace_dir: Path | None = None,
) -> list[AssetCandidateRecord]:
    records = sorted(_load_records(workspace_dir), key=lambda item: item.updated_at or item.created_at, reverse=True)
    normalized_status = status.strip().lower()
    normalized_type = asset_type.strip().lower()
    normalized_query = query.strip().lower()
    if normalized_status:
        records = [record for record in records if record.status == normalized_status or record.review_state == normalized_status]
    if normalized_type:
        records = [record for record in records if record.asset_type == normalized_type]
    if normalized_query:
        records = [record for record in records if _matches_query(record, normalized_query)]
    return records


def list_asset_records(
    *,
    status: str = "",
    asset_type: str = "",
    query: str = "",
    workspace_dir: Path | None = None,
) -> list[AssetRecord]:
    records = sorted(_load_asset_records(workspace_dir), key=lambda item: item.updated_at or item.created_at, reverse=True)
    normalized_status = status.strip().lower()
    normalized_type = asset_type.strip().lower()
    normalized_query = query.strip().lower()
    if normalized_status:
        records = [record for record in records if record.status == normalized_status or record.review_state == normalized_status]
    if normalized_type:
        records = [record for record in records if record.asset_type == normalized_type]
    if normalized_query:
        records = [record for record in records if _matches_asset_query(record, normalized_query)]
    return records


def list_asset_reviews(
    *,
    candidate_id: str = "",
    workspace_dir: Path | None = None,
) -> list[AssetReviewRecord]:
    records = sorted(_load_review_records(workspace_dir), key=lambda item: item.updated_at or item.created_at, reverse=True)
    normalized_candidate = candidate_id.strip()
    if normalized_candidate:
        records = [record for record in records if record.candidate_id == normalized_candidate]
    return records


def list_asset_retrieval_evaluations(*, workspace_dir: Path | None = None) -> list[AssetRetrievalEvaluationRecord]:
    return sorted(_load_retrieval_evaluations(workspace_dir), key=lambda item: item.created_at, reverse=True)


def upsert_asset_candidate(record: AssetCandidateRecord, *, workspace_dir: Path | None = None) -> AssetCandidateRecord:
    records = _load_records(workspace_dir)
    for index, current in enumerate(records):
        if current.id == record.id:
            records[index] = record
            _save_records(records, workspace_dir)
            return record
    records.append(record)
    _save_records(records, workspace_dir)
    return record


def review_asset_candidate(
    candidate_id: str,
    request: AssetCandidateReviewRequest,
    *,
    workspace_dir: Path | None = None,
) -> AssetCandidateReviewResponse:
    normalized_id = candidate_id.strip()
    records = _load_records(workspace_dir)
    index = next((idx for idx, record in enumerate(records) if record.id == normalized_id), -1)
    if index < 0:
        raise KeyError(normalized_id)
    status = _normalize_review_status(request.status)
    timestamp = _now()
    current = records[index]
    relationships = [
        *current.relationships,
        *[item for item in request.link_relationships if isinstance(item, dict)],
    ]
    asset: AssetRecord | None = None
    asset_id = current.asset_id or _asset_id_from_candidate(current)
    reviewed = current.model_copy(
        update={
            "asset_id": asset_id,
            "status": status,
            "review_state": status,
            "relationships": relationships,
            "provenance": {
                **current.provenance,
                "last_review_status": status,
                "last_reviewer_employee_id": request.reviewer_employee_id.strip() or "clara",
                "last_review_reason": request.reason.strip(),
                "merge_target_asset_id": request.merge_target_asset_id.strip(),
            },
            "updated_at": timestamp,
        }
    )
    records[index] = reviewed
    _save_records(records, workspace_dir)
    review = AssetReviewRecord(
        id=f"asset-review-{_safe_ref(normalized_id)}-{len(_load_review_records(workspace_dir)) + 1}",
        candidate_id=reviewed.id,
        asset_id=asset_id if status == "approved" else request.merge_target_asset_id.strip(),
        status=status,
        reviewer_employee_id=request.reviewer_employee_id.strip() or "clara",
        reason=request.reason.strip(),
        merge_target_asset_id=request.merge_target_asset_id.strip(),
        link_relationships=[item for item in request.link_relationships if isinstance(item, dict)],
        created_at=timestamp,
        updated_at=timestamp,
    )
    _append_review_record(review, workspace_dir)
    if status == "approved":
        asset = upsert_asset_record(_asset_from_candidate(reviewed, review, workspace_dir=workspace_dir), workspace_dir=workspace_dir)
    elif status in {"merged", "linked"}:
        _apply_relationship_review(reviewed, review, workspace_dir=workspace_dir)
    return AssetCandidateReviewResponse(
        candidate=reviewed,
        review=review,
        asset=asset,
        saved_paths={
            "asset_candidates": _relative(asset_candidates_path(workspace_dir)),
            "asset_records": _relative(asset_records_path(workspace_dir)),
            "asset_reviews": _relative(asset_reviews_path(workspace_dir)),
        },
    )


def review_asset_candidates(
    request: AssetCandidateBatchReviewRequest,
    *,
    workspace_dir: Path | None = None,
) -> AssetCandidateBatchReviewResponse:
    status = _normalize_review_status(request.status)
    candidate_ids = _unique_candidate_ids(request.candidate_ids)
    if not candidate_ids:
        raise ValueError("At least one Asset candidate id is required for batch review.")
    if status in {"merged", "linked"} and not request.merge_target_asset_id.strip():
        raise ValueError("A merge/link target Asset ID is required for batch review with merged or linked status.")

    results: list[AssetCandidateBatchReviewItem] = []
    for candidate_id in candidate_ids:
        try:
            response = review_asset_candidate(
                candidate_id,
                AssetCandidateReviewRequest(
                    status=status,
                    reviewer_employee_id=request.reviewer_employee_id,
                    reason=request.reason or f"Batch {status} from Assets review queue.",
                    merge_target_asset_id=request.merge_target_asset_id,
                    link_relationships=request.link_relationships,
                ),
                workspace_dir=workspace_dir,
            )
            results.append(
                AssetCandidateBatchReviewItem(
                    candidate_id=candidate_id,
                    status="reviewed",
                    response=response,
                )
            )
        except KeyError:
            results.append(
                AssetCandidateBatchReviewItem(
                    candidate_id=candidate_id,
                    status="failed",
                    error=f"Asset candidate not found: {candidate_id}",
                )
            )
        except ValueError as exc:
            results.append(
                AssetCandidateBatchReviewItem(
                    candidate_id=candidate_id,
                    status="failed",
                    error=str(exc),
                )
            )

    reviewed_count = len([item for item in results if item.status == "reviewed"])
    failed_count = len(results) - reviewed_count
    return AssetCandidateBatchReviewResponse(
        status="completed" if failed_count == 0 else "partial_failed" if reviewed_count else "failed",
        requested_count=len(candidate_ids),
        reviewed_count=reviewed_count,
        failed_count=failed_count,
        results=results,
        saved_paths={
            "asset_candidates": _relative(asset_candidates_path(workspace_dir)),
            "asset_records": _relative(asset_records_path(workspace_dir)),
            "asset_reviews": _relative(asset_reviews_path(workspace_dir)),
        },
    )


def record_asset_retrieval_evaluation(
    request: AssetRetrievalEvaluationRequest,
    retrieved_assets: list[dict[str, Any]],
    *,
    workspace_dir: Path | None = None,
) -> AssetRetrievalEvaluationResponse:
    expected_ids = _unique_candidate_ids(request.expected_asset_ids)
    retrieved = retrieved_assets[: request.top_k]
    retrieved_ids = [str(item.get("id") or "").strip() for item in retrieved if str(item.get("id") or "").strip()]
    matched_ids = [
        expected_id
        for expected_id in expected_ids
        if any(_asset_item_matches_expected_id(item, expected_id) for item in retrieved)
    ]
    missing_ids = [expected_id for expected_id in expected_ids if expected_id not in set(matched_ids)]
    precision = round(len(matched_ids) / len(retrieved_ids), 4) if retrieved_ids else 0.0
    recall = round(len(matched_ids) / len(expected_ids), 4) if expected_ids else 0.0
    record = AssetRetrievalEvaluationRecord(
        id=f"asset-retrieval-eval-{uuid4().hex[:12]}",
        query=request.query.strip(),
        expected_asset_ids=expected_ids,
        retrieved_asset_ids=retrieved_ids,
        matched_asset_ids=matched_ids,
        missing_asset_ids=missing_ids,
        precision=precision,
        recall=recall,
        top_k=request.top_k,
        source_ticket_id=request.source_ticket_id.strip(),
        source_run_id=request.source_run_id.strip(),
        evaluator_employee_id=request.evaluator_employee_id.strip() or "clara",
        usefulness_status=request.usefulness_status.strip().lower() or "unreviewed",
        created_at=_now(),
    )
    records = _load_retrieval_evaluations(workspace_dir)
    records.append(record)
    _save_retrieval_evaluations(records, workspace_dir)
    return AssetRetrievalEvaluationResponse(
        record=record,
        retrieved_assets=retrieved,
        saved_paths={"retrieval_evaluations": _relative(asset_retrieval_evaluations_path(workspace_dir))},
    )


def upsert_asset_record(record: AssetRecord, *, workspace_dir: Path | None = None) -> AssetRecord:
    records = _load_asset_records(workspace_dir)
    for index, current in enumerate(records):
        if current.id == record.id:
            records[index] = record
            _save_asset_records(records, workspace_dir)
            return record
    records.append(record)
    _save_asset_records(records, workspace_dir)
    return record


def sync_asset_usefulness_from_memory_candidate(
    candidate: Any,
    *,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    payload = candidate.model_dump(mode="json") if hasattr(candidate, "model_dump") else dict(candidate)
    candidate_id = str(payload.get("id") or "").strip()
    if not candidate_id:
        raise ValueError("Memory candidate is missing id.")
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    usage_summary = provenance.get("usage_summary") if isinstance(provenance.get("usage_summary"), dict) else {}
    usage_history = provenance.get("usage_history") if isinstance(provenance.get("usage_history"), list) else []
    if not usage_summary and not usage_history:
        return {
            "source_memory_candidate_id": candidate_id,
            "asset_candidate_id": "",
            "asset_record_ids": [],
            "usefulness_stats": {},
        }

    timestamp = _now()
    asset_candidate_id = f"asset-candidate-{candidate_id}"
    asset_id = str(provenance.get("asset_id") or candidate_id).strip() or candidate_id
    records = _load_records(workspace_dir)
    matched_candidate = False
    for index, record in enumerate(records):
        if record.id != asset_candidate_id and record.source_candidate_id != candidate_id and record.asset_id != asset_id:
            continue
        matched_candidate = True
        records[index] = record.model_copy(
            update={
                "usefulness_stats": usage_summary,
                "provenance": {
                    **record.provenance,
                    "usage_summary": usage_summary,
                    "usage_history": [item for item in usage_history if isinstance(item, dict)],
                    "last_usefulness_sync_at": timestamp,
                    "source_memory_candidate_id": candidate_id,
                },
                "updated_at": timestamp,
            }
        )
    if matched_candidate:
        _save_records(records, workspace_dir)
    else:
        upsert_asset_candidate_from_memory_candidate(candidate, workspace_dir=workspace_dir)

    asset_records = _load_asset_records(workspace_dir)
    updated_asset_ids: list[str] = []
    for index, record in enumerate(asset_records):
        record_provenance = record.provenance if isinstance(record.provenance, dict) else {}
        if (
            record.id != asset_id
            and record.content_ref != f"memory_candidate://{candidate_id}"
            and record_provenance.get("source_memory_candidate_id") != candidate_id
            and record_provenance.get("source_candidate_id") != candidate_id
        ):
            continue
        updated_asset_ids.append(record.id)
        asset_records[index] = record.model_copy(
            update={
                "usefulness_stats": usage_summary,
                "provenance": {
                    **record_provenance,
                    "usage_summary": usage_summary,
                    "usage_history": [item for item in usage_history if isinstance(item, dict)],
                    "last_usefulness_sync_at": timestamp,
                    "source_memory_candidate_id": candidate_id,
                },
                "updated_at": timestamp,
            }
        )
    if updated_asset_ids:
        _save_asset_records(asset_records, workspace_dir)

    return {
        "source_memory_candidate_id": candidate_id,
        "asset_candidate_id": asset_candidate_id,
        "asset_record_ids": updated_asset_ids,
        "usefulness_stats": usage_summary,
    }


async def project_asset_record_to_graphiti(
    asset_id: str,
    *,
    workspace_dir: Path | None = None,
) -> AssetRecordProjectionResponse:
    normalized_id = asset_id.strip()
    record = next((item for item in _load_asset_records(workspace_dir) if item.id == normalized_id), None)
    if record is None:
        raise KeyError(normalized_id)
    asset_status = record.status.strip().lower()
    if asset_status not in {"approved", "accepted", "validated"}:
        raise ValueError("Only approved, accepted, or validated AssetRecords can project into Graphiti.")

    previous_workspace = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if workspace_dir is not None:
        os.environ["AITEAMOS_WORKSPACE_DIR"] = str(_workspace_root(workspace_dir))
    try:
        existing = _graphiti_ingestion_record(normalized_id, workspace_dir=workspace_dir)
        if existing is not None:
            graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
            skipped = {
                "asset_id": normalized_id,
                "asset_type": record.asset_type,
                "reason": "already_ingested",
                "episode_id": str(graphiti_status.get("episode_id") or ""),
            }
            _mark_asset_record_graphiti_projection(
                record,
                graphiti_status if isinstance(graphiti_status, dict) else {},
                workspace_dir=workspace_dir,
            )
            return AssetRecordProjectionResponse(
                asset_id=normalized_id,
                status="skipped",
                detail="Approved AssetRecord already exists in Graphiti ingestion audit.",
                skipped_asset=skipped,
                saved_paths={
                    "asset_records": _relative(asset_records_path(workspace_dir)),
                    "graphiti_state": _relative(graphiti_state_path(workspace_dir)),
                },
            )

        from .memory_service import ingest_durable_asset_to_graphiti

        ingested = await ingest_durable_asset_to_graphiti(_durable_asset_request_from_record(record))
        ingested_payload = ingested.model_dump(mode="json")
        _mark_asset_record_graphiti_projection(record, ingested_payload, workspace_dir=workspace_dir)
        return AssetRecordProjectionResponse(
            asset_id=normalized_id,
            status="ingested",
            detail="Approved AssetRecord was projected to Graphiti.",
            ingested_asset=ingested_payload,
            saved_paths={
                "asset_records": _relative(asset_records_path(workspace_dir)),
                "graphiti_state": _relative(graphiti_state_path(workspace_dir)),
            },
        )
    finally:
        if workspace_dir is not None:
            if previous_workspace is None:
                os.environ.pop("AITEAMOS_WORKSPACE_DIR", None)
            else:
                os.environ["AITEAMOS_WORKSPACE_DIR"] = previous_workspace


async def project_asset_record_relationships_to_graphiti(
    asset_id: str,
    *,
    workspace_dir: Path | None = None,
) -> AssetRecordRelationshipProjectionResponse:
    normalized_id = asset_id.strip()
    record = next((item for item in _load_asset_records(workspace_dir) if item.id == normalized_id), None)
    if record is None:
        raise KeyError(normalized_id)
    asset_status = record.status.strip().lower()
    if asset_status not in {"approved", "accepted", "validated"}:
        raise ValueError("Only approved, accepted, or validated AssetRecords can project relationships into Graphiti.")

    previous_workspace = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if workspace_dir is not None:
        os.environ["AITEAMOS_WORKSPACE_DIR"] = str(_workspace_root(workspace_dir))
    ingested: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    unsupported: list[dict[str, str]] = []
    try:
        from .memory_service import ingest_durable_asset_relationship_to_graphiti

        for relationship in record.relationships:
            request, issue = _durable_relationship_request_from_record(record, relationship)
            if issue is not None:
                unsupported.append(issue)
                continue
            projected = await ingest_durable_asset_relationship_to_graphiti(request)
            projected_payload = projected.model_dump(mode="json")
            if projected.status == "ingested":
                ingested.append(projected_payload)
            elif projected.status == "skipped":
                skipped.append(
                    projected.skipped_asset
                    or {
                        "asset_id": projected.relationship_id,
                        "asset_type": "asset_relationship",
                        "reason": "already_ingested",
                        "episode_id": "",
                    }
                )
            else:
                unsupported.append(
                    {
                        "relationship_type": projected.relationship_type,
                        "target_asset_id": projected.target_asset_id,
                        "reason": projected.detail,
                    }
                )
        if ingested or skipped:
            _mark_asset_record_graphiti_relationships(
                record,
                [*ingested, *[{"skipped_asset": item} for item in skipped]],
                workspace_dir=workspace_dir,
            )
        status = "ingested" if ingested else "skipped" if skipped else "unsupported" if unsupported else "no_relationships"
        return AssetRecordRelationshipProjectionResponse(
            asset_id=normalized_id,
            status=status,
            detail=_relationship_projection_detail(status),
            ingested_relationships=ingested,
            skipped_relationships=skipped,
            unsupported_relationships=unsupported,
            saved_paths={
                "asset_records": _relative(asset_records_path(workspace_dir)),
                "graphiti_state": _relative(graphiti_state_path(workspace_dir)),
            },
        )
    finally:
        if workspace_dir is not None:
            if previous_workspace is None:
                os.environ.pop("AITEAMOS_WORKSPACE_DIR", None)
            else:
                os.environ["AITEAMOS_WORKSPACE_DIR"] = previous_workspace


def upsert_asset_candidate_from_memory_candidate(
    candidate: Any,
    *,
    workspace_dir: Path | None = None,
) -> AssetCandidateRecord:
    payload = candidate.model_dump(mode="json") if hasattr(candidate, "model_dump") else dict(candidate)
    candidate_id = str(payload.get("id") or "").strip()
    if not candidate_id:
        raise ValueError("Memory candidate is missing id.")
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    employee_ids = payload.get("employee_ids") if isinstance(payload.get("employee_ids"), list) else []
    relationships = provenance.get("relationships") if isinstance(provenance.get("relationships"), list) else []
    usage_summary = provenance.get("usage_summary") if isinstance(provenance.get("usage_summary"), dict) else {}
    content = str(payload.get("content") or "").strip()
    status = str(payload.get("status") or "proposed").strip().lower() or "proposed"
    memory_type = str(payload.get("memory_type") or provenance.get("asset_type") or "memory").strip().lower()
    asset_type = _asset_type_from_memory_type(memory_type, provenance)
    record = AssetCandidateRecord(
        id=f"asset-candidate-{candidate_id}",
        source_candidate_id=candidate_id,
        asset_id=str(provenance.get("asset_id") or candidate_id),
        asset_type=asset_type,
        title=_candidate_title(content, provenance, asset_type),
        content=content,
        content_ref=f"memory_candidate://{candidate_id}",
        status=status,
        scope_kind=str(payload.get("scope_kind") or "project"),
        scope_ref=str(payload.get("scope_ref") or "aiteamos"),
        owner_employee_id=str(employee_ids[0]) if employee_ids else str(provenance.get("source_employee_id") or ""),
        source_kind=str(payload.get("source_kind") or provenance.get("source_kind") or ""),
        source_ref=str(payload.get("source_ref") or provenance.get("source_ref") or ""),
        provenance={
            **provenance,
            "source_memory_candidate_id": candidate_id,
            "source_asset_candidate_id": f"asset-candidate-{candidate_id}",
        },
        provider="local_file",
        provider_ref=f"{_relative(asset_candidates_path(workspace_dir))}#asset-candidate-{candidate_id}",
        relationships=[item for item in relationships if isinstance(item, dict)],
        review_state=status,
        usefulness_stats=usage_summary,
        created_at=str(payload.get("created_at") or _now()),
        updated_at=str(payload.get("updated_at") or _now()),
    )
    return upsert_asset_candidate(record, workspace_dir=workspace_dir)


def propose_ticket_closeout_asset_candidates(
    ticket_id: str,
    request: TicketCloseoutAssetCandidateRequest | None = None,
    *,
    workspace_dir: Path | None = None,
) -> TicketCloseoutAssetCandidateResponse:
    from .ticket_service import TicketReportRequest, add_ticket_report, get_ticket

    normalized_ticket_id = ticket_id.strip()
    ticket = get_ticket(normalized_ticket_id)
    if ticket is None:
        raise KeyError(normalized_ticket_id)
    if not _ticket_is_closeout_ready(ticket):
        raise ValueError("Only validated, completed, done, or closed Tickets can propose closeout Asset candidates.")

    payload = request or TicketCloseoutAssetCandidateRequest()
    existing_records = {record.id: record for record in _load_records(workspace_dir)}
    existing_ids = set(existing_records)
    candidates = []
    for candidate in _ticket_closeout_candidate_records(ticket, payload, workspace_dir=workspace_dir):
        current = existing_records.get(candidate.id)
        if current is not None and current.status in {"approved", "rejected", "merged", "linked"}:
            candidates.append(current)
            continue
        candidates.append(upsert_asset_candidate(candidate, workspace_dir=workspace_dir))

    evidence_refs = [f"asset-candidate:{candidate.id}" for candidate in candidates]
    report_id = _existing_closeout_report_id(ticket, evidence_refs)
    report_created = False
    if not report_id:
        updated = add_ticket_report(
            normalized_ticket_id,
            TicketReportRequest(
                reporter_employee_id=payload.actor_employee_id.strip() or "clara",
                reporter_role=payload.actor_role.strip(),
                content=_closeout_report_content(ticket, candidates, payload),
                evidence=evidence_refs,
                report_type="ticket_closeout_candidates",
                source_run_id=f"ticket-closeout-candidates:{normalized_ticket_id}",
            ),
        )
        report_id = _existing_closeout_report_id(updated, evidence_refs)
        report_created = True

    all_existing = all(candidate.id in existing_ids for candidate in candidates)
    status = "skipped" if all_existing and not report_created else "proposed"
    return TicketCloseoutAssetCandidateResponse(
        ticket_id=normalized_ticket_id,
        status=status,
        detail=(
            "Ticket closeout Asset candidates were already proposed."
            if status == "skipped"
            else "Ticket closeout Asset candidates were proposed for review."
        ),
        candidates=candidates,
        report_id=report_id,
        saved_paths={"asset_candidates": _relative(asset_candidates_path(workspace_dir))},
    )


async def settle_ticket_closeout_assets(
    ticket_id: str,
    request: TicketCloseoutSettlementRequest | None = None,
    *,
    workspace_dir: Path | None = None,
) -> TicketCloseoutSettlementResponse:
    from .ticket_service import TicketReportRequest, add_ticket_report, get_ticket

    normalized_ticket_id = ticket_id.strip()
    payload = request or TicketCloseoutSettlementRequest()
    proposal = propose_ticket_closeout_asset_candidates(
        normalized_ticket_id,
        TicketCloseoutAssetCandidateRequest(
            actor_employee_id=payload.actor_employee_id,
            actor_role=payload.actor_role,
            reason=payload.reason or "Settle validated Ticket closeout Assets.",
        ),
        workspace_dir=workspace_dir,
    )
    selected_candidates = _settlement_candidates_by_type(proposal.candidates, payload.asset_types)
    candidate_ids = [candidate.id for candidate in selected_candidates]
    proposed_candidate_ids = [
        candidate.id
        for candidate in selected_candidates
        if candidate.status == "proposed" or candidate.review_state == "proposed"
    ]
    review: AssetCandidateBatchReviewResponse | None = None
    if payload.approve_candidates and proposed_candidate_ids:
        review = review_asset_candidates(
            AssetCandidateBatchReviewRequest(
                candidate_ids=proposed_candidate_ids,
                status="approved",
                reviewer_employee_id=payload.reviewer_employee_id.strip() or payload.actor_employee_id.strip() or "clara",
                reason=payload.reason or "Approved validated Ticket closeout Assets for settlement.",
            ),
            workspace_dir=workspace_dir,
        )
    elif payload.approve_candidates:
        review = AssetCandidateBatchReviewResponse(
            status="skipped",
            requested_count=len(candidate_ids),
            reviewed_count=0,
            failed_count=0,
            results=[],
            saved_paths={
                "asset_candidates": _relative(asset_candidates_path(workspace_dir)),
                "asset_records": _relative(asset_records_path(workspace_dir)),
                "asset_reviews": _relative(asset_reviews_path(workspace_dir)),
            },
        )

    candidates = [
        candidate
        for candidate in _load_records(workspace_dir)
        if candidate.id in set(candidate_ids)
    ]
    asset_ids = _settlement_asset_ids(candidates, workspace_dir=workspace_dir)
    projections: list[TicketCloseoutSettlementProjection] = []
    if payload.project_graphiti:
        for asset_id in asset_ids:
            projections.append(
                await _project_settled_asset(
                    asset_id,
                    project_relationships=payload.project_relationships,
                    workspace_dir=workspace_dir,
                )
            )

    ticket = get_ticket(normalized_ticket_id)
    if ticket is None:
        raise KeyError(normalized_ticket_id)
    evidence_refs = [
        *[f"asset-candidate:{candidate_id}" for candidate_id in candidate_ids],
        *[f"asset-registry:{asset_id}" for asset_id in asset_ids],
        *[
            f"graphiti:{projection.projection.ingested_asset.get('episode_id')}"
            for projection in projections
            if projection.projection is not None
            and projection.projection.ingested_asset is not None
            and projection.projection.ingested_asset.get("episode_id")
        ],
    ]
    report_id = _existing_closeout_settlement_report_id(ticket, evidence_refs)
    if not report_id:
        updated = add_ticket_report(
            normalized_ticket_id,
            TicketReportRequest(
                reporter_employee_id=payload.actor_employee_id.strip() or "clara",
                reporter_role=payload.actor_role.strip(),
                content=_closeout_settlement_report_content(
                    candidate_ids=candidate_ids,
                    asset_ids=asset_ids,
                    projections=projections,
                    request=payload,
                ),
                evidence=evidence_refs,
                report_type="ticket_closeout_settlement",
                source_run_id=f"ticket-closeout-settlement:{normalized_ticket_id}",
            ),
        )
        report_id = _existing_closeout_settlement_report_id(updated, evidence_refs)

    status = _closeout_settlement_status(
        approve_requested=payload.approve_candidates,
        project_requested=payload.project_graphiti,
        reviewed_count=review.reviewed_count if review is not None else 0,
        projection_count=len([item for item in projections if item.projection and item.projection.status in {"ingested", "skipped"}]),
        projection_error_count=len([item for item in projections if item.error]),
        asset_count=len(asset_ids),
    )
    return TicketCloseoutSettlementResponse(
        ticket_id=normalized_ticket_id,
        status=status,
        detail=_closeout_settlement_detail(status),
        proposal=proposal,
        review=review,
        candidates=candidates,
        asset_ids=asset_ids,
        projections=projections,
        report_id=report_id,
        saved_paths={
            "asset_candidates": _relative(asset_candidates_path(workspace_dir)),
            "asset_records": _relative(asset_records_path(workspace_dir)),
            "asset_reviews": _relative(asset_reviews_path(workspace_dir)),
            "graphiti_state": _relative(graphiti_state_path(workspace_dir)),
        },
    )


def propose_ticket_failure_retrospective_asset_candidates(
    ticket_id: str,
    request: TicketFailureRetrospectiveAssetCandidateRequest | None = None,
    *,
    workspace_dir: Path | None = None,
) -> TicketFailureRetrospectiveAssetCandidateResponse:
    from .ticket_loop_service import list_ticket_loop_queue
    from .ticket_service import TicketReportRequest, add_ticket_report, get_ticket

    normalized_ticket_id = ticket_id.strip()
    ticket = get_ticket(normalized_ticket_id)
    if ticket is None:
        raise KeyError(normalized_ticket_id)
    payload = request or TicketFailureRetrospectiveAssetCandidateRequest()
    failed_items = [
        item
        for item in list_ticket_loop_queue(workspace_dir=_workspace_dir(workspace_dir))
        if item.ticket_id == normalized_ticket_id and item.status.strip().lower() in {"failed", "blocked"}
    ]
    if len(failed_items) < payload.min_failed_items:
        raise ValueError(
            f"At least {payload.min_failed_items} failed or blocked loop queue items are required "
            "before proposing a failure retrospective Asset candidate."
        )

    existing_ids = {record.id for record in _load_records(workspace_dir)}
    candidate = _ticket_failure_retrospective_candidate_record(
        ticket,
        failed_items,
        payload,
        workspace_dir=workspace_dir,
    )
    upsert_asset_candidate(candidate, workspace_dir=workspace_dir)
    evidence_refs = [f"asset-candidate:{candidate.id}"]
    report_id = _existing_failure_retrospective_report_id(ticket, evidence_refs)
    report_created = False
    if not report_id:
        updated = add_ticket_report(
            normalized_ticket_id,
            TicketReportRequest(
                reporter_employee_id=payload.actor_employee_id.strip() or "clara",
                reporter_role=payload.actor_role.strip(),
                content=_failure_retrospective_report_content(ticket, candidate, failed_items, payload),
                evidence=evidence_refs,
                report_type="ticket_loop_failure_retrospective_candidate",
                source_run_id=f"ticket-loop-failure-retrospective:{normalized_ticket_id}",
            ),
        )
        report_id = _existing_failure_retrospective_report_id(updated, evidence_refs)
        report_created = True

    status = "skipped" if candidate.id in existing_ids and not report_created else "proposed"
    return TicketFailureRetrospectiveAssetCandidateResponse(
        ticket_id=normalized_ticket_id,
        status=status,
        detail=(
            "Ticket loop failure retrospective Asset candidate was already proposed."
            if status == "skipped"
            else "Ticket loop failure retrospective Asset candidate was proposed for review."
        ),
        candidates=[candidate],
        report_id=report_id,
        failed_item_count=len(failed_items),
        saved_paths={"asset_candidates": _relative(asset_candidates_path(workspace_dir))},
    )


def _ticket_failure_retrospective_candidate_record(
    ticket: Any,
    failed_items: list[Any],
    request: TicketFailureRetrospectiveAssetCandidateRequest,
    *,
    workspace_dir: Path | None = None,
) -> AssetCandidateRecord:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    safe_ticket_id = _safe_ref(ticket_id)
    title = str(getattr(ticket, "title", "") or ticket_id).strip()
    timestamp = _now()
    owner = _first_string(getattr(ticket, "assigned_employee_id", ""), request.actor_employee_id)
    queue_refs = [str(getattr(item, "queue_id", "") or "").strip() for item in failed_items if str(getattr(item, "queue_id", "") or "").strip()]
    run_refs = [str(getattr(item, "run_id", "") or "").strip() for item in failed_items if str(getattr(item, "run_id", "") or "").strip()]
    relationships = [
        {"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket_id},
        *[
            {"type": "derived_from_loop_queue_item", "target_kind": "ticket_loop_queue", "target_ref": queue_ref}
            for queue_ref in queue_refs
        ],
    ]
    candidate_id = f"asset-candidate-ticket-loop-failure-retrospective-{safe_ticket_id}"
    return AssetCandidateRecord(
        id=candidate_id,
        source_candidate_id="",
        asset_id=f"ticket-loop-failure-retrospective-{safe_ticket_id}",
        asset_type="failure_retrospective",
        title=f"Failure retrospective: {title}",
        content=_ticket_failure_retrospective_content(ticket, failed_items, request),
        content_ref=f"ticket://{ticket_id}#loop-failure-retrospective",
        status="proposed",
        scope_kind="ticket",
        scope_ref=ticket_id,
        owner_employee_id=owner,
        source_kind="ticket_loop_failure_retrospective",
        source_ref=f"tickets/{ticket_id}/loop/queue",
        provenance={
            "source_ticket_id": ticket_id,
            "source_kind": "ticket_loop_failure_retrospective",
            "source_ref": f"tickets/{ticket_id}/loop/queue",
            "source_employee_id": owner,
            "actor_employee_id": request.actor_employee_id.strip() or "clara",
            "actor_role": request.actor_role.strip(),
            "reason": request.reason.strip(),
            "ticket_status": str(getattr(ticket, "status", "") or "").strip(),
            "failed_item_count": len(failed_items),
            "queue_item_ids": queue_refs,
            "run_ids": run_refs,
            "failure_statuses": sorted({str(getattr(item, "status", "") or "").strip().lower() for item in failed_items if str(getattr(item, "status", "") or "").strip()}),
            "relationships": relationships,
            "generated_at": timestamp,
        },
        provider="local_file",
        provider_ref=f"{_relative(asset_candidates_path(workspace_dir))}#{candidate_id}",
        relationships=relationships,
        review_state="proposed",
        usefulness_stats={},
        created_at=timestamp,
        updated_at=timestamp,
    )


def _ticket_failure_retrospective_content(
    ticket: Any,
    failed_items: list[Any],
    request: TicketFailureRetrospectiveAssetCandidateRequest,
) -> str:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    title = str(getattr(ticket, "title", "") or ticket_id).strip()
    reason = request.reason.strip()
    item_lines = [
        _compact_text(
            "Queue item "
            f"{str(getattr(item, 'queue_id', '') or '-')} "
            f"run={str(getattr(item, 'run_id', '') or '-')} "
            f"status={str(getattr(item, 'status', '') or '-')} "
            f"error={str(getattr(item, 'error', '') or '') or _queue_item_response_error(item) or '-'} "
            f"reason={str(getattr(item, 'reason', '') or '-')}",
            320,
        )
        for item in failed_items[-8:]
    ]
    return _compact_text(
        f"Ticket loop failure retrospective for {ticket_id} ({title}). "
        f"Failed or blocked queue items: {len(failed_items)}. "
        f"Reason: {reason or '-'}. "
        "Retrospective facts: "
        + " | ".join(item_lines),
        1800,
    )


def _queue_item_response_error(item: Any) -> str:
    response = getattr(item, "response", {})
    if not isinstance(response, dict):
        return ""
    errors = response.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[-1]
        if isinstance(first, dict):
            return _first_string(first.get("detail"), first.get("reason"))
    steps = response.get("steps")
    if isinstance(steps, list) and steps:
        step = steps[-1]
        if isinstance(step, dict):
            return _first_string(step.get("ingestion_blocker"), _queue_item_response_error_from_result(step.get("result")))
    return ""


def _queue_item_response_error_from_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[-1]
        if isinstance(first, dict):
            return _first_string(first.get("detail"), first.get("reason"))
    return _first_string(result.get("report"))


def _failure_retrospective_report_content(
    ticket: Any,
    candidate: AssetCandidateRecord,
    failed_items: list[Any],
    request: TicketFailureRetrospectiveAssetCandidateRequest,
) -> str:
    reason = request.reason.strip()
    reason_text = f" Reason: {reason}" if reason else ""
    return _compact_text(
        f"Proposed Ticket loop failure retrospective Asset candidate for review: "
        f"{candidate.asset_type}:{candidate.id}. Failed or blocked queue items: {len(failed_items)}.{reason_text}",
        1200,
    )


def _existing_failure_retrospective_report_id(ticket: Any, evidence_refs: list[str]) -> str:
    expected = set(evidence_refs)
    for report in reversed(getattr(ticket, "reports", []) or []):
        if str(getattr(report, "report_type", "") or "").strip().lower() != "ticket_loop_failure_retrospective_candidate":
            continue
        evidence = {str(item).strip() for item in (getattr(report, "evidence", []) or []) if str(item).strip()}
        if expected.issubset(evidence):
            return str(getattr(report, "id", "") or "").strip()
    return ""


def _workspace_root(workspace_dir: Path | None = None) -> Path:
    if workspace_dir is not None:
        resolved = workspace_dir.resolve()
        return resolved.parent if resolved.name == ".aiteamos" else resolved
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _workspace_dir(workspace_dir: Path | None = None) -> Path:
    explicit = workspace_dir.resolve() if workspace_dir is not None else None
    if explicit is not None and explicit.name == ".aiteamos":
        path = explicit
    else:
        path = _workspace_root(workspace_dir) / ".aiteamos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_records(workspace_dir: Path | None = None) -> list[AssetCandidateRecord]:
    path = asset_candidates_path(workspace_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload if isinstance(payload, list) else payload.get("candidates", []) if isinstance(payload, dict) else []
    return [AssetCandidateRecord.model_validate(item) for item in items if isinstance(item, dict)]


def _load_asset_records(workspace_dir: Path | None = None) -> list[AssetRecord]:
    path = asset_records_path(workspace_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload if isinstance(payload, list) else payload.get("assets", []) if isinstance(payload, dict) else []
    return [AssetRecord.model_validate(item) for item in items if isinstance(item, dict)]


def _load_review_records(workspace_dir: Path | None = None) -> list[AssetReviewRecord]:
    path = asset_reviews_path(workspace_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload if isinstance(payload, list) else payload.get("reviews", []) if isinstance(payload, dict) else []
    return [AssetReviewRecord.model_validate(item) for item in items if isinstance(item, dict)]


def _load_retrieval_evaluations(workspace_dir: Path | None = None) -> list[AssetRetrievalEvaluationRecord]:
    path = asset_retrieval_evaluations_path(workspace_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload if isinstance(payload, list) else payload.get("evaluations", []) if isinstance(payload, dict) else []
    return [AssetRetrievalEvaluationRecord.model_validate(item) for item in items if isinstance(item, dict)]


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _graphiti_ingestion_record(asset_id: str, *, workspace_dir: Path | None = None) -> dict[str, Any] | None:
    target_id = asset_id.strip()
    state = _read_json_object(graphiti_state_path(workspace_dir))
    records = state.get("durable_asset_ingestions")
    if not isinstance(records, list):
        return None
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        if str(record.get("asset_id") or "").strip() != target_id:
            continue
        graphiti_status = record.get("graphiti_status")
        if isinstance(graphiti_status, dict) and graphiti_status.get("status") == "ingested":
            return record
    return None


def _save_records(records: list[AssetCandidateRecord], workspace_dir: Path | None = None) -> None:
    path = asset_candidates_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump(mode="json") for record in sorted(records, key=lambda item: item.created_at)]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _save_asset_records(records: list[AssetRecord], workspace_dir: Path | None = None) -> None:
    path = asset_records_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump(mode="json") for record in sorted(records, key=lambda item: item.created_at)]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _save_review_records(records: list[AssetReviewRecord], workspace_dir: Path | None = None) -> None:
    path = asset_reviews_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump(mode="json") for record in sorted(records, key=lambda item: item.created_at)]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _save_retrieval_evaluations(records: list[AssetRetrievalEvaluationRecord], workspace_dir: Path | None = None) -> None:
    path = asset_retrieval_evaluations_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump(mode="json") for record in sorted(records, key=lambda item: item.created_at)]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_review_record(record: AssetReviewRecord, workspace_dir: Path | None = None) -> None:
    reviews = _load_review_records(workspace_dir)
    reviews.append(record)
    _save_review_records(reviews, workspace_dir)


def _asset_type_from_memory_type(memory_type: str, provenance: dict[str, Any]) -> str:
    explicit = str(provenance.get("asset_type") or "").strip().lower()
    if explicit in {"memory", "doc", "skill", "tool_call", "solution", "suggestion", "decision", "validation_result", "ticket_closeout", "capability"}:
        return explicit
    normalized = memory_type.replace("memory:", "").replace("_candidate", "").strip().lower()
    mapping = {
        "fact": "memory",
        "principle": "memory",
        "summary": "memory",
        "doc": "doc",
        "skill": "skill",
        "decision": "decision",
        "capability": "capability",
        "validated_ticket_summary": "ticket_closeout",
    }
    return mapping.get(normalized, normalized or "memory")


def _candidate_title(content: str, provenance: dict[str, Any], asset_type: str) -> str:
    explicit = str(provenance.get("title") or "").strip()
    if explicit:
        return explicit[:160]
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    cleaned = re.sub(r"\s+", " ", first_line).strip()
    return (cleaned[:120] if cleaned else f"{asset_type.replace('_', ' ').title()} candidate")


def _matches_query(record: AssetCandidateRecord, query: str) -> bool:
    haystack = " ".join(
        [
            record.id,
            record.source_candidate_id,
            record.asset_type,
            record.title,
            record.content,
            record.status,
            record.scope_kind,
            record.scope_ref,
            record.owner_employee_id,
            record.source_kind,
            record.source_ref,
            json.dumps(record.provenance, ensure_ascii=False, sort_keys=True),
        ]
    ).lower()
    return all(term in haystack for term in re.split(r"\s+", query) if term)


def _matches_asset_query(record: AssetRecord, query: str) -> bool:
    haystack = " ".join(
        [
            record.id,
            record.asset_type,
            record.title,
            record.content,
            record.status,
            record.scope_kind,
            record.scope_ref,
            record.owner_employee_id,
            record.source_kind,
            record.source_ref,
            json.dumps(record.provenance, ensure_ascii=False, sort_keys=True),
        ]
    ).lower()
    return all(term in haystack for term in re.split(r"\s+", query) if term)


def _normalize_review_status(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {"approve": "approved", "reject": "rejected", "merge": "merged", "link": "linked"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"approved", "rejected", "merged", "linked"}:
        raise ValueError("Asset candidate review status must be approved, rejected, merged, or linked.")
    return normalized


def _unique_candidate_ids(candidate_ids: list[str]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for value in candidate_ids:
        candidate_id = str(value).strip()
        if not candidate_id or candidate_id in seen:
            continue
        ids.append(candidate_id)
        seen.add(candidate_id)
    return ids


def _asset_item_matches_expected_id(item: dict[str, Any], expected_id: str) -> bool:
    normalized_expected = _normalize_asset_eval_id(expected_id)
    if not normalized_expected:
        return False
    return normalized_expected in {_normalize_asset_eval_id(value) for value in _asset_item_identity_values(item)}


def _asset_item_identity_values(item: dict[str, Any]) -> list[str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    provenance = metadata.get("provenance") if isinstance(metadata.get("provenance"), dict) else {}
    values = [
        str(item.get("id") or ""),
        str(metadata.get("asset_registry_id") or ""),
        str(metadata.get("asset_candidate_id") or ""),
        str(metadata.get("memory_id") or ""),
        str(metadata.get("asset_id") or ""),
        str(provenance.get("source_asset_candidate_id") or ""),
        str(provenance.get("source_candidate_id") or ""),
    ]
    for value in list(values):
        if ":" in value:
            values.append(value.split(":", maxsplit=1)[1])
    return values


def _normalize_asset_eval_id(value: str) -> str:
    return str(value or "").strip().lower()


def _asset_id_from_candidate(candidate: AssetCandidateRecord) -> str:
    if candidate.asset_id.strip():
        return candidate.asset_id.strip()
    return f"asset-{_safe_ref(candidate.id)}"


def _asset_from_candidate(
    candidate: AssetCandidateRecord,
    review: AssetReviewRecord,
    *,
    workspace_dir: Path | None = None,
) -> AssetRecord:
    timestamp = _now()
    created_at = candidate.created_at or timestamp
    asset_id = _asset_id_from_candidate(candidate)
    return AssetRecord(
        id=asset_id,
        asset_type=candidate.asset_type,
        title=candidate.title,
        content=candidate.content,
        content_ref=candidate.content_ref,
        status="approved",
        scope_kind=candidate.scope_kind,
        scope_ref=candidate.scope_ref,
        owner_employee_id=candidate.owner_employee_id,
        source_kind=candidate.source_kind,
        source_ref=candidate.source_ref,
        provenance={
            **candidate.provenance,
            "source_asset_candidate_id": candidate.id,
            "source_candidate_id": candidate.source_candidate_id,
            "asset_review_id": review.id,
            "reviewer_employee_id": review.reviewer_employee_id,
            "review_reason": review.reason,
        },
        provider="local_file",
        provider_ref=f"{_relative(asset_records_path(workspace_dir))}#{asset_id}",
        relationships=candidate.relationships,
        review_state="approved",
        usefulness_stats=candidate.usefulness_stats,
        created_at=created_at,
        updated_at=timestamp,
    )


def _durable_asset_request_from_record(record: AssetRecord) -> Any:
    from .memory_service import DurableAssetIngestRequest

    provenance = record.provenance if isinstance(record.provenance, dict) else {}
    provider_refs = provenance.get("provider_refs")
    if not isinstance(provider_refs, list):
        provider_refs = []
    local_provider_ref = {
        "provider": record.provider,
        "provider_ref": record.provider_ref,
        "source_kind": "asset_record",
    }
    if record.provider_ref and local_provider_ref not in provider_refs:
        provider_refs = [*provider_refs, local_provider_ref]
    source_ticket_id = _first_string(
        provenance.get("source_ticket_id"),
        provenance.get("ticket_id"),
        record.scope_ref if record.scope_kind == "ticket" else "",
    )
    source_employee_id = _first_string(
        provenance.get("source_employee_id"),
        provenance.get("employee_id"),
        record.owner_employee_id,
    )
    return DurableAssetIngestRequest(
        asset_id=record.id,
        asset_type=record.asset_type,
        asset_status=record.status,
        content=record.content,
        source_ticket_id=source_ticket_id,
        source_employee_id=source_employee_id,
        source_run_id=_first_string(provenance.get("source_run_id"), provenance.get("run_id")),
        source_report_id=_first_string(provenance.get("source_report_id"), provenance.get("report_id")),
        evidence_id=_first_string(provenance.get("evidence_id"), provenance.get("source_evidence_id")),
        scope={"kind": record.scope_kind, "ref": record.scope_ref},
        version=_first_string(provenance.get("version")),
        provider_refs=[item for item in provider_refs if isinstance(item, dict)],
        source_ref=record.source_ref or record.content_ref or record.provider_ref,
        source_kind=record.source_kind or "asset_record",
        metadata={
            "asset_registry_id": record.id,
            "asset_record_provider": record.provider,
            "asset_record_provider_ref": record.provider_ref,
            "content_ref": record.content_ref,
            "relationships": record.relationships,
            "review_state": record.review_state,
            "source_asset_candidate_id": _first_string(provenance.get("source_asset_candidate_id")),
            "source_memory_candidate_id": _first_string(provenance.get("source_memory_candidate_id")),
            "asset_review_id": _first_string(provenance.get("asset_review_id")),
            "reviewer_employee_id": _first_string(provenance.get("reviewer_employee_id")),
            "review_reason": _first_string(provenance.get("review_reason")),
            "title": record.title,
        },
    )


def _durable_relationship_request_from_record(record: AssetRecord, relationship: dict[str, Any]) -> tuple[Any | None, dict[str, str] | None]:
    from .memory_service import DurableAssetRelationshipIngestRequest

    if not isinstance(relationship, dict):
        return None, {"relationship_type": "", "target_asset_id": "", "reason": "relationship_not_object"}
    relationship_type = _normalize_relationship_type(_first_string(relationship.get("type"), relationship.get("relationship_type")))
    if relationship_type not in _graphiti_relationship_types():
        return None, {
            "relationship_type": relationship_type,
            "target_asset_id": _relationship_target_ref(relationship),
            "reason": "unsupported_relationship_type",
        }
    target_asset_id = _relationship_target_asset_id(relationship)
    if not target_asset_id:
        return None, {
            "relationship_type": relationship_type,
            "target_asset_id": _relationship_target_ref(relationship),
            "reason": "target_is_not_asset",
        }
    provenance = record.provenance if isinstance(record.provenance, dict) else {}
    reason = _first_string(
        relationship.get("reason"),
        relationship.get("detail"),
        relationship.get("summary"),
        provenance.get("review_reason"),
        f"{record.id} {relationship_type} {target_asset_id}",
    )
    confidence = relationship.get("confidence")
    metadata: dict[str, Any] = {
        "reason": reason,
        "review_status": record.review_state,
        "source_kind": record.source_kind or "asset_record",
        "source_ref": record.source_ref or record.content_ref,
    }
    if isinstance(confidence, (int, float)):
        metadata["confidence"] = confidence
    return DurableAssetRelationshipIngestRequest(
        source_asset_id=record.id,
        target_asset_id=target_asset_id,
        relationship_type=relationship_type,
        asset_status=record.status,
        reason=reason,
        source_ticket_id=_first_string(
            provenance.get("source_ticket_id"),
            provenance.get("ticket_id"),
            record.scope_ref if record.scope_kind == "ticket" else "",
        ),
        source_employee_id=_first_string(
            provenance.get("source_employee_id"),
            provenance.get("employee_id"),
            record.owner_employee_id,
        ),
        source_run_id=_first_string(provenance.get("source_run_id"), provenance.get("run_id")),
        source_report_id=_first_string(provenance.get("source_report_id"), provenance.get("report_id")),
        evidence_id=_first_string(provenance.get("evidence_id"), provenance.get("source_evidence_id")),
        scope={"kind": "asset", "ref": record.id},
        provider_refs=_asset_record_provider_refs(record),
        source_ref=record.source_ref or record.content_ref or record.provider_ref,
        metadata=metadata,
    ), None


def _asset_record_provider_refs(record: AssetRecord) -> list[dict[str, Any]]:
    provenance = record.provenance if isinstance(record.provenance, dict) else {}
    provider_refs = provenance.get("provider_refs")
    if not isinstance(provider_refs, list):
        provider_refs = []
    local_ref = {
        "provider": record.provider,
        "provider_ref": record.provider_ref,
        "source_kind": "asset_record",
    }
    if record.provider_ref and local_ref not in provider_refs:
        provider_refs = [*provider_refs, local_ref]
    return [item for item in provider_refs if isinstance(item, dict)]


def _graphiti_relationship_types() -> set[str]:
    return {"supersedes", "conflicts_with", "derived_from", "used_by", "validated_by"}


def _normalize_relationship_type(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "derived_from_ticket": "derived_from",
        "derived_from_asset": "derived_from",
        "reviewed_candidate": "derived_from",
        "used_by_ticket": "used_by",
        "validated_by_ticket": "validated_by",
    }
    return aliases.get(normalized, normalized)


def _relationship_target_ref(relationship: dict[str, Any]) -> str:
    return _first_string(relationship.get("target_asset_id"), relationship.get("target_ref"), relationship.get("target"))


def _relationship_target_asset_id(relationship: dict[str, Any]) -> str:
    direct = _first_string(relationship.get("target_asset_id"))
    if direct:
        return direct
    target_kind = _first_string(relationship.get("target_kind"), relationship.get("target_type")).strip().lower()
    if target_kind in {"asset", "asset_record", "asset_registry"}:
        return _first_string(relationship.get("target_ref"), relationship.get("target"))
    return ""


def _mark_asset_record_graphiti_projection(
    record: AssetRecord,
    graphiti_status: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> AssetRecord:
    timestamp = _now()
    episode_id = _first_string(graphiti_status.get("episode_id"))
    provider_refs = record.provenance.get("provider_refs") if isinstance(record.provenance.get("provider_refs"), list) else []
    graphiti_ref = {
        "provider": "graphiti",
        "provider_ref": episode_id,
        "source_kind": "asset_graph_projection",
        "status": str(graphiti_status.get("status") or ""),
    }
    if episode_id and graphiti_ref not in provider_refs:
        provider_refs = [*provider_refs, graphiti_ref]
    updated = record.model_copy(
        update={
            "provenance": {
                **record.provenance,
                "graphiti_projected_at": timestamp,
                "graphiti_status": graphiti_status,
                "provider_refs": provider_refs,
            },
            "updated_at": timestamp,
        }
    )
    return upsert_asset_record(updated, workspace_dir=workspace_dir)


def _mark_asset_record_graphiti_relationships(
    record: AssetRecord,
    relationships: list[dict[str, Any]],
    *,
    workspace_dir: Path | None = None,
) -> AssetRecord:
    timestamp = _now()
    current = record.provenance.get("graphiti_relationships")
    existing = [item for item in current if isinstance(item, dict)] if isinstance(current, list) else []
    by_id = {str(item.get("relationship_id") or item.get("asset_id") or ""): item for item in existing}
    for item in relationships:
        relationship_id = _first_string(item.get("relationship_id"))
        skipped_asset = item.get("skipped_asset") if isinstance(item.get("skipped_asset"), dict) else {}
        if not relationship_id:
            relationship_id = _first_string(skipped_asset.get("asset_id"))
        if not relationship_id:
            continue
        ingested_asset = item.get("ingested_asset") if isinstance(item.get("ingested_asset"), dict) else {}
        by_id[relationship_id] = {
            "relationship_id": relationship_id,
            "relationship_type": _first_string(item.get("relationship_type")),
            "source_asset_id": _first_string(item.get("source_asset_id"), record.id),
            "target_asset_id": _first_string(item.get("target_asset_id")),
            "status": _first_string(item.get("status"), "skipped" if skipped_asset else ""),
            "episode_id": _first_string(ingested_asset.get("episode_id"), skipped_asset.get("episode_id")),
            "projected_at": timestamp,
        }
    updated = record.model_copy(
        update={
            "provenance": {
                **record.provenance,
                "graphiti_relationships_projected_at": timestamp,
                "graphiti_relationships": list(by_id.values()),
            },
            "updated_at": timestamp,
        }
    )
    return upsert_asset_record(updated, workspace_dir=workspace_dir)


def _relationship_projection_detail(status: str) -> str:
    if status == "ingested":
        return "Approved AssetRecord relationships were projected to Graphiti."
    if status == "skipped":
        return "Approved AssetRecord relationships already exist in Graphiti ingestion audit."
    if status == "unsupported":
        return "No AssetRecord relationships were eligible for Graphiti projection."
    return "AssetRecord has no relationships eligible for Graphiti projection."


def _apply_relationship_review(
    candidate: AssetCandidateRecord,
    review: AssetReviewRecord,
    *,
    workspace_dir: Path | None = None,
) -> None:
    if not review.merge_target_asset_id and not review.link_relationships:
        return
    records = _load_asset_records(workspace_dir)
    target_id = review.merge_target_asset_id
    for index, record in enumerate(records):
        if target_id and record.id != target_id:
            continue
        relationships = [
            *record.relationships,
            *review.link_relationships,
            {
                "type": "reviewed_candidate",
                "target_kind": "asset_candidate",
                "target_ref": candidate.id,
                "review_id": review.id,
                "status": review.status,
            },
        ]
        records[index] = record.model_copy(update={"relationships": relationships, "updated_at": review.updated_at})
        _save_asset_records(records, workspace_dir)
        return


def _settlement_candidates_by_type(
    candidates: list[AssetCandidateRecord],
    asset_types: list[str],
) -> list[AssetCandidateRecord]:
    requested = {item.strip().lower() for item in asset_types if item.strip()}
    if not requested:
        return candidates
    return [candidate for candidate in candidates if candidate.asset_type.strip().lower() in requested]


def _settlement_asset_ids(
    candidates: list[AssetCandidateRecord],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    asset_records = _load_asset_records(workspace_dir)
    ids: list[str] = []
    for candidate in candidates:
        if candidate.status not in {"approved", "accepted", "validated"} and candidate.review_state not in {"approved", "accepted", "validated"}:
            continue
        expected = _asset_id_from_candidate(candidate)
        source_candidate_id = candidate.source_candidate_id.strip()
        record = next(
            (
                item
                for item in asset_records
                if item.id == expected
                or item.provenance.get("source_asset_candidate_id") == candidate.id
                or (source_candidate_id and item.provenance.get("source_candidate_id") == source_candidate_id)
            ),
            None,
        )
        if record is not None and record.id not in ids:
            ids.append(record.id)
    return ids


async def _project_settled_asset(
    asset_id: str,
    *,
    project_relationships: bool,
    workspace_dir: Path | None = None,
) -> TicketCloseoutSettlementProjection:
    try:
        projection = await project_asset_record_to_graphiti(asset_id, workspace_dir=workspace_dir)
    except (KeyError, ValueError) as exc:
        return TicketCloseoutSettlementProjection(asset_id=asset_id, status="blocked", error=str(exc))

    relationship_projection: AssetRecordRelationshipProjectionResponse | None = None
    relationship_error = ""
    if project_relationships:
        try:
            relationship_projection = await project_asset_record_relationships_to_graphiti(asset_id, workspace_dir=workspace_dir)
        except (KeyError, ValueError) as exc:
            relationship_error = str(exc)

    return TicketCloseoutSettlementProjection(
        asset_id=asset_id,
        status="partial_blocked" if relationship_error else projection.status,
        projection=projection,
        relationship_projection=relationship_projection,
        error=relationship_error,
    )


def _existing_closeout_settlement_report_id(ticket: Any, evidence_refs: list[str]) -> str:
    expected = {ref for ref in evidence_refs if ref}
    for report in reversed(getattr(ticket, "reports", []) or []):
        if str(getattr(report, "report_type", "") or "").strip().lower() != "ticket_closeout_settlement":
            continue
        evidence = {str(item).strip() for item in (getattr(report, "evidence", []) or []) if str(item).strip()}
        if expected.issubset(evidence):
            return str(getattr(report, "id", "") or "").strip()
    return ""


def _closeout_settlement_report_content(
    *,
    candidate_ids: list[str],
    asset_ids: list[str],
    projections: list[TicketCloseoutSettlementProjection],
    request: TicketCloseoutSettlementRequest,
) -> str:
    projected = [
        projection.asset_id
        for projection in projections
        if projection.projection is not None and projection.projection.status in {"ingested", "skipped"}
    ]
    blocked = [projection.asset_id for projection in projections if projection.error]
    reason = request.reason.strip()
    return _compact_text(
        "Settled Ticket closeout Assets. "
        f"Candidates: {', '.join(candidate_ids) or '-'}. "
        f"Approved AssetRecords: {', '.join(asset_ids) or '-'}. "
        f"Graphiti projected/skipped: {', '.join(projected) or '-'}. "
        f"Projection blockers: {', '.join(blocked) or '-'}. "
        f"Reason: {reason or '-'}.",
        1400,
    )


def _closeout_settlement_status(
    *,
    approve_requested: bool,
    project_requested: bool,
    reviewed_count: int,
    projection_count: int,
    projection_error_count: int,
    asset_count: int,
) -> str:
    if projection_error_count:
        return "blocked"
    if project_requested and projection_count:
        return "projected"
    if approve_requested and (reviewed_count or asset_count):
        return "approved"
    return "proposed"


def _closeout_settlement_detail(status: str) -> str:
    if status == "blocked":
        return "Ticket closeout settlement hit one or more provider blockers."
    if status == "projected":
        return "Ticket closeout Assets were approved and projected or confirmed in Graphiti."
    if status == "approved":
        return "Ticket closeout Asset candidates were approved into AssetRecords."
    return "Ticket closeout Asset candidates are proposed and awaiting review."


def _ticket_closeout_candidate_records(
    ticket: Any,
    request: TicketCloseoutAssetCandidateRequest,
    *,
    workspace_dir: Path | None = None,
) -> list[AssetCandidateRecord]:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    safe_ticket_id = _safe_ref(ticket_id)
    ticket_title = str(getattr(ticket, "title", "") or ticket_id).strip()
    timestamp = _now()
    owner = _first_string(getattr(ticket, "assigned_employee_id", ""), getattr(ticket, "validation_employee_id", ""))
    provider_refs = _ticket_provider_refs(ticket)
    reports = [report for report in getattr(ticket, "reports", []) or []]
    evidence_refs = [
        str(evidence).strip()
        for report in reports
        for evidence in (getattr(report, "evidence", []) or [])
        if str(evidence).strip()
    ]
    relationships = [{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket_id}]
    base_provenance = {
        "source_ticket_id": ticket_id,
        "source_kind": "ticket_closeout",
        "source_ref": f"tickets/{ticket_id}",
        "source_employee_id": owner,
        "actor_employee_id": request.actor_employee_id.strip() or "clara",
        "actor_role": request.actor_role.strip(),
        "reason": request.reason.strip(),
        "ticket_status": str(getattr(ticket, "status", "") or "").strip(),
        "provider_refs": provider_refs,
        "report_ids": [str(getattr(report, "id", "") or "").strip() for report in reports if str(getattr(report, "id", "") or "").strip()],
        "evidence_refs": evidence_refs,
        "relationships": relationships,
        "generated_at": timestamp,
    }
    candidates = [
        _candidate_from_ticket(
            candidate_id=f"asset-candidate-ticket-closeout-{safe_ticket_id}",
            asset_id=f"ticket-closeout-{safe_ticket_id}",
            asset_type="ticket_closeout",
            title=f"Ticket closeout: {ticket_title}",
            content=_ticket_closeout_content(ticket, reports, evidence_refs),
            content_ref=f"ticket://{ticket_id}#closeout",
            ticket=ticket,
            owner=owner,
            provenance={**base_provenance, "asset_type": "ticket_closeout"},
            relationships=relationships,
            timestamp=timestamp,
            workspace_dir=workspace_dir,
        )
    ]
    solution_reports = [
        report
        for report in reports
        if str(getattr(report, "report_type", "") or "").strip().lower()
        in {"result", "done", "completed", "external_runtime_report", "external_runtime_repo_mutation"}
    ]
    if solution_reports:
        candidates.append(
            _candidate_from_ticket(
                candidate_id=f"asset-candidate-ticket-solution-{safe_ticket_id}",
                asset_id=f"ticket-solution-{safe_ticket_id}",
                asset_type="solution",
                title=f"Validated solution: {ticket_title}",
                content=_ticket_solution_content(ticket, solution_reports),
                content_ref=f"ticket://{ticket_id}#solution",
                ticket=ticket,
                owner=owner,
                provenance={
                    **base_provenance,
                    "asset_type": "solution",
                    "source_report_ids": [
                        str(getattr(report, "id", "") or "").strip()
                        for report in solution_reports
                        if str(getattr(report, "id", "") or "").strip()
                    ],
                },
                relationships=relationships,
                timestamp=timestamp,
                workspace_dir=workspace_dir,
            )
        )
    validation_reports = [
        report
        for report in reports
        if str(getattr(report, "report_type", "") or "").strip().lower()
        in {"validation", "validated", "validation_passed", "pv_validation"}
    ]
    if validation_reports:
        candidates.append(
            _candidate_from_ticket(
                candidate_id=f"asset-candidate-ticket-validation-{safe_ticket_id}",
                asset_id=f"ticket-validation-{safe_ticket_id}",
                asset_type="validation_result",
                title=f"Validation result: {ticket_title}",
                content=_ticket_solution_content(ticket, validation_reports),
                content_ref=f"ticket://{ticket_id}#validation",
                ticket=ticket,
                owner=_first_string(getattr(ticket, "validation_employee_id", ""), owner),
                provenance={
                    **base_provenance,
                    "asset_type": "validation_result",
                    "source_report_ids": [
                        str(getattr(report, "id", "") or "").strip()
                        for report in validation_reports
                        if str(getattr(report, "id", "") or "").strip()
                    ],
                },
                relationships=relationships,
                timestamp=timestamp,
                workspace_dir=workspace_dir,
            )
        )
    return candidates


def _candidate_from_ticket(
    *,
    candidate_id: str,
    asset_id: str,
    asset_type: str,
    title: str,
    content: str,
    content_ref: str,
    ticket: Any,
    owner: str,
    provenance: dict[str, Any],
    relationships: list[dict[str, Any]],
    timestamp: str,
    workspace_dir: Path | None = None,
) -> AssetCandidateRecord:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    return AssetCandidateRecord(
        id=candidate_id,
        source_candidate_id="",
        asset_id=asset_id,
        asset_type=asset_type,
        title=title[:160],
        content=content,
        content_ref=content_ref,
        status="proposed",
        scope_kind="ticket",
        scope_ref=ticket_id,
        owner_employee_id=owner,
        source_kind="ticket_closeout",
        source_ref=f"tickets/{ticket_id}",
        provenance=provenance,
        provider="local_file",
        provider_ref=f"{_relative(asset_candidates_path(workspace_dir))}#{candidate_id}",
        relationships=relationships,
        review_state="proposed",
        usefulness_stats={},
        created_at=timestamp,
        updated_at=timestamp,
    )


def _ticket_is_closeout_ready(ticket: Any) -> bool:
    status = str(getattr(ticket, "status", "") or "").strip().lower()
    if status in {"validated", "completed", "done", "closed"}:
        return True
    return any(
        str(getattr(report, "report_type", "") or "").strip().lower()
        in {"validation", "validated", "validation_passed", "pv_validation"}
        for report in getattr(ticket, "reports", []) or []
    )


def _ticket_provider_refs(ticket: Any) -> list[dict[str, Any]]:
    provider_ref = getattr(ticket, "provider_ref", None)
    if provider_ref is None:
        return []
    if hasattr(provider_ref, "model_dump"):
        return [provider_ref.model_dump(mode="json")]
    if isinstance(provider_ref, dict):
        return [dict(provider_ref)]
    return []


def _ticket_closeout_content(ticket: Any, reports: list[Any], evidence_refs: list[str]) -> str:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    title = str(getattr(ticket, "title", "") or ticket_id).strip()
    description = str(getattr(ticket, "description", "") or "").strip()
    status = str(getattr(ticket, "status", "") or "").strip()
    assignee = _first_string(getattr(ticket, "assigned_employee_id", ""), getattr(ticket, "assigned_role", ""))
    validator = _first_string(getattr(ticket, "validation_employee_id", ""), getattr(ticket, "validation_role", ""))
    report_summary = "; ".join(
        _compact_text(
            f"{str(getattr(report, 'report_type', '') or 'report')} {str(getattr(report, 'id', '') or '').strip()}: "
            f"{str(getattr(report, 'content', '') or '').strip()}",
            260,
        )
        for report in reports[-6:]
    )
    return _compact_text(
        f"Ticket {ticket_id} closeout for {title}. Status: {status or '-'}. "
        f"Assignee: {assignee or '-'}. Validator: {validator or '-'}. "
        f"Evidence refs: {', '.join(evidence_refs[:8]) or '-'}. "
        f"Description: {description or '-'}. Reports: {report_summary or '-'}.",
        1800,
    )


def _ticket_solution_content(ticket: Any, reports: list[Any]) -> str:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    title = str(getattr(ticket, "title", "") or ticket_id).strip()
    report_summary = " ".join(
        _compact_text(
            f"{str(getattr(report, 'report_type', '') or 'report')} by "
            f"{str(getattr(report, 'reporter_employee_id', '') or 'unknown')}: "
            f"{str(getattr(report, 'content', '') or '').strip()} "
            f"Evidence: {', '.join(str(item).strip() for item in (getattr(report, 'evidence', []) or []) if str(item).strip()) or '-'}.",
            420,
        )
        for report in reports[-6:]
    )
    return _compact_text(f"Ticket {ticket_id} ({title}) validated learning: {report_summary}", 1800)


def _closeout_report_content(
    ticket: Any,
    candidates: list[AssetCandidateRecord],
    request: TicketCloseoutAssetCandidateRequest,
) -> str:
    reason = request.reason.strip()
    reason_text = f" Reason: {reason}" if reason else ""
    candidate_list = ", ".join(f"{candidate.asset_type}:{candidate.id}" for candidate in candidates)
    return _compact_text(f"Proposed Ticket closeout Asset candidates for review: {candidate_list}.{reason_text}", 1200)


def _existing_closeout_report_id(ticket: Any, evidence_refs: list[str]) -> str:
    expected = set(evidence_refs)
    for report in reversed(getattr(ticket, "reports", []) or []):
        if str(getattr(report, "report_type", "") or "").strip().lower() != "ticket_closeout_candidates":
            continue
        evidence = {str(item).strip() for item in (getattr(report, "evidence", []) or []) if str(item).strip()}
        if expected.issubset(evidence):
            return str(getattr(report, "id", "") or "").strip()
    return ""


def _safe_ref(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
    return safe.strip("-") or "ticket"


def _first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _compact_text(value: str, limit: int = 900) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}..."
