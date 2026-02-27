#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-web-scraper-mcp}"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
  echo "This script requires sudo/root."
  exit 1
fi

if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
  systemctl disable --now "${SERVICE_NAME}" || true
fi

if [[ -f "${UNIT_FILE}" ]]; then
  rm -f "${UNIT_FILE}"
fi

systemctl daemon-reload
echo "Removed service ${SERVICE_NAME}."
