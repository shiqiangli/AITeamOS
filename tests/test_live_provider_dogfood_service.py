from __future__ import annotations

import asyncio
import os

import pytest

from aiteamos_api.read import live_provider_dogfood_service, memory_service
from aiteamos_api.read.live_provider_dogfood_service import (
    LiveProviderDogfoodRequest,
    LiveProviderDogfoodService,
)
from aiteamos_api.read.memory_service import MemoryCandidateCreateRequest
from aiteamos_api.read.repository_service import CodeRepositoryUpsertRequest, upsert_code_repository
from aiteamos_api.read.runtime_executor_smoke_service import RuntimeExecutorDogfoodResponse
from aiteamos_api.read.ticket_service import TicketBackendSettingsUpdateRequest, update_ticket_backend_settings
from aiteamos_api.read.ticket_service import (
    TicketCreateRequest,
    TicketHandoffRequest,
    create_ticket,
    record_ticket_handoff,
)


async def _passed_provider_smoke():
    return {
        "status": "passed",
        "provider_smoke": {
            "results": [
                {"provider_id": "ticket:plane", "status": "passed"},
                {"provider_id": "memory:graphiti", "status": "passed"},
            ]
        },
    }


@pytest.mark.asyncio
async def test_live_provider_dogfood_defaults_to_dry_run_without_mutating(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", raising=False)
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    called = {"workbench": False, "runtime": False}

    async def fake_workbench(request, ticket):
        called["workbench"] = True
        return {}

    async def fake_runtime(request, ticket):
        called["runtime"] = True
        return RuntimeExecutorDogfoodResponse(status="completed")

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=_passed_provider_smoke,
        workbench_runner=fake_workbench,
        runtime_dogfood_runner=fake_runtime,
    ).run(LiveProviderDogfoodRequest())

    assert response.status == "dry_run"
    assert response.profile == "core_loop"
    assert response.dry_run is True
    assert response.mutation_gate["open"] is False
    assert response.executor_preflight["executor_id"] == "langgraph"
    assert response.executor_preflight["require_repo_write_executor"] is False
    assert response.executor_preflight["blockers"] == []
    assert response.blockers[0]["reason"] == "live_provider_dogfood_not_confirmed"
    assert called == {"workbench": False, "runtime": False}
    assert not (tmp_path / ".aiteamos" / "tickets" / "index.json").exists()


@pytest.mark.asyncio
async def test_live_provider_dogfood_provider_smoke_timeout_stays_non_mutating(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    async def slow_provider_smoke():
        await asyncio.sleep(60)

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=slow_provider_smoke,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            provider_smoke_timeout_seconds=0.01,
            require_repo_write_executor=False,
        )
    )

    assert response.status == "blocked"
    assert response.provider_smoke["status"] == "timeout"
    assert response.blockers[0]["reason"] == "provider_smoke_timeout"
    assert not (tmp_path / ".aiteamos" / "tickets" / "index.json").exists()


@pytest.mark.asyncio
async def test_live_provider_dogfood_execute_blocks_non_repo_write_executor_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))
    called = {"provider_smoke": False}

    async def provider_smoke():
        called["provider_smoke"] = True
        return await _passed_provider_smoke()

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=provider_smoke,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            profile="repo_write_adapter",
            executor_id="local_tool",
            require_provider_smoke=True,
        )
    )

    assert response.status == "blocked"
    assert response.executor_preflight["blockers"][0]["reason"] == "runtime_executor_lacks_repo_write"
    assert response.blockers[0]["reason"] == "runtime_executor_lacks_repo_write"
    assert called["provider_smoke"] is False
    assert not (tmp_path / ".aiteamos" / "tickets" / "index.json").exists()


@pytest.mark.asyncio
async def test_live_provider_dogfood_readiness_reports_codex_repo_write_candidate_and_provider_blockers(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("OPENHANDS_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCODE_BIN", raising=False)
    fake_codex = tmp_path / "codex"
    fake_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_codex.chmod(0o755)
    monkeypatch.setenv("CODEX_CLI_BIN", str(fake_codex))
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="plane"))

    response = await LiveProviderDogfoodService(workspace_dir=tmp_path).readiness(
        LiveProviderDogfoodRequest(execute=True, profile="repo_write_adapter", executor_id="local_tool")
    )

    assert response.status == "blocked"
    assert response.profile == "repo_write_adapter"
    assert response.selected_executor_id == "local_tool"
    assert response.selected_executor_preflight["blockers"][0]["reason"] == "runtime_executor_lacks_repo_write"
    assert response.summary["repo_write_ready_count"] == 1
    assert response.provider_prerequisites["provider_smoke"]["status"] == "not_run"
    candidates = {item["executor_id"]: item for item in response.repo_write_executor_candidates}
    assert {"claude_code", "codex_cli", "cursor"} <= set(candidates)
    assert candidates["codex_cli"]["status"] == "ready"
    blocker_reasons = {item["reason"] for item in response.blockers}
    assert "runtime_executor_lacks_repo_write" in blocker_reasons
    assert "no_ready_repo_write_runtime_executor" not in blocker_reasons
    assert "ticket_provider_not_ready" in blocker_reasons
    assert "memory_provider_not_ready" in blocker_reasons
    assert "live_provider_dogfood_not_confirmed" in blocker_reasons


