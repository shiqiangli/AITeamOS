"""Knowledge routes for docs, memories, decisions, and review queue."""

from __future__ import annotations

from fastapi import APIRouter, Query

from .knowledge_service import (
    DecisionCreateRequest,
    DecisionRecord,
    KnowledgeDocSummary,
    KnowledgeSearchResponse,
    KnowledgeStatusResponse,
    ReviewQueueItem,
    create_decision,
    knowledge_status,
    list_decisions,
    list_docs,
    review_queue_items,
    search_knowledge_sync,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/status", response_model=KnowledgeStatusResponse)
async def get_knowledge_status() -> KnowledgeStatusResponse:
    return knowledge_status()


@router.get("/docs", response_model=list[KnowledgeDocSummary])
async def get_knowledge_docs() -> list[KnowledgeDocSummary]:
    return list_docs()


@router.get("/decisions", response_model=list[DecisionRecord])
async def get_knowledge_decisions() -> list[DecisionRecord]:
    return list_decisions()


@router.post("/decisions", response_model=DecisionRecord)
async def post_knowledge_decision(request: DecisionCreateRequest) -> DecisionRecord:
    return create_decision(request)


@router.get("/review-queue", response_model=list[ReviewQueueItem])
async def get_knowledge_review_queue() -> list[ReviewQueueItem]:
    return review_queue_items()


@router.get("/search", response_model=KnowledgeSearchResponse)
async def get_knowledge_search(
    q: str = Query("", alias="q"),
    limit: int = 10,
) -> KnowledgeSearchResponse:
    return search_knowledge_sync(q, limit=limit)
