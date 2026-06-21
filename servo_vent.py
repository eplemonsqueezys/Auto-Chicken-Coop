#!/usr/bin/env python3
"""
Direct-drive an MG995 vent servo straight from the Pi — no Arduino/shield yet.

Sends the OPEN or CLOSE signal as a PWM pulse on a GPIO pin. Uses the same
SERVOMIN/SERVOMAX end-stop calibration as config.py, so "open"/"close" land in
the same spots the final PCA9685/Arduino setup will use.

WIRING
  Orange (signal) -> GPIO2 / SDA1 (physical pin 3)   [default; pass another pin below]
  Red    (power)  -> external 5-6V supply +
  Brown  (ground) -> external supply GND  AND a Pi GND pin (pin 6/9/14/...)
                     ^ common ground is REQUIRED or the signal has no reference.

  Do NOT power the servo from the Pi's 5V pin (MG995 stall current browns it out).

NOTE: I2C uses GPIO2/GPIO3. If you enabled I2C earlier this may conflict — if the
servo won't move, either turn I2C off (sudo raspi-config) or move the orange wire
to GPIO12 (pin 32) and run:  ... servo_vent.py open 12

USAGE
  sudo GPIOZERO_PIN_FACTORY=lgpio python3 servo_vent.py open
  sudo GPIOZERO_PIN_FACTORY=lgpio python3 servo_vent.py close
  sudo GPIOZERO_PIN_FACTORY=lgpio python3 servo_vent.py open 12   # use GPIO12
"""

import os
import sys
import time

from gpiozero import Device, Servo
from gpiozero.pins.lgpio import LGPIOFactory

import config

if os.environ.get("GPIOZERO_PIN_FACTORY", "lgpio") == "lgpio":
    Device.pin_factory = LGPIOFactory()

cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""
pin = int(sys.argv[2]) if len(sys.argv) > 2 else 2   # GPIO2 = SDA1 (pin 3)

if cmd not in ("open", "close"):
    print("usage: servo_vent.py open|close [gpio_pin]")
    sys.exit(1)

# Convert the PCA-style pulse counts in config.py to real pulse widths (seconds).
# A count is out of 4096 over one period; config's servos run at 60 Hz.
PERIOD = 1.0 / 60.0
close_pw = config.SERVOMIN / 4096.0 * PERIOD   # vent closed
open_pw  = config.SERVOMAX / 4096.0 * PERIOD   # vent open

servo = Servo(pin, min_pulse_width=close_pw, max_pulse_width=open_pw)

try:
    if cmd == "open":
        servo.max()        # max_pulse_width -> SERVOMAX -> open
        print(f"Vent OPEN  (GPIO{pin}, pulse {open_pw*1000:.2f} ms)")
    else:
        servo.min()        # min_pulse_width -> SERVOMIN -> close
        print(f"Vent CLOSE (GPIO{pin}, pulse {close_pw*1000:.2f} ms)")
    time.sleep(1.0)        # give the servo time to travel
finally:
    servo.detach()         # stop sending pulses so it isn't buzzing
