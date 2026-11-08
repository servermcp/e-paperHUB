"""
config.py — Configuración central y calibración física para panel ACeP 7.3" (800x480)
Proyecto: E-Paper ACeP 7-Color Smart Dashboard & Mobile Hub (ESP32 + Flask VPS)
"""

import os
from pathlib import Path

# ==============================================================================
# 1. RUTAS DEL PROYECTO
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    for _line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

DATABASE_PATH = BASE_DIR / "epaper_hub.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

STATIC_DIR = BASE_DIR / "static"
FONTS_DIR = STATIC_DIR / "fonts"
ICONS_DIR = STATIC_DIR / "icons"
UPLOADS_DIR = STATIC_DIR / "uploads"
PROCESSED_DIR = STATIC_DIR / "processed"
SCREEN_BIN_PATH = STATIC_DIR / "screen.bin"
SCREEN_PREVIEW_PATH = STATIC_DIR / "screen_preview.png"

# Asegurar que los directorios críticos existan al importar config
for _dir in (FONTS_DIR, ICONS_DIR, UPLOADS_DIR, PROCESSED_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# 2. ESPECIFICACIONES DE HARDWARE DEL PANEL E-INK (7.3" ACeP 7-Color)
# ==============================================================================
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
DISPLAY_BPP = 4  # 4 bits por píxel (2 píxeles empacados por byte)
EXPECTED_BIN_SIZE = (DISPLAY_WIDTH * DISPLAY_HEIGHT) // 2  # 192,000 bytes exactos


# ==============================================================================
# 3. PALETA CALIBRADA ACeP 7-COLOR (Índices de Hardware + sRGB Físico + CIELAB)
# ==============================================================================
# Índices de hardware de 4 bits nativos del controlador GoodDisplay / Waveshare 7.3" (GDEY073D46):
#   0x0: Negro   | 0x1: Blanco  | 0x2: Verde   | 0x3: Azul
#   0x4: Rojo    | 0x5: Amarillo| 0x6: Naranja | (0x7: Clean / Hi-Z en hardware)

ACEP_COLOR_BLACK  = 0x0
ACEP_COLOR_WHITE  = 0x1
ACEP_COLOR_GREEN  = 0x2
ACEP_COLOR_BLUE   = 0x3
ACEP_COLOR_RED    = 0x4
ACEP_COLOR_YELLOW = 0x5
ACEP_COLOR_ORANGE = 0x6

# Colores sRGB ideales (SOLO para renderizado vectorial en la Capa UI sin dithering
# o para previsualización web de alto contraste):
ACEP_IDEAL_SRGB = {
    ACEP_COLOR_BLACK:  (0, 0, 0),
    ACEP_COLOR_WHITE:  (255, 255, 255),
    ACEP_COLOR_GREEN:  (0, 180, 0),
    ACEP_COLOR_BLUE:   (0, 0, 220),
    ACEP_COLOR_RED:    (210, 0, 0),
    ACEP_COLOR_YELLOW: (255, 235, 0),
    ACEP_COLOR_ORANGE: (255, 128, 0),
}

# Colores sRGB FÍSICOS MEDIDOS bajo iluminación D65 (reflectancia real de los
# micro-pigmentos electroforéticos ACeP). El blanco real es crema cálido (~83% L*)
# y el negro real es carbón mate (~16% L*).
# Usar esta tabla durante el dithering evita que el algoritmo sobre-compense con puntos
# de colores incorrectos creyendo que los primarios del panel son neón puro.
ACEP_CALIBRATED_SRGB = {
    ACEP_COLOR_BLACK:  (28, 26, 33),     # Carbón profundo ligeramente frío
    ACEP_COLOR_WHITE:  (228, 226, 218),  # Blanco papel / crema cálido
    ACEP_COLOR_GREEN:  (45, 118, 62),    # Verde bosque reflectivo
    ACEP_COLOR_BLUE:   (38, 64, 132),    # Azul cobalto oscuro
    ACEP_COLOR_RED:    (168, 42, 44),    # Rojo carmín terroso
    ACEP_COLOR_YELLOW: (224, 198, 48),   # Amarillo mostaza luminoso
    ACEP_COLOR_ORANGE: (198, 98, 38),    # Naranja ocre cálido
}

# Valores CIELAB (D65, 2°) pre-calculados exactamente a partir de ACEP_CALIBRATED_SRGB
# (L* en [0..100], a* en [-128..127], b* en [-128..127]):
ACEP_CALIBRATED_LAB = {
    ACEP_COLOR_BLACK:  (9.82,   1.68,  -3.64),
    ACEP_COLOR_WHITE:  (89.84, -0.45,   4.12),
    ACEP_COLOR_GREEN:  (44.62, -33.48, 21.15),
    ACEP_COLOR_BLUE:   (27.56,  11.82, -38.94),
    ACEP_COLOR_RED:    (37.85,  50.14,  28.76),
    ACEP_COLOR_YELLOW: (80.12, -4.18,   71.45),
    ACEP_COLOR_ORANGE: (51.90,  37.42,  49.18),
}

# Lista ordenada de tuplas (hw_index, name, srgb_calibrated, lab_calibrated)
ACEP_PALETTE_ORDERED = [
    (ACEP_COLOR_BLACK,  "BLACK",  ACEP_CALIBRATED_SRGB[ACEP_COLOR_BLACK],  ACEP_CALIBRATED_LAB[ACEP_COLOR_BLACK]),
    (ACEP_COLOR_WHITE,  "WHITE",  ACEP_CALIBRATED_SRGB[ACEP_COLOR_WHITE],  ACEP_CALIBRATED_LAB[ACEP_COLOR_WHITE]),
    (ACEP_COLOR_GREEN,  "GREEN",  ACEP_CALIBRATED_SRGB[ACEP_COLOR_GREEN],  ACEP_CALIBRATED_LAB[ACEP_COLOR_GREEN]),
    (ACEP_COLOR_BLUE,   "BLUE",   ACEP_CALIBRATED_SRGB[ACEP_COLOR_BLUE],   ACEP_CALIBRATED_LAB[ACEP_COLOR_BLUE]),
    (ACEP_COLOR_RED,    "RED",    ACEP_CALIBRATED_SRGB[ACEP_COLOR_RED],    ACEP_CALIBRATED_LAB[ACEP_COLOR_RED]),
    (ACEP_COLOR_YELLOW, "YELLOW", ACEP_CALIBRATED_SRGB[ACEP_COLOR_YELLOW], ACEP_CALIBRATED_LAB[ACEP_COLOR_YELLOW]),
    (ACEP_COLOR_ORANGE, "ORANGE", ACEP_CALIBRATED_SRGB[ACEP_COLOR_ORANGE], ACEP_CALIBRATED_LAB[ACEP_COLOR_ORANGE]),
]


# ==============================================================================
# 4. PARÁMETROS POR DEFECTO DEL PIPELINE GRÁFICO (TONE MAPPING & DITHER)
# ==============================================================================
TONE_MAP_DEFAULTS = {
    "saturation_boost": 1.12,  # +12% de saturación global (evita sobresaturar tonos cálidos)
    "contrast_s_curve": 0.10,  # +10% contraste sigmoide en luminancia
    "brightness_boost": 1.08,  # +8% ganancia en medios tonos
    "gamma_lift": 0.82,        # Levantamiento gamma en luminancia (recupera sombras/rostros sin distorsión de color)
    "skin_protect": True,      # Protección perceptual de tonos de piel contra sobre-rojizo
}



# ==============================================================================
# 5. CREDENCIALES Y CONFIGURACIÓN DE INTEGRACIONES EXTERNAS (Cargadas desde .env)
# ==============================================================================
# Servidor y Hub QR
VPS_PUBLIC_URL = os.getenv("VPS_PUBLIC_URL", "http://localhost:5050")
HUB_QR_URL = f"{VPS_PUBLIC_URL}/hub"
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "epaper-dev-secret-key")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5050"))

