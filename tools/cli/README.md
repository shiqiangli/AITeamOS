# AITEAMOS Thin CLI

The MVP CLI is intentionally small. It is not the first product surface.

Initial commands:

```bash
aiteamos serve --workspace .aiteamos
aiteamos workspace validate
aiteamos workspace index
aiteamos db rebuild --from .aiteamos
aiteamos vector rebuild --from .aiteamos
```

Task creation, role assignment, run review, diff review, and memory review should land in the dashboard first. Additional CLI commands should be added only when they support automation, CI, or developer ergonomics without duplicating the dashboard workflow.

Possible later helper:

```bash
aiteamos run ingest RUN-ID --journal journal.md --branch-url URL
```

This helper would support Qoder/Codex/Cursor-style assisted review ingestion without turning the CLI into the main product surface.
