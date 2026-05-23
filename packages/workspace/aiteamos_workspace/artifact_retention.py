from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import re

from aiteamos_schema import Artifact

from .audit import decision_audit_record
from .io import write_yaml
from .loader import WorkspaceIndex, load_workspace, manifest_to_record
from .permissions import explain_effective_permissions


DEFAULT_ARTIFACT_RETENTION_DAYS = 7
ARTIFACT_LIFECYCLES = {"active", "archived", "redacted"}
ARTIFACT_RETENTION_TARGETS = {"archived", "redacted"}
ARTIFACT_EXPORT_POLICIES = {"include", "sanitize", "manifest_only", "manifest-only", "exclude"}


def artifact_retention_candidates(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    project: str | None = None,
    run: str | None = None,
    kind: str | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Return expired Artifact retention candidates without mutating workspace state."""

    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    observed_now = _normalize_retention_now(now)
    scoped_artifacts = []
    candidates: list[dict[str, Any]] = []
    for artifact in sorted(index.artifacts.values(), key=lambda item: item.object_id):
        artifact_project = _artifact_project(index, artifact)
        artifact_run = artifact.spec.run or artifact.spec.sourceRun
        if project is not None and artifact_project != project:
            continue
        if run is not None and artifact_run != run:
            continue
        if kind is not None and artifact.spec.kind != kind:
            continue
        scoped_artifacts.append(artifact)
        lifecycle = str(getattr(artifact.spec, "lifecycle", None) or "active")
        retained_until = _artifact_retained_until(artifact)
        if lifecycle != "active" or retained_until is None or retained_until > observed_now:
            continue
        recommended_lifecycle = _recommended_retention_lifecycle(artifact)
        recommended_export_policy = "exclude" if recommended_lifecycle == "redacted" else "manifest_only"
        warnings: list[str] = []
        if artifact.spec.exportPolicy == "include":
            warnings.append("active include export policy should be reduced after artifact retention expiry")
        if not (artifact.spec.uri or artifact.spec.path or artifact.spec.url or artifact.spec.ref):
            warnings.append("artifact has no external pointer; manifest-only archive is expected")
        candidates.append(
            {
                "id": f"retention:{artifact.object_id}",
                "kind": "ArtifactRetentionCandidate",
                "spec": {
                    "artifact": artifact.object_id,
                    "project": artifact_project,
                    "run": artifact_run,
                    "kind": artifact.spec.kind,
                    "uri": artifact.spec.uri,
                    "path": artifact.spec.path,
                    "url": artifact.spec.url,
                    "ref": artifact.spec.ref,
                    "lifecycle": lifecycle,
                    "retention": artifact.spec.retention,
                    "retainedUntil": retained_until.isoformat(timespec="milliseconds"),
                    "retentionExpiredAt": observed_now.isoformat(timespec="milliseconds"),
                    "retentionAgeHours": round(max(0.0, (observed_now - retained_until).total_seconds() / 3600.0), 3),
                    "exportPolicy": artifact.spec.exportPolicy,
                    "sensitivity": artifact.spec.sensitivity,
                    "recommendedLifecycle": recommended_lifecycle,
                    "recommendedExportPolicy": recommended_export_policy,
                    "recommendedRedactionPolicy": "metadata-only" if recommended_lifecycle == "redacted" else None,
                    "eligible": True,
                    "blockers": [],
                    "warnings": warnings,
                },
            }
        )
    return {
        "kind": "ArtifactRetentionCandidates",
        "filters": {"project": project, "run": run, "kind": kind},
        "evaluatedAt": observed_now.isoformat(timespec="milliseconds"),
        "defaultRetentionDays": DEFAULT_ARTIFACT_RETENTION_DAYS,
        "summary": {
            "scannedArtifacts": len(scoped_artifacts),
            "expiredCandidates": len(candidates),
            "redactionPreferred": sum(1 for item in candidates if item["spec"]["recommendedLifecycle"] == "redacted"),
            "archivePreferred": sum(1 for item in candidates if item["spec"]["recommendedLifecycle"] == "archived"),
        },
        "candidates": candidates,
    }


def sweep_artifact_retention(
    workspace_path: str | Path,
    *,
    actor_member: str,
    target_lifecycle: str | None = None,
    project: str | None = None,
    run: str | None = None,
    kind: str | None = None,
    now: str | datetime | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Archive or redact expired Artifact manifests through the normal lifecycle gate."""

    index = load_workspace(workspace_path)
    actor = index.members.get(actor_member)
    if actor is None:
        raise KeyError(f"unknown actor member {actor_member}")
    if target_lifecycle is not None and target_lifecycle not in ARTIFACT_RETENTION_TARGETS:
        raise ValueError("targetLifecycle must be archived or redacted")
    candidate_set = artifact_retention_candidates(index, project=project, run=run, kind=kind, now=now)
    selected_candidates = list(candidate_set["candidates"])
    if limit is not None:
        selected_candidates = selected_candidates[: max(0, int(limit))]
    updated: list[str] = []
    updated_records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for candidate in selected_candidates:
        spec = candidate["spec"]
        artifact_id = str(spec["artifact"])
        lifecycle = target_lifecycle or str(spec["recommendedLifecycle"])
        export_policy = "exclude" if lifecycle == "redacted" else "manifest_only"
        redaction_policy = "metadata-only" if lifecycle == "redacted" else None
        if dry_run:
            continue
        try:
            result = update_artifact_lifecycle(
                workspace_path,
                artifact_id,
                actor_member=actor_member,
                lifecycle=lifecycle,
                reason=f"Artifact reached retainedUntil {spec.get('retainedUntil')}; retention sweep changed lifecycle to {lifecycle}.",
                redaction_policy=redaction_policy,
                export_policy=export_policy,
                retained_until=str(spec.get("retainedUntil") or ""),
            )
        except (KeyError, ValueError) as exc:
            errors.append({"artifact": artifact_id, "error": str(exc)})
            continue
        updated.append(artifact_id)
        updated_records.append(manifest_to_record(result["artifact"]))
    return {
        "dryRun": dry_run,
        "actorMember": actor_member,
        "targetLifecycle": target_lifecycle,
        "updated": updated,
        "updatedCount": len(updated),
        "errors": errors,
        "candidateSummary": candidate_set["summary"],
        "candidates": selected_candidates,
        "artifacts": updated_records,
    }


def update_artifact_lifecycle(
    workspace_path: str | Path,
    artifact_id: str,
    *,
    actor_member: str,
    lifecycle: str,
    reason: str | None = None,
    redaction_policy: str | None = None,
    export_policy: str | None = None,
    retained_until: str | None = None,
) -> dict[str, Any]:
    """Archive or redact durable Artifact manifests without deleting lineage."""

    index = load_workspace(workspace_path)
    artifact = index.artifacts.get(artifact_id)
    if artifact is None:
        raise KeyError(f"unknown Artifact {artifact_id}")
    actor = index.members.get(actor_member)
    if actor is None:
        raise KeyError(f"unknown actor member {actor_member}")
    if actor.spec.kind not in {"human", "hybrid", "service"}:
        raise ValueError("Artifact lifecycle changes require a human, hybrid, or governed service member")
    if lifecycle not in ARTIFACT_LIFECYCLES:
        raise ValueError(f"unsupported Artifact lifecycle {lifecycle}")
    if export_policy is not None and export_policy not in ARTIFACT_EXPORT_POLICIES:
        raise ValueError(f"unsupported Artifact export policy {export_policy}")
    previous_lifecycle = str(getattr(artifact.spec, "lifecycle", None) or "active")
    if previous_lifecycle == "redacted" and lifecycle != "redacted":
        raise ValueError("redacted Artifact manifests cannot be restored to active or archived")

    manifest_path = _artifact_manifest_path(index.workspace_root, artifact_id)
    project = _artifact_project(index, artifact)
    permission = explain_effective_permissions(
        index,
        member=actor_member,
        project=project,
        action={"tool": "Edit", "path": f"/.aiteamos/artifacts/manifests/{manifest_path.name}", "operation": "update"},
        non_interactive=actor.spec.kind == "service",
    )
    if permission["decision"] == "deny" or permission.get("blockers"):
        raise ValueError(f"Artifact lifecycle update is denied by effective permissions: {permission.get('reason')}; blockers={permission.get('blockers')}")

    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    payload = artifact.model_dump(mode="json", exclude_none=True)
    spec = payload.setdefault("spec", {})
    spec["lifecycle"] = lifecycle
    selected_export_policy = export_policy or artifact.spec.exportPolicy
    if retained_until:
        spec["retainedUntil"] = retained_until

    if lifecycle == "active":
        spec.pop("archivedAt", None)
    elif lifecycle == "archived":
        spec["archivedAt"] = spec.get("archivedAt") or now
        if selected_export_policy in {None, "include"}:
            selected_export_policy = "manifest_only"
    else:
        selected_export_policy = export_policy or "exclude"
        selected_redaction_policy = redaction_policy or artifact.spec.redactionPolicy or "metadata-only"
        spec["redactedAt"] = spec.get("redactedAt") or now
        spec["redactionPolicy"] = selected_redaction_policy
        spec["uri"] = None
        spec["path"] = None
        spec["url"] = None
        spec["ref"] = None
        spec["redaction"] = {
            **(artifact.spec.redaction or {}),
            "strategy": selected_redaction_policy,
            "reason": reason or f"Artifact {artifact_id} redacted by lifecycle policy.",
        }
    if selected_export_policy:
        spec["exportPolicy"] = selected_export_policy

    audit = decision_audit_record(
        index,
        decision_kind="service_policy_decision" if actor.spec.kind == "service" else "human_approval",
        decision=f"artifact-{lifecycle}",
        actor_member=actor_member,
        authority="enforce" if actor.spec.kind == "service" else "approve",
        reason=reason or f"Artifact lifecycle changed from {previous_lifecycle} to {lifecycle}.",
        source="artifact-lifecycle",
        decided_at=now,
        policy_refs=permission.get("selectedPolicyIds", []),
        evidence=[{"kind": "Artifact", "id": artifact_id}],
        requires_human_review=False,
        risk_assessment=permission.get("riskAssessment"),
        metadata={
            "previousLifecycle": previous_lifecycle,
            "lifecycle": lifecycle,
            "redactionPolicy": redaction_policy,
            "exportPolicy": selected_export_policy,
            "retainedUntil": retained_until,
        },
    )
    spec.setdefault("decisionAudit", [])
    spec["decisionAudit"].append(audit)

    updated = Artifact.model_validate(payload)
    write_yaml(manifest_path, updated.model_dump(mode="json", exclude_none=True))
    return {"artifact": updated, "updated": True}


def _artifact_project(index: WorkspaceIndex, artifact: Artifact) -> str:
    run_id = artifact.spec.run or artifact.spec.sourceRun
    if run_id and run_id in index.runs:
        return index.runs[run_id].spec.project or index.project.object_id
    return index.project.object_id


def _artifact_retained_until(artifact: Artifact) -> datetime | None:
    explicit = _parse_artifact_timestamp(getattr(artifact.spec, "retainedUntil", None))
    if explicit is not None:
        return explicit
    created_at = _parse_artifact_timestamp(artifact.metadata.createdAt)
    if created_at is None:
        return None
    days = _retention_days(artifact.spec.retention)
    if days is None:
        return None
    return created_at + timedelta(days=days)


def _retention_days(retention: str | None) -> int | None:
    if not retention:
        return DEFAULT_ARTIFACT_RETENTION_DAYS
    normalized = retention.strip().lower()
    if normalized in {"workspace", "default", "artifact", "temporary"}:
        return DEFAULT_ARTIFACT_RETENTION_DAYS
    if normalized in {"forever", "permanent", "keep"}:
        return None
    match = re.fullmatch(r"(\d+)\s*(d|day|days)", normalized)
    if match:
        return int(match.group(1))
    return DEFAULT_ARTIFACT_RETENTION_DAYS


def _recommended_retention_lifecycle(artifact: Artifact) -> str:
    sensitivity = (artifact.spec.sensitivity or "").lower()
    export_policy = artifact.spec.exportPolicy or ""
    if export_policy == "exclude" or any(marker in sensitivity for marker in ("secret", "credential", "private", "provider")):
        return "redacted"
    return "archived"


def _normalize_retention_now(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now().astimezone()
    if isinstance(value, datetime):
        return value.astimezone() if value.tzinfo else value.astimezone()
    parsed = _parse_artifact_timestamp(value)
    if parsed is None:
        raise ValueError(f"invalid retention timestamp {value!r}")
    return parsed


def _parse_artifact_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()


def _artifact_manifest_path(workspace_root: Path, artifact_id: str) -> Path:
    expected = workspace_root / "artifacts" / "manifests" / f"{artifact_id}.yaml"
    if expected.exists():
        return expected
    raise KeyError(f"missing Artifact manifest file for {artifact_id}")
