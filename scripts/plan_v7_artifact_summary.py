#!/usr/bin/env python3
"""Summarize saved plan_v7 verification artifact manifests."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT_DIR / ".aiteamos" / "artifacts" / "plan_v7"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize plan_v7 verification artifact manifests.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--live-dogfood-max-age-hours",
        type=float,
        default=168.0,
        help="Maximum age for retained live provider dogfood evidence to be considered fresh.",
    )
    parser.add_argument("--output", default="")
    parser.add_argument("--fail-on-failed", action="store_true")
    parser.add_argument(
        "--fail-on-latest-evidence-gaps",
        action="store_true",
        help="Exit non-zero when the latest inspected run has evidence gaps.",
    )
    parser.add_argument(
        "--fail-on-retained-evidence-gaps",
        action="store_true",
        help="Exit non-zero when retained cross-run evidence has gaps.",
    )
    parser.add_argument(
        "--fail-on-evidence-gaps",
        action="store_true",
        help="Exit non-zero when latest or retained evidence has gaps.",
    )
    args = parser.parse_args()

    summary = summarize_artifacts(
        Path(args.artifact_dir).expanduser().resolve(),
        limit=args.limit,
        live_dogfood_max_age_hours=args.live_dogfood_max_age_hours,
    )
    text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return _summary_exit_code(
        summary,
        fail_on_failed=args.fail_on_failed,
        fail_on_latest_evidence_gaps=args.fail_on_latest_evidence_gaps or args.fail_on_evidence_gaps,
        fail_on_retained_evidence_gaps=args.fail_on_retained_evidence_gaps or args.fail_on_evidence_gaps,
    )


def summarize_artifacts(
    artifact_dir: Path,
    *,
    limit: int = 10,
    live_dogfood_max_age_hours: float = 168.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = _ensure_aware_datetime(now) or datetime.now(timezone.utc)
    max_age_seconds = max(0, int(float(live_dogfood_max_age_hours) * 3600))
    manifests = _load_manifests(artifact_dir)
    selected = manifests[: max(0, limit)]
    runs = [
        _run_summary(
            item,
            now=generated_at,
            live_dogfood_max_age_seconds=max_age_seconds,
        )
        for item in selected
    ]
    failed_runs = [run for run in runs if _is_failed_status(str(run.get("status") or ""))]
    running_runs = [run for run in runs if str(run.get("status") or "") == "running"]
    latest = runs[0] if runs else {}
    retained_evidence = _retained_evidence(runs)
    retained_gaps = _retained_evidence_gaps(retained_evidence)
    return {
        "schema": "aiteamos.plan_v7.artifact_summary.v2",
        "generated_at": generated_at.isoformat(),
        "artifact_dir": str(artifact_dir),
        "inspected_run_count": len(runs),
        "total_manifest_count": len(manifests),
        "freshness_policy": {
            "live_dogfood_max_age_hours": live_dogfood_max_age_hours,
            "live_dogfood_max_age_seconds": max_age_seconds,
        },
        "passed_run_count": sum(1 for run in runs if run["status"] == "passed"),
        "failed_run_count": len(failed_runs),
        "running_run_count": len(running_runs),
        "non_passed_run_count": sum(1 for run in runs if run["status"] != "passed"),
        "latest_status": latest.get("status", "missing"),
        "latest_run_id": latest.get("run_id", ""),
        "latest_finished_at": latest.get("finished_at", ""),
        "latest_evidence": latest.get("evidence", {}),
        "latest_evidence_gaps": latest.get("evidence_gaps", []),
        "retained_evidence": retained_evidence,
        "retained_evidence_gaps": retained_gaps,
        "failed_commands": [command for run in failed_runs for command in run["failed_commands"]],
        "runs": runs,
    }


def _load_manifests(artifact_dir: Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    if not artifact_dir.exists():
        return manifests
    for path in artifact_dir.glob("*/manifest.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["_manifest_path"] = str(path)
            manifests.append(payload)
    return sorted(
        manifests,
        key=lambda item: str(item.get("finished_at") or item.get("started_at") or item.get("run_id") or ""),
        reverse=True,
    )


def _run_summary(
    manifest: dict[str, Any],
    *,
    now: datetime,
    live_dogfood_max_age_seconds: int,
) -> dict[str, Any]:
    commands = [item for item in manifest.get("commands", []) if isinstance(item, dict)]
    artifact_root = str(manifest.get("artifact_root") or "")
    evidence = (
        _run_evidence(
            Path(artifact_root),
            manifest,
            commands,
            now=now,
            live_dogfood_max_age_seconds=live_dogfood_max_age_seconds,
        )
        if artifact_root
        else {"items": {}, "gaps": []}
    )
    failed_commands = [
        {
            "run_id": str(manifest.get("run_id") or ""),
            "name": str(command.get("name") or ""),
            "status": str(command.get("status") or ""),
            "return_code": command.get("return_code"),
            "result_path": str(command.get("result_path") or ""),
            "stderr_tail": str(command.get("stderr_tail") or "")[-1000:],
        }
        for command in commands
        if str(command.get("status") or "") != "passed"
    ]
    return {
        "run_id": str(manifest.get("run_id") or ""),
        "status": str(manifest.get("status") or "unknown"),
        "started_at": str(manifest.get("started_at") or ""),
        "finished_at": str(manifest.get("finished_at") or ""),
        "artifact_root": artifact_root,
        "manifest_path": str(manifest.get("_manifest_path") or ""),
        "command_count": len(commands),
        "passed_command_count": sum(1 for command in commands if str(command.get("status") or "") == "passed"),
        "failed_command_count": len(failed_commands),
        "failed_commands": failed_commands,
        "options": manifest.get("options") if isinstance(manifest.get("options"), dict) else {},
        "evidence": evidence["items"],
        "evidence_gaps": evidence["gaps"],
    }


def _is_failed_status(status: str) -> bool:
    return status in {"failed", "blocked", "error", "timed_out"}


def _summary_exit_code(
    summary: dict[str, Any],
    *,
    fail_on_failed: bool = False,
    fail_on_latest_evidence_gaps: bool = False,
    fail_on_retained_evidence_gaps: bool = False,
) -> int:
    if fail_on_failed and _to_int(summary.get("failed_run_count")):
        return 2
    if fail_on_latest_evidence_gaps and _strings(summary.get("latest_evidence_gaps")):
        return 3
    if fail_on_retained_evidence_gaps and _strings(summary.get("retained_evidence_gaps")):
        return 4
    return 0


def _run_evidence(
    artifact_root: Path,
    manifest: dict[str, Any],
    commands: list[dict[str, Any]],
    *,
    now: datetime,
    live_dogfood_max_age_seconds: int,
) -> dict[str, Any]:
    items: dict[str, Any] = {}
    gaps: list[str] = []
    queue_worker = _queue_worker_daemon_evidence(artifact_root)
    if queue_worker:
        items["queue_worker_daemon"] = queue_worker
        gaps.extend(_queue_worker_daemon_gaps(queue_worker))
    else:
        gaps.append("queue_worker_daemon_missing")

    context_retrieval = _context_retrieval_evidence(artifact_root)
    if context_retrieval:
        items["context_retrieval"] = context_retrieval
    else:
        gaps.append("context_retrieval_eval_smoke_missing")

    asset_provenance = _asset_provenance_evidence(artifact_root)
    if asset_provenance:
        items["asset_provenance"] = asset_provenance
    else:
        gaps.append("asset_provenance_eval_smoke_missing")

    runtime_replay = _runtime_replay_evidence(artifact_root)
    if runtime_replay:
        items["runtime_replay"] = runtime_replay
        gaps.extend(_runtime_replay_gaps(runtime_replay))
    else:
        gaps.append("runtime_replay_eval_smoke_missing")

    environment_smoke = _environment_smoke_evidence(artifact_root)
    if environment_smoke:
        items["environment_smoke"] = environment_smoke
        gaps.extend(_environment_smoke_gaps(environment_smoke))
    else:
        gaps.append("environment_smoke_missing")

    runtime_registry = _runtime_registry_evidence(artifact_root)
    if runtime_registry:
        items["runtime_registry"] = runtime_registry
        gaps.extend(_runtime_registry_gaps(runtime_registry))
    else:
        gaps.append("runtime_registry_smoke_missing")

    agent_server = _agent_server_evidence(artifact_root)
    if agent_server:
        items["agent_server"] = agent_server
        gaps.extend(str(item) for item in agent_server.get("gaps", []) if str(item))
    else:
        gaps.append("agent_server_matrix_smoke_missing")

    live_readiness = _live_provider_readiness_evidence(artifact_root)
    if live_readiness:
        items["live_provider_readiness"] = live_readiness
    else:
        gaps.append("live_provider_readiness_missing")

    plane_action = _plane_ticket_action_smoke_evidence(artifact_root)
    if plane_action:
        items["plane_ticket_action_smoke"] = plane_action
        gaps.extend(_plane_ticket_action_smoke_gaps(plane_action))

    live_dogfood = _live_provider_dogfood_evidence(
        artifact_root,
        manifest,
        commands,
        now=now,
        max_age_seconds=live_dogfood_max_age_seconds,
    )
    if live_dogfood:
        items["live_provider_dogfood"] = live_dogfood
        gaps.extend(_live_provider_dogfood_gaps(live_dogfood))
    else:
        gaps.append("live_provider_dogfood_missing")
    return {"items": items, "gaps": gaps}


def _queue_worker_daemon_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "ticket_loop_queue_worker_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    summary = _record(payload.get("summary"))
    daemon = _record(summary.get("daemon")) or _record(payload.get("daemon"))
    stopped_status = _record(daemon.get("stopped_status"))
    after_reliability = _record(summary.get("after_reliability"))
    policy_actions = _records(summary.get("policy_actions"))
    policy_action_kinds = [str(item.get("kind") or "") for item in policy_actions if str(item.get("kind") or "")]
    asset_candidate_ids = _strings(summary.get("asset_candidate_ids"))
    failed_delta = _to_int(summary.get("failed_delta"))
    worker_policy_action_delta = _to_int(summary.get("worker_policy_action_delta"))
    processed_statuses = _strings(summary.get("processed_statuses"))
    tick_delta = _to_int(daemon.get("tick_delta"))
    processed_delta = _to_int(daemon.get("processed_delta"))
    min_ticks = _to_int(daemon.get("min_ticks")) or 0
    repeated_failure_policy_evidence = (
        failed_delta >= 2
        and processed_statuses.count("blocked") + processed_statuses.count("failed") >= 2
        and "failure_retrospective_candidate" in policy_action_kinds
        and bool(asset_candidate_ids)
        and worker_policy_action_delta >= 1
    )
    return {
        "status": str(summary.get("daemon_status") or daemon.get("status") or payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "ticket_id": str(summary.get("ticket_id") or ""),
        "queue_ids": _strings(summary.get("queue_ids")),
        "processed_statuses": processed_statuses,
        "failed_delta": failed_delta,
        "after_reliability_status": str(after_reliability.get("status") or ""),
        "after_reliability_failed_count": _to_int(after_reliability.get("failed_count")),
        "asset_candidate_ids": asset_candidate_ids,
        "policy_action_kinds": policy_action_kinds,
        "worker_processed_delta": _to_int(summary.get("worker_processed_delta")),
        "worker_policy_action_delta": worker_policy_action_delta,
        "repeated_failure_policy_evidence": repeated_failure_policy_evidence,
        "daemon_ticket_id": str(daemon.get("ticket_id") or ""),
        "tick_delta": tick_delta,
        "processed_delta": processed_delta,
        "min_ticks": min_ticks,
        "interval_seconds": _to_float(daemon.get("interval_seconds")),
        "timeout_seconds": _to_float(daemon.get("timeout_seconds")),
        "queue_statuses": _strings(daemon.get("queue_statuses")),
        "run_statuses": _strings(daemon.get("run_statuses")),
        "last_tick_status": str(stopped_status.get("last_tick_status") or daemon.get("last_tick_status") or ""),
        "last_error": str(stopped_status.get("last_error") or daemon.get("last_error") or ""),
        "policy_action_count": len(policy_actions),
        "long_soak": min_ticks >= 6,
        "soak_passed": min_ticks >= 6 and tick_delta >= min_ticks and processed_delta >= 2,
    }


def _queue_worker_daemon_gaps(queue_worker: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    status = str(queue_worker.get("status") or "unknown")
    if status != "passed":
        gaps.append(f"queue_worker_daemon_{status}")
    if not bool(queue_worker.get("soak_passed")):
        gaps.append("queue_worker_daemon_soak_missing")
    if not bool(queue_worker.get("repeated_failure_policy_evidence")):
        gaps.append("queue_worker_repeated_failure_policy_missing")
    if str(queue_worker.get("last_error") or ""):
        gaps.append("queue_worker_daemon_last_error")
    return gaps


def _context_retrieval_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "context_retrieval_eval_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    summary = _record(payload.get("summary"))
    work_history = _record(summary.get("work_history"))
    return {
        "status": str(payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "ticket_id": str(summary.get("ticket_id") or ""),
        "graphiti_result_count": _to_int(summary.get("graphiti_result_count")),
        "graphiti_excluded_result_count": _to_int(summary.get("graphiti_excluded_result_count")),
        "active_asset_ids": _strings(summary.get("active_asset_ids")),
        "stale_hint_asset_ids": _strings(summary.get("stale_hint_asset_ids")),
        "wrong_ticket_filtered": bool(summary.get("wrong_ticket_filtered")),
        "work_history_employee_id": str(work_history.get("employee_id") or ""),
        "work_history_report_id": str(work_history.get("report_id") or ""),
        "work_history_report_count": _to_int(work_history.get("report_count")),
        "work_history_current_ticket_count": _to_int(work_history.get("current_ticket_count")),
        "work_history_eval_recall": _to_float(work_history.get("eval_recall")),
        "work_history_eval_precision_like": _to_float(work_history.get("eval_precision_like")),
        "work_history_missing_ref_count": len(_records(work_history.get("missing_refs"))),
        "provider_blocker_count": _to_int(summary.get("provider_blocker_count")),
    }


def _asset_provenance_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "asset_provenance_eval_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    summary = _record(payload.get("summary"))
    return {
        "status": str(payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "source_asset_id": str(summary.get("source_asset_id") or ""),
        "target_asset_id": str(summary.get("target_asset_id") or ""),
        "relationship_id": str(summary.get("relationship_id") or ""),
        "relationship_projection_status": str(summary.get("relationship_projection_status") or ""),
        "relationship_ingested_count": _to_int(summary.get("relationship_ingested_count")),
        "relationship_repeated_status": str(summary.get("relationship_repeated_status") or ""),
        "relationship_skipped_count": _to_int(summary.get("relationship_skipped_count")),
        "asset_record_graphiti_relationship_count": _to_int(summary.get("asset_record_graphiti_relationship_count")),
        "relationship_search_result_count": _to_int(summary.get("relationship_search_result_count")),
        "stale_memory_id": str(summary.get("stale_memory_id") or ""),
        "stale_review_status": str(summary.get("stale_review_status") or ""),
        "stale_before_result_count": _to_int(summary.get("stale_before_result_count")),
        "stale_after_active_count": _to_int(summary.get("stale_after_active_count")),
        "stale_after_excluded_count": _to_int(summary.get("stale_after_excluded_count")),
        "stale_active_filtered": bool(summary.get("stale_active_filtered")),
    }


def _runtime_replay_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "runtime_replay_eval_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    summary = _record(payload.get("summary"))
    coverage = _record(summary.get("coverage"))
    counts = _record(summary.get("counts"))
    gaps = _strings(summary.get("gaps"))
    return {
        "status": str(payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "ticket_id": str(summary.get("ticket_id") or ""),
        "session_key": str(summary.get("session_key") or ""),
        "request_id": str(summary.get("request_id") or ""),
        "required_chain_complete": bool(summary.get("required_chain_complete")),
        "gap_count": len(gaps),
        "gaps": gaps,
        "ticket": bool(coverage.get("ticket")),
        "employee": bool(coverage.get("employee")),
        "runtime": bool(coverage.get("runtime")),
        "evidence": bool(coverage.get("evidence")),
        "trace": bool(coverage.get("trace")),
        "state": bool(coverage.get("state")),
        "checkpoint": bool(coverage.get("checkpoint")),
        "approval": bool(coverage.get("approval")),
        "asset_or_memory": bool(coverage.get("asset_or_memory")),
        "handoff": bool(summary.get("handoff") or coverage.get("handoff")),
        "handoff_policy": bool(summary.get("handoff_policy") or coverage.get("handoff_policy")),
        "handoff_status": str(summary.get("handoff_status") or ""),
        "handoff_target_employee_id": str(summary.get("handoff_target_employee_id") or ""),
        "handoff_lane": str(summary.get("handoff_lane") or ""),
        "handoff_required_memory_scopes": _strings(summary.get("handoff_required_memory_scopes")),
        "handoff_matched_memory_scopes": _strings(summary.get("handoff_matched_memory_scopes")),
        "handoff_memory_scope_match": str(summary.get("handoff_memory_scope_match") or ""),
        "handoff_risk_level": str(summary.get("handoff_risk_level") or ""),
        "handoff_max_risk_level": str(summary.get("handoff_max_risk_level") or ""),
        "handoff_risk_allowed": bool(summary.get("handoff_risk_allowed")),
        "handoff_ref_count": _to_int(summary.get("handoff_ref_count")) or _to_int(counts.get("handoff_ref_count")),
        "timeline_event_count": _to_int(counts.get("timeline_event_count")),
        "artifact_count": _to_int(counts.get("artifact_count")),
        "evidence_count": _to_int(counts.get("evidence_count")),
        "trace_event_count": _to_int(counts.get("trace_event_count")),
        "state_transition_count": _to_int(counts.get("state_transition_count")),
        "ticket_refs": _strings(summary.get("ticket_refs")),
        "employee_refs": _strings(summary.get("employee_refs")),
        "asset_refs": _strings(summary.get("asset_refs")),
        "memory_refs": _strings(summary.get("memory_refs")),
        "evidence_refs": _strings(summary.get("evidence_refs")),
        "checkpoint_refs": _strings(summary.get("checkpoint_refs")),
        "trace_refs": _strings(summary.get("trace_refs")),
        "trace_redacted": bool(summary.get("trace_redacted")),
        "artifact_secret_redacted": bool(summary.get("artifact_secret_redacted")),
    }


def _runtime_replay_gaps(runtime_replay: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    status = str(runtime_replay.get("status") or "unknown")
    if status != "passed":
        gaps.append(f"runtime_replay_eval_smoke_{status}")
    if not bool(runtime_replay.get("required_chain_complete")) or _to_int(runtime_replay.get("gap_count")):
        gaps.append("runtime_replay_required_chain_incomplete")
    if not bool(runtime_replay.get("handoff")):
        gaps.append("runtime_replay_handoff_summary_missing")
    elif not bool(runtime_replay.get("handoff_policy")):
        gaps.append("runtime_replay_handoff_policy_missing")
    elif not _runtime_replay_handoff_policy_complete(runtime_replay):
        gaps.append("runtime_replay_handoff_policy_incomplete")
    return gaps


def _runtime_replay_handoff_policy_complete(runtime_replay: dict[str, Any]) -> bool:
    return (
        runtime_replay.get("handoff_status") == "employee_handoff_recorded"
        and runtime_replay.get("handoff_target_employee_id") == "victor"
        and "employee:victor" in _strings(runtime_replay.get("handoff_matched_memory_scopes"))
        and runtime_replay.get("handoff_memory_scope_match") == "matched"
        and runtime_replay.get("handoff_risk_level") == "critical"
        and runtime_replay.get("handoff_risk_allowed") is True
        and _to_int(runtime_replay.get("handoff_ref_count")) >= 3
    )


def _environment_smoke_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "environment_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    result = _record(payload.get("result"))
    summary = _record(result.get("summary"))
    provider_smoke = _record(result.get("provider_smoke"))
    provider_summary = _record(provider_smoke.get("summary"))
    checks = _records(result.get("checks"))
    check_summaries = [_environment_check_summary(check) for check in checks]
    langchain_provider = _langchain_model_provider_evidence(checks)
    return {
        "status": str(result.get("status") or payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "contract_version": str(result.get("contract_version") or summary.get("contract_version") or ""),
        "include_external": bool(payload.get("include_external") or summary.get("include_external")),
        "external_calls": bool(summary.get("external_calls")),
        "non_destructive": bool(summary.get("non_destructive")),
        "evaluation_scope": str(summary.get("evaluation_scope") or ""),
        "check_count": _to_int(summary.get("check_count")) or len(check_summaries),
        "passed_count": _to_int(summary.get("passed_count")),
        "blocked_count": _to_int(summary.get("blocked_count")),
        "warning_count": _to_int(summary.get("warning_count")),
        "failed_count": _to_int(summary.get("failed_count")),
        "provider_smoke_status": str(provider_smoke.get("status") or ""),
        "provider_count": _to_int(provider_summary.get("provider_count")),
        "provider_passed_count": _to_int(provider_summary.get("passed_count")),
        "provider_blocked_count": _to_int(provider_summary.get("blocked_count")),
        "provider_warning_count": _to_int(provider_summary.get("warning_count")),
        "provider_failed_count": _to_int(provider_summary.get("failed_count")),
        "provider_external_calls": bool(provider_summary.get("external_calls")),
        "langchain_model_provider": langchain_provider,
        "langchain_provider_boundary_ready": _langchain_provider_boundary_visible(langchain_provider),
        "checks": check_summaries,
        "check_statuses": {item["id"]: item["status"] for item in check_summaries if item.get("id")},
        "blocker_ids": _unique_strings(
            [
                blocker.get("id")
                for check in checks
                for blocker in _records(check.get("blockers"))
            ]
        ),
    }


def _environment_check_summary(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(check.get("id") or ""),
        "scope": str(check.get("scope") or ""),
        "status": str(check.get("status") or ""),
        "check_count": len(_strings(check.get("checks"))),
        "blocker_count": len(_records(check.get("blockers"))),
        "warning_count": len(_strings(check.get("warnings"))),
        "failure_count": len(_strings(check.get("failures"))),
        "external_calls": bool(check.get("external_calls")),
    }


def _langchain_model_provider_evidence(checks: list[dict[str, Any]]) -> dict[str, Any]:
    for check in checks:
        if str(check.get("id") or "") != "ai_engine:deepseek":
            continue
        evidence = _record(check.get("evidence"))
        provider = _record(evidence.get("langchain_model_provider"))
        check_items = _strings(check.get("checks"))
        return {
            "status": str(check.get("status") or ""),
            "selected_provider": str(provider.get("selected_provider") or "deepseek"),
            "deepseek_model": str(provider.get("deepseek_model") or ""),
            "openai_model": str(provider.get("openai_model") or ""),
            "configured": _bool_record(provider.get("configured")),
            "missing_env": _strings(provider.get("missing_env")),
            "provider_packages_required": _strings(provider.get("provider_packages_required")),
            "config_inspected": "langchain_model_provider_config_inspected" in check_items,
            "no_external_llm_call": "no_external_llm_call" in check_items and not bool(check.get("external_calls")),
            "checks": check_items,
            "blocker_count": len(_records(check.get("blockers"))),
            "warning_count": len(_strings(check.get("warnings"))),
        }
    return {}


def _langchain_provider_boundary_visible(evidence: dict[str, Any]) -> bool:
    return (
        bool(evidence)
        and evidence.get("selected_provider") == "deepseek"
        and bool(evidence.get("config_inspected"))
        and bool(evidence.get("no_external_llm_call"))
        and "langchain-deepseek" in _strings(evidence.get("provider_packages_required"))
    )


def _environment_smoke_gaps(environment_smoke: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    status = str(environment_smoke.get("status") or "unknown")
    if status not in {"passed", "warning"}:
        gaps.append(f"environment_smoke_{status}")
    if _to_int(environment_smoke.get("failed_count")):
        gaps.append("environment_smoke_failed_checks")
    if _to_int(environment_smoke.get("provider_failed_count")):
        gaps.append("environment_smoke_provider_failures")
    if not _langchain_provider_boundary_visible(_record(environment_smoke.get("langchain_model_provider"))):
        gaps.append("langchain_model_provider_boundary_missing")
    return gaps


def _runtime_registry_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "runtime_registry_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    summary = _record(payload.get("summary"))
    result = _record(payload.get("result"))
    live_readiness = _record(result.get("live_provider_readiness"))
    live_summary = _record(live_readiness.get("summary"))
    return {
        "status": str(payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "executor_count": _to_int(summary.get("executor_count")),
        "ready_count": _to_int(summary.get("ready_count")),
        "blocked_count": _to_int(summary.get("blocked_count")),
        "runtime_boundary": str(summary.get("runtime_boundary") or ""),
        "executor_ids": _strings(summary.get("executor_ids")),
        "blocker_executor_ids": _strings(summary.get("blocker_executor_ids")),
        "live_provider_status": str(summary.get("live_provider_status") or live_readiness.get("status") or ""),
        "live_provider_selected_executor_id": str(
            summary.get("live_provider_selected_executor_id") or live_readiness.get("selected_executor_id") or ""
        ),
        "live_provider_blocker_count": _to_int(summary.get("live_provider_blocker_count") or live_summary.get("blocker_count")),
        "live_provider_blocker_reasons": _strings(summary.get("live_provider_blocker_reasons") or live_readiness.get("reasons")),
        "live_provider_setup_required": _strings(summary.get("live_provider_setup_required") or live_readiness.get("setup_required")),
        "live_provider_mutation_gate_open": bool(summary.get("live_provider_mutation_gate_open")),
        "live_provider_mutation_gate_confirm_env_var": str(summary.get("live_provider_mutation_gate_confirm_env_var") or ""),
        "live_provider_ticket_backend_status": str(summary.get("live_provider_ticket_backend_status") or ""),
        "live_provider_memory_backend_status": str(summary.get("live_provider_memory_backend_status") or ""),
        "live_provider_provider_smoke_status": str(summary.get("live_provider_provider_smoke_status") or ""),
        "repo_write_ready_count": _to_int(summary.get("repo_write_ready_count") or live_summary.get("repo_write_ready_count")),
        "repo_write_candidate_count": _to_int(summary.get("repo_write_candidate_count") or live_summary.get("repo_write_candidate_count")),
        "repo_write_candidate_executor_ids": _strings(summary.get("repo_write_candidate_executor_ids")),
    }


def _runtime_registry_gaps(runtime_registry: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    status = str(runtime_registry.get("status") or "unknown")
    executor_ids = _strings(runtime_registry.get("executor_ids"))
    if status != "passed":
        gaps.append(f"runtime_registry_smoke_{status}")
    if str(runtime_registry.get("runtime_boundary") or "") != "RuntimeExecutor":
        gaps.append("runtime_registry_boundary_missing")
    if not executor_ids:
        gaps.append("runtime_registry_executors_missing")
    if "direct_llm" in executor_ids:
        gaps.append("runtime_registry_direct_llm_present")
    if str(runtime_registry.get("live_provider_selected_executor_id") or "") not in {"", "langgraph"}:
        gaps.append("runtime_registry_core_loop_not_langgraph")
    if not str(runtime_registry.get("live_provider_status") or ""):
        gaps.append("runtime_registry_live_provider_status_missing")
    return gaps


def _agent_server_evidence(artifact_root: Path) -> dict[str, Any]:
    case_specs = {
        "readonly_list": artifact_root / "agent-server-matrix" / "readonly_list.json",
        "answer_only": artifact_root / "agent-server-matrix" / "answer_only.json",
        "provider_blocker": artifact_root / "agent-server-matrix" / "provider_blocker.json",
        "handoff_policy": artifact_root / "agent-server-matrix" / "handoff_policy.json",
        "approval_resume": artifact_root / "agent-server-matrix" / "approval_resume.json",
        "approval_evidence_review": artifact_root / "agent-server-matrix" / "approval_evidence_review.json",
        "approval_rejected_review": artifact_root / "agent-server-matrix" / "approval_rejected_review.json",
        "approval_changes_review": artifact_root / "agent-server-matrix" / "approval_changes_review.json",
    }
    cases = {
        name: _agent_server_case_evidence(path, name)
        for name, path in case_specs.items()
        if path.exists()
    }
    primary = _agent_server_case_evidence(
        artifact_root / "agent_server_primary_approval_resume.json",
        "primary_approval_resume",
    )
    if not cases and not primary:
        return {}
    langchain_provider = _agent_server_langchain_model_provider_evidence(artifact_root)
    coverage = {
        "readonly_complete": _agent_server_readonly_complete(cases.get("readonly_list", {})),
        "answer_only_complete": _agent_server_answer_only_complete(cases.get("answer_only", {})),
        "provider_blocker_visible": _agent_server_provider_blocker_visible(cases.get("provider_blocker", {})),
        "handoff_policy_memory_risk": _agent_server_handoff_policy_complete(cases.get("handoff_policy", {})),
        "approval_interrupt": _agent_server_approval_interrupt(cases.get("approval_resume", {})),
        "approval_resume_complete": _agent_server_approval_resume_complete(cases.get("approval_resume", {})),
        "review_evidence_requested": _agent_server_review_complete(
            cases.get("approval_evidence_review", {}),
            review_status="evidence_requested",
            ticket_status="waiting_evidence",
            report_type="approval_evidence_requested",
            timeline_status="evidence_requested",
        ),
        "review_rejected": _agent_server_review_complete(
            cases.get("approval_rejected_review", {}),
            review_status="rejected",
            ticket_status="blocked",
            report_type="approval_rejected",
            timeline_status="rejected",
        ),
        "review_changes_requested": _agent_server_review_complete(
            cases.get("approval_changes_review", {}),
            review_status="changes_requested",
            ticket_status="waiting_changes",
            report_type="approval_changes_requested",
            timeline_status="changes_requested",
        ),
        "langchain_provider_boundary_visible": _langchain_provider_boundary_visible(langchain_provider),
    }
    missing_cases = [name for name in case_specs if name not in cases]
    failed_cases = [name for name, case in cases.items() if case.get("status") != "passed" or case.get("smoke_status") != "passed"]
    coverage_gaps = [f"{key}_missing" for key, value in coverage.items() if not value]
    gaps = [f"agent_server_case_missing:{name}" for name in missing_cases]
    gaps.extend(f"agent_server_case_failed:{name}" for name in failed_cases)
    gaps.extend(f"agent_server_coverage:{gap}" for gap in coverage_gaps)
    case_count = len(cases)
    passed_case_count = sum(1 for case in cases.values() if case.get("status") == "passed" and case.get("smoke_status") == "passed")
    return {
        "status": "passed" if case_count and not gaps else "partial",
        "schema": "aiteamos.agent_server_matrix_evidence.v1",
        "case_count": case_count,
        "passed_case_count": passed_case_count,
        "failed_case_count": case_count - passed_case_count,
        "required_case_count": len(case_specs),
        "coverage": coverage,
        "coverage_complete": bool(case_count) and not gaps,
        "gaps": gaps,
        "langchain_model_provider": langchain_provider,
        "cases": cases,
        **({"primary_approval_resume": primary} if primary else {}),
    }


def _agent_server_langchain_model_provider_evidence(artifact_root: Path) -> dict[str, Any]:
    payload = _read_json(artifact_root / "environment_smoke.json")
    if not payload:
        return {}
    result = _record(payload.get("result"))
    checks = _records(result.get("checks"))
    return _langchain_model_provider_evidence(checks)


def _agent_server_case_evidence(path: Path, name: str) -> dict[str, Any]:
    payload = _read_json(path)
    if not payload:
        return {}
    smoke = _record(payload.get("smoke"))
    summary = _record(smoke.get("summary"))
    runtime_status = _record(summary.get("runtime_status"))
    active_ticket = _record(summary.get("active_ticket"))
    review = _record(summary.get("review"))
    resume = _record(summary.get("resume"))
    resume_runtime_status = _record(resume.get("runtime_status"))
    handoff_decision = _record(summary.get("handoff_decision"))
    handoff_policy = _record(handoff_decision.get("policy"))
    handoff_summary = _record(summary.get("handoff_summary"))
    return {
        "name": name,
        "status": str(payload.get("status") or "unknown"),
        "smoke_status": str(smoke.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "smoke_schema": str(smoke.get("schema") or ""),
        "assistant_id": str(payload.get("assistant_id") or smoke.get("assistant_id") or ""),
        "workspace_dir": str(payload.get("workspace_dir") or smoke.get("workspace_dir") or ""),
        "agent_thread_id": str(smoke.get("agent_thread_id") or ""),
        "business_thread_id": str(smoke.get("business_thread_id") or ""),
        "action": str(summary.get("action") or ""),
        "runtime_status": str(runtime_status.get("status") or ""),
        "current_node": str(runtime_status.get("current_node") or ""),
        "graph": str(runtime_status.get("graph") or ""),
        "executor_id": str(runtime_status.get("executor_id") or ""),
        "runtime_run_id": str(summary.get("runtime_run_id") or runtime_status.get("run_id") or ""),
        "ticket_id": str(active_ticket.get("id") or review.get("ticket_id") or _record(resume.get("active_ticket")).get("id") or ""),
        "approval_ref": str(summary.get("approval_ref") or ""),
        "approval_request_count": _to_int(summary.get("approval_request_count")),
        "provider_blocker_count": _to_int(summary.get("provider_blocker_count")),
        "provider_blocker_reasons": _unique_strings(summary.get("provider_blocker_reasons")),
        "asset_candidate_count": _to_int(summary.get("asset_candidate_count")),
        "linked_asset_count": _to_int(summary.get("linked_asset_count")),
        "handoff_target_employee_id": str(handoff_decision.get("target_employee_id") or ""),
        "handoff_status": str(handoff_summary.get("status") or ""),
        "handoff_lane": str(handoff_decision.get("lane") or ""),
        "handoff_required_memory_scopes": _unique_strings(handoff_policy.get("required_memory_scopes")),
        "handoff_matched_memory_scopes": _unique_strings(handoff_policy.get("matched_memory_scopes")),
        "handoff_memory_scope_match": str(handoff_policy.get("memory_scope_match") or ""),
        "handoff_risk_level": str(handoff_policy.get("risk_level") or ""),
        "handoff_max_risk_level": str(handoff_policy.get("max_risk_level") or ""),
        "handoff_risk_allowed": bool(handoff_policy.get("risk_allowed")),
        "ticket_handoff_ref_count": _to_int(summary.get("ticket_handoff_ref_count")),
        "resume_status": str(resume_runtime_status.get("status") or ""),
        "resume_current_node": str(resume_runtime_status.get("current_node") or ""),
        "resume_ticket_report_id": str(resume.get("ticket_report_id") or ""),
        "resume_asset_candidate_count": _to_int(resume.get("asset_candidate_count")),
        "resume_linked_asset_count": _to_int(resume.get("linked_asset_count")),
        "review_status": str(review.get("approval_status") or ""),
        "review_ticket_status": str(review.get("ticket_status") or ""),
        "review_ticket_id": str(review.get("ticket_id") or ""),
        "review_ticket_report_types": _unique_strings(review.get("ticket_report_types")),
        "review_ticket_report_ids": _unique_strings(review.get("ticket_report_ids")),
        "review_timeline_statuses": _unique_strings(review.get("timeline_statuses")),
        "check_count": len(_records(smoke.get("checks"))),
        "failed_check_count": sum(1 for check in _records(smoke.get("checks")) if not check.get("passed")),
    }


def _agent_server_readonly_complete(case: dict[str, Any]) -> bool:
    return (
        case.get("status") == "passed"
        and case.get("smoke_status") == "passed"
        and case.get("action") == "list_employees"
        and case.get("runtime_status") == "completed"
        and case.get("current_node") == "final_response"
        and _to_int(case.get("approval_request_count")) == 0
        and _to_int(case.get("provider_blocker_count")) == 0
    )


def _agent_server_answer_only_complete(case: dict[str, Any]) -> bool:
    return (
        case.get("status") == "passed"
        and case.get("smoke_status") == "passed"
        and case.get("action") == "answer_only"
        and case.get("runtime_status") == "completed"
        and case.get("current_node") == "final_response"
        and _to_int(case.get("approval_request_count")) == 0
        and _to_int(case.get("provider_blocker_count")) == 0
    )


def _agent_server_provider_blocker_visible(case: dict[str, Any]) -> bool:
    return (
        case.get("status") == "passed"
        and case.get("smoke_status") == "passed"
        and _to_int(case.get("provider_blocker_count")) >= 1
        and "plane_setup_blocker" in _strings(case.get("provider_blocker_reasons"))
    )


def _agent_server_handoff_policy_complete(case: dict[str, Any]) -> bool:
    return (
        case.get("status") == "passed"
        and case.get("smoke_status") == "passed"
        and case.get("action") == "answer_only"
        and case.get("runtime_status") == "completed"
        and case.get("current_node") == "final_response"
        and case.get("handoff_target_employee_id") == "victor"
        and case.get("handoff_status") == "durable_handoff_recorded"
        and "employee:victor" in _strings(case.get("handoff_matched_memory_scopes"))
        and case.get("handoff_risk_level") == "critical"
        and case.get("handoff_risk_allowed") is True
        and _to_int(case.get("ticket_handoff_ref_count")) >= 1
        and _to_int(case.get("approval_request_count")) == 0
        and _to_int(case.get("provider_blocker_count")) == 0
    )


def _agent_server_approval_interrupt(case: dict[str, Any]) -> bool:
    return (
        case.get("status") == "passed"
        and case.get("smoke_status") == "passed"
        and case.get("action") == "implement_ticket"
        and case.get("runtime_status") == "needs_approval"
        and case.get("current_node") == "approval_interrupt"
        and _to_int(case.get("approval_request_count")) >= 1
        and bool(str(case.get("approval_ref") or ""))
    )


def _agent_server_approval_resume_complete(case: dict[str, Any]) -> bool:
    return (
        _agent_server_approval_interrupt(case)
        and case.get("resume_status") == "completed"
        and case.get("resume_current_node") == "final_response"
        and bool(str(case.get("resume_ticket_report_id") or ""))
        and _to_int(case.get("resume_linked_asset_count")) >= 1
    )


def _agent_server_review_complete(
    case: dict[str, Any],
    *,
    review_status: str,
    ticket_status: str,
    report_type: str,
    timeline_status: str,
) -> bool:
    return (
        _agent_server_approval_interrupt(case)
        and case.get("review_status") == review_status
        and case.get("review_ticket_status") == ticket_status
        and report_type in _strings(case.get("review_ticket_report_types"))
        and timeline_status in _strings(case.get("review_timeline_statuses"))
    )


def _live_provider_readiness_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "live_provider_readiness_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    summary = _record(payload.get("summary"))
    result = _record(payload.get("result"))
    blockers = _records(result.get("blockers"))
    repo_candidates = _records(result.get("repo_write_executor_candidates"))
    return {
        "status": str(payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "readiness_status": str(summary.get("readiness_status") or result.get("status") or ""),
        "ready_for_live_dogfood": bool(summary.get("ready_for_live_dogfood")),
        "selected_executor_id": str(summary.get("selected_executor_id") or result.get("selected_executor_id") or ""),
        "selected_executor_status": str(summary.get("selected_executor_status") or ""),
        "selected_executor_blocker_reasons": _strings(summary.get("selected_executor_blocker_reasons")),
        "repo_write_candidate_count": _to_int(summary.get("repo_write_candidate_count")),
        "repo_write_ready_count": _to_int(summary.get("repo_write_ready_count")),
        "repo_write_ready_executor_ids": _strings(summary.get("repo_write_ready_executor_ids")),
        "ticket_backend_status": str(summary.get("ticket_backend_status") or ""),
        "memory_backend_status": str(summary.get("memory_backend_status") or ""),
        "provider_smoke_status": str(summary.get("provider_smoke_status") or ""),
        "mutation_gate_open": bool(summary.get("mutation_gate_open")),
        "mutation_gate_execute_flag": bool(summary.get("mutation_gate_execute_flag")),
        "mutation_gate_confirm_env_var": str(summary.get("mutation_gate_confirm_env_var") or ""),
        "mutation_gate_confirm_env_configured": bool(summary.get("mutation_gate_confirm_env_configured")),
        "mutation_gate_blocker_reason": str(summary.get("mutation_gate_blocker_reason") or ""),
        "blocker_count": _to_int(summary.get("blocker_count")),
        "blocker_reasons": _strings(summary.get("blocker_reasons")),
        "blocker_scopes": _strings(summary.get("blocker_scopes")),
        "blockers": _compact_blockers(blockers),
        "setup_required": _setup_required_from_blockers(blockers),
        "repo_write_candidates": _compact_repo_write_candidates(repo_candidates),
    }


def _plane_ticket_action_smoke_evidence(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "plane_ticket_action_smoke.json"
    payload = _read_json(path)
    if not payload:
        return {}
    result = _record(payload.get("result"))
    summary = _record(result.get("summary") or payload.get("summary"))
    blockers = _records(result.get("blockers"))
    return {
        "status": str(result.get("status") or payload.get("status") or "unknown"),
        "artifact_path": str(path),
        "schema": str(payload.get("schema") or ""),
        "provider": str(result.get("provider") or "plane"),
        "ticket_backend_status": str(summary.get("ticket_backend_status") or ""),
        "ticket_id": str(summary.get("ticket_id") or ""),
        "ticket_source": str(summary.get("ticket_source") or ""),
        "provider_record_id": str(summary.get("provider_record_id") or ""),
        "handoff_recorded": bool(summary.get("handoff_recorded")),
        "handoff_report_recorded": bool(summary.get("handoff_report_recorded")),
        "to_employee_id": str(summary.get("to_employee_id") or ""),
        "mutation_gate_open": bool(summary.get("mutation_gate_open")),
        "blocker_stage": str(summary.get("blocker_stage") or ""),
        "blocker_reason": str(summary.get("blocker_reason") or ""),
        "blocker_count": len(blockers),
        "blocker_reasons": _unique_strings([item.get("reason") for item in blockers]),
        "external_calls": bool(result.get("external_calls")),
        "mutating": bool(result.get("mutating")),
    }


def _plane_ticket_action_smoke_gaps(action_smoke: dict[str, Any]) -> list[str]:
    if str(action_smoke.get("status") or "") == "passed":
        return []
    return ["plane_ticket_action_smoke_not_passed"]


def _compact_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for blocker in blockers:
        compact.append(
            {
                "reason": str(blocker.get("reason") or blocker.get("id") or ""),
                "scope": str(blocker.get("scope") or ""),
                "status": str(blocker.get("status") or ""),
                "setup_required": _strings(blocker.get("setup_required")),
            }
        )
    return compact


def _setup_required_from_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    return _unique_strings(
        [
            item
            for blocker in blockers
            for item in _strings(blocker.get("setup_required"))
        ]
    )


def _compact_repo_write_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for candidate in candidates:
        compact.append(
            {
                "executor_id": str(candidate.get("executor_id") or ""),
                "status": str(candidate.get("status") or ""),
                "blocker_reasons": _strings(candidate.get("blocker_reasons")),
                "setup_required": _strings(candidate.get("setup_required")),
            }
        )
    return compact


def _live_provider_dogfood_evidence(
    artifact_root: Path,
    manifest: dict[str, Any],
    commands: list[dict[str, Any]],
    *,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    candidates = _dogfood_artifact_candidates(artifact_root, commands)
    for path in candidates:
        payload = _read_json(path)
        if not payload or not _looks_like_live_provider_dogfood(payload):
            continue
        result = _record(payload.get("result"))
        result_summary = _record(result.get("summary"))
        ticket = _record(result.get("ticket"))
        workbench = _record(result.get("workbench"))
        workbench_runtime_status = _record(result_summary.get("workbench_runtime_status") or workbench.get("runtime_status"))
        executor_preflight = _record(result.get("executor_preflight"))
        status = str(result.get("status") or payload.get("status") or "unknown")
        run_finished_at = str(manifest.get("finished_at") or "")
        age_seconds = _age_seconds(run_finished_at, now)
        freshness_status, freshness_reason = _dogfood_freshness(
            status=status,
            age_seconds=age_seconds,
            max_age_seconds=max_age_seconds,
        )
        return {
            "status": status,
            "artifact_path": str(path),
            "schema": str(payload.get("schema") or ""),
            "profile": str(result.get("profile") or result_summary.get("dogfood_profile") or payload.get("profile") or ""),
            "executor_id": str(
                result.get("executor_id")
                or result.get("selected_executor_id")
                or executor_preflight.get("executor_id")
                or payload.get("executor_id")
                or ""
            ),
            "ticket_id": str(
                result.get("ticket_id")
                or result_summary.get("ticket_id")
                or ticket.get("id")
                or payload.get("ticket_id")
                or ""
            ),
            "runtime_dogfood_status": str(result_summary.get("runtime_dogfood_status") or ""),
            "workbench_runtime_status": str(workbench_runtime_status.get("status") or ""),
            "workbench_runtime_run_id": str(workbench_runtime_status.get("run_id") or ""),
            "langgraph_thread_id": str(result_summary.get("langgraph_thread_id") or workbench.get("thread_id") or ""),
            "memory_candidate_ids": _strings(result_summary.get("memory_candidate_ids")),
            "asset_record_ids": _strings(result_summary.get("asset_record_ids")),
            "asset_record_count": len(_strings(result_summary.get("asset_record_ids"))),
            "graphiti_projection_statuses": _strings(result_summary.get("graphiti_projection_statuses")),
            "graphiti_projection_count": len(_strings(result_summary.get("graphiti_projection_statuses"))),
            "graphiti_recall_count": _to_int(result_summary.get("graphiti_recall_count")),
            "recall_result_count": _to_int(result_summary.get("recall_result_count")),
            "natural_handoff": bool(result_summary.get("natural_handoff")),
            "natural_handoff_required": bool(result_summary.get("natural_handoff_required")),
            "expected_handoff_target_employee_id": str(result_summary.get("expected_handoff_target_employee_id") or ""),
            "handoff_status": str(result_summary.get("handoff_status") or ""),
            "handoff_target_employee_id": str(result_summary.get("handoff_target_employee_id") or ""),
            "handoff_lane": str(result_summary.get("handoff_lane") or ""),
            "handoff_ref_count": _to_int(result_summary.get("handoff_ref_count")),
            "blocker_count": _to_int(result_summary.get("blocker_count")),
            "fresh": freshness_status == "fresh",
            "freshness_status": freshness_status,
            "freshness_reason": freshness_reason,
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
            "run_finished_at": run_finished_at,
        }
    return {}


def _live_provider_dogfood_gaps(dogfood: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not dogfood.get("fresh"):
        gaps.append(f"live_provider_dogfood_{dogfood.get('freshness_status') or 'not_fresh'}")
    if str(dogfood.get("profile") or "") != "core_loop":
        gaps.append("live_provider_dogfood_profile_not_core_loop")
    if str(dogfood.get("executor_id") or "") != "langgraph":
        gaps.append("live_provider_dogfood_executor_not_langgraph")
    if str(dogfood.get("runtime_dogfood_status") or "") != "completed":
        gaps.append("live_provider_dogfood_runtime_not_completed")
    if str(dogfood.get("profile") or "") == "core_loop" and not _live_provider_natural_handoff_complete(dogfood):
        gaps.append("live_provider_dogfood_natural_handoff_missing")
    return gaps


def _live_provider_natural_handoff_complete(dogfood: dict[str, Any]) -> bool:
    expected = str(dogfood.get("expected_handoff_target_employee_id") or "alex")
    target = str(dogfood.get("handoff_target_employee_id") or "")
    return (
        dogfood.get("natural_handoff") is True
        and dogfood.get("handoff_status") == "durable_handoff_recorded"
        and target == expected
        and _to_int(dogfood.get("handoff_ref_count")) >= 1
    )


def _dogfood_artifact_candidates(artifact_root: Path, commands: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    for command in commands:
        if "dogfood" not in str(command.get("name") or ""):
            continue
        result_path = Path(str(command.get("result_path") or ""))
        if result_path.name:
            paths.append(result_path)
    paths.extend(sorted(artifact_root.glob("*dogfood*.json")))
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _looks_like_live_provider_dogfood(payload: dict[str, Any]) -> bool:
    schema = str(payload.get("schema") or "")
    if "live_provider_dogfood" in schema:
        return True
    result = _record(payload.get("result"))
    return bool(result.get("ticket_id") and result.get("executor_id") and result.get("status"))


def _retained_evidence(runs: list[dict[str, Any]]) -> dict[str, Any]:
    retained: dict[str, Any] = {}
    for run in runs:
        evidence = _record(run.get("evidence"))
        if "agent_server" not in retained:
            agent_server = _record(evidence.get("agent_server"))
            if agent_server:
                retained["agent_server"] = {
                    **agent_server,
                    "retained_from_run_id": str(run.get("run_id") or ""),
                    "retained_from_manifest_path": str(run.get("manifest_path") or ""),
                }
        if "queue_worker_daemon" not in retained:
            queue_worker = _record(evidence.get("queue_worker_daemon"))
            if queue_worker:
                retained["queue_worker_daemon"] = {
                    **queue_worker,
                    "retained_from_run_id": str(run.get("run_id") or ""),
                    "retained_from_manifest_path": str(run.get("manifest_path") or ""),
                }
        if "live_provider_dogfood" not in retained:
            dogfood = _record(evidence.get("live_provider_dogfood"))
            if dogfood:
                retained["live_provider_dogfood"] = {
                    **dogfood,
                    "retained_from_run_id": str(run.get("run_id") or ""),
                    "retained_from_manifest_path": str(run.get("manifest_path") or ""),
                }
        if "agent_server" in retained and "queue_worker_daemon" in retained and "live_provider_dogfood" in retained:
            break
    return retained


def _retained_evidence_gaps(retained_evidence: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    agent_server = _record(retained_evidence.get("agent_server"))
    if not agent_server:
        gaps.append("agent_server_matrix_smoke_missing")
    else:
        gaps.extend(str(item) for item in agent_server.get("gaps", []) if str(item))
    queue_worker = _record(retained_evidence.get("queue_worker_daemon"))
    if not queue_worker:
        gaps.append("queue_worker_daemon_missing")
    else:
        gaps.extend(_queue_worker_daemon_gaps(queue_worker))
    dogfood = _record(retained_evidence.get("live_provider_dogfood"))
    if not dogfood:
        gaps.append("live_provider_dogfood_missing")
    else:
        gaps.extend(_live_provider_dogfood_gaps(dogfood))
    return gaps


def _dogfood_freshness(*, status: str, age_seconds: int, max_age_seconds: int) -> tuple[str, str]:
    if status not in {"completed", "passed", "ready"}:
        return "not_completed", f"live dogfood status is {status or 'unknown'}"
    if age_seconds < 0:
        return "unknown_age", "live dogfood artifact has no parseable run_finished_at timestamp"
    if age_seconds > max_age_seconds:
        return "stale", f"live dogfood artifact is older than {max_age_seconds} seconds"
    return "fresh", f"live dogfood artifact completed within {max_age_seconds} seconds"


def _age_seconds(timestamp: str, now: datetime) -> int:
    parsed = _parse_datetime(timestamp)
    if parsed is None:
        return -1
    return max(0, int((now - parsed).total_seconds()))


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return _ensure_aware_datetime(datetime.fromisoformat(text))
    except ValueError:
        return None


def _ensure_aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _bool_record(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {str(key): bool(item) for key, item in value.items()}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _unique_strings(value: Any) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in _strings(value):
        if item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
