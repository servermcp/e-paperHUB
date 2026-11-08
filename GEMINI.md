# 🤖 Contexto para Agentes de Antigravity (IDE Desktop & Cloud VM) — `e-paperHUB`

Si sos un agente ejecutándose en el **Antigravity IDE de escritorio** (en la PC de casa de Matías) o en **Antigravity Web (Cloud VM)**, seguí siempre estas reglas al trabajar en este repositorio:

---

## ⚠️ Reglas Críticas de Seguridad
1. **Servidor Compartido (`45.76.198.7`):** El VPS de Tokyo aloja también un **bot de trading de criptomonedas**. **PROHIBIDO** tocar, detener, modificar o inspeccionar cualquier archivo o servicio fuera de `/root/epaper-hub` y `epaper-hub.service`.
2. **Repositorio Público (`servermcp/e-paperHUB`):** Este repositorio es **público**. **NUNCA** escribas API keys, contraseñas Wi-Fi, contraseñas SSH ni URLs privadas de iCal en `config.py`, archivos `.ino` o documentos Markdown.
   - En Python (`config.py`), leé siempre desde variables de entorno con fallback vacío (`os.getenv("...", "")`) y agregá el nombre de la variable vacía en `.env.example`.
   - En el firmware de ESP32 (`esp32_firmware/*.ino`), las credenciales Wi-Fi se leen desde `esp32_firmware/secrets.h` (ignorado en `.gitignore`), manteniendo `esp32_firmware/secrets.example.h` como plantilla pública.
3. **Orden y Registro de Cambios:**
   - No dejes scripts temporales de prueba/migración `.py` en la raíz del proyecto (solo deben existir `app.py`, `config.py` y `database.py` en la raíz).
   - Registrá cada nueva funcionalidad, corrección o versión de firmware en `CHANGELOG.md` y en la sección **Log de Cambios** de `README.md`.

---

## 🏗️ Arquitectura en Producción (VPS Tokyo `45.76.198.7`)
- **Directorio en el servidor:** `/root/epaper-hub`
- **Secretos en el servidor:** `/root/epaper-hub/.env` (cargado automáticamente por `config.py`) y `/root/epaper-hub/esp32_firmware/secrets.h`.
- **Servicio Systemd:** `epaper-hub.service` (puerto `5050`, entorno virtual `/root/epaper-hub/venv/bin/python`).
- **Compilador y Servidor OTA Automático para Seeed Studio XIAO ESP32-C6:**
  - El archivo fuente es `esp32_firmware/epaper_acep_hub_esp32_c6.ino` (FQBN `esp32:esp32:XIAO_ESP32C6`).
  - Los binarios compilados se publican en `/root/epaper-hub/static/ota/firmware.bin` junto con `/root/epaper-hub/static/ota/version.json`.
  - Antes de instalar una actualización OTA, la placa solicita `/api/screen.bin?touches=ota_updating` para mostrar en el E-Paper la pantalla `"ACTUALIZANDO... ESP32"` (`static/ota/ota_screen.bin`), luego flashea el firmware y al reiniciar restaura la pantalla previa (`resume_after_ota` en `app.py`).

---

## 🔄 Cómo Desplegar Cambios y Compilar OTA

### A) Desde Antigravity Cloud VM (Navegador)
Usá el comando persistente `~/.gemini/epaperhub_ssh/epaper-ctl.sh` (ver skill `epaperhub-server`):
```bash
# Agregar una nueva API key cifrada con AES-256 al .env de Tokyo:
bash ~/.gemini/epaperhub_ssh/epaper-ctl.sh set-secret NOMBRE_CLAVE "valor"

# Desplegar cambios de código (y auto-compilar OTA si cambió el .ino):
bash ~/.gemini/epaperhub_ssh/epaper-ctl.sh deploy "Descripción del cambio"

# Forzar incremento de versión + compilación y publicación OTA del .bin para ESP32-C6:
bash ~/.gemini/epaperhub_ssh/epaper-ctl.sh build-ota "Notas de la versión OTA"
```

### B) Desde Antigravity IDE en la PC de Casa (Escritorio)
1. **Sincronizar el código con GitHub:**
   ```bash
   git pull origin main
   ```
2. **Traer el `.env` y `secrets.h` desde el servidor de Tokyo (por SSH directo en puerto 22):**
   ```bash
   scp root@45.76.198.7:/root/epaper-hub/.env ./.env
   scp root@45.76.198.7:/root/epaper-hub/esp32_firmware/secrets.h ./esp32_firmware/secrets.h
   ```
3. **Desplegar cambios al servidor de Tokyo:**
   - Subí los cambios limpios a GitHub (`git add -A && git commit -m "..." && git push origin main`).
   - Sincronizá por `rsync` al servidor (respetando las exclusiones de `.env`, `*.db`, `static/ota/firmware.bin`, `static/ota/version.json`) o dispará el workflow `.github/workflows/server.yml` (`mode=deploy` / `mode=build_ota`).
