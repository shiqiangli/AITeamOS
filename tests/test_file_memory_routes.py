from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read import memory_service, ticket_service


def test_memory_candidate_approval_requires_graphiti_backend(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("AITEAMOS_GRAPHITI_ENABLED", raising=False)
    monkeypatch.delenv("AITEAMOS_GRAPHITI_URI", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)

    client = TestClient(create_app())

    status = client.get("/api/v1/memory/status")
    assert status.status_code == 200
    assert status.json()["backend"]["backend"] == "graphiti"
    assert status.json()["backend"]["status"] == "disabled"
    assert status.json()["candidate_count"] == 0

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "Coding style: keep AITeamOS memory candidates evidence-backed.",
            "source_kind": "decision",
            "source_ref": "DEC-1",
            "scope_kind": "project",
            "scope_ref": "aiteamos",
            "memory_type": "principle",
            "confidence": 0.9,
            "employee_ids": ["clara"],
            "tags": ["coding-style"],
        },
    )
    assert candidate.status_code == 200
    candidate_id = candidate.json()["id"]

    approved = client.post(f"/api/v1/memory/candidates/{candidate_id}/approve")
    assert approved.status_code == 400
    assert "Graphiti Memory / Asset Graph setup blocker" in approved.json()["detail"]

    search = client.get("/api/v1/memory/search?q=evidence-backed")
    assert search.status_code == 200
    assert search.json()["results"] == []

    candidates_file = workspace / ".aiteamos" / "memory" / "candidates.json"
    approved_file = workspace / ".aiteamos" / "memory" / "approved.json"
    assert candidates_file.exists()
    assert not approved_file.exists()
    state = json.loads((workspace / ".aiteamos" / "memory" / "graphiti_state.json").read_text(encoding="utf-8"))
    assert state["last_candidate_id"] == candidate_id
    assert state["last_graphiti_status"]["status"] == "disabled"