@pytest.mark.asyncio
async def test_live_provider_dogfood_core_loop_readiness_defaults_to_langgraph_without_repo_write(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", raising=False)
    monkeypatch.delenv("PLANE_API_KEY", raising=False)
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    response = await LiveProviderDogfoodService(workspace_dir=tmp_path).readiness()

    assert response.profile == "core_loop"
    assert response.selected_executor_id == "langgraph"
    assert response.require_repo_write_executor is False
    assert response.selected_executor_preflight["require_repo_write_executor"] is False
    assert response.summary["ticket_backend_mode"] == "local_file"
    assert response.summary["plane_ticket_backend_selected"] is False
    assert response.summary["plane_ticket_backend_setup_status"] == "setup_blocked"
    assert response.summary["plane_ticket_backend_setup_required"] == [
        "PUT /api/v1/tickets/backend mode=plane",
        ".aiteamos/tickets/backend.json mode=plane",
        "plane_workspace_slug",
        "plane_project_id",
        "PLANE_API_KEY",
    ]
    plane_setup = response.provider_prerequisites["plane_ticket_backend_setup"]
    assert plane_setup["workspace_configured"] is False
    assert plane_setup["project_configured"] is False
    assert plane_setup["api_key_configured"] is False
    assert plane_setup["code_repository_scope_status"] == "missing"
    assert plane_setup["code_repository_scope_candidate_count"] == 0
    assert plane_setup["code_repository_scope_missing_count"] == 0
    blocker_reasons = {item["reason"] for item in response.blockers}
    assert "runtime_executor_lacks_repo_write" not in blocker_reasons
    assert "no_ready_repo_write_runtime_executor" not in blocker_reasons
    assert "plane_ticket_backend_not_selected" in blocker_reasons
    assert "live_provider_dogfood_not_confirmed" in blocker_reasons


@pytest.mark.asyncio
async def test_live_provider_dogfood_readiness_reports_code_repository_plane_scope_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", raising=False)
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    upsert_code_repository(
        CodeRepositoryUpsertRequest(
            name="AITeamOS",
            provider="local",
            location=str(repo),
            enabled=True,
        )
    )
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    response = await LiveProviderDogfoodService(workspace_dir=tmp_path).readiness()

    plane_setup = response.provider_prerequisites["plane_ticket_backend_setup"]
    assert response.summary["plane_ticket_scope_status"] == "incomplete"
    assert response.summary["plane_ticket_scope_candidate_count"] == 0
    assert response.summary["plane_ticket_scope_missing_count"] == 1
    assert plane_setup["code_repository_scope_status"] == "incomplete"
    assert plane_setup["code_repository_scope_missing"][0]["repository_name"] == "AITeamOS"
    assert plane_setup["code_repository_scope_missing"][0]["workspace_configured"] is False
    assert plane_setup["code_repository_scope_missing"][0]["project_configured"] is False


@pytest.mark.asyncio
async def test_live_provider_dogfood_composes_workbench_assets_graphiti_and_recall(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_ENABLED", "true")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_URI", "bolt://localhost:7687")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_USER", "neo4j")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str) -> None:
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str) -> None:
            self.episode = FakeEpisode(episode_id)

    class FakeSearchResult:
        def __init__(self, *, fact: str, episode_uuid: str) -> None:
            self.uuid = "graphiti-live-dogfood-result"
            self.source_node_uuid = self.uuid
            self.episode_uuid = episode_uuid
            self.fact = fact
            self.score = 0.99

    class FakeGraphiti:
        episodes: list[dict[str, str]] = []

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            episode_id = f"episode-live-dogfood-{len(self.episodes) + 1}"
            self.episodes.append(
                {
                    "episode_id": episode_id,
                    "name": str(kwargs.get("name") or ""),
                    "episode_body": str(kwargs.get("episode_body") or ""),
                }
            )
            return FakeAddResult(episode_id)

        async def search(self, query, **kwargs):
            durable_episode = next(
                (episode for episode in reversed(self.episodes) if episode["name"].startswith("AITeamOS durable asset")),
                self.episodes[-1],
            )
            return [
                FakeSearchResult(
                    fact=durable_episode["episode_body"],
                    episode_uuid=durable_episode["episode_id"],
                )
            ]

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)

    async def fake_workbench(request, ticket):
        return {
            "thread_id": "lg-live-dogfood-thread",
            "active_ticket": {"id": ticket.id},
            "runtime_status": {"status": "completed", "graph": request.assistant_id},
        }

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=_passed_provider_smoke,
        workbench_runner=fake_workbench,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            profile="core_loop",
            executor_id="langgraph",
            require_provider_smoke=True,
        )
    )

    assert response.status == "completed"
    assert response.profile == "core_loop"
    assert response.summary["ticket_id"].startswith("ops-")
    assert response.summary["provider"] == "local_file"
    assert response.summary["dogfood_profile"] == "core_loop"
    assert response.summary["langgraph_thread_id"] == "lg-live-dogfood-thread"
    assert response.summary["memory_candidate_ids"]
    assert response.summary["asset_record_ids"] == response.summary["memory_candidate_ids"]
    assert response.summary["graphiti_projection_statuses"] == ["ingested"]
    assert response.summary["graphiti_recall_count"] == 1
    assert response.asset_reviews[0]["asset"]["status"] == "approved"
    assert response.graphiti_projections[0]["ingested_asset"]["episode_id"] == "episode-live-dogfood-2"
    assert any(item["source"] == "graphiti" for item in response.recall["results"])


