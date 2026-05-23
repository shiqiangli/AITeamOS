from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json

from ..audit import decision_audit_record
from ..git_provider import GitCliProvider, ReviewTargetRef
from ..gitops import changed_paths_from_diff, repository_ref
from ..io import read_text_if_exists
from ..loader import WorkspaceIndex, load_workspace
from ..locks import workspace_lock
from ..mutations import append_run_event, update_run
from ..permissions import connector_action, explain_effective_permissions
from ..review_gate import APPROVAL_VERDICTS
from .review_gate_bridge import (
    _policy_refs,
    _review_is_human,
    _source_integration_authority,
    _source_integration_decision_kind,
)


def request_run_provider_source_integration(
    workspace_path: str | Path,
    run_id: str,
    *,
    actor: str,
    reason: str | None = None,
) -> dict[str, Any]:
    initial_index = load_workspace(workspace_path)
    if run_id not in initial_index.runs:
        raise KeyError(f"unknown run {run_id}")
    if actor not in initial_index.members:
        raise KeyError(f"unknown provider source integration actor member {actor}")

    with workspace_lock(initial_index.workspace_root, f"provider-source-integration-{run_id}", {"run": run_id, "actor": actor}):
        index = load_workspace(workspace_path)
        run = index.runs[run_id]
        source_integration = run.spec.sourceIntegration if isinstance(run.spec.sourceIntegration, dict) else {}
        if source_integration.get("status") == "provider-integration-requested" and source_integration.get("strategy") == "provider-review-target":
            return run.model_dump(mode="json")
        if source_integration.get("status") == "integrated":
            raise ValueError("run source changes are already integrated")

        gate = _evaluate_provider_source_integration_gate(index, run_id, actor_member=actor)
        if gate["blockers"]:
            raise ValueError("run is not ready for provider source integration: " + "; ".join(gate["blockers"]))

        actor_kind = index.members[actor].spec.kind
        reason_text = reason or "request provider-hosted source integration after reviewed run closeout and passing provider checks"
        requested_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        audit = decision_audit_record(
            index,
            decision_kind=_source_integration_decision_kind(actor_kind),
            decision="provider-integration-requested",
            actor_member=actor,
            authority=_source_integration_authority(actor_kind),
            reason=reason_text,
            source="run-provider-source-integration",
            decided_at=requested_at,
            policy_refs=_policy_refs(gate["permissionDecisions"]),
            evidence=[
                {"kind": "run", "run": run_id},
                {"kind": "task", "task": run.spec.task},
                {"kind": "review", "review": (run.spec.closeout or {}).get("latestReview")},
                {"kind": "reviewTarget", "target": gate["reviewTarget"]},
                {"kind": "providerChecks", "status": (gate.get("providerChecks") or {}).get("status")},
            ],
            metadata={
                "strategy": "provider-review-target",
                "provider": gate["provider"],
                "checkStatus": (gate.get("providerChecks") or {}).get("status"),
            },
        )
        provider_record = {
            "status": "provider-integration-requested",
            "summary": gate["summary"],
            "requestedAt": requested_at,
            "requestedByMember": actor,
            "requestedByMemberKind": actor_kind,
            "reason": reason_text,
            "strategy": "provider-review-target",
            "provider": gate["provider"],
            "reviewTarget": gate["reviewTarget"],
            "providerChecks": gate.get("providerChecks"),
            "changedPaths": gate["changedPaths"],
            "blockers": gate["blockers"],
            "warnings": gate["warnings"],
            "gate": {
                "status": gate["status"],
                "summary": gate["summary"],
                "blockers": gate["blockers"],
                "warnings": gate["warnings"],
                "checks": gate["checks"],
            },
            "permissionDecisions": gate["permissionDecisions"],
            "decisionAudit": [audit],
        }
        update_run(workspace_path, run_id, {"sourceIntegration": provider_record})
        append_run_event(
            workspace_path,
            run_id,
            {
                "type": "run.provider_source_integration_requested",
                "actorMember": actor,
                "actorMemberKind": actor_kind,
                "provider": gate["provider"],
                "reviewTarget": gate["reviewTarget"],
                "checkStatus": (gate.get("providerChecks") or {}).get("status"),
                "changedPaths": gate["changedPaths"],
                "decisionAudit": audit,
            },
        )
        return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")

