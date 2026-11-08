"""
generator/dither.py — Motor de Pre-procesamiento (Tone Mapping), Conversión CIELAB
y Algoritmo de Dithering Perceptual Atkinson / Sierra Lite para pantallas E-Ink ACeP 7-Color.
"""

from __future__ import annotations

from typing import Dict, Tuple, Union
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

import config


# ==============================================================================
# 1. CONVERSIÓN DE ESPACIO DE COLOR: sRGB <-> CIELAB (Iluminante D65, 2°)
# ==============================================================================

def srgb_to_lab_array(rgb_uint8: np.ndarray) -> np.ndarray:
    """
    Convierte una matriz de imagen sRGB uint8 de forma (..., 3) al espacio
    perceptual CIELAB (D65) en punto flotante float32 con forma (..., 3).

    Fórmula estándar IEC 61966-2-1 (sRGB) -> CIE 1931 XYZ (D65) -> CIE 1976 L*a*b*.
    """
    rgb = np.asarray(rgb_uint8, dtype=np.float32) / 255.0

    # 1. Expansión gamma inversa (sRGB a RGB lineal)
    mask = rgb > 0.04045
    rgb_lin = np.where(mask, np.power((rgb + 0.055) / 1.055, 2.4), rgb / 12.92)

    # 2. Transformación lineal a CIE XYZ (Iluminante D65)
    r = rgb_lin[..., 0]
    g = rgb_lin[..., 1]
    b = rgb_lin[..., 2]

    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    # Normalizar por el punto blanco de referencia D65 (Xn, Yn, Zn)
    x /= 0.95047
    y /= 1.00000
    z /= 1.08883

    # 3. Función no lineal f(t) de CIELAB
    epsilon = 216.0 / 24389.0  # (6/29)^3 ≈ 0.008856
    kappa = 24389.0 / 27.0     # (29/3)^3 ≈ 903.296

    def f_lab(t: np.ndarray) -> np.ndarray:
        return np.where(t > epsilon, np.cbrt(t), (kappa * t + 16.0) / 116.0)

    fx = f_lab(x)
    fy = f_lab(y)
    fz = f_lab(z)

    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b_val = 200.0 * (fy - fz)

    return np.stack([L, a, b_val], axis=-1).astype(np.float32)


# ==============================================================================
# 2. PRE-PROCESAMIENTO Y TONE MAPPING CALIBRADO PARA PIGMENTOS ACeP
# ==============================================================================

def build_s_curve_lut(contrast_strength: float = 0.15, brightness_boost: float = 1.05) -> np.ndarray:
    """
    Construye una tabla de consulta (LUT) de 256 entradas que aplica simultáneamente:
      1. Ganancia de brillo en medios tonos (+5% por defecto, levantando sombras sin quemar blancos).
      2. Curva S sigmoide (+15% de contraste por defecto) que preserva detalle en altas luces y sombras.
    """
    x = np.linspace(0.0, 1.0, 256, dtype=np.float32)

    # 1. Levantar medios tonos mediante corrección gamma suave (< 1.0 levanta medios tonos)
    if brightness_boost != 1.0 and brightness_boost > 0:
        gamma = 1.0 / float(brightness_boost)
        x = np.power(x, gamma)

    # 2. Curva S basada en función logística centrada en 0.5
    if contrast_strength > 0.0:
        k = 1.0 + (contrast_strength * 8.0)
        centered = x - 0.5
        sig = 1.0 / (1.0 + np.exp(-k * centered * 4.0))
        sig_min = 1.0 / (1.0 + np.exp(-k * (-0.5) * 4.0))
        sig_max = 1.0 / (1.0 + np.exp(-k * (0.5) * 4.0))
        s_curve = (sig - sig_min) / (sig_max - sig_min)
        blend = min(max(contrast_strength * 2.2, 0.0), 1.0)
        x = (1.0 - blend) * x + blend * s_curve

    lut = np.clip(np.round(x * 255.0), 0, 255).astype(np.uint8)
    return lut


