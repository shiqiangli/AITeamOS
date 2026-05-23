from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import zipfile

import yaml

from .io import read_yaml
from .loader import load_workspace


DEFAULT_MAX_LOG_BYTES = 64 * 1024
TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
MANIFEST_SUFFIXES = {".yaml", ".yml"}
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".vite",
    "blob",
    "build",
    "cache",
    "caches",
    "coverage",
    "dist",
    "htmlcov",
    "indexes",
    "node_modules",
    "target",
    "tmp",
    "worktrees",
}
SCREENSHOT_SUFFIXES = {".avif", ".gif", ".jpeg", ".jpg", ".mov", ".mp4", ".png", ".webm"}
EMBEDDING_SUFFIXES = {".faiss", ".npy", ".npz", ".parquet"}
RAW_PROVIDER_MARKERS = (
    "openai_response",
    "provider_response",
    "raw_provider",
    "raw_response",
    "response_body",
)
GENERIC_MANIFEST_EXCLUDE_REASON = "manifest-export-exclude"
EXPORT_POLICIES = {"include", "sanitize", "manifest-only", "exclude"}
MANIFEST_ONLY_SPEC_KEYS = {
    "archivedAt",
    "createdAt",
    "decisionAudit",
    "evidence",
    "exportPolicy",
    "lifecycle",
    "redactedAt",
    "redactionPolicy",
    "retainedUntil",
    "status",
    "updatedAt",
}
MANIFEST_ONLY_REFERENCE_KEYS = {
    "actorMember",
    "assignment",
    "assignments",
    "automation",
    "automationRun",
    "entry",
    "evalSuite",
    "facilitatorMember",
    "fromMember",
    "grantorMember",
    "granteeMember",
    "importedActivities",
    "member",
    "members",
    "ownerMember",
    "ownerProject",
    "participants",
    "project",
    "repository",
    "reviewerMember",
    "roleTemplate",
    "run",
    "sourceMessages",
    "sourceRun",
    "sourceRuns",
    "sourceTask",
    "sourceTasks",
    "store",
    "task",
    "targetId",
    "targetType",
    "toMember",
    "toMembers",
}
SENSITIVE_MANIFEST_KEY_FRAGMENTS = (
    "apikey",
    "api_key",
    "body",
    "bucket",
    "case",
    "comment",
    "contact",
    "content",
    "credential",
    "diagnostic",
    "endpoint",
    "externalid",
    "golden",
    "header",
    "journal",
    "message",
    "note",
    "output",
    "payload",
    "password",
    "private",
    "problem",
    "prompt",
    "raw",
    "ref",
    "routing",
    "secret",
    "snippet",
    "summary",
    "token",
    "url",
)
MANIFEST_ONLY_ARTIFACT_NAMES = {"model_output.md", "worker_output.md"}
SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[A-Z0-9_]*=)([^\s]+)"
)
SECRET_FIELD_RE = re.compile(
    r'(?i)(["\']?(?:api[_-]?key|token|secret|password|credential)["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)'
)
SECRET_TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b")


def default_export_path(workspace: str | Path = ".aiteamos") -> Path:
    index = load_workspace(workspace)
    name = index.workspace_root.name.strip(".") or "aiteamos"
    return index.workspace_root.parent / f"{name}-workspace-sanitized.zip"


