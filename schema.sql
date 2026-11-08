-- ============================================================================
-- schema.sql — Persistencia SQLite para E-Paper ACeP 7-Color Smart Dashboard
-- ============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 1. Seguimiento de Tarjetas de Crédito, Expensas y Servicios (Tabla Principal)
CREATE TABLE IF NOT EXISTS tarjetas_gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    logo_empresa TEXT NOT NULL,
    logo_gasto TEXT NOT NULL,
    etiqueta TEXT NOT NULL DEFAULT '',
    vencimiento TEXT NOT NULL DEFAULT '',
    total REAL NOT NULL DEFAULT 0 CHECK (total >= 0),
    minimo REAL NOT NULL DEFAULT 0 CHECK (minimo >= 0),
    saldo REAL NOT NULL DEFAULT 0 CHECK (saldo >= 0),
    orden INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Gastos históricos (compatibilidad)
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    concepto TEXT NOT NULL,
    monto REAL NOT NULL CHECK (monto >= 0),
    pagado_por TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'Otros',
    saldado BOOLEAN NOT NULL DEFAULT 0
);

-- 3. Post-it Digital / Notas
CREATE TABLE IF NOT EXISTS notas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mensaje TEXT NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT 1,
    expira_en TIMESTAMP NULL
);

-- 4. Galería / Marco de Fotos
CREATE TABLE IF NOT EXISTS fotos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_archivo TEXT NOT NULL UNIQUE,
    fecha_subida TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activa BOOLEAN NOT NULL DEFAULT 1,
    mostrada_veces INTEGER NOT NULL DEFAULT 0
);

-- 5. Caché de Estado de Dispositivos IoT y Telemetría
CREATE TABLE IF NOT EXISTS device_state_cache (
    device_id TEXT PRIMARY KEY,
    device_name TEXT NOT NULL,
    integration TEXT NOT NULL CHECK (integration IN ('tuya', 'google_home', 'vps')),
    status_text TEXT NOT NULL,
    icon_type TEXT NOT NULL DEFAULT 'info',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
