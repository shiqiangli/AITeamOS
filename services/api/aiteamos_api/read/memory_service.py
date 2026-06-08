"""Graphiti-backed memory and persistent asset graph service.

AITeamOS treats Graphiti as a durable asset knowledge graph projection, while
keeping local JSON files as the review queue, approval source, provenance
record, and ingestion audit mirror. The current implementation starts with
approved memories; broader durable asset projection is the next extension.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

from .ai_engine_catalog import AI_ENGINE_CATALOG, GRAPHITI_AI_ENGINE_IDS

try:  # Optional so local development works before Neo4j is configured.
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    from graphiti_core.embedder.client import EmbedderClient
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
except ImportError:  # pragma: no cover - depends on optional environment install.
    CrossEncoderClient = object  # type: ignore[assignment]
    EmbedderClient = object  # type: ignore[assignment]
    Graphiti = None  # type: ignore[assignment]
    EpisodeType = None  # type: ignore[assignment]

_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_MEMORY_SIGNAL_RE = re.compile(
    r"记住|记忆|沉淀|经验|原则|规范|风格|架构|决定|决策|结论|原因|根因|修复|验证|复盘|"
    r"\b(ticket|decision|decided|resolve|resolved|root cause|fix|fixed|verified|lesson|"
    r"principle|coding style|architecture|postmortem|regression)\b",
    re.IGNORECASE,
)

GRAPHITI_EPISODE_SCHEMA_VERSION = "aiteamos.graphiti.episode.v1"
GRAPHITI_MINIMAL_PROVENANCE_FIELDS = (
    "asset_id",
    "asset_type",
    "asset_status",
    "source_ticket_id",
    "source_employee_id",
    "source_run_id",
    "source_report_id",
    "evidence_id",
    "scope",
    "version",
    "content_hash",
    "provider_refs",
    "source_ref",
)
RECALLABLE_MEMORY_STATUSES = {"approved"}
RECALLABLE_DURABLE_ASSET_STATUSES = {"approved", "accepted", "validated"}
MEMORY_REVIEW_STATUSES = {"rejected", "stale", "superseded"}
MEMORY_RECALL_USEFULNESS_STATUSES = {"unreviewed", "useful", "not_useful", "neutral"}
_DURABLE_TICKET_STATUSES = {"validated", "completed", "done", "closed"}
_DURABLE_VALIDATION_REPORT_TYPES = {"validation", "validation_passed", "validation_pass", "passed"}
_ACCEPTED_DECISION_STATUSES = {"accepted"}
_NON_DURABLE_REPORT_TYPES = {
    "validation_failed",
    "validation_rejected",
    "failed",
    "failure",
    "blocked",
    "human_review",
    "human_review_requested",
    "request_human_review",
}
_DURABLE_ASSET_RELATIONSHIP_TYPES = {
    "supersedes",
    "conflicts_with",
    "derived_from",
    "used_by",
    "validated_by",
}


class _AiteamosLocalEmbedder(EmbedderClient):  # type: ignore[misc, valid-type]
    """Deterministic local embeddings for self-hosted Graphiti bootstrap."""

    def __init__(self, dimension: int = 1024):
        self.dimension = dimension

    def _embed(self, value: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[\w:-]+", value.lower())
        for token in tokens or [value.lower()]:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(item * item for item in vector)) or 1.0
        return [item / norm for item in vector]

    async def create(self, input_data: Any) -> list[float]:
        if isinstance(input_data, list):
            text = " ".join(str(item) for item in input_data)
        else:
            text = str(input_data)
        return self._embed(text)

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return [self._embed(item) for item in input_data_list]


class _AiteamosLocalCrossEncoder(CrossEncoderClient):  # type: ignore[misc, valid-type]
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []
        query_terms = set(re.findall(r"[\w:-]+", query.lower()))
        ranked: list[tuple[str, float]] = []
        for passage in passages:
            passage_terms = set(re.findall(r"[\w:-]+", passage.lower()))
            overlap = len(query_terms & passage_terms)
            score = overlap / max(len(query_terms), 1)
            if query.lower() in passage.lower():
                score += 1.0
            ranked.append((passage, score))
        return sorted(ranked, key=lambda item: item[1], reverse=True)


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


class MemoryCandidateReviewRequest(BaseModel):
    status: str = Field(min_length=1)
    reason: str = ""
    actor_employee_id: str = "clara"
    superseded_by_candidate_id: str = ""


class MemoryRecallUsefulnessReviewRequest(BaseModel):
    usefulness_status: str = Field(min_length=1)
    reviewer_employee_id: str = "clara"
    reason: str = ""


class DurableAssetIngestRequest(BaseModel):
    asset_id: str = Field(min_length=1)
    asset_type: str = Field(min_length=1)
    asset_status: str = "validated"
    content: str = Field(min_length=1)
    source_ticket_id: str = ""
    source_employee_id: str = ""
    source_run_id: str = ""
    source_report_id: str = ""
    evidence_id: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    version: str = ""
    provider_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_ref: str = ""
    source_kind: str = "validated_ticket_summary"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DurableAssetIngestResponse(BaseModel):
    status: str
    detail: str
    episode_id: str | None = None
    episode_schema_version: str = GRAPHITI_EPISODE_SCHEMA_VERSION
    provenance: dict[str, Any] = Field(default_factory=dict)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class DurableAssetRelationshipIngestRequest(BaseModel):
    source_asset_id: str = Field(min_length=1)
    target_asset_id: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    asset_status: str = "validated"
    reason: str = ""
    source_ticket_id: str = ""
    source_employee_id: str = ""
    source_run_id: str = ""
    source_report_id: str = ""
    evidence_id: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    provider_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_ref: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DurableAssetRelationshipIngestResponse(BaseModel):
    relationship_id: str
    relationship_type: str
    source_asset_id: str
    target_asset_id: str
    status: str
    detail: str
    ingested_asset: DurableAssetIngestResponse | None = None
    skipped_asset: dict[str, str] | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketDurableAssetProjectionResponse(BaseModel):
    ticket_id: str
    status: str
    detail: str
    ingested_assets: list[DurableAssetIngestResponse] = Field(default_factory=list)
    skipped_assets: list[dict[str, str]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class DecisionDurableAssetProjectionResponse(BaseModel):
    decision_id: str
    status: str
    detail: str
    ingested_asset: DurableAssetIngestResponse | None = None
    skipped_asset: dict[str, str] | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class DecisionDurableAssetBatchProjectionResponse(BaseModel):
    status: str
    detail: str
    ingested_assets: list[DurableAssetIngestResponse] = Field(default_factory=list)
    skipped_assets: list[dict[str, str]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class SkillDurableAssetProjectionResponse(BaseModel):
    skill_id: str
    status: str
    detail: str
    ingested_asset: DurableAssetIngestResponse | None = None
    skipped_asset: dict[str, str] | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class SkillDurableAssetBatchProjectionResponse(BaseModel):
    status: str
    detail: str
    ingested_assets: list[DurableAssetIngestResponse] = Field(default_factory=list)
    skipped_assets: list[dict[str, str]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class DocDurableAssetProjectionResponse(BaseModel):
    doc_id: str
    status: str
    detail: str
    ingested_asset: DurableAssetIngestResponse | None = None
    skipped_asset: dict[str, str] | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class DocDurableAssetBatchProjectionResponse(BaseModel):
    status: str
    detail: str
    ingested_assets: list[DurableAssetIngestResponse] = Field(default_factory=list)
    skipped_assets: list[dict[str, str]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class EmployeeDurableAssetProjectionResponse(BaseModel):
    employee_id: str
    status: str
    detail: str
    ingested_asset: DurableAssetIngestResponse | None = None
    skipped_asset: dict[str, str] | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class EmployeeDurableAssetBatchProjectionResponse(BaseModel):
    status: str
    detail: str
    ingested_assets: list[DurableAssetIngestResponse] = Field(default_factory=list)
    skipped_assets: list[dict[str, str]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class CapabilityDurableAssetProjectionResponse(BaseModel):
    capability_id: str
    status: str
    detail: str
    ingested_asset: DurableAssetIngestResponse | None = None
    skipped_asset: dict[str, str] | None = None
    saved_paths: dict[str, str] = Field(default_factory=dict)


class CapabilityDurableAssetBatchProjectionResponse(BaseModel):
    status: str
    detail: str
    ingested_assets: list[DurableAssetIngestResponse] = Field(default_factory=list)
    skipped_assets: list[dict[str, str]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


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
    graphiti_episode_id: str | None = None


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
        or os.environ.get("AITEAMOS_GRAPHITI_AI_ENGINE")
        or "openai"
    )
    llm_engine = _ai_engine_config(llm_ai_engine)
    llm_model = str(
        settings.get("llm_model")
        or os.environ.get("AITEAMOS_GRAPHITI_LLM_MODEL")
        or llm_engine["model"]
    )
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
        "llm_model": llm_model,
        "llm_base_url": llm_engine["base_url"],
        "llm_api_key_env": llm_engine["api_key_env"],
        "llm_api_key": llm_engine["api_key"],
        "enabled": "true" if enabled else "false",
    }


def _graphiti_constructor_kwargs(config: dict[str, str]) -> dict[str, Any]:
    if config["llm_ai_engine"] == "openai":
        return {}
    try:
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    except ImportError:
        return {}
    llm_config = LLMConfig(
        api_key=config["llm_api_key"],
        model=config["llm_model"],
        small_model=config["llm_model"],
        base_url=config["llm_base_url"],
        temperature=0,
        max_tokens=8192,
    )

    class _AiteamosOpenAICompatibleGraphitiClient(OpenAIGenericClient):
        async def _generate_response(
            self,
            messages: list[Any],
            response_model: type[Any] | None = None,
            max_tokens: int = 8192,
            model_size: Any = None,
        ) -> dict[str, Any]:
            openai_messages: list[dict[str, str]] = []
            for message in messages:
                content = self._clean_input(str(getattr(message, "content", "")))
                role = str(getattr(message, "role", "user"))
                openai_messages.append({"role": role if role in {"system", "user", "assistant"} else "user", "content": content})
            if response_model is not None:
                schema = response_model.model_json_schema()
                openai_messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "Return only a valid JSON object that matches this JSON schema. "
                            "Do not wrap it in markdown.\n"
                            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
                        ),
                    },
                )
            elif openai_messages:
                openai_messages[0]["content"] = "Return only a valid JSON object.\n" + openai_messages[0]["content"]
            response = await self.client.chat.completions.create(
                model=self.model or config["llm_model"],
                messages=openai_messages,
                temperature=0,
                max_tokens=max_tokens or 8192,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content or "{}")

    return {
        "llm_client": _AiteamosOpenAICompatibleGraphitiClient(config=llm_config, max_tokens=8192),
        "embedder": _AiteamosLocalEmbedder(),
        "cross_encoder": _AiteamosLocalCrossEncoder(),
    }


def _new_graphiti_client(graphiti_cls: Any, config: dict[str, str]) -> Any:
    return graphiti_cls(
        config["uri"],
        config["user"],
        config["password"],
        **_graphiti_constructor_kwargs(config),
    )


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
        detail = "Graphiti is not enabled; configure Graphiti to use the target Memory / Asset Graph Backend."
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
        detail = (
            f"Graphiti is configured with {config['llm_ai_engine_name']}; approved memory ingestion is available, "
            "with durable asset projection as the next extension."
        )
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
    approved = list_approved_memories()
    pending = [
        candidate
        for candidate in approved
        if candidate.graphiti_status.get("status") != "ingested"
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
    approved = [candidate for candidate in _load_approved() if candidate.status in RECALLABLE_MEMORY_STATUSES]
    return sorted(approved, key=lambda item: item.updated_at, reverse=True)


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


def _update_approved_if_present(candidate: MemoryCandidate) -> None:
    approved = _load_approved()
    for index, current in enumerate(approved):
        if current.id != candidate.id:
            continue
        approved[index] = candidate
        _save_approved(approved)
        return


def _replace_local_memory_candidate(candidate: MemoryCandidate) -> None:
    candidates = _load_candidates()
    candidate_updated = False
    for index, current in enumerate(candidates):
        if current.id != candidate.id:
            continue
        candidates[index] = candidate
        candidate_updated = True
        break
    if candidate_updated:
        _save_candidates(candidates)
    approved = _load_approved()
    approved_updated = False
    for index, current in enumerate(approved):
        if current.id != candidate.id:
            continue
        approved[index] = candidate
        approved_updated = True
        break
    if approved_updated:
        _save_approved(approved)


def _find_local_memory_candidate(candidate_id: str) -> MemoryCandidate | None:
    for candidate in [*_load_candidates(), *_load_approved()]:
        if candidate.id == candidate_id:
            return candidate
    return None


def _memory_candidate_status(candidate_id: str) -> str | None:
    candidate = _find_local_memory_candidate(candidate_id)
    return candidate.status if candidate is not None else None


def _is_local_memory_asset_recallable(provenance: dict[str, Any]) -> bool:
    asset_id = _first_string(provenance.get("asset_id"), provenance.get("memory_id"))
    if not asset_id:
        return True
    local_status = _memory_candidate_status(asset_id)
    if local_status is not None:
        return local_status in RECALLABLE_MEMORY_STATUSES
    graphiti_status = _first_string(provenance.get("asset_status"), provenance.get("status"))
    return not graphiti_status or graphiti_status in RECALLABLE_DURABLE_ASSET_STATUSES


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


def _content_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _graphiti_asset_provenance(candidate: MemoryCandidate) -> dict[str, Any]:
    provenance = dict(candidate.provenance)
    source_ticket_id = _first_string(
        provenance.get("source_ticket_id"),
        provenance.get("ticket_id"),
        candidate.scope_ref if candidate.scope_kind == "ticket" else "",
    )
    source_employee_id = _first_string(
        provenance.get("source_employee_id"),
        provenance.get("employee_id"),
        candidate.employee_ids[0] if candidate.employee_ids else "",
    )
    source_run_id = _first_string(provenance.get("source_run_id"), provenance.get("run_id"), provenance.get("trace"))
    source_report_id = _first_string(provenance.get("source_report_id"), provenance.get("report_id"))
    evidence_id = _first_string(provenance.get("evidence_id"), provenance.get("source_evidence_id"))
    provider_refs = provenance.get("provider_refs")
    if not isinstance(provider_refs, list):
        provider_ref = provenance.get("provider_ref")
        provider_refs = [provider_ref] if isinstance(provider_ref, dict) else []
    content_hash = _content_hash(candidate.content)
    return {
        "asset_id": candidate.id,
        "asset_type": f"memory:{candidate.memory_type}",
        "asset_status": candidate.status,
        "source_ticket_id": source_ticket_id,
        "source_employee_id": source_employee_id,
        "source_run_id": source_run_id,
        "source_report_id": source_report_id,
        "evidence_id": evidence_id,
        "scope": {"kind": candidate.scope_kind, "ref": candidate.scope_ref},
        "version": content_hash,
        "content_hash": content_hash,
        "provider_refs": provider_refs,
        "source_ref": candidate.source_ref,
        "source_kind": candidate.source_kind,
        "schema_version": GRAPHITI_EPISODE_SCHEMA_VERSION,
    }


def _durable_asset_provenance(request: DurableAssetIngestRequest) -> dict[str, Any]:
    scope = request.scope if isinstance(request.scope, dict) else {}
    if not scope:
        scope = {
            "kind": "ticket" if request.source_ticket_id.strip() else "project",
            "ref": request.source_ticket_id.strip() or "aiteamos",
        }
    content_hash = _content_hash(request.content)
    version = request.version.strip() or content_hash
    return {
        "asset_id": request.asset_id.strip(),
        "asset_type": request.asset_type.strip(),
        "asset_status": request.asset_status.strip().lower(),
        "source_ticket_id": request.source_ticket_id.strip(),
        "source_employee_id": request.source_employee_id.strip(),
        "source_run_id": request.source_run_id.strip(),
        "source_report_id": request.source_report_id.strip(),
        "evidence_id": request.evidence_id.strip(),
        "scope": scope,
        "version": version,
        "content_hash": content_hash,
        "provider_refs": request.provider_refs,
        "source_ref": request.source_ref.strip(),
        "source_kind": request.source_kind.strip() or "durable_asset",
        "schema_version": GRAPHITI_EPISODE_SCHEMA_VERSION,
        "metadata": request.metadata,
    }


def _graphiti_result_provenance(item: Any) -> dict[str, Any]:
    candidates = [
        getattr(item, "provenance", None),
        getattr(item, "metadata", None),
        getattr(item, "attributes", None),
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if isinstance(candidate.get("aiteamos"), dict):
            return dict(candidate["aiteamos"])
        if any(field in candidate for field in GRAPHITI_MINIMAL_PROVENANCE_FIELDS):
            return dict(candidate)
    return {"raw_type": item.__class__.__name__}


def _graphiti_result_local_memory_match(content: str, episode_id: str) -> MemoryCandidate | None:
    result_terms = set(re.findall(r"[\w:-]+", content.lower()))
    normalized_content = content.lower()
    best: tuple[int, MemoryCandidate] | None = None
    for candidate in list_approved_memories():
        score = 0
        if episode_id and candidate.graphiti_episode_id == episode_id:
            score += 100
        tag_hits = [
            tag
            for tag in candidate.tags
            if len(tag) >= 6 and tag.lower() in normalized_content
        ]
        if tag_hits:
            score += 50 + len(tag_hits)
        candidate_terms = set(re.findall(r"[\w:-]+", candidate.content.lower()))
        overlap = len(result_terms & candidate_terms)
        if overlap >= 6:
            score += min(overlap, 30)
        candidate_content = candidate.content.lower()
        if normalized_content and (normalized_content in candidate_content or candidate_content in normalized_content):
            score += 30
        if score >= 12 and (best is None or score > best[0]):
            best = (score, candidate)
    return best[1] if best is not None else None


def _graphiti_durable_asset_ingestion_records() -> list[dict[str, Any]]:
    state = _read_json_object(_state_path())
    records = state.get("durable_asset_ingestions")
    return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []


def _durable_asset_ingestion_record(asset_id: str) -> dict[str, Any] | None:
    target_asset_id = asset_id.strip()
    for record in reversed(_graphiti_durable_asset_ingestion_records()):
        if str(record.get("asset_id") or "").strip() != target_asset_id:
            continue
        graphiti_status = record.get("graphiti_status")
        if isinstance(graphiti_status, dict) and graphiti_status.get("status") == "ingested":
            return record
    return None


def _graphiti_result_durable_asset_match(content: str, episode_id: str) -> dict[str, Any] | None:
    normalized_content = content.lower()
    best: tuple[int, dict[str, Any]] | None = None
    for record in _graphiti_durable_asset_ingestion_records():
        graphiti_status = record.get("graphiti_status")
        if not isinstance(graphiti_status, dict):
            continue
        provenance = graphiti_status.get("provenance")
        if not isinstance(provenance, dict):
            continue
        score = 0
        record_episode_id = _first_string(graphiti_status.get("episode_id"))
        if episode_id and record_episode_id and episode_id == record_episode_id:
            score += 100
        asset_tokens = {
            _first_string(record.get("asset_id")),
            _first_string(provenance.get("asset_id")),
        }
        for token in asset_tokens:
            if token and token.lower() in normalized_content:
                score += 80 + min(len(token), 80)
        for value in (
            provenance.get("source_report_id"),
            provenance.get("evidence_id"),
            provenance.get("source_ticket_id"),
        ):
            token = _first_string(value)
            if token and token.lower() in normalized_content:
                score += 20 + min(len(token), 40)
        source_ref = _first_string(provenance.get("source_ref"))
        if source_ref and source_ref.lower() in normalized_content:
            score += 20
        if score >= 40 and (best is None or score > best[0]):
            best = (score, provenance)
    return dict(best[1]) if best is not None else None


def _accepts_kwarg(parameters: Mapping[str, inspect.Parameter], name: str) -> bool:
    return name in parameters or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())


async def _ingest_graphiti(candidate: MemoryCandidate) -> dict[str, Any]:
    status = graphiti_backend_status()
    if status.status != "ready":
        return {"status": status.status, "detail": status.detail}

    asset_provenance = _graphiti_asset_provenance(candidate)
    episode_body = (
        f"Memory id: {candidate.id}\n"
        f"Scope: {candidate.scope_kind}:{candidate.scope_ref}\n"
        f"Employees: {', '.join(candidate.employee_ids) or 'all'}\n"
        f"Content: {candidate.content}\n"
        "AITeamOS provenance:\n"
        f"{json.dumps(asset_provenance, ensure_ascii=False, sort_keys=True)}"
    )
    source_kind = candidate.source_kind.strip() or "memory_candidate"
    source_description = f"AITeamOS {source_kind} memory candidate"
    source_selector = "message" if candidate.source_kind == "chat" else "text"
    return await _ingest_graphiti_episode(
        name=f"AITeamOS memory {candidate.id}",
        episode_body=episode_body,
        source_description=source_description,
        source_selector=source_selector,
        provenance=asset_provenance,
        success_detail="Approved memory was ingested into Graphiti.",
    )


async def _ingest_graphiti_episode(
    *,
    name: str,
    episode_body: str,
    source_description: str,
    source_selector: str,
    provenance: dict[str, Any],
    success_detail: str,
) -> dict[str, Any]:
    status = graphiti_backend_status()
    if status.status != "ready":
        return {"status": status.status, "detail": status.detail}

    config = _graphiti_config()
    graphiti_cls, episode_type = _graphiti_package()
    previous_env = _set_graphiti_environment(config)
    graphiti = _new_graphiti_client(graphiti_cls, config)
    try:
        build_indices = getattr(graphiti, "build_indices_and_constraints", None)
        if build_indices is not None:
            await _maybe_await(build_indices())

        source = getattr(episode_type, source_selector, None) or episode_type.text
        add_episode = getattr(graphiti, "add_episode")
        parameters = inspect.signature(add_episode).parameters
        kwargs: dict[str, Any] = {
            "name": name,
            "episode_body": episode_body,
            "source": source,
            "source_description": source_description,
            "reference_time": datetime.now(UTC),
        }
        if _accepts_kwarg(parameters, "group_id"):
            kwargs["group_id"] = config["group_id"]
        result = await _maybe_await(add_episode(**kwargs))
        episode = getattr(result, "episode", None)
        episode_id = getattr(episode, "uuid", None) or getattr(result, "uuid", None)
        return {
            "status": "ingested",
            "detail": success_detail,
            "episode_id": str(episode_id) if episode_id else None,
            "episode_schema_version": GRAPHITI_EPISODE_SCHEMA_VERSION,
            "provenance": provenance,
        }
    except Exception as exc:
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
    graphiti_status = await _ingest_graphiti(candidate)
    if graphiti_status.get("status") != "ingested":
        state = {
            "last_blocked_at": timestamp,
            "last_candidate_id": candidate.id,
            "last_graphiti_status": graphiti_status,
            "backend": graphiti_backend_status().model_dump(mode="json"),
        }
        _write_json(_state_path(), state)
        raise ValueError(
            "Graphiti Memory / Asset Graph setup blocker: "
            + str(graphiti_status.get("detail") or graphiti_status.get("status") or "ingestion failed")
        )

    candidate.graphiti_status = graphiti_status
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


async def ingest_durable_asset_to_graphiti(request: DurableAssetIngestRequest) -> DurableAssetIngestResponse:
    allowed_statuses = {"approved", "validated", "accepted"}
    asset_status = request.asset_status.strip().lower()
    if asset_status not in allowed_statuses:
        raise ValueError("Graphiti only ingests approved, accepted, or validated durable assets.")

    asset_type = request.asset_type.strip()
    asset_id = request.asset_id.strip()
    content = request.content.strip()
    provenance = _durable_asset_provenance(
        request.model_copy(update={"asset_status": asset_status, "asset_type": asset_type, "asset_id": asset_id, "content": content})
    )
    scope = provenance.get("scope") if isinstance(provenance.get("scope"), dict) else {}
    scope_ref = str(scope.get("ref") or provenance.get("source_ticket_id") or "aiteamos").strip()
    episode_body = (
        f"Durable asset id: {asset_id}\n"
        f"Type: {asset_type}\n"
        f"Status: {asset_status}\n"
        f"Scope: {json.dumps(scope, ensure_ascii=False, sort_keys=True)}\n"
        f"Content: {content}\n"
        "AITeamOS provenance:\n"
        f"{json.dumps(provenance, ensure_ascii=False, sort_keys=True)}"
    )
    graphiti_status = await _ingest_graphiti_episode(
        name=f"AITeamOS durable asset {asset_id}",
        episode_body=episode_body,
        source_description=f"AITeamOS {asset_type} durable asset",
        source_selector="text",
        provenance=provenance,
        success_detail="Validated durable asset was ingested into Graphiti.",
    )
    timestamp = _now()
    state = _read_json_object(_state_path())
    durable_ingestions = state.get("durable_asset_ingestions")
    if not isinstance(durable_ingestions, list):
        durable_ingestions = []
    audit_record = {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "asset_status": asset_status,
        "source_ticket_id": provenance.get("source_ticket_id", ""),
        "scope_ref": scope_ref,
        "ingested_at": timestamp,
        "graphiti_status": graphiti_status,
    }
    durable_ingestions.append(audit_record)
    durable_ingestions = [item for item in durable_ingestions if isinstance(item, dict)][-100:]
    state.update(
        {
            "last_durable_asset_at": timestamp,
            "last_durable_asset_id": asset_id,
            "last_durable_asset_status": graphiti_status,
            "durable_asset_ingestions": durable_ingestions,
            "backend": graphiti_backend_status().model_dump(mode="json"),
        }
    )
    _write_json(_state_path(), state)
    if graphiti_status.get("status") != "ingested":
        raise ValueError(
            "Graphiti Memory / Asset Graph setup blocker: "
            + str(graphiti_status.get("detail") or graphiti_status.get("status") or "ingestion failed")
        )
    return DurableAssetIngestResponse(
        status="ingested",
        detail=str(graphiti_status.get("detail") or "Validated durable asset was ingested into Graphiti."),
        episode_id=graphiti_status.get("episode_id") if isinstance(graphiti_status.get("episode_id"), str) else None,
        episode_schema_version=GRAPHITI_EPISODE_SCHEMA_VERSION,
        provenance=provenance,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


def _safe_asset_id_component(value: str) -> str:
    component = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip()).strip("-")
    return component[:72] or "asset"


def _durable_asset_relationship_id(request: DurableAssetRelationshipIngestRequest) -> str:
    relationship_type = request.relationship_type.strip().lower()
    digest_source = f"{request.source_asset_id.strip()}|{relationship_type}|{request.target_asset_id.strip()}"
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:12]
    return (
        "asset-relationship-"
        f"{_safe_asset_id_component(relationship_type)}-"
        f"{_safe_asset_id_component(request.source_asset_id)}-"
        f"{_safe_asset_id_component(request.target_asset_id)}-"
        f"{digest}"
    )[:180]


def _relationship_public_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    public_keys = {"reason", "confidence", "review_status", "usage_id", "source_kind", "source_ref"}
    public: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key).strip()
        if key_text in public_keys:
            public[key_text] = value
    return public


def _durable_asset_relationship_request(request: DurableAssetRelationshipIngestRequest) -> DurableAssetIngestRequest:
    relationship_type = request.relationship_type.strip().lower()
    if relationship_type not in _DURABLE_ASSET_RELATIONSHIP_TYPES:
        allowed = ", ".join(sorted(_DURABLE_ASSET_RELATIONSHIP_TYPES))
        raise ValueError(f"Unsupported durable asset relationship type: {relationship_type}. Allowed: {allowed}.")
    source_asset_id = request.source_asset_id.strip()
    target_asset_id = request.target_asset_id.strip()
    reason = request.reason.strip()
    relationship_id = _durable_asset_relationship_id(request)
    scope = request.scope if isinstance(request.scope, dict) else {}
    if not scope:
        scope = {"kind": "asset", "ref": source_asset_id}
    metadata = {
        **_relationship_public_metadata(request.metadata),
        "source_asset_id": source_asset_id,
        "target_asset_id": target_asset_id,
        "relationship_type": relationship_type,
        "reason": reason,
    }
    return DurableAssetIngestRequest(
        asset_id=relationship_id,
        asset_type="asset_relationship",
        asset_status=request.asset_status.strip().lower() or "validated",
        content=_compact_text(
            f"Durable asset relationship: {source_asset_id} {relationship_type} {target_asset_id}. "
            f"Reason: {reason or '-'}",
            1200,
        ),
        source_ticket_id=request.source_ticket_id,
        source_employee_id=request.source_employee_id,
        source_run_id=request.source_run_id,
        source_report_id=request.source_report_id,
        evidence_id=request.evidence_id,
        scope=scope,
        provider_refs=request.provider_refs,
        source_ref=request.source_ref,
        source_kind="durable_asset_relationship",
        metadata=metadata,
    )


async def ingest_durable_asset_relationship_to_graphiti(
    request: DurableAssetRelationshipIngestRequest,
) -> DurableAssetRelationshipIngestResponse:
    durable_request = _durable_asset_relationship_request(request)
    existing = _durable_asset_ingestion_record(durable_request.asset_id)
    relationship_type = request.relationship_type.strip().lower()
    if existing is not None:
        graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
        return DurableAssetRelationshipIngestResponse(
            relationship_id=durable_request.asset_id,
            relationship_type=relationship_type,
            source_asset_id=request.source_asset_id.strip(),
            target_asset_id=request.target_asset_id.strip(),
            status="skipped",
            detail="Durable asset relationship already exists in Graphiti ingestion audit.",
            skipped_asset={
                "asset_id": durable_request.asset_id,
                "asset_type": durable_request.asset_type,
                "reason": "already_ingested",
                "episode_id": str(graphiti_status.get("episode_id") or ""),
            },
            saved_paths={"graphiti_state": _relative(_state_path())},
        )

    ingested = await ingest_durable_asset_to_graphiti(durable_request)
    return DurableAssetRelationshipIngestResponse(
        relationship_id=durable_request.asset_id,
        relationship_type=relationship_type,
        source_asset_id=request.source_asset_id.strip(),
        target_asset_id=request.target_asset_id.strip(),
        status="ingested",
        detail="Durable asset relationship was projected to Graphiti.",
        ingested_asset=ingested,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


def _ticket_is_validated(ticket: Any) -> bool:
    status = str(getattr(ticket, "status", "") or "").strip().lower()
    if status in _DURABLE_TICKET_STATUSES:
        return True
    for report in getattr(ticket, "reports", []) or []:
        report_type = str(getattr(report, "report_type", "") or "").strip().lower()
        if report_type in _DURABLE_VALIDATION_REPORT_TYPES:
            return True
    return False


def _ticket_provider_refs(ticket: Any) -> list[dict[str, Any]]:
    provider_ref = getattr(ticket, "provider_ref", None)
    if provider_ref is None:
        return []
    if hasattr(provider_ref, "model_dump"):
        return [provider_ref.model_dump(mode="json")]
    if isinstance(provider_ref, dict):
        return [dict(provider_ref)]
    return []


def _report_source_run_id(ticket: Any, report: Any) -> str:
    source_event_id = str(getattr(report, "source_event_id", "") or "").strip()
    for event in getattr(ticket, "events", []) or []:
        if str(getattr(event, "event_id", "") or "").strip() != source_event_id:
            continue
        data = getattr(event, "data", {})
        if isinstance(data, dict):
            return _first_string(data.get("source_run_id"))
    return _first_string(getattr(ticket, "source_run_id", ""))


def _ticket_summary_durable_asset_request(ticket: Any) -> DurableAssetIngestRequest:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    ticket_title = str(getattr(ticket, "title", "") or ticket_id).strip()
    description = str(getattr(ticket, "description", "") or "").strip()
    status = str(getattr(ticket, "status", "") or "").strip()
    ticket_type = str(getattr(ticket, "ticket_type", "") or "").strip()
    assigned_employee_id = str(getattr(ticket, "assigned_employee_id", "") or "").strip()
    assigned_role = str(getattr(ticket, "assigned_role", "") or "").strip()
    validation_employee_id = str(getattr(ticket, "validation_employee_id", "") or "").strip()
    validation_role = str(getattr(ticket, "validation_role", "") or "").strip()
    knowledge_refs = [str(item).strip() for item in getattr(ticket, "knowledge_refs", []) or [] if str(item).strip()]
    code_repository_ids = [
        str(item).strip()
        for item in getattr(ticket, "code_repository_ids", []) or []
        if str(item).strip()
    ]
    reports = [report for report in getattr(ticket, "reports", []) or []]
    report_count = len(reports)
    evidence_count = sum(len(getattr(report, "evidence", []) or []) for report in reports)
    provider_refs = _ticket_provider_refs(ticket)
    source_employee_id = assigned_employee_id or validation_employee_id
    return DurableAssetIngestRequest(
        asset_id=f"ticket-summary-{ticket_id}",
        asset_type="ticket_summary",
        asset_status="validated",
        content=_compact_text(
            f"Validated Ticket summary for {ticket_id} ({ticket_title}). "
            f"Type: {ticket_type or '-'} "
            f"Status: {status or '-'} "
            f"Assignee: {assigned_employee_id or assigned_role or '-'} "
            f"Validator: {validation_employee_id or validation_role or '-'} "
            f"Reports: {report_count}; Evidence items: {evidence_count}. "
            f"Description: {description or '-'}",
            1400,
        ),
        source_ticket_id=ticket_id,
        source_employee_id=source_employee_id,
        source_run_id=_first_string(getattr(ticket, "source_run_id", "")),
        source_report_id="",
        evidence_id="",
        scope={"kind": "ticket", "ref": ticket_id},
        provider_refs=provider_refs,
        source_ref=f"tickets/{ticket_id}",
        source_kind="validated_ticket_summary",
        metadata={
            "ticket_title": ticket_title,
            "ticket_type": ticket_type,
            "ticket_status": status,
            "assigned_employee_id": assigned_employee_id,
            "assigned_role": assigned_role,
            "validation_employee_id": validation_employee_id,
            "validation_role": validation_role,
            "knowledge_refs": knowledge_refs,
            "code_repository_ids": code_repository_ids,
            "report_count": report_count,
            "evidence_count": evidence_count,
        },
    )


def _ticket_report_durable_asset_requests(ticket: Any) -> list[DurableAssetIngestRequest]:
    ticket_id = str(getattr(ticket, "id", "") or "").strip()
    ticket_title = str(getattr(ticket, "title", "") or ticket_id).strip()
    provider_refs = _ticket_provider_refs(ticket)
    requests: list[DurableAssetIngestRequest] = [_ticket_summary_durable_asset_request(ticket)]
    for report in getattr(ticket, "reports", []) or []:
        report_id = str(getattr(report, "id", "") or "").strip()
        if not report_id:
            continue
        report_type = str(getattr(report, "report_type", "") or "report").strip().lower()
        if report_type in _NON_DURABLE_REPORT_TYPES:
            continue
        reporter_employee_id = str(getattr(report, "reporter_employee_id", "") or "").strip()
        source_run_id = _report_source_run_id(ticket, report)
        report_content = str(getattr(report, "content", "") or "").strip()
        evidence_items = [str(item).strip() for item in getattr(report, "evidence", []) or [] if str(item).strip()]
        if report_content:
            requests.append(
                DurableAssetIngestRequest(
                    asset_id=f"report-summary-{ticket_id}-{report_id}",
                    asset_type="report_summary",
                    asset_status="validated",
                    content=_compact_text(
                        f"Validated report summary for Ticket {ticket_id} ({ticket_title}). "
                        f"Report {report_id} type={report_type} by {reporter_employee_id or 'unknown Employee'}: {report_content}",
                        1200,
                    ),
                    source_ticket_id=ticket_id,
                    source_employee_id=reporter_employee_id,
                    source_run_id=source_run_id,
                    source_report_id=report_id,
                    evidence_id="",
                    scope={"kind": "ticket", "ref": ticket_id},
                    provider_refs=provider_refs,
                    source_ref=f"tickets/{ticket_id}/reports/{report_id}",
                    source_kind="validated_report_summary",
                    metadata={
                        "ticket_title": ticket_title,
                        "report_type": report_type,
                        "evidence_count": len(evidence_items),
                    },
                )
            )
        for index, evidence in enumerate(evidence_items):
            evidence_id = f"{report_id}:evidence:{index}"
            requests.append(
                DurableAssetIngestRequest(
                    asset_id=f"evidence-summary-{ticket_id}-{report_id}-{index}",
                    asset_type="evidence_summary",
                    asset_status="validated",
                    content=_compact_text(
                        f"Validated evidence summary for Ticket {ticket_id} ({ticket_title}). "
                        f"Evidence {evidence_id} from report {report_id} type={report_type}: {evidence}",
                        1200,
                    ),
                    source_ticket_id=ticket_id,
                    source_employee_id=reporter_employee_id,
                    source_run_id=source_run_id,
                    source_report_id=report_id,
                    evidence_id=evidence_id,
                    scope={"kind": "ticket", "ref": ticket_id},
                    provider_refs=provider_refs,
                    source_ref=f"tickets/{ticket_id}/reports/{report_id}#evidence-{index}",
                    source_kind="validated_evidence_summary",
                    metadata={
                        "ticket_title": ticket_title,
                        "report_type": report_type,
                        "evidence_index": index,
                    },
                )
            )
    return requests


def _decision_durable_asset_request(decision: Any) -> DurableAssetIngestRequest:
    decision_id = str(getattr(decision, "id", "") or "").strip()
    title = str(getattr(decision, "title", "") or decision_id).strip()
    status = str(getattr(decision, "status", "") or "").strip().lower()
    context = str(getattr(decision, "context", "") or "").strip()
    decision_text = str(getattr(decision, "decision", "") or "").strip()
    consequences = str(getattr(decision, "consequences", "") or "").strip()
    linked_tickets = [
        str(item).strip()
        for item in getattr(decision, "linked_tickets", []) or []
        if str(item).strip()
    ]
    linked_memories = [
        str(item).strip()
        for item in getattr(decision, "linked_memories", []) or []
        if str(item).strip()
    ]
    source_ticket_id = linked_tickets[0] if linked_tickets else ""
    source_ref = str(getattr(decision, "saved_path", "") or "").strip() or f"knowledge/decisions/{decision_id}"
    return DurableAssetIngestRequest(
        asset_id=decision_id,
        asset_type="decision",
        asset_status=status,
        content=_compact_text(
            f"Accepted Decision {decision_id} ({title}). "
            f"Context: {context or '-'} "
            f"Decision: {decision_text} "
            f"Consequences: {consequences or '-'}",
            1400,
        ),
        source_ticket_id=source_ticket_id,
        source_employee_id="",
        source_run_id="",
        source_report_id="",
        evidence_id="",
        scope={"kind": "ticket", "ref": source_ticket_id} if source_ticket_id else {"kind": "project", "ref": "aiteamos"},
        source_ref=source_ref,
        source_kind="accepted_decision",
        metadata={
            "title": title,
            "linked_tickets": linked_tickets,
            "linked_memories": linked_memories,
        },
    )


async def ingest_accepted_decision_durable_asset(decision_id: str) -> DecisionDurableAssetProjectionResponse:
    from .knowledge_service import list_decisions

    normalized_decision_id = decision_id.strip()
    decision = next((item for item in list_decisions() if item.id == normalized_decision_id), None)
    if decision is None:
        raise KeyError(normalized_decision_id)
    status = str(decision.status or "").strip().lower()
    if status not in _ACCEPTED_DECISION_STATUSES:
        raise ValueError("Only accepted Decisions can project into Graphiti.")

    request = _decision_durable_asset_request(decision)
    existing = _durable_asset_ingestion_record(request.asset_id)
    if existing is not None:
        graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
        return DecisionDurableAssetProjectionResponse(
            decision_id=normalized_decision_id,
            status="skipped",
            detail="Accepted Decision durable asset already exists in Graphiti ingestion audit.",
            skipped_asset={
                "asset_id": request.asset_id,
                "asset_type": request.asset_type,
                "reason": "already_ingested",
                "episode_id": str(graphiti_status.get("episode_id") or ""),
            },
            saved_paths={"graphiti_state": _relative(_state_path())},
        )

    ingested = await ingest_durable_asset_to_graphiti(request)
    return DecisionDurableAssetProjectionResponse(
        decision_id=normalized_decision_id,
        status="ingested",
        detail="Accepted Decision durable asset was projected to Graphiti.",
        ingested_asset=ingested,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


async def ingest_accepted_decision_durable_assets(
    *,
    max_assets: int = 20,
) -> DecisionDurableAssetBatchProjectionResponse:
    from .knowledge_service import list_decisions

    ingested: list[DurableAssetIngestResponse] = []
    skipped: list[dict[str, str]] = []
    capped_max_assets = max(1, min(max_assets, 50))
    accepted_decisions = [
        decision
        for decision in list_decisions()
        if str(decision.status or "").strip().lower() in _ACCEPTED_DECISION_STATUSES
    ]
    for decision in accepted_decisions:
        request = _decision_durable_asset_request(decision)
        existing = _durable_asset_ingestion_record(request.asset_id)
        if existing is not None:
            graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "already_ingested",
                    "episode_id": str(graphiti_status.get("episode_id") or ""),
                }
            )
            continue
        if len(ingested) >= capped_max_assets:
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "max_assets_limit",
                    "episode_id": "",
                }
            )
            continue
        ingested.append(await ingest_durable_asset_to_graphiti(request))

    status = "ingested" if ingested else "skipped" if skipped else "no_assets"
    return DecisionDurableAssetBatchProjectionResponse(
        status=status,
        detail=(
            "Accepted Decision durable assets were projected to Graphiti."
            if ingested
            else "No new accepted Decision durable assets needed Graphiti ingestion."
        ),
        ingested_assets=ingested,
        skipped_assets=skipped,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


def _skill_durable_asset_request(skill: Any) -> DurableAssetIngestRequest:
    skill_id = str(getattr(skill, "id", "") or "").strip()
    title = str(getattr(skill, "title", "") or skill_id).strip()
    status = str(getattr(skill, "status", "") or "approved").strip().lower()
    metadata = getattr(skill, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    description = _first_string(metadata.get("description"))
    content = _first_string(metadata.get("content"), description, title)
    assigned_employees = [
        str(item).strip()
        for item in getattr(skill, "assigned_employees", []) or []
        if str(item).strip()
    ]
    scopes = [str(item).strip() for item in getattr(skill, "scopes", []) or [] if str(item).strip()]
    source_employee_id = assigned_employees[0] if assigned_employees else ""
    source_ref = _first_string(
        metadata.get("saved_path"),
        metadata.get("source_ref"),
        f"assets/capabilities/skills/{skill_id}",
    )
    scope = (
        {"kind": "employee", "ref": source_employee_id}
        if source_employee_id
        else {"kind": "capability", "ref": skill_id}
    )
    return DurableAssetIngestRequest(
        asset_id=f"skill-summary-{skill_id}",
        asset_type="skill_summary",
        asset_status=status,
        content=_compact_text(
            f"Approved Skill summary for {skill_id} ({title}). "
            f"Description: {description or '-'} "
            f"Content: {content}",
            1600,
        ),
        source_ticket_id="",
        source_employee_id=source_employee_id,
        source_run_id="",
        source_report_id="",
        evidence_id="",
        scope=scope,
        source_ref=source_ref,
        source_kind="approved_skill_summary",
        metadata={
            "source_asset_id": skill_id,
            "title": title,
            "description": description,
            "assigned_employees": assigned_employees,
            "scopes": scopes,
            "resources": metadata.get("resources") if isinstance(metadata.get("resources"), list) else [],
            "source": metadata.get("source") or "",
            "source_ref": metadata.get("source_ref") or source_ref,
        },
    )


def _approved_skill_assets() -> list[Any]:
    from .knowledge_service import all_asset_items

    return [
        item
        for item in all_asset_items()
        if str(getattr(item, "kind", "") or "").strip().lower() == "skill"
        and str(getattr(item, "status", "") or "").strip().lower() == "approved"
    ]


async def ingest_approved_skill_durable_asset(skill_id: str) -> SkillDurableAssetProjectionResponse:
    normalized_skill_id = skill_id.strip()
    skill = next((item for item in _approved_skill_assets() if item.id == normalized_skill_id), None)
    if skill is None:
        raise KeyError(normalized_skill_id)

    request = _skill_durable_asset_request(skill)
    existing = _durable_asset_ingestion_record(request.asset_id)
    if existing is not None:
        graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
        return SkillDurableAssetProjectionResponse(
            skill_id=normalized_skill_id,
            status="skipped",
            detail="Approved Skill durable asset already exists in Graphiti ingestion audit.",
            skipped_asset={
                "asset_id": request.asset_id,
                "asset_type": request.asset_type,
                "reason": "already_ingested",
                "episode_id": str(graphiti_status.get("episode_id") or ""),
            },
            saved_paths={"graphiti_state": _relative(_state_path())},
        )

    ingested = await ingest_durable_asset_to_graphiti(request)
    return SkillDurableAssetProjectionResponse(
        skill_id=normalized_skill_id,
        status="ingested",
        detail="Approved Skill durable asset was projected to Graphiti.",
        ingested_asset=ingested,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


async def ingest_approved_skill_durable_assets(
    *,
    max_assets: int = 20,
) -> SkillDurableAssetBatchProjectionResponse:
    ingested: list[DurableAssetIngestResponse] = []
    skipped: list[dict[str, str]] = []
    capped_max_assets = max(1, min(max_assets, 50))
    for skill in _approved_skill_assets():
        request = _skill_durable_asset_request(skill)
        existing = _durable_asset_ingestion_record(request.asset_id)
        if existing is not None:
            graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "already_ingested",
                    "episode_id": str(graphiti_status.get("episode_id") or ""),
                }
            )
            continue
        if len(ingested) >= capped_max_assets:
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "max_assets_limit",
                    "episode_id": "",
                }
            )
            continue
        ingested.append(await ingest_durable_asset_to_graphiti(request))

    status = "ingested" if ingested else "skipped" if skipped else "no_assets"
    return SkillDurableAssetBatchProjectionResponse(
        status=status,
        detail=(
            "Approved Skill durable assets were projected to Graphiti."
            if ingested
            else "No new approved Skill durable assets needed Graphiti ingestion."
        ),
        ingested_assets=ingested,
        skipped_assets=skipped,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


def _doc_durable_asset_request(doc: Any) -> DurableAssetIngestRequest:
    doc_id = str(getattr(doc, "id", "") or "").strip()
    title = str(getattr(doc, "title", "") or doc_id).strip()
    path = str(getattr(doc, "path", "") or "").strip()
    tags = [str(item).strip() for item in getattr(doc, "tags", []) or [] if str(item).strip()]
    excerpt = str(getattr(doc, "excerpt", "") or "").strip()
    content = str(getattr(doc, "content", "") or "").strip()
    summary_source = content or excerpt or title
    return DurableAssetIngestRequest(
        asset_id=f"doc-summary-{doc_id}",
        asset_type="doc_summary",
        asset_status="approved",
        content=_compact_text(
            f"Approved Doc summary for {doc_id} ({title}). "
            f"Path: {path or '-'} "
            f"Excerpt: {excerpt or '-'} "
            f"Content: {summary_source}",
            1800,
        ),
        source_ticket_id="",
        source_employee_id="",
        source_run_id="",
        source_report_id="",
        evidence_id="",
        scope={"kind": "doc", "ref": doc_id},
        source_ref=path,
        source_kind="approved_doc_summary",
        metadata={
            "source_asset_id": doc_id,
            "title": title,
            "path": path,
            "tags": tags,
            "excerpt": excerpt,
        },
    )


def _approved_docs() -> list[Any]:
    from .knowledge_service import list_docs

    docs: list[Any] = []
    for doc in list_docs():
        path = str(getattr(doc, "path", "") or "")
        tags = [str(item).strip() for item in getattr(doc, "tags", []) or [] if str(item).strip()]
        if "decision" in tags or path.startswith(".aiteamos/knowledge/decisions/"):
            continue
        docs.append(doc)
    return docs


async def ingest_approved_doc_durable_asset(doc_id: str) -> DocDurableAssetProjectionResponse:
    normalized_doc_id = doc_id.strip()
    doc = next((item for item in _approved_docs() if item.id == normalized_doc_id), None)
    if doc is None:
        raise KeyError(normalized_doc_id)

    request = _doc_durable_asset_request(doc)
    existing = _durable_asset_ingestion_record(request.asset_id)
    if existing is not None:
        graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
        return DocDurableAssetProjectionResponse(
            doc_id=normalized_doc_id,
            status="skipped",
            detail="Approved Doc durable asset already exists in Graphiti ingestion audit.",
            skipped_asset={
                "asset_id": request.asset_id,
                "asset_type": request.asset_type,
                "reason": "already_ingested",
                "episode_id": str(graphiti_status.get("episode_id") or ""),
            },
            saved_paths={"graphiti_state": _relative(_state_path())},
        )

    ingested = await ingest_durable_asset_to_graphiti(request)
    return DocDurableAssetProjectionResponse(
        doc_id=normalized_doc_id,
        status="ingested",
        detail="Approved Doc durable asset was projected to Graphiti.",
        ingested_asset=ingested,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


async def ingest_approved_doc_durable_assets(
    *,
    max_assets: int = 20,
) -> DocDurableAssetBatchProjectionResponse:
    ingested: list[DurableAssetIngestResponse] = []
    skipped: list[dict[str, str]] = []
    capped_max_assets = max(1, min(max_assets, 50))
    for doc in _approved_docs():
        request = _doc_durable_asset_request(doc)
        existing = _durable_asset_ingestion_record(request.asset_id)
        if existing is not None:
            graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "already_ingested",
                    "episode_id": str(graphiti_status.get("episode_id") or ""),
                }
            )
            continue
        if len(ingested) >= capped_max_assets:
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "max_assets_limit",
                    "episode_id": "",
                }
            )
            continue
        ingested.append(await ingest_durable_asset_to_graphiti(request))

    status = "ingested" if ingested else "skipped" if skipped else "no_assets"
    return DocDurableAssetBatchProjectionResponse(
        status=status,
        detail=(
            "Approved Doc durable assets were projected to Graphiti."
            if ingested
            else "No new approved Doc durable assets needed Graphiti ingestion."
        ),
        ingested_assets=ingested,
        skipped_assets=skipped,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


def _employee_profiles_dir() -> Path:
    return _workspace_dir() / "employees"


def _profile_string_list(profile: Mapping[str, Any], key: str) -> list[str]:
    raw = profile.get(key)
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    value = str(raw or "").strip()
    return [value] if value else []


def _employee_profile_records() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for path in sorted(_employee_profiles_dir().glob("*.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError:
            continue
        if not isinstance(payload, dict):
            continue
        employee_id = str(payload.get("id") or path.stem).strip()
        if not employee_id:
            continue
        profile = dict(payload)
        profile["id"] = employee_id
        profile["source_ref"] = _relative(path)
        profiles.append(profile)
    return profiles


def _employee_profile_durable_asset_request(profile: Mapping[str, Any]) -> DurableAssetIngestRequest:
    employee_id = str(profile.get("id") or "").strip()
    display_name = str(profile.get("display_name") or employee_id).strip()
    kind = str(profile.get("kind") or "ai").strip()
    role = str(profile.get("role") or "AI Employee").strip()
    summary = str(profile.get("summary") or "").strip()
    personality = str(profile.get("personality") or "").strip()
    responsibilities = _profile_string_list(profile, "responsibilities")
    skills = _profile_string_list(profile, "skills")
    memory_scopes = _profile_string_list(profile, "memory_scopes")
    handoff_rules = _profile_string_list(profile, "handoff_rules")
    source_ref = str(profile.get("source_ref") or f".aiteamos/employees/{employee_id}.yaml").strip()
    content = _compact_text(
        f"Approved Employee profile summary for {employee_id} ({display_name}). "
        f"Kind: {kind or '-'} "
        f"Role: {role or '-'} "
        f"Summary: {summary or '-'} "
        f"Personality: {personality or '-'} "
        f"Responsibilities: {'; '.join(responsibilities) or '-'} "
        f"Skills: {', '.join(skills) or '-'} "
        f"Memory scopes: {', '.join(memory_scopes) or '-'} "
        f"Handoff rules: {'; '.join(handoff_rules) or '-'}",
        1600,
    )
    return DurableAssetIngestRequest(
        asset_id=f"employee-profile-{employee_id}",
        asset_type="employee_profile_summary",
        asset_status="approved",
        content=content,
        source_ticket_id="",
        source_employee_id=employee_id,
        source_run_id="",
        source_report_id="",
        evidence_id="",
        scope={"kind": "employee", "ref": employee_id},
        source_ref=source_ref,
        source_kind="approved_employee_profile_summary",
        metadata={
            "source_asset_id": employee_id,
            "display_name": display_name,
            "kind": kind,
            "role": role,
            "summary": summary,
            "skills": skills,
            "memory_scopes": memory_scopes,
            "responsibilities": responsibilities,
            "handoff_rules": handoff_rules,
            "source_ref": source_ref,
        },
    )


async def ingest_approved_employee_profile_durable_asset(employee_id: str) -> EmployeeDurableAssetProjectionResponse:
    normalized_employee_id = employee_id.strip()
    profile = next((item for item in _employee_profile_records() if item["id"] == normalized_employee_id), None)
    if profile is None:
        raise KeyError(normalized_employee_id)

    request = _employee_profile_durable_asset_request(profile)
    existing = _durable_asset_ingestion_record(request.asset_id)
    if existing is not None:
        graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
        return EmployeeDurableAssetProjectionResponse(
            employee_id=normalized_employee_id,
            status="skipped",
            detail="Approved Employee profile durable asset already exists in Graphiti ingestion audit.",
            skipped_asset={
                "asset_id": request.asset_id,
                "asset_type": request.asset_type,
                "reason": "already_ingested",
                "episode_id": str(graphiti_status.get("episode_id") or ""),
            },
            saved_paths={"graphiti_state": _relative(_state_path())},
        )

    ingested = await ingest_durable_asset_to_graphiti(request)
    return EmployeeDurableAssetProjectionResponse(
        employee_id=normalized_employee_id,
        status="ingested",
        detail="Approved Employee profile durable asset was projected to Graphiti.",
        ingested_asset=ingested,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


async def ingest_approved_employee_profile_durable_assets(
    *,
    max_assets: int = 20,
) -> EmployeeDurableAssetBatchProjectionResponse:
    ingested: list[DurableAssetIngestResponse] = []
    skipped: list[dict[str, str]] = []
    capped_max_assets = max(1, min(max_assets, 50))
    for profile in _employee_profile_records():
        request = _employee_profile_durable_asset_request(profile)
        existing = _durable_asset_ingestion_record(request.asset_id)
        if existing is not None:
            graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "already_ingested",
                    "episode_id": str(graphiti_status.get("episode_id") or ""),
                }
            )
            continue
        if len(ingested) >= capped_max_assets:
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "max_assets_limit",
                    "episode_id": "",
                }
            )
            continue
        ingested.append(await ingest_durable_asset_to_graphiti(request))

    status = "ingested" if ingested else "skipped" if skipped else "no_assets"
    return EmployeeDurableAssetBatchProjectionResponse(
        status=status,
        detail=(
            "Approved Employee profile durable assets were projected to Graphiti."
            if ingested
            else "No new approved Employee profile durable assets needed Graphiti ingestion."
        ),
        ingested_assets=ingested,
        skipped_assets=skipped,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


def _capability_is_durable(capability: Any) -> bool:
    status = str(getattr(capability, "status", "") or "").strip().lower()
    enabled = bool(getattr(capability, "enabled", False))
    configured = bool(getattr(capability, "configured", False))
    return status in {"ready", "active", "configured", "local"} and enabled and configured


def _capability_durable_asset_request(capability: Any) -> DurableAssetIngestRequest:
    capability_id = str(getattr(capability, "id", "") or "").strip()
    name = str(getattr(capability, "name", "") or capability_id).strip()
    kind = str(getattr(capability, "kind", "") or "tool").strip()
    capability_source_kind = str(getattr(capability, "source_kind", "") or "").strip()
    domain = str(getattr(capability, "domain", "") or "").strip()
    source = str(getattr(capability, "source", "") or "").strip()
    status = str(getattr(capability, "status", "") or "ready").strip()
    description = str(getattr(capability, "description", "") or "").strip()
    owner_scope = str(getattr(capability, "owner_scope", "") or "").strip()
    arguments = [str(item).strip() for item in getattr(capability, "arguments", []) or [] if str(item).strip()]
    produces = [str(item).strip() for item in getattr(capability, "produces", []) or [] if str(item).strip()]
    boundary = str(getattr(capability, "boundary", "") or "").strip()
    deep_link = str(getattr(capability, "deep_link", "") or "").strip()
    connector_id = str(getattr(capability, "connector_id", "") or "").strip()
    source_ref = (
        f"tool_connector:{connector_id}:{capability_id}"
        if connector_id
        else f"capability_registry:{capability_source_kind or kind}:{capability_id}"
    )
    return DurableAssetIngestRequest(
        asset_id=f"capability-{capability_id}",
        asset_type="capability_summary",
        asset_status="approved",
        content=_compact_text(
            f"Approved Capability summary for {capability_id} ({name}). "
            f"Kind: {kind or '-'} "
            f"Source kind: {capability_source_kind or '-'} "
            f"Domain: {domain or '-'} "
            f"Status: {status or '-'} "
            f"Description: {description or '-'} "
            f"Owner scope: {owner_scope or '-'} "
            f"Arguments: {', '.join(arguments) or '-'} "
            f"Produces: {', '.join(produces) or '-'} "
            f"Boundary: {boundary or '-'} "
            f"Deep link: {deep_link or '-'}",
            1600,
        ),
        source_ticket_id="",
        source_employee_id="",
        source_run_id="",
        source_report_id="",
        evidence_id="",
        scope={"kind": "capability", "ref": capability_id},
        source_ref=source_ref,
        source_kind="approved_capability_summary",
        metadata={
            "source_asset_id": capability_id,
            "name": name,
            "kind": kind,
            "capability_source_kind": capability_source_kind,
            "domain": domain,
            "source": source,
            "status": status,
            "enabled": bool(getattr(capability, "enabled", False)),
            "configured": bool(getattr(capability, "configured", False)),
            "description": description,
            "owner_scope": owner_scope,
            "arguments": arguments,
            "produces": produces,
            "boundary": boundary,
            "deep_link": deep_link,
            "connector_id": connector_id,
            "source_ref": source_ref,
        },
    )


def _durable_capabilities() -> list[Any]:
    from .capability_service import list_capabilities

    return [item for item in list_capabilities() if _capability_is_durable(item)]


async def ingest_approved_capability_durable_asset(capability_id: str) -> CapabilityDurableAssetProjectionResponse:
    normalized_capability_id = capability_id.strip()
    from .capability_service import list_capabilities

    capability = next((item for item in list_capabilities() if item.id == normalized_capability_id), None)
    if capability is None:
        raise KeyError(normalized_capability_id)
    if not _capability_is_durable(capability):
        raise ValueError("Only ready and configured Capability facts can be projected into Graphiti.")

    request = _capability_durable_asset_request(capability)
    existing = _durable_asset_ingestion_record(request.asset_id)
    if existing is not None:
        graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
        return CapabilityDurableAssetProjectionResponse(
            capability_id=normalized_capability_id,
            status="skipped",
            detail="Approved Capability durable asset already exists in Graphiti ingestion audit.",
            skipped_asset={
                "asset_id": request.asset_id,
                "asset_type": request.asset_type,
                "reason": "already_ingested",
                "episode_id": str(graphiti_status.get("episode_id") or ""),
            },
            saved_paths={"graphiti_state": _relative(_state_path())},
        )

    ingested = await ingest_durable_asset_to_graphiti(request)
    return CapabilityDurableAssetProjectionResponse(
        capability_id=normalized_capability_id,
        status="ingested",
        detail="Approved Capability durable asset was projected to Graphiti.",
        ingested_asset=ingested,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


async def ingest_approved_capability_durable_assets(
    *,
    max_assets: int = 20,
) -> CapabilityDurableAssetBatchProjectionResponse:
    ingested: list[DurableAssetIngestResponse] = []
    skipped: list[dict[str, str]] = []
    capped_max_assets = max(1, min(max_assets, 50))
    for capability in _durable_capabilities():
        request = _capability_durable_asset_request(capability)
        existing = _durable_asset_ingestion_record(request.asset_id)
        if existing is not None:
            graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "already_ingested",
                    "episode_id": str(graphiti_status.get("episode_id") or ""),
                }
            )
            continue
        if len(ingested) >= capped_max_assets:
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "max_assets_limit",
                    "episode_id": "",
                }
            )
            continue
        ingested.append(await ingest_durable_asset_to_graphiti(request))

    status = "ingested" if ingested else "skipped" if skipped else "no_assets"
    return CapabilityDurableAssetBatchProjectionResponse(
        status=status,
        detail=(
            "Approved Capability durable assets were projected to Graphiti."
            if ingested
            else "No new approved Capability durable assets needed Graphiti ingestion."
        ),
        ingested_assets=ingested,
        skipped_assets=skipped,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


async def ingest_validated_ticket_durable_assets(ticket_id: str, *, max_assets: int = 20) -> TicketDurableAssetProjectionResponse:
    from .ticket_service import get_ticket

    normalized_ticket_id = ticket_id.strip()
    ticket = get_ticket(normalized_ticket_id)
    if ticket is None:
        raise KeyError(normalized_ticket_id)
    if not _ticket_is_validated(ticket):
        raise ValueError("Only validated Tickets can project report and evidence summaries into Graphiti.")

    ingested: list[DurableAssetIngestResponse] = []
    skipped: list[dict[str, str]] = []
    capped_max_assets = max(1, min(max_assets, 50))
    for request in _ticket_report_durable_asset_requests(ticket):
        existing = _durable_asset_ingestion_record(request.asset_id)
        if existing is not None:
            graphiti_status = existing.get("graphiti_status") if isinstance(existing.get("graphiti_status"), dict) else {}
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "already_ingested",
                    "episode_id": str(graphiti_status.get("episode_id") or ""),
                }
            )
            continue
        if len(ingested) >= capped_max_assets:
            skipped.append(
                {
                    "asset_id": request.asset_id,
                    "asset_type": request.asset_type,
                    "reason": "max_assets_limit",
                    "episode_id": "",
                }
            )
            continue
        ingested.append(await ingest_durable_asset_to_graphiti(request))

    status = "ingested" if ingested else "skipped" if skipped else "no_assets"
    return TicketDurableAssetProjectionResponse(
        ticket_id=normalized_ticket_id,
        status=status,
        detail=(
            "Validated Ticket report/evidence durable assets were projected to Graphiti."
            if ingested
            else "No new validated Ticket report/evidence durable assets needed Graphiti ingestion."
        ),
        ingested_assets=ingested,
        skipped_assets=skipped,
        saved_paths={"graphiti_state": _relative(_state_path())},
    )


def review_memory_candidate(candidate_id: str, request: MemoryCandidateReviewRequest) -> MemoryCandidate:
    status = request.status.strip().lower()
    if status not in MEMORY_REVIEW_STATUSES:
        raise ValueError(
            "Memory candidate review status must be one of: "
            + ", ".join(sorted(MEMORY_REVIEW_STATUSES))
        )
    candidate = next((item for item in _load_candidates() if item.id == candidate_id), None)
    if candidate is None:
        candidate = next((item for item in _load_approved() if item.id == candidate_id), None)
    if candidate is None:
        raise KeyError(candidate_id)

    timestamp = _now()
    review = {
        "status": status,
        "reason": request.reason.strip(),
        "actor_employee_id": request.actor_employee_id.strip() or "clara",
        "reviewed_at": timestamp,
    }
    superseded_by = request.superseded_by_candidate_id.strip()
    if superseded_by:
        review["superseded_by_candidate_id"] = superseded_by

    provenance = dict(candidate.provenance)
    reviews = provenance.get("reviews")
    if not isinstance(reviews, list):
        reviews = []
    reviews.append(review)
    provenance["reviews"] = reviews
    provenance["latest_review"] = review
    provenance["asset_status"] = status
    if status in {"stale", "superseded"}:
        provenance["not_applicable_at"] = timestamp
    if superseded_by:
        provenance["superseded_by_candidate_id"] = superseded_by

    candidate.status = status
    candidate.updated_at = timestamp
    candidate.provenance = provenance
    _update_candidate(candidate)
    _update_approved_if_present(candidate)
    return candidate


def _usage_summary(usage_history: list[dict[str, Any]]) -> dict[str, Any]:
    useful = len([item for item in usage_history if item.get("usefulness_status") == "useful"])
    not_useful = len([item for item in usage_history if item.get("usefulness_status") == "not_useful"])
    latest = usage_history[-1] if usage_history else {}
    return {
        "recall_count": len(usage_history),
        "useful_count": useful,
        "not_useful_count": not_useful,
        "last_recalled_at": latest.get("at", ""),
        "last_recalled_ticket_id": (latest.get("source_ticket_ids") or [""])[0] if isinstance(latest.get("source_ticket_ids"), list) else "",
        "last_recalled_run_id": latest.get("source_run_id", ""),
        "last_usefulness_status": latest.get("usefulness_status", "unreviewed"),
    }


def record_memory_recall_usage(
    *,
    memory_refs: list[dict[str, Any]],
    run_id: str,
    employee_id: str,
    ticket_keys: list[str],
    query: str,
    trace_path: str,
) -> list[dict[str, Any]]:
    timestamp = _now()
    usage_refs: list[dict[str, Any]] = []
    seen_memory_ids: set[str] = set()
    for ref in memory_refs:
        provenance = ref.get("provenance") if isinstance(ref.get("provenance"), dict) else {}
        memory_id = _first_string(ref.get("memory_id"), provenance.get("asset_id"))
        if not memory_id or memory_id in seen_memory_ids:
            continue
        seen_memory_ids.add(memory_id)
        candidate = _find_local_memory_candidate(memory_id)
        if candidate is None or candidate.status not in RECALLABLE_MEMORY_STATUSES:
            continue

        usage_id = f"usage-{run_id}-{memory_id}"
        candidate_provenance = dict(candidate.provenance)
        usage_history = candidate_provenance.get("usage_history")
        if not isinstance(usage_history, list):
            usage_history = []
        existing = next((item for item in usage_history if isinstance(item, dict) and item.get("usage_id") == usage_id), None)
        if isinstance(existing, dict):
            usage = existing
        else:
            usage = {
                "usage_id": usage_id,
                "at": timestamp,
                "source_kind": "chat_run",
                "source_run_id": run_id,
                "source_trace_path": trace_path,
                "source_employee_id": employee_id,
                "source_ticket_ids": list(ticket_keys),
                "query": _compact_text(query, 240),
                "graphiti_recalled": bool(ref.get("graphiti_recalled")),
                "graphiti_episode_id": ref.get("graphiti_episode_id") or "",
                "graphiti_result_id": ref.get("graphiti_result_id") or "",
                "usefulness_status": "unreviewed",
            }
            usage_history.append(usage)
        usage_history = [item for item in usage_history if isinstance(item, dict)][-50:]
        candidate_provenance["usage_history"] = usage_history
        candidate_provenance["usage_summary"] = _usage_summary(usage_history)
        candidate.provenance = candidate_provenance
        candidate.updated_at = timestamp
        _replace_local_memory_candidate(candidate)

        usage_refs.append(
            {
                "usage_id": usage["usage_id"],
                "memory_id": memory_id,
                "asset_id": memory_id,
                "source_run_id": run_id,
                "source_trace_path": trace_path,
                "source_employee_id": employee_id,
                "source_ticket_ids": list(ticket_keys),
                "graphiti_recalled": bool(usage.get("graphiti_recalled")),
                "graphiti_episode_id": usage.get("graphiti_episode_id") or "",
                "usefulness_status": usage.get("usefulness_status") or "unreviewed",
            }
        )
    return usage_refs


def review_memory_recall_usage(
    candidate_id: str,
    usage_id: str,
    request: MemoryRecallUsefulnessReviewRequest,
) -> MemoryCandidate:
    usefulness_status = request.usefulness_status.strip().lower()
    if usefulness_status not in MEMORY_RECALL_USEFULNESS_STATUSES - {"unreviewed"}:
        raise ValueError(
            "Memory recall usefulness status must be one of: "
            + ", ".join(sorted(MEMORY_RECALL_USEFULNESS_STATUSES - {"unreviewed"}))
        )
    candidate = _find_local_memory_candidate(candidate_id)
    if candidate is None:
        raise KeyError(candidate_id)

    provenance = dict(candidate.provenance)
    usage_history = provenance.get("usage_history")
    if not isinstance(usage_history, list):
        usage_history = []
    matched = False
    timestamp = _now()
    for item in usage_history:
        if not isinstance(item, dict) or item.get("usage_id") != usage_id:
            continue
        item["usefulness_status"] = usefulness_status
        item["reviewed_at"] = timestamp
        item["reviewer_employee_id"] = request.reviewer_employee_id.strip() or "clara"
        item["usefulness_reason"] = request.reason.strip()
        matched = True
        break
    if not matched:
        raise KeyError(usage_id)

    provenance["usage_history"] = usage_history
    provenance["usage_summary"] = _usage_summary([item for item in usage_history if isinstance(item, dict)])
    candidate.provenance = provenance
    candidate.updated_at = timestamp
    _replace_local_memory_candidate(candidate)
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
                graphiti_episode_id=candidate.graphiti_episode_id,
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
    graphiti = _new_graphiti_client(graphiti_cls, config)
    try:
        search = getattr(graphiti, "search")
        parameters = inspect.signature(search).parameters
        kwargs: dict[str, Any] = {}
        if _accepts_kwarg(parameters, "group_ids"):
            kwargs["group_ids"] = [config["group_id"]]
        if _accepts_kwarg(parameters, "num_results"):
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
        episode_id = getattr(item, "episode_uuid", None) or getattr(item, "source_node_uuid", None) or item_id
        provenance = _graphiti_result_provenance(item)
        matched_memory: MemoryCandidate | None = None
        if not _first_string(provenance.get("asset_id"), provenance.get("memory_id")):
            matched_memory = _graphiti_result_local_memory_match(str(content), str(episode_id or ""))
            if matched_memory is not None:
                provenance = {
                    **_graphiti_asset_provenance(matched_memory),
                    "graphiti_result_id": str(item_id),
                    "graphiti_result_episode_id": str(episode_id) if episode_id else "",
                    "graphiti_raw_type": provenance.get("raw_type", item.__class__.__name__),
                }
            else:
                durable_provenance = _graphiti_result_durable_asset_match(str(content), str(episode_id or ""))
                if durable_provenance is not None:
                    provenance = {
                        **durable_provenance,
                        "graphiti_result_id": str(item_id),
                        "graphiti_result_episode_id": str(episode_id) if episode_id else "",
                        "graphiti_raw_type": provenance.get("raw_type", item.__class__.__name__),
                    }
        if not _is_local_memory_asset_recallable(provenance):
            continue
        scope = provenance.get("scope") if isinstance(provenance.get("scope"), dict) else {}
        provenance_source_kind = _first_string(provenance.get("source_kind"), provenance.get("asset_type"))
        provenance_scope_kind = _first_string(scope.get("kind") if isinstance(scope, dict) else None)
        provenance_scope_ref = _first_string(
            scope.get("ref") if isinstance(scope, dict) else None,
            provenance.get("source_ticket_id"),
            backend.group_id,
        )
        provenance_employee_ids: list[str] = []
        source_employee_id = _first_string(provenance.get("source_employee_id"))
        if source_employee_id:
            provenance_employee_ids.append(source_employee_id)
        score = getattr(item, "score", None)
        results.append(
            MemorySearchResult(
                id=str(item_id),
                content=_compact_text(str(content), 1000),
                source="graphiti",
                score=float(score) if isinstance(score, int | float) else None,
                source_kind=matched_memory.source_kind if matched_memory is not None else provenance_source_kind,
                source_ref=matched_memory.source_ref if matched_memory is not None else _first_string(provenance.get("source_ref")),
                scope_kind=matched_memory.scope_kind if matched_memory is not None else provenance_scope_kind,
                scope_ref=matched_memory.scope_ref if matched_memory is not None else provenance_scope_ref,
                memory_type=matched_memory.memory_type if matched_memory is not None else _first_string(provenance.get("asset_type")),
                employee_ids=matched_memory.employee_ids if matched_memory is not None else provenance_employee_ids,
                tags=matched_memory.tags if matched_memory is not None else [],
                provenance=provenance,
                graphiti_episode_id=str(episode_id) if episode_id else None,
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


def recall_memory_snippets(
    *,
    employee_id: str,
    query: str = "",
    ticket_keys: list[str] | None = None,
    limit: int = 5,
) -> list[str]:
    snippets: list[str] = []
    for result in recall_memory_records(
        employee_id=employee_id,
        query=query,
        ticket_keys=ticket_keys,
        limit=limit,
    ):
        snippets.append(
            f"[memory:{result.id}] {result.content} "
            f"(scope={result.scope_kind}:{result.scope_ref}; source={result.source_kind}:{result.source_ref})"
        )
        if len(snippets) >= limit:
            break
    return snippets[:limit]


def recall_memory_records(
    *,
    employee_id: str,
    query: str = "",
    ticket_keys: list[str] | None = None,
    limit: int = 5,
) -> list[MemorySearchResult]:
    search_terms = " ".join(ticket_keys or []).strip() or query
    results = _file_memory_results(
        query=search_terms,
        employee_id=employee_id,
        ticket_key=(ticket_keys or [None])[0],
        limit=limit,
    )
    return results[:limit]


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
    provider_refs: list[dict[str, Any]] | None = None,
    graphiti_episode_refs: list[dict[str, Any]] | None = None,
    source_report_id: str = "",
    evidence_id: str = "",
    recalled_memory_refs: list[dict[str, Any]] | None = None,
    action_plan: dict[str, Any] | None = None,
) -> MemoryCandidate | None:
    if any(
        candidate.source_ref == run_id
        or candidate.source_ref == trace_path
        or candidate.provenance.get("source_run_id") == run_id
        for candidate in _load_candidates()
    ):
        return None

    text = f"{user_message}\n{assistant_reply}"
    detected_ticket = sorted(set(ticket_keys or _JIRA_KEY_RE.findall(text)))
    if not detected_ticket and not _MEMORY_SIGNAL_RE.search(text):
        return None

    scope_kind = "ticket" if detected_ticket else "employee"
    scope_ref = detected_ticket[0] if detected_ticket else employee_id
    source_kind = "ticket_run" if detected_ticket else "chat"
    source_ref = trace_path if detected_ticket else run_id
    tags = {"auto-chat", *detected_ticket}
    if detected_ticket:
        tags.add("ticket-aware")
    if action_plan and action_plan.get("action"):
        tags.add(str(action_plan["action"]))
    content = _compact_text(
        f"In thread {thread_id}, user asked {employee_display_name}: {user_message} "
        f"{employee_display_name} replied: {assistant_reply}",
        900,
    )
    return create_memory_candidate(
        MemoryCandidateCreateRequest(
            content=content,
            source_kind=source_kind,
            source_ref=source_ref,
            scope_kind=scope_kind,
            scope_ref=scope_ref,
            memory_type="episode",
            confidence=0.62 if detected_ticket else 0.42,
            employee_ids=[employee_id],
            tags=sorted(tags),
            provenance={
                "source_ticket_id": scope_ref if scope_kind == "ticket" else "",
                "source_employee_id": employee_id,
                "source_run_id": run_id,
                "source_report_id": source_report_id,
                "evidence_id": evidence_id,
                "source_trace_path": trace_path,
                "thread_id": thread_id,
                "run_id": run_id,
                "employee_id": employee_id,
                "trace": trace_path,
                "ticket_keys": detected_ticket,
                "provider_refs": provider_refs or [],
                "graphiti_episode_refs": graphiti_episode_refs or [],
                "recalled_memory_refs": recalled_memory_refs or [],
                "action_plan": action_plan or {},
                "why_should_be_remembered": (
                    "Ticket-bound chat turn with reusable execution, validation, blocker, or summary context."
                    if detected_ticket
                    else "Chat turn explicitly asked to remember reusable context."
                ),
                "future_recall_query_hints": sorted({*detected_ticket, *_compact_text(user_message, 160).split()[:8]}),
            },
        )
    )