@pytest.mark.asyncio
async def test_live_provider_dogfood_requires_natural_handoff_when_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_ENABLED", "false")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    async def fake_workbench(request, ticket):
        return {
            "thread_id": "lg-natural-handoff-thread",
            "active_ticket": {"id": ticket.id},
            "runtime_status": {"status": "completed", "graph": request.assistant_id},
            "handoff_decision": {
                "should_handoff": True,
                "target_employee_id": "alex",
                "target_role": "AI RD / Implementer",
                "lane": "rd",
                "reason": "Goal asks for backend runtime ownership.",
            },
            "handoff_summary": {
                "status": "durable_handoff_recorded",
                "to_employee_id": "alex",
                "lane": "rd",
                "handoff_ref_count": 1,
            },
            "ticket_handoff_refs": [
                {"kind": "ticket_handoff", "ticket_id": ticket.id, "to_employee_id": "alex"}
            ],
        }

    class FakeDump:
        def __init__(self, payload):
            self._payload = payload

        def model_dump(self, mode="json"):
            return self._payload

    projected_asset_ids: list[str] = []

    async def fake_project_asset_record_to_graphiti(asset_id: str):
        projected_asset_ids.append(asset_id)
        return FakeDump({"status": "ingested", "asset_id": asset_id})

    async def fake_approve_memory_candidate(memory_candidate_id: str):
        return FakeDump({"id": memory_candidate_id, "status": "approved"})

    async def fake_search_memory(**kwargs):
        asset_id = projected_asset_ids[-1] if projected_asset_ids else ""
        return FakeDump(
            {
                "results": [
                    {
                        "id": "graphiti-natural-handoff-result",
                        "source": "graphiti",
                        "provenance": {"asset_id": asset_id},
                    }
                ]
            }
        )

    monkeypatch.setattr(
        live_provider_dogfood_service,
        "project_asset_record_to_graphiti",
        fake_project_asset_record_to_graphiti,
    )
    monkeypatch.setattr(live_provider_dogfood_service, "approve_memory_candidate", fake_approve_memory_candidate)
    monkeypatch.setattr(live_provider_dogfood_service, "search_memory", fake_search_memory)

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=_passed_provider_smoke,
        workbench_runner=fake_workbench,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            profile="core_loop",
            executor_id="langgraph",
            require_provider_smoke=True,
            require_natural_handoff=True,
            expected_handoff_target_employee_id="alex",
        )
    )

    assert response.status == "completed"
    assert response.summary["natural_handoff"] is True
    assert response.summary["natural_handoff_required"] is True
    assert response.summary["handoff_status"] == "durable_handoff_recorded"
    assert response.summary["handoff_target_employee_id"] == "alex"
    assert response.summary["handoff_ref_count"] == 1
    assert response.runtime_dogfood["learning_delta"]["natural_handoff"]["complete"] is True


