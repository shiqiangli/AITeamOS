#!/usr/bin/env python3
"""Emit read-only RuntimeExecutor registry and live readiness evidence."""

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
SMOKE_SCHEMA = "aiteamos.runtime_registry_smoke.v1"
SECRET_KEY_TOKENS = ("authorization", "password", "secret", "token", "api_key")
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only RuntimeExecutor registry evidence.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR") or str(ROOT_DIR))
    parser.add_argument("--output", default="", help="Optional path to write the redacted JSON payload.")
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).expanduser().resolve()
    try:
        payload = asyncio.run(run_smoke(workspace_dir=workspace_dir))
    except Exception as exc:
        payload = {
            "schema": SMOKE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "workspace_dir": str(workspace_dir),
            "error": str(exc),
        }
    redacted = redact(payload)
    text = json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if payload.get("status") == "passed" else 2


async def run_smoke(*, workspace_dir: Path) -> dict[str, Any]:
    from aiteamos_api.read.runtime_executor_routes import list_runtime_executors

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    registry = await list_runtime_executors()
    result = registry.model_dump(mode="json")
    live_readiness = _record(result.get("live_provider_readiness"))
    live_summary = _record(live_readiness.get("summary"))
    mutation_gate = _record(live_readiness.get("mutation_gate"))
    provider_prerequisites = _record(live_readiness.get("provider_prerequisites"))
    return {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "workspace_dir": str(workspace_dir),
        "result": result,
        "summary": {
            "executor_count": _to_int(_record(result.get("summary")).get("executor_count")) or len(_records(result.get("executors"))),
            "ready_count": _to_int(_record(result.get("summary")).get("ready_count")),
            "blocked_count": _to_int(_record(result.get("summary")).get("blocked_count")),
            "runtime_boundary": str(_record(result.get("summary")).get("runtime_boundary") or ""),
            "executor_ids": _unique_strings([item.get("executor_id") for item in _records(result.get("executors"))]),
            "blocker_executor_ids": _unique_strings([item.get("executor_id") for item in _records(result.get("blockers"))]),
            "live_provider_status": str(live_readiness.get("status") or ""),
            "live_provider_selected_executor_id": str(live_readiness.get("selected_executor_id") or ""),
            "live_provider_blocker_count": _to_int(live_summary.get("blocker_count")),
            "live_provider_blocker_reasons": _strings(live_readiness.get("reasons")),
            "live_provider_setup_required": _strings(live_readiness.get("setup_required")),
            "live_provider_mutation_gate_open": bool(mutation_gate.get("open")),
            "live_provider_mutation_gate_confirm_env_var": str(mutation_gate.get("confirm_env_var") or ""),
            "live_provider_ticket_backend_status": str(provider_prerequisites.get("ticket_backend_status") or ""),
            "live_provider_memory_backend_status": str(provider_prerequisites.get("memory_backend_status") or ""),
            "live_provider_provider_smoke_status": str(provider_prerequisites.get("provider_smoke_status") or ""),
            "repo_write_ready_count": _to_int(live_summary.get("repo_write_ready_count")),
            "repo_write_candidate_count": _to_int(live_summary.get("repo_write_candidate_count")),
            "repo_write_candidate_executor_ids": _unique_strings(
                [item.get("executor_id") for item in _records(live_readiness.get("repo_write_candidates"))]
            ),
        },
    }


def redact(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_key(key_text.lower(), item):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = redact(item, parent_key=key_text)
        return redacted
    if isinstance(value, list):
        return [redact(item, parent_key=parent_key) for item in value]
    return value


def _is_secret_key(lowered_key: str, value: Any) -> bool:
    if lowered_key in {"missing_env", "setup_required", "env_vars"}:
        return False
    if lowered_key.endswith("_configured") or isinstance(value, bool):
        return False
    if lowered_key.endswith("_env") or lowered_key.endswith("_env_vars"):
        return False
    return any(token in lowered_key for token in SECRET_KEY_TOKENS)


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return _unique_strings(value if isinstance(value, list) else [])


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            results.append(text)
    return results


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
