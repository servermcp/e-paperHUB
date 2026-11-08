# Documentación Técnica y Bitácora de Construcción
# E-Paper ACeP 7-Color Smart Dashboard & Mobile Hub (ESP32 + Flask VPS)

**Servidor VPS:** Vultr Tokyo (`45.76.198.7`) — `/root/epaper-hub/`  
**Entorno Python VPS:** `/root/epaper-hub/venv` (`Python 3.12`, `Pillow`, `NumPy`, `Flask`, `requests`, `qrcode`)  
**Hardware Objetivo:** ESP32 + Pantalla E-Paper 7.3" ACeP 7-Color (`800x480 px`, 4 bits por píxel empacados = `192,000 bytes`)

---

## 1. Arquitectura General del Sistema

```
+-------------------------------------------------------------------+
|                     VPS VULTR TOKYO (45.76.198.7)                 |
|                                                                   |
|  +-------------------+   +-------------------+   +-------------+  |
|  | Integraciones API |   | Base de Datos     |   | WebApp Hub  |  |
|  | - Open-Meteo      |   | SQLite (WAL mode) |   | Mobile-First|  |
|  | - Google Calendar |-->| - gastos          |<--| - /gastos   |  |
|  | - Tuya OpenAPI    |   | - notas (Post-it) |   | - /subir-foto| |
|  | - Home Assistant  |   | - fotos (800x480) |   | - /nota     |  |
|  +---------+---------+   | - device_state    |   +------+------+  |
|            |             +---------+---------+          |         |
|            v                       v                    v         |
|  +-------------------------------------------------------------+  |
|  | MOTOR GRÁFICO 2 CAPAS (generator/)                          |  |
|  | 1. Capa Base: Tone Mapping (+38% Sat, +15% S-Curve, +5% Br) |  |
|  |    + Cuantización CIELAB D65 + Dithering Atkinson (6/8)     |  |
|  | 2. Capa UI: Texto 1-bit ("1") sin antialiasing + Iconos SVG |  |
|  |    + QR nítido usando índices puros ACeP (0x0..0x6)         |  |
|  | 3. Packer: Empacado de nibbles (px0<<4 | px1) -> 192,000 B  |  |
|  +------------------------------+------------------------------+  |
|                                 |                                 |
+---------------------------------|---------------------------------+
                                  | HTTP GET /api/screen.bin?mode=1..4
                                  v (Stream crudo de 192 KB)
+-------------------------------------------------------------------+
|                 MICROCONTROLADOR ESP32 + E-INK 7.3"               |
| - Cero renderizado local: recibe stream HTTP y envía por SPI DMA  |
| - Deep Sleep (ultrabajo consumo) + Wakeup por Touch Capacitivo:   |
|   * 1 toque: Dashboard Principal                                  |
|   * 2 toques: Modo Marco de Fotos (Carrusel 800x480 dithered)     |
|   * 3 toques: Modo Visitas (QR Wi-Fi Invitados gigante)           |
|   * 4 toques: Pantalla de Diagnóstico y Barras de Calibración     |
|   * Toque largo (3-5s): Ciclo físico anti-ghosting                |
+-------------------------------------------------------------------+
```

---

## 2. Registro de Módulos Implementados y Verificados

### Etapa 1: Configuración Física y Motor de Dithering Perceptual
1. **`/root/epaper-hub/config.py`**
   - Define las dimensiones físicas (`800x480`), tamaño exacto del binario (`192,000 bytes`) y los códigos de 4 bits nativos del controlador (`0x0` Negro a `0x6` Naranja).
   - Separa `ACEP_IDEAL_SRGB` (para UI vectorial pura) de `ACEP_CALIBRATED_SRGB` y `ACEP_CALIBRATED_LAB` (valores reflectivos reales medidos bajo iluminante D65 para el motor de dithering).
   - Centraliza variables de entorno para Open-Meteo, Google Calendar, Tuya OpenAPI, Home Assistant y Wi-Fi de Invitados.

2. **`/root/epaper-hub/generator/dither.py`**
   - **`srgb_to_lab_array()`**: Transformación matemática exacta `sRGB` $\rightarrow$ RGB Lineal $\rightarrow$ `CIE XYZ (D65)` $\rightarrow$ `CIELAB`.
   - **`apply_acep_tone_mapping()`**: Aplica encuadre `800x480` (`LANCZOS`), LUT combinada de brillo en medios tonos (`+5%`) + curva sigmoide S-Curve (`+15%`) y realce de saturación (`+38%`).
   - **`_build_rgb555_to_acep_lut()`**: Pre-computa una LUT 3D de $32 \times 32 \times 32$ en espacio perceptual CIELAB para búsquedas $\Delta E_{ab}^*$ en tiempo $O(1)$.
   - **`dither_image_acep()`**: Implementa difusión de error **Atkinson** (difunde $6/8 = 75\%$ del error, evitando artefactos de "gusano") y **Sierra Lite**, con escaneo serpentino opcional.
   - **Benchmark en VPS Tokyo:** Procesamiento completo de `800x480` en **1,371 ms**.

---

### Etapa 2: Empacador Binario, Persistencia SQLite y Compositor de 2 Capas
3. **`/root/epaper-hub/generator/packer.py`**
   - **`pack_hw_indices_to_bytes()`**: Empaca de forma vectorizada con NumPy pares de píxeles contiguos `(px_even << 4) | (px_odd & 0x0F)` produciendo exactamente `192,000 bytes`.
   - **`save_packed_bin()`**: Escritura atómica mediante archivo temporal `.bin.tmp` y `replace()` para garantizar que el ESP32 nunca descargue un frame incompleto.
   - **`unpack_bytes_to_hw_indices()`** y **`render_preview_from_hw_indices()`**: Verificación inversa y generación de `screen_preview.png` para la WebApp.

4. **`/root/epaper-hub/schema.sql` & `/root/epaper-hub/database.py`**
   - Base de datos SQLite en modo `WAL` (`epaper_hub.db`).
   - Tablas implementadas:
     - `gastos`: Registro de gastos compartidos, cálculo automático de totales, cuota ideal y balance neto a favor/deuda por persona (`get_gastos_summary()`), y liquidación de período (`settle_all_gastos()`).
     - `notas`: Post-it digital en la heladera con soporte de fecha de expiración automática (`get_active_nota()`, `set_active_nota()`).
     - `fotos`: Carrusel de fotografías con balanceo por contador `mostrada_veces` (`pick_next_carousel_foto()`).
     - `device_state_cache`: Caché unificada para `tuya`, `google_home` y `vps` (`upsert_device_state()`).

5. **`/root/epaper-hub/generator/weather.py`**
   - Cliente HTTP hacia Open-Meteo (`https://api.open-meteo.com/v1/forecast`) con caché en memoria (`TTL = 15 min`) y fallback resiliente offline.
   - Traduce códigos meteorológicos WMO a descripciones en español, icono vectorial y color ACeP óptimo.

