#!/usr/bin/env python3
"""Emit deterministic Asset provenance evidence through existing services."""

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
SMOKE_SCHEMA = "aiteamos.asset_provenance_eval_smoke.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Asset provenance smoke evidence.")
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
    from aiteamos_api.read import memory_service
    from aiteamos_api.read.asset_candidate_service import (
        AssetRecord,
        list_asset_records,
        project_asset_record_relationships_to_graphiti,
        upsert_asset_record,
    )
    from aiteamos_api.read.memory_service import (
        GraphitiSettingsUpdateRequest,
        MemoryCandidateCreateRequest,
        MemoryCandidateReviewRequest,
        approve_memory_candidate,
        create_memory_candidate,
        review_memory_candidate,
        search_memory,
        update_graphiti_settings,
    )

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    os.environ["AITEAMOS_GRAPHITI_PASSWORD"] = "neo4j-test-password"
    os.environ.setdefault("OPENAI_API_KEY", "openai-test-key")
    memory_service.Graphiti = _FakeGraphiti  # type: ignore[attr-defined]
    memory_service.EpisodeType = _FakeEpisodeType  # type: ignore[attr-defined]
    _FakeGraphiti.indexed_episodes = []
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    old_asset = upsert_asset_record(
        AssetRecord(
            id="asset-provenance-old-guidance",
            asset_type="solution",
            title="Old runtime guidance",
            content="Old runtime guidance: retry provider work without checking stale Asset relationships.",
            status="approved",
            scope_kind="ticket",
            scope_ref="rd-asset-provenance",
            owner_employee_id="alex",
            source_kind="ticket_report",
            source_ref="report-asset-provenance-old",
            provenance={
                "source_ticket_id": "rd-asset-provenance",
                "source_employee_id": "alex",
                "source_run_id": "run-asset-provenance-old",
                "source_report_id": "report-asset-provenance-old",
                "evidence_id": "evidence-asset-provenance-old",
            },
            created_at=timestamp,
            updated_at=timestamp,
        ),
        workspace_dir=workspace_root,
    )
    new_asset = upsert_asset_record(
        AssetRecord(
            id="asset-provenance-new-guidance",
            asset_type="solution",
            title="New runtime guidance",
            content="New runtime guidance supersedes the old provider retry guidance with governed stale cleanup.",
            status="approved",
            scope_kind="ticket",
            scope_ref="rd-asset-provenance",
            owner_employee_id="alex",
            source_kind="ticket_report",
            source_ref="report-asset-provenance-new",
            provenance={
                "source_ticket_id": "rd-asset-provenance",
                "source_employee_id": "alex",
                "source_run_id": "run-asset-provenance-new",
                "source_report_id": "report-asset-provenance-new",
                "evidence_id": "evidence-asset-provenance-new",
            },
            relationships=[
                {
                    "type": "supersedes",
                    "target_asset_id": old_asset.id,
                    "reason": "New guidance replaces older provider retry guidance.",
                    "confidence": 0.94,
                }
            ],
            created_at=timestamp,
            updated_at=timestamp,
        ),
        workspace_dir=workspace_root,
    )
    relationship_projection = await project_asset_record_relationships_to_graphiti(
        new_asset.id,
        workspace_dir=workspace_root,
    )
    relationship_projection_again = await project_asset_record_relationships_to_graphiti(
        new_asset.id,
        workspace_dir=workspace_root,
    )
    projected_record = next(item for item in list_asset_records(workspace_dir=workspace_root) if item.id == new_asset.id)
    relationship_id = _relationship_id(relationship_projection.model_dump(mode="json"))
    relationship_search = await search_memory(
        query=relationship_id,
        employee_id="alex",
        ticket_key="rd-asset-provenance",
        include_graphiti=True,
        limit=5,
    )

    memory = create_memory_candidate(
        MemoryCandidateCreateRequest(
            content="Old validation pitfall: retry validation without evidence.",
            source_kind="ticket_summary",
            source_ref="traces/run-stale-provenance",
            scope_kind="ticket",
            scope_ref="rd-asset-provenance",
            memory_type="lesson",
            confidence=0.8,
            employee_ids=["clara"],
            tags=["validation", "stale-cleanup"],
            provenance={
                "source_ticket_id": "rd-asset-provenance",
                "source_employee_id": "clara",
                "source_run_id": "run-stale-provenance",
                "source_ref": "traces/run-stale-provenance",
            },
        )
    )
    approved = await approve_memory_candidate(memory.id)
    before_stale = await search_memory(
        query="old validation pitfall",
        employee_id="clara",
        ticket_key="rd-asset-provenance",
        include_graphiti=True,
        limit=5,
    )
    stale = review_memory_candidate(
        approved.id,
        MemoryCandidateReviewRequest(
            status="stale",
            reason="Newer validation policy requires explicit evidence before retry.",
            actor_employee_id="clara",
        ),
    )
    after_stale = await search_memory(
        query="old validation pitfall",
        employee_id="clara",
        ticket_key="rd-asset-provenance",
        include_graphiti=True,
        limit=5,
    )
    before_ids = [item.id for item in before_stale.results]
    after_active_ids = [item.id for item in after_stale.results]
    after_excluded_ids = [str(item.get("asset_id") or item.get("memory_id") or item.get("id") or "") for item in after_stale.excluded_results]
    relationship_graphiti_refs = _records(projected_record.provenance.get("graphiti_relationships"))
    checks = [
        _check("relationship.status", relationship_projection.status, "ingested"),
        _check_int("relationship.ingested_count", len(relationship_projection.ingested_relationships), 1),
        _check("relationship.repeated_status", relationship_projection_again.status, "skipped"),
        _check_int("relationship.skipped_count", len(relationship_projection_again.skipped_relationships), 1),
        _check_present("relationship.id", relationship_id),
        _check_contains("relationship.search_results", [item.source_kind for item in relationship_search.results], "durable_asset_relationship"),
        _check_int("asset_record.graphiti_relationship_count", len(relationship_graphiti_refs), 1),
        _check_contains("stale.before_ids", before_ids, approved.id),
        _check_absent("stale.after_active_ids", after_active_ids, approved.id),
        _check_contains("stale.after_excluded_ids", after_excluded_ids, approved.id),
        _check("stale.status", stale.status, "stale"),
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "workspace_dir": str(workspace_root),
        "checks": checks,
        "summary": {
            "source_asset_id": new_asset.id,
            "target_asset_id": old_asset.id,
            "relationship_id": relationship_id,
            "relationship_projection_status": relationship_projection.status,
            "relationship_ingested_count": len(relationship_projection.ingested_relationships),
            "relationship_repeated_status": relationship_projection_again.status,
            "relationship_skipped_count": len(relationship_projection_again.skipped_relationships),
            "asset_record_graphiti_relationship_count": len(relationship_graphiti_refs),
            "relationship_search_result_count": len(relationship_search.results),
            "stale_memory_id": approved.id,
            "stale_review_status": stale.status,
            "stale_before_result_count": len(before_stale.results),
            "stale_after_active_count": len(after_stale.results),
            "stale_after_excluded_count": len(after_stale.excluded_results),
            "stale_active_filtered": approved.id not in after_active_ids and approved.id in after_excluded_ids,
        },
    }


