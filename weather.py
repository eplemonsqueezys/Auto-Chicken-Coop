#!/usr/bin/env python3
"""
Live weather + sun times for the coop, from Open-Meteo (free, no API key).

Provides:
  - local_now()        timezone-aware-ish "now" for config.TIMEZONE (naive local)
  - temperature()      current outdoor temperature in config.TEMP_UNIT (°F/°C)
  - sun_times()        today's (sunrise, sunset) as naive local datetimes
  - door_window()      (open_at, close_at) = sunrise+offset, sunset+offset

Results are cached for config.WEATHER_REFRESH_MIN minutes so we don't hammer the
API. Everything fails soft: if the Pi is offline, callers get the last cached
value, or None, and the control logic falls back accordingly.
"""

import json
import time
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

import config

try:
    from zoneinfo import ZoneInfo
except ImportError:                      # very old Python
    ZoneInfo = None

log = logging.getLogger("coop.weather")

_API = "https://api.open-meteo.com/v1/forecast"
_cache = {"data": None, "at": 0.0}


def local_now():
    """Current wall-clock time in config.TIMEZONE, as a naive datetime so it
    compares cleanly with the naive sunrise/sunset Open-Meteo returns."""
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(config.TIMEZONE)).replace(tzinfo=None)
        except Exception as e:
            log.warning(f"timezone {config.TIMEZONE} unavailable ({e}); using system time")
    return datetime.now()


def _precip_prob_next(hourly):
    """Max precipitation probability from now through RAIN_LOOKAHEAD_HOURS."""
    try:
        times = hourly["time"]
        probs = hourly["precipitation_probability"]
    except (KeyError, TypeError):
        return None
    now = local_now()
    start = now.replace(minute=0, second=0, microsecond=0)
    end = now + timedelta(hours=config.RAIN_LOOKAHEAD_HOURS)
    vals = []
    for t, p in zip(times, probs):
        if p is None:
            continue
        try:
            dt = datetime.fromisoformat(t)
        except ValueError:
            continue
        if start <= dt <= end:
            vals.append(p)
    return max(vals) if vals else None


def _fetch():
    unit = "fahrenheit" if getattr(config, "TEMP_UNIT", "C").upper() == "F" else "celsius"
    url = _API + "?" + urllib.parse.urlencode({
        "latitude":  config.LATITUDE,
        "longitude": config.LONGITUDE,
        "current":   "temperature_2m,precipitation,weather_code",
        "hourly":    "precipitation_probability",
        "daily":     "sunrise,sunset",
        "timezone":  config.TIMEZONE,
        "temperature_unit": unit,
        "forecast_days": 1,
    })
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.load(r)
    cur = d["current"]
    return {
        "temp":    float(cur["temperature_2m"]),   # in config.TEMP_UNIT
        "precip":  float(cur.get("precipitation", 0) or 0),
        "weather_code": cur.get("weather_code"),
        "precip_prob_next": _precip_prob_next(d.get("hourly", {})),
        "sunrise": datetime.fromisoformat(d["daily"]["sunrise"][0]),
        "sunset":  datetime.fromisoformat(d["daily"]["sunset"][0]),
        "fetched": datetime.now(),
    }


def get_conditions(force=False):
    """Return cached conditions, refetching if stale. None if never fetched and
    the network is unavailable."""
    fresh = _cache["data"] and (time.time() - _cache["at"]) < config.WEATHER_REFRESH_MIN * 60
    if fresh and not force:
        return _cache["data"]
    try:
        data = _fetch()
        _cache["data"] = data
        _cache["at"] = time.time()
        log.info(f"Weather {config.LOCATION_ZIP}: {data['temp']:.1f}{config.TEMP_UNIT}  "
                 f"sunrise {data['sunrise']:%I:%M %p}  sunset {data['sunset']:%I:%M %p}")
    except Exception as e:
        if _cache["data"]:
            log.warning(f"weather refresh failed ({e}); using cached value")
        else:
            log.warning(f"weather fetch failed ({e}); no data yet")
    return _cache["data"]


def reset_cache():
    """Forget cached conditions (call after the location changes)."""
    _cache["data"] = None
    _cache["at"] = 0.0


def geocode_zip(zipcode, country="us"):
    """Look up a postal code -> {zip, latitude, longitude, place} via the free
    zippopotam.us API (no key). Raises on failure (bad zip / offline)."""
    url = "https://api.zippopotam.us/%s/%s" % (country, urllib.parse.quote(str(zipcode).strip()))
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.load(r)
    p = d["places"][0]
    return {
        "zip": str(d.get("post code", zipcode)),
        "latitude": float(p["latitude"]),
        "longitude": float(p["longitude"]),
        "place": "%s, %s" % (p["place name"], p["state abbreviation"]),
    }


def temperature():
    """Current outdoor temperature in config.TEMP_UNIT (°F or °C)."""
    d = get_conditions()
    return d["temp"] if d else None


def sun_times():
    d = get_conditions()
    if d:
        return d["sunrise"], d["sunset"]
    return None, None


# Rain detection (with a sim override for testing from the debug panel).
_sim_rain = None   # None = use real weather; True/False = forced for testing

# WMO weather codes >= 51 are precipitation (drizzle/rain/snow/showers/storm);
# 0-48 are clear/cloud/fog (no precip).
def set_sim_rain(value):
    global _sim_rain
    _sim_rain = value


def rain_expected():
    """True if it's raining now or rain is forecast within the lookahead window."""
    if _sim_rain is not None:
        return _sim_rain
    d = get_conditions()
    if not d:
        return False                      # no data -> don't override
    if d.get("precip") and d["precip"] > 0:
        return True
    code = d.get("weather_code")
    if code is not None and code >= 51:
        return True
    pn = d.get("precip_prob_next")
    if pn is not None and pn >= config.RAIN_PROBABILITY_THRESHOLD:
        return True
    return False


def weather_status():
    d = get_conditions()
    return {
        "temp": d["temp"] if d else None,
        "precip": d.get("precip") if d else None,
        "weather_code": d.get("weather_code") if d else None,
        "precip_prob_next": d.get("precip_prob_next") if d else None,
        "rain_expected": rain_expected(),
        "sim_rain": _sim_rain,
    }


def door_window(sunrise=None, sunset=None):
    """(open_at, close_at) for the door: sunrise+DAWN offset, sunset+DUSK offset."""
    if sunrise is None or sunset is None:
        sunrise, sunset = sun_times()
    if sunrise is None:
        return None, None
    open_at  = sunrise + timedelta(minutes=config.DOOR_OPEN_AFTER_DAWN_MIN)
    close_at = sunset  + timedelta(minutes=config.DOOR_CLOSE_AFTER_DUSK_MIN)
    return open_at, close_at


def door_should_be_open(now, sunrise=None, sunset=None):
    """True if the door should be open at `now` (between open_at and close_at)."""
    open_at, close_at = door_window(sunrise, sunset)
    if open_at is None:
        return None
    return open_at <= now < close_at
