#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.runtime"
PID_FILE="${RUNTIME_DIR}/web_scraper_mcp.pid"
LOG_FILE="${RUNTIME_DIR}/web_scraper_mcp.log"

PYTHON_BIN="${PYTHON_BIN:-python3}"
TRANSPORT="${WST_SERVER_TRANSPORT:-streamable-http}"
HOST="${WST_SERVER_HOST:-0.0.0.0}"
PORT="${WST_SERVER_PORT:-8000}"
MCP_PATH="${WST_SERVER_PATH:-/mcp}"
CONFIG_PATH="${WST_CONFIG_JSON:-${ROOT_DIR}/config.json}"
LOCAL_CONFIG_PATH="${WST_LOCAL_CFG:-${ROOT_DIR}/settings.local.cfg}"
API_KEY="${WST_MCP_API_KEY:-}"

mkdir -p "${RUNTIME_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  EXISTING_PID="$(cat "${PID_FILE}")"
  if kill -0 "${EXISTING_PID}" >/dev/null 2>&1; then
    echo "MCP server already running (pid=${EXISTING_PID})."
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

CMD=(
  "${PYTHON_BIN}" -m web_scraper_toolkit.server.mcp_server
  --transport "${TRANSPORT}"
  --host "${HOST}"
  --port "${PORT}"
  --path "${MCP_PATH}"
  --config "${CONFIG_PATH}"
)

if [[ -f "${LOCAL_CONFIG_PATH}" ]]; then
  CMD+=(--local-config "${LOCAL_CONFIG_PATH}")
fi

echo "Starting MCP server..."
echo "  transport=${TRANSPORT} host=${HOST} port=${PORT} path=${MCP_PATH}"
echo "  log=${LOG_FILE}"

(
  cd "${ROOT_DIR}"
  PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}" nohup "${CMD[@]}" >>"${LOG_FILE}" 2>&1 &
  echo $! > "${PID_FILE}"
)

sleep 2
SERVER_PID="$(cat "${PID_FILE}")"
if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
  echo "Failed to start MCP server. Check ${LOG_FILE}" >&2
  rm -f "${PID_FILE}"
  exit 1
fi

HEALTH_URL="http://127.0.0.1:${PORT}${MCP_PATH}"
HEALTH_ARGS=(--url "${HEALTH_URL}")
if [[ -n "${API_KEY}" ]]; then
  HEALTH_ARGS+=(--api-key "${API_KEY}")
fi

if "${PYTHON_BIN}" "${ROOT_DIR}/scripts/healthcheck_mcp.py" "${HEALTH_ARGS[@]}" >/dev/null; then
  echo "MCP server started (pid=${SERVER_PID}) and passed health check."
else
  echo "MCP server started (pid=${SERVER_PID}) but health check failed. Check ${LOG_FILE}" >&2
  exit 1
fi
