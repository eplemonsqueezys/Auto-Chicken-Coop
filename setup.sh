#!/bin/bash
# Chicken Coop Controller — Raspberry Pi 5 Setup Script
# Run once on a fresh Raspberry Pi OS (64-bit Lite recommended)
# Usage: chmod +x setup.sh && sudo ./setup.sh

set -e

echo "=== Chicken Coop Controller Setup (Pi 5) ==="

# ── Detect config.txt location (Pi 5 moved it) ────────────────
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"   # Pi 5 (Bookworm)
else
    BOOT_CONFIG="/boot/config.txt"            # Pi 4 / older OS
fi
echo "  Using boot config: $BOOT_CONFIG"

# ── System update ──────────────────────────────────────────────
echo "[1/6] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# ── Enable SPI (MCP3008) and I2C (PCA9685) ────────────────────
echo "[2/6] Enabling SPI and I2C interfaces..."
if ! grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
    echo "dtparam=spi=on" >> "$BOOT_CONFIG"
    echo "  SPI enabled"
else
    echo "  SPI already enabled"
fi
if ! grep -q "^dtparam=i2c_arm=on" "$BOOT_CONFIG"; then
    echo "dtparam=i2c_arm=on" >> "$BOOT_CONFIG"
    echo "  I2C enabled (reboot required)"
else
    echo "  I2C already enabled"
fi

# ── Install Python dependencies ────────────────────────────────
echo "[3/6] Installing Python packages..."
apt-get install -y -qq python3-pip python3-dev i2c-tools python3-lgpio

# Pi 5 uses the RP1 GPIO chip — RPi.GPIO does NOT work on Pi 5.
# lgpio is the correct backend for gpiozero on Pi 5.
pip3 install --upgrade gpiozero lgpio --break-system-packages

# Adafruit CircuitPython libraries
pip3 install adafruit-circuitpython-dht     --break-system-packages  # DHT22
pip3 install adafruit-circuitpython-pca9685 --break-system-packages  # PCA9685 servo driver
pip3 install adafruit-blinka                --break-system-packages  # CircuitPython layer for Pi

# spidev for MCP3008 (used by gpiozero MCP3008 class)
pip3 install spidev --break-system-packages

# Flask for the web debug panel
pip3 install flask --break-system-packages

echo "  Python packages installed"
echo ""
echo "  Verify PCA9685 is detected on I2C after reboot:"
echo "    i2cdetect -y 1   (should show 0x40)"

# ── Copy project files ─────────────────────────────────────────
echo "[4/6] Copying project files to /home/pi/coop/..."
mkdir -p /home/pi/coop
cp coop_controller.py /home/pi/coop/
cp config.py /home/pi/coop/
cp debug_panel.py /home/pi/coop/
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

# Tell gpiozero to use lgpio (required for Pi 5's RP1 GPIO chip)
Environment=GPIOZERO_PIN_FACTORY=lgpio

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
echo "  1. Reboot to activate SPI + I2C:  sudo reboot"
echo "  2. After reboot, verify I2C sees the PCA9685:"
echo "       i2cdetect -y 1   (expect 0x40)"
echo "  3. Test the controller manually before enabling the service:"
echo "       sudo GPIOZERO_PIN_FACTORY=lgpio python3 /home/pi/coop/coop_controller.py"
echo "  4. Watch logs live:"
echo "       tail -f /home/pi/coop.log"
echo "  5. Start/stop the service:"
echo "       sudo systemctl start coop"
echo "       sudo systemctl stop coop"
echo "       sudo systemctl status coop"
echo ""
echo "Edit thresholds and pin assignments in /home/pi/coop/config.py"
echo ""
echo "Debug panel (manual control, run separately from the main controller):"
echo "  sudo GPIOZERO_PIN_FACTORY=lgpio python3 /home/pi/coop/debug_panel.py"
echo "  Then open http://<pi-ip>:5000 on any device on your WiFi"
echo "  Find your Pi's IP with: hostname -I"
