"""
generator/weather.py — Cliente Open-Meteo API con caché en memoria y mapeo de códigos WMO
hacia los iconos gráficos de InkyPi optimizados para la paleta ACeP 7-Color.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Tuple
import requests

import config

# Mapa WMO -> (Descripción en español, icono_dia, icono_noche, color_fallback)
WMO_CODE_MAP: Dict[int, Tuple[str, str, str, int]] = {
    0:  ("Despejado",        "01d", "01n", config.ACEP_COLOR_ORANGE),
    1:  ("Mayormente claro", "01d", "01n", config.ACEP_COLOR_YELLOW),
    2:  ("Parcial nublado",  "02d", "02n", config.ACEP_COLOR_ORANGE),
    3:  ("Nublado",          "03d", "03d", config.ACEP_COLOR_BLUE),
    45: ("Niebla",           "50d", "50d", config.ACEP_COLOR_BLUE),
    48: ("Niebla helada",    "50d", "50d", config.ACEP_COLOR_BLUE),
    51: ("Llovizna leve",    "51d", "51d", config.ACEP_COLOR_BLUE),
    53: ("Llovizna",         "51d", "51d", config.ACEP_COLOR_BLUE),
    55: ("Llovizna densa",   "51d", "51d", config.ACEP_COLOR_BLUE),
    61: ("Lluvia leve",      "10d", "10n", config.ACEP_COLOR_BLUE),
    63: ("Lluvia moderada",  "10d", "10n", config.ACEP_COLOR_BLUE),
    65: ("Lluvia fuerte",    "09d", "09d", config.ACEP_COLOR_RED),
    71: ("Nevada leve",      "13d", "13d", config.ACEP_COLOR_BLUE),
    73: ("Nevada",           "13d", "13d", config.ACEP_COLOR_BLUE),
    75: ("Nevada intensa",   "13d", "13d", config.ACEP_COLOR_BLUE),
    80: ("Chaparrones",      "09d", "09d", config.ACEP_COLOR_BLUE),
    81: ("Chaparrón fuerte", "09d", "09d", config.ACEP_COLOR_RED),
    82: ("Tormenta lluvia",  "11d", "11d", config.ACEP_COLOR_RED),
    95: ("Tormenta eléctr.", "11d", "11d", config.ACEP_COLOR_RED),
    96: ("Tormenta granizo", "11d", "11d", config.ACEP_COLOR_RED),
    99: ("Granizo fuerte",   "11d", "11d", config.ACEP_COLOR_RED),
}

_WEATHER_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "data": None,
}


def fetch_weather(force_refresh: bool = False) -> Dict[str, Any]:
    now = time.time()
    if (
        not force_refresh
        and _WEATHER_CACHE["data"] is not None
        and (now - _WEATHER_CACHE["timestamp"]) < config.WEATHER_CACHE_TTL_SEC
    ):
        return _WEATHER_CACHE["data"]

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": config.WEATHER_LATITUDE,
        "longitude": config.WEATHER_LONGITUDE,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": config.WEATHER_TIMEZONE,
        "forecast_days": 1,
    }

    try:
        resp = requests.get(url, params=params, timeout=6.0)
        resp.raise_for_status()
        payload = resp.json()

        curr = payload.get("current", {})
        daily = payload.get("daily", {})

        wmo_code = int(curr.get("weather_code", 0))
        is_night = (datetime.now().hour < 6 or datetime.now().hour >= 20)
        entry = WMO_CODE_MAP.get(wmo_code, ("Variable", "02d", "02n", config.ACEP_COLOR_BLUE))
        desc = entry[0]
        icon_name = entry[2] if is_night else entry[1]
        icon_color = entry[3]

        t_curr = round(float(curr.get("temperature_2m", 21.0)), 1)
        humidity = int(curr.get("relative_humidity_2m", 55))
        wind = round(float(curr.get("wind_speed_10m", 12.0)), 0)

        t_max_list = daily.get("temperature_2m_max", [t_curr + 4])
        t_min_list = daily.get("temperature_2m_min", [t_curr - 4])
        rain_prob_list = daily.get("precipitation_probability_max", [0])

        result = {
            "temp_current": t_curr,
            "temp_max": round(float(t_max_list[0]), 1) if t_max_list else t_curr,
            "temp_min": round(float(t_min_list[0]), 1) if t_min_list else t_curr,
            "rain_prob": int(rain_prob_list[0]) if rain_prob_list else 0,
            "humidity": humidity,
            "wind_kmh": int(wind),
            "wmo_code": wmo_code,
            "description": desc,
            "icon_name": icon_name,
            "icon_hw_color": icon_color,
            "online": True,
        }
        _WEATHER_CACHE["timestamp"] = now
        _WEATHER_CACHE["data"] = result
        return result

    except Exception:
        if _WEATHER_CACHE["data"] is not None:
            return _WEATHER_CACHE["data"]
        return {
            "temp_current": 22.0,
            "temp_max": 26.0,
            "temp_min": 15.0,
            "rain_prob": 10,
            "humidity": 60,
            "wind_kmh": 14,
            "wmo_code": 1,
            "description": "Mayormente claro",
            "icon_name": "01n" if (datetime.now().hour < 6 or datetime.now().hour >= 20) else "01d",
            "icon_hw_color": config.ACEP_COLOR_ORANGE,
            "online": False,
        }
