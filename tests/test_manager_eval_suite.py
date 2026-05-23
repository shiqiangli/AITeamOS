from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_schema import ManagerInputBundle
from aiteamos_workspace import load_workspace, manager_evaluation_signal, manager_input_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGER_SUITE = "aiteamos-manager-recommendation-quality"
MANAGER_RESULT = "ERES-20260522T215837092"


class ManagerEvalSuiteTest(unittest.TestCase):
    def test_manager_eval_suite_pairs_recommendations_with_human_outcomes(self) -> None:
        index = load_workspace(REPO_ROOT / ".aiteamos")

        suite = index.eval_suites[MANAGER_SUITE]
        result = index.eval_results[MANAGER_RESULT]
        signal = manager_evaluation_signal(index, manager="aiteamos-manager", project="aiteamos", assignment="aiteamos-manager")

        self.assertEqual(suite.spec.members, ["aiteamos-manager"])
        self.assertEqual(suite.spec.assignments, ["aiteamos-manager"])
        self.assertEqual(result.spec.status, "pass")
        self.assertEqual(result.spec.evalSuite, MANAGER_SUITE)
        self.assertEqual(signal["recommendationWindow"]["total"], 2)
        self.assertEqual(signal["recommendationWindow"]["accepted"], 1)
        self.assertEqual(signal["recommendationWindow"]["rejected"], 1)
        self.assertEqual(signal["recommendationWindow"]["acceptanceRate"], 0.5)
        self.assertEqual(signal["modelProfileSelection"]["modelProfile"], "openai-gpt-5.5-xhigh")
        self.assertEqual(signal["modelProfileSelection"]["basis"], "manager-eval-suite")
        self.assertEqual(signal["modelProfileSelection"]["lastResultId"], MANAGER_RESULT)
        self.assertEqual(
            {row["outcome"] for row in signal["recommendationPairs"]},
            {"accepted", "rejected"},
        )

    def test_manager_inbox_embeds_eval_signal_without_writing_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            before = _manifest_snapshot(workspace)
            bundle = ManagerInputBundle.model_validate(
                manager_input_bundle(
                    load_workspace(workspace),
                    project="aiteamos",
                    assignment="aiteamos-manager",
                )
            )

            self.assertTrue(bundle.readOnly)
            self.assertEqual(bundle.managerEvaluation["modelProfileSelection"]["lastResultId"], MANAGER_RESULT)
            self.assertEqual(bundle.managerEvaluation["recommendationWindow"]["accepted"], 1)
            self.assertEqual(_manifest_snapshot(workspace), before)

    def test_manager_evaluation_api_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            before = _manifest_snapshot(workspace)

            response = TestClient(create_app(workspace)).get(
                "/manager/evaluation",
                params={"project": "aiteamos", "assignment": "aiteamos-manager", "manager": "aiteamos-manager", "limit": 5},
            )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertTrue(payload["readOnly"])
            self.assertEqual(payload["modelProfileSelection"]["lastResultId"], MANAGER_RESULT)
            self.assertEqual(payload["recommendationWindow"]["rejected"], 1)
            self.assertIn(".aiteamos/eval_results/ERES-20260522T215837092.yaml", payload["sourceRefs"])
            self.assertEqual(_manifest_snapshot(workspace), before)


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _manifest_snapshot(workspace: Path) -> list[str]:
    return sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.is_file())


if __name__ == "__main__":
    unittest.main()
