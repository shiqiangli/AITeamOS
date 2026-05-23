from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib

from aiteamos_schema import API_VERSION, GitActivity, GitActivityImportReceipt

from ..audit import decision_audit_record
from ..connector_health import connector_health_admission_decision
from ..io import write_yaml
from ..loader import WorkspaceIndex, load_workspace
from ..permissions import explain_effective_permissions
from .common import (
    GIT_ACTIVITY_PROVIDERS,
    PROVIDER_EVENT_SOURCES,
    SENSITIVE_REF_RE,
    _activity_type_from_gitlab,
    _current_ref,
    _digest,
    _git,
    _hash_or_none,
    _matches_any,
    _nested_value,
    _next_git_activity_id,
    _next_git_activity_import_receipt_id,
    _normalize_provider_payload,
    _provider_actor_login,
    _provider_installation_id,
    _provider_ref,
    _provider_repository_name,
    _repository_allowed,
    _repository_path,
    _safe_external_id,
    _sanitize_ref,
    _select_actor_mapping,
    _string_list,
    _string_value,
    _unique,
)


def admit_local_git_activity_import(
    workspace_path: str | Path,
    *,
    repository: str | None = None,
    ref: str | None = None,
    actor_member: str | None = None,
    received_at: str | None = None,
) -> dict[str, Any]:
    """Create a reviewed-boundary import receipt from local Git metadata."""

    index = load_workspace(workspace_path)
    repository_id = repository or index.project.spec.defaultRepository or next(iter(index.repositories), None)
    if not repository_id:
        raise ValueError("repository is required")
    if repository_id not in index.repositories:
        raise KeyError(f"unknown repository {repository_id}")
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")

    repo = index.repositories[repository_id]
    repo_path = _repository_path(index.workspace_root, repo.spec.localPath, repo.spec.url)
    if not repo_path.exists():
        raise ValueError(f"repository path does not exist: {repo_path}")
    _git(repo_path, ["rev-parse", "--is-inside-work-tree"])

    raw_ref = ref or _current_ref(repo_path)
    commit = _git(repo_path, ["rev-parse", f"{raw_ref}^{{commit}}"]).strip()
    log_fields = _git(repo_path, ["show", "-s", "--format=%H%x00%an%x00%ae%x00%aI%x00%s", commit]).split("\x00")
    while len(log_fields) < 5:
        log_fields.append("")
    commit_sha, author_name, author_email, authored_at, subject = log_fields[:5]
    changed_files = [line for line in _git(repo_path, ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha]).splitlines() if line]

    raw_payload = {
        "provider": "local",
        "project": index.project.object_id,
        "repository": repository_id,
        "ref": raw_ref,
        "commit": commit_sha,
        "authorName": author_name,
        "authorEmail": author_email,
        "authoredAt": authored_at,
        "subject": subject,
        "changedFiles": changed_files,
    }
    payload_digest = _digest(raw_payload)
    ref_digest = hashlib.sha256(raw_ref.encode("utf-8")).hexdigest()
    dedupe_key = f"local-git:{index.project.object_id}:{repository_id}:{commit_sha[:12]}:{ref_digest[:12]}"
    for existing in index.git_activity_import_receipts.values():
        if existing.spec.dedupeKey == dedupe_key:
            return {
                "receipt": existing,
                "created": False,
                "duplicateOf": existing.object_id,
                "dedupeKey": dedupe_key,
            }

    sanitized_ref, ref_redacted = _sanitize_ref(raw_ref)
    normalized = {
        "provider": "local",
        "ref": sanitized_ref,
        "refRedacted": ref_redacted,
        "commit": commit_sha,
        "commitShort": commit_sha[:12],
        "authorName": author_name,
        "authorEmailSha256": hashlib.sha256(author_email.encode("utf-8")).hexdigest() if author_email else None,
        "authoredAt": authored_at,
        "subjectSha256": hashlib.sha256(subject.encode("utf-8")).hexdigest() if subject else None,
        "changedFileCount": len(changed_files),
    }
    normalized = {key: value for key, value in normalized.items() if value is not None}
    now = received_at or datetime.now().astimezone().isoformat(timespec="milliseconds")
    receipt_id = _next_git_activity_import_receipt_id(index.workspace_root)
    payload = {
        "apiVersion": API_VERSION,
        "kind": "GitActivityImportReceipt",
        "metadata": {"id": receipt_id, "createdAt": now},
        "spec": {
            "project": index.project.object_id,
            "repository": repository_id,
            "provider": "local",
            "sourceType": "local-scan",
            "status": "needs-review",
            "dedupeKey": dedupe_key,
            "payloadDigest": f"sha256:{payload_digest}",
            "redactionPolicy": "metadata-only",
            "importPolicy": "reviewed-import",
            "payloadRetained": False,
            "receivedAt": now,
            "importerMember": actor_member,
            "importedActivities": [],
            "refs": [sanitized_ref, f"commit:{commit_sha}"],
            "normalized": normalized,
            "summary": f"Admitted local Git metadata for repository {repository_id} at commit {commit_sha[:12]}; review is required before creating GitActivity.",
            "evidence": [f"repositories/{repository_id}.yaml"],
            "decisionAudit": [
                decision_audit_record(
                    index,
                    decision_kind="system_check",
                    decision="needs-review",
                    actor_member=actor_member,
                    authority="record",
                    reason="Local Git metadata was normalized into an import receipt; durable GitActivity still requires review.",
                    source="git-activity-local-scan",
                    requires_human_review=True,
                    evidence=[
                        {
                            "kind": "git-local-scan",
                            "repository": repository_id,
                            "payloadDigest": f"sha256:{payload_digest}",
                            "refRedacted": ref_redacted,
                        }
                    ],
                )
            ],
        },
    }
    receipt = GitActivityImportReceipt.model_validate(payload)
    write_yaml(index.workspace_root / "git_activity" / "imports" / f"{receipt_id}.yaml", receipt.model_dump(mode="json", exclude_none=True))
    return {"receipt": receipt, "created": True, "dedupeKey": dedupe_key}

