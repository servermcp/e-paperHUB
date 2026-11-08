"""
database.py — Capa de acceso a datos SQLite para E-Paper ACeP 7-Color Smart Dashboard.
Incluye la gestión de `tarjetas_gastos` (Logo Empresa, Logo Gasto, TOTAL, MÍNIMO, SALDO).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DATABASE_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    schema_sql = config.SCHEMA_PATH.read_text(encoding="utf-8")
    with db_session() as conn:
        conn.executescript(schema_sql)
        # Semilla inicial para tarjetas_gastos si está vacía
        cnt = conn.execute("SELECT COUNT(*) FROM tarjetas_gastos").fetchone()[0]
        if cnt == 0:
            seed_rows = [
                ("galicia",   "amex",       "Galicia Amex",     "08/11", 485000,  92000, 485000, 1),
                ("provincia", "visa",       "Provincia Visa",   "12/11", 312000,  64000, 212000, 2),
                ("galicia",   "mastercard", "Galicia Master",   "08/11", 198500,  45000,      0, 3),
                ("consorcio", "exp",        "Expensas Edif.",   "10/11", 142000, 142000, 142000, 4),
                ("edese",     "luz",        "EDESE Energía",    "15/11",  54200,  54200,      0, 5),
            ]
            conn.executemany(
                """
                INSERT INTO tarjetas_gastos (logo_empresa, logo_gasto, etiqueta, vencimiento, total, minimo, saldo, orden)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seed_rows,
            )


# ==============================================================================
# 1. TABLA DE TARJETAS DE CRÉDITO, EXPENSAS Y SERVICIOS
# ==============================================================================

def list_tarjetas_gastos() -> List[Dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, logo_empresa, logo_gasto, etiqueta, vencimiento, total, minimo, saldo, orden
            FROM tarjetas_gastos
            ORDER BY orden ASC, id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_tarjetas_totals() -> Dict[str, float]:
    rows = list_tarjetas_gastos()
    sum_total = sum(float(r["total"]) for r in rows)
    sum_minimo = sum(float(r["minimo"]) for r in rows)
    sum_saldo = sum(float(r["saldo"]) for r in rows)
    return {
        "total_mes": round(sum_total, 2),
        "total_minimo": round(sum_minimo, 2),
        "total_saldo": round(sum_saldo, 2),
    }


def upsert_tarjeta_gasto(
    logo_empresa: str,
    logo_gasto: str,
    total: float,
    minimo: float,
    saldo: float,
    etiqueta: str = "",
    vencimiento: str = "",
    row_id: Optional[int] = None,
) -> int:
    with db_session() as conn:
        if row_id:
            conn.execute(
                """
                UPDATE tarjetas_gastos
                SET logo_empresa = ?, logo_gasto = ?, etiqueta = ?, vencimiento = ?,
                    total = ?, minimo = ?, saldo = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (logo_empresa, logo_gasto, etiqueta, vencimiento, float(total), float(minimo), max(0.0, float(saldo)), int(row_id)),
            )
            return int(row_id)
        else:
            cur = conn.execute(
                """
                INSERT INTO tarjetas_gastos (logo_empresa, logo_gasto, etiqueta, vencimiento, total, minimo, saldo, orden)
                VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(orden), 0) + 1 FROM tarjetas_gastos))
                """,
                (logo_empresa, logo_gasto, etiqueta, vencimiento, float(total), float(minimo), max(0.0, float(saldo))),
            )
            return int(cur.lastrowid)


def registrar_pago_tarjeta(row_id: int, monto_pagado: float, modo_pago: str = "parcial") -> None:
    """
    Permite saldar el Total ('total'), cubrir el Mínimo ('minimo') o descontar un pago ('parcial').
    """
    with db_session() as conn:
        row = conn.execute("SELECT total, minimo, saldo FROM tarjetas_gastos WHERE id = ?", (int(row_id),)).fetchone()
        if not row:
            return
        if modo_pago == "total":
            nuevo_saldo = 0.0
        elif modo_pago == "minimo":
            nuevo_saldo = max(0.0, float(row["total"]) - float(row["minimo"]))
        else:
            nuevo_saldo = max(0.0, float(row["saldo"]) - float(monto_pagado))

        conn.execute(
            "UPDATE tarjetas_gastos SET saldo = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (nuevo_saldo, int(row_id)),
        )


def delete_tarjeta_gasto(row_id: int) -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM tarjetas_gastos WHERE id = ?", (int(row_id),))


# Compatibilidad con funciones previas
def get_gastos_summary() -> Dict[str, Any]:
    t = get_tarjetas_totals()
    return {
        "total_general": t["total_saldo"],
        "total_mes": t["total_mes"],
        "total_minimo": t["total_minimo"],
        "por_persona": {},
        "balances": {},
        "cuota_ideal": 0.0,
    }

def get_active_gastos(limit: int = 20) -> List[Dict[str, Any]]:
    return list_tarjetas_gastos()[:limit]

def set_active_nota(mensaje: str, expira_en: Optional[str] = None) -> int:
    with db_session() as conn:
        conn.execute("UPDATE notas SET activa = 0 WHERE activa = 1")
        cur = conn.execute(
            "INSERT INTO notas (mensaje, activa, expira_en) VALUES (?, 1, ?)",
            (mensaje.strip(), expira_en),
        )
        return int(cur.lastrowid)

def clear_active_notas() -> int:
    with db_session() as conn:
        cur = conn.execute("UPDATE notas SET activa = 0 WHERE activa = 1")
        return int(cur.rowcount)

def get_active_nota() -> Optional[Dict[str, Any]]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, fecha_creacion, mensaje, activa, expira_en FROM notas WHERE activa = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

def register_foto(nombre_archivo: str) -> int:
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT OR REPLACE INTO fotos (nombre_archivo, activa, mostrada_veces)
            VALUES (?, 1, COALESCE((SELECT mostrada_veces FROM fotos WHERE nombre_archivo = ?), 0))
            """,
            (nombre_archivo, nombre_archivo),
        )
        return int(cur.lastrowid)

