from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from aiteamos_api.read import memory_service
from aiteamos_api.agents.workbench.nodes.context import retrieve_context
from aiteamos_api.read.asset_candidate_service import (
    AssetRecord,
    TicketCloseoutSettlementRequest,
    list_asset_records,
    settle_ticket_closeout_assets,
    upsert_asset_record,
)
from aiteamos_api.read.context_retrieval_eval_service import (
    ContextRetrievalEvalCase,
    ContextRetrievalExpectedRef,
    evaluate_context_retrieval,
)
from aiteamos_api.read.execution_context_service import ExecutionContextService
from aiteamos_api.read.memory_service import (
    MemoryCandidateCreateRequest,
    MemoryCandidateReviewRequest,
    approve_memory_candidate,
    create_memory_candidate,
    review_memory_candidate,
)
from aiteamos_api.read.ticket_service import (
    TicketBackendSettingsUpdateRequest,
    TicketCreateRequest,
    TicketReportRequest,
    TicketStateTransitionRequest,
    add_ticket_report,
    create_ticket,
    transition_ticket_state,
    update_ticket_backend_settings,
)


_SMOKE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "context_retrieval_eval_smoke.py"
_SMOKE_SPEC = importlib.util.spec_from_file_location("context_retrieval_eval_smoke", _SMOKE_SCRIPT)
assert _SMOKE_SPEC and _SMOKE_SPEC.loader
_SMOKE_MODULE = importlib.util.module_from_spec(_SMOKE_SPEC)
_SMOKE_SPEC.loader.exec_module(_SMOKE_MODULE)


def _use_local_ticket_backend() -> None:
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )


def _employee() -> dict:
    return {
        "id": "alex",
        "display_name": "Alex",
        "role": "AI RD / Implementer",
        "summary": "Runtime implementation owner.",
        "skills": ["backend-runtime"],
        "skill_titles": ["Backend Runtime"],
        "permissions": ["repo:read"],
    }


def _employee_profiles() -> list[dict]:
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
        },
        {
            "id": "clara",
            "display_name": "Clara",
            "role": "AI Team OS Manager",
            "summary": "Team coordinator.",
            "skills": ["team-ops"],
            "capability_tags": ["governance"],
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
    ]


def test_context_retrieval_smoke_separates_graphiti_assets_from_file_memories() -> None:
    recalled = [
        {
            "memory_id": "asset-graphiti-context-solution",
            "asset_id": "asset-graphiti-context-solution",
            "source": "graphiti",
            "graphiti_recalled": True,
        },
        {
            "memory_id": "mem-context-retrieval-note",
            "asset_id": "mem-context-retrieval-note",
            "source": "file",
            "graphiti_recalled": False,
        },
        {
            "memory_id": "mem-context-retrieval-note",
            "asset_id": "mem-context-retrieval-note",
            "source": "file",
            "graphiti_recalled": False,
        },
    ]

    assert _SMOKE_MODULE._active_graphiti_asset_ids(recalled) == ["asset-graphiti-context-solution"]
    assert _SMOKE_MODULE._recalled_memory_ids(recalled) == ["mem-context-retrieval-note"]


