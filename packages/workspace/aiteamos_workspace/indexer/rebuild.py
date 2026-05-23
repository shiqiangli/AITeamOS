from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sqlite3
import time

from .health import (
    _insert_activity_records,
    _insert_automation_records,
    _insert_git_records,
    _insert_policy_connector_records,
    _write_index_metadata,
)
from .registry import (
    _clear_index_tables,
    _decision_audit_payloads,
    _init_schema,
    _insert_decision_audit_records,
    _insert_manifest,
    _json,
    default_db_path,
)
from ..loader import WorkspaceIndex, load_workspace, manifest_to_record


def rebuild_database_index(path: str | Path = ".aiteamos", db_path: str | Path | None = None) -> dict[str, Any]:
    index = index_workspace(path, db_path=db_path)
    target = Path(db_path).expanduser().resolve() if db_path else default_db_path(index.workspace_root)
    return {
        "kind": "DerivedDatabaseRebuild",
        "workspaceRoot": str(index.workspace_root),
        "databasePath": str(target),
        "source": str(index.workspace_root),
        "derived": True,
        "counts": index.to_summary()["counts"],
    }


def rebuild_workspace_indexes(
    path: str | Path = ".aiteamos",
    *,
    db_path: str | Path | None = None,
    vector_path: str | Path | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    database = rebuild_database_index(path, db_path=db_path)
    vector = rebuild_vector_index(path, output_path=vector_path)
    duration_seconds = round(time.perf_counter() - started, 6)
    workspace_root = Path(database["workspaceRoot"])
    return {
        "kind": "WorkspaceIndexRebuild",
        "workspaceRoot": database["workspaceRoot"],
        "source": database["source"],
        "derived": True,
        "durationSeconds": duration_seconds,
        "metadataPath": str(
            _write_index_metadata(
                workspace_root,
                duration_seconds=duration_seconds,
                database=database,
                vector=vector,
            )
        ),
        "database": database,
        "vector": vector,
        "dashboardCache": {
            "status": "not_configured",
            "reason": "Dashboard reads derived API/index state; no separate durable dashboard cache is configured.",
        },
        "counts": {
            "database": database["counts"],
            "vector": vector["counts"],
        },
    }


def index_workspace(path: str | Path = ".aiteamos", db_path: str | Path | None = None) -> WorkspaceIndex:
    index = load_workspace(path)
    target = Path(db_path).expanduser().resolve() if db_path else default_db_path(index.workspace_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    try:
        _init_schema(conn)
        _replace_index(conn, index)
        conn.commit()
    finally:
        conn.close()
    return index


def rebuild_vector_index(path: str | Path = ".aiteamos", output_path: str | Path | None = None) -> dict[str, Any]:
    from ..vector_index import rebuild_vector_index as rebuild_vector_source_index

    return rebuild_vector_source_index(path, output_path=output_path)


def _replace_index(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    _clear_index_tables(conn)
    _insert_workspace_records(conn, index)
    _insert_memory_records(conn, index)
    _insert_activity_records(conn, index)
    _insert_git_records(conn, index)
    _insert_automation_records(conn, index)
    _insert_policy_connector_records(conn, index)


def _insert_workspace_records(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    now = datetime.now(timezone.utc).isoformat()
    workspace_record = manifest_to_record(index.workspace)
    conn.execute(
        "insert into workspaces(id, name, mode, root_path, protocol_version, indexed_at, payload_json) values (?, ?, ?, ?, ?, ?, ?)",
        (
            index.workspace.object_id,
            index.workspace.metadata.name,
            index.workspace.spec.mode,
            str(index.workspace_root),
            index.workspace.spec.protocolVersion,
            now,
            _json(workspace_record),
        ),
    )
    _insert_manifest(conn, "Workspace", index.workspace.object_id, "workspace.yaml", workspace_record)

    project_record = manifest_to_record(index.project)
    conn.execute(
        "insert into projects(id, workspace_id, name, manifest_path, status, payload_json) values (?, ?, ?, ?, ?, ?)",
        (index.project.object_id, index.workspace.object_id, index.project.metadata.name, index.workspace.spec.projectRef, "active", _json(project_record)),
    )
    _insert_manifest(conn, "Project", index.project.object_id, index.workspace.spec.projectRef, project_record)

    for repo in index.repositories.values():
        record = manifest_to_record(repo)
        conn.execute(
            "insert into repositories(id, project_id, name, provider, url, local_path, default_branch, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?)",
            (repo.object_id, index.project.object_id, repo.metadata.name, repo.spec.provider, repo.spec.url, repo.spec.localPath, repo.spec.defaultBranch, _json(record)),
        )
        _insert_manifest(conn, "Repository", repo.object_id, f"repositories/{repo.object_id}.yaml", record)

    for template in index.role_templates.values():
        record = manifest_to_record(template)
        conn.execute(
            "insert into role_templates(id, name, version, manifest_path, payload_json) values (?, ?, ?, ?, ?)",
            (template.object_id, template.metadata.name, None, f"role_templates/{template.object_id}.yaml", _json(record)),
        )
        _insert_manifest(conn, "RoleTemplate", template.object_id, f"role_templates/{template.object_id}.yaml", record)

    for member in index.members.values():
        record = manifest_to_record(member)
        conn.execute(
            """
            insert into team_members(
              id, kind, display_name, status, user_binding_json, manifest_path, profile_json, about_me_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                member.object_id,
                member.spec.kind,
                member.spec.profile.displayName,
                member.spec.profile.status,
                _json(member.spec.userBinding.model_dump(mode="json")) if member.spec.userBinding else None,
                f"members/{member.object_id}.yaml",
                _json(member.spec.profile.model_dump(mode="json")),
                _json(member.spec.aboutMe.model_dump(mode="json")),
                _json(record),
            ),
        )
        _insert_manifest(conn, "TeamMember", member.object_id, f"members/{member.object_id}.yaml", record)

    for product_user in index.product_users.values():
        record = manifest_to_record(product_user)
        _insert_manifest(conn, "ProductUser", product_user.object_id, f"product_users/{product_user.object_id}.yaml", record)

    for assignment in index.assignments.values():
        record = manifest_to_record(assignment)
        conn.execute(
            """
            insert into member_assignments(
              id, member_id, project_id, role_template_id, status, modules_json, features_json,
              eval_suite_requirements_json, scope_json, manifest_path, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assignment.object_id,
                assignment.spec.member,
                assignment.spec.project,
                assignment.spec.roleTemplate,
                assignment.spec.status,
                _json(assignment.spec.modules),
                _json(assignment.spec.features),
                _json([requirement.model_dump(mode="json") for requirement in assignment.spec.evalSuiteRequirements]),
                _json(assignment.spec.scope.model_dump(mode="json")),
                f"assignments/{assignment.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "Assignment", assignment.object_id, f"assignments/{assignment.object_id}.yaml", record)

    for task in index.tasks.values():
        record = manifest_to_record(task)
        conn.execute(
            "insert into tasks(id, project_id, assigned_member_id, assignment_id, title, status, priority, manifest_path, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.object_id,
                task.spec.project,
                task.spec.assignedMember,
                task.spec.assignment,
                task.spec.title,
                task.spec.status,
                task.spec.priority,
                f"tasks/{task.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "Task", task.object_id, f"tasks/{task.object_id}.yaml", record)

    for task_plan in index.task_plans.values():
        record = manifest_to_record(task_plan)
        conn.execute(
            "insert into task_plans(id, project_id, source_task_id, created_by_member_id, status, subtask_count, manifest_path, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_plan.object_id,
                task_plan.spec.project,
                task_plan.spec.sourceTask,
                task_plan.spec.createdByMember,
                task_plan.spec.status,
                len(task_plan.spec.subtasks),
                f"task_plans/{task_plan.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "TaskPlan", task_plan.object_id, f"task_plans/{task_plan.object_id}.yaml", record)

    for run in index.runs.values():
        record = manifest_to_record(run)
        conn.execute(
            "insert into runs(id, task_id, member_id, assignment_id, project_id, status, mode, started_at, finished_at, manifest_path, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.object_id,
                run.spec.task,
                run.spec.member,
                run.spec.assignment,
                run.spec.project,
                run.spec.status,
                run.spec.mode,
                run.metadata.createdAt,
                None,
                f"runs/{run.object_id}/run.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "Run", run.object_id, f"runs/{run.object_id}/run.yaml", record)

    for review in index.reviews.values():
        record = manifest_to_record(review)
        conn.execute(
            "insert into reviews(id, run_id, task_id, project_id, reviewer, reviewer_member_id, reviewer_kind, verdict, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                review.object_id,
                review.spec.run,
                review.spec.task,
                review.spec.project,
                review.spec.reviewer,
                review.spec.reviewerMember,
                review.spec.reviewerKind,
                review.spec.verdict,
                _json(_decision_audit_payloads(review.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "Review", review.object_id, f"reviews/{review.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "Review", review.object_id, review.spec.decisionAudit)


def _insert_memory_records(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    for store in index.memory_stores.values():
        record = manifest_to_record(store)
        conn.execute(
            "insert into memory_stores(id, store_type, owner_project_id, owner_member_id, owner_team_id, visibility, lifecycle, manifest_path, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                store.object_id,
                store.spec.storeType,
                store.spec.ownerProject,
                store.spec.ownerMember,
                store.spec.ownerTeam,
                store.spec.visibility,
                store.spec.lifecycle,
                f"memory/stores/{store.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "MemoryStore", store.object_id, f"memory/stores/{store.object_id}.yaml", record)

    for entry in index.memory_entries.values():
        record = manifest_to_record(entry)
        conn.execute(
            """
            insert into memory_entries(
              id, store_id, path, kind, scope, lifecycle, confidence, last_verified_at, sensitivity,
              visibility, title, embedding_json, manifest_path, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.object_id,
                entry.spec.store,
                entry.spec.path,
                entry.spec.kind,
                entry.spec.scope,
                entry.spec.lifecycle,
                entry.spec.confidence,
                entry.spec.lastVerifiedAt,
                entry.spec.sensitivity,
                entry.spec.visibility,
                entry.spec.title,
                _json(entry.spec.embedding),
                f"memory/entries/{entry.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "MemoryEntry", entry.object_id, f"memory/entries/{entry.object_id}.yaml", record)

    for version in index.memory_versions.values():
        record = manifest_to_record(version)
        conn.execute(
            "insert into memory_versions(id, entry_id, store_id, version, operation, content_sha256, created_at, redacted, manifest_path, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version.object_id,
                version.spec.entry,
                version.spec.store,
                version.spec.version,
                version.spec.operation,
                version.spec.contentSha256,
                version.spec.createdAt,
                1 if version.spec.redacted else 0,
                f"memory/versions/{version.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "MemoryVersion", version.object_id, f"memory/versions/{version.object_id}.yaml", record)

    for binding in index.memory_bindings.values():
        record = manifest_to_record(binding)
        conn.execute(
            "insert into memory_bindings(id, store_id, entry_id, target_type, target_id, access_json, status, manifest_path, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                binding.object_id,
                binding.spec.store,
                binding.spec.entry,
                binding.spec.targetType,
                binding.spec.targetId,
                _json(binding.spec.access),
                binding.spec.status,
                f"memory/bindings/{binding.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "MemoryBinding", binding.object_id, f"memory/bindings/{binding.object_id}.yaml", record)

    for grant in index.memory_grants.values():
        record = manifest_to_record(grant)
        conn.execute(
            "insert into memory_grants(id, grantee_member_id, grantor_member_id, task_id, run_id, expires_at, status, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?)",
            (grant.object_id, grant.spec.granteeMember, grant.spec.grantorMember, grant.spec.task, grant.spec.run, grant.spec.expiresAt, grant.spec.status, _json(record)),
        )
        _insert_manifest(conn, "MemoryGrant", grant.object_id, f"memory/grants/{grant.object_id}.yaml", record)

    for proposal in index.memory_proposals.values():
        record = manifest_to_record(proposal)
        conn.execute(
            "insert into memory_proposals(id, project_id, member_id, assignment_id, store_id, source_run_id, status, title, proposed_path, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                proposal.object_id,
                proposal.spec.project,
                proposal.spec.member,
                proposal.spec.assignment,
                proposal.spec.store,
                proposal.spec.sourceRun,
                proposal.spec.status,
                proposal.spec.title,
                proposal.spec.entryPath,
                _json(record),
            ),
        )
        _insert_manifest(conn, "MemoryProposal", proposal.object_id, f"memory/proposals/{proposal.object_id}.yaml", record)

