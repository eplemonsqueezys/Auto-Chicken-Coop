# PCA9685 — same board as the workshop vac system
# Servos: MG995 DIGI HI-SPEED (metal gear, same pulse range as MG996R)
SERVOMIN = 150
SERVOMAX = 325

SERVO_VENT1_CHANNEL = 0
SERVO_VENT2_CHANNEL = 1

SERVO_VENT_OPEN  = SERVOMAX
SERVO_VENT_CLOSE = SERVOMIN  # swap these two if the vent moves the wrong way

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
