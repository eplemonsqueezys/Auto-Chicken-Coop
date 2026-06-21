#!/usr/bin/env python3
"""
Hardware factory + simulation layer for the coop.

Every physical device is created through a make_* function below. Each one
checks the SIM flags in config.py to decide whether to talk to the real wired
hardware or hand back a software mock that just logs what it *would* do.

WORKFLOW
  1. Leave config.SIM_ALL = True and run coop_controller.py or debug_panel.py
     with nothing connected. The full control logic runs end to end; every
     hardware action is logged with a [SIM] prefix.
  2. Wire up one subsystem, set config.SIM_ALL = False, flip that subsystem's
     flag in config.SIM to False, and rerun. That piece now drives real
     hardware while everything else stays simulated.
  3. Repeat until every flag is False and the whole coop is live.

LIVE SIM VALUES
  While simulating, edit sim_state.json (same folder) to feed the control logic
  live sensor readings — it is re-read on every access, so you can change values
  while the program runs:
      temp_c    number  (°C)            -> vents / fan logic
      humidity  number  (%)
      light     0.0-1.0 (LDR)           -> door dawn/dusk logic
      food      0.0-1.0 (food pot)      -> food LEDs
      water     "Empty" | "Low" | "Mid" | "Full"  -> water LEDs
  If the file is missing or a key is absent, sensible defaults are used.
"""

import json
import os
import time
import logging

import config

log = logging.getLogger("coop.hw")

_SIM_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_state.json")

_SIM_DEFAULTS = {
    "temp_c": 22.0,
    "humidity": 50.0,
    "light": 0.5,
    "food": 0.8,
    "water": "Mid",
}


# ── helpers ────────────────────────────────────────────────────────────────
def use_sim(component):
    """True if the given subsystem should be simulated."""
    if getattr(config, "SIM_ALL", False):
        return True
    return config.SIM.get(component, False)


def _sim_values():
    """Read sim_state.json fresh each call; fall back to defaults."""
    vals = dict(_SIM_DEFAULTS)
    try:
        with open(_SIM_STATE_FILE) as f:
            vals.update(json.load(f))
    except FileNotFoundError:
        pass
    except (ValueError, OSError) as e:
        log.warning(f"[SIM] could not read sim_state.json ({e}); using defaults")
    return vals


def mode_banner():
    """One-line summary of what is real vs simulated, for startup logging."""
    if getattr(config, "SIM_ALL", False):
        return "SIMULATION MODE — all hardware simulated (config.SIM_ALL = True)"
    sim = [k for k in config.SIM if config.SIM[k]]
    real = [k for k in config.SIM if not config.SIM[k]]
    return f"MIXED MODE — real: {real or 'none'} | simulated: {sim or 'none'}"


# ── gpiozero pin factory (only set up when we actually touch real GPIO) ─────
_pin_factory_ready = False


def _ensure_pin_factory():
    global _pin_factory_ready
    if _pin_factory_ready:
        return
    from gpiozero import Device
    # Pi 5 uses the RP1 GPIO chip — RPi.GPIO doesn't work, lgpio does.
    if os.environ.get("GPIOZERO_PIN_FACTORY", "lgpio") == "lgpio":
        from gpiozero.pins.lgpio import LGPIOFactory
        Device.pin_factory = LGPIOFactory()
    _pin_factory_ready = True


# ── mock devices ───────────────────────────────────────────────────────────
class _MockChannel:
    def __init__(self, n):
        self.n = n
        self._dc = 0

    @property
    def duty_cycle(self):
        return self._dc

    @duty_cycle.setter
    def duty_cycle(self, v):
        self._dc = v
        log.info(f"[SIM] servo ch{self.n} duty_cycle={v} (~{v * 4096 // 65535} pulse)")


class MockPCA9685:
    def __init__(self):
        self.channels = [_MockChannel(i) for i in range(16)]
        self._freq = 0
        log.info("[SIM] PCA9685 created")

    @property
    def frequency(self):
        return self._freq

    @frequency.setter
    def frequency(self, f):
        self._freq = f
        log.info(f"[SIM] PCA9685 frequency={f}Hz")


class MockDHT22:
    @property
    def temperature(self):
        return float(_sim_values()["temp_c"])

    @property
    def humidity(self):
        return float(_sim_values()["humidity"])


