#!/usr/bin/env python3
"""
comic_generator.py - Generador del Cómic Diario de "Las Gaturrakas" con Diálogos en Español
Estilo: Tira cómica / novela gráfica limpia estilo 'Bone' (Jeff Smith).
Personajes:
  - Gaturraka (Mamá): Negra con corazón blanco en el pecho, cara gruñona pero cariñosa.
  - Lucrecia (Hija 1): Totalmente negra, cola en forma de rayo (zigzag tipo Pikachu), ojos gigantes de sorpresa, parkour felino.
  - Ceniza (Hija 2): Totalmente gris, rellenita, durmiendo plácidamente en su taburete.
"""

import os
import sys
import json
import sqlite3
import datetime
import urllib.request
from PIL import Image

sys.path.append('/root/epaper-hub')
import config
from generator.dither import dither_image_acep
from generator.layout import build_screen_buffer

DB_PATH = '/root/epaper-hub/epaper_hub.db'
UPLOADS_DIR = str(config.UPLOADS_DIR)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs('/root/epaper-hub/logs', exist_ok=True)

DIAS_SEMANA = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo"
}

DIALOGOS_POOL = {
    "lluvioso": {
        "ceniza": "Zzz... el ruido de la lluvia es mi canción de cuna... Zzz...",
        "lucrecia": "¡ALERTA! ¡GOTAS GIGANTES ATACAN EL VIDRIO! ¡MODO RAYO!",
        "gaturraka": "Día gris y húmedo. Más te vale hacerme mimos y darme atún, humano."
    },
    "soleado": {
        "ceniza": "El rayo de sol se movió 5 centímetros... tendré que estirarme... Zzz...",
        "lucrecia": "¡EL PISO ES LAVA! ¡ME VOY AL TECHO!",
        "gaturraka": "Solo un beso en la frente, Matías. Uno solo. Ni se te ocurra tocarme la panza."
    },
    "lunes": {
        "ceniza": "Zzz... ¿Lunes? Esa palabra no existe en mi diccionario... Zzz...",
        "lucrecia": "¡EMPIEZA LA SEMANA! ¡A CORRER POR LOS MUEBLES!",
        "gaturraka": "No me hables hasta que sirvas el desayuno. Bueno... un beso te permito."
    },
    "general": {
        "ceniza": "Dormir 18 horas es mi vocación. Nadie me moverá de este taburete.",
        "lucrecia": "¡MAMÁ! ¡CREO QUE VI UN DUENDE VOLADOR EN EL TECHO!",
        "gaturraka": "Mmmph... siempre el mismo drama en esta casa. Pero acá me quedo."
    }
}

def get_current_day_and_weather():
    now = datetime.datetime.now()
    dia = DIAS_SEMANA.get(now.weekday(), "Hoy")
    weather_desc = "templado y agradable"
    clima_clave = "general"

    if now.weekday() == 0:
        clima_clave = "lunes"

    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT raw_state FROM device_state_cache WHERE device_id='weather_openmeteo'")
        row = cur.fetchone()
        con.close()
        if row and row[0]:
            wdata = json.loads(row[0])
            temp = wdata.get('temp', 22)
            desc = wdata.get('weather_desc', 'Despejado').lower()
            weather_desc = f"{desc}, con una temperatura de {temp}°C"
            if "lluvia" in desc or "tormenta" in desc or "llovizna" in desc:
                clima_clave = "lluvioso"
            elif "despejado" in desc or "sol" in desc:
                clima_clave = "soleado"
    except Exception:
        pass

    return dia, weather_desc, clima_clave

def build_comic_prompt(dia: str, weather_desc: str, clima_clave: str) -> str:
    dialogos = DIALOGOS_POOL.get(clima_clave, DIALOGOS_POOL["general"])
    
    parts = [
        "A full comic strip page in the clean, expressive graphic novel style of Jeff Smith's 'Bone' ",
        "(bold clean black ink outlines, warm cel-shaded colors, white gutters separating 3 clear rectangular panels). ",
        f"Subject: 'Las Gaturrakas' daily domestic pet cat comic strip on {dia} ({weather_desc}). ",
        "Characters & Dialogues in Spanish (render legible, hand-lettered speech balloons): ",
        f"1. Top Panel: CENIZA (chubby, solid smoke-gray cat) sleeping curled on top of a tall round wooden stool, with a speech balloon saying: \"{dialogos['ceniza']}\". ",
        f"2. Middle Panel: LUCRECIA (solid black cat with large round surprised saucer eyes and a funny zigzag Pikachu-style lightning bolt tail) bouncing/parkour off the wall with dynamic comic motion lines, with an excited speech balloon saying: \"{dialogos['lucrecia']}\". ",
        f"3. Bottom Panel: GATURRAKA (sleek black mother cat with a distinct white heart-shaped patch on her chest) sitting with a classic grumpy/unimpressed expression while her human gives her an affectionate forehead kiss, with a speech balloon saying: \"{dialogos['gaturraka']}\". Lucrecia peeks from behind a plant in shock. ",
        f"Header caption on top: \"Las Gaturrakas • {dia}\". Vertical 3:4 aspect ratio, high contrast lineart."
    ]
    return "".join(parts)

