#!/bin/bash
# Chicken Coop Controller — Raspberry Pi 5 Setup Script
# Run once on a fresh Raspberry Pi OS (64-bit Lite recommended)
# Usage: chmod +x setup.sh && sudo ./setup.sh

set -e

echo "=== Chicken Coop Controller Setup (Pi 5) ==="

# ── Install target (don't assume a "pi" user exists) ───────────
TARGET_USER="${SUDO_USER:-$(whoami)}"
TARGET_HOME="$(eval echo "~$TARGET_USER")"
INSTALL_DIR="$TARGET_HOME/coop"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "  Installing for user: $TARGET_USER ($INSTALL_DIR)"

# ── Location setup (prompted, NOT hardcoded) ──────────────────
echo ""
echo "Location setup (for sunrise/sunset + outdoor temperature):"
read -rp "  ZIP / postal code [47909]: " COOP_ZIP;     COOP_ZIP="${COOP_ZIP:-47909}"
read -rp "  Country code [us]: " COOP_COUNTRY;          COOP_COUNTRY="${COOP_COUNTRY:-us}"
read -rp "  Timezone [America/New_York]: " COOP_TZ;     COOP_TZ="${COOP_TZ:-America/New_York}"
read -rp "  Open door this many minutes after dawn [30]: " COOP_DAWN; COOP_DAWN="${COOP_DAWN:-30}"
read -rp "  Close door this many minutes after dusk [30]: " COOP_DUSK; COOP_DUSK="${COOP_DUSK:-30}"

python3 - "$COOP_ZIP" "$COOP_COUNTRY" "$COOP_TZ" "$COOP_DAWN" "$COOP_DUSK" "$SCRIPT_DIR/settings.json" <<'PYEOF'
import sys, json, urllib.request, urllib.parse
zipc, country, tz, dawn, dusk, out = sys.argv[1:7]
s = {"LOCATION_ZIP": zipc, "TIMEZONE": tz,
     "DOOR_OPEN_AFTER_DAWN_MIN": int(dawn), "DOOR_CLOSE_AFTER_DUSK_MIN": int(dusk)}
try:
    url = "https://api.zippopotam.us/%s/%s" % (country, urllib.parse.quote(zipc))
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.load(r)
    p = d["places"][0]
    s["LATITUDE"]  = float(p["latitude"])
    s["LONGITUDE"] = float(p["longitude"])
    s["LOCATION_PLACE"] = "%s, %s" % (p["place name"], p["state abbreviation"])
    print("  Resolved %s -> %s (%.3f, %.3f)" % (zipc, s["LOCATION_PLACE"], s["LATITUDE"], s["LONGITUDE"]))
except Exception as e:
    print("  WARNING: couldn't geocode %s (%s)." % (zipc, e))
    print("           Using config.py lat/lon defaults; fix later in the debug panel's Location card.")
with open(out, "w") as f:
    json.dump(s, f, indent=2)
print("  Wrote", out)
PYEOF
echo ""

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
echo "[4/6] Copying project files to $INSTALL_DIR/..."
mkdir -p "$INSTALL_DIR"
cp coop_controller.py config.py debug_panel.py hardware.py arduino_link.py \
   weather.py detect_hardware.py "$INSTALL_DIR/"
[ -f sim_state.json ] && cp sim_state.json "$INSTALL_DIR/"
[ -f settings.json ]  && cp settings.json  "$INSTALL_DIR/"
chown -R "$TARGET_USER:$TARGET_USER" "$INSTALL_DIR"

# ── Create systemd service (auto-start on boot) ────────────────
echo "[5/6] Installing systemd service..."
cat > /etc/systemd/system/coop.service << EOF
[Unit]
Description=Chicken Coop Automation Controller
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR

# Tell gpiozero to use lgpio (required for Pi 5's RP1 GPIO chip)
Environment=GPIOZERO_PIN_FACTORY=lgpio

ExecStart=/usr/bin/python3 $INSTALL_DIR/coop_controller.py
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
echo "  2. After reboot, detect connected hardware (sets the Arduino port + flags):"
echo "       python3 $INSTALL_DIR/detect_hardware.py"
echo "  3. Test the controller manually before enabling the service:"
echo "       sudo GPIOZERO_PIN_FACTORY=lgpio python3 $INSTALL_DIR/coop_controller.py"
echo "  4. Watch logs live:"
echo "       tail -f $INSTALL_DIR/coop.log"
echo "  5. Start/stop the service:"
echo "       sudo systemctl start coop / stop coop / status coop"
echo ""
echo "Location saved to $INSTALL_DIR/settings.json (ZIP $COOP_ZIP)."
echo "Change it any time from the debug panel's Location card."
echo ""
echo "Debug panel (manual control, run separately from the main controller):"
echo "  sudo GPIOZERO_PIN_FACTORY=lgpio python3 $INSTALL_DIR/debug_panel.py"
echo "  Then open http://<pi-ip>:5000 on any device on your WiFi"
echo "  Find your Pi's IP with: hostname -I"
