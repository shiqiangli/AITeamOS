from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from aiteamos_workspace import (
    create_model_profile,
    create_run,
    create_task,
    evaluate_model_execution_readiness,
    evaluate_model_policy,
    execute_run_with_model,
    load_workspace,
    summarize_model_costs,
)
import aiteamos_workspace.executor as executor_module
from aiteamos_workspace.mutations import append_run_event


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"


class ModelPolicyTest(unittest.TestCase):
    def test_missing_budget_blocks_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Policy block smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["policy blocks"],
            )
            create_model_profile(
                workspace,
                name="local-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="local-provider", mode="managed_llm")
            called = {"value": False}
            original = executor_module.call_model_with_prompt

            def fail_if_called(*_args: object, **_kwargs: object) -> object:
                called["value"] = True
                raise AssertionError("provider call should be unreachable when model policy blocks")

            executor_module.call_model_with_prompt = fail_if_called  # type: ignore[assignment]
            try:
                with self.assertRaises(ValueError):
                    execute_run_with_model(workspace, run.object_id)
            finally:
                executor_module.call_model_with_prompt = original

            self.assertFalse(called["value"])
            index = load_workspace(workspace)
            event_types = [event["type"] for event in index.run_events[run.object_id]]
            self.assertIn("model.policy.blocked", event_types)
            self.assertNotIn("model.call.started", event_types)
            self.assertEqual(index.runs[run.object_id].spec.status, "READY")

    def test_budget_token_limit_blocks_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Token budget smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["policy blocks"],
            )
            create_model_profile(
                workspace,
                name="local-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="local-provider", mode="managed_llm")
            _write_budget_policy(workspace, "tiny-input-budget", member=BACKEND_MEMBER, max_input_tokens=1)

            decision = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=50)

            self.assertFalse(decision["ready"])
            self.assertEqual(decision["policy"], "tiny-input-budget")
            self.assertTrue([check for check in decision["checks"] if check["name"] == "budget-tokens" and check["status"] == "fail"])

    def test_task_budget_policy_overrides_project_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Task policy smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["task policy wins"],
            )
            create_model_profile(
                workspace,
                name="local-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="local-provider", mode="managed_llm")
            _write_budget_policy(workspace, "project-budget", max_input_tokens=100000)
            _write_budget_policy(workspace, "task-budget", task=task.object_id, max_input_tokens=1)

            decision = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=50)

            self.assertEqual(decision["policy"], "task-budget")
            self.assertFalse(decision["ready"])

    def test_soft_budget_warns_without_blocking_when_policy_allows_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Soft budget warn smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["soft warning"],
            )
            create_model_profile(
                workspace,
                name="local-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="local-provider", mode="managed_llm")
            _write_budget_policy(workspace, "soft-warn-budget", member=BACKEND_MEMBER, max_input_tokens=100000, soft_input_tokens=1)

            decision = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=50)

            self.assertTrue(decision["ready"])
            self.assertTrue([check for check in decision["checks"] if check["name"] == "soft-budget-tokens" and check["status"] == "warn"])
            self.assertTrue(decision["warnings"])

    def test_soft_budget_stop_blocks_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Soft budget stop smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["soft stop"],
            )
            create_model_profile(
                workspace,
                name="local-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="local-provider", mode="managed_llm")
            _write_budget_policy(
                workspace,
                "soft-stop-budget",
                member=BACKEND_MEMBER,
                max_input_tokens=100000,
                soft_input_tokens=1,
                on_soft_limit="stop-run",
            )
            called = {"value": False}
            original = executor_module.call_model_with_prompt

            def fail_if_called(*_args: object, **_kwargs: object) -> object:
                called["value"] = True
                raise AssertionError("provider call should be unreachable when soft budget stop blocks")

            executor_module.call_model_with_prompt = fail_if_called  # type: ignore[assignment]
            try:
                with self.assertRaises(ValueError):
                    execute_run_with_model(workspace, run.object_id)
            finally:
                executor_module.call_model_with_prompt = original

            self.assertFalse(called["value"])
            index = load_workspace(workspace)
            event_types = [event["type"] for event in index.run_events[run.object_id]]
            self.assertIn("model.policy.blocked", event_types)
            self.assertNotIn("model.call.started", event_types)

    def test_fallback_attempt_requires_explicit_budget_policy_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Fallback policy disabled smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["fallback blocks"],
            )
            create_model_profile(
                workspace,
                name="local-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="local-provider", mode="managed_llm")
            _write_budget_policy(workspace, "fallback-disabled-budget", member=BACKEND_MEMBER, max_input_tokens=100000)

            primary = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=50)
            fallback = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=50, fallback_attempt=True)

            self.assertTrue(primary["ready"])
            self.assertFalse(fallback["ready"])
            self.assertTrue([check for check in fallback["checks"] if check["name"] == "fallback-policy" and check["status"] == "fail"])

    def test_fallback_attempt_counts_event_ledger_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Fallback policy count smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["fallback accounting"],
            )
            create_model_profile(
                workspace,
                name="local-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="local-provider", mode="managed_llm")
            _write_budget_policy(
                workspace,
                "fallback-allowed-budget",
                member=BACKEND_MEMBER,
                max_input_tokens=100000,
                allow_fallback=True,
                max_fallbacks=1,
            )

            allowed = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=50, fallback_attempt=True)
            self.assertTrue(allowed["ready"])

            append_run_event(
                workspace,
                run.object_id,
                {"type": "model.call.started", "provider": "local", "model": "fallback-model", "fallbackFrom": "local-provider"},
            )
            blocked = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=50, fallback_attempt=True)

            self.assertFalse(blocked["ready"])
            self.assertEqual(blocked["usage"]["fallbacks"], 1)
            self.assertTrue([check for check in blocked["checks"] if check["name"] == "fallback-policy" and check["status"] == "fail"])

    def test_builtin_profile_is_not_executable_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Builtin policy smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["builtin blocks"],
            )
            run = create_run(
                workspace,
                task_id=task.object_id,
                model_profile="builtin/openai-gpt-5.5-xhigh",
                mode="managed_llm",
            )

            readiness = evaluate_model_execution_readiness(workspace, run.object_id)

            self.assertFalse(readiness["ready"])
            self.assertTrue([check for check in readiness["checks"] if check["name"] == "model-source" and check["status"] == "fail"])

    def test_local_manual_profile_passes_without_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Manual policy smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["manual passes"],
            )
            create_model_profile(
                workspace,
                name="manual-profile",
                provider="local",
                model="manual",
                default_for_members=[BACKEND_MEMBER],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")

            decision = evaluate_model_policy(workspace, run.object_id)

            self.assertTrue(decision["ready"])
            self.assertIsNone(decision["policy"])
            self.assertTrue([check for check in decision["checks"] if check["name"] == "budget-policy" and check["status"] == "pass"])

    def test_priced_profile_projects_usd_budget_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Projected USD budget smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["usd blocks"],
            )
            create_model_profile(
                workspace,
                name="priced-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                pricing={"inputUsdPer1MTokens": 1.0, "outputUsdPer1MTokens": 2.0, "requestUsd": 0.01},
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="priced-provider", mode="managed_llm")
            _write_budget_policy(workspace, "tiny-usd-budget", member=BACKEND_MEMBER, max_input_tokens=2_000_000, max_usd=0.50)

            decision = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=1_000_000)

            self.assertFalse(decision["ready"])
            self.assertEqual(decision["estimates"]["costUsd"], 1.01)
            self.assertTrue([check for check in decision["checks"] if check["name"] == "cost-estimate" and check["status"] == "pass"])
            self.assertTrue([check for check in decision["checks"] if check["name"] == "budget-usd" and check["status"] == "fail"])

    def test_cost_summary_derives_cost_from_profile_pricing_when_provider_omits_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Derived cost smoke",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["cost derives"],
            )
            create_model_profile(
                workspace,
                name="priced-provider",
                provider="local",
                model="custom-provider",
                gateway="local-test",
                pricing={"inputUsdPer1MTokens": 1.0, "outputUsdPer1MTokens": 2.0, "requestUsd": 0.01},
                capabilities=["managed_llm"],
            )
            run = create_run(workspace, task_id=task.object_id, model_profile="priced-provider", mode="managed_llm")
            append_run_event(
                workspace,
                run.object_id,
                {
                    "type": "model.call.completed",
                    "provider": "local",
                    "model": "custom-provider",
                    "usage": {"input_tokens": 1_000_000, "output_tokens": 500_000, "total_tokens": 1_500_000},
                },
            )

            summary = summarize_model_costs(workspace)
            policy = evaluate_model_policy(workspace, run.object_id, estimated_input_tokens=0)

            self.assertEqual(summary["totals"]["costUsd"], 2.01)
            self.assertEqual(summary["byRun"][0]["costUsd"], 2.01)
            self.assertEqual(policy["usage"]["costUsd"], 2.01)


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees", "budget_policies"),
    )
    return workspace


