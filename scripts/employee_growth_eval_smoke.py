#!/usr/bin/env python3
"""Emit read-only Employee growth evidence for Plan v8 Track E."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
SMOKE_SCHEMA = "aiteamos.employee_growth_eval_smoke.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))

from aiteamos_api.read.employee_growth_eval_service import employee_growth_eval_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only Employee growth evidence for Plan v8 Track E.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--employee-id", default="", help="Optional Employee id to evaluate. Defaults to the strongest local evidence.")
    parser.add_argument("--output", default="", help="Optional path to write the JSON payload.")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    try:
        result = employee_growth_eval_report(workspace_dir=workspace_root, employee_id=args.employee_id)
        payload = {
            "schema": SMOKE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workspace_dir": str(workspace_root),
            "result": result.model_dump(mode="json"),
            "status": result.status,
            "summary": result.summary.model_dump(mode="json"),
        }
    except Exception as exc:
        payload = {
            "schema": SMOKE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workspace_dir": str(workspace_root),
            "status": "blocked",
            "error": str(exc),
        }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 2 if payload.get("status") in {"blocked", "failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
