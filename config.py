import os

# ── Simulation ────────────────────────────────────────────────────────────
# Test the whole system with NOTHING wired up, then bring real hardware online
# one subsystem at a time.
#
#   SIM_ALL = True   -> everything is simulated (good first run, no hardware).
#   SIM_ALL = False  -> obey the per-subsystem flags in SIM below.
#
# To bring a subsystem online: wire it up, set its flag to False, rerun, and
# confirm that one piece works while everything else stays simulated.
SIM_ALL = False

SIM = {
    "pca":    False,  # vent servos -> Arduino + PCA9685 shield (ARDUINO['servos']).
                      # Falls back to simulation automatically if the Arduino isn't
                      # plugged in, so this is safe to leave False.
    "dht":    True,   # DHT22 -> simulated; flip False once wired to the Arduino (D2)
    "fan":    True,   # fan relay -> simulated until wired
    "water":  True,   # water float switches + LEDs -> simulated until wired
    "door":   False,  # door motor (L298N) on the Pi -> REAL (tested)
    "lights": True,   # coop + run light relays -> simulated until wired
    "food":   True,   # food-level LEDs -> simulated until wired
    "adc":    True,   # LDR + food pot -> simulated; flip False once wired to Arduino
}

# Where logs are written (and read by the debug panel). Kept inside the project
# folder so it works no matter which user runs it (avoids assuming /home/pi).
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coop.log")

# How long the simulated door takes to travel between limit switches (seconds).
SIM_DOOR_TRAVEL_S = 2.0

# ── Arduino co-processor ──────────────────────────────────────────────────
# An Arduino (over USB serial) can handle the servos and analog sensors instead
# of the Pi's PCA9685 / MCP3008. For each subsystem below: if its SIM flag above
# is False AND it is True here, that subsystem is driven via the Arduino. If it's
# False here, the Pi drives it natively (PCA9685 / MCP3008 / GPIO).
#
#   simulated?  -> see SIM above (wins over everything)
#   else arduino? -> see ARDUINO below
#   else native Pi hardware
ARDUINO = {
    "servos": True,   # servos go through the Arduino + PCA9685 shield (isolates
                      # servo noise from the Pi; Pi only talks USB serial)
    "adc":    True,   # 'adc' subsystem -> LDR + food pot on the Arduino's analog pins
    "dht":    True,   # 'dht' subsystem -> DHT22 read by the Arduino
}

ARDUINO_PORT = "/dev/ttyACM0"   # Uno/Nano usually ttyACM0 or ttyUSB0; check `ls /dev/tty*`
ARDUINO_BAUD = 115200

# Arduino analog pins are 10-bit (0-1023). Used to normalize LDR/food to 0.0-1.0.
ARDUINO_ADC_MAX = 1023

# PCA9685 — same board as the workshop vac system
# Servos: MG995 DIGI HI-SPEED (metal gear, same pulse range as MG996R)
# Pulse-length counts out of 4096 at 60Hz. 150..600 is ~full MG995 travel —
# a wide sweep for testing. Narrow these later to the real vent/door end stops.
# These MUST match SERVOMIN/SERVOMAX in coop_arduino/coop_arduino.ino.
SERVOMIN = 150
SERVOMAX = 600

SERVO_VENT1_CHANNEL = 0
SERVO_VENT2_CHANNEL = 1

SERVO_VENT_OPEN  = SERVOMAX
SERVO_VENT_CLOSE = SERVOMIN  # swap these two if the vent moves the wrong way

# ── Door ──────────────────────────────────────────────────────────────────
# "servo" -> MG995 on the PCA9685 shield (channel below), driven gradually.
# "motor" -> L298N + limit switches (the original linear-actuator design).
DOOR_TYPE = "servo"
SERVO_DOOR_CHANNEL = 3            # shield "port 3"
SERVO_DOOR_OPEN  = SERVOMAX       # tweak to the real fully-open spot later
SERVO_DOOR_CLOSE = SERVOMIN       # tweak to the real fully-closed spot later
DOOR_SERVO_TRAVEL_S = 5.0         # seconds to sweep open<->closed (tweak in web UI)

# ── Location, weather & sun schedule (Open-Meteo, no API key) ──────────────
LOCATION_ZIP = "47909"            # Lafayette, IN — change LAT/LON if you move
LATITUDE  = 40.36
LONGITUDE = -86.89
TIMEZONE  = "America/New_York"    # Eastern (EST in winter, EDT in summer)
WEATHER_REFRESH_MIN = 10          # re-fetch temp/sun times at most this often

# Door schedule driven by real sunrise/sunset for the location above:
#   open  DOOR_OPEN_AFTER_DAWN_MIN minutes after sunrise
#   close DOOR_CLOSE_AFTER_DUSK_MIN minutes after sunset
USE_SUN_SCHEDULE = True
DOOR_OPEN_AFTER_DAWN_MIN  = 30
DOOR_CLOSE_AFTER_DUSK_MIN = 30

