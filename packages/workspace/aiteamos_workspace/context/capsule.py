from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .budget import _budget_decision_manifest, _model_and_budget
from .decisions import (
    CODE_MAX_CHARS,
    CODE_MAX_FILES,
    DOC_MAX_CHARS,
    DOC_MAX_FILES,
    JOURNAL_EXCERPT_CHARS,
    MEMORY_MAX_ITEMS,
    RECENT_RUN_MAX,
    REPO_MAP_MAX_FILES,
    _assignment_summary,
    _branch_preview,
    _bullets,
    _collect_permission_context,
    _dedupe_key,
    _excerpt,
    _is_doc_file,
    _is_safe_relative,
    _is_text_file,
    _is_truncated_text,
    _list_repo_files,
    _manifest_summary,
    _member_summary,
    _read_text,
    _score_file,
    _search_terms,
    _source_counts,
    _source_decisions,
    _source_line_end,
    _source_snippet,
)


@dataclass(frozen=True)
class ContextCompilerResult:
    capsule: str
    manifest: dict[str, Any]


def build_context_capsule(
    index: Any,
    *,
    run_id: str,
    task_id: str,
    member_id: str | None = None,
    assignment_id: str | None = None,
    model_profile: str | None = None,
    branch_name: str | None = None,
) -> ContextCompilerResult:
    if task_id not in index.tasks:
        raise KeyError(f"unknown task {task_id}")
    task = index.tasks[task_id]
    run = index.runs.get(run_id)
    selected_member_id = member_id or (run.spec.member if run else None) or task.spec.assignedMember
    if not selected_member_id or selected_member_id not in index.members:
        raise KeyError(f"task {task_id} has no valid assigned TeamMember")
    member = index.members[selected_member_id]
    selected_assignment_id = assignment_id or (run.spec.assignment if run else None) or task.spec.assignment
    if not selected_assignment_id:
        selected_assignment_id = _first_assignment_for_member(index, selected_member_id, task.spec.project)
    assignment = index.assignments.get(selected_assignment_id or "")
    selected_model = model_profile or (run.spec.modelProfile if run else None) or _default_model_profile(index, selected_member_id, selected_assignment_id)
    selected_branch = branch_name or (run.spec.branch.name if run and run.spec.branch else None) or _branch_preview(task_id, selected_member_id, run_id)
    execution_profile = _execution_profile(index, selected_member_id, member.spec.kind)

    repos = _selected_repositories(index, assignment)
    responsibilities = list(assignment.spec.responsibilities if assignment else [])
    terms = _search_terms(
        task.spec.title,
        task.spec.acceptance,
        responsibilities
        + member.spec.aboutMe.coreCapabilities
        + member.spec.aboutMe.workStyle
        + member.spec.aboutMe.workMethod
        + (assignment.spec.modules if assignment else [])
        + (assignment.spec.features if assignment else []),
    )
    read_write_scope = _assignment_scope(assignment)
    docs, doc_sources, doc_exclusions = _collect_project_docs(index, repos)
    repo_maps, map_sources, map_exclusions = _collect_repository_maps(index, repos)
    code, code_sources, code_exclusions = _collect_relevant_code(index, repos, terms, read_write_scope)
    memory, memory_sources, memory_exclusions, binding_ids, grant_ids = _collect_context_memory(
        index,
        project=task.spec.project,
        member_id=selected_member_id,
        assignment_id=selected_assignment_id,
        task_id=task_id,
        run_id=run_id,
    )
    handoff_text, handoff_sources = _collect_recent_handoffs(index, task_id=task_id, run_id=run_id, member_id=selected_member_id)
    recent_runs, run_sources = _collect_recent_runs(
        index,
        current_run_id=run_id,
        task_id=task_id,
        member_id=selected_member_id,
        assignment_id=selected_assignment_id,
    )
    permission_text, permission_sources = _collect_permission_context(index, member, assignment, execution_profile)
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")
    sources = {
        "projectDocs": doc_sources,
        "repositoryMap": map_sources,
        "relevantCode": code_sources,
        "selectedMemory": memory_sources,
        "memoryBindings": [{"id": item} for item in binding_ids],
        "memoryGrants": [{"id": item} for item in grant_ids],
        "handoffs": handoff_sources,
        "permissionPolicies": permission_sources,
        "executionProfile": [_profile_source(execution_profile)],
        "recentRuns": run_sources,
    }
    exclusions = doc_exclusions + map_exclusions + code_exclusions + memory_exclusions
    source_manifest = {
        "generatedAt": generated_at,
        "task": task_id,
        "member": selected_member_id,
        "memberKind": member.spec.kind,
        "assignment": selected_assignment_id,
        "project": task.spec.project,
        "modelProfile": selected_model,
        "branch": selected_branch,
        "memoryBindings": binding_ids,
        "memoryGrants": grant_ids,
        "handoffs": [item["id"] for item in handoff_sources if item.get("id")],
        "sourcePriority": [
            "task",
            "member_identity",
            "assignment_contract",
            "permission_policy",
            "project_rules",
            "repository_map",
            "memory_grants",
            "memory_bindings",
            "recent_handoffs",
            "recent_runs",
            "model_budget",
        ],
        "sources": sources,
        "sourceDecisions": _source_decisions(sources, exclusions),
        "sourceCounts": _source_counts(sources),
        "exclusions": exclusions,
        "freshnessSignals": {
            "generatedAt": generated_at,
            "recentRunCount": len(run_sources),
            "approvedMemoryCount": len(memory_sources),
            "excludedMemoryCount": len(memory_exclusions),
        },
        "budget": _budget_decision_manifest(
            index,
            project=task.spec.project,
            member_id=selected_member_id,
            assignment_id=selected_assignment_id,
            task_id=task_id,
            model_profile=selected_model,
        ),
        "limits": {
            "projectDocs": DOC_MAX_FILES,
            "repositoryMapFiles": REPO_MAP_MAX_FILES,
            "relevantCodeFiles": CODE_MAX_FILES,
            "codeCharsPerFile": CODE_MAX_CHARS,
            "memoryItems": MEMORY_MAX_ITEMS,
        },
    }

    capsule = "\n".join(
        [
            f"# Context Capsule: {run_id}",
            "",
            "## Metadata",
            "",
            f"- Generated at: {generated_at}",
            f"- Project: `{task.spec.project}`",
            f"- Task: `{task_id}`",
            f"- Member: `{selected_member_id}`",
            f"- Member kind: `{member.spec.kind}`",
            f"- Assignment: `{selected_assignment_id or 'unassigned'}`",
            f"- Model profile: `{selected_model or 'unselected'}`",
            f"- Planned branch: `{selected_branch}`",
            "",
            "## Member Identity",
            "",
            _member_summary(member, execution_profile),
            "",
            "## Current Assignment Contract",
            "",
            _assignment_summary(assignment),
            "",
            "## Task",
            "",
            f"Title: {task.spec.title}",
            f"Priority: {task.spec.priority}",
            f"Status: {task.spec.status}",
            f"Execution mode: {task.spec.executionMode or 'unspecified'}",
            f"Risk class: {task.spec.riskClass or 'unspecified'}",
            "",
            "## Acceptance",
            "",
            _bullets(task.spec.acceptance, "No acceptance criteria recorded."),
            "",
            "## Permission Policy",
            "",
            permission_text,
            "",
            "## Project Rules And Canonical Docs",
            "",
            docs or "No project rule entrypoints were readable.",
            "",
            "## Repository Map",
            "",
            repo_maps or "No repository files were available for mapping.",
            "",
            "## Relevant Code Excerpts",
            "",
            code or "No relevant code excerpts were selected by the deterministic scanner.",
            "",
            "## Selected Memory",
            "",
            memory or "No memory was selected through active MemoryBinding or MemoryGrant records.",
            "",
            "## Recent Handoffs",
            "",
            handoff_text or "No recent handoff packets were found for this task/run/member.",
            "",
            "## Recent Related Runs",
            "",
            recent_runs or "No recent related runs were found.",
            "",
            "## Model And Budget",
            "",
            _model_and_budget(index, selected_model),
            "",
            "## Freshness And Conflict Rules",
            "",
            "- Task, member, assignment, and canonical project docs outrank episodic memory.",
            "- Memory is injected only through active MemoryBinding or MemoryGrant records.",
            "- Stale, deprecated, conflicted, or redacted memory is excluded unless a future policy explicitly permits advisory injection.",
            "- Conflicting instructions must be surfaced in the journal instead of silently merged.",
            "- If required files are outside assignment write scope or permission policy, stop and request review.",
            "",
            "## Execution Boundary",
            "",
            f"- Work on branch `{selected_branch}` only.",
            "- Do not work directly on `main`, `master`, or `develop`.",
            "- Return a PR, branch, commit, diff patch, or external review target when available.",
            "- Durable task/run/memory state must be written through AITEAMOS workspace APIs.",
            "- Do not include raw provider responses or secrets in Git-tracked files.",
            "",
            "## Output Contract",
            "",
            "- Write a concise work journal with decisions, commands, failures, and verification.",
            "- Include test commands and outcomes even when they fail.",
            "- Propose memory only when the lesson has evidence and should survive this run.",
            "- Do not approve or directly mutate another member's memory through this capsule.",
            "",
            "## Context Manifest",
            "",
            _manifest_summary(source_manifest),
            "",
        ]
    )
    return ContextCompilerResult(capsule=capsule, manifest=source_manifest)


