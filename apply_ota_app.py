import sys
import re
from pathlib import Path

app_path = Path('/root/epaper-hub/app.py')
content = app_path.read_text(encoding='utf-8')

# 1. Update hub() function to filter devices and pass ota_info
old_hub = '''@app.route("/hub")
def hub():
    gastos_sum = database.get_gastos_summary()
    nota = database.get_active_nota()
    devices = database.get_all_device_states()
    weather = fetch_weather()
    fotos = database.list_fotos(limit=6)
    return render_template(
        "hub.html",
        state=_RUNTIME_STATE,
        gastos_sum=gastos_sum,
        nota=nota,
        devices=devices,
        weather=weather,
        fotos=fotos,
        cache_bust=int(time.time()),
    )'''

new_hub = '''OTA_DIR = config.BASE_DIR / "static" / "ota"
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
    )'''

content = content.replace(old_hub, new_hub)

# 2. Add OTA endpoints before if __name__ == "__main__":
ota_endpoints = '''
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
'''

content = content.replace('if __name__ == "__main__":', ota_endpoints)
app_path.write_text(content, encoding='utf-8')
print("app.py updated successfully!")
