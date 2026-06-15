#!/bin/bash
# Chicken Coop Controller — Raspberry Pi Setup Script
# Run once on a fresh Raspberry Pi OS (64-bit Lite recommended)
# Usage: chmod +x setup.sh && sudo ./setup.sh

set -e

echo "=== Chicken Coop Controller Setup ==="

# ── System update ──────────────────────────────────────────────
echo "[1/6] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# ── Enable SPI (needed for MCP3008) ───────────────────────────
echo "[2/6] Enabling SPI interface..."
if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "dtparam=spi=on" >> /boot/config.txt
    echo "  SPI enabled in /boot/config.txt (reboot required after setup)"
else
    echo "  SPI already enabled"
fi

# ── Install Python dependencies ────────────────────────────────
echo "[3/6] Installing Python packages..."
apt-get install -y -qq python3-pip python3-dev

# gpiozero is pre-installed on Pi OS but ensure it's up to date
pip3 install --upgrade gpiozero RPi.GPIO

# Adafruit DHT22 library
pip3 install adafruit-circuitpython-dht

# spidev for MCP3008 SPI communication (used by gpiozero)
pip3 install spidev

echo "  Python packages installed"

# ── Copy project files ─────────────────────────────────────────
echo "[4/6] Copying project files to /home/pi/coop/..."
mkdir -p /home/pi/coop
cp coop_controller.py /home/pi/coop/
cp config.py /home/pi/coop/
chown -R pi:pi /home/pi/coop

# ── Create systemd service (auto-start on boot) ────────────────
echo "[5/6] Installing systemd service..."
cat > /etc/systemd/system/coop.service << 'EOF'
[Unit]
Description=Chicken Coop Automation Controller
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/coop
ExecStart=/usr/bin/python3 /home/pi/coop/coop_controller.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable coop.service
echo "  Service installed and enabled (starts on next boot)"

# ── Done ───────────────────────────────────────────────────────
echo ""
echo "[6/6] Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Reboot to activate SPI:  sudo reboot"
echo "  2. After reboot, start the controller manually to test:"
echo "       sudo python3 /home/pi/coop/coop_controller.py"
echo "  3. Watch logs live:"
echo "       tail -f /home/pi/coop.log"
echo "  4. Start/stop the service:"
echo "       sudo systemctl start coop"
echo "       sudo systemctl stop coop"
echo "       sudo systemctl status coop"
echo ""
echo "Edit thresholds and pin assignments in /home/pi/coop/config.py"
