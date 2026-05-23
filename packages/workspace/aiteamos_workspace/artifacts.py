from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import hashlib
import re

from aiteamos_schema import Artifact

from .io import write_yaml


MANIFEST_ONLY_KINDS = {
    "model_output",
    "worker_output",
    "raw_provider",
    "raw_provider_response",
    "provider_response",
    "openai_response",
}


def record_artifact_manifest(
    workspace_root: str | Path,
    run_id: str,
    kind: str,
    uri: str,
    *,
    source_id: str | None = None,
    retention: str = "workspace",
    redaction: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    root = Path(workspace_root)
    artifact_id = _artifact_id(run_id, kind, uri, source_id=source_id)
    manifest_ref = f"artifacts/manifests/{artifact_id}.yaml"
    artifact_path = root / uri
    sensitivity, export_policy = _default_artifact_policy(kind)
    created_at = datetime.now().astimezone()
    spec: dict[str, Any] = {
        "run": run_id,
        "kind": kind,
        "uri": uri,
        "sha256": _sha256(artifact_path),
        "sizeBytes": _size_bytes(artifact_path),
        "retention": retention,
        "lifecycle": "active",
        "retainedUntil": (created_at + timedelta(days=7)).isoformat(timespec="milliseconds"),
        "sensitivity": sensitivity,
        "exportPolicy": export_policy,
        "redaction": redaction or {},
    }
    if extra:
        spec.update(extra)
    artifact = Artifact.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Artifact",
            "metadata": {"id": artifact_id, "createdAt": created_at.isoformat(timespec="milliseconds")},
            "spec": spec,
        }
    )
    write_yaml(root / manifest_ref, artifact.model_dump(mode="json", exclude_none=True))
    return manifest_ref


def _default_artifact_policy(kind: str) -> tuple[str, str]:
    normalized = kind.strip().lower()
    if normalized in MANIFEST_ONLY_KINDS:
        return "provider-output", "manifest_only"
    if normalized in {"test_log", "command_log"}:
        return "execution-log", "sanitize"
    if normalized == "diff_patch":
        return "review-diff", "sanitize"
    return "workspace-artifact", "sanitize"


def _artifact_id(run_id: str, kind: str, uri: str, *, source_id: str | None) -> str:
    source = source_id or hashlib.sha256(uri.encode("utf-8")).hexdigest()[:12]
    return f"ART-{_slug(run_id)}-{_slug(source)}-{_slug(kind)}".upper()


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9-]+", "-", value).strip("-")
    return slug or "ARTIFACT"


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _size_bytes(path: Path) -> int | None:
    if not path.exists():
        return None
    return path.stat().st_size
