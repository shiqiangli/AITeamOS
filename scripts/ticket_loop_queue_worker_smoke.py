#!/usr/bin/env python3
"""Smoke the governed Ticket loop queue worker without adding a new runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
SMOKE_SCHEMA = "aiteamos.ticket_loop_queue_worker_smoke.v2"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic Ticket loop queue worker smoke.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--output", default="", help="Optional path to write the JSON result.")
    parser.add_argument("--skip-daemon", action="store_true", help="Only run the single-tick worker smoke.")
    parser.add_argument("--daemon-min-ticks", type=int, default=6, help="Minimum daemon ticks to observe.")
    parser.add_argument("--daemon-interval-seconds", type=float, default=0.1)
    parser.add_argument("--daemon-timeout-seconds", type=float, default=5.0)
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    try:
        payload = asyncio.run(
            run_smoke(
                workspace_root=workspace_root,
                include_daemon=not args.skip_daemon,
                daemon_min_ticks=max(1, args.daemon_min_ticks),
                daemon_interval_seconds=max(0.1, args.daemon_interval_seconds),
                daemon_timeout_seconds=max(0.1, args.daemon_timeout_seconds),
            )
        )
    except Exception as exc:
        payload = {
            "schema": SMOKE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "workspace_dir": str(workspace_root),
            "error": str(exc),
        }
    _write_output(payload, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


async def run_smoke(
    *,
    workspace_root: Path,
    include_daemon: bool = True,
    daemon_min_ticks: int = 6,
    daemon_interval_seconds: float = 0.05,
    daemon_timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    from aiteamos_api.read.asset_candidate_service import list_asset_candidates
    from aiteamos_api.read.ticket_loop_service import (
        TicketAutonomousLoopService,
        TicketLoopEnqueueRequest,
        TicketLoopQueueWorker,
        TicketLoopQueueWorkerControlRequest,
        enqueue_ticket_loop,
        list_ticket_loop_queue,
        ticket_loop_queue_status,
        ticket_loop_timeline,
    )
    from aiteamos_api.read.ticket_service import (
        TicketBackendSettingsUpdateRequest,
        TicketCreateRequest,
        create_ticket,
        update_ticket_backend_settings,
    )

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )
    workspace = workspace_root / ".aiteamos" if workspace_root.name != ".aiteamos" else workspace_root
    ticket = create_ticket(
        TicketCreateRequest(
            title="Queue worker smoke repeated failure retrospective",
            description="Short-lived worker smoke for repeated blocked Ticket loop queue work.",
            ticket_type="ops",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-worker-smoke",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    first = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="First blocked queue worker smoke run.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-worker-smoke-1"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue first blocked worker smoke run.",
        ),
        workspace_dir=workspace,
    )
    second = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Second blocked queue worker smoke run.",
            max_steps=1,
            priority=11,
            runtime_config={"loop_run_id": "ticket-loop-worker-smoke-2"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue second blocked worker smoke run.",
        ),
        workspace_dir=workspace,
    )

    before_status = ticket_loop_queue_status(workspace_dir=workspace)
    before_timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)
    worker = TicketLoopQueueWorker(
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=_BlockedDispatch(),  # type: ignore[arg-type]
        ),
    )
    worker_baseline = worker.status()
    tick = await worker.tick(
        TicketLoopQueueWorkerControlRequest(
            interval_seconds=5,
            max_items=2,
            reason="Run deterministic queue worker smoke tick.",
        )
    )
    after_queue = list_ticket_loop_queue(workspace_dir=workspace)
    after_status = ticket_loop_queue_status(workspace_dir=workspace)
    after_timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)
    candidates = [
        candidate
        for candidate in list_asset_candidates(workspace_dir=workspace_root, asset_type="failure_retrospective")
        if getattr(candidate, "scope_ref", "") == ticket.id
    ]
    retrospective = candidates[0] if candidates else None

    before_reliability = before_timeline.summary.queue_reliability
    after_reliability = after_timeline.summary.queue_reliability
    processed_statuses = [item.status for item in tick.pump.processed]
    policy_actions = tick.pump.policy_actions
    timeline_statuses = [item.status for item in after_timeline.items if item.status]
    failed_delta = after_status.failed_count - before_status.failed_count
    processed_delta = tick.status.total_processed - worker_baseline.total_processed
    policy_action_delta = tick.status.total_policy_actions - worker_baseline.total_policy_actions
    checks = [
        _check("before.queue_status", before_status.status, "queued"),
        _check("before.queue_reliability", before_reliability.status if before_reliability else "", "duplicate_queued"),
        _check_int("before.queued_count", before_status.queued_count, 2),
        _check("tick.status", tick.pump.status, "completed"),
        _check_list("tick.processed_statuses", processed_statuses, ["blocked", "blocked"]),
        _check_int("tick.policy_action_count", len(policy_actions), 1),
        _check("tick.policy_action_kind", policy_actions[0].kind if policy_actions else "", "failure_retrospective_candidate"),
        _check("after.queue_status", after_status.status, "needs_attention"),
        _check_int("after.failed_delta", failed_delta, 2),
        _check("after.queue_reliability", after_reliability.status if after_reliability else "", "error"),
        _check_contains("after.timeline_statuses", timeline_statuses, "blocked"),
        _check_present("asset_candidate.id", retrospective.id if retrospective is not None else ""),
        _check("asset_candidate.type", retrospective.asset_type if retrospective is not None else "", "failure_retrospective"),
        _check_list(
            "asset_candidate.queue_item_ids",
            _candidate_queue_item_ids(retrospective),
            [first.queue_id, second.queue_id],
        ),
        _check_int("worker.processed_delta", processed_delta, 2),
        _check_int("worker.policy_action_delta", policy_action_delta, 1),
    ]
    daemon_evidence: dict[str, Any] = {
        "status": "skipped",
        "checks": [],
        "summary": {"reason": "daemon smoke was disabled"},
    }
    if include_daemon:
        daemon_evidence = await _run_daemon_evidence(
            workspace=workspace,
            min_ticks=daemon_min_ticks,
            interval_seconds=daemon_interval_seconds,
            timeout_seconds=daemon_timeout_seconds,
        )
        checks.extend(daemon_evidence["checks"])
    passed = all(check["passed"] for check in checks)
    return {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "workspace_dir": str(workspace_root),
        "checks": checks,
        "daemon": daemon_evidence,
        "summary": {
            "ticket_id": ticket.id,
            "queue_ids": [first.queue_id, second.queue_id],
            "processed_statuses": processed_statuses,
            "policy_actions": [action.model_dump(mode="json") for action in policy_actions],
            "before_queue_status": before_status.model_dump(mode="json"),
            "after_queue_status": after_status.model_dump(mode="json"),
            "failed_delta": failed_delta,
            "after_queue_items": [
                {"queue_id": item.queue_id, "run_id": item.run_id, "status": item.status}
                for item in after_queue
            ],
            "after_reliability": after_reliability.model_dump(mode="json") if after_reliability is not None else {},
            "timeline_statuses": timeline_statuses,
            "asset_candidate_ids": [candidate.id for candidate in candidates],
            "worker_status": tick.status.model_dump(mode="json"),
            "worker_processed_delta": processed_delta,
            "worker_policy_action_delta": policy_action_delta,
            "daemon_status": daemon_evidence.get("status", "skipped"),
            "daemon": daemon_evidence.get("summary", {}),
        },
    }


class _BlockedDispatch:
    async def dispatch(self, request: Any) -> Any:
        from aiteamos_api.read.execution_contract import ExecutionResult

        return ExecutionResult(
            request_id=request.request_id,
            executor_id="universal_employee_agent",
            status="blocked",
            report="Provider is not configured for the deterministic queue worker smoke.",
            output_ticket_id=request.ticket_id,
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"lg-{request.request_id}",
            checkpoint_ref=f"langgraph:{request.request_id}",
            errors=[
                {
                    "reason": "provider_not_configured",
                    "detail": "Provider is not configured for the deterministic queue worker smoke.",
                }
            ],
            started_at="2026-06-20T00:00:00+00:00",
            finished_at="2026-06-20T00:00:01+00:00",
        )


class _CompletedDispatch:
    async def dispatch(self, request: Any) -> Any:
        from aiteamos_api.read.execution_contract import ExecutionResult

        return ExecutionResult(
            request_id=request.request_id,
            executor_id="universal_employee_agent",
            status="completed",
            report="Deterministic daemon worker smoke loop step completed.",
            output_ticket_id=request.ticket_id,
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"lg-{request.request_id}",
            checkpoint_ref=f"langgraph:{request.request_id}",
            started_at="2026-06-20T00:00:00+00:00",
            finished_at="2026-06-20T00:00:01+00:00",
        )


async def _run_daemon_evidence(
    *,
    workspace: Path,
    min_ticks: int,
    interval_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    from aiteamos_api.read.ticket_loop_service import (
        TicketAutonomousLoopService,
        TicketLoopEnqueueRequest,
        TicketLoopQueueWorker,
        TicketLoopQueueWorkerControlRequest,
        enqueue_ticket_loop,
        get_ticket_loop_run,
        list_ticket_loop_queue,
    )
    from aiteamos_api.read.ticket_service import TicketCreateRequest, create_ticket

    ticket = create_ticket(
        TicketCreateRequest(
            title="Queue worker smoke daemon run",
            description="Multi-tick daemon evidence for the governed Ticket loop queue worker.",
            ticket_type="ops",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-worker-daemon-smoke",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    enqueued = [
        enqueue_ticket_loop(
            ticket.id,
            TicketLoopEnqueueRequest(
                employee_id="alex",
                message=f"Daemon queue worker smoke run {index}.",
                max_steps=1,
                priority=20 + index,
                runtime_config={"loop_run_id": f"ticket-loop-worker-daemon-smoke-{index}"},
                actor_employee_id="clara",
                actor_role="AI Team OS Manager",
                reason=f"Queue daemon worker smoke run {index}.",
            ),
            workspace_dir=workspace,
        )
        for index in (1, 2)
    ]
    queue_ids = [item.queue_id for item in enqueued]
    run_ids = [item.run_id for item in enqueued]
    worker = TicketLoopQueueWorker(
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=_CompletedDispatch(),  # type: ignore[arg-type]
        ),
    )
    baseline = worker.status()
    started = await worker.start(
        TicketLoopQueueWorkerControlRequest(
            interval_seconds=interval_seconds,
            max_items=1,
            reason="Run deterministic queue worker daemon smoke.",
        )
    )
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    try:
        while asyncio.get_running_loop().time() < deadline:
            queue = [item for item in list_ticket_loop_queue(workspace_dir=workspace) if item.queue_id in queue_ids]
            status = worker.status()
            tick_delta = status.total_ticks - baseline.total_ticks
            if queue and all(item.status == "completed" for item in queue) and tick_delta >= min_ticks:
                break
            await asyncio.sleep(min(max(interval_seconds / 2, 0.01), 0.05))
    finally:
        stopped = await worker.stop("Stop deterministic queue worker daemon smoke.")

    queue_after = [item for item in list_ticket_loop_queue(workspace_dir=workspace) if item.queue_id in queue_ids]
    runs_after = [get_ticket_loop_run(ticket.id, run_id, workspace_dir=workspace) for run_id in run_ids]
    completed_statuses = [item.status for item in queue_after]
    run_statuses = [run.status if run is not None else "" for run in runs_after]
    tick_delta = stopped.total_ticks - baseline.total_ticks
    processed_delta = stopped.total_processed - baseline.total_processed
    checks = [
        _check("daemon.started.status", started.status, "running"),
        _check("daemon.stopped.status", stopped.status, "stopped"),
        _check_list("daemon.queue_statuses", completed_statuses, ["completed", "completed"]),
        _check_list("daemon.run_statuses", run_statuses, ["completed", "completed"]),
        _check_min_int("daemon.tick_delta", tick_delta, min_ticks),
        _check_int("daemon.processed_delta", processed_delta, 2),
        _check_in("daemon.last_tick_status", stopped.last_tick_status, ["completed", "idle"]),
        _check("daemon.last_error", stopped.last_error, ""),
        _check_present("daemon.saved_path", stopped.saved_path),
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "status": "passed" if passed else "failed",
        "checks": checks,
        "summary": {
            "ticket_id": ticket.id,
            "queue_ids": queue_ids,
            "run_ids": run_ids,
            "queue_statuses": completed_statuses,
            "run_statuses": run_statuses,
            "tick_delta": tick_delta,
            "processed_delta": processed_delta,
            "min_ticks": min_ticks,
            "interval_seconds": interval_seconds,
            "timeout_seconds": timeout_seconds,
            "started_status": started.model_dump(mode="json"),
            "stopped_status": stopped.model_dump(mode="json"),
        },
    }


def _candidate_queue_item_ids(candidate: Any | None) -> list[str]:
    if candidate is None:
        return []
    provenance = getattr(candidate, "provenance", {})
    if not isinstance(provenance, dict):
        return []
    queue_item_ids = provenance.get("queue_item_ids")
    return [str(item) for item in queue_item_ids] if isinstance(queue_item_ids, list) else []


def _check(name: str, actual: Any, expected: str) -> dict[str, Any]:
    actual_text = str(actual or "")
    return {"name": name, "expected": expected, "actual": actual_text, "passed": actual_text == expected}


def _check_int(name: str, actual: int, expected: int) -> dict[str, Any]:
    return {"name": name, "expected": str(expected), "actual": str(actual), "passed": actual == expected}


def _check_list(name: str, actual: list[str], expected: list[str]) -> dict[str, Any]:
    return {"name": name, "expected": expected, "actual": actual, "passed": actual == expected}


def _check_contains(name: str, actual: list[str], expected: str) -> dict[str, Any]:
    return {"name": name, "expected": expected, "actual": actual, "passed": expected in actual}


def _check_in(name: str, actual: Any, expected: list[str]) -> dict[str, Any]:
    actual_text = str(actual or "")
    return {"name": name, "expected": expected, "actual": actual_text, "passed": actual_text in expected}


def _check_min_int(name: str, actual: int, expected_minimum: int) -> dict[str, Any]:
    return {
        "name": name,
        "expected": f">={expected_minimum}",
        "actual": str(actual),
        "passed": actual >= expected_minimum,
    }


def _check_present(name: str, actual: Any) -> dict[str, Any]:
    actual_text = str(actual or "")
    return {"name": name, "expected": "present", "actual": actual_text, "passed": bool(actual_text)}


def _write_output(payload: dict[str, Any], output: str) -> None:
    if not output:
        return
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
