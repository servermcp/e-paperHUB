"""
generator/layout.py — Compositor gráfico Vertical (480x800 px) con Tabla de Tarjetas y Servicios:
  [Logo Empresa] [Logo Gasto]  |   TOTAL   |   MÍNIMO   |   SALDO
"""

from __future__ import annotations

import os
import socket
import time
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
from generator.dither import dither_image_acep, apply_acep_tone_mapping
from generator.packer import render_preview_from_hw_indices, save_packed_bin
from generator.weather import fetch_weather
from generator.calendar_view import render_monthly_calendar_canvas

PORTRAIT_W = 480
PORTRAIT_H = 800
LOGOS_DIR = config.ICONS_DIR / "logos"

_DAYS_ES = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
_MONTHS_ES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

_FONT_CANDIDATES_BOLD = [
    str(config.FONTS_DIR / "Inter-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
]

_FONT_CANDIDATES_MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]


def load_font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _FONT_CANDIDATES_MONO if (mono or size < 14) else _FONT_CANDIDATES_BOLD
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


class AcepCanvas:
    def __init__(
        self,
        base_hw_indices: Optional[np.ndarray] = None,
        width: int = PORTRAIT_W,
        height: int = PORTRAIT_H,
    ) -> None:
        if base_hw_indices is not None:
            self.matrix = np.array(base_hw_indices, dtype=np.uint8, copy=True)
            self.height, self.width = self.matrix.shape
        else:
            self.width = int(width)
            self.height = int(height)
            self.matrix = np.full(
                (self.height, self.width),
                config.ACEP_COLOR_WHITE,
                dtype=np.uint8,
            )

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, hw_color: int) -> None:
        x0_c = max(0, min(self.width, int(x0)))
        x1_c = max(0, min(self.width, int(x1)))
        y0_c = max(0, min(self.height, int(y0)))
        y1_c = max(0, min(self.height, int(y1)))
        if x1_c > x0_c and y1_c > y1_c:
            pass
        if x1_c > x0_c and y1_c > y0_c:
            self.matrix[y0_c:y1_c, x0_c:x1_c] = np.uint8(hw_color)

    def stroke_rect(
        self, x0: int, y0: int, x1: int, y1: int, hw_color: int, thickness: int = 2
    ) -> None:
        t = max(1, int(thickness))
        self.fill_rect(x0, y0, x1, y0 + t, hw_color)
        self.fill_rect(x0, y1 - t, x1, y1, hw_color)
        self.fill_rect(x0, y0, x0 + t, y1, hw_color)
        self.fill_rect(x1 - t, y0, x1, y1, hw_color)

    def draw_divider(self, y: int, x0: int = 20, x1: int = 460, thickness: int = 2, dashed: bool = False) -> None:
        if not dashed:
            self.fill_rect(x0, y, x1, y + thickness, config.ACEP_COLOR_BLACK)
        else:
            for x in range(x0, x1, 8):
                self.fill_rect(x, y, min(x + 4, x1), y + thickness, config.ACEP_COLOR_BLACK)

    def stamp_logo_icon(self, x: int, y: int, logo_name: str) -> None:
        """
        Estampa un icono de marca pre-calibrado de 32x32 píxeles en 7 colores ACeP
        (`static/icons/logos/<logo_name>.npy`) directamente en la matriz de índices.
        """
        npy_path = LOGOS_DIR / f"{logo_name.lower().strip()}.npy"
        if not npy_path.exists():
            self.stroke_rect(x, y, x + 32, y + 32, config.ACEP_COLOR_BLACK, thickness=2)
            self.draw_text_1bit(x + 4, y + 8, logo_name[:3].upper(), config.ACEP_COLOR_BLACK, font_size=12, mono=True)
            return

        icon_mat = np.load(npy_path)
        ih, iw = icon_mat.shape
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, x0 + iw)
        y1 = min(self.height, y0 + ih)
        if x1 > x0 and y1 > y0:
            self.matrix[y0:y1, x0:x1] = icon_mat[:(y1 - y0), :(x1 - x0)]

    def draw_text_1bit(
        self,
        x: int,
        y: int,
        text: str,
        hw_color: int = config.ACEP_COLOR_BLACK,
        font_size: int = 18,
        mono: bool = False,
        max_width: Optional[int] = None,
        align_right_x: Optional[int] = None,
    ) -> Tuple[int, int]:
        if not text:
            return (0, 0)

        font = load_font(font_size, mono=mono)
        render_str = str(text)
        if max_width is not None and max_width > 20:
            while len(render_str) > 3:
                bbox = font.getbbox(render_str)
                w = bbox[2] - bbox[0]
                if w <= max_width:
                    break
                render_str = render_str[:-2] + "…"

        bbox = font.getbbox(render_str)
        w = max(1, (bbox[2] - bbox[0]) + 4)
        h = max(1, (bbox[3] - bbox[1]) + 6)

        mask_img = Image.new("1", (w, h), 0)
        draw = ImageDraw.Draw(mask_img)
        draw.text((-bbox[0] + 1, -bbox[1] + 1), render_str, fill=1, font=font)

        draw_x = (align_right_x - w) if align_right_x is not None else x
        mask_arr = np.asarray(mask_img, dtype=bool)
        self._stamp_binary_mask(draw_x, y, mask_arr, hw_color)
        return (w, h)

    def _stamp_binary_mask(
        self, x: int, y: int, mask_arr: np.ndarray, hw_color: int
    ) -> None:
        mh, mw = mask_arr.shape
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, int(x) + mw)
        y1 = min(self.height, int(y) + mh)
        if x1 <= x0 or y1 <= y0:
            return

        sub_mask = mask_arr[(y0 - int(y)):(y1 - int(y)), (x0 - int(x)):(x1 - int(x))]
        region = self.matrix[y0:y1, x0:x1]
        region[sub_mask] = np.uint8(hw_color)

    def draw_weather_icon(
        self,
        x: int,
        y: int,
        icon_name: str,
        size: int = 72,
    ) -> bool:
        icon_file = config.BASE_DIR / "static" / "icons" / "weather_acep" / f"{icon_name}_{size}.npy"
        if icon_file.exists():
            try:
                data = np.load(icon_file, allow_pickle=True).item()
                indices = data["indices"]
                mask = data["mask"]

                x0 = max(0, int(x))
                y0 = max(0, int(y))
                x1 = min(self.width, x0 + size)
                y1 = min(self.height, y0 + size)

                if x1 > x0 and y1 > y0:
                    sub_ind = indices[0:(y1 - y0), 0:(x1 - x0)]
                    sub_mask = mask[0:(y1 - y0), 0:(x1 - x0)]
                    region = self.matrix[y0:y1, x0:x1]
                    region[sub_mask] = sub_ind[sub_mask]
                    return True
            except Exception:
                pass
        return False

    def draw_vector_icon(
        self,
        x: int,
        y: int,
        icon_name: str,
        size: int = 36,
        hw_color: int = config.ACEP_COLOR_BLACK,
    ) -> None:
        mask_img = Image.new("1", (size, size), 0)
        d = ImageDraw.Draw(mask_img)
        lw = max(2, size // 11)
        pad = max(3, size // 8)

        name = icon_name.lower()
        if name == "sun":
            c = size // 2
            r = size // 4
            d.ellipse((c - r, c - r, c + r, c + r), outline=1, width=lw)
            for angle_deg in range(0, 360, 45):
                rad = np.deg2rad(angle_deg)
                r1 = r + 4
                r2 = size // 2 - 2
                d.line(
                    (
                        c + int(np.cos(rad) * r1),
                        c + int(np.sin(rad) * r1),
                        c + int(np.cos(rad) * r2),
                        c + int(np.sin(rad) * r2),
                    ),
                    fill=1,
                    width=lw,
                )
        elif name in ("cloud", "cloud-sun", "cloud-rain", "cloud-lightning"):
            y_base = int(size * 0.65)
            d.rounded_rectangle(
                (pad, int(size * 0.38), size - pad, y_base),
                radius=size // 6,
                outline=1,
                width=lw,
            )
            d.arc(
                (int(size * 0.25), int(size * 0.18), int(size * 0.68), int(size * 0.58)),
                start=180,
                end=0,
                fill=1,
                width=lw,
            )
            if "rain" in name:
                for rx in (int(size * 0.32), int(size * 0.50), int(size * 0.68)):
                    d.line((rx, y_base + 3, rx - 3, size - 3), fill=1, width=lw)
            elif "lightning" in name:
                cx = size // 2
                d.line((cx + 2, y_base + 2, cx - 4, y_base + 8, cx + 3, y_base + 8, cx - 2, size - 2), fill=1, width=lw)
        elif name == "wifi":
            cx = size // 2
            by = size - pad - 2
            d.ellipse((cx - 2, by - 2, cx + 2, by + 2), fill=1)
            for rad_r in (size // 5, size // 3, int(size * 0.45)):
                d.arc((cx - rad_r, by - rad_r, cx + rad_r, by + rad_r), start=215, end=325, fill=1, width=lw)
        else:
            d.rounded_rectangle((pad, pad, size - pad, size - pad), radius=5, outline=1, width=lw)
            d.ellipse((size // 2 - 3, size // 2 - 3, size // 2 + 3, size // 2 + 3), fill=1)

        mask_arr = np.asarray(mask_img, dtype=bool)
        self._stamp_binary_mask(x, y, mask_arr, hw_color)

    def draw_qr_code(
        self,
        x: int,
        y: int,
        payload_text: str,
        box_size: int = 3,
        border: int = 1,
        fg_hw: int = config.ACEP_COLOR_BLACK,
        bg_hw: int = config.ACEP_COLOR_WHITE,
    ) -> Tuple[int, int]:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(payload_text)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")
        qr_arr = np.asarray(qr_img, dtype=bool)
        qh, qw = qr_arr.shape

        self.fill_rect(x, y, x + qw, y + qh, bg_hw)
        self._stamp_binary_mask(x, y, ~qr_arr, fg_hw)
        return (qw, qh)


def _fmt_money(val: float) -> str:
    v = round(float(val))
    if v <= 0:
        return "$0"
    return f"${v:,}".replace(",", ".")


# ==============================================================================
# MODO 1: DASHBOARD VERTICAL CON TABLA DE TARJETAS Y SERVICIOS (480 x 800 px)
# ==============================================================================

def render_dashboard_mode(
    calendar_events: Optional[List[Dict[str, str]]] = None,
    theme: Optional[str] = None,
) -> AcepCanvas:
    from generator.dashboard_themes import (
        render_dashboard_crayon,
        render_dashboard_muji,
        render_dashboard_bento,
    )
    selected_theme = (theme or database.get_dashboard_theme()).lower().strip()
    if selected_theme == "muji":
        return render_dashboard_muji(calendar_events=calendar_events)
    elif selected_theme == "bento":
        return render_dashboard_bento(calendar_events=calendar_events)
    else:
        return render_dashboard_crayon(calendar_events=calendar_events)


def render_photo_frame_mode(photo_path: Optional[Path] = None) -> AcepCanvas:
    target_photo: Optional[Path] = photo_path
    if target_photo is None:
        picked = database.pick_next_carousel_foto()
        if picked:
            candidate = config.UPLOADS_DIR / picked["nombre_archivo"]
            if candidate.exists():
                target_photo = candidate

    if target_photo is not None and target_photo.exists():
        src_img = Image.open(target_photo).convert("RGB")
    else:
        x = np.linspace(0, 255, PORTRAIT_W, dtype=np.uint8)
        y = np.linspace(0, 255, PORTRAIT_H, dtype=np.uint8)
        xv, yv = np.meshgrid(x, y)
        synth = np.stack([255 - yv // 4, xv // 2 + 60, yv // 4], axis=-1).astype(np.uint8)
        src_img = Image.fromarray(synth, mode="RGB")

    is_vertical = src_img.height >= src_img.width
    target_dims = (PORTRAIT_W, PORTRAIT_H) if is_vertical else (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)

    toned = apply_acep_tone_mapping(src_img, target_size=target_dims)
    dither_res = dither_image_acep(toned, algorithm="atkinson", apply_tone_map=False)
    canvas = AcepCanvas(base_hw_indices=dither_res["hw_indices"])

    now_str = datetime.now().strftime("%d/%m/%Y • %H:%M")
    if is_vertical:
        canvas.fill_rect(280, 756, 466, 788, config.ACEP_COLOR_WHITE)
        canvas.stroke_rect(280, 756, 466, 788, config.ACEP_COLOR_BLACK, thickness=2)
        canvas.draw_text_1bit(292, 764, now_str, config.ACEP_COLOR_BLACK, font_size=15, mono=True)
    else:
        canvas.fill_rect(598, 436, 786, 468, config.ACEP_COLOR_WHITE)
        canvas.stroke_rect(598, 436, 786, 468, config.ACEP_COLOR_BLACK, thickness=2)
        canvas.draw_text_1bit(610, 444, now_str, config.ACEP_COLOR_BLACK, font_size=15, mono=True)

    return canvas


def render_guest_wifi_mode() -> AcepCanvas:
    canvas = AcepCanvas(width=PORTRAIT_W, height=PORTRAIT_H)
    canvas.draw_text_1bit(20, 24, "CASA GATURRAKAS  •  WI-FI", config.ACEP_COLOR_BLUE, font_size=20)
    canvas.draw_divider(y=56, x0=20, x1=460, thickness=2)
    canvas.draw_text_1bit(20, 78, "Escaneá con tu cámara", config.ACEP_COLOR_BLACK, font_size=26)
    canvas.draw_text_1bit(20, 114, "para conectarte a la red de casa", config.ACEP_COLOR_GREEN, font_size=17)

    wifi_qr_payload = (
        f"WIFI:T:{config.GUEST_WIFI_AUTH};S:{config.GUEST_WIFI_SSID};P:{config.GUEST_WIFI_PASSWORD};;"
    )
    canvas.draw_qr_code(84, 168, wifi_qr_payload, box_size=8, border=2)
    canvas.draw_divider(y=520, x0=20, x1=460, thickness=2)
    canvas.draw_text_1bit(20, 548, "Red Wi-Fi (SSID):", config.ACEP_COLOR_BLACK, font_size=16)
    canvas.draw_text_1bit(20, 574, config.GUEST_WIFI_SSID, config.ACEP_COLOR_BLUE, font_size=26)
    canvas.draw_text_1bit(20, 628, "Contraseña:", config.ACEP_COLOR_BLACK, font_size=16)
    canvas.draw_text_1bit(20, 654, config.GUEST_WIFI_PASSWORD, config.ACEP_COLOR_RED, font_size=26, mono=True)
    canvas.draw_divider(y=720, x0=20, x1=460, thickness=1, dashed=True)
    canvas.draw_text_1bit(20, 742, "1 toque en el marco = Volver al Dashboard", config.ACEP_COLOR_BLACK, font_size=15)
    return canvas


def render_diagnostics_mode(esp32_telemetry: Optional[Dict[str, Any]] = None) -> AcepCanvas:
    canvas = AcepCanvas(width=PORTRAIT_W, height=PORTRAIT_H)
    telem = esp32_telemetry or {}
    rssi = telem.get("rssi", "-61 dBm")
    vbat = telem.get("vbat", "3.98 V (84%)")
    esp_ip = telem.get("ip", "192.168.1.145")
    wake_reason = telem.get("wake_reason", "TOUCH_PAD (4 toques)")

    canvas.draw_text_1bit(20, 24, "DIAGNÓSTICO DE SISTEMA", config.ACEP_COLOR_RED, font_size=20)
    canvas.draw_divider(y=56, x0=20, x1=460, thickness=2)

    items = [
        ("VPS Tokyo:", f"{socket.gethostname()} ({config.VPS_PUBLIC_URL})", config.ACEP_COLOR_BLUE),
        ("Orientación / Buffer:", f"Vertical 480x800  |  {config.EXPECTED_BIN_SIZE:,} B", config.ACEP_COLOR_BLACK),
        ("ESP32 IP Local:", esp_ip, config.ACEP_COLOR_GREEN),
        ("Señal Wi-Fi (RSSI):", rssi, config.ACEP_COLOR_BLUE),
        ("Batería LiPo:", vbat, config.ACEP_COLOR_ORANGE),
        ("Último Wakeup:", wake_reason, config.ACEP_COLOR_BLACK),
        ("SQLite Engine:", f"{config.DATABASE_PATH.name} (WAL Activo)", config.ACEP_COLOR_GREEN),
    ]

    ry = 80
    for label, val, col in items:
        canvas.draw_text_1bit(20, ry, label, config.ACEP_COLOR_BLACK, font_size=15)
        canvas.draw_text_1bit(20, ry + 22, val, col, font_size=17, mono=True, max_width=430)
        canvas.draw_divider(y=ry + 54, x0=20, x1=460, thickness=1, dashed=True)
        ry += 68

    canvas.draw_text_1bit(20, 580, "CALIBRACIÓN DE LOS 7 PIGMENTOS ACeP:", config.ACEP_COLOR_BLACK, font_size=15)
    bx = 20
    bw = 62
    for hw_idx, name, _, _ in config.ACEP_PALETTE_ORDERED:
        canvas.fill_rect(bx, 612, bx + bw - 4, 740, hw_idx)
        canvas.stroke_rect(bx, 612, bx + bw - 4, 740, config.ACEP_COLOR_BLACK, thickness=2)
        bx += bw

    return canvas


def build_screen_buffer(
    mode: str = "dashboard",
    calendar_events: Optional[List[Dict[str, str]]] = None,
    esp32_telemetry: Optional[Dict[str, Any]] = None,
    orientation: str = "vertical",
    photo_path: Optional[Path] = None,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    m = mode.lower().strip()

    if m in ("calendar", "calendar_month", "mes", "2"):
        canvas = render_monthly_calendar_canvas()
        resolved_mode = "calendar_month"
    elif m in ("photo", "photo_frame", "3"):
        canvas = render_photo_frame_mode(photo_path=photo_path)
        resolved_mode = "photo_frame"
    elif m in ("guest", "guest_wifi", "wifi", "4"):
        canvas = render_guest_wifi_mode()
        resolved_mode = "guest_wifi"
    elif m in ("diag", "diagnostics", "5"):
        canvas = render_diagnostics_mode(esp32_telemetry=esp32_telemetry)
        resolved_mode = "diagnostics"
    elif m in ("crayon", "dashboard_crayon"):
        canvas = render_dashboard_mode(calendar_events=calendar_events, theme="crayon")
        resolved_mode = "dashboard"
    elif m in ("muji", "dashboard_muji"):
        canvas = render_dashboard_mode(calendar_events=calendar_events, theme="muji")
        resolved_mode = "dashboard"
    elif m in ("bento", "dashboard_bento"):
        canvas = render_dashboard_mode(calendar_events=calendar_events, theme="bento")
        resolved_mode = "dashboard"
    else:
        canvas = render_dashboard_mode(calendar_events=calendar_events)
        resolved_mode = "dashboard"

    preview_img = render_preview_from_hw_indices(canvas.matrix, calibrated=True)
    preview_img.save(config.SCREEN_PREVIEW_PATH, format="PNG")

    hw_matrix_for_bin = canvas.matrix
    if hw_matrix_for_bin.shape == (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT):
        hw_matrix_for_bin = np.rot90(hw_matrix_for_bin, k=1)

    bin_path = save_packed_bin(hw_matrix_for_bin, config.SCREEN_BIN_PATH)

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    return {
        "mode": resolved_mode,
        "orientation": "vertical" if canvas.height > canvas.width else "horizontal",
        "bin_path": str(bin_path),
        "bin_size_bytes": bin_path.stat().st_size,
        "preview_path": str(config.SCREEN_PREVIEW_PATH),
        "elapsed_ms": elapsed_ms,
    }
