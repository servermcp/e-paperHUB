"""
integrations/google_cal.py — Integración con Google Calendar vía:
  1. URL Secreta iCal (.ics) configurable desde /domotica (método directo sin OAuth).
  2. Service Account JSON (`credentials_google_cal.json`).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import urllib.request

import config

GCAL_CONFIG_FILE = config.BASE_DIR / "google_cal_config.json"

_CAL_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "events": None,
}
_CAL_TTL_SEC = 300


def load_gcal_config() -> Dict[str, str]:
    if GCAL_CONFIG_FILE.exists():
        try:
            return json.loads(GCAL_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"ical_url": os.getenv("GOOGLE_CALENDAR_ICAL_URL", "")}


def save_gcal_ical_url(ical_url: str) -> None:
    GCAL_CONFIG_FILE.write_text(json.dumps({"ical_url": ical_url.strip()}, indent=2), encoding="utf-8")
    _CAL_CACHE["timestamp"] = 0.0
    _CAL_CACHE["events"] = None


def _parse_ics_upcoming(ics_text: str, max_results: int = 2) -> List[Dict[str, str]]:
    """
    Parser ligero de archivos iCalendar (.ics) de Google Calendar sin dependencias pesadas.
    Extrae VEVENTs futuros o del día actual y los ordena cronológicamente.
    """
    now_local = datetime.now()
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    events_found = []

    blocks = ics_text.split("BEGIN:VEVENT")[1:]
    for blk in blocks:
        end_idx = blk.find("END:VEVENT")
        if end_idx != -1:
            blk = blk[:end_idx]

        # Unfold lines según RFC 5545
        unfolded = re.sub(r"\r?\n[ \t]", "", blk)
        dtstart_raw = ""
        summary_raw = "Evento"

        for line in unfolded.splitlines():
            if line.startswith("DTSTART"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    dtstart_raw = parts[1].strip()
            elif line.startswith("SUMMARY"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    summary_raw = parts[1].strip().replace("\\,", ",").replace("\\;", ";")

        if not dtstart_raw:
            continue

        try:
            if "T" in dtstart_raw:
                clean_dt = dtstart_raw.rstrip("Z")[:15]
                dt_obj = datetime.strptime(clean_dt, "%Y%m%dT%H%M%S")
                if dtstart_raw.endswith("Z"):
                    dt_obj = dt_obj.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
                time_str = dt_obj.strftime("%H:%M")
            else:
                dt_obj = datetime.strptime(dtstart_raw[:8], "%Y%m%d")
                time_str = "HOY"

            if dt_obj >= today_start and dt_obj <= (now_local + timedelta(days=7)):
                events_found.append((dt_obj, {"time": time_str, "title": summary_raw}))
        except Exception:
            continue

    events_found.sort(key=lambda x: x[0])
    return [ev for _, ev in events_found[:max_results]]


def get_upcoming_events(max_results: int = 2, force_refresh: bool = False) -> List[Dict[str, str]]:
    now_ts = time.time()
    if (
        not force_refresh
        and _CAL_CACHE["events"] is not None
        and (now_ts - _CAL_CACHE["timestamp"]) < _CAL_TTL_SEC
    ):
        return _CAL_CACHE["events"][:max_results]

    # 1. Intentar por URL iCal (.ics) si está configurada
    cfg = load_gcal_config()
    ical_url = cfg.get("ical_url", "").strip()
    if ical_url:
        try:
            req = urllib.request.Request(ical_url, headers={"User-Agent": "e-paperHUB/1.1"})
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                ics_text = resp.read().decode("utf-8", errors="ignore")
            parsed = _parse_ics_upcoming(ics_text, max_results=max_results)
            if not parsed:
                parsed = [{"time": "--:--", "title": "Sin eventos próximos en agenda"}]
            _CAL_CACHE["timestamp"] = now_ts
            _CAL_CACHE["events"] = parsed
            return parsed[:max_results]
        except Exception as exc:
            print(f"[GoogleCalendar iCal] Error: {exc}")

    # 2. Intentar por Service Account JSON si existe
    creds_path = config.GOOGLE_CALENDAR_CREDENTIALS_FILE
    if os.path.exists(creds_path):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
            creds = service_account.Credentials.from_service_account_file(creds_path, scopes=scopes)
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            now_utc = datetime.now(timezone.utc)
            end_of_day = now_utc + timedelta(days=3)

            events_result = (
                service.events()
                .list(
                    calendarId=config.GOOGLE_CALENDAR_ID,
                    timeMin=now_utc.isoformat(),
                    timeMax=end_of_day.isoformat(),
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            raw_items = events_result.get("items", [])
            parsed = []
            for item in raw_items:
                start_raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
                t_str = start_raw[11:16] if "T" in start_raw else "HOY"
                parsed.append({"time": t_str, "title": item.get("summary", "Evento")})
            if not parsed:
                parsed = [{"time": "--:--", "title": "Sin eventos próximos"}]
            _CAL_CACHE["timestamp"] = now_ts
            _CAL_CACHE["events"] = parsed
            return parsed[:max_results]
        except Exception as exc:
            print(f"[GoogleCalendar API] Error: {exc}")

    default_events = [
        {"time": "10:30", "title": "Revisión contratos & proveedores"},
        {"time": "18:00", "title": "Turno control / Compras supermercado"},
    ]
    _CAL_CACHE["timestamp"] = now_ts
    _CAL_CACHE["events"] = default_events
    return default_events[:max_results]
