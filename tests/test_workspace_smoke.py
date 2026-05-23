from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from aiteamos_workspace import (
    build_run_launch_plan,
    create_run,
    create_task,
    dry_run_automation,
    evaluate_model_execution_readiness,
    evaluate_worker_authorization,
    index_workspace,
    load_workspace,
    propose_memory,
    task_execution_queue,
    workspace_action_board,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"


class WorkspaceSmokeTest(unittest.TestCase):
    def test_workspace_task_run_and_projection_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            index = index_workspace(workspace)
            self.assertEqual(index.project.object_id, "aiteamos")
            self.assertIn(BACKEND_MEMBER, index.members)
            self.assertIn(BACKEND_ASSIGNMENT, index.assignments)
            self.assertFalse([issue for issue in index.health if issue["severity"] == "error"])

            task = create_task(
                workspace,
                title="Smoke test task",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=["task is written to workspace files"],
                markdown="# Smoke test task\n",
            )
            self.assertTrue((workspace / "tasks" / f"{task.object_id}.yaml").exists())
            self.assertTrue((workspace / "tasks" / f"{task.object_id}.md").exists())

            queue = task_execution_queue(workspace)
            smoke_task_item = [item for item in queue["items"] if item["id"] == task.object_id][0]
            self.assertEqual(smoke_task_item["queueStatus"], "ready-to-run")
            self.assertEqual(smoke_task_item["assignedMember"], BACKEND_MEMBER)
            self.assertEqual(smoke_task_item["assignment"], BACKEND_ASSIGNMENT)

            board = workspace_action_board(workspace)
            launch_actions = [
                item
                for item in board["items"]
                if item["targetId"] == task.object_id and item["action"] == "create-run"
            ]
            self.assertTrue(launch_actions)
            self.assertEqual(launch_actions[0]["member"], BACKEND_MEMBER)
            self.assertEqual(launch_actions[0]["assignment"], BACKEND_ASSIGNMENT)

            plan = build_run_launch_plan(workspace, task.object_id, mode="managed_llm")
            self.assertTrue(plan["canCreateRun"])
            self.assertEqual(plan["selectedMember"], BACKEND_MEMBER)
            self.assertEqual(plan["selectedAssignment"], BACKEND_ASSIGNMENT)
            self.assertEqual(plan["selectedModelProfile"], "openai-gpt-5.5-xhigh")

            run = create_run(workspace, task_id=task.object_id, mode="managed_llm")
            updated = load_workspace(workspace)
            self.assertEqual(updated.runs[run.object_id].spec.member, BACKEND_MEMBER)
            self.assertEqual(updated.runs[run.object_id].spec.assignment, BACKEND_ASSIGNMENT)
            self.assertEqual(updated.assignments[BACKEND_ASSIGNMENT].spec.roleTemplate, "backend-engineer")
            self.assertIn("member", updated.run_events[run.object_id][0])
            self.assertEqual(updated.run_context_manifests[run.object_id]["spec"]["member"], BACKEND_MEMBER)
            self.assertEqual(updated.run_context_manifests[run.object_id]["spec"]["assignment"], BACKEND_ASSIGNMENT)

    def test_memory_and_automation_writeback_stay_member_centric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Memory smoke task",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["memory proposal links member and assignment"],
            )
            run = create_run(workspace, task_id=task.object_id)

            proposal = propose_memory(
                workspace,
                project="aiteamos",
                source_run=run.object_id,
                title="Smoke member memory proposal",
                content="The backend digital member should keep runtime changes assignment-scoped.",
                kind="procedural",
                confidence=0.9,
                evidence=["smoke test source run"],
                review_guidance="Human review required before injection.",
            )
            automation_run = dry_run_automation(workspace, "memory-health-dry-run", actor_member="manager")

            updated = load_workspace(workspace)
            self.assertEqual(updated.memory_proposals[proposal.object_id].spec.member, BACKEND_MEMBER)
            self.assertEqual(updated.memory_proposals[proposal.object_id].spec.assignment, BACKEND_ASSIGNMENT)
            self.assertEqual(updated.memory_proposals[proposal.object_id].spec.sourceRun, run.object_id)
            self.assertEqual(updated.automation_runs[automation_run.object_id].spec.serviceMember, "memory-service")
            self.assertEqual(updated.automation_runs[automation_run.object_id].spec.status, "dry-run")
            self.assertTrue(updated.automation_runs[automation_run.object_id].spec.dryRun)

    def test_managed_run_gates_use_member_assignment_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Gate smoke task",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=["worker gates stay member scoped"],
            )
            run = create_run(workspace, task_id=task.object_id, mode="managed_llm")

            model_readiness = evaluate_model_execution_readiness(workspace, run.object_id)
            worker_authorization = evaluate_worker_authorization(workspace, run.object_id)

            self.assertEqual(model_readiness["run"], run.object_id)
            self.assertEqual(model_readiness["member"], BACKEND_MEMBER)
            self.assertEqual(model_readiness["assignment"], BACKEND_ASSIGNMENT)
            self.assertTrue(any("secret" in check["name"] for check in model_readiness["checks"]))
            self.assertEqual(worker_authorization["member"], BACKEND_MEMBER)
            self.assertEqual(worker_authorization["assignment"], BACKEND_ASSIGNMENT)
            self.assertTrue(any(check["name"] == "worker-auth-write-scope" for check in worker_authorization["checks"]))

    def test_roles_directory_emits_layout_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            (workspace / "roles").mkdir()

            index = load_workspace(workspace)

            warnings = [
                issue
                for issue in index.health
                if issue["severity"] == "warning" and issue["kind"] == "workspace_layout"
            ]
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["ref"], "roles/")
            self.assertIn(".aiteamos/roles/ directory is not loaded", warnings[0]["message"])
            self.assertFalse([issue for issue in index.health if issue["severity"] == "error"])

    def test_eval_suite_contract_loads_and_validates_workspace_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            index = load_workspace(workspace)
            suite = index.eval_suites["aiteamos-eval-suite-schema-contract"]
            result = index.eval_results["ERES-20260522T204421556"]

            self.assertEqual(suite.spec.project, "aiteamos")
            self.assertEqual(suite.spec.judge.kind, "policy")
            self.assertEqual(suite.spec.judge.policyRef, "digital-default")
            self.assertEqual(suite.spec.judge.modelProfile, "openai-gpt-5.5-xhigh")
            self.assertEqual(suite.spec.policy.autoPromoteThreshold, 0.95)
            self.assertEqual(set(suite.spec.goldenOutputs), {"schema-contract", "workspace-validation"})
            self.assertEqual(suite.spec.cases[0].goldenOutputRefs, ["schema-contract"])
            requirement = index.assignments[BACKEND_ASSIGNMENT].spec.evalSuiteRequirements[0]
            self.assertEqual(requirement.evalSuite, "aiteamos-eval-suite-schema-contract")
            self.assertEqual(requirement.paths, ["packages/schema/**", "packages/workspace/**"])
            self.assertEqual(requirement.minimumPassRate, 0.95)
            self.assertEqual(result.spec.evalSuite, "aiteamos-eval-suite-schema-contract")
            self.assertEqual(result.spec.passRate, 1.0)
            self.assertFalse([issue for issue in index.health if issue["kind"] == "eval_suite"])

            suite_path = workspace / "eval_suites" / "aiteamos-eval-suite-schema-contract.yaml"
            payload = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
            payload["spec"]["cases"][0]["goldenOutputRefs"] = ["missing-golden-output"]
            suite_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            invalid_index = load_workspace(workspace)
            eval_warnings = [issue for issue in invalid_index.health if issue["kind"] == "eval_suite"]
            self.assertEqual(len(eval_warnings), 1)
            self.assertIn("missing golden output missing-golden-output", eval_warnings[0]["message"])


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
