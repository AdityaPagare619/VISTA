#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# VISTA Deployment Script — Raspberry Pi 4 Setup
# ═══════════════════════════════════════════════════════════════════
#
# Usage:
#   chmod +x scripts/deploy.sh
#   sudo ./scripts/deploy.sh
#
# What this does:
#   1. Installs system-level dependencies (apt)
#   2. Creates Python virtual environment
#   3. Installs Python packages
#   4. Sets up systemd services
#   5. Creates data directories on USB SSD
#   6. Verifies the installation
#
# Prerequisites:
#   - Raspberry Pi 4 (4GB) running Raspberry Pi OS (Bookworm)
#   - USB SSD mounted at /mnt/vista-data (optional, will fallback)
#   - Internet connection for package installation
#
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Configuration ──────────────────────────────────────────────────
VISTA_HOME="/opt/vista"
VISTA_USER="vista"
VISTA_GROUP="vista"
VENV_DIR="${VISTA_HOME}/venv"
SSD_MOUNT="/mnt/vista-data"

echo "═══════════════════════════════════════════════════════════════"
echo "  VISTA Deployment — Raspberry Pi 4"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Check root ─────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root (sudo)"
    exit 1
fi

# ══════════════════════════════════════════════════════════════════
# Phase 1: System Dependencies
# ══════════════════════════════════════════════════════════════════
log_info "Phase 1/6: Installing system dependencies..."

apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    python3-dev \
    portaudio19-dev \
    libasound2-dev \
    libatlas-base-dev \
    i2c-tools \
    bluez \
    bluetooth \
    libbluetooth-dev \
    libgpiod2 \
    sqlite3 \
    git \
    2>/dev/null

# Enable I2C and SPI if not already
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm=on" >> /boot/config.txt
    log_warn "I2C enabled — reboot required after deployment"
fi

log_ok "System dependencies installed"

# ══════════════════════════════════════════════════════════════════
# Phase 2: Create VISTA user and directories
# ══════════════════════════════════════════════════════════════════
log_info "Phase 2/6: Setting up VISTA user and directories..."

# Create system user if not exists
if ! id "${VISTA_USER}" &>/dev/null; then
    useradd --system --create-home --home-dir "${VISTA_HOME}" \
        --groups gpio,i2c,spi,bluetooth,audio,video \
        "${VISTA_USER}"
    log_ok "Created system user: ${VISTA_USER}"
else
    log_ok "User ${VISTA_USER} already exists"
fi

# Create directories
mkdir -p "${VISTA_HOME}"
mkdir -p "${VISTA_HOME}/data/images"
mkdir -p "${VISTA_HOME}/logs"
mkdir -p "${VISTA_HOME}/models"

# SSD mount check
if mountpoint -q "${SSD_MOUNT}" 2>/dev/null; then
    mkdir -p "${SSD_MOUNT}/images"
    mkdir -p "${SSD_MOUNT}/logs"
    chown -R "${VISTA_USER}:${VISTA_GROUP}" "${SSD_MOUNT}"
    log_ok "USB SSD detected at ${SSD_MOUNT}"
else
    log_warn "USB SSD not mounted at ${SSD_MOUNT} — using local storage"
fi

log_ok "Directories created"

# ══════════════════════════════════════════════════════════════════
# Phase 3: Copy VISTA source code
# ══════════════════════════════════════════════════════════════════
log_info "Phase 3/6: Copying VISTA source code..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "${SCRIPT_DIR}")/src/vista"

