#!/usr/bin/env python3
"""Run the AITeamOS read-only environment smoke without starting the API server."""

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
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))

from aiteamos_api.read.provider_conformance_service import provider_environment_smoke  # noqa: E402


SECRET_KEY_TOKENS = ("authorization", "password", "secret", "token", "api_key")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AITeamOS environment smoke and print redacted JSON.")
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Opt in to read-only external Plane / Graphiti smoke when those providers are configured.",
    )
    parser.add_argument(
        "--workspace-dir",
        default=os.environ.get("AITEAMOS_WORKSPACE_DIR") or str(ROOT_DIR),
        help="AITeamOS workspace directory. Defaults to AITEAMOS_WORKSPACE_DIR or repo root.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write the same redacted JSON payload.",
    )
    parser.add_argument(
        "--fail-on-blocker",
        action="store_true",
        help="Exit non-zero when the environment smoke status is not passed or warning.",
    )
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).resolve()
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    result = asyncio.run(provider_environment_smoke(include_external=args.include_external))
    payload = {
        "schema": "aiteamos.environment_smoke.cli.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": str(workspace_dir),
        "include_external": bool(args.include_external),
        "result": result.model_dump(mode="json"),
    }
    redacted = redact(payload)
    text = json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if args.fail_on_blocker and result.status not in {"passed", "warning"}:
        return 2
    return 0


def redact(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if _is_secret_key(lowered, item):
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


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