@pytest.mark.asyncio
async def test_workbench_context_node_recalls_graphiti_scoped_asset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_ENABLED", "true")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_URI", "bolt://localhost:7687")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_USER", "neo4j")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Graphiti-backed context recall Ticket",
            description="Recall an approved Graphiti projected solution through the LangGraph context node.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeSearchResult:
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
                "source_run_id": "run-graphiti-context",
                "source_report_id": "report-graphiti-context",
                "evidence_id": "evidence-graphiti-context",
                "source_ref": asset_id,
                "source_kind": "ticket_closeout_solution",
                "scope": {"kind": "ticket", "ref": ticket_id},
                "superseded_by_candidate_id": superseded_by,
            }

    class FakeGraphiti:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def search(self, query, **kwargs):
            return [
                FakeSearchResult(
                    asset_id="asset-wrong-ticket-solution",
                    ticket_id="rd-wrong-ticket",
                    episode_uuid="episode-wrong-ticket",
                    fact="Wrong Ticket Graphiti auth recovery solution should be filtered out.",
                ),
                FakeSearchResult(
                    asset_id="asset-graphiti-stale-solution",
                    ticket_id=ticket.id,
                    episode_uuid="episode-graphiti-stale-solution",
                    fact="Stale Graphiti context solution should be shown only as an excluded stale hint.",
                    status="stale",
                    superseded_by="asset-graphiti-context-solution",
                ),
                FakeSearchResult(
                    asset_id="asset-graphiti-conflicted-solution",
                    ticket_id=ticket.id,
                    episode_uuid="episode-graphiti-conflicted-solution",
                    fact="Conflicted Graphiti context solution should be shown only as an excluded conflict hint.",
                    status="conflicted",
                ),
                FakeSearchResult(
                    asset_id="asset-graphiti-context-solution",
                    ticket_id=ticket.id,
                    episode_uuid="episode-graphiti-context-solution",
                    fact="Graphiti-backed context solution: align Neo4j password env and rerun provider dogfood.",
                ),
            ]

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)

    query = "Graphiti context Neo4j password provider dogfood"
    state = {
        "messages": [HumanMessage(content=query)],
        "selected_employee": _employee(),
        "employee_profiles": _employee_profiles(),
        "ticket_key": ticket.id,
        "ticket_keys": [ticket.id],
        "selected_ai_engine": "deepseek",
        "context_bundle": {"initial_context_assets": {"memory_refs": []}},
        "runtime_status": {},
    }

    result = await retrieve_context(state)

    universal_context = result["context_bundle"]["universal_context"]
    graphiti_recall = result["context_bundle"]["graphiti_recall"]
    recalled = universal_context["memory_context"]["recalled_memories"]
    stale_hints = universal_context["memory_context"]["stale_memory_hints"]
    audit = universal_context["retrieval_audit"]

    assert graphiti_recall["graphiti_result_count"] == 1
    assert graphiti_recall["graphiti_excluded_result_count"] == 2
    assert graphiti_recall["backend"]["status"] == "ready"
    assert result["runtime_status"]["graphiti_recall_count"] == 1
    assert not any(item.get("reason") == "graphiti_recall_not_ready" for item in result["provider_blockers"])
    assert len(recalled) == 1
    assert recalled[0]["asset_id"] == "asset-graphiti-context-solution"
    assert recalled[0]["graphiti_recalled"] is True
    assert recalled[0]["graphiti_episode_id"] == "episode-graphiti-context-solution"
    assert "Neo4j password env" in recalled[0]["content"]
    assert recalled[0]["provenance"]["source_ticket_id"] == ticket.id
    assert not any(item["asset_id"] == "asset-wrong-ticket-solution" for item in recalled)
    assert {item["asset_id"] for item in stale_hints} == {
        "asset-graphiti-stale-solution",
        "asset-graphiti-conflicted-solution",
    }
    stale_hint = next(item for item in stale_hints if item["asset_id"] == "asset-graphiti-stale-solution")
    conflict_hint = next(item for item in stale_hints if item["asset_id"] == "asset-graphiti-conflicted-solution")
    assert stale_hint["superseded_by_candidate_id"] == "asset-graphiti-context-solution"
    assert stale_hint["graphiti_episode_id"] == "episode-graphiti-stale-solution"
    assert "stale" in stale_hint["exclusion_reason"]
    assert "conflicted" in conflict_hint["exclusion_reason"]
    assert not any(item["asset_id"] == "asset-wrong-ticket-solution" for item in stale_hints)
    assert any(
        item["kind"] == "memory"
        and item["source_ref"] == "asset-graphiti-context-solution"
        and "Graphiti recalled" in item["reason"]
        for item in audit["selected"]
    )
    assert any(
        item["kind"] == "memory"
        and item["source_ref"] == "asset-graphiti-stale-solution"
        and "stale" in item["exclusion_reason"]
        for item in audit["excluded"]
    )


