from __future__ import annotations

from pathlib import Path
from typing import Any
import re
from datetime import datetime

from .loader import WorkspaceIndex, load_workspace, manifest_to_record


DEFAULT_LIMIT = 10
MAX_SNIPPET_CHARS = 480
TEXT_SUFFIXES = {".md", ".rst", ".txt", ".yaml", ".yml"}
SENSITIVE_MEMORY_LEVELS = {"confidential", "secret"}
PRIVATE_MEMORY_VISIBILITIES = {"private"}
SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[A-Z0-9_]*=)([^\s]+)"
)
SECRET_FIELD_RE = re.compile(
    r'(?i)(["\']?(?:api[_-]?key|token|secret|password|credential)["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)'
)
SECRET_TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b")


def get_task_for_tool(workspace_or_index: str | Path | WorkspaceIndex, task_id: str) -> dict[str, Any]:
    index = _index(workspace_or_index)
    if task_id not in index.tasks:
        raise KeyError(f"unknown task {task_id}")
    task = index.tasks[task_id]
    record = manifest_to_record(task)
    record["markdown"] = _redact(index.task_markdown.get(task_id) or "")
    record["runs"] = sorted(run_id for run_id, run in index.runs.items() if run.spec.task == task_id)
    record["reviews"] = sorted(review_id for review_id, review in index.reviews.items() if review.spec.task == task_id)
    return {"tool": "get_task", "task": record}


