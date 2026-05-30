# Migrations

PostgreSQL DDL scripts for initializing the AITeamOS schema.

## Order

Scripts are numbered and must be applied in order:

1. `001_shared_infrastructure.sql` — Outbox, projection offsets
2. `002_knowledge_context.sql` — Memory nodes, edges, versions
3. `003_capability_context.sql` — Skills
4. `004_workforce_context.sql` — Members, departments, projects
5. `005_execution_context.sql` — Tasks, runs, snapshots
6. `006_validation_context.sql` — Harness invocations
7. `007_governance_context.sql` — Reviews, conflicts
8. `008_recall_and_conflict.sql` — Recall audit, conflict tracking
9. `009_schema_gap_fixes.sql` — Supplementary fixes
10. `010_unique_name_constraints.sql` — Human-readable member, department, project uniqueness
11. `011_global_unique_names.sql` — Global name uniqueness for UI addressable resources
12. `012_general_skill_fields.sql` — General neutral Skill attributes

## Applying

```bash
psql -h localhost -U aiteamos -d aiteamos -f migrations/001_shared_infrastructure.sql
# ... repeat for each migration
```
