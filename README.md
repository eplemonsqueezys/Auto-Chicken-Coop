# Auto-Chicken-Coop

Raspberry Pi 5 controller for an automated chicken coop: temperature vents + fan,
dawn/dusk door, scheduled lights, water + food level indicators.

## Architecture: Pi + Arduino + servo shield

- **Raspberry Pi 5** — the brain. Runs the control logic (`coop_controller.py`)
  and a web debug panel (`debug_panel.py`). Drives the door motor (L298N),
  relays, switches, and LEDs directly over GPIO.
- **Arduino Uno + Adafruit PCA9685 servo shield** — drives the MG995 vent
  servos. The Pi talks to it over **USB serial**, so the noisy servo power stays
  off the Pi. (Optionally also reads the LDR, food pot, and DHT22.)
- Servo power (**5–6V**) comes from a buck converter into the shield's **V+**
  terminal — never the Pi, never 12V. See `HARDWARE.md` for the full power budget.

```
                 USB serial                I2C            5-6V V+
 Raspberry Pi  ───────────►  Arduino Uno ──────► PCA9685 ──────► MG995 servos
   (brain)                   + shield            shield          (vents)
       │
       ├─ GPIO ─► L298N ─► door motor / limit switches
       ├─ GPIO ─► relays (fan, coop light, run light)
       └─ GPIO ─► water float switches, LEDs   (MCP3008 optional for analog)
```

## Simulation & per-subsystem hardware

Everything runs with **no hardware connected**. Each subsystem is independently
`simulated` / `Arduino` / `native Pi`, controlled by flags in `config.py`:

- `SIM_ALL = True` — simulate everything (great first run).
- `SIM = {...}` — per-subsystem: `True` = simulated, `False` = real.
- `ARDUINO = {...}` — when a subsystem is real, route it to the Arduino (`True`)
  or native Pi hardware (`False`).

Resolution order per subsystem: **simulated → Arduino → native Pi**. If a
subsystem is set to the Arduino but the Arduino isn't plugged in, it **falls back
to simulation with a warning** instead of crashing.

While simulating, edit `sim_state.json` to feed live sensor values (temp,
humidity, light, food, water) and watch the logic react.

## Auto-detect hardware

Instead of editing flags by hand, plug things in and run:

```bash
python3 detect_hardware.py          # detects, writes detected_hardware.json
python3 detect_hardware.py --dry-run # just show the plan
```

It probes the I2C bus (PCA9685 @ 0x40), the USB serial ports (Arduino running
`coop_arduino.ino`), and SPI, then writes overrides that `config.py` applies
automatically. Delete `detected_hardware.json` to return to manual flags.
It can't detect plain-GPIO parts (relays, switches, LEDs, bare DHT) — those stay
manual.

## Bring-up

1. **Flash the Arduino:** open `coop_arduino/coop_arduino.ino`, install the
   *Adafruit PWM Servo Driver Library* and *DHT sensor library* (with their
   dependencies), and upload to the Uno with the shield stacked on it.
2. **Wire servo power:** buck converter 5–6V → shield **V+** screw terminal;
   servos into channels 0 and 1; common ground.
3. **Connect the Arduino to the Pi** by USB.
4. **On the Pi:**
   ```bash
   pip3 install pyserial --break-system-packages
   python3 detect_hardware.py        # finds the Arduino, sets the port + flags
   sudo GPIOZERO_PIN_FACTORY=lgpio python3 debug_panel.py
   ```
   Open `http://<pi-ip>:5000` and use the Vents Open/Close buttons.

> Clone Unos use a CH340 USB chip and show up as `/dev/ttyUSB0` rather than
> `/dev/ttyACM0`. `detect_hardware.py` finds the right port automatically.

## Running

```bash
# Main controller (the actual coop automation loop):
sudo GPIOZERO_PIN_FACTORY=lgpio python3 coop_controller.py

# Web debug panel (manual control + live sensors), don't run both at once:
sudo GPIOZERO_PIN_FACTORY=lgpio python3 debug_panel.py
```

## Files

| File | Purpose |
|------|---------|
| `coop_controller.py` | Main automation loop |
| `debug_panel.py` | Flask web panel for manual control + sensors |
| `hardware.py` | Device factory: sim / Arduino / native, per subsystem |
| `arduino_link.py` | Pi-side USB-serial link + adapters for the Arduino |
| `coop_arduino/coop_arduino.ino` | Arduino sketch (servo shield + sensors) |
| `detect_hardware.py` | Probe connected hardware, auto-write config overrides |
| `config.py` | Pins, thresholds, SIM/ARDUINO flags, calibration |
| `servo_vent.py` | Standalone direct-GPIO servo test (no Arduino) |
| `sim_state.json` | Live sensor values used in simulation |
| `HARDWARE.md` | Component specs, wiring, power budget |
| `wiring.md` / `parts-list.md` | Pin map and bill of materials |
