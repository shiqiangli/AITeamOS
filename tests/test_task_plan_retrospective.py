from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import create_task_plan_retrospective, create_team_retrospective
from aiteamos_workspace.io import read_yaml, write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_ID = "PLAN-DG122-RETROSPECTIVE"
INCOMPLETE_PLAN_ID = "PLAN-DG122-INCOMPLETE"
TASK_ID_1 = "TASK-20260523T122200001"
TASK_ID_2 = "TASK-20260523T122200002"
RUN_ID_1 = "RUN-DG122-RETRO-1"
RUN_ID_2 = "RUN-DG122-RETRO-2"


class TaskPlanRetrospectiveTest(unittest.TestCase):
    def test_create_task_plan_retrospective_links_plan_execution_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_completed_plan_fixture(workspace)

            result = create_task_plan_retrospective(
                workspace,
                PLAN_ID,
                facilitator_member="manager",
                summary="TaskPlan closeout recorded reusable execution lessons.",
                lessons=["Retrospectives should cite the source TaskPlan."],
                action_items=["Keep TaskPlan retrospective review in the memory queue."],
            )

            retrospective = result["retrospective"]
            proposal = result["proposal"]
            self.assertEqual(retrospective.kind, "TeamRetrospective")
            self.assertEqual(retrospective.spec.sourceTaskPlan, PLAN_ID)
            self.assertEqual(retrospective.spec.sourceRuns, [RUN_ID_1, RUN_ID_2])
            self.assertEqual(retrospective.spec.sourceTasks, [TASK_ID_1, TASK_ID_2])
            self.assertEqual(retrospective.spec.proposedMemory, proposal.object_id)
            self.assertIn(f"task-plan:{PLAN_ID}", proposal.spec.evidence)
            self.assertIn(f"retrospective:{retrospective.object_id}", proposal.spec.evidence)
            self.assertEqual(proposal.spec.sourceExtractorId, "team-retrospective")

            stored = read_yaml(workspace / "im" / "retrospectives" / f"{retrospective.object_id}.yaml")
            self.assertEqual(stored["spec"]["sourceTaskPlan"], PLAN_ID)

    def test_api_can_create_task_plan_and_generic_retrospectives_with_source_task_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_completed_plan_fixture(workspace)
            client = TestClient(create_app(workspace))

            response = client.post(
                f"/task-plans/{PLAN_ID}/retrospective",
                json={
                    "facilitatorMember": "manager",
                    "summary": "API task-plan retrospective captures closeout evidence.",
                    "lessons": ["Use the source TaskPlan as the durable anchor."],
                    "actionItems": ["Review the generated memory proposal."],
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["retrospective"]["spec"]["sourceTaskPlan"], PLAN_ID)
            self.assertEqual(body["proposal"]["spec"]["sourceExtractorId"], "team-retrospective")
            self.assertIn(f"task-plan:{PLAN_ID}", body["proposal"]["spec"]["evidence"])

            generic = client.post(
                "/retrospectives",
                json={
                    "facilitatorMember": "manager",
                    "project": "aiteamos",
                    "sourceTaskPlan": PLAN_ID,
                    "summary": "Generic retrospective also records the source TaskPlan.",
                    "lessons": ["TeamRetrospective is the reusable closeout manifest."],
                    "actionItems": [],
                },
            )
            self.assertEqual(generic.status_code, 200, generic.text)
            self.assertEqual(generic.json()["retrospective"]["spec"]["sourceTaskPlan"], PLAN_ID)

    def test_task_plan_retrospective_rejects_incomplete_accepted_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_incomplete_plan_fixture(workspace)

            with self.assertRaisesRegex(ValueError, "not complete"):
                create_task_plan_retrospective(
                    workspace,
                    INCOMPLETE_PLAN_ID,
                    facilitator_member="manager",
                    summary="This retrospective should wait for completion.",
                )

    def test_team_retrospective_accepts_source_task_plan_as_sole_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_superseded_plan_fixture(workspace)

            result = create_team_retrospective(
                workspace,
                facilitator_member="manager",
                project="aiteamos",
                source_task_plan=INCOMPLETE_PLAN_ID,
                summary="Superseded TaskPlan retrospective records why execution stopped.",
            )

            retrospective = result["retrospective"]
            proposal = result["proposal"]
            self.assertEqual(retrospective.spec.sourceTaskPlan, INCOMPLETE_PLAN_ID)
            self.assertFalse(retrospective.spec.sourceRuns)
            self.assertIn(f"task-plan:{INCOMPLETE_PLAN_ID}", proposal.spec.evidence)


def _write_completed_plan_fixture(workspace: Path) -> None:
    write_yaml(
        workspace / "task_plans" / f"{PLAN_ID}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "TaskPlan",
            "metadata": {"id": PLAN_ID, "createdAt": "2026-05-23T12:22:00+08:00"},
            "spec": {
                "goal": "Verify TaskPlan retrospective closeout.",
                "project": "aiteamos",
                "createdByMember": "manager",
                "status": "accepted",
                "subtasks": [
                    {
                        "title": "Create TaskPlan retrospective protocol",
                        "assignedMember": "backend-digital",
                        "assignment": "aiteamos-backend-runtime",
                        "acceptance": ["Retrospective cites sourceTaskPlan."],
                    },
                    {
                        "title": "Expose TaskPlan retrospective API",
                        "assignedMember": "frontend-human",
                        "assignment": "aiteamos-dashboard",
                        "acceptance": ["API writes TeamRetrospective and MemoryProposal."],
                    },
                ],
            },
        },
    )
    _write_task(workspace, TASK_ID_1, "Create TaskPlan retrospective protocol", RUN_ID_1, subtask=0)
    _write_task(workspace, TASK_ID_2, "Expose TaskPlan retrospective API", RUN_ID_2, subtask=1)


