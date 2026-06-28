#!/usr/bin/env python3
"""
Trip the fan relay (SONGLE SLA-05VDC-SL-C module) directly — quick bench test.

WIRING (relay module):
  IN  -> GPIO17 (physical pin 11)          [signal from the Pi]
  VCC -> Pi 5V (pin 2 or 4)                 [relay coil power]
  GND -> Pi GND (pin 6)                     [common ground]
  COM -> your external fan supply +         [switched side — Pi never sees this]
  NO  -> fan +
  fan - -> external supply -

  Active-HIGH (config.RELAY_ACTIVE_HIGH): GPIO17 HIGH energizes the relay = fan ON.
  If your fan runs when it should be OFF, flip RELAY_ACTIVE_HIGH to False in config.py.

NOTE: this assumes a relay *module* (has an IN pin + driver transistor + flyback
diode). A bare SLA relay's coil pulls ~70-90mA, which a Pi GPIO pin CANNOT drive
directly — that needs a transistor + diode. Almost all hobby relay boards are
modules, so you're fine if yours has IN/VCC/GND screw/header pins.

USAGE:
  sudo GPIOZERO_PIN_FACTORY=lgpio python3 relay_test.py on    # energize, hold until Enter
  sudo GPIOZERO_PIN_FACTORY=lgpio python3 relay_test.py off
  sudo GPIOZERO_PIN_FACTORY=lgpio python3 relay_test.py on 27 # use a different GPIO
"""

import os
import sys

from gpiozero import Device, OutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

import config

if os.environ.get("GPIOZERO_PIN_FACTORY", "lgpio") == "lgpio":
    Device.pin_factory = LGPIOFactory()

cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""
pin = int(sys.argv[2]) if len(sys.argv) > 2 else config.PIN_FAN_RELAY

if cmd not in ("on", "off"):
    print("usage: relay_test.py on|off [gpio_pin]")
    sys.exit(1)

relay = OutputDevice(pin, active_high=config.RELAY_ACTIVE_HIGH, initial_value=False)

if cmd == "on":
    relay.on()
    # Hold the relay energized while the script runs — gpiozero resets the pin
    # on exit, so keep it alive until you press Enter so you can see the fan run.
    print(f"Relay ON (GPIO{pin}) — fan should be running. Press Enter to turn off.")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    relay.off()
    print("Relay OFF")
else:
    relay.off()
    print(f"Relay OFF (GPIO{pin})")
