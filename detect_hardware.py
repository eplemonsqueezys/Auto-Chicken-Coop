#!/usr/bin/env python3
"""
Auto-detect connected coop hardware and configure the system to match.

What it can POSITIVELY detect (things on a bus, with an address/ID):
  - PCA9685 servo driver on I2C (address 0x40)
  - An Arduino on USB serial running coop_arduino.ino (responds to "P" / streams "SENS")
  - Whether the SPI bus is enabled (for the MCP3008)

What it CANNOT detect (plain wires on GPIO — no ID to query):
  - Relays, float switches, limit switches, LEDs, the door motor, a bare DHT22,
    or whether an MCP3008 is actually wired to the SPI bus.
  These stay under manual control via the flags in config.py; the script prints
  recommendations for them.

It writes detected_hardware.json, which config.py reads on startup to override
the SIM / ARDUINO flags. Re-run any time you plug or unplug something.

Usage:
  python3 detect_hardware.py            # detect and write detected_hardware.json
  python3 detect_hardware.py --dry-run  # detect and print only, change nothing
  sudo ... if your user isn't in the i2c/dialout/spi groups
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(HERE, "detected_hardware.json")

PCA9685_ADDR = 0x40


# ── I2C ────────────────────────────────────────────────────────────────────
def scan_i2c(bus=1):
    """Return a set of 7-bit addresses present on the given I2C bus."""
    # Prefer smbus2 (no shell), fall back to the i2cdetect CLI.
    try:
        import smbus2
        found = set()
        b = smbus2.SMBus(bus)
        for addr in range(0x03, 0x78):
            try:
                b.read_byte(addr)
                found.add(addr)
            except OSError:
                pass
        b.close()
        return found
    except Exception:
        pass

    try:
        out = subprocess.check_output(["i2cdetect", "-y", str(bus)],
                                      stderr=subprocess.DEVNULL).decode()
    except Exception:
        return None  # no I2C tooling / bus not available
    found = set()
    for line in out.splitlines()[1:]:
        if ":" not in line:
            continue
        for tok in line.split(":", 1)[1].split():
            if re.fullmatch(r"[0-9a-fA-F]{2}", tok):
                found.add(int(tok, 16))
    return found


# ── SPI ────────────────────────────────────────────────────────────────────
def spi_enabled():
    return bool(glob.glob("/dev/spidev*"))


# ── Arduino over USB serial ─────────────────────────────────────────────────
def candidate_serial_ports():
    ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    return ports


def probe_arduino(port, baud=115200):
    """Open the port and see if it speaks the coop protocol.
    Returns dict: {responds: bool (PONG), streaming: bool (SENS frames)}."""
    try:
        import serial
    except ImportError:
        return None  # pyserial not installed
    result = {"responds": False, "streaming": False}
    try:
        ser = serial.Serial(port, baud, timeout=1)
    except Exception:
        return result
    try:
        time.sleep(2.0)            # board resets when the port opens
        ser.reset_input_buffer()
        ser.write(b"P\n")
        deadline = time.time() + 3.0
        while time.time() < deadline:
            line = ser.readline().decode("ascii", "ignore").strip()
            if not line:
                continue
            if line.startswith("PONG"):
                result["responds"] = True
            if line.startswith("SENS"):
                result["streaming"] = True
                result["responds"] = True  # it's clearly our sketch
            if result["responds"] and result["streaming"]:
                break
    finally:
        ser.close()
    return result


def detect_arduino():
    info = {"present": False, "port": None, "responds": False, "streaming": False}
    for port in candidate_serial_ports():
        info["present"] = True
        probe = probe_arduino(port)
        if probe is None:
            info["port"] = info["port"] or port  # pyserial missing; note the port
            continue
        if probe["responds"]:
            info.update(port=port, responds=True, streaming=probe["streaming"])
            return info
        info["port"] = info["port"] or port
    return info


# ── decide configuration ────────────────────────────────────────────────────
def decide(i2c, spi, ard):
    """Map detections to config overrides. Only override what we're sure of."""
    sim, arduino, notes = {}, {}, []
    port = None
    any_real = False

    pca_on_i2c = (i2c is not None and PCA9685_ADDR in i2c)

    # --- Servos ---
    if ard["responds"]:
        sim["pca"] = False
        arduino["servos"] = True
        port = ard["port"]
        any_real = True
        notes.append(f"Servos -> Arduino on {ard['port']} (PCA9685 shield on the Uno).")
    elif pca_on_i2c:
        sim["pca"] = False
        arduino["servos"] = False
        any_real = True
        notes.append("Servos -> Pi's own PCA9685 over I2C (0x40 found).")
    else:
        sim["pca"] = True
        notes.append("Servos -> SIMULATED (no PCA9685 on I2C, no Arduino).")

    # --- Sensors (ADC + DHT): only positively known via the Arduino sketch ---
    if ard["streaming"]:
        sim["adc"] = False
        arduino["adc"] = True
        sim["dht"] = False
        arduino["dht"] = True
        port = ard["port"]
        any_real = True
        notes.append("LDR/food + DHT22 -> Arduino (it's streaming SENS frames).")
    else:
        if spi:
            notes.append("SPI bus is ENABLED — if an MCP3008 is wired, set "
                         "SIM['adc']=False and ARDUINO['adc']=False to use it. "
                         "(Can't confirm the chip in software.)")
        else:
            notes.append("SPI bus not enabled — MCP3008 (LDR/food) stays simulated "
                         "until you enable SPI and wire it.")
        notes.append("DHT22 can't be auto-detected; leave SIM['dht'] as-is or set "
                     "False once it's wired to GPIO4.")

    if any_real:
        # Something real exists, so don't stay in full-sim mode.
        sim_all = False
    else:
        sim_all = None  # don't touch it

    overrides = {"SIM": sim, "ARDUINO": arduino}
    if port:
        overrides["ARDUINO_PORT"] = port
    if sim_all is not None:
        overrides["SIM_ALL"] = sim_all
    return overrides, notes


