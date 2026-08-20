"""AFICHE del campeonato (opción A del director: plantilla Pillow, S/0).

Genera un póster 1080×1350 (4:5, ideal WhatsApp/IG) con la paleta del logo
nuevo: gradiente azul noche → esmeralda, nombre del torneo en grande (estilo
RALLY CHALLENGE: línea 1 blanca, línea 2 dorada), chips de INICIO / CATEGORÍA /
INSCRIPCIÓN, premios, logo del campeonato y el espacio del AUSPICIADOR.

Se sirve en `GET /c/{id}/afiche.png` y es el `og:image` de la página del
campeonato → WhatsApp muestra el afiche como vista previa del enlace.
Cuando el director dé el API de imágenes, este mismo módulo pondrá el arte
IA de fondo y esta capa de texto encima (híbrido).
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFilter

from .flyer import _bajar_imagen, _envolver, _font, _limpiar

W, H = 1080, 1350

_NAVY = (15, 27, 45)        # #0F1B2D
_NAVY_2 = (23, 42, 66)
_ESMERALDA = (14, 143, 103)  # #0E8F67
_DORADO = (217, 180, 90)     # #D9B45A
_BLANCO = (255, 255, 255)
_GRIS = (233, 238, 244)      # #E9EEF4

_ETI_DEPORTE = {
    "tenis": "TENIS", "futbol": "FÚTBOL", "padel": "PÁDEL",
    "pickleball": "PICKLEBALL", "voley": "VÓLEY", "basquet": "BÁSQUET",
    "natacion": "NATACIÓN",
}


def _fondo() -> Image.Image:
    """Gradiente vertical azul noche → esmeralda con viñeta suave."""
    img = Image.new("RGB", (W, H), _NAVY)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(_NAVY[0] + (_ESMERALDA[0] - _NAVY[0]) * t * 0.85)
        g = int(_NAVY[1] + (_ESMERALDA[1] - _NAVY[1]) * t * 0.85)
        b = int(_NAVY[2] + (_ESMERALDA[2] - _NAVY[2]) * t * 0.85)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    # Círculos decorativos tenues (pelotas), marca de la casa.
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for cx, cy, rr in [(950, 180, 210), (120, 1180, 260), (1010, 1080, 150)]:
        dd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                   outline=(255, 255, 255, 26), width=10)
        dd.line([(cx - rr, cy), (cx + rr, cy)], fill=(255, 255, 255, 20),
                width=6)
    img.paste(deco, (0, 0), deco)
    return img


def _logo_circular(img: Image.Image, url: str, cx: int, cy: int, r: int):
    """Pega el logo del campeonato en un círculo con aro dorado. Best-effort."""
    logo = _bajar_imagen(url)
    if logo is None:
        return
    logo = logo.convert("RGB").resize((r * 2, r * 2))
    mask = Image.new("L", (r * 2, r * 2), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, r * 2, r * 2], fill=255)
    img.paste(logo, (cx - r, cy - r), mask)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=_DORADO, width=8)


def generar_afiche(c: dict) -> bytes:
    """El afiche PNG del campeonato a partir de su `data` (jsonb)."""
    img = _fondo()
    d = ImageDraw.Draw(img)

    nombre = _limpiar(str(c.get("nombre") or "Campeonato"))
    auspiciador = _limpiar(str(c.get("auspiciador") or "")).strip()
    deporte = _ETI_DEPORTE.get(str(c.get("deporte") or ""), "")
    formato = ("LIGA (TABLA)" if c.get("formato") == "liga"
               else "ELIMINACIÓN DIRECTA")
    categoria = _limpiar(str(c.get("categoria") or "")).strip()
    fechas = _limpiar(str(c.get("fechas") or "")).strip()
    mon = str(c.get("moneda") or "").strip() or "S/"
    costo = float(c.get("costoInscripcion") or 0)
    premios = [_limpiar(l).strip() for l in
               str(c.get("premios") or "").split("\n") if l.strip()][:4]

    y = 64
    # Chip superior: deporte · categoría.
    chip = " · ".join(x for x in [deporte, categoria] if x)
    if chip:
        f = _font(30)
        ancho = d.textlength(chip, font=f) + 52
        x0 = (W - ancho) / 2
        d.rounded_rectangle([x0, y, x0 + ancho, y + 58], radius=29,
                            fill=None, outline=_DORADO, width=3)
        d.text((x0 + 26, y + 12), chip, font=f, fill=_DORADO)
        y += 96
    # Kicker: "TORNEO DE …".
    f = _font(34)
    kicker = f"TORNEO DE {formato}"
    d.text(((W - d.textlength(kicker, font=f)) / 2, y), kicker, font=f,
           fill=(235, 240, 246))
    y += 66

    # NOMBRE gigante (hasta 2 líneas: 1ª blanca, 2ª dorada, estilo RALLY).
    f_nom = _font(118)
    lineas = _envolver(d, nombre.upper(), f_nom, W - 140, 2)
    if any(d.textlength(l, font=f_nom) > W - 140 for l in lineas):
        f_nom = _font(92)
        lineas = _envolver(d, nombre.upper(), f_nom, W - 140, 2)
    for i, linea in enumerate(lineas):
        color = _BLANCO if i == 0 else _DORADO
        d.text(((W - d.textlength(linea, font=f_nom)) / 2, y), linea,
               font=f_nom, fill=color)
        y += f_nom.size + 10
    if auspiciador:
        f = _font(36)
        by = f"by {auspiciador}"
        d.text(((W - d.textlength(by, font=f)) / 2, y + 4), by, font=f,
               fill=_GRIS)
        y += 62
    y += 26

    # Logo del campeonato (si tiene), centrado.
    logo_url = str(c.get("logoUrl") or "").strip()
    if logo_url.startswith("http"):
        _logo_circular(img, logo_url, W // 2, y + 110, 110)
        y += 250

    # Caja de datos: INICIO / INSCRIPCIÓN (dos columnas con borde dorado).
    inscripcion = (f"{mon} {costo:.2f}" if costo > 0 else "GRATIS")
    datos = [("INICIO", fechas or "Por definir"), ("INSCRIPCIÓN", inscripcion)]
    caja_y, caja_h = y + 10, 150
    d.rounded_rectangle([70, caja_y, W - 70, caja_y + caja_h], radius=24,
                        outline=_DORADO, width=3)
    col_w = (W - 140) / 2
    for i, (eti, val) in enumerate(datos):
        cx = 70 + col_w * i + col_w / 2
        f1, f2 = _font(28), _font(44)
        d.text((cx - d.textlength(eti, font=f1) / 2, caja_y + 26), eti,
               font=f1, fill=_DORADO)
        if d.textlength(val, font=f2) > col_w - 40:
            f2 = _font(32)
        d.text((cx - d.textlength(val, font=f2) / 2, caja_y + 70), val,
               font=f2, fill=_BLANCO)
    d.line([(W / 2, caja_y + 24), (W / 2, caja_y + caja_h - 24)],
           fill=_DORADO, width=2)
    y = caja_y + caja_h + 46

    # PREMIOS.
    if premios:
        f = _font(34)
        d.text(((W - d.textlength("PREMIOS", font=f)) / 2, y), "PREMIOS",
               font=f, fill=_DORADO)
        y += 56
        f = _font(34, bold=False)
        for p in premios:
            linea = f"•  {p}"
            if d.textlength(linea, font=f) > W - 160:
                linea = linea[:60] + "…"
            d.text(((W - d.textlength(linea, font=f)) / 2, y), linea,
                   font=f, fill=_BLANCO)
            y += 50
        y += 18

    # AUSPICIA (espacio de marca, pastilla blanca).
    if auspiciador:
        f = _font(32)
        texto = f"AUSPICIA: {auspiciador.upper()}"
        ancho = d.textlength(texto, font=f) + 60
        x0 = (W - ancho) / 2
        d.rounded_rectangle([x0, y, x0 + ancho, y + 64], radius=32,
                            fill=_BLANCO)
        d.text((x0 + 30, y + 15), texto, font=f, fill=_NAVY)
        y += 100

    # Pie de marca: pastilla esmeralda + eslogan (anclado abajo).
    f = _font(34)
    marca = "Inscríbete en  Pichangol"
    py = H - 120
    ancho = d.textlength(marca, font=f) + 64
    x0 = (W - ancho) / 2
    d.rounded_rectangle([x0, py, x0 + ancho, py + 66], radius=33,
                        fill=_ESMERALDA)
    d.text((x0 + 32, py + 15), marca, font=f, fill=_BLANCO)
    f = _font(24, bold=False)
    eslogan = "Reserva, juega, repite."
    d.text(((W - d.textlength(eslogan, font=f)) / 2, py + 80), eslogan,
           font=f, fill=_GRIS)

    # Suaviza bordes duros del gradiente y exporta.
    img = img.filter(ImageFilter.SMOOTH_MORE)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
