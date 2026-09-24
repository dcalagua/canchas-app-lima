"""Portada de Facebook/redes de Pichangol (1640×720 = 2× de 820×360: escritorio
recorta 24 px arriba/abajo, móvil muestra el centro 640×360). Se corre desde la
raíz del repo con Pillow: `python tool/portada_facebook.py`. Fuente DM Sans (OFL)
en `tool/fonts/`; logos de `backend/growth/static/brand/`."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
S = os.path.join(os.path.dirname(os.path.abspath(__file__)))  # tool/
W, H = 1640, 720  # 2× de 820×360: escritorio recorta 24 px arriba/abajo, móvil muestra el centro 640×360
VERDE, VERDE_OSC, LIMA, NARANJA, NOCHE = (11, 138, 62), (6, 122, 56), (124, 181, 24), (242, 140, 40), (10, 27, 61)
def F(peso, tam): return ImageFont.truetype(os.path.join(S, "fonts", f"DMSans-{peso}.ttf"), tam)

# Fondo: degradado diagonal verde oscuro → verde con brillo lima a la derecha
img = Image.new("RGB", (W, H), VERDE)
px = img.load()
for x in range(W):
    for y in range(H):
        t = (x / W) * 0.75 + (y / H) * 0.25
        r = int(VERDE_OSC[0] + (VERDE[0] - VERDE_OSC[0]) * t)
        g = int(VERDE_OSC[1] + (VERDE[1] - VERDE_OSC[1]) * t)
        b = int(VERDE_OSC[2] + (VERDE[2] - VERDE_OSC[2]) * t)
        px[x, y] = (r, g, b)
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([1050, -250, 1900, 700], fill=(LIMA[0], LIMA[1], LIMA[2], 90))
glow = glow.filter(ImageFilter.GaussianBlur(160))
img = Image.alpha_composite(img.convert("RGBA"), glow)

# Motivo de cancha (líneas blancas muy suaves): medio campo a la izquierda + círculo central
lin = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ld = ImageDraw.Draw(lin)
a = (255, 255, 255, 34)
ld.rectangle([-40, 40, 1120, H - 40], outline=a, width=6)           # perímetro
ld.rectangle([-40, 190, 260, H - 190], outline=a, width=6)          # área grande
ld.rectangle([-40, 280, 120, H - 280], outline=a, width=6)          # área chica
ld.ellipse([1120 - 170, H // 2 - 170, 1120 + 170, H // 2 + 170], outline=a, width=6)  # círculo central
ld.line([1120, 40, 1120, H - 40], fill=a, width=6)
ld.ellipse([1120 - 10, H // 2 - 10, 1120 + 10, H // 2 + 10], fill=a)
img = Image.alpha_composite(img, lin)
d = ImageDraw.Draw(img)

# Marca (izquierda, dentro del área segura de móvil: x ≥ 180)
x0 = 210
def en_disco(ruta, diam, margen):
    """Logo (fondo blanco) recortado en un disco blanco: sin esquinas del cuadrado."""
    lg = Image.open(ruta).convert("RGBA").resize((diam - 2 * margen, diam - 2 * margen), Image.LANCZOS)
    disco = Image.new("RGBA", (diam, diam), (255, 255, 255, 255))
    disco.paste(lg, (margen, margen), lg)
    mask = Image.new("L", (diam * 4, diam * 4), 0); ImageDraw.Draw(mask).ellipse([0, 0, diam * 4 - 1, diam * 4 - 1], fill=255)
    disco.putalpha(mask.resize((diam, diam), Image.LANCZOS))
    return disco
disco = en_disco("backend/growth/static/brand/logo_pin.png", 124, 14)
img.paste(disco, (x0, 96), disco)
d.text((x0 + 144, 104), "Pichangol", font=F("Bold", 66), fill=(255, 255, 255))
d.text((x0 + 146, 178), "Reserva tu cancha fácil y rápido, donde te encuentres", font=F("Medium", 26), fill=(255, 255, 255, 215))

# Titular + bajada
d.text((x0, 272), "Reserva, juega, repite.", font=F("Bold", 84), fill=(255, 255, 255))
d.text((x0, 388), "Canchas de fútbol, tenis, pádel y pickleball cerca de ti.", font=F("Medium", 34), fill=(255, 255, 255, 230))
d.text((x0, 434), "Elige tu horario, paga en línea y listo. Sin llamadas, sin esperas.", font=F("Regular", 30), fill=(255, 255, 255, 205))

# Pastillas
capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); cd = ImageDraw.Draw(capa)
def pastilla(x, y, txt, f, relleno, color, borde=None, pad=(26, 12)):
    w = cd.textlength(txt, font=f); h = f.size
    cd.rounded_rectangle([x, y, x + w + pad[0] * 2, y + h + pad[1] * 2], radius=(h + pad[1] * 2) // 2, fill=relleno, outline=borde, width=2)
    cd.text((x + pad[0], y + pad[1] - 2), txt, font=f, fill=color)
    return x + w + pad[0] * 2 + 14
x = x0; y = 510
for t in ("Fútbol", "Tenis", "Pádel", "Pickleball", "Vóley", "Básquet"):
    x = pastilla(x, y, t, F("Medium", 27), (255, 255, 255, 28), (255, 255, 255), borde=(255, 255, 255, 110))
x = pastilla(x0, 578, "Perú · Ecuador · Bolivia", F("Medium", 27), (255, 255, 255), NOCHE)
x = pastilla(x, 578, "Descarga la app en Google Play", F("Medium", 27), NARANJA, (255, 255, 255))
img = Image.alpha_composite(img, capa); d = ImageDraw.Draw(img)

# Derecha: logo grande en disco blanco + dominio (fuera de donde cae la foto de perfil)
R = 178; cx, cy = 1335, 322
sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(sombra).ellipse([cx - R, cy - R + 18, cx + R, cy + R + 18], fill=(0, 0, 0, 90))
img = Image.alpha_composite(img, sombra.filter(ImageFilter.GaussianBlur(30))); d = ImageDraw.Draw(img)
big = en_disco("backend/growth/static/brand/logo_pichangol.png", 2 * R, 38)
img.paste(big, (cx - R, cy - R), big)
f = F("Bold", 34); t = "www.pichangol.app"; w = d.textlength(t, font=f)
d.text((cx - w / 2, cy + R + 34), t, font=f, fill=(255, 255, 255))

out = img.convert("RGB")
out.save("backend/growth/static/brand/portada_facebook.png", optimize=True)
out.resize((820, 360), Image.LANCZOS).save("backend/growth/static/brand/portada_facebook_820.png", optimize=True)
print("ok", out.size)