# ── report ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="detect and print only; don't write detected_hardware.json")
    args = ap.parse_args()

    print("Scanning for connected coop hardware...\n")

    i2c = scan_i2c(1)
    spi = spi_enabled()
    ard = detect_arduino()

    # --- detection report ---
    print("== Detected ==")
    if i2c is None:
        print("  I2C bus 1 : not available (enable I2C, or run with permissions)")
    else:
        addrs = ", ".join(f"0x{a:02x}" for a in sorted(i2c)) or "nothing"
        print(f"  I2C bus 1 : {addrs}")
        print(f"              PCA9685 (0x40): {'FOUND' if PCA9685_ADDR in i2c else 'not found'}")
    print(f"  SPI bus   : {'enabled' if spi else 'not enabled'}")
    if ard["present"]:
        state = ("running coop_arduino (PONG+SENS)" if ard["streaming"]
                 else "responds to ping" if ard["responds"]
                 else "serial device found, but not speaking coop protocol")
        print(f"  Arduino   : {ard['port'] or '(port found)'} — {state}")
        if ard["present"] and not ard["responds"]:
            print("              -> flash coop_arduino/coop_arduino.ino to enable it")
    else:
        print("  Arduino   : none on /dev/ttyACM* or /dev/ttyUSB*")

    overrides, notes = decide(i2c, spi, ard)

    print("\n== Plan ==")
    for n in notes:
        print(f"  - {n}")

    print("\n== Config overrides ==")
    print(json.dumps(overrides, indent=2))

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return

    payload = {
        "detected": {
            "i2c": [f"0x{a:02x}" for a in sorted(i2c)] if i2c else [],
            "spi": spi,
            "arduino": ard,
        },
        "overrides": overrides,
    }
    with open(OUT_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote {OUT_FILE}")
    print("Re-run coop_controller.py / debug_panel.py — config.py applies this automatically.")
    print("Delete that file to go back to the manual flags in config.py.")


if __name__ == "__main__":
    main()