def test_graphiti_settings_are_file_backed_and_read_secrets_from_env(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("AITEAMOS_GRAPHITI_ENABLED", raising=False)
    monkeypatch.delenv("AITEAMOS_GRAPHITI_URI", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = TestClient(create_app())

    initial = client.get("/api/v1/memory/graphiti/settings")
    assert initial.status_code == 200
    assert initial.json()["enabled"] is False
    assert initial.json()["password_configured"] is False

    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    updated = client.put(
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
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["enabled"] is True
    assert payload["llm_ai_engine"] == "openai"
    assert payload["password_configured"] is True
    assert payload["llm_api_key_configured"] is True
    assert payload["backend"]["graph_configured"] is True
    assert payload["backend"]["llm_configured"] is True
    assert payload["backend"]["status"] in {"ready", "package_missing"}
    assert "neo4j-test-password" not in json.dumps(payload)
    assert "openai-test-key" not in json.dumps(payload)

    settings_file = workspace / ".aiteamos" / "graphiti.json"
    settings_payload = json.loads(settings_file.read_text(encoding="utf-8"))
    assert settings_payload["uri"] == "bolt://localhost:7687"
    assert settings_payload["group_id"] == "aiteamos-test"
    assert settings_payload["llm_ai_engine"] == "openai"
    assert "password" not in settings_payload
    assert "openai_api_key" not in settings_payload
    assert not (workspace / ".aiteamos" / "secrets.local.json").exists()


def test_graphiti_ingest_and_search_preserve_aiteamos_provenance(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeSearchItem:
        uuid = "graphiti-result-1"
        fact = "Approved memory: keep Plane provider refs in traces."
        score = 0.91

        def __init__(self, provenance: dict):
            self.provenance = provenance

    class FakeGraphiti:
        instances: list["FakeGraphiti"] = []
        last_provenance: dict = {}

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password
            self.episodes: list[dict] = []
            self.searches: list[dict] = []
            FakeGraphiti.instances.append(self)

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            self.episodes.append(kwargs)
            marker = "AITeamOS provenance:\n"
            FakeGraphiti.last_provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            return FakeAddResult()

        async def search(self, query, **kwargs):
            self.searches.append({"query": query, "kwargs": kwargs})
            return [FakeSearchItem(FakeGraphiti.last_provenance)]

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
    assert settings.json()["backend"]["status"] == "ready"

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "Keep Plane provider refs and Graphiti episode refs in every self-bootstrap trace.",
            "source_kind": "ticket_summary",
            "source_ref": "trace/run-123",
            "scope_kind": "ticket",
            "scope_ref": "rd-0001",
            "memory_type": "principle",
            "confidence": 0.88,
            "employee_ids": ["clara"],
            "tags": ["phase-0.5", "plane", "graphiti"],
            "provenance": {
                "source_ticket_id": "rd-0001",
                "source_employee_id": "clara",
                "source_run_id": "run-123",
                "source_report_id": "report-123",
                "evidence_id": "evidence-123",
                "provider_refs": [
                    {
                        "provider": "plane",
                        "provider_record_id": "plane-ticket-1",
                    }
                ],
            },
        },
    )
    assert candidate.status_code == 200

    approved = client.post(f"/api/v1/memory/candidates/{candidate.json()['id']}/approve")
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["graphiti_episode_id"] == "episode-1"
    graphiti_status = approved_payload["graphiti_status"]
    assert graphiti_status["status"] == "ingested"
    assert graphiti_status["episode_schema_version"] == "aiteamos.graphiti.episode.v1"

    provenance = graphiti_status["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == candidate.json()["id"]
    assert provenance["asset_status"] == "approved"
    assert provenance["source_ticket_id"] == "rd-0001"
    assert provenance["source_employee_id"] == "clara"
    assert provenance["source_run_id"] == "run-123"
    assert provenance["source_report_id"] == "report-123"
    assert provenance["evidence_id"] == "evidence-123"
    assert provenance["scope"] == {"kind": "ticket", "ref": "rd-0001"}
    assert provenance["provider_refs"][0]["provider_record_id"] == "plane-ticket-1"
    assert provenance["source_ref"] == "trace/run-123"
    assert provenance["version"].startswith("sha256:")

    episode = FakeGraphiti.instances[0].episodes[0]
    assert episode["group_id"] == "aiteamos-test"
    assert '"asset_id"' in episode["episode_body"]
    assert '"provider_refs"' in episode["episode_body"]

    search = client.get("/api/v1/memory/search?q=Plane provider refs")
    assert search.status_code == 200
    graphiti_result = next(result for result in search.json()["results"] if result["source"] == "graphiti")
    assert graphiti_result["provenance"]["asset_id"] == candidate.json()["id"]
    assert graphiti_result["provenance"]["source_ticket_id"] == "rd-0001"
    assert FakeGraphiti.instances[-1].searches[0]["kwargs"]["group_ids"] == ["aiteamos-test"]

    state = json.loads((workspace / ".aiteamos" / "memory" / "graphiti_state.json").read_text(encoding="utf-8"))
    assert state["last_graphiti_status"]["provenance"]["source_ticket_id"] == "rd-0001"


def test_validated_ticket_summary_durable_asset_ingests_and_searches_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-ticket-summary-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeSearchItem:
        uuid = "graphiti-ticket-summary-result-1"
        episode_uuid = "episode-ticket-summary-1"
        fact = "Validated Ticket summary: Phase 3b uses Graphiti durable asset projection."
        score = 0.96

        def __init__(self, provenance: dict):
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        instances: list["FakeGraphiti"] = []
        last_provenance: dict = {}

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password
            self.episodes: list[dict] = []
            self.searches: list[dict] = []
            FakeGraphiti.instances.append(self)

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            self.episodes.append(kwargs)
            marker = "AITeamOS provenance:\n"
            FakeGraphiti.last_provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            return FakeAddResult()

        async def search(self, query, **kwargs):
            self.searches.append({"query": query, "kwargs": kwargs})
            return [FakeSearchItem(FakeGraphiti.last_provenance)]

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

    blocked = client.post(
        "/api/v1/memory/graphiti/durable-assets",
        json={
            "asset_id": "ticket-summary-rd-0004",
            "asset_type": "ticket_summary",
            "asset_status": "candidate",
            "content": "Unreviewed candidate summary must not enter Graphiti.",
        },
    )
    assert blocked.status_code == 400
    assert "approved, accepted, or validated" in blocked.json()["detail"]
    assert FakeGraphiti.instances == []

    ingested = client.post(
        "/api/v1/memory/graphiti/durable-assets",
        json={
            "asset_id": "ticket-summary-rd-0004",
            "asset_type": "ticket_summary",
            "asset_status": "validated",
            "content": "Validated Ticket summary: Phase 3b uses Graphiti durable asset projection.",
            "source_ticket_id": "rd-0004",
            "source_employee_id": "clara",
            "source_run_id": "run-ticket-summary-1",
            "source_report_id": "report-summary-1",
            "evidence_id": "report-summary-1:evidence:0",
            "scope": {"kind": "ticket", "ref": "rd-0004"},
            "provider_refs": [
                {
                    "provider": "plane",
                    "provider_record_id": "plane-ticket-rd-0004",
                    "provider_project_id": "plane-project-1",
                }
            ],
            "source_ref": "tickets/rd-0004#summary",
            "source_kind": "validated_ticket_summary",
            "metadata": {"validation_report_id": "report-validation-1"},
        },
    )
    assert ingested.status_code == 200
    payload = ingested.json()
    assert payload["status"] == "ingested"
    assert payload["episode_id"] == "episode-ticket-summary-1"
    provenance = payload["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == "ticket-summary-rd-0004"
    assert provenance["asset_type"] == "ticket_summary"
    assert provenance["asset_status"] == "validated"
    assert provenance["source_ticket_id"] == "rd-0004"
    assert provenance["source_employee_id"] == "clara"
    assert provenance["source_run_id"] == "run-ticket-summary-1"
    assert provenance["source_report_id"] == "report-summary-1"
    assert provenance["evidence_id"] == "report-summary-1:evidence:0"
    assert provenance["scope"] == {"kind": "ticket", "ref": "rd-0004"}
    assert provenance["provider_refs"][0]["provider_record_id"] == "plane-ticket-rd-0004"
    assert provenance["source_ref"] == "tickets/rd-0004#summary"
    assert provenance["content_hash"].startswith("sha256:")

    episode = FakeGraphiti.instances[0].episodes[0]
    assert episode["group_id"] == "aiteamos-test"
    assert "Validated Ticket summary" in episode["episode_body"]
    assert '"asset_type": "ticket_summary"' in episode["episode_body"]

    state_path = workspace / ".aiteamos" / "memory" / "graphiti_state.json"
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    prefix_record = dict(state_payload["durable_asset_ingestions"][0])
    prefix_status = dict(prefix_record["graphiti_status"])
    prefix_provenance = dict(prefix_status["provenance"])
    prefix_record["asset_id"] = "ticket-summary-rd-000"
    prefix_provenance["asset_id"] = "ticket-summary-rd-000"
    prefix_status["episode_id"] = "episode-prefix-ticket-summary"
    prefix_status["provenance"] = prefix_provenance
    prefix_record["graphiti_status"] = prefix_status
    state_payload["durable_asset_ingestions"].insert(0, prefix_record)
    state_path.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    search = client.get(
        "/api/v1/memory/search",
        params={"q": "Phase 3b durable asset projection", "include_graphiti": True},
    )
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "validated_ticket_summary"
    assert graphiti_result["scope_kind"] == "ticket"
    assert graphiti_result["scope_ref"] == "rd-0004"
    assert graphiti_result["memory_type"] == "ticket_summary"
    assert graphiti_result["employee_ids"] == ["clara"]
    assert graphiti_result["provenance"]["asset_id"] == "ticket-summary-rd-0004"
    assert graphiti_result["provenance"]["source_ticket_id"] == "rd-0004"
    assert FakeGraphiti.instances[-1].searches[0]["kwargs"]["group_ids"] == ["aiteamos-test"]

    state = json.loads((workspace / ".aiteamos" / "memory" / "graphiti_state.json").read_text(encoding="utf-8"))
    assert state["last_durable_asset_id"] == "ticket-summary-rd-0004"
    assert state["last_durable_asset_status"]["provenance"]["source_ticket_id"] == "rd-0004"


def test_accepted_decision_durable_asset_projects_to_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeSearchItem:
        score = 0.97

        def __init__(self, asset_id: str):
            self.uuid = f"graphiti-{asset_id}"
            self.episode_uuid = f"episode-{asset_id}"
            self.fact = f"{asset_id} is an accepted Decision durable asset from AITeamOS."
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []
        indexed_episodes: list[dict] = []

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult(f"episode-{asset_id}")

        async def search(self, query, **kwargs):
            matched = [asset_id for asset_id in FakeGraphiti.indexed_asset_ids if asset_id in query]
            return [FakeSearchItem(asset_id) for asset_id in (matched or FakeGraphiti.indexed_asset_ids[:1])]

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

    candidate_decision = client.post(
        "/api/v1/knowledge/decisions",
        json={
            "title": "Candidate Decision stays local",
            "status": "candidate",
            "context": "Candidate decisions require governance before durable graph projection.",
            "decision": "Do not ingest candidate Decisions into Graphiti.",
            "linked_tickets": ["rd-0100"],
        },
    )
    assert candidate_decision.status_code == 200
    blocked = client.post(
        f"/api/v1/memory/graphiti/decisions/{candidate_decision.json()['id']}/durable-asset"
    )
    assert blocked.status_code == 400
    assert "Only accepted Decisions" in blocked.json()["detail"]
    assert FakeGraphiti.indexed_asset_ids == []

    decision = client.post(
        "/api/v1/knowledge/decisions",
        json={
            "title": "Project Decisions to Graphiti",
            "status": "accepted",
            "context": "Phase 3b expands durable asset projection beyond Memories.",
            "decision": "Accepted Decisions should be ingested as Graphiti durable assets with AITeamOS provenance.",
            "consequences": "Decision recall can guide similar self-bootstrap Tickets.",
            "linked_tickets": ["rd-0101"],
            "linked_memories": ["mem-graphiti-decision"],
        },
    )
    assert decision.status_code == 200
    decision_id = decision.json()["id"]

    projected = client.post(f"/api/v1/memory/graphiti/decisions/{decision_id}/durable-asset")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert payload["ingested_asset"]["episode_id"] == f"episode-{decision_id}"
    provenance = payload["ingested_asset"]["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == decision_id
    assert provenance["asset_type"] == "decision"
    assert provenance["asset_status"] == "accepted"
    assert provenance["source_ticket_id"] == "rd-0101"
    assert provenance["scope"] == {"kind": "ticket", "ref": "rd-0101"}
    assert provenance["source_ref"].startswith(".aiteamos/knowledge/decisions/")
    assert provenance["source_kind"] == "accepted_decision"
    assert provenance["metadata"]["linked_tickets"] == ["rd-0101"]
    assert provenance["metadata"]["linked_memories"] == ["mem-graphiti-decision"]

    episode = FakeGraphiti.indexed_episodes[0]
    assert "Accepted Decision" in episode["episode_body"]
    assert '"asset_type": "decision"' in episode["episode_body"]

    repeated = client.post(f"/api/v1/memory/graphiti/decisions/{decision_id}/durable-asset")
    assert repeated.status_code == 200
    repeated_payload = repeated.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["skipped_asset"]["reason"] == "already_ingested"
    assert repeated_payload["skipped_asset"]["episode_id"] == f"episode-{decision_id}"

    batch_decision = client.post(
        "/api/v1/knowledge/decisions",
        json={
            "title": "Batch Project Accepted Decisions",
            "status": "accepted",
            "context": "Self-bootstrap batches need bounded durable asset ingestion.",
            "decision": "Accepted Decisions can be projected to Graphiti in capped batches.",
            "consequences": "AITeamOS can seed broader Decision recall without unbounded ingestion.",
            "linked_tickets": ["rd-0102"],
        },
    )
    assert batch_decision.status_code == 200
    batch_decision_id = batch_decision.json()["id"]

    batch = client.post("/api/v1/memory/graphiti/decisions/durable-assets", params={"max_assets": 1})
    assert batch.status_code == 200
    batch_payload = batch.json()
    assert batch_payload["status"] == "ingested"
    assert [item["provenance"]["asset_id"] for item in batch_payload["ingested_assets"]] == [batch_decision_id]
    assert any(
        item["asset_id"] == decision_id and item["reason"] == "already_ingested"
        for item in batch_payload["skipped_assets"]
    )
    assert candidate_decision.json()["id"] not in {
        item["provenance"]["asset_id"] for item in batch_payload["ingested_assets"]
    }

    search = client.get("/api/v1/memory/search", params={"q": decision_id, "include_graphiti": True})
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "accepted_decision"
    assert graphiti_result["scope_kind"] == "ticket"
    assert graphiti_result["scope_ref"] == "rd-0101"
    assert graphiti_result["memory_type"] == "decision"
    assert graphiti_result["provenance"]["asset_id"] == decision_id
    assert graphiti_result["provenance"]["source_ticket_id"] == "rd-0101"


def test_approved_skill_durable_assets_project_to_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implements Ticket-bound changes.
skills:
  - graphiti-skill-projection
""".strip(),
        encoding="utf-8",
    )
    skill_dir = workspace / ".aiteamos" / "skills" / "graphiti-skill-projection"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """
# Graphiti Skill Projection

> Project approved Skill summaries into Graphiti with AITeamOS provenance.

## Procedure
1. Keep the source Skill as the AITeamOS asset.
2. Ingest only an approved durable summary.
3. Preserve assigned Employee and source_ref.
""".strip(),
        encoding="utf-8",
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeSearchItem:
        score = 0.95

        def __init__(self, asset_id: str):
            self.uuid = f"graphiti-{asset_id}"
            self.episode_uuid = f"episode-{asset_id}"
            self.fact = f"{asset_id} is an approved Skill summary durable asset from AITeamOS."
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []
        indexed_episodes: list[dict] = []

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult(f"episode-{asset_id}")

        async def search(self, query, **kwargs):
            matched = [asset_id for asset_id in FakeGraphiti.indexed_asset_ids if asset_id in query]
            return [FakeSearchItem(asset_id) for asset_id in (matched or FakeGraphiti.indexed_asset_ids[:1])]

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

    missing = client.post("/api/v1/memory/graphiti/skills/not-a-skill/durable-asset")
    assert missing.status_code == 404
    assert FakeGraphiti.indexed_asset_ids == []

    projected = client.post("/api/v1/memory/graphiti/skills/graphiti-skill-projection/durable-asset")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert payload["ingested_asset"]["episode_id"] == "episode-skill-summary-graphiti-skill-projection"
    provenance = payload["ingested_asset"]["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == "skill-summary-graphiti-skill-projection"
    assert provenance["asset_type"] == "skill_summary"
    assert provenance["asset_status"] == "approved"
    assert provenance["source_employee_id"] == "alex"
    assert provenance["scope"] == {"kind": "employee", "ref": "alex"}
    assert provenance["source_ref"] == ".aiteamos/skills/graphiti-skill-projection/SKILL.md"
    assert provenance["source_kind"] == "approved_skill_summary"
    assert provenance["metadata"]["source_asset_id"] == "graphiti-skill-projection"
    assert provenance["metadata"]["assigned_employees"] == ["alex"]

    episode = FakeGraphiti.indexed_episodes[0]
    assert "Approved Skill summary" in episode["episode_body"]
    assert '"asset_type": "skill_summary"' in episode["episode_body"]

    repeated = client.post("/api/v1/memory/graphiti/skills/graphiti-skill-projection/durable-asset")
    assert repeated.status_code == 200
    repeated_payload = repeated.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["skipped_asset"]["reason"] == "already_ingested"

    batch = client.post("/api/v1/memory/graphiti/skills/durable-assets", params={"max_assets": 50})
    assert batch.status_code == 200
    batch_payload = batch.json()
    assert batch_payload["status"] == "ingested"
    assert any(
        item["asset_id"] == "skill-summary-graphiti-skill-projection" and item["reason"] == "already_ingested"
        for item in batch_payload["skipped_assets"]
    )
    assert all(item["provenance"]["asset_type"] == "skill_summary" for item in batch_payload["ingested_assets"])

    search = client.get(
        "/api/v1/memory/search",
        params={"q": "skill-summary-graphiti-skill-projection", "include_graphiti": True},
    )
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "approved_skill_summary"
    assert graphiti_result["scope_kind"] == "employee"
    assert graphiti_result["scope_ref"] == "alex"
    assert graphiti_result["memory_type"] == "skill_summary"
    assert graphiti_result["employee_ids"] == ["alex"]
    assert graphiti_result["provenance"]["asset_id"] == "skill-summary-graphiti-skill-projection"
    assert graphiti_result["provenance"]["metadata"]["source_asset_id"] == "graphiti-skill-projection"


def test_approved_doc_durable_assets_project_to_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    docs_dir = workspace / "docs"
    docs_dir.mkdir()
    (docs_dir / "GRAPHITI-DOC.md").write_text(
        """
# Graphiti Doc Projection

Approved Docs can be projected to Graphiti as durable doc summaries.

The projection must keep AITeamOS provenance and source_ref back to the doc path.
""".strip(),
        encoding="utf-8",
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeSearchItem:
        score = 0.96

        def __init__(self, asset_id: str):
            self.uuid = f"graphiti-{asset_id}"
            self.episode_uuid = f"episode-{asset_id}"
            self.fact = f"{asset_id} is an approved Doc summary durable asset from AITeamOS."
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []
        indexed_episodes: list[dict] = []

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult(f"episode-{asset_id}")

        async def search(self, query, **kwargs):
            matched = [asset_id for asset_id in FakeGraphiti.indexed_asset_ids if asset_id in query]
            return [FakeSearchItem(asset_id) for asset_id in (matched or FakeGraphiti.indexed_asset_ids[:1])]

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

    decision = client.post(
        "/api/v1/knowledge/decisions",
        json={
            "title": "Decision markdown is not a Doc summary",
            "status": "accepted",
            "decision": "Decision markdown should use Decision durable asset projection.",
        },
    )
    assert decision.status_code == 200
    decision_doc_id = decision.json()["saved_path"].removesuffix(".md").replace("/", "-").replace("_", "-").lower()

    missing = client.post("/api/v1/memory/graphiti/docs/not-a-doc/durable-asset")
    assert missing.status_code == 404
    assert FakeGraphiti.indexed_asset_ids == []

    projected = client.post("/api/v1/memory/graphiti/docs/docs-graphiti-doc/durable-asset")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert payload["ingested_asset"]["episode_id"] == "episode-doc-summary-docs-graphiti-doc"
    provenance = payload["ingested_asset"]["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == "doc-summary-docs-graphiti-doc"
    assert provenance["asset_type"] == "doc_summary"
    assert provenance["asset_status"] == "approved"
    assert provenance["scope"] == {"kind": "doc", "ref": "docs-graphiti-doc"}
    assert provenance["source_ref"] == "docs/GRAPHITI-DOC.md"
    assert provenance["source_kind"] == "approved_doc_summary"
    assert provenance["metadata"]["source_asset_id"] == "docs-graphiti-doc"
    assert provenance["metadata"]["path"] == "docs/GRAPHITI-DOC.md"

    episode = FakeGraphiti.indexed_episodes[0]
    assert "Approved Doc summary" in episode["episode_body"]
    assert '"asset_type": "doc_summary"' in episode["episode_body"]

    repeated = client.post("/api/v1/memory/graphiti/docs/docs-graphiti-doc/durable-asset")
    assert repeated.status_code == 200
    repeated_payload = repeated.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["skipped_asset"]["reason"] == "already_ingested"

    batch = client.post("/api/v1/memory/graphiti/docs/durable-assets", params={"max_assets": 50})
    assert batch.status_code == 200
    batch_payload = batch.json()
    assert batch_payload["status"] in {"ingested", "skipped"}
    assert any(
        item["asset_id"] == "doc-summary-docs-graphiti-doc" and item["reason"] == "already_ingested"
        for item in batch_payload["skipped_assets"]
    )
    batch_asset_ids = {
        item["provenance"]["asset_id"]
        for item in batch_payload["ingested_assets"]
    }
    assert f"doc-summary-{decision_doc_id}" not in batch_asset_ids
    assert all(item["provenance"]["asset_type"] == "doc_summary" for item in batch_payload["ingested_assets"])

    search = client.get(
        "/api/v1/memory/search",
        params={"q": "doc-summary-docs-graphiti-doc", "include_graphiti": True},
    )
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "approved_doc_summary"
    assert graphiti_result["scope_kind"] == "doc"
    assert graphiti_result["scope_ref"] == "docs-graphiti-doc"
    assert graphiti_result["memory_type"] == "doc_summary"
    assert graphiti_result["provenance"]["asset_id"] == "doc-summary-docs-graphiti-doc"
    assert graphiti_result["provenance"]["metadata"]["source_asset_id"] == "docs-graphiti-doc"


def test_approved_employee_profile_durable_assets_project_to_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implements Ticket-bound changes.
personality: Direct and evidence-driven.
responsibilities:
  - Investigate Ticket-linked engineering work.
  - Report changed files and verification.
skills:
  - backend-api-implementation
memory_scopes:
  - aiteamos
  - employee:alex
permissions:
  - run_terminal
  - propose_code_change
handoff_rules:
  - Ask PV to validate regression evidence.
""".strip(),
        encoding="utf-8",
    )
    (employees_dir / "peter.yaml").write_text(
        """
id: peter
display_name: Peter
kind: ai
role: AI PV
summary: Validates Ticket evidence.
skills:
  - validation-strategy
memory_scopes:
  - aiteamos
  - employee:peter
permissions:
  - read_validation_evidence
""".strip(),
        encoding="utf-8",
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeSearchItem:
        score = 0.97

        def __init__(self, asset_id: str):
            self.uuid = f"graphiti-{asset_id}"
            self.episode_uuid = f"episode-{asset_id}"
            self.fact = f"{asset_id} is an approved Employee profile summary durable asset from AITeamOS."
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []
        indexed_episodes: list[dict] = []

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult(f"episode-{asset_id}")

        async def search(self, query, **kwargs):
            matched = [asset_id for asset_id in FakeGraphiti.indexed_asset_ids if asset_id in query]
            return [FakeSearchItem(asset_id) for asset_id in (matched or FakeGraphiti.indexed_asset_ids[:1])]

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

    missing = client.post("/api/v1/memory/graphiti/employees/not-an-employee/durable-asset")
    assert missing.status_code == 404
    assert FakeGraphiti.indexed_asset_ids == []

    projected = client.post("/api/v1/memory/graphiti/employees/alex/durable-asset")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert payload["ingested_asset"]["episode_id"] == "episode-employee-profile-alex"
    provenance = payload["ingested_asset"]["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == "employee-profile-alex"
    assert provenance["asset_type"] == "employee_profile_summary"
    assert provenance["asset_status"] == "approved"
    assert provenance["source_employee_id"] == "alex"
    assert provenance["scope"] == {"kind": "employee", "ref": "alex"}
    assert provenance["source_ref"] == ".aiteamos/employees/alex.yaml"
    assert provenance["source_kind"] == "approved_employee_profile_summary"
    assert provenance["metadata"]["source_asset_id"] == "alex"
    assert provenance["metadata"]["skills"] == ["backend-api-implementation"]
    assert "permissions" not in provenance["metadata"]

    episode = FakeGraphiti.indexed_episodes[0]
    assert "Approved Employee profile summary" in episode["episode_body"]
    assert '"asset_type": "employee_profile_summary"' in episode["episode_body"]
    assert "permissions" not in episode["episode_body"]
    assert "run_terminal" not in episode["episode_body"]
    assert "propose_code_change" not in episode["episode_body"]

    repeated = client.post("/api/v1/memory/graphiti/employees/alex/durable-asset")
    assert repeated.status_code == 200
    repeated_payload = repeated.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["skipped_asset"]["reason"] == "already_ingested"

    batch = client.post("/api/v1/memory/graphiti/employees/durable-assets", params={"max_assets": 50})
    assert batch.status_code == 200
    batch_payload = batch.json()
    assert batch_payload["status"] == "ingested"
    assert any(
        item["asset_id"] == "employee-profile-alex" and item["reason"] == "already_ingested"
        for item in batch_payload["skipped_assets"]
    )
    assert {
        item["provenance"]["asset_id"]
        for item in batch_payload["ingested_assets"]
    } == {"employee-profile-peter"}
    assert all(item["provenance"]["asset_type"] == "employee_profile_summary" for item in batch_payload["ingested_assets"])

    search = client.get(
        "/api/v1/memory/search",
        params={"q": "employee-profile-alex", "include_graphiti": True},
    )
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "approved_employee_profile_summary"
    assert graphiti_result["scope_kind"] == "employee"
    assert graphiti_result["scope_ref"] == "alex"
    assert graphiti_result["memory_type"] == "employee_profile_summary"
    assert graphiti_result["employee_ids"] == ["alex"]
    assert graphiti_result["provenance"]["asset_id"] == "employee-profile-alex"
    assert graphiti_result["provenance"]["metadata"]["source_asset_id"] == "alex"


def test_approved_capability_durable_assets_project_to_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    connectors_path = workspace / ".aiteamos" / "tool_connectors.json"
    connectors_path.parent.mkdir(parents=True)
    connectors_path.write_text(
        json.dumps(
            [
                {
                    "id": "github",
                    "name": "GitHub",
                    "status": "configured",
                    "transport": "mcp",
                    "enabled": True,
                    "configured": True,
                    "description": "Repository connector for configured workspaces.",
                    "capabilities": ["repo.search"],
                    "permissions": ["repo:read"],
                    "required_settings": ["owner", "repo", "GITHUB_TOKEN"],
                    "server": {},
                    "updated_at": "2026-06-07T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeSearchItem:
        score = 0.98

        def __init__(self, asset_id: str):
            self.uuid = f"graphiti-{asset_id}"
            self.episode_uuid = f"episode-{asset_id}"
            self.fact = f"{asset_id} is an approved Capability summary durable asset from AITeamOS."
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []
        indexed_episodes: list[dict] = []

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult(f"episode-{asset_id}")

        async def search(self, query, **kwargs):
            matched = [asset_id for asset_id in FakeGraphiti.indexed_asset_ids if asset_id in query]
            return [FakeSearchItem(asset_id) for asset_id in (matched or FakeGraphiti.indexed_asset_ids[:1])]

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

    missing = client.post("/api/v1/memory/graphiti/capabilities/not-a-capability/durable-asset")
    assert missing.status_code == 404
    planned = client.post("/api/v1/memory/graphiti/capabilities/mcp:ci-harness:validation.run/durable-asset")
    assert planned.status_code == 400
    assert FakeGraphiti.indexed_asset_ids == []

    projected = client.post("/api/v1/memory/graphiti/capabilities/terminal.run/durable-asset")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert payload["ingested_asset"]["episode_id"] == "episode-capability-terminal.run"
    provenance = payload["ingested_asset"]["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == "capability-terminal.run"
    assert provenance["asset_type"] == "capability_summary"
    assert provenance["asset_status"] == "approved"
    assert provenance["scope"] == {"kind": "capability", "ref": "terminal.run"}
    assert provenance["source_ref"] == "capability_registry:kernel_command:terminal.run"
    assert provenance["source_kind"] == "approved_capability_summary"
    assert provenance["metadata"]["source_asset_id"] == "terminal.run"
    assert provenance["metadata"]["capability_source_kind"] == "kernel_command"
    assert "permissions" not in provenance["metadata"]
    assert "required_settings" not in provenance["metadata"]

    mcp_projected = client.post("/api/v1/memory/graphiti/capabilities/mcp:github:repo.search/durable-asset")
    assert mcp_projected.status_code == 200
    mcp_provenance = mcp_projected.json()["ingested_asset"]["provenance"]
    assert mcp_provenance["asset_id"] == "capability-mcp:github:repo.search"
    assert mcp_provenance["metadata"]["connector_id"] == "github"
    assert mcp_provenance["metadata"]["capability_source_kind"] == "mcp_server"
    assert mcp_provenance["source_ref"] == "tool_connector:github:mcp:github:repo.search"
    assert "permissions" not in mcp_provenance["metadata"]
    assert "required_settings" not in mcp_provenance["metadata"]

    combined_episode_body = "\n".join(item["episode_body"] for item in FakeGraphiti.indexed_episodes)
    assert "Approved Capability summary" in combined_episode_body
    assert '"asset_type": "capability_summary"' in combined_episode_body
    assert "repo:read" not in combined_episode_body
    assert "terminal:run" not in combined_episode_body
    assert "GITHUB_TOKEN" not in combined_episode_body
    assert "required_settings" not in combined_episode_body

    repeated = client.post("/api/v1/memory/graphiti/capabilities/terminal.run/durable-asset")
    assert repeated.status_code == 200
    repeated_payload = repeated.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["skipped_asset"]["reason"] == "already_ingested"

    batch = client.post("/api/v1/memory/graphiti/capabilities/durable-assets", params={"max_assets": 50})
    assert batch.status_code == 200
    batch_payload = batch.json()
    assert batch_payload["status"] == "ingested"
    assert any(
        item["asset_id"] == "capability-terminal.run" and item["reason"] == "already_ingested"
        for item in batch_payload["skipped_assets"]
    )
    assert any(
        item["asset_id"] == "capability-mcp:github:repo.search" and item["reason"] == "already_ingested"
        for item in batch_payload["skipped_assets"]
    )
    assert all(item["provenance"]["asset_type"] == "capability_summary" for item in batch_payload["ingested_assets"])

    search = client.get(
        "/api/v1/memory/search",
        params={"q": "capability-terminal.run", "include_graphiti": True},
    )
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "approved_capability_summary"
    assert graphiti_result["scope_kind"] == "capability"
    assert graphiti_result["scope_ref"] == "terminal.run"
    assert graphiti_result["memory_type"] == "capability_summary"
    assert graphiti_result["provenance"]["asset_id"] == "capability-terminal.run"
    assert graphiti_result["provenance"]["metadata"]["source_asset_id"] == "terminal.run"


def test_durable_asset_relationships_project_to_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeSearchItem:
        score = 0.99

        def __init__(self, asset_id: str):
            self.uuid = f"graphiti-{asset_id}"
            self.episode_uuid = f"episode-{asset_id}"
            self.fact = f"{asset_id} is a durable asset relationship fact from AITeamOS."
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []
        indexed_episodes: list[dict] = []

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult(f"episode-{asset_id}")

        async def search(self, query, **kwargs):
            matched = [asset_id for asset_id in FakeGraphiti.indexed_asset_ids if asset_id in query]
            return [FakeSearchItem(asset_id) for asset_id in (matched or FakeGraphiti.indexed_asset_ids[:1])]

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

    invalid = client.post(
        "/api/v1/memory/graphiti/asset-relationships",
        json={
            "source_asset_id": "mem-old",
            "target_asset_id": "mem-new",
            "relationship_type": "raw_trace_contains",
            "reason": "Raw traces must not become Graphiti relationship facts.",
        },
    )
    assert invalid.status_code == 400
    assert "Unsupported durable asset relationship type" in invalid.json()["detail"]
    assert FakeGraphiti.indexed_asset_ids == []

    projected = client.post(
        "/api/v1/memory/graphiti/asset-relationships",
        json={
            "source_asset_id": "mem-new",
            "target_asset_id": "mem-old",
            "relationship_type": "supersedes",
            "asset_status": "validated",
            "reason": "New PV evidence updates the old validation guidance.",
            "source_ticket_id": "rd-0201",
            "source_employee_id": "clara",
            "source_run_id": "run-asset-relationship",
            "source_report_id": "report-asset-relationship",
            "evidence_id": "evidence-asset-relationship",
            "scope": {"kind": "asset", "ref": "mem-new"},
            "provider_refs": [{"provider": "plane", "provider_record_id": "plane-rel-1"}],
            "source_ref": "traces/run-asset-relationship.jsonl",
            "metadata": {
                "confidence": 0.92,
                "review_status": "validated",
                "raw_tool_log": "must not enter Graphiti",
                "secret_token": "must-not-enter-graphiti",
                "permission_authority": "must not enter Graphiti",
            },
        },
    )
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert payload["relationship_type"] == "supersedes"
    assert payload["source_asset_id"] == "mem-new"
    assert payload["target_asset_id"] == "mem-old"
    relationship_id = payload["relationship_id"]
    assert payload["ingested_asset"]["episode_id"] == f"episode-{relationship_id}"
    provenance = payload["ingested_asset"]["provenance"]
    for field in memory_service.GRAPHITI_MINIMAL_PROVENANCE_FIELDS:
        assert field in provenance
    assert provenance["asset_id"] == relationship_id
    assert provenance["asset_type"] == "asset_relationship"
    assert provenance["asset_status"] == "validated"
    assert provenance["source_ticket_id"] == "rd-0201"
    assert provenance["source_employee_id"] == "clara"
    assert provenance["source_run_id"] == "run-asset-relationship"
    assert provenance["source_report_id"] == "report-asset-relationship"
    assert provenance["evidence_id"] == "evidence-asset-relationship"
    assert provenance["scope"] == {"kind": "asset", "ref": "mem-new"}
    assert provenance["provider_refs"][0]["provider_record_id"] == "plane-rel-1"
    assert provenance["source_ref"] == "traces/run-asset-relationship.jsonl"
    assert provenance["source_kind"] == "durable_asset_relationship"
    assert provenance["metadata"]["source_asset_id"] == "mem-new"
    assert provenance["metadata"]["target_asset_id"] == "mem-old"
    assert provenance["metadata"]["relationship_type"] == "supersedes"
    assert provenance["metadata"]["confidence"] == 0.92
    assert "raw_tool_log" not in provenance["metadata"]
    assert "secret_token" not in provenance["metadata"]
    assert "permission_authority" not in provenance["metadata"]

    episode_body = FakeGraphiti.indexed_episodes[0]["episode_body"]
    assert "Durable asset relationship" in episode_body
    assert "mem-new supersedes mem-old" in episode_body
    assert "raw_tool_log" not in episode_body
    assert "must-not-enter-graphiti" not in episode_body
    assert "permission_authority" not in episode_body

    repeated = client.post(
        "/api/v1/memory/graphiti/asset-relationships",
        json={
            "source_asset_id": "mem-new",
            "target_asset_id": "mem-old",
            "relationship_type": "supersedes",
            "reason": "New PV evidence updates the old validation guidance.",
        },
    )
    assert repeated.status_code == 200
    repeated_payload = repeated.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["relationship_id"] == relationship_id
    assert repeated_payload["skipped_asset"]["reason"] == "already_ingested"

    search = client.get(
        "/api/v1/memory/search",
        params={"q": relationship_id, "include_graphiti": True},
    )
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "durable_asset_relationship"
    assert graphiti_result["scope_kind"] == "asset"
    assert graphiti_result["scope_ref"] == "mem-new"
    assert graphiti_result["memory_type"] == "asset_relationship"
    assert graphiti_result["employee_ids"] == ["clara"]
    assert graphiti_result["provenance"]["asset_id"] == relationship_id
    assert graphiti_result["provenance"]["metadata"]["relationship_type"] == "supersedes"


def test_validated_ticket_report_and_evidence_assets_project_to_graphiti(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeSearchItem:
        score = 0.95

        def __init__(self, asset_id: str):
            self.uuid = f"graphiti-{asset_id}"
            self.episode_uuid = f"episode-{asset_id}"
            self.fact = f"{asset_id} is a validated Graphiti durable asset from AITeamOS."
            self.metadata = {"graphiti_fact_kind": "extracted_without_aiteamos_provenance"}

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            return FakeAddResult(f"episode-{asset_id}")

        async def search(self, query, **kwargs):
            matched = [asset_id for asset_id in FakeGraphiti.indexed_asset_ids if asset_id in query]
            return [FakeSearchItem(asset_id) for asset_id in (matched or FakeGraphiti.indexed_asset_ids[:1])]

        async def close(self):
            return None

    class FakePlaneResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    plane_state = {"state": "state-assigned"}

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
                        "id": "plane-ticket-report-assets-1",
                        "project": "plane-project-1",
                        "sequence_id": 91,
                        "state": "state-assigned",
                    },
                )
            if method == "POST" and url.endswith("/work-items/plane-ticket-report-assets-1/comments/"):
                report_type = (
                    ((json or {}).get("comment_json") or {})
                    .get("aiteamos", {})
                    .get("report_type", "")
                )
                if report_type == "validation":
                    plane_state["state"] = "state-validated"
                return FakePlaneResponse(201, {"id": "plane-comment-report-assets"})
            if method == "GET" and url.endswith("/work-items/plane-ticket-report-assets-1/"):
                return FakePlaneResponse(
                    200,
                    {
                        "id": "plane-ticket-report-assets-1",
                        "project": "plane-project-1",
                        "state": plane_state["state"],
                    },
                )
            return FakePlaneResponse(404, {"detail": f"unexpected {method} {url}"})

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

    client = TestClient(create_app())
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
            "plane_state_ids": {"assigned": "state-assigned", "validated": "state-validated"},
            "plane_employee_assignee_ids": {"alex": "plane-user-alex", "peter": "plane-user-peter"},
        },
    )
    assert backend.status_code == 200

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Project validated report and evidence assets",
            "description": "Phase 3b should project validated report and evidence summaries to Graphiti.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
            "validation_employee_id": "peter",
            "validation_role": "AI PV",
            "source_run_id": "run-create-report-assets",
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]

    result_report = client.post(
        f"/api/v1/tickets/{ticket_id}/reports",
        json={
            "reporter_employee_id": "alex",
            "reporter_role": "AI RD / Implementer",
            "content": "Implemented report and evidence durable asset projection.",
            "report_type": "result",
            "evidence": ["pytest tests/test_file_memory_routes.py -q passed"],
            "source_run_id": "run-result-report-assets",
        },
    )
    assert result_report.status_code == 200

    blocked_projection = client.post(f"/api/v1/memory/graphiti/tickets/{ticket_id}/durable-assets")
    assert blocked_projection.status_code == 400
    assert "Only validated Tickets" in blocked_projection.json()["detail"]
    assert FakeGraphiti.indexed_asset_ids == []

    validated = client.post(
        f"/api/v1/tickets/{ticket_id}/reports",
        json={
            "reporter_employee_id": "peter",
            "reporter_role": "AI PV",
            "content": "Validation passed with focused backend evidence.",
            "report_type": "validation",
            "evidence": ["pytest passed", "npm test passed"],
            "source_run_id": "run-validation-report-assets",
        },
    )
    assert validated.status_code == 200
    ticket_payload = validated.json()
    assert ticket_payload["status"] == "validated"
    report_ids = [report["id"] for report in ticket_payload["reports"]]

    projected = client.post(f"/api/v1/memory/graphiti/tickets/{ticket_id}/durable-assets")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert len(payload["ingested_assets"]) == 6
    asset_types = [item["provenance"]["asset_type"] for item in payload["ingested_assets"]]
    assert asset_types.count("ticket_summary") == 1
    assert asset_types.count("report_summary") == 2
    assert asset_types.count("evidence_summary") == 3
    assert {item["provenance"]["source_ticket_id"] for item in payload["ingested_assets"]} == {ticket_id}
    assert {item["provenance"]["provider_refs"][0]["provider_record_id"] for item in payload["ingested_assets"]} == {
        "plane-ticket-report-assets-1"
    }
    assert {item["provenance"]["source_run_id"] for item in payload["ingested_assets"] if item["provenance"]["source_run_id"]} == {
        "run-create-report-assets",
        "run-result-report-assets",
        "run-validation-report-assets",
    }
    ticket_summary = next(item for item in payload["ingested_assets"] if item["provenance"]["asset_type"] == "ticket_summary")
    assert ticket_summary["provenance"]["asset_id"] == f"ticket-summary-{ticket_id}"
    assert ticket_summary["provenance"]["source_kind"] == "validated_ticket_summary"
    assert ticket_summary["provenance"]["scope"] == {"kind": "ticket", "ref": ticket_id}
    assert ticket_summary["provenance"]["metadata"]["report_count"] == 2
    assert ticket_summary["provenance"]["metadata"]["evidence_count"] == 3
    assert ticket_summary["provenance"]["metadata"]["assigned_employee_id"] == "alex"
    assert ticket_summary["provenance"]["metadata"]["validation_employee_id"] == "peter"
    evidence_asset = next(item for item in payload["ingested_assets"] if item["provenance"]["asset_type"] == "evidence_summary")
    assert evidence_asset["provenance"]["source_report_id"] in report_ids
    assert evidence_asset["provenance"]["evidence_id"].endswith(":evidence:0")

    repeated = client.post(f"/api/v1/memory/graphiti/tickets/{ticket_id}/durable-assets")
    assert repeated.status_code == 200
    repeated_payload = repeated.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["ingested_assets"] == []
    assert len(repeated_payload["skipped_assets"]) == 6

    evidence_asset_id = evidence_asset["provenance"]["asset_id"]
    search = client.get("/api/v1/memory/search", params={"q": evidence_asset_id, "include_graphiti": True})
    assert search.status_code == 200
    graphiti_result = search.json()["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "validated_evidence_summary"
    assert graphiti_result["scope_kind"] == "ticket"
    assert graphiti_result["scope_ref"] == ticket_id
    assert graphiti_result["provenance"]["asset_id"] == evidence_asset_id
    assert graphiti_result["provenance"]["source_ticket_id"] == ticket_id

    ticket_summary_search = client.get(
        "/api/v1/memory/search",
        params={"q": f"ticket-summary-{ticket_id}", "include_graphiti": True},
    )
    assert ticket_summary_search.status_code == 200
    ticket_summary_result = ticket_summary_search.json()["results"][0]
    assert ticket_summary_result["source"] == "graphiti"
    assert ticket_summary_result["source_kind"] == "validated_ticket_summary"
    assert ticket_summary_result["scope_kind"] == "ticket"
    assert ticket_summary_result["scope_ref"] == ticket_id
    assert ticket_summary_result["memory_type"] == "ticket_summary"
    assert ticket_summary_result["employee_ids"] == ["alex"]
    assert ticket_summary_result["provenance"]["asset_id"] == f"ticket-summary-{ticket_id}"


def test_graphiti_fact_result_aligns_to_local_approved_memory_provenance(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-align-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeSearchItem:
        uuid = "graphiti-edge-align-1"
        episode_uuid = "graphiti-edge-episode-1"
        fact = "AITeamOS graphiti align-abc123 preserves provider_ref for Plane-backed Tickets"

    class FakeGraphiti:
        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            return FakeAddResult()

        async def search(self, query, **kwargs):
            return [FakeSearchItem()]

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

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "AITeamOS graphiti align-abc123: Plane-backed Tickets preserve provider_ref and approved memories keep provenance.",
            "source_kind": "ticket_summary",
            "source_ref": "trace/run-align",
            "scope_kind": "ticket",
            "scope_ref": "rd-0001",
            "memory_type": "principle",
            "confidence": 0.9,
            "employee_ids": ["clara"],
            "tags": ["align-abc123", "graphiti", "plane"],
            "provenance": {
                "source_ticket_id": "rd-0001",
                "source_employee_id": "clara",
                "source_run_id": "run-align",
                "source_report_id": "report-align",
                "evidence_id": "evidence-align",
            },
        },
    )
    assert candidate.status_code == 200
    approved = client.post(f"/api/v1/memory/candidates/{candidate.json()['id']}/approve")
    assert approved.status_code == 200

    search = client.get(
        "/api/v1/memory/search",
        params={
            "q": "Plane-backed Tickets preserve provider_ref",
            "ticket_key": "rd-0002",
        },
    )
    assert search.status_code == 200
    payload = search.json()
    assert len(payload["results"]) == 1
    graphiti_result = payload["results"][0]
    assert graphiti_result["source"] == "graphiti"
    assert graphiti_result["source_kind"] == "ticket_summary"
    assert graphiti_result["scope_kind"] == "ticket"
    assert graphiti_result["scope_ref"] == "rd-0001"
    assert graphiti_result["provenance"]["asset_id"] == candidate.json()["id"]
    assert graphiti_result["provenance"]["source_ticket_id"] == "rd-0001"
    assert graphiti_result["provenance"]["source_employee_id"] == "clara"
    assert graphiti_result["provenance"]["source_run_id"] == "run-align"
    assert graphiti_result["provenance"]["source_report_id"] == "report-align"
    assert graphiti_result["provenance"]["evidence_id"] == "evidence-align"
    assert graphiti_result["provenance"]["graphiti_result_id"] == "graphiti-edge-align-1"


def test_approved_memory_can_be_marked_stale_and_is_not_recalled(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-stale-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeSearchItem:
        uuid = "graphiti-stale-result-1"
        episode_uuid = "episode-stale-1"
        fact = "Approved memory: old validation pitfall."
        score = 0.94

        def __init__(self, provenance: dict):
            self.provenance = provenance

    class FakeGraphiti:
        last_provenance: dict = {}

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            FakeGraphiti.last_provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            return FakeAddResult()

        async def search(self, query, **kwargs):
            if not FakeGraphiti.last_provenance:
                return []
            return [FakeSearchItem(FakeGraphiti.last_provenance)]

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

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "Old validation pitfall: retry validation without evidence.",
            "source_kind": "ticket_summary",
            "source_ref": "traces/run-stale",
            "scope_kind": "ticket",
            "scope_ref": "rd-0002",
            "memory_type": "lesson",
            "confidence": 0.8,
            "employee_ids": ["clara"],
            "tags": ["validation"],
            "provenance": {
                "source_ticket_id": "rd-0002",
                "source_employee_id": "clara",
                "source_run_id": "run-stale",
                "source_ref": "traces/run-stale",
            },
        },
    )
    assert candidate.status_code == 200
    candidate_id = candidate.json()["id"]

    approved = client.post(f"/api/v1/memory/candidates/{candidate_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    before = client.get("/api/v1/memory/search?q=validation pitfall")
    assert before.status_code == 200
    assert {result["source"] for result in before.json()["results"]} == {"file", "graphiti"}

    reviewed = client.post(
        f"/api/v1/memory/candidates/{candidate_id}/review",
        json={
            "status": "stale",
            "reason": "Newer validation policy requires explicit evidence before retry.",
            "actor_employee_id": "clara",
        },
    )
    assert reviewed.status_code == 200
    reviewed_payload = reviewed.json()
    assert reviewed_payload["status"] == "stale"
    assert reviewed_payload["provenance"]["latest_review"]["status"] == "stale"
    assert reviewed_payload["provenance"]["not_applicable_at"]

    stale_candidates = client.get("/api/v1/memory/candidates?status=stale")
    assert stale_candidates.status_code == 200
    assert stale_candidates.json()[0]["id"] == candidate_id

    approved_after = client.get("/api/v1/memory/approved")
    assert approved_after.status_code == 200
    assert approved_after.json() == []

    status_after = client.get("/api/v1/memory/status")
    assert status_after.status_code == 200
    assert status_after.json()["approved_count"] == 0

    after = client.get("/api/v1/memory/search?q=validation pitfall")
    assert after.status_code == 200
    assert after.json()["results"] == []

    approved_mirror = json.loads((workspace / ".aiteamos" / "memory" / "approved.json").read_text(encoding="utf-8"))
    assert approved_mirror[0]["id"] == candidate_id
    assert approved_mirror[0]["status"] == "stale"


def test_chat_proposes_memory_candidate_and_recalls_approved_memory(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-chat-1"

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

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

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
    assert settings.json()["backend"]["status"] == "ready"

    first = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请推进 Ticket SV-4321，并把 root cause 和验证结论沉淀下来。",
            "thread_id": "memory-chat-test",
            "target_employee_id": "clara",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert any(event["event"] == "memory.candidate.proposed" for event in first_payload["trace_events"])

    candidates = client.get("/api/v1/memory/candidates")
    assert candidates.status_code == 200
    assert len(candidates.json()) == 1
    candidate_id = candidates.json()[0]["id"]
    assert candidates.json()[0]["scope_kind"] == "ticket"
    assert candidates.json()[0]["scope_ref"] == "SV-4321"

    approved = client.post(f"/api/v1/memory/candidates/{candidate_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["graphiti_episode_id"] == "episode-chat-1"

    second = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，继续处理 SV-4321。",
            "thread_id": "memory-chat-test",
            "target_employee_id": "clara",
        },
    )
    assert second.status_code == 200
    assert (
        "1 local memory snippet(s)" in second.json()["reply"]
        or "1 条本地记忆片段" in second.json()["reply"]
    )
    context_loaded = next(event for event in second.json()["trace_events"] if event["event"] == "context.loaded")
    assert context_loaded["data"]["memory_count"] == 1
    recalled_refs = context_loaded["data"]["recalled_memory_refs"]
    assert recalled_refs[0]["memory_id"] == candidate_id
    assert recalled_refs[0]["graphiti_episode_id"] == "episode-chat-1"

    run_metadata = second.json()["run_metadata"]
    assert run_metadata["recalled_memory_refs"][0]["memory_id"] == candidate_id
    assert run_metadata["graphiti_episode_refs"][0]["graphiti_episode_id"] == "episode-chat-1"

    trace_path = workspace / second.json()["saved_paths"]["trace"]
    trace_events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    recorded = next(event for event in trace_events if event["event"] == "run.metadata.recorded")
    assert recorded["data"]["graphiti_episode_refs"][0]["graphiti_episode_id"] == "episode-chat-1"


def test_ticket_aware_candidate_approval_is_recalled_through_graphiti_in_chat(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-ticket-aware-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeSearchItem:
        uuid = "graphiti-result-ticket-aware-1"
        episode_uuid = "episode-ticket-aware-1"
        fact = "Approved memory: preserve root cause evidence for similar Ticket fixes."
        score = 0.93

        def __init__(self, provenance: dict):
            self.provenance = provenance

    class FakeGraphiti:
        instances: list["FakeGraphiti"] = []
        last_provenance: dict = {}

        def __init__(self, uri, user, password):
            self.uri = uri
            self.user = user
            self.password = password
            self.searches: list[dict] = []
            FakeGraphiti.instances.append(self)

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            marker = "AITeamOS provenance:\n"
            FakeGraphiti.last_provenance = json.loads(kwargs["episode_body"].split(marker, maxsplit=1)[1])
            return FakeAddResult()

        async def search(self, query, **kwargs):
            self.searches.append({"query": query, "kwargs": kwargs})
            if not FakeGraphiti.last_provenance:
                return []
            return [FakeSearchItem(FakeGraphiti.last_provenance)]

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

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

    first = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请处理 rd-0001，把 root cause 沉淀为可复用记忆。",
            "thread_id": "ticket-aware-memory",
            "target_employee_id": "clara",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    candidate_event = next(event for event in first_payload["trace_events"] if event["event"] == "memory.candidate.proposed")
    assert candidate_event["data"]["source_kind"] == "ticket_run"
    assert candidate_event["data"]["provenance"]["source_ticket_id"] == "rd-0001"
    assert candidate_event["data"]["provenance"]["source_run_id"] == first_payload["run_id"]
    assert candidate_event["data"]["provenance"]["source_trace_path"] == first_payload["saved_paths"]["trace"]
    assert "why_should_be_remembered" in candidate_event["data"]["provenance"]
    assert first_payload["run_metadata"]["memory_candidate_refs"][0]["candidate_id"] == candidate_event["data"]["candidate_id"]
    assert first_payload["run_metadata"]["learning_summary"]["source_ticket_id"] == "rd-0001"
    assert first_payload["run_metadata"]["learning_summary"]["future_recall_query_hints"]
    assert first_payload["run_metadata"]["learning_summary"]["new_candidate_count"] == 1
    assert "Memory candidate" in first_payload["run_metadata"]["learning_summary"]["clara_summary"]

    candidates = client.get("/api/v1/memory/candidates")
    assert candidates.status_code == 200
    candidate = candidates.json()[0]
    assert candidate["scope_kind"] == "ticket"
    assert candidate["scope_ref"] == "rd-0001"
    assert candidate["source_kind"] == "ticket_run"
    assert "ticket-aware" in candidate["tags"]

    approved = client.post(f"/api/v1/memory/candidates/{candidate['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["graphiti_episode_id"] == "episode-ticket-aware-1"

    second = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，继续处理 rd-0001 root cause。",
            "thread_id": "ticket-aware-memory",
            "target_employee_id": "clara",
        },
    )
    assert second.status_code == 200
    second_payload = second.json()
    recall_event = next(event for event in second_payload["trace_events"] if event["event"] == "memory.recall.completed")
    assert recall_event["data"]["graphiti_result_count"] == 1
    assert recall_event["data"]["ticket_keys"] == ["rd-0001"]
    assert recall_event["data"]["graphiti_recalled_memory_refs"][0]["memory_id"] == candidate["id"]
    assert recall_event["data"]["graphiti_recalled_memory_refs"][0]["graphiti_episode_id"] == "episode-ticket-aware-1"

    context_loaded = next(event for event in second_payload["trace_events"] if event["event"] == "context.loaded")
    recalled_ref = context_loaded["data"]["recalled_memory_refs"][0]
    assert recalled_ref["memory_id"] == candidate["id"]
    assert recalled_ref["graphiti_recalled"] is True
    assert recalled_ref["graphiti_result_id"] == "graphiti-result-ticket-aware-1"

    run_metadata = second_payload["run_metadata"]
    assert run_metadata["recalled_memory_refs"][0]["memory_id"] == candidate["id"]
    assert run_metadata["graphiti_episode_refs"][0]["graphiti_episode_id"] == "episode-ticket-aware-1"
    usage_ref = run_metadata["memory_usage_refs"][0]
    assert usage_ref["memory_id"] == candidate["id"]
    assert usage_ref["source_run_id"] == second_payload["run_id"]
    assert usage_ref["source_ticket_ids"] == ["rd-0001"]
    assert usage_ref["graphiti_recalled"] is True
    assert usage_ref["usefulness_status"] == "unreviewed"
    assert run_metadata["learning_effectiveness"]["recalled_asset_count"] == 1

    usage_event = next(event for event in second_payload["trace_events"] if event["event"] == "memory.recall.usage_recorded")
    assert usage_event["data"]["usage_refs"][0]["usage_id"] == usage_ref["usage_id"]

    learning_summary = run_metadata["learning_summary"]
    assert learning_summary["used_approved_asset_count"] == 1
    assert learning_summary["recalled_assets"][0]["memory_id"] == candidate["id"]
    assert learning_summary["recalled_assets"][0]["usage_id"] == usage_ref["usage_id"]
    assert learning_summary["recalled_assets"][0]["graphiti_recalled"] is True
    assert learning_summary["source_ticket_id"] == "rd-0001"
    assert learning_summary["next_round_guidance"]
    assert "approved Memory" in learning_summary["clara_summary"]
    summary_event = next(event for event in second_payload["trace_events"] if event["event"] == "learning.summary.recorded")
    assert summary_event["data"]["used_approved_asset_count"] == 1

    approved_after_recall = client.get("/api/v1/memory/approved")
    assert approved_after_recall.status_code == 200
    approved_memory = approved_after_recall.json()[0]
    usage_history = approved_memory["provenance"]["usage_history"]
    assert usage_history[0]["usage_id"] == usage_ref["usage_id"]
    assert usage_history[0]["source_run_id"] == second_payload["run_id"]
    assert usage_history[0]["source_trace_path"] == second_payload["saved_paths"]["trace"]
    assert approved_memory["provenance"]["usage_summary"]["recall_count"] == 1

    usefulness = client.post(
        f"/api/v1/memory/candidates/{candidate['id']}/usage/{usage_ref['usage_id']}/review",
        json={
            "usefulness_status": "useful",
            "reviewer_employee_id": "pv",
            "reason": "The recalled memory guided the follow-up Ticket context.",
        },
    )
    assert usefulness.status_code == 200
    reviewed_memory = usefulness.json()
    assert reviewed_memory["provenance"]["usage_history"][0]["usefulness_status"] == "useful"
    assert reviewed_memory["provenance"]["usage_history"][0]["reviewer_employee_id"] == "pv"
    assert reviewed_memory["provenance"]["usage_summary"]["useful_count"] == 1
    assert FakeGraphiti.instances[-1].searches[-1]["kwargs"]["group_ids"] == ["aiteamos-test"]
