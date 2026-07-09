#!/usr/bin/env python3
"""Run plan_v7 verification commands and retain CI-friendly artifacts.

This script is intentionally only an artifact wrapper around existing commands.
It does not introduce a new test runner, observability backend, or agent loop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT_DIR / ".aiteamos" / "artifacts" / "plan_v7"


@dataclass(frozen=True)
class CommandSpec:
    name: str
    argv: list[str]
    cwd: Path = ROOT_DIR
    timeout_seconds: float = 300.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run plan_v7 verification and write artifact manifest/logs.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--full", action="store_true", help="Include the broader backend dispatch contract suite.")
    parser.add_argument("--include-frontend", action="store_true", help="Include dashboard vitest/build commands.")
    parser.add_argument("--include-agent-server-smoke", action="store_true", help="Include the primary graph Agent Server approval resume smoke.")
    parser.add_argument("--include-agent-server-matrix-smoke", action="store_true", help="Include read-only, answer-only, provider-blocker, and approval/resume Agent Server smoke paths.")
    parser.add_argument(
        "--production-readiness",
        action="store_true",
        help=(
            "Run the production readiness profile: broader backend contracts, Agent Server matrix, "
            "and strict artifact summary evidence gates. Live provider dogfood still requires "
            "--include-live-provider-dogfood plus AITEAMOS_LIVE_PROVIDER_DOGFOOD=1."
        ),
    )
    parser.add_argument("--include-live-provider-dogfood", action="store_true", help="Opt in to the gated live provider dogfood execution command.")
    parser.add_argument(
        "--live-provider-profile",
        default=os.environ.get("AITEAMOS_LIVE_DOGFOOD_PROFILE", "core-loop"),
        choices=["core-loop", "core_loop", "repo-write-adapter", "repo_write_adapter"],
    )
    parser.add_argument("--live-provider-executor-id", default=os.environ.get("AITEAMOS_LIVE_DOGFOOD_EXECUTOR", ""))
    parser.add_argument("--live-provider-ticket-id", default="", help="Optional existing Ticket id for the opt-in live provider dogfood run.")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    run_id = args.run_id.strip() or _run_id()
    artifact_root = Path(args.artifact_dir).expanduser().resolve() / run_id
    workspace_dir = Path(args.workspace_dir).expanduser().resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    env.setdefault("PYTHONUNBUFFERED", "1")

    effective_full = bool(args.full or args.production_readiness)
    effective_include_agent_server_matrix_smoke = bool(args.include_agent_server_matrix_smoke or args.production_readiness)
    live_provider_profile = _normalize_live_provider_profile(args.live_provider_profile)
    live_provider_executor_id = args.live_provider_executor_id.strip() or _default_executor_for_live_provider_profile(live_provider_profile)
    commands = _commands(
        full=effective_full,
        include_frontend=args.include_frontend,
        include_agent_server_smoke=args.include_agent_server_smoke,
        include_agent_server_matrix_smoke=effective_include_agent_server_matrix_smoke,
        include_live_provider_dogfood=args.include_live_provider_dogfood,
        live_provider_profile=live_provider_profile,
        live_provider_executor_id=live_provider_executor_id,
        live_provider_ticket_id=args.live_provider_ticket_id,
        artifact_root=artifact_root,
        workspace_dir=workspace_dir,
    )
    post_commands = _post_commands(
        production_readiness=args.production_readiness,
        artifact_root=artifact_root,
    )
    manifest: dict[str, Any] = {
        "schema": "aiteamos.plan_v7.ci_artifacts.v1",
        "run_id": run_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": "",
        "workspace_dir": str(workspace_dir),
        "artifact_root": str(artifact_root),
        "options": {
            "production_readiness": bool(args.production_readiness),
            "full": effective_full,
            "include_frontend": bool(args.include_frontend),
            "include_agent_server_smoke": bool(args.include_agent_server_smoke),
            "include_agent_server_matrix_smoke": effective_include_agent_server_matrix_smoke,
            "include_live_provider_dogfood": bool(args.include_live_provider_dogfood),
            "live_provider_profile": live_provider_profile,
            "live_provider_executor_id": live_provider_executor_id,
            "live_provider_ticket_id": args.live_provider_ticket_id,
            "fail_fast": bool(args.fail_fast),
        },
        "commands": [],
    }
    manifest_path = artifact_root / "manifest.json"
    _write_manifest(manifest_path, manifest)

    failed = False
    for index, command in enumerate(commands, start=1):
        result = _run_command(index=index, command=command, artifact_root=artifact_root, env=env)
        manifest["commands"].append(result)
        if result["status"] != "passed":
            failed = True
        manifest["status"] = "failed" if failed else "running"
        _write_manifest(manifest_path, manifest)
        if failed and args.fail_fast:
            break

    manifest["status"] = "failed" if failed else "passed"
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, manifest)
    if not failed:
        for command in post_commands:
            result = _run_command(index=len(manifest["commands"]) + 1, command=command, artifact_root=artifact_root, env=env)
            manifest["commands"].append(result)
            if result["status"] != "passed":
                failed = True
            manifest["status"] = "failed" if failed else "passed"
            manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
            _write_manifest(manifest_path, manifest)
            if failed and args.fail_fast:
                break
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if failed else 0


def _commands(
    *,
    full: bool,
    include_frontend: bool,
    include_agent_server_smoke: bool,
    include_agent_server_matrix_smoke: bool,
    include_live_provider_dogfood: bool,
    live_provider_profile: str,
    live_provider_executor_id: str,
    live_provider_ticket_id: str,
    artifact_root: Path,
    workspace_dir: Path,
) -> list[CommandSpec]:
    python = sys.executable or "python"
    commands = [
        CommandSpec(
            name="py_compile_plan_v7_core",
            argv=[
                python,
                "-m",
                "py_compile",
                "scripts/langgraph_agent_server_smoke.py",
                "scripts/langgraph_agent_server_ci_smoke.py",
                "scripts/context_retrieval_eval_smoke.py",
                "scripts/asset_provenance_eval_smoke.py",
                "scripts/runtime_replay_eval_smoke.py",
                "scripts/environment_smoke.py",
                "scripts/runtime_registry_smoke.py",
                "scripts/live_provider_dogfood.py",
                "scripts/live_provider_readiness_smoke.py",
                "scripts/plane_ticket_action_smoke.py",
                "scripts/ticket_loop_queue_worker_smoke.py",
                "scripts/plan_v7_ci_artifacts.py",
                "scripts/plan_v7_artifact_summary.py",
                "services/api/aiteamos_api/agents/aiteamos_workbench_graph.py",
                "services/api/aiteamos_api/agents/workbench/approval_fixture_graph.py",
                "services/api/aiteamos_api/agents/workbench/nodes/bootstrap.py",
                "services/api/aiteamos_api/agents/workbench/nodes/context.py",
                "services/api/aiteamos_api/agents/workbench/nodes/governance.py",
                "services/api/aiteamos_api/agents/workbench/nodes/execution.py",
                "services/api/aiteamos_api/agents/workbench/nodes/handoff.py",
                "services/api/aiteamos_api/read/memory_service.py",
                "services/api/aiteamos_api/read/employee_handoff_service.py",
                "services/api/aiteamos_api/read/langchain_model_provider.py",
                "services/api/aiteamos_api/read/chat_action_planning_service.py",
                "services/api/aiteamos_api/read/provider_conformance_service.py",
                "services/api/aiteamos_api/read/ticket_service.py",
                "services/api/aiteamos_api/read/execution_dispatch_service.py",
                "services/api/aiteamos_api/read/execution_approval_service.py",
                "services/api/aiteamos_api/read/execution_replay_service.py",
                "services/api/aiteamos_api/read/live_provider_dogfood_service.py",
                "services/api/aiteamos_api/read/runtime_executor_routes.py",
                "services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py",
                "services/api/aiteamos_api/read/execution_context_service.py",
                "services/api/aiteamos_api/read/context_retrieval_eval_service.py",
                "services/api/aiteamos_api/read/workbench_runtime_context_service.py",
                "tests/test_aiteamos_workbench_graph.py",
                "tests/test_context_retrieval_eval.py",
                "tests/test_plan_v7_ci_artifacts.py",
                "tests/test_plan_v7_artifact_summary.py",
                "tests/test_plan_v7_workflow.py",
                "tests/test_execution_dispatch_contract.py",
                "tests/test_runtime_executor_routes.py",
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="context_retrieval_eval_smoke",
            argv=[
                python,
                "scripts/context_retrieval_eval_smoke.py",
                "--workspace-dir",
                str(artifact_root / "context-retrieval-eval-smoke-workspace"),
                "--output",
                str(artifact_root / "context_retrieval_eval_smoke.json"),
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="asset_provenance_eval_smoke",
            argv=[
                python,
                "scripts/asset_provenance_eval_smoke.py",
                "--workspace-dir",
                str(artifact_root / "asset-provenance-eval-smoke-workspace"),
                "--output",
                str(artifact_root / "asset_provenance_eval_smoke.json"),
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="runtime_replay_eval_smoke",
            argv=[
                python,
                "scripts/runtime_replay_eval_smoke.py",
                "--workspace-dir",
                str(artifact_root / "runtime-replay-eval-smoke-workspace"),
                "--output",
                str(artifact_root / "runtime_replay_eval_smoke.json"),
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="environment_smoke",
            argv=[
                python,
                "scripts/environment_smoke.py",
                "--workspace-dir",
                str(workspace_dir),
                "--output",
                str(artifact_root / "environment_smoke.json"),
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="runtime_registry_smoke",
            argv=[
                python,
                "scripts/runtime_registry_smoke.py",
                "--workspace-dir",
                str(workspace_dir),
                "--output",
                str(artifact_root / "runtime_registry_smoke.json"),
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="live_provider_readiness_smoke",
            argv=[
                python,
                "scripts/live_provider_readiness_smoke.py",
                "--workspace-dir",
                str(workspace_dir),
                "--profile",
                live_provider_profile,
                "--executor-id",
                live_provider_executor_id,
                "--output",
                str(artifact_root / "live_provider_readiness_smoke.json"),
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="pytest_context_retrieval_eval",
            argv=[python, "-m", "pytest", "tests/test_context_retrieval_eval.py", "-q"],
            timeout_seconds=180,
        ),
        CommandSpec(
            name="pytest_workbench_graph_and_context",
            argv=[python, "-m", "pytest", "tests/test_aiteamos_workbench_graph.py", "tests/test_context_retrieval_eval.py", "-q"],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="pytest_plan_v7_artifact_summary",
            argv=[python, "-m", "pytest", "tests/test_plan_v7_artifact_summary.py", "-q"],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="pytest_plan_v7_ci_artifacts",
            argv=[python, "-m", "pytest", "tests/test_plan_v7_ci_artifacts.py", "tests/test_plan_v7_workflow.py", "-q"],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="pytest_runtime_approval_outcomes",
            argv=[
                python,
                "-m",
                "pytest",
                "tests/test_runtime_executor_routes.py",
                "-q",
                "-k",
                "rejected_runtime_approval_writes_ticket_and_employee_ledger or runtime_approval_request_changes_and_evidence_reviews_write_ticket_reports",
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="pytest_runtime_replay_coverage",
            argv=[
                python,
                "-m",
                "pytest",
                "tests/test_runtime_executor_routes.py",
                "-q",
                "-k",
                "runtime_execution_sessions_list_checkpoint_and_replay_refs",
            ],
            timeout_seconds=180,
        ),
        CommandSpec(
            name="pytest_ticket_loop_queue_reliability",
            argv=[
                python,
                "-m",
                "pytest",
                "tests/test_execution_dispatch_contract.py",
                "-q",
                "-k",
                "ticket_loop_queue_enqueue_and_pump_runs_existing_loop_service or ticket_loop_queue_reliability_flags_duplicate_queued_work or ticket_loop_queue_reliability_flags_stale_running_work or ticket_loop_queue_reliability_surfaces_blocked_provider_runs or ticket_loop_queue_pump_auto_proposes_failure_retrospective_after_repeated_failures or ticket_loop_queue_worker_status_records_recent_policy_actions",
            ],
            timeout_seconds=300,
        ),
        CommandSpec(
            name="ticket_loop_queue_worker_smoke",
            argv=[
                python,
                "scripts/ticket_loop_queue_worker_smoke.py",
                "--workspace-dir",
                str(artifact_root / "ticket-loop-queue-worker-smoke-workspace"),
                "--output",
                str(artifact_root / "ticket_loop_queue_worker_smoke.json"),
                "--daemon-min-ticks",
                "6",
                "--daemon-interval-seconds",
                "0.1",
                "--daemon-timeout-seconds",
                "10",
            ],
            timeout_seconds=120,
        ),
        CommandSpec(
            name="langgraph_validate",
            argv=["langgraph", "validate", "--config", "langgraph.json"],
            timeout_seconds=180,
        ),
        CommandSpec(
            name="git_diff_check_plan_v7_slice",
            argv=[
                "git",
                "diff",
                "--check",
                "--",
                "scripts/plan_v7_ci_artifacts.py",
                "scripts/plan_v7_artifact_summary.py",
                "scripts/langgraph_agent_server_smoke.py",
                "scripts/langgraph_agent_server_ci_smoke.py",
                "scripts/context_retrieval_eval_smoke.py",
                "scripts/asset_provenance_eval_smoke.py",
                "scripts/runtime_replay_eval_smoke.py",
                "scripts/environment_smoke.py",
                "scripts/runtime_registry_smoke.py",
                "scripts/live_provider_readiness_smoke.py",
                "scripts/plane_ticket_action_smoke.py",
                "scripts/ticket_loop_queue_worker_smoke.py",
                "services/api/aiteamos_api/agents/aiteamos_workbench_graph.py",
                "services/api/aiteamos_api/agents/workbench/approval_fixture_graph.py",
                "services/api/aiteamos_api/agents/workbench/nodes/bootstrap.py",
                "services/api/aiteamos_api/agents/workbench/nodes/context.py",
                "services/api/aiteamos_api/agents/workbench/nodes/governance.py",
                "services/api/aiteamos_api/agents/workbench/nodes/execution.py",
                "services/api/aiteamos_api/agents/workbench/nodes/handoff.py",
                "services/api/aiteamos_api/read/memory_service.py",
                "services/api/aiteamos_api/read/employee_handoff_service.py",
                "services/api/aiteamos_api/read/langchain_model_provider.py",
                "services/api/aiteamos_api/read/chat_action_planning_service.py",
                "services/api/aiteamos_api/read/provider_conformance_service.py",
                "services/api/aiteamos_api/read/ticket_service.py",
                "services/api/aiteamos_api/read/execution_dispatch_service.py",
                "services/api/aiteamos_api/read/execution_approval_service.py",
                "services/api/aiteamos_api/read/execution_replay_service.py",
                "services/api/aiteamos_api/read/runtime_executor_routes.py",
                "services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py",
                "services/api/aiteamos_api/read/execution_context_service.py",
                "services/api/aiteamos_api/read/context_retrieval_eval_service.py",
                "services/api/aiteamos_api/read/workbench_runtime_context_service.py",
                "apps/dashboard/src/api/runtimeExecutors.ts",
                "apps/dashboard/src/components/runtimeReplay.tsx",
                "tests/test_aiteamos_workbench_graph.py",
                "tests/test_context_retrieval_eval.py",
                "tests/test_plan_v7_ci_artifacts.py",
                "tests/test_plan_v7_artifact_summary.py",
                "tests/test_plan_v7_workflow.py",
                "tests/test_execution_dispatch_contract.py",
                "tests/test_runtime_executor_routes.py",
                "apps/dashboard/src/__tests__/runtime-page.test.tsx",
                "README.md",
                "plan_v7.md",
            ],
            timeout_seconds=120,
        ),
    ]
    if full:
        commands.append(
            CommandSpec(
                name="pytest_execution_dispatch_contract",
                argv=[python, "-m", "pytest", "tests/test_execution_dispatch_contract.py", "-q"],
                timeout_seconds=600,
            )
        )
    if include_frontend:
        dashboard_dir = ROOT_DIR / "apps" / "dashboard"
        commands.extend(
            [
                CommandSpec(
                    name="dashboard_vitest",
                    argv=["npm", "test"],
                    cwd=dashboard_dir,
                    timeout_seconds=600,
                ),
                CommandSpec(
                    name="dashboard_build",
                    argv=["npm", "run", "build"],
                    cwd=dashboard_dir,
                    timeout_seconds=600,
                ),
            ]
        )
    if include_agent_server_smoke:
        smoke_workspace = artifact_root / "agent-server-workspace"
        smoke_output = artifact_root / "agent_server_primary_approval_resume.json"
        smoke_log = artifact_root / "agent_server_primary_approval_resume.log"
        commands.append(
            CommandSpec(
                name="agent_server_primary_approval_resume_smoke",
                argv=[
                    python,
                    "scripts/langgraph_agent_server_ci_smoke.py",
                    "--workspace-dir",
                    str(smoke_workspace),
                    "--startup-timeout",
                    "120",
                    "--assistant-id",
                    "aiteamos_workbench",
                    "--thread-id",
                    f"plan-v7-ci-{artifact_root.name}",
                    "--message",
                    "Implement code changes for ticket ticket-plan-v7-ci-primary-approval",
                    "--ticket-key",
                    "ticket-plan-v7-ci-primary-approval",
                    "--seed-ticket",
                    "--runtime-run-id",
                    "run-plan-v7-ci-primary-approval",
                    "--expect-status",
                    "needs_approval",
                    "--expect-current-node",
                    "approval_interrupt",
                    "--expect-action",
                    "implement_ticket",
                    "--expect-approval-ref",
                    "approval-run-plan-v7-ci-primary-approval-1",
                    "--resume-approval-ref",
                    "approval-run-plan-v7-ci-primary-approval-1",
                    "--review-resume-approval",
                    "--expect-resume-status",
                    "completed",
                    "--expect-resume-current-node",
                    "final_response",
                    "--require-resume-ticket-report",
                    "--min-resume-linked-assets",
                    "1",
                    "--output",
                    str(smoke_output),
                    "--server-log",
                    str(smoke_log),
                ],
                timeout_seconds=240,
            )
        )
    if include_agent_server_matrix_smoke:
        commands.extend(_agent_server_matrix_smoke_commands(python=python, artifact_root=artifact_root))
    if include_live_provider_dogfood:
        commands.extend(
            [
                _plane_ticket_action_smoke_command(
                    python=python,
                    artifact_root=artifact_root,
                    workspace_dir=workspace_dir,
                    ticket_id=live_provider_ticket_id,
                ),
                _live_provider_dogfood_command(
                    python=python,
                    artifact_root=artifact_root,
                    workspace_dir=workspace_dir,
                    profile=live_provider_profile,
                    executor_id=live_provider_executor_id,
                    ticket_id=live_provider_ticket_id,
                ),
            ]
        )
    return commands


def _post_commands(*, production_readiness: bool, artifact_root: Path) -> list[CommandSpec]:
    if not production_readiness:
        return []
    python = sys.executable or "python"
    return [_production_readiness_summary_gate_command(python=python, artifact_root=artifact_root)]


def _production_readiness_summary_gate_command(*, python: str, artifact_root: Path) -> CommandSpec:
    return CommandSpec(
        name="plan_v7_production_readiness_summary_gate",
        argv=[
            python,
            "scripts/plan_v7_artifact_summary.py",
            "--artifact-dir",
            str(artifact_root.parent),
            "--limit",
            "25",
            "--fail-on-evidence-gaps",
            "--output",
            str(artifact_root / "production_readiness_summary.json"),
        ],
        timeout_seconds=120,
    )


def _live_provider_dogfood_command(
    *,
    python: str,
    artifact_root: Path,
    workspace_dir: Path,
    profile: str,
    executor_id: str,
    ticket_id: str,
) -> CommandSpec:
    argv = [
        python,
        "scripts/live_provider_dogfood.py",
        "--execute",
        "--workspace-dir",
        str(workspace_dir),
        "--profile",
        profile,
        "--executor-id",
        executor_id,
        "--start-agent-server",
        "--server-log",
        str(artifact_root / "live_provider_agent_server.log"),
        "--output",
        str(artifact_root / "live_provider_dogfood.json"),
    ]
    if ticket_id.strip():
        argv.extend(["--ticket-id", ticket_id.strip(), "--no-create-ticket"])
    if profile == "core_loop":
        argv.extend(
            [
                "--require-natural-handoff",
                "--expected-handoff-target",
                "alex",
            ]
        )
    return CommandSpec(
        name="live_provider_dogfood_execute",
        argv=argv,
        timeout_seconds=600,
    )


def _plane_ticket_action_smoke_command(
    *,
    python: str,
    artifact_root: Path,
    workspace_dir: Path,
    ticket_id: str,
) -> CommandSpec:
    argv = [
        python,
        "scripts/plane_ticket_action_smoke.py",
        "--execute",
        "--workspace-dir",
        str(workspace_dir),
        "--source-run-id",
        f"plan-v7-{artifact_root.name}-plane-action-smoke",
        "--output",
        str(artifact_root / "plane_ticket_action_smoke.json"),
    ]
    if ticket_id.strip():
        argv.extend(["--ticket-id", ticket_id.strip(), "--no-create-ticket"])
    return CommandSpec(
        name="plane_ticket_action_smoke",
        argv=argv,
        timeout_seconds=180,
    )


def _agent_server_matrix_smoke_commands(*, python: str, artifact_root: Path) -> list[CommandSpec]:
    matrix_root = artifact_root / "agent-server-matrix"
    return [
        CommandSpec(
            name="agent_server_readonly_list_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "readonly-list-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-readonly-list",
                "--message",
                "List employees",
                "--use-local-ticket-backend",
                "--runtime-run-id",
                "run-plan-v7-ci-readonly-list",
                "--expect-status",
                "completed",
                "--expect-current-node",
                "final_response",
                "--expect-action",
                "list_employees",
                "--expect-approval-request-count",
                "0",
                "--max-provider-blockers",
                "0",
                "--output",
                str(matrix_root / "readonly_list.json"),
                "--server-log",
                str(matrix_root / "readonly_list.log"),
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="agent_server_answer_only_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "answer-only-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-answer-only",
                "--message",
                "Summarize the AITeamOS operating model in one concise paragraph.",
                "--use-local-ticket-backend",
                "--runtime-run-id",
                "run-plan-v7-ci-answer-only",
                "--expect-status",
                "completed",
                "--expect-current-node",
                "final_response",
                "--expect-action",
                "answer_only",
                "--expect-approval-request-count",
                "0",
                "--max-provider-blockers",
                "0",
                "--output",
                str(matrix_root / "answer_only.json"),
                "--server-log",
                str(matrix_root / "answer_only.log"),
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="agent_server_provider_blocker_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "provider-blocker-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-provider-blocker",
                "--message",
                "Summarize the AITeamOS operating model in one concise paragraph.",
                "--runtime-run-id",
                "run-plan-v7-ci-provider-blocker",
                "--expect-status",
                "completed",
                "--expect-current-node",
                "final_response",
                "--expect-action",
                "answer_only",
                "--expect-approval-request-count",
                "0",
                "--min-provider-blockers",
                "1",
                "--expect-provider-blocker-reason",
                "plane_setup_blocker",
                "--output",
                str(matrix_root / "provider_blocker.json"),
                "--server-log",
                str(matrix_root / "provider_blocker.log"),
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="agent_server_handoff_policy_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "handoff-policy-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-handoff-policy",
                "--message",
                "Coordinate backend runtime ownership using employee:victor scoped context for production readiness.",
                "--ticket-key",
                "ticket-plan-v7-ci-handoff-policy",
                "--seed-ticket",
                "--seed-handoff-policy-employees",
                "--runtime-run-id",
                "run-plan-v7-ci-handoff-policy",
                "--expect-status",
                "completed",
                "--expect-current-node",
                "final_response",
                "--expect-action",
                "answer_only",
                "--expect-approval-request-count",
                "0",
                "--max-provider-blockers",
                "0",
                "--expect-handoff-target",
                "victor",
                "--expect-handoff-status",
                "durable_handoff_recorded",
                "--expect-handoff-memory-scope",
                "employee:victor",
                "--expect-handoff-risk-level",
                "critical",
                "--expect-handoff-risk-allowed",
                "--min-handoff-refs",
                "1",
                "--output",
                str(matrix_root / "handoff_policy.json"),
                "--server-log",
                str(matrix_root / "handoff_policy.log"),
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="agent_server_primary_approval_resume_matrix_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "approval-resume-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-approval-resume",
                "--message",
                "Implement code changes for ticket ticket-plan-v7-ci-matrix-approval",
                "--ticket-key",
                "ticket-plan-v7-ci-matrix-approval",
                "--seed-ticket",
                "--runtime-run-id",
                "run-plan-v7-ci-matrix-approval",
                "--expect-status",
                "needs_approval",
                "--expect-current-node",
                "approval_interrupt",
                "--expect-action",
                "implement_ticket",
                "--expect-approval-ref",
                "approval-run-plan-v7-ci-matrix-approval-1",
                "--expect-approval-request-count",
                "1",
                "--max-provider-blockers",
                "0",
                "--resume-approval-ref",
                "approval-run-plan-v7-ci-matrix-approval-1",
                "--review-resume-approval",
                "--expect-resume-status",
                "completed",
                "--expect-resume-current-node",
                "final_response",
                "--require-resume-ticket-report",
                "--min-resume-linked-assets",
                "1",
                "--output",
                str(matrix_root / "approval_resume.json"),
                "--server-log",
                str(matrix_root / "approval_resume.log"),
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="agent_server_approval_evidence_review_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "approval-evidence-review-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-approval-evidence-review",
                "--message",
                "Implement code changes for ticket ticket-plan-v7-ci-evidence-review",
                "--ticket-key",
                "ticket-plan-v7-ci-evidence-review",
                "--seed-ticket",
                "--runtime-run-id",
                "run-plan-v7-ci-evidence-review",
                "--expect-status",
                "needs_approval",
                "--expect-current-node",
                "approval_interrupt",
                "--expect-action",
                "implement_ticket",
                "--expect-approval-ref",
                "approval-run-plan-v7-ci-evidence-review-1",
                "--expect-approval-request-count",
                "1",
                "--max-provider-blockers",
                "0",
                "--review-approval-ref",
                "approval-run-plan-v7-ci-evidence-review-1",
                "--review-approval-status",
                "evidence_requested",
                "--review-approval-reason",
                "Request deterministic evidence before resuming the runtime.",
                "--expect-review-status",
                "evidence_requested",
                "--expect-review-ticket-status",
                "waiting_evidence",
                "--expect-review-ticket-report-type",
                "approval_evidence_requested",
                "--expect-review-timeline-status",
                "evidence_requested",
                "--output",
                str(matrix_root / "approval_evidence_review.json"),
                "--server-log",
                str(matrix_root / "approval_evidence_review.log"),
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="agent_server_approval_rejected_review_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "approval-rejected-review-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-approval-rejected-review",
                "--message",
                "Implement code changes for ticket ticket-plan-v7-ci-rejected-review",
                "--ticket-key",
                "ticket-plan-v7-ci-rejected-review",
                "--seed-ticket",
                "--runtime-run-id",
                "run-plan-v7-ci-rejected-review",
                "--expect-status",
                "needs_approval",
                "--expect-current-node",
                "approval_interrupt",
                "--expect-action",
                "implement_ticket",
                "--expect-approval-ref",
                "approval-run-plan-v7-ci-rejected-review-1",
                "--expect-approval-request-count",
                "1",
                "--max-provider-blockers",
                "0",
                "--review-approval-ref",
                "approval-run-plan-v7-ci-rejected-review-1",
                "--review-approval-status",
                "rejected",
                "--review-approval-reason",
                "Reject this deterministic runtime mutation for smoke coverage.",
                "--expect-review-status",
                "rejected",
                "--expect-review-ticket-status",
                "blocked",
                "--expect-review-ticket-report-type",
                "approval_rejected",
                "--expect-review-timeline-status",
                "rejected",
                "--output",
                str(matrix_root / "approval_rejected_review.json"),
                "--server-log",
                str(matrix_root / "approval_rejected_review.log"),
            ],
            timeout_seconds=240,
        ),
        CommandSpec(
            name="agent_server_approval_changes_review_smoke",
            argv=[
                python,
                "scripts/langgraph_agent_server_ci_smoke.py",
                "--workspace-dir",
                str(matrix_root / "approval-changes-review-workspace"),
                "--startup-timeout",
                "120",
                "--assistant-id",
                "aiteamos_workbench",
                "--thread-id",
                f"plan-v7-ci-{artifact_root.name}-approval-changes-review",
                "--message",
                "Implement code changes for ticket ticket-plan-v7-ci-changes-review",
                "--ticket-key",
                "ticket-plan-v7-ci-changes-review",
                "--seed-ticket",
                "--runtime-run-id",
                "run-plan-v7-ci-changes-review",
                "--expect-status",
                "needs_approval",
                "--expect-current-node",
                "approval_interrupt",
                "--expect-action",
                "implement_ticket",
                "--expect-approval-ref",
                "approval-run-plan-v7-ci-changes-review-1",
                "--expect-approval-request-count",
                "1",
                "--max-provider-blockers",
                "0",
                "--review-approval-ref",
                "approval-run-plan-v7-ci-changes-review-1",
                "--review-approval-status",
                "changes_requested",
                "--review-approval-reason",
                "Request deterministic changes before resuming the runtime.",
                "--expect-review-status",
                "changes_requested",
                "--expect-review-ticket-status",
                "waiting_changes",
                "--expect-review-ticket-report-type",
                "approval_changes_requested",
                "--expect-review-timeline-status",
                "changes_requested",
                "--output",
                str(matrix_root / "approval_changes_review.json"),
                "--server-log",
                str(matrix_root / "approval_changes_review.log"),
            ],
            timeout_seconds=240,
        ),
    ]


def _run_command(*, index: int, command: CommandSpec, artifact_root: Path, env: dict[str, str]) -> dict[str, Any]:
    slug = f"{index:02d}-{_slug(command.name)}"
    stdout_path = artifact_root / f"{slug}.stdout.log"
    stderr_path = artifact_root / f"{slug}.stderr.log"
    result_path = artifact_root / f"{slug}.json"
    started = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command.argv,
            cwd=str(command.cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=command.timeout_seconds,
            check=False,
        )
        return_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        return_code = 124
        stdout = _stringify_timeout_output(exc.stdout)
        stderr = _stringify_timeout_output(exc.stderr) + f"\nCommand timed out after {command.timeout_seconds:.0f}s.\n"

    duration_seconds = round(time.monotonic() - started_monotonic, 3)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    payload = {
        "name": command.name,
        "status": "passed" if return_code == 0 else "failed",
        "return_code": return_code,
        "timed_out": timed_out,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration_seconds,
        "cwd": str(command.cwd),
        "argv": command.argv,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["result_path"] = str(result_path)
    return payload


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_live_provider_profile(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"", "core", "core_loop", "langgraph", "langgraph_core_loop"}:
        return "core_loop"
    if normalized in {"repo", "repo_write", "repo_write_adapter", "runtime_executor", "external_runtime"}:
        return "repo_write_adapter"
    return normalized


def _default_executor_for_live_provider_profile(profile: str) -> str:
    return "codex_cli" if profile == "repo_write_adapter" else "langgraph"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "command"


def _stringify_timeout_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
