"""Asset proposal nodes for the AITeamOS Workbench graph."""

from typing import Any

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, record, text


def propose_asset_candidates(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    response = record(state.get("aiteamos_chat_response"))
    metadata = record(response.get("run_metadata"))
    execution = record(metadata.get("execution"))
    result = record(execution.get("result"))
    candidates: list[dict[str, Any]] = []
    memory_candidate_count = result.get("memory_candidate_count")
    if isinstance(memory_candidate_count, int) and memory_candidate_count > 0:
        candidates.append(
            {
                "kind": "memory_candidate",
                "count": memory_candidate_count,
                "source_run_id": text(response.get("run_id")),
                "review_required": True,
            }
        )
    return {
        "asset_candidates": candidates,
        "asset_proposal_summary": {
            "node": "propose_asset_candidates",
            "candidate_count": len(candidates),
            "memory_candidate_count": memory_candidate_count if isinstance(memory_candidate_count, int) else 0,
            "review_required": any(bool(candidate.get("review_required")) for candidate in candidates),
        },
        "runtime_status": {
            **record(state.get("runtime_status")),
            "current_node": "propose_asset_candidates",
        },
    }
