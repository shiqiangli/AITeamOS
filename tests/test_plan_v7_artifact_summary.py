from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "plan_v7_artifact_summary.py"
    spec = importlib.util.spec_from_file_location("plan_v7_artifact_summary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(
    root: Path,
    run_id: str,
    *,
    status: str,
    command_statuses: list[str],
    finished_at: str = "",
) -> None:
    path = root / run_id / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "aiteamos.plan_v7.ci_artifacts.v1",
                "run_id": run_id,
                "status": status,
                "started_at": f"2026-06-19T00:00:0{len(command_statuses)}+00:00",
                "finished_at": finished_at or f"2026-06-19T00:00:0{len(run_id)}+00:00",
                "artifact_root": str(path.parent),
                "options": {"full": False},
                "commands": [
                    {
                        "name": f"cmd-{index}",
                        "status": command_status,
                        "return_code": 0 if command_status == "passed" else 2,
                        "result_path": str(path.parent / f"cmd-{index}.json"),
                        "stderr_tail": "boom" if command_status != "passed" else "",
                    }
                    for index, command_status in enumerate(command_statuses, start=1)
                ],
            }
        ),
        encoding="utf-8",
    )


def _live_handoff_summary(target_employee_id: str = "alex") -> dict:
    return {
        "natural_handoff": True,
        "natural_handoff_required": True,
        "expected_handoff_target_employee_id": target_employee_id,
        "handoff_status": "durable_handoff_recorded",
        "handoff_target_employee_id": target_employee_id,
        "handoff_lane": "rd",
        "handoff_ref_count": 1,
        "handoff_refs": [
            {
                "kind": "ticket_handoff",
                "ticket_id": "rd-live-0001",
                "to_employee_id": target_employee_id,
            }
        ],
    }