@pytest.mark.asyncio
async def test_live_provider_dogfood_blocks_when_required_natural_handoff_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    async def fake_workbench(request, ticket):
        return {
            "thread_id": "lg-no-handoff-thread",
            "active_ticket": {"id": ticket.id},
            "runtime_status": {"status": "completed", "graph": request.assistant_id},
        }

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=_passed_provider_smoke,
        workbench_runner=fake_workbench,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            profile="core_loop",
            executor_id="langgraph",
            require_provider_smoke=True,
            require_natural_handoff=True,
            expected_handoff_target_employee_id="alex",
        )
    )

    assert response.status == "blocked"
    assert response.blockers[0]["reason"] == "live_provider_natural_handoff_missing"
    assert response.summary["natural_handoff"] is False
    assert response.summary["natural_handoff_required"] is True
    assert response.summary["expected_handoff_target_employee_id"] == "alex"
    assert response.asset_reviews == []
    assert response.graphiti_projections == []


def test_live_provider_dogfood_execution_evidence_reads_nested_agent_server_state():
    evidence = live_provider_dogfood_service._workbench_execution_evidence(
        {
            "thread_id": "lg-nested-thread",
            "runtime_status": {"status": "completed", "current_node": "final_response"},
            "state": {
                "aiteamos_chat_response": {
                    "run_metadata": {
                        "execution": {
                            "status": "blocked",
                            "request_id": "run-nested-blocked",
                            "executor_id": "universal_employee_agent",
                            "result": {
                                "errors": [{"reason": "ingestion_blocked", "detail": "Plane 502"}],
                                "error_count": 1,
                            },
                        }
                    }
                }
            },
        }
    )

    assert evidence["status"] == "blocked"
    assert evidence["request_id"] == "run-nested-blocked"
    assert evidence["errors"][0]["reason"] == "ingestion_blocked"


def test_live_provider_dogfood_handoff_evidence_reads_ticket_ledger_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ledger-backed handoff Ticket",
            description="Natural handoff evidence can be recovered from Ticket ledger facts.",
            ticket_type="rd",
            assigned_employee_id="clara",
            assigned_role="AI Team OS Manager",
            source_thread_id="thread-ledger-handoff",
            source_run_id="seed-ledger-handoff",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    record_ticket_handoff(
        ticket.id,
        TicketHandoffRequest(
            to_employee_id="alex",
            to_role="AI RD / Implementer",
            from_employee_id="clara",
            from_role="AI Team OS Manager",
            content="Goal asks for implementation or engineering work.",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            source_run_id="run-ledger-handoff",
        ),
    )

    evidence = live_provider_dogfood_service._workbench_handoff_evidence(
        {
            "state": {
                "active_ticket": {"id": ticket.id},
                "runtime_status": {"status": "completed", "run_id": "run-ledger-handoff", "ticket_id": ticket.id},
                "handoff_decision": {
                    "should_handoff": True,
                    "target_employee_id": "alex",
                    "target_role": "AI RD / Implementer",
                },
                "handoff_summary": {
                    "status": "handoff_artifact_proposed",
                    "ticket_id": ticket.id,
                    "to_employee_id": "alex",
                    "handoff_ref_count": 0,
                },
                "ticket_handoff_refs": [],
            }
        },
        request=LiveProviderDogfoodRequest(require_natural_handoff=True, expected_handoff_target_employee_id="alex"),
    )

    assert evidence["complete"] is True
    assert evidence["status"] == "durable_handoff_recorded"
    assert evidence["target_employee_id"] == "alex"
    assert evidence["ref_count"] == 1
    assert evidence["ticket_handoff_refs"][0]["source"] == "ticket_ledger"


