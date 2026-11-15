#!/usr/bin/env python3
"""Comercial Camisa Maestro: clip real de Talento de Barrio + camisa + cierre.
9:16 1080x1920. Audio: el del clip + ticks/campana sintetizados (sin música de terceros).
Uso: python3 build-comercial.py  (desde la carpeta campaign-maestro)
"""
import math, os, struct, subprocess, wave
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.expanduser("~/workspace/campaign-maestro")
TMP = f"{BASE}/tmp-comercial"; os.makedirs(TMP, exist_ok=True)
FONT = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
CAMISA = f"{BASE}/camisa"
ESTUDIO = f"{CAMISA}/mockup-estudio.webp"
PUESTA = f"{CAMISA}/mockup-puesta.webp"

def sh(*args):
    subprocess.run(args, check=True)

# --- stills normalizados 2160x3840 para zoompan ---
def fill_canvas(src, out, x_bias=0.5):
    im = Image.open(src).convert("RGB")
    s = max(2160 / im.width, 3840 / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)))
    x = int((im.width - 2160) * x_bias); y = (im.height - 3840) // 2
    im.crop((x, y, x + 2160, y + 3840)).save(out)

fill_canvas(ESTUDIO, f"{TMP}/com-estudio.png")
fill_canvas(PUESTA, f"{TMP}/com-puesta.png", x_bias=0.30)
# detalle del estampado desde el mockup de estudio
im = Image.open(ESTUDIO).convert("RGB")
w, h = im.size
im.crop((int(w * 0.18), int(h * 0.30), int(w * 0.82), int(h * 0.62))).resize((2160, 3840)).save(f"{TMP}/com-detalle.png")

# --- tarjeta final ---
def card(path, lines, footer):
    img = Image.new("RGB", (1080, 1920), (11, 11, 14)); d = ImageDraw.Draw(img)
    d.text((540, 150), "MAESTRO", font=ImageFont.truetype(FONT, 54), fill=(237, 196, 145), anchor="mm")
    sizes = [104, 104] if len(lines) == 2 else [96] * len(lines)
    total = sum(sizes) + (len(lines) - 1) * 26; y = 960 - total // 2
    for t, s in zip(lines, sizes):
        d.text((540, y + s // 2), t, font=ImageFont.truetype(FONT, s), fill=(245, 240, 230), anchor="mm"); y += s + 26
    fy = 1580
    for fl in (footer if isinstance(footer, list) else [footer]):
        d.text((540, fy), fl, font=ImageFont.truetype(FONT, 40), fill=(150, 150, 150), anchor="mm"); fy += 56
    img.save(path)

card(f"{TMP}/card-final.png", ["Este Año Nuevo,", "cero balas al aire."],
     footer=["CAMISA MAESTRO — $34 + ENVÍO", "PEDIDOS: [ENLACE] · TALLAS: [EDITABLE]"])

# --- audio sintetizado para la parte sin clip (11.5 s) ---
def make_audio(path, seconds, chime_at, sr=44100):
    n = int(seconds * sr); buf = []
    for i in range(n):
        t = i / sr; v = 0.0
        ph = t - math.floor(t)
        if ph < 0.03: v += 0.20 * math.sin(2 * math.pi * 1900 * t) * (1 - ph / 0.03)
        ct = t - chime_at
        if 0 <= ct < 1.6:
            env = math.exp(-3.0 * ct)
            v += 0.30 * env * (math.sin(2 * math.pi * 1318.5 * t) + 0.6 * math.sin(2 * math.pi * 1760.0 * t))
        buf.append(struct.pack("<h", int(max(-1, min(1, v)) * 32767)))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(b"".join(buf))

make_audio(f"{TMP}/aud-resto.wav", 11.5, 8.5)

# --- ensamblaje ---
fc = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2,eq=brightness=-0.18[bg];"
      "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,setsar=1[v0];"
      "[1:v]zoompan=z='1+0.05*on/90':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=90:s=1080x1920:fps=30,setsar=1[v1];"
      "[2:v]zoompan=z='1+0.05*on/90':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=90:s=1080x1920:fps=30,setsar=1[v2];"
      "[3:v]zoompan=z='1+0.04*on/75':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=75:s=1080x1920:fps=30,setsar=1[v3];"
      "[4:v]scale=1080:1920,fps=30,setsar=1[v4];"
      "[v0][v1][v2][v3][v4]concat=n=5:v=1:a=0[v];"
      "[0:a]aresample=44100[ca];[5:a]aresample=44100[sa];[ca][sa]concat=n=2:v=0:a=1[a]")
sh("ffmpeg", "-y", "-v", "error",
   "-i", f"{BASE}/clip/que-sean-las-12-ya.mp4",
   "-i", f"{TMP}/com-estudio.png", "-i", f"{TMP}/com-puesta.png", "-i", f"{TMP}/com-detalle.png",
   "-loop", "1", "-t", "3", "-i", f"{TMP}/card-final.png",
   "-i", f"{TMP}/aud-resto.wav",
   "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
   "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
   f"{BASE}/final/comercial-camisa-maestro.mp4")
print("COMERCIAL OK")
