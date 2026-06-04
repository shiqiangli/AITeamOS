"""Graphiti-backed memory service with a local audit mirror.

AITeamOS treats Graphiti as the long-term memory backend, while keeping local
JSON files as the review queue, provenance record, and offline recall mirror.
"""

from __future__ import annotations

import inspect
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .ai_engine_catalog import AI_ENGINE_CATALOG, GRAPHITI_AI_ENGINE_IDS

try:  # Optional so local development works before Neo4j is configured.
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
except ImportError:  # pragma: no cover - depends on optional environment install.
    Graphiti = None  # type: ignore[assignment]
    EpisodeType = None  # type: ignore[assignment]

_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_MEMORY_SIGNAL_RE = re.compile(
    r"记住|记忆|沉淀|经验|原则|规范|风格|架构|决定|决策|结论|原因|根因|修复|验证|复盘|"
    r"\b(ticket|decision|decided|resolve|resolved|root cause|fix|fixed|verified|lesson|"
    r"principle|coding style|architecture|postmortem|regression)\b",
    re.IGNORECASE,
)


def _graphiti_package() -> tuple[Any, Any]:
    global Graphiti, EpisodeType
    if Graphiti is not None and EpisodeType is not None:
        return Graphiti, EpisodeType
    try:
        from graphiti_core import Graphiti as ImportedGraphiti
        from graphiti_core.nodes import EpisodeType as ImportedEpisodeType
    except ImportError:
        return None, None
    Graphiti = ImportedGraphiti  # type: ignore[assignment]
    EpisodeType = ImportedEpisodeType  # type: ignore[assignment]
    return Graphiti, EpisodeType


class GraphitiBackendStatus(BaseModel):
    backend: str = "graphiti"
    enabled: bool
    configured: bool
    graph_configured: bool = False
    llm_configured: bool = False
    package_installed: bool
    status: str
    detail: str
    group_id: str
    graph_database: str = "neo4j"
    uri: str = ""
    user: str = ""
    llm_ai_engine: str = "openai"
    llm_ai_engine_name: str = "ChatGPT / OpenAI API"
    llm_api_key_env: str = "OPENAI_API_KEY"
    password_configured: bool = False
    llm_api_key_configured: bool = False


class GraphitiSettingsResponse(BaseModel):
    enabled: bool
    graph_database: str = "neo4j"
    uri: str = ""
    user: str = "neo4j"
    group_id: str = "aiteamos"
    llm_ai_engine: str = "openai"
    llm_ai_engine_name: str = "ChatGPT / OpenAI API"
    llm_api_key_env: str = "OPENAI_API_KEY"
    password_configured: bool = False
    llm_api_key_configured: bool = False
    saved_paths: dict[str, str] = Field(default_factory=dict)
    backend: GraphitiBackendStatus


class GraphitiSettingsUpdateRequest(BaseModel):
    enabled: bool = True
    graph_database: str = "neo4j"
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    group_id: str = "aiteamos"
    llm_ai_engine: str = "openai"


class MemoryCandidate(BaseModel):
    id: str
    content: str
    status: str = "proposed"
    source_kind: str = "manual"
    source_ref: str = ""
    scope_kind: str = "project"
    scope_ref: str = "aiteamos"
    memory_type: str = "fact"
    confidence: float = 0.5
    employee_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    approved_at: str | None = None
    graphiti_episode_id: str | None = None
    graphiti_status: dict[str, Any] = Field(default_factory=dict)


class MemoryCandidateCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    source_kind: str = "manual"
    source_ref: str = ""
    scope_kind: str = "project"
    scope_ref: str = "aiteamos"
    memory_type: str = "fact"
    confidence: float = 0.5
    employee_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class MemoryStatusResponse(BaseModel):
    backend: GraphitiBackendStatus
    candidate_count: int
    approved_count: int
    pending_graphiti_count: int
    saved_paths: dict[str, str]


class MemorySearchResult(BaseModel):
    id: str
    content: str
    source: str
    score: float | None = None
    source_kind: str = ""
    source_ref: str = ""
    scope_kind: str = ""
    scope_ref: str = ""
    memory_type: str = ""
    employee_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class MemorySearchResponse(BaseModel):
    query: str
    results: list[MemorySearchResult]
    backend: GraphitiBackendStatus


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    return Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", Path.cwd())).resolve()


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _memory_dir() -> Path:
    path = _workspace_dir() / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _candidates_path() -> Path:
    return _memory_dir() / "candidates.json"


