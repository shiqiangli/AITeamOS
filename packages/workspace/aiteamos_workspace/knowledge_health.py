from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aiteamos_schema import KnowledgeHealthRecord

from .connector_operations import connector_failure_escalation_candidates
from .loader import WorkspaceIndex, load_workspace
from .memory_gate import STRONG_CONFIDENCE, SENSITIVE_TERMS, evaluate_memory_promotion_gate


STALE_AFTER_DAYS = 90


def evaluate_knowledge_health(workspace_or_index: str | Path | WorkspaceIndex) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    issues: list[dict[str, Any]] = []

    for entry_id in sorted(index.memory_entries):
        entry = index.memory_entries[entry_id]
        _memory_entry_issues(index, entry_id, entry, issues)

    for binding_id in sorted(index.memory_bindings):
        binding = index.memory_bindings[binding_id]
        _memory_binding_issues(index, binding_id, binding, issues)

    for grant_id in sorted(index.memory_grants):
        grant = index.memory_grants[grant_id]
        _memory_grant_issues(index, grant_id, grant, issues)

    for proposal_id in sorted(index.memory_proposals):
        proposal = index.memory_proposals[proposal_id]
        if proposal.spec.status != "pending-review":
            continue
        gate = evaluate_memory_promotion_gate(index, proposal_id)
        if gate["blockers"]:
            issues.append(
                {
                    "severity": "warning",
                    "kind": "memory-proposal-blocked",
                    "ref": proposal_id,
                    "message": f"Pending proposal has {len(gate['blockers'])} promotion blocker(s).",
                    "action": "Edit the proposal evidence, confidence, or content before approval.",
                }
            )
        elif gate["warnings"]:
            issues.append(
                {
                    "severity": "info",
                    "kind": "memory-proposal-warning",
                    "ref": proposal_id,
                    "message": f"Pending proposal has {len(gate['warnings'])} promotion warning(s).",
                    "action": "Review warnings before approving the proposal.",
                }
            )

    _connector_escalation_issues(index, issues)

    health = {
        "generatedAt": _now(),
        "summary": {
            "memoryEntries": len(index.memory_entries),
            "approvedMemory": len(index.memory_entries),
            "pendingProposals": len([proposal for proposal in index.memory_proposals.values() if proposal.spec.status == "pending-review"]),
            "activeBindings": len([binding for binding in index.memory_bindings.values() if binding.spec.status == "active"]),
            "activeGrants": len([grant for grant in index.memory_grants.values() if grant.spec.status == "active" and _grant_effective_status(grant) == "active"]),
            "staleMemory": len([entry for entry in index.memory_entries.values() if entry.spec.lifecycle == "stale"]),
            "conflictedMemory": len(
                [entry for entry in index.memory_entries.values() if entry.spec.lifecycle == "conflicted" or (entry.spec.lifecycle == "active" and bool(entry.spec.conflictsWith))]
            ),
            "sensitiveMemory": len(
                [entry for entry in index.memory_entries.values() if entry.spec.sensitivity in {"confidential", "secret"} or entry.spec.lifecycle == "redacted"]
            ),
            "orphanedBindings": len([binding for binding in index.memory_bindings.values() if _binding_has_orphan(index, binding)]),
            "orphanedGrants": len([grant for grant in index.memory_grants.values() if _grant_has_orphan(index, grant)]),
            "expiredGrants": len([grant for grant in index.memory_grants.values() if _grant_effective_status(grant) == "expired"]),
            "issues": len(issues),
            "warnings": len([issue for issue in issues if issue["severity"] == "warning"]),
            "errors": len([issue for issue in issues if issue["severity"] == "error"]),
        },
        "issues": issues,
    }
    return KnowledgeHealthRecord.model_validate(health).model_dump(mode="json")


