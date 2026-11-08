"""
app.py — Entrypoint Flask para E-Paper ACeP 7-Color Smart Dashboard & Mobile Hub.
"""

from __future__ import annotations

import base64
import hashlib
import io
import time
from datetime import datetime
from typing import Any, Dict

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from PIL import Image, ImageOps

import config
import database
from generator.dither import dither_image_acep, apply_acep_tone_mapping
from generator.layout import build_screen_buffer
from generator.weather import fetch_weather
from integrations.google_cal import get_upcoming_events
from integrations.home_assistant import process_ha_webhook_payload
from integrations.tuya_client import sync_irrigation_status
from integrations.xiaomi_client import get_qr_status, start_qr_login_session, sync_romina_status

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
app.config["MAX_FORM_MEMORY_SIZE"] = 32 * 1024 * 1024

_RUNTIME_STATE: Dict[str, Any] = {
    "current_mode": "dashboard",
    "orientation": "vertical",
    "last_render_ms": 0.0,
    "last_updated": "--:--:--",
    "esp32_telemetry": {
        "ip": "192.168.1.145",
        "rssi": "-60 dBm",
        "vbat": "4.02 V (88%)",
        "wake_reason": "TIMER / 1 TOQUE",
    },
}


def _trigger_screen_rebuild(mode: str | None = None, force_integrations: bool = False) -> Dict[str, Any]:
    target_mode = mode if mode else _RUNTIME_STATE["current_mode"]
    _RUNTIME_STATE["current_mode"] = target_mode

    if force_integrations:
        sync_irrigation_status()
        fetch_weather(force_refresh=True)

    cal_events = get_upcoming_events(max_results=2, force_refresh=force_integrations)
    info = build_screen_buffer(
        mode=target_mode,
        calendar_events=cal_events,
        esp32_telemetry=_RUNTIME_STATE["esp32_telemetry"],
        orientation=_RUNTIME_STATE["orientation"],
    )
    _RUNTIME_STATE["last_render_ms"] = info["elapsed_ms"]
    _RUNTIME_STATE["last_updated"] = datetime.now().strftime("%H:%M:%S")
    return info


with app.app_context():
    database.init_db()
    if not config.SCREEN_BIN_PATH.exists():
        _trigger_screen_rebuild("dashboard")


@app.route("/")
def index():
    return redirect(url_for("hub"))


OTA_DIR = config.BASE_DIR / "static" / "ota"
OTA_VERSION_FILE = OTA_DIR / "version.json"
OTA_FIRMWARE_FILE = OTA_DIR / "firmware.bin"

def get_ota_info():
    if not OTA_DIR.exists():
        OTA_DIR.mkdir(parents=True, exist_ok=True)
    if OTA_VERSION_FILE.exists():
        try:
            data = json.loads(OTA_VERSION_FILE.read_text(encoding="utf-8"))
            data["has_binary"] = OTA_FIRMWARE_FILE.exists()
            return data
        except Exception:
            pass
    return {
        "version": "1.0.0",
        "filename": "firmware_v1.0.0.bin",
        "uploaded_at": "2026-11-05 00:30:00",
        "size_bytes": 0,
        "md5": "",
        "changelog": "Versión base con soporte OTA",
        "has_binary": OTA_FIRMWARE_FILE.exists(),
    }

@app.route("/hub")
def hub():
    gastos_sum = database.get_gastos_summary()
    nota = database.get_active_nota()
    all_devs = database.get_all_device_states()
    devices = [d for d in all_devs if d.get("enabled") and d.get("integration") in ("tuya", "xiaomi")]
    weather = fetch_weather()
    fotos = database.list_fotos(limit=6)
    ota_info = get_ota_info()
    return render_template(
        "hub.html",
        state=_RUNTIME_STATE,
        gastos_sum=gastos_sum,
        nota=nota,
        devices=devices,
        weather=weather,
        fotos=fotos,
        ota=ota_info,
        cache_bust=int(time.time()),
    )


