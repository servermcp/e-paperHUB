import os
from pathlib import Path
from PIL import Image
import numpy as np

RAW_DIR = Path('/root/epaper-hub/static/icons/weather_inkypi')
OUT_DIR = Path('/root/epaper-hub/static/icons/weather_acep')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 7 ACeP Colors
ACEP_PALETTE = [
    (0, 0, 0),       # 0: Black
    (255, 255, 255), # 1: White
    (0, 180, 0),     # 2: Green
    (0, 70, 220),    # 3: Blue
    (220, 20, 20),   # 4: Red
    (255, 220, 0),   # 5: Yellow
    (255, 120, 0),   # 6: Orange
]

pal_img = Image.new("P", (1, 1))
pal_bytes = []
for c in ACEP_PALETTE:
    pal_bytes.extend(c)
pal_bytes.extend([0] * (768 - len(pal_bytes)))
pal_img.putpalette(pal_bytes)

def convert_and_save(raw_filename, out_stem, target_size=72):
    raw_path = RAW_DIR / raw_filename
    if not raw_path.exists():
        print(f"Not found: {raw_filename}")
        return
    
    im = Image.open(raw_path).convert("RGBA")
    im = im.resize((target_size, target_size), Image.Resampling.LANCZOS)
    
    alpha = np.array(im)[:, :, 3]
    mask = alpha > 60
    
    # White background for quantizing non-transparent pixels
    white_bg = Image.new("RGBA", (target_size, target_size), (255, 255, 255, 255))
    white_bg.alpha_composite(im)
    rgb = white_bg.convert("RGB")
    
    # Floyd-Steinberg dither to ACeP palette
    quant = rgb.quantize(palette=pal_img, dither=Image.Dither.FLOYDSTEINBERG)
    indices = np.array(quant, dtype=np.uint8)
    
    # Save .npy with indices and mask
    np.save(OUT_DIR / f"{out_stem}_{target_size}.npy", {"indices": indices, "mask": mask})
    
    # Also save a clean preview PNG
    quant.save(OUT_DIR / f"{out_stem}_{target_size}.png")
    print(f"Processed: {raw_filename} -> {out_stem}_{target_size}")

# Process main weather icons (72x72)
main_icons = [
    ("01d.png", "01d"), ("01n.png", "01n"),
    ("02d.png", "02d"), ("02n.png", "02n"),
    ("03d.png", "03d"), ("04d.png", "04d"),
    ("09d.png", "09d"), ("10d.png", "10d"), ("10n.png", "10n"),
    ("11d.png", "11d"), ("13d.png", "13d"),
    ("50d.png", "50d"), ("51d.png", "51d"),
    ("wind.png", "wind"), ("humidity.png", "humidity")
]

for raw, stem in main_icons:
    convert_and_save(raw, stem, 72)

# Also process metrics icons at 20x20
convert_and_save("humidity.png", "humidity", 20)
convert_and_save("wind.png", "wind", 20)

print("Batch conversion completed!")
