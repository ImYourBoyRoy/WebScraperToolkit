#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/.runtime/web_scraper_mcp.pid"
PORT="${WST_SERVER_PORT:-8000}"
MCP_PATH="${WST_SERVER_PATH:-/mcp}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
API_KEY="${WST_MCP_API_KEY:-}"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "MCP server is not running (pid file missing)."
  exit 1
fi

SERVER_PID="$(cat "${PID_FILE}")"
if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
  echo "MCP server is not running (stale pid=${SERVER_PID})."
  exit 1
fi

echo "MCP server process is running (pid=${SERVER_PID})."

HEALTH_URL="http://127.0.0.1:${PORT}${MCP_PATH}"
HEALTH_ARGS=(--url "${HEALTH_URL}")
if [[ -n "${API_KEY}" ]]; then
  HEALTH_ARGS+=(--api-key "${API_KEY}")
fi

if "${PYTHON_BIN}" "${ROOT_DIR}/scripts/healthcheck_mcp.py" "${HEALTH_ARGS[@]}" >/dev/null; then
  echo "Health check: OK (${HEALTH_URL})"
  exit 0
fi

echo "Health check: FAILED (${HEALTH_URL})"
exit 2
