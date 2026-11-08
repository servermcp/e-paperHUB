# 📋 Changelog — e-paperHUB

Registro histórico de versiones y cambios del servidor backend y del firmware de la **Seeed Studio XIAO ESP32-C6**.

---

## [v1.1.3] — 2026-11-08
### Mejorado
- **Calibración Perceptual CIE94 para E-Paper ACeP 7-Color:** Reemplazo de la métrica euclidiana cruda CIELAB 1976 por la norma estándar **CIE94** (con escala de tolerancia cromática $S_C$ y de tono $S_H$). Esto desbloquea el uso natural del pigmento Amarillo en pieles y evita que el algoritmo descarte el amarillo en favor exclusivo del Naranja y Rojo.
- **Protección Inteligente de Tonos de Piel (Skin-Tone Protection):**
  - Detección adaptativa de matices cálidos de piel humana (campana gaussiana centrada en $\sim 25^\circ$).
  - Restricción de saturación en pieles para permitir un dithering suave entre Blanco y Amarillo sin provocar caras "coloradas" o manchadas de rojo/naranja.
  - Levantamiento de sombras y medios tonos aplicado estrictamente sobre la **Luminancia ($Y$)**, evitando que las curvas S de contraste separen los canales RGB y fuercen saturaciones rojas extremas.
  - Micro-ganancia de exposición para rostros en interiores o con iluminación tenue.

---

## [v1.1.2-carrusel] — 2026-11-08
### Agregado
- **Pantalla E-Paper `"ACTUALIZANDO... ESP32"` pre-OTA (`static/ota/ota_screen.bin`):** Adaptación de la ilustración de *Las Gaturrakas* en `480×800` vertical con dithering ACeP 7-Color (fondo blanco limpio y trazos negros puros).
- **Flujo Pre-OTA y Restauración Post-Reinicio:** Cuando la XIAO ESP32-C6 detecta una nueva versión OTA, primero dibuja en el E-Paper la pantalla `"ACTUALIZANDO... ESP32"`, luego descarga e instala el firmware, y al reiniciar vuelve a mostrar exactamente la misma pantalla que estaba activa antes de la actualización (`resume_after_ota` en `app.py`).

---

## [v1.1.1-carrusel] — 2026-11-08
### Agregado
- **Auto-compilador OTA para XIAO ESP32-C6 (`mode=build_ota`):** Compilación automática del archivo `.bin` usando `arduino-cli` (`esp32:esp32:XIAO_ESP32C6`), incremento automático de versión en `epaper_acep_hub_esp32_c6.ino` y publicación directa en `/static/ota/firmware.bin` y `/static/ota/version.json`.
- **Chequeo OTA continuo en `loop()`:** La XIAO ESP32-C6 ahora verifica si hay actualizaciones OTA tanto al encender (`setup()`) como en cada ciclo del carrusel (`loop()`).
- **Gestión cifrada de secretos (`.env` + AES-256):** Carga automática de `.env` en `config.py`, plantillas públicas `.env.example` y `esp32_firmware/secrets.example.h`, e inyección cifrada de claves al servidor de Tokyo.
- **Documentación:** Creación de `README.md` principal y `CHANGELOG.md`.

### Limpieza
- Eliminados 17 scripts temporales de prueba/parches de la raíz del proyecto (`apply_*.py`, `fix_*.py`, `list_*.py`, `migrate_*.py`, `patch_*.py`, `discover_xiaomi.py`, `test_wifi_render.py`, `trigger_rebuild.py`, `update_tuya_sync.py`, `check_visible.py`, `cleanup_domotica.py`, `download_inkypi_icons.py`, `process_inkypi_icons.py`).

---

## [v1.1.0-carrusel] — 2026-11-06
### Agregado
- Soporte nativo para **Seeed Studio XIAO ESP32-C6** (`epaper_acep_hub_esp32_c6.ino`).
- Modo carrusel automático (60 segundos por pantalla) + salto instantáneo con botón `BOOT` (`GPIO 9`).

---

## [v1.0.0] — 2026-11-05
### Agregado
- Pipeline gráfico calibrado para panel **E-Paper 7.3" ACeP 7-Color** (`800×480`, dithering Atkinson/Sierra Lite en CIELAB).
- Integraciones en vivo con **Open-Meteo**, **Google Calendar (`.ics`)**, **Tuya Smart / Smart Life** (22 dispositivos) y **Xiaomi Cloud** (aspiradora robot Romina).
- Generador automático del cómic diario *"Las Gaturrakas"* con **Google Gemini API**.
- Calendario mensual estilo Doodle con tipografía `Patrick Hand`.
- Servidor web Mobile Hub (`/hub`, `/gastos`, `/domotica`, `/subir-foto`, `/notas`, `/ota`).