@app.route("/gastos", methods=["GET", "POST"])
def gastos_view():
    if request.method == "POST":
        action = request.form.get("action", "upsert")
        row_id = request.form.get("row_id", "").strip()
        try:
            if action == "pay_total" and row_id:
                database.registrar_pago_tarjeta(int(row_id), 0, modo_pago="total")
                flash("Tarjeta/servicio marcado como PAGADO ($0).", "success")
            elif action == "pay_min" and row_id:
                database.registrar_pago_tarjeta(int(row_id), 0, modo_pago="minimo")
                flash("Pago mínimo descontado del saldo.", "success")
            elif action == "delete" and row_id:
                database.delete_tarjeta_gasto(int(row_id))
                flash("Fila eliminada.", "success")
            else:
                logo_emp = request.form.get("logo_empresa", "galicia").strip()
                logo_gas = request.form.get("logo_gasto", "amex").strip()
                etiqueta = request.form.get("etiqueta", "").strip()
                vencimiento = request.form.get("vencimiento", "").strip()
                total = float(request.form.get("total", "0") or 0)
                minimo = float(request.form.get("minimo", "0") or 0)
                saldo = float(request.form.get("saldo", str(total)) or 0)
                database.upsert_tarjeta_gasto(
                    logo_empresa=logo_emp,
                    logo_gasto=logo_gas,
                    total=total,
                    minimo=minimo,
                    saldo=saldo,
                    etiqueta=etiqueta,
                    vencimiento=vencimiento,
                    row_id=int(row_id) if row_id else None,
                )
                flash("Fila guardada y pantalla E-Paper actualizada.", "success")
            _trigger_screen_rebuild("dashboard")
        except Exception as exc:
            flash(f"Error: {exc}", "error")
        return redirect(url_for("gastos_view"))

    tarjetas = database.list_tarjetas_gastos()
    totals = database.get_tarjetas_totals()
    return render_template("gastos.html", tarjetas=tarjetas, totals=totals)



@app.route("/domotica", methods=["GET", "POST"])
def domotica_view():
    from integrations.tuya_client import (
        DEVICE_ASSIGNMENTS_FILE,
        fetch_all_tuya_devices,
        load_device_assignments,
    )
    from integrations.google_cal import load_gcal_config, save_gcal_ical_url
    import json

    if request.method == "POST":
        form_type = request.form.get("form_type", "device_row")
        if form_type == "save_assignments":
            new_map = {}
            for k, v in request.form.items():
                if k.startswith("assign_") and v.strip():
                    dev_id = k[len("assign_"):]
                    new_map[dev_id] = v.strip()
            DEVICE_ASSIGNMENTS_FILE.write_text(json.dumps(new_map, indent=2), encoding="utf-8")
            sync_irrigation_status()
            _trigger_screen_rebuild("dashboard")
            flash("Asignaciones Pina / Santiago guardadas y sincronizadas en vivo.", "success")
        elif form_type == "gcal_config":
            ical_url = request.form.get("ical_url", "").strip()
            save_gcal_ical_url(ical_url)
            _trigger_screen_rebuild("dashboard", force_integrations=True)
            flash("URL de Google Calendar guardada y eventos actualizados.", "success")
        else:
            dev_id = request.form.get("device_id", "").strip()
            enabled = request.form.get("enabled") == "1"
            is_active = request.form.get("is_active") == "1"
            show_mode = request.form.get("show_mode", "always").strip()
            status_text = request.form.get("status_text", "").strip()
            if dev_id:
                database.update_device_config(dev_id, enabled, show_mode, is_active, status_text)
                _trigger_screen_rebuild("dashboard")
                flash("Dispositivo actualizado y pantalla regenerada.", "success")
        return redirect(url_for("domotica_view"))

    devices = database.get_all_device_states()
    tuya_devices = fetch_all_tuya_devices()
    assignments = load_device_assignments()
    gcal_cfg = load_gcal_config()
    return render_template(
        "domotica.html",
        devices=devices,
        tuya_devices=tuya_devices,
        assignments=assignments,
        gcal_cfg=gcal_cfg,
        xiaomi_state=get_qr_status(),
    )

