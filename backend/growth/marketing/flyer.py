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
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        return None

    W = H = 1080
    img = Image.new("RGB", (W, H), _BOSQUE)
    draw = ImageDraw.Draw(img)

    # Degradado vertical bosque → bosque oscuro.
    for y in range(H):
        t = y / H
        r = int(_BOSQUE[0] + (_BOSQUE2[0] - _BOSQUE[0]) * t)
        g = int(_BOSQUE[1] + (_BOSQUE2[1] - _BOSQUE[1]) * t)
        b = int(_BOSQUE[2] + (_BOSQUE2[2] - _BOSQUE[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

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