def _approved_path() -> Path:
    return _memory_dir() / "approved.json"


def _state_path() -> Path:
    return _memory_dir() / "graphiti_state.json"


def _graphiti_settings_path() -> Path:
    return _workspace_dir() / "graphiti.json"


def _ai_engine_settings_path() -> Path:
    return _workspace_dir() / "ai_engines.json"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_candidates() -> list[MemoryCandidate]:
    return [MemoryCandidate.model_validate(item) for item in _read_json_list(_candidates_path())]


def _save_candidates(candidates: list[MemoryCandidate]) -> None:
    _write_json(_candidates_path(), [candidate.model_dump(mode="json") for candidate in candidates])


def _load_approved() -> list[MemoryCandidate]:
    return [MemoryCandidate.model_validate(item) for item in _read_json_list(_approved_path())]


def _save_approved(approved: list[MemoryCandidate]) -> None:
    _write_json(_approved_path(), [candidate.model_dump(mode="json") for candidate in approved])


def _bool_setting(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(value)


def _normalize_graphiti_ai_engine(value: Any) -> str:
    engine_id = str(value or "openai").strip().lower()
    return engine_id if engine_id in GRAPHITI_AI_ENGINE_IDS else "openai"


def _engine_file_config(engine_id: str, file_config: dict[str, Any]) -> dict[str, Any]:
    engines = file_config.get("engines") if isinstance(file_config.get("engines"), dict) else {}
    engine_config = engines.get(engine_id) if isinstance(engines.get(engine_id), dict) else {}
    return dict(engine_config)


def _ai_engine_config(engine_id: str) -> dict[str, str]:
    catalog = AI_ENGINE_CATALOG.get(engine_id, {})
    file_config = _read_json_object(_ai_engine_settings_path())
    engine_config = _engine_file_config(engine_id, file_config)
    env_prefix = engine_id.upper().replace("-", "_")
    model = (
        engine_config.get("model")
        or file_config.get(f"{engine_id}_model")
        or os.environ.get(f"AITEAMOS_{env_prefix}_MODEL")
        or catalog.get("default_model")
        or ""
    )
    base_url = (
        engine_config.get("base_url")
        or file_config.get(f"{engine_id}_base_url")
        or os.environ.get(f"AITEAMOS_{env_prefix}_BASE_URL")
        or catalog.get("default_base_url")
        or ""
    )
    api_key_env = (
        engine_config.get("api_key_env")
        or file_config.get(f"{engine_id}_api_key_env")
        or catalog.get("default_api_key_env")
        or ""
    )
    return {
        "id": engine_id,
        "display_name": str(catalog.get("display_name") or engine_id),
        "model": str(model),
        "base_url": str(base_url),
        "api_key_env": str(api_key_env),
        "api_key": str(os.environ.get(str(api_key_env)) or "") if api_key_env else "",
    }


def _graphiti_config() -> dict[str, str]:
    settings = _read_json_object(_graphiti_settings_path())

    explicit_enabled = os.environ.get("AITEAMOS_GRAPHITI_ENABLED", "").strip().lower()
    backend = os.environ.get("AITEAMOS_MEMORY_BACKEND", "").strip().lower()
    uri = str(settings.get("uri") or os.environ.get("AITEAMOS_GRAPHITI_URI") or os.environ.get("NEO4J_URI") or "")
    user = str(settings.get("user") or os.environ.get("AITEAMOS_GRAPHITI_USER") or os.environ.get("NEO4J_USER") or "neo4j")
    password = str(
        os.environ.get("AITEAMOS_GRAPHITI_PASSWORD")
        or os.environ.get("NEO4J_PASSWORD")
        or ""
    )
    group_id = str(settings.get("group_id") or os.environ.get("AITEAMOS_GRAPHITI_GROUP_ID") or "aiteamos")
    graph_database = str(settings.get("graph_database") or "neo4j").strip().lower() or "neo4j"
    llm_ai_engine = _normalize_graphiti_ai_engine(
        settings.get("llm_ai_engine")
        or settings.get("llm_provider")
        or os.environ.get("AITEAMOS_GRAPHITI_AI_ENGINE")
        or "openai"
    )
    llm_engine = _ai_engine_config(llm_ai_engine)
    file_enabled = settings.get("enabled")
    enabled = (
        _bool_setting(file_enabled)
        if file_enabled is not None
        else explicit_enabled in {"1", "true", "yes", "on"} or backend == "graphiti" or bool(uri)
    )
    return {
        "uri": uri,
        "user": user,
        "password": password,
        "group_id": group_id,
        "graph_database": graph_database,
        "llm_ai_engine": llm_ai_engine,
        "llm_ai_engine_name": llm_engine["display_name"],
        "llm_model": llm_engine["model"],
        "llm_base_url": llm_engine["base_url"],
        "llm_api_key_env": llm_engine["api_key_env"],
        "llm_api_key": llm_engine["api_key"],
        "enabled": "true" if enabled else "false",
    }


def graphiti_backend_status() -> GraphitiBackendStatus:
    config = _graphiti_config()
    enabled = config["enabled"] == "true"
    graph_configured = bool(config["uri"] and config["user"] and config["password"])
    llm_configured = bool(config["llm_api_key"])
    configured = graph_configured and llm_configured
    graphiti_cls, episode_type = _graphiti_package()
    package_installed = graphiti_cls is not None and episode_type is not None
    if not enabled:
        status = "disabled"
        detail = "Graphiti is not enabled; local memory mirror is active."
    elif not graph_configured:
        status = "not_configured"
        detail = "Set Graphiti Neo4j URI/user in Settings and password via AITEAMOS_GRAPHITI_PASSWORD or NEO4J_PASSWORD."
    elif not llm_configured:
        status = "llm_not_configured"
        detail = f"Set {config['llm_api_key_env'] or 'the selected AI Engine API key env'} for Graphiti ingestion and graph search."
    elif not package_installed:
        status = "package_missing"
        detail = "Install the graphiti optional dependency to enable ingestion and graph search."
    else:
        status = "ready"
        detail = f"Graphiti is configured with {config['llm_ai_engine_name']}; approved memory can be ingested."
    return GraphitiBackendStatus(
        enabled=enabled,
        configured=configured,
        graph_configured=graph_configured,
        llm_configured=llm_configured,
        package_installed=package_installed,
        status=status,
        detail=detail,
        group_id=config["group_id"],
        graph_database=config["graph_database"],
        uri=config["uri"],
        user=config["user"],
        llm_ai_engine=config["llm_ai_engine"],
        llm_ai_engine_name=config["llm_ai_engine_name"],
        llm_api_key_env=config["llm_api_key_env"],
        password_configured=bool(config["password"]),
        llm_api_key_configured=bool(config["llm_api_key"]),
    )


def graphiti_settings_response() -> GraphitiSettingsResponse:
    config = _graphiti_config()
    return GraphitiSettingsResponse(
        enabled=config["enabled"] == "true",
        graph_database=config["graph_database"],
        uri=config["uri"],
        user=config["user"],
        group_id=config["group_id"],
        llm_ai_engine=config["llm_ai_engine"],
        llm_ai_engine_name=config["llm_ai_engine_name"],
        llm_api_key_env=config["llm_api_key_env"],
        password_configured=bool(config["password"]),
        llm_api_key_configured=bool(config["llm_api_key"]),
        saved_paths={
            "settings": _relative(_graphiti_settings_path()),
        },
        backend=graphiti_backend_status(),
    )


def update_graphiti_settings(request: GraphitiSettingsUpdateRequest) -> GraphitiSettingsResponse:
    graph_database = request.graph_database.strip().lower() or "neo4j"
    if graph_database != "neo4j":
        raise ValueError("Only Neo4j is supported as the Graphiti graph database in this build.")
    llm_ai_engine = request.llm_ai_engine.strip().lower() or "openai"
    if llm_ai_engine not in GRAPHITI_AI_ENGINE_IDS:
        raise ValueError("Select a Graphiti-compatible AI Engine from Settings / AI Engines.")

    _write_json(
        _graphiti_settings_path(),
        {
            "enabled": request.enabled,
            "graph_database": graph_database,
            "uri": request.uri.strip() or "bolt://localhost:7687",
            "user": request.user.strip() or "neo4j",
            "group_id": request.group_id.strip() or "aiteamos",
            "llm_ai_engine": llm_ai_engine,
            "updated_at": _now(),
        },
    )

    return graphiti_settings_response()


def memory_status() -> MemoryStatusResponse:
    candidates = _load_candidates()
    approved = _load_approved()
    pending = [
        candidate
        for candidate in approved
        if candidate.graphiti_status.get("status") not in {"ingested", "skipped_disabled"}
    ]
    return MemoryStatusResponse(
        backend=graphiti_backend_status(),
        candidate_count=len(candidates),
        approved_count=len(approved),
        pending_graphiti_count=len(pending),
        saved_paths={
            "candidates": _relative(_candidates_path()),
            "approved": _relative(_approved_path()),
            "graphiti_state": _relative(_state_path()),
            "graphiti_settings": _relative(_graphiti_settings_path()),
        },
    )


def list_memory_candidates(status: str | None = None) -> list[MemoryCandidate]:
    candidates = sorted(_load_candidates(), key=lambda item: item.updated_at, reverse=True)
    if status:
        candidates = [candidate for candidate in candidates if candidate.status == status]
    return candidates


def list_approved_memories() -> list[MemoryCandidate]:
    return sorted(_load_approved(), key=lambda item: item.updated_at, reverse=True)


def create_memory_candidate(request: MemoryCandidateCreateRequest) -> MemoryCandidate:
    timestamp = _now()
    candidate = MemoryCandidate(
        id=f"mem-{uuid4().hex[:12]}",
        content=request.content.strip(),
        source_kind=request.source_kind.strip() or "manual",
        source_ref=request.source_ref.strip(),
        scope_kind=request.scope_kind.strip() or "project",
        scope_ref=request.scope_ref.strip() or "aiteamos",
        memory_type=request.memory_type.strip() or "fact",
        confidence=max(0.0, min(float(request.confidence), 1.0)),
        employee_ids=sorted({item.strip() for item in request.employee_ids if item.strip()}),
        tags=sorted({item.strip() for item in request.tags if item.strip()}),
        provenance=request.provenance,
        created_at=timestamp,
        updated_at=timestamp,
    )
    candidates = _load_candidates()
    candidates.append(candidate)
    _save_candidates(candidates)
    return candidate


def _update_candidate(candidate: MemoryCandidate) -> MemoryCandidate:
    candidates = _load_candidates()
    for index, current in enumerate(candidates):
        if current.id == candidate.id:
            candidates[index] = candidate
            _save_candidates(candidates)
            return candidate
    candidates.append(candidate)
    _save_candidates(candidates)
    return candidate


def _upsert_approved(candidate: MemoryCandidate) -> None:
    approved = _load_approved()
    for index, current in enumerate(approved):
        if current.id == candidate.id:
            approved[index] = candidate
            _save_approved(approved)
            return
    approved.append(candidate)
    _save_approved(approved)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _set_graphiti_environment(config: dict[str, str]) -> dict[str, str | None]:
    previous = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL"),
    }
    if config["llm_api_key"]:
        os.environ["OPENAI_API_KEY"] = config["llm_api_key"]
    if config["llm_base_url"]:
        os.environ["OPENAI_BASE_URL"] = config["llm_base_url"]
    return previous


