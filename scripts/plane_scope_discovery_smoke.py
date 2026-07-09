#!/usr/bin/env python3
"""Emit read-only Plane workspace/project discovery evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
SMOKE_SCHEMA = "aiteamos.plane_scope_discovery_smoke.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only Plane scope discovery evidence.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--output", default="", help="Optional path to write the JSON result.")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    try:
        payload = run_smoke(workspace_root=workspace_root)
    except Exception as exc:
        payload = {
            "schema": SMOKE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "workspace_dir": str(workspace_root),
            "error": str(exc),
        }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if payload["status"] == "passed" else 2


def run_smoke(*, workspace_root: Path) -> dict[str, Any]:
    from aiteamos_api.read.ticket_service import discover_ticket_backend_plane_scope  # noqa: PLC0415

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    discovery = discover_ticket_backend_plane_scope()
    result = discovery.model_dump(mode="json")
    suggestions = [item for item in result.get("suggestions", []) if isinstance(item, dict)]
    first_suggestion = suggestions[0] if suggestions else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    summary = {
        "discovery_status": str(result.get("status") or ""),
        "detail": str(result.get("detail") or ""),
        "api_key_env": str(result.get("api_key_env") or ""),
        "api_key_configured": bool(result.get("api_key_configured")),
        "external_calls": bool(result.get("external_calls")),
        "external_mutation": False,
        "workspace_count": _safe_int(evidence.get("workspace_count")),
        "project_count": _safe_int(evidence.get("project_count")),
        "suggestion_count": len(suggestions),
        "first_workspace_slug": str(first_suggestion.get("plane_workspace_slug") or ""),
        "first_project_id": str(first_suggestion.get("plane_project_id") or ""),
        "first_workspace_name": str(first_suggestion.get("workspace_name") or ""),
        "first_project_name": str(first_suggestion.get("project_name") or ""),
        "checks": [str(item) for item in result.get("checks", []) if str(item)],
        "setup_required": [str(item) for item in result.get("setup_required", []) if str(item)],
    }
    return {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "workspace_dir": str(workspace_root),
        "result": result,
        "summary": summary,
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
