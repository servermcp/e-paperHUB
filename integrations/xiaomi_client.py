"""
integrations/xiaomi_client.py — Conector Xiaomi Cloud (Mi Home) con soporte de:
  1. Autenticación moderna por QR Oficial (`account.xiaomi.com/longPolling/loginUrl`)
     que evita el bloqueo de contraseña MD5 (`code 70016`) desde IPs de datacenter (Tokyo VPS).
  2. Persistencia de sesión permanente (`passToken`, `ssecurity`, `serviceToken`) en `xiaomi_session.json`.
  3. Descubrimiento de todos los dispositivos en todas las regiones (`us`, `de`, `cn`, `sg`, `ru`)
     y lectura en vivo del estado del robot aspiradora ("Romina").
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
import requests
from Crypto.Cipher import ARC4

import config
import database

SESSION_FILE = config.BASE_DIR / "xiaomi_session.json"

_QR_STATE: Dict[str, Any] = {
    "status": "idle",  # 'idle', 'waiting_scan', 'authenticated', 'error'
    "qr_image_url": "",
    "login_url": "",
    "lp_url": "",
    "error": "",
    "devices": [],
    "updated_at": 0.0,
}


def _clean_xiaomi_json(text: str) -> Dict[str, Any]:
    if text.startswith("&&&START&&&"):
        text = text[11:]
    return json.loads(text)


def load_saved_session() -> Dict[str, Any]:
    if SESSION_FILE.exists():
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            if data.get("serviceToken") and data.get("ssecurity"):
                return data
        except Exception:
            pass
    return {}


def start_qr_login_session() -> Dict[str, Any]:
    """
    Solicita un código QR oficial a Xiaomi (`longPolling/loginUrl`) y lanza un hilo
    en background en el VPS que espera a que el usuario lo escanee desde la app
    Xiaomi Home (Mi Home). Apenas lo escanea, guarda la sesión permanente y descubre
    el robot aspiradora automáticamente.
    """
    sess = requests.Session()
    ua = "Android-7.1.1-1.0.0-ONEPLUS A3010-136-AABBCCDDEEFF APP/xiaomi.smarthome APPV/62830"
    sess.headers.update({"User-Agent": ua})

    params = {
        "_qrsize": "240",
        "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
        "callback": "https://sts.api.io.mi.com/sts",
        "_hasLogo": "false",
        "sid": "xiaomiio",
        "serviceParam": "",
        "_locale": "en_US",
        "_dc": str(int(time.time() * 1000)),
    }
    r = sess.get("https://account.xiaomi.com/longPolling/loginUrl", params=params, timeout=10)
    data = _clean_xiaomi_json(r.text)

    qr_img_url = data.get("qr", "")
    lp_url = data.get("lp", "")
    login_url = data.get("loginUrl", "")

    if not lp_url:
        _QR_STATE["status"] = "error"
        _QR_STATE["error"] = f"Respuesta inesperada de Xiaomi QR: {data}"
        return dict(_QR_STATE)

    _QR_STATE.update({
        "status": "waiting_scan",
        "qr_image_url": qr_img_url,
        "login_url": login_url,
        "lp_url": lp_url,
        "error": "",
        "updated_at": time.time(),
    })

    def _poll_worker(session_obj: requests.Session, poll_url: str) -> None:
        try:
            # Xiaomi mantiene abierto el long-poll hasta que el usuario escanea en la app
            resp = session_obj.get(poll_url, timeout=120)
            auth_data = _clean_xiaomi_json(resp.text)

            ssecurity = auth_data.get("ssecurity")
            user_id = auth_data.get("userId")
            pass_token = auth_data.get("passToken")
            location = auth_data.get("location")

            if not (ssecurity and location):
                _QR_STATE["status"] = "error"
                _QR_STATE["error"] = f"No se completó el escaneo: {auth_data}"
                return

            r_sts = session_obj.get(location, timeout=10)
            service_token = session_obj.cookies.get("serviceToken") or r_sts.cookies.get("serviceToken")

            saved = {
                "userId": str(user_id),
                "ssecurity": ssecurity,
                "passToken": pass_token,
                "serviceToken": service_token,
                "saved_at": time.time(),
            }
            SESSION_FILE.write_text(json.dumps(saved, indent=2), encoding="utf-8")

            # Descubrir dispositivos en todas las regiones
            devs = discover_all_xiaomi_devices(saved)
            saved["devices"] = devs
            SESSION_FILE.write_text(json.dumps(saved, indent=2), encoding="utf-8")

            _QR_STATE["status"] = "authenticated"
            _QR_STATE["devices"] = devs
            sync_romina_status()
        except Exception as exc:
            _QR_STATE["status"] = "error"
            _QR_STATE["error"] = f"Tiempo agotado o error esperando escaneo: {exc}"

    t = threading.Thread(target=_poll_worker, args=(sess, lp_url), daemon=True)
    t.start()
    return dict(_QR_STATE)


def _rc4_crypt(key_b64: str, data_bytes: bytes) -> bytes:
    cipher = ARC4.new(base64.b64decode(key_b64))
    cipher.encrypt(bytes(1024))
    return cipher.encrypt(data_bytes)


def xiaomi_api_call(session_data: Dict[str, Any], country: str, uri: str, params_dict: Dict[str, Any]) -> Dict[str, Any]:
    ssecurity = session_data["ssecurity"]
    user_id = str(session_data["userId"])
    service_token = str(session_data["serviceToken"])

    base = "https://api.io.mi.com/app" if country == "cn" else f"https://{country}.api.io.mi.com/app"
    url = base + uri

    nonce = base64.b64encode(os.urandom(8) + int(time.time() / 60).to_bytes(4, "big")).decode()
    snonce = base64.b64encode(
        hashlib.sha256(base64.b64decode(ssecurity) + base64.b64decode(nonce)).digest()
    ).decode()

    rc4_params = {"data": json.dumps(params_dict)}
    msg = "&".join(["POST", uri] + [f"{k}={v}" for k, v in rc4_params.items()] + [snonce])
    rc4_params["rc4_hash__"] = base64.b64encode(hashlib.sha1(msg.encode()).digest()).decode()

    enc_params = {
        k: base64.b64encode(_rc4_crypt(snonce, v.encode())).decode()
        for k, v in rc4_params.items()
    }
    msg2 = "&".join(["POST", uri] + [f"{k}={v}" for k, v in enc_params.items()] + [snonce])
    enc_params["signature"] = base64.b64encode(hashlib.sha1(msg2.encode()).digest()).decode()
    enc_params["_nonce"] = nonce
    enc_params["ssecurity"] = ssecurity

    headers = {
        "User-Agent": "Android-7.1.1-1.0.0-ONEPLUS A3010-136-AABBCCDDEEFF APP/xiaomi.smarthome APPV/62830",
        "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
        "Accept-Encoding": "identity",
        "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
    }
    cookies = {
        "userId": user_id,
        "yetAnotherServiceToken": service_token,
        "serviceToken": service_token,
        "locale": "en_US",
        "timezone": "GMT+00:00",
    }
    resp = requests.post(url, data=enc_params, headers=headers, cookies=cookies, timeout=10)
    dec = _rc4_crypt(snonce, base64.b64decode(resp.text))
    return json.loads(dec.decode("utf-8", errors="replace"))


def discover_all_xiaomi_devices(session_data: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    sess = session_data or load_saved_session()
    if not sess:
        return []

    found: List[Dict[str, Any]] = []
    for region in ("us", "de", "cn", "sg"):
        try:
            res = xiaomi_api_call(
                sess,
                region,
                "/home/device_list",
                {"getVirtualModel": True, "getHuamiDevices": 1, "get_split_device": False, "support_smart_home": True},
            )
            devs = res.get("result", {}).get("list", [])
            for d in devs:
                found.append({
                    "region": region,
                    "name": d.get("name"),
                    "did": d.get("did"),
                    "model": d.get("model"),
                    "localip": d.get("localip"),
                    "token": d.get("token"),
                    "isOnline": d.get("isOnline"),
                    "prop": d.get("prop", {}),
                })
        except Exception:
            continue
    return found


def sync_romina_status() -> Dict[str, Any]:
    """
    Lee el estado del robot aspiradora en Xiaomi Cloud y actualiza `romina_robot`
    en `device_state_cache` (si está barriendo -> `is_active = 1`, si está en base -> `is_active = 0`).
    """
    sess = load_saved_session()
    if not sess:
        return {"ok": False, "configured": False}

    devs = discover_all_xiaomi_devices(sess)
    for d in devs:
        model = str(d.get("model", "")).lower()
        name = str(d.get("name", ""))
        if any(k in model for k in ("vacuum", "roborock", "dreame", "viomi", "ijai", "roidmi")) or "romina" in name.lower():
            prop = d.get("prop", {})
            state_str = str(prop).lower()
            is_cleaning = any(k in state_str for k in ("sweeping", "cleaning", "working", "mopping", "'state': '5'", "'state': 5"))
            status_txt = "Barriendo" if is_cleaning else "En base (Cargada)"
            with database.db_session() as conn:
                conn.execute(
                    "UPDATE device_state_cache SET status_text = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'romina_robot'",
                    (status_txt, 1 if is_cleaning else 0),
                )
            return {"ok": True, "robot": d, "is_cleaning": is_cleaning}

    return {"ok": True, "devices_found": len(devs)}


def get_qr_status() -> Dict[str, Any]:
    saved = load_saved_session()
    if saved:
        return {
            "status": "authenticated",
            "userId": saved.get("userId"),
            "devices": saved.get("devices", []),
        }
    return dict(_QR_STATE)