def _write_budget_policy(
    workspace: Path,
    name: str,
    *,
    member: str | None = None,
    task: str | None = None,
    max_input_tokens: int,
    soft_input_tokens: int | None = None,
    on_soft_limit: str = "warn",
    allow_fallback: bool = False,
    max_fallbacks: int = 0,
    max_usd: float = 10.0,
) -> None:
    scope_lines = ["    project: aiteamos"]
    if member:
        scope_lines.append(f"    member: {member}")
    if task:
        scope_lines.append(f"    task: {task}")
    content = "\n".join(
        [
            "apiVersion: aiteamos.dev/v1alpha1",
            "kind: BudgetPolicy",
            "metadata:",
            f"  name: {name}",
            "spec:",
            "  scope:",
            *scope_lines,
            "  limits:",
            f"    maxInputTokensPerRun: {max_input_tokens}",
            f"    maxUsdPerRun: {max_usd}",
            *( [f"    softInputTokensPerRun: {soft_input_tokens}"] if soft_input_tokens is not None else [] ),
            "  enforcement:",
            f"    onSoftLimit: {on_soft_limit}",
            "    onHardLimit: stop-run",
            "  fallback:",
            f"    allowModelFallback: {str(allow_fallback).lower()}",
            f"    maxFallbacksPerRun: {max_fallbacks}",
            "",
        ]
    )
    path = workspace / "budget_policies" / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
