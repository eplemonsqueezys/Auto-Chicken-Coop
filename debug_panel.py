#!/usr/bin/env python3
"""
Chicken Coop — Web Debug Panel
Runs alongside coop_controller.py and serves a local web UI on port 5000.

Access from any device on your WiFi:  http://<pi-ip>:5000

Lets you:
  - See live sensor readings (temp, humidity, light level, food level, water level)
  - Manually open/close vents
  - Toggle fan on/off
  - Open/close the chicken door
  - Toggle coop and run lights
  - Override automation (hold a state regardless of sensors)
  - View the last 50 log lines

Run with:  sudo GPIOZERO_PIN_FACTORY=lgpio python3 debug_panel.py
Or run alongside the main controller by importing shared hardware.

NOTE: This panel takes direct control of hardware — don't run both
debug_panel.py AND coop_controller.py at the same time, as they'll
fight over GPIO. Use the panel for manual testing, the controller for
normal operation.
"""

import os
import time
import threading
import board
import busio
import adafruit_dht
from adafruit_pca9685 import PCA9685
from gpiozero import Device, Motor, Button, LED, OutputDevice, MCP3008
from gpiozero.pins.lgpio import LGPIOFactory
from flask import Flask, jsonify, render_template_string
import config

# Pi 5 lgpio backend
if os.environ.get("GPIOZERO_PIN_FACTORY", "lgpio") == "lgpio":
    Device.pin_factory = LGPIOFactory()

app = Flask(__name__)

# ── Shared hardware init (same as coop_controller.py) ──────────
i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 60

dht        = adafruit_dht.DHT22(board.D4)
fan        = OutputDevice(config.PIN_FAN_RELAY,       active_high=False, initial_value=False)
door_motor = Motor(forward=config.PIN_DOOR_IN1,       backward=config.PIN_DOOR_IN2)
coop_light = OutputDevice(config.PIN_COOP_LIGHT_RELAY, active_high=False, initial_value=False)
run_light  = OutputDevice(config.PIN_RUN_LIGHT_RELAY,  active_high=False, initial_value=False)

water_low    = Button(config.PIN_WATER_LOW,  pull_up=False)
water_mid    = Button(config.PIN_WATER_MID,  pull_up=False)
water_high   = Button(config.PIN_WATER_HIGH, pull_up=False)
water_led_r  = LED(config.PIN_WATER_LED_RED)
water_led_y  = LED(config.PIN_WATER_LED_YELLOW)
water_led_g  = LED(config.PIN_WATER_LED_GREEN)
food_led_r   = LED(config.PIN_FOOD_LED_RED)
food_led_g   = LED(config.PIN_FOOD_LED_GREEN)
limit_open   = Button(config.PIN_DOOR_LIMIT_OPEN,   pull_up=True)
limit_closed = Button(config.PIN_DOOR_LIMIT_CLOSED, pull_up=True)
ldr          = MCP3008(channel=config.MCP3008_LDR_CHANNEL)
food_pot     = MCP3008(channel=config.MCP3008_FOOD_CHANNEL)

# ── State ───────────────────────────────────────────────────────
state = {
    "vents_open":  False,
    "fan_on":      False,
    "door_open":   None,
    "coop_light":  False,
    "run_light":   False,
}

def set_servo(channel, pulse_value):
    duty = int(pulse_value * 65535 / 4096)
    pca.channels[channel].duty_cycle = duty

# ── Sensor reading ──────────────────────────────────────────────
def read_sensors():
    data = {}
    try:
        data["temp_c"]   = round(dht.temperature or 0, 1)
        data["humidity"] = round(dht.humidity or 0, 1)
    except Exception:
        data["temp_c"]   = None
        data["humidity"] = None

    data["light_level"] = round(ldr.value, 2)
    data["food_level"]  = round(food_pot.value, 2)

    if water_high.is_active:
        data["water"] = "Full"
    elif water_mid.is_active:
        data["water"] = "Mid"
    elif water_low.is_active:
        data["water"] = "Low"
    else:
        data["water"] = "Empty"

    data["limit_open"]   = limit_open.is_active
    data["limit_closed"] = limit_closed.is_active
    return data