def _restore_environment(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


async def _ingest_graphiti(candidate: MemoryCandidate) -> dict[str, Any]:
    status = graphiti_backend_status()
    if status.status == "disabled":
        return {"status": "skipped_disabled", "detail": status.detail}
    if status.status != "ready":
        return {"status": status.status, "detail": status.detail}

    config = _graphiti_config()
    graphiti_cls, episode_type = _graphiti_package()
    previous_env = _set_graphiti_environment(config)
    graphiti = graphiti_cls(config["uri"], config["user"], config["password"])
    try:
        build_indices = getattr(graphiti, "build_indices_and_constraints", None)
        if build_indices is not None:
            await _maybe_await(build_indices())

        source = episode_type.message if candidate.source_kind == "chat" else episode_type.text
        episode_body = (
            f"Memory id: {candidate.id}\n"
            f"Scope: {candidate.scope_kind}:{candidate.scope_ref}\n"
            f"Employees: {', '.join(candidate.employee_ids) or 'all'}\n"
            f"Content: {candidate.content}"
        )
        add_episode = getattr(graphiti, "add_episode")
        parameters = inspect.signature(add_episode).parameters
        kwargs: dict[str, Any] = {
            "name": f"AITeamOS memory {candidate.id}",
            "episode_body": episode_body,
            "source": source,
            "source_description": f"AITeamOS {candidate.source_kind} memory candidate",
            "reference_time": datetime.now(UTC),
        }
        if "group_id" in parameters:
            kwargs["group_id"] = config["group_id"]
        result = await _maybe_await(add_episode(**kwargs))
        episode = getattr(result, "episode", None)
        episode_id = getattr(episode, "uuid", None) or getattr(result, "uuid", None)
        return {
            "status": "ingested",
            "detail": "Approved memory was ingested into Graphiti.",
            "episode_id": str(episode_id) if episode_id else None,
        }
    except Exception as exc:  # Keep the local approval path usable.
        return {"status": "error", "detail": str(exc)[:500]}
    finally:
        close = getattr(graphiti, "close", None)
        if close is not None:
            await _maybe_await(close())
        _restore_environment(previous_env)


async def approve_memory_candidate(candidate_id: str) -> MemoryCandidate:
    candidate = next((item for item in _load_candidates() if item.id == candidate_id), None)
    if candidate is None:
        raise KeyError(candidate_id)

    timestamp = _now()
    candidate.status = "approved"
    candidate.approved_at = candidate.approved_at or timestamp
    candidate.updated_at = timestamp
    candidate.graphiti_status = await _ingest_graphiti(candidate)
    episode_id = candidate.graphiti_status.get("episode_id")
    if isinstance(episode_id, str) and episode_id:
        candidate.graphiti_episode_id = episode_id
    _update_candidate(candidate)
    _upsert_approved(candidate)

    state = {
        "last_approved_at": timestamp,
        "last_candidate_id": candidate.id,
        "last_graphiti_status": candidate.graphiti_status,
        "backend": graphiti_backend_status().model_dump(mode="json"),
    }
    _write_json(_state_path(), state)
    return candidate


def _compact_text(value: str, limit: int = 900) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}…"