def admit_provider_git_activity_import(
    workspace_path: str | Path,
    *,
    provider: str,
    repository: str | None = None,
    source_type: str = "webhook",
    payload: dict[str, Any] | None = None,
    actor_member: str | None = None,
    connector: str | None = None,
    received_at: str | None = None,
) -> dict[str, Any]:
    """Create a reviewed-boundary import receipt from Git provider metadata."""

    provider_id = provider.strip().lower()
    if provider_id not in GIT_ACTIVITY_PROVIDERS:
        raise ValueError(f"unsupported git activity provider {provider}")
    if source_type not in PROVIDER_EVENT_SOURCES:
        raise ValueError(f"unsupported provider import source type {source_type}")

    raw_payload = payload or {}
    if not isinstance(raw_payload, dict):
        raise ValueError("payload must be a JSON object")
    index = load_workspace(workspace_path)
    repository_id = repository or index.project.spec.defaultRepository or next(iter(index.repositories), None)
    if not repository_id:
        raise ValueError("repository is required")
    if repository_id not in index.repositories:
        raise KeyError(f"unknown repository {repository_id}")
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")

    policy_explanation = explain_git_activity_import_policy(
        index,
        provider=provider_id,
        repository=repository_id,
        source_type=source_type,
        payload=raw_payload,
        connector=connector,
    )
    payload_digest = _digest(raw_payload)
    normalized = dict(policy_explanation["normalized"])
    ref_digest = hashlib.sha256(str(normalized.get("ref") or "").encode("utf-8")).hexdigest()
    dedupe_identity = _string_value(normalized.get("externalId")) or _string_value(normalized.get("commit")) or payload_digest[:16]
    dedupe_key = (
        f"provider-git:{provider_id}:{source_type}:{index.project.object_id}:{repository_id}:"
        f"{normalized.get('eventType', 'event')}:{ref_digest[:12]}:{dedupe_identity[:24]}"
    )
    for existing in index.git_activity_import_receipts.values():
        if existing.spec.dedupeKey == dedupe_key:
            return {
                "receipt": existing,
                "created": False,
                "duplicateOf": existing.object_id,
                "dedupeKey": dedupe_key,
            }

    refs = []
    if normalized.get("ref"):
        refs.append(str(normalized["ref"]))
    if normalized.get("commit"):
        refs.append(f"commit:{normalized['commit']}")

    now = received_at or datetime.now().astimezone().isoformat(timespec="milliseconds")
    receipt_id = _next_git_activity_import_receipt_id(index.workspace_root)
    evidence = [f"repositories/{repository_id}.yaml"]
    if connector:
        evidence.append(f"connectors/{connector}.yaml")
    status = "blocked" if policy_explanation["blockers"] else "needs-review"
    receipt_payload = {
        "apiVersion": API_VERSION,
        "kind": "GitActivityImportReceipt",
        "metadata": {"id": receipt_id, "createdAt": now},
        "spec": {
            "project": index.project.object_id,
            "repository": repository_id,
            "provider": provider_id,
            "connector": connector,
            "sourceType": source_type,
            "status": status,
            "dedupeKey": dedupe_key,
            "payloadDigest": f"sha256:{payload_digest}",
            "redactionPolicy": "metadata-only",
            "importPolicy": policy_explanation["importPolicy"],
            "payloadRetained": False,
            "receivedAt": now,
            "importerMember": actor_member,
            "importedActivities": [],
            "refs": refs,
            "normalized": {
                **normalized,
                "payloadDigestShort": payload_digest[:16],
            },
            "summary": (
                f"{'Blocked' if status == 'blocked' else 'Admitted'} {provider_id} {source_type} metadata for repository {repository_id}; "
                "review is required before creating GitActivity."
            ),
            "blockers": policy_explanation["blockers"],
            "warnings": policy_explanation["warnings"],
            "evidence": evidence,
            "decisionAudit": [
                decision_audit_record(
                    index,
                    decision_kind="system_check",
                    decision=status,
                    actor_member=actor_member,
                    authority="record",
                    reason="Git provider metadata was evaluated against connector import policy and normalized into an import receipt; durable GitActivity still requires review.",
                    source="git-activity-provider-admission",
                    requires_human_review=True,
                    evidence=[
                        {
                            "kind": "git-provider-event",
                            "provider": provider_id,
                            "sourceType": source_type,
                            "repository": repository_id,
                            "eventType": normalized.get("eventType"),
                            "payloadDigest": f"sha256:{payload_digest}",
                            "refRedacted": normalized.get("refRedacted", False),
                            "connectorPolicyDecision": policy_explanation["decision"],
                        }
                    ],
                )
            ],
        },
    }
    receipt = GitActivityImportReceipt.model_validate(receipt_payload)
    write_yaml(index.workspace_root / "git_activity" / "imports" / f"{receipt_id}.yaml", receipt.model_dump(mode="json", exclude_none=True))
    return {"receipt": receipt, "created": True, "dedupeKey": dedupe_key}

