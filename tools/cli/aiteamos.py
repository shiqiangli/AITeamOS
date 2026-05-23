from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from aiteamos_schema import export_schema_files


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON_SCHEMA = REPO_ROOT / "packages" / "schema" / "generated" / "aiteamos.schema.json"
DEFAULT_OPENAPI = REPO_ROOT / "packages" / "schema" / "generated" / "openapi.json"
DEFAULT_DASHBOARD_TYPES = REPO_ROOT / "apps" / "dashboard" / "src" / "generated" / "aiteamos-schema.ts"
DEFAULT_AITEAMOS_BUNDLE_SCHEMA = REPO_ROOT / "packages" / "schema" / "generated" / "aiteamos-bundle.schema.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiteamos")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the local AITEAMOS API and dashboard")
    serve_parser.add_argument("--workspace", default=".aiteamos")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8765, type=int)

    worker_parser = subparsers.add_parser("worker", help="Start the standalone managed worker process")
    worker_parser.add_argument("--workspace", default=".aiteamos")
    worker_parser.add_argument("--run", dest="run_id", default=None)
    worker_parser.add_argument("--once", action="store_true", help="Poll once and exit. This is the default unless --watch is set.")
    worker_parser.add_argument("--watch", action="store_true", help="Keep polling until interrupted.")
    worker_parser.add_argument("--interval", type=float, default=5.0, help="Seconds between polls when --watch is set.")
    worker_parser.add_argument("--write-event", action="store_true", help="Record a worker.queue.* event in the selected Run ledger.")
    worker_parser.add_argument("--execute", action="store_true", help="Execute the selected Run after readiness and authorization pass.")
    worker_parser.add_argument("--create-pr", action="store_true", help="Ask the worker executor to create a PR after a diff is produced.")
    worker_parser.add_argument("--fail-on-blocked", action="store_true", help="Return non-zero when a selected Run is blocked.")

    workspace_parser = subparsers.add_parser("workspace", help="Workspace operations")
    workspace_sub = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    validate_parser = workspace_sub.add_parser("validate", help="Validate workspace manifests")
    validate_parser.add_argument("--workspace", default=".aiteamos")
    index_parser = workspace_sub.add_parser("index", help="Rebuild derived workspace indexes")
    index_parser.add_argument("--workspace", default=".aiteamos")
    index_parser.add_argument("--output", default=None, help="Optional SQLite database output path")
    index_parser.add_argument("--vector-output", default=None, help="Optional vector source manifest output path")
    export_workspace_parser = workspace_sub.add_parser("export", help="Create a sanitized workspace bundle")
    export_workspace_parser.add_argument("--workspace", default=".aiteamos")
    export_workspace_parser.add_argument("--output", required=True)
    export_workspace_parser.add_argument("--force", action="store_true", help="Overwrite an existing output bundle")
    export_workspace_parser.add_argument("--max-log-bytes", type=int, default=64 * 1024)

    db_parser = subparsers.add_parser("db", help="Derived database operations")
    db_sub = db_parser.add_subparsers(dest="db_command", required=True)
    db_rebuild_parser = db_sub.add_parser("rebuild", help="Rebuild the derived SQLite database from workspace files")
    db_rebuild_parser.add_argument("--from", dest="source", default=".aiteamos")
    db_rebuild_parser.add_argument("--output", default=None)

    vector_parser = subparsers.add_parser("vector", help="Derived vector index operations")
    vector_sub = vector_parser.add_subparsers(dest="vector_command", required=True)
    vector_rebuild_parser = vector_sub.add_parser("rebuild", help="Rebuild the derived vector source manifest from workspace files")
    vector_rebuild_parser.add_argument("--from", dest="source", default=".aiteamos")
    vector_rebuild_parser.add_argument("--output", default=None)

    schema_parser = subparsers.add_parser("schema", help="Schema contract operations")
    schema_sub = schema_parser.add_subparsers(dest="schema_command", required=True)
    export_parser = schema_sub.add_parser("export", help="Generate JSON Schema, OpenAPI, and dashboard TypeScript types")
    export_parser.add_argument("--json-schema", default=str(DEFAULT_JSON_SCHEMA))
    export_parser.add_argument("--openapi", default=str(DEFAULT_OPENAPI))
    export_parser.add_argument("--typescript", default=str(DEFAULT_DASHBOARD_TYPES))
    export_parser.add_argument("--bundle-schema", default=None, help="Optional aiteamos-bundle JSON Schema output path")

    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn
        from aiteamos_api import create_app

        workspace = Path(args.workspace).resolve()
        os.environ["AITEAMOS_WORKSPACE"] = str(workspace)
        app = create_app(workspace)
        print(f"Serving AITEAMOS from {workspace} at http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    if args.command == "worker":
        worker_path = REPO_ROOT / "services" / "worker"
        if str(worker_path) not in sys.path:
            sys.path.insert(0, str(worker_path))
        from aiteamos_worker.runner import run_cli

        return run_cli(args)

    if args.command == "workspace" and args.workspace_command == "validate":
        from aiteamos_workspace import load_workspace

        index = load_workspace(args.workspace)
        for issue in index.health:
            ref = f" [{issue['ref']}]" if "ref" in issue else ""
            print(f"{issue['severity'].upper()} {issue['kind']}{ref}: {issue['message']}")
        if any(issue["severity"] == "error" for issue in index.health):
            return 1
        print(f"Workspace valid: {index.workspace_root}")
        return 0

    if args.command == "workspace" and args.workspace_command == "index":
        from aiteamos_workspace import rebuild_workspace_indexes

        result = rebuild_workspace_indexes(args.workspace, db_path=args.output, vector_path=args.vector_output)
        print(f"Indexed workspace: {result['source']}")
        print(f"Derived database: {result['database']['databasePath']}")
        print(f"Derived vector sources: {result['vector']['path']}")
        print(f"Derived vector chunks: {result['vector']['chunkManifestPath']}")
        print(f"Dashboard cache: {result['dashboardCache']['status']}")
        print(result["counts"])
        return 0

    if args.command == "workspace" and args.workspace_command == "export":
        from aiteamos_workspace import export_workspace_bundle

        result = export_workspace_bundle(
            args.workspace,
            args.output,
            overwrite=args.force,
            max_log_bytes=args.max_log_bytes,
        )
        print(f"Exported sanitized workspace bundle: {result['path']}")
        print(f"Included files: {len(result['included'])}")
        print(f"Excluded files: {len(result['excluded'])}")
        return 0

    if args.command == "db" and args.db_command == "rebuild":
        from aiteamos_workspace import rebuild_database_index

        result = rebuild_database_index(args.source, db_path=args.output)
        print(f"Rebuilt derived database: {result['databasePath']}")
        print(f"Source workspace: {result['source']}")
        print(result["counts"])
        return 0

    if args.command == "vector" and args.vector_command == "rebuild":
        from aiteamos_workspace import rebuild_vector_index

        result = rebuild_vector_index(args.source, output_path=args.output)
        print(f"Rebuilt derived vector source manifest: {result['path']}")
        print(f"Rebuilt derived vector chunk manifest: {result['chunkManifestPath']}")
        print(f"Source workspace: {result['source']}")
        print(f"Embeddings generated: {result['embeddingsGenerated']}")
        print(result["counts"])
        return 0

    if args.command == "schema" and args.schema_command == "export":
        written = export_schema_files(
            json_schema_path=args.json_schema,
            openapi_path=args.openapi,
            typescript_path=args.typescript,
            aiteamos_bundle_schema_path=args.bundle_schema,
        )
        for path in written:
            print(f"Generated {path}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
