from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from aiteamos_workspace import (
    create_run,
    create_task,
    evaluate_run_review_gate,
    evaluate_worker_readiness,
    load_workspace,
    update_run,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHITECT_MEMBER = "architect"
ARCHITECTURE_ASSIGNMENT = "aiteamos-architecture"
API_SURFACE_SUITE = "aiteamos-eval-suite-api-surface"
API_SURFACE_RESULT = "ERES-20260522T212401445"
APP_SURFACE_PATH = "services/api/aiteamos_api/app.py"


class ApiSurfaceEvalBootstrapTest(unittest.TestCase):
    def test_architecture_assignment_declares_api_surface_eval_requirement(self) -> None:
        index = load_workspace(REPO_ROOT / ".aiteamos")

        suite = index.eval_suites[API_SURFACE_SUITE]
        assignment = index.assignments[ARCHITECTURE_ASSIGNMENT]
        requirement = assignment.spec.evalSuiteRequirements[0]

        self.assertEqual(suite.spec.assignments, [ARCHITECTURE_ASSIGNMENT])
        self.assertEqual(suite.spec.cases[0].input["command"], "PYTHONPATH=packages/schema:packages/workspace:services/api:services/worker:. python -m unittest tests.test_api_surface")
        self.assertEqual(requirement.evalSuite, API_SURFACE_SUITE)
        self.assertEqual(requirement.paths, [APP_SURFACE_PATH])
        self.assertEqual(requirement.minimumPassRate, 1.0)

    def test_review_gate_blocks_app_py_patch_when_latest_api_surface_eval_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_failing_api_surface_result(workspace)
            run = _create_architecture_run(workspace)
            _make_diff_patch_reviewable(workspace, run.object_id, _app_surface_diff())

            gate = evaluate_run_review_gate(workspace, run.object_id)

            self.assertFalse(gate["readyForHumanReview"])
            self.assertEqual(gate["evalSuiteRequirements"][0]["status"], "fail")
            self.assertEqual(gate["evalSuiteRequirements"][0]["lastResultId"], "ERES-20990101T000000000")
            self.assertTrue(
                [
                    check
                    for check in gate["checks"]
                    if check["name"] == "eval-suite-requirement" and check["status"] == "fail"
                ]
            )

    def test_review_gate_allows_app_py_patch_when_api_surface_eval_is_green(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_passing_api_surface_result(workspace)
            run = _create_architecture_run(workspace)
            _make_diff_patch_reviewable(workspace, run.object_id, _app_surface_diff())

            gate = evaluate_run_review_gate(workspace, run.object_id)

            self.assertTrue(gate["readyForHumanReview"])
            self.assertEqual(gate["evalSuiteRequirements"][0]["status"], "pass")
            self.assertEqual(gate["evalSuiteRequirements"][0]["lastResultId"], API_SURFACE_RESULT)
            self.assertTrue(
                [
                    check
                    for check in gate["checks"]
                    if check["name"] == "eval-suite-requirement" and check["status"] == "pass"
                ]
            )

    def test_worker_readiness_blocks_app_py_plan_when_latest_api_surface_eval_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_failing_api_surface_result(workspace)
            run = _create_architecture_run(
                workspace,
                extra_spec={"worker": {"changedPaths": [APP_SURFACE_PATH]}},
            )

            readiness = evaluate_worker_readiness(workspace, run.object_id)

            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["evalSuiteRequirements"][0]["status"], "fail")
            self.assertTrue(
                [
                    check
                    for check in readiness["checks"]
                    if check["name"] == "eval-suite-requirement" and check["status"] == "fail"
                ]
            )


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _create_architecture_run(workspace: Path, extra_spec: dict | None = None) -> object:
    task = create_task(
        workspace,
        title="API surface EvalSuite bootstrap check",
        assigned_member=ARCHITECT_MEMBER,
        assignment=ARCHITECTURE_ASSIGNMENT,
        execution_mode="managed_llm",
        acceptance=["Review gate blocks app.py changes unless the API surface EvalSuite is green."],
    )
    return create_run(workspace, task_id=task.object_id, mode="managed_llm", extra_spec=extra_spec)


def _make_diff_patch_reviewable(workspace: Path, run_id: str, diff_text: str) -> None:
    run_dir = workspace / "runs" / run_id
    (run_dir / "diff.patch").write_text(diff_text, encoding="utf-8")
    update_run(workspace, run_id, {"status": "REVIEW", "reviewTarget": {"type": "diff_patch"}})


def _write_failing_api_surface_result(workspace: Path) -> None:
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "EvalResult",
        "metadata": {
            "id": "ERES-20990101T000000000",
            "createdAt": "2099-01-01T00:00:00+08:00",
        },
        "spec": {
            "evalSuite": API_SURFACE_SUITE,
            "project": "aiteamos",
            "evaluatedAt": "2099-01-01T00:00:00+08:00",
            "member": ARCHITECT_MEMBER,
            "assignment": ARCHITECTURE_ASSIGNMENT,
            "status": "fail",
            "totalCases": 1,
            "passedCases": 0,
            "failedCases": 1,
            "passRate": 0.0,
            "caseResults": [
                {
                    "caseId": "api-surface-contract",
                    "caseTitle": "API surface test remains green for app.py changes",
                    "status": "fail",
                    "score": 0.0,
                    "evidence": ["tests/test_api_surface.py"],
                    "message": "Simulated API surface regression for review gate fail-closed coverage.",
                }
            ],
            "evidence": [APP_SURFACE_PATH, "tests/test_api_surface.py"],
            "summary": "Simulated latest API surface EvalResult failure.",
        },
    }
    path = workspace / "eval_results" / "ERES-20990101T000000000.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_passing_api_surface_result(workspace: Path) -> None:
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "EvalResult",
        "metadata": {
            "id": API_SURFACE_RESULT,
            "createdAt": "2099-01-01T00:00:00+08:00",
        },
        "spec": {
            "evalSuite": API_SURFACE_SUITE,
            "project": "aiteamos",
            "evaluatedAt": "2099-01-01T00:00:00+08:00",
            "member": ARCHITECT_MEMBER,
            "assignment": ARCHITECTURE_ASSIGNMENT,
            "status": "pass",
            "totalCases": 1,
            "passedCases": 1,
            "failedCases": 0,
            "passRate": 1.0,
            "caseResults": [
                {
                    "caseId": "api-surface-contract",
                    "caseTitle": "API surface test remains green for app.py changes",
                    "status": "pass",
                    "score": 1.0,
                    "evidence": ["tests/test_api_surface.py"],
                }
            ],
            "evidence": [APP_SURFACE_PATH, "tests/test_api_surface.py"],
            "summary": "Temporary API surface EvalResult for review gate green-path coverage.",
        },
    }
    path = workspace / "eval_results" / f"{API_SURFACE_RESULT}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _app_surface_diff() -> str:
    return "\n".join(
        [
            f"diff --git a/{APP_SURFACE_PATH} b/{APP_SURFACE_PATH}",
            "index 1111111..2222222 100644",
            f"--- a/{APP_SURFACE_PATH}",
            f"+++ b/{APP_SURFACE_PATH}",
            "@@ -1 +1 @@",
            "-from .routes import create_app",
            "+from .routes import create_app as create_app",
            "",
        ]
    )


if __name__ == "__main__":
    unittest.main()
