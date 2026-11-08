import sys
sys.path.append('/root/epaper-hub')
import app

print("Triggering screen rebuild via app...")
info = app._trigger_screen_rebuild('dashboard', force_integrations=True)
print("Screen rebuild result:", info)
