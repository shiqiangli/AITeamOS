from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3


def default_db_path(workspace_root: Path) -> Path:
    return workspace_root / "indexes" / "aiteamos.sqlite"


def default_vector_index_path(workspace_root: Path) -> Path:
    return workspace_root / "indexes" / "vector_sources.json"


def default_vector_chunks_path(workspace_root: Path) -> Path:
    return workspace_root / "indexes" / "vector_chunks.json"


def default_index_metadata_path(workspace_root: Path) -> Path:
    return workspace_root / "indexes" / "index_metadata.json"


INDEX_TABLES = [
    "manifests",
    "workspaces",
    "projects",
    "repositories",
    "role_templates",
    "team_members",
    "member_assignments",
    "tasks",
    "task_plans",
    "runs",
    "reviews",
    "memory_stores",
    "memory_entries",
    "memory_versions",
    "memory_bindings",
    "memory_grants",
    "memory_proposals",
    "learning_extractions",
    "eval_results",
    "team_retrospectives",
    "member_activity",
    "git_activity",
    "git_activity_import_receipts",
    "git_activity_correlation_reviews",
    "automations",
    "automation_runs",
    "automation_trigger_events",
    "automation_provider_deliveries",
    "automation_scheduler_leases",
    "automation_approvals",
    "approval_workflows",
    "permissions",
    "permission_requests",
    "permission_grants",
    "skills",
    "connectors",
    "connector_health_checks",
    "decision_audit",
    "model_profiles",
    "budget_policies",
    "project_member_views",
]


def _clear_index_tables(conn: sqlite3.Connection) -> None:
    for table in INDEX_TABLES:
        conn.execute(f"delete from {table}")


