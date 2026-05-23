from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from aiteamos_workspace import (
    append_run_event,
    evaluate_worker_authorization,
    evaluate_worker_readiness,
    execute_worker_run,
    load_workspace,
)
from aiteamos_workspace.loader import WorkspaceIndex


LOCAL_QUEUE_BACKEND = "file"
CONSUMABLE_RUN_STATUSES = {"READY"}


def shared_domain_imports() -> list[str]:
    from aiteamos_api.automation import trigger_automation as _trigger_automation
    from aiteamos_api.connector import check_connector_health as _check_connector_health
    from aiteamos_api.context import build_context_capsule as _build_context_capsule
    from aiteamos_api.git_activity import admit_local_git_activity_import as _admit_local_git_activity_import
    from aiteamos_api.memory import create_memory_store as _create_memory_store
    from aiteamos_api.permission import explain_effective_permissions as _explain_effective_permissions

    imported = {
        "aiteamos_api.context.build_context_capsule": _build_context_capsule,
        "aiteamos_api.memory.create_memory_store": _create_memory_store,
        "aiteamos_api.automation.trigger_automation": _trigger_automation,
        "aiteamos_api.permission.explain_effective_permissions": _explain_effective_permissions,
        "aiteamos_api.connector.check_connector_health": _check_connector_health,
        "aiteamos_api.git_activity.admit_local_git_activity_import": _admit_local_git_activity_import,
    }
    return list(imported)


def select_next_run(index: WorkspaceIndex, run_id: str | None = None) -> str | None:
    if run_id:
        if run_id not in index.runs:
            raise KeyError(f"unknown run {run_id}")
        return run_id

    candidates = [
        run
        for run in index.runs.values()
        if run.spec.mode == "managed_llm" and run.spec.status in CONSUMABLE_RUN_STATUSES
    ]
    candidates.sort(key=lambda run: (str(run.metadata.createdAt or ""), run.object_id))
    return candidates[0].object_id if candidates else None


def run_worker_once(
    workspace_path: str | Path,
    *,
    run_id: str | None = None,
    queue_backend: str = LOCAL_QUEUE_BACKEND,
    write_event: bool = False,
    execute: bool = False,
    create_pr: bool = False,
) -> dict[str, Any]:
    if queue_backend != LOCAL_QUEUE_BACKEND:
        raise ValueError(f"unsupported worker queue backend {queue_backend!r}; only {LOCAL_QUEUE_BACKEND!r} is available locally")

    workspace = Path(workspace_path).resolve()
    shared_imports = shared_domain_imports()
    index = load_workspace(workspace)
    selected_run = select_next_run(index, run_id=run_id)
    if selected_run is None:
        return worker_process_result(
            workspace=workspace,
            status="idle",
            summary="No consumable managed_llm Run is ready in the local workspace queue.",
            selected_run=None,
            shared_imports=shared_imports,
        )

    readiness = evaluate_worker_readiness(index, selected_run)
    authorization = evaluate_worker_authorization(index, selected_run)
    gates_ready = bool(readiness.get("ready") and authorization.get("ready"))

    if execute:
        if not gates_ready:
            if write_event:
                append_run_event(
                    workspace,
                    selected_run,
                    {
                        "type": "worker.queue.blocked",
                        "queueBackend": queue_backend,
                        "workerProcess": "aiteamos_worker",
                        "readinessStatus": readiness.get("status"),
                        "authorizationStatus": authorization.get("status"),
                    },
                )
            return worker_process_result(
                workspace=workspace,
                status="blocked",
                summary="Worker selected a Run, but readiness or authorization blocked execution.",
                selected_run=selected_run,
                shared_imports=shared_imports,
                readiness=readiness,
                authorization=authorization,
                event_written=write_event,
            )
        executed_run = execute_worker_run(workspace, selected_run, create_pr=create_pr)
        return worker_process_result(
            workspace=workspace,
            status="executed",
            summary="Worker executed the selected Run.",
            selected_run=selected_run,
            shared_imports=shared_imports,
            readiness=readiness,
            authorization=authorization,
            execution=executed_run,
        )

    if write_event:
        append_run_event(
            workspace,
            selected_run,
            {
                "type": "worker.queue.consumed" if gates_ready else "worker.queue.blocked",
                "queueBackend": queue_backend,
                "workerProcess": "aiteamos_worker",
                "execute": False,
                "readinessStatus": readiness.get("status"),
                "authorizationStatus": authorization.get("status"),
            },
        )

    return worker_process_result(
        workspace=workspace,
        status="consumed" if write_event and gates_ready else "blocked" if write_event else "dry-run",
        summary=(
            "Worker consumed the selected Run and recorded a queue event."
            if write_event and gates_ready
            else "Worker selected a Run, but readiness or authorization blocked consumption."
            if write_event
            else "Worker selected a Run without mutating the workspace."
        ),
        selected_run=selected_run,
        shared_imports=shared_imports,
        readiness=readiness,
        authorization=authorization,
        event_written=write_event,
    )


def worker_process_result(
    *,
    workspace: Path,
    status: str,
    summary: str,
    selected_run: str | None,
    shared_imports: list[str] | None = None,
    readiness: dict[str, Any] | None = None,
    authorization: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    event_written: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "process": "aiteamos_worker",
        "workspace": str(workspace),
        "queueBackend": LOCAL_QUEUE_BACKEND,
        "status": status,
        "summary": summary,
        "selectedRun": selected_run,
        "eventWritten": event_written,
        "sharedImports": shared_imports or [],
    }
    if readiness is not None:
        result["readiness"] = _summarize_gate(readiness)
    if authorization is not None:
        result["authorization"] = _summarize_gate(authorization)
    if execution is not None:
        result["execution"] = execution
    return result


def add_worker_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default=".aiteamos")
    parser.add_argument("--run", dest="run_id", default=None)
    parser.add_argument("--once", action="store_true", help="Poll once and exit. This is the default unless --watch is set.")
    parser.add_argument("--watch", action="store_true", help="Keep polling until interrupted.")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between polls when --watch is set.")
    parser.add_argument("--write-event", action="store_true", help="Record a worker.queue.* event in the selected Run ledger.")
    parser.add_argument("--execute", action="store_true", help="Execute the selected Run after readiness and authorization pass.")
    parser.add_argument("--create-pr", action="store_true", help="Ask the worker executor to create a PR after a diff is produced.")
    parser.add_argument("--fail-on-blocked", action="store_true", help="Return non-zero when a selected Run is blocked.")


def run_cli(args: argparse.Namespace) -> int:
    while True:
        result = run_worker_once(
            args.workspace,
            run_id=args.run_id,
            write_event=args.write_event,
            execute=args.execute,
            create_pr=args.create_pr,
        )
        print(json.dumps(result, sort_keys=True))
        if not args.watch:
            return 1 if args.fail_on_blocked and result["status"] == "blocked" else 0
        time.sleep(max(0.1, args.interval))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiteamos_worker")
    add_worker_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run_cli(args)
    except Exception as exc:
        print(json.dumps({"process": "aiteamos_worker", "status": "error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


def _summarize_gate(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": gate.get("status"),
        "ready": gate.get("ready"),
        "blockers": list(gate.get("blockers") or []),
        "warnings": list(gate.get("warnings") or []),
    }