@pytest.mark.asyncio
async def test_live_provider_dogfood_blocks_when_workbench_execution_result_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    async def fake_workbench(request, ticket):
        return {
            "thread_id": "lg-plane-blocked-thread",
            "active_ticket": {"id": ticket.id},
            "runtime_status": {"status": "completed", "current_node": "final_response"},
            "handoff_decision": {
                "target_employee_id": "alex",
                "lane": "rd",
                "reason": "Backend runtime work needs RD ownership.",
            },
            "aiteamos_chat_response": {
                "run_metadata": {
                    "execution": {
                        "status": "blocked",
                        "request_id": "run-plane-blocked",
                        "executor_id": "universal_employee_agent",
                        "result": {
                            "errors": [
                                {
                                    "reason": "ingestion_blocked",
                                    "detail": "Plane Ticket Backend action blocker: 502",
                                }
                            ],
                            "error_count": 1,
                        },
                    }
                }
            },
        }

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=_passed_provider_smoke,
        workbench_runner=fake_workbench,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            profile="core_loop",
            executor_id="langgraph",
            require_provider_smoke=True,
            require_natural_handoff=True,
            expected_handoff_target_employee_id="alex",
        )
    )

    assert response.status == "blocked"
    assert response.blockers[0]["reason"] == "runtime_dogfood_not_completed"
    dogfood_blocker = response.blockers[0]["dogfood_blockers"][0]
    assert dogfood_blocker["reason"] == "core_loop_execution_not_completed"
    assert dogfood_blocker["workbench_execution_status"] == "blocked"
    assert dogfood_blocker["workbench_execution_errors"][0]["reason"] == "ingestion_blocked"
    assert response.runtime_dogfood["learning_delta"]["natural_handoff"]["target_employee_id"] == "alex"
    assert response.asset_reviews == []
    assert response.graphiti_projections == []


@pytest.mark.asyncio
async def test_live_provider_dogfood_blocks_agent_server_error_before_core_loop_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    async def fake_workbench(request, ticket):
        return {
            "thread_id": "lg-blocking-error-thread",
            "active_ticket": {"id": ticket.id},
            "runtime_status": {},
            "state": {
                "__error__": {
                    "error": "BlockingError",
                    "message": "Synchronous file I/O was called in the LangGraph Server event loop.",
                }
            },
        }

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=_passed_provider_smoke,
        workbench_runner=fake_workbench,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            profile="core_loop",
            executor_id="langgraph",
            require_provider_smoke=True,
        )
    )

    assert response.status == "blocked"
    assert response.blockers[0]["reason"] == "runtime_dogfood_not_completed"
    dogfood_blocker = response.blockers[0]["dogfood_blockers"][0]
    assert dogfood_blocker["reason"] == "core_loop_workbench_not_completed"
    assert dogfood_blocker["workbench_error"]["error"] == "BlockingError"
    assert response.ticket["reports"] == []
    assert response.asset_reviews == []
    assert response.graphiti_projections == []


@pytest.mark.asyncio
async def test_live_provider_dogfood_repo_write_adapter_uses_runtime_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_LIVE_PROVIDER_DOGFOOD", "1")
    update_ticket_backend_settings(TicketBackendSettingsUpdateRequest(mode="local_file"))

    called = {"runtime": False}

    async def fake_workbench(request, ticket):
        return {"thread_id": "repo-adapter-thread", "runtime_status": {"status": "completed"}}

    async def fake_runtime(request, ticket):
        called["runtime"] = True
        candidate = memory_service.create_memory_candidate(
            MemoryCandidateCreateRequest(
                content="Repo-write adapter dogfood remains optional conformance evidence.",
                source_kind="runtime_executor_dogfood",
                source_ref="repo-write-adapter",
                scope_kind="ticket",
                scope_ref=ticket.id,
                memory_type="summary",
                confidence=0.8,
                employee_ids=[request.worker_employee_id],
                tags=["repo-write-adapter"],
                provenance={"source_ticket_id": ticket.id, "source_run_id": "repo-write-adapter"},
            )
        )
        return RuntimeExecutorDogfoodResponse(
            status="completed",
            ticket=ticket.model_dump(mode="json"),
            approval={"id": "approval-repo-adapter", "status": "approved"},
            approved_run={"result": {"status": "completed", "executor_id": request.executor_id}},
            summary_report={"ticket_id": ticket.id},
            learning_delta={"dogfood_profile": "repo_write_adapter", "memory_candidate_ids": [candidate.id]},
        )

    response = await LiveProviderDogfoodService(
        workspace_dir=tmp_path,
        provider_smoke_runner=_passed_provider_smoke,
        workbench_runner=fake_workbench,
        runtime_dogfood_runner=fake_runtime,
    ).run(
        LiveProviderDogfoodRequest(
            execute=True,
            profile="repo_write_adapter",
            executor_id="local_tool",
            require_provider_smoke=True,
            require_repo_write_executor=False,
        )
    )

    assert called["runtime"] is True
    assert response.runtime_dogfood["learning_delta"]["dogfood_profile"] == "repo_write_adapter"
    assert response.runtime_dogfood["learning_delta"]["memory_candidate_ids"]
    assert response.summary["dogfood_profile"] == "repo_write_adapter"
