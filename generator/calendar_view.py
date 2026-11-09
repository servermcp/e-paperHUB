"""
generator/calendar_view.py — Calendario Mensual Estilo Minimalista Japonés / Muji para E-Paper ACeP 7 Colores.

Inspirado en el diseño limpio de papel digital:
- Fondo blanco puro.
- Cabecera: Año (izq), Número Gigante de Mes (centro), Hora actual (der).
- Días de la semana: S (Rojo), M T W T F (Negro), S (Azul).
- Grilla: Domingos en rojo, Sábados en azul, Feriados nacionales en rojo.
- Día actual ("HOY"): Placa circular roja sólida con número blanco invertido.
- Días del mes previo/posterior: Desvanecidos en gris claro (trama checkerboard 50% para tinta electrónica).
- Eventos:
  - Eventos de varios días: Barras horizontales continuas con puntas redondeadas que cruzan las columnas y se adaptan a las semanas.
  - Eventos de un solo día: Pastillas redondeadas bajo el número con título del evento centrado debajo.
  - Paleta ACeP 7 colores (Negro, Blanco, Verde, Azul, Rojo, Amarillo, Naranja).
"""

from __future__ import annotations

import calendar
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import urllib.request

import config
from integrations.google_cal import load_gcal_config

# Rutas de tipografías TrueType
FONTS_DIR = config.BASE_DIR / "static" / "fonts"
FONT_BOLD_PATH = FONTS_DIR / "Roboto-Bold.ttf"
FONT_MED_PATH = FONTS_DIR / "Roboto-Medium.ttf"
FONT_REG_PATH = FONTS_DIR / "Roboto-Regular.ttf"

# Feriados nacionales fijos de Argentina (Mes, Día) -> Nombre
ARG_HOLIDAYS_FIXED: Dict[Tuple[int, int], str] = {
    (1, 1): "Año Nuevo",
    (3, 24): "Memoria y Justicia",
    (4, 2): "Vet. de Malvinas",
    (5, 1): "Día del Trabajador",
    (5, 25): "Revolución de Mayo",
    (6, 20): "Día de la Bandera",
    (7, 9): "Independencia",
    (8, 17): "Gral. San Martín",
    (10, 12): "Diversidad Cultural",
    (11, 20): "Soberanía Nac.",
    (12, 8): "Inmaculada Concepción",
    (12, 25): "Navidad",
}

# Paleta ACeP 7-Color RGB de referencia para renderizado
COLOR_RGB_BLACK = (25, 25, 25)
COLOR_RGB_WHITE = (255, 255, 255)
COLOR_RGB_GREEN = (140, 195, 30)   # Verde / Lima vivo
COLOR_RGB_BLUE = (0, 135, 215)     # Azul / Cyan Muji
COLOR_RGB_RED = (215, 30, 40)      # Rojo coral e-paper
COLOR_RGB_YELLOW = (224, 198, 48)  # Amarillo suave
COLOR_RGB_ORANGE = (220, 110, 30)  # Naranja teja

# Cache en memoria de eventos mensuales
_MONTH_EVENTS_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "key": "",
    "events": [],
}
_CACHE_TTL_SEC = 300


