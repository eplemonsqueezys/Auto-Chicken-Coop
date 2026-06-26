#!/usr/bin/env python3
"""
Live weather + sun times for the coop, from Open-Meteo (free, no API key).

Provides:
  - local_now()        timezone-aware-ish "now" for config.TIMEZONE (naive local)
  - temperature_c()    current outdoor temperature in °C for the location
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


def _fetch():
    url = _API + "?" + urllib.parse.urlencode({
        "latitude":  config.LATITUDE,
        "longitude": config.LONGITUDE,
        "current":   "temperature_2m",
        "daily":     "sunrise,sunset",
        "timezone":  config.TIMEZONE,
        "forecast_days": 1,
    })
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.load(r)
    return {
        "temp_c":  float(d["current"]["temperature_2m"]),
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
        log.info(f"Weather {config.LOCATION_ZIP}: {data['temp_c']:.1f}C  "
                 f"sunrise {data['sunrise']:%H:%M}  sunset {data['sunset']:%H:%M}")
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


def temperature_c():
    d = get_conditions()
    return d["temp_c"] if d else None


def sun_times():
    d = get_conditions()
    if d:
        return d["sunrise"], d["sunset"]
    return None, None


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
