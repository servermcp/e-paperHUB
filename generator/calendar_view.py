import calendar
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

import sys
sys.path.append('/root/epaper-hub')
import config
from integrations.google_cal import load_gcal_config
import requests

FONT_PATH = config.BASE_DIR / 'static' / 'fonts' / 'PatrickHand-Regular.ttf'

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]
DIAS_SEMANA = ["Dom", "Lun", "Mar", "Mie", "Jue", "Vie", "Sab"]

def get_font(size: int):
    if FONT_PATH.exists():
        try:
            return ImageFont.truetype(str(FONT_PATH), size=size)
        except Exception:
            pass
    return ImageFont.load_default()

def draw_text_pillow(draw, cx, cy, text, font, fill_color, align="center"):
    # Render with Pillow Draw
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    if align == "center":
        x = cx - w // 2 - bbox[0]
        y = cy - h // 2 - bbox[1]
    elif align == "right":
        x = cx - w - bbox[0]
        y = cy - bbox[1]
    else:
        x = cx - bbox[0]
        y = cy - bbox[1]
    draw.text((x, y), text, font=font, fill=fill_color)

def render_monthly_calendar_canvas():
    from generator.layout import AcepCanvas, PORTRAIT_W, PORTRAIT_H

    # Create RGB image in PIL, draw crisp vectors/fonts, then map to AcepCanvas
    img = Image.new("RGB", (PORTRAIT_W, PORTRAIT_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    now = datetime.now()
    year = now.year
    month_idx = now.month - 1
    today = now.day

    font_title = get_font(56)
    font_year = get_font(30)
    font_day_hdr = get_font(26)
    font_num = get_font(34)
    font_footer = get_font(22)
    font_ev = get_font(20)

    # 1. Cabecera (Año y Mes)
    draw_text_pillow(draw, PORTRAIT_W // 2, 42, str(year), font_year, (0, 0, 0), align="center")
    draw_text_pillow(draw, PORTRAIT_W // 2, 98, MESES_ES[month_idx], font_title, (0, 0, 0), align="center")

    # Línea superior de días de semana (3 px)
    draw.line((35, 138, PORTRAIT_W - 35, 138), fill=(0, 0, 0), width=3)

    # 2. Encabezados de días: Dom (Rojo), Lun a Sab (Negro)
    margen_x = 35
    ancho_util = PORTRAIT_W - (margen_x * 2)
    ancho_col = ancho_util // 7
    y_hdr = 168

    for c in range(7):
        cx = margen_x + c * ancho_col + (ancho_col // 2)
        col_rgb = (220, 20, 20) if c == 0 else (0, 0, 0)
        draw_text_pillow(draw, cx, y_hdr, DIAS_SEMANA[c], font_day_hdr, col_rgb, align="center")

    # Línea inferior de días de semana (3 px)
    draw.line((35, 198, PORTRAIT_W - 35, 198), fill=(0, 0, 0), width=3)

    # 3. Días del mes
    first_weekday, num_days = calendar.monthrange(year, now.month)
    start_col = (first_weekday + 1) % 7 # 0 = Domingo

    # Buscar eventos del calendario Google
    events_by_day = {}
    try:
        cfg = load_gcal_config()
        ical_url = cfg.get("ical_url", "")
        if ical_url:
            r = requests.get(ical_url, timeout=5)
            if r.status_code == 200:
                for blk in r.text.split("BEGIN:VEVENT")[1:]:
                    end_i = blk.find("END:VEVENT")
                    if end_i != -1:
                        blk = blk[:end_i]
                    d_ev = None
                    s_ev = "Evento"
                    for line in blk.splitlines():
                        if line.startswith("DTSTART"):
                            parts = line.split(":", 1)
                            if len(parts) == 2 and len(parts[1].strip()) >= 8:
                                raw = parts[1].strip()
                                if int(raw[:4]) == year and int(raw[4:6]) == now.month:
                                    d_ev = int(raw[6:8])
                        elif line.startswith("SUMMARY:"):
                            s_ev = line.split(":", 1)[1].strip().replace("\\,", ",")
                    if d_ev:
                        events_by_day.setdefault(d_ev, []).append(s_ev)
    except Exception as e:
        print("Cal error:", e)

    y_row_start = 248
    row_height = 68
    cur_col = start_col
    cur_row = 0

    for d in range(1, num_days + 1):
        cx = margen_x + cur_col * ancho_col + (ancho_col // 2)
        cy = y_row_start + cur_row * row_height

        is_sunday = (cur_col == 0)
        is_today = (d == today)

        if is_today:
            # Círculo doodle rojo grueso (varios círculos concéntricos para estilo tiza/marcador)
            draw.ellipse((cx - 24, cy - 20, cx + 24, cy + 28), outline=(220, 20, 20), width=3)
            draw_text_pillow(draw, cx, cy, str(d), font_num, (220, 20, 20), align="center")
        else:
            num_col = (220, 20, 20) if is_sunday else (0, 0, 0)
            draw_text_pillow(draw, cx, cy, str(d), font_num, num_col, align="center")

        # Indicador de eventos en el día
        if d in events_by_day:
            draw.ellipse((cx - 4, cy + 24, cx + 4, cy + 32), fill=(0, 70, 220))

        cur_col += 1
        if cur_col > 6:
            cur_col = 0
            cur_row += 1

    # Línea punteada divisoria inferior
    y_div_foot = max(y_row_start + (cur_row + 1) * row_height + 10, 660)
    for x in range(35, PORTRAIT_W - 35, 10):
        draw.line((x, y_div_foot, min(x + 5, PORTRAIT_W - 35), y_div_foot), fill=(0, 0, 0), width=2)

    # Pie de página: Agenda o Frase
    if events_by_day:
        draw_text_pillow(draw, 35, y_div_foot + 18, "AGENDA DEL MES:", font_footer, (0, 70, 220), align="left")
        ev_y = y_div_foot + 46
        shown = 0
        for d in sorted(events_by_day.keys()):
            for ev_title in events_by_day[d]:
                if shown < 3:
                    draw_text_pillow(draw, 35, ev_y, f"• Día {d:02d}: {ev_title[:38]}", font_ev, (0, 0, 0), align="left")
                    ev_y += 24
                    shown += 1
    else:
        draw_text_pillow(draw, PORTRAIT_W // 2, 705, "- Everyday is a fresh beginning! -", font_footer, (0, 0, 0), align="center")
        draw_text_pillow(draw, PORTRAIT_W // 2, 742, "CASA GATURRAKAS • EPAPER CALENDAR", font_footer, (0, 70, 220), align="center")

    # Mapear imagen RGB limpia a matriz ACeP (0..6)
    canvas = AcepCanvas(width=PORTRAIT_W, height=PORTRAIT_H)
    arr = np.array(img)
    # Color mapping directo sin grises difusos para texto ultra-nítido:
    # Si es rojo (R > 180, G < 60, B < 60) -> 0x4 (Rojo)
    # Si es azul (B > 180, R < 60) -> 0x3 (Azul)
    # Si es oscuro (R < 100, G < 100, B < 100) -> 0x0 (Negro)
    # Resto -> 0x1 (Blanco)
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]

    is_red = (r > 150) & (g < 80) & (b < 80)
    is_blue = (b > 150) & (r < 80)
    is_black = (r < 110) & (g < 110) & (b < 110)

    canvas.matrix[is_black] = config.ACEP_COLOR_BLACK
    canvas.matrix[is_red] = config.ACEP_COLOR_RED
    canvas.matrix[is_blue] = config.ACEP_COLOR_BLUE

    return canvas
