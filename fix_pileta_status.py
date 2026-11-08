import sys
sys.path.append('/root/epaper-hub')
import database

# 1. Update pileta_filtro to inactive and Apagada
with database.db_session() as conn:
    conn.execute(
        "UPDATE device_state_cache SET status_text = 'Apagada', is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'pileta_filtro'"
    )
print("Updated pileta_filtro to Apagada, is_active = 0")

# 2. Check visible devices
vis = database.get_visible_dashboard_devices()
print(f"Visible dashboard devices ({len(vis)}):")
for v in vis:
    print(" -", v['device_name'], f"({v['integration']}) :", v['status_text'])

# 3. Trigger screen rebuild
import app
info = app._trigger_screen_rebuild('dashboard', force_integrations=True)
print("Screen rebuilt successfully:", info)
