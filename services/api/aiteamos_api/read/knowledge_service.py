"""Knowledge service for docs, memories, decisions, and review items."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .memory_service import MemoryCandidate, list_approved_memories, list_memory_candidates

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


class KnowledgeStatusResponse(BaseModel):
    docs_count: int
    memories_count: int
    decisions_count: int
    review_queue_count: int
    saved_paths: dict[str, str]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    return Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", Path.cwd())).resolve()


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

    return DecisionRecord(
        id=decision_id,
        title=title,
        status=status,
        context=section("Context"),
        decision=section("Decision") or _excerpt(text),
        consequences=section("Consequences"),
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


def knowledge_status() -> KnowledgeStatusResponse:
    return KnowledgeStatusResponse(
        docs_count=len(list_docs()),
        memories_count=len(list_approved_memories()),
        decisions_count=len(list_decisions()),
        review_queue_count=len(review_queue_items()),
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
