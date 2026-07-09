"""Release hygiene summary for source, generated artifacts, and local state."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

RELEASE_HYGIENE_CONTRACT_VERSION = "aiteamos_release_hygiene.v1"


class ReleaseHygieneItem(BaseModel):
    path: str
    status_code: str
    category: str
    review_action: str
    detail: str


class ReleaseHygieneSummary(BaseModel):
    total_changed: int = 0
    source_count: int = 0
    generated_artifact_count: int = 0
    local_projection_count: int = 0
    test_output_count: int = 0
    unknown_count: int = 0
    untracked_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0


class ReleaseHygieneResponse(BaseModel):
    contract_version: str = RELEASE_HYGIENE_CONTRACT_VERSION
    status: str
    detail: str
    git_root: str = ""
    summary: ReleaseHygieneSummary = Field(default_factory=ReleaseHygieneSummary)
    review_commands: list[str] = Field(default_factory=list)
    boundary_notes: list[str] = Field(default_factory=list)
    category_samples: dict[str, list[ReleaseHygieneItem]] = Field(default_factory=dict)
    items: list[ReleaseHygieneItem] = Field(default_factory=list)


def release_hygiene_report(
    *,
    workspace_dir: Path | None = None,
    limit: int = 24,
) -> ReleaseHygieneResponse:
    root = _project_root(workspace_dir)
    if not _is_git_worktree(root):
        return ReleaseHygieneResponse(
            status="blocked",
            detail="Release hygiene requires a git worktree so source and generated artifacts can be separated.",
            git_root=str(root),
            review_commands=[],
            boundary_notes=_boundary_notes(),
            category_samples={},
        )

    result = _git_status(root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git status failed").strip()
        return ReleaseHygieneResponse(
            status="blocked",
            detail=detail,
            git_root=str(root),
            review_commands=_review_commands(),
            boundary_notes=_boundary_notes(),
            category_samples={},
        )

    all_items = [_item_from_status(line) for line in result.stdout.splitlines() if line.strip()]
    all_items = [item for item in all_items if item is not None]
    summary = _summary(all_items)
    if summary.unknown_count:
        status = "blocked"
        detail = "Some changed paths are outside the known source/artifact/local-state boundaries."
    elif summary.total_changed:
        status = "warning"
        detail = "Worktree has changed files; review source changes separately from generated artifacts and local provider projections."
    else:
        status = "ready"
        detail = "Git worktree is clean."
    return ReleaseHygieneResponse(
        status=status,
        detail=detail,
        git_root=str(root),
        summary=summary,
        review_commands=_review_commands(),
        boundary_notes=_boundary_notes(),
        category_samples=_category_samples(all_items),
        items=all_items[: max(0, limit)],
    )


def _project_root(workspace_dir: Path | None) -> Path:
    override = os.environ.get("AITEAMOS_RELEASE_HYGIENE_GIT_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    raw = workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).expanduser()
    root = raw.resolve()
    return root.parent if root.name == ".aiteamos" else root


def _is_git_worktree(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_status(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _item_from_status(line: str) -> ReleaseHygieneItem | None:
    if len(line) < 4:
        return None
    status_code = line[:2]
    raw_path = line[3:].strip()
    path = _normalize_status_path(raw_path)
    if not path:
        return None
    category = _category(path)
    return ReleaseHygieneItem(
        path=path,
        status_code=status_code,
        category=category,
        review_action=_review_action(category),
        detail=_detail(category),
    )


def _normalize_status_path(value: str) -> str:
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value.strip()


def _category(path: str) -> str:
    if path.startswith(".aiteamos/artifacts/"):
        return "generated_artifact"
    if path.startswith(".aiteamos/"):
        return "local_projection"
    if (
        path.startswith("apps/dashboard/dist/")
        or path.startswith("apps/dashboard/coverage/")
        or path.startswith(".pytest_cache/")
        or path.startswith("htmlcov/")
        or path.endswith(".pyc")
    ):
        return "test_output"
    if path == "plan_v8_progress.md":
        return "generated_artifact"
    source_roots = (
        ".github/",
        "apps/",
        "docker/",
        "docs/",
        "scripts/",
        "services/",
        "tests/",
    )
    source_files = (
        ".gitignore",
        "README.md",
        "langgraph.json",
        "package.json",
        "package-lock.json",
        "plan_v3.md",
        "plan_v4.md",
        "plan_v5.md",
        "plan_v6.md",
        "plan_v7.md",
        "plan_v8.md",
        "pyproject.toml",
    )
    if path.startswith(source_roots) or path in source_files:
        return "source"
    return "unknown"


def _review_action(category: str) -> str:
    return {
        "source": "review_in_code_diff",
        "generated_artifact": "retain_as_evidence_or_archive",
        "local_projection": "do_not_treat_as_source_without_explicit_decision",
        "test_output": "ignore_or_clean_before_release_review",
        "unknown": "classify_before_release_review",
    }.get(category, "classify_before_release_review")


def _detail(category: str) -> str:
    return {
        "source": "Source/config/test/docs change that belongs in normal code review.",
        "generated_artifact": "Generated evidence or progress artifact; review as proof, not as product source.",
        "local_projection": "Local provider projection or runtime state; preserve only when intentionally promoted.",
        "test_output": "Build/test output that should not drive product behavior.",
        "unknown": "Path is outside known release hygiene boundaries.",
    }.get(category, "Path is outside known release hygiene boundaries.")


def _summary(items: list[ReleaseHygieneItem]) -> ReleaseHygieneSummary:
    return ReleaseHygieneSummary(
        total_changed=len(items),
        source_count=sum(1 for item in items if item.category == "source"),
        generated_artifact_count=sum(1 for item in items if item.category == "generated_artifact"),
        local_projection_count=sum(1 for item in items if item.category == "local_projection"),
        test_output_count=sum(1 for item in items if item.category == "test_output"),
        unknown_count=sum(1 for item in items if item.category == "unknown"),
        untracked_count=sum(1 for item in items if "?" in item.status_code),
        modified_count=sum(1 for item in items if "M" in item.status_code),
        deleted_count=sum(1 for item in items if "D" in item.status_code),
    )


def _category_samples(items: list[ReleaseHygieneItem], *, limit: int = 4) -> dict[str, list[ReleaseHygieneItem]]:
    categories = ("source", "generated_artifact", "local_projection", "test_output", "unknown")
    samples: dict[str, list[ReleaseHygieneItem]] = {category: [] for category in categories}
    for item in sorted(items, key=_sample_sort_key):
        if item.category not in samples or len(samples[item.category]) >= limit:
            continue
        samples[item.category].append(item)
    return {category: values for category, values in samples.items() if values}


def _sample_sort_key(item: ReleaseHygieneItem) -> tuple[int, int, str]:
    if item.category == "generated_artifact":
        path = item.path
        if path.startswith(".aiteamos/artifacts/plan_v8/track-") and path.endswith(".json"):
            return (0, path.count("/"), path)
        if path == "plan_v8_progress.md":
            return (1, 0, path)
        return (2, path.count("/"), path)
    return (0, item.path.count("/"), item.path)


def _review_commands() -> list[str]:
    return [
        "git status --short",
        "git diff --stat",
        "python scripts/plan_v8_artifact_summary.py --workspace-dir .",
    ]


def _boundary_notes() -> list[str]:
    return [
        "Source files are reviewed as implementation changes.",
        "Generated artifacts under .aiteamos/artifacts are evidence, not durable product truth.",
        "Local provider projections under .aiteamos are runtime state unless explicitly promoted.",
        "plan_v8.md is the stable baseline; progress belongs in plan_v8_progress.md.",
    ]