def _candidate_matches_query(candidate: MemoryCandidate, query: str) -> bool:
    if not query:
        return True
    normalized = query.lower()
    haystack = " ".join(
        [
            candidate.content,
            candidate.source_kind,
            candidate.source_ref,
            candidate.scope_kind,
            candidate.scope_ref,
            candidate.memory_type,
            " ".join(candidate.tags),
        ]
    ).lower()
    return all(part in haystack for part in normalized.split())


def _candidate_matches_scope(
    candidate: MemoryCandidate,
    *,
    employee_id: str | None = None,
    ticket_key: str | None = None,
    project: str | None = None,
) -> bool:
    if employee_id and candidate.employee_ids and employee_id not in candidate.employee_ids:
        return False
    if ticket_key and candidate.scope_kind == "ticket" and candidate.scope_ref != ticket_key:
        return False
    if project and candidate.scope_kind == "project" and candidate.scope_ref not in {project, "aiteamos"}:
        return False
    return True


def _file_memory_results(
    *,
    query: str,
    employee_id: str | None = None,
    ticket_key: str | None = None,
    project: str | None = None,
    limit: int = 10,
) -> list[MemorySearchResult]:
    results: list[MemorySearchResult] = []
    for candidate in list_approved_memories():
        if not _candidate_matches_query(candidate, query):
            continue
        if not _candidate_matches_scope(candidate, employee_id=employee_id, ticket_key=ticket_key, project=project):
            continue
        results.append(
            MemorySearchResult(
                id=candidate.id,
                content=candidate.content,
                source="file",
                source_kind=candidate.source_kind,
                source_ref=candidate.source_ref,
                scope_kind=candidate.scope_kind,
                scope_ref=candidate.scope_ref,
                memory_type=candidate.memory_type,
                employee_ids=candidate.employee_ids,
                tags=candidate.tags,
                provenance=candidate.provenance,
            )
        )
        if len(results) >= limit:
            break
    return results