# ── API routes ──────────────────────────────────────────────────

@app.route("/api/sensors")
def api_sensors():
    return jsonify(read_sensors())

@app.route("/api/state")
def api_state():
    return jsonify(state)

@app.route("/api/vents/open")
def vents_open():
    set_servo(config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_OPEN)
    set_servo(config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_OPEN)
    state["vents_open"] = True
    return jsonify({"ok": True, "vents_open": True})

@app.route("/api/vents/close")
def vents_close():
    set_servo(config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_CLOSE)
    set_servo(config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_CLOSE)
    state["vents_open"] = False
    return jsonify({"ok": True, "vents_open": False})

@app.route("/api/fan/on")
def fan_on():
    fan.on()
    state["fan_on"] = True
    return jsonify({"ok": True, "fan_on": True})

@app.route("/api/fan/off")
def fan_off():
    fan.off()
    state["fan_on"] = False
    return jsonify({"ok": True, "fan_on": False})

@app.route("/api/door/open")
def door_open():
    door_motor.forward()
    start = time.time()
    while not limit_open.is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            door_motor.stop()
            return jsonify({"ok": False, "error": "Timeout — check limit switch"})
        time.sleep(0.1)
    door_motor.stop()
    state["door_open"] = True
    return jsonify({"ok": True, "door_open": True})

@app.route("/api/door/close")
def door_close():
    door_motor.backward()
    start = time.time()
    while not limit_closed.is_active:
        if time.time() - start > config.DOOR_ACTUATOR_TIMEOUT:
            door_motor.stop()
            return jsonify({"ok": False, "error": "Timeout — check limit switch"})
        time.sleep(0.1)
    door_motor.stop()
    state["door_open"] = False
    return jsonify({"ok": True, "door_open": False})

@app.route("/api/door/stop")
def door_stop():
    door_motor.stop()
    return jsonify({"ok": True})

@app.route("/api/coop_light/on")
def coop_light_on():
    coop_light.on()
    state["coop_light"] = True
    return jsonify({"ok": True})

@app.route("/api/coop_light/off")
def coop_light_off():
    coop_light.off()
    state["coop_light"] = False
    return jsonify({"ok": True})

@app.route("/api/run_light/on")
def run_light_on():
    run_light.on()
    state["run_light"] = True
    return jsonify({"ok": True})

@app.route("/api/run_light/off")
def run_light_off():
    run_light.off()
    state["run_light"] = False
    return jsonify({"ok": True})

@app.route("/api/log")
def api_log():
    try:
        with open("/home/pi/coop.log") as f:
            lines = f.readlines()[-50:]
        return jsonify({"lines": [l.rstrip() for l in lines]})
    except FileNotFoundError:
        return jsonify({"lines": ["Log file not found — controller may not have run yet"]})

