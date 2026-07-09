from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read import memory_service, ticket_service


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_system_status_reports_secret_health_without_settings_compat_route(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PLANE_API_KEY", raising=False)
    monkeypatch.delenv("AITEAMOS_GRAPHITI_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("AITEAMOS_NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("OPENHANDS_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCODE_BIN", raising=False)
    workspace = tmp_path / ".aiteamos"
    fake_codex = workspace / "bin" / "codex"
    fake_codex.parent.mkdir(parents=True)
    fake_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    monkeypatch.setenv("CODEX_CLI_BIN", str(fake_codex))
    (workspace / "assets").mkdir(parents=True)
    (workspace / "employees").mkdir(parents=True)
    (workspace / "tickets").mkdir(parents=True)
    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / "services" / "api" / "release_hygiene_fixture.py").write_text("VALUE = 1\n", encoding="utf-8")
    (workspace / "execution_sessions.json").write_text(
        json.dumps(
            {
                "clara::thread-schema::ops-1": {
                    "session_key": "clara::thread-schema::ops-1",
                    "employee_id": "clara",
                    "thread_id": "thread-schema",
                    "ticket_id": "ops-1",
                    "status": "running",
                }
            }
        ),
        encoding="utf-8",
    )
    (workspace / "execution_approvals.json").write_text("[]\n", encoding="utf-8")
    (workspace / "assets" / "candidates.json").write_text("[]\n", encoding="utf-8")
    (workspace / "assets" / "index.json").write_text("[]\n", encoding="utf-8")
    (workspace / "assets" / "reviews.json").write_text("[]\n", encoding="utf-8")
    (workspace / "assets" / "retrieval_evaluations.json").write_text("[]\n", encoding="utf-8")
    (workspace / "employees" / "clara.yaml").write_text("id: clara\ndisplay_name: Clara\n", encoding="utf-8")
    (workspace / "tickets" / "index.json").write_text("[]\n", encoding="utf-8")
    artifact_dir = workspace / "artifacts" / "plan_v8"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "track-c-agent-server-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.langgraph_agent_server_ci_smoke.v1",
                "status": "passed",
                "generated_at": "2026-06-21T03:20:00+00:00",
                "assistant_id": "aiteamos_workbench",
                "url": "http://127.0.0.1:45271",
                "smoke": {
                    "status": "passed",
                    "summary": {
                        "runtime_status": {
                            "status": "completed",
                            "current_node": "final_response",
                        },
                        "visible_response": {
                            "version": "chat_visible_response.v1",
                            "display_state": "completed",
                        },
                        "provider_blocker_count": 0,
                        "provider_blocker_reasons": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-a-chat-visible-response-matrix.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.chat_visible_response_matrix.cli.v1",
                "generated_at": "2026-06-21T03:20:30+00:00",
                "workspace_dir": str(tmp_path),
                "result": {
                    "contract_version": "aiteamos_chat_visible_response_matrix.v1",
                    "status": "passed",
                    "detail": "Chat visible-response matrix covers completed, blocked, approval, handoff, and provider-blocker states.",
                    "summary": {
                        "case_count": 5,
                        "passed_case_count": 5,
                        "failed_case_count": 0,
                        "required_states": ["completed", "blocked", "needs_approval", "handoff", "provider_blocker"],
                        "observed_states": ["completed", "blocked", "needs_approval", "handoff", "provider_blocker"],
                        "missing_states": [],
                        "assistant_reply_visible_count": 5,
                        "runtime_status_visible_count": 5,
                        "blocked_reason_visible_count": 2,
                        "retry_cause_visible_count": 1,
                        "approval_request_visible_count": 1,
                        "handoff_visible_count": 1,
                        "provider_blocker_visible_count": 1,
                    },
                    "blockers": [],
                    "cases": [],
                    "commands": ["python scripts/chat_visible_response_matrix.py --workspace-dir ."],
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-c-live-provider-readiness.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_readiness_smoke.v1",
                "status": "passed",
                "generated_at": "2026-06-21T03:19:00+00:00",
                "summary": {
                    "readiness_status": "blocked",
                    "profile": "core_loop",
                    "selected_executor_id": "langgraph",
                    "repo_write_ready_count": 1,
                    "repo_write_candidate_count": 3,
                    "ticket_backend_status": "setup_blocked",
                    "ticket_backend_release_target_status": "blocked",
                    "ticket_backend_release_target_ready": False,
                    "ticket_backend_release_target_blockers": ["plane_api_key_missing"],
                    "ticket_backend_release_target_setup_action": "configure_plane_ticket_backend",
                    "memory_backend_status": "disabled",
                    "provider_smoke_status": "not_run",
                    "mutation_gate_open": False,
                    "blocker_count": 2,
                    "blocker_reasons": ["ticket_provider_not_ready", "memory_provider_not_ready"],
                    "blocker_scopes": ["ticket_backend", "memory_backend"],
                },
                "result": {"status": "blocked", "profile": "core_loop", "selected_executor_id": "langgraph"},
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-c-live-provider-soak-evidence.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_soak_evidence.cli.v1",
                "generated_at": "2026-06-21T03:23:00+00:00",
                "workspace_dir": str(tmp_path),
                "result": {
                    "contract_version": "aiteamos_live_provider_soak_evidence.v1",
                    "status": "blocked",
                    "detail": "Repeated live-provider soak evidence is blocked by 1 readiness signal(s).",
                    "summary": {
                        "scenario_count": 5,
                        "passed_scenario_count": 0,
                        "blocked_scenario_count": 5,
                        "failed_scenario_count": 0,
                        "missing_scenario_count": 0,
                        "warning_scenario_count": 0,
                        "latest_generated_at": "",
                        "mutation_gate_open": False,
                        "ready_to_execute": False,
                        "ready_for_release": False,
                        "contract_version": "aiteamos_live_provider_soak_evidence.v1",
                    },
                    "blockers": ["live_provider_dogfood_not_confirmed"],
                    "scenarios": [],
                    "commands": ["python scripts/live_provider_soak_evidence.py --workspace-dir ."],
                    "evidence_refs": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-c-plane-ticket-action-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.plane_ticket_action_smoke.v1",
                "generated_at": "2026-06-21T03:23:30+00:00",
                "workspace_dir": str(tmp_path),
                "result": {
                    "status": "dry_run",
                    "provider": "plane",
                    "checks": ["plane_action_smoke_requested", "plane_action_smoke_mutation_gate_checked"],
                    "warnings": [],
                    "failures": [],
                    "blockers": [
                        {
                            "id": "ticket:plane:action_smoke:confirmation",
                            "reason": "plane_action_smoke_not_confirmed",
                            "status": "confirmation_required",
                            "detail": "Pass --execute and set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 to run a mutating Plane Ticket handoff/report action smoke.",
                            "setup_required": ["--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
                        }
                    ],
                    "evidence": {
                        "confirm_env_var": "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
                        "confirm_env_configured": False,
                        "ticket_backend_status": {"status": "ready"},
                    },
                    "summary": {
                        "ticket_backend_status": "ready",
                        "mutation_gate_open": False,
                    },
                    "external_calls": False,
                    "mutating": False,
                },
                "summary": {
                    "ticket_backend_status": "ready",
                    "mutation_gate_open": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-c-plane-scope-discovery-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.plane_scope_discovery_smoke.v1",
                "generated_at": "2026-06-21T03:23:20+00:00",
                "workspace_dir": str(tmp_path),
                "status": "passed",
                "result": {
                    "status": "ready",
                    "detail": "Plane scope discovery found workspace/project candidates.",
                    "api_key_env": "PLANE_API_KEY",
                    "api_key_configured": True,
                    "external_calls": True,
                    "checks": ["plane_workspace_list_requested", "plane_project_list_requested"],
                    "setup_required": [],
                    "suggestions": [
                        {
                            "source": "plane_discovery",
                            "plane_workspace_slug": "ait",
                            "plane_project_id": "plane-project-1",
                            "workspace_name": "AITeamOS",
                            "project_name": "Core Loop",
                            "status": "available",
                            "deep_link": "#/settings/code-repositories",
                        }
                    ],
                    "evidence": {"workspace_count": 1, "project_count": 1},
                },
                "summary": {
                    "discovery_status": "ready",
                    "api_key_env": "PLANE_API_KEY",
                    "api_key_configured": True,
                    "external_calls": True,
                    "external_mutation": False,
                    "workspace_count": 1,
                    "project_count": 1,
                    "suggestion_count": 1,
                    "first_workspace_slug": "ait",
                    "first_project_id": "plane-project-1",
                    "first_workspace_name": "AITeamOS",
                    "first_project_name": "Core Loop",
                    "checks": ["plane_workspace_list_requested", "plane_project_list_requested"],
                    "setup_required": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-c-ticket-loop-worker-soak.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.ticket_loop_queue_worker_smoke.v2",
                "status": "passed",
                "generated_at": "2026-06-21T03:24:00+00:00",
                "summary": {
                    "ticket_id": "ops-worker-soak",
                    "processed_statuses": ["blocked", "blocked"],
                    "queue_ids": ["queue-worker-1", "queue-worker-2"],
                    "asset_candidate_ids": ["asset-candidate-ticket-loop-failure-retrospective-ops-worker-soak"],
                    "timeline_statuses": ["assigned", "loop_queued", "blocked", "proposed"],
                    "after_reliability": {
                        "status": "error",
                        "detail": "At least one queued loop item failed.",
                    },
                    "worker_status": {"status": "completed"},
                    "worker_processed_delta": 2,
                    "worker_policy_action_delta": 1,
                    "failed_delta": 2,
                    "daemon_status": "passed",
                    "daemon": {
                        "processed_delta": 2,
                        "tick_delta": 6,
                        "run_statuses": ["completed", "completed"],
                        "queue_statuses": ["completed", "completed"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-e-employee-growth-eval-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.employee_growth_eval_smoke.v1",
                "generated_at": "2026-06-21T03:24:30+00:00",
                "workspace_dir": str(tmp_path),
                "status": "passed",
                "summary": {
                    "employee_id": "alex",
                    "current_load_status": "needs_attention",
                    "active_ticket_count": 1,
                    "active_run_count": 1,
                    "current_ticket_count": 1,
                    "historical_ticket_count": 1,
                    "report_count": 2,
                    "handoff_count": 1,
                    "asset_candidate_count": 2,
                    "approved_asset_count": 1,
                    "asset_review_count": 1,
                    "runtime_run_count": 1,
                    "quality_feedback_count": 2,
                    "improvement_candidate_count": 1,
                    "approved_improvement_count": 1,
                    "applied_improvement_count": 0,
                    "improvement_loop_proof_status": "passed",
                    "improvement_loop_candidate_id": "employee-improvement-alex-runtime-feedback:employee-growth-proof-request",
                    "improvement_loop_asset_id": "asset-employee-improvement-alex-runtime-feedback:employee-growth-proof-request",
                    "improvement_loop_application_status": "applied",
                    "improvement_loop_ticket_report_id": "report-employee-growth-proof",
                    "improvement_loop_applied_change_count": 4,
                    "improvement_loop_workspace": "temporary",
                    "handoff_target_employee_id": "alex",
                    "handoff_work_history_score": 3,
                    "provider_projection_status": "not_projected",
                    "graph_node_count": 4,
                    "graph_edge_count": 3,
                },
                "result": {
                    "contract_version": "aiteamos_employee_growth_eval.v1",
                    "status": "passed",
                    "detail": "Employee growth evidence is passing for alex.",
                    "summary": {
                        "employee_id": "alex",
                        "current_load_status": "needs_attention",
                        "active_ticket_count": 1,
                        "active_run_count": 1,
                        "current_ticket_count": 1,
                        "historical_ticket_count": 1,
                        "report_count": 2,
                        "handoff_count": 1,
                        "asset_candidate_count": 2,
                        "approved_asset_count": 1,
                        "asset_review_count": 1,
                        "runtime_run_count": 1,
                        "quality_feedback_count": 2,
                        "improvement_candidate_count": 1,
                        "approved_improvement_count": 1,
                        "applied_improvement_count": 0,
                        "improvement_loop_proof_status": "passed",
                        "improvement_loop_candidate_id": "employee-improvement-alex-runtime-feedback:employee-growth-proof-request",
                        "improvement_loop_asset_id": "asset-employee-improvement-alex-runtime-feedback:employee-growth-proof-request",
                        "improvement_loop_application_status": "applied",
                        "improvement_loop_ticket_report_id": "report-employee-growth-proof",
                        "improvement_loop_applied_change_count": 4,
                        "improvement_loop_workspace": "temporary",
                        "handoff_target_employee_id": "alex",
                        "handoff_work_history_score": 3,
                        "provider_projection_status": "not_projected",
                        "graph_node_count": 4,
                        "graph_edge_count": 3,
                    },
                    "checks": [],
                    "blockers": [],
                    "warnings": [],
                    "commands": [
                        "python scripts/employee_growth_eval_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-e-employee-growth-eval-smoke.json"
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-f-context-retrieval-eval-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.context_retrieval_eval_smoke.v1",
                "status": "passed",
                "generated_at": "2026-06-21T03:21:00+00:00",
                "summary": {
                    "ticket_id": "rd-context-retrieval",
                    "query": "Graphiti context Neo4j password provider dogfood",
                    "graphiti_result_count": 1,
                    "graphiti_excluded_result_count": 2,
                    "active_asset_ids": ["asset-graphiti-context-solution"],
                    "recalled_memory_ids": ["mem-context-retrieval-note"],
                    "stale_hint_asset_ids": ["asset-graphiti-stale-solution", "asset-graphiti-conflicted-solution"],
                    "excluded_asset_ids": ["asset-graphiti-stale-solution"],
                    "wrong_ticket_filtered": True,
                    "work_history": {
                        "eval_recall": 1.0,
                        "eval_precision_like": 1.0,
                        "matched_refs": [{"kind": "work_ticket", "ref": "rd-context-retrieval"}],
                        "missing_refs": [],
                    },
                    "provider_blocker_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-f-asset-provenance-eval-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.asset_provenance_eval_smoke.v1",
                "status": "passed",
                "generated_at": "2026-06-21T03:22:00+00:00",
                "summary": {
                    "source_asset_id": "asset-provenance-new-guidance",
                    "target_asset_id": "asset-provenance-old-guidance",
                    "relationship_id": "asset-relationship-asset-provenance-new-guidance-supersedes-asset-provenance-old-guidance",
                    "relationship_projection_status": "ingested",
                    "relationship_ingested_count": 1,
                    "relationship_search_result_count": 1,
                    "stale_memory_id": "mem-stale-provenance",
                    "stale_review_status": "stale",
                    "stale_after_excluded_count": 1,
                    "stale_active_filtered": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "track-g-plan-v8-readiness.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.plan_v8_readiness.cli.v1",
                "generated_at": "2026-06-21T03:25:00+00:00",
                "workspace_dir": str(tmp_path),
                "result": {
                    "contract_version": "aiteamos_plan_v8_readiness.v1",
                    "status": "blocked",
                    "detail": "Plan v8 readiness is blocked by 1 signal(s).",
                    "summary": {
                        "check_count": 6,
                        "passed_count": 3,
                        "warning_count": 2,
                        "blocked_count": 1,
                        "failed_count": 0,
                        "ready_for_release": False,
                        "contract_version": "aiteamos_plan_v8_readiness.v1",
                        "next_action": "Open the live mutation gate explicitly, then run the live provider dogfood soak against Plane and Graphiti.",
                    },
                    "checks": [],
                    "blockers": ["live_provider_dogfood_not_confirmed"],
                    "commands": [
                        "python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json"
                    ],
                    "evidence_refs": [
                        "track-c-agent-server-smoke.json",
                        "track-a-chat-visible-response-matrix.json",
                        "track-c-ticket-loop-worker-soak.json",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    client = TestClient(create_app())

    status = client.get("/api/v1/system-status")
    assert status.status_code == 200
    payload = status.json()
    assert "secrets" in payload
    assert "items" not in payload

    secrets = {item["id"]: item for item in payload["secrets"]}
    assert secrets["openai_api_key"]["configured"] is True
    assert secrets["deepseek_api_key"]["configured"] is False
    assert secrets["plane_api_key"]["env_vars"] == ["PLANE_API_KEY"]
    assert secrets["plane_api_key"]["configured"] is False
    assert secrets["graphiti_neo4j_password"]["configured"] is False
    assert secrets["anthropic_api_key"]["configured"] is False
    assert secrets["claude_code_bin"]["env_vars"] == ["CLAUDE_CODE_BIN"]
    assert secrets["claude_code_bin"]["configured"] is False
    assert secrets["cursor_api_key"]["env_vars"] == ["CURSOR_API_KEY"]
    assert secrets["openhands_base_url"]["configured"] is False
    assert secrets["opencode_bin"]["configured"] is False

    assert payload["ticket_backend"]["provider"] == "plane"
    assert payload["ticket_backend"]["status"] == "setup_blocked"
    assert "PLANE_API_KEY" in payload["ticket_backend"]["setup_required"]
    assert payload["ticket_backend"]["release_target"]["status"] == "blocked"
    assert "plane_api_key_missing" in payload["ticket_backend"]["release_target"]["blockers"]
    assert payload["memory_backend"]["backend"] == "graphiti"
    assert payload["memory_backend"]["status"] == "disabled"
    provider_conformance = payload["provider_conformance"]
    assert provider_conformance["contract_version"] == "provider_conformance.v1"
    assert provider_conformance["summary"]["core_model_boundary"].startswith("Ticket / Employee / Asset")
    assert provider_conformance["summary"]["core_required_count"] >= 5
    assert provider_conformance["summary"]["production_ready_count"] >= 3
    assert provider_conformance["summary"]["core_blocked_count"] >= 1
    assert provider_conformance["summary"]["runtime_boundary_status"] == "passed"
    assert provider_conformance["summary"]["runtime_boundary_checks"] == [
        "chat_route_transport_adapter",
        "chat_runtime_factory_route_free",
        "chat_execution_service_contract_boundary",
        "workbench_runtime_context_contract_boundary",
        "workbench_context_node_route_free_services",
        "workbench_governance_node_route_free_services",
        "graphiti_memory_provider_langchain_boundary",
    ]
    assert provider_conformance["summary"]["runtime_boundary_warnings"] == []
    assert provider_conformance["summary"]["runtime_boundary_blockers"] == []
    plan_v8_artifacts = payload["plan_v8_artifacts"]
    assert plan_v8_artifacts["status"] == "warning"
    assert plan_v8_artifacts["artifact_count"] == 11
    assert plan_v8_artifacts["agent_server_smoke_count"] == 1
    assert plan_v8_artifacts["chat_visible_response_matrix_count"] == 1
    assert plan_v8_artifacts["live_provider_readiness_count"] == 1
    assert plan_v8_artifacts["live_provider_soak_evidence_count"] == 1
    assert plan_v8_artifacts["plane_scope_discovery_smoke_count"] == 1
    assert plan_v8_artifacts["plane_ticket_action_smoke_count"] == 1
    assert plan_v8_artifacts["ticket_loop_worker_soak_count"] == 1
    assert plan_v8_artifacts["context_retrieval_eval_count"] == 1
    assert plan_v8_artifacts["asset_provenance_eval_count"] == 1
    assert plan_v8_artifacts["plan_v8_readiness_count"] == 1
    assert plan_v8_artifacts["employee_growth_eval_count"] == 1
    assert plan_v8_artifacts["evidence_gaps"] == []
    assert plan_v8_artifacts["provider_blockers"] == [
        "ticket_provider_not_ready",
        "memory_provider_not_ready",
        "live_provider_dogfood_not_confirmed",
    ]
    assert plan_v8_artifacts["latest_agent_server_smoke"]["summary"]["visible_response_version"] == "chat_visible_response.v1"
    assert plan_v8_artifacts["latest_chat_visible_response_matrix"]["summary"]["passed_case_count"] == 5
    assert plan_v8_artifacts["latest_chat_visible_response_matrix"]["summary"]["observed_states"] == [
        "completed",
        "blocked",
        "needs_approval",
        "handoff",
        "provider_blocker",
    ]
    assert plan_v8_artifacts["latest_live_provider_readiness"]["summary"]["readiness_status"] == "blocked"
    assert plan_v8_artifacts["latest_live_provider_readiness"]["summary"]["ticket_backend_release_target_status"] == "blocked"
    assert plan_v8_artifacts["latest_live_provider_readiness"]["summary"]["ticket_backend_release_target_blockers"] == ["plane_api_key_missing"]
    assert plan_v8_artifacts["latest_live_provider_soak_evidence"]["summary"]["blocked_scenario_count"] == 5
    assert plan_v8_artifacts["latest_plane_scope_discovery_smoke"]["summary"]["discovery_status"] == "ready"
    assert plan_v8_artifacts["latest_plane_scope_discovery_smoke"]["summary"]["suggestion_count"] == 1
    assert plan_v8_artifacts["latest_plane_scope_discovery_smoke"]["summary"]["external_mutation"] is False
    assert plan_v8_artifacts["latest_plane_ticket_action_smoke"]["summary"]["provider"] == "plane"
    assert plan_v8_artifacts["latest_plane_ticket_action_smoke"]["summary"]["confirm_env_var"] == "AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    assert plan_v8_artifacts["latest_ticket_loop_worker_soak"]["summary"]["worker_processed_delta"] == 2
    assert plan_v8_artifacts["latest_ticket_loop_worker_soak"]["summary"]["worker_policy_action_delta"] == 1
    assert plan_v8_artifacts["latest_ticket_loop_worker_soak"]["summary"]["asset_candidate_count"] == 1
    assert plan_v8_artifacts["latest_ticket_loop_worker_soak"]["summary"]["daemon_status"] == "passed"
    assert plan_v8_artifacts["latest_context_retrieval_eval"]["summary"]["wrong_ticket_filtered"] is True
    assert plan_v8_artifacts["latest_context_retrieval_eval"]["summary"]["work_history_eval_recall"] == 1.0
    assert plan_v8_artifacts["latest_context_retrieval_eval"]["summary"]["recalled_memory_ids"] == [
        "mem-context-retrieval-note"
    ]
    assert plan_v8_artifacts["latest_asset_provenance_eval"]["summary"]["stale_active_filtered"] is True
    assert plan_v8_artifacts["latest_asset_provenance_eval"]["summary"]["relationship_search_result_count"] == 1
    assert plan_v8_artifacts["latest_plan_v8_readiness"]["summary"]["blocked_count"] == 1
    assert plan_v8_artifacts["latest_plan_v8_readiness"]["summary"]["ready_for_release"] is False
    assert plan_v8_artifacts["latest_employee_growth_eval"]["summary"]["employee_id"] == "alex"
    assert plan_v8_artifacts["latest_employee_growth_eval"]["summary"]["quality_feedback_count"] == 2
    assert plan_v8_artifacts["latest_employee_growth_eval"]["summary"]["handoff_work_history_score"] == 3
    assert plan_v8_artifacts["latest_employee_growth_eval"]["summary"]["improvement_loop_proof_status"] == "passed"
    assert plan_v8_artifacts["latest_employee_growth_eval"]["summary"]["improvement_loop_application_status"] == "applied"
    assert plan_v8_artifacts["latest_employee_growth_eval"]["summary"]["improvement_loop_ticket_report_id"] == "report-employee-growth-proof"
    assert plan_v8_artifacts["evidence_warnings"] == []
    artifact_status = client.get("/api/v1/system-status/plan-v8-artifacts")
    assert artifact_status.status_code == 200
    assert artifact_status.json()["latest_agent_server_smoke"]["name"] == "track-c-agent-server-smoke.json"
    assert artifact_status.json()["latest_plane_scope_discovery_smoke"]["name"] == "track-c-plane-scope-discovery-smoke.json"
    assert artifact_status.json()["latest_ticket_loop_worker_soak"]["name"] == "track-c-ticket-loop-worker-soak.json"
    assert artifact_status.json()["latest_plan_v8_readiness"]["name"] == "track-g-plan-v8-readiness.json"
    assert artifact_status.json()["latest_employee_growth_eval"]["name"] == "track-e-employee-growth-eval-smoke.json"
    plan_v8_readiness = payload["plan_v8_readiness"]
    assert plan_v8_readiness["contract_version"] == "aiteamos_plan_v8_readiness.v1"
    assert plan_v8_readiness["status"] == "blocked"
    assert plan_v8_readiness["summary"]["ready_for_release"] is False
    assert plan_v8_readiness["summary"]["blocked_count"] >= 1
    assert plan_v8_readiness["summary"]["next_steps"]
    assert any("Settings -> Ticket Backend" in step for step in plan_v8_readiness["summary"]["next_steps"])
    assert plan_v8_readiness["summary"]["next_step_actions"]
    assert any(
        item["href"] == "#/settings/ticket-backend"
        for item in plan_v8_readiness["summary"]["next_step_actions"]
    )
    readiness_actions = {item["id"]: item for item in plan_v8_readiness["summary"]["next_step_actions"]}
    assert readiness_actions["run_live_provider_readiness_smoke"]["command"].startswith(
        "python scripts/live_provider_readiness_smoke.py"
    )
    assert readiness_actions["run_live_provider_readiness_smoke"]["mutation_gate_required"] is False
    assert readiness_actions["run_live_provider_readiness_smoke"]["status"] == "ready_to_run"
    assert readiness_actions["complete_code_repository_plane_scope"]["status"] in {"missing", "incomplete", "blocked"}
    assert readiness_actions["complete_code_repository_plane_scope"]["evidence"]["scope_missing"] >= 0
    assert (
        readiness_actions["complete_code_repository_plane_scope"]["evidence"]["discovery_endpoint"]
        == "/api/v1/tickets/backend/plane-scope/discovery"
    )
    assert readiness_actions["complete_code_repository_plane_scope"]["evidence"]["discovery_ui_action"] == "Discover Plane scope"
    assert readiness_actions["complete_code_repository_plane_scope"]["evidence"]["external_mutation"] is False
    assert isinstance(readiness_actions["apply_plane_ticket_backend"]["evidence"]["plane_selected"], bool)
    assert readiness_actions["apply_plane_ticket_backend"]["evidence"]["release_target_status"] == "blocked"
    assert readiness_actions["apply_plane_ticket_backend"]["evidence"]["release_target_ready"] is False
    assert readiness_actions["apply_plane_ticket_backend"]["evidence"]["release_target_blockers"]
    assert readiness_actions["apply_plane_ticket_backend"]["status"] in {"ready", "setup_blocked"}
    assert readiness_actions["keep_mutation_gate_closed"]["command"] == "unset AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    assert readiness_actions["keep_mutation_gate_closed"]["mutation_gate_required"] is True
    assert readiness_actions["keep_mutation_gate_closed"]["status"] in {"closed", "open"}
    assert readiness_actions["keep_mutation_gate_closed"]["evidence"]["confirm_env_var"] == "AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    assert "track-c-ticket-loop-worker-soak.json" in plan_v8_readiness["evidence_refs"]
    assert "track-e-employee-growth-eval-smoke.json" in plan_v8_readiness["evidence_refs"]
    checks_by_id = {item["id"]: item for item in plan_v8_readiness["checks"]}
    assert checks_by_id["chat_visible_response"]["status"] == "passed"
    assert checks_by_id["chat_visible_response"]["evidence"]["matrix_artifact"] == "track-a-chat-visible-response-matrix.json"
    assert checks_by_id["chat_visible_response"]["evidence"]["matrix_passed_case_count"] == 5
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["plane_ticket_action_smoke_count"] == 1
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["plane_scope_discovery_smoke_count"] == 1
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["plane_scope_discovery_status"] == "ready"
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["plane_scope_discovery_suggestion_count"] == 1
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["plane_scope_discovery_external_mutation"] is False
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["plane_ticket_action_smoke_status"] == "dry_run"
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["plan_v8_readiness_count"] == 1
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["employee_growth_eval_count"] == 1
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["employee_growth_warning_count"] == 0
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["employee_growth_improvement_loop_proof_status"] == "passed"
    assert checks_by_id["plan_v8_artifact_evidence"]["evidence"]["employee_growth_improvement_loop_application_status"] == "applied"
    assert checks_by_id["provider_boundary"]["evidence"]["runtime_boundary_status"] == "passed"
    assert checks_by_id["provider_boundary"]["evidence"]["runtime_boundary_blocker_count"] == 0
    assert "chat_route_transport_adapter" in checks_by_id["provider_boundary"]["evidence"]["runtime_boundary_checks"]
    assert "workbench_runtime_context_contract_boundary" in checks_by_id["provider_boundary"]["evidence"]["runtime_boundary_checks"]
    assert "workbench_context_node_route_free_services" in checks_by_id["provider_boundary"]["evidence"]["runtime_boundary_checks"]
    assert "workbench_governance_node_route_free_services" in checks_by_id["provider_boundary"]["evidence"]["runtime_boundary_checks"]
    assert "graphiti_memory_provider_langchain_boundary" in checks_by_id["provider_boundary"]["evidence"]["runtime_boundary_checks"]
    assert checks_by_id["live_provider_dogfood"]["status"] == "blocked"
    assert checks_by_id["release_hygiene"]["status"] == "warning"
    assert (
        "python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json"
        in plan_v8_readiness["commands"]
    )
    assert (
        "python scripts/plane_scope_discovery_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-plane-scope-discovery-smoke.json"
        in plan_v8_readiness["commands"]
    )
    assert (
        "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json"
        in plan_v8_readiness["commands"]
    )
    readiness_status = client.get("/api/v1/system-status/plan-v8-readiness")
    assert readiness_status.status_code == 200
    assert readiness_status.json()["contract_version"] == "aiteamos_plan_v8_readiness.v1"
    release_hygiene = payload["release_hygiene"]
    assert release_hygiene["contract_version"] == "aiteamos_release_hygiene.v1"
    assert release_hygiene["status"] == "warning"
    assert release_hygiene["summary"]["source_count"] >= 1
    assert release_hygiene["summary"]["generated_artifact_count"] >= 1
    assert release_hygiene["summary"]["local_projection_count"] >= 1
    assert release_hygiene["summary"]["unknown_count"] == 0
    assert release_hygiene["category_samples"]["source"]
    assert release_hygiene["category_samples"]["generated_artifact"]
    assert release_hygiene["category_samples"]["local_projection"]
    assert "git status --short" in release_hygiene["review_commands"]
    assert "python scripts/plan_v8_artifact_summary.py --workspace-dir ." in release_hygiene["review_commands"]
    release_status = client.get("/api/v1/system-status/release-hygiene")
    assert release_status.status_code == 200
    assert release_status.json()["summary"]["source_count"] >= 1
    assert release_status.json()["category_samples"]["generated_artifact"][0]["review_action"] == "retain_as_evidence_or_archive"
    providers = {item["provider_id"]: item for item in provider_conformance["providers"]}
    assert providers["ticket:plane"]["provider_kind"] == "ticket"
    assert providers["ticket:plane"]["status"] == "setup_blocked"
    assert providers["ticket:plane"]["fallback_provider"] == "ticket:local_file"
    assert providers["ticket:plane"]["production_evaluation"]["schema_version"] == "provider_conformance.v1"
    assert providers["ticket:plane"]["production_evaluation"]["migration_status"] == "schema_current"
    assert providers["ticket:plane"]["production_evaluation"]["required_for_core"] is True
    assert providers["ticket:plane"]["production_evaluation"]["production_ready"] is False
    assert providers["ticket:plane"]["production_evaluation"]["readiness_level"] == "degraded_with_fallback"
    assert "ticket:plane:setup" in providers["ticket:plane"]["production_evaluation"]["blockers"]
    assert "PLANE_API_KEY" in providers["ticket:plane"]["setup_blockers"][0]["setup_required"]
    assert providers["ticket:plane"]["conformance_smoke"]["endpoint"] == "/api/v1/tickets/status"
    assert "append_report" in providers["ticket:plane"]["capabilities"]
    assert "provider_ref is a projection pointer, not the domain object" in providers["ticket:plane"]["domain_boundary"]
    ticket_expectations = {item["id"]: item for item in providers["ticket:plane"]["contract_expectations"]}
    assert ticket_expectations["ticket.required_capabilities"]["status"] == "passed"
    assert ticket_expectations["ticket.required_capabilities"]["missing"] == []
    assert "append_report" in ticket_expectations["ticket.required_capabilities"]["satisfied"]
    assert ticket_expectations["ticket.failure_semantics"]["required"] == [
        "missing_config_reports_setup_blocker",
        "provider_error_must_not_mark_ticket_completed",
    ]
    assert providers["asset:local_registry"]["status"] == "ready"
    assert providers["asset:local_registry"]["conformance_smoke"]["endpoint"] == "/api/v1/assets/candidates"
    assert providers["asset:local_registry"]["production_evaluation"]["production_ready"] is True
    assert providers["asset:local_registry"]["production_evaluation"]["readiness_level"] == "production_ready"
    asset_expectations = {item["id"]: item for item in providers["asset:local_registry"]["contract_expectations"]}
    assert asset_expectations["asset.domain_boundary"]["status"] == "passed"
    assert providers["employee:local_profiles"]["status"] == "ready"
    assert providers["employee:local_profiles"]["conformance_smoke"]["endpoint"] == "/api/v1/chat/employees"
    employee_expectations = {item["id"]: item for item in providers["employee:local_profiles"]["contract_expectations"]}
    assert employee_expectations["employee.required_capabilities"]["status"] == "passed"
    assert providers["memory:graphiti"]["status"] == "disabled"
    assert providers["memory:graphiti"]["fallback_provider"] == "asset:local_registry"
    assert "disabled_graphiti_keeps_local_asset_and_memory_registry_available" in providers["memory:graphiti"]["failure_semantics"]
    memory_expectations = {item["id"]: item for item in providers["memory:graphiti"]["contract_expectations"]}
    assert memory_expectations["memory.failure_semantics"]["status"] == "passed"
    assert providers["runtime:claude_code"]["conformance_smoke"]["endpoint"] == "/api/v1/runtime-executors/claude_code/smoke"
    assert providers["runtime:claude_code"]["setup_blockers"][0]["setup_required"] == ["CLAUDE_CODE_BIN"]
    assert "repo_write_requires_approval" in providers["runtime:claude_code"]["failure_semantics"]
    runtime_expectations = {item["id"]: item for item in providers["runtime:claude_code"]["contract_expectations"]}
    assert runtime_expectations["runtime.repo_write_guard"]["status"] == "passed"
    assert runtime_expectations["runtime.domain_boundary"]["satisfied"] == [
        "RuntimeProvider executes agent/tool work behind ExecutionRequest/ExecutionResult",
        "Chat route remains entry/bridge, not an agent loop",
        "writes return governed artifacts and pass through ingestion",
    ]
    executors = {item["executor_id"]: item for item in payload["runtime_executors"]}
    assert "direct_llm" not in executors
    assert executors["langgraph"]["status"] == "ready"
    assert "answer_only" in executors["langgraph"]["capabilities"]
    assert executors["universal_employee_agent"]["status"] == "ready"
    assert "employee_agent_loop" in executors["universal_employee_agent"]["capabilities"]
    assert executors["claude_code"]["status"] == "setup_blocked"
    assert executors["claude_code"]["missing_env"] == ["CLAUDE_CODE_BIN"]
    assert executors["claude_code"]["config"]["api_key_env"] == ""
    assert executors["claude_code"]["delivery"]["configured_mode"] == "handoff"
    assert executors["claude_code"]["delivery"]["supported_modes"] == ["local_cli"]
    assert executors["claude_code"]["delivery"]["prompt_delivery"] == "artifact_handoff"
    assert executors["claude_code"]["config_env"]["binary_path"] == "CLAUDE_CODE_BIN"
    assert executors["claude_code"]["config_env"]["api_base_url"] == "CLAUDE_CODE_API_BASE_URL"
    assert executors["claude_code"]["expected_output_schema"]["tool_events"] == "list[dict]"
    assert executors["claude_code"]["expected_output_schema"]["approval_requests"] == "list[dict]"
    assert executors["claude_code"]["diagnostics"]["smoke"]["endpoint"] == "/api/v1/runtime-executors/claude_code/smoke"
    assert executors["claude_code"]["diagnostics"]["smoke"]["method"] == "POST"
    assert executors["claude_code"]["diagnostics"]["smoke"]["default_ingest_result"] is False
    assert executors["claude_code"]["diagnostics"]["smoke"]["ingest_requires_ticket"] is True
    assert executors["claude_code"]["diagnostics"]["smoke"]["dispatch_boundary"] == "RuntimeExecutor"
    assert executors["claude_code"]["diagnostics"]["dogfood"]["endpoint"] == "/api/v1/runtime-executors/dogfood"
    assert executors["claude_code"]["diagnostics"]["dogfood"]["approval_required"] is True
    assert executors["claude_code"]["diagnostics"]["dogfood"]["creates_ticket_if_missing"] is True
    assert executors["claude_code"]["diagnostics"]["dogfood"]["repo_mutation_guard"] == [
        "ticket_bound",
        "approval_bound",
        "evidence_bound",
    ]
    assert "compatible_local_cli" in executors["claude_code"]["capabilities"]
    assert executors["codex_cli"]["status"] == "ready"
    assert executors["codex_cli"]["config"]["binary_path"] == str(fake_codex)
    assert "repo:write" in executors["codex_cli"]["capabilities"]
    assert executors["codex_cli"]["diagnostics"]["dogfood"]["endpoint"] == "/api/v1/runtime-executors/dogfood"
    assert executors["cursor"]["status"] == "setup_blocked"
    assert executors["cursor"]["missing_env"] == ["CURSOR_API_KEY"]
    assert executors["cursor"]["delivery"]["supported_modes"] == ["http"]
    assert executors["cursor"]["config_env"]["http_endpoint_path"] == "CURSOR_INSPECT_ENDPOINT"
    assert executors["cursor"]["expected_output_schema"]["status"].startswith("completed")
    assert "repo:write" in executors["cursor"]["capabilities"]
    assert "inspect_code_repository" in executors["cursor"]["supported_actions"]
    assert executors["cursor"]["safety_policy"]["default_mode"] == "non_destructive_inspect_and_report"
    assert executors["cursor"]["safety_policy"]["repo_mutation_guard"] == [
        "ticket_bound",
        "approval_bound",
        "evidence_bound",
        "repo_write_capability_required",
    ]
    assert executors["cursor"]["safety_policy"]["completion_policy"] == "external_runtime_completion_must_not_be_faked"
    live_dogfood = payload["live_provider_dogfood"]
    assert live_dogfood["status"] == "blocked"
    assert live_dogfood["profile"] == "core_loop"
    assert live_dogfood["selected_executor_id"] == "langgraph"
    assert live_dogfood["require_repo_write_executor"] is False
    assert live_dogfood["selected_executor_preflight"]["status"] == "passed"
    assert live_dogfood["selected_executor_preflight"]["blockers"] == []
    assert live_dogfood["summary"]["repo_write_ready_count"] == 1
    assert live_dogfood["provider_prerequisites"]["provider_smoke"]["status"] == "not_run"
    live_candidate_ids = {item["executor_id"] for item in live_dogfood["repo_write_executor_candidates"]}
    assert {"claude_code", "codex_cli", "cursor"} <= live_candidate_ids
    live_blocker_reasons = {item["reason"] for item in live_dogfood["blockers"]}
    assert "runtime_executor_lacks_repo_write" not in live_blocker_reasons
    assert "no_ready_repo_write_runtime_executor" not in live_blocker_reasons
    assert "ticket_provider_not_ready" in live_blocker_reasons
    assert "memory_provider_not_ready" in live_blocker_reasons
    soak_plan = payload["live_provider_soak_plan"]
    assert soak_plan["contract_version"] == "aiteamos_live_provider_soak_plan.v1"
    assert soak_plan["status"] == "blocked"
    assert soak_plan["summary"]["scenario_count"] == 6
    assert soak_plan["summary"]["blocked_scenario_count"] == 6
    assert "completed" in soak_plan["summary"]["expected_states"]
    assert "handoff" in soak_plan["summary"]["expected_states"]
    assert "approval" in soak_plan["summary"]["expected_states"]
    assert "preflight" in soak_plan["summary"]["expected_states"]
    assert "retry" in soak_plan["summary"]["expected_states"]
    assert "live_provider_dogfood_not_confirmed" in soak_plan["blockers"]
    assert any(item["id"] == "core_loop_completed_closeout_asset" for item in soak_plan["scenarios"])
    assert any(item["id"] == "plane_ticket_action_preflight" for item in soak_plan["scenarios"])
    assert any("live_provider_soak_plan.py" in command for command in soak_plan["commands"])
    assert any("plane_ticket_action_smoke.py" in command for command in soak_plan["commands"])
    soak_plan_status = client.get("/api/v1/system-status/live-provider-soak-plan")
    assert soak_plan_status.status_code == 200
    assert soak_plan_status.json()["contract_version"] == "aiteamos_live_provider_soak_plan.v1"
    soak_evidence = payload["live_provider_soak_evidence"]
    assert soak_evidence["contract_version"] == "aiteamos_live_provider_soak_evidence.v1"
    assert soak_evidence["status"] == "blocked"
    assert soak_evidence["summary"]["scenario_count"] == 6
    assert soak_evidence["summary"]["passed_scenario_count"] == 2
    assert soak_evidence["summary"]["blocked_scenario_count"] == 4
    assert soak_evidence["summary"]["passed_non_mutating_scenario_count"] == 2
    assert "track-c-plane-ticket-action-smoke.json" in soak_evidence["evidence_refs"]
    assert "track-c-ticket-loop-worker-soak.json" in soak_evidence["evidence_refs"]
    assert soak_evidence["summary"]["ready_for_release"] is False
    assert "live_provider_dogfood_not_confirmed" in soak_evidence["blockers"]
    assert {item["id"] for item in soak_evidence["scenarios"]} >= {
        "core_loop_completed_closeout_asset",
        "natural_handoff",
        "approval_and_asset_governance",
        "provider_blocker_visibility",
        "plane_ticket_action_preflight",
        "retry_resume_closeout",
    }
    assert all(item["artifact_name"] for item in soak_evidence["scenarios"])
    retry_scenario = {item["id"]: item for item in soak_evidence["scenarios"]}["retry_resume_closeout"]
    assert retry_scenario["status"] == "passed"
    assert retry_scenario["artifact_name"] == "track-c-ticket-loop-worker-soak.json"
    plane_preflight = {item["id"]: item for item in soak_evidence["scenarios"]}["plane_ticket_action_preflight"]
    assert plane_preflight["status"] == "passed"
    assert plane_preflight["artifact_status"] == "dry_run"
    assert plane_preflight["operator_action"] == "covered"
    assert any("live_provider_soak_evidence.py" in command for command in soak_evidence["commands"])
    assert any("plane_ticket_action_smoke.py" in command for command in soak_evidence["commands"])
    soak_evidence_status = client.get("/api/v1/system-status/live-provider-soak-evidence")
    assert soak_evidence_status.status_code == 200
    assert soak_evidence_status.json()["contract_version"] == "aiteamos_live_provider_soak_evidence.v1"
    blockers = {item["id"]: item for item in payload["blockers"]}
    assert blockers["ticket_backend"]["status"] == "setup_blocked"
    assert blockers["memory_asset_graph_backend"]["status"] == "disabled"
    assert blockers["runtime_executor:claude_code"]["status"] == "setup_blocked"
    assert blockers["runtime_executor:claude_code"]["setup_required"] == ["CLAUDE_CODE_BIN"]
    assert blockers["runtime_executor:cursor"]["status"] == "setup_blocked"
    assert blockers["runtime_executor:cursor"]["setup_required"] == ["CURSOR_API_KEY"]
    assert blockers["live_provider_dogfood"]["status"] == "blocked"
    assert "select a ready RuntimeExecutor with repo:write" not in blockers["live_provider_dogfood"]["setup_required"]
    assert "runtime_executor_lacks_repo_write" not in blockers["live_provider_dogfood"]["reasons"]
    assert "live_provider_dogfood_not_confirmed" in blockers["live_provider_dogfood"]["reasons"]
    assert blockers["live_provider_dogfood"]["summary"]["profile"] == "core_loop"
    assert blockers["live_provider_dogfood"]["summary"]["selected_executor_id"] == "langgraph"
    assert blockers["live_provider_dogfood"]["summary"]["repo_write_ready_count"] == 1
    assert blockers["live_provider_dogfood"]["summary"]["mutation_gate_open"] is False
    live_related_blockers = {item["reason"]: item for item in blockers["live_provider_dogfood"]["related_blockers"]}
    assert live_related_blockers["live_provider_dogfood_not_confirmed"]["status"] == "confirmation_required"
    live_related_candidates = {item["executor_id"]: item for item in blockers["live_provider_dogfood"]["related_candidates"]}
    assert live_related_candidates["codex_cli"]["ready"] is True
    assert live_related_candidates["claude_code"]["setup_required"] == ["CLAUDE_CODE_BIN"]

    conformance = client.get("/api/v1/system-status/providers")
    assert conformance.status_code == 200
    conformance_payload = conformance.json()
    assert conformance_payload["summary"]["provider_count"] >= 5
    assert {item["provider_kind"] for item in conformance_payload["providers"]} >= {
        "ticket",
        "asset",
        "memory",
        "employee",
        "runtime",
    }

    checks = client.get("/api/v1/system-status/providers/checks")
    assert checks.status_code == 200
    checks_payload = checks.json()
    assert checks_payload["status"] == "passed"
    assert checks_payload["summary"]["external_calls"] is False
    assert checks_payload["summary"]["evaluation_scope"] == "metadata_contract_only"
    checks_by_provider = {item["provider_id"]: item for item in checks_payload["checks"]}
    assert checks_by_provider["ticket:plane"]["status"] == "passed"
    assert "setup_blocker_reported" in checks_by_provider["ticket:plane"]["checks"]
    assert "contract:ticket.required_capabilities" in checks_by_provider["ticket:plane"]["checks"]
    assert "contract:ticket.failure_semantics" in checks_by_provider["ticket:plane"]["checks"]
    assert "production_evaluation" in checks_by_provider["ticket:plane"]["checks"]
    assert "readiness:degraded_with_fallback" in checks_by_provider["ticket:plane"]["checks"]
    assert "contract_schema_current" in checks_by_provider["ticket:plane"]["checks"]
    assert "fallback_provider" in checks_by_provider["ticket:plane"]["checks"]
    assert checks_by_provider["memory:graphiti"]["status"] == "passed"
    assert "contract:memory.domain_boundary" in checks_by_provider["memory:graphiti"]["checks"]
    assert "fallback_provider" in checks_by_provider["memory:graphiti"]["checks"]
    assert checks_by_provider["runtime:claude_code"]["status"] == "passed"
    assert "repo_write_guard" in checks_by_provider["runtime:claude_code"]["checks"]
    assert "contract:runtime.repo_write_guard" in checks_by_provider["runtime:claude_code"]["checks"]
    assert checks_by_provider["runtime:codex_cli"]["status"] == "passed"
    assert "contract:runtime.repo_write_guard" in checks_by_provider["runtime:codex_cli"]["checks"]

    smoke = client.get("/api/v1/system-status/providers/smoke")
    assert smoke.status_code == 200
    smoke_payload = smoke.json()
    assert smoke_payload["status"] == "passed"
    assert smoke_payload["summary"]["evaluation_scope"] == "provider_status_and_adapter_health"
    assert smoke_payload["summary"]["non_destructive"] is True
    assert smoke_payload["summary"]["external_calls"] is False
    smoke_by_provider = {item["provider_id"]: item for item in smoke_payload["results"]}
    assert smoke_by_provider["ticket:plane"]["status"] == "setup_blocked"
    assert smoke_by_provider["ticket:plane"]["smoke_kind"] == "ticket_backend_status"
    assert "ticket_backend_status_read" in smoke_by_provider["ticket:plane"]["checks"]
    assert "no_fake_success_for_blocked_provider" in smoke_by_provider["ticket:plane"]["checks"]
    assert "external_provider_smoke_skipped" in smoke_by_provider["ticket:plane"]["warnings"]
    assert "PLANE_API_KEY" in smoke_by_provider["ticket:plane"]["blockers"][0]["setup_required"]
    assert smoke_by_provider["ticket:plane"]["evidence"]["ticket_backend_status"]["status"] == "setup_blocked"
    assert smoke_by_provider["asset:local_registry"]["status"] == "passed"
    assert "asset_registry_contract_read" in smoke_by_provider["asset:local_registry"]["checks"]
    assert smoke_by_provider["employee:local_profiles"]["status"] == "passed"
    assert "employee_provider_contract_read" in smoke_by_provider["employee:local_profiles"]["checks"]
    assert smoke_by_provider["memory:graphiti"]["status"] == "disabled"
    assert "memory_backend_status_read" in smoke_by_provider["memory:graphiti"]["checks"]
    assert "external_provider_smoke_skipped" in smoke_by_provider["memory:graphiti"]["warnings"]
    assert smoke_by_provider["runtime:claude_code"]["status"] == "setup_blocked"
    assert "runtime_executor_health_read" in smoke_by_provider["runtime:claude_code"]["checks"]
    assert smoke_by_provider["runtime:codex_cli"]["status"] == "passed"
    assert "runtime:direct_llm" not in smoke_by_provider
    assert smoke_by_provider["runtime:langgraph"]["status"] == "passed"
    assert smoke_by_provider["runtime:langgraph"]["evidence"]["runtime_executor"]["executor_id"] == "langgraph"

    schema_registry = payload["schema_registry"]
    assert schema_registry["contract_version"] == "aiteamos_schema_registry.v1"
    assert schema_registry["status"] == "passed"
    assert schema_registry["summary"]["store_count"] == 8
    assert schema_registry["summary"]["current_count"] == 8
    assert schema_registry["summary"]["migration_required_count"] == 0
    assert schema_registry["summary"]["covered_domains"] == ["assets", "employees", "runtime", "tickets"]
    stores = {item["id"]: item for item in schema_registry["stores"]}
    assert stores["execution.sessions"]["schema_version"] == "execution_sessions.v1"
    assert stores["execution.sessions"]["actual_shape"] == "object_map"
    assert stores["execution.sessions"]["item_count"] == 1
    assert stores["execution.sessions"]["migration_status"] == "schema_current"
    assert stores["execution.sessions"]["path"] == ".aiteamos/execution_sessions.json"
    assert stores["execution.approvals"]["schema_version"] == "execution_approvals.v1"
    assert stores["assets.candidates"]["schema_version"] == "asset_candidates.v1"
    assert stores["assets.records"]["schema_version"] == "asset_records.v1"
    assert stores["assets.reviews"]["schema_version"] == "asset_reviews.v1"
    assert stores["assets.retrieval_evaluations"]["schema_version"] == "asset_retrieval_evaluations.v1"
    assert stores["employees.local_profiles"]["actual_shape"] == "directory"
    assert stores["employees.local_profiles"]["item_count"] == 1
    assert stores["tickets.projection"]["schema_version"] == "ticket_projection.v1"
    assert "Tickets are the collaboration" in stores["tickets.projection"]["provenance_boundary"]

    schema = client.get("/api/v1/system-status/schema")
    assert schema.status_code == 200
    schema_payload = schema.json()
    assert schema_payload["summary"]["current_count"] == 8

    environment = client.get("/api/v1/system-status/environment-smoke")
    assert environment.status_code == 200
    environment_payload = environment.json()
    assert environment_payload["status"] == "setup_blocked"
    assert environment_payload["summary"]["evaluation_scope"] == "environment_readiness_with_provider_smoke"
    assert environment_payload["summary"]["non_destructive"] is True
    assert environment_payload["summary"]["external_calls"] is False
    assert environment_payload["summary"]["include_external"] is False
    environment_checks = {item["id"]: item for item in environment_payload["checks"]}
    assert environment_checks["ai_engine:deepseek"]["status"] == "setup_blocked"
    assert "langchain_model_provider_config_inspected" in environment_checks["ai_engine:deepseek"]["checks"]
    assert "no_external_llm_call" in environment_checks["ai_engine:deepseek"]["checks"]
    assert environment_checks["ai_engine:deepseek"]["blockers"][0]["setup_required"] == ["DEEPSEEK_API_KEY"]
    assert environment_checks["providers:core"]["status"] == "setup_blocked"
    assert "provider_conformance_smoke_run" in environment_checks["providers:core"]["checks"]
    assert "external_provider_smoke_not_requested" in environment_checks["providers:core"]["checks"]
    assert any(blocker.get("provider_id") == "ticket:plane" for blocker in environment_checks["providers:core"]["blockers"])
    assert any(warning.startswith("optional_provider_setup_blocked:runtime:") for warning in environment_checks["providers:core"]["warnings"])
    assert environment_checks["fallback:local"]["status"] == "passed"
    assert "local_asset_registry_ready" in environment_checks["fallback:local"]["checks"]
    assert "ticket_local_file_fallback_declared" in environment_checks["fallback:local"]["checks"]
    assert environment_checks["runtime:agent_loop"]["status"] == "passed"
    assert "chat_route_bridge_boundary" in environment_checks["runtime:agent_loop"]["checks"]
    assert "runtime_boundary_source_audited" in environment_checks["runtime:agent_loop"]["checks"]
    assert "chat_route_transport_adapter" in environment_checks["runtime:agent_loop"]["checks"]
    assert "chat_runtime_factory_route_free" in environment_checks["runtime:agent_loop"]["checks"]
    assert "workbench_runtime_context_contract_boundary" in environment_checks["runtime:agent_loop"]["checks"]
    assert "workbench_context_node_route_free_services" in environment_checks["runtime:agent_loop"]["checks"]
    assert "workbench_governance_node_route_free_services" in environment_checks["runtime:agent_loop"]["checks"]
    assert "graphiti_memory_provider_langchain_boundary" in environment_checks["runtime:agent_loop"]["checks"]
    assert environment_checks["runtime:agent_loop"]["warnings"] == []
    runtime_boundary_audit = environment_checks["runtime:agent_loop"]["evidence"]["runtime_boundary_audit"]
    assert runtime_boundary_audit["contract_version"] == "aiteamos_runtime_boundary_audit.v1"
    assert runtime_boundary_audit["summary"]["blocked_count"] == 0
    assert runtime_boundary_audit["summary"]["chat_route_line_count"] < 350
    assert runtime_boundary_audit["summary"]["workbench_context_line_count"] < 300
    assert runtime_boundary_audit["summary"]["workbench_context_node_line_count"] < 420
    assert runtime_boundary_audit["summary"]["workbench_governance_node_line_count"] < 450


def test_schema_registry_reports_invalid_json_blocker(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    workspace = tmp_path / ".aiteamos"
    workspace.mkdir(parents=True)
    (workspace / "execution_sessions.json").write_text("{not-json", encoding="utf-8")

    client = TestClient(create_app())

    response = client.get("/api/v1/system-status/schema")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["summary"]["invalid_count"] == 1
    assert payload["summary"]["migration_required_count"] == 1
    stores = {item["id"]: item for item in payload["stores"]}
    assert stores["execution.sessions"]["status"] == "invalid"
    assert stores["execution.sessions"]["migration_status"] == "migration_blocked"
    assert stores["execution.sessions"]["migration_required"] is True
    assert stores["execution.sessions"]["blockers"][0].startswith("invalid_json:")


def test_environment_smoke_script_outputs_redacted_readiness_payload(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env["OPENAI_API_KEY"] = "openai-test-key"
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("PLANE_API_KEY", None)
    env.pop("AITEAMOS_GRAPHITI_PASSWORD", None)
    env.pop("NEO4J_PASSWORD", None)
    env.pop("AITEAMOS_NEO4J_PASSWORD", None)

    completed = subprocess.run(
        [sys.executable, "scripts/environment_smoke.py"],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.environment_smoke.cli.v1"
    assert payload["workspace_dir"] == str(tmp_path)
    assert payload["include_external"] is False
    assert payload["result"]["summary"]["evaluation_scope"] == "environment_readiness_with_provider_smoke"
    assert payload["result"]["summary"]["external_calls"] is False
    checks = {item["id"]: item for item in payload["result"]["checks"]}
    assert checks["ai_engine:deepseek"]["status"] == "setup_blocked"
    assert checks["ai_engine:deepseek"]["blockers"][0]["setup_required"] == ["DEEPSEEK_API_KEY"]
    assert "openai_api_key_configured" in checks["ai_engine:deepseek"]["checks"]
    assert "langchain_model_provider_config_inspected" in checks["ai_engine:deepseek"]["checks"]
    assert "openai-test-key" not in completed.stdout
    assert "no_external_llm_call" in checks["ai_engine:deepseek"]["checks"]


def test_plan_v8_readiness_script_outputs_repeatable_release_payload(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env["OPENAI_API_KEY"] = "openai-test-key"
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("PLANE_API_KEY", None)
    env.pop("AITEAMOS_GRAPHITI_PASSWORD", None)
    env.pop("NEO4J_PASSWORD", None)
    env.pop("AITEAMOS_NEO4J_PASSWORD", None)

    output_path = tmp_path / ".aiteamos" / "artifacts" / "plan_v8" / "track-g-plan-v8-readiness.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/plan_v8_readiness.py",
            "--workspace-dir",
            str(tmp_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.plan_v8_readiness.cli.v1"
    assert payload["workspace_dir"] == str(tmp_path)
    result = payload["result"]
    assert result["contract_version"] == "aiteamos_plan_v8_readiness.v1"
    assert result["status"] == "blocked"
    assert result["summary"]["ready_for_release"] is False
    assert result["summary"]["next_steps"]
    assert any("AITEAMOS_LIVE_PROVIDER_DOGFOOD" in step for step in result["summary"]["next_steps"])
    assert result["summary"]["next_step_actions"]
    assert any(
        item["command"].startswith("python scripts/plane_ticket_action_smoke.py")
        for item in result["summary"]["next_step_actions"]
    )
    actions_by_id = {item["id"]: item for item in result["summary"]["next_step_actions"]}
    assert actions_by_id["run_live_provider_readiness_smoke"]["command"].startswith(
        "python scripts/live_provider_readiness_smoke.py"
    )
    assert actions_by_id["run_live_provider_readiness_smoke"]["mutation_gate_required"] is False
    assert actions_by_id["run_live_provider_readiness_smoke"]["status"] == "ready_to_run"
    assert actions_by_id["complete_code_repository_plane_scope"]["evidence"]["scope_candidates"] >= 0
    assert (
        actions_by_id["complete_code_repository_plane_scope"]["evidence"]["discovery_endpoint"]
        == "/api/v1/tickets/backend/plane-scope/discovery"
    )
    assert actions_by_id["complete_code_repository_plane_scope"]["evidence"]["discovery_ui_action"] == "Discover Plane scope"
    assert actions_by_id["complete_code_repository_plane_scope"]["evidence"]["api_key_configured"] is False
    assert actions_by_id["complete_code_repository_plane_scope"]["evidence"]["external_mutation"] is False
    assert actions_by_id["apply_plane_ticket_backend"]["evidence"]["current_mode"]
    assert actions_by_id["apply_plane_ticket_backend"]["evidence"]["release_target_status"] == "blocked"
    assert actions_by_id["apply_plane_ticket_backend"]["evidence"]["release_target_ready"] is False
    assert "plane_api_key_missing" in actions_by_id["apply_plane_ticket_backend"]["evidence"]["release_target_blockers"]
    assert actions_by_id["keep_mutation_gate_closed"]["command"] == "unset AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    assert actions_by_id["keep_mutation_gate_closed"]["mutation_gate_required"] is True
    assert actions_by_id["keep_mutation_gate_closed"]["status"] == "closed"
    assert (
        "python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json"
        in result["commands"]
    )
    assert (
        "python scripts/plane_scope_discovery_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-plane-scope-discovery-smoke.json"
        in result["commands"]
    )
    assert (
        "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json"
        in result["commands"]
    )
    checks = {item["id"]: item for item in result["checks"]}
    assert checks["chat_visible_response"]["status"] == "blocked"
    assert checks["live_provider_dogfood"]["status"] == "blocked"
    assert "openai-test-key" not in completed.stdout
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema"] == "aiteamos.plan_v8_readiness.cli.v1"


def test_plane_scope_discovery_smoke_outputs_non_mutating_blocker_artifact(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env.pop("PLANE_API_KEY", None)

    output_path = tmp_path / ".aiteamos" / "artifacts" / "plan_v8" / "track-c-plane-scope-discovery-smoke.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/plane_scope_discovery_smoke.py",
            "--workspace-dir",
            str(tmp_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.plane_scope_discovery_smoke.v1"
    assert payload["status"] == "passed"
    assert payload["result"]["status"] == "blocked"
    assert payload["summary"]["discovery_status"] == "blocked"
    assert payload["summary"]["api_key_env"] == "PLANE_API_KEY"
    assert payload["summary"]["api_key_configured"] is False
    assert payload["summary"]["external_calls"] is False
    assert payload["summary"]["external_mutation"] is False
    assert payload["summary"]["suggestion_count"] == 0
    assert payload["summary"]["setup_required"] == ["PLANE_API_KEY"]
    assert "PLANE_API_KEY" in completed.stdout
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema"] == "aiteamos.plane_scope_discovery_smoke.v1"


def test_live_provider_readiness_smoke_outputs_release_target_evidence(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env["OPENAI_API_KEY"] = "openai-test-key"
    env.pop("PLANE_API_KEY", None)
    env.pop("AITEAMOS_LIVE_PROVIDER_DOGFOOD", None)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/live_provider_readiness_smoke.py",
            "--workspace-dir",
            str(tmp_path),
        ],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.live_provider_readiness_smoke.v1"
    assert payload["summary"]["readiness_status"] == "blocked"
    assert payload["summary"]["ticket_backend_release_target_status"] == "blocked"
    assert payload["summary"]["ticket_backend_release_target_ready"] is False
    assert "plane_api_key_missing" in payload["summary"]["ticket_backend_release_target_blockers"]
    assert payload["summary"]["ticket_backend_release_target_setup_action"]


def test_plan_v8_artifact_summary_script_outputs_release_evidence(tmp_path):
    artifact_dir = tmp_path / ".aiteamos" / "artifacts" / "plan_v8"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "track-a-agent-server-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.langgraph_agent_server_ci_smoke.v1",
                "status": "passed",
                "generated_at": "2026-06-23T00:00:00+00:00",
                "assistant_id": "aiteamos_workbench",
                "url": "http://127.0.0.1:2026",
                "smoke": {
                    "status": "passed",
                    "summary": {
                        "runtime_status": {"status": "completed", "current_node": "final_response"},
                        "visible_response": {
                            "version": "chat_visible_response.v1",
                            "display_state": "completed",
                        },
                        "provider_blocker_count": 0,
                        "provider_blocker_reasons": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "artifact-summary.json"
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/plan_v8_artifact_summary.py",
            "--workspace-dir",
            str(tmp_path),
            "--limit",
            "1",
            "--output",
            str(output_path),
        ],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.plan_v8_artifact_summary.cli.v1"
    assert payload["workspace_dir"] == str(tmp_path)
    result = payload["result"]
    assert result["artifact_count"] == 1
    assert result["agent_server_smoke_count"] == 1
    assert result["records"][0]["name"] == "track-a-agent-server-smoke.json"
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload

    blocked = subprocess.run(
        [
            sys.executable,
            "scripts/plan_v8_artifact_summary.py",
            "--workspace-dir",
            str(tmp_path),
            "--fail-on-gap",
        ],
        cwd=ROOT_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 2


def test_chat_visible_response_matrix_script_outputs_five_visible_states(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [sys.executable, "scripts/chat_visible_response_matrix.py", "--workspace-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.chat_visible_response_matrix.cli.v1"
    assert payload["workspace_dir"] == str(tmp_path)
    result = payload["result"]
    assert result["contract_version"] == "aiteamos_chat_visible_response_matrix.v1"
    assert result["status"] == "passed"
    assert result["summary"]["case_count"] == 5
    assert result["summary"]["passed_case_count"] == 5
    assert result["summary"]["observed_states"] == [
        "completed",
        "blocked",
        "needs_approval",
        "handoff",
        "provider_blocker",
    ]
    cases = {item["id"]: item for item in result["cases"]}
    assert cases["provider_blocker"]["visible_response"]["display_state"] == "provider_blocker"
    assert "provider_blocker" in cases["provider_blocker"]["observed_evidence"]
    assert cases["blocked"]["visible_response"]["retry_cause"] == "Plane write failed."
    assert any("chat_visible_response_matrix.py" in command for command in result["commands"])


def test_runtime_boundary_audit_is_source_backed_and_non_blocking():
    from aiteamos_api.read.runtime_boundary_audit_service import runtime_boundary_audit_report

    result = runtime_boundary_audit_report()
    assert result.contract_version == "aiteamos_runtime_boundary_audit.v1"
    assert result.status == "passed"
    assert result.blockers == []
    checks = {item.id: item for item in result.checks}
    assert checks["chat_route_transport_adapter"].status == "passed"
    assert checks["chat_route_transport_adapter"].forbidden_hits == []
    assert checks["chat_runtime_factory_route_free"].status == "passed"
    assert checks["chat_runtime_factory_route_free"].forbidden_hits == []
    assert checks["chat_execution_service_contract_boundary"].status == "passed"
    assert checks["workbench_runtime_context_contract_boundary"].status == "passed"
    assert checks["workbench_runtime_context_contract_boundary"].forbidden_hits == []
    assert checks["workbench_context_node_route_free_services"].status == "passed"
    assert checks["workbench_context_node_route_free_services"].forbidden_hits == []
    assert checks["workbench_governance_node_route_free_services"].status == "passed"
    assert checks["workbench_governance_node_route_free_services"].forbidden_hits == []
    assert checks["graphiti_memory_provider_langchain_boundary"].status == "passed"
    assert checks["graphiti_memory_provider_langchain_boundary"].forbidden_hits == []
    assert result.summary.chat_route_line_count < 350
    assert result.summary.workbench_context_line_count < 300
    assert result.summary.workbench_context_node_line_count < 420
    assert result.summary.workbench_governance_node_line_count < 450
    assert result.warnings == []


def test_live_provider_soak_plan_script_outputs_repeated_soak_matrix(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env.pop("AITEAMOS_LIVE_PROVIDER_DOGFOOD", None)

    completed = subprocess.run(
        [sys.executable, "scripts/live_provider_soak_plan.py", "--workspace-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.live_provider_soak_plan.cli.v1"
    assert payload["workspace_dir"] == str(tmp_path)
    result = payload["result"]
    assert result["contract_version"] == "aiteamos_live_provider_soak_plan.v1"
    assert result["status"] == "blocked"
    assert result["summary"]["scenario_count"] == 6
    scenario_ids = {item["id"] for item in result["scenarios"]}
    assert {
        "core_loop_completed_closeout_asset",
        "natural_handoff",
        "approval_and_asset_governance",
        "provider_blocker_visibility",
        "plane_ticket_action_preflight",
        "retry_resume_closeout",
    } <= scenario_ids
    scenario_by_id = {item["id"]: item for item in result["scenarios"]}
    assert scenario_by_id["retry_resume_closeout"]["required_evidence"] == [
        "retry_cause",
        "ticket_report",
        "queue_reliability",
        "failure_retrospective_candidate",
        "daemon_resume_settlement",
    ]
    assert "live_provider_dogfood_not_confirmed" in result["blockers"]
    assert any("live_provider_soak_plan.py" in command for command in result["commands"])
    assert any("plane_ticket_action_smoke.py" in command for command in result["commands"])
    assert any("ticket_loop_queue_worker_smoke.py" in command for command in result["commands"])


def test_live_provider_soak_evidence_script_outputs_scenario_coverage(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env.pop("AITEAMOS_LIVE_PROVIDER_DOGFOOD", None)

    completed = subprocess.run(
        [sys.executable, "scripts/live_provider_soak_evidence.py", "--workspace-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema"] == "aiteamos.live_provider_soak_evidence.cli.v1"
    assert payload["workspace_dir"] == str(tmp_path)
    result = payload["result"]
    assert result["contract_version"] == "aiteamos_live_provider_soak_evidence.v1"
    assert result["status"] == "blocked"
    assert result["summary"]["scenario_count"] == 6
    assert result["summary"]["blocked_scenario_count"] == 6
    assert result["summary"]["live_write_scenario_count"] == 3
    assert result["summary"]["remaining_live_write_scenario_count"] == 3
    assert result["summary"]["operator_action_required"] is True
    assert result["summary"]["mutation_gate_env_var"] == "AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    assert "Plane Ticket reports / comments" in result["summary"]["live_write_targets"]
    assert result["summary"]["ready_for_release"] is False
    scenario_by_id = {item["id"]: item for item in result["scenarios"]}
    assert scenario_by_id["core_loop_completed_closeout_asset"]["artifact_name"] == "track-c-live-soak-completed.json"
    assert scenario_by_id["core_loop_completed_closeout_asset"]["execution_kind"] == "live_provider_write"
    assert scenario_by_id["core_loop_completed_closeout_asset"]["operator_action"] == "open_live_mutation_gate_and_run_command"
    assert "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1" in scenario_by_id["core_loop_completed_closeout_asset"]["command"]
    assert scenario_by_id["natural_handoff"]["artifact_name"] == "track-c-live-soak-handoff.json"
    assert scenario_by_id["provider_blocker_visibility"]["artifact_name"] == "track-c-live-provider-readiness-smoke.json"
    assert scenario_by_id["provider_blocker_visibility"]["execution_kind"] == "read_only_provider_blocker_smoke"
    assert scenario_by_id["plane_ticket_action_preflight"]["artifact_name"] == "track-c-plane-ticket-action-smoke.json"
    assert scenario_by_id["plane_ticket_action_preflight"]["execution_kind"] == "gated_provider_action_smoke"
    assert "live_provider_dogfood_not_confirmed" in result["blockers"]
    assert any("live_provider_soak_evidence.py" in command for command in result["commands"])
    assert any("plane_ticket_action_smoke.py" in command for command in result["commands"])


def test_live_provider_soak_evidence_counts_expected_blocker_artifact_as_passed(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env.pop("AITEAMOS_LIVE_PROVIDER_DOGFOOD", None)
    artifact_dir = tmp_path / ".aiteamos" / "artifacts" / "plan_v8"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "track-c-live-provider-readiness-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_readiness_smoke.v1",
                "status": "passed",
                "generated_at": "2026-06-21T03:22:59+00:00",
                "result": {
                    "status": "blocked",
                    "profile": "core_loop",
                    "blockers": [
                        {
                            "reason": "live_provider_dogfood_not_confirmed",
                            "scope": "mutation_gate",
                        }
                    ],
                    "summary": {
                        "ticket_backend_status": "ready",
                        "memory_backend_status": "ready",
                    },
                    "provider_prerequisites": {
                        "provider_smoke": {"status": "not_run"},
                    },
                },
                "summary": {
                    "readiness_status": "blocked",
                    "blocker_reasons": ["live_provider_dogfood_not_confirmed"],
                    "blocker_scopes": ["mutation_gate"],
                    "ticket_backend_status": "ready",
                    "memory_backend_status": "ready",
                    "provider_smoke_status": "not_run",
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "scripts/live_provider_soak_evidence.py", "--workspace-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    result = payload["result"]
    assert result["status"] == "blocked"
    assert result["summary"]["scenario_count"] == 6
    assert result["summary"]["passed_scenario_count"] == 1
    assert result["summary"]["blocked_scenario_count"] == 5
    assert result["summary"]["live_write_scenario_count"] == 3
    assert result["summary"]["remaining_live_write_scenario_count"] == 3
    assert result["summary"]["passed_non_mutating_scenario_count"] == 1
    scenario_by_id = {item["id"]: item for item in result["scenarios"]}
    provider_blocker = scenario_by_id["provider_blocker_visibility"]
    assert provider_blocker["status"] == "passed"
    assert provider_blocker["artifact_status"] == "blocked"
    assert provider_blocker["operator_action"] == "covered"
    assert provider_blocker["missing_evidence"] == []
    assert {
        "blocker_reasons",
        "blocker_scopes",
        "ticket_backend_status",
        "memory_backend_status",
        "provider_smoke_status",
    } <= set(provider_blocker["observed_evidence"])


def test_live_provider_soak_evidence_counts_plane_action_dry_run_as_preflight(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env.pop("AITEAMOS_LIVE_PROVIDER_DOGFOOD", None)
    artifact_dir = tmp_path / ".aiteamos" / "artifacts" / "plan_v8"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "track-c-plane-ticket-action-smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.plane_ticket_action_smoke.v1",
                "status": "dry_run",
                "generated_at": "2026-06-23T00:00:00+00:00",
                "result": {
                    "status": "dry_run",
                    "provider": "plane",
                    "checks": ["plane_action_smoke_requested", "plane_action_smoke_mutation_gate_checked"],
                    "blockers": [
                        {
                            "reason": "plane_action_smoke_not_confirmed",
                            "scope": "mutation_gate",
                        }
                    ],
                    "evidence": {
                        "confirm_env_var": "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
                        "confirm_env_configured": False,
                        "ticket_backend_status": {"status": "ready"},
                    },
                    "summary": {
                        "ticket_backend_status": "ready",
                        "mutation_gate_open": False,
                    },
                    "external_calls": False,
                    "mutating": False,
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "scripts/live_provider_soak_evidence.py", "--workspace-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    result = payload["result"]
    assert result["status"] == "blocked"
    assert result["summary"]["scenario_count"] == 6
    assert result["summary"]["passed_scenario_count"] == 1
    assert result["summary"]["blocked_scenario_count"] == 5
    assert result["summary"]["passed_non_mutating_scenario_count"] == 1
    assert "track-c-plane-ticket-action-smoke.json" in result["evidence_refs"]
    scenario_by_id = {item["id"]: item for item in result["scenarios"]}
    plane_preflight = scenario_by_id["plane_ticket_action_preflight"]
    assert plane_preflight["status"] == "passed"
    assert plane_preflight["artifact_status"] == "dry_run"
    assert plane_preflight["execution_kind"] == "gated_provider_action_smoke"
    assert plane_preflight["operator_action"] == "covered"
    assert plane_preflight["missing_evidence"] == []
    assert {
        "ticket_backend_status",
        "plane_action_smoke_guard",
        "confirm_env_var",
    } <= set(plane_preflight["observed_evidence"])


def test_live_provider_soak_evidence_counts_queue_worker_artifact_as_passed(tmp_path):
    env = os.environ.copy()
    env["AITEAMOS_WORKSPACE_DIR"] = str(tmp_path)
    env.pop("AITEAMOS_LIVE_PROVIDER_DOGFOOD", None)
    artifact_dir = tmp_path / ".aiteamos" / "artifacts" / "plan_v8"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "track-c-ticket-loop-worker-soak.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.ticket_loop_queue_worker_smoke.v2",
                "status": "passed",
                "generated_at": "2026-06-21T15:22:34+00:00",
                "summary": {
                    "ticket_id": "ops-queue-worker",
                    "processed_statuses": ["blocked", "blocked"],
                    "after_reliability": {"status": "error"},
                    "asset_candidate_ids": ["asset-candidate-ticket-loop-failure-retrospective-ops-queue-worker"],
                    "daemon_status": "passed",
                    "daemon": {
                        "queue_statuses": ["completed", "completed"],
                        "run_statuses": ["completed", "completed"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "scripts/live_provider_soak_evidence.py", "--workspace-dir", str(tmp_path)],
        cwd=ROOT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    result = payload["result"]
    assert result["status"] == "blocked"
    assert result["summary"]["scenario_count"] == 6
    assert result["summary"]["passed_scenario_count"] == 1
    assert result["summary"]["blocked_scenario_count"] == 5
    assert result["summary"]["live_write_scenario_count"] == 3
    assert result["summary"]["remaining_live_write_scenario_count"] == 3
    assert result["summary"]["passed_non_mutating_scenario_count"] == 1
    assert "track-c-ticket-loop-worker-soak.json" in result["evidence_refs"]
    scenario_by_id = {item["id"]: item for item in result["scenarios"]}
    retry = scenario_by_id["retry_resume_closeout"]
    assert retry["status"] == "passed"
    assert retry["artifact_status"] == "passed"
    assert retry["execution_kind"] == "local_queue_worker"
    assert retry["operator_action"] == "covered"
    assert retry["missing_evidence"] == []
    assert {
        "retry_cause",
        "ticket_report",
        "queue_reliability",
        "failure_retrospective_candidate",
        "daemon_resume_settlement",
    } <= set(retry["observed_evidence"])


def test_provider_conformance_external_smoke_uses_configured_plane_and_graphiti_adapters(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    plane_calls: list[dict] = []

    class FakePlaneResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    class FakePlaneClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, headers, json):
            plane_calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "GET" and url.endswith("/work-items/"):
                return FakePlaneResponse(200, {"results": [{"id": "plane-smoke-1"}], "total_count": 1})
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeGraphiti:
        instances: list["FakeGraphiti"] = []

        def __init__(self, uri, user, password, **kwargs):
            self.uri = uri
            self.user = user
            self.password = password
            self.searches: list[dict] = []
            FakeGraphiti.instances.append(self)

        async def search(self, query, **kwargs):
            self.searches.append({"query": query, "kwargs": kwargs})
            return []

        async def close(self):
            return None

    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)
    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)

    client = TestClient(create_app())
    backend = client.put(
        "/api/v1/tickets/backend",
        json={
            "mode": "plane",
            "plane_api_base_url": "https://plane.test",
            "plane_web_base_url": "https://app.plane.test",
            "plane_workspace_slug": "ait",
            "plane_project_id": "plane-project-1",
            "plane_api_key_env": "PLANE_API_KEY",
        },
    )
    assert backend.status_code == 200
    graphiti = client.put(
        "/api/v1/memory/graphiti/settings",
        json={
            "enabled": True,
            "uri": "bolt://graphiti.test:7687",
            "user": "neo4j",
            "group_id": "aiteamos-test",
            "llm_ai_engine": "openai",
        },
    )
    assert graphiti.status_code == 200

    smoke = client.get("/api/v1/system-status/providers/smoke?include_external=true")

    assert smoke.status_code == 200
    payload = smoke.json()
    assert payload["status"] == "passed"
    assert payload["summary"]["include_external"] is True
    assert payload["summary"]["external_calls"] is True
    by_provider = {item["provider_id"]: item for item in payload["results"]}
    assert by_provider["ticket:plane"]["status"] == "passed"
    assert by_provider["ticket:plane"]["external_calls"] is True
    assert "external_smoke_requested" in by_provider["ticket:plane"]["checks"]
    assert "plane_project_work_items_read" in by_provider["ticket:plane"]["checks"]
    assert by_provider["ticket:plane"]["evidence"]["external_smoke"]["response_keys"] == ["results", "total_count"]
    assert plane_calls[0]["method"] == "GET"
    assert plane_calls[0]["url"] == "https://plane.test/api/v1/workspaces/ait/projects/plane-project-1/work-items/"
    assert plane_calls[0]["headers"]["X-API-Key"] == "plane-test-key"
    assert by_provider["memory:graphiti"]["status"] == "passed"
    assert by_provider["memory:graphiti"]["external_calls"] is True
    assert "graphiti_read_search" in by_provider["memory:graphiti"]["checks"]
    assert by_provider["memory:graphiti"]["evidence"]["external_smoke"]["group_id"] == "aiteamos-test"
    assert FakeGraphiti.instances
    assert FakeGraphiti.instances[-1].searches[-1]["query"] == "AITeamOS provider conformance smoke"
    assert FakeGraphiti.instances[-1].searches[-1]["kwargs"]["group_ids"] == ["aiteamos-test"]

    environment = client.get("/api/v1/system-status/environment-smoke?include_external=true")

    assert environment.status_code == 200
    environment_payload = environment.json()
    assert environment_payload["status"] == "warning"
    assert environment_payload["summary"]["include_external"] is True
    assert environment_payload["summary"]["external_calls"] is True
    environment_checks = {item["id"]: item for item in environment_payload["checks"]}
    assert environment_checks["ai_engine:deepseek"]["status"] == "passed"
    assert "deepseek_api_key_configured" in environment_checks["ai_engine:deepseek"]["checks"]
    assert "langchain_model_provider_config_inspected" in environment_checks["ai_engine:deepseek"]["checks"]
    assert environment_checks["providers:core"]["status"] == "warning"
    assert "external_provider_smoke_requested" in environment_checks["providers:core"]["checks"]
    assert "provider:ticket:plane:passed" in environment_checks["providers:core"]["checks"]
    assert "provider:memory:graphiti:passed" in environment_checks["providers:core"]["checks"]
    assert environment_checks["providers:core"]["external_calls"] is True
    assert any(warning.startswith("optional_provider_setup_blocked:runtime:") for warning in environment_checks["providers:core"]["warnings"])
    assert environment_checks["fallback:local"]["status"] == "passed"
    assert environment_checks["runtime:agent_loop"]["status"] == "passed"
