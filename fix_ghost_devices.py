import sys
import re
from pathlib import Path
sys.path.append('/root/epaper-hub')
import database

# 1. Clean database
with database.db_session() as conn:
    conn.execute("DELETE FROM device_state_cache WHERE device_id IN ('ghome_gate_01', 'ghome_lights_01', 'ghome_hvac_01', 'tuya_irrigation_01')")
    conn.execute("DELETE FROM device_state_cache WHERE integration NOT IN ('tuya', 'xiaomi')")

print("DB cleaned of ghost devices!")

# 2. Fix schema.sql so init_db() never reinserts them
schema_file = Path('/root/epaper-hub/schema.sql')
schema_text = schema_file.read_text(encoding='utf-8')
# Remove INSERT OR IGNORE INTO device_state_cache block
idx = schema_text.find("INSERT OR IGNORE INTO device_state_cache")
if idx != -1:
    schema_text = schema_text[:idx].rstrip() + "\n"
    schema_file.write_text(schema_text, encoding='utf-8')
    print("schema.sql cleaned!")

# 3. Fix database.py get_visible_dashboard_devices()
db_file = Path('/root/epaper-hub/database.py')
db_text = db_file.read_text(encoding='utf-8')
db_text = db_text.replace(
    "WHERE enabled = 1 AND (show_mode = 'always' OR is_active = 1)",
    "WHERE enabled = 1 AND integration IN ('tuya', 'xiaomi') AND (show_mode = 'always' OR is_active = 1)"
)
db_file.write_text(db_text, encoding='utf-8')
print("database.py updated to strictly require integration IN ('tuya', 'xiaomi')!")

# 4. Trigger screen rebuild
import app
info = app._trigger_screen_rebuild('dashboard', force_integrations=True)
print("Rebuilt screen info:", info)

# 5. Check visible devices
vis = database.get_visible_dashboard_devices()
print(f"Total visible devices now: {len(vis)}")
for v in vis:
    print(" -", v['device_name'], f"({v['integration']}) :", v['status_text'])
