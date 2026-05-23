# RUN-0001 Journal

## Summary

Created the first AITEAMOS architecture document and initialized an embedded self-hosting workspace in this repository.

## Decisions

- Use `docs/architecture.md` as the primary architecture blueprint.
- Use public protocol fixtures as the neutral external example.
- Represent self-hosting through an embedded `.aiteamos/` workspace in the AITEAMOS repository.
- Describe delivery as three practical modes and tracks: Protocol Mode, Assisted IDE Mode, and Managed Worker Mode.
- Keep `.aiteamos` workspace files as source of truth; DB, vector index, dashboard cache, and worker state are derived.

## Follow-up candidates

- Add JSON Schema or Pydantic models for the `aiteamos.dev/v1alpha1` manifests.
- Implement `aiteamos workspace validate`.
- Implement `aiteamos task list` and `aiteamos context build` for the embedded workspace.
- Add a sanitized protocol fixture workspace under `examples/protocol-fixture/`. 
