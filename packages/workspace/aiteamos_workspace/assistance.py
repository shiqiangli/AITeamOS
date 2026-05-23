from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from aiteamos_schema import RunAssistanceBundleFile, RunAssistanceBundleRecord, RunAssistancePackageRecord

from .context import build_context_capsule


ASSISTED_MEMBER_KINDS = {"human", "hybrid"}
ASSISTED_RUN_MODES = {"assisted", "manual"}


def build_run_assistance_package(index: Any, run_id: str) -> RunAssistancePackageRecord:
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    task_id = run.spec.task
    member_id = run.spec.member
    assignment_id = run.spec.assignment
    if task_id not in index.tasks:
        raise KeyError(f"unknown task {task_id}")
    if member_id not in index.members:
        raise KeyError(f"unknown member {member_id}")

    task = index.tasks[task_id]
    member = index.members[member_id]
    assignment = index.assignments.get(assignment_id or "")
    member_kind = run.spec.memberKind or member.spec.kind
    blockers: list[str] = []
    warnings: list[str] = []

    if member_kind not in ASSISTED_MEMBER_KINDS:
        blockers.append("Assisted execution packages are only ready for human or hybrid TeamMembers.")
    if run.spec.mode not in ASSISTED_RUN_MODES:
        blockers.append("Run mode is not an assisted/manual execution mode.")
    if assignment_id and not assignment:
        blockers.append(f"Run references unknown assignment {assignment_id}.")
    if not assignment_id:
        warnings.append("Run has no Assignment; package cannot include an assignment-level write contract.")

    context_sources: dict[str, int] = {}
    selected_memory: list[str] = []
    handoffs: list[str] = []
    try:
        context = build_context_capsule(
            index,
            run_id=run_id,
            task_id=task_id,
            member_id=member_id,
            assignment_id=assignment_id,
            model_profile=run.spec.modelProfile,
            branch_name=run.spec.branch.name if run.spec.branch else None,
        )
        manifest = context.manifest
        context_sources = _int_dict(manifest.get("sourceCounts"))
        selected_memory = _source_ids(manifest, "selectedMemory", ("memory", "id"))
        handoffs = _source_ids(manifest, "handoffs", ("id",))
    except Exception as exc:  # pragma: no cover - defensive projection fallback
        warnings.append(f"Context capsule preview is unavailable: {exc}")

    allowed_writes = _dedupe(_assignment_scope(assignment, "write"))
    read_scope = _dedupe(_assignment_scope(assignment, "read") + _repository_scope(assignment))
    responsibilities = list(assignment.spec.responsibilities if assignment else [])
    branch = _branch_contract(index, run, task_id, member_id)
    api_run_path = _workspace_api_path(index, f"/runs/{run_id}")
    summary = (
        f"{member_id} can execute {task_id} with an assisted package and return journal, review target, tests, "
        "and memory proposals through the explicit ingest API."
        if not blockers
        else f"{member_id} has a package preview for {task_id}, but it is blocked until the run/member contract is corrected."
    )

    return RunAssistancePackageRecord(
        run=run_id,
        task=task_id,
        project=run.spec.project,
        member=member_id,
        memberKind=member_kind,
        assignment=assignment_id,
        mode=run.spec.mode,
        status=run.spec.status,
        readyForAssistedExecution=not blockers,
        generatedAt=datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
        summary=summary,
        entrypoints=[
            {
                "label": "Open Run Detail",
                "command": f"/?page=Runs&run={run_id}",
                "purpose": "Open the URL-addressable Run detail and assisted ingest workbench.",
            },
            {
                "label": "Validate Workspace",
                "command": "./aiteamos workspace validate --workspace .aiteamos",
                "purpose": "Check the source-of-truth manifests before returning assisted work.",
            },
            {
                "label": "Return Assisted Output",
                "command": f"POST {api_run_path}/assisted-ingest",
                "purpose": "Submit journal, diff or review target, tests, and optional memory proposal through the durable API boundary.",
            },
        ],
        ideWorkspace={
            "route": f"/?page=Runs&run={run_id}",
            "memberDisplayName": member.spec.profile.displayName or member_id,
            "recommendedPanels": ["Assisted Execution Package", "Assisted Ingest Workbench", "Run Review Console"],
            "repositories": _repository_records(index, assignment),
        },
        branch=branch,
        allowedWrites=allowed_writes,
        readScope=read_scope,
        responsibilities=responsibilities,
        acceptance=list(task.spec.acceptance),
        contextSources=context_sources,
        selectedMemory=selected_memory,
        handoffs=handoffs,
        ingestContract={
            "requiredInputs": ["journal", "reviewTarget or diffPatch"],
            "expectedArtifacts": ["journal.md", "diff.patch or external review target", "test.log optional", "pending memory proposal optional"],
            "reviewTargetTypes": ["external_review", "pull_request", "branch", "commit", "diff_patch"],
            "memoryProposalPolicy": "Optional proposals enter pending review; approved MemoryEntry/MemoryVersion/Binding remain separate.",
            "durableMutationBoundary": f"{api_run_path}/assisted-ingest",
        },
        reviewContract={
            "reviewBoundary": f"{api_run_path}/reviews",
            "closeoutBoundary": f"{api_run_path}/closeout",
            "sourceIntegrationBoundary": f"{api_run_path}/source-integration",
            "requiresHumanReview": _assignment_scope(assignment, "requiresHumanReview"),
        },
        warnings=warnings,
        blockers=blockers,
    )