def _get_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_pill(draw: ImageDraw.ImageDraw, x0: float, y0: float, x1: float, y1: float, fill: Tuple[int, int, int]) -> None:
    """Dibuja una barra o pastilla horizontal con puntas redondeadas (cápsula)."""
    h = y1 - y0
    r = max(2, int(h // 2))
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill)


def _categorize_event_color(summary: str) -> Tuple[int, int, int]:
    """Asigna un color ACeP según las palabras clave del evento o categoría."""
    s = summary.lower()
    # Viajes, vacaciones, escapadas, playa -> Verde
    if any(k in s for k in ("viaje", "vacacion", "mardel", "escapada", "vuelo", "hotel", "trip", "playa", "salida")):
        return COLOR_RGB_GREEN
    # Cumpleaños, aniversarios, fiestas, feriados, urgente -> Rojo
    if any(k in s for k in ("cumple", "aniversario", "boda", "fiesta", "feriado", "urgente", "alerta")):
        return COLOR_RGB_RED
    # Turnos médicos, trabajo, reuniones, citas -> Azul
    if any(k in s for k in ("turno", "médic", "medico", "dentista", "doctor", "cita", "reunion", "reunión", "meet", "zoom", "trabajo")):
        return COLOR_RGB_BLUE
    # Pagos, vencimientos, finanzas, facturas -> Naranja
    if any(k in s for k in ("pago", "vto", "vencimiento", "tarjeta", "factura", "afip", "banco", "alquiler", "expensas")):
        return COLOR_RGB_ORANGE

    # Color predeterminado según hash del título para consistencia visual
    palette_options = [COLOR_RGB_GREEN, COLOR_RGB_RED, COLOR_RGB_BLUE, COLOR_RGB_ORANGE]
    return palette_options[abs(hash(summary)) % len(palette_options)]


def _parse_ical_date(raw_val: str) -> Optional[datetime]:
    """Convierte cadenas DTSTART/DTEND de iCal (ej. 20261105T153000Z o 20261105) a datetime local."""
    val = raw_val.strip()
    if not val:
        return None
    try:
        if "T" in val:
            clean = val.rstrip("Z")[:15]
            dt = datetime.strptime(clean, "%Y%m%dT%H%M%S")
            if val.endswith("Z"):
                # Convertir UTC a hora de Argentina (UTC-3)
                tz_arg = timezone(timedelta(hours=-3))
                dt = dt.replace(tzinfo=timezone.utc).astimezone(tz_arg).replace(tzinfo=None)
            return dt
        else:
            return datetime.strptime(val[:8], "%Y%m%d")
    except Exception:
        return None


def fetch_monthly_events(year: int, month: int, visible_start: date, visible_end: date) -> List[Dict[str, Any]]:
    """
    Obtiene los eventos del mes desde Google Calendar (iCal) y los feriados nacionales.
    Filtra los eventos que se superponen con el rango visible en la grilla.
    """
    import time
    now_ts = time.time()
    cache_key = f"{year}-{month}"

    events_list: List[Dict[str, Any]] = []

    # Verificar cache
    if (
        _MONTH_EVENTS_CACHE["key"] == cache_key
        and (now_ts - _MONTH_EVENTS_CACHE["timestamp"]) < _CACHE_TTL_SEC
    ):
        raw_events = _MONTH_EVENTS_CACHE["events"]
    else:
        raw_events = []
        try:
            cfg = load_gcal_config()
            ical_url = cfg.get("ical_url", "").strip()
            if ical_url:
                req = urllib.request.Request(ical_url, headers={"User-Agent": "e-paperHUB/1.1"})
                with urllib.request.urlopen(req, timeout=7.0) as resp:
                    ics_text = resp.read().decode("utf-8", errors="ignore")
                blocks = ics_text.split("BEGIN:VEVENT")[1:]
                for blk in blocks:
                    end_i = blk.find("END:VEVENT")
                    if end_i != -1:
                        blk = blk[:end_i]
                    unfolded = re.sub(r"\r?\n[ \t]", "", blk)

                    dt_start_raw = ""
                    dt_end_raw = ""
                    summary_raw = "Evento"

                    for line in unfolded.splitlines():
                        if line.startswith("DTSTART"):
                            parts = line.split(":", 1)
                            if len(parts) == 2:
                                dt_start_raw = parts[1].strip()
                        elif line.startswith("DTEND"):
                            parts = line.split(":", 1)
                            if len(parts) == 2:
                                dt_end_raw = parts[1].strip()
                        elif line.startswith("SUMMARY"):
                            parts = line.split(":", 1)
                            if len(parts) == 2:
                                summary_raw = parts[1].strip().replace("\\,", ",").replace("\\;", ";")

                    if not dt_start_raw:
                        continue

                    dt_start = _parse_ical_date(dt_start_raw)
                    if not dt_start:
                        continue

                    dt_end = _parse_ical_date(dt_end_raw) if dt_end_raw else dt_start
                    if not dt_end:
                        dt_end = dt_start

                    d_start = dt_start.date()
                    d_end = dt_end.date()

                    # En iCal, los eventos de día completo suelen tener DTEND exclusivo
                    if "T" not in dt_start_raw and "T" not in dt_end_raw and d_end > d_start:
                        d_end = d_end - timedelta(days=1)
                    elif "T" in dt_start_raw and d_end > d_start and dt_end.time() == datetime.min.time():
                        d_end = d_end - timedelta(days=1)

                    if d_end < d_start:
                        d_end = d_start

                    raw_events.append({
                        "start": d_start,
                        "end": d_end,
                        "title": summary_raw,
                        "color": _categorize_event_color(summary_raw),
                        "is_holiday": False,
                    })

                _MONTH_EVENTS_CACHE["key"] = cache_key
                _MONTH_EVENTS_CACHE["timestamp"] = now_ts
                _MONTH_EVENTS_CACHE["events"] = raw_events
        except Exception as e:
            print(f"[Calendar] Error obteniendo iCal: {e}")

    # Agregar feriados nacionales de Argentina en el rango visible
    cur_d = visible_start
    while cur_d <= visible_end:
        key = (cur_d.month, cur_d.day)
        if key in ARG_HOLIDAYS_FIXED:
            h_title = ARG_HOLIDAYS_FIXED[key]
            # Solo agregar si no existe ya un evento con nombre similar
            if not any(ev["start"] == cur_d and h_title.lower() in ev["title"].lower() for ev in raw_events):
                raw_events.append({
                    "start": cur_d,
                    "end": cur_d,
                    "title": h_title,
                    "color": COLOR_RGB_RED,
                    "is_holiday": True,
                })
        cur_d += timedelta(days=1)

    # Filtrar solo los que se intersectan con la grilla visible
    for ev in raw_events:
        if ev["end"] >= visible_start and ev["start"] <= visible_end:
            events_list.append(ev)

    # Ordenar: eventos multi-día primero, luego por fecha de inicio
    events_list.sort(key=lambda x: (0 if x["end"] > x["start"] else 1, x["start"]))
    return events_list


def render_monthly_calendar_canvas():
    """
    Renderiza el calendario mensual minimalista estilo Muji/Japonés en 480x800 vertical.
    Retorna una instancia de AcepCanvas lista para enviar a la pantalla o guardar como preview.
    """
    from generator.layout import AcepCanvas, PORTRAIT_W, PORTRAIT_H

    # Imagen RGB base en blanco puro
    img = Image.new("RGB", (PORTRAIT_W, PORTRAIT_H), COLOR_RGB_WHITE)
    draw = ImageDraw.Draw(img)

    # Cargar fuentes
    font_month = _get_font(FONT_BOLD_PATH, 88)
    font_header = _get_font(FONT_MED_PATH, 24)
    font_weekdays = _get_font(FONT_BOLD_PATH, 30)
    font_days = _get_font(FONT_MED_PATH, 32)
    font_today = _get_font(FONT_BOLD_PATH, 30)
    font_event = _get_font(FONT_REG_PATH, 10)

    # Fecha y hora actual (hora de Buenos Aires si está disponible)
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    except Exception:
        now = datetime.now()

    year = now.year
    month = now.month
    current_day = now.day
    time_str = now.strftime("%H:%M")

    # 1. Cabecera superior: Año (izq), Mes (centro gigante), Hora (der)
    draw.text((38, 48), str(year), font=font_header, fill=COLOR_RGB_BLACK)

    tb_time = draw.textbbox((0, 0), time_str, font=font_header)
    w_time = tb_time[2] - tb_time[0]
    draw.text((PORTRAIT_W - 38 - w_time, 48), time_str, font=font_header, fill=COLOR_RGB_BLACK)

    m_str = str(month)
    tb_m = draw.textbbox((0, 0), m_str, font=font_month)
    w_m = tb_m[2] - tb_m[0]
    draw.text(((PORTRAIT_W - w_m) // 2 - tb_m[0], 25 - tb_m[1]), m_str, font=font_month, fill=COLOR_RGB_BLACK)

    # 2. Encabezados de días: S M T W T F S
    margin_x = 28
    grid_w = PORTRAIT_W - margin_x * 2
    col_w = grid_w / 7.0

    weekday_letters = ["S", "M", "T", "W", "T", "F", "S"]
    weekday_colors = [
        COLOR_RGB_RED,    # Domingo: Rojo
        COLOR_RGB_BLACK,  # Lunes: Negro
        COLOR_RGB_BLACK,  # Martes: Negro
        COLOR_RGB_BLACK,  # Miércoles: Negro
        COLOR_RGB_BLACK,  # Jueves: Negro
        COLOR_RGB_BLACK,  # Viernes: Negro
        COLOR_RGB_BLUE,   # Sábado: Azul
    ]

    y_weekday = 155
    for c in range(7):
        cx = margin_x + (c + 0.5) * col_w
        let = weekday_letters[c]
        col = weekday_colors[c]
        tb = draw.textbbox((0, 0), let, font=font_weekdays)
        w = tb[2] - tb[0]
        h = tb[3] - tb[1]
        draw.text((cx - w / 2 - tb[0], y_weekday - h / 2 - tb[1]), let, font=font_weekdays, fill=col)

    # 3. Cálculo de la cuadrícula mensual
    first_weekday, num_days = calendar.monthrange(year, month)
    # Python: 0=Lunes, 6=Domingo. Convertimos para Domingo en col 0:
    start_col = (first_weekday + 1) % 7

    # Días del mes anterior para desborde superior
    prev_year = year if month > 1 else year - 1
    prev_month = month - 1 if month > 1 else 12
    _, num_days_prev = calendar.monthrange(prev_year, prev_month)

    total_cells = start_col + num_days
    num_rows = max(5, (total_cells + 6) // 7)

    y_grid_top = 210
    y_grid_bot = 770
    row_h = (y_grid_bot - y_grid_top) / float(num_rows)

    cells: Dict[Tuple[int, int], Tuple[int, bool, bool, bool, date]] = {}
    day_positions: Dict[date, Tuple[int, int]] = {}

    # Desborde de mes anterior
    first_visible_date = None
    for i in range(start_col):
        d = num_days_prev - start_col + 1 + i
        r = 0
        c = i
        dt = date(prev_year, prev_month, d)
        cells[(r, c)] = (d, False, True, False, dt)
        day_positions[dt] = (r, c)
        if first_visible_date is None:
            first_visible_date = dt

    if first_visible_date is None:
        first_visible_date = date(year, month, 1)

    # Días del mes actual
    for d in range(1, num_days + 1):
        idx = start_col + d - 1
        r = idx // 7
        c = idx % 7
        dt = date(year, month, d)
        cells[(r, c)] = (d, True, False, False, dt)
        day_positions[dt] = (r, c)

    # Desborde de mes posterior
    next_year = year if month < 12 else year + 1
    next_month = month + 1 if month < 12 else 1
    d_next = 1
    last_visible_date = None
    for idx in range(total_cells, num_rows * 7):
        r = idx // 7
        c = idx % 7
        dt = date(next_year, next_month, d_next)
        cells[(r, c)] = (d_next, False, False, True, dt)
        day_positions[dt] = (r, c)
        last_visible_date = dt
        d_next += 1

    if last_visible_date is None:
        last_visible_date = date(year, month, num_days)

    # Obtener eventos del rango visible
    events = fetch_monthly_events(year, month, first_visible_date, last_visible_date)

    # Diccionario de feriados para marcar los números de día en rojo
    holidays_by_date = {ev["start"]: ev["title"] for ev in events if ev.get("is_holiday")}

    # 4. Dibujar números de los días
    grey_mask = Image.new("1", (PORTRAIT_W, PORTRAIT_H), 0)
    draw_grey = ImageDraw.Draw(grey_mask)

    for (r, c), (d, is_cur, is_prev, is_next, dt) in cells.items():
        cx = margin_x + (c + 0.5) * col_w
        cy = y_grid_top + r * row_h + 24

        is_today = (is_cur and d == current_day)
        is_holiday = (dt in holidays_by_date)

        if is_today:
            # Placa circular roja sólida con número blanco invertido
            rad = 22
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=COLOR_RGB_RED)
            d_str = str(d)
            tb = draw.textbbox((0, 0), d_str, font=font_today)
            w = tb[2] - tb[0]
            h = tb[3] - tb[1]
            draw.text((cx - w / 2 - tb[0], cy - h / 2 - tb[1]), d_str, font=font_today, fill=COLOR_RGB_WHITE)
        elif is_cur:
            # Domingo o Feriado -> Rojo; Sábado -> Azul; Días de semana -> Negro
            if c == 0 or is_holiday:
                col = COLOR_RGB_RED
            elif c == 6:
                col = COLOR_RGB_BLUE
            else:
                col = COLOR_RGB_BLACK

            d_str = str(d)
            tb = draw.textbbox((0, 0), d_str, font=font_days)
            w = tb[2] - tb[0]
            h = tb[3] - tb[1]
            draw.text((cx - w / 2 - tb[0], cy - h / 2 - tb[1]), d_str, font=font_days, fill=col)
        else:
            # Días de desborde del mes previo o siguiente: dibujamos en máscara para tramado 50%
            d_str = str(d)
            tb = draw.textbbox((0, 0), d_str, font=font_days)
            w = tb[2] - tb[0]
            h = tb[3] - tb[1]
            draw_grey.text((cx - w / 2 - tb[0], cy - h / 2 - tb[1]), d_str, font=font_days, fill=1)

    # 5. Renderizado de líneas / barras de eventos
    # Máximo 2 eventos representados por día para evitar amontonamiento
    day_event_slots: Dict[date, int] = {}

    for ev in events:
        ev_start = ev["start"]
        ev_end = ev["end"]
        ev_title = ev["title"]
        ev_color = ev.get("color", COLOR_RGB_GREEN)

        cur_dt = max(ev_start, first_visible_date)
        max_dt = min(ev_end, last_visible_date)

        while cur_dt <= max_dt:
            if cur_dt not in day_positions:
                cur_dt += timedelta(days=1)
                continue

            r, c_start = day_positions[cur_dt]
            slot = day_event_slots.get(cur_dt, 0)
            if slot >= 2:
                cur_dt += timedelta(days=1)
                continue

            # Buscar extensión continua en la misma fila de la semana
            c_end = c_start
            row_last_dt = cur_dt
            next_test = cur_dt + timedelta(days=1)
            while next_test <= max_dt and next_test in day_positions:
                r_next, c_next = day_positions[next_test]
                if r_next == r:
                    c_end = c_next
                    row_last_dt = next_test
                    next_test += timedelta(days=1)
                else:
                    break

            # Altura del slot de evento
            slot_offset = slot * 20
            y_bar = y_grid_top + r * row_h + 49 + slot_offset
            bar_h = 6

            is_multi = (ev_end > ev_start)
            if is_multi:
                # Barra horizontal continua que cruza las columnas
                x0 = margin_x + c_start * col_w + 4
                x1 = margin_x + (c_end + 1) * col_w - 4
            else:
                # Pastilla redondeada centrada bajo el día
                cx = margin_x + (c_start + 0.5) * col_w
                pill_w = col_w * 0.60
                x0 = cx - pill_w / 2
                x1 = cx + pill_w / 2

            _draw_pill(draw, x0, y_bar, x1, y_bar + bar_h, fill=ev_color)

            # Título del evento bajo la barra
            y_txt = y_bar + bar_h + 2
            max_txt_w = max(col_w * (c_end - c_start + 1) + 12, col_w + 12)

            disp_title = ev_title
            while disp_title:
                tb = draw.textbbox((0, 0), disp_title, font=font_event)
                tw = tb[2] - tb[0]
                if tw <= max_txt_w:
                    break
                disp_title = disp_title[:-2] + "…"

            tb = draw.textbbox((0, 0), disp_title, font=font_event)
            tw = tb[2] - tb[0]
            tx = (x0 + x1) / 2 - tw / 2 - tb[0]
            tx = max(margin_x + 2, min(PORTRAIT_W - margin_x - tw - 2, tx))
            draw.text((tx, y_txt), disp_title, font=font_event, fill=COLOR_RGB_BLACK)

            # Registrar slots ocupados para estos días
            d_mark = cur_dt
            while d_mark <= row_last_dt:
                day_event_slots[d_mark] = day_event_slots.get(d_mark, 0) + 1
                d_mark += timedelta(days=1)

            cur_dt = row_last_dt + timedelta(days=1)

    # 6. Aplicar trama Bayer checkerboard 50% para desvanecer números del mes previo/siguiente
    img_arr = np.array(img)
    grey_arr = np.array(grey_mask)
    yy, xx = np.indices((PORTRAIT_H, PORTRAIT_W))
    checker = ((xx + yy) % 2 == 0)
    to_black = (grey_arr == 1) & checker
    img_arr[to_black] = [30, 30, 30]

    # 7. Mapeo directo y ultra-nítido a la matriz de hardware ACeP 7 Colores (0x0 .. 0x6)
    canvas = AcepCanvas(width=PORTRAIT_W, height=PORTRAIT_H)

    r_ch = img_arr[:, :, 0]
    g_ch = img_arr[:, :, 1]
    b_ch = img_arr[:, :, 2]

    # Clasificación precisa por umbrales RGB puros
    is_black = (r_ch < 80) & (g_ch < 80) & (b_ch < 80)
    is_red = (r_ch > 160) & (g_ch < 80) & (b_ch < 80)
    is_blue = (b_ch > 160) & (r_ch < 80)
    is_green = (g_ch > 140) & (b_ch < 90) & (r_ch < 180)
    is_orange = (r_ch > 180) & (g_ch >= 70) & (g_ch <= 150) & (b_ch < 70)
    is_yellow = (r_ch > 180) & (g_ch > 160) & (b_ch < 90)

    # Por defecto todo es blanco (0x1)
    canvas.matrix.fill(config.ACEP_COLOR_WHITE)
    canvas.matrix[is_black] = config.ACEP_COLOR_BLACK
    canvas.matrix[is_red] = config.ACEP_COLOR_RED
    canvas.matrix[is_blue] = config.ACEP_COLOR_BLUE
    canvas.matrix[is_green] = config.ACEP_COLOR_GREEN
    canvas.matrix[is_orange] = config.ACEP_COLOR_ORANGE
    canvas.matrix[is_yellow] = config.ACEP_COLOR_YELLOW

    return canvas
