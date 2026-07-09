#!/usr/bin/env python3
"""Run a gated Plane Ticket handoff/report action smoke.

This script is intentionally a thin wrapper around the existing Ticket service.
It does not call Plane directly and does not add another provider adapter.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
SMOKE_SCHEMA = "aiteamos.plane_ticket_action_smoke.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a gated Plane Ticket handoff/report action smoke.")
    parser.add_argument("--execute", action="store_true", help="Attempt live Plane writes when the confirmation env var is also set.")
    parser.add_argument("--confirm-env-var", default="AITEAMOS_LIVE_PROVIDER_DOGFOOD")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--ticket-id", default="", help="Existing AITeamOS Ticket id. If omitted, a smoke Ticket may be created.")
    parser.add_argument("--no-create-ticket", action="store_true", help="Require --ticket-id instead of creating a smoke Ticket.")
    parser.add_argument("--from-employee-id", default="clara")
    parser.add_argument("--from-role", default="AI Team OS Manager")
    parser.add_argument("--to-employee-id", default="alex")
    parser.add_argument("--to-role", default="AI RD / Implementer")
    parser.add_argument("--source-run-id", default="plane-ticket-action-smoke")
    parser.add_argument("--report-content", default="AITeamOS Plane action smoke for Ticket handoff/report writes.")
    parser.add_argument("--output", default="", help="Optional path to write the JSON response.")
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).expanduser().resolve()
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)

    from aiteamos_api.read.ticket_service import (  # noqa: PLC0415
        TicketProviderActionSmokeRequest,
        ticket_provider_action_smoke,
    )

    request = TicketProviderActionSmokeRequest(
        execute=args.execute,
        confirm_env_var=args.confirm_env_var,
        ticket_id=args.ticket_id,
        create_ticket_if_missing=not args.no_create_ticket,
        from_employee_id=args.from_employee_id,
        from_role=args.from_role,
        to_employee_id=args.to_employee_id,
        to_role=args.to_role,
        source_run_id=args.source_run_id,
        report_content=args.report_content,
    )
    response = ticket_provider_action_smoke(request)
    payload = {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": str(workspace_dir),
        "result": response.model_dump(mode="json"),
        "summary": response.summary,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if response.status in {"passed", "dry_run", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
