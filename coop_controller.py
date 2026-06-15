#!/usr/bin/env python3
"""
Chicken Coop Automation Controller
Hardware: Raspberry Pi 4 + MCP3008 ADC

Systems controlled:
  1. Temperature monitoring (DHT22)
  2. Vent sliders (2x MG996R servo, temp-triggered)
  3. Circulation fan (relay, temp-triggered)
  4. Water level indicator (3x float switch, 3x LED)
  5. Chicken door (linear actuator, dawn/dusk via LDR + time)
  6. Coop & run lights (2x relay, time-based schedule)
  7. Food level indicator (potentiometer lever, LED)

Run with: sudo python3 coop_controller.py
(sudo needed for hardware PWM servo control)
"""

import time
import board
import adafruit_dht
from gpiozero import Servo, Motor, Button, LED, OutputDevice, MCP3008
from datetime import datetime
import config
import logging

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


# ── Hardware initialisation ────────────────────────────────────

def init_hardware():
    """Initialise all GPIO devices. Returns a dict of device handles."""
    log.info("Initialising hardware...")

    hw = {}

    # DHT22 temperature + humidity sensor
    hw["dht"] = adafruit_dht.DHT22(board.D4)

    # Vent servos (gpiozero uses software PWM by default; fine for prototype)
    hw["servo1"] = Servo(config.PIN_SERVO_1)
    hw["servo2"] = Servo(config.PIN_SERVO_2)

    # Fan relay — active HIGH
    hw["fan"] = OutputDevice(config.PIN_FAN_RELAY, active_high=True, initial_value=False)

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

    # Door limit switches (NO: pressed = actuator has reached that end)
    hw["limit_open"]   = Button(config.PIN_DOOR_LIMIT_OPEN,   pull_up=True)
    hw["limit_closed"] = Button(config.PIN_DOOR_LIMIT_CLOSED, pull_up=True)

    # Light relays
    hw["coop_light"] = OutputDevice(config.PIN_COOP_LIGHT_RELAY, active_high=True, initial_value=False)
    hw["run_light"]  = OutputDevice(config.PIN_RUN_LIGHT_RELAY,  active_high=True, initial_value=False)

    # Food level LEDs
    hw["food_red"]   = LED(config.PIN_FOOD_LED_RED)
    hw["food_green"] = LED(config.PIN_FOOD_LED_GREEN)

    # MCP3008 analog inputs via SPI
    hw["ldr"]  = MCP3008(channel=config.MCP3008_LDR_CHANNEL)    # Light sensor
    hw["food"] = MCP3008(channel=config.MCP3008_FOOD_CHANNEL)   # Food level pot

    log.info("Hardware initialised OK")
    return hw


# ── Vent / Fan control ─────────────────────────────────────────

def update_vents_and_fan(hw, state, temp):
    """Open/close vents and fan based on temperature with hysteresis."""

    # Vents
    if not state["vents_open"] and temp >= config.TEMP_VENT_OPEN:
        hw["servo1"].value = config.SERVO_VENT_OPEN
        hw["servo2"].value = config.SERVO_VENT_OPEN
        state["vents_open"] = True
        log.info(f"Vents OPENED (temp={temp:.1f}°C)")

    elif state["vents_open"] and temp <= config.TEMP_VENT_CLOSE:
        hw["servo1"].value = config.SERVO_VENT_CLOSE
        hw["servo2"].value = config.SERVO_VENT_CLOSE
        state["vents_open"] = False
        log.info(f"Vents CLOSED (temp={temp:.1f}°C)")

    # Fan
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
    Read float switches and update indicator LEDs.
    Float switches are NO: is_active (pressed) = water is at that height.
    Logic: show the highest level that is triggered.
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
        hw["water_red"].on()       # Low — still some water
    else:
        hw["water_red"].on()       # Empty — below lowest sensor


# ── Chicken door ───────────────────────────────────────────────

def open_door(hw, state):
    """Drive actuator to open position, stop when limit switch triggers."""
    if state["door_open"] is True:
        return

    log.info("Opening chicken door...")
    hw["door_motor"].forward()

    start = time.time()
    while not hw["limit_open"].is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            log.warning("Door OPEN timeout — check limit switch wiring!")
            break
        time.sleep(0.1)

    hw["door_motor"].stop()
    state["door_open"] = True
    log.info("Chicken door OPEN")


def close_door(hw, state):
    """Drive actuator to closed position, stop when limit switch triggers."""
    if state["door_open"] is False:
        return

    log.info("Closing chicken door...")
    hw["door_motor"].backward()

    start = time.time()
    while not hw["limit_closed"].is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            log.warning("Door CLOSE timeout — check limit switch wiring!")
            break
        time.sleep(0.1)

    hw["door_motor"].stop()
    state["door_open"] = False
    log.info("Chicken door CLOSED")


def update_door(hw, state, now):
    """
    Decide whether to open or close the door.
    Uses LDR (dawn/dusk sensing) confirmed against clock limits.
    """
    hour = now.hour
    light_level = hw["ldr"].value   # 0.0 dark → 1.0 bright

    # Dawn: LDR says bright AND we're past the earliest allowed open hour
    is_dawn = (light_level >= config.LDR_DAWN_THRESHOLD) or (hour >= config.DOOR_OPEN_LATEST_HOUR)

    # Dusk: LDR says dark AND we're past the earliest allowed close hour
    is_dusk = (light_level <= config.LDR_DUSK_THRESHOLD) and (hour >= config.DOOR_CLOSE_EARLIEST_HOUR)

    if is_dawn and state["door_open"] is not True:
        open_door(hw, state)
    elif is_dusk and state["door_open"] is not False:
        close_door(hw, state)


# ── Lights ─────────────────────────────────────────────────────

def update_lights(hw, state, now):
    """Turn coop and run lights on/off according to the configured schedule."""
    current_mins = now.hour * 60 + now.minute
    on_mins  = config.LIGHT_ON_HOUR  * 60 + config.LIGHT_ON_MINUTE
    off_mins = config.LIGHT_OFF_HOUR * 60 + config.LIGHT_OFF_MINUTE

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
    Read potentiometer at food lever pivot.
    0.0 = lever fully down (feeder empty), 1.0 = lever up (feeder full).
    Calibrate FOOD_LOW_THRESHOLD in config.py after fitting the lever.
    """
    food_level = hw["food"].value

    if food_level < config.FOOD_LOW_THRESHOLD:
        hw["food_red"].on()
        hw["food_green"].off()
        log.info(f"Food LOW ({food_level:.2f}) — red light on")
    else:
        hw["food_red"].off()
        hw["food_green"].on()


# ── Startup checks ─────────────────────────────────────────────

def detect_door_state(hw, state):
    """Read limit switches at boot to determine current door position."""
    if hw["limit_open"].is_active:
        state["door_open"] = True
        log.info("Startup: door is OPEN")
    elif hw["limit_closed"].is_active:
        state["door_open"] = False
        log.info("Startup: door is CLOSED")
    else:
        state["door_open"] = None
        log.warning("Startup: door position unknown (neither limit switch active)")


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
            # DHT22 occasionally misreads — just skip this cycle
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
        # gpiozero cleans up GPIO automatically on object deletion
        log.info("Controller stopped.")
