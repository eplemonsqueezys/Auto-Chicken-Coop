#!/usr/bin/env python3
"""
Chicken Coop Automation Controller
Hardware: Raspberry Pi 5 + Adafruit PCA9685 PWM Servo Driver + MCP3008 ADC

Pi 5 uses the RP1 GPIO chip — gpiozero must use the lgpio backend.
Set env var before running:  GPIOZERO_PIN_FACTORY=lgpio
Or use setup.sh which configures this automatically in the systemd service.

Servo control uses the same Adafruit PCA9685 board and SERVOMIN/SERVOMAX
values as the workshop dust collection system.

Systems controlled:
  1. Temperature monitoring (DHT22)
  2. Vent sliders (2x servo via PCA9685, temp-triggered)
  3. Circulation fan (relay, temp-triggered)
  4. Water level indicator (3x float switch, 3x LED)
  5. Chicken door (linear actuator via L298N, dawn/dusk via LDR + time)
  6. Coop & run lights (2x relay, time-based schedule)
  7. Food level indicator (potentiometer lever, LED)

Run manually:  sudo GPIOZERO_PIN_FACTORY=lgpio python3 coop_controller.py
"""

import os
import time
import board
import busio
import adafruit_dht
from adafruit_pca9685 import PCA9685
from gpiozero import Device, Motor, Button, LED, OutputDevice, MCP3008
from gpiozero.pins.lgpio import LGPIOFactory
from datetime import datetime
import config
import logging

# ── Pi 5: force lgpio pin factory ─────────────────────────────
# Pi 5 uses the RP1 GPIO chip; RPi.GPIO doesn't work on it.
# lgpio is the correct backend. We set it here in code AND via the
# GPIOZERO_PIN_FACTORY env var in setup.sh as a belt-and-suspenders approach.
if os.environ.get("GPIOZERO_PIN_FACTORY", "lgpio") == "lgpio":
    Device.pin_factory = LGPIOFactory()

# ── Logging setup ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/home/pi/coop.log")
    ]
)
log = logging.getLogger("coop")


# ── PCA9685 servo helper ───────────────────────────────────────

def set_servo(pca, channel, pulse_value):
    """
    Set a servo channel to a raw pulse value.
    Matches the Arduino: pwm.setPWM(channel, 0, pulse_value)
    pulse_value: SERVOMIN (150) = closed, SERVOMAX (325) = open
    """
    # PCA9685 Python library uses 16-bit duty cycle (0–65535).
    # Convert from the 12-bit (0–4095) raw pulse value used in Arduino.
    duty = int(pulse_value * 65535 / 4096)
    pca.channels[channel].duty_cycle = duty


# ── Hardware initialisation ────────────────────────────────────

