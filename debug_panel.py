#!/usr/bin/env python3
# sudo GPIOZERO_PIN_FACTORY=lgpio python3 debug_panel.py
# Open http://<pi-ip>:5000 from any device on your network
# Don't run this at the same time as coop_controller.py

import time
import logging
import threading
from flask import Flask, jsonify, render_template_string, request

from datetime import timedelta

import config
import hardware
import weather
import coop_controller as cc   # reuse the real vent/fan automation logic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("coop.hw").info(hardware.mode_banner())

app = Flask(__name__)

pca = hardware.make_pca()
pca.frequency = 60

dht          = hardware.make_dht()
fan          = hardware.make_relay("fan",    config.PIN_FAN_RELAY, "fan")
coop_light   = hardware.make_relay("lights", config.PIN_COOP_LIGHT_RELAY, "coop_light")
run_light    = hardware.make_relay("lights", config.PIN_RUN_LIGHT_RELAY,  "run_light")
water_low    = hardware.make_water_switch("water_low",  config.PIN_WATER_LOW)
water_mid    = hardware.make_water_switch("water_mid",  config.PIN_WATER_MID)
water_high   = hardware.make_water_switch("water_high", config.PIN_WATER_HIGH)
# Door: a servo (on the shield) or an L298N motor + limit switches.
door_motor   = hardware.make_motor(config.PIN_DOOR_IN1, config.PIN_DOOR_IN2) if config.DOOR_TYPE == "motor" else None
limit_open   = hardware.make_limit("open",   config.PIN_DOOR_LIMIT_OPEN)   if config.DOOR_TYPE == "motor" else None
limit_closed = hardware.make_limit("closed", config.PIN_DOOR_LIMIT_CLOSED) if config.DOOR_TYPE == "motor" else None
ldr          = hardware.make_adc(config.MCP3008_LDR_CHANNEL)
food_pot     = hardware.make_adc(config.MCP3008_FOOD_CHANNEL)

state = {
    "vents_open": False,
    "fan_on":     False,
    "door_open":  None,
    "coop_light": False,
    "run_light":  False,
}

# Climate control: a settable test temperature (no real DHT yet) plus the live
# thresholds. cc.update_vents_and_fan() runs the SAME automation as the main
# controller, driving the servos + fan through these objects.
climate = {"temp": 22.0}
_hw_climate = {"pca": pca, "fan": fan}

_THRESHOLD_KEYS = {
    "vent_open":  "TEMP_VENT_OPEN",
    "vent_close": "TEMP_VENT_CLOSE",
    "fan_on":     "TEMP_FAN_ON",
    "fan_off":    "TEMP_FAN_OFF",
}

def run_climate_logic():
    """Apply the vent/fan automation at the current test temperature."""
    cc.update_vents_and_fan(_hw_climate, state, climate["temp"])

# Schedule simulation: override the time-of-day to test the door's dawn/dusk
# behavior without waiting for actual sunrise/sunset.
sched = {"sim_minutes": None}   # None -> use real local time

def eval_now():
    base = weather.local_now()
    if sched["sim_minutes"] is not None:
        m = int(sched["sim_minutes"])
        base = base.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0)
    return base

def apply_schedule():
    """Open/close the servo door based on the (possibly simulated) time vs the
    real sunrise+offset / sunset+offset window."""
    if config.DOOR_TYPE != "servo":
        return
    should_open = weather.door_should_be_open(eval_now())
    if should_open is None:
        return
    if should_open and state["door_open"] is not True:
        door_move(config.SERVO_DOOR_OPEN, True)
    elif not should_open and state["door_open"] is not False:
        door_move(config.SERVO_DOOR_CLOSE, False)

def set_servo(channel, pulse):
    pca.channels[channel].duty_cycle = int(pulse * 65535 / 4096)

# Servo-door state: eased open/shut over config.DOOR_SERVO_TRAVEL_S (no limits).
_door = {"pulse": config.SERVO_DOOR_CLOSE, "moving": False, "stop": False, "thread": None}

def _door_sweep(target_pulse):
    _door["moving"] = True
    start = _door["pulse"]
    dur = max(0.1, config.DOOR_SERVO_TRAVEL_S)
    steps = max(1, int(dur / 0.05))      # ~20 updates/sec
    for i in range(1, steps + 1):
        if _door["stop"]:
            break
        p = start + (target_pulse - start) * i / steps
        _door["pulse"] = p
        set_servo(config.SERVO_DOOR_CHANNEL, int(p))
        time.sleep(dur / steps)
    _door["moving"] = False