@pytest.mark.asyncio
async def test_context_retrieval_eval_recalls_approved_closeout_solution_asset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Closeout Graphiti auth recovery Ticket",
            description="Document the validated solution for Graphiti auth recovery in external runtime dogfood.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            validation_employee_id="peter",
            validation_role="AI PV",
            source_run_id="run-closeout-retrieval-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content=(
                "Graphiti auth recovery solution: reset the Neo4j password env alignment, wait for the "
                "AuthenticationRateLimit window, then rerun the external runtime dogfood smoke."
            ),
            report_type="result",
            evidence=["pytest::closeout-retrieval::result"],
            source_run_id="run-closeout-retrieval-result",
        ),
    )
    validated = add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="peter",
            reporter_role="AI PV",
            content="Validation passed for Graphiti auth recovery closeout.",
            report_type="validation",
            evidence=["pytest::closeout-retrieval::validation"],
            source_run_id="run-closeout-retrieval-validation",
        ),
    )
    validation_report_id = validated.reports[-1].id
    transition_ticket_state(
        ticket.id,
        TicketStateTransitionRequest(
            status="validated",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            source_run_id="run-closeout-retrieval-validated",
        ),
    )
    settlement = await settle_ticket_closeout_assets(
        ticket.id,
        TicketCloseoutSettlementRequest(
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reviewer_employee_id="clara",
            reason="Approve validated closeout solution for retrieval eval.",
            approve_candidates=True,
            project_graphiti=False,
            asset_types=["solution"],
        ),
        workspace_dir=tmp_path,
    )
    solution_asset = next(record for record in list_asset_records(workspace_dir=tmp_path) if record.asset_type == "solution")
    query = "Graphiti auth recovery AuthenticationRateLimit external runtime dogfood"

    context = ExecutionContextService().build(
        message=query,
        employee=_employee(),
        employee_profiles=_employee_profiles(),
        recent_messages=[],
        ticket_keys=[ticket.id],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )
    universal_context = context.universal_context
    relevant_assets = universal_context["asset_context"]["relevant_assets"]
    audit = universal_context["retrieval_audit"]

    assert settlement.status == "approved"
    assert settlement.asset_ids == [solution_asset.id]
    assert settlement.review is not None
    assert settlement.review.reviewed_count == 1
    assert universal_context["summary"]["ticket_id"] == ticket.id
    assert universal_context["summary"]["relevant_asset_count"] >= 1
    assert any(item["asset_id"] == solution_asset.id for item in relevant_assets)
    selected_asset = next(item for item in relevant_assets if item["asset_id"] == solution_asset.id)
    assert selected_asset["asset_type"] == "solution"
    assert selected_asset["status"] == "approved"
    assert selected_asset["provenance"]["source_ticket_id"] == ticket.id
    assert validation_report_id in selected_asset["provenance"]["report_ids"]
    assert selected_asset["provenance"]["source_asset_candidate_id"].startswith("asset-candidate-ticket-solution-")
    assert any(
        item["kind"] == "asset"
        and item["source_ref"] == solution_asset.id
        and item["reason"] == "Ticket-scoped approved Asset"
        for item in audit["selected"]
    )

    result = evaluate_context_retrieval(
        context,
        ContextRetrievalEvalCase(
            id="closeout-graphiti-auth-recovery-solution",
            query=query,
            expected_refs=[
                ContextRetrievalExpectedRef(kind="employee", ref="alex"),
                ContextRetrievalExpectedRef(kind="ticket", ref=ticket.id),
                ContextRetrievalExpectedRef(kind="asset", ref=solution_asset.id),
                ContextRetrievalExpectedRef(kind="evidence", ref=validation_report_id),
            ],
        ),
    )

    assert result.recall == 1.0
    assert result.missing_refs == []
    assert result.precision_like > 0
    assert result.audit["schema"] == "context_retrieval_audit.v1"


