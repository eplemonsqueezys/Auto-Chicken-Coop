#!/usr/bin/env python3
"""
Quick MG995 servo test — drive the servo straight off a Pi GPIO pin.

Wiring (NO L298N — a servo is not a DC motor):
    Orange (signal) -> GPIO pin below (default GPIO12 / physical pin 32)
    Red    (power)  -> external 5-6V supply +  (your buck converter output)
    Brown  (ground) -> supply ground AND a Pi GND pin (common ground required)

    Do NOT power the red wire from the Pi's own 5V pin — an MG995 can pull
    ~2.5A when it stalls and will brown out / reboot the Pi. Use the external
    5-6V rail and just share grounds.

Run:
    sudo GPIOZERO_PIN_FACTORY=lgpio python3 servo_test.py
    sudo GPIOZERO_PIN_FACTORY=lgpio python3 servo_test.py 13   # use GPIO13 instead

Then type:
    a number 0-180  -> move to that angle
    s               -> sweep 0 -> 180 -> 0
    c               -> centre (90)
    q               -> quit
"""

import os
import sys
import time

from gpiozero import Device, AngularServo
from gpiozero.pins.lgpio import LGPIOFactory

if os.environ.get("GPIOZERO_PIN_FACTORY", "lgpio") == "lgpio":
    Device.pin_factory = LGPIOFactory()

PIN = int(sys.argv[1]) if len(sys.argv) > 1 else 12

# MG995 accepts roughly a 0.5ms-2.5ms pulse for its full ~180° travel.
# If the servo buzzes or strains at the ends, narrow these toward 1.0/2.0ms.
servo = AngularServo(
    PIN,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.5 / 1000,
    max_pulse_width=2.5 / 1000,
)


def move(angle):
    angle = max(0, min(180, angle))
    servo.angle = angle
    print(f"  -> {angle}°")
    time.sleep(0.4)


print(f"MG995 servo test on GPIO{PIN}. Type 0-180, 's' sweep, 'c' centre, 'q' quit.")
move(90)

try:
    while True:
        cmd = input("angle> ").strip().lower()
        if cmd in ("q", "quit", "exit"):
            break
        elif cmd == "c":
            move(90)
        elif cmd == "s":
            for a in list(range(0, 181, 15)) + list(range(180, -1, -15)):
                move(a)
                time.sleep(0.1)
        elif cmd:
            try:
                move(int(float(cmd)))
            except ValueError:
                print("  enter a number 0-180, or s / c / q")
except (KeyboardInterrupt, EOFError):
    pass
finally:
    servo.detach()   # stop sending pulses so the servo relaxes
    print("\nDone.")
