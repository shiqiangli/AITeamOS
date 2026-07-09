from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "plan_v7_ci_artifacts.py"
    spec = importlib.util.spec_from_file_location("plan_v7_ci_artifacts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plan_v7_artifact_commands_do_not_run_live_dogfood_by_default(tmp_path) -> None:
    module = _module()

    commands = module._commands(
        full=False,
        include_frontend=False,
        include_agent_server_smoke=False,
        include_agent_server_matrix_smoke=False,
        include_live_provider_dogfood=False,
        live_provider_profile="core_loop",
        live_provider_executor_id="langgraph",
        live_provider_ticket_id="",
        artifact_root=tmp_path / "artifacts",
        workspace_dir=tmp_path / "workspace",
    )

    command_names = [command.name for command in commands]
    assert "environment_smoke" in command_names
    assert "runtime_registry_smoke" in command_names
    assert "live_provider_readiness_smoke" in command_names
    readiness = next(command for command in commands if command.name == "live_provider_readiness_smoke")
    assert readiness.argv[readiness.argv.index("--profile") + 1] == "core_loop"
    assert readiness.argv[readiness.argv.index("--executor-id") + 1] == "langgraph"
    queue_worker = next(command for command in commands if command.name == "ticket_loop_queue_worker_smoke")
    assert queue_worker.argv[queue_worker.argv.index("--daemon-min-ticks") + 1] == "6"
    assert queue_worker.argv[queue_worker.argv.index("--daemon-timeout-seconds") + 1] == "10"
    assert "plane_ticket_action_smoke" not in command_names
    assert "live_provider_dogfood_execute" not in command_names
    assert not any(command.name == "live_provider_dogfood_execute" and "--execute" in command.argv for command in commands)


def test_plan_v7_artifact_commands_add_gated_live_dogfood_when_explicit(tmp_path) -> None:
    module = _module()

    commands = module._commands(
        full=False,
        include_frontend=False,
        include_agent_server_smoke=False,
        include_agent_server_matrix_smoke=False,
        include_live_provider_dogfood=True,
        live_provider_profile="repo_write_adapter",
        live_provider_executor_id="codex_cli",
        live_provider_ticket_id="ticket-live-1",
        artifact_root=tmp_path / "artifacts",
        workspace_dir=tmp_path / "workspace",
    )

    action_smokes = [command for command in commands if command.name == "plane_ticket_action_smoke"]
    assert len(action_smokes) == 1
    action_argv = action_smokes[0].argv
    assert "scripts/plane_ticket_action_smoke.py" in action_argv
    assert "--execute" in action_argv
    assert action_argv[action_argv.index("--workspace-dir") + 1] == str(tmp_path / "workspace")
    assert action_argv[action_argv.index("--ticket-id") + 1] == "ticket-live-1"
    assert "--no-create-ticket" in action_argv
    assert action_argv[action_argv.index("--output") + 1] == str(tmp_path / "artifacts" / "plane_ticket_action_smoke.json")

    live_commands = [command for command in commands if command.name == "live_provider_dogfood_execute"]
    assert len(live_commands) == 1
    argv = live_commands[0].argv
    assert "scripts/live_provider_dogfood.py" in argv
    assert "--execute" in argv
    assert argv[argv.index("--profile") + 1] == "repo_write_adapter"
    assert argv[argv.index("--executor-id") + 1] == "codex_cli"
    assert argv[argv.index("--workspace-dir") + 1] == str(tmp_path / "workspace")
    assert argv[argv.index("--ticket-id") + 1] == "ticket-live-1"
    assert "--no-create-ticket" in argv
    assert "--start-agent-server" in argv
    assert argv[argv.index("--server-log") + 1] == str(tmp_path / "artifacts" / "live_provider_agent_server.log")
    assert argv[argv.index("--output") + 1] == str(tmp_path / "artifacts" / "live_provider_dogfood.json")


def test_plan_v7_production_readiness_profile_keeps_live_dogfood_opt_in(tmp_path) -> None:
    module = _module()

    commands = module._commands(
        full=True,
        include_frontend=False,
        include_agent_server_smoke=False,
        include_agent_server_matrix_smoke=True,
        include_live_provider_dogfood=False,
        live_provider_profile="core_loop",
        live_provider_executor_id="langgraph",
        live_provider_ticket_id="",
        artifact_root=tmp_path / "artifacts",
        workspace_dir=tmp_path / "workspace",
    )

    command_names = [command.name for command in commands]
    assert "pytest_execution_dispatch_contract" in command_names
    assert "agent_server_readonly_list_smoke" in command_names
    assert "agent_server_answer_only_smoke" in command_names
    assert "agent_server_provider_blocker_smoke" in command_names
    assert "agent_server_handoff_policy_smoke" in command_names
    assert "agent_server_primary_approval_resume_matrix_smoke" in command_names
    assert "agent_server_approval_evidence_review_smoke" in command_names
    assert "agent_server_approval_rejected_review_smoke" in command_names
    assert "agent_server_approval_changes_review_smoke" in command_names
    assert "plane_ticket_action_smoke" not in command_names
    assert "live_provider_dogfood_execute" not in command_names
    assert "plan_v7_production_readiness_summary_gate" not in command_names
    assert not any(command.name == "live_provider_dogfood_execute" and "--execute" in command.argv for command in commands)

    post_commands = module._post_commands(production_readiness=True, artifact_root=tmp_path / "artifacts")
    assert [command.name for command in post_commands] == ["plan_v7_production_readiness_summary_gate"]
    summary_gate = post_commands[0]
    assert "scripts/plan_v7_artifact_summary.py" in summary_gate.argv
    assert summary_gate.argv[summary_gate.argv.index("--artifact-dir") + 1] == str(tmp_path)
    assert "--fail-on-evidence-gaps" in summary_gate.argv
    assert summary_gate.argv[summary_gate.argv.index("--output") + 1] == str(
        tmp_path / "artifacts" / "production_readiness_summary.json"
    )

    assert module._post_commands(production_readiness=False, artifact_root=tmp_path / "artifacts") == []