def test_context_retrieval_eval_scores_employee_work_history_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Employee work history retrieval eval Ticket",
            description="Agent context should retrieve Alex work history from governed Ticket reports.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-work-history-eval-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    updated = add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Work history retrieval eval evidence for Alex runtime implementation.",
            report_type="progress",
            evidence=["pytest::work-history-retrieval::passed"],
            source_run_id="run-work-history-eval-report",
        ),
    )
    report_id = updated.reports[-1].id

    context = ExecutionContextService().build(
        message="Use Alex work history for runtime implementation planning.",
        employee=_employee(),
        employee_profiles=_employee_profiles(),
        recent_messages=[],
        ticket_keys=[ticket.id],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )
    work_history = context.universal_context["employee_context"]["work_history"]
    audit = context.universal_context["retrieval_audit"]

    assert work_history["summary"]["source"] == "employee_work_ledger"
    assert work_history["summary"]["report_count"] == 1
    assert any(item["ticket_id"] == ticket.id for item in work_history["refs"]["current_tickets"])
    assert any(
        item["kind"] == "employee_work_history"
        and item["source_ref"] == "alex"
        and item["reason"] == "Employee Ticket/runtime work ledger"
        for item in audit["selected"]
    )

    result = evaluate_context_retrieval(
        context,
        ContextRetrievalEvalCase(
            id="employee-work-history-runtime-implementation",
            query="Use Alex work history for runtime implementation planning.",
            expected_refs=[
                ContextRetrievalExpectedRef(kind="employee_work_history", ref="alex"),
                ContextRetrievalExpectedRef(kind="work_ticket", ref=ticket.id),
                ContextRetrievalExpectedRef(kind="work_report", ref=report_id),
            ],
        ),
    )

    assert result.recall == 1.0
    assert result.missing_refs == []
    assert {"kind": "employee_work_history", "ref": "alex"} in result.retrieved_refs
    assert {"kind": "work_ticket", "ref": ticket.id} in result.retrieved_refs
    assert {"kind": "work_report", "ref": report_id} in result.retrieved_refs


