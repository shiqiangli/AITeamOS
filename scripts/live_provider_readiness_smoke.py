#!/usr/bin/env python3
"""Emit non-mutating live provider dogfood readiness evidence."""

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
SMOKE_SCHEMA = "aiteamos.live_provider_readiness_smoke.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only live provider dogfood readiness evidence.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument(
        "--profile",
        default=os.environ.get("AITEAMOS_LIVE_DOGFOOD_PROFILE", "core-loop"),
        choices=["core-loop", "core_loop", "repo-write-adapter", "repo_write_adapter"],
    )
    parser.add_argument("--executor-id", default=os.environ.get("AITEAMOS_LIVE_DOGFOOD_EXECUTOR", ""))
    parser.add_argument("--confirm-env-var", default="AITEAMOS_LIVE_PROVIDER_DOGFOOD")
    parser.add_argument("--output", default="", help="Optional path to write the JSON result.")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    try:
        payload = asyncio.run(
            run_smoke(
                workspace_root=workspace_root,
                profile=args.profile,
                executor_id=args.executor_id,
                confirm_env_var=args.confirm_env_var,
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


async def run_smoke(*, workspace_root: Path, profile: str, executor_id: str, confirm_env_var: str) -> dict[str, Any]:
    from aiteamos_api.read.live_provider_dogfood_service import (
        REPO_WRITE_ADAPTER_PROFILE,
        LiveProviderDogfoodRequest,
        LiveProviderDogfoodService,
        normalize_live_dogfood_profile,
    )

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    normalized_profile = normalize_live_dogfood_profile(profile)
    selected_executor_id = executor_id.strip() or ("codex_cli" if normalized_profile == REPO_WRITE_ADAPTER_PROFILE else "langgraph")
    request = LiveProviderDogfoodRequest(
        execute=True,
        profile=normalized_profile,
        confirm_env_var=confirm_env_var,
        executor_id=selected_executor_id,
        require_provider_smoke=False,
        require_repo_write_executor=normalized_profile == REPO_WRITE_ADAPTER_PROFILE,
    )
    readiness = await LiveProviderDogfoodService(workspace_dir=workspace_root).readiness(request)
    result = readiness.model_dump(mode="json")
    selected_preflight = _record(result.get("selected_executor_preflight"))
    mutation_gate = _record(result.get("mutation_gate"))
    provider_prerequisites = _record(result.get("provider_prerequisites"))
    ticket_backend = _record(provider_prerequisites.get("ticket_backend"))
    release_target = _record(ticket_backend.get("release_target"))
    plane_ticket_setup = _record(provider_prerequisites.get("plane_ticket_backend_setup"))
    memory_backend = _record(provider_prerequisites.get("memory_backend"))
    provider_smoke = _record(provider_prerequisites.get("provider_smoke"))
    result_summary = _record(result.get("summary"))
    blockers = _records(result.get("blockers"))
    repo_candidates = _records(result.get("repo_write_executor_candidates"))
    ready_candidate_ids = [str(item.get("executor_id") or "") for item in repo_candidates if item.get("status") == "ready"]
    return {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "workspace_dir": str(workspace_root),
        "result": result,
        "summary": {
            "readiness_status": str(result.get("status") or ""),
            "profile": str(result.get("profile") or normalized_profile),
            "ready_for_live_dogfood": result.get("status") == "ready",
            "selected_executor_id": str(result.get("selected_executor_id") or ""),
            "selected_executor_status": str(selected_preflight.get("status") or ""),
            "selected_executor_blocker_reasons": _blocker_reasons(selected_preflight.get("blockers")),
            "repo_write_candidate_count": len(repo_candidates),
            "repo_write_ready_count": len(ready_candidate_ids),
            "repo_write_ready_executor_ids": ready_candidate_ids,
            "ticket_backend_status": str(ticket_backend.get("status") or ""),
            "ticket_backend_mode": str(ticket_backend.get("mode") or ""),
            "ticket_backend_provider": str(ticket_backend.get("provider") or ""),
            "ticket_backend_release_target_status": str(
                result_summary.get("ticket_backend_release_target_status")
                or release_target.get("status")
                or ""
            ),
            "ticket_backend_release_target_ready": bool(
                result_summary.get("ticket_backend_release_target_ready")
                if "ticket_backend_release_target_ready" in result_summary
                else release_target.get("ready")
            ),
            "ticket_backend_release_target_blockers": _unique_strings(
                result_summary.get("ticket_backend_release_target_blockers")
                if "ticket_backend_release_target_blockers" in result_summary
                else release_target.get("blockers")
            ),
            "ticket_backend_release_target_setup_action": str(
                result_summary.get("ticket_backend_release_target_setup_action")
                or release_target.get("setup_action")
                or ""
            ),
            "plane_ticket_backend_selected": bool(result_summary.get("plane_ticket_backend_selected")),
            "plane_ticket_backend_setup_status": str(plane_ticket_setup.get("status") or ""),
            "plane_ticket_backend_setup_required": _unique_strings(plane_ticket_setup.get("setup_required")),
            "plane_ticket_backend_configured": bool(result_summary.get("plane_ticket_backend_configured")),
            "plane_ticket_workspace_configured": bool(result_summary.get("plane_ticket_workspace_configured")),
            "plane_ticket_project_configured": bool(result_summary.get("plane_ticket_project_configured")),
            "plane_ticket_api_key_configured": bool(result_summary.get("plane_ticket_api_key_configured")),
            "plane_ticket_scope_status": str(result_summary.get("plane_ticket_scope_status") or plane_ticket_setup.get("code_repository_scope_status") or ""),
            "plane_ticket_scope_candidate_count": _safe_int(
                result_summary.get("plane_ticket_scope_candidate_count")
                if "plane_ticket_scope_candidate_count" in result_summary
                else plane_ticket_setup.get("code_repository_scope_candidate_count")
            ),
            "plane_ticket_scope_missing_count": _safe_int(
                result_summary.get("plane_ticket_scope_missing_count")
                if "plane_ticket_scope_missing_count" in result_summary
                else plane_ticket_setup.get("code_repository_scope_missing_count")
            ),
            "plane_ticket_scope_setup_action": str(
                result_summary.get("plane_ticket_scope_setup_action")
                or plane_ticket_setup.get("code_repository_scope_setup_action")
                or ""
            ),
            "memory_backend_status": str(memory_backend.get("status") or ""),
            "provider_smoke_status": str(provider_smoke.get("status") or ""),
            "mutation_gate_open": bool(mutation_gate.get("open")),
            "mutation_gate_execute_flag": bool(mutation_gate.get("execute_flag")),
            "mutation_gate_confirm_env_var": str(mutation_gate.get("confirm_env_var") or confirm_env_var),
            "mutation_gate_confirm_env_configured": bool(mutation_gate.get("confirm_env_configured")),
            "mutation_gate_blocker_reason": str(_record(mutation_gate.get("blocker")).get("reason") or ""),
            "blocker_count": len(blockers),
            "blocker_reasons": _blocker_reasons(blockers),
            "blocker_scopes": _unique_strings([item.get("scope") for item in blockers]),
        },
    }


def _write_output(payload: dict[str, Any], output: str) -> None:
    if not output:
        return
    path = Path(output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _blocker_reasons(value: Any) -> list[str]:
    return _unique_strings([item.get("reason") for item in _records(value)])


def _unique_strings(value: Any) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in value if isinstance(value, list) else []:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
