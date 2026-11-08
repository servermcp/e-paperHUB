"""
integrations/home_assistant.py — Conector de Webhooks y Polling hacia Home Assistant / Google Home
para actualizar el estado de portón, luces exteriores y climatización en `device_state_cache`.
"""

from __future__ import annotations

from typing import Any, Dict, List
import requests

import config
import database


def process_ha_webhook_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa un webhook entrante desde Home Assistant o Google Home Routines.
    Formato JSON esperado:
    {
      "device_id": "ghome_gate_01",
      "device_name": "Portón Garage",
      "integration": "google_home",
      "status_text": "Abierto (hace 2m)",
      "icon_type": "shield-alert"
    }
    O lista de dispositivos bajo la clave "devices".
    """
    devices_list: List[Dict[str, Any]] = []
    if "devices" in payload and isinstance(payload["devices"], list):
        devices_list = payload["devices"]
    elif "device_id" in payload:
        devices_list = [payload]

    updated = 0
    for item in devices_list:
        dev_id = str(item.get("device_id", "")).strip()
        if not dev_id:
            continue
        dev_name = str(item.get("device_name", dev_id)).strip()
        integration = str(item.get("integration", "google_home")).strip()
        if integration not in ("tuya", "google_home", "vps"):
            integration = "google_home"
        status_text = str(item.get("status_text", "Actualizado")).strip()
        icon_type = str(item.get("icon_type", "info")).strip()

        database.upsert_device_state(
            device_id=dev_id,
            device_name=dev_name,
            integration=integration,
            status_text=status_text,
            icon_type=icon_type,
        )
        updated += 1

    return {"ok": True, "updated_count": updated}


def poll_home_assistant_entities(entity_map: Dict[str, Tuple[str, str, str]] | None = None) -> Dict[str, Any]:
    """
    Opcional: Si `HOME_ASSISTANT_TOKEN` está configurado, consulta por REST API
    el estado de las entidades mapeadas en Home Assistant.
    """
    if not config.HOME_ASSISTANT_TOKEN:
        return {"ok": True, "configured": False}

    if entity_map is None:
        entity_map = {
            "cover.porton_garage": ("ghome_gate_01", "Portón Garage", "shield-check"),
            "light.luces_exterior": ("ghome_lights_01", "Luces Exterior", "sun"),
            "climate.living": ("ghome_hvac_01", "Clima Living", "thermometer"),
        }

    headers = {
        "Authorization": f"Bearer {config.HOME_ASSISTANT_TOKEN}",
        "Content-Type": "application/json",
    }
    base_url = config.HOME_ASSISTANT_URL.rstrip("/")
    updated = 0

    for entity_id, (dev_id, dev_name, icon) in entity_map.items():
        try:
            r = requests.get(f"{base_url}/api/states/{entity_id}", headers=headers, timeout=5.0)
            if r.status_code == 200:
                data = r.json()
                state = str(data.get("state", "unknown"))
                attrs = data.get("attributes", {})
                if "temperature" in attrs:
                    state = f"{attrs['temperature']}°C ({state})"
                database.upsert_device_state(dev_id, dev_name, "google_home", state.capitalize(), icon)
                updated += 1
        except Exception:
            continue

    return {"ok": True, "configured": True, "updated_count": updated}