def build_run_assistance_bundle(index: Any, run_id: str) -> RunAssistanceBundleRecord:
    package = build_run_assistance_package(index, run_id)
    warnings = list(package.warnings)
    blockers = list(package.blockers)
    context_capsule = ""
    context_manifest: dict[str, Any] = {}

    try:
        context = build_context_capsule(
            index,
            run_id=run_id,
            task_id=package.task,
            member_id=package.member,
            assignment_id=package.assignment,
            model_profile=index.runs[run_id].spec.modelProfile,
            branch_name=index.runs[run_id].spec.branch.name if index.runs[run_id].spec.branch else None,
        )
        context_capsule = context.capsule
        context_manifest = context.manifest
    except Exception as exc:  # pragma: no cover - defensive projection fallback
        warnings.append(f"Context capsule file is unavailable: {exc}")

    files = [
        _bundle_file(
            "README.md",
            "text/markdown",
            "Human-readable handoff summary for IDE or CLI assisted execution.",
            _bundle_readme(package),
        ),
        _bundle_file(
            "context-capsule.md",
            "text/markdown",
            "Context Compiler capsule to load beside the source repository before doing work.",
            context_capsule or _fallback_capsule(package),
        ),
        _bundle_file(
            "aiteamos-handoff.json",
            "application/json",
            "Machine-readable package manifest for IDE extensions or thin CLI helpers.",
            _json_text(_handoff_manifest(package, context_manifest)),
        ),
        _bundle_file(
            "assisted-ingest-template.json",
            "application/json",
            "Template payload for returning journal, diff, review target, tests, and memory proposal through the durable ingest API.",
            _json_text(_assisted_ingest_template(package)),
        ),
        _bundle_file(
            "verification-checklist.md",
            "text/markdown",
            "Checklist for local validation before assisted ingest.",
            _verification_checklist(package),
        ),
    ]

    total_size = sum(file.sizeBytes for file in files)
    return RunAssistanceBundleRecord(
        run=package.run,
        task=package.task,
        project=package.project,
        member=package.member,
        memberKind=package.memberKind,
        assignment=package.assignment,
        generatedAt=datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
        ready=package.readyForAssistedExecution and not blockers,
        package=package,
        files=files,
        fileCount=len(files),
        totalSizeBytes=total_size,
        instructions=[
            "Open the assigned source repository and keep writes inside allowedWrites.",
            "Use context-capsule.md as the execution context; do not depend on hidden reasoning state.",
            "Return durable output only through the assisted ingest API boundary.",
            "Do not edit .aiteamos manifests directly; memory proposals must remain pending review.",
        ],
        warnings=warnings,
        blockers=blockers,
    )