def export_workspace_bundle(
    workspace: str | Path = ".aiteamos",
    output: str | Path | None = None,
    *,
    overwrite: bool = False,
    max_log_bytes: int = DEFAULT_MAX_LOG_BYTES,
) -> dict[str, Any]:
    index = load_workspace(workspace)
    root = index.workspace_root
    target = Path(output).expanduser().resolve() if output is not None else default_export_path(root)
    if target.exists() and not overwrite:
        raise FileExistsError(f"export bundle already exists: {target}")
    if target.is_dir():
        raise IsADirectoryError(f"export target is a directory: {target}")

    included: list[str] = []
    excluded: list[dict[str, str]] = []
    archive_root = root.name
    artifact_policies = _artifact_export_policies(index)
    git_activity_policies = _git_activity_export_policies(index)
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            reason = _exclusion_reason(
                root,
                path,
                target,
                max_log_bytes=max_log_bytes,
                artifact_policies=artifact_policies,
                git_activity_policies=git_activity_policies,
            )
            if reason:
                excluded.append({"path": f"{archive_root}/{relative}", "reason": reason})
                continue
            archive_name = f"{archive_root}/{relative}"
            payload = _read_sanitized(path, git_activity_policy=git_activity_policies.get(relative))
            if isinstance(payload, str):
                bundle.writestr(archive_name, payload.encode("utf-8"))
            else:
                bundle.writestr(archive_name, payload)
            included.append(archive_name)

        manifest = {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "WorkspaceExport",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "workspace": index.workspace.object_id,
            "project": index.project.object_id,
            "protocolVersion": index.workspace.spec.protocolVersion,
            "sanitized": True,
            "includedFiles": len(included),
            "excludedFiles": excluded,
            "rules": [
                "Derived indexes, caches, build trees, artifact blobs, and worktrees are excluded.",
                "Screenshots, videos, embeddings, raw provider responses, and long logs are excluded.",
                "Text files are copied with conservative secret-value redaction.",
                "Manifest exportPolicy controls include, sanitize, manifest-only, and exclude behavior for source manifest YAML.",
                "GitActivity exportPolicy controls include, sanitize, manifest-only, and exclude behavior; archived or redacted activity evidence is never exported with provider-facing details.",
            ],
        }
        bundle.writestr("AITEAMOS_EXPORT_MANIFEST.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")

    return {
        "path": target,
        "workspace": root,
        "included": included,
        "excluded": excluded,
        "sanitized": True,
    }


def _exclusion_reason(
    root: Path,
    path: Path,
    target: Path,
    *,
    max_log_bytes: int,
    artifact_policies: dict[str, dict[str, str]],
    git_activity_policies: dict[str, dict[str, str]],
) -> str | None:
    if path.resolve() == target:
        return "export-target"
    relative = path.relative_to(root).as_posix()
    policy = artifact_policies.get(relative, {})
    export_policy = policy.get("exportPolicy")
    if export_policy in {"manifest_only", "manifest-only", "exclude"}:
        return f"artifact-{export_policy.replace('_', '-')}"
    git_activity_policy = git_activity_policies.get(relative, {})
    if git_activity_policy.get("exportPolicy") == "exclude":
        return "git-activity-export-exclude"
    manifest_policy = _manifest_export_policy(path)
    if manifest_policy == "exclude":
        return GENERIC_MANIFEST_EXCLUDE_REASON
    relative_parts = path.relative_to(root).parts
    lowered_parts = [part.lower() for part in relative_parts]
    suffix = path.suffix.lower()
    if suffix == ".sqlite" or suffix in {".db", ".sqlite3"}:
        return "derived-database"
    if "artifacts" in lowered_parts and any(part in {"blob", "cache", "worktrees"} for part in lowered_parts):
        return "artifact-blob-or-worktree"
    if any(part in EXCLUDED_DIR_NAMES for part in lowered_parts[:-1]):
        return "derived-or-large-directory"
    name = path.name.lower()
    if name in MANIFEST_ONLY_ARTIFACT_NAMES:
        return "artifact-manifest-only"
    if suffix in SCREENSHOT_SUFFIXES:
        return "screenshot-or-video"
    if suffix in EMBEDDING_SUFFIXES or "embedding" in name or "vector" in name:
        return "embedding-or-vector-state"
    if any(marker in name for marker in RAW_PROVIDER_MARKERS):
        return "raw-provider-response"
    if suffix == ".log" and path.stat().st_size > max(0, max_log_bytes):
        return "long-log"
    return None