# Pull the vent/fan temperature from the web for the location (instead of a DHT).
USE_WEATHER_TEMP = True

# Relay polarity — SONGLE SLA-05VDC-SL-C (direct-drive board, no optocoupler)
# HIGH = relay energized = load ON
# If you swap to an optocoupler module (active-LOW), set this to False
RELAY_ACTIVE_HIGH = True

# GPIO pins (BCM)
PIN_DHT22             = 4
PIN_FAN_RELAY         = 17
PIN_WATER_LOW         = 22
PIN_WATER_MID         = 23
PIN_WATER_HIGH        = 24
PIN_WATER_LED_RED     = 25
PIN_WATER_LED_YELLOW  = 27
PIN_WATER_LED_GREEN   = 18
PIN_DOOR_IN1          = 5
PIN_DOOR_IN2          = 6
PIN_DOOR_LIMIT_OPEN   = 16
PIN_DOOR_LIMIT_CLOSED = 20
PIN_COOP_LIGHT_RELAY  = 19
PIN_RUN_LIGHT_RELAY   = 26
PIN_FOOD_LED_RED      = 21
PIN_FOOD_LED_GREEN    = 14

# MCP3008 channels
MCP3008_LDR_CHANNEL  = 0
MCP3008_FOOD_CHANNEL = 1

# Temperature thresholds (°C) — gap between open/close prevents chatter
TEMP_VENT_OPEN  = 27.0
TEMP_VENT_CLOSE = 25.0
TEMP_FAN_ON     = 30.0
TEMP_FAN_OFF    = 28.0

# Light schedule
LIGHT_ON_HOUR    = 6
LIGHT_ON_MINUTE  = 0
LIGHT_OFF_HOUR   = 22
LIGHT_OFF_MINUTE = 0

# LDR reads 0.0 (dark) to 1.0 (bright) — tune these after testing outside
LDR_DAWN_THRESHOLD = 0.60
LDR_DUSK_THRESHOLD = 0.30

# Clock fallback — forces door open by 9am on overcast days, won't close before 8pm
DOOR_OPEN_LATEST_HOUR    = 9
DOOR_CLOSE_EARLIEST_HOUR = 20
DOOR_ACTUATOR_TIMEOUT    = 30  # seconds before giving up if limit switch isn't hit

# Food lever pot: 0.0 = empty, 1.0 = full — adjust after fitting the arm
FOOD_LOW_THRESHOLD = 0.25

POLL_INTERVAL = 10  # seconds


# ── Auto-detected hardware overrides ──────────────────────────────────────
# detect_hardware.py probes what's actually connected and writes
# detected_hardware.json. If that file exists, apply its overrides on top of
# the manual flags above. Delete the file to return to fully manual control.
def _apply_detected_overrides():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "detected_hardware.json")
    if not os.path.exists(path):
        return
    import json
    try:
        with open(path) as f:
            ov = json.load(f).get("overrides", {})
    except (ValueError, OSError):
        return
    global SIM_ALL, ARDUINO_PORT
    if "SIM_ALL" in ov:
        SIM_ALL = ov["SIM_ALL"]
    if "ARDUINO_PORT" in ov:
        ARDUINO_PORT = ov["ARDUINO_PORT"]
    SIM.update(ov.get("SIM", {}))
    ARDUINO.update(ov.get("ARDUINO", {}))


_apply_detected_overrides()


# ── User location/schedule settings (settings.json) ───────────────────────
# Written by setup.sh (prompted on install) and editable live from the debug
# panel's Location card — so the location is NOT hardcoded. These keys override
# the defaults above when settings.json is present.
_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
_SETTINGS_KEYS = [
    "LOCATION_ZIP", "LOCATION_PLACE", "LATITUDE", "LONGITUDE", "TIMEZONE",
    "DOOR_OPEN_AFTER_DAWN_MIN", "DOOR_CLOSE_AFTER_DUSK_MIN",
]
LOCATION_PLACE = ""   # human-readable "City, ST" filled in by geocoding


def _apply_settings():
    if not os.path.exists(_SETTINGS_FILE):
        return
    import json
    try:
        with open(_SETTINGS_FILE) as f:
            s = json.load(f)
    except (ValueError, OSError):
        return
    g = globals()
    for k in _SETTINGS_KEYS:
        if k in s:
            g[k] = s[k]


def save_settings(updates):
    """Persist user-editable location/schedule settings to settings.json and
    apply them live. Returns the merged settings dict."""
    import json
    current = {}
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE) as f:
                current = json.load(f)
        except (ValueError, OSError):
            current = {}
    for k, v in updates.items():
        if k in _SETTINGS_KEYS:
            current[k] = v
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(current, f, indent=2)
    g = globals()
    for k, v in current.items():
        if k in _SETTINGS_KEYS:
            g[k] = v
    return current


_apply_settings()
