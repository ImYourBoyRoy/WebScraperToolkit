#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/.runtime/web_scraper_mcp.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "MCP server pid file not found. Nothing to stop."
  exit 0
fi

SERVER_PID="$(cat "${PID_FILE}")"
if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
  echo "Stale pid file found. Cleaning up."
  rm -f "${PID_FILE}"
  exit 0
fi

echo "Stopping MCP server (pid=${SERVER_PID})..."
kill "${SERVER_PID}" || true

for _ in {1..20}; do
  if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    rm -f "${PID_FILE}"
    echo "MCP server stopped."
    exit 0
  fi
  sleep 0.5
done

echo "Force killing MCP server (pid=${SERVER_PID})..."
kill -9 "${SERVER_PID}" || true
rm -f "${PID_FILE}"
echo "MCP server stopped."
