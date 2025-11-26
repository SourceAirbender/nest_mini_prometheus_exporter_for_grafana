#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="nest-mini-exporter.service"

if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "[healthcheck] $SERVICE_NAME is not active, restarting..."
  systemctl restart "$SERVICE_NAME"
else
  echo "[healthcheck] $SERVICE_NAME is active."
fi
