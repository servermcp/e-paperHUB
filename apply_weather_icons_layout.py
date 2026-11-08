from pathlib import Path
import re

# 1. Update weather.py
weather_file = Path('/root/epaper-hub/generator/weather.py')
w_code = weather_file.read_text(encoding='utf-8')

new_wmo_map = '''WMO_CODE_MAP: Dict[int, Tuple[str, str, str, int]] = {
    0:  ("Despejado",        "01d", "01n", config.ACEP_COLOR_ORANGE),
    1:  ("Mayormente claro", "01d", "01n", config.ACEP_COLOR_YELLOW),
    2:  ("Parcial nublado",  "02d", "02n", config.ACEP_COLOR_ORANGE),
    3:  ("Nublado",          "03d", "03d", config.ACEP_COLOR_BLUE),
    45: ("Niebla",           "50d", "50d", config.ACEP_COLOR_BLUE),
    48: ("Niebla helada",    "50d", "50d", config.ACEP_COLOR_BLUE),
    51: ("Llovizna leve",    "51d", "51d", config.ACEP_COLOR_BLUE),
    53: ("Llovizna",         "51d", "51d", config.ACEP_COLOR_BLUE),
    55: ("Llovizna densa",   "51d", "51d", config.ACEP_COLOR_BLUE),
    61: ("Lluvia leve",      "10d", "10n", config.ACEP_COLOR_BLUE),
    63: ("Lluvia moderada",  "10d", "10n", config.ACEP_COLOR_BLUE),
    65: ("Lluvia fuerte",    "09d", "09d", config.ACEP_COLOR_RED),
    71: ("Nevada leve",      "13d", "13d", config.ACEP_COLOR_BLUE),
    73: ("Nevada",           "13d", "13d", config.ACEP_COLOR_BLUE),
    75: ("Nevada intensa",   "13d", "13d", config.ACEP_COLOR_BLUE),
    80: ("Chaparrones",      "09d", "09d", config.ACEP_COLOR_BLUE),
    81: ("Chaparrón fuerte", "09d", "09d", config.ACEP_COLOR_RED),
    82: ("Tormenta lluvia",  "11d", "11d", config.ACEP_COLOR_RED),
    95: ("Tormenta eléctr.", "11d", "11d", config.ACEP_COLOR_RED),
    96: ("Tormenta granizo", "11d", "11d", config.ACEP_COLOR_RED),
    99: ("Granizo fuerte",   "11d", "11d", config.ACEP_COLOR_RED),
}'''

# Replace WMO_CODE_MAP definition
old_map_match = re.search(r'WMO_CODE_MAP: Dict\[int, Tuple\[str, str, int\]\] = \{.*?
\}', w_code, re.DOTALL)
if old_map_match:
    w_code = w_code[:old_map_match.start()] + new_wmo_map + w_code[old_map_match.end():]

# In fetch_weather(), handle (desc, icon_d, icon_n, icon_color)
old_unpack = 'desc, icon_name, icon_color = WMO_CODE_MAP.get('
new_unpack = '''from datetime import datetime
        is_night = (datetime.now().hour < 6 or datetime.now().hour >= 20)
        entry = WMO_CODE_MAP.get(wmo_code, ("Variable", "02d", "02n", config.ACEP_COLOR_BLUE))
        desc = entry[0]
        icon_name = entry[2] if is_night else entry[1]
        icon_color = entry[3]
        if False:
            desc, icon_name, icon_color = WMO_CODE_MAP.get('''

if old_unpack in w_code and 'is_night =' not in w_code:
    w_code = w_code.replace(old_unpack, new_unpack)

weather_file.write_text(w_code, encoding='utf-8')
print("weather.py updated successfully!")

# 2. Update layout.py
layout_file = Path('/root/epaper-hub/generator/layout.py')
l_code = layout_file.read_text(encoding='utf-8')

draw_weather_method = '''    def draw_weather_icon(
        self,
        x: int,
        y: int,
        icon_name: str,
        size: int = 72,
    ) -> bool:
        icon_file = config.BASE_DIR / "static" / "icons" / "weather_acep" / f"{icon_name}_{size}.npy"
        if icon_file.exists():
            try:
                data = np.load(icon_file, allow_pickle=True).item()
                indices = data["indices"]
                mask = data["mask"]

                x0 = max(0, int(x))
                y0 = max(0, int(y))
                x1 = min(self.width, x0 + size)
                y1 = min(self.height, y0 + size)

                if x1 > x0 and y1 > y0:
                    sub_ind = indices[0:(y1 - y0), 0:(x1 - x0)]
                    sub_mask = mask[0:(y1 - y0), 0:(x1 - x0)]
                    region = self.matrix[y0:y1, x0:x1]
                    region[sub_mask] = sub_ind[sub_mask]
                    return True
            except Exception:
                pass
        return False
'''

if 'def draw_weather_icon' not in l_code:
    # insert before def draw_vector_icon
    idx = l_code.find('    def draw_vector_icon(')
    if idx != -1:
        l_code = l_code[:idx] + draw_weather_method + '
' + l_code[idx:]

# In render_dashboard_mode, use draw_weather_icon
old_draw_call = 'canvas.draw_vector_icon(20, 50, weather["icon_name"], size=68, hw_color=weather["icon_hw_color"])'
new_draw_call = '''if not canvas.draw_weather_icon(18, 46, weather["icon_name"], size=72):
        canvas.draw_vector_icon(20, 50, weather["icon_name"], size=68, hw_color=weather["icon_hw_color"])'''

if old_draw_call in l_code:
    l_code = l_code.replace(old_draw_call, new_draw_call)

# In metrics line, use small icons for humidity and wind
old_metrics = '''    canvas.draw_text_1bit(
        20, 136,
        f"Humedad {weather['humidity']}%   •   Viento {weather['wind_kmh']} km/h",
        config.ACEP_COLOR_BLACK,
        font_size=15,
    )'''

new_metrics = '''    canvas.draw_weather_icon(20, 134, "humidity", size=20)
    canvas.draw_text_1bit(44, 136, f"Humedad {weather['humidity']}%", config.ACEP_COLOR_BLACK, font_size=15)
    canvas.draw_weather_icon(170, 134, "wind", size=20)
    canvas.draw_text_1bit(196, 136, f"Viento {weather['wind_kmh']} km/h", config.ACEP_COLOR_BLACK, font_size=15)'''

if old_metrics in l_code:
    l_code = l_code.replace(old_metrics, new_metrics)

layout_file.write_text(l_code, encoding='utf-8')
print("layout.py updated successfully!")

# 3. Test screen rebuild
import app
info = app._trigger_screen_rebuild('dashboard', force_integrations=True)
print("Screen rebuild with InkyPi weather icons result:", info)
