"""Local work item routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .work_item_service import (
    WorkItem,
    WorkItemCreateRequest,
    WorkItemReportRequest,
    add_work_item_report,
    create_work_item,
    get_work_item,
    list_work_items,
)

router = APIRouter(prefix="/api/v1/work-items", tags=["work-items"])


@router.get("", response_model=list[WorkItem])
async def get_work_items(status: str | None = None) -> list[WorkItem]:
    return list_work_items(status=status)


@router.post("", response_model=WorkItem)
async def post_work_item(request: WorkItemCreateRequest) -> WorkItem:
    return create_work_item(request)


@router.get("/{work_item_id}", response_model=WorkItem)
async def get_work_item_detail(work_item_id: str) -> WorkItem:
    item = get_work_item(work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Work item not found: {work_item_id}")
    return item


@router.post("/{work_item_id}/reports", response_model=WorkItem)
async def post_work_item_report(work_item_id: str, request: WorkItemReportRequest) -> WorkItem:
    try:
        return add_work_item_report(work_item_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Work item not found: {work_item_id}") from exc