# ── HTML debug panel ────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coop Debug Panel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f1a; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; padding: 16px; }
  h1 { font-size: 18px; color: #7fbbff; margin-bottom: 16px; }
  h2 { font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }

  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; margin-bottom: 16px; }

  .card { background: #16213e; border: 1px solid #2a3a5c; border-radius: 8px; padding: 14px; }
  .card.green  { border-color: #2ecc71; }
  .card.orange { border-color: #e67e22; }
  .card.yellow { border-color: #f1c40f; }
  .card.teal   { border-color: #1abc9c; }
  .card.red    { border-color: #e74c3c; }
  .card.purple { border-color: #9b59b6; }

  .sensor-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #1a2a3a; font-size: 13px; }
  .sensor-row:last-child { border-bottom: none; }
  .val { font-weight: 700; color: #7fbbff; font-size: 15px; }
  .val.ok    { color: #2ecc71; }
  .val.warn  { color: #f1c40f; }
  .val.bad   { color: #e74c3c; }

  .btn-row { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
  button {
    padding: 8px 16px; border: none; border-radius: 5px;
    font-size: 12px; font-weight: 600; cursor: pointer;
    transition: opacity 0.15s;
  }
  button:hover { opacity: 0.85; }
  button:active { opacity: 0.7; }
  .btn-on  { background: #2ecc71; color: #0a2010; }
  .btn-off { background: #e74c3c; color: #fff; }
  .btn-act { background: #3498db; color: #fff; }
  .btn-warn { background: #e67e22; color: #fff; }

  .status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 6px; }
  .dot-on  { background: #2ecc71; box-shadow: 0 0 6px #2ecc71; }
  .dot-off { background: #444; }

  .log-box {
    background: #080810; border: 1px solid #2a3a5c; border-radius: 6px;
    padding: 10px; font-family: monospace; font-size: 11px; color: #aaa;
    height: 200px; overflow-y: auto; line-height: 1.6;
  }
  .log-box p { white-space: pre-wrap; word-break: break-all; }

  .refresh-note { font-size: 11px; color: #555; margin-top: 8px; }
  #last-update { color: #3498db; }
</style>
</head>
<body>
<h1>🐔 Coop Debug Panel</h1>

<div class="grid">

  <!-- Sensors -->
  <div class="card green">
    <h2>Sensors</h2>
    <div class="sensor-row"><span>Temperature</span><span class="val" id="temp">—</span></div>
    <div class="sensor-row"><span>Humidity</span><span class="val" id="humidity">—</span></div>
    <div class="sensor-row"><span>Light Level</span><span class="val" id="light">—</span></div>
    <div class="sensor-row"><span>Food Level</span><span class="val" id="food">—</span></div>
    <div class="sensor-row"><span>Water Level</span><span class="val" id="water">—</span></div>
    <div class="sensor-row"><span>Limit: Open</span><span class="val" id="lim-open">—</span></div>
    <div class="sensor-row"><span>Limit: Closed</span><span class="val" id="lim-closed">—</span></div>
  </div>

  <!-- Vents -->
  <div class="card green">
    <h2>Vent Sliders</h2>
    <div class="sensor-row">
      <span>Status</span>
      <span><span class="status-dot" id="vent-dot"></span><span id="vent-state">—</span></span>
    </div>
    <div class="btn-row">
      <button class="btn-on"  onclick="cmd('/api/vents/open')">Open Vents</button>
      <button class="btn-off" onclick="cmd('/api/vents/close')">Close Vents</button>
    </div>
  </div>

  <!-- Fan -->
  <div class="card green">
    <h2>Circulation Fan</h2>
    <div class="sensor-row">
      <span>Status</span>
      <span><span class="status-dot" id="fan-dot"></span><span id="fan-state">—</span></span>
    </div>
    <div class="btn-row">
      <button class="btn-on"  onclick="cmd('/api/fan/on')">Fan ON</button>
      <button class="btn-off" onclick="cmd('/api/fan/off')">Fan OFF</button>
    </div>
  </div>

  <!-- Door -->
  <div class="card orange">
    <h2>Chicken Door</h2>
    <div class="sensor-row">
      <span>Status</span>
      <span><span class="status-dot" id="door-dot"></span><span id="door-state">—</span></span>
    </div>
    <div class="btn-row">
      <button class="btn-on"  onclick="cmd('/api/door/open')">Open Door</button>
      <button class="btn-off" onclick="cmd('/api/door/close')">Close Door</button>
      <button class="btn-warn" onclick="cmd('/api/door/stop')">STOP</button>
    </div>
    <p style="font-size:11px;color:#888;margin-top:8px;">Open/Close waits for limit switch. STOP halts motor immediately.</p>
  </div>

  <!-- Lights -->
  <div class="card yellow">
    <h2>Lights</h2>
    <div class="sensor-row">
      <span>Coop Interior</span>
      <span><span class="status-dot" id="coop-light-dot"></span><span id="coop-light-state">—</span></span>
    </div>
    <div class="btn-row">
      <button class="btn-on"  onclick="cmd('/api/coop_light/on')">ON</button>
      <button class="btn-off" onclick="cmd('/api/coop_light/off')">OFF</button>
    </div>
    <div class="sensor-row" style="margin-top:10px">
      <span>Run Lights</span>
      <span><span class="status-dot" id="run-light-dot"></span><span id="run-light-state">—</span></span>
    </div>
    <div class="btn-row">
      <button class="btn-on"  onclick="cmd('/api/run_light/on')">ON</button>
      <button class="btn-off" onclick="cmd('/api/run_light/off')">OFF</button>
    </div>
  </div>

</div>

<!-- Log -->
<div class="card" style="margin-bottom:12px">
  <h2>Controller Log <button class="btn-act" style="float:right;padding:4px 10px;font-size:11px" onclick="loadLog()">Refresh</button></h2>
  <div class="log-box" id="log-box"><p>Loading...</p></div>
</div>

<p class="refresh-note">Sensors auto-refresh every 5s. Last update: <span id="last-update">—</span></p>

<script>
async function cmd(url) {
  try {
    const r = await fetch(url);
    const d = await r.json();
    if (!d.ok && d.error) alert('Error: ' + d.error);
    await loadState();
  } catch(e) { alert('Request failed: ' + e); }
}

async function loadSensors() {
  try {
    const r = await fetch('/api/sensors');
    const d = await r.json();

    const temp = d.temp_c;
    const tempEl = document.getElementById('temp');
    tempEl.textContent = temp !== null ? temp + ' °C' : 'Read error';
    tempEl.className = 'val' + (temp > 30 ? ' bad' : temp > 27 ? ' warn' : ' ok');

    document.getElementById('humidity').textContent = d.humidity !== null ? d.humidity + ' %' : '—';

    const light = d.light_level;
    const lightEl = document.getElementById('light');
    lightEl.textContent = light.toFixed(2) + (light > 0.6 ? ' (Dawn)' : light < 0.3 ? ' (Dusk)' : ' (Mid)');
    lightEl.className = 'val' + (light > 0.6 ? ' ok' : light < 0.3 ? ' warn' : '');

    const food = d.food_level;
    const foodEl = document.getElementById('food');
    foodEl.textContent = Math.round(food * 100) + ' %';
    foodEl.className = 'val' + (food < 0.25 ? ' bad' : food < 0.5 ? ' warn' : ' ok');

    const waterEl = document.getElementById('water');
    waterEl.textContent = d.water;
    waterEl.className = 'val' + (d.water === 'Full' ? ' ok' : d.water === 'Empty' ? ' bad' : ' warn');

    document.getElementById('lim-open').textContent   = d.limit_open   ? 'TRIGGERED' : 'Clear';
    document.getElementById('lim-closed').textContent = d.limit_closed ? 'TRIGGERED' : 'Clear';

    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
  } catch(e) { console.error(e); }
}

async function loadState() {
  try {
    const r = await fetch('/api/state');
    const s = await r.json();

    setDot('vent-dot',       s.vents_open);
    setDot('fan-dot',        s.fan_on);
    setDot('door-dot',       s.door_open);
    setDot('coop-light-dot', s.coop_light);
    setDot('run-light-dot',  s.run_light);

    document.getElementById('vent-state').textContent      = s.vents_open  ? 'Open'   : 'Closed';
    document.getElementById('fan-state').textContent       = s.fan_on      ? 'ON'     : 'OFF';
    document.getElementById('door-state').textContent      = s.door_open === null ? 'Unknown' : s.door_open ? 'Open' : 'Closed';
    document.getElementById('coop-light-state').textContent = s.coop_light ? 'ON' : 'OFF';
    document.getElementById('run-light-state').textContent  = s.run_light  ? 'ON' : 'OFF';
  } catch(e) { console.error(e); }
}

function setDot(id, on) {
  const el = document.getElementById(id);
  el.className = 'status-dot ' + (on ? 'dot-on' : 'dot-off');
}

async function loadLog() {
  try {
    const r = await fetch('/api/log');
    const d = await r.json();
    const box = document.getElementById('log-box');
    box.innerHTML = d.lines.map(l => `<p>${l}</p>`).join('');
    box.scrollTop = box.scrollHeight;
  } catch(e) { console.error(e); }
}

// Auto-refresh
loadSensors();
loadState();
loadLog();
setInterval(() => { loadSensors(); loadState(); }, 5000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    print("Coop Debug Panel running at http://0.0.0.0:5000")
    print("Find your Pi's IP with: hostname -I")
    app.run(host="0.0.0.0", port=5000, debug=False)
