from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from aiteamos_workspace import (
    create_run,
    create_task,
    evaluate_run_review_gate,
    evaluate_worker_readiness,
    update_run,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
EVAL_RESULT_ID = "ERES-20260522T204421556"


class EvalSuiteRequirementGateTest(unittest.TestCase):
    def test_worker_readiness_blocks_matching_paths_without_passing_eval_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _remove_schema_contract_result(workspace)
            run = _create_backend_run(
                workspace,
                extra_spec={"worker": {"changedPaths": ["packages/workspace/runtime_change.py"]}},
            )

            readiness = evaluate_worker_readiness(workspace, run.object_id)

            self.assertFalse(readiness["ready"])
            self.assertEqual(readiness["evalSuiteRequirements"][0]["status"], "fail")
            self.assertEqual(readiness["evalSuiteRequirements"][0]["matchedPaths"], ["packages/workspace/runtime_change.py"])
            self.assertTrue(
                [
                    check
                    for check in readiness["checks"]
                    if check["name"] == "eval-suite-requirement" and check["status"] == "fail"
                ]
            )

    def test_review_gate_blocks_matching_diff_without_passing_eval_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _remove_schema_contract_result(workspace)
            run = _create_backend_run(workspace)
            _make_diff_patch_reviewable(workspace, run.object_id, _workspace_diff())

            gate = evaluate_run_review_gate(workspace, run.object_id)

            self.assertFalse(gate["readyForHumanReview"])
            self.assertEqual(gate["evalSuiteRequirements"][0]["status"], "fail")
            self.assertTrue(
                [
                    check
                    for check in gate["checks"]
                    if check["name"] == "eval-suite-requirement" and check["status"] == "fail"
                ]
            )

    def test_review_gate_passes_matching_diff_with_green_eval_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            _make_diff_patch_reviewable(workspace, run.object_id, _workspace_diff())

            gate = evaluate_run_review_gate(workspace, run.object_id)

            self.assertTrue(gate["readyForHumanReview"])
            self.assertEqual(gate["evalSuiteRequirements"][0]["status"], "pass")
            self.assertEqual(gate["evalSuiteRequirements"][0]["lastResultId"], EVAL_RESULT_ID)
            self.assertTrue(
                [
                    check
                    for check in gate["checks"]
                    if check["name"] == "eval-suite-requirement" and check["status"] == "pass"
                ]
            )

    def test_review_gate_skips_eval_requirement_for_unmatched_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _remove_schema_contract_result(workspace)
            run = _create_backend_run(workspace)
            _make_diff_patch_reviewable(workspace, run.object_id, _services_diff())

            gate = evaluate_run_review_gate(workspace, run.object_id)

            self.assertTrue(gate["readyForHumanReview"])
            self.assertEqual(gate["evalSuiteRequirements"][0]["status"], "skip")
            self.assertFalse([check for check in gate["checks"] if check["name"] == "eval-suite-requirement"])


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _create_backend_run(workspace: Path, extra_spec: dict | None = None) -> object:
    task = create_task(
        workspace,
        title="EvalSuite requirement gate task",
        assigned_member=BACKEND_MEMBER,
        assignment=BACKEND_ASSIGNMENT,
        execution_mode="managed_llm",
        acceptance=["EvalSuite requirements gate worker and review readiness."],
    )
    return create_run(workspace, task_id=task.object_id, mode="managed_llm", extra_spec=extra_spec)


def _remove_schema_contract_result(workspace: Path) -> None:
    (workspace / "eval_results" / f"{EVAL_RESULT_ID}.yaml").unlink()


def _make_diff_patch_reviewable(workspace: Path, run_id: str, diff_text: str) -> None:
    run_dir = workspace / "runs" / run_id
    (run_dir / "diff.patch").write_text(diff_text, encoding="utf-8")
    update_run(workspace, run_id, {"status": "REVIEW", "reviewTarget": {"type": "diff_patch"}})


def _workspace_diff() -> str:
    return "\n".join(
        [
            "diff --git a/packages/workspace/runtime_change.py b/packages/workspace/runtime_change.py",
            "new file mode 100644",
            "index 0000000..1111111",
            "--- /dev/null",
            "+++ b/packages/workspace/runtime_change.py",
            "@@ -0,0 +1 @@",
            "+RUNTIME_CHANGE = True",
            "",
        ]
    )


def _services_diff() -> str:
    return "\n".join(
        [
            "diff --git a/services/api/eval_requirement_skip.py b/services/api/eval_requirement_skip.py",
            "new file mode 100644",
            "index 0000000..1111111",
            "--- /dev/null",
            "+++ b/services/api/eval_requirement_skip.py",
            "@@ -0,0 +1 @@",
            "+SERVICE_CHANGE = True",
            "",
        ]
    )


if __name__ == "__main__":
    unittest.main()
