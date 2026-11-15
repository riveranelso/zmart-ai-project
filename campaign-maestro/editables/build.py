#!/usr/bin/env python3
"""Build script — Campaña Maestro «Que sean las doce ya» (cero balas al aire).
Reproducible: python3 build.py  (requiere ffmpeg, PIL, fuentes Noto Sans Bold)
- Audio 100% sintetizado (ticks de reloj + campana suave). Sin música de terceros.
- Tarjetas de cierre PIL con el mensaje exacto, legibles 2.5 s.
- Reel de venta armado desde la MAQUETA (sin muestra real todavía).
"""
import math, os, struct, subprocess, wave
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.expanduser("~/workspace/campaign-maestro")
SRC, FIN, COV, EDI = (os.path.join(ROOT, d) for d in ("src", "final", "covers", "editables"))
TMP = os.path.join(ROOT, "tmp"); os.makedirs(TMP, exist_ok=True)
FONT = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
IVORY = (237, 228, 210); CHAMP = (218, 176, 120); BG = (11, 11, 14); WHITE = (245, 245, 245)

A = os.path.join(SRC, "media-generation-meme-a-1159-v2-0-5727a044-40be-4158-a573-9a96e3356c98.mp4")
B = os.path.join(SRC, "media-generation-meme-b-tio-conteo-v2-0-5e3c2d75-8b93-4072-ab33-39fdc70567a1.mp4")
C = os.path.join(SRC, "media-generation-meme-c-filtro-v2-0-02d03593-9be5-4a84-a774-ecece10753b8.mp4")
MOCK = os.path.join(SRC, "media-generation-camisa-maestro-maqueta-0-fba704c3-c804-4f12-a187-b68f3b84a74e.webp")

def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ---------- AUDIO ----------
def make_audio(path, seconds, chime_at=None):
    sr = 44100; n = int(sr * seconds); buf = [0.0] * n
    def add(i, v):
        if 0 <= i < n: buf[i] += v
    for s in range(int(seconds)):  # tick cada segundo
        t0 = int(s * sr)
        for k in range(int(0.03 * sr)):
            add(t0 + k, 0.45 * math.sin(2 * math.pi * 1900 * k / sr) * math.exp(-k / (0.006 * sr)))
    if chime_at is not None:  # campana suave de medianoche (dos senos, decaimiento)
        t0 = int(chime_at * sr)
        for k in range(int(1.4 * sr)):
            env = math.exp(-k / (0.45 * sr))
            add(t0 + k, 0.22 * env * (math.sin(2 * math.pi * 880 * k / sr) + 0.6 * math.sin(2 * math.pi * 1318 * k / sr)))
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in buf))

# ---------- TARJETAS ----------
def card(path, lines, footer="MAESTRO · QUE SEAN LAS DOCE YA", top="MAESTRO"):
    img = Image.new("RGB", (1080, 1920), BG); d = ImageDraw.Draw(img)
    f_top = ImageFont.truetype(FONT, 44); f_main = ImageFont.truetype(FONT, 96); f_foot = ImageFont.truetype(FONT_R, 40)
    d.text((540, 300), top, font=f_top, fill=CHAMP, anchor="mm")
    y = 880
    for ln in lines:
        d.text((540, y), ln, font=f_main, fill=IVORY, anchor="mm"); y += 118
    fy = 1580
    for fl in (footer if isinstance(footer, list) else [footer]):
        d.text((540, fy), fl, font=f_foot, fill=(150, 150, 150), anchor="mm"); fy += 56
    img.save(path)

