#!/usr/bin/env python3
"""Emit the aggregate Plan v8 artifact evidence summary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
SUMMARY_SCHEMA = "aiteamos.plan_v8_artifact_summary.cli.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))

from aiteamos_api.read.plan_v8_artifact_service import plan_v8_artifact_summary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize AITeamOS Plan v8 evidence artifacts.")
    parser.add_argument(
        "--workspace-dir",
        default=os.environ.get("AITEAMOS_WORKSPACE_DIR") or str(ROOT_DIR),
        help="AITeamOS workspace directory. Defaults to AITEAMOS_WORKSPACE_DIR or repo root.",
    )
    parser.add_argument("--limit", type=int, default=8, help="Maximum recent records to include.")
    parser.add_argument("--output", default="", help="Optional path to write the JSON payload.")
    parser.add_argument(
        "--fail-on-gap",
        action="store_true",
        help="Exit non-zero when the artifact summary is blocked.",
    )
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    result = plan_v8_artifact_summary(workspace_dir=workspace_root, limit=max(0, args.limit))
    payload = {
        "schema": SUMMARY_SCHEMA,
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
    if args.fail_on_gap and result.status == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