def apply_acep_tone_mapping(
    image: Image.Image,
    saturation_boost: float = config.TONE_MAP_DEFAULTS.get("saturation_boost", 1.12),
    contrast_s_curve: float = config.TONE_MAP_DEFAULTS.get("contrast_s_curve", 0.10),
    brightness_boost: float = config.TONE_MAP_DEFAULTS.get("brightness_boost", 1.08),
    gamma_lift: float = config.TONE_MAP_DEFAULTS.get("gamma_lift", 0.82),
    skin_protect: bool = config.TONE_MAP_DEFAULTS.get("skin_protect", True),
    target_size: Tuple[int, int] = (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT),
) -> Image.Image:
    """
    Ejecuta el pre-procesamiento optimizado para la pantalla E-Paper ACeP de 7 colores:
      1. Ajuste dimensional inteligente (center-crop con LANCZOS al target_size).
      2. Levantamiento de sombras y medios tonos en Luminancia (Y Rec.601) preservando fidelidad
         de color (evita que los rostros en sombra caigan en pigmentos rojos/naranjas saturados).
      3. Contraste sigmoide suave en luminancia para conservar profundidad sin distorsionar croma.
      4. Saturación perceptual adaptativa con protección de tonos de piel humanos (evita
         el efecto de 'cara colorada/quemada' al ditherizar con la paleta limitada ACeP).
    """
    img = ImageOps.exif_transpose(image).convert("RGB")

    if img.size != target_size:
        img = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    arr = np.asarray(img, dtype=np.float32) / 255.0

    # 1. Luminancia preservada (Y Rec.601)
    y = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]

    # Corrección de brillo/gamma en luminancia (levanta sombras y rostros sin descalibrar el matiz)
    effective_gamma = gamma_lift
    if brightness_boost != 1.0 and brightness_boost > 0:
        effective_gamma *= (1.0 / float(brightness_boost))

    y_corr = np.power(np.maximum(y, 1e-4), effective_gamma)

    # 2. Contraste sigmoide S-curve aplicado a la luminancia
    if contrast_s_curve > 0.0:
        k = 1.0 + (contrast_s_curve * 8.0)
        centered = y_corr - 0.5
        sig = 1.0 / (1.0 + np.exp(-k * centered * 4.0))
        sig_min = 1.0 / (1.0 + np.exp(-k * (-0.5) * 4.0))
        sig_max = 1.0 / (1.0 + np.exp(-k * (0.5) * 4.0))
        s_curve = (sig - sig_min) / (sig_max - sig_min)
        blend = min(max(contrast_s_curve * 2.0, 0.0), 1.0)
        y_corr = (1.0 - blend) * y_corr + blend * s_curve

    scale = np.where(y > 1e-4, y_corr / np.maximum(y, 1e-4), 1.0)[..., None]
    arr_lifted = np.clip(arr * scale, 0.0, 1.0)

    # 3. Saturación adaptativa y protección de tonos de piel
    if skin_protect:
        rgb_uint8 = (arr_lifted * 255.0).astype(np.uint8)
        hsv = np.asarray(Image.fromarray(rgb_uint8, mode="RGB").convert("HSV"), dtype=np.float32)
        h = hsv[..., 0]  # 0..255 (en escala de 360°, 0=rojo, ~20=naranja, ~42=amarillo)
        s = hsv[..., 1] / 255.0
        v = hsv[..., 2] / 255.0

        # Campana gaussiana centrada en tonos cálidos de piel humana (~25° de matiz)
        is_warm = np.exp(-((h - 18.0) ** 2) / (2.0 * (12.0 ** 2)))
        is_skin = is_warm * np.clip((s - 0.12) / 0.18, 0.0, 1.0) * np.clip((v - 0.20) / 0.20, 0.0, 1.0)

        # Para pieles: saturación contenida (0.90) para permitir que el blanco y amarillo
        # dithericen suavemente sin disparar puntos rojos/naranjas aislados.
        # Para el resto (paisajes, vegetación, cielo, ropa): boost de saturación configurado.
        sat_mult = (1.0 - is_skin) * saturation_boost + is_skin * 0.90
        hsv[..., 1] = np.clip(s * sat_mult * 255.0, 0, 255)

        # Micro-ganancia en medios tonos de piel para asegurar que las caras no queden en sombras densas
        v_boost = np.clip(is_skin * (0.62 - v) * 0.25, 0.0, 0.12)
        hsv[..., 2] = np.clip((v + v_boost) * 255.0, 0, 255)

        img_out = Image.fromarray(hsv.astype(np.uint8), mode="HSV").convert("RGB")
    else:
        rgb_uint8 = (arr_lifted * 255.0).astype(np.uint8)
        img_out = Image.fromarray(rgb_uint8, mode="RGB")
        if saturation_boost != 1.0:
            enhancer = ImageEnhance.Color(img_out)
            img_out = enhancer.enhance(saturation_boost)

    return img_out