def _connector_escalation_issues(index: WorkspaceIndex, issues: list[dict[str, Any]]) -> None:
    escalation_set = connector_failure_escalation_candidates(index)
    for candidate in escalation_set["candidates"]:
        spec = candidate["spec"]
        evidence_count = int(spec.get("evidenceCount") or 0)
        if spec.get("existingReviewRequest"):
            _issue(
                issues,
                "warning",
                "connector-failure-review-open",
                str(spec["existingReviewRequest"]),
                f"Connector {spec.get('connector')} has an open failure review request backed by {evidence_count} evidence item(s).",
                "Resolve the review request only after inspecting connector health, provider delivery evidence, and existing reminder messages.",
            )
        elif spec.get("routable"):
            _issue(
                issues,
                "warning",
                "connector-failure-escalation",
                candidate["id"],
                f"Connector {spec.get('connector')} has repeated failure evidence and can be escalated for review.",
                "Route a connector failure review request or inspect the Project/Employee connector escalation projection.",
            )


def _memory_entry_issues(index: WorkspaceIndex, entry_id: str, entry: Any, issues: list[dict[str, Any]]) -> None:
    if entry.spec.lifecycle == "stale":
        _issue(
            issues,
            "warning",
            "memory-status",
            entry_id,
            "Memory entry is marked stale and must not be injected without re-verification.",
            "Re-verify the memory through review before restoring active context injection.",
        )
    elif entry.spec.lifecycle == "conflicted":
        _issue(
            issues,
            "error",
            "memory-conflict",
            entry_id,
            "Memory entry is marked conflicted.",
            "Resolve conflicts against canonical docs or superseding memory before context injection.",
        )
    elif entry.spec.lifecycle in {"deprecated", "archived"}:
        _issue(
            issues,
            "info",
            "memory-lifecycle",
            entry_id,
            f"Memory entry is {entry.spec.lifecycle} and should remain out of active context.",
            "Keep it for audit only or supersede it with an active entry.",
        )
    elif entry.spec.lifecycle == "redacted":
        _issue(
            issues,
            "warning",
            "memory-redacted",
            entry_id,
            "Memory entry is redacted.",
            "Expose metadata only and ensure content is not searchable or injected.",
        )
    elif entry.spec.lifecycle != "active":
        _issue(
            issues,
            "warning",
            "memory-lifecycle",
            entry_id,
            f"Memory entry lifecycle is {entry.spec.lifecycle!r}, not active.",
            "Promote through memory review or keep it out of context.",
        )

    lineage = entry.spec.lineage
    if entry.spec.store not in index.memory_stores:
        _issue(issues, "error", "memory-store", entry_id, f"Memory entry store {entry.spec.store} is missing.", "Restore the store or rebind the memory.")

    if lineage.sourceRun and lineage.sourceRun not in index.runs:
        _issue(
            issues,
            "warning",
            "memory-source",
            entry_id,
            f"Memory sourceRun {lineage.sourceRun} is missing.",
            "Restore the source run or mark the memory stale.",
        )
    elif not (entry.spec.source or lineage.sourceRun or lineage.sourceTask):
        _issue(
            issues,
            "warning",
            "memory-source",
            entry_id,
            "Memory entry has no source, sourceRun, or sourceTask.",
            "Trace this memory to a document, task, run, or reviewed external note.",
        )

    evidence = list(dict.fromkeys([*entry.spec.evidence, *lineage.evidence]))
    if not evidence:
        _issue(issues, "warning", "memory-evidence", entry_id, "Memory entry has no evidence paths.", "Add evidence or keep it out of context.")
    else:
        missing = [item for item in evidence if not item.startswith(("http://", "https://")) and not (index.workspace_root / item).exists()]
        if missing:
            _issue(
                issues,
                "warning",
                "memory-evidence",
                entry_id,
                "Memory evidence path(s) are missing: " + ", ".join(missing[:5]),
                "Fix evidence paths or mark the memory stale.",
            )

    confidence = entry.spec.confidence
    if confidence is None:
        _issue(issues, "warning", "memory-confidence", entry_id, "Memory entry has no confidence score.", "Add confidence during review.")
    elif confidence < STRONG_CONFIDENCE:
        _issue(
            issues,
            "warning",
            "memory-confidence",
            entry_id,
            f"Memory confidence {confidence:.2f} is below {STRONG_CONFIDENCE:.2f}.",
            "Re-review the memory before injecting it into future context.",
        )

    last_verified = _parse_time(entry.spec.lastVerifiedAt)
    if not last_verified:
        _issue(issues, "warning", "memory-freshness", entry_id, "Memory entry has no lastVerifiedAt.", "Verify the memory against current docs/code.")
    elif datetime.now().astimezone() > last_verified + timedelta(days=STALE_AFTER_DAYS):
        _issue(
            issues,
            "warning",
            "memory-freshness",
            entry_id,
            f"Memory entry has not been verified for more than {STALE_AFTER_DAYS} days.",
            "Re-verify or mark stale.",
        )

    if entry.spec.sensitivity == "secret" and entry.spec.visibility in {"public", "organization"}:
        _issue(
            issues,
            "error",
            "memory-acl",
            entry_id,
            "Secret memory has overly broad visibility.",
            "Redact it or restrict visibility and ACL before any global projection.",
        )
    elif entry.spec.sensitivity in {"confidential", "secret"} and entry.spec.lifecycle == "active":
        _issue(
            issues,
            "warning",
            "memory-sensitive",
            entry_id,
            f"Active memory is marked {entry.spec.sensitivity}.",
            "Verify ACL, bindings, and grants before exposing it through Project or Employee views.",
        )

    if entry.spec.conflictsWith and entry.spec.lifecycle == "active":
        _issue(
            issues,
            "warning",
            "memory-conflict-link",
            entry_id,
            "Active memory declares conflictsWith entries.",
            "Resolve or mark conflicted before injection.",
        )

    sensitive = _sensitive_hits(entry.spec.title, entry.spec.content)
    if sensitive:
        _issue(
            issues,
            "warning",
            "memory-sensitive-topic",
            entry_id,
            "Memory mentions sensitive topic(s): " + ", ".join(sensitive),
            "Check against canonical docs before trusting this memory.",
        )


