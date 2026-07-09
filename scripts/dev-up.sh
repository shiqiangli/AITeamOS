#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${AITEAMOS_VENV_DIR:-$ROOT_DIR/.venv}"
NEO4J_PASSWORD="${AITEAMOS_NEO4J_PASSWORD:?Set AITEAMOS_NEO4J_PASSWORD before starting AITeamOS local services.}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required to start AITeamOS local services." >&2
  exit 1
fi

COMPOSE_CMD=()
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "Docker Compose is required. Install either the docker compose plugin or docker-compose." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to start the dashboard." >&2
  exit 1
fi

echo "Starting Neo4j for Graphiti..."
AITEAMOS_NEO4J_PASSWORD="$NEO4J_PASSWORD" "${COMPOSE_CMD[@]}" -f "$ROOT_DIR/docker/docker-compose.yml" up -d neo4j

if [[ "${AITEAMOS_WITH_PLANE:-0}" == "1" ]]; then
  echo "Starting Plane Ticket/Docs backend..."
  "$ROOT_DIR/scripts/plane-up.sh" up
fi

echo "Preparing local Graphiti settings..."
"$PYTHON_BIN" - "$ROOT_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
workspace = root / ".aiteamos"
workspace.mkdir(parents=True, exist_ok=True)

settings_path = workspace / "graphiti.json"

def read_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}

settings = read_object(settings_path)
if not settings:
    settings = {
        "enabled": True,
        "graph_database": "neo4j",
        "uri": "bolt://localhost:7687",
        "user": "neo4j",
        "group_id": "aiteamos",
        "llm_ai_engine": "openai",
    }
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating Python virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

if [[ "${AITEAMOS_SKIP_INSTALL:-0}" != "1" ]]; then
  echo "Installing backend dependencies..."
  "$PIP" install -e "$ROOT_DIR[dev,graphiti]"

  if [[ ! -d "$ROOT_DIR/apps/dashboard/node_modules" ]]; then
    echo "Installing dashboard dependencies..."
    (cd "$ROOT_DIR/apps/dashboard" && npm install)
  fi
fi

export AITEAMOS_WORKSPACE_DIR="${AITEAMOS_WORKSPACE_DIR:-$ROOT_DIR}"
export AITEAMOS_GRAPHITI_PASSWORD="${AITEAMOS_GRAPHITI_PASSWORD:-$NEO4J_PASSWORD}"
export VITE_LANGGRAPH_API_URL="${VITE_LANGGRAPH_API_URL:-http://127.0.0.1:${AITEAMOS_LANGGRAPH_PORT:-2024}}"
export VITE_LANGGRAPH_ASSISTANT_ID="${VITE_LANGGRAPH_ASSISTANT_ID:-aiteamos_workbench}"

echo "Starting AITeamOS API at http://127.0.0.1:8000"
"$PY" -m uvicorn aiteamos_api.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

LANGGRAPH_PID=""
if [[ "${AITEAMOS_WITH_LANGGRAPH:-1}" == "1" ]]; then
  LANGGRAPH_PORT="${AITEAMOS_LANGGRAPH_PORT:-2024}"
  echo "Starting LangGraph Agent Server at http://127.0.0.1:$LANGGRAPH_PORT"
  (
    cd "$ROOT_DIR"
    "$VENV_DIR/bin/langgraph" dev --host 127.0.0.1 --port "$LANGGRAPH_PORT" --no-reload --allow-blocking
  ) &
  LANGGRAPH_PID=$!
fi

echo "Starting AITeamOS Dashboard at http://127.0.0.1:5173"
(cd "$ROOT_DIR/apps/dashboard" && npm run dev) &
WEB_PID=$!

cleanup() {
  if [[ -n "$LANGGRAPH_PID" ]]; then
    kill "$API_PID" "$WEB_PID" "$LANGGRAPH_PID" 2>/dev/null || true
  else
    kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ -n "$LANGGRAPH_PID" ]]; then
  wait -n "$API_PID" "$WEB_PID" "$LANGGRAPH_PID"
else
  wait -n "$API_PID" "$WEB_PID"
fi
