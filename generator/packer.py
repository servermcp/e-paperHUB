"""
generator/packer.py — Empacador y desempacador binario de 4 bits por píxel (nibbles)
para el panel E-Paper 7.3" ACeP (800x480 px -> 192,000 bytes exactos).
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union
import numpy as np
from PIL import Image

import config


def pack_hw_indices_to_bytes(hw_indices: np.ndarray) -> bytes:
    """
    Empaca una matriz 2D uint8 de dimensión (480, 800) con índices de hardware ACeP (0x0..0x7)
    en un buffer binario crudo de 4 bits por píxel (2 píxeles por byte: nibble alto = px par,
    nibble bajo = px impar):
        byte = (px0 << 4) | (px1 & 0x0F)

    Retorna exactamente 192,000 bytes listos para enviar por HTTP y volcar vía SPI DMA.
    """
    arr = np.asarray(hw_indices, dtype=np.uint8)
    expected_shape = (config.DISPLAY_HEIGHT, config.DISPLAY_WIDTH)
    if arr.shape != expected_shape:
        raise ValueError(
            f"Dimensión inválida para empacado ACeP: {arr.shape}. Se esperaba {expected_shape}."
        )

    # Validar rango de 4 bits (0x0..0x7)
    arr_clamped = np.clip(arr, 0x00, 0x07)

    # Tomar píxeles pares (columnas 0, 2, 4...) e impares (columnas 1, 3, 5...) de forma vectorizada
    px_even = arr_clamped[:, 0::2]  # (480, 400)
    px_odd = arr_clamped[:, 1::2]   # (480, 400)

    packed = np.bitwise_or(np.left_shift(px_even, 4), np.bitwise_and(px_odd, 0x0F)).astype(np.uint8)
    raw_bytes = packed.tobytes()

    if len(raw_bytes) != config.EXPECTED_BIN_SIZE:
        raise RuntimeError(
            f"Tamaño de binario corrupto: {len(raw_bytes)} bytes (esperado: {config.EXPECTED_BIN_SIZE})."
        )
    return raw_bytes


def save_packed_bin(
    hw_indices: np.ndarray,
    output_path: Union[str, Path] = config.SCREEN_BIN_PATH,
) -> Path:
    """
    Empaca la matriz 800x480 a 192,000 bytes y la guarda atómicamente en disco
    (escribiendo primero en un archivo temporal .tmp y renombrando) para evitar que
    el ESP32 descargue un buffer a medio escribir.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".bin.tmp")

    raw_bytes = pack_hw_indices_to_bytes(hw_indices)
    tmp_path.write_bytes(raw_bytes)
    tmp_path.replace(out_path)
    return out_path


def unpack_bytes_to_hw_indices(raw_bytes: bytes) -> np.ndarray:
    """
    Operación inversa de verificación: desempaca un buffer de 192,000 bytes
    nuevamente a una matriz (480, 800) uint8 con índices 0x0..0x7.
    """
    if len(raw_bytes) != config.EXPECTED_BIN_SIZE:
        raise ValueError(
            f"El buffer debe medir exactamente {config.EXPECTED_BIN_SIZE} bytes (recibido: {len(raw_bytes)})."
        )
    packed = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(
        (config.DISPLAY_HEIGHT, config.DISPLAY_WIDTH // 2)
    )
    px_even = np.right_shift(packed, 4) & 0x0F
    px_odd = packed & 0x0F

    out = np.empty((config.DISPLAY_HEIGHT, config.DISPLAY_WIDTH), dtype=np.uint8)
    out[:, 0::2] = px_even
    out[:, 1::2] = px_odd
    return out


def render_preview_from_hw_indices(
    hw_indices: np.ndarray, calibrated: bool = True
) -> Image.Image:
    """
    Convierte cualquier matriz (480, 800) de índices de hardware ACeP (0x0..0x6)
    a una imagen RGB PIL (usando colores calibrados de papel o ideales vibrantes)
    para mostrar la vista previa en la WebApp móvil.
    """
    lut = np.zeros((16, 3), dtype=np.uint8)
    color_map = config.ACEP_CALIBRATED_SRGB if calibrated else config.ACEP_IDEAL_SRGB
    for hw_idx, rgb in color_map.items():
        lut[hw_idx] = rgb
    rgb_arr = lut[np.clip(hw_indices, 0, 15)]
    return Image.fromarray(rgb_arr, mode="RGB")