def _memory_binding_issues(index: WorkspaceIndex, binding_id: str, binding: Any, issues: list[dict[str, Any]]) -> None:
    if binding.spec.status in {"revoked", "archived"}:
        return
    if not (binding.spec.store or binding.spec.entry or binding.spec.collectionPath):
        _issue(
            issues,
            "warning",
            "memory-binding-empty",
            binding_id,
            "Memory binding has no store, entry, or collectionPath source.",
            "Attach a store or entry, or archive the binding.",
        )
    if binding.spec.store and binding.spec.store not in index.memory_stores:
        _issue(
            issues,
            "error",
            "memory-binding-orphan-store",
            binding_id,
            f"Memory binding references missing store {binding.spec.store}.",
            "Restore the store or archive the binding.",
        )
    if binding.spec.entry and binding.spec.entry not in index.memory_entries:
        _issue(
            issues,
            "error",
            "memory-binding-orphan-entry",
            binding_id,
            f"Memory binding references missing entry {binding.spec.entry}.",
            "Restore the entry or archive the binding.",
        )
    if not _binding_target_exists(index, binding):
        _issue(
            issues,
            "error",
            "memory-binding-orphan-target",
            binding_id,
            f"Memory binding target {binding.spec.targetType}:{binding.spec.targetId} does not exist.",
            "Restore the target object or archive the binding.",
        )
    if binding.spec.entry:
        entry = index.memory_entries.get(binding.spec.entry)
        if entry and entry.spec.sensitivity in {"confidential", "secret"} and "inject" in binding.spec.access:
            _issue(
                issues,
                "warning",
                "memory-binding-sensitive",
                binding_id,
                f"Memory binding injects {entry.spec.sensitivity} memory {entry.object_id}.",
                "Review ACL and target scope before keeping this binding active.",
            )