def explain_git_activity_import_policy(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    provider: str,
    repository: str | None = None,
    source_type: str = "webhook",
    payload: dict[str, Any] | None = None,
    connector: str | None = None,
) -> dict[str, Any]:
    """Explain how connector policy would treat Git provider import metadata."""

    provider_id = provider.strip().lower()
    if provider_id not in GIT_ACTIVITY_PROVIDERS:
        raise ValueError(f"unsupported git activity provider {provider}")
    if source_type not in PROVIDER_EVENT_SOURCES:
        raise ValueError(f"unsupported provider import source type {source_type}")
    raw_payload = payload or {}
    if not isinstance(raw_payload, dict):
        raise ValueError("payload must be a JSON object")
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    repository_id = repository or index.project.spec.defaultRepository or next(iter(index.repositories), None)
    if not repository_id:
        raise ValueError("repository is required")
    if repository_id not in index.repositories:
        raise KeyError(f"unknown repository {repository_id}")

    normalized = _normalize_provider_payload(provider_id, raw_payload)
    provider_repository = _provider_repository_name(provider_id, raw_payload)
    installation_id = _provider_installation_id(provider_id, raw_payload)
    actor_login = _provider_actor_login(provider_id, raw_payload)
    actor_login_hash = _hash_or_none(actor_login)
    raw_ref = _provider_ref(provider_id, raw_payload)
    blockers: list[str] = []
    warnings: list[str] = []
    import_policy = "reviewed-import"
    policy_summary: dict[str, Any] = {
        "enabled": False,
        "autoPromotion": "disabled",
        "dedupeStrategy": ["external-id", "commit-ref", "payload-digest"],
    }

    if connector is None:
        warnings.append("no connector supplied; provider import remains review-only and cannot use connector allowlists or actor mapping")
    else:
        if connector not in index.connectors:
            raise KeyError(f"unknown connector {connector}")
        connector_record = index.connectors[connector]
        connector_spec = connector_record.spec
        if connector_spec.provider != provider_id:
            blockers.append(f"connector {connector} provider {connector_spec.provider} does not match event provider {provider_id}")
        if connector_spec.connectorType != "git":
            blockers.append(f"connector {connector} is {connector_spec.connectorType}, not git")
        if connector_spec.projects and index.project.object_id not in connector_spec.projects:
            blockers.append(f"connector {connector} is not bound to project {index.project.object_id}")

        git_policy = connector_spec.gitActivityImport
        config = dict(connector_spec.config or {})
        allowed_repositories = _string_list(git_policy.allowedRepositories or config.get("allowedRepositories") or config.get("repositoryAllowlist") or config.get("repositories"))
        allowed_installations = _string_list(git_policy.allowedInstallationIds or config.get("allowedInstallationIds") or config.get("installationIds"))
        protected_patterns = _string_list(git_policy.protectedRefPatterns or config.get("protectedRefPatterns"))
        import_policy = git_policy.importPolicy
        policy_summary = {
            "enabled": git_policy.enabled,
            "autoPromotion": git_policy.autoPromotion,
            "dedupeStrategy": list(git_policy.dedupeStrategy),
            "allowedRepositoryCount": len(allowed_repositories),
            "allowedInstallationCount": len(allowed_installations),
            "actorMappingCount": len(git_policy.actorMappings),
            "protectedRefPatternCount": len(protected_patterns),
            "requireHealthyConnector": git_policy.requireHealthyConnector,
        }
        if not git_policy.enabled:
            warnings.append(f"connector {connector} has gitActivityImport disabled; provider import remains manual-review only")
        if allowed_repositories and not _repository_allowed(repository_id, provider_repository, allowed_repositories):
            blockers.append("provider repository is outside connector git import allowlist")
        elif not allowed_repositories:
            warnings.append(f"connector {connector} has no git import repository allowlist")
        if allowed_installations and (not installation_id or installation_id not in allowed_installations):
            blockers.append("provider installation id is outside connector git import allowlist")
        elif allowed_installations and installation_id:
            normalized["installationId"] = installation_id
        elif not allowed_installations:
            warnings.append(f"connector {connector} has no git import installation allowlist")

        if raw_ref and (_matches_any(raw_ref, protected_patterns) or SENSITIVE_REF_RE.search(raw_ref)):
            normalized["protectedRef"] = True
            warnings.append("provider ref is protected or sensitive; durable GitActivity requires explicit review")

        mapping = _select_actor_mapping(git_policy.actorMappings, actor_login, actor_login_hash)
        if mapping is not None:
            normalized["actorMappingPolicy"] = mapping.policy
            if mapping.policy == "ignore":
                blockers.append("provider actor mapping is configured to ignore this actor")
            elif mapping.policy == "map-to-member":
                if not mapping.member:
                    blockers.append("provider actor mapping is map-to-member but has no member")
                elif mapping.member not in index.members:
                    blockers.append(f"provider actor mapping targets unknown member {mapping.member}")
                else:
                    normalized["member"] = mapping.member
                    if mapping.assignment:
                        if mapping.assignment not in index.assignments:
                            blockers.append(f"provider actor mapping targets unknown assignment {mapping.assignment}")
                        else:
                            assignment = index.assignments[mapping.assignment]
                            if assignment.spec.member != mapping.member:
                                blockers.append(f"provider actor mapping assignment {mapping.assignment} belongs to {assignment.spec.member}, not {mapping.member}")
                            elif assignment.spec.project != index.project.object_id:
                                blockers.append(f"provider actor mapping assignment {mapping.assignment} belongs to project {assignment.spec.project}")
                            else:
                                normalized["assignment"] = mapping.assignment
            else:
                warnings.append("provider actor mapping requires explicit review")
        elif git_policy.defaultMember:
            if git_policy.defaultMember not in index.members:
                blockers.append(f"git import defaultMember {git_policy.defaultMember} is unknown")
            else:
                normalized["member"] = git_policy.defaultMember
                if git_policy.defaultAssignment:
                    if git_policy.defaultAssignment not in index.assignments:
                        blockers.append(f"git import defaultAssignment {git_policy.defaultAssignment} is unknown")
                    else:
                        normalized["assignment"] = git_policy.defaultAssignment
        else:
            warnings.append("no provider actor mapping matched; promotion must choose TeamMember and Assignment explicitly")
        if git_policy.autoPromotion != "disabled":
            warnings.append("auto promotion is not enabled by this slice; service-policy still requires reviewed promotion")
        if git_policy.requireHealthyConnector:
            health = connector_health_admission_decision(index, connector, config=config)
            blockers.extend(health["blockers"])
            warnings.extend(health["warnings"])
            policy_summary["connectorHealth"] = health["record"]

    normalized = {key: value for key, value in normalized.items() if value not in {None, ""}}
    decision = "blocked" if blockers else "admit-needs-review"
    return {
        "decision": decision,
        "canCreateReceipt": True,
        "canAutoPromote": False,
        "project": index.project.object_id,
        "repository": repository_id,
        "provider": provider_id,
        "connector": connector,
        "sourceType": source_type,
        "importPolicy": import_policy,
        "targetMember": normalized.get("member"),
        "targetAssignment": normalized.get("assignment"),
        "normalized": normalized,
        "policy": policy_summary,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
    }

