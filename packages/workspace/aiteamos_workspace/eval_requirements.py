from __future__ import annotations

from typing import Any
import fnmatch

from .loader import WorkspaceIndex, load_workspace


def evaluate_run_eval_suite_requirements(
    workspace_or_index: str | WorkspaceIndex,
    run_id: str,
    *,
    changed_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    assignment = index.assignments.get(run.spec.assignment or "")
    if assignment is None:
        return []

    paths = _normalized_paths(changed_paths or [])
    statuses: list[dict[str, Any]] = []
    for requirement in assignment.spec.evalSuiteRequirements:
        requirement_paths = _normalized_paths(requirement.paths)
        matched_paths = _matched_paths(paths, requirement_paths)
        if paths and not matched_paths:
            statuses.append(
                {
                    "evalSuite": requirement.evalSuite,
                    "paths": requirement_paths,
                    "matchedPaths": [],
                    "threshold": requirement.minimumPassRate,
                    "status": "skip",
                    "message": f"EvalSuite {requirement.evalSuite} is not required for the changed path set.",
                }
            )
            continue
        if not paths and requirement_paths:
            statuses.append(
                {
                    "evalSuite": requirement.evalSuite,
                    "paths": requirement_paths,
                    "matchedPaths": [],
                    "threshold": requirement.minimumPassRate,
                    "status": "skip",
                    "message": f"EvalSuite {requirement.evalSuite} requires changed paths before it can be evaluated.",
                }
            )
            continue
        statuses.append(_evaluate_requirement(index, requirement, matched_paths or paths))
    return statuses


def blocking_eval_suite_requirement_statuses(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [status for status in statuses if status.get("status") == "fail"]


def planned_worker_changed_paths(run: Any) -> list[str]:
    payload = run.model_dump(mode="json") if hasattr(run, "model_dump") else {}
    spec = payload.get("spec", {})
    worker = spec.get("worker") if isinstance(spec.get("worker"), dict) else {}
    source_integration = spec.get("sourceIntegration") if isinstance(spec.get("sourceIntegration"), dict) else {}
    for key in ("changedPaths", "plannedChangedPaths", "targetPaths"):
        values = worker.get(key)
        if isinstance(values, list) and values:
            return _normalized_paths([str(value) for value in values])
    values = source_integration.get("changedPaths")
    if isinstance(values, list) and values:
        return _normalized_paths([str(value) for value in values])
    return []


def _evaluate_requirement(index: WorkspaceIndex, requirement: Any, matched_paths: list[str]) -> dict[str, Any]:
    suite = index.eval_suites.get(requirement.evalSuite)
    if suite is None:
        return {
            "evalSuite": requirement.evalSuite,
            "paths": _normalized_paths(requirement.paths),
            "matchedPaths": matched_paths,
            "threshold": requirement.minimumPassRate,
            "status": "fail",
            "message": f"EvalSuite requirement references missing suite {requirement.evalSuite}.",
        }

    threshold = requirement.minimumPassRate
    if threshold is None:
        threshold = suite.spec.policy.autoPromoteThreshold
    result_id, result = _latest_eval_result(index, requirement.evalSuite)
    if result is None:
        return {
            "evalSuite": requirement.evalSuite,
            "paths": _normalized_paths(requirement.paths),
            "matchedPaths": matched_paths,
            "threshold": threshold,
            "status": "fail",
            "message": f"EvalSuite {requirement.evalSuite} has no EvalResult for the matched changed paths.",
        }

    pass_rate = result.spec.passRate
    if result.spec.status != "pass" or pass_rate < threshold:
        return {
            "evalSuite": requirement.evalSuite,
            "paths": _normalized_paths(requirement.paths),
            "matchedPaths": matched_paths,
            "threshold": threshold,
            "lastResultId": result_id,
            "passRate": pass_rate,
            "status": "fail",
            "message": f"EvalSuite {requirement.evalSuite} latest result {result_id} is {result.spec.status} with pass rate {pass_rate:.2f}; required {threshold:.2f}.",
        }

    return {
        "evalSuite": requirement.evalSuite,
        "paths": _normalized_paths(requirement.paths),
        "matchedPaths": matched_paths,
        "threshold": threshold,
        "lastResultId": result_id,
        "passRate": pass_rate,
        "status": "pass",
        "message": f"EvalSuite {requirement.evalSuite} latest result {result_id} passed with rate {pass_rate:.2f}.",
    }


def _latest_eval_result(index: WorkspaceIndex, suite_id: str) -> tuple[str | None, Any | None]:
    candidates = [
        (result_id, result)
        for result_id, result in index.eval_results.items()
        if result.spec.evalSuite == suite_id
    ]
    if not candidates:
        return None, None
    return sorted(candidates, key=lambda item: (item[1].spec.evaluatedAt or item[1].metadata.createdAt or "", item[0]))[-1]


def _matched_paths(changed_paths: list[str], requirement_paths: list[str]) -> list[str]:
    if not changed_paths:
        return []
    if not requirement_paths:
        return changed_paths
    return [
        path
        for path in changed_paths
        if any(fnmatch.fnmatch(path, pattern) for pattern in requirement_paths)
    ]


def _normalized_paths(paths: list[str]) -> list[str]:
    return [str(path).strip().lstrip("./") for path in paths if str(path).strip()]