def build_run_assistance_bundle_archive(index: Any, run_id: str) -> tuple[str, bytes]:
    bundle = build_run_assistance_bundle(index, run_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "aiteamos-bundle.json",
            _json_text(bundle.model_dump(mode="json", exclude_none=True)),
        )
        for file in bundle.files:
            archive.writestr(_safe_archive_path(file.path), file.content)
    return f"{_safe_archive_name(bundle.run)}-assisted-handoff.zip", buffer.getvalue()


def _bundle_file(path: str, media_type: str, purpose: str, content: str) -> RunAssistanceBundleFile:
    return RunAssistanceBundleFile(
        path=path,
        mediaType=media_type,
        purpose=purpose,
        content=content,
        sizeBytes=len(content.encode("utf-8")),
        sensitive=False,
    )


def _bundle_readme(package: RunAssistancePackageRecord) -> str:
    allowed_writes = _markdown_list(package.allowedWrites, "No assignment write scope declared.")
    read_scope = _markdown_list(package.readScope, "No assignment read scope declared.")
    responsibilities = _markdown_list(package.responsibilities, "No assignment responsibilities declared.")
    acceptance = _markdown_list(package.acceptance, "No task acceptance criteria declared.")
    entrypoints = _markdown_list([f"{item.label}: {item.command}" for item in package.entrypoints], "No entrypoints declared.")
    expected_artifacts = _markdown_list(package.ingestContract.expectedArtifacts, "No expected artifacts declared.")
    blockers = _markdown_list(package.blockers, "No blockers.")
    warnings = _markdown_list(package.warnings, "No warnings.")
    return "\n".join(
        [
            f"# Assisted Handoff Bundle: {package.run}",
            "",
            "## Identity",
            f"- Project: {package.project}",
            f"- TeamMember: {package.member} ({package.memberKind})",
            f"- Task: {package.task}",
            f"- Assignment: {package.assignment or 'none'}",
            f"- Run mode: {package.mode}",
            f"- Ready: {'yes' if package.readyForAssistedExecution else 'no'}",
            "",
            "## Work Boundary",
            "Allowed writes:",
            allowed_writes,
            "",
            "Read scope:",
            read_scope,
            "",
            "Responsibilities:",
            responsibilities,
            "",
            "Acceptance:",
            acceptance,
            "",
            "## Return Contract",
            f"- Durable ingest boundary: {package.ingestContract.durableMutationBoundary}",
            f"- Review boundary: {package.reviewContract.get('reviewBoundary', '')}",
            f"- Memory proposal policy: {package.ingestContract.memoryProposalPolicy}",
            "",
            "Expected artifacts:",
            expected_artifacts,
            "",
            "Entry points:",
            entrypoints,
            "",
            "## Guardrails",
            "- Do not edit `.aiteamos` manifests directly.",
            "- Keep memory proposals pending for review instead of writing MemoryEntry manifests.",
            "- Submit journal, review target or diff, tests, and optional memory proposal through assisted ingest.",
            "",
            "Blockers:",
            blockers,
            "",
            "Warnings:",
            warnings,
            "",
        ]
    )


def _fallback_capsule(package: RunAssistancePackageRecord) -> str:
    return "\n".join(
        [
            f"# Context Capsule Unavailable: {package.run}",
            "",
            package.summary,
            "",
            "Use README.md and aiteamos-handoff.json for the execution contract. Rebuild context-preview from the API before doing risky work.",
        ]
    )