def execute_run_provider_source_integration(
    workspace_path: str | Path,
    run_id: str,
    *,
    actor: str,
    reason: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    initial_index = load_workspace(workspace_path)
    if run_id not in initial_index.runs:
        raise KeyError(f"unknown run {run_id}")
    if actor not in initial_index.members:
        raise KeyError(f"unknown provider source integration actor member {actor}")

    with workspace_lock(initial_index.workspace_root, f"provider-source-integration-execute-{run_id}", {"run": run_id, "actor": actor}):
        index = load_workspace(workspace_path)
        run = index.runs[run_id]
        source_integration = dict(run.spec.sourceIntegration) if isinstance(run.spec.sourceIntegration, dict) else {}
        if source_integration.get("status") != "provider-integration-requested" or source_integration.get("strategy") != "provider-review-target":
            raise ValueError("provider source integration execution requires an existing provider-integration-requested run state")

        gate = _evaluate_provider_source_integration_gate(index, run_id, actor_member=actor)
        actor_kind = index.members[actor].spec.kind
        attempted_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        provider = str(gate.get("provider") or "git-provider")
        reason_text = reason or (
            "dry-run provider source integration preflight" if dry_run else "execute provider source integration after reviewed request"
        )
        provider_result: dict[str, Any] | None = None
        error: str | None = None

        if gate["blockers"]:
            status = "blocked"
            summary = f"Provider source integration execution has {len(gate['blockers'])} blocker(s)."
        elif dry_run:
            status = "dry-run-passed"
            summary = "Provider source integration preflight passed; provider merge was not called."
        else:
            target = _review_target_ref(gate.get("reviewTarget"))
            try:
                provider_result = GitCliProvider().merge_pull_request(repository_ref(index), target, "merge")
                status = "succeeded"
                summary = "Provider source integration completed through the configured provider."
            except NotImplementedError as exc:
                status = "unsupported"
                error = str(exc)
                summary = "Provider merge execution is not configured; the reviewed provider request remains queued for manual execution or retry."
            except Exception as exc:  # pragma: no cover - provider adapters are intentionally pluggable.
                status = "failed"
                error = str(exc)
                summary = "Provider merge execution failed; the reviewed provider request remains queued for retry."

        execution_warnings = list(gate["warnings"])
        if provider_result and provider_result.get("sourceSynced") is False:
            source_sync_summary = str(provider_result.get("sourceSyncSummary") or "Provider merge succeeded but local source reconciliation did not complete.")
            execution_warnings.append(source_sync_summary)

        audit = decision_audit_record(
            index,
            decision_kind=_source_integration_decision_kind(actor_kind),
            decision=status,
            actor_member=actor,
            authority=_source_integration_authority(actor_kind),
            reason=reason_text,
            source="run-provider-source-integration-execution",
            decided_at=attempted_at,
            policy_refs=_policy_refs(gate["permissionDecisions"]),
            evidence=[
                {"kind": "run", "run": run_id},
                {"kind": "task", "task": run.spec.task},
                {"kind": "review", "review": (run.spec.closeout or {}).get("latestReview")},
                {"kind": "reviewTarget", "target": gate.get("reviewTarget")},
                {"kind": "providerChecks", "status": (gate.get("providerChecks") or {}).get("status")},
            ],
            metadata={
                "strategy": "provider-review-target-execution",
                "provider": provider,
                "dryRun": dry_run,
                "executionStatus": status,
            },
        )
        execution_record = {
            "run": run_id,
            "status": status,
            "summary": summary,
            "strategy": "provider-review-target-execution",
            "provider": provider,
            "dryRun": dry_run,
            "reviewTarget": gate.get("reviewTarget"),
            "providerChecks": gate.get("providerChecks"),
            "changedPaths": gate["changedPaths"],
            "blockers": gate["blockers"],
            "warnings": execution_warnings,
            "gate": {
                "status": gate["status"],
                "summary": gate["summary"],
                "blockers": gate["blockers"],
                "warnings": execution_warnings,
                "checks": gate["checks"],
            },
            "permissionDecisions": gate["permissionDecisions"],
            "decisionAudit": [audit],
            "providerResult": provider_result,
            "error": error,
            "attemptedAt": attempted_at,
            "attemptedByMember": actor,
            "attemptedByMemberKind": actor_kind,
        }
        history = [item for item in source_integration.get("providerExecutionHistory") or [] if isinstance(item, dict)]
        history.append(execution_record)
        source_integration.update(
            {
                "providerExecution": execution_record,
                "providerExecutionHistory": history[-10:],
                "lastProviderExecutionStatus": status,
                "lastProviderExecutionAt": attempted_at,
            }
        )
        if status == "succeeded":
            source_integration["status"] = "provider-integrated"
            source_integration["integratedAt"] = attempted_at
            source_integration["integratedByMember"] = actor
            source_integration["integratedByMemberKind"] = actor_kind

        update_run(workspace_path, run_id, {"sourceIntegration": source_integration})
        append_run_event(
            workspace_path,
            run_id,
            {
                "type": _provider_execution_event_type(status),
                "actorMember": actor,
                "actorMemberKind": actor_kind,
                "provider": provider,
                "dryRun": dry_run,
                "executionStatus": status,
                "reviewTarget": gate.get("reviewTarget"),
                "checkStatus": (gate.get("providerChecks") or {}).get("status"),
                "changedPaths": gate["changedPaths"],
                "decisionAudit": audit,
                **({"providerResult": provider_result} if provider_result else {}),
                **({"error": error} if error else {}),
            },
        )
        return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")

def _evaluate_provider_source_integration_gate(
    index: WorkspaceIndex,
    run_id: str,
    *,
    actor_member: str,
) -> dict[str, Any]:
    run = index.runs[run_id]
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    permission_decisions: list[dict[str, Any]] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "fail":
            blockers.append(message)
        elif status == "warn":
            warnings.append(message)

    if run.spec.status not in {"DONE", "FINISHED"}:
        check("run-status", "fail", f"Run must be DONE before provider source integration; current status is {run.spec.status}.")
    else:
        check("run-status", "pass", f"Run is {run.spec.status}.")

    closeout = run.spec.closeout if isinstance(run.spec.closeout, dict) else {}
    if closeout.get("status") != "closed":
        check("run-closeout", "fail", "Provider source integration requires an audited reviewed closeout.")
    else:
        check("run-closeout", "pass", "Run has an audited closeout record.")
        review_id = closeout.get("latestReview")
        review = index.reviews.get(str(review_id)) if review_id else None
        if not review:
            check("closeout-review", "fail", "Closeout does not reference a known Review.")
        elif review.spec.verdict.strip().lower() in APPROVAL_VERDICTS and _review_is_human(index, review):
            check("closeout-review", "pass", f"Closeout Review {review_id} is a human approval.")
        else:
            check("closeout-review", "fail", f"Closeout Review {review_id} is not an approved human review.")

    target = run.spec.reviewTarget.model_dump(mode="json", exclude_none=True) if run.spec.reviewTarget else None
    provider = _review_target_provider(target)
    if not target or target.get("type") != "pull_request":
        check("provider-review-target", "fail", "Provider source integration requires a pull_request review target.")
    elif not target.get("url") and not target.get("ref"):
        check("provider-review-target", "fail", "Provider source integration requires a pull request URL or ref.")
    else:
        check("provider-review-target", "pass", f"Review target is a {provider} pull request.")

    checks_payload = _read_run_checks(index, run_id)
    if checks_payload is None:
        check("provider-checks", "fail", "Provider review target checks must be refreshed before provider source integration.")
    elif checks_payload.get("status") != "passed":
        check("provider-checks", "fail", f"Provider checks must pass before provider source integration; current status is {checks_payload.get('status')}.")
    else:
        check("provider-checks", "pass", str(checks_payload.get("summary") or "Provider checks passed."))

    changed_paths = changed_paths_from_diff(read_text_if_exists(index.workspace_root / "runs" / run_id / "diff.patch") or "")
    if changed_paths:
        check("diff-patch", "pass", f"Run diff touches {len(changed_paths)} source path(s).")
    else:
        check("diff-patch", "warn", "No local diff.patch was found; provider merge request will rely on the pull request target.")

    permission_checks, permission_blockers, permission_warnings, permission_decisions = _provider_permission_checks(
        index,
        run_id,
        actor_member=actor_member,
        provider=provider,
    )
    checks.extend(permission_checks)
    blockers.extend(permission_blockers)
    warnings.extend(permission_warnings)
    permission_decisions.extend(permission_decisions)

    return {
        "run": run_id,
        "readyForProviderSourceIntegration": not blockers,
        "status": "READY_FOR_PROVIDER_SOURCE_INTEGRATION" if not blockers else "BLOCKED",
        "summary": "Provider review target can be queued for source integration." if not blockers else f"Provider source integration has {len(blockers)} blocker(s).",
        "provider": provider,
        "reviewTarget": target,
        "providerChecks": checks_payload,
        "changedPaths": changed_paths,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "permissionDecisions": permission_decisions,
    }

def _provider_permission_checks(
    index: WorkspaceIndex,
    run_id: str,
    *,
    actor_member: str,
    provider: str,
) -> tuple[list[dict[str, str]], list[str], list[str], list[dict[str, Any]]]:
    run = index.runs[run_id]
    if actor_member not in index.members:
        message = f"unknown provider source integration actor member {actor_member}"
        return ([{"name": "provider-source-integration-actor", "status": "fail", "message": message}], [message], [], [])
    actor_kind = index.members[actor_member].spec.kind
    decision = explain_effective_permissions(
        index,
        member=actor_member,
        project=run.spec.project,
        action=connector_action(provider, "merge", connector_type="git", connector_scope="pull_request"),
        non_interactive=actor_kind in {"digital", "service"},
    )
    summary = {"target": "provider-review-target", "provider": provider, **decision}
    decision_value = decision.get("decision")
    if decision_value == "deny" or decision.get("blockers"):
        message = f"actor {actor_member} cannot request {provider} provider integration: {decision.get('reason')}"
        return ([{"name": "provider-source-integration-permission", "status": "fail", "message": message}], [message], [], [summary])
    if decision_value == "ask":
        message = f"actor {actor_member} provider integration permission is ask; explicit request submission is the approval boundary."
        return ([{"name": "provider-source-integration-permission", "status": "warn", "message": message}], [], [message], [summary])
    return ([{"name": "provider-source-integration-permission", "status": "pass", "message": f"actor {actor_member} may request {provider} provider integration."}], [], [], [summary])

def _read_run_checks(index: WorkspaceIndex, run_id: str) -> dict[str, Any] | None:
    text = read_text_if_exists(index.workspace_root / "runs" / run_id / "checks.json")
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"status": "invalid", "summary": "Run checks.json is not valid JSON.", "checks": []}
    return payload if isinstance(payload, dict) else {"status": "invalid", "summary": "Run checks.json is not an object.", "checks": []}

def _review_target_provider(target: dict[str, Any] | None) -> str:
    if target and target.get("provider"):
        return str(target["provider"])
    url = str((target or {}).get("url") or "").lower()
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    return "git-provider"

def _review_target_ref(target: dict[str, Any] | None) -> ReviewTargetRef:
    payload = target if isinstance(target, dict) else {}
    return ReviewTargetRef(
        type=str(payload.get("type") or "pull_request"),
        ref=str(payload.get("ref") or ""),
        url=str(payload["url"]) if payload.get("url") else None,
        description=str(payload["description"]) if payload.get("description") else None,
        provider=str(payload["provider"]) if payload.get("provider") else None,
        fallback_reason=str(payload["fallbackReason"]) if payload.get("fallbackReason") else None,
    )

def _provider_execution_event_type(status: str) -> str:
    if status == "dry-run-passed":
        return "run.provider_source_integration_preflight_passed"
    if status == "blocked":
        return "run.provider_source_integration_execution_blocked"
    if status == "unsupported":
        return "run.provider_source_integration_execution_unsupported"
    if status == "succeeded":
        return "run.provider_source_integrated"
    return "run.provider_source_integration_execution_failed"
