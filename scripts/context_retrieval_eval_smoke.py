#!/usr/bin/env python3
"""Emit deterministic context retrieval evidence without adding a new retriever."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
SMOKE_SCHEMA = "aiteamos.context_retrieval_eval_smoke.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic LangGraph context retrieval evidence.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--output", default="", help="Optional path to write the JSON result.")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    try:
        payload = asyncio.run(run_smoke(workspace_root=workspace_root))
    except Exception as exc:
        payload = {
            "schema": SMOKE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "workspace_dir": str(workspace_root),
            "error": str(exc),
        }
    _write_output(payload, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


async def run_smoke(*, workspace_root: Path) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage

    from aiteamos_api.agents.workbench.nodes.context import retrieve_context
    from aiteamos_api.read import memory_service
    from aiteamos_api.read.context_retrieval_eval_service import (
        ContextRetrievalEvalCase,
        ContextRetrievalExpectedRef,
        evaluate_context_retrieval,
    )
    from aiteamos_api.read.ticket_service import (
        TicketBackendSettingsUpdateRequest,
        TicketCreateRequest,
        TicketReportRequest,
        add_ticket_report,
        create_ticket,
        update_ticket_backend_settings,
    )

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    os.environ["AITEAMOS_GRAPHITI_ENABLED"] = "true"
    os.environ.setdefault("AITEAMOS_GRAPHITI_URI", "bolt://localhost:7687")
    os.environ.setdefault("AITEAMOS_GRAPHITI_USER", "neo4j")
    os.environ.setdefault("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    os.environ.setdefault("OPENAI_API_KEY", "openai-test-key")
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Context retrieval smoke Ticket",
            description="Verify scoped Graphiti recall and excluded stale/conflict hints.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    updated = add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Context retrieval smoke work-history report for Alex runtime implementation.",
            report_type="progress",
            evidence=["pytest::context-retrieval-smoke::work-history"],
            source_run_id="run-context-retrieval-smoke-work-history",
        ),
    )
    work_report_id = updated.reports[-1].id

    memory_service.Graphiti = _fake_graphiti_for_ticket(ticket.id)  # type: ignore[attr-defined]
    memory_service.EpisodeType = _FakeEpisodeType  # type: ignore[attr-defined]

    query = "Graphiti context Neo4j password provider dogfood"
    result = await retrieve_context(
        {
            "messages": [HumanMessage(content=query)],
            "selected_employee": _employee(),
            "employee_profiles": _employee_profiles(),
            "ticket_key": ticket.id,
            "ticket_keys": [ticket.id],
            "selected_ai_engine": "deepseek",
            "context_bundle": {"initial_context_assets": {"memory_refs": []}},
            "runtime_status": {},
        }
    )
    universal_context = _record(_record(result.get("context_bundle")).get("universal_context"))
    graphiti_recall = _record(_record(result.get("context_bundle")).get("graphiti_recall"))
    memory_context = _record(universal_context.get("memory_context"))
    recalled = _records(memory_context.get("recalled_memories"))
    stale_hints = _records(memory_context.get("stale_memory_hints"))
    audit = _record(universal_context.get("retrieval_audit"))
    selected = _records(audit.get("selected"))
    excluded = _records(audit.get("excluded"))
    active_asset_ids = _active_graphiti_asset_ids(recalled)
    recalled_memory_ids = _recalled_memory_ids(recalled)
    stale_hint_asset_ids = [str(item.get("asset_id") or "") for item in stale_hints if str(item.get("asset_id") or "")]
    excluded_asset_ids = [str(item.get("source_ref") or item.get("asset_id") or "") for item in excluded]
    eval_result = evaluate_context_retrieval(
        {
            "universal_context": universal_context,
        },
        ContextRetrievalEvalCase(
            id="context-retrieval-smoke-work-history",
            query=query,
            expected_refs=[
                ContextRetrievalExpectedRef(kind="employee_work_history", ref="alex"),
                ContextRetrievalExpectedRef(kind="work_ticket", ref=ticket.id),
                ContextRetrievalExpectedRef(kind="work_report", ref=work_report_id),
            ],
        ),
    )
    work_history = _record(_record(universal_context.get("employee_context")).get("work_history"))
    work_history_summary = _record(work_history.get("summary"))
    work_history_eval = eval_result.model_dump(mode="json")
    checks = [
        _check("graphiti.status", graphiti_recall.get("status"), "ready"),
        _check_int("graphiti.result_count", graphiti_recall.get("graphiti_result_count"), 1),
        _check_int("graphiti.excluded_result_count", graphiti_recall.get("graphiti_excluded_result_count"), 2),
        _check("work_history.eval_recall", eval_result.recall, 1.0),
        _check("work_history.missing_refs", eval_result.missing_refs, []),
        _check_int_at_least("work_history.report_count", work_history_summary.get("report_count"), 1),
        _check_list("active.asset_ids", active_asset_ids, ["asset-graphiti-context-solution"]),
        _check_contains("stale_hint.asset_ids", stale_hint_asset_ids, "asset-graphiti-stale-solution"),
        _check_contains("stale_hint.asset_ids", stale_hint_asset_ids, "asset-graphiti-conflicted-solution"),
        _check_absent("wrong_ticket.active", active_asset_ids, "asset-wrong-ticket-solution"),
        _check_absent("wrong_ticket.stale_hint", stale_hint_asset_ids, "asset-wrong-ticket-solution"),
        _check_contains("audit.selected", [str(item.get("source_ref") or "") for item in selected], "asset-graphiti-context-solution"),
        _check_contains("audit.excluded", excluded_asset_ids, "asset-graphiti-stale-solution"),
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "workspace_dir": str(workspace_root),
        "checks": checks,
        "summary": {
            "ticket_id": ticket.id,
            "query": query,
            "graphiti_result_count": int(graphiti_recall.get("graphiti_result_count") or 0),
            "graphiti_excluded_result_count": int(graphiti_recall.get("graphiti_excluded_result_count") or 0),
            "active_asset_ids": active_asset_ids,
            "recalled_memory_ids": recalled_memory_ids,
            "stale_hint_asset_ids": stale_hint_asset_ids,
            "excluded_asset_ids": excluded_asset_ids,
            "wrong_ticket_filtered": "asset-wrong-ticket-solution" not in active_asset_ids + stale_hint_asset_ids,
            "work_history": {
                "employee_id": "alex",
                "report_id": work_report_id,
                "report_count": int(work_history_summary.get("report_count") or 0),
                "current_ticket_count": int(work_history_summary.get("current_ticket_count") or 0),
                "eval_recall": eval_result.recall,
                "eval_precision_like": eval_result.precision_like,
                "matched_refs": work_history_eval["matched_refs"],
                "missing_refs": work_history_eval["missing_refs"],
                "retrieved_refs": [
                    ref
                    for ref in work_history_eval["retrieved_refs"]
                    if ref["kind"] in {"employee_work_history", "work_ticket", "work_report"}
                ],
            },
            "provider_blocker_count": len(_records(result.get("provider_blockers"))),
        },
    }


class _FakeEpisodeType:
    message = "message"
    text = "text"


class _FakeSearchResult:
    def __init__(
        self,
        *,
        asset_id: str,
        ticket_id: str,
        episode_uuid: str,
        fact: str,
        status: str = "approved",
        superseded_by: str = "",
    ) -> None:
        self.uuid = f"graphiti-result-{asset_id}"
        self.source_node_uuid = self.uuid
        self.episode_uuid = episode_uuid
        self.fact = fact
        self.score = 0.97
        self.provenance = {
            "asset_id": asset_id,
            "asset_type": "solution",
            "asset_status": status,
            "source_ticket_id": ticket_id,
            "source_employee_id": "alex",
            "source_run_id": "run-context-retrieval-smoke",
            "source_report_id": "report-context-retrieval-smoke",
            "evidence_id": "evidence-context-retrieval-smoke",
            "source_ref": asset_id,
            "source_kind": "ticket_closeout_solution",
            "scope": {"kind": "ticket", "ref": ticket_id},
            "superseded_by_candidate_id": superseded_by,
        }


def _fake_graphiti_for_ticket(ticket_id: str):
    class FakeGraphiti:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def search(self, query, **kwargs):
            return [
                _FakeSearchResult(
                    asset_id="asset-wrong-ticket-solution",
                    ticket_id="rd-wrong-ticket",
                    episode_uuid="episode-wrong-ticket",
                    fact="Wrong Ticket Graphiti auth recovery solution should be filtered out.",
                ),
                _FakeSearchResult(
                    asset_id="asset-graphiti-stale-solution",
                    ticket_id=ticket_id,
                    episode_uuid="episode-graphiti-stale-solution",
                    fact="Stale Graphiti context solution should become an excluded stale hint.",
                    status="stale",
                    superseded_by="asset-graphiti-context-solution",
                ),
                _FakeSearchResult(
                    asset_id="asset-graphiti-conflicted-solution",
                    ticket_id=ticket_id,
                    episode_uuid="episode-graphiti-conflicted-solution",
                    fact="Conflicted Graphiti context solution should become an excluded conflict hint.",
                    status="conflicted",
                ),
                _FakeSearchResult(
                    asset_id="asset-graphiti-context-solution",
                    ticket_id=ticket_id,
                    episode_uuid="episode-graphiti-context-solution",
                    fact="Graphiti-backed context solution: align Neo4j password env and rerun provider dogfood.",
                ),
            ]

        async def close(self):
            return None

    return FakeGraphiti


def _employee() -> dict[str, Any]:
    return {
        "id": "alex",
        "display_name": "Alex",
        "role": "AI RD / Implementer",
        "summary": "Runtime implementation owner.",
        "skills": ["backend-runtime"],
        "skill_titles": ["Backend Runtime"],
        "permissions": ["repo:read"],
    }


def _employee_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": "alex",
            "display_name": "Alex",
            "role": "AI RD / Implementer",
            "summary": "Runtime implementation owner.",
            "skills": ["backend-runtime"],
            "capability_tags": ["backend", "runtime"],
            "personality_tags": ["precise", "evidence-oriented"],
            "permissions": ["repo:read"],
            "memory_scopes": ["ticket", "project"],
            "current_load": {"active_ticket_count": 1, "status": "available"},
        }
    ]


def _check(name: str, actual: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": expected, "passed": actual == expected}


def _check_int(name: str, actual: Any, expected: int) -> dict[str, Any]:
    try:
        normalized = int(actual)
    except (TypeError, ValueError):
        normalized = -1
    return _check(name, normalized, expected)


def _check_int_at_least(name: str, actual: Any, expected_min: int) -> dict[str, Any]:
    try:
        normalized = int(actual)
    except (TypeError, ValueError):
        normalized = -1
    return {
        "name": name,
        "actual": normalized,
        "expected": f">={expected_min}",
        "passed": normalized >= expected_min,
    }


def _check_list(name: str, actual: list[str], expected: list[str]) -> dict[str, Any]:
    return _check(name, actual, expected)


def _check_contains(name: str, actual: list[str], expected: str) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": expected, "passed": expected in actual}


def _check_absent(name: str, actual: list[str], expected: str) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": f"absent:{expected}", "passed": expected not in actual}


def _active_graphiti_asset_ids(recalled: list[dict[str, Any]]) -> list[str]:
    return _unique_strings(
        str(item.get("asset_id") or item.get("memory_id") or "")
        for item in recalled
        if item.get("graphiti_recalled") is True or str(item.get("source") or "") == "graphiti"
    )


def _recalled_memory_ids(recalled: list[dict[str, Any]]) -> list[str]:
    return _unique_strings(
        str(item.get("memory_id") or item.get("asset_id") or "")
        for item in recalled
        if not (item.get("graphiti_recalled") is True or str(item.get("source") or "") == "graphiti")
    )


def _unique_strings(values) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _write_output(payload: dict[str, Any], output: str) -> None:
    if not output:
        return
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
