#!/usr/bin/env python3
"""Start LangGraph Agent Server, run the existing smoke, then shut it down."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from langgraph_agent_server_smoke import run_smoke  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Start LangGraph Agent Server and run the AITeamOS SDK smoke.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Use 0 to choose an available local port.")
    parser.add_argument("--config", default=str(ROOT_DIR / "langgraph.json"))
    parser.add_argument("--langgraph-bin", default=os.environ.get("LANGGRAPH_BIN", "langgraph"))
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--allow-blocking", action="store_true")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--assistant-id", default=os.environ.get("AITEAMOS_LANGGRAPH_ASSISTANT_ID", "aiteamos_workbench"))
    parser.add_argument("--message", default="List employees")
    parser.add_argument("--employee-id", default="clara")
    parser.add_argument("--thread-id", default="agent-server-ci-smoke-clara")
    parser.add_argument("--ticket-key", default="")
    parser.add_argument("--runtime-run-id", default="", help="Optional deterministic LangGraph runtime run_id.")
    parser.add_argument("--use-local-ticket-backend", action="store_true")
    parser.add_argument("--seed-ticket", action="store_true")
    parser.add_argument("--expect-status", default="completed")
    parser.add_argument("--expect-current-node", default="final_response")
    parser.add_argument("--expect-context-source", default="langgraph_context_node")
    parser.add_argument("--expect-approval-ref", default="")
    parser.add_argument("--expect-approval-request-count", type=int, default=-1)
    parser.add_argument("--min-provider-blockers", type=int, default=-1)
    parser.add_argument("--max-provider-blockers", type=int, default=-1)
    parser.add_argument("--expect-provider-blocker-reason", default="")
    parser.add_argument("--min-asset-candidates", type=int, default=-1)
    parser.add_argument("--min-linked-assets", type=int, default=-1)
    parser.add_argument("--resume-approval-ref", default="")
    parser.add_argument("--review-resume-approval", action="store_true", help="Mark the resume approval as approved before sending the LangGraph resume command.")
    parser.add_argument("--review-approval-ref", default="", help="Review an approval after the initial Agent Server run without sending a resume command.")
    parser.add_argument("--review-approval-status", default="")
    parser.add_argument("--review-approval-reason", default="Reviewed by LangGraph Agent Server CI smoke.")
    parser.add_argument("--expect-review-status", default="")
    parser.add_argument("--expect-review-ticket-status", default="")
    parser.add_argument("--expect-review-ticket-report-type", default="")
    parser.add_argument("--expect-review-timeline-status", default="")
    parser.add_argument("--resume-approved-capabilities", default="repo:write")
    parser.add_argument("--expect-resume-status", default="completed")
    parser.add_argument("--expect-resume-current-node", default="final_response")
    parser.add_argument("--require-resume-ticket-report", action="store_true")
    parser.add_argument("--min-resume-asset-candidates", type=int, default=-1)
    parser.add_argument("--min-resume-linked-assets", type=int, default=-1)
    parser.add_argument("--expect-action", default="")
    parser.add_argument("--expect-handoff-target", default="")
    parser.add_argument("--expect-handoff-status", default="")
    parser.add_argument("--expect-handoff-memory-scope", default="")
    parser.add_argument("--expect-handoff-risk-level", default="")
    parser.add_argument("--expect-handoff-risk-allowed", action="store_true")
    parser.add_argument("--min-handoff-refs", type=int, default=-1)
    parser.add_argument("--expect-visible-response-version", default="")
    parser.add_argument("--expect-visible-display-state", default="")
    parser.add_argument("--expect-visible-assistant-contains", default="")
    parser.add_argument(
        "--seed-handoff-policy-employees",
        action="store_true",
        help="Seed deterministic Clara/RD profiles for memory-scope and risk-aware handoff smoke.",
    )
    parser.add_argument("--server-log", default="")
    parser.add_argument("--output", default="", help="Optional path to write the JSON result.")
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).expanduser().resolve()
    if args.use_local_ticket_backend:
        _configure_local_ticket_backend(workspace_dir=workspace_dir)
    if args.seed_ticket:
        _seed_ticket(workspace_dir=workspace_dir, ticket_key=args.ticket_key)
    if args.seed_handoff_policy_employees:
        _seed_handoff_policy_employees(workspace_dir=workspace_dir)
    port = args.port if args.port else _free_port(args.host)
    url = f"http://{args.host}:{port}"
    log_path = Path(args.server_log).expanduser().resolve() if args.server_log else _temporary_log_path()
    command = [
        args.langgraph_bin,
        "dev",
        "--host",
        args.host,
        "--port",
        str(port),
        "--config",
        str(Path(args.config).expanduser().resolve()),
        "--no-reload",
        "--no-browser",
    ]
    if args.allow_blocking:
        command.append("--allow-blocking")

    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    env["AITEAMOS_LANGGRAPH_URL"] = url
    env["AITEAMOS_LANGGRAPH_ASSISTANT_ID"] = args.assistant_id

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT_DIR),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    try:
        payload, exit_code = _wait_and_smoke(
            process=process,
            url=url,
            assistant_id=args.assistant_id,
            message=args.message,
            employee_id=args.employee_id,
            thread_id=args.thread_id,
            ticket_key=args.ticket_key,
            runtime_run_id=args.runtime_run_id,
            expect_status=args.expect_status,
            expect_current_node=args.expect_current_node,
            expect_context_source=args.expect_context_source,
            expect_approval_ref=args.expect_approval_ref,
            expect_approval_request_count=args.expect_approval_request_count,
            min_provider_blockers=args.min_provider_blockers,
            max_provider_blockers=args.max_provider_blockers,
            expect_provider_blocker_reason=args.expect_provider_blocker_reason,
            min_asset_candidates=args.min_asset_candidates,
            min_linked_assets=args.min_linked_assets,
            resume_approval_ref=args.resume_approval_ref,
            review_resume_approval=args.review_resume_approval,
            review_approval_ref=args.review_approval_ref,
            review_approval_status=args.review_approval_status,
            review_approval_reason=args.review_approval_reason,
            expect_review_status=args.expect_review_status,
            expect_review_ticket_status=args.expect_review_ticket_status,
            expect_review_ticket_report_type=args.expect_review_ticket_report_type,
            expect_review_timeline_status=args.expect_review_timeline_status,
            resume_approved_capabilities=_csv(args.resume_approved_capabilities),
            expect_resume_status=args.expect_resume_status,
            expect_resume_current_node=args.expect_resume_current_node,
            require_resume_ticket_report=args.require_resume_ticket_report,
            min_resume_asset_candidates=args.min_resume_asset_candidates,
            min_resume_linked_assets=args.min_resume_linked_assets,
            expect_action=args.expect_action,
            expect_handoff_target=args.expect_handoff_target,
            expect_handoff_status=args.expect_handoff_status,
            expect_handoff_memory_scope=args.expect_handoff_memory_scope,
            expect_handoff_risk_level=args.expect_handoff_risk_level,
            expect_handoff_risk_allowed=args.expect_handoff_risk_allowed,
            min_handoff_refs=args.min_handoff_refs,
            expect_visible_response_version=args.expect_visible_response_version,
            expect_visible_display_state=args.expect_visible_display_state,
            expect_visible_assistant_contains=args.expect_visible_assistant_contains,
            workspace_dir=workspace_dir,
            startup_timeout=args.startup_timeout,
            poll_interval=args.poll_interval,
            command=command,
            log_path=log_path,
        )
    finally:
        _terminate_process(process)

    _write_output(payload, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def _wait_and_smoke(
    *,
    process: subprocess.Popen[Any],
    url: str,
    assistant_id: str,
    message: str,
    employee_id: str,
    thread_id: str,
    ticket_key: str,
    runtime_run_id: str,
    expect_status: str,
    expect_current_node: str,
    expect_context_source: str,
    expect_approval_ref: str,
    expect_approval_request_count: int,
    min_provider_blockers: int,
    max_provider_blockers: int,
    expect_provider_blocker_reason: str,
    min_asset_candidates: int,
    min_linked_assets: int,
    resume_approval_ref: str,
    review_resume_approval: bool,
    review_approval_ref: str,
    review_approval_status: str,
    review_approval_reason: str,
    expect_review_status: str,
    expect_review_ticket_status: str,
    expect_review_ticket_report_type: str,
    expect_review_timeline_status: str,
    resume_approved_capabilities: list[str],
    expect_resume_status: str,
    expect_resume_current_node: str,
    require_resume_ticket_report: bool,
    min_resume_asset_candidates: int,
    min_resume_linked_assets: int,
    expect_action: str,
    expect_handoff_target: str,
    expect_handoff_status: str,
    expect_handoff_memory_scope: str,
    expect_handoff_risk_level: str,
    expect_handoff_risk_allowed: bool,
    min_handoff_refs: int,
    expect_visible_response_version: str,
    expect_visible_display_state: str,
    expect_visible_assistant_contains: str,
    workspace_dir: Path,
    startup_timeout: float,
    poll_interval: float,
    command: list[str],
    log_path: Path,
) -> tuple[dict[str, Any], int]:
    deadline = time.monotonic() + startup_timeout
    last_error = ""
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            payload = _base_payload(
                status="blocked",
                url=url,
                assistant_id=assistant_id,
                workspace_dir=workspace_dir,
                command=command,
                log_path=log_path,
            )
            payload.update(
                {
                    "error": f"LangGraph Agent Server exited before smoke completed with code {return_code}.",
                    "server_log_tail": _tail(log_path),
                }
            )
            return payload, 2
        try:
            smoke = run_smoke(
                url=url,
                assistant_id=assistant_id,
                message=message,
                employee_id=employee_id,
                thread_id=thread_id,
                ticket_key=ticket_key,
                runtime_run_id=runtime_run_id,
                expect_status=expect_status,
                expect_current_node=expect_current_node,
                expect_context_source=expect_context_source,
                expect_approval_ref=expect_approval_ref,
                expect_approval_request_count=expect_approval_request_count,
                min_provider_blockers=min_provider_blockers,
                max_provider_blockers=max_provider_blockers,
                expect_provider_blocker_reason=expect_provider_blocker_reason,
                min_asset_candidates=min_asset_candidates,
                min_linked_assets=min_linked_assets,
                resume_approval_ref=resume_approval_ref,
                review_resume_approval=review_resume_approval,
                review_approval_ref=review_approval_ref,
                review_approval_status=review_approval_status,
                review_approval_reason=review_approval_reason,
                expect_review_status=expect_review_status,
                expect_review_ticket_status=expect_review_ticket_status,
                expect_review_ticket_report_type=expect_review_ticket_report_type,
                expect_review_timeline_status=expect_review_timeline_status,
                resume_approved_capabilities=resume_approved_capabilities,
                expect_resume_status=expect_resume_status,
                expect_resume_current_node=expect_resume_current_node,
                require_resume_ticket_report=require_resume_ticket_report,
                min_resume_asset_candidates=min_resume_asset_candidates,
                min_resume_linked_assets=min_resume_linked_assets,
                expect_action=expect_action,
                expect_handoff_target=expect_handoff_target,
                expect_handoff_status=expect_handoff_status,
                expect_handoff_memory_scope=expect_handoff_memory_scope,
                expect_handoff_risk_level=expect_handoff_risk_level,
                expect_handoff_risk_allowed=expect_handoff_risk_allowed,
                min_handoff_refs=min_handoff_refs,
                expect_visible_response_version=expect_visible_response_version,
                expect_visible_display_state=expect_visible_display_state,
                expect_visible_assistant_contains=expect_visible_assistant_contains,
                workspace_dir=workspace_dir,
            )
        except Exception as exc:
            last_error = str(exc)
            time.sleep(max(0.1, poll_interval))
            continue
        payload = _base_payload(
            status=smoke["status"],
            url=url,
            assistant_id=assistant_id,
            workspace_dir=workspace_dir,
            command=command,
            log_path=log_path,
        )
        payload["smoke"] = smoke
        if smoke["status"] == "passed":
            return payload, 0
        payload["server_log_tail"] = _tail(log_path)
        return payload, 2

    payload = _base_payload(
        status="blocked",
        url=url,
        assistant_id=assistant_id,
        workspace_dir=workspace_dir,
        command=command,
        log_path=log_path,
    )
    payload.update(
        {
            "error": f"LangGraph Agent Server was not ready within {startup_timeout:.1f}s.",
            "last_error": last_error,
            "server_log_tail": _tail(log_path),
        }
    )
    return payload, 2


def _base_payload(
    *,
    status: str,
    url: str,
    assistant_id: str,
    workspace_dir: Path,
    command: list[str],
    log_path: Path,
) -> dict[str, Any]:
    return {
        "schema": "aiteamos.langgraph_agent_server_ci_smoke.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "url": url,
        "assistant_id": assistant_id,
        "workspace_dir": str(workspace_dir),
        "command": command,
        "server_log": str(log_path),
    }


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _temporary_log_path() -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="aiteamos-langgraph-agent-server-", suffix=".log", delete=False)
    try:
        return Path(handle.name)
    finally:
        handle.close()


def _tail(path: Path, *, max_chars: int = 6000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:]


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _configure_local_ticket_backend(*, workspace_dir: Path) -> None:
    services_api_dir = ROOT_DIR / "services" / "api"
    if str(services_api_dir) not in sys.path:
        sys.path.insert(0, str(services_api_dir))
    from aiteamos_api.read.ticket_service import TicketBackendSettingsUpdateRequest, update_ticket_backend_settings

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )


def _seed_ticket(*, workspace_dir: Path, ticket_key: str) -> None:
    normalized = ticket_key.strip()
    if not normalized:
        raise ValueError("--seed-ticket requires --ticket-key.")
    namespace = normalized.split("-", maxsplit=1)[0].lower()
    if not namespace:
        raise ValueError(f"Ticket key must include a namespace: {normalized}")

    services_api_dir = ROOT_DIR / "services" / "api"
    if str(services_api_dir) not in sys.path:
        sys.path.insert(0, str(services_api_dir))
    from aiteamos_api.read.ticket_service import TicketEvent, list_tickets

    _configure_local_ticket_backend(workspace_dir=workspace_dir)
    ticket_path = workspace_dir / ".aiteamos" / "tickets" / namespace / f"{normalized}.ticket.jsonl"
    if ticket_path.exists():
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    events = [
        TicketEvent(
            event_id=f"event-{uuid4().hex}",
            ticket_id=normalized,
            type="created",
            at=timestamp,
            actor={"id": "clara", "role": "AI Team OS Manager"},
            data={
                "title": "Agent Server approval resume smoke",
                "description": "Seed Ticket for LangGraph Agent Server approval resume smoke.",
                "status": "assigned",
                "ticket_type": namespace,
                "knowledge_refs": [],
                "code_repository_ids": [],
                "source_thread_id": "agent-server-ci-smoke",
                "source_run_id": "seed-ticket",
            },
        ),
        TicketEvent(
            event_id=f"event-{uuid4().hex}",
            ticket_id=normalized,
            type="assigned",
            at=timestamp,
            actor={"id": "clara", "role": "AI Team OS Manager"},
            data={"assigned_employee_id": "clara", "assigned_role": "AI Team OS Manager"},
        ),
    ]
    ticket_path.parent.mkdir(parents=True, exist_ok=True)
    ticket_path.write_text(
        "".join(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    list_tickets()


def _seed_handoff_policy_employees(*, workspace_dir: Path) -> None:
    employees_dir = workspace_dir / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True, exist_ok=True)
    profiles = {
        "clara": {
            "id": "clara",
            "display_name": "Clara",
            "kind": "ai",
            "role": "AI Team OS Manager",
            "summary": "Ticket-flow manager for governed Employee handoff smoke.",
            "skills": ["ticket-specification", "employee-ticket-flow-design", "technical-decision"],
            "memory_scopes": ["global", "aiteamos"],
            "permissions": ["chat", "manage_tickets", "route_employee", "read_local_assets", "write_trace"],
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["pm", "memory_curator"], "max_risk_level": "critical"},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
        "alex": {
            "id": "alex",
            "display_name": "Alex",
            "kind": "ai",
            "role": "AI RD / Implementer",
            "summary": "Implementation-focused Employee without the requested scoped memory boundary.",
            "skills": ["backend-api-implementation", "test-engineering"],
            "memory_scopes": ["aiteamos"],
            "permissions": ["chat", "read_local_assets", "write_trace", "propose_code_change"],
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["rd"], "max_risk_level": "medium"},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
        "victor": {
            "id": "victor",
            "display_name": "Victor",
            "kind": "ai",
            "role": "AI RD / Implementer",
            "summary": "Implementation-focused Employee allowed for Victor-scoped production handoffs.",
            "skills": ["backend-api-implementation", "runtime-engineering", "test-engineering"],
            "memory_scopes": ["aiteamos", "employee:victor"],
            "permissions": ["chat", "read_local_assets", "write_trace", "propose_code_change"],
            "handoff_policy": {
                "can_receive_handoffs": True,
                "accepts_lanes": ["rd"],
                "preferred_lanes": ["rd"],
                "max_risk_level": "critical",
            },
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
    }
    for employee_id, profile in profiles.items():
        (employees_dir / f"{employee_id}.yaml").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def _write_output(payload: dict[str, Any], output: str) -> None:
    if not output:
        return
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
