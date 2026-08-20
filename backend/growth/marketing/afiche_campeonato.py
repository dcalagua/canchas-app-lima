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

from . import arte_ia
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


def _cover(im: Image.Image) -> Image.Image:
    """Recorta/escala la imagen para llenar exactamente W×H (sin deformar)."""
    esc = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * esc) + 1, int(im.height * esc) + 1))
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _con_velo(foto: Image.Image) -> Image.Image:
    """Foto → fondo del afiche: cover a W×H + velo azul noche + degradados
    arriba/abajo para que la tipografía siempre se lea."""
    img = _cover(foto)
    velo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dv = ImageDraw.Draw(velo)
    # Tinte navy general (integra la foto a la marca).
    dv.rectangle([0, 0, W, H], fill=(_NAVY[0], _NAVY[1], _NAVY[2], 96))
    # Degradado superior e inferior (zonas de texto).
    for i in range(430):
        a = int(215 * (1 - i / 430))
        dv.line([(0, i), (W, i)], fill=(_NAVY[0], _NAVY[1], _NAVY[2], a))
    for i in range(520):
        a = int(230 * (1 - i / 520))
        yy = H - 1 - i
        dv.line([(0, yy), (W, yy)], fill=(_NAVY[0], _NAVY[1], _NAVY[2], a))
    img = img.convert("RGB")
    img.paste(velo, (0, 0), velo)
    return img


def _fondo_propio(url: str) -> Image.Image | None:
    """FOTO DEL ORGANIZADOR como fondo del afiche (la eligió en la app:
    'Cambiar fondo del afiche' → 'Usar una foto mía'). Best-effort."""
    foto = _bajar_imagen(url)
    return None if foto is None else _con_velo(foto.convert("RGB"))


def _fondo_ia(deporte: str, esperar: bool = True,
              variante: int = 0, tema: str = "") -> Image.Image | None:
    """Fondo FOTOGRÁFICO generado por IA (si hay proveedor configurado).
    [variante] cambia el encuadre ('Generar OTRO arte' en la app).
    None = usar el gradiente de marca.
    Con esperar=False NUNCA bloquea: usa solo la caché y, si falta, dispara
    la generación en segundo plano (el robot de WhatsApp que baja el
    og:image corta a los ~5 s; mejor gradiente al instante que nada)."""
    if esperar:
        foto = arte_ia.fondo_para(deporte, variante, tema)
    else:
        foto = arte_ia.fondo_cacheado(deporte, variante, tema)
        if foto is None:
            arte_ia.precalentar(deporte, variante, tema)
    return None if foto is None else _con_velo(foto)


def _tile_logo(img: Image.Image, im: Image.Image, x: float, y: float,
               tw: int, th: int) -> None:
    """Un logo de auspiciador "contain" dentro de un tile blanco redondeado."""
    tile = Image.new("RGB", (tw, th), _BLANCO)
    esc = min((tw - 22) / im.width, (th - 22) / im.height)
    lw = max(1, int(im.width * esc))
    lh = max(1, int(im.height * esc))
    tile.paste(im.resize((lw, lh)), ((tw - lw) // 2, (th - lh) // 2))
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tw - 1, th - 1],
                                           radius=18, fill=255)
    img.paste(tile, (int(x), int(y)), mask)


def generar_afiche(c: dict, esperar_ia: bool = True) -> bytes:
    """El afiche PNG del campeonato a partir de su `data` (jsonb). Con
    proveedor de imágenes configurado (env en Railway), el fondo es una FOTO
    deportiva generada por IA (cacheada por deporte); si no, el gradiente de
    marca de siempre. Los textos SIEMPRE los pone Pillow (exactos).
    esperar_ia=False (og:image) responde al instante con lo que haya.
    Prioridad del fondo: foto PROPIA del organizador (aficheFondoUrl) →
    arte IA en su variante (aficheVariante) → gradiente de marca."""
    fondo_url = str(c.get("aficheFondoUrl") or "").strip()
    try:
        variante = int(c.get("aficheVariante") or 0)
    except (TypeError, ValueError):
        variante = 0
    tema = str(c.get("aficheTema") or "").strip()
    img = _fondo_propio(fondo_url) if fondo_url.startswith("http") else None
    if img is None:
        img = _fondo_ia(str(c.get("deporte") or ""), esperar_ia, variante,
                        tema)
    img = img or _fondo()
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
    logos_ausp = [str(u) for u in (c.get("auspiciadoresLogos") or [])
                  if str(u).startswith("http")]
    # Con logos de auspiciadores abajo hay menos alto libre: máx 3 premios.
    premios = [_limpiar(l).strip() for l in
               str(c.get("premios") or "").split("\n")
               if l.strip()][:3 if logos_ausp else 4]

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

    # Logo del campeonato (si tiene), centrado. Con logos de auspiciadores
    # abajo, va un poco más chico para que todo respire sin encimarse.
    logo_url = str(c.get("logoUrl") or "").strip()
    if logo_url.startswith("http"):
        r_logo = 80 if logos_ausp else 110
        _logo_circular(img, logo_url, W // 2, y + r_logo + 15, r_logo)
        y += r_logo * 2 + 40

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

    # PREMIOS y AUSPICIAN. Con logos de auspiciadores va en DOS COLUMNAS
    # (premios izquierda, logos derecha) DENTRO del flujo — antes los tiles
    # iban anclados a una altura fija y con mucho contenido se encimaban
    # sobre los premios. Sin logos, premios centrados como siempre.
    logos_img = []
    for u in logos_ausp[:4]:
        im_l = _bajar_imagen(u)
        if im_l is not None:
            logos_img.append(im_l.convert("RGB"))
    if premios and not logos_img:
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
    elif premios or logos_img:
        y_izq = y_der = y
        if premios:
            f = _font(34)
            d.text((100, y_izq), "PREMIOS", font=f, fill=_DORADO)
            y_izq += 56
            f = _font(28, bold=False)
            for p in premios:
                linea = f"•  {p}"
                corto = False
                while len(linea) > 6 and d.textlength(linea, font=f) > 520:
                    linea = linea[:-1]
                    corto = True
                d.text((100, y_izq), linea + ("…" if corto else ""),
                       font=f, fill=_BLANCO)
                y_izq += 46
        if logos_img:
            cx = 810 if premios else W // 2
            f = _font(28)
            eti = "AUSPICIAN"
            d.text((cx - d.textlength(eti, font=f) / 2, y_der), eti,
                   font=f, fill=_DORADO)
            y_der += 46
            tw, th, sep = 170, 88, 12
            por_fila = 2 if premios else min(len(logos_img), 4)
            i = 0
            while i < len(logos_img):
                fila = logos_img[i:i + por_fila]
                total = len(fila) * tw + (len(fila) - 1) * sep
                x = cx - total / 2
                for im_l in fila:
                    _tile_logo(img, im_l, x, y_der, tw, th)
                    x += tw + sep
                y_der += th + sep
                i += por_fila
        y = max(y_izq, y_der) + 18

    # AUSPICIA (espacio de marca, pastilla blanca). Si hay LOGOS, la fila de
    # tiles de abajo ya es el espacio de marca y la pastilla sobra.
    if auspiciador and not logos_ausp:
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
