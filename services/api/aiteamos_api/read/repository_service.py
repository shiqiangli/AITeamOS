"""File-backed code repository registry.

AITeamOS only needs a thin map from Ticket and evidence scope to code repository
locations. Full repository intelligence should live behind repo tools,
Tool Connectors, or AI Engines.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_REMOTE_RE = re.compile(r"^(https?://|ssh://|git@|[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:).+")
_IGNORED_DIRS = {
    ".aiteamos",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
_MAX_SEARCH_FILES = 800
_MAX_SEARCH_FILE_BYTES = 256_000
_MAX_READ_BYTES = 32_000
_TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


class CodeRepository(BaseModel):
    id: str
    name: str
    provider: str = "local"
    location: str
    default_branch: str = ""
    plane_workspace_slug: str = ""
    plane_project_id: str = ""
    description: str = ""
    enabled: bool = True
    status: str = "unknown"
    detail: str = ""
    git_detected: bool = False
    current_branch: str = ""
    created_at: str
    updated_at: str
    saved_path: str = ""


class CodeRepositoryUpsertRequest(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    provider: str = "local"
    location: str = Field(min_length=1)
    default_branch: str = ""
    plane_workspace_slug: str = ""
    plane_project_id: str = ""
    description: str = ""
    enabled: bool = True


class CodeRepositoryStatus(BaseModel):
    repository_count: int
    enabled_count: int
    ready_count: int
    local_count: int
    remote_count: int
    plane_scope_status: str = ""
    plane_scope_detail: str = ""
    plane_scope_candidate_count: int = 0
    plane_scope_missing_count: int = 0
    plane_scope_setup_action: str = ""
    plane_scope_candidates: list[dict[str, Any]] = Field(default_factory=list)
    plane_scope_missing: list[dict[str, Any]] = Field(default_factory=list)
    plane_scope_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class CodeRepositoryFileMatch(BaseModel):
    path: str
    line: int
    excerpt: str


class CodeRepositoryFileContent(BaseModel):
    path: str
    content: str
    truncated: bool = False


class CodeRepositoryInspection(BaseModel):
    repository: CodeRepository
    query: str = ""
    status: str
    detail: str
    matches: list[CodeRepositoryFileMatch] = Field(default_factory=list)
    files: list[CodeRepositoryFileContent] = Field(default_factory=list)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _registry_path() -> Path:
    return _workspace_dir() / "code_repositories.json"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _read_rows() -> list[dict[str, Any]]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_items(items: list[CodeRepository]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump(mode="json") for item in sorted(items, key=lambda repo: repo.name.lower())]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip().lower()).strip("-")
    return slug[:72] or "repo"


def _normalize_provider(value: str) -> str:
    provider = value.strip().lower() or "local"
    if provider not in {"local", "github", "gitea", "gitlab", "generic_git"}:
        raise ValueError(f"Unsupported repository provider: {value}")
    return provider


def _normalize_id(value: str | None, fallback: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        candidate = f"repo-{_slug(fallback)}-{uuid4().hex[:6]}"
    if not _SAFE_ID_RE.fullmatch(candidate):
        raise ValueError(f"Invalid repository id: {candidate}")
    return candidate


def _local_path(location: str) -> Path:
    path = Path(location).expanduser()
    if not path.is_absolute():
        path = _workspace_root() / path
    return path.resolve()


def _repository_root(repository: CodeRepository) -> Path:
    if repository.provider != "local":
        raise ValueError("Only local repositories can be inspected without a Tool Connector or AI Engine handoff.")
    root = _local_path(repository.location)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Local repository is not available: {root}")
    return root


def _safe_relative_path(root: Path, value: str) -> Path:
    raw = value.strip().lstrip("/")
    if not raw or raw in {".", "./"}:
        raise ValueError("File path is empty.")
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path is outside repository: {value}") from exc
    return candidate


def _repo_relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_DIRS for part in path.parts)


def _is_probably_text(path: Path, data: bytes) -> bool:
    if b"\x00" in data:
        return False
    if path.suffix.lower() in _TEXT_SUFFIXES:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _read_text_file(root: Path, relative_path: str, *, max_bytes: int = _MAX_READ_BYTES) -> CodeRepositoryFileContent:
    path = _safe_relative_path(root, relative_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"File not found in repository: {relative_path}")
    if _is_ignored(path.relative_to(root)):
        raise ValueError(f"File path is ignored by AITeamOS repo tools: {relative_path}")
    data = path.read_bytes()[: max_bytes + 1]
    if not _is_probably_text(path, data):
        raise ValueError(f"File is not a supported text file: {relative_path}")
    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    return CodeRepositoryFileContent(path=_repo_relative(root, path), content=text, truncated=truncated)


def _search_terms(query: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9_./:-]{3,}|[\u4e00-\u9fff]{2,}", query)
    ignored = {
        "clara",
        "alex",
        "repo",
        "repos",
        "repository",
        "repositories",
        "ticket",
        "tickets",
        "代码仓库",
        "代码库",
        "仓库",
        "检查",
        "读取",
        "搜索",
        "分析",
        "查看",
    }
    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in ignored or key.startswith("ticket-"):
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result[:8]


def _iter_search_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= _MAX_SEARCH_FILES:
            break
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _is_ignored(relative):
            continue
        try:
            if path.stat().st_size > _MAX_SEARCH_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def _read_git_branch(path: Path) -> str:
    head = path / ".git" / "HEAD"
    if not head.exists():
        return ""
    try:
        content = head.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if content.startswith("ref: refs/heads/"):
        return content.removeprefix("ref: refs/heads/")
    return content[:12]


def _with_health(item: CodeRepository) -> CodeRepository:
    if not item.enabled:
        return item.model_copy(update={"status": "disabled", "detail": "Repository is disabled."})

    if item.provider == "local":
        path = _local_path(item.location)
        if not path.exists():
            return item.model_copy(
                update={
                    "status": "missing",
                    "detail": f"Local path does not exist: {path}",
                    "git_detected": False,
                    "current_branch": "",
                }
            )
        if not path.is_dir():
            return item.model_copy(
                update={
                    "status": "invalid",
                    "detail": f"Local path is not a directory: {path}",
                    "git_detected": False,
                    "current_branch": "",
                }
            )
        git_detected = (path / ".git").exists()
        branch = _read_git_branch(path) if git_detected else ""
        return item.model_copy(
            update={
                "status": "ready" if git_detected else "available",
                "detail": "Local Git repository is available." if git_detected else "Local path exists but .git was not found.",
                "git_detected": git_detected,
                "current_branch": branch,
            }
        )

    if not _REMOTE_RE.match(item.location.strip()):
        return item.model_copy(
            update={
                "status": "invalid",
                "detail": "Remote repository location must be an HTTPS, SSH, or git@ URL.",
                "git_detected": False,
                "current_branch": "",
            }
        )
    return item.model_copy(
        update={
            "status": "configured",
            "detail": "Remote repository location is recorded. API/MCP connectivity is handled by Tool Connectors or AI Engine handoff.",
            "git_detected": True,
            "current_branch": item.default_branch,
        }
    )


def _load_items() -> list[CodeRepository]:
    items: list[CodeRepository] = []
    for row in _read_rows():
        if not isinstance(row, dict):
            continue
        try:
            item = CodeRepository.model_validate(row)
        except ValueError:
            continue
        items.append(_with_health(item))
    return sorted(items, key=lambda item: item.name.lower())


def list_code_repositories() -> list[CodeRepository]:
    return _load_items()


def code_repository_status() -> CodeRepositoryStatus:
    items = list_code_repositories()
    plane_scope = code_repository_plane_scope_summary(items)
    return CodeRepositoryStatus(
        repository_count=len(items),
        enabled_count=sum(1 for item in items if item.enabled),
        ready_count=sum(1 for item in items if item.status in {"ready", "configured"}),
        local_count=sum(1 for item in items if item.provider == "local"),
        remote_count=sum(1 for item in items if item.provider != "local"),
        plane_scope_status=str(plane_scope["code_repository_scope_status"]),
        plane_scope_detail=str(plane_scope["code_repository_scope_detail"]),
        plane_scope_candidate_count=int(plane_scope["code_repository_scope_candidate_count"]),
        plane_scope_missing_count=int(plane_scope["code_repository_scope_missing_count"]),
        plane_scope_setup_action=str(plane_scope["code_repository_scope_setup_action"]),
        plane_scope_candidates=list(plane_scope["code_repository_scope_candidates"]),
        plane_scope_missing=list(plane_scope["code_repository_scope_missing"]),
        plane_scope_suggestions=list(plane_scope["code_repository_scope_suggestions"]),
        saved_paths={"registry": _relative(_registry_path())},
    )


def _ticket_backend_plane_scope_suggestion() -> dict[str, Any] | None:
    path = _workspace_dir() / "tickets" / "backend.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    workspace = str(payload.get("plane_workspace_slug") or "").strip()
    project = str(payload.get("plane_project_id") or "").strip()
    if not workspace or not project:
        return None
    return {
        "source": "ticket_backend",
        "mode": str(payload.get("mode") or ""),
        "plane_workspace_slug": workspace,
        "plane_project_id": project,
        "settings_path": _relative(path),
        "deep_link": "#/settings/ticket-backend",
        "status": "available",
    }


def code_repository_plane_scope_summary(items: list[CodeRepository] | None = None) -> dict[str, Any]:
    repositories = items if items is not None else list_code_repositories()
    candidates: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for repository in repositories:
        if not repository.enabled:
            continue
        workspace = repository.plane_workspace_slug.strip()
        project = repository.plane_project_id.strip()
        payload = {
            "source": "code_repository",
            "repository_id": repository.id,
            "repository_name": repository.name,
            "provider": repository.provider,
            "status": repository.status,
            "deep_link": "#/settings/code-repositories",
        }
        if workspace and project:
            candidates.append(
                {
                    **payload,
                    "plane_workspace_slug": workspace,
                    "plane_project_id": project,
                }
            )
        else:
            missing.append(
                {
                    **payload,
                    "workspace_configured": bool(workspace),
                    "project_configured": bool(project),
                }
            )
    suggestions = [_ticket_backend_plane_scope_suggestion()]
    suggestions = [suggestion for suggestion in suggestions if suggestion is not None]
    if candidates:
        scope_status = "available"
        detail = "Code Repository registry has Plane workspace/project scope candidates."
        action = "apply_code_repository_plane_scope_to_ticket_backend"
    elif suggestions and missing:
        scope_status = "incomplete"
        detail = "Code Repository registry has no ready Plane scope, but Ticket Backend has Plane workspace/project values."
        action = "copy_ticket_backend_plane_scope_to_code_repository"
    elif missing:
        scope_status = "incomplete"
        detail = "Code Repository registry has repositories, but none has both Plane workspace and project configured."
        action = "add_plane_scope_to_code_repository_or_ticket_backend"
    else:
        scope_status = "missing"
        detail = "No enabled Code Repository can provide a Plane workspace/project scope candidate."
        action = "configure_plane_scope_in_ticket_backend"
    return {
        "code_repository_scope_status": scope_status,
        "code_repository_scope_detail": detail,
        "code_repository_scope_candidate_count": len(candidates),
        "code_repository_scope_missing_count": len(missing),
        "code_repository_scope_candidates": candidates[:5],
        "code_repository_scope_missing": missing[:5],
        "code_repository_scope_suggestions": suggestions[:5],
        "code_repository_scope_setup_action": action,
    }


def get_code_repository(repo_id: str) -> CodeRepository | None:
    return next((item for item in list_code_repositories() if item.id == repo_id), None)


def upsert_code_repository(request: CodeRepositoryUpsertRequest, *, existing_id: str | None = None) -> CodeRepository:
    timestamp = _now()
    repo_id = _normalize_id(existing_id or request.id, request.name)
    provider = _normalize_provider(request.provider)
    items = list_code_repositories()
    existing = next((item for item in items if item.id == repo_id), None)
    if existing_id and existing is None:
        raise KeyError(existing_id)

    item = CodeRepository(
        id=repo_id,
        name=request.name.strip(),
        provider=provider,
        location=request.location.strip(),
        default_branch=request.default_branch.strip(),
        plane_workspace_slug=request.plane_workspace_slug.strip(),
        plane_project_id=request.plane_project_id.strip(),
        description=request.description.strip(),
        enabled=request.enabled,
        created_at=existing.created_at if existing else timestamp,
        updated_at=timestamp,
        saved_path=_relative(_registry_path()),
    )
    item = _with_health(item)

    next_items = [current for current in items if current.id != repo_id]
    next_items.append(item)
    _write_items(next_items)
    return item


def delete_code_repository(repo_id: str) -> None:
    items = list_code_repositories()
    next_items = [item for item in items if item.id != repo_id]
    if len(next_items) == len(items):
        raise KeyError(repo_id)
    _write_items(next_items)


def inspect_code_repository(
    repository: CodeRepository,
    *,
    query: str = "",
    file_paths: list[str] | None = None,
) -> CodeRepositoryInspection:
    repository = _with_health(repository)
    if not repository.enabled:
        return CodeRepositoryInspection(
            repository=repository,
            query=query,
            status="blocked",
            detail="Repository is disabled.",
        )
    if repository.provider != "local":
        return CodeRepositoryInspection(
            repository=repository,
            query=query,
            status="blocked",
            detail="Remote repositories require a Tool Connector or AI Engine handoff before code inspection.",
        )

    root = _repository_root(repository)
    files: list[CodeRepositoryFileContent] = []
    matches: list[CodeRepositoryFileMatch] = []
    for file_path in file_paths or []:
        files.append(_read_text_file(root, file_path))

    terms = _search_terms(query)
    if terms:
        lowered_terms = [term.lower() for term in terms]
        for path in _iter_search_files(root):
            if len(matches) >= 20:
                break
            data = path.read_bytes()[:_MAX_SEARCH_FILE_BYTES]
            if not _is_probably_text(path, data):
                continue
            text = data.decode("utf-8", errors="replace")
            lower_text = text.lower()
            if not any(term in lower_text for term in lowered_terms):
                continue
            for index, line in enumerate(text.splitlines(), start=1):
                lower_line = line.lower()
                if any(term in lower_line for term in lowered_terms):
                    matches.append(
                        CodeRepositoryFileMatch(
                            path=_repo_relative(root, path),
                            line=index,
                            excerpt=line.strip()[:260],
                        )
                    )
                    break

    detail = "Local repository inspected."
    if not matches and not files:
        detail = "Local repository is available, but no matching text files were found."
    return CodeRepositoryInspection(
        repository=repository,
        query=query,
        status="completed",
        detail=detail,
        matches=matches,
        files=files,
    )
