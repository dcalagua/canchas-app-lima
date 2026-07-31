"""Flyer de MARCA para el community manager autónomo (CM Fase 0).

Genera una imagen cuadrada (1080x1080) lista para Instagram/Facebook, con la
FOTO real del negocio de fondo, un degradado oscuro para leer el texto, y la
identidad de Pichangol. Diseño tipo "poster": nombre grande, deporte/sede, un
gancho y un CTA de WhatsApp — todo anclado abajo, sobre la zona oscura.

Es Pillow puro (sin navegador): funciona en Railway. La FUENTE va EMPAQUETADA en
`marketing/assets/` para que el texto salga grande SIEMPRE (Railway no trae
DejaVu → si no, Pillow caería a una fuente diminuta). Fail-safe: si Pillow no
está, devuelve None y el endpoint responde igual (solo con el texto).
"""

from __future__ import annotations

import io
import os

# Paleta de marca (EBIM/Pichangol).
_BOSQUE = (20, 70, 58)      # #14463A
_BOSQUE2 = (7, 34, 27)      # más oscuro para el degradado / scrim
_LIMA = (174, 234, 148)     # #AEEA94
_WA = (37, 211, 102)        # verde WhatsApp

_DIR = os.path.dirname(os.path.abspath(__file__))
_FUENTE_BOLD = os.path.join(_DIR, "assets", "DejaVuSans-Bold.ttf")
_FUENTE_REG = os.path.join(_DIR, "assets", "DejaVuSans.ttf")
# Respaldos del sistema por si faltara el asset.
_SYS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_SYS_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(tam: int, bold: bool = True):
    from PIL import ImageFont

    for ruta in ([_FUENTE_BOLD, _SYS_BOLD] if bold else [_FUENTE_REG, _SYS_REG]):
        try:
            return ImageFont.truetype(ruta, tam)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _limpiar(t: str) -> str:
    """Quita emojis y símbolos que la fuente NO renderiza (saldrían como cuadros).
    Conserva latín, acentos y puntuación tipográfica (¡¿ – — … « »)."""
    out = "".join(c for c in (t or "") if ord(c) < 0x2190)
    return " ".join(out.split()).strip()


def _ancho(draw, texto: str, font) -> int:
    x0, _, x1, _ = draw.textbbox((0, 0), texto, font=font)
    return x1 - x0


def _envolver(draw, texto: str, font, max_ancho: int, max_lineas: int) -> list[str]:
    lineas: list[str] = []
    actual = ""
    for p in (texto or "").split():
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
    if len(lineas) == max_lineas and _ancho(draw, lineas[-1] + "…", font) <= max_ancho:
        # si quedó texto fuera, marca el corte
        pass
    return lineas


def _bajar_imagen(url: str):
    """Baja una imagen (foto del negocio) y la abre con PIL. Fail-safe → None."""
    import urllib.request

    from PIL import Image

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "PichangolBot/1.0 (+https://www.pichangol.app)"})
        with urllib.request.urlopen(req, timeout=6) as r:  # noqa: S310
            datos = r.read(8 * 1024 * 1024)
        return Image.open(io.BytesIO(datos))
    except Exception:  # noqa: BLE001
        return None


def _cover(im, W: int, H: int):
    from PIL import Image

    im = im.convert("RGB")
    iw, ih = im.size
    escala = max(W / iw, H / ih)
    nw, nh = max(1, int(iw * escala)), max(1, int(ih * escala))
    im = im.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - W) // 2, (nh - H) // 2
    return im.crop((x, y, x + W, y + H))


def _fondo(datos: dict, W: int, H: int):
    """Fondo: FOTO real del negocio con degradado oscuro (más opaco abajo, donde
    va el texto) si la hay; si no, degradado de marca."""
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
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scrim)
        for y in range(H):
            t = y / H
            # Transparente arriba → casi opaco bosque en el tercio inferior.
            a = int(min(238, max(0, (t - 0.30) / 0.70 * 250)) + 30 * t)
            sd.line([(0, y), (W, y)],
                    fill=(_BOSQUE2[0], _BOSQUE2[1], _BOSQUE2[2], min(245, a)))
        return Image.alpha_composite(base, scrim).convert("RGB")

    img = Image.new("RGB", (W, H), _BOSQUE)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(_BOSQUE[0] + (_BOSQUE2[0] - _BOSQUE[0]) * t)
        g = int(_BOSQUE[1] + (_BOSQUE2[1] - _BOSQUE[1]) * t)
        b = int(_BOSQUE[2] + (_BOSQUE2[2] - _BOSQUE[2]) * t)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    return img


def generar_flyer(datos: dict, gancho: str) -> bytes | None:
    """Devuelve el PNG (bytes) del flyer, o None si Pillow no está disponible."""
    try:
        from PIL import ImageDraw
    except Exception:  # noqa: BLE001
        return None

    W = H = 1080
    img = _fondo(datos, W, H)
    draw = ImageDraw.Draw(img)

    m = 80  # margen lateral
    nombre = _limpiar(str(datos.get("nombre") or "Academia")) or "Academia"
    deporte = _limpiar(str(datos.get("deporte") or "")).capitalize()
    sede = _limpiar(str(datos.get("sede") or ""))
    sub = "  ·  ".join(x for x in [deporte, sede] if x).upper()
    frase = _limpiar(gancho)
    if "." in frase:
        frase = frase.split(".")[0].strip()

    # Wordmark arriba-izquierda.
    draw.text((m, 62), "PICHANGOL", font=_font(44), fill=_LIMA)

    # ---- Bloque de texto ANCLADO ABAJO (sobre la zona oscura) ----
    # Se mide de abajo hacia arriba para que siempre quede pegado al pie.
    y = H - 96

    # CTA WhatsApp (pill) — lo más abajo.
    f_cta = _font(46)
    cta = "Reserva por WhatsApp"
    cta_h = 104
    draw.rounded_rectangle([m, y - cta_h, W - m, y], radius=52, fill=_WA)
    cw = _ancho(draw, cta, f_cta)
    draw.text(((W - cw) / 2, y - cta_h + 28), cta, font=f_cta, fill=(255, 255, 255))
    y -= cta_h + 34

    # Gancho (1-2 líneas, blanco, grande).
    if frase:
        f_g = _font(50, bold=False)
        gl = _envolver(draw, frase, f_g, W - 2 * m, 2)
        for ln in reversed(gl):
            y -= 62
            draw.text((m, y), ln, font=f_g, fill=(240, 245, 240))
        y -= 14

    # Nombre de la academia (grande y bold, hasta 2 líneas). Auto-encaje: baja el
    # tamaño si el nombre es largo.
    tam = 86
    while tam > 52:
        f_n = _font(tam)
        ln = _envolver(draw, nombre, f_n, W - 2 * m, 2)
        if len(ln) <= 2 and all(_ancho(draw, x, f_n) <= W - 2 * m for x in ln):
            break
        tam -= 6
    f_n = _font(tam)
    nl = _envolver(draw, nombre, f_n, W - 2 * m, 2)
    for ln in reversed(nl):
        y -= tam + 8
        draw.text((m, y), ln, font=f_n, fill=(255, 255, 255))

    # Eyebrow deporte · sede (lima) arriba del nombre.
    if sub:
        f_s = _font(38)
        y -= 52
        draw.text((m, y), sub, font=f_s, fill=_LIMA)

    # Acento lima: barrita a la izquierda del bloque (toque premium).
    draw.rounded_rectangle([m - 22, y + 6, m - 12, H - 210], radius=6, fill=_LIMA)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