def band(img, text="MAQUETA — SIN MUESTRA REAL TODAVÍA"):
    img = img.convert("RGB"); d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, img.height - 120, img.width, img.height], fill=(0, 0, 0, 190))
    d.text((img.width // 2, img.height - 60), text, font=ImageFont.truetype(FONT, 44), fill=WHITE, anchor="mm")
    return img

def fit(img, w=1080, h=1920):
    s = max(w / img.width, h / img.height); img = img.resize((int(img.width * s), int(img.height * s)))
    x = (img.width - w) // 2; y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))

# Tarjetas de cierre
card(f"{TMP}/card-a.png", ["Este Año Nuevo,", "cero balas al aire."])
card(f"{TMP}/card-b.png", ["Que suene la música.", "Cero balas al aire."])
card(f"{TMP}/card-c.png", ["Este Año Nuevo,", "cero balas al aire."])
card(f"{TMP}/card-open.png", ["Que sean", "las doce ya"], footer="CAMISA MAESTRO — $34 + ENVÍO")
card(f"{TMP}/card-end.png", ["Camisa Maestro", "$34 + envío"], footer=["TALLAS: [EDITABLE] · PEDIDOS: [ENLACE]", "ENVÍOS DESDE: [FECHA]"])

# Stills del reel de venta desde la maqueta (con banda MAQUETA)
mock = Image.open(MOCK)
band(fit(mock.copy()), ).save(f"{TMP}/shirt-full.png")
band(fit(mock.crop((430, 90, 920, 420)).resize((1080, 726)).resize((1344, 1792)))).save(f"{TMP}/shirt-collar.png")
band(fit(mock.crop((330, 520, 1030, 880)).resize((1344, 1792)))).save(f"{TMP}/shirt-print.png")

# ---------- MEMES ----------
def meme(src, cardpng, audio_wav, out):
    run("ffmpeg", "-y", "-i", src, "-loop", "1", "-t", "2.5", "-i", cardpng, "-i", audio_wav,
        "-filter_complex",
        "[0:v]scale=1080:1920:flags=lanczos,fps=30,setsar=1[v0];"
        "[1:v]scale=1080:1920,fps=30,setsar=1[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", out)

for name, src, cp in (("a", A, "card-a.png"), ("b", B, "card-b.png"), ("c", C, "card-c.png")):
    make_audio(f"{TMP}/aud-{name}.wav", 12.5, chime_at=10.0)

meme(A, f"{TMP}/card-a.png", f"{TMP}/aud-a.wav", f"{FIN}/meme-a-1159.mp4")
meme(B, f"{TMP}/card-b.png", f"{TMP}/aud-b.wav", f"{FIN}/meme-b-tio-conteo.mp4")
meme(C, f"{TMP}/card-c.png", f"{TMP}/aud-c.wav", f"{FIN}/meme-c-filtro.mp4")

# ---------- REEL DE VENTA (13.5 s) ----------
segs = [("card-open.png", 2.5, "1"), ("shirt-full.png", 3.5, "z"), ("shirt-collar.png", 3.0, "z"),
        ("shirt-print.png", 2.5, "z"), ("card-end.png", 2.0, "1")]
inputs, filt = [], []
for i, (png, dur, mode) in enumerate(segs):
    if mode == "z":  # una sola imagen: zoompan genera el segmento con d=<frames>
        inputs += ["-i", f"{TMP}/{png}"]
    else:
        inputs += ["-loop", "1", "-t", str(dur), "-i", f"{TMP}/{png}"]
    if mode == "z":
        filt.append(f"[{i}:v]scale=2160:3840,zoompan=z='1+0.06*on/{int(dur*30)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(dur*30)}:s=1080x1920:fps=30,setsar=1[v{i}]")
    else:
        filt.append(f"[{i}:v]scale=1080:1920,fps=30,setsar=1[v{i}]")
make_audio(f"{TMP}/aud-venta.wav", 13.5, chime_at=11.5)
run("ffmpeg", "-y", *inputs, "-i", f"{TMP}/aud-venta.wav", "-filter_complex",
    ";".join(filt) + ";" + "".join(f"[v{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[v]",
    "-map", "[v]", "-map", f"{len(segs)}:a", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "128k", "-shortest", f"{FIN}/reel-venta-camisa.mp4")

# ---------- PORTADAS ----------
run("ffmpeg", "-y", "-ss", "1", "-i", f"{FIN}/meme-a-1159.mp4", "-frames:v", "1", "-q:v", "3", f"{COV}/portada-meme-a.jpg")
run("ffmpeg", "-y", "-ss", "1", "-i", f"{FIN}/meme-b-tio-conteo.mp4", "-frames:v", "1", "-q:v", "3", f"{COV}/portada-meme-b.jpg")
run("ffmpeg", "-y", "-ss", "0.8", "-i", f"{FIN}/meme-c-filtro.mp4", "-frames:v", "1", "-q:v", "3", f"{COV}/portada-meme-c.jpg")
Image.open(f"{TMP}/shirt-full.png").save(f"{COV}/portada-reel-venta.jpg", quality=90)

# Maqueta marcada (entregable aparte)
band(fit(Image.open(MOCK))).save(os.path.join(ROOT, "final", "camisa-maestro-MAQUETA.png"))

# ---------- 4:5 (meme A, el más claro sin sonido) ----------
run("ffmpeg", "-y", "-i", f"{FIN}/meme-a-1159.mp4", "-vf", "crop=1080:1350:0:250",
    "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", f"{FIN}/meme-a-1159-4x5.mp4")
print("BUILD OK")