def _execution_profile(index: Any, member_id: str, member_kind: str) -> Any | None:
    stores = {
        "digital": index.digital_execution_profiles,
        "human": index.human_collaboration_profiles,
        "hybrid": index.hybrid_execution_profiles,
        "service": index.service_account_profiles,
    }
    return stores.get(member_kind, {}).get(member_id)


def _profile_source(profile: Any | None) -> dict[str, Any]:
    if profile is None:
        return {"id": None, "reason": "no execution/collaboration profile found"}
    return {"id": profile.object_id, "kind": profile.kind}


def _first_assignment_for_member(index: Any, member_id: str, project: str) -> str | None:
    matches = [
        assignment.object_id
        for assignment in index.assignments.values()
        if assignment.spec.member == member_id and assignment.spec.project == project and assignment.spec.status == "active"
    ]
    return sorted(matches)[0] if len(matches) == 1 else None


def _default_model_profile(index: Any, member_id: str, assignment_id: str | None) -> str | None:
    member = index.members.get(member_id)
    profile = _execution_profile(index, member_id, member.spec.kind) if member else None
    if profile is not None and getattr(profile.spec, "defaultModelProfile", None):
        return profile.spec.defaultModelProfile
    for profile_id, model in sorted(index.model_profiles.items()):
        if assignment_id and assignment_id in model.spec.defaultForAssignments:
            return profile_id
        if member_id in model.spec.defaultForMembers:
            return profile_id
    return None


