from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from aiteamos_workspace import append_run_event, cost_alert_candidates, load_workspace, route_cost_alerts


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT / ".aiteamos"


class ModelCostAlertTest(unittest.TestCase):
    def test_cost_threshold_candidates_route_deduplicated_cost_alert_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_usd_budget_policy(workspace, "RUN-0001", "tiny-run-budget")
            append_run_event(
                workspace,
                "RUN-0001",
                {
                    "type": "model.call.completed",
                    "provider": "openai",
                    "model": "example-model",
                    "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
                    "cost_usd": 0.06,
                    "latency_ms": 25,
                    "ts": "2026-05-22T00:00:00Z",
                },
            )

            overview = cost_alert_candidates(workspace)
            self.assertEqual(overview["metricName"], "aiteamos_model_call_cost_usd_total")
            self.assertEqual(overview["summary"]["routable"], 1)
            candidate = overview["candidates"][0]
            self.assertEqual(candidate["policy"], "tiny-run-budget")
            self.assertEqual(candidate["thresholdName"], "maxUsdPerRun")
            self.assertEqual(candidate["thresholdKind"], "hard")
            self.assertEqual(candidate["costUsd"], 0.06)
            self.assertEqual(candidate["limitUsd"], 0.05)
            self.assertEqual(candidate["targetMembers"], ["architect"])

            dry_run = route_cost_alerts(workspace, actor_member="team-execution-service", dry_run=True)
            self.assertEqual(dry_run["createdMessages"], [])
            self.assertFalse(
                [
                    message
                    for message in load_workspace(workspace).member_messages.values()
                    if message.spec.messageType == "cost-alert"
                ]
            )

            routed = route_cost_alerts(workspace, actor_member="team-execution-service", dry_run=False)
            self.assertEqual(len(routed["createdMessages"]), 1)
            index = load_workspace(workspace)
            messages = [message for message in index.member_messages.values() if message.spec.messageType == "cost-alert"]
            self.assertEqual(len(messages), 1)
            message = messages[0]
            self.assertEqual(message.spec.fromMember, "team-execution-service")
            self.assertEqual(message.spec.toMembers, ["architect"])
            self.assertEqual(message.spec.audit["costAlertDedupeKey"], candidate["dedupeKey"])
            self.assertEqual(message.spec.audit["metricName"], "aiteamos_model_call_cost_usd_total")

            duplicate = route_cost_alerts(workspace, actor_member="team-execution-service", dry_run=False)
            self.assertEqual(duplicate["createdMessages"], [])
            self.assertEqual(duplicate["summary"]["suppressed"], 1)
            self.assertEqual(
                len(
                    [
                        message
                        for message in load_workspace(workspace).member_messages.values()
                        if message.spec.messageType == "cost-alert"
                    ]
                ),
                1,
            )


def _copy_workspace(temp_dir: Path) -> Path:
    target = temp_dir / ".aiteamos"
    shutil.copytree(
        WORKSPACE,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return target


def _write_usd_budget_policy(workspace: Path, run_id: str, name: str) -> None:
    index = load_workspace(workspace)
    run = index.runs[run_id]
    path = workspace / "budget_policies" / f"{name}.yaml"
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "BudgetPolicy",
        "metadata": {"name": name},
        "spec": {
            "scope": {"task": run.spec.task},
            "limits": {"softUsdPerRun": 0.03, "maxUsdPerRun": 0.05},
            "enforcement": {"onSoftLimit": "warn", "onHardLimit": "stop-run"},
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