@app.route("/nota", methods=["GET", "POST"])
def nota_view():
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "clear":
            database.clear_active_notas()
            _trigger_screen_rebuild("dashboard")
            flash("Post-it borrado de la pantalla.", "success")
            return redirect(url_for("nota_view"))

        mensaje = request.form.get("mensaje", "").strip()
        expira_en = request.form.get("expira_en", "").strip() or None
        if mensaje:
            database.set_active_nota(mensaje=mensaje, expira_en=expira_en)
            _trigger_screen_rebuild("dashboard")
            flash("¡Post-it fijado en la pantalla E-Paper!", "success")
        else:
            flash("Escribí un mensaje antes de fijar la nota.", "error")
        return redirect(url_for("nota_view"))

    nota_actual = database.get_active_nota()
    return render_template("postit.html", nota=nota_actual)


@app.route("/subir-foto", methods=["GET", "POST"])
def subir_foto_view():
    if request.method == "POST":
        orientation = request.form.get("orientation", _RUNTIME_STATE["orientation"]).lower().strip()
        if orientation not in ("horizontal", "vertical"):
            orientation = "horizontal"
        _RUNTIME_STATE["orientation"] = orientation

        set_mode_now = request.form.get("activate_frame", "1") == "1"
        cropped_b64 = request.form.get("cropped_image_b64", "")

        try:
            if "cropped_blob" in request.files and request.files["cropped_blob"].filename:
                img = Image.open(request.files["cropped_blob"].stream).convert("RGB")
            elif cropped_b64 and "," in cropped_b64:
                raw_bytes = base64.b64decode(cropped_b64.split(",", 1)[1])
                img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            elif "photo_file" in request.files and request.files["photo_file"].filename:
                img = ImageOps.exif_transpose(Image.open(request.files["photo_file"].stream)).convert("RGB")
            else:
                raise ValueError("Seleccioná una imagen primero.")

            target_dims = (
                (config.DISPLAY_HEIGHT, config.DISPLAY_WIDTH)
                if orientation == "vertical"
                else (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
            )

            ts_name = datetime.now().strftime(f"foto_{orientation[:3]}_%Y%m%d_%H%M%S.png")
            orig_path = config.UPLOADS_DIR / ts_name
            proc_path = config.PROCESSED_DIR / ts_name

            img_fitted = ImageOps.fit(img, target_dims, method=Image.Resampling.LANCZOS)
            img_fitted.save(orig_path, format="PNG")

            toned = apply_acep_tone_mapping(img_fitted, target_size=target_dims)
            dither_out = dither_image_acep(toned, algorithm="atkinson", apply_tone_map=False)
            dither_out["preview_calibrated"].save(proc_path, format="PNG")

            database.register_foto(ts_name)
            if set_mode_now:
                _RUNTIME_STATE["current_mode"] = "photo_frame"
                build_screen_buffer(mode="photo_frame", orientation=orientation)

            dim_label = "480×800 Vertical" if orientation == "vertical" else "800×480 Horizontal"
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"ok": True, "message": f"Foto ({dim_label}) procesada y enviada al marco."})

            flash(f"¡Foto ({dim_label}) calibrada en CIELAB y enviada al marco E-Paper!", "success")
            return redirect(url_for("subir_foto_view"))
        except Exception as exc:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"ok": False, "error": str(exc)}), 400
            flash(f"Error al procesar la foto: {exc}", "error")
            return redirect(url_for("subir_foto_view"))

    fotos = database.list_fotos(limit=12)
    return render_template("upload_photo.html", fotos=fotos, current_orientation=_RUNTIME_STATE["orientation"])


@app.route("/api/render", methods=["POST"])
def api_render():
    payload = request.get_json(silent=True) or request.form
    mode = payload.get("mode", _RUNTIME_STATE["current_mode"])
    if "orientation" in payload:
        ori = str(payload.get("orientation")).lower().strip()
        if ori in ("horizontal", "vertical"):
            _RUNTIME_STATE["orientation"] = ori
    force_int = str(payload.get("force_integrations", "false")).lower() in ("1", "true", "yes")

    if mode in ("carrusel", "auto", "cycle"):
        _RUNTIME_STATE["current_mode"] = "carrusel"
        _RUNTIME_STATE["auto_cycle_index"] = 0
        info = _trigger_screen_rebuild(mode="dashboard", force_integrations=force_int)
        info["mode"] = "carrusel (dashboard)"
        _RUNTIME_STATE["rendered_mode"] = "carrusel"
    else:
        _RUNTIME_STATE["current_mode"] = mode
        info = _trigger_screen_rebuild(mode=mode, force_integrations=force_int)
        _RUNTIME_STATE["rendered_mode"] = mode

    if request.accept_mimetypes.accept_html and not request.is_json:
        flash(f"Buffer regenerado en {info['elapsed_ms']} ms (Modo: {info['mode']}).", "success")
        return redirect(url_for("hub"))
    return jsonify({"ok": True, **info})