def promote_git_activity_import_receipt(
    workspace_path: str | Path,
    receipt_id: str,
    *,
    reviewer_member: str,
    member: str | None = None,
    assignment: str | None = None,
    activity_type: str | None = None,
    summary: str | None = None,
    occurred_at: str | None = None,
    visibility: str = "project",
    refs: list[str] | None = None,
) -> dict[str, Any]:
    """Promote a reviewed Git import receipt into durable GitActivity evidence."""

    index = load_workspace(workspace_path)
    if receipt_id not in index.git_activity_import_receipts:
        raise KeyError(f"unknown git activity import receipt {receipt_id}")
    if reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    reviewer = index.members[reviewer_member]
    receipt = index.git_activity_import_receipts[receipt_id]
    if receipt.spec.project != index.project.object_id:
        raise ValueError(f"receipt {receipt_id} targets project {receipt.spec.project}, not {index.project.object_id}")
    if receipt.spec.status == "imported":
        activities = [index.git_activities[activity_id] for activity_id in receipt.spec.importedActivities if activity_id in index.git_activities]
        if len(activities) == len(receipt.spec.importedActivities):
            return {"receipt": receipt, "activities": activities, "created": False, "alreadyImported": True}
        raise ValueError(f"receipt {receipt_id} is imported but references missing GitActivity records")
    if receipt.spec.status not in {"candidate", "needs-review"}:
        raise ValueError(f"receipt {receipt_id} cannot be promoted from status {receipt.spec.status}")
    if reviewer.spec.kind == "service" and receipt.spec.importPolicy != "service-policy-import":
        raise ValueError("service reviewers can promote only service-policy-import receipts")
    if reviewer.spec.kind != "human" and not (reviewer.spec.kind == "service" and receipt.spec.importPolicy == "service-policy-import"):
        raise ValueError("git activity import promotion requires a human reviewer or governed service policy reviewer")

    normalized = receipt.spec.normalized
    target_member = member or _string_value(normalized.get("member"))
    if not target_member:
        raise ValueError("promotion requires a target member when the receipt does not declare normalized.member")
    if target_member not in index.members:
        raise KeyError(f"unknown target member {target_member}")
    target_assignment = assignment or _string_value(normalized.get("assignment"))
    if target_assignment:
        if target_assignment not in index.assignments:
            raise KeyError(f"unknown assignment {target_assignment}")
        assignment_record = index.assignments[target_assignment]
        if assignment_record.spec.member != target_member:
            raise ValueError(f"assignment {target_assignment} belongs to member {assignment_record.spec.member}, not {target_member}")
        if assignment_record.spec.project != receipt.spec.project:
            raise ValueError(f"assignment {target_assignment} belongs to project {assignment_record.spec.project}, not {receipt.spec.project}")
    if receipt.spec.repository and receipt.spec.repository not in index.repositories:
        raise KeyError(f"unknown repository {receipt.spec.repository}")

    permission_update = explain_effective_permissions(
        index,
        member=reviewer_member,
        project=receipt.spec.project,
        action={"tool": "Edit", "path": f"/.aiteamos/git_activity/imports/{receipt_id}.yaml", "operation": "update"},
        non_interactive=reviewer.spec.kind == "service",
    )
    permission_create = explain_effective_permissions(
        index,
        member=reviewer_member,
        project=receipt.spec.project,
        action={"tool": "Edit", "path": "/.aiteamos/git_activity/GIT-*.yaml", "operation": "create"},
        non_interactive=reviewer.spec.kind == "service",
    )
    for label, decision in [("receipt update", permission_update), ("GitActivity creation", permission_create)]:
        if decision["decision"] == "deny" or decision.get("blockers"):
            raise ValueError(f"{label} is denied by effective permissions: {decision.get('reason')}; blockers={decision.get('blockers')}")

    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    git_activity_id = _next_git_activity_id(index.workspace_root)
    selected_activity_type = activity_type or _string_value(normalized.get("activityType")) or ("commit" if normalized.get("commit") else "other")
    selected_refs = refs if refs is not None else list(receipt.spec.refs)
    evidence = _unique([*receipt.spec.evidence, f"git_activity/imports/{receipt_id}.yaml"])
    activity = GitActivity.model_validate(
        {
            "apiVersion": API_VERSION,
            "kind": "GitActivity",
            "metadata": {"id": git_activity_id, "createdAt": now},
            "spec": {
                "member": target_member,
                "project": receipt.spec.project,
                "repository": receipt.spec.repository,
                "assignment": target_assignment,
                "activityType": selected_activity_type,
                "provider": receipt.spec.provider,
                "externalId": _string_value(normalized.get("externalId")) or _string_value(normalized.get("commit")),
                "url": _string_value(normalized.get("url")),
                "occurredAt": occurred_at or _string_value(normalized.get("authoredAt")) or now,
                "summary": summary or receipt.spec.summary or f"Promoted reviewed Git import receipt {receipt_id}.",
                "refs": selected_refs,
                "evidence": evidence,
                "visibility": visibility,
            },
        }
    )

    audit = decision_audit_record(
        index,
        decision_kind="human_approval" if reviewer.spec.kind == "human" else "service_policy_decision",
        decision="promote",
        actor_member=reviewer_member,
        authority="approve" if reviewer.spec.kind == "human" else "enforce",
        reason="Reviewed Git import receipt was promoted into durable GitActivity evidence.",
        source="git-activity-import-promotion",
        policy_refs=_unique([*permission_update.get("selectedPolicyIds", []), *permission_create.get("selectedPolicyIds", [])]),
        evidence=[
            {"kind": "GitActivityImportReceipt", "id": receipt_id},
            {"kind": "GitActivity", "id": git_activity_id},
        ],
        requires_human_review=False,
        risk_assessment=permission_create.get("riskAssessment"),
        metadata={
            "receiptUpdateDecision": permission_update.get("decision"),
            "activityCreateDecision": permission_create.get("decision"),
            "targetMember": target_member,
            "targetAssignment": target_assignment,
        },
    )
    receipt_payload = receipt.model_dump(mode="json", exclude_none=True)
    receipt_spec = receipt_payload.setdefault("spec", {})
    receipt_spec["status"] = "imported"
    receipt_spec["reviewedByMember"] = reviewer_member
    receipt_spec["reviewedAt"] = now
    receipt_spec["importedActivities"] = _unique([*receipt.spec.importedActivities, git_activity_id])
    receipt_spec["evidence"] = _unique([*receipt.spec.evidence, f"git_activity/{git_activity_id}.yaml"])
    receipt_spec.setdefault("decisionAudit", [])
    receipt_spec["decisionAudit"].append(audit)
    updated_receipt = GitActivityImportReceipt.model_validate(receipt_payload)

    write_yaml(index.workspace_root / "git_activity" / f"{git_activity_id}.yaml", activity.model_dump(mode="json", exclude_none=True))
    write_yaml(index.workspace_root / "git_activity" / "imports" / f"{receipt_id}.yaml", updated_receipt.model_dump(mode="json", exclude_none=True))
    return {"receipt": updated_receipt, "activities": [activity], "created": True, "alreadyImported": False}


__all__ = [
    "admit_local_git_activity_import",
    "admit_provider_git_activity_import",
    "explain_git_activity_import_policy",
    "promote_git_activity_import_receipt",
]
