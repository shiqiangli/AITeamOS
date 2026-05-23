from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import WorkspaceIndex, load_workspace


MIN_CONFIDENCE = 0.5
STRONG_CONFIDENCE = 0.75
REPAIR_CONFIDENCE = 0.8
SENSITIVE_TERMS = {
    "auto-merge",
    "deployment",
    "governance",
    "model policy",
    "permission",
    "production",
    "schema",
    "secret",
    "security",
    "worker sandbox",
}
EVAL_EVIDENCE_PREFIX = "eval://"


def evaluate_memory_promotion_gate(workspace_or_index: str | Path | WorkspaceIndex, proposal_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    proposal = index.memory_proposals[proposal_id]
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    eval_confidence_sources = memory_eval_confidence_sources(index, proposal_id)
    effective_confidence = _effective_confidence(proposal.spec.confidence, eval_confidence_sources)

    _check_status(proposal.spec.status, checks, blockers)
    _check_source_run(index, proposal_id, checks, blockers)
    _check_evidence(index, proposal_id, checks, blockers)
    _check_confidence(effective_confidence, checks, blockers, warnings)
    _check_eval_confidence_source(proposal.spec.confidence, eval_confidence_sources, checks, warnings)
    _check_content(proposal.spec.content, checks, blockers)
    _check_review_guidance(proposal.spec.reviewGuidance, checks, warnings)
    _check_sensitivity(proposal.spec.title, proposal.spec.content, proposal.spec.kind, checks, warnings)

    ready = not blockers
    return {
        "proposal": proposal_id,
        "readyForApproval": ready,
        "status": "READY_FOR_APPROVAL" if ready else "BLOCKED",
        "summary": "Memory proposal is ready for human approval." if ready else f"Memory proposal has {len(blockers)} blocker(s).",
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "confidence": proposal.spec.confidence,
        "effectiveConfidence": effective_confidence,
        "evalConfidenceSources": eval_confidence_sources,
    }


def memory_proposal_repair_hints(workspace_or_index: str | Path | WorkspaceIndex, proposal_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    proposal = index.memory_proposals[proposal_id]
    gate = evaluate_memory_promotion_gate(index, proposal_id)
    failed_checks = [check["name"] for check in gate["checks"] if check["status"] == "fail"]
    evidence = _suggest_evidence(index, proposal.spec.sourceRun)
    eval_evidence = memory_eval_evidence_refs(index, proposal_id)
    valid_existing_evidence = _valid_evidence(index, proposal.spec.evidence or [])
    suggested_evidence = _unique([*valid_existing_evidence, *evidence, *eval_evidence])
    eval_rates = [
        float(source["passRate"])
        for source in memory_eval_confidence_sources(index, proposal_id)
        if source.get("meetsThreshold")
    ]
    suggested_confidence = None
    if proposal.spec.confidence is None:
        suggested_confidence = max([REPAIR_CONFIDENCE, *eval_rates])
    elif "confidence" in failed_checks:
        suggested_confidence = max([float(proposal.spec.confidence or 0), REPAIR_CONFIDENCE, *eval_rates])
    suggested_review_guidance = None
    if not proposal.spec.reviewGuidance:
        suggested_review_guidance = "Human repaired proposal evidence/confidence before approval; verify against source run artifacts."
    can_apply = proposal.spec.status == "pending-review" and bool(
        ("evidence" in failed_checks and suggested_evidence)
        or suggested_confidence is not None
        or suggested_review_guidance
    )
    return {
        "proposal": proposal_id,
        "canApply": can_apply,
        "summary": "Repair hints are available." if can_apply else "No safe automatic repair hints are available.",
        "failedChecks": failed_checks,
        "suggestedEvidence": suggested_evidence if "evidence" in failed_checks else proposal.spec.evidence,
        "suggestedConfidence": suggested_confidence,
        "suggestedReviewGuidance": suggested_review_guidance,
        "blockers": gate["blockers"],
        "warnings": gate["warnings"],
    }


def memory_proposal_review_queue(workspace_or_index: str | Path | WorkspaceIndex) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    items = []
    counts = {"ready": 0, "ready-with-warnings": 0, "repairable": 0, "blocked": 0, "closed": 0}
    for proposal_id in sorted(index.memory_proposals):
        proposal = index.memory_proposals[proposal_id]
        gate = evaluate_memory_promotion_gate(index, proposal_id)
        repair = memory_proposal_repair_hints(index, proposal_id)
        queue_status = _proposal_queue_status(proposal.spec.status, gate, repair)
        counts[queue_status] += 1
        items.append(
            {
                "id": proposal_id,
                "queueStatus": queue_status,
                "member": proposal.spec.member,
                "assignment": proposal.spec.assignment,
                "project": proposal.spec.project,
                "sourceRun": proposal.spec.sourceRun,
                "sourceTask": proposal.spec.sourceTask,
                "kind": proposal.spec.kind,
                "title": proposal.spec.title,
                "proposalStatus": proposal.spec.status,
                "readyForApproval": gate["readyForApproval"],
                "canRepair": repair["canApply"],
                "blockerCount": len(gate["blockers"]),
                "warningCount": len(gate["warnings"]),
                "effectiveConfidence": gate["effectiveConfidence"],
                "evalConfidenceSources": gate["evalConfidenceSources"],
            }
        )
    order = {"ready": 0, "ready-with-warnings": 1, "repairable": 2, "blocked": 3, "closed": 4}
    items.sort(key=lambda item: (order[item["queueStatus"]], item["member"] or "", item["assignment"] or "", item["id"]))
    return {"summary": counts | {"total": len(items)}, "items": items}


def memory_eval_confidence_sources(workspace_or_index: str | Path | WorkspaceIndex, proposal_id: str) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    proposal = index.memory_proposals[proposal_id]
    latest_by_suite: dict[str, tuple[tuple[str, str], Any]] = {}
    for result_id, result in index.eval_results.items():
        suite = index.eval_suites.get(result.spec.evalSuite)
        if suite is None or not _eval_result_matches_proposal(suite, proposal):
            continue
        sort_key = (result.spec.evaluatedAt or result.metadata.createdAt or "", result_id)
        existing = latest_by_suite.get(result.spec.evalSuite)
        if existing is None or sort_key > existing[0]:
            latest_by_suite[result.spec.evalSuite] = (sort_key, result)
    sources: list[dict[str, Any]] = []
    for suite_id, (_sort_key, result) in sorted(latest_by_suite.items()):
        suite = index.eval_suites[suite_id]
        threshold = suite.spec.policy.autoPromoteThreshold if suite.spec.policy.autoPromoteThreshold is not None else STRONG_CONFIDENCE
        meets_threshold = result.spec.status in {"pass", "mixed"} and result.spec.passRate >= threshold
        sources.append(
            {
                "evalSuiteId": suite_id,
                "lastResultId": result.object_id,
                "status": result.spec.status,
                "passRate": result.spec.passRate,
                "threshold": threshold,
                "meetsThreshold": meets_threshold,
                "evidenceRef": format_eval_evidence_ref(suite_id, result.object_id),
            }
        )
    return sources


def memory_eval_evidence_refs(workspace_or_index: str | Path | WorkspaceIndex, proposal_id: str) -> list[str]:
    return [
        str(source["evidenceRef"])
        for source in memory_eval_confidence_sources(workspace_or_index, proposal_id)
        if source.get("meetsThreshold")
    ]


def memory_eval_evidence_records(workspace_or_index: str | Path | WorkspaceIndex, proposal_id: str) -> list[dict[str, Any]]:
    return [
        {
            "kind": "eval-suite-result",
            "evalSuiteId": source["evalSuiteId"],
            "lastResultId": source["lastResultId"],
            "passRate": source["passRate"],
            "threshold": source["threshold"],
        }
        for source in memory_eval_confidence_sources(workspace_or_index, proposal_id)
        if source.get("meetsThreshold")
    ]


def format_eval_evidence_ref(eval_suite_id: str, result_id: str) -> str:
    return f"{EVAL_EVIDENCE_PREFIX}{eval_suite_id}/{result_id}"


def _proposal_queue_status(status: str, gate: dict[str, Any], repair: dict[str, Any]) -> str:
    if status != "pending-review":
        return "closed"
    if gate["readyForApproval"] and gate["warnings"]:
        return "ready-with-warnings"
    if gate["readyForApproval"]:
        return "ready"
    if repair["canApply"]:
        return "repairable"
    return "blocked"


def _suggest_evidence(index: WorkspaceIndex, source_run: str | None) -> list[str]:
    if not source_run or source_run not in index.runs:
        return []
    run_dir = index.workspace_root / "runs" / source_run
    candidates = ["journal.md", "model_output.md", "worker_output.md", "test.log", "diff.patch", "events.jsonl"]
    return [f"runs/{source_run}/{name}" for name in candidates if (run_dir / name).exists()]


def _valid_evidence(index: WorkspaceIndex, evidence: list[str]) -> list[str]:
    valid = []
    for item in evidence:
        if (
            item.startswith(("http://", "https://"))
            or _is_valid_eval_evidence_ref(index, item)
            or (index.workspace_root / item).exists()
        ):
            valid.append(item)
    return valid


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _check_status(status: str, checks: list[dict[str, str]], blockers: list[str]) -> None:
    if status == "pending-review":
        checks.append({"name": "status", "status": "pass", "message": "Proposal is pending review."})
        return
    message = f"Proposal status is {status}; only pending-review proposals can be promoted."
    blockers.append(message)
    checks.append({"name": "status", "status": "fail", "message": message})


def _check_source_run(index: WorkspaceIndex, proposal_id: str, checks: list[dict[str, str]], blockers: list[str]) -> None:
    proposal = index.memory_proposals[proposal_id]
    source_run = proposal.spec.sourceRun
    if not source_run:
        message = "Proposal has no sourceRun."
        blockers.append(message)
        checks.append({"name": "source-run", "status": "fail", "message": message})
        return
    if source_run not in index.runs:
        message = f"Proposal sourceRun {source_run} does not exist in the workspace."
        blockers.append(message)
        checks.append({"name": "source-run", "status": "fail", "message": message})
        return
    checks.append({"name": "source-run", "status": "pass", "message": f"Source run {source_run} exists."})


def _check_evidence(index: WorkspaceIndex, proposal_id: str, checks: list[dict[str, str]], blockers: list[str]) -> None:
    proposal = index.memory_proposals[proposal_id]
    evidence = proposal.spec.evidence
    if not evidence:
        message = "Proposal has no evidence paths."
        blockers.append(message)
        checks.append({"name": "evidence", "status": "fail", "message": message})
        return
    missing = []
    for item in evidence:
        if item.startswith(("http://", "https://")):
            continue
        if _is_valid_eval_evidence_ref(index, item):
            continue
        path = index.workspace_root / item
        if not path.exists():
            missing.append(item)
    if missing:
        message = "Evidence path(s) are missing: " + ", ".join(missing[:5])
        blockers.append(message)
        checks.append({"name": "evidence", "status": "fail", "message": message})
        return
    checks.append({"name": "evidence", "status": "pass", "message": f"{len(evidence)} evidence item(s) recorded."})


def _effective_confidence(proposal_confidence: float | None, eval_sources: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    if proposal_confidence is not None:
        values.append(float(proposal_confidence))
    values.extend(float(source["passRate"]) for source in eval_sources if source.get("meetsThreshold"))
    return max(values) if values else None


def _check_confidence(
    confidence: float | None,
    checks: list[dict[str, str]],
    blockers: list[str],
    warnings: list[str],
) -> None:
    if confidence is None:
        message = "Proposal has no confidence score."
        blockers.append(message)
        checks.append({"name": "confidence", "status": "fail", "message": message})
        return
    if confidence < MIN_CONFIDENCE:
        message = f"Confidence {confidence:.2f} is below the minimum {MIN_CONFIDENCE:.2f}."
        blockers.append(message)
        checks.append({"name": "confidence", "status": "fail", "message": message})
        return
    if confidence < STRONG_CONFIDENCE:
        message = f"Confidence {confidence:.2f} is advisory; approve only after close human review."
        warnings.append(message)
        checks.append({"name": "confidence", "status": "warn", "message": message})
        return
    checks.append({"name": "confidence", "status": "pass", "message": f"Confidence {confidence:.2f} is recorded."})


def _check_eval_confidence_source(
    proposal_confidence: float | None,
    eval_sources: list[dict[str, Any]],
    checks: list[dict[str, str]],
    warnings: list[str],
) -> None:
    usable = [source for source in eval_sources if source.get("meetsThreshold")]
    if usable:
        best = max(usable, key=lambda source: float(source["passRate"]))
        checks.append(
            {
                "name": "eval-confidence-source",
                "status": "pass",
                "message": (
                    f"EvalSuite {best['evalSuiteId']} result {best['lastResultId']} "
                    f"contributes pass rate {float(best['passRate']):.2f}."
                ),
            }
        )
        return
    if eval_sources:
        warnings.append("EvalSuite results exist but no latest result meets its autoPromoteThreshold.")
        checks.append(
            {
                "name": "eval-confidence-source",
                "status": "warn",
                "message": "No EvalSuite result met its auto-promote threshold.",
            }
        )
        return
    if proposal_confidence is None:
        checks.append(
            {
                "name": "eval-confidence-source",
                "status": "fail",
                "message": "No proposal confidence or EvalSuite result pass rate is available.",
            }
        )
    else:
        checks.append(
            {
                "name": "eval-confidence-source",
                "status": "warn",
                "message": "No EvalSuite result pass rate is available; using proposal confidence only.",
            }
        )


def _eval_result_matches_proposal(suite: Any, proposal: Any) -> bool:
    if proposal.spec.project and suite.spec.project != proposal.spec.project:
        return False
    if proposal.spec.member and suite.spec.members and proposal.spec.member not in suite.spec.members:
        return False
    if proposal.spec.assignment and suite.spec.assignments and proposal.spec.assignment not in suite.spec.assignments:
        return False
    return True


def _is_valid_eval_evidence_ref(index: WorkspaceIndex, ref: str) -> bool:
    parsed = _parse_eval_evidence_ref(ref)
    if parsed is None:
        return False
    suite_id, result_id = parsed
    result = index.eval_results.get(result_id)
    return bool(result and suite_id in index.eval_suites and result.spec.evalSuite == suite_id)


def _parse_eval_evidence_ref(ref: str) -> tuple[str, str] | None:
    if not ref.startswith(EVAL_EVIDENCE_PREFIX):
        return None
    rest = ref[len(EVAL_EVIDENCE_PREFIX) :]
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _check_content(content: str, checks: list[dict[str, str]], blockers: list[str]) -> None:
    if len(content.strip()) < 24:
        message = "Proposal content is too short to become durable memory."
        blockers.append(message)
        checks.append({"name": "content", "status": "fail", "message": message})
        return
    checks.append({"name": "content", "status": "pass", "message": "Proposal content is non-empty."})


def _check_review_guidance(review_guidance: str | None, checks: list[dict[str, str]], warnings: list[str]) -> None:
    if review_guidance and review_guidance.strip():
        checks.append({"name": "review-guidance", "status": "pass", "message": "Review guidance is present."})
        return
    message = "No review guidance is recorded."
    warnings.append(message)
    checks.append({"name": "review-guidance", "status": "warn", "message": message})


def _check_sensitivity(
    title: str,
    content: str,
    kind: str,
    checks: list[dict[str, str]],
    warnings: list[str],
) -> None:
    text = f"{title}\n{content}".lower()
    hits = sorted(term for term in SENSITIVE_TERMS if term in text)
    if kind in {"decision", "mistake"}:
        warnings.append(f"{kind} memory should be checked against canonical docs before approval.")
    if hits:
        message = "Sensitive topic detected: " + ", ".join(hits)
        warnings.append(message)
        checks.append({"name": "sensitivity", "status": "warn", "message": message})
        return
    checks.append({"name": "sensitivity", "status": "pass", "message": "No sensitive governance/security terms detected."})
