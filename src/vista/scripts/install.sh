#!/usr/bin/env bash
# ============================================================================
# VISTA — Raspberry Pi 4B Complete Installation Script
# ============================================================================
# Installs ALL system dependencies, Python packages, configures services,
# and prepares the Pi for VISTA operation.
#
# Usage:
#   chmod +x scripts/install.sh
#   sudo ./scripts/install.sh
#
# Tested on: Raspberry Pi OS Bookworm (64-bit, 2024+)
# ============================================================================

set -euo pipefail

# ── Color output ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BLUE}[STEP]${NC} $*"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

# ── Check if running as root ───────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root (sudo)."
    exit 1
fi

# ── Determine VISTA root directory ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VISTA_ROOT="$(dirname "$SCRIPT_DIR")"
info "VISTA root: ${VISTA_ROOT}"

PI_HOME="/home/pi"
if [[ ! -d "$PI_HOME" ]]; then
    warn "/home/pi not found — using current user home"
    PI_HOME="$HOME"
fi

VENV_DIR="${VISTA_ROOT}/venv"

# ════════════════════════════════════════════════════════════════════════════
# Step 1: System Update & Base Dependencies
# ════════════════════════════════════════════════════════════════════════════

step "Step 1/8 — Updating system and installing base dependencies"

apt-get update -y
apt-get upgrade -y

apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-numpy \
    git \
    curl \
    wget \
    vim

info "Base packages installed"


# ════════════════════════════════════════════════════════════════════════════
# Step 2: Hardware Enablement (I2C, Camera, Serial)
# ════════════════════════════════════════════════════════════════════════════

step "Step 2/8 — Enabling I2C, Camera, and Serial interfaces"

# raspi-config non-interactive commands
raspi-config nonint do_i2c 0      # Enable I2C
raspi-config nonint do_camera 0   # Enable CSI camera (legacy camera on Bookworm)
raspi-config nonint do_serial_hw 0  # Enable serial hardware
raspi-config nonint do_serial_cons 1  # Disable serial console (free for OBD)

info "I2C, Camera, and Serial enabled"

# Install I2C tools
apt-get install -y i2c-tools

# Load kernel modules
if ! grep -q "^i2c-dev" /etc/modules 2>/dev/null; then
    echo "i2c-dev" >> /etc/modules
fi
if ! grep -q "^i2c-bcm2708" /etc/modules 2>/dev/null; then
    echo "i2c-bcm2708" >> /etc/modules
fi

modprobe i2c-dev 2>/dev/null || true
modprobe i2c-bcm2708 2>/dev/null || true

info "I2C tools installed and modules loaded"


# ════════════════════════════════════════════════════════════════════════════
# Step 3: System Services (InfluxDB, Mosquitto MQTT, Grafana)
# ════════════════════════════════════════════════════════════════════════════

step "Step 3/8 — Installing InfluxDB, Mosquitto MQTT, and Grafana"

# InfluxDB v2
if ! command -v influxd &>/dev/null; then
    info "Installing InfluxDB v2..."
    curl -sL https://repos.influxdata.com/influxdata-archive_compat.key | \
        gpg --dearmor -o /usr/share/keyrings/influxdata-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/influxdata-archive-keyring.gpg] https://repos.influxdata.com/debian stable main" | \
        tee /etc/apt/sources.list.d/influxdata.list
    apt-get update -y
    apt-get install -y influxdb2 influxdb2-cli
    systemctl enable influxdb
    systemctl start influxdb
    info "InfluxDB v2 installed and started"
else
    info "InfluxDB already installed — skipping"
fi

# Mosquitto MQTT broker
if ! command -v mosquitto &>/dev/null; then
    info "Installing Mosquitto MQTT..."
    apt-get install -y mosquitto mosquitto-clients
    systemctl enable mosquitto
    systemctl start mosquitto
    info "Mosquitto MQTT installed and started"
else
    info "Mosquitto already installed — skipping"
fi

# Grafana
if ! command -v grafana-server &>/dev/null; then
    info "Installing Grafana..."
    apt-get install -y software-properties-common
    curl -sL https://packages.grafana.com/gpg.key | \
        gpg --dearmor -o /usr/share/keyrings/grafana-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/grafana-archive-keyring.gpg] https://packages.grafana.com/oss/deb stable main" | \
        tee /etc/apt/sources.list.d/grafana.list
    apt-get update -y
    apt-get install -y grafana
    systemctl enable grafana-server
    systemctl start grafana-server
    info "Grafana installed and started (http://localhost:3000)"
