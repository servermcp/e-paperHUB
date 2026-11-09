"""
integrations/tuya_client.py - Sincronizacion en vivo de los 22 dispositivos de Tuya Smart + Smart Life.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, List
import requests

import config
import database

DEVICE_ASSIGNMENTS_FILE = config.BASE_DIR / "tuya_device_assignments.json"


def load_device_assignments() -> Dict[str, str]:
    if DEVICE_ASSIGNMENTS_FILE.exists():
        try:
            return json.loads(DEVICE_ASSIGNMENTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    default_map = {
        "eb17f07432300b71aeqewh": "porton_main",     # Porton (ckmkzq)
        "eb4247200f590ffc6eiddw": "temp_pina",       # Temp (wk -> temp_current 24.2 C)
        "eb2c827fc495d18c09czca": "riego_main",      # Riego (Tuya)
        "eb6fc0540f867b2c37go2w": "riego_main",      # Riego (Smart Life)
        "ebf640c87905406b80badt": "luces_pina",      # Living 2
        "ebd96d8e2091161e28w3oq": "luces_pina",      # Cocina (Tuya)
        "ebf415a936aa3e7a2asu3n": "luces_pina",      # Comedor 3
        "eb3000364235c31b4ezzmc": "luces_pina",      # Living 1
        "eb142d876d86739d3ezvda": "luces_pina",      # Comedor 3
        "ebfe96090da274549eya3m": "luces_pina",      # Comedor 1
        "ebd8ab1914b6e6b262iocp": "luces_santiago",  # Cocina (tdq)
        "eb4f5f277fa693f5d7twdb": "luces_santiago",  # Cuarto3
        "eb9e928382bcf9fe05vz9x": "luces_santiago",  # Comedor3
        "ebfae9f22a8fcf3f81msam": "luces_santiago",  # Comedor2
        "ebde2bdc4b695b5538xjha": "luces_santiago",  # Cuarto2
        "eb61a367f1966cd9cbx0hs": "luces_santiago",  # Cuarto1
        "eb191e9b2e1c2fe0c4rvfx": "luces_santiago",  # Cuarto3
    }
    return default_map


def save_device_assignment(tuya_dev_id: str, target_group: str) -> None:
    m = load_device_assignments()
    m[tuya_dev_id] = target_group
    DEVICE_ASSIGNMENTS_FILE.write_text(json.dumps(m, indent=2), encoding="utf-8")


def _sign_req(method: str, path: str, token: str = "", body: str = "") -> Dict[str, str]:
    t_ms = str(int(time.time() * 1000))
    ch = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sts = f"{method.upper()}\n{ch}\n\n{path}"
    sig = (
        hmac.new(
            config.TUYA_ACCESS_SECRET.encode("utf-8"),
            (config.TUYA_ACCESS_ID + token + t_ms + sts).encode("utf-8"),
            hashlib.sha256,
        )
        .hexdigest()
        .upper()
    )
    headers = {
        "client_id": config.TUYA_ACCESS_ID,
        "sign": sig,
        "t": t_ms,
        "sign_method": "HMAC-SHA256",
    }
    if token:
        headers["access_token"] = token
    return headers


def fetch_all_tuya_devices() -> List[Dict[str, Any]]:
    if not (config.TUYA_ACCESS_ID and config.TUYA_ACCESS_SECRET):
        return []

    base_url = config.TUYA_API_ENDPOINT.rstrip("/")
    t_path = "/v1.0/token?grant_type=1"
    r_tok = requests.get(f"{base_url}{t_path}", headers=_sign_req("GET", t_path), timeout=7.0).json()
    if not r_tok.get("success"):
        return []

    token = r_tok["result"]["access_token"]
    all_devs: List[Dict[str, Any]] = []
    last_row_key = ""

    while True:
        path = "/v1.0/iot-01/associated-users/devices?size=100" + (
            f"&last_row_key={last_row_key}" if last_row_key else ""
        )
        res = requests.get(f"{base_url}{path}", headers=_sign_req("GET", path, token), timeout=8.0).json()
        result = res.get("result", {})
        devs = result.get("devices", [])
        all_devs.extend(devs)
        if not result.get("has_more") or not result.get("last_row_key"):
            break
        last_row_key = result["last_row_key"]

    return all_devs


_LAST_SYNC_TS: float = 0.0


def get_last_tuya_sync_age() -> float:
    """Retorna la cantidad de segundos transcurridos desde la última sincronización con Tuya."""
    if _LAST_SYNC_TS <= 0.0:
        return 999999.0
    return time.time() - _LAST_SYNC_TS


def sync_irrigation_status() -> Dict[str, Any]:
    global _LAST_SYNC_TS
    try:
        devs = fetch_all_tuya_devices()
        if not devs:
            return {"ok": False, "reason": "No se recibieron dispositivos desde Tuya Cloud"}

        assignments = load_device_assignments()
        pina_on = 0
        sgo_on = 0
        state_changed = False

        # Cargar estados actuales para detectar cambios críticos (ej. portón abierto/cerrado)
        with database.db_session() as conn:
            prev_rows = conn.execute(
                "SELECT device_id, status_text, is_active FROM device_state_cache"
            ).fetchall()
            prev_states = {r["device_id"]: (r["status_text"], r["is_active"]) for r in prev_rows}

        for d in devs:
            dev_id = str(d.get("id", ""))
            online = bool(d.get("online", False))
            status_map = {s.get("code"): s.get("value") for s in d.get("status", []) if isinstance(s, dict)}
            group = assignments.get(dev_id, "")

            if group == "luces_pina":
                if online and bool(status_map.get("switch_led") or status_map.get("switch_1") or status_map.get("switch")):
                    pina_on += 1
            elif group == "luces_santiago":
                if online and bool(status_map.get("switch_led") or status_map.get("switch_1") or status_map.get("switch")):
                    sgo_on += 1
            elif group == "porton_main":
                is_open = bool(status_map.get("doorcontact_state") or status_map.get("switch_1"))
                p_txt = "Abierto" if is_open else "Cerrado"
                new_act = 1 if is_open else 0
                if prev_states.get("porton_main") != (p_txt, new_act):
                    state_changed = True
                with database.db_session() as conn:
                    conn.execute(
                        "UPDATE device_state_cache SET status_text = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'porton_main'",
                        (p_txt, new_act),
                    )
            elif group == "temp_pina":
                raw_t = status_map.get("temp_current") or status_map.get("va_temperature")
                if isinstance(raw_t, (int, float)):
                    t_val = raw_t / 10.0 if raw_t > 80 else float(raw_t)
                    t_txt = f"{t_val:.1f}°"
                    if prev_states.get("temp_pina", (None,))[0] != t_txt:
                        state_changed = True
                    with database.db_session() as conn:
                        conn.execute(
                            "UPDATE device_state_cache SET status_text = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'temp_pina'",
                            (t_txt,),
                        )
            elif group == "riego_main":
                if online:
                    is_w = bool(status_map.get("switch_1") or status_map.get("switch"))
                    r_txt = "Regando" if is_w else "Próximo 06:30"
                    r_act = 1 if is_w else 0
                    if prev_states.get("riego_main") != (r_txt, r_act):
                        state_changed = True
                    with database.db_session() as conn:
                        conn.execute(
                            "UPDATE device_state_cache SET status_text = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'riego_main'",
                            (r_txt, r_act),
                        )
            elif group == "pileta_filtro":
                is_f = online and bool(status_map.get("switch_1") or status_map.get("switch"))
                f_txt = "Filtrando" if is_f else "Apagada"
                f_act = 1 if is_f else 0
                if prev_states.get("pileta_filtro") != (f_txt, f_act):
                    state_changed = True
                with database.db_session() as conn:
                    conn.execute(
                        "UPDATE device_state_cache SET status_text = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'pileta_filtro'",
                        (f_txt, f_act),
                    )

        pina_txt = f"{pina_on} encendidas"
        pina_act = 1 if pina_on > 0 else 0
        if prev_states.get("luces_pina") != (pina_txt, pina_act):
            state_changed = True

        sgo_txt = f"{sgo_on} encendidas"
        sgo_act = 1 if sgo_on > 0 else 0
        if prev_states.get("luces_santiago") != (sgo_txt, sgo_act):
            state_changed = True

        with database.db_session() as conn:
            conn.execute(
                "UPDATE device_state_cache SET status_text = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'luces_pina'",
                (pina_txt, pina_act),
            )
            conn.execute(
                "UPDATE device_state_cache SET status_text = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'luces_santiago'",
                (sgo_txt, sgo_act),
            )

        # Si no hay ningun dispositivo asignado a la pileta, asegurar que quede en estado Apagada / Inactiva
        has_pileta_assigned = any(grp == "pileta_filtro" for grp in assignments.values())
        if not has_pileta_assigned:
            with database.db_session() as conn:
                conn.execute(
                    "UPDATE device_state_cache SET status_text = 'Apagada', is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'pileta_filtro'"
                )

        _LAST_SYNC_TS = time.time()
        return {
            "ok": True,
            "state_changed": state_changed,
            "devices_total": len(devs),
            "pina_on": pina_on,
            "sgo_on": sgo_on,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