def _memory_grant_issues(index: WorkspaceIndex, grant_id: str, grant: Any, issues: list[dict[str, Any]]) -> None:
    effective_status = _grant_effective_status(grant)
    if grant.spec.granteeMember not in index.members:
        _issue(
            issues,
            "error",
            "memory-grant-orphan-grantee",
            grant_id,
            f"Memory grant grantee {grant.spec.granteeMember} does not exist.",
            "Restore the member or revoke the grant.",
        )
    if grant.spec.grantorMember and grant.spec.grantorMember not in index.members:
        _issue(
            issues,
            "warning",
            "memory-grant-orphan-grantor",
            grant_id,
            f"Memory grant grantor {grant.spec.grantorMember} does not exist.",
            "Restore the grantor member or record a reviewed replacement grant.",
        )
    if grant.spec.task and grant.spec.task not in index.tasks:
        _issue(
            issues,
            "warning",
            "memory-grant-orphan-task",
            grant_id,
            f"Memory grant task {grant.spec.task} does not exist.",
            "Revoke the task-scoped grant or restore the task.",
        )
    if grant.spec.run and grant.spec.run not in index.runs:
        _issue(
            issues,
            "warning",
            "memory-grant-orphan-run",
            grant_id,
            f"Memory grant run {grant.spec.run} does not exist.",
            "Revoke the run-scoped grant or restore the run.",
        )
    for store_id in grant.spec.stores:
        if store_id not in index.memory_stores:
            _issue(
                issues,
                "error",
                "memory-grant-orphan-store",
                grant_id,
                f"Memory grant references missing store {store_id}.",
                "Restore the store or revoke the grant.",
            )
    for entry_id in grant.spec.entries:
        entry = index.memory_entries.get(entry_id)
        if not entry:
            _issue(
                issues,
                "error",
                "memory-grant-orphan-entry",
                grant_id,
                f"Memory grant references missing entry {entry_id}.",
                "Restore the entry or revoke the grant.",
            )
            continue
        if entry.spec.sensitivity in {"confidential", "secret"} and "inject" in grant.spec.access:
            _issue(
                issues,
                "warning",
                "memory-grant-sensitive",
                grant_id,
                f"Memory grant injects {entry.spec.sensitivity} memory {entry.object_id}.",
                "Review ACL and expiry before using this grant for context injection.",
            )
    if effective_status == "expired":
        _issue(
            issues,
            "warning",
            "memory-grant-expired",
            grant_id,
            f"Memory grant is effectively expired at {grant.spec.expiresAt or 'unknown time'}.",
            "Revoke it or issue a fresh reviewed grant before context injection.",
        )
    elif effective_status == "invalid":
        _issue(
            issues,
            "error",
            "memory-grant-invalid-expiry",
            grant_id,
            f"Memory grant has invalid expiresAt value {grant.spec.expiresAt!r}.",
            "Fix the timestamp or revoke the grant; invalid expiry is treated as non-injectable.",
        )


def _issue(issues: list[dict[str, Any]], severity: str, kind: str, ref: str, message: str, action: str) -> None:
    issues.append({"severity": severity, "kind": kind, "ref": ref, "message": message, "action": action})


def _sensitive_hits(title: str, content: str) -> list[str]:
    text = f"{title}\n{content}".lower()
    return sorted(term for term in SENSITIVE_TERMS if term in text)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _binding_has_orphan(index: WorkspaceIndex, binding: Any) -> bool:
    if binding.spec.status in {"revoked", "archived"}:
        return False
    return bool(
        (binding.spec.store and binding.spec.store not in index.memory_stores)
        or (binding.spec.entry and binding.spec.entry not in index.memory_entries)
        or not _binding_target_exists(index, binding)
    )


def _grant_has_orphan(index: WorkspaceIndex, grant: Any) -> bool:
    return bool(
        grant.spec.granteeMember not in index.members
        or (grant.spec.grantorMember and grant.spec.grantorMember not in index.members)
        or (grant.spec.task and grant.spec.task not in index.tasks)
        or (grant.spec.run and grant.spec.run not in index.runs)
        or any(store_id not in index.memory_stores for store_id in grant.spec.stores)
        or any(entry_id not in index.memory_entries for entry_id in grant.spec.entries)
    )


def _binding_target_exists(index: WorkspaceIndex, binding: Any) -> bool:
    target = binding.spec.targetId
    if binding.spec.targetType == "project":
        return target == index.project.object_id
    if binding.spec.targetType == "member":
        return target in index.members
    if binding.spec.targetType == "assignment":
        return target in index.assignments
    if binding.spec.targetType == "task":
        return target in index.tasks
    if binding.spec.targetType in {"run", "context-capsule"}:
        return target in index.runs
    if binding.spec.targetType == "team":
        return target in index.teams
    return False


def _grant_effective_status(grant: Any) -> str:
    if grant.spec.status in {"expired", "revoked"}:
        return grant.spec.status
    if not grant.spec.expiresAt:
        return "active"
    parsed = _parse_time(grant.spec.expiresAt)
    if parsed is None:
        return "invalid"
    return "expired" if datetime.now().astimezone() >= parsed else "active"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
