#!/usr/bin/env python3
# sudo GPIOZERO_PIN_FACTORY=lgpio python3 debug_panel.py
# Open http://<pi-ip>:5000 from any device on your network
# Don't run this at the same time as coop_controller.py

import time
import logging
from flask import Flask, jsonify, render_template_string

import config
import hardware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("coop.hw").info(hardware.mode_banner())

app = Flask(__name__)

pca = hardware.make_pca()
pca.frequency = 60

dht          = hardware.make_dht()
fan          = hardware.make_relay("fan",    config.PIN_FAN_RELAY, "fan")
door_motor   = hardware.make_motor(config.PIN_DOOR_IN1, config.PIN_DOOR_IN2)
coop_light   = hardware.make_relay("lights", config.PIN_COOP_LIGHT_RELAY, "coop_light")
run_light    = hardware.make_relay("lights", config.PIN_RUN_LIGHT_RELAY,  "run_light")
water_low    = hardware.make_water_switch("water_low",  config.PIN_WATER_LOW)
water_mid    = hardware.make_water_switch("water_mid",  config.PIN_WATER_MID)
water_high   = hardware.make_water_switch("water_high", config.PIN_WATER_HIGH)
limit_open   = hardware.make_limit("open",   config.PIN_DOOR_LIMIT_OPEN)
limit_closed = hardware.make_limit("closed", config.PIN_DOOR_LIMIT_CLOSED)
ldr          = hardware.make_adc(config.MCP3008_LDR_CHANNEL)
food_pot     = hardware.make_adc(config.MCP3008_FOOD_CHANNEL)

state = {
    "vents_open": False,
    "fan_on":     False,
    "door_open":  None,
    "coop_light": False,
    "run_light":  False,
}

def set_servo(channel, pulse):
    pca.channels[channel].duty_cycle = int(pulse * 65535 / 4096)

def read_sensors():
    data = {}
    try:
        data["temp_c"]   = round(dht.temperature or 0, 1)
        data["humidity"] = round(dht.humidity or 0, 1)
    except Exception:
        data["temp_c"] = data["humidity"] = None

    data["light_level"] = round(ldr.value, 2)
    data["food_level"]  = round(food_pot.value, 2)
    data["water"]       = "Full" if water_high.is_active else "Mid" if water_mid.is_active else "Low" if water_low.is_active else "Empty"
    data["limit_open"]  = limit_open.is_active
    data["limit_closed"]= limit_closed.is_active
    return data


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
    return jsonify({"ok": True})

@app.route("/api/vents/close")
def vents_close():
    set_servo(config.SERVO_VENT1_CHANNEL, config.SERVO_VENT_CLOSE)
    set_servo(config.SERVO_VENT2_CHANNEL, config.SERVO_VENT_CLOSE)
    state["vents_open"] = False
    return jsonify({"ok": True})

@app.route("/api/fan/on")
def api_fan_on():
    fan.on()
    state["fan_on"] = True
    return jsonify({"ok": True})

@app.route("/api/fan/off")
def api_fan_off():
    fan.off()
    state["fan_on"] = False
    return jsonify({"ok": True})

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
    return jsonify({"ok": True})

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
    return jsonify({"ok": True})

@app.route("/api/door/stop")
def door_stop():
    door_motor.stop()
    state["door_open"] = None
    return jsonify({"ok": True})

# --- Motor jog (manual test) -------------------------------------------------
# Non-blocking: just start/stop the motor. Use these to bench-test the L298N +
# motor before the limit switches are wired. Hold the button to run; release to
# stop. Does NOT wait on limit switches, so nothing blocks for 30s.
@app.route("/api/door/jog/forward")
def door_jog_forward():
    door_motor.forward()
    state["door_open"] = None
    return jsonify({"ok": True})

@app.route("/api/door/jog/backward")
def door_jog_backward():
    door_motor.backward()
    state["door_open"] = None
    return jsonify({"ok": True})

@app.route("/api/coop_light/on")
def coop_light_on():
    coop_light.on(); state["coop_light"] = True; return jsonify({"ok": True})

@app.route("/api/coop_light/off")
def coop_light_off():
    coop_light.off(); state["coop_light"] = False; return jsonify({"ok": True})

@app.route("/api/run_light/on")
def run_light_on():
    run_light.on(); state["run_light"] = True; return jsonify({"ok": True})

@app.route("/api/run_light/off")
def run_light_off():
    run_light.off(); state["run_light"] = False; return jsonify({"ok": True})