def _write_incomplete_plan_fixture(workspace: Path) -> None:
    write_yaml(
        workspace / "task_plans" / f"{INCOMPLETE_PLAN_ID}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "TaskPlan",
            "metadata": {"id": INCOMPLETE_PLAN_ID, "createdAt": "2026-05-23T12:25:00+08:00"},
            "spec": {
                "goal": "Incomplete accepted TaskPlan should not allow retrospective.",
                "project": "aiteamos",
                "createdByMember": "manager",
                "status": "accepted",
                "subtasks": [
                    {
                        "title": "Still waiting for materialized task evidence",
                        "assignedMember": "backend-digital",
                        "assignment": "aiteamos-backend-runtime",
                    }
                ],
            },
        },
    )


def _write_superseded_plan_fixture(workspace: Path) -> None:
    _write_incomplete_plan_fixture(workspace)
    data = read_yaml(workspace / "task_plans" / f"{INCOMPLETE_PLAN_ID}.yaml")
    data["spec"]["status"] = "superseded"
    write_yaml(workspace / "task_plans" / f"{INCOMPLETE_PLAN_ID}.yaml", data)


def _write_task(workspace: Path, task_id: str, title: str, run_id: str, *, subtask: int) -> None:
    write_yaml(
        workspace / "tasks" / f"{task_id}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Task",
            "metadata": {"id": task_id, "createdAt": "2026-05-23T12:23:00+08:00"},
            "spec": {
                "title": title,
                "project": "aiteamos",
                "assignedMember": "backend-digital",
                "assignment": "aiteamos-backend-runtime",
                "status": "DONE",
                "acceptance": ["Retrospective cites sourceTaskPlan."],
                "relatedRuns": [run_id],
                "sourceTaskPlan": PLAN_ID,
                "sourceTaskPlanSubtask": subtask,
            },
        },
    )
    write_yaml(
        workspace / "runs" / run_id / "run.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Run",
            "metadata": {"id": run_id, "createdAt": "2026-05-23T12:24:00+08:00"},
            "spec": {
                "project": "aiteamos",
                "task": task_id,
                "member": "backend-digital",
                "assignment": "aiteamos-backend-runtime",
                "status": "SUCCEEDED",
                "sourceTaskPlan": PLAN_ID,
                "sourceTaskPlanSubtask": subtask,
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