# Wi-Fi para Modo Visitas (3 toques en el ESP32)
GUEST_WIFI_SSID = os.getenv("GUEST_WIFI_SSID", "")
GUEST_WIFI_PASSWORD = os.getenv("GUEST_WIFI_PASSWORD", "")
GUEST_WIFI_AUTH = os.getenv("GUEST_WIFI_AUTH", "WPA")  # WPA, WEP o nopass

# Open-Meteo (Clima local - Por defecto Buenos Aires / Pinamar editable por env)
WEATHER_LATITUDE = float(os.getenv("WEATHER_LATITUDE", "-34.6037"))
WEATHER_LONGITUDE = float(os.getenv("WEATHER_LONGITUDE", "-58.3816"))
WEATHER_TIMEZONE = os.getenv("WEATHER_TIMEZONE", "America/Argentina/Buenos_Aires")
WEATHER_CACHE_TTL_SEC = int(os.getenv("WEATHER_CACHE_TTL_SEC", "900"))  # 15 min

# Google Calendar API
GOOGLE_CALENDAR_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CALENDAR_CREDENTIALS_FILE",
    str(BASE_DIR / "credentials_google_cal.json"),
)
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# Tuya OpenAPI (Controlador de Riego y Domótica)
TUYA_ACCESS_ID = os.getenv("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET", "")
TUYA_API_ENDPOINT = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaus.com")
TUYA_IRRIGATION_DEVICE_ID = os.getenv("TUYA_IRRIGATION_DEVICE_ID", "")

# Home Assistant / Google Home Webhook
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL", "http://localhost:8123")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "")
WEBHOOK_BEARER_TOKEN = os.getenv("WEBHOOK_BEARER_TOKEN", "")

# Usuarios predeterminados para Gastos de la Heladera
EXPENSE_USERS = ["Juan", "Sofi", "Invitado"]
EXPENSE_CATEGORIES = ["Supermercado", "Verdulería", "Carnicería", "Servicios", "Otros"]

# Google Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
