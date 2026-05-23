from __future__ import annotations

from pathlib import Path
from typing import Any

from .closeout import evaluate_run_closeout_gate
from .loader import WorkspaceIndex, load_workspace


ACTIVE_RUN_STATUSES = {"QUEUED", "RUNNING", "TESTING", "RECOVERING"}
RECOVERY_RUN_STATUSES = {"STALLED", "FAILED", "INTERRUPTED"}
TERMINAL_RUN_STATUSES = {"DONE", "FINISHED"}
MANAGED_RUN_MODES = {"managed_llm"}


def build_run_execution_plan(workspace_or_index: str | Path | WorkspaceIndex, run_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    run_dir = index.workspace_root / "runs" / run_id
    status = run.spec.status
    mode = run.spec.mode
    has_context = bool(index.run_context_capsules.get(run_id))
    has_journal = bool(index.run_journals.get(run_id))
    has_diff = (run_dir / "diff.patch").exists()
    has_test_log = (run_dir / "test.log").exists()
    has_model_output = (run_dir / "model_output.md").exists()
    has_worker_output = (run_dir / "worker_output.md").exists()
    has_review_target = bool(run.spec.reviewTarget)
    has_events = bool(index.run_events.get(run_id))
    has_model = bool(run.spec.modelProfile)
    has_memory_proposals = bool(run.spec.memoryProposals)

    blockers: list[str] = []
    warnings: list[str] = []
    recommended: list[str] = []
    actions = {
        "rebuildContext": False,
        "executeModel": False,
        "startWorker": False,
        "ingestAssisted": False,
        "inspectRecovery": False,
        "buildRetryPlan": False,
        "createReviewTarget": False,
        "recordHumanReview": False,
        "closeRun": False,
        "extractMemory": False,
        "refreshChecks": False,
    }

    if not has_context:
        blockers.append("Run has no context capsule.")
        actions["rebuildContext"] = True
        recommended.append("Rebuild the context capsule before execution.")

    if status in ACTIVE_RUN_STATUSES:
        recommended.append("Inspect worker events, heartbeat, command logs, and workspace health.")
    elif status in RECOVERY_RUN_STATUSES:
        actions["inspectRecovery"] = True
        actions["buildRetryPlan"] = True
        recommended.append("Inspect recovery, preserve artifacts, then move to review or build a retry plan.")
    elif status == "INGEST_INCOMPLETE":
        actions["ingestAssisted"] = True
        missing = run.spec.ingest.get("missing", []) if isinstance(run.spec.ingest, dict) else []
        for item in missing:
            blockers.append(f"Assisted ingest is missing {item}.")
        recommended.append("Complete assisted ingest with journal and a review target or diff.")
    elif status == "REVIEW":
        actions["recordHumanReview"] = True
        actions["extractMemory"] = has_journal and not has_memory_proposals
        closeout_gate = evaluate_run_closeout_gate(index, run_id)
        actions["closeRun"] = closeout_gate["readyForCloseout"]
        if run.spec.reviewTarget and run.spec.reviewTarget.type == "pull_request":
            actions["refreshChecks"] = True
        if not has_review_target and not has_diff:
            actions["createReviewTarget"] = True
            blockers.append("Review run has no review target or diff patch.")
        if not has_journal:
            warnings.append("Review run has no journal.")
        if closeout_gate["readyForCloseout"]:
            recommended.append("Close the run and mark the task DONE after approved human review.")
        else:
            recommended.append("Inspect the review gate, review target, journal, tests, and record human review.")
    elif status in TERMINAL_RUN_STATUSES:
        recommended.append("No execution action is required.")
    else:
        if mode in MANAGED_RUN_MODES:
            if not has_model:
                blockers.append(f"Run mode {mode} requires a model profile.")
            if has_context and has_model:
                actions["executeModel"] = True
                actions["startWorker"] = True
                recommended.append("Inspect the context capsule, then choose Execute Model or Start Worker.")
        else:
            actions["ingestAssisted"] = True
            if not has_model:
                warnings.append("Assisted mode has no model profile; execution must happen outside AITEAMOS.")
            if has_context:
                recommended.append("Execute from the context capsule in an IDE or external agent, then ingest the result.")

    if not has_events:
        warnings.append("Run has no event ledger entries.")
    if status == "REVIEW" and not has_test_log:
        warnings.append("Review run has no test log.")

    return {
        "run": run_id,
        "status": status,
        "mode": mode,
        "summary": _summary(status, mode, blockers, recommended),
        "blockers": blockers,
        "warnings": warnings,
        "recommendedActions": recommended,
        "actions": actions,
        "artifacts": {
            "contextCapsule": has_context,
            "journal": has_journal,
            "diffPatch": has_diff,
            "modelOutput": has_model_output,
            "workerOutput": has_worker_output,
            "testLog": has_test_log,
            "reviewTarget": has_review_target,
            "events": has_events,
            "memoryProposals": has_memory_proposals,
        },
    }


def _summary(status: str, mode: str, blockers: list[str], recommended: list[str]) -> str:
    if blockers:
        return f"{status} run needs attention: {blockers[0]}"
    if recommended:
        return recommended[0]
    return f"{status} run is ready for the next {mode} step."