@app.route("/api/screen.bin", methods=["GET"])
def api_screen_bin():
    touches = request.args.get("touches", "").strip()
    explicit_mode = request.args.get("mode", "").strip()

    rssi = request.args.get("rssi")
    vbat = request.args.get("vbat")
    esp_ip = request.args.get("ip") or request.remote_addr
    if rssi or vbat:
        _RUNTIME_STATE["esp32_telemetry"] = {
            "ip": esp_ip,
            "rssi": f"{rssi} dBm" if rssi else _RUNTIME_STATE["esp32_telemetry"]["rssi"],
            "vbat": f"{vbat} V" if vbat else _RUNTIME_STATE["esp32_telemetry"]["vbat"],
            "wake_reason": f"TOUCH ({touches} toques)" if touches else "POLL_40S",
        }
        database.upsert_device_state(
            device_id="vps_esp32_diag",
            device_name="ESP32 E-Paper",
            integration="vps",
            status_text=f"{_RUNTIME_STATE['esp32_telemetry']['vbat']} | {_RUNTIME_STATE['esp32_telemetry']['rssi']}",
            icon_type="cpu",
        )

    touch_to_mode = {
        "1": "dashboard",
        "2": "calendar_month",
        "3": "photo_frame",
        "4": "guest_wifi",
        "5": "diagnostics",
    }

    if explicit_mode:
        _RUNTIME_STATE["current_mode"] = explicit_mode
    elif touches in touch_to_mode:
        _RUNTIME_STATE["current_mode"] = touch_to_mode[touches]

    is_carrusel = (_RUNTIME_STATE.get("current_mode") in ("auto", "cycle", "carrusel")) or (touches in ("auto", "cycle", "carrusel", "next"))

    if is_carrusel:
        with database.db_session() as conn:
            fotos_count = conn.execute("SELECT COUNT(*) FROM fotos WHERE activa = 1").fetchone()[0]
        fotos_count = max(1, fotos_count)

        steps = ["dashboard", "calendar_month"]
        for _ in range(fotos_count):
            steps.append("photo_frame")
        steps.append("guest_wifi")
        steps.append("diagnostics")

        cycle_idx = _RUNTIME_STATE.get("auto_cycle_index", 0)
        target_mode = steps[cycle_idx % len(steps)]
        _RUNTIME_STATE["auto_cycle_index"] = (cycle_idx + 1) % len(steps)
        info = _trigger_screen_rebuild(mode=target_mode)
    else:
        target_mode = _RUNTIME_STATE["current_mode"]
        if not config.SCREEN_BIN_PATH.exists() or _RUNTIME_STATE.get("rendered_mode") != target_mode:
            info = _trigger_screen_rebuild(mode=target_mode)
            _RUNTIME_STATE["rendered_mode"] = target_mode
        else:
            info = {"mode": target_mode, "elapsed_ms": _RUNTIME_STATE.get("last_render_ms", 0.0)}

    raw_bytes = config.SCREEN_BIN_PATH.read_bytes()
    etag = hashlib.md5(raw_bytes).hexdigest()

    if request.headers.get("If-None-Match") == etag:
        return Response(status=304, headers={"ETag": etag, "X-Epaper-Mode": info["mode"]})

    return Response(
        raw_bytes,
        status=200,
        mimetype="application/octet-stream",
        headers={
            "Content-Length": str(len(raw_bytes)),
            "ETag": etag,
            "X-Epaper-Mode": info["mode"],
            "X-Render-Ms": str(info.get("elapsed_ms", 0.0)),
            "Cache-Control": "no-cache",
        },
    )


