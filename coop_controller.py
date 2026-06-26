#!/usr/bin/env python3
# Run: sudo GPIOZERO_PIN_FACTORY=lgpio python3 coop_controller.py
#
# Hardware is created through hardware.py, which simulates any subsystem whose
# flag is set in config.SIM / config.SIM_ALL. With SIM_ALL = True this runs the
# full control loop with nothing wired up.

import time
from datetime import datetime
import logging

import config
import hardware
import weather

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_PATH)]
)
log = logging.getLogger("coop")


def set_servo(pca, channel, pulse):
    # PCA9685 Python lib wants 16-bit duty cycle; Arduino used 12-bit raw pulse
    pca.channels[channel].duty_cycle = int(pulse * 65535 / 4096)


def init_hardware():
    log.info(hardware.mode_banner())
    hw = {}

    pca = hardware.make_pca()
    pca.frequency = 60
    hw["pca"] = pca

    # Sweep servos to both ends on startup so we know they're working
    set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_OPEN)
    set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_OPEN)
    time.sleep(1)
    set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_CLOSE)
    set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_CLOSE)
    time.sleep(1)

    hw["dht"]         = hardware.make_dht()
    hw["fan"]         = hardware.make_relay("fan", config.PIN_FAN_RELAY, "fan")
    hw["water_low"]   = hardware.make_water_switch("water_low",  config.PIN_WATER_LOW)
    hw["water_mid"]   = hardware.make_water_switch("water_mid",  config.PIN_WATER_MID)
    hw["water_high"]  = hardware.make_water_switch("water_high", config.PIN_WATER_HIGH)
    hw["water_red"]   = hardware.make_led("water", config.PIN_WATER_LED_RED,    "water_red")
    hw["water_yellow"]= hardware.make_led("water", config.PIN_WATER_LED_YELLOW, "water_yellow")
    hw["water_green"] = hardware.make_led("water", config.PIN_WATER_LED_GREEN,  "water_green")
    if config.DOOR_TYPE == "motor":
        hw["door_motor"]  = hardware.make_motor(config.PIN_DOOR_IN1, config.PIN_DOOR_IN2)
        hw["limit_open"]  = hardware.make_limit("open",   config.PIN_DOOR_LIMIT_OPEN)
        hw["limit_closed"]= hardware.make_limit("closed", config.PIN_DOOR_LIMIT_CLOSED)
    # DOOR_TYPE == "servo": the door is a servo on hw["pca"] channel
    # config.SERVO_DOOR_CHANNEL — no motor or limit switches needed.
    hw["coop_light"]  = hardware.make_relay("lights", config.PIN_COOP_LIGHT_RELAY, "coop_light")
    hw["run_light"]   = hardware.make_relay("lights", config.PIN_RUN_LIGHT_RELAY,  "run_light")
    hw["food_red"]    = hardware.make_led("food", config.PIN_FOOD_LED_RED,   "food_red")
    hw["food_green"]  = hardware.make_led("food", config.PIN_FOOD_LED_GREEN, "food_green")
    hw["ldr"]         = hardware.make_adc(config.MCP3008_LDR_CHANNEL)
    hw["food"]        = hardware.make_adc(config.MCP3008_FOOD_CHANNEL)

    return hw


def update_vents_and_fan(hw, state, temp):
    pca = hw["pca"]

    # Rain override: keep the coop dry — force vents shut and fan off, ignore temp.
    if config.RAIN_CLOSE_VENTS and weather.rain_expected():
        if state["vents_open"]:
            set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_CLOSE)
            set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_CLOSE)
            state["vents_open"] = False
            log.info("Vents closed (rain)")
        if state["fan_on"]:
            hw["fan"].off()
            state["fan_on"] = False
            log.info("Fan off (rain)")
        return

    if not state["vents_open"] and temp >= config.TEMP_VENT_OPEN:
        set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_OPEN)
        set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_OPEN)
        state["vents_open"] = True
        log.info(f"Vents open ({temp:.1f}C)")
    elif state["vents_open"] and temp <= config.TEMP_VENT_CLOSE:
        set_servo(pca, config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_CLOSE)
        set_servo(pca, config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_CLOSE)
        state["vents_open"] = False
        log.info(f"Vents closed ({temp:.1f}C)")

    if not state["fan_on"] and temp >= config.TEMP_FAN_ON:
        hw["fan"].on()
        state["fan_on"] = True
        log.info(f"Fan on ({temp:.1f}C)")
    elif state["fan_on"] and temp <= config.TEMP_FAN_OFF:
        hw["fan"].off()
        state["fan_on"] = False
        log.info(f"Fan off ({temp:.1f}C)")


def update_water_leds(hw):
    hw["water_red"].off()
    hw["water_yellow"].off()
    hw["water_green"].off()

    if hw["water_high"].is_active:
        hw["water_green"].on()
    elif hw["water_mid"].is_active:
        hw["water_yellow"].on()
    else:
        hw["water_red"].on()