def _artifact_export_policies(index: Any) -> dict[str, dict[str, str]]:
    policies: dict[str, dict[str, str]] = {}
    for artifact in index.artifacts.values():
        uri = artifact.spec.uri or artifact.spec.path
        if not uri:
            continue
        policies[str(uri)] = {
            "kind": str(artifact.spec.kind),
            "sensitivity": str(getattr(artifact.spec, "sensitivity", "") or ""),
            "exportPolicy": str(getattr(artifact.spec, "exportPolicy", "") or ""),
        }
    return policies


def _git_activity_export_policies(index: Any) -> dict[str, dict[str, str]]:
    policies: dict[str, dict[str, str]] = {}
    for activity_id, activity in index.git_activities.items():
        policies[f"git_activity/{activity_id}.yaml"] = {
            "lifecycle": str(getattr(activity.spec, "lifecycle", "") or "active"),
            "exportPolicy": str(getattr(activity.spec, "exportPolicy", "") or "sanitize"),
        }
    return policies


def _read_sanitized(path: Path, *, git_activity_policy: dict[str, str] | None = None) -> bytes | str:
    if git_activity_policy is not None:
        return _read_git_activity_sanitized(path, git_activity_policy)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return path.read_bytes()
    manifest = _read_manifest(path)
    if manifest is not None:
        return _read_manifest_sanitized(manifest)
    text = path.read_text(encoding="utf-8", errors="replace")
    return _sanitize_text(text)


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() not in MANIFEST_SUFFIXES:
        return None
    try:
        data = read_yaml(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("kind"), str):
        return None
    spec = data.get("spec")
    if not isinstance(spec, dict):
        return None
    return data


def _manifest_export_policy(path: Path) -> str | None:
    manifest = _read_manifest(path)
    if manifest is None:
        return None
    spec = manifest.get("spec", {})
    if not isinstance(spec, dict):
        return None
    return _normalize_export_policy(spec.get("exportPolicy"))


