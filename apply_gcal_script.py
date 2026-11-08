import sys
sys.path.append('/root/epaper-hub')
from integrations.google_cal import save_gcal_ical_url, get_upcoming_events
import generator.layout as layout
import generator.packer as packer
import os
import config
from pathlib import Path

url = os.getenv("GOOGLE_CALENDAR_ICAL_URL", "")
print("Saving iCal URL...")
save_gcal_ical_url(url)

print("Fetching upcoming events...")
events = get_upcoming_events(max_results=5, force_refresh=True)
print("Events returned:", events)

print("Rebuilding dashboard screen...")
raw_indices = layout.build_screen_buffer(mode='dashboard', force_integrations=True)
packed = packer.pack_hw_indices_to_bytes(raw_indices)
packer.save_packed_bin(packed, Path('/root/epaper-hub/static/screen.bin'))
packer.render_preview_from_hw_indices(raw_indices, Path('/root/epaper-hub/static/screen_preview.png'))
print("Screen rebuilt successfully! Buffer size:", len(packed))
