"""Flyer de MARCA para el community manager autónomo (CM Fase 0).

Genera una imagen cuadrada (1080x1080) lista para postear en Instagram/Facebook,
con la identidad de Pichangol (verde bosque + lima) y los datos de la academia:
nombre, deporte/sede, un gancho (primera línea del copy) y un CTA de WhatsApp.

Es Pillow puro (sin navegador): funciona en Railway. Fail-safe: si Pillow o las
fuentes no están, devuelve None y el endpoint responde igual (solo con el texto).
"""

from __future__ import annotations

import io

# Paleta de marca (EBIM/Pichangol).
_BOSQUE = (20, 70, 58)      # #14463A
_BOSQUE2 = (9, 42, 34)      # más oscuro para el degradado
_LIMA = (174, 234, 148)     # #AEEA94
_CREMA = (250, 247, 242)    # #FAF7F2

_FUENTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


def _font(tam: int):
    from PIL import ImageFont

    for ruta in _FUENTES:
        try:
            return ImageFont.truetype(ruta, tam)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _bajar_imagen(url: str):
    """Baja una imagen (foto del negocio) y la abre con PIL. Fail-safe → None.
    En Railway funciona; si no hay red (tests) cae al degradado de marca."""
    import urllib.request

    from PIL import Image

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "PichangolBot/1.0 (+https://www.pichangol.app)"})
        with urllib.request.urlopen(req, timeout=6) as r:  # noqa: S310
            datos = r.read(8 * 1024 * 1024)  # tope 8 MB
        return Image.open(io.BytesIO(datos))
    except Exception:  # noqa: BLE001
        return None


def _cover(im, W: int, H: int):
    """Redimensiona + recorta al centro para CUBRIR WxH (como object-fit: cover)."""
    from PIL import Image

    im = im.convert("RGB")
    iw, ih = im.size
    escala = max(W / iw, H / ih)
    nw, nh = max(1, int(iw * escala)), max(1, int(ih * escala))
    im = im.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - W) // 2, (nh - H) // 2
    return im.crop((x, y, x + W, y + H))


def _fondo(datos: dict, W: int, H: int):
    """Fondo del flyer: la FOTO real del negocio (con scrim oscuro para leer el
    texto) si la hay y se puede bajar; si no, el degradado de marca."""
    from PIL import Image, ImageDraw

    url = ""
    fotos = datos.get("fotos")
    if isinstance(fotos, list) and fotos:
        url = str(fotos[0] or "")
    if not url.startswith("http") and str(datos.get("logo_url") or "").startswith("http"):
        url = str(datos["logo_url"])

    foto = _bajar_imagen(url) if url.startswith("http") else None
    if foto is not None:
        base = _cover(foto, W, H).convert("RGBA")
        # Scrim: gradiente bosque translúcido (más opaco abajo, donde va el texto).
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scrim)
        for y in range(H):
            a = int(50 + 175 * (y / H))  # 50 arriba → 225 abajo
            sd.line([(0, y), (W, y)],
                    fill=(_BOSQUE2[0], _BOSQUE2[1], _BOSQUE2[2], a))
        return Image.alpha_composite(base, scrim).convert("RGB")

    # Sin foto: degradado de marca bosque → bosque oscuro.
    img = Image.new("RGB", (W, H), _BOSQUE)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(_BOSQUE[0] + (_BOSQUE2[0] - _BOSQUE[0]) * t)
        g = int(_BOSQUE[1] + (_BOSQUE2[1] - _BOSQUE[1]) * t)
        b = int(_BOSQUE[2] + (_BOSQUE2[2] - _BOSQUE[2]) * t)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    return img


def _ancho(draw, texto: str, font) -> int:
    x0, _, x1, _ = draw.textbbox((0, 0), texto, font=font)
    return x1 - x0


def _envolver(draw, texto: str, font, max_ancho: int, max_lineas: int) -> list[str]:
    palabras = (texto or "").split()
    lineas: list[str] = []
    actual = ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if _ancho(draw, prueba, font) <= max_ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
        if len(lineas) >= max_lineas:
            break
    if actual and len(lineas) < max_lineas:
        lineas.append(actual)
    if len(lineas) == max_lineas and palabras:
        # marca el corte con "…" si quedó texto fuera
        if _ancho(draw, lineas[-1] + "…", font) <= max_ancho:
            lineas[-1] = lineas[-1] + "…"
    return lineas


def generar_flyer(datos: dict, gancho: str) -> bytes | None:
    """Devuelve el PNG (bytes) del flyer, o None si Pillow no está disponible."""
    try:
        from PIL import ImageDraw
    except Exception:  # noqa: BLE001
        return None

    W = H = 1080
    img = _fondo(datos, W, H)  # foto real del negocio (con scrim) o degradado
    draw = ImageDraw.Draw(img)

    margen = 90
    nombre = str(datos.get("nombre") or "Academia").strip()
    deporte = str(datos.get("deporte") or "").strip().capitalize()
    sede = str(datos.get("sede") or "").strip()
    sub = " · ".join(x for x in [deporte, sede] if x)

    # Wordmark arriba.
    f_marca = _font(46)
    draw.text((margen, 70), "PICHANGOL", font=f_marca, fill=_LIMA)

    # Nombre de la academia (grande, hasta 2 líneas).
    f_titulo = _font(96)
    lineas = _envolver(draw, nombre, f_titulo, W - 2 * margen, 2)
    y = 230
    for ln in lineas:
        draw.text((margen, y), ln, font=f_titulo, fill=(255, 255, 255))
        y += 108

    # Subtítulo deporte · sede.
    if sub:
        f_sub = _font(44)
        draw.text((margen, y + 6), sub, font=f_sub, fill=_LIMA)
        y += 70

    # Banda lima con el gancho (primera frase del copy).
    frase = (gancho or "").replace("\n", " ").strip()
    if "." in frase:
        frase = frase.split(".")[0].strip() + "."
    if frase:
        f_gancho = _font(52)
        gl = _envolver(draw, frase, f_gancho, W - 2 * margen - 60, 3)
        alto_banda = 60 + len(gl) * 66
        by = H - 320 - alto_banda
        draw.rounded_rectangle(
            [margen - 20, by, W - margen + 20, by + alto_banda],
            radius=32, fill=_LIMA)
        ty = by + 30
        for ln in gl:
            draw.text((margen + 10, ty), ln, font=f_gancho, fill=_BOSQUE2)
            ty += 66

    # CTA WhatsApp abajo.
    f_cta = _font(48)
    cta = "Reserva por WhatsApp"
    draw.rounded_rectangle(
        [margen - 20, H - 190, W - margen + 20, H - 90],
        radius=50, fill=(37, 211, 102))  # verde WhatsApp
    tw = _ancho(draw, cta, f_cta)
    draw.text(((W - tw) / 2, H - 168), cta, font=f_cta, fill=(255, 255, 255))

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