def generate_with_gemini(prompt: str) -> str:
    """Llama a la API de Gemini (requiere facturación Pay-as-you-go en Google AI Studio)."""
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={config.GEMINI_API_KEY}'
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]}
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        candidates = res.get('candidates', [])
        parts = candidates[0].get('content', {}).get('parts', [])
        for p in parts:
            if 'inlineData' in p:
                b64_data = p['inlineData'].get('data')
                import base64
                img_bytes = base64.b64decode(b64_data)
                today_str = datetime.date.today().strftime('%Y%m%d')
                raw_path = os.path.join(UPLOADS_DIR, f"comic_raw_{today_str}.png")
                with open(raw_path, 'wb') as f:
                    f.write(img_bytes)
                return raw_path
    raise RuntimeError("No image returned by Gemini")

def process_and_register_comic(img_path: str):
    """
    1. Recorta a 480x800 vertical.
    2. Aplica Atkinson Dithering perceptual CIELAB.
    3. Guarda como comic_YYYYMMDD.png en uploads/.
    4. Desactiva cómics de días anteriores (quedan archivados en disco y DB).
    5. Activa el de hoy como prioritario en el carrusel (mostrada_veces=0).
    """
    img = Image.open(img_path).convert('RGB')
    w, h = img.size
    target_w, target_h = 480, 800
    target_ratio = target_w / target_h
    src_ratio = w / h

    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    today_str = datetime.date.today().strftime('%Y%m%d')
    base_name = f"comic_{today_str}.png"
    final_path = os.path.join(UPLOADS_DIR, base_name)
    img.save(final_path)

    # Dithering ACeP de alta fidelidad
    res = dither_image_acep(img, algorithm='atkinson', apply_tone_map=True)
    preview = res.get('preview_ideal') or res.get('preview_calibrated')
    preview_path = os.path.join(UPLOADS_DIR, f"comic_{today_str}_acep_preview.png")
    preview.save(preview_path)

    # Actualizar DB: archivar cómics pasados y activar solo el de hoy
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    # Desactivar cómics de días anteriores para que no roten en el carrusel hoy
    cur.execute("UPDATE fotos SET activa = 0 WHERE nombre_archivo LIKE 'comic_%' AND nombre_archivo != ?", (base_name,))
    
    # Registrar / activar el de hoy con prioridad 0
    cur.execute("""
        INSERT INTO fotos (nombre_archivo, activa, mostrada_veces)
        VALUES (?, 1, 0)
        ON CONFLICT(nombre_archivo) DO UPDATE SET activa = 1, mostrada_veces = 0
    """, (base_name,))
    con.commit()
    con.close()

    print(f"[OK] Cómic de hoy archivado y activado: {base_name}")
    print(f"[OK] Cómics de días anteriores desactivados del carrusel pero preservados en disco y DB.")

    # Re-renderizar buffer de pantalla si el modo foto está activo
    try:
        build_screen_buffer(mode='photo_frame')
        print("[OK] Buffer de pantalla de marco de fotos actualizado con el nuevo cómic.")
    except Exception as e:
        print(f"[AVISO] No se pudo regenerar screen buffer de inmediato: {e}")

def main():
    dia, weather, clima_clave = get_current_day_and_weather()
    prompt = build_comic_prompt(dia, weather, clima_clave)
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] === Tira Cómica Las Gaturrakas ===")
    print(f"Día: {dia} | Clima: {weather}")

    # Si se pasa una imagen manual
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        print(f"Procesando imagen provista: {sys.argv[1]}")
        process_and_register_comic(sys.argv[1])
        return

    # Si no, intenta generar vía Gemini API
    try:
        print("Llamando a Gemini API para generar el cómic del día...")
        raw_img = generate_with_gemini(prompt)
        process_and_register_comic(raw_img)
    except Exception as e:
        print(f"[AVISO] Generación automática pausada: {e}")
        print("Nota: En cuanto actives el plan Pay-as-you-go en Google AI Studio, este script correrá 100% automático cada día a las 05:00 AM.")

if __name__ == '__main__':
    main()