def door_move(target_pulse, opening):
    """Interrupt any current move and start easing toward target_pulse."""
    _door["stop"] = True
    t = _door["thread"]
    if t and t.is_alive():
        t.join(timeout=2)
    _door["stop"] = False
    state["door_open"] = opening
    th = threading.Thread(target=_door_sweep, args=(target_pulse,), daemon=True)
    _door["thread"] = th
    th.start()

def read_sensors():
    data = {}
    try:
        t = dht.temperature
        h = dht.humidity
        # No real DHT wired -> reading is None; fall back to the test temperature.
        data["temp_c"]   = round(t, 1) if t is not None else round(climate["temp"], 1)
        data["humidity"] = round(h, 1) if h is not None else None
    except Exception:
        data["temp_c"] = climate["temp"]
        data["humidity"] = None

    data["light_level"] = round(ldr.value, 2)
    data["food_level"]  = round(food_pot.value, 2)
    data["water"]       = "Full" if water_high.is_active else "Mid" if water_mid.is_active else "Low" if water_low.is_active else "Empty"
    data["limit_open"]  = limit_open.is_active   if limit_open   else None
    data["limit_closed"]= limit_closed.is_active if limit_closed else None
    return data


@app.route("/api/sensors")
def api_sensors():
    return jsonify(read_sensors())

@app.route("/api/state")
def api_state():
    return jsonify(state)

@app.route("/api/climate")
def api_climate():
    return jsonify({
        "temp": round(climate["temp"], 1),
        "thresholds": {k: getattr(config, attr) for k, attr in _THRESHOLD_KEYS.items()},
        "vents_open": state["vents_open"],
        "fan_on": state["fan_on"],
    })

