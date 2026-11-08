import sys
sys.path.append('/root/epaper-hub')
import app

print("Triggering guest_wifi mode render...")
info = app._trigger_screen_rebuild('guest_wifi')
print("Guest Wi-Fi render result:", info)

# Now switch back to dashboard so that the default screen is the dashboard
app._trigger_screen_rebuild('dashboard')
print("Switched back to dashboard.")
