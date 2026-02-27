#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   SERVICE_NAME=web-scraper-mcp ./scripts/setup_mcp_service_ubuntu.sh
# Optional env:
#   SERVICE_NAME, SERVICE_USER, INSTALL_DIR, PYTHON_BIN, WST_CONFIG_JSON, WST_LOCAL_CFG,
#   WST_SERVER_TRANSPORT, WST_SERVER_HOST, WST_SERVER_PORT, WST_SERVER_PATH, WST_MCP_API_KEY

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-web-scraper-mcp}"
SERVICE_USER="${SERVICE_USER:-$USER}"
INSTALL_DIR="${INSTALL_DIR:-$ROOT_DIR}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

TRANSPORT="${WST_SERVER_TRANSPORT:-streamable-http}"
HOST="${WST_SERVER_HOST:-127.0.0.1}"
PORT="${WST_SERVER_PORT:-8000}"
MCP_PATH="${WST_SERVER_PATH:-/mcp}"
CONFIG_PATH="${WST_CONFIG_JSON:-${INSTALL_DIR}/config.json}"
LOCAL_CONFIG_PATH="${WST_LOCAL_CFG:-${INSTALL_DIR}/settings.local.cfg}"

UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
  echo "This script requires sudo/root to write ${UNIT_FILE}."
  exit 1
fi

cat >"${UNIT_FILE}" <<EOF
[Unit]
Description=Web Scraper Toolkit MCP Server
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONPATH=${INSTALL_DIR}/src
Environment=WST_MCP_API_KEY=${WST_MCP_API_KEY:-}
ExecStart=${PYTHON_BIN} -m web_scraper_toolkit.server.mcp_server --transport ${TRANSPORT} --host ${HOST} --port ${PORT} --path ${MCP_PATH} --config ${CONFIG_PATH} --local-config ${LOCAL_CONFIG_PATH}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
systemctl --no-pager status "${SERVICE_NAME}" || true

echo ""
echo "Service installed: ${SERVICE_NAME}"
echo "Manage with:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo "  sudo systemctl stop ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "Logs:"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
