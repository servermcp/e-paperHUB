"""
generator/dashboard_themes.py — Motores gráficos para los 3 temas de Dashboard de e-paperHUB:
  1. Crayón / Hecho a Mano (Playful Sketch con tipografía Crayon Libre y trazo de cera)
  2. Muji Minimal / E-Ink Studio (Diseño limpio japonés/escandinavo, hermano del Calendario)
  3. Modern Bento Grid (Tarjetas modulares redondeadas de alta densidad)

Todos los temas aprovechan el ancho completo (480 x 800 px) con márgenes mínimos de 14-16 px.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import qrcode
except ImportError:
    qrcode = None

import config
import database
from generator.weather import fetch_weather

PORTRAIT_W = 480
PORTRAIT_H = 800

# Tipografías del proyecto
FONTS_DIR = config.FONTS_DIR
FONT_CRAYON = FONTS_DIR / "CrayonLibre-Regular.ttf"
FONT_ROBOTO_BOLD = FONTS_DIR / "Roboto-Bold.ttf"
FONT_ROBOTO_MED = FONTS_DIR / "Roboto-Medium.ttf"
FONT_ROBOTO_REG = FONTS_DIR / "Roboto-Regular.ttf"

_FONT_CANDIDATES_MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]

# Directorios de recursos
LOGOS_DIR = config.ICONS_DIR / "logos"
WEATHER_CRAYON_DIR = config.ICONS_DIR / "weather_crayon"
WEATHER_ACEP_DIR = config.ICONS_DIR / "weather_acep"

_DAYS_ES = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
_DAYS_ES_TITLE = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_MONTHS_ES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
_MONTHS_ES_FULL = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# Paleta ACeP RGB pura de referencia
RGB_BLACK = (25, 25, 25)
RGB_WHITE = (255, 255, 255)
RGB_GREEN = (126, 188, 36)
RGB_BLUE = (0, 135, 215)
RGB_RED = (215, 30, 40)
RGB_YELLOW = (229, 196, 40)
RGB_ORANGE = (220, 110, 30)


def _load_font(path: Path | str, size: int) -> ImageFont.FreeTypeFont:
    p = Path(path)
    if p.exists():
        try:
            return ImageFont.truetype(str(p), size=size)
        except Exception:
            pass
    for cand in _FONT_CANDIDATES_MONO:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _load_mono_font(size: int) -> ImageFont.FreeTypeFont:
    for cand in _FONT_CANDIDATES_MONO:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size=size)
            except Exception:
                pass
    return _load_font(FONT_ROBOTO_BOLD, size)


def _fmt_money(val: float) -> str:
    v = round(float(val))
    if v <= 0:
        return "$0"
    return f"${v:,}".replace(",", ".")


def _draw_qr_to_image(img: Image.Image, x: int, y: int, size: int = 70, border: int = 1) -> None:
    if qrcode is None:
        d = ImageDraw.Draw(img)
        d.rectangle([x, y, x + size, y + size], fill=RGB_BLACK)
        d.text((x + 10, y + size // 2 - 8), "QR", fill=RGB_WHITE)
        return
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=3,
        border=border,
    )
    qr.add_data(config.HUB_QR_URL)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_resized = qr_img.resize((size, size), Image.Resampling.NEAREST)
    img.paste(qr_resized, (x, y))


def _paste_logo(img: Image.Image, x: int, y: int, logo_name: str, size: int = 28) -> None:
    clean_name = logo_name.lower().strip()
    png_path = LOGOS_DIR / f"{clean_name}.png"
    if png_path.exists():
        try:
            icon = Image.open(png_path).convert("RGBA")
            if icon.size != (size, size):
                icon = icon.resize((size, size), Image.Resampling.LANCZOS)
            img.paste(icon, (x, y), icon)
            return
        except Exception:
            pass
    # Fallback badge
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x + size, y + size], radius=4, fill=RGB_WHITE, outline=RGB_BLACK, width=1)
    letter = clean_name[:2].upper() if clean_name else "ID"
    f = _load_mono_font(10)
    d.text((x + 4, y + size // 2 - 6), letter, font=f, fill=RGB_BLACK)


def _pil_to_acep_canvas(img: Image.Image) -> Any:
    """
    Convierte una imagen PIL RGB de 480x800 a AcepCanvas mapeando nítidamente
    los 7 pigmentos de hardware ACeP.
    """
    from generator.layout import AcepCanvas
    arr = np.array(img.convert("RGB"))
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]

    # Clasificación directa por pigmentos puros
    is_black = (r < 85) & (g < 85) & (b < 85)
    is_red = (r > 160) & (g < 85) & (b < 85)
    is_blue = (b > 155) & (r < 100)
    is_green = (g > 130) & (b < 100) & (r < 180)
    is_orange = (r > 175) & (g >= 65) & (g <= 150) & (b < 75)
    is_yellow = (r > 175) & (g > 155) & (b < 110)

    canvas = AcepCanvas(width=PORTRAIT_W, height=PORTRAIT_H)
    canvas.matrix.fill(config.ACEP_COLOR_WHITE)
    canvas.matrix[is_black] = config.ACEP_COLOR_BLACK
    canvas.matrix[is_red] = config.ACEP_COLOR_RED
    canvas.matrix[is_blue] = config.ACEP_COLOR_BLUE
    canvas.matrix[is_green] = config.ACEP_COLOR_GREEN
    canvas.matrix[is_orange] = config.ACEP_COLOR_ORANGE
    canvas.matrix[is_yellow] = config.ACEP_COLOR_YELLOW
    return canvas


# ==============================================================================
# TEMA 1: CRAYÓN / HECHO A MANO (TRAZO DE CERA AUTÉNTICO)
# ==============================================================================

def render_dashboard_crayon(
    calendar_events: Optional[List[Dict[str, str]]] = None,
) -> Any:
    img = Image.new("RGB", (PORTRAIT_W, PORTRAIT_H), RGB_WHITE)
    d = ImageDraw.Draw(img)

    f_title = _load_font(FONT_CRAYON, 32)
    f_lg = _load_font(FONT_CRAYON, 24)
    f_md = _load_font(FONT_CRAYON, 19)
    f_sm = _load_font(FONT_CRAYON, 15)

    now = datetime.now()
    date_label = f"{_DAYS_ES_TITLE[now.weekday()]} {now.day:02d} {_MONTHS_ES[now.month - 1]}"
    time_label = now.strftime("%H:%M")

    weather = fetch_weather()
    tarjetas = database.list_tarjetas_gastos()
    totales = database.get_tarjetas_totals()
    devices = database.get_visible_dashboard_devices()

    if calendar_events is None:
        calendar_events = [
            {"time": "10:30", "title": "Revisión contratos & proveedores"},
            {"time": "18:00", "title": "Turno control / Compras súper"},
        ]

    # Helper para líneas de crayón imperfectas (wobbly lines)
    def draw_crayon_line(x0: int, y: int, x1: int, color: Tuple[int, int, int], width: int = 2):
        np.random.seed(int(y) * 17 + int(x0))
        pts = []
        for x in range(x0, x1 + 1, 6):
            jitter_y = y + np.sin(x * 0.08) * 1.5 + (np.random.rand() - 0.5) * 1.5
            pts.append((x, jitter_y))
        d.line(pts, fill=color, width=width)

    M = 14
    W_C = PORTRAIT_W - M

    # 1. Cabecera (Fecha + Hora)
    d.text((M, 10), date_label, font=f_title, fill=RGB_BLACK)
    d.text((W_C - 80, 10), time_label, font=f_title, fill=RGB_RED)
    draw_crayon_line(M, 48, W_C, RGB_ORANGE, width=3)

    # 2. Clima con ícono de crayón
    icon_name = weather.get("icon_name", "01d")
    # Buscar ícono en static/icons/weather_crayon/
    crayon_icon_path = WEATHER_CRAYON_DIR / f"{icon_name}.png"
    if not crayon_icon_path.exists():
        crayon_icon_path = WEATHER_CRAYON_DIR / "01d.png"

    if crayon_icon_path.exists():
        try:
            w_ico = Image.open(crayon_icon_path).convert("RGBA")
            w_ico = w_ico.resize((92, 92), Image.Resampling.LANCZOS)
            img.paste(w_ico, (M, 54), w_ico)
        except Exception:
            pass

    # Temperatura grande en crayón
    d.text((M + 104, 56), f"{weather['temp_current']}°", font=_load_font(FONT_CRAYON, 48), fill=RGB_BLACK)
    desc_str = weather.get("description", "Despejado")
    d.text((M + 106, 110), desc_str[:22], font=f_md, fill=RGB_BLUE)

    # Métricas a la derecha
    d.text((W_C - 105, 58), f"Max: {weather['temp_max']}°", font=f_md, fill=RGB_RED)
    d.text((W_C - 105, 82), f"Min: {weather['temp_min']}°", font=f_md, fill=RGB_BLUE)
    rain_p = weather.get("rain_prob", 0)
    rain_col = RGB_RED if rain_p >= 50 else RGB_GREEN
    d.text((W_C - 105, 106), f"Lluvia: {rain_p}%", font=f_md, fill=rain_col)

    draw_crayon_line(M, 150, W_C, RGB_BLACK, width=2)

    # 3. Agenda / Cosas de hoy
    d.text((M, 156), "Cosas para hacer hoy:", font=f_lg, fill=RGB_BLACK)
    ev_y = 188
    for idx, ev in enumerate(calendar_events[:2]):
        col_box = RGB_GREEN if idx == 0 else RGB_BLUE
        d.rounded_rectangle([M, ev_y, W_C, ev_y + 32], radius=8, outline=col_box, width=2)
        d.text((M + 10, ev_y + 4), f"{ev.get('time', '--:--')}  {ev.get('title', '')[:30]}", font=f_md, fill=RGB_BLACK)
        ev_y += 38

    draw_crayon_line(M, ev_y + 4, W_C, RGB_RED, width=3)

    # 4. Tabla de Cuentas y Tarjetas
    t_y = ev_y + 12
    d.text((M, t_y), "Cuentas del mes (a pagar!):", font=f_lg, fill=RGB_RED)

    # Encabezados de tabla
    d.text((M, t_y + 30), "CUENTA", font=f_sm, fill=RGB_BLUE)
    d.text((200, t_y + 30), "TOTAL", font=f_sm, fill=RGB_BLUE)
    d.text((305, t_y + 30), "MÍNIMO", font=f_sm, fill=RGB_BLUE)
    d.text((395, t_y + 30), "SALDO", font=f_sm, fill=RGB_BLUE)
    draw_crayon_line(M, t_y + 50, W_C, (220, 220, 220), width=1)

    ry = t_y + 56
    for item in tarjetas[:5]:
        _paste_logo(img, M, ry, item.get("logo_empresa", ""), size=22)
        _paste_logo(img, M + 26, ry, item.get("logo_gasto", ""), size=22)

        name = item.get("etiqueta", "")[:12]
        d.text((M + 52, ry + 1), name, font=f_md, fill=RGB_BLACK)

        tot_val = float(item["total"])
        min_val = float(item["minimo"])
        sal_val = float(item["saldo"])

        d.text((195, ry + 1), _fmt_money(tot_val), font=f_md, fill=RGB_BLACK)
        d.text((305, ry + 1), _fmt_money(min_val), font=f_md, fill=RGB_BLACK)

        if sal_val <= 0:
            d.text((395, ry + 1), "PAGADO!", font=f_md, fill=RGB_GREEN)
        elif tot_val - sal_val >= min_val and min_val > 0:
            d.text((395, ry + 1), _fmt_money(sal_val), font=f_md, fill=RGB_ORANGE)
        else:
            d.text((395, ry + 1), _fmt_money(sal_val), font=f_md, fill=RGB_RED)

        ry += 32
        draw_crayon_line(M, ry - 4, W_C, (230, 230, 230), width=1)

    # Caja de Total Pendiente en Crayón Amarillo
    tot_box_y = max(ry + 2, 492)
    d.rounded_rectangle([M, tot_box_y, W_C, tot_box_y + 40], radius=10, fill=(255, 250, 215), outline=RGB_BLACK, width=2)
    d.text((M + 12, tot_box_y + 7), "TOTAL PENDIENTE:", font=f_lg, fill=RGB_BLACK)
    tot_sal = totales.get("total_saldo", 0)
    tot_col = RGB_GREEN if tot_sal <= 0 else RGB_RED
    d.text((W_C - 145, tot_box_y + 7), _fmt_money(tot_sal), font=f_lg, fill=tot_col)

    draw_crayon_line(M, tot_box_y + 50, W_C, RGB_BLUE, width=3)

    # 5. Domótica + QR
    dom_y = tot_box_y + 58
    d.text((M, dom_y), "Casa & Jardín:", font=f_lg, fill=RGB_BLUE)

    dy_item = dom_y + 28
    for dev in devices[:4]:
        st = dev.get("status_text", "")
        st_low = st.lower()
        if any(w in st_low for w in ("encendida", "cerrado", "filtrando", "regando", "barriendo")):
            st_col = RGB_GREEN if ("regando" in st_low or "filtrando" in st_low or "cerrado" in st_low) else RGB_ORANGE
        elif "°" in st_low:
            st_col = RGB_BLUE
        else:
            st_col = RGB_RED

        d.text((M + 4, dy_item), f"■ {dev['device_name'][:12]}:", font=f_md, fill=RGB_BLACK)
        d.text((M + 140, dy_item), st[:18], font=f_md, fill=st_col)
        dy_item += 25

    # QR del Hub a la derecha con marco de crayón
    qr_x = W_C - 100
    qr_y = dom_y + 8
    d.rounded_rectangle([qr_x, qr_y, W_C, qr_y + 115], radius=8, outline=RGB_BLACK, width=2)
    _draw_qr_to_image(img, qr_x + 15, qr_y + 10, size=70, border=1)
    d.text((qr_x + 12, qr_y + 84), "ESCANEA", font=f_sm, fill=RGB_BLUE)
    d.text((qr_x + 16, qr_y + 98), "EL HUB", font=f_sm, fill=RGB_BLUE)

    # Footer
    d.text((M, 774), "Batería: 88% (4.02V) • Wi-Fi OK", font=f_sm, fill=RGB_BLACK)
    d.text((W_C - 90, 774), "Tokyo VPS ✓", font=f_sm, fill=RGB_GREEN)

    return _pil_to_acep_canvas(img)


# ==============================================================================
# TEMA 2: MUJI MINIMAL / E-INK STUDIO (HERMANO DEL CALENDARIO)
# ==============================================================================

def render_dashboard_muji(
    calendar_events: Optional[List[Dict[str, str]]] = None,
) -> Any:
    img = Image.new("RGB", (PORTRAIT_W, PORTRAIT_H), RGB_WHITE)
    d = ImageDraw.Draw(img)

    f_num_big = _load_font(FONT_ROBOTO_BOLD, 56)
    f_h1 = _load_font(FONT_ROBOTO_BOLD, 24)
    f_h2 = _load_font(FONT_ROBOTO_MED, 16)
    f_reg = _load_font(FONT_ROBOTO_REG, 15)
    f_bold = _load_font(FONT_ROBOTO_BOLD, 15)
    f_sm = _load_font(FONT_ROBOTO_REG, 12)
    f_sm_bold = _load_font(FONT_ROBOTO_BOLD, 12)
    f_mono = _load_mono_font(15)

    now = datetime.now()
    time_label = now.strftime("%H:%M")

    weather = fetch_weather()
    tarjetas = database.list_tarjetas_gastos()
    totales = database.get_tarjetas_totals()
    devices = database.get_visible_dashboard_devices()

    if calendar_events is None:
        calendar_events = [
            {"time": "10:30", "title": "Revisión contratos & proveedores"},
            {"time": "18:00", "title": "Turno control / Compras súper"},
        ]

    M = 16
    W_C = PORTRAIT_W - M
    GREY_LINE = (220, 220, 220)
    GREY_TEXT = (130, 130, 130)

    # 1. Cabecera Muji: Gran número de día, LUNES en rojo, mes en gris
    d.text((M, 16), f"{now.day:02d}", font=f_num_big, fill=RGB_BLACK)
    d.text((M + 75, 22), _DAYS_ES[now.weekday()], font=f_h2, fill=RGB_RED)
    d.text((M + 75, 46), f"{_MONTHS_ES_FULL[now.month - 1].upper()} {now.year}", font=f_sm, fill=GREY_TEXT)

    # Pastilla negra redondeada para la hora (idéntica al calendario)
    d.rounded_rectangle([W_C - 74, 26, W_C, 56], radius=15, fill=RGB_BLACK)
    d.text((W_C - 60, 32), time_label, font=f_bold, fill=RGB_WHITE)

    d.line([(M, 86), (W_C, 86)], fill=GREY_LINE, width=1)

    # 2. Clima Muji
    d.text((M, 98), f"{weather['temp_current']}°", font=_load_font(FONT_ROBOTO_BOLD, 52), fill=RGB_BLACK)
    d.text((M + 95, 106), weather.get("description", "Despejado")[:20], font=f_h1, fill=RGB_BLUE)
    d.text((M + 95, 136), f"Humedad {weather['humidity']}% • Viento {weather['wind_kmh']} km/h", font=f_sm, fill=GREY_TEXT)

    # Píldoras climáticas
    d.rounded_rectangle([W_C - 170, 104, W_C - 95, 128], radius=6, fill=(254, 242, 242), outline=RGB_RED, width=1)
    d.text((W_C - 162, 108), f"▲ {weather['temp_max']}° MAX", font=f_sm_bold, fill=RGB_RED)

    d.rounded_rectangle([W_C - 85, 104, W_C, 128], radius=6, fill=(240, 249, 255), outline=RGB_BLUE, width=1)
    d.text((W_C - 78, 108), f"▼ {weather['temp_min']}° MIN", font=f_sm_bold, fill=RGB_BLUE)

    rain_p = weather.get("rain_prob", 0)
    d.rounded_rectangle([W_C - 85, 136, W_C, 160], radius=6, fill=(245, 245, 245), outline=GREY_LINE, width=1)
    d.text((W_C - 74, 140), f"{rain_p}% LLUVIA", font=f_sm_bold, fill=RGB_BLACK)

    d.line([(M, 172), (W_C, 172)], fill=GREY_LINE, width=1)

    # 3. Agenda Muji
    d.text((M, 184), "PRÓXIMOS COMPROMISOS", font=f_sm_bold, fill=GREY_TEXT)
    ev_y = 210
    for idx, ev in enumerate(calendar_events[:2]):
        col_pill = RGB_GREEN if idx == 0 else RGB_BLUE
        d.rounded_rectangle([M, ev_y, M + 68, ev_y + 26], radius=13, fill=col_pill)
        d.text((M + 14, ev_y + 5), ev.get("time", "--:--"), font=f_sm_bold, fill=RGB_WHITE)
        d.text((M + 80, ev_y + 4), ev.get("title", "")[:32], font=f_bold, fill=RGB_BLACK)
        ev_y += 36

    d.line([(M, 288), (W_C, 288)], fill=GREY_LINE, width=1)

    # 4. Tabla de Tarjetas y Servicios
    d.text((M, 300), "TARJETAS Y SERVICIOS", font=f_sm_bold, fill=GREY_TEXT)
    d.text((W_C - 120, 300), "CIERRE MENSUAL", font=f_sm, fill=GREY_TEXT)

    d.text((M, 324), "EMPRESA / SERVICIO", font=f_sm_bold, fill=GREY_TEXT)
    d.text((210, 324), "TOTAL", font=f_sm_bold, fill=GREY_TEXT)
    d.text((310, 324), "MÍNIMO", font=f_sm_bold, fill=GREY_TEXT)
    d.text((400, 324), "SALDO", font=f_sm_bold, fill=GREY_TEXT)
    d.line([(M, 344), (W_C, 344)], fill=GREY_LINE, width=1)

    ry = 356
    for item in tarjetas[:5]:
        _paste_logo(img, M, ry, item.get("logo_empresa", ""), size=22)
        _paste_logo(img, M + 26, ry, item.get("logo_gasto", ""), size=22)

        name = item.get("etiqueta", "")[:12]
        d.text((M + 52, ry), name, font=f_bold, fill=RGB_BLACK)
        vto = str(item.get("vencimiento", "")).strip()
        if vto:
            d.text((M + 52, ry + 16), f"Vto: {vto[:5]}", font=f_sm, fill=GREY_TEXT)

        tot_val = float(item["total"])
        min_val = float(item["minimo"])
        sal_val = float(item["saldo"])

        d.text((205, ry + 2), _fmt_money(tot_val), font=f_mono, fill=RGB_BLACK)
        d.text((310, ry + 2), _fmt_money(min_val), font=f_mono, fill=RGB_BLACK)

        if sal_val <= 0:
            d.rounded_rectangle([W_C - 74, ry, W_C, ry + 22], radius=11, fill=(236, 253, 245), outline=RGB_GREEN, width=1)
            d.text((W_C - 62, ry + 3), "PAGADO", font=f_sm_bold, fill=RGB_GREEN)
        elif tot_val - sal_val >= min_val and min_val > 0:
            d.text((395, ry + 2), _fmt_money(sal_val), font=f_mono, fill=RGB_ORANGE)
        else:
            d.text((395, ry + 2), _fmt_money(sal_val), font=f_mono, fill=RGB_RED)

        ry += 40
        d.line([(M, ry - 4), (W_C, ry - 4)], fill=(242, 242, 242), width=1)

    # Barra de Total Muji
    tot_bar_y = max(ry, 524)
    d.rounded_rectangle([M, tot_bar_y, W_C, tot_bar_y + 36], radius=8, fill=(249, 250, 251), outline=GREY_LINE, width=1)
    d.text((M + 14, tot_bar_y + 9), "TOTAL PENDIENTE DEL MES", font=f_sm_bold, fill=RGB_BLACK)
    tot_sal = totales.get("total_saldo", 0)
    d.text((W_C - 120, tot_bar_y + 8), _fmt_money(tot_sal), font=f_h2, fill=RGB_RED if tot_sal > 0 else RGB_GREEN)

    d.line([(M, tot_bar_y + 48), (W_C, tot_bar_y + 48)], fill=GREY_LINE, width=1)

    # 5. Domótica + QR Muji
    dom_y = tot_bar_y + 58
    d.text((M, dom_y), "DISPOSITIVOS CONECTADOS", font=f_sm_bold, fill=GREY_TEXT)

    dy_pos = dom_y + 24
    for dev in devices[:4]:
        st = dev.get("status_text", "")
        st_low = st.lower()
        if any(w in st_low for w in ("encendida", "cerrado", "filtrando", "regando", "barriendo")):
            dot_c = RGB_GREEN if ("regando" in st_low or "filtrando" in st_low or "cerrado" in st_low) else RGB_ORANGE
        elif "°" in st_low:
            dot_c = RGB_BLUE
        else:
            dot_c = RGB_RED

        d.ellipse([M, dy_pos + 4, M + 8, dy_pos + 12], fill=dot_c)
        d.text((M + 16, dy_pos), dev["device_name"][:14], font=f_bold, fill=RGB_BLACK)
        d.text((M + 140, dy_pos), st[:18], font=f_reg, fill=dot_c)
        dy_pos += 26

    # QR limpio
    qr_x = W_C - 85
    qr_y = dom_y + 10
    d.rounded_rectangle([qr_x, qr_y, W_C, qr_y + 95], radius=8, fill=RGB_WHITE, outline=GREY_LINE, width=1)
    _draw_qr_to_image(img, qr_x + 10, qr_y + 8, size=65, border=1)
    d.text((qr_x + 14, qr_y + 78), "WEB HUB", font=f_sm_bold, fill=RGB_BLACK)

    # Footer telemetría
    d.line([(M, 770), (W_C, 770)], fill=GREY_LINE, width=1)
    d.text((M, 778), "ESP32-C6 • 4.02V (88%) • RSSI -60 dBm", font=f_sm, fill=GREY_TEXT)
    d.text((W_C - 85, 778), "Tokyo VPS OK", font=f_sm_bold, fill=RGB_GREEN)

    return _pil_to_acep_canvas(img)


# ==============================================================================
# TEMA 3: MODERN BENTO GRID (MODULAR TECH)
# ==============================================================================

def render_dashboard_bento(
    calendar_events: Optional[List[Dict[str, str]]] = None,
) -> Any:
    img = Image.new("RGB", (PORTRAIT_W, PORTRAIT_H), (245, 243, 239))
    d = ImageDraw.Draw(img)

    f_h1 = _load_font(FONT_ROBOTO_BOLD, 20)
    f_h2 = _load_font(FONT_ROBOTO_MED, 16)
    f_bold = _load_font(FONT_ROBOTO_BOLD, 14)
    f_reg = _load_font(FONT_ROBOTO_REG, 14)
    f_sm = _load_font(FONT_ROBOTO_REG, 12)
    f_sm_bold = _load_font(FONT_ROBOTO_BOLD, 12)
    f_mono = _load_mono_font(14)

    now = datetime.now()
    weather = fetch_weather()
    tarjetas = database.list_tarjetas_gastos()
    totales = database.get_tarjetas_totals()
    devices = database.get_visible_dashboard_devices()

    if calendar_events is None:
        calendar_events = [
            {"time": "10:30", "title": "Revisión contratos & proveedores"},
            {"time": "18:00", "title": "Turno control / Compras súper"},
        ]

    M = 14
    W_CARD = PORTRAIT_W - M
    BORDER = (35, 35, 35)

    # CARD 1: HEADER & CLIMA (14 .. 166)
    d.rounded_rectangle([M, 14, W_CARD, 166], radius=12, fill=RGB_WHITE, outline=BORDER, width=2)
    d.rounded_rectangle([M + 10, 24, M + 115, 48], radius=6, fill=RGB_BLACK)
    d.text((M + 18, 28), f"{_DAYS_ES[now.weekday()][:3]} {now.day:02d} {_MONTHS_ES[now.month - 1]}", font=f_sm_bold, fill=RGB_WHITE)
    d.text((M + 125, 28), f"Semana {now.isocalendar()[1]}", font=f_sm, fill=(120, 120, 120))
    d.text((W_CARD - 70, 26), now.strftime("%H:%M hs"), font=f_h2, fill=RGB_BLUE)
    d.line([(M + 10, 56), (W_CARD - 10, 56)], fill=(230, 230, 230), width=1)

    d.text((M + 14, 66), f"{weather['temp_current']}°C", font=_load_font(FONT_ROBOTO_BOLD, 52), fill=RGB_BLACK)
    d.text((M + 18, 128), weather.get("description", "Despejado")[:22], font=f_sm_bold, fill=RGB_BLUE)
    d.text((M + 18, 144), f"Viento {weather['wind_kmh']} km/h • Hum. {weather['humidity']}%", font=f_sm, fill=(120, 120, 120))

    # Micro-pills derecha
    d.rounded_rectangle([W_CARD - 110, 68, W_CARD - 14, 94], radius=6, fill=(254, 242, 242), outline=RGB_RED, width=1)
    d.text((W_CARD - 98, 73), f"▲ MAX {weather['temp_max']}°", font=f_sm_bold, fill=RGB_RED)

    d.rounded_rectangle([W_CARD - 110, 102, W_CARD - 14, 128], radius=6, fill=(240, 249, 255), outline=RGB_BLUE, width=1)
    d.text((W_CARD - 98, 107), f"▼ MIN {weather['temp_min']}°", font=f_sm_bold, fill=RGB_BLUE)

    d.rounded_rectangle([W_CARD - 110, 134, W_CARD - 14, 158], radius=6, fill=(245, 245, 245), outline=BORDER, width=1)
    d.text((W_CARD - 98, 139), f"💧 LLUVIA {weather.get('rain_prob', 0)}%", font=f_sm_bold, fill=RGB_BLACK)

    # CARD 2: AGENDA DE HOY (176 .. 280)
    d.rounded_rectangle([M, 176, W_CARD, 280], radius=12, fill=RGB_WHITE, outline=BORDER, width=2)
    d.text((M + 14, 186), "📅  AGENDA DE HOY", font=f_sm_bold, fill=RGB_BLACK)
    d.text((W_CARD - 80, 186), f"{len(calendar_events)} EVENTOS", font=f_sm, fill=(120, 120, 120))

    ev_y = 210
    for idx, ev in enumerate(calendar_events[:2]):
        col_pill = RGB_GREEN if idx == 0 else RGB_BLUE
        d.rounded_rectangle([M + 10, ev_y, W_CARD - 10, ev_y + 28], radius=8, fill=(249, 250, 251), outline=(220, 220, 220), width=1)
        d.rounded_rectangle([M + 16, ev_y + 5, M + 70, ev_y + 23], radius=4, fill=col_pill)
        d.text((M + 24, ev_y + 7), ev.get("time", "--:--"), font=f_sm_bold, fill=RGB_WHITE)
        d.text((M + 80, ev_y + 6), ev.get("title", "")[:32], font=f_bold, fill=RGB_BLACK)
        ev_y += 34

    # CARD 3: FINANZAS & SERVICIOS (290 .. 580)
    d.rounded_rectangle([M, 290, W_CARD, 580], radius=12, fill=RGB_WHITE, outline=BORDER, width=2)
    d.text((M + 14, 302), "💳  FINANZAS Y SERVICIOS", font=f_sm_bold, fill=RGB_BLACK)
    d.text((W_CARD - 110, 302), "CIERRE MENSUAL", font=f_sm, fill=RGB_RED)

    d.text((M + 14, 326), "CUENTA", font=f_sm_bold, fill=(120, 120, 120))
    d.text((200, 326), "TOTAL", font=f_sm_bold, fill=(120, 120, 120))
    d.text((295, 326), "MÍNIMO", font=f_sm_bold, fill=(120, 120, 120))
    d.text((390, 326), "SALDO", font=f_sm_bold, fill=(120, 120, 120))
    d.line([(M + 10, 344), (W_CARD - 10, 344)], fill=(230, 230, 230), width=1)

    bry = 354
    for item in tarjetas[:5]:
        _paste_logo(img, M + 14, bry, item.get("logo_empresa", ""), size=20)
        _paste_logo(img, M + 38, bry, item.get("logo_gasto", ""), size=20)

        name = item.get("etiqueta", "")[:10]
        d.text((M + 62, bry + 2), name, font=f_bold, fill=RGB_BLACK)

        tot_val = float(item["total"])
        min_val = float(item["minimo"])
        sal_val = float(item["saldo"])

        d.text((195, bry + 2), _fmt_money(tot_val), font=f_mono, fill=RGB_BLACK)
        d.text((295, bry + 2), _fmt_money(min_val), font=f_mono, fill=RGB_BLACK)

        if sal_val <= 0:
            d.rounded_rectangle([W_CARD - 70, bry, W_CARD - 14, bry + 22], radius=4, fill=(236, 253, 245), outline=RGB_GREEN, width=1)
            d.text((W_CARD - 62, bry + 4), "PAGADO", font=f_sm_bold, fill=RGB_GREEN)
        elif tot_val - sal_val >= min_val and min_val > 0:
            d.text((385, bry + 2), _fmt_money(sal_val), font=f_mono, fill=RGB_ORANGE)
        else:
            d.text((385, bry + 2), _fmt_money(sal_val), font=f_mono, fill=RGB_RED)

        bry += 34
        d.line([(M + 10, bry - 4), (W_CARD - 10, bry - 4)], fill=(240, 240, 240), width=1)

    # Total Bento
    d.rounded_rectangle([M + 10, 532, W_CARD - 10, 568], radius=8, fill=(254, 243, 199), outline=(217, 119, 6), width=1)
    d.text((M + 20, 542), "TOTAL SALDO PENDIENTE:", font=f_sm_bold, fill=RGB_BLACK)
    tot_sal = totales.get("total_saldo", 0)
    d.text((W_CARD - 120, 540), _fmt_money(tot_sal), font=f_h2, fill=RGB_RED if tot_sal > 0 else RGB_GREEN)

    # CARD 4: DOMÓTICA & QR (590 .. 750)
    d.rounded_rectangle([M, 590, W_CARD, 750], radius=12, fill=RGB_WHITE, outline=BORDER, width=2)
    d.text((M + 14, 602), "🏡  DOMÓTICA CASA", font=f_sm_bold, fill=RGB_BLACK)

    b_dy = 626
    for dev in devices[:4]:
        st = dev.get("status_text", "")
        st_low = st.lower()
        if any(w in st_low for w in ("encendida", "cerrado", "filtrando", "regando", "barriendo")):
            dc = RGB_GREEN if ("regando" in st_low or "filtrando" in st_low or "cerrado" in st_low) else RGB_ORANGE
        elif "°" in st_low:
            dc = RGB_BLUE
        else:
            dc = RGB_RED
        d.text((M + 14, b_dy), f"■ {dev['device_name'][:12]}:", font=f_bold, fill=RGB_BLACK)
        d.text((M + 130, b_dy), st[:18], font=f_reg, fill=dc)
        b_dy += 26

    # Divisor vertical QR
    d.line([(340, 600), (340, 740)], fill=(230, 230, 230), width=1)
    _draw_qr_to_image(img, 360, 615, size=75, border=1)
    d.text((364, 705), "ESCANEAR HUB", font=f_sm_bold, fill=RGB_BLACK)
    d.text((372, 722), "Panel Web", font=f_sm, fill=(120, 120, 120))

    # Footer telemetría
    d.text((M + 4, 768), "ESP32-C6 • LiPo 4.02V (88%) • Wi-Fi -60 dBm", font=f_sm, fill=(100, 100, 100))
    d.text((W_CARD - 70, 768), "Tokyo VPS ✓", font=f_sm_bold, fill=RGB_GREEN)

    return _pil_to_acep_canvas(img)