def init_hardware():
    """Initialise all devices. Returns a dict of handles."""
    log.info("Initialising hardware...")

    hw = {}

    # PCA9685 PWM servo driver via I2C (SDA=GPIO2, SCL=GPIO3)
    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)
    pca.frequency = 60    # 60 Hz — same as Arduino pwm.setPWMFreq(60)
    hw["pca"] = pca

    # Calibrate both vent servos to known positions on startup
    # (mirrors the setup() block in the Arduino sketch)
    log.info("Calibrating vent servos...")
    set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_OPEN)
    set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_OPEN)
    time.sleep(1)
    set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_CLOSE)
    set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_CLOSE)
    time.sleep(1)
    log.info("Servo calibration done — vents closed")

    # DHT22 temperature + humidity sensor
    hw["dht"] = adafruit_dht.DHT22(board.D4)

    # Fan relay — active HIGH (HIGH = off, LOW = on, same as Arduino sketches)
    hw["fan"] = OutputDevice(config.PIN_FAN_RELAY, active_high=False, initial_value=False)

    # Water level float switches (NO: float up = water present = circuit closed)
    hw["water_low"]  = Button(config.PIN_WATER_LOW,  pull_up=False)
    hw["water_mid"]  = Button(config.PIN_WATER_MID,  pull_up=False)
    hw["water_high"] = Button(config.PIN_WATER_HIGH, pull_up=False)

    # Water level indicator LEDs
    hw["water_red"]    = LED(config.PIN_WATER_LED_RED)
    hw["water_yellow"] = LED(config.PIN_WATER_LED_YELLOW)
    hw["water_green"]  = LED(config.PIN_WATER_LED_GREEN)

    # Chicken door — L298N H-bridge via gpiozero Motor
    hw["door_motor"] = Motor(forward=config.PIN_DOOR_IN1, backward=config.PIN_DOOR_IN2)

    # Door limit switches (NO: active = actuator has reached that end)
    hw["limit_open"]   = Button(config.PIN_DOOR_LIMIT_OPEN,   pull_up=True)
    hw["limit_closed"] = Button(config.PIN_DOOR_LIMIT_CLOSED, pull_up=True)

    # Light relays (active LOW — same convention as Arduino relay modules)
    hw["coop_light"] = OutputDevice(config.PIN_COOP_LIGHT_RELAY, active_high=False, initial_value=False)
    hw["run_light"]  = OutputDevice(config.PIN_RUN_LIGHT_RELAY,  active_high=False, initial_value=False)

    # Food level LEDs
    hw["food_red"]   = LED(config.PIN_FOOD_LED_RED)
    hw["food_green"] = LED(config.PIN_FOOD_LED_GREEN)

    # MCP3008 analog inputs via SPI
    hw["ldr"]  = MCP3008(channel=config.MCP3008_LDR_CHANNEL)    # Dawn/dusk light sensor
    hw["food"] = MCP3008(channel=config.MCP3008_FOOD_CHANNEL)   # Food level potentiometer

    log.info("Hardware initialised OK")
    return hw


# ── Vent / Fan control ─────────────────────────────────────────

def update_vents_and_fan(hw, state, temp):
    """Open/close vent sliders and fan based on temperature with hysteresis."""

    pca = hw["pca"]

    # Vents — open when hot, close when cooled back down
    if not state["vents_open"] and temp >= config.TEMP_VENT_OPEN:
        set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_OPEN)
        set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_OPEN)
        state["vents_open"] = True
        log.info(f"Vents OPENED (temp={temp:.1f}°C)")

    elif state["vents_open"] and temp <= config.TEMP_VENT_CLOSE:
        set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_CLOSE)
        set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_CLOSE)
        state["vents_open"] = False
        log.info(f"Vents CLOSED (temp={temp:.1f}°C)")

    # Fan — on when hotter, off when cooled
    if not state["fan_on"] and temp >= config.TEMP_FAN_ON:
        hw["fan"].on()
        state["fan_on"] = True
        log.info(f"Fan ON (temp={temp:.1f}°C)")

    elif state["fan_on"] and temp <= config.TEMP_FAN_OFF:
        hw["fan"].off()
        state["fan_on"] = False
        log.info(f"Fan OFF (temp={temp:.1f}°C)")


# ── Water level ────────────────────────────────────────────────

def update_water_leds(hw):
    """
    Read float switches, light the LED for the highest active level.
    Float switches are NO: is_active = water is at or above that sensor.
    """
    has_high = hw["water_high"].is_active
    has_mid  = hw["water_mid"].is_active
    has_low  = hw["water_low"].is_active

    hw["water_red"].off()
    hw["water_yellow"].off()
    hw["water_green"].off()

    if has_high:
        hw["water_green"].on()     # Full
    elif has_mid:
        hw["water_yellow"].on()    # Mid
    elif has_low:
        hw["water_red"].on()       # Low — getting there
    else:
        hw["water_red"].on()       # Empty — below lowest sensor


# ── Chicken door ───────────────────────────────────────────────

def open_door(hw, state):
    """Drive actuator forward until fully-open limit switch fires."""
    if state["door_open"] is True:
        return

    log.info("Opening chicken door...")
    hw["door_motor"].forward()

    start = time.time()
    while not hw["limit_open"].is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            log.warning("Door OPEN timeout — check limit switch!")
            break
        time.sleep(0.1)

    hw["door_motor"].stop()
    state["door_open"] = True
    log.info("Chicken door OPEN")