def sweep_door_servo(hw, state, target_pulse):
    """Move the door servo gradually from its current pulse to target_pulse over
    config.DOOR_SERVO_TRAVEL_S seconds, so the door eases open/shut."""
    pca = hw["pca"]
    start = state.get("door_pulse", config.SERVO_DOOR_CLOSE)
    dur = max(0.1, config.DOOR_SERVO_TRAVEL_S)
    steps = max(1, int(dur / 0.05))   # ~20 updates/sec
    for i in range(1, steps + 1):
        p = start + (target_pulse - start) * i / steps
        set_servo(pca, config.SERVO_DOOR_CHANNEL, int(p))
        state["door_pulse"] = p
        time.sleep(dur / steps)
    state["door_pulse"] = target_pulse


def open_door(hw, state):
    if state["door_open"] is True:
        return
    if config.DOOR_TYPE == "servo":
        log.info("Opening door (servo, gradual)")
        sweep_door_servo(hw, state, config.SERVO_DOOR_OPEN)
        state["door_open"] = True
        return
    log.info("Opening door")
    hw["door_motor"].forward()
    start = time.time()
    while not hw["limit_open"].is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            log.warning("Door open timeout — limit switch not hit")
            break
        time.sleep(0.1)
    hw["door_motor"].stop()
    state["door_open"] = True


def close_door(hw, state):
    if state["door_open"] is False:
        return
    if config.DOOR_TYPE == "servo":
        log.info("Closing door (servo, gradual)")
        sweep_door_servo(hw, state, config.SERVO_DOOR_CLOSE)
        state["door_open"] = False
        return
    log.info("Closing door")
    hw["door_motor"].backward()
    start = time.time()
    while not hw["limit_closed"].is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            log.warning("Door close timeout — limit switch not hit")
            break
        time.sleep(0.1)
    hw["door_motor"].stop()
    state["door_open"] = False


def update_door(hw, state, now):
    # Preferred: real sunrise/sunset for the location, open at dawn+offset and
    # close at dusk+offset. Falls back to the LDR/clock logic if weather is down.
    if config.USE_SUN_SCHEDULE:
        should_open = weather.door_should_be_open(now)
        if should_open is not None:
            if should_open and state["door_open"] is not True:
                open_door(hw, state)
            elif not should_open and state["door_open"] is not False:
                close_door(hw, state)
            return
        log.warning("No sun times available — falling back to LDR for the door")

    light = hw["ldr"].value
    hour  = now.hour
    is_dawn = light >= config.LDR_DAWN_THRESHOLD or hour >= config.DOOR_OPEN_LATEST_HOUR
    is_dusk = light <= config.LDR_DUSK_THRESHOLD and hour >= config.DOOR_CLOSE_EARLIEST_HOUR

    if is_dawn and state["door_open"] is not True:
        open_door(hw, state)
    elif is_dusk and state["door_open"] is not False:
        close_door(hw, state)


def update_lights(hw, state, now):
    mins    = now.hour * 60 + now.minute
    on_min  = config.LIGHT_ON_HOUR  * 60 + config.LIGHT_ON_MINUTE
    off_min = config.LIGHT_OFF_HOUR * 60 + config.LIGHT_OFF_MINUTE
    on      = on_min <= mins < off_min

    if on and not state["lights_on"]:
        hw["coop_light"].on()
        hw["run_light"].on()
        state["lights_on"] = True
        log.info("Lights on")
    elif not on and state["lights_on"]:
        hw["coop_light"].off()
        hw["run_light"].off()
        state["lights_on"] = False
        log.info("Lights off")


def update_food_leds(hw):
    if hw["food"].value < config.FOOD_LOW_THRESHOLD:
        hw["food_red"].on()
        hw["food_green"].off()
    else:
        hw["food_red"].off()
        hw["food_green"].on()


def main():
    hw = init_hardware()
    state = {"vents_open": False, "fan_on": False, "door_open": None,
             "lights_on": False, "door_pulse": config.SERVO_DOOR_CLOSE}

    if config.DOOR_TYPE == "motor":
        if hw["limit_open"].is_active:
            state["door_open"] = True
        elif hw["limit_closed"].is_active:
            state["door_open"] = False
        else:
            log.warning("Door position unknown at startup")
    else:
        log.info("Servo door — position set on first dawn/dusk check")

    log.info("Running")

    while True:
        now = weather.local_now()

        try:
            if config.USE_WEATHER_TEMP:
                temp = weather.temperature_c()
                if temp is not None:
                    log.info(f"Outdoor temp ({config.LOCATION_ZIP}): {temp:.1f}C")
            else:
                temp = hw["dht"].temperature
                if temp is not None:
                    hum = hw["dht"].humidity
                    hum_s = f"{hum:.1f}" if hum is not None else "n/a"
                    log.info(f"Temp: {temp:.1f}C  Humidity: {hum_s}%")
            if temp is not None:
                update_vents_and_fan(hw, state, temp)
        except RuntimeError:
            pass

        update_water_leds(hw)
        update_door(hw, state, now)
        update_lights(hw, state, now)
        update_food_leds(hw)

        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.exception(e)
