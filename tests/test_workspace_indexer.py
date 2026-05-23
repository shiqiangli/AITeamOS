from __future__ import annotations

from pathlib import Path
import json
import shutil
import sqlite3
import tempfile
import unittest

from aiteamos_workspace import dry_run_automation, index_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class WorkspaceIndexerTest(unittest.TestCase):
    def test_indexer_populates_v2_member_memory_and_automation_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            automation_run = dry_run_automation(workspace, "memory-health-dry-run", actor_member="manager")
            db_path = Path(temp_dir) / "aiteamos.sqlite"

            index = index_workspace(workspace, db_path=db_path)

            self.assertIn("backend-digital", index.members)
            self.assertIn("aiteamos-backend-runtime", index.assignments)
            self.assertIn("team-member-baseline", index.memory_entries)
            self.assertIn(automation_run.object_id, index.automation_runs)

            conn = sqlite3.connect(db_path)
            try:
                tables = _tables(conn)
                for table in [
                    "workspaces",
                    "projects",
                    "repositories",
                    "role_templates",
                    "team_members",
                    "member_assignments",
                    "tasks",
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
                    "member_activity",
                    "git_activity",
                    "git_activity_import_receipts",
                    "git_activity_correlation_reviews",
                    "automations",
                    "automation_runs",
                    "automation_provider_deliveries",
                    "permissions",
                    "permission_requests",
                    "permission_grants",
                    "decision_audit",
                    "skills",
                    "connectors",
                    "model_profiles",
                    "budget_policies",
                    "project_member_views",
                    "manifests",
                ]:
                    self.assertIn(table, tables)
                for removed_table in ["project_roles", "memory_items", "mistake_items"]:
                    self.assertNotIn(removed_table, tables)

                member = conn.execute(
                    "select kind, display_name, status from team_members where id = 'backend-digital'"
                ).fetchone()
                self.assertEqual(member, ("digital", "Backend Digital Engineer", "active"))

                assignment = conn.execute(
                    """
                    select member_id, project_id, role_template_id, status, eval_suite_requirements_json
                    from member_assignments
                    where id = 'aiteamos-backend-runtime'
                    """
                ).fetchone()
                self.assertEqual(assignment[:4], ("backend-digital", "aiteamos", "backend-engineer", "active"))
                requirements = json.loads(assignment[4])
                self.assertEqual(requirements[0]["evalSuite"], "aiteamos-eval-suite-schema-contract")
                self.assertEqual(requirements[0]["paths"], ["packages/schema/**", "packages/workspace/**"])

                task_row = conn.execute(
                    """
                    select assigned_member_id, assignment_id
                    from tasks
                    where assigned_member_id = 'backend-digital'
                    limit 1
                    """
                ).fetchone()
                self.assertEqual(task_row, ("backend-digital", "aiteamos-backend-runtime"))

                run_row = conn.execute(
                    """
                    select member_id, assignment_id, project_id
                    from runs
                    where member_id = 'backend-digital'
                    limit 1
                    """
                ).fetchone()
                self.assertEqual(run_row, ("backend-digital", "aiteamos-backend-runtime", "aiteamos"))

                memory_entry = conn.execute(
                    """
                    select store_id, kind, scope, lifecycle, visibility, title
                    from memory_entries
                    where id = 'team-member-baseline'
                    """
                ).fetchone()
                self.assertEqual(
                    memory_entry,
                    (
                        "aiteamos-project-memory",
                        "decision",
                        "project",
                        "active",
                        "project",
                        "TeamMember is the durable identity",
                    ),
                )

                member_activity = conn.execute(
                    """
                    select member_id, project_id, assignment_id, activity_type, source_type, contribution_kind
                    from member_activity
                    where id = 'ACT-20260521T090000000'
                    """
                ).fetchone()
                self.assertEqual(
                    member_activity,
                    ("backend-digital", "aiteamos", "aiteamos-backend-runtime", "implementation", "run", "authored-work"),
                )

                git_activity = conn.execute(
                    """
                    select member_id, project_id, repository_id, assignment_id, activity_type, provider
                    from git_activity
                    where id = 'GIT-20260521T090500000'
                    """
                ).fetchone()
                self.assertEqual(
                    git_activity,
                    ("backend-digital", "aiteamos", "aiteamos", "aiteamos-backend-runtime", "branch", "local"),
                )

                git_import = conn.execute(
                    """
                    select project_id, repository_id, provider, source_type, status, redaction_policy,
                           import_policy, payload_retained, reviewed_by_member_id, imported_activities_json
                    from git_activity_import_receipts
                    where id = 'GITIMP-20260521T093000000'
                    """
                ).fetchone()
                self.assertEqual(git_import[:9], ("aiteamos", "aiteamos", "local", "local-scan", "imported", "metadata-only", "reviewed-import", 0, "frontend-human"))
                self.assertEqual(json.loads(git_import[9]), ["GIT-20260521T090500000"])

                binding_targets = {
                    row[0]
                    for row in conn.execute(
                        "select target_id from memory_bindings where store_id = 'aiteamos-project-memory'"
                    ).fetchall()
                }
                self.assertIn("aiteamos-backend-runtime", binding_targets)

                grant = conn.execute(
                    """
                    select grantee_member_id, grantor_member_id, status
                    from memory_grants
                    where id = 'grant-team-member-baseline-to-current-task'
                    """
                ).fetchone()
                self.assertEqual(grant, ("backend-digital", "architect", "active"))

                automation = conn.execute(
                    "select owner_member_id, service_member_id, target_type, dry_run from automations where id = 'memory-health-dry-run'"
                ).fetchone()
                self.assertEqual(automation, ("manager", "memory-service", "memory_health", 1))

                automation_run_row = conn.execute(
                    """
                    select automation_id, owner_member_id, service_member_id, trigger_type, status, dry_run
                    from automation_runs
                    where id = ?
                    """,
                    (automation_run.object_id,),
                ).fetchone()
                self.assertEqual(automation_run_row, ("memory-health-dry-run", "manager", "memory-service", "manual", "dry-run", 1))

                automation_audit = conn.execute(
                    """
                    select decision_kind, actor_member_id, actor_member_kind, risk_level, risk_recommended_decision
                    from decision_audit
                    where resource_kind = 'AutomationRun' and resource_id = ?
                    """,
                    (automation_run.object_id,),
                ).fetchone()
                self.assertEqual(automation_audit, ("service_policy_decision", "memory-service", "service", "low", "allow"))

                model_profile = conn.execute(
                    """
                    select provider, model, gateway
                    from model_profiles
                    where id = 'openai-gpt-5.5-xhigh'
                    """
                ).fetchone()
                self.assertEqual(model_profile, ("openai", "gpt-5.5", "openai-responses"))

                budget_policy = conn.execute(
                    """
                    select project_id, member_id, assignment_id, task_id, limits_json
                    from budget_policies
                    where id = 'default-budget'
                    """
                ).fetchone()
                self.assertEqual(budget_policy[:4], ("aiteamos", None, None, None))
                self.assertEqual(json.loads(budget_policy[4])["maxRetriesPerRun"], 2)

                eval_result = conn.execute(
                    """
                    select eval_suite_id, project_id, assignment_id, status, pass_rate
                    from eval_results
                    where id = 'ERES-20260522T204421556'
                    """
                ).fetchone()
                self.assertEqual(eval_result, ("aiteamos-eval-suite-schema-contract", "aiteamos", "aiteamos-backend-runtime", "pass", 1.0))

                projection = conn.execute(
                    """
                    select assignment_count, task_count, run_count, active_task_count
                    from project_member_views
                    where project_id = 'aiteamos' and member_id = 'backend-digital'
                    """
                ).fetchone()
                self.assertIsNotNone(projection)
                self.assertGreaterEqual(projection[0], 1)
                self.assertGreaterEqual(projection[1], 1)
                self.assertGreaterEqual(projection[2], 1)

                manifest_kinds = {
                    row[0]
                    for row in conn.execute(
                        """
                        select kind
                        from manifests
                        where id in (
                          'backend-digital',
                          'aiteamos-backend-runtime',
                          'team-member-baseline',
                          'grant-team-member-baseline-to-current-task',
                          'ACT-20260521T090000000',
                          'GIT-20260521T090500000',
                          'GITIMP-20260521T093000000',
                          ?
                        )
                        """,
                        (automation_run.object_id,),
                    ).fetchall()
                }
                self.assertEqual(manifest_kinds, {"TeamMember", "Assignment", "MemoryEntry", "MemoryGrant", "MemberActivity", "GitActivity", "GitActivityImportReceipt", "AutomationRun"})
            finally:
                conn.close()

    def test_index_rebuild_removes_deleted_v2_manifest_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            automation_run = dry_run_automation(workspace, "memory-health-dry-run", actor_member="manager")
            db_path = Path(temp_dir) / "aiteamos.sqlite"

            index_workspace(workspace, db_path=db_path)
            (workspace / "automations" / "runs" / f"{automation_run.object_id}.yaml").unlink()
            index_workspace(workspace, db_path=db_path)

            conn = sqlite3.connect(db_path)
            try:
                count = conn.execute("select count(*) from automation_runs where id = ?", (automation_run.object_id,)).fetchone()[0]
                self.assertEqual(count, 0)
                manifest_count = conn.execute(
                    "select count(*) from manifests where kind = 'AutomationRun' and id = ?",
                    (automation_run.object_id,),
                ).fetchone()[0]
                self.assertEqual(manifest_count, 0)
            finally:
                conn.close()


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("select name from sqlite_master where type = 'table'").fetchall()
    return {row[0] for row in rows}


if __name__ == "__main__":
    unittest.main()
