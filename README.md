# 🖼️ E-Paper ACeP 7-Color Smart Dashboard & Mobile Hub

Sistema integral de **Dashboard Inteligente de Ultra-Bajo Consumo** para pantallas **E-Paper ACeP de 7 colores (`800×480 px`, Waveshare / GoodDisplay 7.3" GDEY073D46)** impulsado por una **Seeed Studio XIAO ESP32-C6** (o ESP32 estándar) y un servidor backend en **Python + Flask**.

La filosofía del proyecto es **Cero Renderizado en el Microcontrolador**: el servidor procesa el clima, la agenda de Google Calendar, el estado de domótica (Tuya / Smart Life / Xiaomi Cloud / Home Assistant), las finanzas del hogar y una tira cómica diaria generada con IA, aplica **Tone Mapping y Dithering perceptual en espacio CIELAB**, y empaqueta un binario crudo de `192.000 bytes` (`4 bits por píxel`) que la ESP32 descarga por Wi-Fi e inyecta directo por SPI al panel E-Paper.

---

## ✨ Características Principales

- 🎨 **Pipeline Gráfico Calibrado para E-Paper ACeP (7 Colores):**
  - Paleta física calibrada bajo iluminante D65 en espacio perceptual **CIELAB**.
  - **Tone Mapping previo** (`+38%` saturación, curva S sigmoide de contraste) con LUT 3D `RGB555 → CIELAB` de alta velocidad (`~140 ms` por frame).
  - Algoritmos de difusión de error **Atkinson** (para fotografías e ilustraciones) y **Sierra Lite** (para gráficos).
  - Capa UI vectorial 1-bit sin dithering para textos, íconos y códigos QR ultra nítidos.
- 🔄 **5 Pantallas en Modo Carrusel Automático (XIAO ESP32-C6) o por Toques:**
  1. **Dashboard Principal:** Clima en vivo (Open-Meteo con íconos estilo InkyPi), próximos eventos de Google Calendar, tabla de gastos/tarjetas con semáforo de estado y domótica en vivo + QR al Hub móvil.
  2. **Calendario Mensual Doodle:** Vista mensual completa con tipografía manuscrita (`Patrick Hand`) y días con eventos destacados.
  3. **Marco de Fotos / Cómic Diario ("Las Gaturrakas"):** Tira cómica diaria generada automáticamente cada mañana con **Google Gemini** según el día de la semana y el clima actual, o fotos subidas desde el celular con recorte interactivo (`Cropper.js`).
  4. **Modo Visitas (QR Wi-Fi):** Tarjeta de bienvenida con código QR estándar `WIFI:T:WPA;S:...` para conectar invitados con la cámara del teléfono.
  5. **Diagnóstico Técnico y Calibración:** Barras de los 7 colores físicos ACeP, telemetría Wi-Fi (`RSSI`, `IP`, `VBAT`) y estado del servidor.
- 📡 **Actualizaciones OTA Automáticas (Cero Arduino IDE):**
  - Compilación automática en la nube (`arduino-cli` + core `esp32:esp32:XIAO_ESP32C6`) e incremento automático de versión SemVer.
  - La placa verifica en el arranque y en cada ciclo si existe una nueva versión en `/api/ota/check`, descarga `/api/ota/download`, se flashea por Wi-Fi y se reinicia sola.

---

## 📁 Estructura del Proyecto

```text
e-paperHUB/
├── app.py                        # Servidor web Flask, endpoints REST y servidor OTA
├── config.py                     # Calibración física ACeP 7-Color y carga automática de .env
├── database.py                   # Capa de persistencia SQLite (gastos, notas, fotos, caché)
├── schema.sql                    # Esquema de base de datos SQLite
├── .env.example                  # Plantilla pública de variables de entorno y API keys
├── generator/                    # Motor gráfico E-Paper (800x480 / 480x800, 4-bit packed)
│   ├── dither.py                 # Tone Mapping + LUT RGB555->CIELAB + Atkinson / Sierra Lite
│   ├── layout.py                 # Renderizador de las 5 pantallas del E-Paper
│   ├── calendar_view.py          # Renderizador del calendario mensual estilo Doodle
│   ├── comic_generator.py        # Generador diario del cómic con Google Gemini API
│   ├── packer.py                 # Empaquetador 2px/byte (192.000 bytes) y vista previa PNG
│   └── weather.py                # Cliente Open-Meteo con caché local
├── integrations/                 # Conectores de Domótica y Calendario
│   ├── tuya_client.py            # Cliente Tuya OpenAPI (HMAC-SHA256) para luces, riego, portón, pileta
│   ├── xiaomi_client.py          # Cliente Xiaomi Cloud (RC4 ssecurity) para robot aspiradora
│   ├── google_cal.py             # Lector de agenda vía URL secreta iCal (.ics) o Service Account
│   └── home_assistant.py         # Conector opcional para Home Assistant REST / Webhooks
├── esp32_firmware/               # Firmwares para el microcontrolador
│   ├── epaper_acep_hub_esp32_c6.ino  # Firmware principal para Seeed Studio XIAO ESP32-C6 (Carrusel + OTA)
│   ├── epaper_acep_hub_esp32.ino     # Firmware alternativo para ESP32 clásico con Deep Sleep
│   └── secrets.example.h         # Plantilla de credenciales Wi-Fi para compilar el firmware
├── templates/                    # Interfaz Web Mobile-First (TailwindCSS + Cropper.js)
│   ├── base.html                 # Layout base oscuro con navegación móvil
│   ├── hub.html                  # Panel de control principal y vista previa en vivo
│   ├── gastos.html               # Gestor de tarjetas, vencimientos y gastos
│   ├── domotica.html             # Asignador de dispositivos Tuya/Xiaomi y Google Calendar
│   ├── upload_photo.html         # Subida y recorte de fotos con selector de dithering
│   ├── postit.html               # Notas rápidas para la pantalla
│   └── ota.html                  # Panel de estado y gestión de versiones de firmware OTA
└── static/                       # Fuentes, íconos ACeP/InkyPi y directorio OTA
```

---

## 🔌 Conexión de Hardware (Seeed Studio XIAO ESP32-C6 + Waveshare 7.3" ACeP)

| Cable Waveshare (8 hilos) | Pin en XIAO ESP32-C6 | GPIO Interno | Función |
| :--- | :--- | :--- | :--- |
| **Rojo** (`VCC`) | `3V3` | `3.3V Out` | Alimentación lógica (**¡Nunca conectar a 5V!**) |
| **Negro** (`GND`) | `GND` | `GND` | Tierra común |
| **Azul** (`DIN / MOSI`) | `D10` | `GPIO 18` | Hardware SPI Data Out |
| **Amarillo** (`CLK / SCK`) | `D8` | `GPIO 19` | Hardware SPI Clock |
| **Naranja** (`CS`) | `D3` | `GPIO 21` | SPI Chip Select |
| **Verde** (`DC`) | `D1` | `GPIO 1` | Data / Command |
| **Blanco** (`RST`) | `D2` | `GPIO 2` | Hardware Reset |
| **Violeta** (`BUSY`) | `D0` | `GPIO 0` | Busy Status |

> **Nota:** El botón `BOOT` integrado en la XIAO ESP32-C6 (`GPIO 9`) permite saltar inmediatamente a la siguiente pantalla del carrusel sin esperar los 60 segundos.

---

## 🚀 Instalación y Configuración Rápida

### 1. Servidor Backend (Python 3.10+)
```bash
git clone https://github.com/servermcp/e-paperHUB.git
cd e-paperHUB
python3 -m venv venv
source venv/bin/activate
pip install flask pillow numpy requests qrcode pycryptodome

# Crear archivo .env con tus claves privadas (nunca se sube a Git)
cp .env.example .env
nano .env

# Iniciar servidor (por defecto en el puerto 5050)
python app.py
```

### 2. Firmware ESP32-C6
1. Para el primer flasheo por USB, copiá `esp32_firmware/secrets.example.h` a `esp32_firmware/secrets.h` y completá tu Wi-Fi y la URL de tu servidor.
2. Una vez flasheada por primera vez, **todas las actualizaciones siguientes se realizan automáticamente por Wi-Fi (OTA)** desde el servidor.

---

## 📋 Log de Cambios (Changelog)

### `2026-11-09` — `v1.1.5` (Nuevo Calendario Minimalista Muji E-Ink con Barras de Eventos)
- **Rediseño Completo del Modo Calendario Mensual (`generator/calendar_view.py`):**
  - Reproducción pixel-perfect de la estética japonesa minimalista (`Calendario.jpg`) para panel ACeP 7 Colores (`480×800` vertical).
  - Fondo blanco puro, fuentes sans-serif nítidas (`Roboto-Bold`, `Roboto-Medium`, `Roboto-Regular`), sin líneas de cuadrícula para máxima limpieza visual.
  - Cabecera: Año (izq), Número Gigante de Mes (centro) y Hora actual en tiempo real (der).
  - Encabezados de días en español (`D L M M J V S`): Domingo en Rojo, Lunes a Viernes en Negro sólido, Sábado en Azul cian.
  - Placa circular sólida en Rojo para el día actual ("HOY") con número en Blanco invertido.
  - Días de desborde del mes previo y posterior renderizados con trama checkerboard al 50% (gris suave de tinta electrónica).
  - Feriados nacionales argentinos destacados en Rojo con etiqueta informativa.
- **Barras y Pastillas de Eventos (Google Calendar iCal):**
  - Eventos de varios días con barras horizontales continuas y esquinas redondeadas que cruzan las columnas y se adaptan semana a semana.
  - Eventos de un día con pastillas redondeadas bajo el número del día.
  - Categorización cromática inteligente (Verde para viajes/vacaciones, Rojo para feriados/cumpleaños, Azul para turnos/médico, Naranja para vencimientos/pagos).
  - Mapeo directo y ultra-nítido a la matriz de hardware ACeP (`0x0..0x6`).

### `2026-11-08` — `v1.1.4` (Gestión, Eliminación y Activación Rápida de Fotos)
- **Eliminación Segura de Fotos (`/fotos/eliminar/<id>`):**
  - Botón de borrado directo con confirmación en la galería de `/subir-foto`.
  - Eliminación sincronizada del registro en la base de datos SQLite y de los archivos en disco (`static/uploads/` y `static/processed/`).
  - Auto-regeneración del búfer del marco E-Paper en caso de que la foto borrada estuviera activa.
- **Activación Rápida en Pantalla (`/fotos/activar/<id>`):**
  - Botón *"Mostrar"* en cada tarjeta de la galería para enviar fotos guardadas directamente al marco E-Paper sin tener que re-subirlas.
  - Galería extendida a 36 fotos por página.

### `2026-11-08` — `v1.1.3` (Calibración Perceptual CIE94 y Protección Inteligente de Tonos de Piel)
- **Corrección de "Caras Coloradas / Quemadas":**
  - Implementación de la norma internacional **CIE94** en la tabla 3D de cuantización perceptual (`generator/dither.py`). Se ponderan el croma ($S_C$) y el tono ($S_H$), eliminando la penalización artificial que excluía al pigmento Amarillo para tonos cálidos.
  - **Skin-Tone Protection:** Detección de matices de piel humana con preservación de saturación natural ($\sim 0.90\times$) y micro-ganancia de exposición en rostros en penumbra.
  - El pre-procesamiento de brillo y contraste S-curve se ejecuta ahora de manera estrictamente preservativa sobre la **Luminancia ($Y$)**, evitando que los canales RGB se separen y saturen artificialmente los rojos.
  - Reducción del boost global de saturación a $+12\%$ (en lugar del $+38\%$ previo que teñía las fotos de rojo y naranja).

### `2026-11-08` — `v1.1.2-carrusel` (Pantalla E-Paper `"ACTUALIZANDO... ESP32"` y Restauración Post-OTA)
- **Pantalla visual de actualización OTA (`static/ota/ota_screen.bin`):** Se adaptó la ilustración de *Las Gaturrakas* (`"ACTUALIZANDO... ESP32"`) a `480×800` vertical con paleta calibrada ACeP de 7 colores (`192.000 bytes`).
- **Secuencia en ESP32-C6 y Backend:** Antes de iniciar `httpUpdate.update()`, el ESP32 solicita `touches=ota_updating` y refresca el panel con la imagen de actualización; una vez flasheado el firmware y reiniciada la placa, el servidor restaura automáticamente la misma pantalla que se estaba mostrando antes del OTA.

### `2026-11-08` — `v1.1.1-carrusel` (Seguridad de Credenciales, Limpieza de Repo y Auto-Compilador OTA)
- **Compilador y Publicador OTA Automático para XIAO ESP32-C6:**
  - Se implementó el flujo `build_ota` con `arduino-cli` (`esp32:esp32:XIAO_ESP32C6`) y caché persistente del core ESP32.
  - Incremento automático de versión SemVer en `esp32_firmware/epaper_acep_hub_esp32_c6.ino` y generación automática de `/static/ota/firmware.bin` + `/static/ota/version.json`.
  - Se agregó chequeo `checkForFirmwareUpdate()` en cada ciclo del `loop()` del ESP32-C6 además del arranque en `setup()`.
- **Protección de Secretos para Repositorio Público:**
  - Se añadió carga automática de `/root/epaper-hub/.env` en `config.py` y se eliminaron todas las claves y contraseñas hardcodeadas del código fuente.
  - Se separaron las credenciales Wi-Fi del firmware a `esp32_firmware/secrets.h` (ignorado por Git) con plantilla pública `secrets.example.h`.
  - Se creó el sistema de sincronización cifrada con AES-256 (`sync_env` y `exec_enc`) para inyectar nuevas API keys en el servidor de producción sin exponerlas en el repositorio ni en los logs de GitHub Actions.
- **Orden y Limpieza del Repositorio:**
  - Se eliminaron 17 scripts temporales de migración/parches de la raíz del proyecto, dejando únicamente los módulos productivos (`app.py`, `config.py`, `database.py`, `generator/`, `integrations/`, `esp32_firmware/`, `templates/`, `static/`).

### `2026-11-06` — `v1.1.0-carrusel` (Migración a Seeed Studio XIAO ESP32-C6 y Modo Carrusel)
- Adaptación completa del mapeo de pines SPI para la placa **Seeed Studio XIAO ESP32-C6 (RISC-V Wi-Fi 6)**.
- Implementación del **Modo Carrusel Continuo** (rotación automática cada 60 segundos entre Dashboard, Calendario Mensual, Fotos/Cómic, QR Wi-Fi Visitas y Diagnóstico) con soporte del botón `BOOT` (`GPIO 9`) para avanzar de pantalla al instante.

### `2026-11-05` — `v1.0.0` (Cómic Diario con IA, Calendario Doodle, Íconos InkyPi y Domótica Real)
- **Generador de Cómic Diario ("Las Gaturrakas"):** Integración con `gemini-2.5-flash-image` (`generator/comic_generator.py`) para crear cada mañana una tira cómica personalizada según el día y el clima actual.
- **Calendario Mensual Doodle (`generator/calendar_view.py`):** Vista mensual completa con fuente `Patrick Hand` sincronizada con Google Calendar (`.ics`).
- **Clima estilo InkyPi:** Integración de íconos meteorológicos a color y layout vertical sin bordes (`480×800 px`).
- **Domótica Completa y Sistema OTA Base:** Integración en vivo con 22 dispositivos de **Tuya Smart / Smart Life**, aspiradora robot **Xiaomi Cloud** (`Romina`), y endpoints `/api/ota/check` y `/api/ota/download`.