def _init_schema(conn: sqlite3.Connection) -> None:
    # The SQLite file is a derived cache; rebuilds are allowed to replace schema
    # shape and discard stale cache tables.
    conn.executescript(
        """
        drop table if exists project_member_views;
        drop table if exists connector_health_checks;
        drop table if exists connectors;
        drop table if exists skills;
        drop table if exists decision_audit;
        drop table if exists permission_grants;
        drop table if exists permission_requests;
        drop table if exists permissions;
        drop table if exists budget_policies;
        drop table if exists model_profiles;
        drop table if exists automation_approvals;
        drop table if exists approval_workflows;
        drop table if exists automation_scheduler_leases;
        drop table if exists automation_provider_deliveries;
        drop table if exists automation_trigger_events;
        drop table if exists automation_runs;
        drop table if exists automations;
        drop table if exists git_activity_correlation_reviews;
        drop table if exists git_activity_import_receipts;
        drop table if exists git_activity;
        drop table if exists member_activity;
        drop table if exists team_retrospectives;
        drop table if exists eval_results;
        drop table if exists learning_extractions;
        drop table if exists memory_proposals;
        drop table if exists memory_grants;
        drop table if exists memory_bindings;
        drop table if exists memory_versions;
        drop table if exists memory_entries;
        drop table if exists memory_stores;
        drop table if exists reviews;
        drop table if exists runs;
        drop table if exists task_plans;
        drop table if exists tasks;
        drop table if exists member_assignments;
        drop table if exists team_members;
        drop table if exists role_templates;
        drop table if exists repositories;
        drop table if exists projects;
        drop table if exists workspaces;
        drop table if exists manifests;
        """
    )
    conn.executescript(
        """
        create table if not exists manifests (
          kind text not null,
          id text not null,
          manifest_path text,
          payload_json text not null,
          primary key(kind, id)
        );
        create table if not exists workspaces (
          id text primary key,
          name text,
          mode text,
          root_path text,
          protocol_version text,
          indexed_at text,
          payload_json text not null
        );
        create table if not exists projects (
          id text primary key,
          workspace_id text,
          name text,
          manifest_path text,
          status text,
          payload_json text not null
        );
        create table if not exists repositories (
          id text primary key,
          project_id text,
          name text,
          provider text,
          url text,
          local_path text,
          default_branch text,
          payload_json text not null
        );
        create table if not exists role_templates (
          id text primary key,
          name text,
          version text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists team_members (
          id text primary key,
          kind text,
          display_name text,
          status text,
          user_binding_json text,
          manifest_path text,
          profile_json text,
          about_me_json text,
          payload_json text not null
        );
        create table if not exists member_assignments (
          id text primary key,
          member_id text,
          project_id text,
          role_template_id text,
          status text,
          modules_json text,
          features_json text,
          eval_suite_requirements_json text,
          scope_json text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists tasks (
          id text primary key,
          project_id text,
          assigned_member_id text,
          assignment_id text,
          title text,
          status text,
          priority text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists task_plans (
          id text primary key,
          project_id text,
          source_task_id text,
          created_by_member_id text,
          status text,
          subtask_count integer,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists runs (
          id text primary key,
          task_id text,
          member_id text,
          assignment_id text,
          project_id text,
          status text,
          mode text,
          started_at text,
          finished_at text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists reviews (
          id text primary key,
          run_id text,
          task_id text,
          project_id text,
          reviewer text,
          reviewer_member_id text,
          reviewer_kind text,
          verdict text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists memory_stores (
          id text primary key,
          store_type text,
          owner_project_id text,
          owner_member_id text,
          owner_team_id text,
          visibility text,
          lifecycle text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists memory_entries (
          id text primary key,
          store_id text,
          path text,
          kind text,
          scope text,
          lifecycle text,
          confidence real,
          last_verified_at text,
          sensitivity text,
          visibility text,
          title text,
          embedding_json text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists memory_versions (
          id text primary key,
          entry_id text,
          store_id text,
          version integer,
          operation text,
          content_sha256 text,
          created_at text,
          redacted integer,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists memory_bindings (
          id text primary key,
          store_id text,
          entry_id text,
          target_type text,
          target_id text,
          access_json text,
          status text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists memory_grants (
          id text primary key,
          grantee_member_id text,
          grantor_member_id text,
          task_id text,
          run_id text,
          expires_at text,
          status text,
          payload_json text not null
        );
        create table if not exists memory_proposals (
          id text primary key,
          project_id text,
          member_id text,
          assignment_id text,
          store_id text,
          source_run_id text,
          status text,
          title text,
          proposed_path text,
          payload_json text not null
        );
        create table if not exists learning_extractions (
          id text primary key,
          run_id text,
          project_id text,
          member_id text,
          assignment_id text,
          extracted_at text,
          dedupe_key text,
          extractor_id text,
          extractor_version text,
          proposal_count integer,
          proposal_kinds_json text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists eval_results (
          id text primary key,
          eval_suite_id text,
          project_id text,
          task_id text,
          run_id text,
          member_id text,
          assignment_id text,
          status text,
          pass_rate real,
          evaluated_at text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists team_retrospectives (
          id text primary key,
          project_id text,
          facilitator_member_id text,
          status text,
          proposed_memory_id text,
          source_task_plan_id text,
          source_runs_json text,
          source_tasks_json text,
          source_messages_json text,
          source_handoffs_json text,
          payload_json text not null
        );
        create table if not exists member_activity (
          id text primary key,
          member_id text,
          project_id text,
          assignment_id text,
          task_id text,
          run_id text,
          activity_type text,
          source_type text,
          contribution_kind text,
          source_id text,
          occurred_at text,
          visibility text,
          payload_json text not null
        );
        create table if not exists git_activity (
          id text primary key,
          member_id text,
          project_id text,
          repository_id text,
          assignment_id text,
          activity_type text,
          provider text,
          external_id text,
          occurred_at text,
          visibility text,
          lifecycle text,
          retained_until text,
          archived_at text,
          redacted_at text,
          redaction_policy text,
          export_policy text,
          refs_json text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists git_activity_import_receipts (
          id text primary key,
          project_id text,
          repository_id text,
          provider text,
          connector_id text,
          source_type text,
          status text,
          dedupe_key text,
          payload_digest text,
          redaction_policy text,
          import_policy text,
          payload_retained integer,
          retained_until text,
          received_at text,
          reviewed_by_member_id text,
          imported_activities_json text,
          refs_json text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists git_activity_correlation_reviews (
          id text primary key,
          project_id text,
          repository_id text,
          provider text,
          connector_id text,
          correlation_key text,
          decision text,
          reviewer_member_id text,
          reviewer_member_kind text,
          reviewed_at text,
          receipts_json text,
          imported_activities_json text,
          risk_flags_json text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists automations (
          id text primary key,
          owner_member_id text,
          service_member_id text,
          project_id text,
          target_type text,
          status text,
          dry_run integer,
          payload_json text not null
        );
        create table if not exists automation_runs (
          id text primary key,
          automation_id text,
          project_id text,
          owner_member_id text,
          service_member_id text,
          target_type text,
          trigger_type text,
          status text,
          dry_run integer,
          approvals_json text,
          created_task_id text,
          created_run_id text,
          created_task_plan_id text,
          created_message_id text,
          started_at text,
          finished_at text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists automation_trigger_events (
          id text primary key,
          automation_id text,
          project_id text,
          trigger_type text,
          source text,
          actor_member_id text,
          dedupe_key text,
          dry_run integer,
          status text,
          automation_run_id text,
          received_at text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists automation_provider_deliveries (
          id text primary key,
          automation_id text,
          project_id text,
          connector_id text,
          provider text,
          event_type text,
          trigger_type text,
          delivery_id text,
          dedupe_key text,
          payload_digest text,
          replay_status text,
          admission_status text,
          lifecycle text,
          retained_until text,
          archived_at text,
          attempt_count integer,
          automation_trigger_event_id text,
          automation_run_id text,
          first_seen_at text,
          last_seen_at text,
          received_at text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists automation_scheduler_leases (
          id text primary key,
          automation_id text,
          project_id text,
          scheduler_id text,
          tick_key text,
          status text,
          automation_trigger_event_id text,
          automation_run_id text,
          lease_acquired_at text,
          lease_expires_at text,
          heartbeat_at text,
          dedupe_key text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists automation_approvals (
          id text primary key,
          automation_run_id text,
          automation_id text,
          project_id text,
          reviewer_member_id text,
          reviewer_member_kind text,
          decision text,
          approval_workflow_id text,
          approval_gates_json text,
          decided_at text,
          expires_at text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists approval_workflows (
          id text primary key,
          project_id text,
          subject_kind text,
          subject_ref text,
          status text,
          current_stage text,
          stages_json text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists permissions (
          id text primary key,
          scope_json text,
          default_mode text,
          allow_json text,
          ask_json text,
          deny_json text,
          payload_json text not null
        );
        create table if not exists permission_requests (
          id text primary key,
          project_id text,
          member_id text,
          assignment_id text,
          status text,
          action_json text,
          reviewer_member_id text,
          approval_workflow_id text,
          grant_id text,
          expires_at text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists permission_grants (
          id text primary key,
          project_id text,
          member_id text,
          assignment_id text,
          status text,
          action_json text,
          source_request_id text,
          approved_by_member_id text,
          expires_at text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists decision_audit (
          id text primary key,
          resource_kind text not null,
          resource_id text not null,
          sequence integer not null,
          decision_kind text,
          decision text,
          actor_member_id text,
          actor_member_kind text,
          authority text,
          decided_at text,
          requires_human_review integer,
          risk_level text,
          risk_recommended_decision text,
          risk_requires_human_review integer,
          payload_json text not null
        );
        create table if not exists skills (
          id text primary key,
          owner_member_id text,
          lifecycle text,
          capabilities_json text,
          required_permissions_json text,
          payload_json text not null
        );
        create table if not exists connectors (
          id text primary key,
          provider text,
          connector_type text,
          owner_member_id text,
          payload_json text not null
        );
        create table if not exists connector_health_checks (
          id text primary key,
          connector_id text,
          provider text,
          connector_type text,
          project_id text,
          status text,
          readiness text,
          token_status text,
          installation_status text,
          lifecycle text,
          retained_until text,
          archived_at text,
          checked_at text,
          decision_audit_json text,
          payload_json text not null
        );
        create table if not exists model_profiles (
          id text primary key,
          provider text,
          model text,
          gateway text,
          manifest_path text,
          pricing_json text,
          default_members_json text,
          default_assignments_json text,
          payload_json text not null
        );
        create table if not exists budget_policies (
          id text primary key,
          project_id text,
          member_id text,
          assignment_id text,
          task_id text,
          limits_json text,
          rate_limit_json text,
          fallback_json text,
          enforcement_json text,
          manifest_path text,
          payload_json text not null
        );
        create table if not exists project_member_views (
          project_id text,
          member_id text,
          assignment_count integer,
          task_count integer,
          run_count integer,
          active_task_count integer,
          latest_activity_at text,
          primary key(project_id, member_id)
        );
        """
    )




