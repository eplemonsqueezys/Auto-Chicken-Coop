#!/usr/bin/env python3
"""
Pi <-> Arduino serial link + adapter objects.

The Arduino handles the MG995 servos and the analog/DHT sensors. This module
talks to it over USB serial and exposes adapter objects that look EXACTLY like
the PCA9685 / MCP3008 / DHT22 objects the rest of the code already uses, so
coop_controller.py and debug_panel.py don't need to know the difference.

Serial protocol (newline-delimited ASCII, 115200 baud):

  Pi  -> Arduino
      "S<ch> <angle>\\n"   set servo channel <ch> to <angle> degrees (0-180)
      "P\\n"               ping (Arduino replies "PONG")

  Arduino -> Pi   (streamed ~3x/sec)
      "SENS <tempC> <hum> <ldrRaw> <foodRaw>\\n"
          tempC/hum are floats (or 'nan' if the DHT read failed)
          ldrRaw/foodRaw are 0-1023 analog counts

A background thread reads the stream and keeps the latest sensor frame; sensor
adapters just return the cached value, exactly like polling a real chip.
"""

import threading
import time
import logging

import config

log = logging.getLogger("coop.arduino")

_link = None
_link_lock = threading.Lock()


def get_link():
    """Return the shared ArduinoLink, opening the serial port on first use."""
    global _link
    with _link_lock:
        if _link is None:
            link = ArduinoLink(config.ARDUINO_PORT, config.ARDUINO_BAUD)
            link.start()          # may raise if pyserial missing or port absent
            _link = link          # only cache once it's actually open
        return _link


class ArduinoLink:
    def __init__(self, port, baud):
        self.port = port
        self.baud = baud
        self._ser = None
        self._latest = {"temp_c": None, "humidity": None, "ldr": 0, "food": 0}
        self._lock = threading.Lock()
        self._stop = False

    def start(self):
        import serial  # pyserial; only needed on the real Pi
        self._ser = serial.Serial(self.port, self.baud, timeout=1)
        time.sleep(2.0)  # Arduino auto-resets when the port opens; wait for boot
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()
        log.info(f"Arduino link open on {self.port} @ {self.baud}")

    # -- reading -----------------------------------------------------------
    def _reader(self):
        while not self._stop:
            try:
                raw = self._ser.readline().decode("ascii", "ignore").strip()
            except Exception as e:
                log.warning(f"serial read error: {e}")
                time.sleep(0.5)
                continue
            if raw:
                self.parse_line(raw)

    def parse_line(self, line):
        """Parse one line from the Arduino. Separated out so it's unit-testable."""
        parts = line.split()
        if not parts:
            return
        if parts[0] == "SENS" and len(parts) >= 5:
            def f(x):
                try:
                    v = float(x)
                    return None if v != v else v  # nan -> None
                except ValueError:
                    return None
            def i(x):
                try:
                    return int(float(x))
                except ValueError:
                    return 0
            with self._lock:
                self._latest = {
                    "temp_c":   f(parts[1]),
                    "humidity": f(parts[2]),
                    "ldr":      i(parts[3]),
                    "food":     i(parts[4]),
                }
        elif parts[0] == "PONG":
            log.info("Arduino ponged")

    def latest(self):
        with self._lock:
            return dict(self._latest)

    # -- writing -----------------------------------------------------------
    def send_servo(self, channel, angle):
        angle = max(0, min(180, int(round(angle))))
        msg = f"S{channel} {angle}\n".encode("ascii")
        if self._ser is not None:
            self._ser.write(msg)
        log.info(f"[ARDUINO] servo ch{channel} -> {angle}deg")

    def stop(self):
        self._stop = True
        if self._ser is not None:
            self._ser.close()


# ── Adapter objects matching the existing hardware interfaces ──────────────
def _duty_to_angle(duty_cycle):
    """Convert a PCA-style 16-bit duty cycle back to a 0-180 servo angle,
    using the SERVOMIN/SERVOMAX calibration in config (close=0, open=180)."""
    pulse = duty_cycle * 4096 / 65535
    span = (config.SERVOMAX - config.SERVOMIN) or 1
    angle = (pulse - config.SERVOMIN) * 180.0 / span
    return max(0.0, min(180.0, angle))


class _ArduinoServoChannel:
    def __init__(self, link, n):
        self._link = link
        self.n = n
        self._dc = 0

    @property
    def duty_cycle(self):
        return self._dc

    @duty_cycle.setter
    def duty_cycle(self, v):
        self._dc = v
        self._link.send_servo(self.n, _duty_to_angle(v))


class ArduinoServoDriver:
    """Looks like a PCA9685: .frequency and .channels[ch].duty_cycle."""
    def __init__(self):
        self._link = get_link()
        self.channels = [_ArduinoServoChannel(self._link, i) for i in range(16)]
        self._freq = 0

    @property
    def frequency(self):
        return self._freq

    @frequency.setter
    def frequency(self, f):
        self._freq = f  # servo timing lives on the Arduino; nothing to send


class ArduinoADC:
    """Looks like an MCP3008 channel: .value in 0.0-1.0."""
    def __init__(self, channel):
        self.channel = channel
        self._link = get_link()

    @property
    def value(self):
        d = self._link.latest()
        if self.channel == config.MCP3008_LDR_CHANNEL:
            raw = d["ldr"]
        elif self.channel == config.MCP3008_FOOD_CHANNEL:
            raw = d["food"]
        else:
            raw = 0
        return max(0.0, min(1.0, raw / config.ARDUINO_ADC_MAX))


class ArduinoDHT:
    """Looks like adafruit_dht.DHT22: .temperature and .humidity."""
    def __init__(self):
        self._link = get_link()

    @property
    def temperature(self):
        return self._link.latest()["temp_c"]

    @property
    def humidity(self):
        return self._link.latest()["humidity"]
