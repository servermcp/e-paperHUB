# 📋 Changelog — e-paperHUB

Registro histórico de versiones y cambios del servidor backend y del firmware de la **Seeed Studio XIAO ESP32-C6**.

---

## [v1.1.8] — 2026-11-11
### Corregido
- **Fijación de Modo y Control Remoto Web (`/api/render` y `/api/dashboard/theme`):**
  - Se corrigió la condición en `api_screen_bin` que trataba `touches=auto` del ESP32 como una orden forzada de avance de carrusel, lo que anulaba la selección hecha por el usuario desde la web y cambiaba de pantalla en la siguiente petición.
  - Ahora se respeta el modo seleccionado por el usuario en el panel web (`_RUNTIME_STATE["current_mode"]`). Si se elige Dashboard, Calendario o Marco Foto, la pantalla queda fija en ese modo sin rotar.
  - Al cambiar de tema (Crayón, Muji o Bento), el modo se fija automáticamente en Dashboard para mostrar el tema seleccionado inmediatamente en el E-Paper.
  - La rotación continua solo se activa si el usuario selecciona explícitamente *"Carrusel Auto"*.
  - En el firmware ESP32-C6, la pulsación manual del botón `BOOT` ahora envía `touches=next` para diferenciar saltos manuales de ciclos periódicos `touches=auto`.

---

## [v1.1.7] — 2026-11-09
### Agregado
- **Sincronización Automática en Segundo Plano de Domótica IoT (Tuya) & Smart TTL:**
  - **Worker Demonio Continuo (`_start_background_iot_worker`):** Hilo en segundo plano en `app.py` que consulta periódicamente (cada 60s) la nube de Tuya Cloud para obtener el estado real de los 22 dispositivos (portón, luces, temperatura, riego).
  - **Detección Automática de Cambios de Estado:** Si el portón se abre o se cierra, o cambia el número de luces encendidas, se detecta el cambio de inmediato (`state_changed`), se actualiza la base de datos `device_state_cache` y se dispara la regeneración de pantalla en caso de estar en el Dashboard o modo carrusel.
### Corregido
- **Bucle Infinito de Reinicio OTA en XIAO ESP32-C6:** Se agregó el `import json` faltante en `app.py` que causaba que `get_ota_info()` fallara silenciosamente con `NameError` y reportara versión base `1.0.0`. Esto provocaba que el endpoint `/api/ota/check` respondiera falsamente `update_available: true` a la placa (que reportaba `1.1.2-carrusel`), atrapándola en un ciclo sin fin de descarga y re-flasheo de firmware sin llegar al ciclo del carrusel.
- **Definición de `OTA_SCREEN_BIN_FILE` (`static/ota/ota_screen.bin`):** Se definió la variable faltante en `app.py` que causaba un error 500 al solicitar la pantalla *"ACTUALIZANDO... ESP32"*.

---

## [v1.1.6] — 2026-11-09
### Agregado
- **3 Temas de Dashboard Seleccionables desde la Web (`crayon`, `muji`, `bento`):**
  - **🖍️ Crayón Real (Trazo de Nene):** Renderizado auténtico con la tipografía `Crayon Libre` (CC0 con textura de cera), líneas onduladas a mano, cajas con resaltador y sellitos de estado `¡PAGADO!`.
  - **⚪ Muji Minimal (E-Ink Studio):** Diseño sobrio y limpio en sintonía directa con el nuevo Calendario mensual. Tipografía geométrica `Roboto`, divisores sutiles de 1px a todo lo ancho y cápsulas redondeadas.
  - **🍱 Bento Grid (Modular Tech):** Módulos contemporáneos redondeados de alta densidad informativa con borde definido y distribución prolija.
- **Pack Completo de 7 Íconos de Clima en Crayón (`static/icons/weather_crayon/`):**
  - Generación asistida por IA reproduciendo la técnica de cera, espirales y trazo infantil del sol original aportado por el usuario.
  - Íconos incluidos y mapeados automáticamente a los códigos WMO de Open-Meteo: `01d` (Sol Despejado), `01n` (Luna Serena), `02d/03d` (Sol con Nubes), `04d` (Cubierto), `10d` (Lluvia), `11d` (Tormenta) y `13d` (Nieve).
- **Control Web y Persistencia en Base de Datos:**
  - Nueva tabla `system_config` en SQLite para persistir `dashboard_theme`.
  - Botonera de cambio instantáneo de 1 clic en el panel web (`hub.html`), regenerando el búfer E-Paper en caliente.
  - Nuevo endpoint `/api/dashboard/theme` (POST) para cambio vía web o API.
  - Aprovechamiento del ancho total (full-width) de 480 px con márgenes mínimos de 14-16 px.
- **Galería Visual de Capturas en README (`docs/screenshots/`):**
  - Incorporación de capturas de pantalla auténticas a resolución nativa (`480×800 px`) para el E-Paper ACeP de 7 colores: Dashboard Crayón, Dashboard Muji, Calendario Mensual Muji y foto dithered en primer plano de *Las Gaturrakas* (sin presencia de humanos).

---

## [v1.1.5] — 2026-11-09
### Agregado
- **Rediseño Completo del Calendario Mensual (Estilo Muji / Minimalista Japonés):**
  - Reproducción pixel-perfect del diseño de papel minimalista (`Calendario.jpg`) para panel ACeP 7 Colores (`480×800` vertical).
  - Fondo blanco puro con fuentes tipográficas nítidas (`Roboto-Bold`, `Roboto-Medium`, `Roboto-Regular`).
  - Cabecera: Año (izq), Número Gigante de Mes (centro) y Hora actual en tiempo real (der).
  - Encabezados de días en español (`D L M M J V S`): Domingo en Rojo, Lunes a Viernes en Negro sólido, Sábado en Azul cian.
  - Placa circular sólida en Rojo para el día actual ("HOY") con número en Blanco invertido.
  - Días de desborde del mes previo y posterior desvanecidos con trama checkerboard 50% (gris claro en tinta electrónica).
  - Feriados nacionales argentinos destacados automáticamente con número en Rojo y pastilla informativa.
- **Barras y Pastillas de Eventos (Google Calendar iCal):**
  - Eventos de varios días: Barras horizontales continuas con extremos redondeados que cruzan las columnas de la semana y continúan en la siguiente fila si cruzan de semana, con el título centrado bajo la barra.
  - Eventos de un solo día: Pastillas redondeadas centradas bajo el número del día con etiqueta legible.
  - Categorización cromática inteligente (Viajes/Vacaciones -> Verde, Cumpleaños/Feriados -> Rojo, Turnos/Médico -> Azul, Finanzas/Pagos -> Naranja).
  - Mapeo directo y ultra-nítido a los índices de hardware ACeP (`0x0..0x6`).

---

## [v1.1.4] — 2026-11-08
### Agregado
- **Gestión y Eliminación de Fotos (`/fotos/eliminar/<id>`):**
  - Botón de eliminación con confirmación modal interactiva en la galería del panel web (`/subir-foto`).
  - Limpieza sincronizada en base de datos SQLite (`fotos`) y borrado seguro de los archivos físicos en disco (`static/uploads/` y `static/processed/`).
  - Auto-actualización del búfer de pantalla si la foto eliminada estaba actualmente desplegada en el marco E-Paper.
- **Activación Rápida de Fotos (`/fotos/activar/<id>`):**
  - Botón *"Mostrar"* en cada tarjeta de la galería para enviar cualquier foto previa directamente a la pantalla física sin tener que volver a subirla ni recortarla.
  - Ampliación del límite de fotos visualizadas en la galería a 36 elementos.

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
