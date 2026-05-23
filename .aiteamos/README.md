# AITEAMOS Self-hosting Workspace

This directory is the embedded AITEAMOS workspace for the AITEAMOS project itself.

It is intentionally small at first:

- `workspace.yaml` declares the local embedded workspace.
- `project.yaml` declares the AITEAMOS project.
- `repositories/aiteamos.yaml` binds this source repository.
- `members/`, `assignments/`, and `role_templates/` define durable team members and their project-scoped responsibilities.
- `tasks/` records project tasks.
- `reviews/` records human or assisted IDE review results and review target links.
- `runs/` records execution attempts, journals, context capsules, and event ledgers.
- `memory/` stores memory proposals and approved knowledge.

This self-hosting workspace may be tracked when the content is safe to publish. Large logs, raw provider responses, screenshots, build outputs, embeddings, and cache files should stay out of Git and be referenced by artifact manifests.

Current delivery direction: TeamMember-first, project-backed, thin-CLI. The first product loop should let the dashboard browse this workspace, manage employees and assignments, inspect run journals, and govern neutral memory proposals.