6. **`/root/epaper-hub/generator/layout.py`**
   - Clase **`AcepCanvas`**: Opera directamente sobre una matriz `uint8` de `480x800` con códigos de hardware `0x0..0x6`.
   - **`draw_text_1bit()`**: Renderiza tipografías Bold en máscaras binarias de 1-bit (`mode="1"`) sin antialiasing gris y estampa los píxeles activos con el índice de hardware exacto.
   - **`draw_vector_icon()`** y **`draw_qr_code()`**: Iconografía lineal de trazo grueso y códigos QR 1-bit ultra-nítidos.
   - Renderiza los **4 modos interactivos del botón táctil del ESP32**:
     - Modo 1 (`dashboard`): Clima + Agenda Google Calendar + Domótica Tuya/Home Assistant + Post-it Amarillo + Gastos de la Heladera + QR al Hub.
     - Modo 2 (`photo_frame`): Fotografía a pantalla completa `800x480` con Tone Mapping y Dither Atkinson + etiqueta minimalista de fecha/hora en Capa UI.
     - Modo 3 (`guest_wifi`): QR gigante de conexión Wi-Fi automática para visitas + tarjeta de credenciales.
     - Modo 4 (`diagnostics`): Telemetría técnica (IP VPS, IP/RSSI/Voltaje del ESP32, estado SQLite) + barras de prueba de los 7 pigmentos ACeP (`0x0` a `0x6`).

---

### Etapa 3: Integraciones Externas, Backend Flask, WebApp Móvil y Firmware ESP32

7. **Integraciones Externas (`/root/epaper-hub/integrations/`)**
   - **`google_cal.py`**: Consulta Google Calendar v3 API vía Service Account (`credentials_google_cal.json`) con caché de 5 minutos y fallback resiliente local para recuperar los próximos 2 eventos del día.
   - **`tuya_client.py`**: Cliente para Tuya OpenAPI v2.0 (compatible con `tuya-connector-python` y firma HMAC-SHA256 nativa) que consulta `switch_1` y `countdown_1` de la electroválvula de riego y persiste el estado en `device_state_cache` (`tuya_irrigation_01`).
   - **`home_assistant.py`**: Procesador de Webhooks (`POST /api/webhook/home-assistant`) y polling REST para entidades de Google Home / Home Assistant (portón garage, luces exteriores, climatización).

8. **Backend Flask y Endpoints (`/root/epaper-hub/app.py`)**
   - Servicio systemd activo: `epaper-hub.service` en el puerto `5050` (`http://45.76.198.7:5050/hub`).
   - **Rutas WebApp Móvil (Mobile-First):**
     - `GET /hub`: Vista en vivo del buffer `800x480` (`screen_preview.png`), descarga directa del `.bin` de 192 KB, Control Remoto de los 4 modos del ESP32 y estado de domótica/clima.
     - `GET/POST /gastos` y `POST /gastos/saldar`: Carga rápida en 3 toques con teclado numérico, cálculo de cuota ideal, saldos a favor/deuda por persona y liquidación de período.
     - `GET/POST /subir-foto`: Integración con **Cropper.js 1.6.2** con relación de aspecto bloqueada estrictamente a `800:480`, zoom, paneo y rotación. Al enviar, aplica Tone Mapping + Dithering Atkinson en CIELAB, guarda original en `static/uploads/` y procesada en `static/processed/`, y actualiza el marco.
     - `GET/POST /nota`: Editor del Post-it Digital urgente de la heladera con renderizado inmediato en la pantalla E-Paper.
   - **Endpoints API para ESP32 y Domótica:**
     - `GET /api/screen.bin?touches=1..4&vbat=4.02&rssi=-60&ip=...`: Registra la telemetría del ESP32 en SQLite, compila la vista solicitada, calcula `ETag` MD5 (retorna `304 Not Modified` en despertares por timer si la imagen no cambió para ahorrar batería) y entrega los **192.000 bytes** exactos (`application/octet-stream`).
     - `POST /api/render`: Regeneración forzada o cambio de modo remoto.
     - `POST /api/webhook/home-assistant`: Recepción de estados de Home Assistant / Google Home.
     - `POST /api/tuya/sync`: Sincronización manual/programada de la electroválvula Tuya.

