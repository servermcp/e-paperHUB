import sys
sys.path.append('/root/epaper-hub')
import database

visible = database.get_visible_dashboard_devices()
print("Visible dashboard devices count:", len(visible))
for d in visible:
    print(d)
