import sys
sys.path.append('/root/epaper-hub')
import database

with database.db_session() as conn:
    # 1. Create new table without restrictive check constraint
    conn.execute("""
    CREATE TABLE IF NOT EXISTS device_state_cache_new (
        device_id TEXT PRIMARY KEY,
        device_name TEXT NOT NULL,
        integration TEXT NOT NULL DEFAULT 'tuya',
        status_text TEXT NOT NULL,
        icon_type TEXT NOT NULL DEFAULT 'info',
        enabled INTEGER NOT NULL DEFAULT 1,
        show_mode TEXT NOT NULL DEFAULT 'always',
        is_active INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 10,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Copy existing valid devices
    conn.execute("""
    INSERT OR REPLACE INTO device_state_cache_new (device_id, device_name, integration, status_text, icon_type, enabled, show_mode, is_active, sort_order, updated_at)
    SELECT device_id, device_name, 
           CASE WHEN device_id = 'romina_robot' THEN 'xiaomi' ELSE integration END,
           status_text, icon_type, enabled, show_mode, is_active, sort_order, updated_at
    FROM device_state_cache
    WHERE integration != 'google_home' OR device_id = 'romina_robot';
    """)

    # 3. Drop old and rename
    conn.execute("DROP TABLE device_state_cache;")
    conn.execute("ALTER TABLE device_state_cache_new RENAME TO device_state_cache;")

    # 4. Remove duplicate irrigation row if any
    conn.execute("DELETE FROM device_state_cache WHERE device_id = 'tuya_irrigation_01';")

    # 5. Disable vps telemetry from domotica list
    conn.execute("UPDATE device_state_cache SET enabled = 0 WHERE device_id = 'vps_esp32_diag';")

print("Migration completed successfully!")
devices = database.get_all_device_states()
for d in devices:
    print(d['device_id'], '|', d['device_name'], '|', d['integration'], '| enabled =', d['enabled'], '|', d['status_text'])