@pytest.mark.asyncio
async def test_context_retrieval_golden_query_scores_ticket_asset_and_memory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    current = create_ticket(
        TicketCreateRequest(
            title="Parser fallback latency Ticket",
            description="Implement the parser fallback latency playbook.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    related = create_ticket(
        TicketCreateRequest(
            title="Prior parser fallback incident",
            description="Historical parser fallback latency mitigation and root cause notes.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    current = add_ticket_report(
        current.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Validation evidence for parser fallback latency mitigation.",
            evidence=["pytest::parser-fallback-latency::passed"],
            report_type="validation",
            source_run_id="golden-context-run",
        ),
    )
    report_id = current.reports[-1].id

    async def fake_ingest_graphiti(candidate):
        return {"status": "ingested", "episode_id": f"episode-{candidate.id}", "provider": "fake_graphiti"}

    monkeypatch.setattr(memory_service, "_ingest_graphiti", fake_ingest_graphiti)
    memory = create_memory_candidate(
        MemoryCandidateCreateRequest(
            content="Parser fallback latency playbook requires bounded retries and validation evidence.",
            source_kind="ticket_report",
            source_ref=report_id,
            scope_kind="ticket",
            scope_ref=current.id,
            memory_type="solution",
            confidence=0.91,
            employee_ids=["alex"],
            tags=["parser", "fallback", "latency", "playbook"],
            provenance={
                "source_ticket_id": current.id,
                "source_report_id": report_id,
                "source_employee_id": "alex",
                "why_should_be_remembered": "Reusable parser fallback latency solution.",
            },
        )
    )
    approved_memory = await approve_memory_candidate(memory.id)
    stale_memory = create_memory_candidate(
        MemoryCandidateCreateRequest(
            content="parser fallback latency playbook obsolete threshold",
            source_kind="ticket_report",
            source_ref=report_id,
            scope_kind="ticket",
            scope_ref=current.id,
            memory_type="solution",
            confidence=0.4,
            employee_ids=["alex"],
            tags=["parser", "fallback", "latency", "playbook"],
            provenance={
                "source_ticket_id": current.id,
                "source_report_id": report_id,
                "source_employee_id": "alex",
            },
        )
    )
    stale_memory = review_memory_candidate(
        stale_memory.id,
        MemoryCandidateReviewRequest(
            status="stale",
            reason="Obsolete parser fallback latency threshold was replaced by the approved playbook.",
            actor_employee_id="clara",
        ),
    )

    timestamp = datetime.now(UTC).isoformat()
    asset = upsert_asset_record(
        AssetRecord(
            id="asset-parser-fallback-playbook",
            asset_type="solution",
            title="Parser fallback latency playbook",
            content="Use bounded retries, validation evidence, and Ticket closeout for parser fallback latency work.",
            status="approved",
            scope_kind="ticket",
            scope_ref=current.id,
            owner_employee_id="alex",
            source_kind="ticket_report",
            source_ref=report_id,
            provenance={
                "source_ticket_id": current.id,
                "source_report_id": report_id,
                "source_employee_id": "alex",
            },
            relationships=[
                {"type": "supported_by_report", "target_kind": "ticket_report", "target_ref": report_id},
            ],
            created_at=timestamp,
            updated_at=timestamp,
        ),
        workspace_dir=tmp_path,
    )

    query = "parser fallback latency playbook"
    context = ExecutionContextService().build(
        message=query,
        employee=_employee(),
        employee_profiles=_employee_profiles(),
        recent_messages=[],
        ticket_keys=[current.id],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )
    universal_context = context.universal_context
    audit = universal_context["retrieval_audit"]
    selected_refs = {(item["kind"], item["source_ref"]) for item in audit["selected"]}

    assert universal_context["summary"]["ticket_id"] == current.id
    assert universal_context["summary"]["related_ticket_count"] >= 1
    assert universal_context["summary"]["relevant_asset_count"] >= 1
    assert universal_context["summary"]["recalled_memory_count"] >= 1
    assert ("asset", asset.id) in selected_refs
    assert ("memory", approved_memory.id) in selected_refs
    assert any(item["ticket_id"] == related.id for item in universal_context["ticket_context"]["related_tickets"])
    assert any(item["asset_id"] == asset.id for item in universal_context["asset_context"]["relevant_assets"])
    assert any(item["memory_id"] == approved_memory.id for item in universal_context["memory_context"]["recalled_memories"])
    assert not any(item["memory_id"] == stale_memory.id for item in universal_context["memory_context"]["recalled_memories"])
    assert any(item["memory_id"] == stale_memory.id for item in universal_context["memory_context"]["stale_memory_hints"])
    assert any(item["report_id"] == report_id for item in universal_context["ticket_context"]["prior_evidence"])
    assert any(
        item["kind"] == "memory"
        and item["source_ref"] == stale_memory.id
        and "Obsolete parser fallback" in item["exclusion_reason"]
        for item in audit["excluded"]
    )
    assert all("provenance" in item and item["source_confidence"] > 0 for item in universal_context["asset_context"]["relevant_assets"])
    assert all("provenance" in item and item["source_confidence"] > 0 for item in universal_context["memory_context"]["recalled_memories"])

    result = evaluate_context_retrieval(
        context,
        ContextRetrievalEvalCase(
            id="parser-fallback-latency",
            query=query,
            expected_refs=[
                ContextRetrievalExpectedRef(kind="employee", ref="alex"),
                ContextRetrievalExpectedRef(kind="ticket", ref=current.id),
                ContextRetrievalExpectedRef(kind="related_ticket", ref=related.id),
                ContextRetrievalExpectedRef(kind="asset", ref=asset.id),
                ContextRetrievalExpectedRef(kind="memory", ref=approved_memory.id),
                ContextRetrievalExpectedRef(kind="evidence", ref=report_id),
            ],
        ),
    )

    assert result.recall == 1.0
    assert result.missing_refs == []
    assert result.precision_like > 0
    assert result.audit["schema"] == "context_retrieval_audit.v1"


def test_context_retrieval_uses_asset_relationships_as_conflict_hints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Asset relationship conflict Ticket",
            description="Use approved Asset relationships to avoid stale runtime guidance.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    timestamp = datetime.now(UTC).isoformat()
    old_asset = upsert_asset_record(
        AssetRecord(
            id="asset-runtime-old-guidance",
            asset_type="solution",
            title="Old runtime guidance",
            content="Old runtime guidance should be superseded by newer governed guidance.",
            status="approved",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="ticket_report",
            source_ref="report-runtime-old-guidance",
            provenance={
                "source_ticket_id": ticket.id,
                "source_report_id": "report-runtime-old-guidance",
                "source_employee_id": "alex",
            },
            created_at=timestamp,
            updated_at=timestamp,
        ),
        workspace_dir=tmp_path,
    )
    conflicting_asset = upsert_asset_record(
        AssetRecord(
            id="asset-runtime-conflicting-guidance",
            asset_type="solution",
            title="Conflicting runtime guidance",
            content="Conflicting runtime guidance should be excluded as a conflict hint.",
            status="approved",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="ticket_report",
            source_ref="report-runtime-conflicting-guidance",
            provenance={
                "source_ticket_id": ticket.id,
                "source_report_id": "report-runtime-conflicting-guidance",
                "source_employee_id": "alex",
            },
            created_at=timestamp,
            updated_at=timestamp,
        ),
        workspace_dir=tmp_path,
    )
    new_asset = upsert_asset_record(
        AssetRecord(
            id="asset-runtime-new-guidance",
            asset_type="solution",
            title="New runtime guidance",
            content="New governed runtime guidance should be active context.",
            status="approved",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="ticket_report",
            source_ref="report-runtime-new-guidance",
            provenance={
                "source_ticket_id": ticket.id,
                "source_report_id": "report-runtime-new-guidance",
                "source_employee_id": "alex",
            },
            relationships=[
                {
                    "type": "supersedes",
                    "target_asset_id": old_asset.id,
                    "reason": "New governed runtime guidance supersedes the old guidance.",
                    "confidence": 0.94,
                },
                {
                    "type": "conflicts_with",
                    "target_asset_id": conflicting_asset.id,
                    "reason": "New governed runtime guidance conflicts with the prior risky guidance.",
                    "confidence": 0.88,
                },
            ],
            created_at=timestamp,
            updated_at=timestamp,
        ),
        workspace_dir=tmp_path,
    )

    context = ExecutionContextService().build(
        message="runtime guidance governed stale conflict",
        employee=_employee(),
        employee_profiles=_employee_profiles(),
        recent_messages=[],
        ticket_keys=[ticket.id],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )
    asset_context = context.universal_context["asset_context"]
    relevant_assets = asset_context["relevant_assets"]
    relationship_hints = asset_context["relationship_hints"]
    audit = context.universal_context["retrieval_audit"]

    active_asset_ids = {item["asset_id"] for item in relevant_assets}
    assert new_asset.id in active_asset_ids
    assert old_asset.id not in active_asset_ids
    assert conflicting_asset.id not in active_asset_ids
    assert context.universal_context["summary"]["asset_relationship_hint_count"] == 2
    hints_by_target = {item["target_asset_id"]: item for item in relationship_hints}
    assert hints_by_target[old_asset.id]["status"] == "superseded"
    assert hints_by_target[old_asset.id]["superseded_by_asset_id"] == new_asset.id
    assert "supersedes" in hints_by_target[old_asset.id]["exclusion_reason"]
    assert hints_by_target[conflicting_asset.id]["status"] == "conflicted"
    assert hints_by_target[conflicting_asset.id]["conflicted_by_asset_id"] == new_asset.id
    assert "conflicts" in hints_by_target[conflicting_asset.id]["exclusion_reason"]
    assert any(
        item["kind"] == "asset"
        and item["source_ref"] == old_asset.id
        and "superseded" in item["exclusion_reason"]
        for item in audit["excluded"]
    )
    assert any(
        item["kind"] == "asset"
        and item["source_ref"] == conflicting_asset.id
        and "conflicted" in item["exclusion_reason"]
        for item in audit["excluded"]
    )


def test_context_retrieval_audit_surfaces_exclusion_reasons(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    context = ExecutionContextService().build(
        message="general operating status",
        employee=_employee(),
        employee_profiles=_employee_profiles(),
        recent_messages=[],
        ticket_keys=[],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )

    audit = context.universal_context["retrieval_audit"]
    exclusions = {(item["kind"], item["source_ref"]): item["exclusion_reason"] for item in audit["excluded"]}

    assert audit["schema"] == "context_retrieval_audit.v1"
    assert ("ticket", "current_ticket") in exclusions
    assert ("asset", "ticket_asset_projection") in exclusions
    assert ("memory", "recall_memory_records") in exclusions
    assert context.exclusions == [
        "raw secrets",
        "raw permission authority",
        "raw terminal logs",
        "unrelated global memory dumps",
    ]
