from __future__ import annotations

from pathlib import Path
from typing import Any
import importlib.util
import os
import shutil
import subprocess

from aiteamos_schema import ModelProfile

from .eval_requirements import evaluate_run_eval_suite_requirements, planned_worker_changed_paths
from .loader import WorkspaceIndex, load_workspace
from .locks import lock_status
from .model_policy import evaluate_model_policy, estimate_tokens, resolve_run_model_profile
from .worker_authorization import evaluate_worker_authorization
from .worker_state import ACTIVE_WORKER_STATUSES


MANAGED_WORKER_MODES = {"managed_llm"}


def evaluate_worker_readiness(workspace_or_index: str | Path | WorkspaceIndex, run_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "fail":
            blockers.append(message)
        elif status == "warn":
            warnings.append(message)

    if run.spec.status in ACTIVE_WORKER_STATUSES:
        check("run-status", "fail", f"Run is already active with status {run.spec.status}.")
    elif run.spec.status in {"DONE", "FINISHED"}:
        check("run-status", "warn", f"Run status is {run.spec.status}; starting a worker is usually unnecessary.")
    elif run.spec.status == "REVIEW":
        check("run-status", "warn", "Run is already in review; prefer review or changes-requested flow before restarting worker.")
    else:
        check("run-status", "pass", f"Run status {run.spec.status} is not active.")

    if run.spec.mode in MANAGED_WORKER_MODES:
        check("run-mode", "pass", f"Run mode {run.spec.mode} is eligible for managed worker execution.")
    else:
        check("run-mode", "fail", f"Run mode {run.spec.mode} is not a managed worker mode; use assisted/manual ingest instead.")

    lock = lock_status(index.workspace_root, f"run-{run_id}")
    if lock.get("held"):
        if lock.get("pidAlive") is False:
            check("worker-lock", "fail", "Worker lock is held by a dead PID; clear the stale lock before starting.")
        else:
            check("worker-lock", "fail", "Worker lock is already held; another worker may be running.")
    else:
        check("worker-lock", "pass", "No worker lock is held for this run.")

    if run.spec.task not in index.tasks:
        check("task", "fail", f"Run references missing task {run.spec.task}.")
    else:
        check("task", "pass", f"Task {run.spec.task} exists.")

    member = index.members.get(run.spec.member)
    if member is None:
        check("member", "fail", f"Run references missing TeamMember {run.spec.member}.")
    else:
        check("member", "pass", f"TeamMember {run.spec.member} exists with kind {member.spec.kind}.")
        if run.spec.mode == "managed_llm" and member.spec.kind != "digital":
            check("run-mode-member-kind", "fail", f"managed_llm worker runs require a digital member, but {run.spec.member} is {member.spec.kind}.")
        elif run.spec.mode == "service" and member.spec.kind != "service":
            check("run-mode-member-kind", "fail", f"service worker runs require a service member, but {run.spec.member} is {member.spec.kind}.")
        elif run.spec.mode in MANAGED_WORKER_MODES:
            check("run-mode-member-kind", "pass", f"Run mode {run.spec.mode} matches member kind {member.spec.kind}.")
        profile = _execution_profile(index, run.spec.member, member.spec.kind)
        if member.spec.kind in {"digital", "hybrid", "service"} and profile is None:
            check("execution-profile", "fail", f"Member {run.spec.member} has no {member.spec.kind} execution/collaboration profile.")
        else:
            check("execution-profile", "pass", f"Execution/collaboration profile is available for {run.spec.member}.")

    assignment = index.assignments.get(run.spec.assignment or "")
    if assignment is None:
        check("assignment", "fail", "Run has no valid Assignment for project/module/feature scope.")
    else:
        if assignment.spec.member != run.spec.member:
            check("assignment", "fail", f"Assignment {assignment.object_id} belongs to {assignment.spec.member}, not {run.spec.member}.")
        elif assignment.spec.project != run.spec.project:
            check("assignment", "fail", f"Assignment {assignment.object_id} belongs to project {assignment.spec.project}, not {run.spec.project}.")
        elif not assignment.spec.scope.write:
            check("assignment-write-scope", "fail", f"Assignment {assignment.object_id} has no write scope for worker validation.")
        else:
            check("assignment", "pass", f"Assignment {assignment.object_id} scopes this run.")
            check("assignment-write-scope", "pass", "Assignment write scope is explicit.")

    if run.spec.contextCapsule and run_id in index.run_context_capsules:
        check("context-capsule", "pass", f"Context capsule {run.spec.contextCapsule} is available.")
    else:
        check("context-capsule", "fail", "Run has no built context capsule; rebuild context before starting worker.")

    profile = None
    profile_id, profile_source = resolve_run_model_profile(index, run)
    if not profile_id:
        if run.spec.mode == "managed_llm":
            check("model-profile", "fail", "Run has no model profile selected or resolvable from member/assignment defaults.")
        else:
            check("model-profile", "warn", "No model profile is selected; non-managed flows may be model-free.")
    else:
        profile = index.model_profiles.get(profile_id)
        if profile is None:
            check("model-profile", "fail", f"Model profile {profile_id} does not exist.")
        else:
            check("model-profile", "pass", f"Model profile {profile_id} resolves from {profile_source} to {profile.spec.provider}/{profile.spec.model}.")

    if profile is not None:
        _check_model_runtime(profile, check)
    _append_model_policy_checks(index, run_id, check)
    _append_worker_authorization_checks(index, run_id, check)
    eval_suite_requirements = _append_eval_suite_requirement_checks(index, run_id, check)

    _check_git_runtime(index, check)

    if run.spec.branch and run.spec.branch.name:
        check("branch", "pass", f"Worker branch is planned as {run.spec.branch.name}.")
    else:
        check("branch", "warn", "Run has no planned branch; worker will fall back to a generated branch name.")

    ready = not blockers
    return {
        "run": run_id,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "ready": ready,
        "status": "READY" if ready else "BLOCKED",
        "summary": "Worker can be started." if ready else f"Worker start is blocked: {blockers[0]}",
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "lock": lock,
        "evalSuiteRequirements": eval_suite_requirements,
    }


def evaluate_model_execution_readiness(workspace_or_index: str | Path | WorkspaceIndex, run_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "fail":
            blockers.append(message)
        elif status == "warn":
            warnings.append(message)

    if run.spec.status in ACTIVE_WORKER_STATUSES:
        check("run-status", "fail", f"Run is already active with status {run.spec.status}.")
    elif run.spec.status in {"DONE", "FINISHED"}:
        check("run-status", "warn", f"Run status is {run.spec.status}; model execution is usually unnecessary.")
    else:
        check("run-status", "pass", f"Run status {run.spec.status} can be evaluated for model execution.")

    if run.spec.mode == "managed_llm":
        check("run-mode", "pass", "Run mode managed_llm can invoke the model gateway.")
    else:
        check("run-mode", "fail", f"Run mode {run.spec.mode} cannot invoke the model gateway directly; use assisted/manual ingest or automation service flow.")

    member = index.members.get(run.spec.member)
    if member is None:
        check("member", "fail", f"Run references missing TeamMember {run.spec.member}.")
    elif run.spec.mode == "managed_llm" and member.spec.kind != "digital":
        check("run-mode-member-kind", "fail", f"managed_llm model execution requires a digital member, but {run.spec.member} is {member.spec.kind}.")
    else:
        check("member", "pass", f"TeamMember {run.spec.member} exists with kind {member.spec.kind}.")

    if run.spec.contextCapsule and run_id in index.run_context_capsules:
        check("context-capsule", "pass", f"Context capsule {run.spec.contextCapsule} is available.")
    else:
        check("context-capsule", "fail", "Run has no built context capsule; rebuild context before model execution.")

    profile = None
    profile_id, profile_source = resolve_run_model_profile(index, run)
    if not profile_id:
        if run.spec.mode == "managed_llm":
            check("model-profile", "fail", "Run has no model profile selected or resolvable from member/assignment defaults.")
        else:
            check("model-profile", "warn", "No model profile is selected; assisted/manual/service flows may be model-free.")
    else:
        profile = index.model_profiles.get(profile_id)
        if profile is None:
            check("model-profile", "fail", f"Model profile {profile_id} does not exist.")
        else:
            check("model-profile", "pass", f"Model profile {profile_id} resolves from {profile_source} to {profile.spec.provider}/{profile.spec.model}.")

    if profile is not None:
        _check_model_runtime(profile, check)
    _append_model_policy_checks(index, run_id, check)

    ready = not blockers
    return {
        "run": run_id,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "ready": ready,
        "status": "READY" if ready else "BLOCKED",
        "summary": "Managed model execution can be started." if ready else f"Managed model execution is blocked: {blockers[0]}",
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }


def evaluate_model_profile_readiness(workspace_or_index: str | Path | WorkspaceIndex, profile_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    profile = index.model_profiles.get(profile_id)
    if profile is None:
        return _blocked_profile_readiness(profile_id, f"Model profile {profile_id} does not exist.")
    return evaluate_model_profile_object_readiness(profile)


def evaluate_model_profile_payload_readiness(profile_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = ModelProfile.model_validate(profile_payload)
    except Exception as exc:
        profile_id = str(profile_payload.get("id") or profile_payload.get("metadata", {}).get("name") or "unknown")
        return _blocked_profile_readiness(profile_id, f"Model profile manifest is invalid: {exc}")
    return evaluate_model_profile_object_readiness(profile)


def evaluate_model_profile_object_readiness(profile: ModelProfile) -> dict[str, Any]:
    profile_id = profile.object_id
    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "fail":
            blockers.append(message)
        elif status == "warn":
            warnings.append(message)

    check("profile", "pass", f"Model profile {profile_id} is syntactically valid.")
    if "managed_llm" not in (profile.spec.capabilities or []) and not (profile.spec.provider.lower() == "local" and profile.spec.model == "manual"):
        check("capability", "warn", "Profile does not declare managed_llm capability; it may be intended for assisted use only.")
    else:
        check("capability", "pass", "Profile declares managed execution capability or is local/manual.")
    _check_model_runtime(profile, check)

    ready = not blockers
    return {
        "profile": profile_id,
        "ready": ready,
        "status": "READY" if ready else "BLOCKED",
        "summary": "Model profile runtime is ready." if ready else f"Model profile is blocked: {blockers[0]}",
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }


def _blocked_profile_readiness(profile_id: str, message: str) -> dict[str, Any]:
    return {
        "profile": profile_id,
        "ready": False,
        "status": "BLOCKED",
        "summary": f"Model profile is blocked: {message}",
        "blockers": [message],
        "warnings": [],
        "checks": [{"name": "profile", "status": "fail", "message": message}],
    }


def _append_model_policy_checks(index: WorkspaceIndex, run_id: str, check: Any) -> None:
    context = index.run_context_capsules.get(run_id) or ""
    decision = evaluate_model_policy(index, run_id, estimated_input_tokens=estimate_tokens(context))
    for item in decision["checks"]:
        check(item["name"], item["status"], item["message"])


def _append_worker_authorization_checks(index: WorkspaceIndex, run_id: str, check: Any) -> None:
    decision = evaluate_worker_authorization(index, run_id)
    for item in decision["checks"]:
        check(item["name"], item["status"], item["message"])


def _append_eval_suite_requirement_checks(index: WorkspaceIndex, run_id: str, check: Any) -> list[dict[str, Any]]:
    run = index.runs[run_id]
    statuses = evaluate_run_eval_suite_requirements(index, run_id, changed_paths=planned_worker_changed_paths(run))
    for status in statuses:
        if status["status"] == "skip":
            continue
        check("eval-suite-requirement", status["status"], status["message"])
    return statuses


def _check_model_runtime(profile: Any, check: Any) -> None:
    provider = profile.spec.provider.lower()
    gateway = (profile.spec.gateway or "").lower()
    if provider == "local" and profile.spec.model == "manual":
        check("model-runtime", "pass", "Local/manual profile does not require a provider call.")
        return

    if gateway == "litellm":
        if importlib.util.find_spec("litellm") is None:
            check("model-runtime", "fail", "LiteLLM gateway is selected but the litellm package is not installed.")
        else:
            check("model-runtime", "pass", "LiteLLM package is installed.")
    elif provider == "openai":
        check("model-runtime", "pass", "OpenAI Responses gateway is executable by the current worker.")
    else:
        check("model-runtime", "fail", f"Provider {profile.spec.provider} with gateway {profile.spec.gateway} is not executable by the current worker.")

    secret_env = profile.spec.secretEnv
    if provider == "openai" and not secret_env:
        secret_env = "OPENAI_API_KEY"
    if secret_env:
        if os.environ.get(secret_env):
            check("provider-secret", "pass", f"Required provider secret env {secret_env} is present.")
        else:
            check("provider-secret", "fail", f"Required provider secret env {secret_env} is missing.")


def _check_git_runtime(index: WorkspaceIndex, check: Any) -> None:
    if not shutil.which("git"):
        check("git", "fail", "git executable is not available on PATH.")
        return
    repo_path = _repository_path(index)
    if not repo_path.exists():
        check("git-repository", "fail", f"Source repository path does not exist: {repo_path}.")
        return
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        check("git-repository", "fail", f"Source repository is not a git repository: {repo_path}.")
        return
    check("git", "pass", "git is available and source repository is valid.")


def _repository_path(index: WorkspaceIndex) -> Path:
    repository = next(iter(index.repositories.values()), None)
    if repository and repository.spec.localPath:
        return Path(repository.spec.localPath).expanduser().resolve()
    return index.workspace_root.parent.resolve()


def _execution_profile(index: WorkspaceIndex, member_id: str | None, member_kind: str | None) -> Any | None:
    if not member_id or not member_kind:
        return None
    stores = {
        "digital": index.digital_execution_profiles,
        "human": index.human_collaboration_profiles,
        "hybrid": index.hybrid_execution_profiles,
        "service": index.service_account_profiles,
    }
    return stores.get(member_kind, {}).get(member_id)
