#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

EXPORTER_SERVICE="nest-mini-exporter.service"
IMAGE_RELAY_SERVICE="nest-mini-image-relay.service"
HEALTHCHECK_SERVICE="nest_mini_exporter_check_sh_script.service"
HEALTHCHECK_TIMER="nest_mini_exporter_check_sh_script.timer"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This script must be run as root. Use: sudo ./install.sh"
  exit 1
fi

RUN_USER="${SUDO_USER:-$USER}"

echo "[install] Repo directory: ${SCRIPT_DIR}"
echo "[install] Using virtualenv: ${VENV_DIR}"
echo "[install] Running services as user: ${RUN_USER}"

# Create venv if needed
if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[install] Creating virtualenv..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
else
  echo "[install] Virtualenv already exists."
fi

echo "[install] Installing Python dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip
if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
  "${VENV_DIR}/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"
else
  "${VENV_DIR}/bin/pip" install pychromecast prometheus_client Flask \
    Werkzeug requests python-dotenv
fi

# Systemd unit: Nest Mini exporter
EXPORTER_UNIT="/etc/systemd/system/${EXPORTER_SERVICE}"
cat > "${EXPORTER_UNIT}" <<EOF
[Unit]
Description=Nest Mini Prometheus Exporter
After=network.target

[Service]
User=${RUN_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_DIR}/bin/python ${SCRIPT_DIR}/nest_exporter.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Systemd unit: Top 10 Image Relay
IMAGE_RELAY_UNIT="/etc/systemd/system/${IMAGE_RELAY_SERVICE}"
cat > "${IMAGE_RELAY_UNIT}" <<EOF
[Unit]
Description=Nest Mini Top 10 Metrics & Image Relay
After=network.target

[Service]
User=${RUN_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV_DIR}/bin/python ${SCRIPT_DIR}/nest_top10_image_relay.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Systemd unit: Healthcheck
HEALTHCHECK_UNIT="/etc/systemd/system/${HEALTHCHECK_SERVICE}"
cat > "${HEALTHCHECK_UNIT}" <<EOF
[Unit]
Description=Check Nest Mini Exporter and restart if not active

[Service]
Type=oneshot
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${SCRIPT_DIR}/nest_exporter_healthcheck.sh
EOF

# Systemd timer: Healthcheck timer
HEALTHCHECK_TIMER_UNIT="/etc/systemd/system/${HEALTHCHECK_TIMER}"
cat > "${HEALTHCHECK_TIMER_UNIT}" <<EOF
[Unit]
Description=Run Nest Mini Exporter health check every 2 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
Unit=${HEALTHCHECK_SERVICE}

[Install]
WantedBy=timers.target
EOF

echo "[install] Reloading systemd..."
systemctl daemon-reload

echo "[install] Enabling and starting services..."
systemctl enable --now "${EXPORTER_SERVICE}"
systemctl enable --now "${IMAGE_RELAY_SERVICE}"
systemctl enable --now "${HEALTHCHECK_TIMER}"

echo
echo "✅ Install complete."
echo "Status:"
echo "  sudo systemctl status ${EXPORTER_SERVICE}"
echo "  sudo systemctl status ${IMAGE_RELAY_SERVICE}"
echo "Timers:"
echo "  systemctl list-timers | grep nest_mini_exporter_check_sh_script"