@app.route("/api/log")
def api_log():
    try:
        with open(config.LOG_PATH) as f:
            lines = f.readlines()[-50:]
        return jsonify({"lines": [l.rstrip() for l in lines]})
    except FileNotFoundError:
        return jsonify({"lines": ["No log yet"]})


HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coop</title>
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
  .row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #1a2a3a; font-size: 13px; }
  .row:last-child { border-bottom: none; }
  .val { font-weight: 700; color: #7fbbff; font-size: 15px; }
  .val.ok   { color: #2ecc71; }
  .val.warn { color: #f1c40f; }
  .val.bad  { color: #e74c3c; }
  .btns { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
  button { padding: 8px 16px; border: none; border-radius: 5px; font-size: 12px; font-weight: 600; cursor: pointer; }
  button:hover { opacity: 0.85; }
  .on   { background: #2ecc71; color: #0a2010; }
  .off  { background: #e74c3c; color: #fff; }
  .act  { background: #3498db; color: #fff; }
  .stop { background: #e67e22; color: #fff; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 6px; background: #444; }
  .dot.lit { background: #2ecc71; box-shadow: 0 0 6px #2ecc71; }
  .log { background: #080810; border: 1px solid #2a3a5c; border-radius: 6px; padding: 10px; font-family: monospace; font-size: 11px; color: #aaa; height: 200px; overflow-y: auto; line-height: 1.6; }
  .log p { white-space: pre-wrap; word-break: break-all; }
  .foot { font-size: 11px; color: #555; margin-top: 8px; }
  #ts { color: #3498db; }
</style>
</head>
<body>
<h1>Coop</h1>
<div class="grid">

  <div class="card green">
    <h2>Sensors</h2>
    <div class="row"><span>Temperature</span><span class="val" id="temp">—</span></div>
    <div class="row"><span>Humidity</span><span class="val" id="humidity">—</span></div>
    <div class="row"><span>Light</span><span class="val" id="light">—</span></div>
    <div class="row"><span>Food</span><span class="val" id="food">—</span></div>
    <div class="row"><span>Water</span><span class="val" id="water">—</span></div>
    <div class="row"><span>Limit open</span><span class="val" id="lim-open">—</span></div>
    <div class="row"><span>Limit closed</span><span class="val" id="lim-closed">—</span></div>
  </div>

  <div class="card green">
    <h2>Vents</h2>
    <div class="row"><span>Status</span><span><span class="dot" id="vent-dot"></span><span id="vent-s">—</span></span></div>
    <div class="btns">
      <button class="on"  onclick="cmd('/api/vents/open')">Open</button>
      <button class="off" onclick="cmd('/api/vents/close')">Close</button>
    </div>
  </div>

  <div class="card green">
    <h2>Fan</h2>
    <div class="row"><span>Status</span><span><span class="dot" id="fan-dot"></span><span id="fan-s">—</span></span></div>
    <div class="btns">
      <button class="on"  onclick="cmd('/api/fan/on')">On</button>
      <button class="off" onclick="cmd('/api/fan/off')">Off</button>
    </div>
  </div>

  <div class="card orange">
    <h2>Door</h2>
    <div class="row"><span>Status</span><span><span class="dot" id="door-dot"></span><span id="door-s">—</span></span></div>
    <div class="btns">
      <button class="on"   onclick="cmd('/api/door/open')">Open</button>
      <button class="off"  onclick="cmd('/api/door/close')">Close</button>
      <button class="stop" onclick="cmd('/api/door/stop')">Stop</button>
    </div>
    <div class="row" style="margin-top:10px"><span>Motor jog (hold)</span></div>
    <div class="btns">
      <button class="act"  id="jog-fwd">▲ Forward</button>
      <button class="act"  id="jog-bwd">▼ Backward</button>
    </div>
    <p class="foot">Hold to run, release to stop. For bench-testing the motor before limit switches are wired.</p>
  </div>

  <div class="card yellow">
    <h2>Lights</h2>
    <div class="row"><span>Coop</span><span><span class="dot" id="coop-dot"></span><span id="coop-s">—</span></span></div>
    <div class="btns">
      <button class="on"  onclick="cmd('/api/coop_light/on')">On</button>
      <button class="off" onclick="cmd('/api/coop_light/off')">Off</button>
    </div>
    <div class="row" style="margin-top:10px"><span>Run</span><span><span class="dot" id="run-dot"></span><span id="run-s">—</span></span></div>
    <div class="btns">
      <button class="on"  onclick="cmd('/api/run_light/on')">On</button>
      <button class="off" onclick="cmd('/api/run_light/off')">Off</button>
    </div>
  </div>

</div>

<div class="card" style="margin-bottom:12px">
  <h2>Log <button class="act" style="float:right;padding:4px 10px;font-size:11px" onclick="loadLog()">Refresh</button></h2>
  <div class="log" id="log"><p>Loading...</p></div>
</div>

<p class="foot">Refreshes every 5s &mdash; last update: <span id="ts">—</span></p>

<script>
async function cmd(url) {
  const r = await fetch(url).catch(e => { alert(e); return null; });
  if (!r) return;
  const d = await r.json();
  if (!d.ok && d.error) alert(d.error);
  loadState();
}

async function loadSensors() {
  const d = await fetch('/api/sensors').then(r => r.json()).catch(() => null);
  if (!d) return;

  const tempEl = document.getElementById('temp');
  tempEl.textContent = d.temp_c !== null ? d.temp_c + ' °C' : 'err';
  tempEl.className = 'val' + (d.temp_c > 30 ? ' bad' : d.temp_c > 27 ? ' warn' : ' ok');

  document.getElementById('humidity').textContent = d.humidity !== null ? d.humidity + '%' : '—';

  const lightEl = document.getElementById('light');
  lightEl.textContent = d.light_level.toFixed(2) + (d.light_level > 0.6 ? ' (dawn)' : d.light_level < 0.3 ? ' (dusk)' : '');
  lightEl.className = 'val' + (d.light_level > 0.6 ? ' ok' : d.light_level < 0.3 ? ' warn' : '');

  const foodEl = document.getElementById('food');
  foodEl.textContent = Math.round(d.food_level * 100) + '%';
  foodEl.className = 'val' + (d.food_level < 0.25 ? ' bad' : d.food_level < 0.5 ? ' warn' : ' ok');

  const waterEl = document.getElementById('water');
  waterEl.textContent = d.water;
  waterEl.className = 'val' + (d.water === 'Full' ? ' ok' : d.water === 'Empty' ? ' bad' : ' warn');

  document.getElementById('lim-open').textContent   = d.limit_open   ? 'triggered' : 'clear';
  document.getElementById('lim-closed').textContent = d.limit_closed ? 'triggered' : 'clear';
  document.getElementById('ts').textContent = new Date().toLocaleTimeString();
}

async function loadState() {
  const s = await fetch('/api/state').then(r => r.json()).catch(() => null);
  if (!s) return;

  dot('vent-dot', s.vents_open); document.getElementById('vent-s').textContent = s.vents_open ? 'Open' : 'Closed';
  dot('fan-dot',  s.fan_on);     document.getElementById('fan-s').textContent  = s.fan_on     ? 'On'   : 'Off';
  dot('door-dot', s.door_open);  document.getElementById('door-s').textContent = s.door_open === null ? 'Unknown' : s.door_open ? 'Open' : 'Closed';
  dot('coop-dot', s.coop_light); document.getElementById('coop-s').textContent = s.coop_light ? 'On' : 'Off';
  dot('run-dot',  s.run_light);  document.getElementById('run-s').textContent  = s.run_light  ? 'On' : 'Off';
}

function dot(id, on) {
  document.getElementById(id).className = 'dot' + (on ? ' lit' : '');
}

async function loadLog() {
  const d = await fetch('/api/log').then(r => r.json()).catch(() => null);
  if (!d) return;
  const box = document.getElementById('log');
  box.innerHTML = d.lines.map(l => `<p>${l}</p>`).join('');
  box.scrollTop = box.scrollHeight;
}

// Hold-to-run jog: start motor on press, stop on release/leave.
function holdJog(btnId, dir) {
  const btn = document.getElementById(btnId);
  const start = e => { e.preventDefault(); fetch('/api/door/jog/' + dir); };
  const stop  = e => { e.preventDefault(); fetch('/api/door/stop').then(loadState); };
  btn.addEventListener('mousedown', start);
  btn.addEventListener('mouseup', stop);
  btn.addEventListener('mouseleave', stop);
  btn.addEventListener('touchstart', start);
  btn.addEventListener('touchend', stop);
}
holdJog('jog-fwd', 'forward');
holdJog('jog-bwd', 'backward');

loadSensors(); loadState(); loadLog();
setInterval(() => { loadSensors(); loadState(); }, 5000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    print(f"http://0.0.0.0:5000  —  your Pi's IP: run 'hostname -I'")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