@app.route("/api/climate/temp")
def api_climate_temp():
    try:
        climate["temp"] = float(request.args.get("value"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad temperature value"})
    run_climate_logic()
    return jsonify({"ok": True, "vents_open": state["vents_open"], "fan_on": state["fan_on"]})

@app.route("/api/climate/threshold")
def api_climate_threshold():
    key = request.args.get("key")
    if key not in _THRESHOLD_KEYS:
        return jsonify({"ok": False, "error": "unknown threshold"})
    try:
        val = float(request.args.get("value"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad value"})
    setattr(config, _THRESHOLD_KEYS[key], val)   # live for this session
    run_climate_logic()
    return jsonify({"ok": True})

@app.route("/api/climate/pull_temp")
def api_climate_pull():
    t = weather.temperature_c()
    if t is None:
        return jsonify({"ok": False, "error": "no weather data (offline?)"})
    climate["temp"] = round(t, 1)
    run_climate_logic()
    return jsonify({"ok": True, "temp": climate["temp"]})

@app.route("/api/schedule")
def api_schedule():
    sunrise, sunset = weather.sun_times()
    open_at, close_at = weather.door_window(sunrise, sunset)
    now = eval_now()
    fmt = lambda d: d.strftime("%H:%M") if d else "—"
    return jsonify({
        "zip": config.LOCATION_ZIP,
        "now": fmt(now),
        "now_min": now.hour * 60 + now.minute,
        "sim": sched["sim_minutes"] is not None,
        "sunrise": fmt(sunrise), "sunset": fmt(sunset),
        "open_at": fmt(open_at), "close_at": fmt(close_at),
        "dawn_offset": config.DOOR_OPEN_AFTER_DAWN_MIN,
        "dusk_offset": config.DOOR_CLOSE_AFTER_DUSK_MIN,
        "door_open": state["door_open"],
    })

@app.route("/api/schedule/time")
def api_schedule_time():
    try:
        sched["sim_minutes"] = max(0, min(1439, int(float(request.args.get("value")))))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad time"})
    apply_schedule()
    return jsonify({"ok": True})

@app.route("/api/schedule/realtime")
def api_schedule_realtime():
    sched["sim_minutes"] = None
    apply_schedule()
    return jsonify({"ok": True})

@app.route("/api/location")
def api_location():
    return jsonify({
        "zip": config.LOCATION_ZIP, "place": getattr(config, "LOCATION_PLACE", ""),
        "lat": config.LATITUDE, "lon": config.LONGITUDE, "tz": config.TIMEZONE,
        "dawn_offset": config.DOOR_OPEN_AFTER_DAWN_MIN,
        "dusk_offset": config.DOOR_CLOSE_AFTER_DUSK_MIN,
    })

@app.route("/api/location/set")
def api_location_set():
    zipc = (request.args.get("zip") or "").strip()
    tz   = (request.args.get("timezone") or config.TIMEZONE).strip()
    updates = {"TIMEZONE": tz}
    if zipc:
        try:
            g = weather.geocode_zip(zipc)
        except Exception as e:
            return jsonify({"ok": False, "error": f"couldn't look up ZIP {zipc} ({e})"})
        updates.update(LOCATION_ZIP=g["zip"], LATITUDE=g["latitude"],
                       LONGITUDE=g["longitude"], LOCATION_PLACE=g["place"])
    config.save_settings(updates)
    weather.reset_cache()          # new location -> refetch temp/sun times
    return jsonify({"ok": True, "zip": config.LOCATION_ZIP,
                    "place": config.LOCATION_PLACE, "tz": config.TIMEZONE})

@app.route("/api/location/offsets")
def api_location_offsets():
    upd = {}
    try:
        if request.args.get("dawn") is not None:
            upd["DOOR_OPEN_AFTER_DAWN_MIN"] = int(float(request.args.get("dawn")))
        if request.args.get("dusk") is not None:
            upd["DOOR_CLOSE_AFTER_DUSK_MIN"] = int(float(request.args.get("dusk")))
    except ValueError:
        return jsonify({"ok": False, "error": "bad offset"})
    config.save_settings(upd)
    apply_schedule()
    return jsonify({"ok": True})

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

@app.route("/api/door")
def api_door():
    return jsonify({"type": config.DOOR_TYPE, "travel": config.DOOR_SERVO_TRAVEL_S,
                    "moving": _door["moving"], "open": state["door_open"]})

@app.route("/api/door/open")
def door_open():
    if config.DOOR_TYPE == "servo":
        door_move(config.SERVO_DOOR_OPEN, True)
        return jsonify({"ok": True})
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
    if config.DOOR_TYPE == "servo":
        door_move(config.SERVO_DOOR_CLOSE, False)
        return jsonify({"ok": True})
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
    if config.DOOR_TYPE == "servo":
        _door["stop"] = True          # halt an in-progress sweep
        return jsonify({"ok": True})
    door_motor.stop()
    state["door_open"] = None
    return jsonify({"ok": True})

@app.route("/api/door/travel")
def door_travel():
    try:
        config.DOOR_SERVO_TRAVEL_S = max(0.1, float(request.args.get("value")))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad value"})
    return jsonify({"ok": True, "travel": config.DOOR_SERVO_TRAVEL_S})

# --- Motor jog (manual test, "motor" door type only) -------------------------
@app.route("/api/door/jog/forward")
def door_jog_forward():
    if config.DOOR_TYPE != "motor":
        return jsonify({"ok": False, "error": "servo door — use Open/Close"})
    door_motor.forward()
    state["door_open"] = None
    return jsonify({"ok": True})

@app.route("/api/door/jog/backward")
def door_jog_backward():
    if config.DOOR_TYPE != "motor":
        return jsonify({"ok": False, "error": "servo door — use Open/Close"})
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
  .slider { width: 100%; margin: 10px 0; accent-color: #2ecc71; }
  .thr { width: 72px; background: #0d1526; color: #7fbbff; border: 1px solid #2a3a5c;
         border-radius: 4px; padding: 4px 6px; text-align: right; font-size: 13px; }
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
    <h2>Climate Control</h2>
    <div class="row"><span>Test temp</span><span class="val" id="cl-temp">—</span></div>
    <input type="range" id="cl-slider" class="slider" min="0" max="45" step="0.5">
    <div class="btns"><button class="act" id="cl-pull">Pull live temp ({{ zip }})</button></div>
    <div class="row"><span>Vent open &ge;</span><input class="thr" id="thr-vent_open" type="number" step="0.5"></div>
    <div class="row"><span>Vent close &le;</span><input class="thr" id="thr-vent_close" type="number" step="0.5"></div>
    <div class="row"><span>Fan on &ge;</span><input class="thr" id="thr-fan_on" type="number" step="0.5"></div>
    <div class="row"><span>Fan off &le;</span><input class="thr" id="thr-fan_off" type="number" step="0.5"></div>
    <div class="btns"><button class="act" id="thr-save">Save thresholds</button></div>
    <p class="foot">Drag the temp to watch vents &amp; fan react. Thresholds apply live (reset on restart).</p>
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
    {% if door_type == 'servo' %}
    <div class="row" style="margin-top:10px"><span>Travel time (s)</span><input class="thr" id="door-travel" type="number" step="0.5" min="0.5"></div>
    <div class="btns"><button class="act" id="door-travel-save">Save time</button></div>
    <p class="foot">Servo door on channel 3 — eases open/shut over the travel time. Stop halts it mid-move.</p>
    {% else %}
    <div class="row" style="margin-top:10px"><span>Motor jog (hold)</span></div>
    <div class="btns">
      <button class="act"  id="jog-fwd">▲ Forward</button>
      <button class="act"  id="jog-bwd">▼ Backward</button>
    </div>
    <p class="foot">Hold to run, release to stop. For bench-testing the motor before limit switches are wired.</p>
    {% endif %}
  </div>

  <div class="card green">
    <h2>Location</h2>
    <div class="row"><span>Place</span><span class="val" id="loc-place">—</span></div>
    <div class="row"><span>ZIP</span><input class="thr" id="loc-zip" type="text" style="width:90px;text-align:left"></div>
    <div class="row"><span>Timezone</span><input class="thr" id="loc-tz" type="text" style="width:160px;text-align:left"></div>
    <div class="btns"><button class="act" id="loc-apply">Apply location</button></div>
    <div class="row" style="margin-top:8px"><span>Open after dawn (min)</span><input class="thr" id="loc-dawn" type="number" step="5"></div>
    <div class="row"><span>Close after dusk (min)</span><input class="thr" id="loc-dusk" type="number" step="5"></div>
    <div class="btns"><button class="act" id="loc-off-save">Save offsets</button></div>
    <p class="foot">Set by setup.sh on install; change here for testing. ZIP is geocoded to lat/lon.</p>
  </div>

  <div class="card orange">
    <h2>Door Schedule</h2>
    <div class="row"><span>Location (ZIP)</span><span class="val" id="sc-zip">—</span></div>
    <div class="row"><span>Sunrise</span><span class="val ok" id="sc-sunrise">—</span></div>
    <div class="row"><span>Sunset</span><span class="val warn" id="sc-sunset">—</span></div>
    <div class="row"><span>Open at (dawn+<span id="sc-dawnoff">?</span>m)</span><span class="val ok" id="sc-open">—</span></div>
    <div class="row"><span>Close at (dusk+<span id="sc-duskoff">?</span>m)</span><span class="val warn" id="sc-close">—</span></div>
    <div class="row"><span>Time</span><span class="val" id="sc-now">—</span></div>
    <input type="range" id="sc-slider" class="slider" min="0" max="1439" step="5">
    <div class="btns"><button class="act" id="sc-realtime">Use real time</button></div>
    <p class="foot">Drag to simulate the time of day and watch the door open at dawn+offset / close at dusk+offset. "Use real time" returns to the live clock.</p>
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

async function loadClimate() {
  const c = await fetch('/api/climate').then(r => r.json()).catch(() => null);
  if (!c) return;
  document.getElementById('cl-temp').textContent = c.temp + ' °C';
  const sl = document.getElementById('cl-slider');
  if (document.activeElement !== sl) sl.value = c.temp;
  for (const k in c.thresholds) {
    const el = document.getElementById('thr-' + k);
    if (el && document.activeElement !== el) el.value = c.thresholds[k];
  }
}

let clTimer = null;
document.getElementById('cl-slider').addEventListener('input', e => {
  document.getElementById('cl-temp').textContent = e.target.value + ' °C';
  clearTimeout(clTimer);
  clTimer = setTimeout(() => {
    fetch('/api/climate/temp?value=' + e.target.value).then(() => { loadState(); loadSensors(); });
  }, 120);
});

document.getElementById('thr-save').addEventListener('click', async () => {
  for (const k of ['vent_open', 'vent_close', 'fan_on', 'fan_off']) {
    const v = document.getElementById('thr-' + k).value;
    await fetch('/api/climate/threshold?key=' + k + '&value=' + v);
  }
  loadState(); loadClimate();
});

const clPull = document.getElementById('cl-pull');
if (clPull) clPull.addEventListener('click', () => {
  fetch('/api/climate/pull_temp').then(r => r.json()).then(d => {
    if (d.ok) { document.getElementById('cl-slider').value = d.temp; loadClimate(); loadState(); loadSensors(); }
    else alert(d.error || 'no weather data');
  });
});

function hhmm(m) {
  return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
}
async function loadSchedule() {
  const s = await fetch('/api/schedule').then(r => r.json()).catch(() => null);
  if (!s) return;
  document.getElementById('sc-zip').textContent = s.zip;
  document.getElementById('sc-sunrise').textContent = s.sunrise;
  document.getElementById('sc-sunset').textContent = s.sunset;
  document.getElementById('sc-open').textContent = s.open_at;
  document.getElementById('sc-close').textContent = s.close_at;
  document.getElementById('sc-dawnoff').textContent = s.dawn_offset;
  document.getElementById('sc-duskoff').textContent = s.dusk_offset;
  document.getElementById('sc-now').textContent = s.now + (s.sim ? ' (sim)' : '');
  const sl = document.getElementById('sc-slider');
  if (document.activeElement !== sl) sl.value = s.now_min;
}
let scTimer = null;
document.getElementById('sc-slider').addEventListener('input', e => {
  const m = +e.target.value;
  document.getElementById('sc-now').textContent = hhmm(m) + ' (sim)';
  clearTimeout(scTimer);
  scTimer = setTimeout(() => fetch('/api/schedule/time?value=' + m).then(() => { loadState(); loadSchedule(); }), 150);
});
document.getElementById('sc-realtime').addEventListener('click', () => {
  fetch('/api/schedule/realtime').then(() => { loadState(); loadSchedule(); });
});

function setIf(id, v) {
  const e = document.getElementById(id);
  if (e && document.activeElement !== e) e.value = v;
}
async function loadLocation() {
  const l = await fetch('/api/location').then(r => r.json()).catch(() => null);
  if (!l) return;
  document.getElementById('loc-place').textContent = l.place || (l.lat.toFixed(2) + ', ' + l.lon.toFixed(2));
  setIf('loc-zip', l.zip); setIf('loc-tz', l.tz);
  setIf('loc-dawn', l.dawn_offset); setIf('loc-dusk', l.dusk_offset);
}
document.getElementById('loc-apply').addEventListener('click', () => {
  const z = document.getElementById('loc-zip').value, tz = document.getElementById('loc-tz').value;
  fetch('/api/location/set?zip=' + encodeURIComponent(z) + '&timezone=' + encodeURIComponent(tz))
    .then(r => r.json()).then(d => { if (!d.ok) alert(d.error || 'failed'); loadLocation(); loadSchedule(); });
});
document.getElementById('loc-off-save').addEventListener('click', () => {
  const dn = document.getElementById('loc-dawn').value, dk = document.getElementById('loc-dusk').value;
  fetch('/api/location/offsets?dawn=' + dn + '&dusk=' + dk).then(() => { loadSchedule(); loadLocation(); });
});

async function loadDoor() {
  const d = await fetch('/api/door').then(r => r.json()).catch(() => null);
  if (!d || d.type !== 'servo') return;
  const el = document.getElementById('door-travel');
  if (el && document.activeElement !== el) el.value = d.travel;
}
const doorSave = document.getElementById('door-travel-save');
if (doorSave) doorSave.addEventListener('click', () => {
  const v = document.getElementById('door-travel').value;
  fetch('/api/door/travel?value=' + v).then(loadDoor);
});

// Hold-to-run jog: start motor on press, stop on release/leave.
function holdJog(btnId, dir) {
  const btn = document.getElementById(btnId);
  if (!btn) return;                    // servo door has no jog buttons
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

loadSensors(); loadState(); loadLog(); loadClimate(); loadDoor(); loadSchedule(); loadLocation();
setInterval(() => { loadSensors(); loadState(); loadClimate(); loadDoor(); loadSchedule(); loadLocation(); }, 5000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML, door_type=config.DOOR_TYPE, zip=config.LOCATION_ZIP)

if __name__ == "__main__":
    print(f"http://0.0.0.0:5000  —  your Pi's IP: run 'hostname -I'")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
