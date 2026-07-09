"""Schema and migration readiness registry for AITeamOS local ledgers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

SCHEMA_REGISTRY_CONTRACT_VERSION = "aiteamos_schema_registry.v1"


class SchemaStoreRecord(BaseModel):
    id: str
    domain: str
    display_name: str
    provider: str = "local_file"
    schema_version: str
    expected_shape: str
    actual_shape: str = ""
    path: str
    status: str
    migration_status: str
    migration_required: bool = False
    item_count: int = 0
    exists: bool = False
    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    provenance_boundary: str = ""
    migration_strategy: str = ""


class SchemaRegistrySummary(BaseModel):
    store_count: int
    current_count: int
    missing_count: int
    legacy_count: int
    invalid_count: int
    migration_required_count: int
    contract_version: str = SCHEMA_REGISTRY_CONTRACT_VERSION
    covered_domains: list[str] = Field(default_factory=list)


class SchemaRegistryResponse(BaseModel):
    contract_version: str = SCHEMA_REGISTRY_CONTRACT_VERSION
    status: str
    summary: SchemaRegistrySummary
    stores: list[SchemaStoreRecord] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class _StoreSpec:
    id: str
    domain: str
    display_name: str
    rel_path: str
    schema_version: str
    expected_shape: str
    current_shapes: tuple[str, ...]
    provider: str = "local_file"
    kind: Literal["json", "directory"] = "json"
    envelope_key: str = ""
    allow_missing: bool = True
    compatible_shapes: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    provenance_boundary: str = ""
    migration_strategy: str = "read-compatible; migrate by explicit future writer, not implicit status read"
    glob_pattern: str = "*.yaml"
    directory_required_fields: tuple[str, ...] = field(default_factory=tuple)


_STORE_SPECS: tuple[_StoreSpec, ...] = (
    _StoreSpec(
        id="execution.sessions",
        domain="runtime",
        display_name="Execution Sessions",
        rel_path="execution_sessions.json",
        schema_version="execution_sessions.v1",
        expected_shape="object map keyed by employee_id::thread_id::ticket_id",
        current_shapes=("object_map", "empty_object"),
        required_fields=("session_key", "employee_id", "thread_id", "ticket_id", "status"),
        provenance_boundary="Runtime sessions correlate Employee, Ticket, checkpoint, approval, tool events, and replay refs.",
    ),
    _StoreSpec(
        id="execution.approvals",
        domain="runtime",
        display_name="Execution Approvals",
        rel_path="execution_approvals.json",
        schema_version="execution_approvals.v1",
        expected_shape="list[ExecutionApprovalRecord]",
        current_shapes=("list",),
        compatible_shapes=("envelope",),
        envelope_key="approvals",
        required_fields=("id", "status", "ticket_id", "employee_id", "executor_id"),
        provenance_boundary="Approval records preserve high-risk action, checkpoint, review, and resume provenance.",
    ),
    _StoreSpec(
        id="assets.candidates",
        domain="assets",
        display_name="Asset Candidates",
        rel_path="assets/candidates.json",
        schema_version="asset_candidates.v1",
        expected_shape="list[AssetCandidateRecord]",
        current_shapes=("list",),
        compatible_shapes=("envelope",),
        envelope_key="candidates",
        required_fields=("id", "asset_type", "title", "status", "provenance"),
        provenance_boundary="Governed runtime artifacts enter long-term Assets through candidate review.",
    ),
    _StoreSpec(
        id="assets.records",
        domain="assets",
        display_name="Approved Assets",
        rel_path="assets/index.json",
        schema_version="asset_records.v1",
        expected_shape="list[AssetRecord]",
        current_shapes=("list",),
        compatible_shapes=("envelope",),
        envelope_key="assets",
        required_fields=("id", "asset_type", "title", "status", "provenance"),
        provenance_boundary="Approved Assets are AITeamOS-owned source-of-truth records before provider projection.",
    ),
    _StoreSpec(
        id="assets.reviews",
        domain="assets",
        display_name="Asset Reviews",
        rel_path="assets/reviews.json",
        schema_version="asset_reviews.v1",
        expected_shape="list[AssetReviewRecord]",
        current_shapes=("list",),
        compatible_shapes=("envelope",),
        envelope_key="reviews",
        required_fields=("id", "candidate_id", "status", "reviewer_employee_id"),
        provenance_boundary="Asset reviews capture human or Employee review decisions for candidate promotion.",
    ),
    _StoreSpec(
        id="assets.retrieval_evaluations",
        domain="assets",
        display_name="Retrieval Evaluations",
        rel_path="assets/retrieval_evaluations.json",
        schema_version="asset_retrieval_evaluations.v1",
        expected_shape="list[AssetRetrievalEvaluationRecord]",
        current_shapes=("list",),
        compatible_shapes=("envelope",),
        envelope_key="evaluations",
        required_fields=("id", "query", "expected_asset_ids", "retrieved_asset_ids", "precision", "recall"),
        provenance_boundary="Retrieval evaluations make Asset recall quality auditable over time.",
    ),
    _StoreSpec(
        id="employees.local_profiles",
        domain="employees",
        display_name="Local Employee Profiles",
        rel_path="employees",
        schema_version="employee_profiles.v1",
        expected_shape="directory of YAML Employee profiles",
        current_shapes=("directory",),
        kind="directory",
        directory_required_fields=("id", "display_name"),
        provenance_boundary="Employees remain fixed AITeamOS identities; providers may execute for them but cannot redefine them.",
        migration_strategy="file-backed YAML profiles; future provider adapters project from this source of truth",
    ),
    _StoreSpec(
        id="tickets.projection",
        domain="tickets",
        display_name="Ticket Projection Index",
        rel_path="tickets/index.json",
        schema_version="ticket_projection.v1",
        expected_shape="list[Ticket]",
        current_shapes=("list",),
        compatible_shapes=("envelope",),
        envelope_key="tickets",
        required_fields=("id", "title", "status", "events", "reports"),
        provenance_boundary="Tickets are the collaboration, handoff, report, validation, and closeout channel.",
    ),
)


def schema_registry_report(*, workspace_dir: Path | None = None) -> SchemaRegistryResponse:
    workspace = _workspace_dir(workspace_dir)
    stores = [_evaluate_store(spec, workspace) for spec in _STORE_SPECS]
    invalid_count = sum(1 for item in stores if item.status == "invalid")
    migration_required_count = sum(1 for item in stores if item.migration_required)
    summary = SchemaRegistrySummary(
        store_count=len(stores),
        current_count=sum(1 for item in stores if item.status == "current"),
        missing_count=sum(1 for item in stores if item.status == "missing"),
        legacy_count=sum(1 for item in stores if item.status == "legacy"),
        invalid_count=invalid_count,
        migration_required_count=migration_required_count,
        covered_domains=sorted({item.domain for item in stores}),
    )
    status = "failed" if invalid_count else "warning" if migration_required_count else "passed"
    return SchemaRegistryResponse(
        status=status,
        summary=summary,
        stores=stores,
        saved_paths={"workspace": _relative(workspace, workspace)},
    )


def _evaluate_store(spec: _StoreSpec, workspace_dir: Path) -> SchemaStoreRecord:
    path = workspace_dir / spec.rel_path
    base = {
        "id": spec.id,
        "domain": spec.domain,
        "display_name": spec.display_name,
        "provider": spec.provider,
        "schema_version": spec.schema_version,
        "expected_shape": spec.expected_shape,
        "path": _relative(path, workspace_dir),
        "provenance_boundary": spec.provenance_boundary,
        "migration_strategy": spec.migration_strategy,
    }
    if not path.exists():
        return SchemaStoreRecord(
            **base,
            actual_shape="missing",
            status="missing",
            migration_status="not_created_yet" if spec.allow_missing else "migration_required",
            migration_required=not spec.allow_missing,
            exists=False,
            checks=[f"schema:{spec.schema_version}", "path_missing_allowed" if spec.allow_missing else "path_missing"],
            warnings=[] if spec.allow_missing else ["required_store_missing"],
            blockers=[] if spec.allow_missing else ["required_store_missing"],
        )
    if spec.kind == "directory":
        return _evaluate_directory_store(spec, path, base)
    return _evaluate_json_store(spec, path, base)


def _evaluate_directory_store(spec: _StoreSpec, path: Path, base: dict[str, Any]) -> SchemaStoreRecord:
    if not path.is_dir():
        return SchemaStoreRecord(
            **base,
            actual_shape="not_directory",
            status="invalid",
            migration_status="migration_blocked",
            migration_required=True,
            exists=True,
            checks=[f"schema:{spec.schema_version}", "path_exists"],
            blockers=["expected_directory"],
        )
    files = sorted(path.glob(spec.glob_pattern))
    warnings: list[str] = []
    checks = [f"schema:{spec.schema_version}", "path_exists", "shape:directory"]
    for profile_path in files[:12]:
        missing = _missing_yaml_fields(profile_path, spec.directory_required_fields)
        if missing:
            warnings.append(f"{profile_path.name}:missing_fields:{','.join(missing)}")
    return SchemaStoreRecord(
        **base,
        actual_shape="directory",
        status="current",
        migration_status="schema_current",
        exists=True,
        item_count=len(files),
        checks=checks,
        warnings=warnings,
    )


def _evaluate_json_store(spec: _StoreSpec, path: Path, base: dict[str, Any]) -> SchemaStoreRecord:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return SchemaStoreRecord(
            **base,
            actual_shape="invalid_json",
            status="invalid",
            migration_status="migration_blocked",
            migration_required=True,
            exists=True,
            checks=[f"schema:{spec.schema_version}", "path_exists"],
            blockers=[f"invalid_json:{exc.__class__.__name__}"],
        )

    actual_shape, items = _json_items(payload, spec)
    warnings = _field_warnings(items, spec.required_fields)
    checks = [f"schema:{spec.schema_version}", "path_exists", "json_loaded", f"shape:{actual_shape}"]
    if actual_shape in spec.current_shapes:
        return SchemaStoreRecord(
            **base,
            actual_shape=actual_shape,
            status="current",
            migration_status="schema_current",
            exists=True,
            item_count=len(items),
            checks=checks,
            warnings=warnings,
        )
    if actual_shape in spec.compatible_shapes:
        return SchemaStoreRecord(
            **base,
            actual_shape=actual_shape,
            status="legacy",
            migration_status="legacy_shape_supported",
            exists=True,
            item_count=len(items),
            checks=[*checks, "legacy_loader_supported"],
            warnings=[*warnings, "legacy_shape_supported_by_loader"],
        )
    return SchemaStoreRecord(
        **base,
        actual_shape=actual_shape,
        status="invalid",
        migration_status="migration_required",
        migration_required=True,
        exists=True,
        item_count=len(items),
        checks=checks,
        warnings=warnings,
        blockers=[f"expected:{'|'.join(spec.current_shapes)}", f"actual:{actual_shape}"],
    )


def _json_items(payload: Any, spec: _StoreSpec) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(payload, list):
        return "list", [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if spec.envelope_key and isinstance(payload.get(spec.envelope_key), list):
            return "envelope", [item for item in payload[spec.envelope_key] if isinstance(item, dict)]
        if not payload:
            return "empty_object", []
        if all(isinstance(value, dict) for value in payload.values()):
            return "object_map", [value for value in payload.values() if isinstance(value, dict)]
        return "object"
    return type(payload).__name__


def _field_warnings(items: list[dict[str, Any]], required_fields: tuple[str, ...]) -> list[str]:
    if not items or not required_fields:
        return []
    warnings: list[str] = []
    for index, item in enumerate(items[:12]):
        missing = [field for field in required_fields if field not in item]
        if missing:
            warnings.append(f"item:{index}:missing_fields:{','.join(missing)}")
    return warnings


def _missing_yaml_fields(path: Path, required_fields: tuple[str, ...]) -> list[str]:
    if not required_fields:
        return []
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return list(required_fields)
    if not isinstance(payload, dict):
        return list(required_fields)
    return [field for field in required_fields if field not in payload]


def _workspace_root(workspace_dir: Path | None = None) -> Path:
    if workspace_dir is not None:
        candidate = workspace_dir.expanduser().resolve()
        return candidate.parent if candidate.name == ".aiteamos" else candidate
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).expanduser().resolve() if configured else Path.cwd().resolve()


def _workspace_dir(workspace_dir: Path | None = None) -> Path:
    candidate = workspace_dir.expanduser().resolve() if workspace_dir is not None else _workspace_root() / ".aiteamos"
    return candidate if candidate.name == ".aiteamos" else candidate / ".aiteamos"


def _relative(path: Path, workspace_dir: Path | None = None) -> str:
    try:
        return str(path.relative_to(_workspace_root(workspace_dir)))
    except ValueError:
        return str(path)