# ==============================================================================
# 3. CUANTIZACIÓN PERCEPTUAL EN CIE94 + DITHERING ATKINSON / SIERRA LITE
# ==============================================================================

_PALETTE_HW_INDICES = np.array([item[0] for item in config.ACEP_PALETTE_ORDERED], dtype=np.uint8)
_PALETTE_SRGB_CAL = np.array([item[2] for item in config.ACEP_PALETTE_ORDERED], dtype=np.float32)
_PALETTE_SRGB_IDEAL = np.array(
    [config.ACEP_IDEAL_SRGB[item[0]] for item in config.ACEP_PALETTE_ORDERED], dtype=np.uint8
)
_PALETTE_LAB_CAL = srgb_to_lab_array(_PALETTE_SRGB_CAL.astype(np.uint8))


def _build_rgb555_to_acep_lut() -> Tuple[np.ndarray, np.ndarray]:
    """
    Construye una LUT 3D de 32x32x32 (32,768 entradas, RGB555) que mapea cualquier
    triplete RGB al índice de color más cercano de la paleta ACeP usando la métrica
    perceptual CIE94 en espacio CIELAB (con ponderación de croma y tono).
    """
    grid = np.linspace(0, 255, 32, dtype=np.float32)
    r_grid, g_grid, b_grid = np.meshgrid(grid, grid, grid, indexing="ij")
    rgb_grid = np.stack([r_grid, g_grid, b_grid], axis=-1)

    lab_grid = srgb_to_lab_array(rgb_grid)

    L1 = lab_grid[..., 0, None]
    L2 = _PALETTE_LAB_CAL[None, None, None, :, 0]
    dL = L1 - L2

    a1 = lab_grid[..., 1, None]
    b1 = lab_grid[..., 2, None]
    a2 = _PALETTE_LAB_CAL[None, None, None, :, 1]
    b2 = _PALETTE_LAB_CAL[None, None, None, :, 2]

    C1 = np.sqrt(a1**2 + b1**2)
    C2 = np.sqrt(a2**2 + b2**2)
    dC = C1 - C2
    da = a1 - a2
    db = b1 - b2
    dH2 = np.maximum(0.0, da**2 + db**2 - dC**2)

    # Coeficientes estándar CIE94 para artes gráficas
    SC = 1.0 + 0.045 * C1
    SH = 1.0 + 0.015 * C1

    # Factor de ponderación en luminancia (1.08) para preservar contraste estructural
    dE2 = (dL * 1.08)**2 + (dC / SC)**2 + (dH2 / (SH**2))

    best_palette_pos = np.argmin(dE2, axis=-1).astype(np.uint8)
    return best_palette_pos, _PALETTE_SRGB_CAL