class MockADC:
    """Stand-in for an MCP3008 channel."""
    def __init__(self, channel):
        self.channel = channel

    @property
    def value(self):
        v = _sim_values()
        if self.channel == config.MCP3008_LDR_CHANNEL:
            return float(v["light"])
        if self.channel == config.MCP3008_FOOD_CHANNEL:
            return float(v["food"])
        return 0.0


class MockOutput:
    """Stand-in for an OutputDevice (relay) or LED — same .on()/.off()/.value API."""
    def __init__(self, name, initial_value=False):
        self.name = name
        self.value = bool(initial_value)

    def on(self):
        self.value = True
        log.info(f"[SIM] {self.name} ON")

    def off(self):
        self.value = False
        log.info(f"[SIM] {self.name} OFF")


_WATER_LEVELS = {"Empty": 0, "Low": 1, "Mid": 2, "Full": 3}


class MockWaterSwitch:
    """Stand-in for a water-level float switch (gpiozero Button)."""
    def __init__(self, source):
        self.source = source  # water_low | water_mid | water_high

    @property
    def is_active(self):
        lvl = _WATER_LEVELS.get(_sim_values()["water"], 2)
        if self.source == "water_low":
            return lvl >= 1
        if self.source == "water_mid":
            return lvl >= 2
        if self.source == "water_high":
            return lvl >= 3
        return False


class _SimDoor:
    """Shared state so the mock motor and mock limit switches agree."""
    def __init__(self):
        self.pos = "closed"
        self.target = "closed"
        self.t0 = time.monotonic()

    def command(self, target):
        self.target = target
        self.t0 = time.monotonic()

    def _settle(self):
        if self.pos != self.target and time.monotonic() - self.t0 >= config.SIM_DOOR_TRAVEL_S:
            self.pos = self.target

    def stop(self):
        self._settle()

    def at(self, which):
        self._settle()
        return self.pos == which


_sim_door = _SimDoor()


class MockMotor:
    def __init__(self, name, door):
        self.name = name
        self.door = door

    def forward(self):
        self.door.command("open")
        log.info(f"[SIM] {self.name} motor FORWARD (opening)")

    def backward(self):
        self.door.command("closed")
        log.info(f"[SIM] {self.name} motor BACKWARD (closing)")

    def stop(self):
        self.door.stop()
        log.info(f"[SIM] {self.name} motor STOP (door now '{self.door.pos}')")


class MockLimitSwitch:
    def __init__(self, which, door):
        self.which = which  # "open" or "closed"
        self.door = door

    @property
    def is_active(self):
        return self.door.at(self.which)


# ── factories ──────────────────────────────────────────────────────────────
def make_pca():
    """PCA9685 servo driver (vents). Caller sets .frequency afterwards."""
    if use_sim("pca"):
        return MockPCA9685()
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    return PCA9685(busio.I2C(board.SCL, board.SDA))


def make_dht():
    if use_sim("dht"):
        return MockDHT22()
    import board
    import adafruit_dht
    return adafruit_dht.DHT22(board.D4)


def make_relay(component, pin, name):
    if use_sim(component):
        return MockOutput(name)
    _ensure_pin_factory()
    from gpiozero import OutputDevice
    return OutputDevice(pin, active_high=config.RELAY_ACTIVE_HIGH, initial_value=False)


def make_led(component, pin, name):
    if use_sim(component):
        return MockOutput(name)
    _ensure_pin_factory()
    from gpiozero import LED
    return LED(pin)


def make_water_switch(source, pin):
    if use_sim("water"):
        return MockWaterSwitch(source)
    _ensure_pin_factory()
    from gpiozero import Button
    return Button(pin, pull_up=False)


def make_motor(forward_pin, backward_pin):
    if use_sim("door"):
        return MockMotor("door", _sim_door)
    _ensure_pin_factory()
    from gpiozero import Motor
    return Motor(forward=forward_pin, backward=backward_pin)


def make_limit(which, pin):
    if use_sim("door"):
        return MockLimitSwitch(which, _sim_door)
    _ensure_pin_factory()
    from gpiozero import Button
    return Button(pin, pull_up=True)


def make_adc(channel):
    if use_sim("adc"):
        return MockADC(channel)
    _ensure_pin_factory()
    from gpiozero import MCP3008
    return MCP3008(channel=channel)