class _FakeEpisodeType:
    message = "message"
    text = "text"


class _FakeEpisode:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid


class _FakeAddResult:
    def __init__(self, episode_id: str) -> None:
        self.episode = _FakeEpisode(episode_id)


class _FakeSearchItem:
    def __init__(self, provenance: dict[str, Any]) -> None:
        asset_id = str(provenance.get("asset_id") or provenance.get("memory_id") or "graphiti-result")
        self.uuid = f"graphiti-{asset_id}"
        self.source_node_uuid = self.uuid
        self.episode_uuid = f"episode-{asset_id}"
        self.fact = str(provenance.get("content") or provenance.get("source_ref") or asset_id)
        self.score = 0.97
        self.provenance = provenance


class _FakeGraphiti:
    indexed_episodes: list[dict[str, Any]] = []

    def __init__(self, uri, user, password) -> None:
        self.uri = uri
        self.user = user
        self.password = password

    async def build_indices_and_constraints(self):
        return None

    async def add_episode(self, **kwargs):
        marker = "AITeamOS provenance:\n"
        provenance = json.loads(str(kwargs["episode_body"]).split(marker, maxsplit=1)[1])
        content = str(kwargs.get("episode_body") or "")
        asset_id = str(provenance.get("asset_id") or "asset")
        stored = {**provenance, "content": content}
        self.indexed_episodes.append(stored)
        return _FakeAddResult(f"episode-{asset_id}")

    async def search(self, query, **kwargs):
        query_text = str(query or "").lower()
        matches = [
            item
            for item in self.indexed_episodes
            if query_text in str(item.get("asset_id") or "").lower()
            or all(term in str(item.get("content") or "").lower() for term in query_text.split() if term)
        ]
        return [_FakeSearchItem(item) for item in (matches or self.indexed_episodes[:1])]

    async def close(self):
        return None


def _relationship_id(payload: dict[str, Any]) -> str:
    ingested = _records(payload.get("ingested_relationships"))
    if ingested:
        return str(ingested[0].get("relationship_id") or "")
    skipped = _records(payload.get("skipped_relationships"))
    return str(skipped[0].get("asset_id") or "") if skipped else ""


def _check(name: str, actual: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": expected, "passed": actual == expected}


def _check_int(name: str, actual: Any, expected: int) -> dict[str, Any]:
    try:
        normalized = int(actual)
    except (TypeError, ValueError):
        normalized = -1
    return _check(name, normalized, expected)


def _check_present(name: str, actual: Any) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": "present", "passed": bool(actual)}


def _check_contains(name: str, actual: list[str], expected: str) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": expected, "passed": expected in actual}


def _check_absent(name: str, actual: list[str], expected: str) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": f"absent:{expected}", "passed": expected not in actual}


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