_LUT_BEST_POS: np.ndarray | None = None
_LUT_PALETTE_SRGB: np.ndarray | None = None


def _get_perceptual_lut() -> Tuple[np.ndarray, np.ndarray]:
    global _LUT_BEST_POS, _LUT_PALETTE_SRGB
    if _LUT_BEST_POS is None or _LUT_PALETTE_SRGB is None:
        _LUT_BEST_POS, _LUT_PALETTE_SRGB = _build_rgb555_to_acep_lut()
    return _LUT_BEST_POS, _LUT_PALETTE_SRGB


def dither_image_acep(
    image: Image.Image,
    algorithm: str = "atkinson",
    apply_tone_map: bool = True,
    serpentine: bool = True,
) -> Dict[str, Union[np.ndarray, Image.Image]]:
    """
    Ejecuta el pipeline completo sobre una imagen para la Capa Base de 800x480:
      1. Tone Mapping ACeP (+38% saturación, +15% contraste S-curve, +5% brillo).
      2. Cuantización perceptual en espacio CIELAB contra la paleta física de 7 colores.
      3. Difusión de error mediante el algoritmo **Atkinson** (difunde 6/8 = 75% del error,
         eliminando artefactos de "gusano" y preservando contraste local en bordes)
         o **Sierra Lite** (difunde 4/4 con huella compacta).

    Retorna un diccionario con:
      - 'hw_indices': np.ndarray (H, W) uint8 con los códigos de hardware ACeP (0x0..0x6)
      - 'preview_calibrated': PIL.Image RGB simulando el aspecto real del papel electrónico.
      - 'preview_ideal': PIL.Image RGB con los colores ideales vibrantes.
    """
    if apply_tone_map:
        work_img = apply_acep_tone_mapping(image)
    else:
        work_img = image.convert("RGB")

    width, height = work_img.size
    lut_pos, palette_srgb = _get_perceptual_lut()

    # Padding lateral de 2 px a izquierda/derecha y 2 filas extra abajo
    stride = width + 4
    padded = np.zeros((height + 2, stride, 3), dtype=np.float32)
    padded[:height, 2:width + 2, :] = np.asarray(work_img, dtype=np.float32)

    # Listas planas 1D nativas de Python para eliminar el overhead de boxing de NumPy en el bucle
    buf_r = padded[:, :, 0].ravel().tolist()
    buf_g = padded[:, :, 1].ravel().tolist()
    buf_b = padded[:, :, 2].ravel().tolist()

    out_pos_flat = [0] * (height * width)

    algo = algorithm.lower().strip()
    if algo not in ("atkinson", "sierra_lite"):
        raise ValueError(f"Algoritmo de dithering no soportado: {algorithm}. Use 'atkinson' o 'sierra_lite'.")

    p_r = palette_srgb[:, 0].tolist()
    p_g = palette_srgb[:, 1].tolist()
    p_b = palette_srgb[:, 2].tolist()
    lut_flat = lut_pos.ravel().tolist()

    stride2 = stride * 2

    for y in range(height):
        row_base = y * stride
        out_base = y * width

        reverse_scan = serpentine and (y & 1 == 1)
        if reverse_scan:
            x_iter = range(width + 1, 1, -1)
            s1 = -1
            s2 = -2
        else:
            x_iter = range(2, width + 2)
            s1 = 1
            s2 = 2

        if algo == "atkinson":
            # Kernel Atkinson:
            #       [ * ] [1/8] [1/8]
            # [1/8] [1/8] [1/8]
            #       [1/8]
            for x in x_iter:
                i = row_base + x
                r = buf_r[i]
                g = buf_g[i]
                b = buf_b[i]

                ri = 0 if r <= 0.0 else (31 if r >= 255.0 else int(r * 0.1215686))
                gi = 0 if g <= 0.0 else (31 if g >= 255.0 else int(g * 0.1215686))
                bi = 0 if b <= 0.0 else (31 if b >= 255.0 else int(b * 0.1215686))

                idx = lut_flat[(ri << 10) | (gi << 5) | bi]
                out_pos_flat[out_base + x - 2] = idx

                er = (r - p_r[idx]) * 0.125
                eg = (g - p_g[idx]) * 0.125
                eb = (b - p_b[idx]) * 0.125

                # Vecinos fila actual: i + s1, i + s2
                i1 = i + s1
                buf_r[i1] += er; buf_g[i1] += eg; buf_b[i1] += eb
                i2 = i + s2
                buf_r[i2] += er; buf_g[i2] += eg; buf_b[i2] += eb

                # Vecinos fila siguiente (y + 1): j - s1, j, j + s1
                j = i + stride
                jm = j - s1
                buf_r[jm] += er; buf_g[jm] += eg; buf_b[jm] += eb
                buf_r[j] += er;  buf_g[j] += eg;  buf_b[j] += eb
                jp = j + s1
                buf_r[jp] += er; buf_g[jp] += eg; buf_b[jp] += eb

                # Vecino fila y + 2: i + 2*stride
                k = i + stride2
                buf_r[k] += er; buf_g[k] += eg; buf_b[k] += eb

        else:
            # Kernel Sierra Lite:
            #       [ * ] [2/4]
            # [1/4] [1/4]
            for x in x_iter:
                i = row_base + x
                r = buf_r[i]
                g = buf_g[i]
                b = buf_b[i]

                ri = 0 if r <= 0.0 else (31 if r >= 255.0 else int(r * 0.1215686))
                gi = 0 if g <= 0.0 else (31 if g >= 255.0 else int(g * 0.1215686))
                bi = 0 if b <= 0.0 else (31 if b >= 255.0 else int(b * 0.1215686))

                idx = lut_flat[(ri << 10) | (gi << 5) | bi]
                out_pos_flat[out_base + x - 2] = idx

                er_q = (r - p_r[idx]) * 0.25
                eg_q = (g - p_g[idx]) * 0.25
                eb_q = (b - p_b[idx]) * 0.25

                i1 = i + s1
                buf_r[i1] += er_q * 2.0; buf_g[i1] += eg_q * 2.0; buf_b[i1] += eb_q * 2.0

                j = i + stride
                jm = j - s1
                buf_r[jm] += er_q; buf_g[jm] += eg_q; buf_b[jm] += eb_q
                buf_r[j] += er_q;  buf_g[j] += eg_q;  buf_b[j] += eb_q

    out_pos = np.array(out_pos_flat, dtype=np.uint8).reshape((height, width))
    hw_indices = _PALETTE_HW_INDICES[out_pos]

    preview_cal_arr = _PALETTE_SRGB_CAL.astype(np.uint8)[out_pos]
    preview_ideal_arr = _PALETTE_SRGB_IDEAL[out_pos]

    return {
        "hw_indices": hw_indices,
        "preview_calibrated": Image.fromarray(preview_cal_arr, mode="RGB"),
        "preview_ideal": Image.fromarray(preview_ideal_arr, mode="RGB"),
    }


def quantize_color_to_acep_hw(rgb: Tuple[int, int, int]) -> int:
    """
    Convierte un color RGB puntual al índice de hardware ACeP (0x0..0x6) más cercano
    en espacio perceptual CIE94 (útil para colorear elementos de UI o iconos SVG).
    """
    lut_pos, _ = _get_perceptual_lut()
    r = int(rgb[0])
    g = int(rgb[1])
    b = int(rgb[2])
    ri = 0 if r <= 0 else (31 if r >= 255 else int(r * 0.1215686))
    gi = 0 if g <= 0 else (31 if g >= 255 else int(g * 0.1215686))
    bi = 0 if b <= 0 else (31 if b >= 255 else int(b * 0.1215686))
    best_pos = lut_pos[ri, gi, bi]
    return int(_PALETTE_HW_INDICES[best_pos])