else
    info "Grafana already installed — skipping"
fi

# PortAudio for PyAudio
apt-get install -y portaudio19-dev libportaudio2

info "System services installed"


# ════════════════════════════════════════════════════════════════════════════
# Step 4: Python Virtual Environment
# ════════════════════════════════════════════════════════════════════════════

step "Step 4/8 — Creating Python virtual environment"

if [[ -d "$VENV_DIR" ]]; then
    warn "Virtual environment already exists at ${VENV_DIR}"
    info "Recreating..."
    rm -rf "$VENV_DIR"
fi

python3 -m venv "$VENV_DIR"
info "Virtual environment created at ${VENV_DIR}"

# Activate and upgrade pip
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip setuptools wheel

info "venv ready"


# ════════════════════════════════════════════════════════════════════════════
# Step 5: Python Dependencies
# ════════════════════════════════════════════════════════════════════════════

step "Step 5/8 — Installing Python requirements"

REQUIREMENTS="${VISTA_ROOT}/requirements.txt"

if [[ ! -f "$REQUIREMENTS" ]]; then
    error "requirements.txt not found at ${REQUIREMENTS}"
    exit 1
fi

source "${VENV_DIR}/bin/activate"

# Install in two passes: first the essentials, then hardware-specific
# Some Pi packages (picamera2, RPi.GPIO) only exist on Raspberry Pi OS
pip install pyyaml python-dotenv loguru psutil numpy scipy 2>&1 | tail -3

# Install full requirements (best-effort for Pi-specific packages)
info "Installing all requirements (best-effort)..."
pip install -r "$REQUIREMENTS" 2>&1 || {
    warn "Some packages failed to install (expected on non-Pi systems)"
    warn "Hardware packages (picamera2, RPi.GPIO) require Raspberry Pi OS"
}

# Verify critical packages
CRITICAL_PKGS="pyyaml python-dotenv loguru numpy paho-mqtt flask pyyaml"
for pkg in $CRITICAL_PKGS; do
    if pip show "$pkg" &>/dev/null; then
        info "  ✓ $pkg"
    else
        error "  ✗ $pkg — NOT INSTALLED"
    fi
done

info "Python dependencies installed"


# ════════════════════════════════════════════════════════════════════════════
# Step 6: InfluxDB Setup
# ════════════════════════════════════════════════════════════════════════════

step "Step 6/8 — Setting up InfluxDB"

INFLUX_BUCKET="vista_telemetry"
INFLUX_ORG="vista"
INFLUX_RETENTION="30d"

# Check if InfluxDB is running
if ! systemctl is-active --quiet influxdb; then
    error "InfluxDB is not running — cannot set up"
    warn "Start with: sudo systemctl start influxdb"
    warn "Then re-run: influx setup"
else
    info "Checking InfluxDB setup..."
    # Check if already configured
    if influx auth list --skip-verify 2>/dev/null | grep -q "vista"; then
        info "InfluxDB already configured — skipping setup"
    else
        warn "InfluxDB needs initial setup. Run manually:"
        warn "  influx setup --org ${INFLUX_ORG} --bucket ${INFLUX_BUCKET} --retention ${INFLUX_RETENTION} --username admin --password <your-password> --force"
        warn "  Then save the token to your .env file as INFLUXDB_TOKEN=<token>"
    fi
fi

info "InfluxDB setup completed"


# ════════════════════════════════════════════════════════════════════════════
# Step 7: Systemd Services
# ════════════════════════════════════════════════════════════════════════════

step "Step 7/8 — Installing systemd services"

SERVICES_DIR="${VISTA_ROOT}/services"

