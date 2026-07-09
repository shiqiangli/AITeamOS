"""Knowledge service for docs, memories, decisions, and review items."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

from .capability_service import list_capabilities
from .memory_service import MemoryCandidate, list_approved_memories, list_memory_candidates
from .skill_usage_service import skill_usage_summary
from .ticket_service import ticket_asset_records
from .validation_skill_catalog import VALIDATION_SKILL_DEFINITIONS

_MAX_DOC_BYTES = 256_000
_DOC_GLOBS = (
    "*.md",
    "docs/**/*.md",
    ".aiteamos/docs/**/*.md",
    ".aiteamos/knowledge/docs/**/*.md",
)


class KnowledgeDocSummary(BaseModel):
    id: str
    title: str
    source: str = "local"
    path: str
    excerpt: str = ""
    content: str = ""
    updated_at: str = ""
    tags: list[str] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    id: str
    title: str
    status: str = "accepted"
    context: str = ""
    decision: str
    consequences: str = ""
    linked_tickets: list[str] = Field(default_factory=list)
    linked_memories: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    saved_path: str = ""


class DecisionCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    status: str = "accepted"
    context: str = ""
    decision: str = Field(min_length=1)
    consequences: str = ""
    linked_tickets: list[str] = Field(default_factory=list)
    linked_memories: list[str] = Field(default_factory=list)


class KnowledgeSearchResult(BaseModel):
    id: str
    title: str
    content: str
    source_type: str
    source_ref: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeSearchResult]


class ReviewQueueItem(BaseModel):
    id: str
    kind: str
    title: str
    content: str
    status: str
    source_ref: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetRecord(BaseModel):
    id: str
    kind: str
    title: str
    status: str = "active"
    source_ticket: str = ""
    source_employee: str = ""
    assigned_employees: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeStatusResponse(BaseModel):
    docs_count: int
    memories_count: int
    decisions_count: int
    review_queue_count: int
    asset_count: int = 0
    saved_paths: dict[str, str]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _knowledge_dir() -> Path:
    path = _workspace_dir() / "knowledge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _decisions_dir() -> Path:
    path = _knowledge_dir() / "decisions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _employees_dir() -> Path:
    return _workspace_dir() / "employees"


def _skills_dir() -> Path:
    return _workspace_dir() / "skills"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip().lower()).strip("-")
    return slug[:96] or f"item-{uuid4().hex[:8]}"


def _safe_doc_path(path: Path) -> bool:
    relative = _relative(path)
    blocked_parts = {".git", "node_modules", ".venv", "dist", "__pycache__", ".pytest_cache"}
    if any(part in blocked_parts for part in path.parts):
        return False
    if relative.startswith(".aiteamos/memory/"):
        return False
    if relative.startswith(".aiteamos/threads/") or relative.startswith(".aiteamos/conversations/"):
        return False
    return path.is_file() and path.suffix.lower() == ".md"


def _read_text(path: Path) -> str:
    if path.stat().st_size > _MAX_DOC_BYTES:
        return path.read_text(encoding="utf-8", errors="ignore")[:_MAX_DOC_BYTES]
    return path.read_text(encoding="utf-8", errors="ignore")


def _first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
        return stripped[:96]
    return fallback


def _excerpt(text: str, limit: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:limit] + ("..." if len(cleaned) > limit else "")


def _asset_metadata(domain: str, asset_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"asset_domain": domain, "asset_type": asset_type, **payload}


def _doc_id(path: Path) -> str:
    return _slugify(_relative(path).removesuffix(".md"))


def list_docs() -> list[KnowledgeDocSummary]:
    paths: dict[str, Path] = {}
    root = _workspace_root()
    for pattern in _DOC_GLOBS:
        for path in root.glob(pattern):
            if _safe_doc_path(path):
                paths[_relative(path)] = path

    docs: list[KnowledgeDocSummary] = []
    for relative, path in sorted(paths.items()):
        try:
            text = _read_text(path)
            updated_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        except OSError:
            continue
        tags = ["decision"] if relative.startswith(".aiteamos/knowledge/decisions/") else []
        docs.append(
            KnowledgeDocSummary(
                id=_doc_id(path),
                title=_first_heading(text, path.stem),
                path=relative,
                excerpt=_excerpt(text),
                content=text,
                updated_at=updated_at,
                tags=tags,
            )
        )
    return docs


def _score_text(query_terms: list[str], text: str) -> float:
    if not query_terms:
        return 1.0
    normalized = text.lower()
    score = 0.0
    for term in query_terms:
        if term in normalized:
            score += 1.0
    return score / max(len(query_terms), 1)


def _terms(query: str) -> list[str]:
    return [part for part in re.split(r"\s+", query.lower().strip()) if part]


def _find_best_snippet(text: str, terms: list[str], limit: int = 420) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not terms:
        return cleaned[:limit]
    lower = cleaned.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    if not positions:
        return cleaned[:limit]
    start = max(0, min(positions) - 120)
    return cleaned[start : start + limit]


def _doc_results(query: str, limit: int) -> list[KnowledgeSearchResult]:
    terms = _terms(query)
    results: list[KnowledgeSearchResult] = []
    for doc in list_docs():
        path = _workspace_root() / doc.path
        try:
            text = _read_text(path)
        except OSError:
            continue
        haystack = f"{doc.title}\n{doc.path}\n{text}"
        score = _score_text(terms, haystack)
        if score <= 0 and terms:
            continue
        results.append(
            KnowledgeSearchResult(
                id=doc.id,
                title=doc.title,
                content=_find_best_snippet(text, terms),
                source_type="doc",
                source_ref=doc.path,
                score=score,
                metadata={"path": doc.path, "tags": doc.tags},
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


def _memory_results(query: str, limit: int) -> list[KnowledgeSearchResult]:
    terms = _terms(query)
    results: list[KnowledgeSearchResult] = []
    for memory in list_approved_memories():
        haystack = " ".join(
            [
                memory.content,
                memory.source_kind,
                memory.source_ref,
                memory.scope_kind,
                memory.scope_ref,
                " ".join(memory.tags),
            ]
        )
        score = _score_text(terms, haystack)
        if score <= 0 and terms:
            continue
        results.append(
            KnowledgeSearchResult(
                id=memory.id,
                title=f"Memory {memory.scope_kind}:{memory.scope_ref}",
                content=memory.content,
                source_type="memory",
                source_ref=memory.source_ref,
                score=score,
                metadata=memory.model_dump(mode="json"),
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


def _decision_path(decision_id: str) -> Path:
    return _decisions_dir() / f"{decision_id}.md"


def _decision_to_markdown(decision: DecisionRecord) -> str:
    return "\n".join(
        [
            f"# {decision.title}",
            "",
            f"Status: {decision.status}",
            f"ID: {decision.id}",
            f"Created: {decision.created_at}",
            f"Updated: {decision.updated_at}",
            "",
            "## Context",
            decision.context or "-",
            "",
            "## Decision",
            decision.decision,
            "",
            "## Consequences",
            decision.consequences or "-",
            "",
            "## Links",
            f"- Tickets: {', '.join(decision.linked_tickets) or '-'}",
            f"- Memories: {', '.join(decision.linked_memories) or '-'}",
            "",
        ]
    )


def _markdown_to_decision(path: Path) -> DecisionRecord | None:
    try:
        text = _read_text(path)
        stat = path.stat()
    except OSError:
        return None

    decision_id = path.stem
    title = _first_heading(text, decision_id)
    status_match = re.search(r"^Status:\s*(.+)$", text, re.MULTILINE)
    status = status_match.group(1).strip() if status_match else "accepted"

    def section(name: str) -> str:
        pattern = rf"^## {re.escape(name)}\s*$([\s\S]*?)(?=^## |\Z)"
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def links(name: str) -> list[str]:
        match = re.search(rf"^- {re.escape(name)}:\s*(.+)$", text, re.MULTILINE)
        if not match:
            return []
        raw = match.group(1).strip()
        if not raw or raw == "-":
            return []
        return sorted({item.strip() for item in raw.split(",") if item.strip() and item.strip() != "-"})

    return DecisionRecord(
        id=decision_id,
        title=title,
        status=status,
        context=section("Context"),
        decision=section("Decision") or _excerpt(text),
        consequences=section("Consequences"),
        linked_tickets=links("Tickets"),
        linked_memories=links("Memories"),
        created_at=datetime.fromtimestamp(stat.st_ctime, UTC).isoformat(),
        updated_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        saved_path=_relative(path),
    )


def list_decisions() -> list[DecisionRecord]:
    decisions = [
        decision
        for decision in (_markdown_to_decision(path) for path in sorted(_decisions_dir().glob("*.md")))
        if decision is not None
    ]
    return sorted(decisions, key=lambda item: item.updated_at, reverse=True)


def create_decision(request: DecisionCreateRequest) -> DecisionRecord:
    timestamp = _now()
    decision_id = f"dec-{_slugify(request.title)[:64]}-{uuid4().hex[:6]}"
    path = _decision_path(decision_id)
    decision = DecisionRecord(
        id=decision_id,
        title=request.title.strip(),
        status=request.status.strip() or "accepted",
        context=request.context.strip(),
        decision=request.decision.strip(),
        consequences=request.consequences.strip(),
        linked_tickets=sorted({item.strip() for item in request.linked_tickets if item.strip()}),
        linked_memories=sorted({item.strip() for item in request.linked_memories if item.strip()}),
        created_at=timestamp,
        updated_at=timestamp,
        saved_path=_relative(path),
    )
    path.write_text(_decision_to_markdown(decision), encoding="utf-8")
    return decision


def _decision_results(query: str, limit: int) -> list[KnowledgeSearchResult]:
    terms = _terms(query)
    results: list[KnowledgeSearchResult] = []
    for decision in list_decisions():
        haystack = "\n".join([decision.title, decision.context, decision.decision, decision.consequences])
        score = _score_text(terms, haystack)
        if score <= 0 and terms:
            continue
        results.append(
            KnowledgeSearchResult(
                id=decision.id,
                title=decision.title,
                content=decision.decision,
                source_type="decision",
                source_ref=decision.saved_path,
                score=score,
                metadata=decision.model_dump(mode="json"),
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


def search_knowledge_sync(query: str, *, limit: int = 10) -> KnowledgeSearchResponse:
    capped_limit = max(1, min(limit, 50))
    results = [
        *_doc_results(query, capped_limit),
        *_decision_results(query, capped_limit),
        *_memory_results(query, capped_limit),
    ]
    results = sorted(results, key=lambda item: item.score, reverse=True)[:capped_limit]
    return KnowledgeSearchResponse(query=query, results=results)


def review_queue_items() -> list[ReviewQueueItem]:
    items: list[ReviewQueueItem] = []
    for candidate in list_memory_candidates(status="proposed"):
        items.append(
            ReviewQueueItem(
                id=candidate.id,
                kind="memory",
                title=f"Memory candidate from {candidate.source_kind}",
                content=candidate.content,
                status=candidate.status,
                source_ref=candidate.source_ref,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
                metadata=candidate.model_dump(mode="json"),
            )
        )
    return sorted(items, key=lambda item: item.updated_at, reverse=True)


def _skill_title_and_description(skill_id: str, text: str) -> tuple[str, str]:
    title = skill_id.replace("-", " ").title()
    description = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip() or title
            continue
        if stripped.startswith(">") and not description:
            description = stripped.lstrip(">").strip()
            continue
        if not description and not stripped.startswith("---"):
            description = stripped[:240]
        if title and description:
            break
    return title, description


def _employee_skill_assignments() -> dict[str, list[str]]:
    assignments: dict[str, list[str]] = {}
    for path in sorted(_employees_dir().glob("*.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError:
            continue
        if not isinstance(payload, dict):
            continue
        employee_id = str(payload.get("id") or path.stem)
        for skill in payload.get("skills", []) if isinstance(payload.get("skills"), list) else []:
            skill_id = str(skill).strip()
            if skill_id:
                assignments.setdefault(skill_id, []).append(employee_id)
    return {skill_id: sorted(set(employee_ids)) for skill_id, employee_ids in assignments.items()}


def _skill_asset_items() -> list[AssetRecord]:
    assignments = _employee_skill_assignments()
    items: list[AssetRecord] = []
    local_skill_ids: set[str] = set()
    for path in sorted(_skills_dir().glob("*/SKILL.md")):
        skill_id = path.parent.name
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            updated_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        except OSError:
            continue
        local_skill_ids.add(skill_id)
        title, description = _skill_title_and_description(skill_id, text)
        resources = [
            str(resource.relative_to(path.parent))
            for resource in sorted(path.parent.rglob("*"))
            if resource.is_file() and resource.name != "SKILL.md"
        ]
        metadata = {
            "id": skill_id,
            "description": description,
            "content": text,
            "resources": resources,
            "saved_path": _relative(path),
            **skill_usage_summary(_workspace_dir(), skill_id),
        }
        items.append(
            AssetRecord(
                id=skill_id,
                kind="skill",
                title=title,
                status="approved",
                assigned_employees=assignments.get(skill_id, []),
                scopes=["capabilities", "skills"],
                created_at=updated_at,
                updated_at=updated_at,
                metadata=_asset_metadata("capabilities", "skills", metadata),
            )
        )
    seeded_at = _now()
    for skill in VALIDATION_SKILL_DEFINITIONS:
        if skill.id in local_skill_ids:
            continue
        metadata = {
            "id": skill.id,
            "description": skill.description,
            "content": skill.content,
            "resources": [],
            "saved_path": skill.source_ref,
            "source": "builtin",
            "source_ref": skill.source_ref,
            "owner_roles": list(skill.owner_roles),
            "phase": "phase5_validation",
            **skill_usage_summary(_workspace_dir(), skill.id),
        }
        items.append(
            AssetRecord(
                id=skill.id,
                kind="skill",
                title=skill.title,
                status="approved",
                assigned_employees=assignments.get(skill.id, []),
                scopes=["capabilities", "skills", "validation", *skill.owner_roles],
                created_at=seeded_at,
                updated_at=seeded_at,
                metadata=_asset_metadata("capabilities", "skills", metadata),
            )
        )
    return items


def _capability_asset_type(kind: str, source_kind: str) -> str:
    if kind != "tool":
        return "capabilities"
    mapping = {
        "kernel_command": "kernel-commands",
        "mcp_server": "mcp-tools",
        "native_api": "native-api-tools",
        "cli": "cli-tools",
        "ci": "ci-tools",
        "ticket_backend": "ticket-backend-tools",
        "ai_engine_bridge": "ai-engine-tools",
    }
    return mapping.get(source_kind or "kernel_command", "kernel-commands")


def _capability_asset_items() -> list[AssetRecord]:
    timestamp = _now()
    items: list[AssetRecord] = []
    for capability in list_capabilities():
        asset_type = _capability_asset_type(capability.kind, capability.source_kind)
        metadata = capability.model_dump(mode="json")
        items.append(
            AssetRecord(
                id=capability.id,
                kind="tool",
                title=capability.name,
                status=capability.status,
                scopes=["capabilities", asset_type, capability.domain],
                created_at=timestamp,
                updated_at=timestamp,
                metadata=_asset_metadata("capabilities", asset_type, metadata),
            )
        )
    return items


def all_asset_items() -> list[AssetRecord]:
    items: list[AssetRecord] = []
    for doc in list_docs():
        items.append(
            AssetRecord(
                id=doc.id,
                kind="doc",
                title=doc.title,
                status="approved",
                scopes=doc.tags,
                created_at=doc.updated_at,
                updated_at=doc.updated_at,
                metadata=_asset_metadata("knowledge", "docs", doc.model_dump(mode="json")),
            )
        )
    for decision in list_decisions():
        items.append(
            AssetRecord(
                id=decision.id,
                kind="decision",
                title=decision.title,
                status=decision.status,
                source_ticket=decision.linked_tickets[0] if decision.linked_tickets else "",
                scopes=decision.linked_tickets,
                created_at=decision.created_at,
                updated_at=decision.updated_at,
                metadata=_asset_metadata("knowledge", "decisions", decision.model_dump(mode="json")),
            )
        )
    for memory in [*list_memory_candidates(), *list_approved_memories()]:
        items.append(
            AssetRecord(
                id=memory.id,
                kind="memory",
                title=f"Memory {memory.scope_kind}:{memory.scope_ref}",
                status=memory.status,
                source_ticket=memory.scope_ref if memory.scope_kind == "ticket" else "",
                source_employee=memory.employee_ids[0] if memory.employee_ids else "",
                assigned_employees=memory.employee_ids,
                scopes=[f"{memory.scope_kind}:{memory.scope_ref}", *memory.tags],
                created_at=memory.created_at,
                updated_at=memory.updated_at,
                metadata=_asset_metadata("knowledge", "memories", memory.model_dump(mode="json")),
            )
        )
    try:
        ticket_assets = ticket_asset_records()
    except ValueError:
        ticket_assets = []
    for ticket_asset in ticket_assets:
        items.append(
            AssetRecord(
                id=ticket_asset.id,
                kind=ticket_asset.kind,
                title=ticket_asset.title,
                status=ticket_asset.status,
                source_ticket=ticket_asset.source_ticket_id,
                source_employee=ticket_asset.source_employee_id,
                assigned_employees=ticket_asset.assigned_employees,
                scopes=ticket_asset.scopes,
                created_at=ticket_asset.created_at,
                updated_at=ticket_asset.updated_at,
                metadata=_asset_metadata("work", ticket_asset.kind, ticket_asset.metadata),
            )
        )
    items.extend(_skill_asset_items())
    items.extend(_capability_asset_items())
    return sorted(items, key=lambda item: item.updated_at or item.created_at, reverse=True)


def _asset_matches_query(item: AssetRecord, query: str) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return True
    haystack = " ".join(
        [
            item.id,
            item.kind,
            item.title,
            item.status,
            item.source_ticket,
            item.source_employee,
            " ".join(item.assigned_employees),
            " ".join(item.scopes),
            json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
        ]
    ).lower()
    return all(term in haystack for term in re.split(r"\s+", normalized) if term)


def _asset_domain(item: AssetRecord) -> str:
    value = item.metadata.get("asset_domain")
    return str(value) if value else ""


def _asset_type(item: AssetRecord) -> str:
    value = item.metadata.get("asset_type")
    return str(value) if value else ""


def _is_review_asset(item: AssetRecord) -> bool:
    return item.status in {"proposed", "candidate", "needs_review", "pending"} or _asset_domain(item) == "review"


def asset_items(*, domain: str = "", asset_type: str = "", query: str = "") -> list[AssetRecord]:
    items = all_asset_items()
    if domain:
        if domain == "review":
            items = [item for item in items if _is_review_asset(item)]
        else:
            items = [item for item in items if _asset_domain(item) == domain]
    if asset_type:
        items = [item for item in items if _asset_type(item) == asset_type]
    if query.strip():
        items = [item for item in items if _asset_matches_query(item, query)]
    return items


def knowledge_status() -> KnowledgeStatusResponse:
    return KnowledgeStatusResponse(
        docs_count=len(list_docs()),
        memories_count=len(list_approved_memories()),
        decisions_count=len(list_decisions()),
        review_queue_count=len(review_queue_items()),
        asset_count=len(all_asset_items()),
        saved_paths={
            "docs": ".aiteamos/docs",
            "decisions": _relative(_decisions_dir()),
            "memory_candidates": ".aiteamos/memory/candidates.json",
            "memory_approved": ".aiteamos/memory/approved.json",
        },
    )


def knowledge_snippets(query: str, *, limit: int = 5) -> list[str]:
    response = search_knowledge_sync(query, limit=limit)
    return [
        f"[{item.source_type}:{item.id}] {item.title} - {item.content} (source={item.source_ref})"
        for item in response.results[:limit]
    ]
