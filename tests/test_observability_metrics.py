from __future__ import annotations

from pathlib import Path
import re
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import rebuild_workspace_indexes, render_prometheus_metrics


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT / ".aiteamos"


class ObservabilityMetricsTest(unittest.TestCase):
    def test_metrics_endpoint_exposes_prometheus_naming_baseline(self) -> None:
        response = TestClient(create_app(WORKSPACE)).get("/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        text = response.text
        for metric_name in [
            "aiteamos_run_state_total",
            "aiteamos_model_call_cost_usd_total",
            "aiteamos_index_rebuild_seconds",
            "aiteamos_worker_heartbeat_lag_seconds",
        ]:
            self.assertIn(f"# HELP {metric_name}", text)
            self.assertIn(f"# TYPE {metric_name}", text)

        self.assertIn('aiteamos_run_state_total{state="FINISHED"}', text)
        self.assertIn('aiteamos_model_call_cost_usd_total{provider="unknown",model="unknown"} 0', text)
        self.assertRegex(text, r"aiteamos_index_rebuild_seconds [0-9.]+")
        self.assertIn('aiteamos_worker_heartbeat_lag_seconds{run="none"', text)

    def test_workspace_index_rebuild_records_duration_for_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            result = rebuild_workspace_indexes(workspace)
            text = render_prometheus_metrics(workspace)

            self.assertGreaterEqual(result["durationSeconds"], 0)
            self.assertTrue((workspace / "indexes" / "index_metadata.json").exists())
            match = re.search(r"^aiteamos_index_rebuild_seconds ([0-9.]+)$", text, flags=re.MULTILINE)
            self.assertIsNotNone(match)
            self.assertGreaterEqual(float(match.group(1)), 0.0)


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        WORKSPACE,
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


if __name__ == "__main__":
    unittest.main()
