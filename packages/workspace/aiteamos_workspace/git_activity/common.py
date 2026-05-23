from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import fnmatch
import hashlib
import json
import re
import subprocess

from aiteamos_schema import (
    GitActivity,
    GitActivityCorrelationReview,
    GitActivityImportReceipt,
    timestamp_git_activity_correlation_review_id,
    timestamp_git_activity_id,
    timestamp_git_activity_import_receipt_id,
)

from ..audit import decision_audit_record
from ..io import write_yaml
from ..loader import WorkspaceIndex
from ..permissions import explain_effective_permissions


SENSITIVE_REF_RE = re.compile(r"(^|[/_-])(private|secret|token|credential|customer|internal)([/_-]|$)", re.IGNORECASE)
PROVIDER_EVENT_SOURCES = {"provider-sync", "webhook"}
GIT_ACTIVITY_PROVIDERS = {"github", "gitlab"}
GIT_ACTIVITY_TYPES = {"commit", "branch", "pull-request", "review-comment", "merge", "tag", "other"}
GIT_ACTIVITY_LIFECYCLES = {"active", "archived", "redacted"}
GIT_ACTIVITY_REDACTION_POLICIES = {"metadata-only", "redacted-summary", "artifact-reference"}
GIT_ACTIVITY_EXPORT_POLICIES = {"include", "sanitize", "manifest-only", "exclude"}
GIT_ACTIVITY_RETENTION_TARGETS = {"archived", "redacted"}


def _parse_git_activity_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed

def _normalize_retention_now(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone() if value.tzinfo is not None else value.astimezone()
    parsed = _parse_git_activity_timestamp(value) if value is not None else None
    return parsed or datetime.now().astimezone()

def _recommended_retention_lifecycle(activity: GitActivity) -> str:
    if activity.spec.exportPolicy == "exclude" or activity.spec.redactionPolicy == "redacted-summary":
        return "redacted"
    if any(_is_sensitive_ref(ref) for ref in activity.spec.refs):
        return "redacted"
    return "archived"

def _is_sensitive_ref(ref: str) -> bool:
    return ref.startswith("redacted-ref:") or ref.startswith("redacted-commit:") or bool(SENSITIVE_REF_RE.search(ref))

def _receipt_matches_member_assignment(
    index: WorkspaceIndex,
    receipt: GitActivityImportReceipt,
    *,
    member: str | None,
    assignment: str | None,
) -> bool:
    normalized = receipt.spec.normalized
    member_refs = {
        _string_value(normalized.get("member")),
        receipt.spec.importerMember,
        receipt.spec.reviewedByMember,
        receipt.spec.serviceMember,
    }
    assignment_refs = {_string_value(normalized.get("assignment"))}
    for activity_id in receipt.spec.importedActivities:
        activity = index.git_activities.get(activity_id)
        if not activity:
            continue
        member_refs.add(activity.spec.member)
        assignment_refs.add(activity.spec.assignment)
    if member and member not in member_refs:
        return False
    if assignment and assignment not in assignment_refs:
        return False
    return True

def _find_correlation_preview_group(preview: dict[str, Any], correlation_key: str) -> dict[str, Any] | None:
    for group in preview.get("groups", []):
        if isinstance(group, dict) and group.get("correlationKey") == correlation_key:
            return group
    return None

def _correlation_risk_flags(group: dict[str, Any], receipts: list[GitActivityImportReceipt]) -> list[str]:
    flags = []
    if group.get("forcePushRisk"):
        flags.append("force-push")
    if group.get("squashMergeRisk"):
        flags.append("squash-merge")
    if group.get("multiEventRisk"):
        flags.append("multi-event")
    if any(receipt.spec.status == "blocked" for receipt in receipts):
        flags.append("blocked-receipt")
    if group.get("importedActivities"):
        flags.append("imported-activity")
    if flags or len(receipts) > 1:
        flags.append("manual-review-required")
    return _unique(flags)

def _receipt_correlation_key_and_signals(receipt: GitActivityImportReceipt) -> tuple[str, list[dict[str, Any]]]:
    normalized = receipt.spec.normalized
    provider = receipt.spec.provider or "unknown"
    repository = receipt.spec.repository or "unknown"
    project = receipt.spec.project
    activity_type = _string_value(normalized.get("activityType")) or "event"
    external_id = _string_value(normalized.get("externalId"))
    commit = _string_value(normalized.get("commit"))
    pull_request = _pull_request_identifier(normalized)
    primary_ref = _primary_ref(receipt.spec.refs)
    signals: list[dict[str, Any]] = []
    if pull_request:
        signals.append(_correlation_signal("pull-request", pull_request, receipt.object_id, weight=5))
    if external_id:
        signals.append(_correlation_signal("external-id", external_id, receipt.object_id, weight=4))
    if primary_ref:
        signals.append(_correlation_signal("ref", primary_ref, receipt.object_id, weight=3))
    if commit:
        signals.append(_correlation_signal("commit", commit, receipt.object_id, weight=3))
    payload_short = _string_value(normalized.get("payloadDigestShort")) or receipt.spec.payloadDigest.removeprefix("sha256:")[:16]
    if payload_short:
        signals.append(_correlation_signal("payload-digest", payload_short, receipt.object_id, weight=1))
    for activity_id in receipt.spec.importedActivities:
        signals.append(_correlation_signal("imported-activity", activity_id, receipt.object_id, weight=2))

    if pull_request:
        key = f"pr:{provider}:{project}:{repository}:{_key_part(pull_request)}"
    elif activity_type in {"pull-request", "review-comment", "merge"} and external_id:
        key = f"external:{provider}:{project}:{repository}:{_key_part(external_id)}"
    elif activity_type == "commit" and primary_ref:
        key = f"ref:{provider}:{project}:{repository}:{_key_part(primary_ref)}"
    elif commit:
        key = f"commit:{provider}:{project}:{repository}:{commit[:12]}"
    elif external_id:
        key = f"external:{provider}:{project}:{repository}:{_key_part(external_id)}"
    else:
        key = f"payload:{provider}:{project}:{repository}:{_key_part(payload_short or receipt.object_id)}"
    return key, signals

def _correlation_signal(kind: str, value: str, receipt_id: str, *, weight: int) -> dict[str, Any]:
    return {
        "kind": kind,
        "value": value,
        "weight": weight,
        "sourceReceipt": receipt_id,
        "evidence": {"source": "GitActivityImportReceipt"},
    }

def _pull_request_identifier(normalized: dict[str, Any]) -> str | None:
    for key in ("pullRequest", "pullRequestNumber", "prNumber", "mergeRequest", "mergeRequestIid"):
        value = _string_value(normalized.get(key))
        if value:
            return value
    return None

def _primary_ref(refs: list[str]) -> str | None:
    for ref in refs:
        if ref.startswith("ref:") or ref.startswith("redacted-ref:"):
            return ref
    return None

def _key_part(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value):
        return value
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"

def _correlation_group_summary(group: dict[str, Any]) -> str:
    parts = [
        f"{len(group['receipts'])} receipt(s)",
        f"{len(group['importedActivities'])} imported GitActivity record(s)",
        f"{len(group['eventFamilies'])} event family/families",
    ]
    if group.get("pullRequests"):
        parts.append(f"pull requests: {', '.join(group['pullRequests'])}")
    if group.get("commits"):
        parts.append(f"commits: {', '.join(str(value)[:12] for value in group['commits'])}")
    if group.get("refs"):
        parts.append(f"refs: {', '.join(group['refs'][:3])}")
    return "; ".join(parts)

def _repository_path(workspace_root: Path, local_path: str | None, url: str | None) -> Path:
    if local_path:
        path = Path(local_path).expanduser()
        return path if path.is_absolute() else (workspace_root.parent / path).resolve()
    if url and url.startswith("file://"):
        return Path(url.removeprefix("file://")).expanduser()
    raise ValueError("repository must declare localPath or file:// url for local scan")

def _current_ref(repo_path: Path) -> str:
    branch = _git(repo_path, ["branch", "--show-current"], check=False).strip()
    if branch:
        return branch
    return "HEAD"

def _sanitize_ref(ref: str) -> tuple[str, bool]:
    if SENSITIVE_REF_RE.search(ref):
        digest = hashlib.sha256(ref.encode("utf-8")).hexdigest()[:16]
        return f"redacted-ref:{digest}", True
    return f"ref:{ref}", False

def _redacted_identifier(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("redacted:sha256:"):
        return value
    return f"redacted:sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"

def _redacted_ref_value(value: str) -> str:
    if value.startswith("redacted-ref:") or value.startswith("redacted-commit:"):
        return value
    if value.startswith("commit:"):
        return f"redacted-commit:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"
    return f"redacted-ref:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"

def _evidence_ref(value: str) -> dict[str, str]:
    return {"kind": "workspace-path", "path": value}

def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _next_git_activity_id(workspace_root: Path) -> str:
    now = datetime.now().astimezone()
    for _ in range(100):
        activity_id = timestamp_git_activity_id(now)
        if not (workspace_root / "git_activity" / f"{activity_id}.yaml").exists():
            return activity_id
        now = now + timedelta(milliseconds=1)
    raise RuntimeError("could not allocate unique GitActivity id")

def _next_git_activity_import_receipt_id(workspace_root: Path) -> str:
    now = datetime.now().astimezone()
    for _ in range(100):
        receipt_id = timestamp_git_activity_import_receipt_id(now)
        if not (workspace_root / "git_activity" / "imports" / f"{receipt_id}.yaml").exists():
            return receipt_id
        now = now + timedelta(milliseconds=1)
    raise RuntimeError("could not allocate unique GitActivityImportReceipt id")

def _next_git_activity_correlation_review_id(workspace_root: Path) -> str:
    now = datetime.now().astimezone()
    for _ in range(100):
        review_id = timestamp_git_activity_correlation_review_id(now)
        if not (workspace_root / "git_activity" / "correlations" / f"{review_id}.yaml").exists():
            return review_id
        now = now + timedelta(milliseconds=1)
    raise RuntimeError("could not allocate unique GitActivityCorrelationReview id")

def _normalize_provider_payload(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    if provider == "github":
        return _normalize_github_payload(payload)
    if provider == "gitlab":
        return _normalize_gitlab_payload(payload)
    raise ValueError(f"unsupported git activity provider {provider}")

def _normalize_github_payload(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = _safe_metadata_string(_first_string(payload.get("event"), payload.get("action"), payload.get("hook", {}).get("type") if isinstance(payload.get("hook"), dict) else None)) or _infer_github_event(payload)
    raw_ref = _first_string(
        payload.get("ref"),
        _nested_value(payload, "pull_request", "head", "ref"),
        _nested_value(payload, "pull_request", "base", "ref"),
        _nested_value(payload, "ref_name"),
    )
    sanitized_ref, ref_redacted = _sanitize_ref(raw_ref) if raw_ref else ("", False)
    commit = _sha_value(_first_string(payload.get("after"), payload.get("checkout_sha"), _nested_value(payload, "pull_request", "head", "sha")))
    external_id = _safe_external_id(_first_string(_nested_value(payload, "pull_request", "node_id"), _nested_value(payload, "pull_request", "id"), _nested_value(payload, "pull_request", "number"), payload.get("delivery_id"), payload.get("deliveryId")))
    pull_request = _safe_external_id(_first_string(_nested_value(payload, "pull_request", "number"), _nested_value(payload, "issue", "number")))
    url_hash = _hash_or_none(_first_string(_nested_value(payload, "pull_request", "html_url"), _nested_value(payload, "comment", "html_url"), payload.get("html_url")))
    actor_hash = _hash_or_none(_first_string(_nested_value(payload, "sender", "login"), _nested_value(payload, "pusher", "name")))
    repo_hash = _hash_or_none(_first_string(_nested_value(payload, "repository", "full_name"), _nested_value(payload, "repository", "name")))
    installation_id = _safe_external_id(_first_string(_nested_value(payload, "installation", "id")))
    normalized = {
        "provider": "github",
        "eventType": event_type,
        "activityType": _activity_type_from_github(payload, event_type),
        "ref": sanitized_ref or None,
        "refRedacted": ref_redacted,
        "commit": commit,
        "externalId": external_id,
        "pullRequest": pull_request,
        "urlSha256": url_hash,
        "actorLoginSha256": actor_hash,
        "repositoryFullNameSha256": repo_hash,
        "installationId": installation_id,
        "occurredAt": _first_string(_nested_value(payload, "pull_request", "updated_at"), _nested_value(payload, "pull_request", "created_at"), _nested_value(payload, "head_commit", "timestamp")),
    }
    return {key: value for key, value in normalized.items() if value not in {None, ""}}

def _normalize_gitlab_payload(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = _safe_metadata_string(_first_string(payload.get("object_kind"), payload.get("event_name"), payload.get("event_type"))) or "event"
    raw_ref = _first_string(
        payload.get("ref"),
        _nested_value(payload, "object_attributes", "source_branch"),
        _nested_value(payload, "object_attributes", "target_branch"),
        _nested_value(payload, "object_attributes", "ref"),
    )
    sanitized_ref, ref_redacted = _sanitize_ref(raw_ref) if raw_ref else ("", False)
    commit = _sha_value(_first_string(payload.get("after"), payload.get("checkout_sha"), _nested_value(payload, "object_attributes", "last_commit", "id")))
    external_id = _safe_external_id(_first_string(_nested_value(payload, "object_attributes", "id"), _nested_value(payload, "object_attributes", "iid"), payload.get("event_id")))
    merge_request = _safe_external_id(_first_string(_nested_value(payload, "object_attributes", "iid")))
    url_hash = _hash_or_none(_first_string(_nested_value(payload, "object_attributes", "url"), _nested_value(payload, "project", "web_url")))
    actor_hash = _hash_or_none(_first_string(payload.get("user_username"), _nested_value(payload, "user", "username"), payload.get("user_name")))
    repo_hash = _hash_or_none(_first_string(_nested_value(payload, "project", "path_with_namespace"), _nested_value(payload, "repository", "name")))
    installation_id = _safe_external_id(_first_string(_nested_value(payload, "project", "id")))
    normalized = {
        "provider": "gitlab",
        "eventType": event_type,
        "activityType": _activity_type_from_gitlab(payload, event_type),
        "ref": sanitized_ref or None,
        "refRedacted": ref_redacted,
        "commit": commit,
        "externalId": external_id,
        "mergeRequest": merge_request,
        "urlSha256": url_hash,
        "actorLoginSha256": actor_hash,
        "repositoryFullNameSha256": repo_hash,
        "installationId": installation_id,
        "occurredAt": _first_string(_nested_value(payload, "object_attributes", "updated_at"), _nested_value(payload, "object_attributes", "created_at"), payload.get("event_created_at")),
    }
    return {key: value for key, value in normalized.items() if value not in {None, ""}}

def _infer_github_event(payload: dict[str, Any]) -> str:
    if payload.get("pull_request"):
        return "pull_request"
    if payload.get("review") or payload.get("comment"):
        return "review_comment"
    if payload.get("after") or payload.get("commits"):
        return "push"
    return "event"

def _activity_type_from_github(payload: dict[str, Any], event_type: str) -> str:
    event = event_type.lower()
    if "pull" in event or payload.get("pull_request"):
        return "pull-request"
    if "review" in event or "comment" in event or payload.get("review") or payload.get("comment"):
        return "review-comment"
    if "create" in event or "delete" in event:
        return "branch"
    if payload.get("ref_type") == "tag" or "tag" in event:
        return "tag"
    if payload.get("after") or payload.get("commits") or "push" in event:
        return "commit"
    return "other"

def _activity_type_from_gitlab(payload: dict[str, Any], event_type: str) -> str:
    event = event_type.lower()
    if "merge_request" in event:
        return "pull-request"
    if "note" in event or "comment" in event:
        return "review-comment"
    if "tag" in event:
        return "tag"
    if payload.get("after") or "push" in event:
        return "commit"
    return "other"

def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (int, float)):
            return str(value)
    return None

def _provider_repository_name(provider: str, payload: dict[str, Any]) -> str | None:
    if provider == "github":
        return _first_string(_nested_value(payload, "repository", "full_name"), _nested_value(payload, "repository", "name"))
    if provider == "gitlab":
        return _first_string(_nested_value(payload, "project", "path_with_namespace"), _nested_value(payload, "repository", "name"))
    return None

def _provider_installation_id(provider: str, payload: dict[str, Any]) -> str | None:
    if provider == "github":
        return _first_string(_nested_value(payload, "installation", "id"))
    if provider == "gitlab":
        return _first_string(_nested_value(payload, "project", "id"))
    return None

def _provider_actor_login(provider: str, payload: dict[str, Any]) -> str | None:
    if provider == "github":
        return _first_string(_nested_value(payload, "sender", "login"), _nested_value(payload, "pusher", "name"))
    if provider == "gitlab":
        return _first_string(payload.get("user_username"), _nested_value(payload, "user", "username"), payload.get("user_name"))
    return None

def _provider_ref(provider: str, payload: dict[str, Any]) -> str | None:
    if provider == "github":
        return _first_string(
            payload.get("ref"),
            _nested_value(payload, "pull_request", "head", "ref"),
            _nested_value(payload, "pull_request", "base", "ref"),
            payload.get("ref_name"),
        )
    if provider == "gitlab":
        return _first_string(
            payload.get("ref"),
            _nested_value(payload, "object_attributes", "source_branch"),
            _nested_value(payload, "object_attributes", "target_branch"),
            _nested_value(payload, "object_attributes", "ref"),
        )
    return None

def _repository_allowed(repository_id: str, provider_repository: str | None, allowed_repositories: list[str]) -> bool:
    candidates = {repository_id}
    if provider_repository:
        candidates.add(provider_repository)
        candidates.add(f"sha256:{hashlib.sha256(provider_repository.encode('utf-8')).hexdigest()}")
    return any(candidate in allowed_repositories for candidate in candidates)

def _matches_any(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)

def _select_actor_mapping(mappings: list[Any], actor_login: str | None, actor_login_hash: str | None) -> Any | None:
    for mapping in mappings:
        raw_login = getattr(mapping, "actorLogin", None)
        login_hash = getattr(mapping, "actorLoginSha256", None)
        if raw_login and actor_login and raw_login == actor_login:
            return mapping
        if login_hash and actor_login_hash and login_hash == actor_login_hash:
            return mapping
    return None

def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []

def _nested_value(payload: dict[str, Any], *path: str) -> Any:
    value: Any = payload
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value

def _safe_metadata_string(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())[:80]
    if not cleaned or SENSITIVE_REF_RE.search(cleaned):
        return "redacted"
    return cleaned

def _safe_external_id(value: str | None) -> str | None:
    if not value:
        return None
    if re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value) and not SENSITIVE_REF_RE.search(value):
        return value
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"

def _sha_value(value: str | None) -> str | None:
    if value and re.fullmatch(r"[0-9a-fA-F]{7,64}", value):
        return value.lower()
    return None

def _hash_or_none(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None

def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None

def _unique(values: list[Any]) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result

def _git(cwd: Path, args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=60)
    if check and result.returncode != 0:
        raise ValueError(f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def _common_promoted_activity(
    index: WorkspaceIndex,
    review: GitActivityCorrelationReview,
    receipts: list[GitActivityImportReceipt],
) -> GitActivity | None:
    activity_sets = [set(receipt.spec.importedActivities) for receipt in receipts]
    if not any(activity_sets) and not review.spec.importedActivities:
        return None
    if any(not activity_set for activity_set in activity_sets):
        raise ValueError("correlation review has a partially promoted receipt set; promote or unwind individual receipts before group promotion")
    common = set.intersection(*activity_sets)
    union = set.union(*activity_sets)
    if len(common) != 1 or union != common:
        raise ValueError("correlation review receipts already link different GitActivity records; refusing to double-count grouped evidence")
    activity_id = next(iter(common))
    if review.spec.importedActivities and set(review.spec.importedActivities) != {activity_id}:
        raise ValueError("correlation review importedActivities disagree with receipt importedActivities")
    activity = index.git_activities.get(activity_id)
    if not activity:
        raise ValueError(f"correlation review references missing GitActivity {activity_id}")
    return activity

def _mark_correlation_review_promoted(
    index: WorkspaceIndex,
    review: GitActivityCorrelationReview,
    receipts: list[GitActivityImportReceipt],
    activity: GitActivity,
    *,
    reviewer_member: str,
    permission_decisions: list[tuple[str, dict[str, Any]]],
    idempotent: bool,
) -> GitActivityCorrelationReview:
    if activity.object_id in review.spec.importedActivities:
        return review
    permission_decisions = permission_decisions or _correlation_promotion_permissions(index, review, receipts, reviewer_member=reviewer_member)
    for label, decision in permission_decisions:
        if decision["decision"] == "deny" or decision.get("blockers"):
            raise ValueError(f"{label} is denied by effective permissions: {decision.get('reason')}; blockers={decision.get('blockers')}")
    audit = _correlation_promotion_audit(
        index,
        review,
        receipts,
        activity,
        reviewer_member=reviewer_member,
        permission_decisions=permission_decisions,
        idempotent=idempotent,
    )
    review_payload = review.model_dump(mode="json", exclude_none=True)
    review_spec = review_payload.setdefault("spec", {})
    review_spec["importedActivities"] = _unique([*review.spec.importedActivities, activity.object_id])
    review_spec["members"] = _unique([*review.spec.members, activity.spec.member])
    if activity.spec.assignment:
        review_spec["assignments"] = _unique([*review.spec.assignments, activity.spec.assignment])
    review_spec["eventFamilies"] = _unique([*review.spec.eventFamilies, activity.spec.activityType])
    review_spec["refs"] = _unique([*review.spec.refs, *activity.spec.refs])
    review_spec["evidence"] = _unique([*review.spec.evidence, f"git_activity/{activity.object_id}.yaml"])
    review_spec.setdefault("decisionAudit", [])
    review_spec["decisionAudit"].append(audit)
    updated_review = GitActivityCorrelationReview.model_validate(review_payload)
    write_yaml(index.workspace_root / "git_activity" / "correlations" / f"{review.object_id}.yaml", updated_review.model_dump(mode="json", exclude_none=True))
    return updated_review

def _correlation_promotion_permissions(
    index: WorkspaceIndex,
    review: GitActivityCorrelationReview,
    receipts: list[GitActivityImportReceipt],
    *,
    reviewer_member: str,
) -> list[tuple[str, dict[str, Any]]]:
    reviewer = index.members[reviewer_member]
    non_interactive = reviewer.spec.kind == "service"
    decisions = [
        (
            "correlation review update",
            explain_effective_permissions(
                index,
                member=reviewer_member,
                project=review.spec.project,
                action={"tool": "Edit", "path": f"/.aiteamos/git_activity/correlations/{review.object_id}.yaml", "operation": "update"},
                non_interactive=non_interactive,
            ),
        ),
        (
            "GitActivity creation",
            explain_effective_permissions(
                index,
                member=reviewer_member,
                project=review.spec.project,
                action={"tool": "Edit", "path": "/.aiteamos/git_activity/GIT-*.yaml", "operation": "create"},
                non_interactive=non_interactive,
            ),
        ),
    ]
    for receipt in receipts:
        decisions.append(
            (
                f"receipt {receipt.object_id} update",
                explain_effective_permissions(
                    index,
                    member=reviewer_member,
                    project=review.spec.project,
                    action={"tool": "Edit", "path": f"/.aiteamos/git_activity/imports/{receipt.object_id}.yaml", "operation": "update"},
                    non_interactive=non_interactive,
                ),
            )
        )
    return decisions

def _correlation_promotion_audit(
    index: WorkspaceIndex,
    review: GitActivityCorrelationReview,
    receipts: list[GitActivityImportReceipt],
    activity: GitActivity,
    *,
    reviewer_member: str,
    permission_decisions: list[tuple[str, dict[str, Any]]],
    idempotent: bool,
) -> Any:
    reviewer = index.members[reviewer_member]
    policy_refs: list[str] = []
    for _, decision in permission_decisions:
        policy_refs.extend(decision.get("selectedPolicyIds", []))
    risk_assessment = next((decision.get("riskAssessment") for _, decision in permission_decisions if decision.get("riskAssessment")), None)
    return decision_audit_record(
        index,
        decision_kind="service_policy_decision" if reviewer.spec.kind == "service" else "human_approval",
        decision="promote-correlation-idempotent" if idempotent else "promote-correlation",
        actor_member=reviewer_member,
        authority="enforce" if reviewer.spec.kind == "service" else "approve",
        reason="Approved Git import correlation review was consumed into one durable GitActivity without duplicating grouped evidence.",
        source="git-activity-correlation-promotion",
        policy_refs=_unique(policy_refs),
        evidence=[
            {"kind": "GitActivityCorrelationReview", "id": review.object_id},
            {"kind": "GitActivity", "id": activity.object_id},
            *[{"kind": "GitActivityImportReceipt", "id": receipt.object_id} for receipt in receipts],
        ],
        requires_human_review=False,
        risk_assessment=risk_assessment,
        metadata={
            "correlationKey": review.spec.correlationKey,
            "targetMember": activity.spec.member,
            "targetAssignment": activity.spec.assignment,
            "receiptCount": len(receipts),
            "idempotent": idempotent,
        },
    )

def _common_normalized_value(receipts: list[GitActivityImportReceipt], key: str) -> str | None:
    values = _unique([value for value in (_string_value(receipt.spec.normalized.get(key)) for receipt in receipts) if value])
    return values[0] if len(values) == 1 else None

def _common_receipt_value(receipts: list[GitActivityImportReceipt], key: str) -> str | None:
    values = _unique([value for value in (_string_value(getattr(receipt.spec, key, None)) for receipt in receipts) if value])
    return values[0] if len(values) == 1 else None

def _selected_correlation_activity_type(
    review: GitActivityCorrelationReview,
    receipts: list[GitActivityImportReceipt],
    requested: str | None,
) -> str:
    candidates = [
        requested,
        _string_value(review.spec.recommendedPromotion.get("activityType")),
        *(value for value in review.spec.eventFamilies),
        *(_string_value(receipt.spec.normalized.get("activityType")) for receipt in receipts),
        "pull-request" if review.spec.pullRequests else None,
        "commit" if review.spec.commits else None,
        "other",
    ]
    for candidate in candidates:
        if candidate in GIT_ACTIVITY_TYPES:
            return str(candidate)
    return "other"

def _first_string_value(*values: Any) -> str | None:
    for value in values:
        candidate = _string_value(value)
        if candidate:
            return candidate
    return None

def _promotion_int(config: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = config.get(key)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return None
    return None

def _promotion_float(config: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = config.get(key)
        if value is None:
            continue
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None
    return None


__all__ = [
    "git_activity_correlation_preview",
    "git_activity_correlation_promotion_candidates",
    "promote_git_activity_correlation_review",
    "review_git_activity_correlation",
]

__all__ = [
    "GIT_ACTIVITY_EXPORT_POLICIES",
    "GIT_ACTIVITY_LIFECYCLES",
    "GIT_ACTIVITY_PROVIDERS",
    "GIT_ACTIVITY_REDACTION_POLICIES",
    "GIT_ACTIVITY_RETENTION_TARGETS",
    "GIT_ACTIVITY_TYPES",
    "PROVIDER_EVENT_SOURCES",
    "SENSITIVE_REF_RE",
]
