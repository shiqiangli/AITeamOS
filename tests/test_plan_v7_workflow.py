from __future__ import annotations

from pathlib import Path

import yaml


def test_plan_v7_workflow_exposes_non_mutating_production_readiness_input() -> None:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "plan-v7-verification.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    event_config = workflow.get(True, {}) if True in workflow else workflow.get("on", {})
    inputs = event_config["workflow_dispatch"]["inputs"]

    production = inputs["production_readiness"]
    assert production["default"] == "false"
    assert production["options"] == ["false", "true"]

    run_script = workflow["jobs"]["plan-v7-verification"]["steps"][-2]["run"]
    assert 'inputs.production_readiness }}" = "true"' in run_script
    assert "ARGS=\"$ARGS --production-readiness\"" in run_script
    assert "--include-live-provider-dogfood" not in run_script