def _selected_repositories(index: Any, assignment: Any | None) -> list[Any]:
    names = list(assignment.spec.scope.repositories if assignment else [])
    if assignment:
        names.extend(name for name in assignment.spec.repositories if name not in names)
    if not names:
        names = list(index.repositories)
    repos = [index.repositories[name] for name in names if name in index.repositories]
    return sorted(repos or list(index.repositories.values()), key=lambda repo: repo.object_id)


def _assignment_scope(assignment: Any | None) -> list[str]:
    if assignment is None:
        return []
    return list(assignment.spec.scope.read) + list(assignment.spec.scope.write) + list(assignment.spec.modules)


def _repo_root(index: Any, repo: Any) -> Path | None:
    if repo.spec.localPath:
        path = Path(repo.spec.localPath).expanduser()
    elif repo.spec.workspaceRelation == "embedded":
        path = index.workspace_root.parent
    else:
        return None
    try:
        resolved = path.resolve()
    except OSError:
        return None
    return resolved if resolved.exists() and resolved.is_dir() else None


def _collect_project_docs(index: Any, repos: list[Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    default_repo = index.repositories.get(index.project.spec.defaultRepository or "")
    search_repos = [default_repo] if default_repo else repos
    entries = list(index.project.spec.ruleEntrypoints)
    for fallback in ["README.md", "docs/architecture.md"]:
        if fallback not in entries:
            entries.append(fallback)

    chunks: list[str] = []
    sources: list[dict[str, Any]] = []
    exclusions: list[str] = []
    for rel in entries:
        if len(sources) >= DOC_MAX_FILES:
            exclusions.append(f"project docs capped before {rel}")
            break
        doc_path = None
        repo_name = None
        for repo in search_repos:
            if repo is None:
                continue
            root = _repo_root(index, repo)
            if not root:
                continue
            candidate = (root / rel).resolve()
            if candidate.exists() and candidate.is_file() and _is_safe_relative(root, candidate):
                doc_path = candidate
                repo_name = repo.object_id
                break
        if not doc_path:
            exclusions.append(f"missing project doc {rel}")
            continue
        text = _read_text(doc_path, DOC_MAX_CHARS)
        chunks.append(f"### {repo_name}:{rel}\n\n{text}")
        sources.append(
            {
                "repo": repo_name,
                "path": rel,
                "reason": "project.ruleEntrypoints",
                "dedupeKey": _dedupe_key("projectDoc", repo_name, rel),
                "charsIncluded": len(text),
                "charsLimit": DOC_MAX_CHARS,
                "truncated": _is_truncated_text(text),
                "snippetPreview": _source_snippet(text),
                "lineStart": 1,
                "lineEnd": _source_line_end(text),
            }
        )
    return "\n\n".join(chunks), sources, exclusions


def _collect_repository_maps(index: Any, repos: list[Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    chunks: list[str] = []
    sources: list[dict[str, Any]] = []
    exclusions: list[str] = []
    for repo in repos:
        root = _repo_root(index, repo)
        repo_info = [
            f"### Repository `{repo.object_id}`",
            "",
            f"- Provider: {repo.spec.provider}",
            f"- URL: {repo.spec.url or 'none'}",
            f"- Local path: {str(root) if root else repo.spec.localPath or 'unresolved'}",
            f"- Default branch: {repo.spec.defaultBranch or 'unspecified'}",
            f"- Workspace relation: {repo.spec.workspaceRelation or 'unspecified'}",
            "",
        ]
        if not root:
            chunks.append("\n".join(repo_info) + "Repository local path could not be resolved.")
            exclusions.append(f"unresolved repository {repo.object_id}")
            continue
        files = _list_repo_files(root, REPO_MAP_MAX_FILES)
        if len(files) >= REPO_MAP_MAX_FILES:
            exclusions.append(f"repository map capped for {repo.object_id}")
        repo_info.append("\n".join(f"- {rel}" for rel in files) or "- No files found.")
        chunks.append("\n".join(repo_info))
        sources.append(
            {
                "repo": repo.object_id,
                "path": str(root),
                "files": len(files),
                "fileSample": files[:12],
                "reason": "repository.map",
                "dedupeKey": _dedupe_key("repositoryMap", repo.object_id),
                "budgetBucket": "repositoryMapFiles",
            }
        )
    return "\n\n".join(chunks), sources, exclusions


def _collect_relevant_code(
    index: Any,
    repos: list[Any],
    terms: list[str],
    scope_patterns: list[str],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    ranked: list[tuple[int, str, Any, Path]] = []
    exclusions: list[str] = []
    for repo in repos:
        root = _repo_root(index, repo)
        if not root:
            continue
        for rel in _list_repo_files(root, 2_500):
            path = root / rel
            if not _is_text_file(path) or _is_doc_file(rel):
                continue
            score = _score_file(path, rel, terms, scope_patterns)
            if score > 0:
                ranked.append((score, rel, repo, path))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = ranked[:CODE_MAX_FILES]
    if len(ranked) > CODE_MAX_FILES:
        exclusions.append(f"relevant code capped from {len(ranked)} candidates")

    chunks: list[str] = []
    sources: list[dict[str, Any]] = []
    for score, rel, repo, path in selected:
        text = _read_text(path, CODE_MAX_CHARS)
        chunks.append(f"### {repo.object_id}:{rel}\n\n```text\n{text}\n```")
        sources.append(
            {
                "repo": repo.object_id,
                "path": rel,
                "score": score,
                "reason": "term+scope match",
                "dedupeKey": _dedupe_key("relevantCode", repo.object_id, rel),
                "charsIncluded": len(text),
                "charsLimit": CODE_MAX_CHARS,
                "truncated": _is_truncated_text(text),
                "snippetPreview": _source_snippet(text),
                "lineStart": 1,
                "lineEnd": _source_line_end(text),
            }
        )
    return "\n\n".join(chunks), sources, exclusions


def _collect_context_memory(
    index: Any,
    *,
    project: str,
    member_id: str,
    assignment_id: str | None,
    task_id: str,
    run_id: str,
) -> tuple[str, list[dict[str, Any]], list[str], list[str], list[str]]:
    binding_ids: list[str] = []
    grant_ids: list[str] = []
    selected: dict[str, tuple[Any, int, str]] = {}
    exclusions: list[str] = []

    for binding in index.memory_bindings.values():
        if binding.spec.status != "active" or "inject" not in binding.spec.access:
            continue
        if not _binding_targets_context(binding, project, member_id, assignment_id, task_id, run_id):
            continue
        binding_ids.append(binding.object_id)
        for entry in _entries_for_binding(index, binding):
            _select_memory_entry(selected, exclusions, entry, rank=20, reason=f"binding:{binding.object_id}", member_id=member_id, project=project)

    for grant in index.memory_grants.values():
        if grant.spec.status != "active" or grant.spec.granteeMember != member_id or "inject" not in grant.spec.access:
            continue
        if _memory_grant_expiry_state(grant) != "active":
            exclusions.append(f"expired memory grant omitted {grant.object_id}")
            continue
        if grant.spec.task and grant.spec.task != task_id:
            continue
        if grant.spec.run and grant.spec.run != run_id:
            continue
        grant_ids.append(grant.object_id)
        for store_id in grant.spec.stores:
            for entry in _entries_for_store(index, store_id):
                _select_memory_entry(selected, exclusions, entry, rank=10, reason=f"grant:{grant.object_id}", member_id=member_id, project=project)
        for entry_id in grant.spec.entries:
            entry = index.memory_entries.get(entry_id)
            if entry:
                _select_memory_entry(selected, exclusions, entry, rank=5, reason=f"grant:{grant.object_id}", member_id=member_id, project=project)

    ranked = sorted(selected.values(), key=lambda item: (item[1], item[0].object_id))[:MEMORY_MAX_ITEMS]
    if len(selected) > MEMORY_MAX_ITEMS:
        exclusions.append(f"memory capped from {len(selected)} candidates")
    chunks: list[str] = []
    sources: list[dict[str, Any]] = []
    for entry, rank, reason in ranked:
        chunks.append(
            "\n".join(
                [
                    f"### {entry.spec.title}",
                    "",
                    f"- ID: `{entry.object_id}`",
                    f"- Store: `{entry.spec.store}`",
                    f"- Path: `{entry.spec.path}`",
                    f"- Kind: {entry.spec.kind}",
                    f"- Scope: {entry.spec.scope}",
                    f"- Lifecycle: {entry.spec.lifecycle}",
                    f"- Source: {entry.spec.source or 'unspecified'}",
                    f"- Confidence: {entry.spec.confidence if entry.spec.confidence is not None else 'unspecified'}",
                    f"- Last verified at: {entry.spec.lastVerifiedAt or 'missing'}",
                    f"- Evidence: {', '.join(entry.spec.evidence) or 'none'}",
                    f"- Selection reason: {reason}",
                    "",
                    entry.spec.content,
                ]
            )
        )
        sources.append(
            {
                "memory": entry.object_id,
                "store": entry.spec.store,
                "kind": entry.spec.kind,
                "scope": entry.spec.scope,
                "lifecycle": entry.spec.lifecycle,
                "confidence": entry.spec.confidence,
                "freshness": entry.spec.freshness,
                "lastVerifiedAt": entry.spec.lastVerifiedAt,
                "aclRead": list(entry.spec.acl.read),
                "sensitivity": entry.spec.sensitivity,
                "evidenceCount": len(entry.spec.evidence),
                "rank": rank,
                "reason": reason,
                "dedupeKey": _dedupe_key("memory", entry.object_id),
                "budgetBucket": "memoryItems",
                "snippetPreview": _source_snippet(entry.spec.content),
                "lineStart": 1,
                "lineEnd": _source_line_end(entry.spec.content),
            }
        )
    return "\n\n".join(chunks), sources, exclusions, sorted(set(binding_ids)), sorted(set(grant_ids))


def _binding_targets_context(
    binding: Any,
    project: str,
    member_id: str,
    assignment_id: str | None,
    task_id: str,
    run_id: str,
) -> bool:
    target = binding.spec.targetId
    return (
        (binding.spec.targetType == "project" and target == project)
        or (binding.spec.targetType == "member" and target == member_id)
        or (binding.spec.targetType == "assignment" and target == assignment_id)
        or (binding.spec.targetType == "task" and target == task_id)
        or (binding.spec.targetType == "run" and target == run_id)
        or (binding.spec.targetType == "context-capsule" and target == run_id)
    )


def _entries_for_binding(index: Any, binding: Any) -> list[Any]:
    if binding.spec.entry and binding.spec.entry in index.memory_entries:
        return [index.memory_entries[binding.spec.entry]]
    if binding.spec.store:
        return _entries_for_store(index, binding.spec.store)
    return []


def _entries_for_store(index: Any, store_id: str) -> list[Any]:
    return [entry for entry in index.memory_entries.values() if entry.spec.store == store_id]


def _memory_grant_expiry_state(grant: Any) -> str:
    expires_at = grant.spec.expiresAt
    if not expires_at:
        return "active"
    try:
        parsed = datetime.fromisoformat(expires_at)
    except ValueError:
        return "expired"
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return "expired" if datetime.now(timezone.utc).astimezone() >= parsed else "active"


def _select_memory_entry(
    selected: dict[str, tuple[Any, int, str]],
    exclusions: list[str],
    entry: Any,
    *,
    rank: int,
    reason: str,
    member_id: str,
    project: str,
) -> None:
    if entry.spec.lifecycle in {"stale", "deprecated", "conflicted", "redacted", "archived"}:
        exclusions.append(f"{entry.spec.lifecycle} memory omitted {entry.object_id}")
        return
    if entry.spec.sensitivity == "secret":
        exclusions.append(f"secret memory omitted {entry.object_id}")
        return
    if not _memory_acl_allows(entry.spec.acl.read, member_id=member_id, project=project):
        exclusions.append(f"memory ACL omitted {entry.object_id}")
        return
    previous = selected.get(entry.object_id)
    if previous is None or rank < previous[1]:
        selected[entry.object_id] = (entry, rank, reason)


def _memory_acl_allows(read_acl: list[str], *, member_id: str, project: str) -> bool:
    if not read_acl:
        return True
    allowed = {f"member:{member_id}", f"project:{project}", "organization", "public", "admin"}
    return bool(set(read_acl) & allowed)


def _collect_recent_handoffs(index: Any, *, task_id: str, run_id: str, member_id: str) -> tuple[str, list[dict[str, Any]]]:
    records = [
        handoff
        for handoff in index.handoffs.values()
        if handoff.spec.task == task_id
        and (handoff.spec.run in {None, run_id} or handoff.spec.run == run_id)
        and member_id in {handoff.spec.fromMember, handoff.spec.toMember}
    ]
    records.sort(key=lambda item: item.object_id, reverse=True)
    chunks: list[str] = []
    sources: list[dict[str, Any]] = []
    for handoff in records[:RECENT_RUN_MAX]:
        chunks.append(
            "\n".join(
                [
                    f"### {handoff.object_id}",
                    "",
                    f"- From: `{handoff.spec.fromMember}`",
                    f"- To: `{handoff.spec.toMember}`",
                    f"- Ownership: {handoff.spec.ownership}",
                    f"- Status: {handoff.spec.status}",
                    f"- Problem: {handoff.spec.problem}",
                    f"- Recommended next step: {handoff.spec.recommendedNextStep or 'unspecified'}",
                    f"- Shared memory pack: {', '.join(handoff.spec.sharedMemoryPack) or 'none'}",
                ]
            )
        )
        sources.append({"id": handoff.object_id, "from": handoff.spec.fromMember, "to": handoff.spec.toMember})
    return "\n\n".join(chunks), sources


def _collect_recent_runs(
    index: Any,
    *,
    current_run_id: str,
    task_id: str,
    member_id: str,
    assignment_id: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    candidates = []
    task = index.tasks.get(task_id)
    related = set(task.spec.relatedRuns if task else [])
    for run_id, run in index.runs.items():
        if run_id == current_run_id:
            continue
        if run_id in related or run.spec.member == member_id or run.spec.assignment == assignment_id or run.spec.task == task_id:
            candidates.append((run_id, run))
    candidates.sort(key=lambda item: item[0], reverse=True)
    chunks: list[str] = []
    sources: list[dict[str, Any]] = []
    for run_id, run in candidates[:RECENT_RUN_MAX]:
        events = index.run_events.get(run_id, [])
        journal = index.run_journals.get(run_id, "")
        event_tail = events[-3:]
        chunks.append(
            "\n".join(
                [
                    f"### {run_id}",
                    "",
                    f"- Task: `{run.spec.task}`",
                    f"- Member: `{run.spec.member}`",
                    f"- Assignment: `{run.spec.assignment or 'none'}`",
                    f"- Status: {run.spec.status}",
                    f"- Model profile: {run.spec.modelProfile or 'unselected'}",
                    f"- Review target: {run.spec.reviewTarget.url if run.spec.reviewTarget and run.spec.reviewTarget.url else 'none'}",
                    f"- Recent events: {event_tail or 'none'}",
                    "",
                    _excerpt(journal, JOURNAL_EXCERPT_CHARS) or "No journal excerpt recorded.",
                ]
            )
        )
        sources.append({"run": run_id, "task": run.spec.task, "member": run.spec.member, "assignment": run.spec.assignment, "status": run.spec.status})
    return "\n\n".join(chunks), sources
