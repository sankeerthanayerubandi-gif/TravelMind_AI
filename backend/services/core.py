from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import os
from typing import Any

import requests


@lru_cache(maxsize=64)
def get_weather(city: str, latitude: float | None = None, longitude: float | None = None) -> dict[str, Any]:
    try:
        if latitude is not None and longitude is not None:
            response = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": latitude, "longitude": longitude, "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code", "timezone": "auto"}, timeout=6)
            response.raise_for_status()
            current = response.json().get("current", {})
            return {"city": city, "temperature": round(float(current.get("temperature_2m", 0))), "condition": _weather_code(current.get("weather_code")), "humidity": round(float(current.get("relative_humidity_2m", 0))), "wind": round(float(current.get("wind_speed_10m", 0))), "source": "Open-Meteo live"}
    except (requests.RequestException, ValueError, TypeError, KeyError):
        pass
    return {"city": city, "temperature": None, "condition": "Live weather unavailable", "humidity": None, "wind": None, "source": "No live weather response"}


def _weather_code(code: Any) -> str:
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "Current conditions"
    if code == 0: return "Clear sky"
    if code in {1, 2, 3}: return "Partly cloudy"
    if code in {45, 48}: return "Foggy"
    if code in range(51, 68): return "Drizzle or rain"
    if code in range(71, 78): return "Snow"
    if code in range(80, 83): return "Rain showers"
    if code >= 95: return "Thunderstorm"
    return "Current conditions"


@lru_cache(maxsize=64)
def convert_currency(amount: float, source: str, target: str) -> dict[str, Any]:
    source, target = source.upper(), target.upper()
    if source == target:
        return {"amount": amount, "source": source, "target": target, "converted": round(amount, 2), "rate": 1.0, "live": False, "source_name": "Same currency"}
    try:
        response = requests.get("https://api.frankfurter.app/latest", params={"amount": amount, "from": source, "to": target}, timeout=6)
        response.raise_for_status()
        value = float(response.json()["rates"][target])
        return {"amount": amount, "source": source, "target": target, "converted": round(value, 2), "rate": round(value / amount, 6) if amount else 0, "live": True, "source_name": "Frankfurter ECB reference"}
    except (requests.RequestException, ValueError, TypeError, KeyError):
        rates = {"EUR": 1.0, "USD": 1.09, "GBP": 0.86, "JPY": 162.0, "INR": 96.0, "NZD": 1.78}
        base = amount / rates.get(source, 1.0)
        value = base * rates.get(target, 1.0)
        return {"amount": amount, "source": source, "target": target, "converted": round(value, 2), "rate": round(rates.get(target, 1.0) / rates.get(source, 1.0), 6), "live": False, "source_name": "Reference fallback"}


def save_trip(trip: dict, store: list[dict]) -> list[dict]:
    record = dict(trip)
    record["saved_at"] = datetime.now().isoformat(timespec="seconds")
    return [record] + store[:9]


def monitor_signals() -> list[dict]:
    return [{"type": "Weather", "status": "Check live forecast", "detail": "Live weather is queried only when coordinates are available.", "severity": "low"}, {"type": "Transport", "status": "Verify locally", "detail": "Transit time is an estimate based on route distance.", "severity": "medium"}, {"type": "Crowds", "status": "Not connected", "detail": "No crowd provider is configured; no crowd claim is shown.", "severity": "low"}]
