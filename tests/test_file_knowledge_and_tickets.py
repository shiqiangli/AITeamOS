from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read import chat_routes, memory_service, ticket_service


def _command_event(payload: dict, command_id: str, phase: str = "completed") -> dict:
    return next(
        event
        for event in payload["trace_events"]
        if event["event"] == f"command.{phase}"
        and event.get("data", {}).get("command", {}).get("id") == command_id
    )


def _write_employee(path, *, employee_id: str, name: str, role: str) -> None:
    path.write_text(
        f"""
id: {employee_id}
display_name: {name}
kind: ai
role: {role}
summary: {role}
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: {employee_id}
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )


def _ticket_for_evidence_profile(
    *,
    ticket_type: str,
    title: str,
    description: str,
    code_repository_ids: list[str] | None = None,
    knowledge_refs: list[str] | None = None,
) -> ticket_service.Ticket:
    timestamp = "2026-06-07T00:00:00+00:00"
    return ticket_service.Ticket(
        id=f"{ticket_type or 'ops'}-9999",
        title=title,
        description=description,
        ticket_type=ticket_type,
        assigned_employee_id="alex",
        assigned_role="AI RD / Implementer",
        validation_employee_id="peter",
        validation_role="AI PV",
        code_repository_ids=code_repository_ids or [],
        knowledge_refs=knowledge_refs or [],
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_plane_ticket_mapping_table_freezes_phase05_contract():
    assert ticket_service.PLANE_TICKET_MAPPING == {
        "Ticket": "provider record",
        "namespace": "Plane label",
        "Employee": "Plane member mapping or AITeamOS employee_id in comment metadata",
        "assignee": "Plane assignee when mapped, otherwise AITeamOS event projection",
        "report": "Plane comment with AITeamOS metadata",
        "validation": "Plane comment plus AITeamOS validation event projection",
        "state": "Plane state mapping table",
        "evidence": "tagged Plane comment link",
        "asset_link": "AITeamOS asset graph edge plus optional Plane comment backlink",
    }


@pytest.mark.parametrize(
    ("ticket", "expected_profile", "expected_commands"),
    [
        (
            _ticket_for_evidence_profile(
                ticket_type="doc",
                title="Update docs/USER_GUIDE.md",
                description="Document the self-bootstrap operating loop and PRD acceptance.",
                knowledge_refs=["docs/USER_GUIDE.md"],
            ),
            "docs_change",
            ["focused doc/product review evidence"],
        ),
        (
            _ticket_for_evidence_profile(
                ticket_type="rd",
                title="Fix dashboard Ticket evidence checklist",
                description="Frontend React TSX UI change in apps/dashboard.",
            ),
            "frontend_change",
            ["cd apps/dashboard && npm test", "cd apps/dashboard && npm run build"],
        ),
        (
            _ticket_for_evidence_profile(
                ticket_type="rd",
                title="Update FastAPI Ticket service",
                description="Backend Python service change must run pytest.",
                code_repository_ids=["repo-aiteamos"],
            ),
            "backend_change",
            ["pytest"],
        ),
        (
            _ticket_for_evidence_profile(
                ticket_type="ops",
                title="Plane Graphiti adapter smoke",
                description="Integration smoke for Plane and Graphiti adapter behavior.",
            ),
            "integration_change",
            ["pytest focused integration smoke", "pytest"],
        ),
        (
            _ticket_for_evidence_profile(
                ticket_type="ops",
                title="Tune AI Engine prompt contract",
                description="Model prompt change for DeepSeek and OpenAI action-plan behavior.",
            ),
            "model_prompt_change",
            ["focused Chat / AI Engine smoke"],
        ),
    ],
)
def test_phase5_evidence_requirement_profiles_cover_ticket_types(
    ticket: ticket_service.Ticket,
    expected_profile: str,
    expected_commands: list[str],
):
    requirements = ticket_service._ticket_evidence_requirements_from_ticket(ticket)

    assert requirements.profile == expected_profile
    assert requirements.satisfied is False
    assert requirements.missing_required == [f"{expected_profile}:validation_evidence"]
    assert requirements.requirements[0].id == f"{expected_profile}:validation_evidence"
    assert requirements.requirements[0].required is True
    assert requirements.requirements[0].recommended_commands == expected_commands

    satisfied = ticket_service._ticket_evidence_requirements_from_ticket(ticket, pending_evidence=["focused smoke passed"])
    assert satisfied.profile == expected_profile
    assert satisfied.satisfied is True
    assert satisfied.missing_required == []
    assert satisfied.evidence_refs == ["focused smoke passed"]


def test_general_ticket_evidence_requirement_is_optional():
    ticket = _ticket_for_evidence_profile(
        ticket_type="ops",
        title="Plan next self-bootstrap batch",
        description="Clarify owners and scope before creating implementation Tickets.",
    )

    requirements = ticket_service._ticket_evidence_requirements_from_ticket(ticket)

    assert requirements.profile == "general"
    assert requirements.satisfied is True
    assert requirements.missing_required == []
    assert requirements.requirements[0].required is False


def test_self_bootstrap_next_action_treats_stale_candidates_as_governed():
    stale_candidate_action = ticket_service._self_bootstrap_next_learning_action(
        missing_required_evidence=0,
        blocked_or_failed=False,
        memory_candidates=1,
        approved_memory_candidates=0,
        pending_memory_candidates=0,
        approved_memories_recalled=0,
        useful_memory_recalls=0,
        validation_passed=True,
    )
    pending_candidate_action = ticket_service._self_bootstrap_next_learning_action(
        missing_required_evidence=0,
        blocked_or_failed=False,
        memory_candidates=1,
        approved_memory_candidates=0,
        pending_memory_candidates=1,
        approved_memories_recalled=0,
        useful_memory_recalls=0,
        validation_passed=True,
    )

    assert "Post Clara learning summary" in stale_candidate_action
    assert "Review generated Memory candidates" in pending_candidate_action


def test_knowledge_routes_search_docs_memories_and_decisions(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    (workspace / "PRODUCT_DIRECTION.md").write_text(
        "# Product Direction\n\nAITeamOS uses Clara as control-plane manager.\n",
        encoding="utf-8",
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-knowledge-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeGraphiti:
        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            return FakeAddResult()

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)

    client = TestClient(create_app())
    settings = client.put(
        "/api/v1/memory/graphiti/settings",
        json={
            "enabled": True,
            "graph_database": "neo4j",
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "group_id": "aiteamos-test",
            "llm_ai_engine": "openai",
        },
    )
    assert settings.status_code == 200

    docs = client.get("/api/v1/knowledge/docs")
    assert docs.status_code == 200
    assert docs.json()[0]["path"] == "PRODUCT_DIRECTION.md"

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "Clara should delegate repo inspection to RD employees.",
            "source_kind": "manual",
            "scope_kind": "project",
            "scope_ref": "aiteamos",
            "employee_ids": ["clara"],
        },
    )
    assert candidate.status_code == 200
    approved = client.post(f"/api/v1/memory/candidates/{candidate.json()['id']}/approve")
    assert approved.status_code == 200

    decision = client.post(
        "/api/v1/knowledge/decisions",
        json={
            "title": "Clara stays control plane",
            "context": "Clara coordinates employees.",
            "decision": "Clara delegates code Tickets to RD and PV.",
            "consequences": "Clara reads Knowledge, not repository state.",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["saved_path"].startswith(".aiteamos/knowledge/decisions/")

    search = client.get("/api/v1/knowledge/search?q=Clara control-plane delegate")
    assert search.status_code == 200
    source_types = {item["source_type"] for item in search.json()["results"]}
    assert {"doc", "memory", "decision"}.issubset(source_types)

    review = client.get("/api/v1/knowledge/review-queue")
    assert review.status_code == 200
    assert review.json() == []


def test_ticket_routes_create_and_record_reports(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    backend = client.get("/api/v1/tickets/backend")
    assert backend.status_code == 200
    assert backend.json()["mode"] == "plane"

    default_status = client.get("/api/v1/tickets/status")
    assert default_status.status_code == 200
    assert default_status.json()["status"] == "setup_blocked"
    assert default_status.json()["provider"] == "plane"
    assert {"plane_workspace_slug", "plane_project_id", "PLANE_API_KEY"}.issubset(set(default_status.json()["setup_required"]))

    default_create = client.post(
        "/api/v1/tickets",
        json={
            "title": "Should not fall back to local files",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
        },
    )
    assert default_create.status_code == 400
    assert "Plane Ticket Backend setup blocker" in default_create.json()["detail"]
    assert not (workspace / ".aiteamos" / "tickets" / "rd").exists()

    legacy_backend = client.put(
        "/api/v1/tickets/backend",
        json={
            "mode": "local_file",
            "local_file_path": ".aiteamos/tickets/index.json",
        },
    )
    assert legacy_backend.status_code == 200
    assert legacy_backend.json()["mode"] == "local_file"

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Implement Knowledge flow",
            "description": "Create docs, memories, decisions and review queue views.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
            "validation_employee_id": "peter",
            "validation_role": "AI PV",
            "knowledge_refs": ["doc:product-direction"],
            "code_repository_ids": ["repo-aiteamos"],
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]
    assert ticket_id == "rd-0001"
    assert created.json()["ticket_type"] == "rd"
    assert created.json()["status"] == "assigned"
    assert created.json()["code_repository_ids"] == ["repo-aiteamos"]

    reported = client.post(
        f"/api/v1/tickets/{ticket_id}/reports",
        json={
            "reporter_employee_id": "peter",
            "reporter_role": "AI PV",
            "content": "Validation passed.",
            "report_type": "validation",
            "evidence": ["pytest passed"],
        },
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "validated"
    assert reported.json()["reports"][0]["evidence"] == ["pytest passed"]

    event_file = workspace / ".aiteamos" / "tickets" / "rd" / f"{ticket_id}.ticket.jsonl"
    assert event_file.exists()
    event_lines = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]
    assert [event["type"] for event in event_lines[:3]] == ["created", "assigned", "validation_requested"]

    events = client.get(f"/api/v1/tickets/{ticket_id}/events")
    assert events.status_code == 200
    event_types = [event["type"] for event in events.json()]
    assert "validated" in event_types
    assert "status_changed" in event_types
    assert any(event["type"] == "asset_linked" and event["data"]["target_kind"] == "evidence" for event in events.json())

    peter_work = client.get("/api/v1/tickets/employees/peter/work")
    assert peter_work.status_code == 200
    assert peter_work.json()["contribution"]["validation_count"] == 1
    assert peter_work.json()["validations"][0]["ticket_id"] == ticket_id

    alex_work = client.get("/api/v1/tickets/employees/alex/work")
    assert alex_work.status_code == 200
    assert alex_work.json()["historical_tickets"][0]["ticket_id"] == ticket_id

    ticket_assets = client.get("/api/v1/tickets/assets")
    assert ticket_assets.status_code == 200
    assert {item["kind"] for item in ticket_assets.json()} == {"report", "evidence"}
    assert {item["source_ticket_id"] for item in ticket_assets.json()} == {ticket_id}

    all_assets = client.get("/api/v1/assets")
    assert all_assets.status_code == 200
    evidence_asset = next(item for item in all_assets.json() if item["kind"] == "evidence")
    assert evidence_asset["source_ticket"] == ticket_id
    assert evidence_asset["source_employee"] == "peter"

    knowledge_docs = client.get("/api/v1/assets/knowledge/docs")
    assert knowledge_docs.status_code == 200
    assert all(item["metadata"]["asset_domain"] == "knowledge" for item in knowledge_docs.json())

    forbidden = client.post(
        "/api/v1/tickets",
        json={
            "title": "PV-only namespace",
            "description": "RD employee should not create PV Tickets.",
            "ticket_type": "pv",
            "actor_employee_id": "alex",
            "actor_role": "AI RD / Implementer",
        },
    )
    assert forbidden.status_code == 400
    assert "cannot create pv Tickets" in forbidden.json()["detail"]

    unassigned = client.post(
        "/api/v1/tickets",
        json={
            "title": "Detached work record",
            "description": "A Ticket without an assignee would bypass Clara-led flow.",
            "ticket_type": "rd",
        },
    )
    assert unassigned.status_code == 400
    assert "requires an assignee" in unassigned.json()["detail"]

    status = client.get("/api/v1/tickets/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert status.json()["ticket_count"] == 1

    index = json.loads((workspace / ".aiteamos" / "tickets" / "index.json").read_text(encoding="utf-8"))
    assert index[0]["id"] == ticket_id

    updated_backend = client.put(
        "/api/v1/tickets/backend",
        json={
            "mode": "local_file",
            "local_file_path": "tickets/self-improvement.json",
        },
    )
    assert updated_backend.status_code == 200
    assert updated_backend.json()["local_file_path"] == "tickets/self-improvement.json"


def test_builtin_validation_skills_are_queryable_capability_assets(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    _write_employee(employees_dir / "peter.yaml", employee_id="peter", name="Peter", role="AI PV")
    profile = chat_routes.yaml.safe_load((employees_dir / "peter.yaml").read_text(encoding="utf-8"))
    profile["skills"] = ["evidence-review"]
    (employees_dir / "peter.yaml").write_text(chat_routes.yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    client = TestClient(create_app())
    skills = client.get("/api/v1/assets/capabilities/skills")

    assert skills.status_code == 200
    skills_by_id = {item["id"]: item for item in skills.json()}
    assert {
        "validation-strategy",
        "evidence-review",
        "regression-check",
        "product-model-review",
    }.issubset(skills_by_id)
    evidence_review = skills_by_id["evidence-review"]
    assert evidence_review["assigned_employees"] == ["peter"]
    assert evidence_review["metadata"]["asset_domain"] == "capabilities"
    assert evidence_review["metadata"]["asset_type"] == "skills"
    assert evidence_review["metadata"]["source"] == "builtin"
    assert evidence_review["metadata"]["phase"] == "phase5_validation"
    assert evidence_review["metadata"]["source_ref"] == "aiteamos://builtin/validation-skills/evidence-review"

    searched = client.get("/api/v1/assets/capabilities/skills?q=product model")
    assert searched.status_code == 200
    assert {item["id"] for item in searched.json()} == {"product-model-review"}

    local_override_dir = workspace / ".aiteamos" / "skills" / "evidence-review"
    local_override_dir.mkdir(parents=True)
    (local_override_dir / "SKILL.md").write_text("# Local Evidence Review\n\n> Local override.", encoding="utf-8")

    overridden = client.get("/api/v1/assets/capabilities/skills?q=evidence-review")
    assert overridden.status_code == 200
    overridden_items = [item for item in overridden.json() if item["id"] == "evidence-review"]
    assert len(overridden_items) == 1
    assert overridden_items[0]["title"] == "Local Evidence Review"
    assert overridden_items[0]["metadata"]["saved_path"] == ".aiteamos/skills/evidence-review/SKILL.md"


def test_plane_ticket_backend_smoke_create_report_transition(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    calls: list[dict] = []
    provider_state = {"value": "state-assigned"}

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
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "POST" and url.endswith("/work-items/"):
                return FakePlaneResponse(
                    201,
                    {
                        "id": "plane-ticket-1",
                        "project": "plane-project-1",
                        "sequence_id": 42,
                        "state": "state-assigned",
                    },
                )
            if method == "GET" and url.endswith("/work-items/plane-ticket-1/"):
                return FakePlaneResponse(
                    200,
                    {
                        "id": "plane-ticket-1",
                        "project": "plane-project-1",
                        "state": {
                            "id": provider_state["value"],
                            "name": "Assigned" if provider_state["value"] == "state-assigned" else "In Review",
                        },
                    },
                )
            if method == "POST" and url.endswith("/work-items/plane-ticket-1/comments/"):
                return FakePlaneResponse(201, {"id": "plane-comment-1"})
            if method == "PATCH" and url.endswith("/work-items/plane-ticket-1/"):
                provider_state["value"] = json["state"]
                return FakePlaneResponse(
                    200,
                    {
                        "id": "plane-ticket-1",
                        "project": "plane-project-1",
                        "state": {"id": json["state"], "name": "In Review"},
                    },
                )
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

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
            "plane_namespace_label_ids": {"rd": "label-rd"},
            "plane_state_ids": {"assigned": "state-assigned", "in_review": "state-review"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex"},
        },
    )
    assert backend.status_code == 200
    assert backend.json()["mode"] == "plane"

    status = client.get("/api/v1/tickets/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert status.json()["provider"] == "plane"
    assert status.json()["mapping"]["Ticket"] == "provider record"
    assert "request_validation" in status.json()["capabilities"]
    assert "request_human_review" in status.json()["capabilities"]

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Plane-backed Knowledge flow",
            "description": "Create a Plane-backed AITeamOS Ticket.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
            "validation_employee_id": "peter",
            "validation_role": "AI PV",
            "knowledge_refs": ["doc:product-direction"],
            "code_repository_ids": ["repo-aiteamos"],
        },
    )
    assert created.status_code == 200
    ticket = created.json()
    assert ticket["id"] == "rd-0001"
    assert ticket["provider_ref"]["provider"] == "plane"
    assert ticket["provider_ref"]["provider_record_id"] == "plane-ticket-1"
    assert ticket["provider_ref"]["provider_project_id"] == "plane-project-1"
    assert ticket["external_url"].startswith("https://app.plane.test/ait/projects/plane-project-1/work-items/")
    assert ticket["provider_metadata"]["mapping"]["report"] == "Plane comment with AITeamOS metadata"

    create_call = calls[0]
    assert create_call["method"] == "POST"
    assert create_call["url"] == "https://plane.test/api/v1/workspaces/ait/projects/plane-project-1/work-items/"
    assert create_call["headers"]["X-API-Key"] == "plane-test-key"
    assert create_call["json"]["name"] == "Plane-backed Knowledge flow"
    assert create_call["json"]["external_source"] == "aiteamos"
    assert create_call["json"]["external_id"] == "rd-0001"
    assert create_call["json"]["labels"] == ["label-rd"]
    assert create_call["json"]["assignees"] == ["plane-user-alex"]

    detail = client.get("/api/v1/tickets/rd-0001")
    assert detail.status_code == 200
    assert detail.json()["provider_ref"]["provider_record_id"] == "plane-ticket-1"
    assert detail.json()["provider_metadata"]["current_state"]["provider_state_id"] == "state-assigned"
    assert calls[1]["method"] == "GET"

    reported = client.post(
        "/api/v1/tickets/rd-0001/reports",
        json={
            "reporter_employee_id": "alex",
            "reporter_role": "AI RD / Implementer",
            "content": "Implemented the Plane-backed Ticket adapter smoke.",
            "report_type": "progress",
            "evidence": ["pytest focused plane smoke"],
            "source_run_id": "run-plane-report",
        },
    )
    assert reported.status_code == 200
    assert reported.json()["reports"][-1]["content"].startswith("Implemented")
    comment_call = calls[2]
    assert comment_call["method"] == "POST"
    assert comment_call["url"].endswith("/work-items/plane-ticket-1/comments/")
    assert comment_call["json"]["comment_json"]["aiteamos"]["ticket_id"] == "rd-0001"
    assert comment_call["json"]["external_source"] == "aiteamos"

    transitioned = client.post(
        "/api/v1/tickets/rd-0001/state",
        json={
            "status": "in_review",
            "actor_employee_id": "peter",
            "actor_role": "AI PV",
        },
    )
    assert transitioned.status_code == 200
    assert transitioned.json()["status"] == "in_review"
    assert transitioned.json()["provider_metadata"]["current_state"]["provider_state_id"] == "state-review"
    transition_call = calls[3]
    assert transition_call["method"] == "PATCH"
    assert transition_call["url"].endswith("/work-items/plane-ticket-1/")
    assert transition_call["json"] == {"state": "state-review"}

    refreshed = client.get("/api/v1/tickets/rd-0001")
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "in_review"
    assert refreshed.json()["provider_metadata"]["current_state"]["provider_state_id"] == "state-review"

    events = client.get("/api/v1/tickets/rd-0001/events")
    assert events.status_code == 200
    assert any(event["type"] == "status_changed" and event["data"]["provider_ref"]["provider"] == "plane" for event in events.json())

    graph = client.get("/api/v1/tickets/rd-0001/graph")
    assert graph.status_code == 200
    graph_payload = graph.json()
    assert graph_payload["ticket_id"] == "rd-0001"
    node_kinds = {node["kind"] for node in graph_payload["nodes"]}
    assert {"ticket", "employee", "report", "evidence", "repository", "run"}.issubset(node_kinds)
    edge_types = {edge["type"] for edge in graph_payload["edges"]}
    assert {
        "ticket.assigned_to.employee",
        "ticket.validated_by.employee",
        "employee.produced.report",
        "report.belongs_to.ticket",
        "report.has_evidence",
        "ticket.references_repository",
    }.issubset(edge_types)
    assert graph_payload["grouped_edges"]["report.has_evidence"][0]["evidence_refs"] == ["pytest focused plane smoke"]
    assert graph_payload["source_counts"]["reports"] == 1

    performance = client.get("/api/v1/tickets/rd-0001/performance")
    assert performance.status_code == 200
    performance_payload = performance.json()
    assert performance_payload["ticket_id"] == "rd-0001"
    assert performance_payload["source_counts"]["reports"] == 1
    assert performance_payload["source_counts"]["evidence"] == 1
    assert performance_payload["source_counts"]["graph_edges"] >= len(edge_types)
    assert performance_payload["quality_signals"]["has_assignee"] is True
    assert performance_payload["quality_signals"]["has_report"] is True
    assert performance_payload["quality_signals"]["has_evidence"] is True
    assert performance_payload["quality_signals"]["validation_requested"] is True
    assert performance_payload["quality_signals"]["provider_ref_recorded"] is True
    contribution_by_employee = {item["employee_id"]: item for item in performance_payload["contribution"]}
    assert contribution_by_employee["alex"]["assigned"] is True
    assert contribution_by_employee["alex"]["report_count"] == 1
    assert contribution_by_employee["alex"]["evidence_count"] == 1
    assert contribution_by_employee["peter"]["validator"] is True
    assert contribution_by_employee["peter"]["event_count"] == 1

    employee_graph = client.get("/api/v1/employees/alex/graph")
    assert employee_graph.status_code == 200
    employee_graph_payload = employee_graph.json()
    assert employee_graph_payload["employee_id"] == "alex"
    employee_edge_types = {edge["type"] for edge in employee_graph_payload["edges"]}
    assert {
        "ticket.assigned_to.employee",
        "employee.produced.report",
        "report.belongs_to.ticket",
        "report.has_evidence",
        "run.produces.report",
    }.issubset(employee_edge_types)
    assert employee_graph_payload["source_counts"]["tickets"] == 1
    assert employee_graph_payload["source_counts"]["reports"] == 1

    ticket_assets = client.get("/api/v1/tickets/rd-0001/assets")
    assert ticket_assets.status_code == 200
    assert {item["kind"] for item in ticket_assets.json()} == {"report", "evidence"}
    assert {item["source_ticket_id"] for item in ticket_assets.json()} == {"rd-0001"}

    asset_graph_status = client.get("/api/v1/asset-graph/status")
    assert asset_graph_status.status_code == 200
    assert asset_graph_status.json()["status"] == "ready"
    assert asset_graph_status.json()["ticket_count"] == 1
    assert asset_graph_status.json()["asset_record_count"] == 2
    assert "asset_graph_projection" in asset_graph_status.json()["capabilities"]

    plane_projection = workspace / ".aiteamos" / "tickets" / "plane" / "rd" / "rd-0001.ticket.jsonl"
    assert plane_projection.exists()
    assert not (workspace / ".aiteamos" / "tickets" / "rd" / "rd-0001.ticket.jsonl").exists()


def test_ticket_assets_include_approved_memory_recall_usage(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-ticket-asset-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeGraphiti:
        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            return FakeAddResult()

        async def close(self):
            return None

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
            if method == "POST" and url.endswith("/work-items/"):
                return FakePlaneResponse(
                    201,
                    {
                        "id": "plane-ticket-memory-1",
                        "project": "plane-project-1",
                        "sequence_id": 77,
                        "state": "state-assigned",
                    },
                )
            return FakePlaneResponse(404, {"detail": "unexpected call"})

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
            "plane_namespace_label_ids": {"rd": "label-rd"},
            "plane_state_ids": {"assigned": "state-assigned"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex"},
        },
    )
    assert backend.status_code == 200

    graphiti_settings = client.put(
        "/api/v1/memory/graphiti/settings",
        json={
            "enabled": True,
            "graph_database": "neo4j",
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "group_id": "aiteamos-test",
            "llm_ai_engine": "openai",
        },
    )
    assert graphiti_settings.status_code == 200

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Reuse approved memory in follow-up Ticket",
            "description": "Show recalled approved assets in the follow-up Ticket asset projection.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "When self-bootstrap Tickets use Graphiti recall, surface the approved asset on the Ticket.",
            "source_kind": "ticket_summary",
            "source_ref": ".aiteamos/traces/run-prior.jsonl",
            "scope_kind": "ticket",
            "scope_ref": "rd-0000",
            "memory_type": "principle",
            "confidence": 0.92,
            "employee_ids": ["clara"],
            "tags": ["self-bootstrap", "graphiti"],
            "provenance": {
                "source_ticket_id": "rd-0000",
                "source_employee_id": "clara",
                "source_run_id": "run-prior",
                "source_report_id": "report-prior",
                "evidence_id": "evidence-prior",
                "provider_refs": [{"provider": "plane", "provider_record_id": "plane-ticket-prior"}],
            },
        },
    )
    assert candidate.status_code == 200
    approved = client.post(f"/api/v1/memory/candidates/{candidate.json()['id']}/approve")
    assert approved.status_code == 200

    usage_refs = memory_service.record_memory_recall_usage(
        memory_refs=[
            {
                "memory_id": candidate.json()["id"],
                "graphiti_recalled": True,
                "graphiti_episode_id": "episode-ticket-asset-1",
                "graphiti_result_id": "graphiti-result-ticket-asset-1",
                "provenance": {"asset_id": candidate.json()["id"]},
            }
        ],
        run_id="run-followup",
        employee_id="alex",
        ticket_keys=[ticket_id],
        query="Graphiti recall Ticket asset projection",
        trace_path=".aiteamos/traces/run-followup.jsonl",
    )
    assert usage_refs[0]["source_ticket_ids"] == [ticket_id]

    reviewed_usage = client.post(
        f"/api/v1/memory/candidates/{candidate.json()['id']}/usage/{usage_refs[0]['usage_id']}/review",
        json={
            "usefulness_status": "useful",
            "reason": "The recalled Graphiti asset helped Clara explain the follow-up Ticket.",
            "reviewer_employee_id": "peter",
        },
    )
    assert reviewed_usage.status_code == 200

    assets = client.get("/api/v1/tickets/assets")
    assert assets.status_code == 200
    candidate_asset = next(item for item in assets.json() if item["kind"] == "memory_candidate")
    assert candidate_asset["source_ticket_id"] == "rd-0000"
    assert candidate_asset["status"] == "approved"
    assert candidate_asset["metadata"]["memory_id"] == candidate.json()["id"]
    assert candidate_asset["metadata"]["source_run_id"] == "run-prior"
    assert candidate_asset["metadata"]["source_report_id"] == "report-prior"
    memory_asset = next(item for item in assets.json() if item["kind"] == "memory")
    assert memory_asset["source_ticket_id"] == ticket_id
    assert memory_asset["source_employee_id"] == "alex"
    assert memory_asset["status"] == "approved"
    assert memory_asset["metadata"]["memory_id"] == candidate.json()["id"]
    assert memory_asset["metadata"]["source_run_id"] == "run-followup"
    assert memory_asset["metadata"]["source_trace_path"] == ".aiteamos/traces/run-followup.jsonl"
    assert memory_asset["metadata"]["graphiti_episode_id"] == "episode-ticket-asset-1"
    assert memory_asset["metadata"]["graphiti_result_id"] == "graphiti-result-ticket-asset-1"
    assert memory_asset["metadata"]["usefulness_status"] == "useful"
    assert memory_asset["metadata"]["derived_from_ticket_id"] == "rd-0000"
    assert memory_asset["metadata"]["source_report_id"] == "report-prior"
    assert memory_asset["metadata"]["evidence_id"] == "evidence-prior"

    followup_assets = client.get(f"/api/v1/tickets/{ticket_id}/assets")
    assert followup_assets.status_code == 200
    assert [item["kind"] for item in followup_assets.json()] == ["memory"]
    assert followup_assets.json()[0]["metadata"]["usage_id"] == usage_refs[0]["usage_id"]

    performance = client.get(f"/api/v1/tickets/{ticket_id}/performance")
    assert performance.status_code == 200
    performance_payload = performance.json()
    assert performance_payload["source_counts"]["recalled_assets"] == 1
    assert performance_payload["source_counts"]["graphiti_recalled_assets"] == 1
    assert performance_payload["quality_signals"]["used_recalled_asset"] is True
    assert performance_payload["quality_signals"]["graphiti_recall_recorded"] is True
    contribution_by_employee = {item["employee_id"]: item for item in performance_payload["contribution"]}
    assert contribution_by_employee["alex"]["recalled_asset_count"] == 1

    graph = client.get(f"/api/v1/tickets/{ticket_id}/graph")
    assert graph.status_code == 200
    graph_payload = graph.json()
    edge_types = {edge["type"] for edge in graph_payload["edges"]}
    assert "run.recalls_memory" in edge_types
    assert "memory.derived_from.ticket" in edge_types
    assert any(node["kind"] == "asset" and node["metadata"].get("memory_id") == candidate.json()["id"] for node in graph_payload["nodes"])

    bootstrap_summary = client.get("/api/v1/tickets/self-bootstrap/summary")
    assert bootstrap_summary.status_code == 200
    summary_payload = bootstrap_summary.json()
    assert summary_payload["ticket_count"] == 1
    assert summary_payload["memory_candidates_produced"] == 1
    assert summary_payload["approved_memory_candidates"] == 1
    assert summary_payload["approved_memories_recalled"] == 1
    assert summary_payload["graphiti_memories_recalled"] == 1
    assert summary_payload["useful_memory_recalls"] == 1
    assert summary_payload["learning_delta"]["reused_prior_assets"] == 1
    summary_ticket = summary_payload["tickets"][0]
    assert summary_ticket["ticket_id"] == ticket_id
    assert summary_ticket["approved_memories_recalled"] == 1
    assert summary_ticket["graphiti_memories_recalled"] == 1
    assert summary_ticket["useful_memory_recalls"] == 1
    assert summary_ticket["provider_ref_recorded"] is True
    assert summary_ticket["missing_required_evidence"] == 1
    assert "validation evidence" in summary_ticket["next_learning_action"]

    asset_graph = client.get(f"/api/v1/assets/{candidate.json()['id']}/graph")
    assert asset_graph.status_code == 200
    asset_graph_payload = asset_graph.json()
    assert asset_graph_payload["asset_id"] == candidate.json()["id"]
    asset_edge_types = {edge["type"] for edge in asset_graph_payload["edges"]}
    assert {
        "asset.used_by.ticket",
        "memory.derived_from.ticket",
        "run.recalls_memory",
        "run.proposes_memory_candidate",
        "report.supports.asset",
        "evidence.supports.asset",
    }.issubset(asset_edge_types)
    assert asset_graph_payload["source_counts"]["records"] == 2
    assert asset_graph_payload["source_counts"]["tickets"] == 2
    assert asset_graph_payload["source_counts"]["runs"] == 2
    assert any(node["kind"] == "ticket" and node["ref"] == "rd-0000" for node in asset_graph_payload["nodes"])
    assert any(node["kind"] == "ticket" and node["ref"] == ticket_id for node in asset_graph_payload["nodes"])
    assert any(
        edge["type"] == "run.recalls_memory"
        and edge["metadata"].get("usage_id") == usage_refs[0]["usage_id"]
        for edge in asset_graph_payload["edges"]
    )

    asset_graph_status = client.get("/api/v1/asset-graph/status")
    assert asset_graph_status.status_code == 200
    assert asset_graph_status.json()["asset_record_count"] == 2
    assert asset_graph_status.json()["graph_asset_count"] == 1

    alex_analytics = client.get("/api/v1/employees/alex/analytics")
    assert alex_analytics.status_code == 200
    assert alex_analytics.json()["assigned_ticket_count"] == 1
    assert alex_analytics.json()["completed_ticket_count"] == 0
    assert alex_analytics.json()["candidates_produced"] == 0
    assert alex_analytics.json()["recalled_asset_count"] == 1

    clara_analytics = client.get("/api/v1/employees/clara/analytics")
    assert clara_analytics.status_code == 200
    assert clara_analytics.json()["assigned_ticket_count"] == 0
    assert clara_analytics.json()["candidates_produced"] == 1

    analytics_summary = client.get("/api/v1/employees/analytics/summary")
    assert analytics_summary.status_code == 200
    summary_by_employee = {item["employee_id"]: item for item in analytics_summary.json()["employees"]}
    assert summary_by_employee["alex"]["recalled_asset_count"] == 1
    assert summary_by_employee["clara"]["candidates_produced"] == 1


def test_validation_evidence_requirements_block_unproven_code_validation_and_record_failure_rework(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    calls: list[dict] = []

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
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "POST" and url.endswith("/work-items/"):
                return FakePlaneResponse(
                    201,
                    {
                        "id": "plane-ticket-evidence-1",
                        "project": "plane-project-1",
                        "sequence_id": 78,
                        "state": "state-assigned",
                    },
                )
            if method == "POST" and url.endswith("/work-items/plane-ticket-evidence-1/comments/"):
                return FakePlaneResponse(201, {"id": f"plane-comment-{len(calls)}"})
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

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
            "plane_namespace_label_ids": {"rd": "label-rd"},
            "plane_state_ids": {"assigned": "state-assigned"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex"},
        },
    )
    assert backend.status_code == 200

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Backend evidence discipline",
            "description": "Backend code change must not be validated without test or review evidence.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
            "validation_employee_id": "peter",
            "validation_role": "AI PV",
            "code_repository_ids": ["repo-aiteamos"],
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]
    assert ticket_id == "rd-0001"
    assert len(calls) == 1

    requirements = client.get(f"/api/v1/tickets/{ticket_id}/evidence-requirements")
    assert requirements.status_code == 200
    requirements_payload = requirements.json()
    assert requirements_payload["profile"] == "backend_change"
    assert requirements_payload["satisfied"] is False
    assert requirements_payload["missing_required"] == ["backend_change:validation_evidence"]
    assert "pytest" in requirements_payload["requirements"][0]["recommended_commands"]

    blocked_validation = client.post(
        f"/api/v1/tickets/{ticket_id}/reports",
        json={
            "reporter_employee_id": "peter",
            "reporter_role": "AI PV",
            "content": "Validation passed, but no evidence was attached.",
            "report_type": "validation",
        },
    )
    assert blocked_validation.status_code == 400
    assert "Validation evidence blocker" in blocked_validation.json()["detail"]
    assert len(calls) == 1

    failed_validation = client.post(
        f"/api/v1/tickets/{ticket_id}/reports",
        json={
            "reporter_employee_id": "peter",
            "reporter_role": "AI PV",
            "content": "Validation failed; rerun focused tests and attach evidence before approval.",
            "report_type": "validation_failed",
        },
    )
    assert failed_validation.status_code == 200
    assert failed_validation.json()["status"] == "blocked"
    assert failed_validation.json()["reports"][-1]["report_type"] == "validation_failed"
    assert len(calls) == 2

    events = client.get(f"/api/v1/tickets/{ticket_id}/events")
    assert events.status_code == 200
    assert any(event["type"] == "blocked" for event in events.json())
    assert any(event["type"] == "status_changed" and event["data"]["to"] == "blocked" for event in events.json())

    performance = client.get(f"/api/v1/tickets/{ticket_id}/performance")
    assert performance.status_code == 200
    performance_payload = performance.json()
    assert performance_payload["quality_signals"]["blocked_or_failed"] is True
    assert performance_payload["quality_signals"]["missing_evidence"] is True
    assert performance_payload["quality_signals"]["evidence_requirements_satisfied"] is False
    assert performance_payload["quality_signals"]["missing_required_evidence"] == 1


def test_chat_request_validation_uses_phase1_action_plan_and_plane_provider_ref(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    calls: list[dict] = []

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    _write_employee(employees_dir / "clara.yaml", employee_id="clara", name="Clara", role="AI Team OS Manager")
    _write_employee(employees_dir / "alex.yaml", employee_id="alex", name="Alex", role="AI RD / Implementer")
    _write_employee(employees_dir / "peter.yaml", employee_id="peter", name="Peter", role="AI PV")

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
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "POST" and url.endswith("/work-items/"):
                return FakePlaneResponse(
                    201,
                    {
                        "id": "plane-ticket-validation-1",
                        "project": "plane-project-1",
                        "sequence_id": 12,
                        "state": "state-assigned",
                    },
                )
            if method == "POST" and url.endswith("/work-items/plane-ticket-validation-1/comments/"):
                return FakePlaneResponse(201, {"id": "plane-comment-validation-1"})
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

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
            "plane_namespace_label_ids": {"rd": "label-rd"},
            "plane_state_ids": {"assigned": "state-assigned"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex"},
        },
    )
    assert backend.status_code == 200

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Phase 1 validation action",
            "description": "Create a Plane-backed Ticket for validation request smoke.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]

    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": f"Clara，请请求 Peter 验证 {ticket_id}。",
            "thread_id": "phase1-request-validation",
            "target_employee_id": "clara",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "已请求 Ticket 验证" in payload["reply"]
    action_event = next(event for event in payload["trace_events"] if event["event"] == "chat.action_plan.completed")
    assert action_event["data"]["action"] == "request_validation"
    assert action_event["data"]["kernel_command"] == "tickets.manage:request_validation"

    completed = _command_event(payload, "tickets.manage:request_validation")
    ticket = completed["data"]["ticket"]
    assert ticket["id"] == ticket_id
    assert ticket["validation_employee_id"] == "peter"
    assert ticket["provider_ref"]["provider_record_id"] == "plane-ticket-validation-1"
    assert payload["run_metadata"]["provider_refs"][0]["provider_record_id"] == "plane-ticket-validation-1"

    comment_call = calls[1]
    assert comment_call["method"] == "POST"
    assert comment_call["json"]["external_source"] == "aiteamos"
    assert comment_call["json"]["comment_json"]["aiteamos"]["request_type"] == "validation_request"
    assert comment_call["json"]["comment_json"]["aiteamos"]["validation_employee_id"] == "peter"

    events = client.get(f"/api/v1/tickets/{ticket_id}/events")
    assert events.status_code == 200
    validation_event = next(event for event in events.json() if event["type"] == "validation_requested")
    assert validation_event["data"]["provider_ref"]["provider"] == "plane"
    assert validation_event["data"]["provider_metadata"]["provider_comment_id"] == "plane-comment-validation-1"


def test_chat_request_human_review_records_blocker_report_and_plane_ref(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    calls: list[dict] = []

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    _write_employee(employees_dir / "clara.yaml", employee_id="clara", name="Clara", role="AI Team OS Manager")
    _write_employee(employees_dir / "alex.yaml", employee_id="alex", name="Alex", role="AI RD / Implementer")

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
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "POST" and url.endswith("/work-items/"):
                return FakePlaneResponse(
                    201,
                    {
                        "id": "plane-ticket-human-review-1",
                        "project": "plane-project-1",
                        "sequence_id": 14,
                        "state": "state-assigned",
                    },
                )
            if method == "POST" and url.endswith("/work-items/plane-ticket-human-review-1/comments/"):
                return FakePlaneResponse(201, {"id": "plane-comment-human-review-1"})
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

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
            "plane_namespace_label_ids": {"rd": "label-rd"},
            "plane_state_ids": {"assigned": "state-assigned", "blocked": "state-blocked"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex"},
        },
    )
    assert backend.status_code == 200

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Human review action",
            "description": "Create a Plane-backed Ticket for human review smoke.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]

    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": f"Clara，请请求人工复核 {ticket_id}，原因是缺少外部发布授权。",
            "thread_id": "phase5-request-human-review",
            "target_employee_id": "clara",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "已请求 Human Review" in payload["reply"]
    action_event = next(event for event in payload["trace_events"] if event["event"] == "chat.action_plan.completed")
    assert action_event["data"]["action"] == "request_human_review"
    assert action_event["data"]["kernel_command"] == "tickets.manage:request_human_review"

    completed = _command_event(payload, "tickets.manage:request_human_review")
    ticket = completed["data"]["ticket"]
    assert ticket["id"] == ticket_id
    assert ticket["status"] == "blocked"
    assert ticket["reports"][-1]["report_type"] == "human_review_requested"
    assert "缺少外部发布授权" in ticket["reports"][-1]["content"]
    assert payload["run_metadata"]["provider_refs"][0]["provider_record_id"] == "plane-ticket-human-review-1"

    comment_call = calls[1]
    assert comment_call["method"] == "POST"
    assert comment_call["json"]["external_source"] == "aiteamos"
    assert comment_call["json"]["comment_json"]["aiteamos"]["report_type"] == "human_review_requested"
    assert comment_call["json"]["comment_json"]["aiteamos"]["reporter_employee_id"] == "clara"

    events = client.get(f"/api/v1/tickets/{ticket_id}/events")
    assert events.status_code == 200
    blocked_event = next(event for event in events.json() if event["type"] == "blocked")
    assert blocked_event["data"]["report"]["report_type"] == "human_review_requested"
    assert blocked_event["data"]["provider_ref"]["provider"] == "plane"
    assert blocked_event["data"]["provider_metadata"]["provider_comment_id"] == "plane-comment-human-review-1"
    assert any(event["type"] == "status_changed" and event["data"]["to"] == "blocked" for event in events.json())


def test_plane_ticket_backend_setup_blocker_does_not_fallback_to_local_file(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("PLANE_API_KEY", raising=False)

    client = TestClient(create_app())
    backend = client.get("/api/v1/tickets/backend")
    assert backend.status_code == 200
    assert backend.json()["mode"] == "plane"

    status = client.get("/api/v1/tickets/status")
    assert status.status_code == 200
    assert status.json()["status"] == "setup_blocked"
    assert {"plane_workspace_slug", "plane_project_id", "PLANE_API_KEY"}.issubset(set(status.json()["setup_required"]))

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Should block without Plane secret",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
        },
    )
    assert created.status_code == 400
    assert "Plane Ticket Backend setup blocker" in created.json()["detail"]
    assert not (workspace / ".aiteamos" / "tickets" / "rd").exists()


def test_chat_create_ticket_records_plane_provider_ref_in_trace(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    calls: list[dict] = []

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    _write_employee(employees_dir / "clara.yaml", employee_id="clara", name="Clara", role="AI Team OS Manager")
    _write_employee(employees_dir / "alex.yaml", employee_id="alex", name="Alex", role="AI RD / Implementer")
    _write_employee(employees_dir / "peter.yaml", employee_id="peter", name="Peter", role="AI PV")

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
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "POST" and url.endswith("/work-items/"):
                return FakePlaneResponse(
                    201,
                    {
                        "id": "plane-ticket-chat-1",
                        "project": "plane-project-1",
                        "sequence_id": 7,
                        "state": "state-assigned",
                    },
                )
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

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
            "plane_namespace_label_ids": {"rd": "label-rd"},
            "plane_state_ids": {"assigned": "state-assigned"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex"},
        },
    )
    assert backend.status_code == 200

    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请创建 Ticket，交给 Alex 完善 Plane-backed trace smoke，并由 Peter 验证。",
            "thread_id": "plane-chat-smoke",
            "target_employee_id": "clara",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "已创建 Ticket" in payload["reply"]
    assert "已创建本地 Ticket" not in payload["reply"]
    assert "https://app.plane.test/ait/projects/plane-project-1/work-items/" in payload["reply"]

    completed = _command_event(payload, "tickets.manage:create")
    ticket = completed["data"]["ticket"]
    assert ticket["provider_ref"]["provider"] == "plane"
    assert ticket["provider_ref"]["provider_record_id"] == "plane-ticket-chat-1"
    assert ticket["external_url"].startswith("https://app.plane.test/ait/projects/plane-project-1/work-items/")
    assert calls[0]["json"]["external_source"] == "aiteamos"
    assert calls[0]["json"]["external_id"] == ticket["id"]

    provider_refs = payload["run_metadata"]["provider_refs"]
    assert provider_refs[0]["provider"] == "plane"
    assert provider_refs[0]["provider_record_id"] == "plane-ticket-chat-1"

    trace_path = workspace / payload["saved_paths"]["trace"]
    trace_events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    recorded = next(event for event in trace_events if event["event"] == "run.metadata.recorded")
    assert recorded["data"]["provider_refs"][0]["provider_record_id"] == "plane-ticket-chat-1"


def test_clara_can_search_knowledge_and_create_ticket(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")
    calls: list[dict] = []
    (workspace / "PRODUCT_DIRECTION.md").write_text(
        "# Product Direction\n\nKnowledge contains Docs, Memories, Decisions, and Review Queue.\n",
        encoding="utf-8",
    )

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    _write_employee(employees_dir / "clara.yaml", employee_id="clara", name="Clara", role="AI Team OS Manager")
    _write_employee(employees_dir / "alex.yaml", employee_id="alex", name="Alex", role="AI RD / Implementer")
    _write_employee(employees_dir / "peter.yaml", employee_id="peter", name="Peter", role="AI PV")

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for local Knowledge/Ticket tools")

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
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "POST" and url.endswith("/work-items/"):
                return FakePlaneResponse(
                    201,
                    {
                        "id": "plane-ticket-knowledge-1",
                        "project": "plane-project-1",
                        "sequence_id": 11,
                        "state": "state-assigned",
                    },
                )
            if method == "POST" and url.endswith("/work-items/plane-ticket-knowledge-1/comments/"):
                return FakePlaneResponse(201, {"id": "plane-comment-knowledge-1"})
            if method == "GET" and url.endswith("/work-items/plane-ticket-knowledge-1/"):
                return FakePlaneResponse(
                    200,
                    {
                        "id": "plane-ticket-knowledge-1",
                        "project": "plane-project-1",
                        "state": "state-assigned",
                    },
                )
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)
    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

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
            "plane_namespace_label_ids": {"rd": "label-rd"},
            "plane_state_ids": {"assigned": "state-assigned"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex"},
        },
    )
    assert backend.status_code == 200

    repo_dir = workspace / "repo"
    (repo_dir / ".git").mkdir(parents=True)
    (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    tickets_page = repo_dir / "apps" / "dashboard" / "src" / "pages" / "tickets" / "index.tsx"
    tickets_page.parent.mkdir(parents=True)
    tickets_page.write_text(
        "export function TicketsPage() {\n  return <section>Tickets 页面实现 repo context implementation</section>;\n}\n",
        encoding="utf-8",
    )
    repo = client.post(
        "/api/v1/code-repositories",
        json={
            "id": "repo-aiteamos",
            "name": "AITeamOS",
            "provider": "local",
            "location": str(repo_dir),
            "default_branch": "main",
            "plane_workspace_slug": "ait",
            "plane_project_id": "aiteamos",
        },
    )
    assert repo.status_code == 200

    list_repos = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请列出所有代码仓库。",
            "thread_id": "repo-tool-test",
            "target_employee_id": "clara",
        },
    )
    assert list_repos.status_code == 200
    assert "代码仓库" in list_repos.json()["reply"]
    _command_event(list_repos.json(), "repositories.list:list")

    search = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请搜索知识库 Knowledge flow。",
            "thread_id": "knowledge-tool-test",
            "target_employee_id": "clara",
        },
    )
    assert search.status_code == 200
    assert "我搜索了 Knowledge" in search.json()["reply"]
    _command_event(search.json(), "knowledge.search:search")

    create = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请创建 Ticket，交给 Alex 完善 AITeamOS 代码仓库中的 Knowledge flow，并由 Peter 验证。",
            "thread_id": "ticket-tool-test",
            "target_employee_id": "clara",
        },
    )
    assert create.status_code == 200
    payload = create.json()
    assert "已创建 Ticket" in payload["reply"]
    completed = _command_event(payload, "tickets.manage:create")
    ticket = completed["data"]["ticket"]
    assert ticket["id"].startswith("rd-")
    assert ticket["ticket_type"] == "rd"
    assert ticket["assigned_employee_id"] == "alex"
    assert ticket["validation_employee_id"] == "peter"
    assert ticket["knowledge_refs"]
    assert ticket["code_repository_ids"] == ["repo-aiteamos"]
    assert ticket["provider_ref"]["provider_record_id"] == "plane-ticket-knowledge-1"
    assert calls[0]["json"]["external_source"] == "aiteamos"

    inspect = client.post(
        "/api/v1/chat/messages",
        json={
            "message": f"Alex，请检查 {ticket['id']} 里的 Tickets 页面实现。",
            "thread_id": "repo-inspect-tool-test",
            "target_employee_id": "alex",
        },
    )
    assert inspect.status_code == 200
    inspect_payload = inspect.json()
    assert "已检查代码仓库" in inspect_payload["reply"]
    inspect_event = _command_event(inspect_payload, "repositories.inspect:inspect")
    assert inspect_event["data"]["matches"]
    assert inspect_event["data"]["ticket"]["reports"][-1]["report_type"] == "repo_inspection"
    assert inspect_event["data"]["ticket"]["events"][-1]["type"] == "asset_linked"