def get_context_capsule_for_tool(workspace_or_index: str | Path | WorkspaceIndex, run_id: str) -> dict[str, Any]:
    index = _index(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    content = index.run_context_capsules.get(run_id)
    if content is None:
        raise ValueError(f"run {run_id} has no context capsule")
    path = f"runs/{run_id}/{run.spec.contextCapsule}" if run.spec.contextCapsule else None
    return {
        "tool": "get_context_capsule",
        "run": run_id,
        "task": run.spec.task,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "memberKind": run.spec.memberKind,
        "path": path,
        "content": _redact(content),
        "contextManifest": index.run_context_manifests.get(run_id),
    }


def search_memory_for_tool(
    workspace_or_index: str | Path | WorkspaceIndex,
    query: str,
    *,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    store: str | None = None,
    limit: int = DEFAULT_LIMIT,
    viewer_member: str | None = None,
    apply_governance: bool = False,
) -> dict[str, Any]:
    index = _index(workspace_or_index)
    terms = _terms(query)
    selected_project = _selected_project(index, project)
    if member and member not in index.members:
        raise KeyError(f"unknown member {member}")
    if viewer_member and viewer_member not in index.members:
        raise KeyError(f"unknown viewer member {viewer_member}")
    if assignment and assignment not in index.assignments:
        raise KeyError(f"unknown assignment {assignment}")
    if assignment:
        assignment_record = index.assignments[assignment]
        if assignment_record.spec.project != selected_project:
            raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {selected_project}")
        if member and assignment_record.spec.member != member:
            raise ValueError(f"assignment {assignment} belongs to member {assignment_record.spec.member}, not {member}")
        member = member or assignment_record.spec.member
    if store and store not in index.memory_stores:
        raise KeyError(f"unknown memory store {store}")
    matches: list[dict[str, Any]] = []
    excluded_matches = 0

    for entry_id, entry in index.memory_entries.items():
        if not _entry_matches_scope(index, entry_id, entry, selected_project, member, assignment, store):
            continue
        if apply_governance and _memory_entry_requires_redaction(index, entry_id, entry, viewer_member=viewer_member):
            excluded_matches += 1
            continue
        metadata = _entry_scope_metadata(index, entry_id, entry)
        text = "\n".join([entry.spec.title, entry.spec.content, "\n".join(entry.spec.evidence), "\n".join(entry.spec.tags)])
        score = _score(text, terms) if terms else 1
        if score:
            matches.append(
                {
                    "id": entry_id,
                    "source": "memory-entry",
                    "lifecycle": entry.spec.lifecycle,
                    "project": metadata["project"],
                    "member": metadata["member"],
                    "assignment": metadata["assignment"],
                    "store": entry.spec.store,
                    "kind": entry.spec.kind,
                    "scope": entry.spec.scope,
                    "title": entry.spec.title,
                    "snippet": _snippet(text, terms),
                    "score": score,
                    "bindings": metadata["bindings"],
                    "grants": metadata["grants"],
                    "relatedProjects": entry.spec.relatedProjects,
                    "relatedMembers": entry.spec.relatedMembers,
                    "relatedAssignments": entry.spec.relatedAssignments,
                }
            )

    for proposal_id, proposal in index.memory_proposals.items():
        if not _proposal_matches_scope(proposal, selected_project, member, assignment, store):
            continue
        if apply_governance and not _viewer_can_read_memory_proposal(index, proposal, viewer_member=viewer_member):
            excluded_matches += 1
            continue
        text = "\n".join([proposal.spec.title, proposal.spec.content, "\n".join(proposal.spec.evidence)])
        score = _score(text, terms) if terms else 1
        if score:
            matches.append(
                {
                    "id": proposal_id,
                    "source": "memory-proposal",
                    "status": proposal.spec.status,
                    "project": proposal.spec.project,
                    "member": proposal.spec.member,
                    "assignment": proposal.spec.assignment,
                    "store": proposal.spec.store,
                    "kind": proposal.spec.kind,
                    "title": proposal.spec.title,
                    "snippet": _snippet(text, terms),
                    "score": score,
                }
            )

    matches.sort(key=lambda item: (-item["score"], item["source"], item["id"]))
    return {
        "tool": "search_memory",
        "query": query,
        "project": selected_project,
        "member": member,
        "assignment": assignment,
        "store": store,
        "viewerMember": viewer_member,
        "excludedMatches": excluded_matches,
        "matches": matches[: _limit(limit)],
    }


def search_docs_for_tool(
    workspace_or_index: str | Path | WorkspaceIndex,
    query: str,
    *,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    index = _index(workspace_or_index)
    selected_project = _selected_project(index, project)
    if member and member not in index.members:
        raise KeyError(f"unknown member {member}")
    if assignment and assignment not in index.assignments:
        raise KeyError(f"unknown assignment {assignment}")
    if assignment:
        assignment_record = index.assignments[assignment]
        if assignment_record.spec.project != selected_project:
            raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {selected_project}")
        if member and assignment_record.spec.member != member:
            raise ValueError(f"assignment {assignment} belongs to member {assignment_record.spec.member}, not {member}")
        member = member or assignment_record.spec.member
    terms = _terms(query)
    docs = _project_doc_candidates(index, selected_project, member, assignment)
    matches: list[dict[str, Any]] = []
    for candidate in docs:
        text = candidate["content"]
        score = _score(text, terms) if terms else 1
        if not score:
            continue
        matches.append(
            {
                "repo": candidate["repo"],
                "path": candidate["path"],
                "reason": candidate["reason"],
                "snippet": _snippet(text, terms),
                "score": score,
            }
        )
    matches.sort(key=lambda item: (-item["score"], item["repo"], item["path"]))
    return {
        "tool": "search_docs",
        "query": query,
        "project": selected_project,
        "member": member,
        "assignment": assignment,
        "matches": matches[: _limit(limit)],
    }


def _index(workspace_or_index: str | Path | WorkspaceIndex) -> WorkspaceIndex:
    if isinstance(workspace_or_index, WorkspaceIndex):
        return workspace_or_index
    return load_workspace(workspace_or_index)


def _selected_project(index: WorkspaceIndex, project: str | None) -> str:
    selected_project = project or index.project.object_id
    if selected_project != index.project.object_id:
        raise KeyError(f"unknown project {selected_project}")
    return selected_project


def _project_doc_candidates(
    index: WorkspaceIndex,
    project: str,
    member: str | None,
    assignment: str | None,
) -> list[dict[str, str]]:
    entries: list[tuple[str, str]] = [(path, "project.ruleEntrypoints") for path in index.project.spec.ruleEntrypoints]
    for fallback in ["README.md", "docs/architecture.md"]:
        if fallback not in {entry[0] for entry in entries}:
            entries.append((fallback, "project.fallback"))

    assignment_ids = _assignment_ids_for_scope(index, project, member, assignment)
    for assignment_id in assignment_ids:
        assignment_record = index.assignments[assignment_id]
        for path in assignment_record.spec.scope.read:
            entries.append((path, f"assignment.scope.read:{assignment_id}"))

    candidates: list[dict[str, str]] = []
    for repo in index.repositories.values():
        root = _repo_root(index, repo)
        if root is None:
            continue
        seen: set[str] = set()
        for rel, reason in entries:
            for path, display_path in _expand_text_paths(root, rel):
                if display_path in seen:
                    continue
                seen.add(display_path)
                candidates.append(
                    {
                        "repo": repo.object_id,
                        "path": display_path,
                        "reason": reason,
                        "content": _redact(path.read_text(encoding="utf-8", errors="replace")),
                    }
                )
    return candidates


def _assignment_ids_for_scope(index: WorkspaceIndex, project: str, member: str | None, assignment: str | None) -> list[str]:
    if assignment:
        return [assignment]
    if not member:
        return []
    return [
        assignment_id
        for assignment_id, record in sorted(index.assignments.items())
        if record.spec.project == project and record.spec.member == member and record.spec.status == "active"
    ]


def _expand_text_paths(root: Path, rel: str) -> list[tuple[Path, str]]:
    if not rel or rel.startswith("/"):
        return []
    pattern = rel.rstrip("/")
    paths: list[tuple[Path, str]] = []
    if any(char in pattern for char in "*?[]"):
        for path in sorted(root.glob(pattern)):
            resolved = path.resolve()
            if resolved.is_file() and resolved.suffix.lower() in TEXT_SUFFIXES and _is_safe_relative(root, resolved):
                paths.append((resolved, resolved.relative_to(root).as_posix()))
        return paths[:200]

    path = (root / pattern).resolve()
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            resolved = child.resolve()
            if resolved.is_file() and resolved.suffix.lower() in TEXT_SUFFIXES and _is_safe_relative(root, resolved):
                paths.append((resolved, resolved.relative_to(root).as_posix()))
        return paths[:200]
    if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and _is_safe_relative(root, path):
        return [(path, pattern)]
    return []


def _entry_matches_scope(
    index: WorkspaceIndex,
    entry_id: str,
    entry: Any,
    project: str,
    member: str | None,
    assignment: str | None,
    store: str | None,
) -> bool:
    if entry.spec.lifecycle in {"redacted", "archived"} or entry.spec.sensitivity == "secret":
        return False
    if store and entry.spec.store != store:
        return False
    if not _entry_project_ids(index, entry_id, entry) or project not in _entry_project_ids(index, entry_id, entry):
        return False
    if member and member not in _entry_member_ids(index, entry_id, entry):
        return False
    if assignment and assignment not in _entry_assignment_ids(index, entry_id, entry):
        return False
    return True


def _memory_entry_requires_redaction(
    index: WorkspaceIndex,
    entry_id: str,
    entry: Any,
    *,
    viewer_member: str | None = None,
) -> bool:
    if entry.spec.lifecycle == "redacted":
        return True
    if _viewer_can_read_memory_entry(index, entry_id, entry, viewer_member=viewer_member):
        return False
    return entry.spec.visibility in PRIVATE_MEMORY_VISIBILITIES or entry.spec.sensitivity in SENSITIVE_MEMORY_LEVELS


def _viewer_can_read_memory_entry(
    index: WorkspaceIndex,
    entry_id: str,
    entry: Any,
    *,
    viewer_member: str | None = None,
) -> bool:
    if entry.spec.lifecycle in {"redacted", "archived"}:
        return False
    if entry.spec.visibility == "public" and entry.spec.sensitivity != "secret":
        return True
    principals = _memory_viewer_principals(index, viewer_member)
    if entry.spec.acl.read:
        return bool(principals.intersection(entry.spec.acl.read))
    if entry.spec.sensitivity == "secret":
        return False
    if not viewer_member:
        return False
    if entry.spec.visibility == "organization":
        return True
    if viewer_member in set(entry.spec.relatedMembers):
        return True
    if _viewer_can_read_memory_store(index, index.memory_stores.get(entry.spec.store), viewer_member=viewer_member):
        return True
    if any(f"project:{project_id}" in principals for project_id in _entry_project_ids(index, entry_id, entry)):
        return entry.spec.visibility == "project"
    return False


def _viewer_can_read_memory_store(index: WorkspaceIndex, store: Any, *, viewer_member: str | None = None) -> bool:
    if store is None:
        return False
    visibility = store.spec.visibility
    if visibility == "public":
        return True
    principals = _memory_viewer_principals(index, viewer_member)
    if store.spec.acl.read:
        return bool(principals.intersection(store.spec.acl.read))
    if not viewer_member:
        return False
    if visibility == "organization":
        return True
    if visibility == "project" and store.spec.ownerProject and f"project:{store.spec.ownerProject}" in principals:
        return True
    if visibility == "private" and store.spec.ownerMember == viewer_member:
        return True
    return False


def _viewer_can_read_memory_proposal(index: WorkspaceIndex, proposal: Any, *, viewer_member: str | None = None) -> bool:
    if not viewer_member:
        return True
    if proposal.spec.member:
        return proposal.spec.member == viewer_member
    if proposal.spec.assignment:
        assignment = index.assignments.get(proposal.spec.assignment)
        return bool(assignment and assignment.spec.member == viewer_member)
    return f"project:{proposal.spec.project}" in _memory_viewer_principals(index, viewer_member)


def _memory_viewer_principals(index: WorkspaceIndex, viewer_member: str | None) -> set[str]:
    if not viewer_member or viewer_member not in index.members:
        return {"public"}
    principals = {"public", "organization", f"member:{viewer_member}"}
    for assignment in index.assignments.values():
        if assignment.spec.member == viewer_member:
            principals.add(f"assignment:{assignment.object_id}")
            principals.add(f"project:{assignment.spec.project}")
    return principals


def _proposal_matches_scope(
    proposal: Any,
    project: str,
    member: str | None,
    assignment: str | None,
    store: str | None,
) -> bool:
    if proposal.spec.project != project:
        return False
    if member and proposal.spec.member != member:
        return False
    if assignment and proposal.spec.assignment != assignment:
        return False
    if store and proposal.spec.store != store:
        return False
    return True


def _entry_scope_metadata(index: WorkspaceIndex, entry_id: str, entry: Any) -> dict[str, Any]:
    projects = sorted(_entry_project_ids(index, entry_id, entry))
    members = sorted(_entry_member_ids(index, entry_id, entry))
    assignments = sorted(_entry_assignment_ids(index, entry_id, entry))
    return {
        "project": projects[0] if projects else None,
        "member": members[0] if members else None,
        "assignment": assignments[0] if assignments else None,
        "bindings": sorted(_entry_binding_ids(index, entry_id, entry)),
        "grants": sorted(_entry_grant_ids(index, entry_id, entry)),
    }


def _entry_project_ids(index: WorkspaceIndex, entry_id: str, entry: Any) -> set[str]:
    projects = set(entry.spec.relatedProjects)
    store = index.memory_stores.get(entry.spec.store)
    if store and store.spec.ownerProject:
        projects.add(store.spec.ownerProject)
    for binding in _entry_bindings(index, entry_id, entry):
        if binding.spec.targetType == "project":
            projects.add(binding.spec.targetId)
        elif binding.spec.targetType == "assignment" and binding.spec.targetId in index.assignments:
            projects.add(index.assignments[binding.spec.targetId].spec.project)
        elif binding.spec.targetType == "member":
            for assignment in index.assignments.values():
                if assignment.spec.member == binding.spec.targetId:
                    projects.add(assignment.spec.project)
    if not projects and entry.spec.scope == "project":
        projects.add(index.project.object_id)
    return projects


def _entry_member_ids(index: WorkspaceIndex, entry_id: str, entry: Any) -> set[str]:
    members = set(entry.spec.relatedMembers)
    store = index.memory_stores.get(entry.spec.store)
    if store and store.spec.ownerMember:
        members.add(store.spec.ownerMember)
    for binding in _entry_bindings(index, entry_id, entry):
        if binding.spec.targetType == "member":
            members.add(binding.spec.targetId)
        elif binding.spec.targetType == "assignment" and binding.spec.targetId in index.assignments:
            members.add(index.assignments[binding.spec.targetId].spec.member)
    for grant in _entry_grants(index, entry_id, entry):
        members.add(grant.spec.granteeMember)
    return members


def _entry_assignment_ids(index: WorkspaceIndex, entry_id: str, entry: Any) -> set[str]:
    assignments = set(entry.spec.relatedAssignments)
    for binding in _entry_bindings(index, entry_id, entry):
        if binding.spec.targetType == "assignment":
            assignments.add(binding.spec.targetId)
    return assignments


def _entry_binding_ids(index: WorkspaceIndex, entry_id: str, entry: Any) -> set[str]:
    return {binding_id for binding_id, binding in index.memory_bindings.items() if _binding_applies_to_entry(binding, entry_id, entry)}


def _entry_bindings(index: WorkspaceIndex, entry_id: str, entry: Any) -> list[Any]:
    return [binding for binding in index.memory_bindings.values() if _binding_applies_to_entry(binding, entry_id, entry)]


def _binding_applies_to_entry(binding: Any, entry_id: str, entry: Any) -> bool:
    if binding.spec.status != "active":
        return False
    if binding.spec.entry:
        return binding.spec.entry == entry_id
    if binding.spec.store and binding.spec.store != entry.spec.store:
        return False
    if binding.spec.collectionPath:
        return entry.spec.path.startswith(binding.spec.collectionPath.rstrip("/") + "/")
    return bool(binding.spec.store)


def _entry_grant_ids(index: WorkspaceIndex, entry_id: str, entry: Any) -> set[str]:
    return {grant_id for grant_id, grant in index.memory_grants.items() if _grant_applies_to_entry(grant, entry_id, entry)}


def _entry_grants(index: WorkspaceIndex, entry_id: str, entry: Any) -> list[Any]:
    return [grant for grant in index.memory_grants.values() if _grant_applies_to_entry(grant, entry_id, entry)]


def _grant_applies_to_entry(grant: Any, entry_id: str, entry: Any) -> bool:
    if grant.spec.status != "active":
        return False
    expires_at = _parse_time(grant.spec.expiresAt)
    if expires_at and datetime.now().astimezone() > expires_at:
        return False
    return entry_id in grant.spec.entries or entry.spec.store in grant.spec.stores


def _repo_root(index: WorkspaceIndex, repo: Any) -> Path | None:
    if repo.spec.localPath:
        root = Path(repo.spec.localPath).expanduser()
        if not root.is_absolute():
            root = index.workspace_root.parent / root
    elif repo.spec.workspaceRelation == "embedded":
        root = index.workspace_root.parent
    else:
        root = index.workspace_root.parent
    root = root.resolve()
    return root if root.exists() and root.is_dir() else None


def _is_safe_relative(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    return not any(part in {".git", ".aiteamos", "node_modules", "dist", "build"} for part in path.parts)


def _terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[a-zA-Z0-9_.-]{2,}", query.lower()) if term]


def _score(text: str, terms: list[str]) -> int:
    if not terms:
        return 0
    lowered = text.lower()
    return sum(lowered.count(term) for term in terms)


def _snippet(text: str, terms: list[str]) -> str:
    redacted = _redact(text)
    lowered = redacted.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 120)
    snippet = redacted[start : start + MAX_SNIPPET_CHARS].strip()
    return snippet.replace("\n", " ")


def _limit(limit: int) -> int:
    return max(1, min(50, int(limit or DEFAULT_LIMIT)))


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _redact(text: str) -> str:
    redacted = SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", text)
    redacted = SECRET_FIELD_RE.sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_TOKEN_RE.sub("sk-[REDACTED]", redacted)
    return redacted
