# AITEAMOS Bundle Reference Extension

This is the minimal VSCode/Cursor reference bridge for `aiteamos-bundle.json` v1.

It supports two commands:

- `AITEAMOS Bundle: Import aiteamos-bundle.json` stores the selected bundle in workspace state after checking `kind: AiteamosBundle`, `schemaVersion: aiteamos-bundle.v1`, and the assisted ingest boundary.
- `AITEAMOS Bundle: Submit Assisted Ingest` builds a `RunAssistedIngestInput` payload and posts it to the bundle's `/api/runs/{run}/assisted-ingest` boundary.

The bundle never carries credentials. Set `AITEAMOS_API_BASE_URL` when the local API is not `http://127.0.0.1:8765`, and set `AITEAMOS_API_TOKEN` only in the extension host environment when the API requires a bearer token.
