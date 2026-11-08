import os
import requests
from pathlib import Path
from PIL import Image

DEST_DIR = Path('/root/epaper-hub/static/icons/weather_inkypi')
DEST_DIR.mkdir(parents=True, exist_ok=True)

api_url = 'https://api.github.com/repos/fatihak/InkyPi/contents/src/plugins/weather/icons'
headers = {'User-Agent': 'Antigravity-Agent'}

print('Fetching file list from GitHub...')
r = requests.get(api_url, headers=headers, timeout=15)
if r.status_code == 200:
    items = r.json()
    print(f'Total icons to download: {len(items)}')
    for item in items:
        name = item['name']
        d_url = item['download_url']
        file_path = DEST_DIR / name
        if not file_path.exists():
            res = requests.get(d_url, timeout=10)
            file_path.write_bytes(res.content)
            print(f'Downloaded: {name} ({len(res.content)} bytes)')
        else:
            print(f'Already exists: {name}')
else:
    print('Error fetching list:', r.status_code, r.text[:200])

print('All icons downloaded to', DEST_DIR)
