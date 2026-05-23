from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re
import subprocess

from .artifacts import record_artifact_manifest
from .io import read_jsonl, read_text_if_exists, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .run_events import append_run_event_record
from .permissions import explain_effective_permissions
from .worker_authorization import validate_managed_worktree
from .worker_state import touch_worker_heartbeat


@dataclass(frozen=True)
class VerificationCommandResult:
    index: int
    command: str
    returncode: int | None
    timedOut: bool
    durationSeconds: float
    stdout: str
    stderr: str
    permissionDecision: dict[str, Any] | None = None


def run_verification_commands(
    workspace_path: str | Path,
    run_id: str,
    *,
    worktree: str | Path,
    commands: list[str],
    timeout_seconds: int = 120,
) -> list[VerificationCommandResult]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    normalized = [command.strip() for command in commands if command.strip()]
    if not normalized:
        return []

    worktree_path = Path(worktree).expanduser().resolve()
    if not worktree_path.exists() or not worktree_path.is_dir():
        raise ValueError(f"worktree does not exist: {worktree_path}")
    run_data = index.runs[run_id].model_dump(mode="json").get("spec", {})
    worker = run_data.get("worker") if isinstance(run_data.get("worker"), dict) else {}
    if run_data.get("worktree") or worker.get("worktree"):
        violations = validate_managed_worktree(index, run_id, worktree_path)
        if violations:
            raise ValueError("unsafe verification worktree: " + "; ".join(violations))

    run_dir = index.workspace_root / "runs" / run_id
    test_log_path = run_dir / "test.log"
    command_log_path = run_dir / "command_results.jsonl"

    results: list[VerificationCommandResult] = []
    previous_log = read_text_if_exists(test_log_path) or ""
    for idx, command in enumerate(normalized, start=1):
        touch_worker_heartbeat(workspace_path, run_id, stage="testing")
        command_violation = _command_policy_violation(command)
        permission_decision = _command_permission_decision(index, run_id, command)
        permission_violation = _permission_violation_message(permission_decision)
        if command_violation or permission_violation:
            violation = command_violation or permission_violation or "command blocked"
            result = VerificationCommandResult(
                index=idx,
                command=command,
                returncode=126,
                timedOut=False,
                durationSeconds=0.0,
                stdout="",
                stderr=violation,
                permissionDecision=permission_decision,
            )
            results.append(result)
            _append_command_jsonl(command_log_path, result)
            previous_log = _append_test_log(previous_log, result)
            _append_event(
                index.workspace_root,
                run_id,
                {
                    "type": "command.blocked",
                    "index": idx,
                    "command": command,
                    "reason": violation,
                    "permissionDecision": permission_decision,
                    "log": f"runs/{run_id}/test.log",
                },
            )
            continue
        _append_event(index.workspace_root, run_id, {"type": "command.started", "index": idx, "command": command})
        start = datetime.now().astimezone()
        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            finished = datetime.now().astimezone()
            result = VerificationCommandResult(
                index=idx,
                command=command,
                returncode=completed.returncode,
                timedOut=False,
                durationSeconds=(finished - start).total_seconds(),
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            finished = datetime.now().astimezone()
            result = VerificationCommandResult(
                index=idx,
                command=command,
                returncode=None,
                timedOut=True,
                durationSeconds=(finished - start).total_seconds(),
                stdout=_decode_timeout_stream(exc.stdout),
                stderr=_decode_timeout_stream(exc.stderr),
            )
        results.append(result)
        _append_command_jsonl(command_log_path, result)
        previous_log = _append_test_log(previous_log, result)
        event_type = "command.timeout" if result.timedOut else "command.completed"
        _append_event(
            index.workspace_root,
            run_id,
            {
                "type": event_type,
                "index": idx,
                "command": command,
                "returncode": result.returncode,
                "timedOut": result.timedOut,
                "durationSeconds": round(result.durationSeconds, 3),
                "log": f"runs/{run_id}/test.log",
            },
        )
    write_text(test_log_path, previous_log)
    test_uri = f"runs/{run_id}/test.log"
    command_uri = f"runs/{run_id}/command_results.jsonl"
    test_manifest = record_artifact_manifest(index.workspace_root, run_id, "test_log", test_uri, source_id="verification")
    command_manifest = record_artifact_manifest(index.workspace_root, run_id, "command_log", command_uri, source_id="verification")
    _record_output(index.workspace_root, run_id, {"type": "test_log", "path": test_uri, "artifactManifest": test_manifest})
    _record_output(index.workspace_root, run_id, {"type": "command_log", "path": command_uri, "artifactManifest": command_manifest})
    return results


def _command_permission_decision(index: Any, run_id: str, command: str) -> dict[str, Any] | None:
    run = index.runs[run_id]
    if run.spec.mode not in {"managed_llm", "service"}:
        return None
    decision = explain_effective_permissions(
        index,
        member=run.spec.member,
        project=run.spec.project,
        assignment=run.spec.assignment,
        action={"tool": "Bash", "command": command},
        non_interactive=True,
    )
    return {
        "member": decision.get("member"),
        "memberKind": decision.get("memberKind"),
        "project": decision.get("project"),
        "assignment": decision.get("assignment"),
        "action": decision.get("normalizedAction"),
        "decision": decision.get("decision"),
        "reason": decision.get("reason"),
        "selectedPolicyIds": decision.get("selectedPolicyIds", []),
        "matchedRules": decision.get("matchedRules", []),
        "blockers": decision.get("blockers", []),
        "warnings": decision.get("warnings", []),
    }


def _permission_violation_message(decision: dict[str, Any] | None) -> str | None:
    if decision is None:
        return None
    if decision["decision"] == "allow" and not decision["blockers"]:
        return None
    return f"command denied by effective permissions: {decision['reason']}"


def has_verification_failure(results: list[VerificationCommandResult]) -> bool:
    return any(result.timedOut or result.returncode not in {0, None} for result in results)


def _command_policy_violation(command: str) -> str | None:
    lowered = command.lower()
    patterns = [
        (r"(^|[;&|]\s*)sudo(\s|$)", "sudo is not allowed in worker verification commands"),
        (r"\brm\s+-[^\n;]*r[^\n;]*f\s+/", "destructive root removal is not allowed"),
        (r"\bgit\s+push\b", "git push is not allowed in worker verification commands"),
        (r"\bgh\s+pr\s+merge\b", "PR merge is not allowed in worker verification commands"),
        (r"\bgit\s+reset\s+--hard\b", "git reset --hard is not allowed in worker verification commands"),
        (r"(^|[;&|]\s*)(env|printenv|set)(\s|$)", "environment dumps are not allowed in worker verification commands"),
        (r"(\btee\b|>|>>|\brm\b|\bmv\b|\bcp\b)[^\n;]*\.aiteamos(/|$)", ".aiteamos writes must go through workspace APIs"),
    ]
    for pattern, message in patterns:
        if re.search(pattern, lowered):
            return message
    return None


def _append_test_log(previous: str, result: VerificationCommandResult) -> str:
    status = "TIMEOUT" if result.timedOut else f"exit {result.returncode}"
    section = f"""

## Command {result.index}: {result.command}

Status: {status}
Duration: {result.durationSeconds:.3f}s

### stdout

```text
{result.stdout.rstrip()}
```

### stderr

```text
{result.stderr.rstrip()}
```
"""
    return previous.rstrip() + section + "\n"


def _append_command_jsonl(path: Path, result: VerificationCommandResult) -> None:
    lines = []
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {"ts": datetime.now().astimezone().isoformat(timespec="milliseconds"), **asdict(result)}
    lines.append(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    write_text(path, "\n".join(lines) + "\n")


def _append_event(workspace_root: Path, run_id: str, event: dict[str, Any]) -> None:
    append_run_event_record(workspace_root, run_id, event)


def _record_output(workspace_root: Path, run_id: str, output: dict[str, Any]) -> None:
    path = workspace_root / "runs" / run_id / "run.yaml"
    data = read_yaml(path)
    outputs = data.setdefault("spec", {}).setdefault("outputs", [])
    outputs[:] = [
        item
        for item in outputs
        if not (isinstance(item, dict) and item.get("type") == output.get("type") and item.get("path") == output.get("path"))
    ]
    outputs.append(output)
    write_yaml(path, data)


def _decode_timeout_stream(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