async def _graphiti_memory_results(query: str, limit: int) -> list[MemorySearchResult]:
    backend = graphiti_backend_status()
    if backend.status != "ready" or not query.strip():
        return []

    config = _graphiti_config()
    graphiti_cls, _episode_type = _graphiti_package()
    previous_env = _set_graphiti_environment(config)
    graphiti = graphiti_cls(config["uri"], config["user"], config["password"])
    try:
        search = getattr(graphiti, "search")
        parameters = inspect.signature(search).parameters
        kwargs: dict[str, Any] = {}
        if "group_ids" in parameters:
            kwargs["group_ids"] = [config["group_id"]]
        if "num_results" in parameters:
            kwargs["num_results"] = limit
        raw_results = await _maybe_await(search(query, **kwargs))
    except Exception:
        return []
    finally:
        close = getattr(graphiti, "close", None)
        if close is not None:
            await _maybe_await(close())
        _restore_environment(previous_env)

    results: list[MemorySearchResult] = []
    for index, item in enumerate(list(raw_results or [])[:limit]):
        content = getattr(item, "fact", None) or getattr(item, "name", None) or str(item)
        item_id = getattr(item, "uuid", None) or getattr(item, "source_node_uuid", None) or f"graphiti-{index}"
        score = getattr(item, "score", None)
        results.append(
            MemorySearchResult(
                id=str(item_id),
                content=_compact_text(str(content), 1000),
                source="graphiti",
                score=float(score) if isinstance(score, int | float) else None,
                scope_kind="graphiti",
                scope_ref=backend.group_id,
                provenance={"raw_type": item.__class__.__name__},
            )
        )
    return results