def _handoff_manifest(package: RunAssistancePackageRecord, context_manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "aiteamos.assisted_handoff_bundle.v1",
        "run": package.run,
        "task": package.task,
        "project": package.project,
        "member": package.member,
        "memberKind": package.memberKind,
        "assignment": package.assignment,
        "route": package.ideWorkspace.get("route"),
        "ready": package.readyForAssistedExecution,
        "branch": package.branch,
        "allowedWrites": package.allowedWrites,
        "readScope": package.readScope,
        "repositories": package.ideWorkspace.get("repositories", []),
        "entrypoints": [item.model_dump(mode="json", exclude_none=True) for item in package.entrypoints],
        "ingestContract": package.ingestContract.model_dump(mode="json", exclude_none=True),
        "reviewContract": package.reviewContract,
        "contextSources": package.contextSources,
        "selectedMemory": package.selectedMemory,
        "handoffs": package.handoffs,
        "contextSourceDecisions": context_manifest.get("sourceDecisions", []),
    }


def _assisted_ingest_template(package: RunAssistancePackageRecord) -> dict[str, Any]:
    return {
        "journal": "Summarize what changed, why, and any residual risk.",
        "diffPatch": "Optional unified diff, if work produced code changes.",
        "testLog": "Optional verification output with secrets redacted.",
        "reviewTarget": {
            "type": "external_review",
            "url": "https://example.invalid/reviews/replace-me",
            "description": f"Review target for {package.run}",
        },
        "memoryProposal": {
            "title": f"Lesson from {package.run}",
            "content": "Optional lesson proposed from the assisted work. It remains pending review.",
            "kind": "procedural",
            "confidence": 0.75,
            "reviewGuidance": "Check run journal, diff or review target, and test evidence before approval.",
        },
    }


def _verification_checklist(package: RunAssistancePackageRecord) -> str:
    items = [
        "Read context-capsule.md and README.md before editing source files.",
        "Confirm planned edits stay inside allowedWrites.",
        "Run the narrow verification needed by the task acceptance criteria.",
        f"Submit results through `{package.ingestContract.durableMutationBoundary}`.",
        "Leave memory as a proposal; approval creates MemoryEntry, MemoryVersion, and bindings later.",
    ]
    return "\n".join(["# Verification Checklist", "", *[f"- {item}" for item in items], ""])


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _safe_archive_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value).strip("-")
    return safe or "aiteamos-run"


def _safe_archive_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError(f"unsafe bundle archive path {path!r}")
    return parsed.as_posix()


def _markdown_list(values: list[str], empty_text: str) -> str:
    if not values:
        return f"- {empty_text}"
    return "\n".join(f"- {value}" for value in values)


def _assignment_scope(assignment: Any | None, field: str) -> list[str]:
    if not assignment:
        return []
    return [str(item) for item in getattr(assignment.spec.scope, field, []) or []]


def _workspace_api_path(index: Any, path: str) -> str:
    return f"/workspaces/{index.workspace.object_id}{path}"


def _repository_scope(assignment: Any | None) -> list[str]:
    if not assignment:
        return []
    return [f"repository:{repo_id}" for repo_id in assignment.spec.repositories]


def _repository_records(index: Any, assignment: Any | None) -> list[dict[str, Any]]:
    if not assignment:
        return []
    records = []
    for repo_id in assignment.spec.repositories:
        repo = index.repositories.get(repo_id)
        if not repo:
            continue
        records.append(
            {
                "id": repo_id,
                "provider": repo.spec.provider,
                "localPath": repo.spec.localPath,
                "defaultBranch": repo.spec.defaultBranch,
                "workspaceRelation": repo.spec.workspaceRelation,
            }
        )
    return records


def _branch_contract(index: Any, run: Any, task_id: str, member_id: str) -> dict[str, Any]:
    if run.spec.branch:
        return run.spec.branch.model_dump(mode="json", exclude_none=True)
    default_repo = next(iter(index.repositories.values()), None)
    return {
        "name": f"aiteamos/{task_id}/{member_id}/{run.object_id}",
        "base": (default_repo.spec.defaultBranch if default_repo else None) or "develop",
        "status": "planned",
    }


def _source_ids(manifest: dict[str, Any], source_name: str, keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        return values
    items = sources.get(source_name)
    if not isinstance(items, list):
        return values
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if value:
                values.append(str(value))
                break
    return _dedupe(values)


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            result[str(key)] = item
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