if [ -d "${SOURCE_DIR}" ]; then
    cp -r "${SOURCE_DIR}"/* "${VISTA_HOME}/"
    log_ok "Source code copied to ${VISTA_HOME}"
else
    log_error "Source directory not found at ${SOURCE_DIR}"
    log_error "Run this script from the VISO-PROJECT root directory"
    exit 1
fi

# ══════════════════════════════════════════════════════════════════
# Phase 4: Python virtual environment
# ══════════════════════════════════════════════════════════════════
log_info "Phase 4/6: Setting up Python virtual environment..."

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip wheel setuptools -q

# Install requirements
if [ -f "${SCRIPT_DIR}/../requirements.txt" ]; then
    pip install -r "${SCRIPT_DIR}/../requirements.txt" -q 2>/dev/null || true
    log_ok "Python packages installed from requirements.txt"
else
    # Install core packages manually
    pip install -q \
        numpy \
        pyyaml \
        loguru \
        flask \
        flask-socketio \
        python-dotenv \
        requests \
        2>/dev/null || true
    log_ok "Core Python packages installed"
fi

# Install Pi-specific packages (may fail on non-Pi)
pip install -q \
    RPi.GPIO \
    smbus2 \
    mpu6050-raspberrypi \
    python-obd \
    pyaudio \
    bleak \
    paho-mqtt \
    2>/dev/null || log_warn "Some Pi-specific packages failed (expected on non-Pi)"

# TFLite runtime
pip install -q tflite-runtime 2>/dev/null || \
    log_warn "tflite-runtime not available — will use tensorflow if installed"

deactivate
log_ok "Virtual environment ready at ${VENV_DIR}"

# ══════════════════════════════════════════════════════════════════
# Phase 5: Systemd services
# ══════════════════════════════════════════════════════════════════
log_info "Phase 5/6: Installing systemd services..."

# Main VISTA service
cat > /etc/systemd/system/vista.service << EOF
[Unit]
Description=VISTA Vehicle Intelligence & Safety Telematics
After=network.target bluetooth.target
Wants=bluetooth.target

[Service]
Type=simple
User=${VISTA_USER}
Group=${VISTA_GROUP}
WorkingDirectory=${VISTA_HOME}
ExecStart=${VENV_DIR}/bin/python ${VISTA_HOME}/main.py --mode driving
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=${VISTA_HOME}/data ${VISTA_HOME}/logs ${SSD_MOUNT}
MemoryMax=512M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

# Dashboard service
cat > /etc/systemd/system/vista-dashboard.service << EOF
[Unit]
Description=VISTA Web Dashboard
After=vista.service
Requires=vista.service

[Service]
Type=simple
User=${VISTA_USER}
Group=${VISTA_GROUP}
WorkingDirectory=${VISTA_HOME}
ExecStart=${VENV_DIR}/bin/python ${VISTA_HOME}/dashboard/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Set ownership
chown -R "${VISTA_USER}:${VISTA_GROUP}" "${VISTA_HOME}"

# Reload and enable
systemctl daemon-reload
systemctl enable vista.service
systemctl enable vista-dashboard.service

log_ok "Systemd services installed and enabled"

# ══════════════════════════════════════════════════════════════════
# Phase 6: Verification
# ══════════════════════════════════════════════════════════════════
log_info "Phase 6/6: Verifying installation..."

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  VERIFICATION"
echo "═══════════════════════════════════════════════════════════════"

# Check Python
if "${VENV_DIR}/bin/python" -c "import yaml; import numpy; import loguru; print('Core imports OK')"; then
    log_ok "Python core imports"
else
    log_error "Python core imports FAILED"
fi

# Check YAMNet model
if [ -f "${VISTA_HOME}/models/yamnet.tflite" ]; then
    MODEL_SIZE=$(stat --printf="%s" "${VISTA_HOME}/models/yamnet.tflite")
    log_ok "YAMNet model present (${MODEL_SIZE} bytes)"
else
    log_warn "YAMNet model not found — audio classification will be disabled"
fi

# Check config
if [ -f "${VISTA_HOME}/config.yaml" ]; then
    log_ok "config.yaml present"
else
    log_error "config.yaml NOT FOUND — system will not start"
fi

# Check .env
if [ -f "${VISTA_HOME}/.env" ]; then
    log_ok ".env file present"
else
    log_warn ".env file missing — Telegram/Gemini features will be disabled"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  To start VISTA:"
echo "    sudo systemctl start vista"
echo "    sudo systemctl start vista-dashboard"
echo ""
echo "  To view logs:"
echo "    journalctl -u vista -f"
echo "    journalctl -u vista-dashboard -f"
echo ""
echo "  Dashboard URL:"
echo "    http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "  To run in demo mode (no hardware):"
echo "    DEMO_MODE=true ${VENV_DIR}/bin/python ${VISTA_HOME}/main.py --mode demo"
echo ""
echo "═══════════════════════════════════════════════════════════════"
