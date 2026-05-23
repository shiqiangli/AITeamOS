"""API-facing memory fabric boundary."""

from aiteamos_workspace import (
    approve_memory_proposal,
    archive_memory_binding,
    create_memory_binding,
    create_memory_entry,
    create_memory_grant,
    create_memory_store,
    mark_memory_entry_stale,
    reject_memory_proposal,
    repair_memory_proposal,
    share_memory,
    update_memory_entry,
    update_memory_proposal,
    verify_memory_entry,
)
from aiteamos_workspace.memory_gate import memory_proposal_review_queue
from aiteamos_workspace.queries import search_memory_for_tool
from aiteamos_workspace.tool_mutations import grant_memory_for_tool, propose_memory_for_tool, share_memory_for_tool

__all__ = [
    "approve_memory_proposal",
    "archive_memory_binding",
    "create_memory_binding",
    "create_memory_entry",
    "create_memory_grant",
    "create_memory_store",
    "grant_memory_for_tool",
    "mark_memory_entry_stale",
    "memory_proposal_review_queue",
    "propose_memory_for_tool",
    "reject_memory_proposal",
    "repair_memory_proposal",
    "search_memory_for_tool",
    "share_memory",
    "share_memory_for_tool",
    "update_memory_entry",
    "update_memory_proposal",
    "verify_memory_entry",
]
