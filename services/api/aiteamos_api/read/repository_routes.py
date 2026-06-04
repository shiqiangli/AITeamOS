"""Code repository registry routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from .repository_service import (
    CodeRepository,
    CodeRepositoryStatus,
    CodeRepositoryUpsertRequest,
    code_repository_status,
    delete_code_repository,
    get_code_repository,
    list_code_repositories,
    upsert_code_repository,
)

router = APIRouter(prefix="/api/v1/code-repositories", tags=["code-repositories"])


@router.get("/status", response_model=CodeRepositoryStatus)
async def get_code_repository_status() -> CodeRepositoryStatus:
    return code_repository_status()


@router.get("", response_model=list[CodeRepository])
async def get_code_repositories() -> list[CodeRepository]:
    return list_code_repositories()


@router.post("", response_model=CodeRepository)
async def post_code_repository(request: CodeRepositoryUpsertRequest) -> CodeRepository:
    try:
        return upsert_code_repository(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{repo_id}", response_model=CodeRepository)
async def get_code_repository_detail(repo_id: str) -> CodeRepository:
    item = get_code_repository(repo_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Code repository not found: {repo_id}")
    return item


@router.put("/{repo_id}", response_model=CodeRepository)
async def put_code_repository(repo_id: str, request: CodeRepositoryUpsertRequest) -> CodeRepository:
    try:
        return upsert_code_repository(request, existing_id=repo_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Code repository not found: {repo_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{repo_id}", status_code=204)
async def delete_code_repository_route(repo_id: str) -> Response:
    try:
        delete_code_repository(repo_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Code repository not found: {repo_id}") from exc
    return Response(status_code=204)
