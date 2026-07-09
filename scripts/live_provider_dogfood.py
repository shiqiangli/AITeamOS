#!/usr/bin/env python
"""Run the opt-in plan_v7 live provider dogfood loop.

By default this is a dry-run mutation-gate check. Add --include-provider-smoke
to run read-only external provider smoke during dry-run. To mutate live Plane /
Graphiti state, pass --execute and set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aiteamos_api.read.live_provider_dogfood_service import (
    CORE_LOOP_PROFILE,
    LiveProviderDogfoodRequest,
    LiveProviderDogfoodService,
    REPO_WRITE_ADAPTER_PROFILE,
    normalize_live_dogfood_profile,
)
from langgraph_agent_server_ci_smoke import _free_port, _tail, _temporary_log_path, _terminate_process


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AITeamOS live provider dogfood loop.")
    parser.add_argument("--execute", action="store_true", help="Attempt live provider writes when the confirmation env var is also set.")
    parser.add_argument("--readiness", action="store_true", help="Print read-only live dogfood readiness instead of running the loop.")
    parser.add_argument("--confirm-env-var", default="AITEAMOS_LIVE_PROVIDER_DOGFOOD")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(Path.cwd())))
    parser.add_argument("--langgraph-url", default=os.environ.get("AITEAMOS_LANGGRAPH_URL", "http://127.0.0.1:2024"))
    parser.add_argument("--assistant-id", default=os.environ.get("AITEAMOS_LANGGRAPH_ASSISTANT_ID", "aiteamos_workbench"))
    parser.add_argument("--start-agent-server", action="store_true", help="Start a temporary LangGraph Agent Server for this dogfood run.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Temporary Agent Server port when --start-agent-server is set. 0 chooses a free port.")
    parser.add_argument("--config", default=str(Path.cwd() / "langgraph.json"))
    parser.add_argument("--langgraph-bin", default=os.environ.get("LANGGRAPH_BIN", "langgraph"))
    parser.add_argument("--startup-timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--server-log", default="", help="Optional Agent Server log path when --start-agent-server is set.")
    parser.add_argument(
        "--profile",
        default=os.environ.get("AITEAMOS_LIVE_DOGFOOD_PROFILE", "core-loop"),
        choices=["core-loop", "core_loop", "repo-write-adapter", "repo_write_adapter"],
        help="Dogfood profile: core-loop proves LangGraph+DeepSeek; repo-write-adapter proves optional coding executors.",
    )
    parser.add_argument("--employee-id", default="clara")
    parser.add_argument("--worker-employee-id", default="alex")
    parser.add_argument("--reviewer-employee-id", default="clara")
    parser.add_argument("--executor-id", default=os.environ.get("AITEAMOS_LIVE_DOGFOOD_EXECUTOR", ""))
    parser.add_argument(
        "--allow-non-mutating-executor",
        action="store_true",
        help="Allow executors without repo:write capability. Intended for controlled local tests only.",
    )
    parser.add_argument("--ticket-id", default="")
    parser.add_argument("--no-create-ticket", action="store_true", help="Require --ticket-id instead of creating a provider Ticket.")
    parser.add_argument("--repository-id", action="append", default=[], help="Code Repository id to include. May be repeated.")
    parser.add_argument("--message", default="Run the AITeamOS plan_v7 LangGraph core-loop dogfood.")
    parser.add_argument("--recall-query", default="AITeamOS live provider dogfood approved asset recall")
    parser.add_argument(
        "--require-natural-handoff",
        action="store_true",
        help="Require the LangGraph core-loop run to produce a durable Ticket-backed Employee handoff.",
    )
    parser.add_argument("--expected-handoff-target", default="", help="Optional Employee id expected for the natural handoff.")
    parser.add_argument("--include-provider-smoke", action="store_true", help="Run read-only external provider smoke during dry-run.")
    parser.add_argument("--skip-provider-smoke", action="store_true", help="Skip the read-only external provider smoke preflight, including execute mode.")
    parser.add_argument("--provider-smoke-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--output", default="", help="Optional path to write the JSON response.")
    return parser


async def _main() -> int:
    args = _parser().parse_args()
    workspace_dir = Path(args.workspace_dir).expanduser().resolve()
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    profile = normalize_live_dogfood_profile(args.profile)
    executor_id = args.executor_id.strip() or _default_executor_for_profile(profile)
    message = args.message
    if message == _parser().get_default("message"):
        message = _default_message_for_profile(profile)
    require_provider_smoke = (args.execute and not args.skip_provider_smoke) or (args.include_provider_smoke and not args.skip_provider_smoke)
    require_repo_write_executor = (
        profile == REPO_WRITE_ADAPTER_PROFILE
        if not args.allow_non_mutating_executor
        else False
    )
    request = LiveProviderDogfoodRequest(
        execute=args.execute,
        profile=profile,
        confirm_env_var=args.confirm_env_var,
        langgraph_url=args.langgraph_url,
        assistant_id=args.assistant_id,
        employee_id=args.employee_id,
        worker_employee_id=args.worker_employee_id,
        reviewer_employee_id=args.reviewer_employee_id,
        executor_id=executor_id,
        ticket_id=args.ticket_id,
        create_ticket_if_missing=not args.no_create_ticket,
        repository_ids=args.repository_id,
        message=message,
        recall_query=args.recall_query,
        require_provider_smoke=require_provider_smoke,
        provider_smoke_timeout_seconds=args.provider_smoke_timeout_seconds,
        require_repo_write_executor=require_repo_write_executor,
        require_natural_handoff=args.require_natural_handoff,
        expected_handoff_target_employee_id=args.expected_handoff_target,
    )
    service = LiveProviderDogfoodService(workspace_dir=workspace_dir)
    agent_server: dict[str, Any] = {}
    process: subprocess.Popen[Any] | None = None
    if args.start_agent_server:
        agent_server, process = _start_agent_server(
            host=args.host,
            port=args.port,
            config=Path(args.config).expanduser().resolve(),
            langgraph_bin=args.langgraph_bin,
            workspace_dir=workspace_dir,
            assistant_id=args.assistant_id,
            server_log=args.server_log,
        )
        request = request.model_copy(update={"langgraph_url": agent_server["url"]})
        try:
            _wait_for_agent_server(
                agent_server["url"],
                timeout_seconds=args.startup_timeout,
                poll_interval=args.poll_interval,
            )
            agent_server["status"] = "ready"
        except Exception as exc:
            agent_server["status"] = "blocked"
            agent_server["error"] = str(exc)
            agent_server["server_log_tail"] = _tail(Path(agent_server["server_log"]))
            payload = {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "workspace_dir": str(workspace_dir),
                "agent_server": agent_server,
                "result": {
                    "status": "blocked",
                    "profile": profile,
                    "blockers": [
                        {
                            "reason": "langgraph_agent_server_not_ready",
                            "detail": str(exc),
                            "server_log": agent_server["server_log"],
                        }
                    ],
                },
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            if args.output:
                Path(args.output).expanduser().resolve().write_text(text, encoding="utf-8")
            print(text, end="")
            if process is not None:
                _terminate_process(process)
            return 2
    if args.readiness:
        readiness = await service.readiness(
            request.model_copy(update={"execute": True, "require_provider_smoke": False})
        )
        payload = {
            "schema": "aiteamos.live_provider_dogfood.readiness.cli.v1",
            "workspace_dir": str(workspace_dir),
            **({"agent_server": agent_server} if agent_server else {}),
            "result": readiness.model_dump(mode="json"),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            Path(args.output).expanduser().resolve().write_text(text, encoding="utf-8")
        print(text, end="")
        if process is not None:
            _terminate_process(process)
        return 0 if readiness.status == "ready" else 2

    try:
        response = await service.run(request)
        payload: dict[str, Any] = {
            "schema": "aiteamos.live_provider_dogfood.cli.v1",
            "workspace_dir": str(workspace_dir),
            **({"agent_server": agent_server} if agent_server else {}),
            "result": response.model_dump(mode="json"),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            Path(args.output).expanduser().resolve().write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if response.status in {"completed", "dry_run"} else 2
    finally:
        if process is not None:
            _terminate_process(process)


def _start_agent_server(
    *,
    host: str,
    port: int,
    config: Path,
    langgraph_bin: str,
    workspace_dir: Path,
    assistant_id: str,
    server_log: str,
) -> tuple[dict[str, Any], subprocess.Popen[Any]]:
    selected_port = port or _free_port(host)
    url = f"http://{host}:{selected_port}"
    log_path = Path(server_log).expanduser().resolve() if server_log else _temporary_log_path()
    command = [
        langgraph_bin,
        "dev",
        "--host",
        host,
        "--port",
        str(selected_port),
        "--config",
        str(config),
        "--no-reload",
        "--no-browser",
    ]
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    env["AITEAMOS_LANGGRAPH_URL"] = url
    env["AITEAMOS_LANGGRAPH_ASSISTANT_ID"] = assistant_id
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return (
        {
            "status": "starting",
            "url": url,
            "assistant_id": assistant_id,
            "command": command,
            "server_log": str(log_path),
        },
        process,
    )


def _wait_for_agent_server(url: str, *, timeout_seconds: float, poll_interval: float) -> None:
    from langgraph_sdk import get_sync_client

    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            client = get_sync_client(url=url)
            try:
                client.threads.create(metadata={"source": "aiteamos_live_provider_dogfood_readiness"})
            finally:
                close = getattr(client, "close", None)
                if close is not None:
                    close()
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(max(0.1, poll_interval))
    raise TimeoutError(f"LangGraph Agent Server was not ready within {timeout_seconds:.1f}s: {last_error}")


def _default_executor_for_profile(profile: str) -> str:
    if profile == REPO_WRITE_ADAPTER_PROFILE:
        return "codex_cli"
    return "langgraph"


def _default_message_for_profile(profile: str) -> str:
    if profile == CORE_LOOP_PROFILE:
        return (
            "Coordinate backend runtime ownership for AITeamOS production readiness with the existing team profiles "
            "and Ticket context, while keeping DeepSeek behind LangGraph."
        )
    return "Run the AITeamOS plan_v7 repo-write adapter dogfood loop."


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