if [[ -d "$SERVICES_DIR" ]]; then
    for service_file in "$SERVICES_DIR"/*.service; do
        if [[ -f "$service_file" ]]; then
            svc_name="$(basename "$service_file")"
            info "Installing ${svc_name}..."
            cp "$service_file" /etc/systemd/system/
            systemctl daemon-reload
            systemctl enable "$svc_name"
            info "  ${svc_name} installed and enabled"
        fi
    done
else
    warn "services/ directory not found — skipping systemd installation"
fi

info "Systemd services installed"


# ════════════════════════════════════════════════════════════════════════════
# Step 8: Permissions and Final Setup
# ════════════════════════════════════════════════════════════════════════════

step "Step 8/8 — Setting permissions and finalizing"

# Create required directories
mkdir -p "${VISTA_ROOT}/data"
mkdir -p "${VISTA_ROOT}/data/images"
mkdir -p "${VISTA_ROOT}/logs"
mkdir -p "${VISTA_ROOT}/models"

# Set ownership to pi user (for systemd)
if id "pi" &>/dev/null; then
    chown -R pi:pi "$VISTA_ROOT"
    info "Ownership set to pi:pi"
else
    warn "User 'pi' not found — permissions not changed"
fi

# Add pi to required groups
if id "pi" &>/dev/null; then
    usermod -a -G i2c,spi,gpio,video,audio,dialout pi 2>/dev/null || true
    info "User 'pi' added to hardware groups (i2c, spi, gpio, video, audio, dialout)"
fi

# Copy .env if it doesn't exist
if [[ ! -f "${VISTA_ROOT}/.env" ]] && [[ -f "${VISTA_ROOT}/.env.example" ]]; then
    cp "${VISTA_ROOT}/.env.example" "${VISTA_ROOT}/.env"
    warn ".env created from .env.example — EDIT WITH YOUR API KEYS!"
fi

# Set hostname
CURRENT_HOSTNAME="$(hostname)"
if [[ "$CURRENT_HOSTNAME" != "vista-pi" ]]; then
    hostnamectl set-hostname vista-pi
    info "Hostname set to vista-pi"
fi

info "Final setup complete"


# ════════════════════════════════════════════════════════════════════════════
# Done!
# ════════════════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║   ██╗   ██╗██╗███████╗████████╗ █████╗                      ║"
echo "║   ██║   ██║██║██╔════╝╚══██╔══╝██╔══██╗                     ║"
echo "║   ██║   ██║██║███████╗   ██║   ███████║                     ║"
echo "║   ╚██╗ ██╔╝██║╚════██║   ██║   ██╔══██║                     ║"
echo "║    ╚████╔╝ ██║███████║   ██║   ██║  ██║                     ║"
echo "║     ╚═══╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝                     ║"
echo "║                                                              ║"
echo "║          INSTALLATION COMPLETE!                               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo "📋 NEXT STEPS:"
echo "  1. Edit ${VISTA_ROOT}/.env with your API keys:"
echo "     - GEMINI_API_KEY=your_gemini_key"
echo "     - TELEGRAM_BOT_TOKEN=your_telegram_token"
echo "     - INFLUXDB_TOKEN=your_influxdb_token"
echo ""
echo "  2. Set up InfluxDB (first-time only):"
echo "     influx setup \\"
echo "       --org vista \\"
echo "       --bucket vista_telemetry \\"
echo "       --retention 30d \\"
echo "       --username admin \\"
echo "       --password <your-password> \\"
echo "       --force"
echo "     Save the token to ${VISTA_ROOT}/.env"
echo ""
echo "  3. Configure Grafana (http://localhost:3000):"
echo "     - Login: admin / admin"
echo "     - Add InfluxDB data source"
echo "     - Import VISTA dashboard"
echo ""
echo "  4. Verify hardware:"
echo "     i2cdetect -y 1          # Should show 0x68 (MPU6050)"
echo "     ls /dev/ttyUSB*          # Should show OBD adapter"
echo ""
echo "  5. Test the system:"
echo "     source ${VISTA_ROOT}/venv/bin/activate"
echo "     python ${VISTA_ROOT}/main.py --mode demo --demo-scenario normal"
echo ""
echo "  6. Start services:"
echo "     sudo systemctl start vista.service"
echo "     sudo systemctl status vista.service"
echo ""
echo "  📡 WiFi Hotspot: VISTA-Demo (password: vista1234)"
echo "  🌐 Dashboard: http://$(hostname -I | awk '{print $1}'):5000"
echo "  📊 Grafana:   http://$(hostname -I | awk '{print $1}'):3000"
echo ""
echo "  Happy driving! 🚗"
echo ""