@app.route("/api/webhook/home-assistant", methods=["POST"])
def api_ha_webhook():
    payload = request.get_json(silent=True) or {}
    res = process_ha_webhook_payload(payload)
    if res.get("updated_count", 0) > 0:
        _trigger_screen_rebuild()
    return jsonify(res)


@app.route("/api/tuya/sync", methods=["POST"])
def api_tuya_sync():
    res = sync_irrigation_status()
    _trigger_screen_rebuild()
    return jsonify(res)



@app.route("/api/xiaomi/start-qr", methods=["POST"])
def api_xiaomi_start_qr():
    return jsonify(start_qr_login_session())


@app.route("/api/xiaomi/status", methods=["GET"])
def api_xiaomi_status():
    return jsonify(get_qr_status())


@app.route("/ota")
def ota_view():
    ota = get_ota_info()
    return render_template("ota.html", ota=ota)


@app.route("/api/ota/check", methods=["GET"])
def api_ota_check():
    client_version = request.args.get("version", "").strip()
    ota = get_ota_info()
    latest_version = ota.get("version", "1.0.0")

    update_available = False
    if ota.get("has_binary"):
        if not client_version or client_version != latest_version:
            update_available = True

    return jsonify({
        "update_available": update_available,
        "client_version": client_version,
        "latest_version": latest_version,
        "size_bytes": ota.get("size_bytes", 0),
        "md5": ota.get("md5", ""),
        "download_url": f"{request.host_url.rstrip('/')}/api/ota/download",
    })


@app.route("/api/ota/download", methods=["GET"])
def api_ota_download():
    ota = get_ota_info()
    if not OTA_FIRMWARE_FILE.exists():
        return jsonify({"error": "No firmware binary available"}), 404

    esp_ver = request.headers.get("x-ESP32-version", "").strip()
    if esp_ver and esp_ver == ota.get("version"):
        return Response(status=304)

    raw_bytes = OTA_FIRMWARE_FILE.read_bytes()
    md5_hash = ota.get("md5") or hashlib.md5(raw_bytes).hexdigest()

    return Response(
        raw_bytes,
        status=200,
        mimetype="application/octet-stream",
        headers={
            "Content-Length": str(len(raw_bytes)),
            "x-MD5": md5_hash,
            "ETag": md5_hash,
            "Content-Disposition": f'attachment; filename="{ota.get("filename", "firmware.bin")}"',
            "Cache-Control": "no-cache",
        },
    )


@app.route("/api/ota/upload", methods=["POST"])
def api_ota_upload():
    f = request.files.get("firmware_file")
    new_version = request.form.get("version", "").strip()
    changelog = request.form.get("changelog", "").strip()

    if not f or not f.filename:
        flash("Seleccioná un archivo de firmware .bin.", "error")
        return redirect(url_for("ota_view"))

    if not f.filename.lower().endswith(".bin"):
        flash("El archivo debe tener extensión .bin.", "error")
        return redirect(url_for("ota_view"))

    if not new_version:
        flash("Indicá el número de versión (ej: 1.0.1).", "error")
        return redirect(url_for("ota_view"))

    content = f.read()
    if len(content) < 50000:
        flash("El archivo es demasiado pequeño para ser un firmware de ESP32.", "error")
        return redirect(url_for("ota_view"))

    OTA_DIR.mkdir(parents=True, exist_ok=True)
    OTA_FIRMWARE_FILE.write_bytes(content)

    archive_file = OTA_DIR / f"firmware_v{new_version}.bin"
    archive_file.write_bytes(content)

    md5_hash = hashlib.md5(content).hexdigest()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    info = {
        "version": new_version,
        "filename": f"firmware_v{new_version}.bin",
        "uploaded_at": now_str,
        "size_bytes": len(content),
        "md5": md5_hash,
        "changelog": changelog,
    }
    OTA_VERSION_FILE.write_text(json.dumps(info, indent=2), encoding="utf-8")

    flash(f"¡Firmware v{new_version} publicado con éxito! ({len(content):,} bytes). El ESP32 se actualizará al próximo despertar.", "success")
    return redirect(url_for("ota_view"))

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False)
