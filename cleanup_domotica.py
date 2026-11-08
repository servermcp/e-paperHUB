import sys
sys.path.append('/root/epaper-hub')
import database

with database.db_session() as conn:
    # 1. Delete mock Google Home devices
    conn.execute("DELETE FROM device_state_cache WHERE integration = 'google_home' AND device_id != 'romina_robot'")
    
    # 2. Delete duplicate irrigation row
    conn.execute("DELETE FROM device_state_cache WHERE device_id = 'tuya_irrigation_01'")

    # 3. Update romina_robot integration to 'xiaomi'
    conn.execute("UPDATE device_state_cache SET integration = 'xiaomi' WHERE device_id = 'romina_robot'")

    # 4. Hide vps_esp32_diag from dashboard devices (enabled = 0)
    conn.execute("UPDATE device_state_cache SET enabled = 0 WHERE device_id = 'vps_esp32_diag'")

print("Cleanup executed successfully!")
devices = database.get_all_device_states()
for d in devices:
    print(d['device_id'], '|', d['device_name'], '|', d['integration'], '| enabled =', d['enabled'], '|', d['status_text'])
