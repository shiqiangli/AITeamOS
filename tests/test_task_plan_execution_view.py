from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import task_plan_execution_view, task_plan_execution_view_records
from aiteamos_workspace.io import write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_ID = "PLAN-DG121-EXECUTION"
TASK_ID_1 = "TASK-20260523T111111111"
TASK_ID_2 = "TASK-20260523T111111112"
RUN_ID = "RUN-DG121-EXECUTION"
REVIEW_ID = "REVIEW-DG121-EXECUTION"
MEMORY_ID = "MP-DG121-EXECUTION"


class TaskPlanExecutionViewTest(unittest.TestCase):
    def test_projection_links_subtasks_to_tasks_runs_reviews_and_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_fixture(workspace)

            view = task_plan_execution_view(workspace, PLAN_ID)

            self.assertEqual(view["kind"], "TaskPlanExecutionView")
            self.assertEqual(view["spec"]["taskPlan"], PLAN_ID)
            self.assertEqual(view["spec"]["summary"]["subtasks"], 2)
            self.assertEqual(view["spec"]["summary"]["linkedTasks"], 2)
            self.assertEqual(view["spec"]["summary"]["linkedRuns"], 1)
            self.assertEqual(view["spec"]["summary"]["linkedReviews"], 1)
            self.assertEqual(view["spec"]["summary"]["linkedMemoryProposals"], 1)
            self.assertEqual(view["spec"]["summary"]["completedSubtasks"], 1)
            self.assertEqual(view["spec"]["summary"]["driftCounts"], {"deferred": 1, "split": 1})

            implementation = view["spec"]["subtasks"][0]
            self.assertEqual(implementation["actualState"], "completed")
            self.assertEqual(implementation["drift"], "split")
            self.assertEqual(implementation["tasks"], [TASK_ID_1, TASK_ID_2])
            self.assertEqual(implementation["runs"], [RUN_ID])
            self.assertEqual(implementation["reviews"], [REVIEW_ID])
            self.assertEqual(implementation["memoryProposals"], [MEMORY_ID])
            self.assertEqual(implementation["acceptanceCoverage"]["rate"], 1.0)
            self.assertIn(".aiteamos/memory/proposals/MP-DG121-EXECUTION.yaml", implementation["evidence"])

            dashboard = view["spec"]["subtasks"][1]
            self.assertEqual(dashboard["actualState"], "deferred")
            self.assertEqual(dashboard["drift"], "deferred")
            self.assertFalse(dashboard["tasks"])

    def test_projection_list_and_api_endpoint_are_read_only_views(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_fixture(workspace)

            projection = task_plan_execution_view_records(workspace, task_plan=PLAN_ID)
            self.assertEqual(projection["summary"]["taskPlans"], 1)
            self.assertEqual(projection["summary"]["linkedTasks"], 2)

            client = TestClient(create_app(workspace))
            response = client.get(f"/task-plans/{PLAN_ID}/execution-view")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["spec"]["taskPlan"], PLAN_ID)

            list_response = client.get("/task-plans/execution-views")
            self.assertEqual(list_response.status_code, 200)
            self.assertTrue(any(item["spec"]["taskPlan"] == PLAN_ID for item in list_response.json()["taskPlans"]))


def _write_fixture(workspace: Path) -> None:
    write_yaml(
        workspace / "task_plans" / f"{PLAN_ID}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "TaskPlan",
            "metadata": {"id": PLAN_ID, "createdAt": "2026-05-23T11:00:00+08:00"},
            "spec": {
                "goal": "Verify plan-vs-actual projection.",
                "project": "aiteamos",
                "createdByMember": "manager",
                "status": "accepted",
                "reviewGates": ["manager-review"],
                "subtasks": [
                    {
                        "title": "Implement TaskPlan execution projection",
                        "assignedMember": "backend-digital",
                        "assignment": "aiteamos-backend-runtime",
                        "acceptance": ["Projection links subtask evidence."],
                        "risks": ["lineage drift"],
                        "reviewGates": ["engineering-review"],
                    },
                    {
                        "title": "Render TaskPlan execution projection",
                        "assignedMember": "frontend-human",
                        "assignment": "aiteamos-dashboard",
                        "acceptance": ["Dashboard renders projection."],
                        "risks": ["empty state drift"],
                        "reviewGates": ["ui-review"],
                    },
                ],
            },
        },
    )
    _write_task(workspace, TASK_ID_1, "Implement TaskPlan execution projection", related_runs=[RUN_ID], related_reviews=[REVIEW_ID])
    _write_task(workspace, TASK_ID_2, "Implement TaskPlan execution projection follow-up")
    write_yaml(
        workspace / "runs" / RUN_ID / "run.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Run",
            "metadata": {"id": RUN_ID, "createdAt": "2026-05-23T11:05:00+08:00"},
            "spec": {
                "project": "aiteamos",
                "task": TASK_ID_1,
                "member": "backend-digital",
                "assignment": "aiteamos-backend-runtime",
                "status": "SUCCEEDED",
                "reviews": [REVIEW_ID],
                "memoryProposals": [MEMORY_ID],
                "sourceTaskPlan": PLAN_ID,
                "sourceTaskPlanSubtask": 0,
            },
        },
    )
    write_yaml(
        workspace / "reviews" / f"{REVIEW_ID}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Review",
            "metadata": {"id": REVIEW_ID, "createdAt": "2026-05-23T11:10:00+08:00"},
            "spec": {
                "project": "aiteamos",
                "task": TASK_ID_1,
                "run": RUN_ID,
                "reviewer": "frontend-human",
                "verdict": "approved",
                "findings": [],
            },
        },
    )
    write_yaml(
        workspace / "memory" / "proposals" / f"{MEMORY_ID}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryProposal",
            "metadata": {"id": MEMORY_ID, "createdAt": "2026-05-23T11:15:00+08:00"},
            "spec": {
                "project": "aiteamos",
                "member": "backend-digital",
                "assignment": "aiteamos-backend-runtime",
                "sourceRun": RUN_ID,
                "sourceTask": TASK_ID_1,
                "status": "pending-review",
                "kind": "procedural",
                "title": "TaskPlan execution projection lesson",
                "content": "Plan-vs-actual projections should stay derived from source manifests.",
                "evidence": [f".aiteamos/runs/{RUN_ID}/run.yaml"],
            },
        },
    )


def _write_task(workspace: Path, task_id: str, title: str, *, related_runs: list[str] | None = None, related_reviews: list[str] | None = None) -> None:
    write_yaml(
        workspace / "tasks" / f"{task_id}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Task",
            "metadata": {"id": task_id, "createdAt": "2026-05-23T11:01:00+08:00"},
            "spec": {
                "title": title,
                "project": "aiteamos",
                "assignedMember": "backend-digital",
                "assignment": "aiteamos-backend-runtime",
                "status": "DONE",
                "acceptance": ["Projection links subtask evidence."],
                "relatedRuns": related_runs or [],
                "relatedReviews": related_reviews or [],
                "sourceTaskPlan": PLAN_ID,
                "sourceTaskPlanSubtask": 0,
            },
        },
    )


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


if __name__ == "__main__":
    unittest.main()
