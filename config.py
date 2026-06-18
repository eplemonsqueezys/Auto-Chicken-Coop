"""
Chicken Coop Automation — Configuration
Edit this file to tune thresholds, schedules, and pin assignments.
"""

# ── Adafruit PCA9685 PWM Servo Driver (I2C) ───────────────────
# Same board/library as the workshop dust collection system.
# Pi connects via I2C: SDA=GPIO2 (pin 3), SCL=GPIO3 (pin 5)

PCA9685_CHANNELS = 16     # 16-channel board
SERVOMIN = 150            # Minimum pulse length (matches workshop system)
SERVOMAX = 325            # Maximum pulse length (matches workshop system)

# PCA9685 channel assignments for vent servos
SERVO_VENT1_CHANNEL = 0   # Vent slider 1
SERVO_VENT2_CHANNEL = 1   # Vent slider 2

# ── GPIO Pin Assignments (BCM numbering) ──────────────────────

# Temperature (DHT22)
PIN_DHT22 = 4

# Fan relay
PIN_FAN_RELAY = 17

# Water level float switches (NO — float up = circuit closes = "pressed")
PIN_WATER_LOW  = 22
PIN_WATER_MID  = 23
PIN_WATER_HIGH = 24

# Water level LEDs
PIN_WATER_LED_RED    = 25   # Low / empty
PIN_WATER_LED_YELLOW = 27   # Mid level
PIN_WATER_LED_GREEN  = 18   # Full

# Chicken door — L298N H-bridge
PIN_DOOR_IN1          = 5   # Motor forward (door opens)
PIN_DOOR_IN2          = 6   # Motor backward (door closes)
PIN_DOOR_LIMIT_OPEN   = 16  # Limit switch: door fully open
PIN_DOOR_LIMIT_CLOSED = 20  # Limit switch: door fully closed

# Light relays
PIN_COOP_LIGHT_RELAY = 19
PIN_RUN_LIGHT_RELAY  = 26

# Food level LEDs
PIN_FOOD_LED_RED   = 21   # Needs food
PIN_FOOD_LED_GREEN = 14   # OK

# MCP3008 SPI channels (uses default SPI0: CLK=11, MOSI=10, MISO=9, CE0=8)
MCP3008_LDR_CHANNEL  = 0   # LDR voltage divider for dawn/dusk detection
MCP3008_FOOD_CHANNEL = 1   # Potentiometer at food lever pivot

# ── Temperature Thresholds (°C) ───────────────────────────────

TEMP_VENT_OPEN  = 27.0   # Open vent sliders above this temp
TEMP_VENT_CLOSE = 25.0   # Close vents below this (hysteresis gap prevents chatter)

TEMP_FAN_ON  = 30.0      # Turn on circulation fan above this temp
TEMP_FAN_OFF = 28.0      # Turn off fan below this (hysteresis)

# ── Servo Positions (PCA9685 raw pulse values) ────────────────
# Matches your existing workshop system (SERVOMIN / SERVOMAX above).
# SERVOMAX = slider open, SERVOMIN = slider closed.
# Swap if your vent moves the wrong direction after mounting.

SERVO_VENT_OPEN  = SERVOMAX   # 325 — vent fully open
SERVO_VENT_CLOSE = SERVOMIN   # 150 — vent fully closed

# ── Light Schedule ────────────────────────────────────────────

LIGHT_ON_HOUR    = 6    # Lights on at 06:00
LIGHT_ON_MINUTE  = 0
LIGHT_OFF_HOUR   = 22   # Lights off at 22:00
LIGHT_OFF_MINUTE = 0

# ── Door Dawn/Dusk Detection ──────────────────────────────────
# MCP3008 returns 0.0 (dark) to 1.0 (bright)
# Adjust these after testing your LDR voltage divider in real conditions

LDR_DAWN_THRESHOLD = 0.60   # Above this = bright enough to open door
LDR_DUSK_THRESHOLD = 0.30   # Below this = dark enough to close door

# Absolute time limits (safety net for overcast days)
DOOR_OPEN_LATEST_HOUR  = 9    # Force open by 09:00 even if LDR disagrees
DOOR_CLOSE_EARLIEST_HOUR = 20  # Allow close no earlier than 20:00

# Actuator travel timeout (seconds) — stop motor if limit switch not hit
DOOR_ACTUATOR_TIMEOUT = 30

# ── Food Level ────────────────────────────────────────────────
# Potentiometer reads 0.0 (lever fully down = empty) to 1.0 (lever up = full)
# Adjust LOW_THRESHOLD after calibrating your lever range

FOOD_LOW_THRESHOLD = 0.25   # Below 25% → red LED on

# ── Polling interval ──────────────────────────────────────────

POLL_INTERVAL = 10   # Seconds between sensor checks