def _insert_manifest(conn: sqlite3.Connection, kind: str, object_id: str, manifest_path: str, record: dict[str, Any]) -> None:
    conn.execute(
        "insert into manifests(kind, id, manifest_path, payload_json) values (?, ?, ?, ?)",
        (kind, object_id, manifest_path, _json(record)),
    )


def _insert_decision_audit_records(conn: sqlite3.Connection, resource_kind: str, resource_id: str, records: list[Any]) -> None:
    for index, record in enumerate(_decision_audit_payloads(records), start=1):
        conn.execute(
            """
            insert into decision_audit(
              id, resource_kind, resource_id, sequence, decision_kind, decision,
              actor_member_id, actor_member_kind, authority, decided_at, requires_human_review,
              risk_level, risk_recommended_decision, risk_requires_human_review, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{resource_kind}:{resource_id}:{index}",
                resource_kind,
                resource_id,
                index,
                record.get("decisionKind"),
                record.get("decision"),
                record.get("actorMember"),
                record.get("actorMemberKind"),
                record.get("authority"),
                record.get("decidedAt"),
                1 if record.get("requiresHumanReview") else 0,
                (record.get("riskAssessment") or {}).get("riskLevel"),
                (record.get("riskAssessment") or {}).get("recommendedDecision"),
                1 if (record.get("riskAssessment") or {}).get("requiresHumanReview") else 0,
                _json(record),
            ),
        )


def _decision_audit_payloads(records: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for record in records:
        if hasattr(record, "model_dump"):
            payloads.append(record.model_dump(mode="json", exclude_none=True))
        elif isinstance(record, dict):
            payloads.append(dict(record))
    return payloads


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
