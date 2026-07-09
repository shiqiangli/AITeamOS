#!/usr/bin/env python3
"""Emit the read-only Plan v8 live-provider repeated-soak plan."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
SOAK_PLAN_SCHEMA = "aiteamos.live_provider_soak_plan.cli.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))

from aiteamos_api.read.live_provider_soak_plan_service import live_provider_soak_plan_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the read-only AITeamOS live-provider soak plan.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR") or str(ROOT_DIR))
    parser.add_argument("--output", default="", help="Optional path to write the JSON payload.")
    parser.add_argument(
        "--fail-on-blocker",
        action="store_true",
        help="Exit non-zero when the soak plan is blocked.",
    )
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    result = asyncio.run(live_provider_soak_plan_report(workspace_dir=workspace_root))
    payload = {
        "schema": SOAK_PLAN_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": str(workspace_root),
        "result": result.model_dump(mode="json"),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if args.fail_on_blocker and result.status == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