def _normalize_export_policy(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    policy = value.replace("_", "-").strip()
    if policy in EXPORT_POLICIES:
        return policy
    return None


def _read_manifest_sanitized(data: dict[str, Any]) -> str:
    spec = data.get("spec", {})
    if not isinstance(spec, dict):
        spec = {}
    export_policy = _normalize_export_policy(spec.get("exportPolicy")) or "sanitize"
    lifecycle = str(spec.get("lifecycle") or "active")

    payload = data
    if export_policy == "manifest-only":
        payload = _manifest_only(data)
    elif export_policy == "sanitize" or lifecycle in {"archived", "redacted"}:
        payload = _manifest_redacted(data, reason=f"export-policy:{export_policy};lifecycle:{lifecycle}")

    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    return _sanitize_text(text)


def _manifest_only(data: dict[str, Any]) -> dict[str, Any]:
    spec = data.get("spec", {})
    if not isinstance(spec, dict):
        spec = {}
    kept = {
        key: value
        for key, value in spec.items()
        if key in MANIFEST_ONLY_SPEC_KEYS or key in MANIFEST_ONLY_REFERENCE_KEYS
    }
    if kept:
        kept["manifestOnlyReason"] = "Provider-facing, large, and free-text payload fields were omitted by exportPolicy."
    return {
        "apiVersion": data.get("apiVersion", "aiteamos.dev/v1alpha1"),
        "kind": data.get("kind", "Manifest"),
        "metadata": data.get("metadata", {}),
        "spec": kept,
    }


def _manifest_redacted(data: dict[str, Any], *, reason: str) -> dict[str, Any]:
    payload = dict(data)
    spec = payload.get("spec", {})
    if not isinstance(spec, dict):
        spec = {}
    payload["spec"] = _redact_manifest_value(spec, parent_key=None)
    payload["spec"]["exportRedactionReason"] = reason
    return payload


def _redact_manifest_value(value: Any, *, parent_key: str | None) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if key == "decisionAudit":
                result[key] = child
            elif _is_sensitive_manifest_key(key):
                result[key] = _redacted_manifest_marker(key, child)
            else:
                result[key] = _redact_manifest_value(child, parent_key=key)
        return result
    if isinstance(value, list):
        if parent_key and _is_sensitive_manifest_key(parent_key):
            return _redacted_manifest_marker(parent_key, value)
        return [_redact_manifest_value(item, parent_key=parent_key) for item in value]
    return value


def _is_sensitive_manifest_key(key: str) -> bool:
    lowered = key.replace("-", "").replace("_", "").lower()
    return any(fragment.replace("_", "") in lowered for fragment in SENSITIVE_MANIFEST_KEY_FRAGMENTS)


def _redacted_manifest_marker(key: str, value: Any) -> Any:
    if value in (None, "", [], {}):
        return value
    encoded = json.dumps(value, sort_keys=True, default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
    if isinstance(value, list):
        return [f"redacted:{key}:{digest}"]
    if isinstance(value, dict):
        return {"redacted": True, "field": key, "digest": digest}
    return f"redacted:{key}:{digest}"


def _read_git_activity_sanitized(path: Path, policy: dict[str, str]) -> str:
    data = read_yaml(path)
    export_policy = policy.get("exportPolicy") or "sanitize"
    lifecycle = policy.get("lifecycle") or "active"

    if export_policy == "manifest-only":
        data = _git_activity_manifest_only(data)
    elif export_policy == "sanitize" or lifecycle in {"archived", "redacted"}:
        data = _git_activity_redacted(data, reason=f"export-policy:{export_policy};lifecycle:{lifecycle}")

    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=False)
    return _sanitize_text(text)


def _git_activity_manifest_only(data: dict[str, Any]) -> dict[str, Any]:
    spec = data.get("spec", {})
    if not isinstance(spec, dict):
        spec = {}
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    activity_id = metadata.get("id") or metadata.get("name") or "unknown"
    kept = {
        key: spec[key]
        for key in [
            "member",
            "project",
            "repository",
            "assignment",
            "activityType",
            "provider",
            "occurredAt",
            "visibility",
            "lifecycle",
            "retainedUntil",
            "archivedAt",
            "redactedAt",
            "redactionPolicy",
            "exportPolicy",
            "evidence",
            "decisionAudit",
        ]
        if key in spec
    }
    kept["summary"] = f"Manifest-only GitActivity export for {activity_id}; provider-facing details were omitted."
    return {
        "apiVersion": data.get("apiVersion", "aiteamos.dev/v1alpha1"),
        "kind": data.get("kind", "GitActivity"),
        "metadata": metadata,
        "spec": kept,
    }


def _git_activity_redacted(data: dict[str, Any], *, reason: str) -> dict[str, Any]:
    payload = dict(data)
    spec = payload.get("spec", {})
    if not isinstance(spec, dict):
        spec = {}
    else:
        spec = dict(spec)
    metadata = payload.get("metadata", {})
    activity_id = "unknown"
    if isinstance(metadata, dict):
        activity_id = str(metadata.get("id") or metadata.get("name") or activity_id)

    if spec.get("summary"):
        spec["summary"] = f"Sanitized GitActivity evidence {activity_id}; lineage is preserved while provider-facing details are redacted."
    if spec.get("externalId"):
        spec["externalId"] = _redacted_value(str(spec["externalId"]), prefix="redacted:external")
    if spec.get("url"):
        spec["url"] = _redacted_value(str(spec["url"]), prefix="redacted:url")
    refs = spec.get("refs")
    if isinstance(refs, list):
        spec["refs"] = [_redacted_value(str(ref), prefix="redacted-ref") for ref in refs]
    spec["exportRedactionReason"] = reason
    payload["spec"] = spec
    return payload


def _redacted_value(value: str, *, prefix: str) -> str:
    if value.startswith(f"{prefix}:"):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _sanitize_text(text: str) -> str:
    text = SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", text)
    text = SECRET_FIELD_RE.sub(r"\1[REDACTED]", text)
    text = SECRET_TOKEN_RE.sub("sk-[REDACTED]", text)
    return text
