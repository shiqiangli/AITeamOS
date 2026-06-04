#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLANE_VERSION="${AITEAMOS_PLANE_VERSION:-v1.3.1}"
PLANE_DIR="${AITEAMOS_PLANE_DIR:-$ROOT_DIR/.aiteamos/plane}"
PLANE_HTTP_PORT="${AITEAMOS_PLANE_HTTP_PORT:-8082}"
PLANE_URL="${AITEAMOS_PLANE_URL:-http://localhost:$PLANE_HTTP_PORT}"
SETUP_URL="https://github.com/makeplane/plane/releases/download/$PLANE_VERSION/setup.sh"
ACTION="${1:-up}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required to start Plane." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download the Plane setup script." >&2
  exit 1
fi

download_setup() {
  mkdir -p "$PLANE_DIR"
  if [[ ! -f "$PLANE_DIR/setup.sh" || "${AITEAMOS_PLANE_REFRESH_SETUP:-0}" == "1" ]]; then
    echo "Downloading Plane $PLANE_VERSION setup script..."
    curl -fsSL "$SETUP_URL" -o "$PLANE_DIR/setup.sh"
    chmod +x "$PLANE_DIR/setup.sh"
  fi
}

upsert_env() {
  local key="$1"
  local value="$2"
  local file="$3"
  if grep -q "^$key=" "$file"; then
    sed -i "s|^$key=.*|$key=$value|g" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

configure_plane_env() {
  local env_file="$PLANE_DIR/plane-app/plane.env"
  if [[ ! -f "$env_file" ]]; then
    echo "Plane environment file not found: $env_file" >&2
    exit 1
  fi
  upsert_env "LISTEN_HTTP_PORT" "$PLANE_HTTP_PORT" "$env_file"
  upsert_env "WEB_URL" "$PLANE_URL" "$env_file"
  upsert_env "CORS_ALLOWED_ORIGINS" "$PLANE_URL,http://localhost:5173,http://127.0.0.1:5173" "$env_file"
  upsert_env "APP_RELEASE" "$PLANE_VERSION" "$env_file"
}

install_plane() {
  download_setup
  if [[ ! -f "$PLANE_DIR/plane-app/docker-compose.yaml" || "${AITEAMOS_PLANE_REINSTALL:-0}" == "1" ]]; then
    echo "Installing Plane $PLANE_VERSION Docker files..."
    (cd "$PLANE_DIR" && APP_RELEASE="$PLANE_VERSION" bash ./setup.sh install)
  fi
  configure_plane_env
}

start_plane() {
  install_plane
  echo "Starting Plane at $PLANE_URL..."
  (cd "$PLANE_DIR" && APP_RELEASE="$PLANE_VERSION" bash ./setup.sh start)
  echo "Plane is available at $PLANE_URL. Configure it from AITeamOS Settings / Ticket Backend."
}

run_setup_action() {
  download_setup
  if [[ ! -f "$PLANE_DIR/plane-app/docker-compose.yaml" ]]; then
    echo "Plane is not installed yet. Run: $0 up" >&2
    exit 1
  fi
  (cd "$PLANE_DIR" && APP_RELEASE="$PLANE_VERSION" bash ./setup.sh "$@")
}

case "$ACTION" in
  up|start)
    start_plane
    ;;
  install)
    install_plane
    ;;
  stop)
    run_setup_action stop
    ;;
  restart)
    run_setup_action restart
    ;;
  logs)
    shift || true
    run_setup_action logs "$@"
    ;;
  backup)
    run_setup_action backup
    ;;
  *)
    echo "Usage: $0 [up|install|stop|restart|logs [service]|backup]" >&2
    exit 1
    ;;
esac
