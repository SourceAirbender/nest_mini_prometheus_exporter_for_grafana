#!/usr/bin/env bash
set -euo pipefail

EXPORTER_SERVICE="nest-mini-exporter.service"
IMAGE_RELAY_SERVICE="nest-mini-image-relay.service"
HEALTHCHECK_SERVICE="nest_mini_exporter_check_sh_script.service"
HEALTHCHECK_TIMER="nest_mini_exporter_check_sh_script.timer"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This script must be run as root. Use: sudo ./uninstall.sh"
  exit 1
fi

echo "[uninstall] Stopping services and timer..."
systemctl stop "${EXPORTER_SERVICE}" 2>/dev/null || true
systemctl stop "${IMAGE_RELAY_SERVICE}" 2>/dev/null || true
systemctl stop "${HEALTHCHECK_TIMER}" 2>/dev/null || true

echo "[uninstall] Disabling services and timer..."
systemctl disable "${EXPORTER_SERVICE}" 2>/dev/null || true
systemctl disable "${IMAGE_RELAY_SERVICE}" 2>/dev/null || true
systemctl disable "${HEALTHCHECK_TIMER}" 2>/dev/null || true

for UNIT in \
  "/etc/systemd/system/${EXPORTER_SERVICE}" \
  "/etc/systemd/system/${IMAGE_RELAY_SERVICE}" \
  "/etc/systemd/system/${HEALTHCHECK_SERVICE}" \
  "/etc/systemd/system/${HEALTHCHECK_TIMER}"
do
  if [[ -f "${UNIT}" ]]; then
    echo "[uninstall] Removing ${UNIT}..."
    rm -f "${UNIT}"
  fi
done

echo "[uninstall] Reloading systemd..."
systemctl daemon-reload

echo
echo "✅ Uninstall complete."
echo "Note: Project files and venv were not removed."