def _write_agent_server_case(
    root: Path,
    name: str,
    *,
    action: str,
    runtime_status: str,
    current_node: str,
    approval_request_count: int = 0,
    provider_blocker_reasons: list[str] | None = None,
    approval_ref: str = "",
    ticket_id: str = "",
    resume: dict | None = None,
    review: dict | None = None,
    handoff: dict | None = None,
) -> None:
    path = root / "agent-server-matrix" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    provider_reasons = provider_blocker_reasons or []
    path.write_text(
        json.dumps(
            {
                "schema": "aiteamos.langgraph_agent_server_ci_smoke.v1",
                "status": "passed",
                "assistant_id": "aiteamos_workbench",
                "workspace_dir": str(path.parent / f"{name}-workspace"),
                "smoke": {
                    "schema": "aiteamos.langgraph_agent_server_smoke.v1",
                    "status": "passed",
                    "agent_thread_id": f"agent-thread-{name}",
                    "business_thread_id": f"business-thread-{name}",
                    "checks": [{"name": "runtime_status.status", "passed": True}],
                    "summary": {
                        "action": action,
                        "runtime_run_id": f"run-{name}",
                        "employee_id": "clara",
                        "active_ticket": {"id": ticket_id} if ticket_id else None,
                        "approval_ref": approval_ref,
                        "approval_request_count": approval_request_count,
                        "provider_blocker_count": len(provider_reasons),
                        "provider_blocker_reasons": provider_reasons,
                        "asset_candidate_count": 1 if action == "answer_only" else 0,
                        "linked_asset_count": 0,
                        **({"handoff_decision": handoff.get("decision", {})} if handoff else {}),
                        **({"handoff_summary": handoff.get("summary", {})} if handoff else {}),
                        **({"ticket_handoff_ref_count": handoff.get("ticket_handoff_ref_count", 0)} if handoff else {}),
                        **({"ticket_handoff_refs": handoff.get("ticket_handoff_refs", [])} if handoff else {}),
                        "runtime_status": {
                            "status": runtime_status,
                            "current_node": current_node,
                            "graph": "aiteamos_workbench",
                            "executor_id": "universal_employee_agent",
                            "run_id": f"run-{name}",
                        },
                        **({"resume": resume} if resume else {}),
                        **({"review": review} if review else {}),
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _write_environment_smoke(root: Path) -> None:
    (root / "environment_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.environment_smoke.cli.v1",
                "include_external": False,
                "result": {
                    "contract_version": "provider_conformance.v1",
                    "status": "passed",
                    "summary": {
                        "check_count": 4,
                        "passed_count": 4,
                        "blocked_count": 0,
                        "warning_count": 0,
                        "failed_count": 0,
                        "contract_version": "provider_conformance.v1",
                        "evaluation_scope": "environment_readiness_with_provider_smoke",
                        "external_calls": False,
                        "include_external": False,
                        "non_destructive": True,
                    },
                    "checks": [
                        {
                            "id": "ai_engine:deepseek",
                            "scope": "AI Engines",
                            "status": "passed",
                            "checks": [
                                "langchain_model_provider_config_inspected",
                                "deepseek_configuration_inspected",
                                "no_external_llm_call",
                                "deepseek_api_key_configured",
                            ],
                            "warnings": [],
                            "failures": [],
                            "blockers": [],
                            "evidence": {
                                "langchain_model_provider": {
                                    "selected_provider": "deepseek",
                                    "deepseek_model": "deepseek-v4-flash",
                                    "openai_model": "gpt-5.5",
                                    "configured": {"deepseek": True, "openai": False},
                                    "missing_env": ["OPENAI_API_KEY"],
                                    "provider_packages_required": ["langchain-deepseek", "langchain-openai"],
                                }
                            },
                            "external_calls": False,
                        },
                        {"id": "providers:core", "scope": "Provider Adapters", "status": "passed", "checks": ["provider_conformance_smoke_run"], "warnings": [], "failures": [], "blockers": [], "external_calls": False},
                        {"id": "fallback:local", "scope": "Local Fallback", "status": "passed", "checks": ["local_asset_registry_ready"], "warnings": [], "failures": [], "blockers": [], "external_calls": False},
                        {"id": "runtime:agent_loop", "scope": "LangGraph Agent Loop", "status": "passed", "checks": ["runtime:universal_employee_agent_ready"], "warnings": [], "failures": [], "blockers": [], "external_calls": False},
                    ],
                    "provider_smoke": {
                        "status": "passed",
                        "summary": {
                            "provider_count": 14,
                            "passed_count": 7,
                            "blocked_count": 0,
                            "warning_count": 0,
                            "failed_count": 0,
                            "external_calls": False,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _write_queue_worker_long_soak(
    root: Path,
    *,
    tick_delta: int = 6,
    min_ticks: int = 6,
    processed_delta: int = 2,
    last_error: str = "",
) -> None:
    (root / "ticket_loop_queue_worker_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.ticket_loop_queue_worker_smoke.v2",
                "status": "passed",
                "summary": {
                    "ticket_id": "ops-retained-queue-worker",
                    "queue_ids": ["queue-failed-1", "queue-failed-2"],
                    "processed_statuses": ["blocked", "blocked"],
                    "failed_delta": 2,
                    "after_reliability": {"status": "error", "failed_count": 2},
                    "asset_candidate_ids": ["asset-candidate-ticket-loop-failure-retrospective"],
                    "worker_processed_delta": 2,
                    "worker_policy_action_delta": 1,
                    "daemon_status": "passed",
                    "policy_actions": [{"kind": "failure_retrospective_candidate"}],
                    "daemon": {
                        "ticket_id": "ops-retained-daemon",
                        "tick_delta": tick_delta,
                        "processed_delta": processed_delta,
                        "min_ticks": min_ticks,
                        "interval_seconds": 0.1,
                        "timeout_seconds": 10.0,
                        "queue_statuses": ["completed", "completed"],
                        "run_statuses": ["completed", "completed"],
                        "stopped_status": {"last_tick_status": "idle", "last_error": last_error},
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _write_agent_server_matrix(root: Path) -> None:
    _write_environment_smoke(root)
    _write_agent_server_case(
        root,
        "readonly_list",
        action="list_employees",
        runtime_status="completed",
        current_node="final_response",
    )
    _write_agent_server_case(
        root,
        "answer_only",
        action="answer_only",
        runtime_status="completed",
        current_node="final_response",
    )
    _write_agent_server_case(
        root,
        "provider_blocker",
        action="answer_only",
        runtime_status="completed",
        current_node="final_response",
        provider_blocker_reasons=["plane_setup_blocker"],
    )
    _write_agent_server_case(
        root,
        "handoff_policy",
        action="answer_only",
        runtime_status="completed",
        current_node="final_response",
        ticket_id="ticket-handoff-policy",
        handoff={
            "decision": {
                "should_handoff": True,
                "target_employee_id": "victor",
                "target_role": "AI RD / Implementer",
                "lane": "rd",
                "reason": "Selected under handoff_policy. memory_scope matched. risk_boundary=critical.",
                "confidence": 0.95,
                "policy": {
                    "policy_aware": True,
                    "required_memory_scopes": ["employee:victor"],
                    "matched_memory_scopes": ["employee:victor"],
                    "available_memory_scopes": ["aiteamos", "employee:victor"],
                    "memory_scope_match": "matched",
                    "risk_level": "critical",
                    "max_risk_level": "critical",
                    "risk_allowed": True,
                },
            },
            "summary": {
                "status": "durable_handoff_recorded",
                "to_employee_id": "victor",
                "lane": "rd",
                "handoff_ref_count": 1,
            },
            "ticket_handoff_ref_count": 1,
            "ticket_handoff_refs": [{"kind": "ticket_handoff", "ticket_id": "ticket-handoff-policy", "to_employee_id": "victor"}],
        },
    )
    _write_agent_server_case(
        root,
        "approval_resume",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-resume-1",
        ticket_id="ticket-approval-resume",
        resume={
            "active_ticket": {"id": "ticket-approval-resume"},
            "approval_ref": "approval-resume-1",
            "asset_candidate_count": 1,
            "linked_asset_count": 1,
            "ticket_report_id": "report-resume-1",
            "runtime_status": {"status": "completed", "current_node": "final_response"},
        },
    )
    _write_agent_server_case(
        root,
        "approval_evidence_review",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-evidence-1",
        ticket_id="ticket-evidence-review",
        review={
            "approval_ref": "approval-evidence-1",
            "approval_status": "evidence_requested",
            "ticket_id": "ticket-evidence-review",
            "ticket_status": "waiting_evidence",
            "ticket_report_types": ["approval_evidence_requested"],
            "ticket_report_ids": ["report-evidence-1"],
            "timeline_statuses": ["evidence_requested"],
        },
    )
    _write_agent_server_case(
        root,
        "approval_rejected_review",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-rejected-1",
        ticket_id="ticket-rejected-review",
        review={
            "approval_ref": "approval-rejected-1",
            "approval_status": "rejected",
            "ticket_id": "ticket-rejected-review",
            "ticket_status": "blocked",
            "ticket_report_types": ["approval_rejected"],
            "ticket_report_ids": ["report-rejected-1"],
            "timeline_statuses": ["rejected"],
        },
    )
    _write_agent_server_case(
        root,
        "approval_changes_review",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-changes-1",
        ticket_id="ticket-changes-review",
        review={
            "approval_ref": "approval-changes-1",
            "approval_status": "changes_requested",
            "ticket_id": "ticket-changes-review",
            "ticket_status": "waiting_changes",
            "ticket_report_types": ["approval_changes_requested"],
            "ticket_report_ids": ["report-changes-1"],
            "timeline_statuses": ["changes_requested"],
        },
    )


def test_plan_v7_artifact_summary_reports_latest_and_failures(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "older", status="passed", command_statuses=["passed", "passed"])
    _write_manifest(tmp_path, "newer-run", status="failed", command_statuses=["passed", "failed"])

    summary = module.summarize_artifacts(tmp_path, limit=10)

    assert summary["total_manifest_count"] == 2
    assert summary["inspected_run_count"] == 2
    assert summary["passed_run_count"] == 1
    assert summary["failed_run_count"] == 1
    assert summary["latest_run_id"] == "newer-run"
    assert summary["latest_status"] == "failed"
    assert summary["failed_commands"][0]["name"] == "cmd-2"
    assert summary["failed_commands"][0]["stderr_tail"] == "boom"


def test_plan_v7_artifact_summary_handles_missing_dir(tmp_path) -> None:
    module = _module()

    summary = module.summarize_artifacts(tmp_path / "missing", limit=10)

    assert summary["total_manifest_count"] == 0
    assert summary["latest_status"] == "missing"


def test_plan_v7_artifact_summary_keeps_running_separate_from_failed(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "running", status="running", command_statuses=["passed"])

    summary = module.summarize_artifacts(tmp_path, limit=10)

    assert summary["running_run_count"] == 1
    assert summary["failed_run_count"] == 0
    assert summary["non_passed_run_count"] == 1


def test_plan_v7_artifact_summary_exit_code_respects_explicit_gates(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "failed-run", status="failed", command_statuses=["failed"])

    summary = module.summarize_artifacts(tmp_path, limit=10)

    assert module._summary_exit_code(summary) == 0
    assert module._summary_exit_code(summary, fail_on_failed=True) == 2
    assert module._summary_exit_code(summary, fail_on_latest_evidence_gaps=True) == 3
    assert module._summary_exit_code(summary, fail_on_retained_evidence_gaps=True) == 4


def test_plan_v7_artifact_summary_extracts_loop_evidence(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "evidence-run", status="passed", command_statuses=["passed"])
    run_root = tmp_path / "evidence-run"
    (run_root / "context_retrieval_eval_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.context_retrieval_eval_smoke.v1",
                "status": "passed",
                "summary": {
                    "ticket_id": "rd-0001",
                    "graphiti_result_count": 1,
                    "graphiti_excluded_result_count": 2,
                    "active_asset_ids": ["asset-graphiti-context-solution"],
                    "stale_hint_asset_ids": [
                        "asset-graphiti-stale-solution",
                        "asset-graphiti-conflicted-solution",
                    ],
                    "wrong_ticket_filtered": True,
                    "work_history": {
                        "employee_id": "alex",
                        "report_id": "report-work-history-1",
                        "report_count": 1,
                        "current_ticket_count": 1,
                        "eval_recall": 1.0,
                        "eval_precision_like": 0.5,
                        "matched_refs": [
                            {"kind": "employee_work_history", "ref": "alex"},
                            {"kind": "work_ticket", "ref": "rd-0001"},
                            {"kind": "work_report", "ref": "report-work-history-1"},
                        ],
                        "missing_refs": [],
                    },
                    "provider_blocker_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "ticket_loop_queue_worker_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.ticket_loop_queue_worker_smoke.v2",
                "status": "passed",
                "summary": {
                    "ticket_id": "ops-0001",
                    "queue_ids": ["queue-failed-1", "queue-failed-2"],
                    "processed_statuses": ["blocked", "blocked"],
                    "failed_delta": 2,
                    "after_reliability": {"status": "error", "failed_count": 2},
                    "asset_candidate_ids": ["asset-candidate-ticket-loop-failure-retrospective"],
                    "worker_processed_delta": 2,
                    "worker_policy_action_delta": 1,
                    "daemon_status": "passed",
                    "policy_actions": [{"kind": "failure_retrospective_candidate"}],
                    "daemon": {
                        "ticket_id": "ops-daemon-0001",
                        "tick_delta": 6,
                        "processed_delta": 2,
                        "min_ticks": 6,
                        "interval_seconds": 0.1,
                        "timeout_seconds": 10.0,
                        "queue_statuses": ["completed", "completed"],
                        "run_statuses": ["completed", "completed"],
                        "stopped_status": {"last_tick_status": "idle", "last_error": ""},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "asset_provenance_eval_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.asset_provenance_eval_smoke.v1",
                "status": "passed",
                "summary": {
                    "source_asset_id": "asset-new-guidance",
                    "target_asset_id": "asset-old-guidance",
                    "relationship_id": "asset-relationship-supersedes-new-old",
                    "relationship_projection_status": "ingested",
                    "relationship_ingested_count": 1,
                    "relationship_repeated_status": "skipped",
                    "relationship_skipped_count": 1,
                    "asset_record_graphiti_relationship_count": 1,
                    "relationship_search_result_count": 1,
                    "stale_memory_id": "mem-stale",
                    "stale_review_status": "stale",
                    "stale_before_result_count": 2,
                    "stale_after_active_count": 0,
                    "stale_after_excluded_count": 1,
                    "stale_active_filtered": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "runtime_replay_eval_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.runtime_replay_eval_smoke.v1",
                "status": "passed",
                "summary": {
                    "ticket_id": "rd-runtime-0001",
                    "session_key": "alex::thread-runtime::rd-runtime-0001",
                    "request_id": "runtime-replay-smoke",
                    "required_chain_complete": True,
                    "gaps": [],
                    "coverage": {
                        "ticket": True,
                        "employee": True,
                        "runtime": True,
                        "evidence": True,
                        "trace": True,
                        "state": True,
                        "checkpoint": True,
                        "approval": True,
                        "asset_or_memory": True,
                        "handoff": True,
                        "handoff_policy": True,
                    },
                    "counts": {
                        "timeline_event_count": 6,
                        "artifact_count": 2,
                        "evidence_count": 1,
                        "trace_event_count": 1,
                        "state_transition_count": 2,
                        "handoff_ref_count": 4,
                    },
                    "handoff": True,
                    "handoff_policy": True,
                    "handoff_status": "employee_handoff_recorded",
                    "handoff_target_employee_id": "victor",
                    "handoff_lane": "rd",
                    "handoff_required_memory_scopes": ["employee:victor"],
                    "handoff_matched_memory_scopes": ["employee:victor"],
                    "handoff_memory_scope_match": "matched",
                    "handoff_risk_level": "critical",
                    "handoff_max_risk_level": "critical",
                    "handoff_risk_allowed": True,
                    "handoff_ref_count": 4,
                    "handoff_refs": [
                        {"kind": "ticket", "ref": "rd-runtime-0001"},
                        {"kind": "employee", "ref": "alex"},
                        {"kind": "employee", "ref": "victor"},
                        {"kind": "request", "ref": "runtime-replay-smoke"},
                    ],
                    "ticket_refs": ["rd-runtime-0001"],
                    "employee_refs": ["alex"],
                    "asset_refs": ["asset-runtime-replay-smoke"],
                    "memory_refs": ["mem-runtime-replay-smoke"],
                    "evidence_refs": ["pytest::runtime-replay-smoke::passed"],
                    "checkpoint_refs": ["claude_code:runtime-replay-smoke"],
                    "trace_refs": [".aiteamos/traces/runtime-replay-smoke.jsonl"],
                    "trace_redacted": True,
                    "artifact_secret_redacted": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "environment_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.environment_smoke.cli.v1",
                "include_external": False,
                "result": {
                    "contract_version": "provider_conformance.v1",
                    "status": "passed",
                    "summary": {
                        "check_count": 4,
                        "passed_count": 4,
                        "blocked_count": 0,
                        "warning_count": 0,
                        "failed_count": 0,
                        "contract_version": "provider_conformance.v1",
                        "evaluation_scope": "environment_readiness_with_provider_smoke",
                        "external_calls": False,
                        "include_external": False,
                        "non_destructive": True,
                    },
                    "checks": [
                        {
                            "id": "ai_engine:deepseek",
                            "scope": "AI Engines",
                            "status": "passed",
                            "checks": [
                                "langchain_model_provider_config_inspected",
                                "deepseek_configuration_inspected",
                                "no_external_llm_call",
                                "deepseek_api_key_configured",
                            ],
                            "warnings": [],
                            "failures": [],
                            "blockers": [],
                            "evidence": {
                                "langchain_model_provider": {
                                    "selected_provider": "deepseek",
                                    "deepseek_model": "deepseek-v4-flash",
                                    "openai_model": "gpt-5.5",
                                    "configured": {"deepseek": True, "openai": False},
                                    "missing_env": ["OPENAI_API_KEY"],
                                    "provider_packages_required": ["langchain-deepseek", "langchain-openai"],
                                }
                            },
                            "external_calls": False,
                        },
                        {"id": "providers:core", "scope": "Provider Adapters", "status": "passed", "checks": ["provider_conformance_smoke_run"], "warnings": [], "failures": [], "blockers": [], "external_calls": False},
                        {"id": "fallback:local", "scope": "Local Fallback", "status": "passed", "checks": ["local_asset_registry_ready"], "warnings": [], "failures": [], "blockers": [], "external_calls": False},
                        {"id": "runtime:agent_loop", "scope": "LangGraph Agent Loop", "status": "passed", "checks": ["runtime:universal_employee_agent_ready"], "warnings": [], "failures": [], "blockers": [], "external_calls": False},
                    ],
                    "provider_smoke": {
                        "status": "passed",
                        "summary": {
                            "provider_count": 14,
                            "passed_count": 7,
                            "blocked_count": 0,
                            "warning_count": 0,
                            "failed_count": 0,
                            "external_calls": False,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "runtime_registry_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.runtime_registry_smoke.v1",
                "status": "passed",
                "result": {
                    "summary": {
                        "executor_count": 4,
                        "ready_count": 3,
                        "blocked_count": 1,
                        "runtime_boundary": "RuntimeExecutor",
                    },
                    "executors": [
                        {"executor_id": "langgraph", "status": "ready"},
                        {"executor_id": "universal_employee_agent", "status": "ready"},
                        {"executor_id": "codex_cli", "status": "ready"},
                        {"executor_id": "cursor", "status": "setup_blocked"},
                    ],
                    "blockers": [
                        {"executor_id": "cursor", "status": "setup_blocked", "setup_required": ["CURSOR_API_KEY"]},
                    ],
                    "live_provider_readiness": {
                        "status": "blocked",
                        "selected_executor_id": "langgraph",
                        "reasons": ["live_provider_dogfood_not_confirmed"],
                        "setup_required": ["--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
                        "summary": {
                            "blocker_count": 1,
                            "repo_write_ready_count": 1,
                            "repo_write_candidate_count": 2,
                        },
                    },
                },
                "summary": {
                    "executor_count": 4,
                    "ready_count": 3,
                    "blocked_count": 1,
                    "runtime_boundary": "RuntimeExecutor",
                    "executor_ids": ["langgraph", "universal_employee_agent", "codex_cli", "cursor"],
                    "blocker_executor_ids": ["cursor"],
                    "live_provider_status": "blocked",
                    "live_provider_selected_executor_id": "langgraph",
                    "live_provider_blocker_count": 1,
                    "live_provider_blocker_reasons": ["live_provider_dogfood_not_confirmed"],
                    "live_provider_setup_required": ["--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
                    "live_provider_mutation_gate_open": False,
                    "live_provider_mutation_gate_confirm_env_var": "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
                    "live_provider_ticket_backend_status": "ready",
                    "live_provider_memory_backend_status": "ready",
                    "live_provider_provider_smoke_status": "not_run",
                    "repo_write_ready_count": 1,
                    "repo_write_candidate_count": 2,
                    "repo_write_candidate_executor_ids": ["codex_cli", "cursor"],
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "live_provider_readiness_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_readiness_smoke.v1",
                "status": "passed",
                "result": {
                    "status": "blocked",
                    "selected_executor_id": "langgraph",
                    "repo_write_executor_candidates": [
                        {
                            "executor_id": "codex_cli",
                            "status": "ready",
                            "blocker_reasons": [],
                            "setup_required": [],
                        },
                        {
                            "executor_id": "cursor",
                            "status": "setup_blocked",
                            "blocker_reasons": ["cursor_api_key_missing"],
                            "setup_required": ["CURSOR_API_KEY"],
                        },
                    ],
                    "blockers": [
                        {
                            "reason": "ticket_provider_not_ready",
                            "scope": "ticket_backend",
                            "status": "setup_blocked",
                            "setup_required": ["PLANE_API_KEY"],
                        },
                        {
                            "reason": "memory_provider_not_ready",
                            "scope": "memory_backend",
                            "status": "disabled",
                            "setup_required": ["Graphiti enabled", "OPENAI_API_KEY"],
                        },
                        {
                            "reason": "live_provider_dogfood_not_confirmed",
                            "scope": "mutation_gate",
                            "status": "confirmation_required",
                            "setup_required": [],
                        },
                    ],
                },
                "summary": {
                    "readiness_status": "blocked",
                    "ready_for_live_dogfood": False,
                    "selected_executor_id": "langgraph",
                    "selected_executor_status": "passed",
                    "selected_executor_blocker_reasons": [],
                    "repo_write_candidate_count": 2,
                    "repo_write_ready_count": 1,
                    "repo_write_ready_executor_ids": ["codex_cli"],
                    "ticket_backend_status": "ready",
                    "memory_backend_status": "ready",
                    "provider_smoke_status": "not_run",
                    "mutation_gate_open": False,
                    "mutation_gate_execute_flag": True,
                    "mutation_gate_confirm_env_var": "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
                    "mutation_gate_confirm_env_configured": False,
                    "mutation_gate_blocker_reason": "live_provider_dogfood_not_confirmed",
                    "blocker_count": 1,
                    "blocker_reasons": ["live_provider_dogfood_not_confirmed"],
                    "blocker_scopes": ["mutation_gate"],
                },
            }
        ),
        encoding="utf-8",
    )
    _write_agent_server_case(
        run_root,
        "readonly_list",
        action="list_employees",
        runtime_status="completed",
        current_node="final_response",
    )
    _write_agent_server_case(
        run_root,
        "answer_only",
        action="answer_only",
        runtime_status="completed",
        current_node="final_response",
    )
    _write_agent_server_case(
        run_root,
        "provider_blocker",
        action="answer_only",
        runtime_status="completed",
        current_node="final_response",
        provider_blocker_reasons=["plane_setup_blocker"],
    )
    _write_agent_server_case(
        run_root,
        "handoff_policy",
        action="answer_only",
        runtime_status="completed",
        current_node="final_response",
        ticket_id="ticket-handoff-policy",
        handoff={
            "decision": {
                "should_handoff": True,
                "target_employee_id": "victor",
                "target_role": "AI RD / Implementer",
                "lane": "rd",
                "reason": "Selected under handoff_policy. memory_scope matched. risk_boundary=critical.",
                "confidence": 0.95,
                "policy": {
                    "policy_aware": True,
                    "required_memory_scopes": ["employee:victor"],
                    "matched_memory_scopes": ["employee:victor"],
                    "available_memory_scopes": ["aiteamos", "employee:victor"],
                    "memory_scope_match": "matched",
                    "risk_level": "critical",
                    "max_risk_level": "critical",
                    "risk_allowed": True,
                },
            },
            "summary": {
                "status": "durable_handoff_recorded",
                "to_employee_id": "victor",
                "lane": "rd",
                "handoff_ref_count": 1,
            },
            "ticket_handoff_ref_count": 1,
            "ticket_handoff_refs": [{"kind": "ticket_handoff", "ticket_id": "ticket-handoff-policy", "to_employee_id": "victor"}],
        },
    )
    _write_agent_server_case(
        run_root,
        "approval_resume",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-resume-1",
        ticket_id="ticket-approval-resume",
        resume={
            "active_ticket": {"id": "ticket-approval-resume"},
            "approval_ref": "approval-resume-1",
            "asset_candidate_count": 1,
            "linked_asset_count": 1,
            "ticket_report_id": "report-resume-1",
            "runtime_status": {"status": "completed", "current_node": "final_response"},
        },
    )
    _write_agent_server_case(
        run_root,
        "approval_evidence_review",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-evidence-1",
        ticket_id="ticket-evidence-review",
        review={
            "approval_ref": "approval-evidence-1",
            "approval_status": "evidence_requested",
            "ticket_id": "ticket-evidence-review",
            "ticket_status": "waiting_evidence",
            "ticket_report_types": ["approval_evidence_requested"],
            "ticket_report_ids": ["report-evidence-1"],
            "timeline_statuses": ["evidence_requested"],
        },
    )
    _write_agent_server_case(
        run_root,
        "approval_rejected_review",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-rejected-1",
        ticket_id="ticket-rejected-review",
        review={
            "approval_ref": "approval-rejected-1",
            "approval_status": "rejected",
            "ticket_id": "ticket-rejected-review",
            "ticket_status": "blocked",
            "ticket_report_types": ["approval_rejected"],
            "ticket_report_ids": ["report-rejected-1"],
            "timeline_statuses": ["rejected"],
        },
    )
    _write_agent_server_case(
        run_root,
        "approval_changes_review",
        action="implement_ticket",
        runtime_status="needs_approval",
        current_node="approval_interrupt",
        approval_request_count=1,
        approval_ref="approval-changes-1",
        ticket_id="ticket-changes-review",
        review={
            "approval_ref": "approval-changes-1",
            "approval_status": "changes_requested",
            "ticket_id": "ticket-changes-review",
            "ticket_status": "waiting_changes",
            "ticket_report_types": ["approval_changes_requested"],
            "ticket_report_ids": ["report-changes-1"],
            "timeline_statuses": ["changes_requested"],
        },
    )

    summary = module.summarize_artifacts(tmp_path, limit=10)

    assert summary["schema"] == "aiteamos.plan_v7.artifact_summary.v2"
    context = summary["latest_evidence"]["context_retrieval"]
    assert context["status"] == "passed"
    assert context["graphiti_result_count"] == 1
    assert context["graphiti_excluded_result_count"] == 2
    assert context["wrong_ticket_filtered"] is True
    assert context["work_history_employee_id"] == "alex"
    assert context["work_history_report_id"] == "report-work-history-1"
    assert context["work_history_report_count"] == 1
    assert context["work_history_current_ticket_count"] == 1
    assert context["work_history_eval_recall"] == 1.0
    assert context["work_history_eval_precision_like"] == 0.5
    assert context["work_history_missing_ref_count"] == 0
    daemon = summary["latest_evidence"]["queue_worker_daemon"]
    assert daemon["status"] == "passed"
    assert daemon["daemon_ticket_id"] == "ops-daemon-0001"
    assert daemon["tick_delta"] == 6
    assert daemon["processed_delta"] == 2
    assert daemon["min_ticks"] == 6
    assert daemon["long_soak"] is True
    assert daemon["soak_passed"] is True
    assert daemon["queue_statuses"] == ["completed", "completed"]
    assert daemon["run_statuses"] == ["completed", "completed"]
    assert daemon["policy_action_count"] == 1
    assert daemon["processed_statuses"] == ["blocked", "blocked"]
    assert daemon["failed_delta"] == 2
    assert daemon["after_reliability_status"] == "error"
    assert daemon["after_reliability_failed_count"] == 2
    assert daemon["asset_candidate_ids"] == ["asset-candidate-ticket-loop-failure-retrospective"]
    assert daemon["policy_action_kinds"] == ["failure_retrospective_candidate"]
    assert daemon["worker_processed_delta"] == 2
    assert daemon["worker_policy_action_delta"] == 1
    assert daemon["repeated_failure_policy_evidence"] is True
    asset_provenance = summary["latest_evidence"]["asset_provenance"]
    assert asset_provenance["relationship_projection_status"] == "ingested"
    assert asset_provenance["relationship_ingested_count"] == 1
    assert asset_provenance["relationship_repeated_status"] == "skipped"
    assert asset_provenance["stale_review_status"] == "stale"
    assert asset_provenance["stale_active_filtered"] is True
    runtime_replay = summary["latest_evidence"]["runtime_replay"]
    assert runtime_replay["status"] == "passed"
    assert runtime_replay["ticket_id"] == "rd-runtime-0001"
    assert runtime_replay["session_key"] == "alex::thread-runtime::rd-runtime-0001"
    assert runtime_replay["required_chain_complete"] is True
    assert runtime_replay["gap_count"] == 0
    assert runtime_replay["ticket"] is True
    assert runtime_replay["employee"] is True
    assert runtime_replay["runtime"] is True
    assert runtime_replay["evidence"] is True
    assert runtime_replay["trace"] is True
    assert runtime_replay["state"] is True
    assert runtime_replay["checkpoint"] is True
    assert runtime_replay["asset_or_memory"] is True
    assert runtime_replay["handoff"] is True
    assert runtime_replay["handoff_policy"] is True
    assert runtime_replay["handoff_status"] == "employee_handoff_recorded"
    assert runtime_replay["handoff_target_employee_id"] == "victor"
    assert runtime_replay["handoff_matched_memory_scopes"] == ["employee:victor"]
    assert runtime_replay["handoff_memory_scope_match"] == "matched"
    assert runtime_replay["handoff_risk_level"] == "critical"
    assert runtime_replay["handoff_risk_allowed"] is True
    assert runtime_replay["handoff_ref_count"] == 4
    assert runtime_replay["timeline_event_count"] == 6
    assert runtime_replay["trace_event_count"] == 1
    assert runtime_replay["state_transition_count"] == 2
    assert runtime_replay["ticket_refs"] == ["rd-runtime-0001"]
    assert runtime_replay["asset_refs"] == ["asset-runtime-replay-smoke"]
    assert runtime_replay["memory_refs"] == ["mem-runtime-replay-smoke"]
    assert runtime_replay["trace_redacted"] is True
    assert runtime_replay["artifact_secret_redacted"] is True
    environment = summary["latest_evidence"]["environment_smoke"]
    assert environment["status"] == "passed"
    assert environment["contract_version"] == "provider_conformance.v1"
    assert environment["check_count"] == 4
    assert environment["passed_count"] == 4
    assert environment["blocked_count"] == 0
    assert environment["provider_smoke_status"] == "passed"
    assert environment["provider_count"] == 14
    assert environment["provider_failed_count"] == 0
    assert environment["check_statuses"]["ai_engine:deepseek"] == "passed"
    assert environment["check_statuses"]["runtime:agent_loop"] == "passed"
    assert environment["langchain_provider_boundary_ready"] is True
    assert environment["langchain_model_provider"]["selected_provider"] == "deepseek"
    assert environment["langchain_model_provider"]["config_inspected"] is True
    assert environment["langchain_model_provider"]["no_external_llm_call"] is True
    assert environment["langchain_model_provider"]["provider_packages_required"] == ["langchain-deepseek", "langchain-openai"]
    assert environment["blocker_ids"] == []
    runtime_registry = summary["latest_evidence"]["runtime_registry"]
    assert runtime_registry["status"] == "passed"
    assert runtime_registry["runtime_boundary"] == "RuntimeExecutor"
    assert runtime_registry["executor_count"] == 4
    assert runtime_registry["ready_count"] == 3
    assert runtime_registry["blocked_count"] == 1
    assert runtime_registry["executor_ids"] == ["langgraph", "universal_employee_agent", "codex_cli", "cursor"]
    assert runtime_registry["blocker_executor_ids"] == ["cursor"]
    assert runtime_registry["live_provider_status"] == "blocked"
    assert runtime_registry["live_provider_selected_executor_id"] == "langgraph"
    assert runtime_registry["live_provider_blocker_count"] == 1
    assert runtime_registry["live_provider_blocker_reasons"] == ["live_provider_dogfood_not_confirmed"]
    assert runtime_registry["live_provider_setup_required"] == ["--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"]
    assert runtime_registry["live_provider_mutation_gate_open"] is False
    assert runtime_registry["live_provider_ticket_backend_status"] == "ready"
    assert runtime_registry["live_provider_memory_backend_status"] == "ready"
    assert runtime_registry["repo_write_ready_count"] == 1
    assert runtime_registry["repo_write_candidate_executor_ids"] == ["codex_cli", "cursor"]
    live_readiness = summary["latest_evidence"]["live_provider_readiness"]
    assert live_readiness["status"] == "passed"
    assert live_readiness["readiness_status"] == "blocked"
    assert live_readiness["ready_for_live_dogfood"] is False
    assert live_readiness["selected_executor_id"] == "langgraph"
    assert live_readiness["repo_write_ready_count"] == 1
    assert live_readiness["ticket_backend_status"] == "ready"
    assert live_readiness["memory_backend_status"] == "ready"
    assert live_readiness["mutation_gate_open"] is False
    assert live_readiness["mutation_gate_blocker_reason"] == "live_provider_dogfood_not_confirmed"
    assert live_readiness["blocker_reasons"] == ["live_provider_dogfood_not_confirmed"]
    assert live_readiness["blocker_scopes"] == ["mutation_gate"]
    assert live_readiness["blockers"] == [
        {
            "reason": "ticket_provider_not_ready",
            "scope": "ticket_backend",
            "status": "setup_blocked",
            "setup_required": ["PLANE_API_KEY"],
        },
        {
            "reason": "memory_provider_not_ready",
            "scope": "memory_backend",
            "status": "disabled",
            "setup_required": ["Graphiti enabled", "OPENAI_API_KEY"],
        },
        {
            "reason": "live_provider_dogfood_not_confirmed",
            "scope": "mutation_gate",
            "status": "confirmation_required",
            "setup_required": [],
        },
    ]
    assert live_readiness["setup_required"] == ["PLANE_API_KEY", "Graphiti enabled", "OPENAI_API_KEY"]
    assert live_readiness["repo_write_candidates"] == [
        {"executor_id": "codex_cli", "status": "ready", "blocker_reasons": [], "setup_required": []},
        {
            "executor_id": "cursor",
            "status": "setup_blocked",
            "blocker_reasons": ["cursor_api_key_missing"],
            "setup_required": ["CURSOR_API_KEY"],
        },
    ]
    agent_server = summary["latest_evidence"]["agent_server"]
    assert agent_server["status"] == "passed"
    assert agent_server["case_count"] == 8
    assert agent_server["passed_case_count"] == 8
    assert agent_server["coverage_complete"] is True
    assert agent_server["coverage"]["readonly_complete"] is True
    assert agent_server["coverage"]["answer_only_complete"] is True
    assert agent_server["coverage"]["provider_blocker_visible"] is True
    assert agent_server["coverage"]["handoff_policy_memory_risk"] is True
    assert agent_server["coverage"]["approval_interrupt"] is True
    assert agent_server["coverage"]["approval_resume_complete"] is True
    assert agent_server["coverage"]["review_evidence_requested"] is True
    assert agent_server["coverage"]["review_rejected"] is True
    assert agent_server["coverage"]["review_changes_requested"] is True
    assert agent_server["coverage"]["langchain_provider_boundary_visible"] is True
    assert agent_server["langchain_model_provider"]["selected_provider"] == "deepseek"
    assert agent_server["cases"]["provider_blocker"]["provider_blocker_reasons"] == ["plane_setup_blocker"]
    assert agent_server["cases"]["handoff_policy"]["handoff_target_employee_id"] == "victor"
    assert agent_server["cases"]["handoff_policy"]["handoff_status"] == "durable_handoff_recorded"
    assert agent_server["cases"]["handoff_policy"]["handoff_matched_memory_scopes"] == ["employee:victor"]
    assert agent_server["cases"]["handoff_policy"]["handoff_risk_level"] == "critical"
    assert agent_server["cases"]["handoff_policy"]["handoff_risk_allowed"] is True
    assert agent_server["cases"]["handoff_policy"]["ticket_handoff_ref_count"] == 1
    assert agent_server["cases"]["approval_resume"]["resume_ticket_report_id"] == "report-resume-1"
    assert agent_server["cases"]["approval_rejected_review"]["review_ticket_status"] == "blocked"
    assert summary["latest_evidence_gaps"] == ["live_provider_dogfood_missing"]


def test_plan_v7_artifact_summary_reports_live_dogfood_freshness(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "dogfood-run",
        status="passed",
        command_statuses=["passed"],
        finished_at=(now - timedelta(hours=2)).isoformat(),
    )
    run_root = tmp_path / "dogfood-run"
    _write_agent_server_matrix(run_root)
    _write_queue_worker_long_soak(run_root)
    (run_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "completed",
                    "profile": "core_loop",
                    "executor_preflight": {"executor_id": "langgraph"},
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "rd-live-0001",
                        "runtime_dogfood_status": "completed",
                        "workbench_runtime_status": {"status": "completed", "run_id": "run-live-0001"},
                        "langgraph_thread_id": "thread-live-0001",
                        "memory_candidate_ids": ["mem-live-0001"],
                        "asset_record_ids": ["asset-live-0001"],
                        "graphiti_projection_statuses": ["ingested"],
                        "graphiti_recall_count": 1,
                        "recall_result_count": 1,
                        **_live_handoff_summary(),
                        "blocker_count": 0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "plane_ticket_action_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.plane_ticket_action_smoke.v1",
                "result": {
                    "status": "passed",
                    "provider": "plane",
                    "external_calls": True,
                    "mutating": True,
                    "summary": {
                        "ticket_backend_status": "ready",
                        "ticket_id": "rd-live-0001",
                        "ticket_source": "existing",
                        "provider_record_id": "plane-live-0001",
                        "handoff_recorded": True,
                        "handoff_report_recorded": True,
                        "to_employee_id": "alex",
                        "mutation_gate_open": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now, live_dogfood_max_age_hours=24)

    dogfood = summary["latest_evidence"]["live_provider_dogfood"]
    plane_action = summary["latest_evidence"]["plane_ticket_action_smoke"]
    assert plane_action["status"] == "passed"
    assert plane_action["ticket_id"] == "rd-live-0001"
    assert plane_action["provider_record_id"] == "plane-live-0001"
    assert plane_action["handoff_recorded"] is True
    assert plane_action["handoff_report_recorded"] is True
    assert plane_action["external_calls"] is True
    assert plane_action["mutating"] is True
    assert dogfood["status"] == "completed"
    assert dogfood["fresh"] is True
    assert dogfood["freshness_status"] == "fresh"
    assert dogfood["age_seconds"] == 7200
    assert dogfood["max_age_seconds"] == 86400
    assert dogfood["profile"] == "core_loop"
    assert dogfood["ticket_id"] == "rd-live-0001"
    assert dogfood["executor_id"] == "langgraph"
    assert dogfood["runtime_dogfood_status"] == "completed"
    assert dogfood["workbench_runtime_status"] == "completed"
    assert dogfood["workbench_runtime_run_id"] == "run-live-0001"
    assert dogfood["langgraph_thread_id"] == "thread-live-0001"
    assert dogfood["memory_candidate_ids"] == ["mem-live-0001"]
    assert dogfood["asset_record_ids"] == ["asset-live-0001"]
    assert dogfood["graphiti_projection_statuses"] == ["ingested"]
    assert dogfood["graphiti_recall_count"] == 1
    assert dogfood["recall_result_count"] == 1
    assert dogfood["natural_handoff"] is True
    assert dogfood["handoff_status"] == "durable_handoff_recorded"
    assert dogfood["handoff_target_employee_id"] == "alex"
    assert dogfood["handoff_ref_count"] == 1
    assert "live_provider_dogfood_missing" not in summary["latest_evidence_gaps"]
    assert summary["retained_evidence"]["agent_server"]["retained_from_run_id"] == "dogfood-run"
    assert summary["retained_evidence"]["agent_server"]["coverage_complete"] is True
    assert summary["retained_evidence"]["queue_worker_daemon"]["retained_from_run_id"] == "dogfood-run"
    assert summary["retained_evidence"]["queue_worker_daemon"]["soak_passed"] is True
    assert summary["retained_evidence"]["live_provider_dogfood"]["retained_from_run_id"] == "dogfood-run"
    assert summary["retained_evidence_gaps"] == []
    assert module._summary_exit_code(summary, fail_on_latest_evidence_gaps=True) == 3
    assert module._summary_exit_code(summary, fail_on_retained_evidence_gaps=True) == 0


def test_plan_v7_artifact_summary_reports_environment_smoke_blockers(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "env-blocked-run", status="passed", command_statuses=["passed"])
    run_root = tmp_path / "env-blocked-run"
    (run_root / "environment_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.environment_smoke.cli.v1",
                "include_external": False,
                "result": {
                    "contract_version": "provider_conformance.v1",
                    "status": "setup_blocked",
                    "summary": {
                        "check_count": 4,
                        "passed_count": 3,
                        "blocked_count": 1,
                        "warning_count": 1,
                        "failed_count": 0,
                        "contract_version": "provider_conformance.v1",
                        "evaluation_scope": "environment_readiness_with_provider_smoke",
                        "external_calls": False,
                        "include_external": False,
                        "non_destructive": True,
                    },
                    "checks": [
                        {"id": "ai_engine:deepseek", "scope": "AI Engines", "status": "passed", "checks": [], "warnings": [], "failures": [], "blockers": [], "external_calls": False},
                        {
                            "id": "providers:core",
                            "scope": "Provider Adapters",
                            "status": "setup_blocked",
                            "checks": ["provider_conformance_smoke_run"],
                            "warnings": ["external_provider_smoke_skipped"],
                            "failures": [],
                            "blockers": [
                                {"id": "ticket:plane:setup", "status": "setup_blocked"},
                                {"id": "memory:graphiti:setup", "status": "disabled"},
                            ],
                            "external_calls": False,
                        },
                    ],
                    "provider_smoke": {
                        "status": "passed",
                        "summary": {
                            "provider_count": 14,
                            "passed_count": 7,
                            "blocked_count": 2,
                            "warning_count": 1,
                            "failed_count": 0,
                            "external_calls": False,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10)

    environment = summary["latest_evidence"]["environment_smoke"]
    assert environment["status"] == "setup_blocked"
    assert environment["blocked_count"] == 1
    assert environment["provider_blocked_count"] == 2
    assert environment["check_statuses"]["providers:core"] == "setup_blocked"
    assert environment["blocker_ids"] == ["ticket:plane:setup", "memory:graphiti:setup"]
    assert "environment_smoke_setup_blocked" in summary["latest_evidence_gaps"]


def test_plan_v7_artifact_summary_flags_short_queue_worker_soak(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "short-worker-run", status="passed", command_statuses=["passed"])
    run_root = tmp_path / "short-worker-run"
    (run_root / "ticket_loop_queue_worker_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.ticket_loop_queue_worker_smoke.v2",
                "status": "passed",
                "summary": {
                    "ticket_id": "ops-short-0001",
                    "queue_ids": ["queue-failed-1", "queue-failed-2"],
                    "processed_statuses": ["blocked", "blocked"],
                    "failed_delta": 2,
                    "after_reliability": {"status": "error", "failed_count": 2},
                    "asset_candidate_ids": ["asset-candidate-ticket-loop-failure-retrospective"],
                    "worker_processed_delta": 2,
                    "worker_policy_action_delta": 1,
                    "daemon_status": "passed",
                    "policy_actions": [{"kind": "failure_retrospective_candidate"}],
                    "daemon": {
                        "ticket_id": "ops-daemon-short-0001",
                        "tick_delta": 3,
                        "processed_delta": 2,
                        "min_ticks": 3,
                        "queue_statuses": ["completed", "completed"],
                        "run_statuses": ["completed", "completed"],
                        "stopped_status": {"last_tick_status": "idle", "last_error": ""},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10)

    queue_worker = summary["latest_evidence"]["queue_worker_daemon"]
    assert queue_worker["status"] == "passed"
    assert queue_worker["long_soak"] is False
    assert queue_worker["soak_passed"] is False
    assert "queue_worker_daemon_soak_missing" in summary["latest_evidence_gaps"]


def test_plan_v7_artifact_summary_rejects_repo_write_live_dogfood_as_core_loop_evidence(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "repo-write-live-dogfood",
        status="passed",
        command_statuses=["passed"],
        finished_at=now.isoformat(),
    )
    run_root = tmp_path / "repo-write-live-dogfood"
    _write_agent_server_matrix(run_root)
    _write_queue_worker_long_soak(run_root)
    (run_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "completed",
                    "profile": "repo_write_adapter",
                    "executor_preflight": {"executor_id": "codex_cli"},
                    "summary": {
                        "dogfood_profile": "repo_write_adapter",
                        "ticket_id": "rd-repo-write-dogfood",
                        "runtime_dogfood_status": "completed",
                        "asset_record_ids": ["asset-repo-write-0001"],
                        "graphiti_projection_statuses": ["ingested"],
                        "graphiti_recall_count": 1,
                        "blocker_count": 0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now, live_dogfood_max_age_hours=24)

    dogfood = summary["latest_evidence"]["live_provider_dogfood"]
    assert dogfood["status"] == "completed"
    assert dogfood["fresh"] is True
    assert dogfood["profile"] == "repo_write_adapter"
    assert dogfood["executor_id"] == "codex_cli"
    assert "live_provider_dogfood_profile_not_core_loop" in summary["latest_evidence_gaps"]
    assert "live_provider_dogfood_executor_not_langgraph" in summary["latest_evidence_gaps"]
    assert "live_provider_dogfood_profile_not_core_loop" in summary["retained_evidence_gaps"]
    assert "live_provider_dogfood_executor_not_langgraph" in summary["retained_evidence_gaps"]
    assert module._summary_exit_code(summary, fail_on_latest_evidence_gaps=True) == 3
    assert module._summary_exit_code(summary, fail_on_retained_evidence_gaps=True) == 4


def test_plan_v7_artifact_summary_flags_direct_llm_runtime_registry_regression(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "direct-llm-registry-run", status="passed", command_statuses=["passed"])
    run_root = tmp_path / "direct-llm-registry-run"
    (run_root / "runtime_registry_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.runtime_registry_smoke.v1",
                "status": "passed",
                "result": {},
                "summary": {
                    "executor_count": 3,
                    "ready_count": 3,
                    "blocked_count": 0,
                    "runtime_boundary": "RuntimeExecutor",
                    "executor_ids": ["local_tool", "direct_llm", "langgraph"],
                    "blocker_executor_ids": [],
                    "live_provider_status": "blocked",
                    "live_provider_selected_executor_id": "direct_llm",
                    "live_provider_blocker_count": 1,
                    "live_provider_blocker_reasons": ["live_provider_dogfood_not_confirmed"],
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10)

    runtime_registry = summary["latest_evidence"]["runtime_registry"]
    assert runtime_registry["executor_ids"] == ["local_tool", "direct_llm", "langgraph"]
    assert "runtime_registry_direct_llm_present" in summary["latest_evidence_gaps"]
    assert "runtime_registry_core_loop_not_langgraph" in summary["latest_evidence_gaps"]


def test_plan_v7_artifact_summary_flags_runtime_replay_without_handoff_summary(tmp_path) -> None:
    module = _module()
    _write_manifest(tmp_path, "runtime-replay-no-handoff", status="passed", command_statuses=["passed"])
    run_root = tmp_path / "runtime-replay-no-handoff"
    (run_root / "runtime_replay_eval_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.runtime_replay_eval_smoke.v1",
                "status": "passed",
                "summary": {
                    "ticket_id": "rd-runtime-0001",
                    "session_key": "alex::thread-runtime::rd-runtime-0001",
                    "request_id": "runtime-replay-smoke",
                    "required_chain_complete": True,
                    "gaps": [],
                    "coverage": {
                        "ticket": True,
                        "employee": True,
                        "runtime": True,
                        "evidence": True,
                        "trace": True,
                        "state": True,
                        "checkpoint": True,
                        "approval": True,
                        "asset_or_memory": True,
                    },
                    "counts": {
                        "timeline_event_count": 6,
                        "artifact_count": 2,
                        "evidence_count": 1,
                        "trace_event_count": 1,
                        "state_transition_count": 2,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10)

    runtime_replay = summary["latest_evidence"]["runtime_replay"]
    assert runtime_replay["handoff"] is False
    assert "runtime_replay_handoff_summary_missing" in summary["latest_evidence_gaps"]
    assert module._summary_exit_code(summary, fail_on_latest_evidence_gaps=True) == 3


def test_plan_v7_artifact_summary_does_not_count_dry_run_as_live_dogfood(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "dry-run",
        status="passed",
        command_statuses=["passed"],
        finished_at=now.isoformat(),
    )
    run_root = tmp_path / "dry-run"
    _write_agent_server_matrix(run_root)
    _write_queue_worker_long_soak(run_root)
    (run_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "dry_run",
                    "profile": "core_loop",
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "rd-dry-run",
                        "runtime_dogfood_status": "completed",
                    },
                    "executor_preflight": {"executor_id": "langgraph"},
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now)

    dogfood = summary["latest_evidence"]["live_provider_dogfood"]
    assert dogfood["status"] == "dry_run"
    assert dogfood["fresh"] is False
    assert dogfood["freshness_status"] == "not_completed"
    assert "live_provider_dogfood_not_completed" in summary["latest_evidence_gaps"]
    assert "live_provider_dogfood_natural_handoff_missing" in summary["latest_evidence_gaps"]
    assert summary["retained_evidence_gaps"] == [
        "live_provider_dogfood_not_completed",
        "live_provider_dogfood_natural_handoff_missing",
    ]


def test_plan_v7_artifact_summary_rejects_core_loop_live_dogfood_without_natural_handoff(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "core-loop-no-natural-handoff",
        status="passed",
        command_statuses=["passed"],
        finished_at=now.isoformat(),
    )
    run_root = tmp_path / "core-loop-no-natural-handoff"
    _write_agent_server_matrix(run_root)
    _write_queue_worker_long_soak(run_root)
    (run_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "completed",
                    "profile": "core_loop",
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "rd-live-no-handoff",
                        "runtime_dogfood_status": "completed",
                        "blocker_count": 0,
                    },
                    "executor_preflight": {"executor_id": "langgraph"},
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now)

    dogfood = summary["latest_evidence"]["live_provider_dogfood"]
    assert dogfood["status"] == "completed"
    assert dogfood["natural_handoff"] is False
    assert "live_provider_dogfood_natural_handoff_missing" in summary["latest_evidence_gaps"]
    assert module._summary_exit_code(summary, fail_on_latest_evidence_gaps=True) == 3


def test_plan_v7_artifact_summary_reports_plane_ticket_action_smoke_blocker(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "plane-action-blocked",
        status="failed",
        command_statuses=["passed", "failed"],
        finished_at=now.isoformat(),
    )
    run_root = tmp_path / "plane-action-blocked"
    _write_agent_server_matrix(run_root)
    _write_queue_worker_long_soak(run_root)
    (run_root / "plane_ticket_action_smoke.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.plane_ticket_action_smoke.v1",
                "result": {
                    "status": "blocked",
                    "provider": "plane",
                    "external_calls": True,
                    "mutating": True,
                    "blockers": [
                        {
                            "reason": "plane_handoff_report_action_failed",
                            "stage": "append_handoff_report",
                        }
                    ],
                    "summary": {
                        "ticket_backend_status": "ready",
                        "ticket_id": "ops-0014",
                        "blocker_stage": "append_handoff_report",
                        "blocker_reason": "plane_handoff_report_action_failed",
                        "mutation_gate_open": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "blocked",
                    "profile": "core_loop",
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "ops-0014",
                        "runtime_dogfood_status": "blocked",
                    },
                    "executor_preflight": {"executor_id": "langgraph"},
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now)

    plane_action = summary["latest_evidence"]["plane_ticket_action_smoke"]
    assert plane_action["status"] == "blocked"
    assert plane_action["blocker_stage"] == "append_handoff_report"
    assert plane_action["blocker_reasons"] == ["plane_handoff_report_action_failed"]
    assert "plane_ticket_action_smoke_not_passed" in summary["latest_evidence_gaps"]


def test_plan_v7_artifact_summary_retains_queue_worker_long_soak_from_previous_run(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "queue-worker-long-soak",
        status="passed",
        command_statuses=["passed"],
        finished_at=(now - timedelta(hours=3)).isoformat(),
    )
    _write_queue_worker_long_soak(tmp_path / "queue-worker-long-soak")
    _write_manifest(
        tmp_path,
        "newer-matrix-dogfood",
        status="passed",
        command_statuses=["passed"],
        finished_at=now.isoformat(),
    )
    newer_root = tmp_path / "newer-matrix-dogfood"
    _write_agent_server_matrix(newer_root)
    (newer_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "completed",
                    "profile": "core_loop",
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "rd-retained-queue",
                        "runtime_dogfood_status": "completed",
                        **_live_handoff_summary(),
                    },
                    "executor_preflight": {"executor_id": "langgraph"},
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now, live_dogfood_max_age_hours=24)

    assert summary["latest_run_id"] == "newer-matrix-dogfood"
    assert "queue_worker_daemon_missing" in summary["latest_evidence_gaps"]
    queue_worker = summary["retained_evidence"]["queue_worker_daemon"]
    assert queue_worker["retained_from_run_id"] == "queue-worker-long-soak"
    assert queue_worker["tick_delta"] == 6
    assert queue_worker["min_ticks"] == 6
    assert queue_worker["soak_passed"] is True
    assert summary["retained_evidence"]["agent_server"]["retained_from_run_id"] == "newer-matrix-dogfood"
    assert summary["retained_evidence"]["live_provider_dogfood"]["retained_from_run_id"] == "newer-matrix-dogfood"
    assert summary["retained_evidence_gaps"] == []
    assert module._summary_exit_code(summary, fail_on_latest_evidence_gaps=True) == 3
    assert module._summary_exit_code(summary, fail_on_retained_evidence_gaps=True) == 0


def test_plan_v7_artifact_summary_flags_retained_short_queue_worker_soak(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "short-retained-queue",
        status="passed",
        command_statuses=["passed"],
        finished_at=now.isoformat(),
    )
    run_root = tmp_path / "short-retained-queue"
    _write_agent_server_matrix(run_root)
    _write_queue_worker_long_soak(run_root, tick_delta=3, min_ticks=3)
    (run_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "completed",
                    "profile": "core_loop",
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "rd-short-queue",
                        "runtime_dogfood_status": "completed",
                        **_live_handoff_summary(),
                    },
                    "executor_preflight": {"executor_id": "langgraph"},
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now, live_dogfood_max_age_hours=24)

    assert summary["retained_evidence"]["queue_worker_daemon"]["long_soak"] is False
    assert summary["retained_evidence"]["queue_worker_daemon"]["soak_passed"] is False
    assert summary["retained_evidence_gaps"] == ["queue_worker_daemon_soak_missing"]
    assert module._summary_exit_code(summary, fail_on_retained_evidence_gaps=True) == 4


def test_plan_v7_artifact_summary_retains_recent_live_dogfood_from_previous_run(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "live-dogfood",
        status="passed",
        command_statuses=["passed"],
        finished_at=(now - timedelta(hours=4)).isoformat(),
    )
    live_root = tmp_path / "live-dogfood"
    (live_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "completed",
                    "profile": "core_loop",
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "rd-live-retained",
                        "runtime_dogfood_status": "completed",
                        **_live_handoff_summary(),
                    },
                    "executor_preflight": {"executor_id": "langgraph"},
                },
            }
        ),
        encoding="utf-8",
    )
    _write_manifest(
        tmp_path,
        "newer-matrix",
        status="passed",
        command_statuses=["passed"],
        finished_at=now.isoformat(),
    )
    _write_agent_server_matrix(tmp_path / "newer-matrix")
    _write_queue_worker_long_soak(tmp_path / "newer-matrix")

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now, live_dogfood_max_age_hours=24)

    assert summary["latest_run_id"] == "newer-matrix"
    assert "live_provider_dogfood_missing" in summary["latest_evidence_gaps"]
    agent_server = summary["retained_evidence"]["agent_server"]
    assert agent_server["retained_from_run_id"] == "newer-matrix"
    assert agent_server["coverage_complete"] is True
    retained = summary["retained_evidence"]["live_provider_dogfood"]
    assert retained["retained_from_run_id"] == "live-dogfood"
    assert retained["fresh"] is True
    assert retained["ticket_id"] == "rd-live-retained"
    assert summary["retained_evidence_gaps"] == []
    assert module._summary_exit_code(summary, fail_on_latest_evidence_gaps=True) == 3
    assert module._summary_exit_code(summary, fail_on_retained_evidence_gaps=True) == 0


def test_plan_v7_artifact_summary_marks_retained_live_dogfood_stale(tmp_path) -> None:
    module = _module()
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    _write_manifest(
        tmp_path,
        "old-live-dogfood",
        status="passed",
        command_statuses=["passed"],
        finished_at=(now - timedelta(days=8)).isoformat(),
    )
    run_root = tmp_path / "old-live-dogfood"
    _write_agent_server_matrix(run_root)
    _write_queue_worker_long_soak(run_root)
    (run_root / "live_provider_dogfood.json").write_text(
        json.dumps(
            {
                "schema": "aiteamos.live_provider_dogfood.cli.v1",
                "result": {
                    "status": "completed",
                    "profile": "core_loop",
                    "summary": {
                        "dogfood_profile": "core_loop",
                        "ticket_id": "rd-live-old",
                        "runtime_dogfood_status": "completed",
                        **_live_handoff_summary(),
                    },
                    "executor_preflight": {"executor_id": "langgraph"},
                },
            }
        ),
        encoding="utf-8",
    )

    summary = module.summarize_artifacts(tmp_path, limit=10, now=now, live_dogfood_max_age_hours=24)

    dogfood = summary["latest_evidence"]["live_provider_dogfood"]
    assert dogfood["fresh"] is False
    assert dogfood["freshness_status"] == "stale"
    assert "live_provider_dogfood_stale" in summary["latest_evidence_gaps"]
    assert summary["retained_evidence_gaps"] == ["live_provider_dogfood_stale"]