def close_door(hw, state):
    """Drive actuator backward until fully-closed limit switch fires."""
    if state["door_open"] is False:
        return

    log.info("Closing chicken door...")
    hw["door_motor"].backward()

    start = time.time()
    while not hw["limit_closed"].is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            log.warning("Door CLOSE timeout — check limit switch!")
            break
        time.sleep(0.1)

    hw["door_motor"].stop()
    state["door_open"] = False
    log.info("Chicken door CLOSED")


def update_door(hw, state, now):
    """
    Open at dawn, close at dusk.
    Uses LDR for natural light sensing + clock as safety net for overcast days.
    """
    hour        = now.hour
    light_level = hw["ldr"].value   # 0.0 = dark, 1.0 = bright

    is_dawn = (light_level >= config.LDR_DAWN_THRESHOLD) or (hour >= config.DOOR_OPEN_LATEST_HOUR)
    is_dusk = (light_level <= config.LDR_DUSK_THRESHOLD) and (hour >= config.DOOR_CLOSE_EARLIEST_HOUR)

    if is_dawn and state["door_open"] is not True:
        open_door(hw, state)
    elif is_dusk and state["door_open"] is not False:
        close_door(hw, state)


# ── Lights ─────────────────────────────────────────────────────

def update_lights(hw, state, now):
    """Switch coop and run lights on/off per the configured time schedule."""
    current_mins = now.hour * 60 + now.minute
    on_mins      = config.LIGHT_ON_HOUR  * 60 + config.LIGHT_ON_MINUTE
    off_mins     = config.LIGHT_OFF_HOUR * 60 + config.LIGHT_OFF_MINUTE

    should_be_on = on_mins <= current_mins < off_mins

    if should_be_on and not state["lights_on"]:
        hw["coop_light"].on()
        hw["run_light"].on()
        state["lights_on"] = True
        log.info("Lights ON")

    elif not should_be_on and state["lights_on"]:
        hw["coop_light"].off()
        hw["run_light"].off()
        state["lights_on"] = False
        log.info("Lights OFF")


# ── Food level ─────────────────────────────────────────────────

def update_food_leds(hw):
    """
    Read potentiometer at food lever pivot via MCP3008.
    0.0 = lever down (empty), 1.0 = lever up (full).
    Adjust FOOD_LOW_THRESHOLD in config.py after fitting the lever.
    """
    food_level = hw["food"].value

    if food_level < config.FOOD_LOW_THRESHOLD:
        hw["food_red"].on()
        hw["food_green"].off()
        log.info(f"Food LOW ({food_level:.2f})")
    else:
        hw["food_red"].off()
        hw["food_green"].on()


# ── Startup door detection ─────────────────────────────────────

def detect_door_state(hw, state):
    """Check limit switches at boot so we know starting position."""
    if hw["limit_open"].is_active:
        state["door_open"] = True
        log.info("Startup: door is OPEN")
    elif hw["limit_closed"].is_active:
        state["door_open"] = False
        log.info("Startup: door is CLOSED")
    else:
        state["door_open"] = None
        log.warning("Startup: door position unknown — will move on first dawn/dusk trigger")


# ── Main loop ──────────────────────────────────────────────────

def main():
    hw = init_hardware()

    state = {
        "vents_open": False,
        "fan_on":     False,
        "door_open":  None,
        "lights_on":  False,
    }

    detect_door_state(hw, state)
    log.info("Coop controller running. Press Ctrl+C to stop.")

    while True:
        now = datetime.now()

        # 1. Temperature → vents + fan
        try:
            temp     = hw["dht"].temperature
            humidity = hw["dht"].humidity
            if temp is not None:
                log.info(f"Temp: {temp:.1f}°C  Humidity: {humidity:.1f}%")
                update_vents_and_fan(hw, state, temp)
        except RuntimeError as e:
            log.debug(f"DHT22 read error (will retry): {e}")

        # 2. Water level LEDs
        update_water_leds(hw)

        # 3. Chicken door
        update_door(hw, state, now)

        # 4. Lights
        update_lights(hw, state, now)

        # 5. Food level LEDs
        update_food_leds(hw)

        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Shutting down gracefully...")
    except Exception as e:
        log.exception(f"Unhandled exception: {e}")
    finally:
        log.info("Controller stopped.")