9. **Firmware ESP32 Ultrabajo Consumo (`/root/epaper-hub/esp32_firmware/epaper_acep_hub_esp32.ino`)**
   - Cero renderizado en el microcontrolador: descarga el stream HTTP en bloques de `1024 bytes` y los transfiere directo por hardware SPI (`10 MHz`) al controlador ACeP (`GDEY073D46` / Waveshare 7.3" 7-Color).
   - Detección en ventana de tiempo del pin táctil capacitivo (`T3 / GPIO 15`):
     - `1 toque` $\rightarrow$ `GET /api/screen.bin?touches=1` (Dashboard Principal)
     - `2 toques` $\rightarrow$ `GET /api/screen.bin?touches=2` (Marco de Fotos Carrusel)
     - `3 toques` $\rightarrow$ `GET /api/screen.bin?touches=3` (Modo Visitas QR Wi-Fi)
     - `4 toques` $\rightarrow$ `GET /api/screen.bin?touches=4` (Diagnóstico y Barras de Pigmento)
     - `Toque largo (>3.2 s)` $\rightarrow$ Ciclo físico de limpieza profunda (`Blanco -> Negro -> Blanco`) anti-ghosting.
   - Deep Sleep automático (`15 min` por RTC Timer + Touchpad Wakeup) con soporte de `ETag` en memoria `RTC_DATA_ATTR`.

---

### Etapa 4: Corrección de Subida de Fotos (`HTTP 413`) y Soporte de Orientación Horizontal / Vertical

1. **Causa raíz del `Request Entity Too Large` (HTTP 413) y solución:**
   - En Werkzeug 3.x (`Flask 3.x`), además de `MAX_CONTENT_LENGTH`, existe `MAX_FORM_MEMORY_SIZE` cuyo valor por defecto es `500 KB` para cualquier campo de formulario que no sea archivo (`multipart/form-data` text field). Enviar el canvas recortado como cadena Base64 dentro de un `<input type="hidden">` superaba los `500 KB` y disparaba `413 Request Entity Too Large`.
   - **Solución implementada:**
     - En `templates/upload_photo.html`, el recorte de Cropper.js ahora se exporta mediante `canvas.toBlob()` y se envía como un archivo binario real (`cropped_blob`) vía `FormData` + `fetch()` (~150–300 KB en vez de subir la foto cruda de cámara de 15 MB o un string Base64 gigante).
     - En `app.py`, se ampliaron preventivamente `MAX_CONTENT_LENGTH = 64 MB` y `MAX_FORM_MEMORY_SIZE = 32 MB`.

2. **Selector de Orientación de Pantalla (`Horizontal 800×480` vs `Vertical 480×800`):**
   - En `/subir-foto`, se agregaron dos botones de selección rápida:
     - **🖥️ Horizontal (`800 × 480 px`, ratio `5:3`)**
     - **📱 Vertical (`480 × 800 px`, ratio `3:5`)**
   - Al alternar entre ambos, `Cropper.js` actualiza en vivo su `aspectRatio` (`800/480` o `480/800`).
   - En `generator/layout.py` (`render_photo_frame_mode` y `build_screen_buffer`):
     - Si la foto es **Vertical (`480×800`)**, tanto el Tone Mapping como el Dithering Atkinson CIELAB y la etiqueta de fecha/hora en la Capa UI se renderizan en `480×800` para que se lean al derecho con el marco parado verticalmente.
     - La vista previa web (`screen_preview.png` y galería) se guarda al derecho (`480×800`), mientras que para el archivo físico `screen.bin` la matriz se rota 90° (`np.rot90`) a `(480, 800)` antes de empacar los nibbles para que coincida con la GRAM nativa del controlador ACeP (`192.000 bytes` exactos).

---

### Etapa 5: Rediseño Editorial del Dashboard en Formato Vertical (`480 × 800 px`)

1. **Verificación de foto subida por el usuario:**
   - Archivo registrado en SQLite (`fotos.id = 2`): `foto_ver_20261104_204134.png`
   - Dimensiones verificadas en `static/uploads/` y `static/processed/`: `(480, 800)` (orientación Vertical).

2. **Nuevo Diseño del Dashboard Vertical (`480 × 800 px`) en `generator/layout.py`:**
   - Se eliminaron las tarjetas con bordes y barras de título para maximizar el aire visual y el aprovechamiento de los `800 px` verticales, separando los bloques únicamente con líneas divisorias limpias de 1–2 px.
   - Se retiró el bloque de Post-it del dashboard principal.
   - **Estructura de arriba hacia abajo (`480 × 800 px`):**
     - **Bloque 1 — Clima suelto (`y: 18..190`):** Fecha en español a la izquierda y hora a la derecha; debajo, icono meteorológico grande (`74×74 px`), temperatura actual de `48 px` Bold, descripción del estado y a la derecha máxima (`▲`), mínima (`▼`), probabilidad de lluvia, humedad y viento.
     - **Bloque 2 — Próximos 2 Eventos de Google Calendar (`y: 206..318`):** Dos filas sueltas con píldora de hora (`10:30`, `18:00`) y título del evento en `18 px` Bold a todo el ancho (`440 px`).
     - **Bloque 3 — Gastos de la Heladera (`y: 334..570`):** Monto total acumulado grande (`34 px`) a la izquierda, balances netos por persona (`+$` en verde / `-$` en rojo) alineados a la derecha, línea punteada sutil y lista limpia de los últimos 4 movimientos con importe alineado a la derecha.
     - **Bloque 4 — Domótica + QR Compacto (`y: 588..786`):** A la izquierda, los 4 dispositivos (`Riego Jardín`, `Portón Garage`, `Luces Exterior`, `Clima Living`) con barra indicadora vertical de color ACeP; a la derecha, el código QR limpio hacia `/hub`.

---

### Etapa 6: Conversión de Logos a Iconos ACeP (`32×32 px`) y Tabla de Seguimiento de Tarjetas / Servicios

1. **Conversión de Logos Subidos a Matrices Indexadas ACeP (`static/icons/logos/*.npy` y `*.png`):**
   - Para evitar que el dithering introduzca granulado en iconos pequeños (`32×32 px`), se aplicó **segmentación cromática directa** hacia los 7 índices físicos del panel (`0x0..0x6`):
     - `exp`: Fondo Azul ACeP (`0x3`) con letras `EXP` y barras en Blanco (`0x1`).
     - `galicia`: Fondo Naranja ACeP (`0x6`) con la cruz de Santiago en Blanco (`0x1`).
     - `edese`: Recorte automático de márgenes blancos + letras en Azul (`0x3`), `D` en Rojo (`0x4`) y estrella en Amarillo (`0x5`) con marco de 1px.
     - `amex`: Fondo Azul ACeP (`0x3`) con letras `AM EX` en Blanco (`0x1`).
     - `provincia`: Fondo Blanco (`0x1`) con isotipo `P` en Verde ACeP (`0x2`) y borde de 1px.
   - Se generaron además iconos complementarios de `32×32 px` para **`visa`**, **`mastercard`**, **`consorcio`** y **`luz`**.

2. **Nueva Tabla `tarjetas_gastos` en SQLite y Dashboard Vertical (`480 × 800 px`):**
   - Columnas en pantalla: **`EMP / GASTO | TOTAL | MÍNIMO | SALDO`** (+ fecha corta de vencimiento `DD/MM`).
   - **Semáforo Inteligente ACeP en la columna `SALDO`:**
     - **Rojo (`0x4`)**: Pendiente de pago y aún no se cubrió el Pago Mínimo.
     - **Naranja (`0x6`)**: Ya se cubrió el Pago Mínimo (`pagado >= minimo`), pero resta saldo del total.
     - **Verde (`0x2` — `PAGADO`)**: Saldo `$0`.
   - **Pie de Tabla Amarillo (`TOTAL MES`):** Suma automáticamente las columnas `TOTAL`, `MÍNIMO` y `SALDO` de todas las tarjetas y servicios activos.
   - **Gestión en 1 toque desde `/gastos`:** Permite agregar/editar cualquier combinación de `Logo Empresa` + `Logo Gasto`, o tocar **"Cubrir Mínimo"** / **"✓ Saldar Total"** para actualizar el saldo y refrescar el E-Paper al instante.

3. **Actualización con Logos Oficiales de VISA y Mastercard (`32×32 px` ACeP):**
   - `visa`: Recorte ajustado sobre fondo Blanco (`0x1`), letras `VISA` en Azul ACeP (`0x3`), ala superior izquierda de la `V` en Naranja ACeP (`0x6`) y marco fino de 1px.
   - `mastercard`: Recorte ajustado sobre fondo Blanco (`0x1`), círculo izquierdo en Rojo ACeP (`0x4`), intersección central en Naranja ACeP (`0x6`) y círculo derecho en Amarillo ACeP (`0x5`) con marco de 1px.

---

### Etapa 7: Selector de Domótica (`/domotica`), Reglas Condicionales (`only_active`) y Guía de APIs Cloud

1. **Los 7 Dispositivos / Grupos Configurados en `device_state_cache`:**
   - `luces_santiago` (**Luces Santiago**): `"4 encendidas"` — Regla: `always` (Siempre visible).
   - `luces_pina` (**Luces Pina**): `"3 encendidas"` — Regla: `always` (Siempre visible).
   - `porton_main` (**Portón**): `"Cerrado"` — Regla: `always` (Siempre visible).
   - `riego_main` (**Riego**): `"Próximo 06:30"` / `"Regando"` / `"Suspendido"` — Regla: `always`.
   - `pileta_filtro` (**Pileta**): `"Filtrando"` — Regla: `only_active` (**Solo se dibuja en el E-Paper cuando está filtrando**; cuando `is_active = 0`, no ocupa espacio).
   - `temp_pina` (**Temp. Pina**): `"25°"` — Regla: `always`.
   - `romina_robot` (**Romina**): `"Barriendo"` — Regla: `only_active` (**Solo se dibuja en el E-Paper cuando está barriendo**; cuando vuelve a la base, se oculta automáticamente).

2. **Nueva Pantalla `/domotica` en el Hub Móvil:**
   - Accesible desde la barra inferior (`🏡 Domótica`).
   - Permite activar/desactivar cada ítem, alternar su regla entre **👁️ Siempre visible** y **⚡ Solo cuando está activo**, y cambiar o simular su estado en vivo.

3. **Arquitectura de APIs Cloud para Conectar Santiago + Pinamar desde el VPS de Tokyo:**
   - **Tuya / Smart Life (`iot.tuya.com`)**: Cubre llaves de luz Wi-Fi, riego, bomba de pileta, portón y sensores de temperatura.
   - **Xiaomi Cloud (`Mi Home`)**: Cubre la aspiradora robot **Romina** vía `micloud` / `python-miio`.
   - **eWeLink / Sonoff** (si aplica): Cubre relés Sonoff vía `eWeLink API`.

---

### Etapa 8: Conexión Real con Tuya OpenAPI

1. **Credenciales configuradas en `/root/epaper-hub/.env` (`config.py`):**
   - **Project Code:** `<TUYA_PROJECT_CODE>`
   - **Access ID:** `<TUYA_ACCESS_ID>`
   - **Endpoint Activo:** `https://openapi.tuyaus.com` (Western America Data Center)

2. **Primeros 8 Dispositivos Detectados en la Cuenta Tuya Smart (Pinamar `-37.11, -56.88`):**
   - `Living 2` (`ebf640c87905406b80badt`) — Categoría `dj` (ETHEOS Lámpara SMART)
   - `Cocina` (`ebd96d8e2091161e28w3oq`) — Categoría `dj` (ETHEOS Lámpara SMART)
   - `Puerta de enlace inteligente` (`eb98f8e29ff06e786bdniu`) — Categoría `wg2` (Gateway)
   - `Riego` (`eb2c827fc495d18c09czca`) — Categoría `sfkzq` (Controlador de riego)
   - `Comedor 3` (`ebf415a936aa3e7a2asu3n`) — Categoría `dj`
   - `Living 1` (`eb3000364235c31b4ezzmc`) — Categoría `dj`
   - `Comedor 3` (`eb142d876d86739d3ezvda`) — Categoría `dj`
   - `Comedor 1` (`ebfe96090da274549eya3m`) — Categoría `dj`

3. **Cómo sumar los dispositivos de la app Smart Life al mismo proyecto:**
   - En `iot.tuya.com` $\rightarrow$ entrar al mismo proyecto $\rightarrow$ pestaña **Devices** $\rightarrow$ **Link Tuya App Account** $\rightarrow$ clic en **Add App Account** y escanear el código QR desde la app **Smart Life**.

---

### Etapa 9: Vinculación Completa de Smart Life (22 Dispositivos) + Xiaomi Cloud (Robot "Romina")

1. **Xiaomi Cloud — Vinculado exitosamente por QR:**
   - **Dispositivo detectado:** `Romina`
   - **DID:** `472391882`
   - **Modelo:** `ijai.vacuum.v10` (Región `us`, IP local `192.168.1.242`, Token `<XIAOMI_DEVICE_TOKEN>`)
   - **Sesión persistente:** Guardada en `/root/epaper-hub/xiaomi_session.json`.

2. **Tuya Smart + Smart Life — 22 Dispositivos Detectados:**
   - **Hogar `18524070` (Smart Life):**
     1. `Portón` (`eb17f07432300b71aeqewh`, `ckmkzq`, Online: `True`)
     2. `Cocina` (`ebd8ab1914b6e6b262iocp`, `tdq`, Online: `True`)
     3. `Temp` (`eb4247200f590ffc6eiddw`, `wk`, Online: `True`, `temp_current: 24.2°C`)
     4. `Cuarto3` (`eb4f5f277fa693f5d7twdb`, `dj`, Online: `True`)
     5. `Comedor3` (`eb9e928382bcf9fe05vz9x`, `dj`, Online: `True`)
     6. `Comedor2` (`ebfae9f22a8fcf3f81msam`, `dj`, Online: `True`)
     7. `Cuarto2` (`ebde2bdc4b695b5538xjha`, `dj`, Online: `True`)
     8. `Cuarto1` (`eb61a367f1966cd9cbx0hs`, `dj`, Online: `True`)
     9. `Cuarto3` (`eb191e9b2e1c2fe0c4rvfx`, `dj`, Online: `True`)
     10. `Riego` (`eb6fc0540f867b2c37go2w`, `sfkzq`, Online: `False`)
     11. `aire` (`ebb9b774b654601e23oaju`, `wnykq`, Control IR)
     12. `Aire acondicionado` (`ebab6ae7257e6749d1o6gm`, `infrared_ac`)
     13. `TV` (`eb8c7c0bd8f8ac8499adns`, `infrared_tv`)
     14. `Puerta` (`eb93b0f88918f6dc9axbzz`, `jtmspro`, Cerradura inteligente, Online: `True`)
   - **Hogar `7792533` (Tuya Smart):**
     15. `Living 2` (`ebf640c87905406b80badt`, `dj`, Online: `True`)
     16. `Cocina` (`ebd96d8e2091161e28w3oq`, `dj`, Online: `True`)
     17. `Puerta de enlace inteligente` (`eb98f8e29ff06e786bdniu`, `wg2`)
     18. `Riego` (`eb2c827fc495d18c09czca`, `sfkzq`)
     19. `Comedor 3` (`ebf415a936aa3e7a2asu3n`, `dj`)
     20. `Living 1` (`eb3000364235c31b4ezzmc`, `dj`)
     21. `Comedor 3` (`eb142d876d86739d3ezvda`, `dj`)
     22. `Comedor 1` (`ebfe96090da274549eya3m`, `dj`)

---

### Etapa 10: Asignador Individual Pina / Santiago (`/domotica`), Google Calendar (`.ics`) y Handover para el Agente de Casa

1. **Selector Individual de Hogar/Grupo para los 22 Dispositivos (`http://45.76.198.7:5050/domotica`):**
   - Se agregó la sección **"🔌 Asignar Dispositivos (Pina / Santiago)"** directamente en `http://45.76.198.7:5050/domotica`.
   - Al lado de cada uno de los 22 dispositivos detectados en Tuya Smart y Smart Life hay un menú desplegable que permite asignarlo a:
     - `💡 Luces Pina`
     - `💡 Luces Santiago`
     - `🚪 Portón`
     - `🚿 Riego`
     - `🏊 Pileta (Filtro)`
     - `🌡️ Temp. Pina`
     - `➖ Ignorar / No mostrar`
   - Las asignaciones se guardan de forma persistente en `/root/epaper-hub/tuya_device_assignments.json` (con valores iniciales preconfigurados automáticamente según `owner_id` y categoría) y al tocar **"💾 Guardar Asignación Pina / Santiago y Actualizar E-Paper"** se recalcula al instante cuántas luces están encendidas en cada casa y se regenera el binario `screen.bin`.

2. **Nota sobre Jwcom Smart (`"Programación de no interrumpir"`):**
   - La app **Jwcom Smart** es una marca blanca OEM de Tuya que tiene bloqueado el escaneo QR de desarrollador (`iot.tuya.com`).
   - **Soluciones disponibles:**
     - **Opción A (Sin reconfigurar Wi-Fi):** En la app *Jwcom Smart*, entrar a cada dispositivo $\rightarrow$ ícone de lápiz (arriba a la derecha) $\rightarrow$ **Compartir equipo (Share Device)** $\rightarrow$ compartirlo con la cuenta de **Smart Life** o **Tuya Smart**.
     - **Opción B (Recomendada a largo plazo):** Vincular esos dispositivos directamente en la app oficial **Smart Life** (usan exactamente el mismo chip y protocolo Tuya, por lo que aparecen automáticamente en la API sin depender de Jwcom).

3. **Integración con Google Calendar (`/root/epaper-hub/integrations/gcal_client.py`):**
   - Ya está desplegado y activo el cliente de Google Calendar en `/root/epaper-hub/integrations/gcal_client.py` y su panel de configuración en `http://45.76.198.7:5050/domotica` (sección **"📅 Google Calendar (Próximos 2 Eventos)"**).
   - **Cómo conectarlo en 30 segundos desde casa:**
     1. Abrir [Google Calendar en la compu](https://calendar.google.com) $\rightarrow$ clic en el engranaje ⚙️ **Configuración**.
     2. En la columna izquierda, hacer clic sobre el calendario personal $\rightarrow$ bajar hasta **"Integrar el calendario"**.
     3. Copiar la **"Dirección secreta en formato iCal"** (termina en `.../basic.ics`).
     4. Pegarla en `http://45.76.198.7:5050/domotica` dentro del cuadro **"📅 Google Calendar"** y tocar **"💾 Conectar Google Calendar y Actualizar E-Paper"**.
   - El parser `.ics` soporta eventos puntuales, eventos de día completo (`Todo el día`), zonas horarias (`America/Argentina/Buenos_Aires`, UTC-3) y guarda la configuración en `/root/epaper-hub/gcal_config.json`, actualizando automáticamente la tabla `calendar_cache` de SQLite con los próximos Eventos que se dibujan debajo del clima.

---

## 🤝 Guía de Handover para el Agente de Casa (Resumen Ejecutivo de Continuidad)

Si sos el agente ejecutándose en la computadora de la casa de Matías, acá tenés **todo el estado técnico exacto** para continuar sin perder un segundo:

### 1. Acceso al Servidor VPS (Producción Activa)
- **Proveedor / Región:** Vultr Tokyo
- **IP Pública:** `45.76.198.7`
- **Usuario SSH:** `root`
- **Password SSH:** `<CONFIGURADO_EN_SKILL_PRIVADA>`
- **Puerto Web / API:** `5050` (abierto en `ufw`)
- **URLs activas:**
  - **Hub Móvil Principal:** `http://45.76.198.7:5050/hub`
  - **Gestor de Gastos y Tarjetas:** `http://45.76.198.7:5050/gastos`
  - **Gestor de Domótica, Asignador Pina/Santiago y Google Calendar:** `http://45.76.198.7:5050/domotica`
  - **Subida de Fotos con recorte Vertical/Horizontal:** `http://45.76.198.7:5050/subir-foto`
  - **Binario crudo para el ESP32 (192.000 bytes):** `http://45.76.198.7:5050/epaper/screen.bin`
  - **JSON de metadatos para el ESP32:** `http://45.76.198.7:5050/api/status`
- **Servicio Systemd:** `epaper-hub.service`
  - Ver estado: `systemctl status epaper-hub.service`
  - Reiniciar tras cambios: `systemctl restart epaper-hub.service`
  - Entorno virtual Python: `/root/epaper-hub/venv/bin/python`

### 2. Mapa de Archivos en el VPS (`/root/epaper-hub/`)
- `/root/epaper-hub/config.py`: Paleta calibrada ACeP 7-Color (`ACEP_PALETTE_SRGB`, `ACEP_PALETTE_LAB`), coordenadas de clima y carga automática de variables desde `/root/epaper-hub/.env`.
- `/root/epaper-hub/database.py`: Esquema SQLite (`/root/epaper-hub/data/hub.db`) con tablas `system_state`, `expenses`, `notes`, `photos`, `calendar_cache`, `device_state_cache`.
- `/root/epaper-hub/app.py`: Servidor Flask principal con todas las rutas web (`/hub`, `/gastos`, `/domotica`, `/subir-foto`, `/notas`) y endpoints REST (`/api/status`, `/epaper/screen.bin`, `/api/domotica/sync-real`, `/api/domotica/save-assignments`, `/api/gcal/save`).
- `/root/epaper-hub/generator/dither.py`: Motor de Tone Mapping (`+38%` saturación, curva S de contraste) + LUT 3D `RGB555 -> CIELAB` + dithering **Atkinson** (fotos) y **Sierra Lite** (gráficos).
- `/root/epaper-hub/generator/packer.py`: Empaquetador vectorial de 4 bits (`2 píxeles por byte`, `192.000 bytes` exactos) y generador de `static/screen_preview.png`.
- `/root/epaper-hub/generator/layout.py`: Renderizador del Dashboard Vertical (`480 × 800 px`, sin tarjetas contenedoras, rotado automáticamente 90° al empaquetar `screen.bin` para los `800 × 480` físicos del controlador ACeP):
  1. **Arriba (`y = 0..176`):** Clima en vivo (Open-Meteo) sin cajas + fecha.
  2. **Medio-Alto (`y = 178..264`):** Próximos 2 eventos de Google Calendar.
  3. **Medio-Bajo (`y = 266..522`):** Tabla de Tarjetas y Gastos (`EMP / GASTO | TOTAL | MÍNIMO | SALDO`) con iconos `32×32 px` en `/root/epaper-hub/static/icons/logos/` (`galicia`, `provincia`, `edese`, `amex`, `exp`, `visa`, `mastercard`, `consorcio`, `luz`), semáforo de colores en `SALDO` y fila `TOTAL MES`.
  4. **Abajo (`y = 524..800`):** 7 filas de Domótica con soporte `only_active` (`Pileta` solo se muestra cuando está filtrando; `Romina` solo cuando está barriendo) + QR al Hub.
- `/root/epaper-hub/integrations/tuya_client.py`: Cliente Tuya OpenAPI HMAC-SHA256 que lee los 22 dispositivos de los hogares `18524070` (Smart Life) y `7792533` (Tuya Smart) y aplica el mapeo de `/root/epaper-hub/tuya_device_assignments.json`.
- `/root/epaper-hub/integrations/xiaomi_client.py`: Cliente Xiaomi Cloud RC4 (`ssecurity`) autenticado mediante QR (`/root/epaper-hub/xiaomi_session.json`) que consulta a la aspiradora robot **Romina** (`did: 472391882`, `model: ijai.vacuum.v10`).
- `/root/epaper-hub/integrations/gcal_client.py`: Cliente iCal (`.ics`) para sincronizar los próximos 2 eventos de Google Calendar (`/root/epaper-hub/gcal_config.json`).

### 3. Próximos Pasos Pendientes para Continuar desde Casa
1. **Terminar de conectar Google Calendar:** Pegar la URL secreta `.ics` del calendario de Google en `http://45.76.198.7:5050/domotica` (o ayudar a Matías a obtenerla).
2. **Revisar la asignación Pina / Santiago de las luces:** En `http://45.76.198.7:5050/domotica`, verificar con Matías si alguna lámpara específica de los 22 dispositivos listados debe cambiarse entre `Luces Pina`, `Luces Santiago` o `Pileta (Filtro)`.
3. **Dispositivos de Jwcom Smart:** Si Matías decide compartirlos a su cuenta de Smart Life o vincularlos directamente en Smart Life, tocar **"🔄 Sincronizar Tuya + Xiaomi Ahora"** en `/domotica` para que aparezcan automáticamente en la lista y asignarlos.
4. **Flasheo del ESP32 cuando llegue la pantalla física:** El código completo del firmware (`esp32_firmware/src/main.cpp` y `platformio.ini`) está en la **Sección 4** de este mismo documento, listo para compilar con PlatformIO.


---

### Etapa 11: Vinculación Efectiva de Google Calendar (Calendario "Familia" vía iCal Secreto)

1. **Configuración de la URL Secreta (`google_cal_config.json`):**
   - **URL vinculada:** `<GOOGLE_CALENDAR_ICAL_URL>`
   - **Archivo de persistencia:** `/root/epaper-hub/google_cal_config.json`
   - **Nombre de calendario detectado:** `Familia` (`X-WR-CALNAME:Familia`).

2. **Verificación del Flujo de Sincronización:**
   - La petición HTTP a Google devolvió `HTTP 200 OK`.
   - El parser `integrations/google_cal.py` procesó el archivo `.ics`.
   - Estado de eventos: Actualmente el calendario tiene `0 eventos` programados para los próximos 7 días, por lo que el dashboard despliega limpiamente el fallback: `--:-- | Sin eventos próximos en agenda`.
   - Cualquier evento agregado en Google Calendar (puntual o de día completo) se reflejará automáticamente en el próximo ciclo de actualización (`TTL = 5 min`).

3. **Reconstrucción del Buffer y Preview:**
   - Se disparó la regeneración de la pantalla del Dashboard Vertical (`480 × 800 px`).
   - Binario `screen.bin`: `192.000 bytes` exactos empaquetados.
   - Vista previa `screen_preview.png`: Actualizada y visible en `http://45.76.198.7:5050/hub`.
   - Servicio `epaper-hub.service`: Reiniciado y activo en segundo plano.


---

### Etapa 12: Configuración de Red Wi-Fi "GATURRAKA" y Modo Visitas "CASA GATURRAKAS"

1. **Parámetros de Red Doméstica:**
   - **Nombre de la casa:** `Gaturrakas`
   - **SSID:** `GATURRAKA`
   - **Contraseña:** `<CONFIGURADO_EN_ENV>`
   - **Seguridad:** WPA/WPA2 Personal

2. **Archivos Actualizados:**
   - `/root/epaper-hub/.env` (`config.py`):
     - `GUEST_WIFI_SSID = "GATURRAKA"`
     - `GUEST_WIFI_PASSWORD = "<CONFIGURADO_EN_ENV>"`
   - `/root/epaper-hub/esp32_firmware/secrets.h`:
     - `SECRET_WIFI_SSID = "GATURRAKA"`
     - `SECRET_WIFI_PASS = "<CONFIGURADO_EN_SECRETS_H>"`
   - `/root/epaper-hub/generator/layout.py`:
     - Encabezado del Modo 3 (3 toques táctiles): `"CASA GATURRAKAS  •  WI-FI"`
     - Código QR 1-bit nítido con payload estándar `WIFI:T:WPA;S:GATURRAKA;P:<PASSWORD>;;` para escaneo automático directo con cámara de smartphones iOS y Android.
     - Tarjeta con SSID en Azul ACeP y Contraseña en Rojo ACeP monoespaciada para lectura clara.

3. **Verificación y Pruebas:**
   - Se ejecutó el render de prueba del modo `guest_wifi` completándose en **143.1 ms**.
   - Se reinició el servicio `epaper-hub.service`.


---

### Etapa 13: Depuración de Domótica Real (Exclusión de Google Home) e Implementación del Sistema OTA

1. **Saneamiento de Dispositivos de Domótica:**
   - Se eliminaron de `device_state_cache` los registros mock de Google Home (`ghome_gate_01`, `ghome_hvac_01`, `ghome_lights_01`) y el duplicado `tuya_irrigation_01`.
   - Se migró la aspiradora robot **Romina** a su integración real: `integration = 'xiaomi'`.
   - Se actualizó el esquema SQLite para admitir integraciones dinámicas sin CHECK restrictivo.
   - En `app.py` y `templates/hub.html`, la sección **"🏡 Estado Domótica & Clima"** ahora refleja estrictamente los servicios reales y conectados:
     - ☀️ Clima (Open-Meteo)
     - 💡 Luces Santiago (Tuya)
     - 💡 Luces Pina (Tuya)
     - 🚪 Portón (Tuya)
     - 🚿 Riego (Tuya)
     - 🏊 Pileta (Tuya - condicional `only_active`)
     - 🌡️ Temp. Pina (Tuya)
     - 🤖 Romina (Xiaomi - condicional `only_active`)

2. **Sistema Completo de Actualización Inalámbrica OTA (Over-The-Air):**
   - **Endpoint de Verificación:** `GET /api/ota/check?version=X.Y.Z` (informa si existe una versión superior y sus metadatos).
   - **Endpoint de Descarga:** `GET /api/ota/download` (entrega `firmware.bin` por stream HTTP con cabeceras `x-MD5` y soporte para código 304).
   - **Panel Web de Publicación (`GET /ota`):**
     - Accesible desde el Hub principal en un toque: [http://45.76.198.7:5050/ota](http://45.76.198.7:5050/ota).
     - Muestra versión activa, fecha, peso en KB y notas de cambios.
     - Formulario de subida de binario `.bin` con validación de tamaño y cálculo automático de hash MD5.
     - Descarga directa del `.bin` activo.
   - **Firmware ESP32 (`esp32_firmware/epaper_acep_hub_esp32.ino`):**
     - Integración con `<HTTPUpdate.h>`.
     - Función `checkForFirmwareUpdate()` ejecutada inmediatamente al conectar Wi-Fi en `setup()`.
     - Si detecta versión nueva, descarga el binario inalámbricamente por Wi-Fi, flashea la partición de la memoria Flash del ESP32 y se reinicia de forma autónoma.


---

### Etapa 14: Erradicación Definitiva del Dispositivo Mock "Portón Garage"

1. **Causa Raíz Identificada:**
   - En la creación inicial del proyecto, `schema.sql` contenía una semilla (`INSERT OR IGNORE INTO device_state_cache`) con `'ghome_gate_01'` (*Portón Garage*, integración `google_home`).
   - Al reiniciar el servicio Flask, `database.init_db()` ejecutaba el script del esquema, reinsertando ese registro de prueba si no existía.
   - Además, la función `get_visible_dashboard_devices()` no filtraba por tipo de integración, por lo que el renderizador del E-Paper dibujaba tanto el **Portón** real de Tuya (`porton_main`) como el **Portón Garage** mock.

2. **Acciones Correctivas Implementadas:**
   - **Base de datos:** Se eliminó `'ghome_gate_01'` y cualquier residuo fuera de `tuya` y `xiaomi`.
   - **`schema.sql`:** Se removió por completo la sección `INSERT OR IGNORE` de datos de prueba para evitar regeneraciones automáticas tras reinicios.
   - **`database.py`:** Se blindó `get_visible_dashboard_devices()` agregando la condición estricta `AND integration IN ('tuya', 'xiaomi')`.
   - **Regeneración de pantalla:** Se recalculó el buffer vertical (`screen.bin` y `screen_preview.png`). Ahora la lista de domótica muestra únicamente los 6 dispositivos reales y sincronizados de casa.


---

### Etapa 15: Corrección de Estado de Pileta y Fallback Automático

1. **Causa del Estado "Filtrando":**
   - El registro `pileta_filtro` tenía un valor de prueba inicial congelado en SQLite (`status_text = 'Filtrando'`, `is_active = 1`).
   - Al no existir actualmente ningún dispositivo de Tuya/Smart Life mapeado al grupo `pileta_filtro` en `tuya_device_assignments.json`, el ciclo de sincronización nunca lo actualizaba.
   - Dado que su regla de visualización es `only_active`, el valor `is_active = 1` provocaba que se dibujara ininterrumpidamente en la pantalla E-Paper.

2. **Solución Implementada:**
   - **Base de datos:** Se actualizó `pileta_filtro` a `status_text = 'Apagada'` y `is_active = 0`. Al pasar a inactiva, la regla `only_active` la oculta automáticamente del panel físico.
   - **`integrations/tuya_client.py`:** Se programó una cláusula de seguridad: si ningún dispositivo de Tuya está asignado a `pileta_filtro`, el sincronizador fuerza su estado a `Apagada` (`is_active = 0`), evitando que quede congelada en un estado activo previo.
   - **Regeneración de pantalla:** El buffer del dashboard ahora despliega limpiamente los 5 dispositivos en uso activo (Luces Santiago, Luces Pina, Portón, Riego y Temp. Pina).


---

### Etapa 16: Integración de la Colección de Iconos Meteorológicos InkyPi (7 Colores ACeP)

1. **Descarga y Repositorio de Iconos:**
   - Se clonaron los 38 iconos vectoriales de alta definición desde el repositorio `fatihak/InkyPi` (`src/plugins/weather/icons/`).
   - Guardados en `/root/epaper-hub/static/icons/weather_inkypi/`.

2. **Conversión y Optimización a la Paleta ACeP 7 Colores (`weather_acep/`):**
   - Se desarrolló un pipeline por lotes (`process_inkypi_icons.py`) que pre-procesa cada icono aplicando tramado Floyd-Steinberg contra los 7 pigmentos nativos (`0x0..0x6`), conservando la máscara alfa:
     - **Iconos Principales (`72×72 px`):** Para el bloque superior de clima (`01d`, `01n`, `02d`, `02n`, `03d`, `04d`, `09d`, `10d`, `10n`, `11d`, `13d`, `50d`, `51d`).
     - **Iconos Métricos (`20×20 px`):** Para la barra de telemetría (`humidity_20`, `wind_20`).
   - Los datos indexados se almacenan en binarios vectorizados `.npy` para estampado en $O(1)$ sin sobrecargar la CPU del servidor.

3. **Mapeo Inteligente WMO y Soporte Día / Noche (`generator/weather.py`):**
   - El código detecta automáticamente la hora local de Buenos Aires/Pinamar:
     - De día (`06:00 a 20:00`): Despejado utiliza `01d` (Sol dorado), Parcial nublado utiliza `02d`.
     - De noche (`20:00 a 06:00`): Despejado conmuta a `01n` (Luna en cuarto creciente), Lluvia nocturna a `10n`.
   - Se actualizaron las descripciones y el fallback en caso de desconexión.

4. **Integración en `generator/layout.py`:**
   - La clase `AcepCanvas` incorpora el método `draw_weather_icon(x, y, icon_name, size)`.
   - El bloque superior ahora dibuja el icono de 72 px en lugar de las primitivas geométricas básicas.
   - La línea de telemetría dibuja las miniaturas nítidas de la gota (`humidity_20`) y la ráfaga (`wind_20`).
   - El tiempo de renderizado de pantalla completa se redujo a **108.6 ms**.


---

### Etapa 17: Integración del Calendario Mensual Minimalista (Patrick Hand) y Clave Gemini API

1. **Implementación del Calendario Mensual (`generator/calendar_view.py`):**
   - Se trasladó la lógica del sketch de Arduino hacia el servidor, eliminando todo peso de la memoria Flash de la ESP32.
   - **Tipografía Patrick Hand:** Se subió `PatrickHand-Regular.ttf` al servidor (`/root/epaper-hub/static/fonts/`).
   - **Diseño Doodle / Bold:**
     - Año centrado arriba y Mes gigante destacado en negrita.
     - Días de la semana `Dom, Lun, Mar, Mie, Jue, Vie, Sab` delimitados por líneas triples de 3px. Domingos en Rojo (`0x4`), resto en Negro (`0x0`).
     - Grilla mensual con numeración en tamaño 34 pt.
     - **Día de hoy resaltado con círculo doodle rojo hecho a mano** y número en rojo.
     - Días con eventos de Google Calendar sincronizados marcados con un punto azul (`0x3`).
     - Pie con frase motivacional `"- Everyday is a fresh beginning! -"` o listado de eventos del mes de la agenda.
   - **Mapeo cromático 1-bit nítido:** El texto y líneas se renderizan sin antialiasing grisáceo para garantizar máximo contraste y blancura en el panel ACeP.

2. **Reorganización de los 5 Modos del Botón Táctil y del Hub Web:**
   - **1 toque:** `dashboard` (Dashboard principal con clima, tarjetas, domótica y QR).
   - **2 toques:** `calendar_month` (Calendario del Mes en curso estilo Patrick Hand con eventos).
   - **3 toques:** `photo_frame` (Marco de fotos 7C / Cómic diario).
   - **4 toques:** `guest_wifi` (Modo Visitas con QR gigante de CASA GATURRAKAS).
   - **5 toques:** `diagnostics` (Diagnóstico técnico y barras de calibración ACeP).
   - Se actualizaron el firmware `epaper_acep_hub_esp32.ino` y el control remoto en `templates/hub.html`.

3. **Configuración de Google Gemini API:**
   - Clave vinculada de forma segura en `config.py` (`GEMINI_API_KEY`).
   - Conexión verificada exitosamente (`HTTP 200`) contra Google Generative Language API con modelos habilitados de generación de imagen y texto (`gemini-2.5-flash-image`, `gemini-3-pro-image`, `gemini-2.5-flash`).

### Etapa 18: Generador de Cómic Diario 'Las Gaturrakas' (Estilo Jeff Smith's Bone)
- **Personajes:**
  1. **Gaturraka (Mamá):** Pelaje negro, corazón blanco distintivo en el pecho, expresión gruñona pero cariñosa.
  2. **Lucrecia (Hija 1):** Totalmente negra, cola en forma de rayo (zigzag como Pikachu), ojos gigantes de sorpresa, parkour felino.
  3. **Ceniza (Hija 2):** Color gris humo, contextura rellenita, durmiendo plácidamente en su taburete de madera.
- **Estilo Artístico:** Inspirado en la novela gráfica *Bone* de Jeff Smith (viñetas rectangulares con bordes negros limpios, márgenes blancos, entintado expresivo y colores cálidos).
- **Módulo Creado:** `/root/epaper-hub/generator/comic_generator.py`.
  - Construye el prompt según el día de la semana y el clima actual de Open-Meteo.
  - Conecta con la API de Gemini (o procesa imágenes suministradas vía CLI/Upload).
  - Procesa la imagen a `480x800` px mediante Tone Mapping + Dithering Atkinson perceptual en espacio CIELAB.
  - Almacena y activa el cómic en la base de datos `epaper_hub.db` (`fotos`).
  - Asignado al **Modo 3 toques** del sensor táctil del ESP32.

### Etapa 19: Diálogos en Español, Prioridad en Carrusel, Archivo y Cron 05:00 AM
- **Diálogos Contextuales en Español:**
  - El generador de prompts (`comic_generator.py`) ahora incorpora bocadillos de diálogo (speech balloons) dinámicos según el día de la semana y clima:
    - *Ceniza:* Frases cómicas de siesta y devoción por su taburete.
    - *Lucrecia:* Exclamaciones de sobresalto ("¡El piso es lava!", "¡Modo Rayo!") acordes a su cola de Pikachu.
    - *Gaturraka:* Respuestas gruñonas y exigentes pero permitiendo besos ("Solo un beso en la frente, Matías...").
- **Prioridad al Iniciar el Carrusel:**
  - En `database.py` (`pick_next_carousel_foto()`), el cómic del día tiene prioridad número 1 (`ORDER BY CASE WHEN nombre_archivo LIKE 'comic_YYYYMMDD%' AND mostrada_veces=0 THEN 0...`). Al entrar al carrusel, siempre se muestra primero el cómic de ese día, y luego continúa la rotación natural con el resto de fotos familiares.
- **Archivo Histórico Preservado:**
  - Los cómics anteriores (`comic_YYYYMMDD.png`) no se borran; permanecen en `/root/epaper-hub/static/uploads/` y en la base de datos `fotos` con `activa = 0`. De esta manera, se conservan todas las historietas pasadas pero únicamente la del día en curso participa del carrusel activo.
- **Automatización Diaria (Cron):**
  - Configurado en `/etc/cron.d/epaper-daily-comic` para ejecutarse todos los días a las `08:00 UTC` (`05:00 AM` hora Argentina). En cuanto la API Key tenga habilitado Pay-as-you-go en Google AI Studio, generará la nueva tira cómica de cada amanecer de forma 100% desatendida.

### Etapa 20: Firmware y Mapeo de Pines para ESP32-C6 (RISC-V Wi-Fi 6)
- **Análisis de Hardware ESP32-C6:**
  - Microcontrolador RISC-V 32-bit single-core con soporte Wi-Fi 6 (802.11ax), BT 5.0 y Zigbee/Thread.
  - *Diferencia Crítica:* El ESP32-C6 **NO posee hardware táctil capacitivo** (`touchRead()` ni `TOUCH_PAD` no existen).
  - *Mapeo de Pines:* En el ESP32 clásico se usaban GPIO 25, 26, 27 y 35, los cuales en el ESP32-C6 no existen o están reservados internamente a la memoria Flash (GPIO 24..30).
- **Nuevo Firmware Dedicado:** `/root/epaper-hub/esp32_firmware/epaper_acep_hub_esp32_c6.ino`.
  - **Mapeo de Pines E-Paper 8-pin:**
    - `DIN (MOSI)` -> `GPIO 7`
    - `CLK (SCK)` -> `GPIO 6`
    - `CS` -> `GPIO 18`
    - `DC` -> `GPIO 19`
    - `RST` -> `GPIO 20`
    - `BUSY` -> `GPIO 21`
    - `VCC` -> `3.3V` (¡Nunca 5V!) | `GND` -> `GND`
  - **Interacción por Botón (GPIO 9 - BOOT):**
    - Se utiliza el botón `BOOT` integrado en la placa ESP32-C6 (o un pulsador/sensor externo digital).
    - Despertar por Deep Sleep mediante `esp_deep_sleep_enable_gpio_wakeup(1ULL << 9, ESP_GPIO_WAKEUP_GPIO_LOW)`.
    - Detección de 1 a 5 clics y pulsación larga (> 3s) para el ciclo anti-ghosting.
  - **Compatibilidad Arduino IDE:** Requiere el paquete `esp32 by Espressif` versión `>= 3.0.0` y placa `ESP32C6 Dev Module`.

### Etapa 21: Mapeo Físico de Pines para Seeed Studio XIAO ESP32-C6
- **Factor de Forma XIAO (14 Pines Totales):**
  - La placa ultra-compacta dispone de 7 pines por lateral.
  - Los pines SPI nativos expuestos en la XIAO son: `D8` (SCK, GPIO 19) y `D10` (MOSI, GPIO 18).
- **Mapeo Cable Waveshare 7.3" ↔ Seeed Studio XIAO ESP32-C6:**
  - `VCC` (Rojo)     -> Pin `3V3` (Pin 7, abajo a la izquierda). ¡Nunca 5V!
  - `GND` (Negro)    -> Pin `GND` (Pin 13, arriba a la derecha).
  - `DIN` (Azul)     -> Pin `D10` (GPIO 18 / SPI MOSI).
  - `CLK` (Amarillo) -> Pin `D8`  (GPIO 19 / SPI SCK).
  - `CS`  (Naranja)  -> Pin `D3`  (GPIO 21).
  - `DC`  (Verde)    -> Pin `D1`  (GPIO 1).
  - `RST` (Blanco)   -> Pin `D2`  (GPIO 2).
  - `BUSY` (Violeta) -> Pin `D0`  (GPIO 0).
- **Control e Interacción:**
  - Botón `BOOT` físico integrado en la XIAO (GPIO 9).
  - Wakeup por interrupción GPIO en Deep Sleep.

### Etapa 22: Modo Carrusel Continuo Autónomo (Demo 1 min por pantalla)
- **Motivación:** Al no disponer de sensor táctil capacitivo en la placa XIAO ESP32-C6, se implementa una rotación autónoma de pantallas sin necesidad de botones para verificar el funcionamiento integral del sistema.
- **Ciclo de Pantallas Implementado (1 minuto exacto por pantalla):**
  1. `1 minuto`: **Dashboard Principal** (Clima InkyPi, Google Cal, Gastos, Domótica).
  2. `1 minuto`: **Calendario Mensual Patrick Hand**.
  3. `1 minuto`: **Por cada Foto activa / Cómic de Las Gaturrakas** (itera por cada foto subida).
  4. `1 minuto`: **Modo Visitas** (QR Wi-Fi CASA GATURRAKAS).
  5. `1 minuto`: **Diagnóstico Técnico** (Calibración ACeP, RSSI, IP).
  - Vuelve a empezar automáticamente en bucle continuo.
- **Backend (`app.py`):**
  - Soporte para parámetro `?touches=auto` / `?cycle=1` en `/api/screen.bin`.
  - El servidor orquesta la secuencia determinando cuántas fotos activas existen y avanzando el índice cíclico en cada petición.
- **Firmware XIAO (`epaper_acep_hub_esp32_c6.ino`):**
  - Ejecuta un `loop()` continuo sin Deep Sleep (manteniendo activo el puerto serie USB-CDC con cuenta regresiva en pantalla).
  - Botón `BOOT` integrado (GPIO 9): si se presiona, salta de inmediato a la siguiente pantalla sin esperar los 60 segundos.

### Etapa 23: Corrección de Compilación C++ (User-defined Literal en OTA Check)
- **Problema:** En el compilador GCC de Arduino para RISC-V (C++11/17), la sintaxis con comillas escapadas `indexOf("update_available":true)` activaba la regla del parser para operadores de literales definidos por usuario (`operator""update_available`).
- **Solución:** Simplificación a `payload.indexOf("update_available") >= 0 && payload.indexOf("true") >= 0` sin caracteres de escape conflictivos.
- **Archivos Actualizados:** `/root/epaper-hub/esp32_firmware/epaper_acep_hub_esp32_c6.ino` y copia local en `scratch/` y `brain/`.
