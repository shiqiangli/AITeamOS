from __future__ import annotations

from pathlib import Path
from typing import Any
import fnmatch
import os
import re


DOC_MAX_FILES = 8
DOC_MAX_CHARS = 2_400
REPO_MAP_MAX_FILES = 180
CODE_MAX_FILES = 10
CODE_MAX_CHARS = 2_000
MEMORY_MAX_ITEMS = 12
RECENT_RUN_MAX = 6
JOURNAL_EXCERPT_CHARS = 900
SOURCE_SNIPPET_CHARS = 320

SKIP_PARTS = {
    ".aiteamos",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
}

TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".rs",
    ".sql",
    ".toml",
    ".tsx",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}

STOPWORDS = {
    "acceptance",
    "assigned",
    "assignment",
    "context",
    "create",
    "dashboard",
    "detail",
    "employee",
    "execution",
    "implementation",
    "managed",
    "member",
    "model",
    "project",
    "review",
    "status",
    "system",
    "task",
    "the",
    "with",
    "work",
    "workspace",
}


def _source_decisions(sources: dict[str, list[Any]], exclusions: list[str]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    included_specs = [
        ("projectDocs", "projectDoc", "projectDocs"),
        ("repositoryMap", "repositoryMap", "repositoryMapFiles"),
        ("relevantCode", "code", "relevantCodeFiles"),
        ("selectedMemory", "memory", "memoryItems"),
        ("memoryBindings", "memoryBinding", "memoryBindings"),
        ("memoryGrants", "memoryGrant", "memoryGrants"),
        ("handoffs", "handoff", "handoffs"),
        ("permissionPolicies", "permissionPolicy", "permissionPolicies"),
        ("executionProfile", "executionProfile", "executionProfile"),
        ("recentRuns", "recentRun", "recentRuns"),
    ]
    for bucket, source_type, budget_bucket in included_specs:
        for index, source in enumerate(sources.get(bucket, []), start=1):
            if not isinstance(source, dict):
                continue
            decisions.append(_included_source_decision(source_type, source, budget_bucket, index))
    for index, reason in enumerate(exclusions, start=1):
        category = _exclusion_category(reason)
        decisions.append(
            {
                "sourceType": category,
                "sourceRef": _excluded_source_ref(reason),
                "outcome": "excluded",
                "reason": reason,
                "category": category,
                "dedupeKey": _dedupe_key("excluded", category, reason),
                "budgetBucket": _exclusion_budget_bucket(category),
                "rank": index,
            }
        )
    return decisions


def _included_source_decision(source_type: str, source: dict[str, Any], budget_bucket: str, index: int) -> dict[str, Any]:
    source_ref = _included_source_ref(source_type, source, index)
    return _without_empty(
        {
            "sourceType": source_type,
            "sourceRef": source_ref,
            "outcome": "included",
            "reason": str(source.get("reason") or source_type),
            "category": source_type,
            "repo": source.get("repo"),
            "path": source.get("path"),
            "dedupeKey": source.get("dedupeKey") or _dedupe_key(source_type, source_ref),
            "budgetBucket": source.get("budgetBucket") or budget_bucket,
            "rank": source.get("rank"),
            "score": source.get("score"),
            "aclRead": source.get("aclRead") or [],
            "lifecycle": source.get("lifecycle"),
            "freshness": source.get("freshness"),
            "confidence": source.get("confidence"),
            "sensitivity": source.get("sensitivity"),
            "charsIncluded": source.get("charsIncluded"),
            "charsLimit": source.get("charsLimit"),
            "truncated": source.get("truncated"),
            "snippetPreview": source.get("snippetPreview"),
            "lineStart": source.get("lineStart"),
            "lineEnd": source.get("lineEnd"),
        }
    )


def _included_source_ref(source_type: str, source: dict[str, Any], index: int) -> str:
    if source_type == "memory":
        return str(source.get("memory") or f"memory:{index}")
    if source_type in {"memoryBinding", "memoryGrant", "permissionPolicy", "handoff"}:
        return str(source.get("id") or f"{source_type}:{index}")
    if source_type == "recentRun":
        return str(source.get("run") or f"recentRun:{index}")
    if source_type == "executionProfile":
        return str(source.get("id") or source.get("kind") or f"executionProfile:{index}")
    repo = source.get("repo")
    path = source.get("path")
    if repo and path:
        return f"{repo}:{path}"
    if repo:
        return str(repo)
    if path:
        return str(path)
    return f"{source_type}:{index}"


def _exclusion_category(reason: str) -> str:
    lowered = reason.lower()
    if "memory" in lowered:
        return "memory"
    if "code" in lowered:
        return "code"
    if "doc" in lowered:
        return "projectDoc"
    if "repository" in lowered:
        return "repositoryMap"
    if "budget" in lowered:
        return "budget"
    return "context"


def _exclusion_budget_bucket(category: str) -> str:
    return {
        "memory": "memoryItems",
        "code": "relevantCodeFiles",
        "projectDoc": "projectDocs",
        "repositoryMap": "repositoryMapFiles",
        "budget": "modelBudget",
    }.get(category, "context")


def _excluded_source_ref(reason: str) -> str:
    tokens = reason.strip().split()
    return tokens[-1] if tokens else "excluded"


def _without_empty(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if value is not None and value != []}


def _source_counts(sources: dict[str, list[Any]]) -> dict[str, int]:
    return {name: len(records) for name, records in sorted(sources.items())}


def _manifest_summary(manifest: dict[str, Any]) -> str:
    lines = [
        f"- Source priority: {', '.join(manifest['sourcePriority'])}",
        f"- Project docs: {len(manifest['sources']['projectDocs'])}",
        f"- Repository maps: {len(manifest['sources']['repositoryMap'])}",
        f"- Relevant code excerpts: {len(manifest['sources']['relevantCode'])}",
        f"- Selected memory items: {len(manifest['sources']['selectedMemory'])}",
        f"- Source decisions: {len(manifest.get('sourceDecisions', []))}",
        f"- Memory bindings: {len(manifest['memoryBindings'])}",
        f"- Memory grants: {len(manifest['memoryGrants'])}",
        f"- Recent handoffs: {len(manifest['handoffs'])}",
        f"- Recent runs: {len(manifest['sources']['recentRuns'])}",
        f"- Applicable budget policy: {manifest['budget'].get('applicablePolicy') or 'none'}",
    ]
    if manifest["exclusions"]:
        lines.append("- Exclusions:")
        lines.extend(f"  - {item}" for item in manifest["exclusions"])
    return "\n".join(lines)


def _collect_permission_context(index: Any, member: Any, assignment: Any | None, execution_profile: Any | None) -> tuple[str, list[dict[str, Any]]]:
    policy_ids = list(member.spec.permissionPolicies)
    if assignment:
        policy_ids.extend(policy for policy in assignment.spec.permissionPolicies if policy not in policy_ids)
    if execution_profile is not None:
        policy_id = getattr(execution_profile.spec, "toolPolicy", {}).get("permissionPolicy") if hasattr(execution_profile.spec, "toolPolicy") else None
        if policy_id and policy_id not in policy_ids:
            policy_ids.append(policy_id)
    for policy_id, policy in index.permission_policies.items():
        scope = policy.spec.scope
        if scope.get("member") == member.object_id or scope.get("memberKind") == member.spec.kind:
            if policy_id not in policy_ids:
                policy_ids.append(policy_id)

    chunks: list[str] = []
    sources: list[dict[str, Any]] = []
    for policy_id in policy_ids:
        policy = index.permission_policies.get(policy_id)
        if not policy:
            continue
        chunks.append(
            "\n".join(
                [
                    f"### {policy_id}",
                    "",
                    f"- Scope: {policy.spec.scope}",
                    f"- Default mode: {policy.spec.defaultMode}",
                    f"- Allow: {', '.join(rule.match for rule in policy.spec.allow) or 'none'}",
                    f"- Ask: {', '.join(rule.match for rule in policy.spec.ask) or 'none'}",
                    f"- Deny: {', '.join(rule.match for rule in policy.spec.deny) or 'none'}",
                    f"- Sensitive paths: {', '.join(policy.spec.sensitivePaths) or 'none'}",
                ]
            )
        )
        sources.append({"id": policy_id, "defaultMode": policy.spec.defaultMode, "scope": policy.spec.scope})
    if not chunks:
        return "No permission policy was selected; fail closed and request human review for writes/tools.", sources
    chunks.append("\nDecision order: deny overrides ask; ask overrides allow; absent matches use defaultMode.")
    return "\n\n".join(chunks), sources


def _member_summary(member: Any, execution_profile: Any | None) -> str:
    lines = [
        f"- Display name: {member.spec.profile.displayName or member.object_id}",
        f"- Title: {member.spec.profile.title or 'unspecified'}",
        f"- Status: {member.spec.profile.status}",
        f"- Summary: {member.spec.profile.summary or 'unspecified'}",
        "",
        "Core capabilities:",
        "",
        _bullets(member.spec.aboutMe.coreCapabilities, "No core capabilities recorded."),
        "",
        "Work style:",
        "",
        _bullets(member.spec.aboutMe.workStyle, "No work style recorded."),
        "",
        "Work method:",
        "",
        _bullets(member.spec.aboutMe.workMethod, "No work method recorded."),
    ]
    if execution_profile is not None:
        lines.extend(["", f"Execution/collaboration profile: `{execution_profile.object_id}` ({execution_profile.kind})"])
    return "\n".join(lines)


def _assignment_summary(assignment: Any | None) -> str:
    if assignment is None:
        return "No assignment was selected. Treat this as an unscoped task and request assignment before writes."
    return "\n".join(
        [
            f"- Assignment: `{assignment.object_id}`",
            f"- Title: {assignment.spec.title or 'unspecified'}",
            f"- Role template: `{assignment.spec.roleTemplate or 'none'}`",
            f"- Role context: `{assignment.spec.roleContext or 'none'}`",
            f"- Status: {assignment.spec.status}",
            f"- Modules: {', '.join(assignment.spec.modules) or 'none'}",
            f"- Features: {', '.join(assignment.spec.features) or 'none'}",
            "",
            "Responsibilities:",
            "",
            _bullets(assignment.spec.responsibilities, "No assignment responsibilities recorded."),
            "",
            "Allowed read scope:",
            "",
            _bullets(assignment.spec.scope.read, "No explicit read scope recorded."),
            "",
            "Allowed write scope:",
            "",
            _bullets(assignment.spec.scope.write, "No explicit write scope recorded."),
            "",
            "Requires human review:",
            "",
            _bullets(assignment.spec.scope.requiresHumanReview, "No explicit review-sensitive scope recorded."),
        ]
    )


def _search_terms(title: str, acceptance: list[str], context_terms: list[str]) -> list[str]:
    text = " ".join([title, *acceptance, *context_terms]).lower()
    terms = []
    for token in re.findall(r"[a-z][a-z0-9_./-]{2,}", text):
        clean = token.strip("./-_")
        if clean and clean not in STOPWORDS and len(clean) >= 3 and clean not in terms:
            terms.append(clean)
    return terms[:24]


def _score_file(path: Path, rel: str, terms: list[str], scope_patterns: list[str]) -> int:
    rel_lower = rel.lower()
    score = 0
    for term in terms:
        if term in rel_lower:
            score += 4
    if any(_match_glob(rel, pattern) for pattern in scope_patterns):
        score += 3
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return score
    for term in terms:
        if term in text:
            score += min(text.count(term), 3)
    return score


def _list_repo_files(root: Path, limit: int) -> list[str]:
    files: list[str] = []
    try:
        for current_root, dirs, names in os.walk(root):
            rel_root = Path(current_root).relative_to(root).as_posix()
            dirs[:] = sorted(directory for directory in dirs if not _should_skip(_join_rel(rel_root, directory)))
            for name in sorted(names):
                if len(files) >= limit:
                    break
                rel = _join_rel(rel_root, name)
                if _should_skip(rel):
                    continue
                files.append(rel)
            if len(files) >= limit:
                break
    except OSError:
        return files
    return files


def _should_skip(rel: str) -> bool:
    parts = set(Path(rel).parts)
    if parts & SKIP_PARTS:
        return True
    if rel.endswith((".pyc", ".pyo", ".sqlite", ".db", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip")):
        return True
    return False


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def _is_doc_file(rel: str) -> bool:
    return rel.lower().endswith((".md", ".rst", ".txt"))


def _read_text(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]"
    return text


def _source_snippet(text: str) -> str:
    return _excerpt(" ".join(text.split()), SOURCE_SNIPPET_CHARS)


def _source_line_end(text: str) -> int:
    lines = text.splitlines()
    if not lines:
        return 1
    consumed = 0
    for index, line in enumerate(lines, start=1):
        consumed += len(line.strip()) + 1
        if consumed >= SOURCE_SNIPPET_CHARS:
            return index
    return len(lines)


def _is_truncated_text(text: str) -> bool:
    return text.endswith("\n...[truncated]")


def _dedupe_key(*parts: object) -> str:
    raw = ":".join(str(part) for part in parts if part is not None and str(part))
    return re.sub(r"[^A-Za-z0-9_.:/-]+", "-", raw).strip("-")


def _excerpt(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]"
    return text


def _is_safe_relative(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _match_glob(rel: str, pattern: str) -> bool:
    normalized = pattern.lstrip("/")
    return fnmatch.fnmatch(rel, normalized) or fnmatch.fnmatch("/" + rel, pattern)


def _join_rel(root: str, name: str) -> str:
    return name if root in {"", "."} else f"{root}/{name}"


def _bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def _branch_preview(task_id: str, member_id: str, run_id: str) -> str:
    return f"aiteamos/{task_id}/{member_id}/{run_id}"