def pick_next_carousel_foto() -> Optional[Dict[str, Any]]:
    import datetime
    today_prefix = f"comic_{datetime.date.today().strftime('%Y%m%d')}"
    with db_session() as conn:
        # Priorizar el cómic del día al iniciar el carrusel (mostrada_veces=0), luego rotar normalmente
        row = conn.execute(
            """
            SELECT id, nombre_archivo, fecha_subida, mostrada_veces 
            FROM fotos 
            WHERE activa = 1 
            ORDER BY 
                (CASE WHEN nombre_archivo LIKE ? || '%' AND mostrada_veces = 0 THEN 0 
                      WHEN nombre_archivo LIKE ? || '%' THEN 1 
                      ELSE 2 END),
                mostrada_veces ASC, 
                RANDOM() 
            LIMIT 1
            """,
            (today_prefix, today_prefix)
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE fotos SET mostrada_veces = mostrada_veces + 1 WHERE id = ?", (row["id"],))
        return dict(row)

def list_fotos(limit: int = 24) -> List[Dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute("SELECT id, nombre_archivo, fecha_subida, activa, mostrada_veces FROM fotos ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def upsert_device_state(device_id: str, device_name: str, integration: str, status_text: str, icon_type: str = "info") -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO device_state_cache (device_id, device_name, integration, status_text, icon_type, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(device_id) DO UPDATE SET
                device_name = excluded.device_name,
                integration = excluded.integration,
                status_text = excluded.status_text,
                icon_type = excluded.icon_type,
                updated_at = CURRENT_TIMESTAMP
            """,
            (device_id, device_name, integration, status_text, icon_type),
        )

def get_all_device_states() -> List[Dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT device_id, device_name, integration, status_text, icon_type, updated_at FROM device_state_cache ORDER BY integration ASC, device_id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_device_states() -> List[Dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT device_id, device_name, integration, status_text, icon_type, enabled, show_mode, is_active, sort_order, updated_at FROM device_state_cache ORDER BY sort_order ASC, device_id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_visible_dashboard_devices() -> List[Dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT device_id, device_name, integration, status_text, icon_type, enabled, show_mode, is_active, sort_order FROM device_state_cache WHERE enabled = 1 AND integration IN ('tuya', 'xiaomi') AND (show_mode = 'always' OR is_active = 1) ORDER BY sort_order ASC, device_id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_device_config(device_id: str, enabled: bool, show_mode: str, is_active: bool, status_text: str) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE device_state_cache SET enabled = ?, show_mode = ?, is_active = ?, status_text = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = ?",
            (1 if enabled else 0, show_mode, 1 if is_active else 0, status_text.strip(), device_id),
        )