async def search_memory(
    *,
    query: str,
    employee_id: str | None = None,
    ticket_key: str | None = None,
    project: str | None = None,
    limit: int = 10,
    include_graphiti: bool = True,
) -> MemorySearchResponse:
    capped_limit = max(1, min(limit, 50))
    file_results = _file_memory_results(
        query=query,
        employee_id=employee_id,
        ticket_key=ticket_key,
        project=project,
        limit=capped_limit,
    )
    remaining = max(0, capped_limit - len(file_results))
    graphiti_results = (
        await _graphiti_memory_results(query, remaining)
        if include_graphiti and remaining
        else []
    )
    return MemorySearchResponse(
        query=query,
        results=[*file_results, *graphiti_results],
        backend=graphiti_backend_status(),
    )


def _legacy_memory_snippets(employee_id: str, limit: int) -> list[str]:
    memories_dir = _workspace_dir() / "memories"
    if not memories_dir.exists():
        return []

    snippets: list[str] = []
    for path in sorted(memories_dir.rglob("*.md"))[:limit]:
        try:
            first_line = next(
                (line.strip("# ").strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()),
                path.stem,
            )
        except OSError:
            first_line = path.stem
        snippets.append(f"{employee_id}:{path.relative_to(memories_dir)}:{first_line}")
    return snippets


def recall_memory_snippets(
    *,
    employee_id: str,
    query: str = "",
    ticket_keys: list[str] | None = None,
    limit: int = 5,
) -> list[str]:
    snippets: list[str] = []
    search_terms = " ".join(ticket_keys or []).strip() or query
    for result in _file_memory_results(
        query=search_terms,
        employee_id=employee_id,
        ticket_key=(ticket_keys or [None])[0],
        limit=limit,
    ):
        snippets.append(
            f"[memory:{result.id}] {result.content} "
            f"(scope={result.scope_kind}:{result.scope_ref}; source={result.source_kind}:{result.source_ref})"
        )
        if len(snippets) >= limit:
            break

    if len(snippets) < limit:
        snippets.extend(_legacy_memory_snippets(employee_id, limit - len(snippets)))
    return snippets[:limit]


def propose_memory_from_chat_turn(
    *,
    run_id: str,
    thread_id: str,
    employee_id: str,
    employee_display_name: str,
    user_message: str,
    assistant_reply: str,
    ticket_keys: list[str],
    trace_path: str,
) -> MemoryCandidate | None:
    if any(candidate.source_kind == "chat" and candidate.source_ref == run_id for candidate in _load_candidates()):
        return None

    text = f"{user_message}\n{assistant_reply}"
    detected_ticket = sorted(set(ticket_keys or _JIRA_KEY_RE.findall(text)))
    if not detected_ticket and not _MEMORY_SIGNAL_RE.search(text):
        return None

    scope_kind = "ticket" if detected_ticket else "employee"
    scope_ref = detected_ticket[0] if detected_ticket else employee_id
    content = _compact_text(
        f"In thread {thread_id}, user asked {employee_display_name}: {user_message} "
        f"{employee_display_name} replied: {assistant_reply}",
        900,
    )
    return create_memory_candidate(
        MemoryCandidateCreateRequest(
            content=content,
            source_kind="chat",
            source_ref=run_id,
            scope_kind=scope_kind,
            scope_ref=scope_ref,
            memory_type="episode",
            confidence=0.62 if detected_ticket else 0.42,
            employee_ids=[employee_id],
            tags=sorted({"auto-chat", *detected_ticket}),
            provenance={
                "thread_id": thread_id,
                "run_id": run_id,
                "employee_id": employee_id,
                "trace": trace_path,
                "ticket_keys": detected_ticket,
            },
        )
    )
