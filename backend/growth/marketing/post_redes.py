"""Publicaciones de la PÁGINA DE FACEBOOK DE PICHANGOL desde la torre.

Pedido del director (sep-2026): "una variante con fotos reales de canchas para
mi primera publicación… y que en el admin haya un agente que mueva las redes".
Fase 1 (esto): el operador elige un local, marca hasta 4 FOTOS REALES (las que
el dueño subió al bucket `canchas/`, o sube desde su computadora), una plantilla
de texto y la torre COMPONE la pieza (1080×1080 o 1200×630, Pillow, DM Sans,
paleta del logo) con vista previa, descarga y **Publicar en Facebook** (Graph
API `/{page}/photos` con el archivo en multipart: no hace falta URL pública).
Fase 2 (siguiente): calendario + IA de copy con el motor del CM (`cm.py`).

Credenciales: `config.FB_PAGE_ID` + `config.FB_PAGE_TOKEN` (Railway). Sin
ellas, componer y descargar siguen funcionando; publicar responde
`sin_credenciales` con la guía.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import config
from db.store import stores

_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(os.path.dirname(_DIR), "static", "brand")
VERDE, VERDE_OSC, LIMA, NARANJA, NOCHE = (11, 138, 62), (6, 122, 56), (124, 181, 24), (242, 140, 40), (10, 27, 61)
FORMATOS = {"cuadrado": (1080, 1080), "horizontal": (1200, 630), "historia": (1080, 1920)}
MAX_FOTOS = 4
MAX_BYTES = 12 * 1024 * 1024

# Plantillas de la primera etapa. `{local}`, `{zona}`, `{deportes}`, `{precio}`
# se rellenan con la cancha elegida; el operador puede editar todo antes de publicar.
PLANTILLAS = {
    "lanzamiento": {
        "nombre": "Lanzamiento",
        "titulo": "¡Llegó Pichangol!",
        "subtitulo": "Reserva tu cancha fácil y rápido, donde te encuentres.",
        "texto": ("🎾⚽ ¡Llegó Pichangol! Reserva canchas de fútbol, tenis, pádel y pickleball en minutos, "
                  "desde tu celular o en www.pichangol.app.\n\n📍 Ya puedes reservar en {local} ({zona}).\n"
                  "✅ Horarios en vivo · Pago en línea · Confirmación al instante.\n\n"
                  "👉 Descarga la app: https://play.google.com/store/apps/details?id=pe.ebim.pichangol\n"
                  "#Pichangol #ReservaJuegaRepite #{deporte_tag} #Lima"),
    },
    "nuevo_local": {
        "nombre": "Nuevo local",
        "titulo": "Nuevo en Pichangol",
        "subtitulo": "{local} · {zona}",
        "texto": ("🆕 {local} ya está en Pichangol.\n{deportes} · desde {precio} la hora.\n"
                  "Elige tu horario y reserva en segundos: {url}\n\n#Pichangol #ReservaJuegaRepite #{deporte_tag}"),
    },
    "promo": {
        "nombre": "Promoción",
        "titulo": "Juega esta semana",
        "subtitulo": "{local} · desde {precio} la hora",
        "texto": ("🔥 ¿Ya armaste la pichanga? {local} tiene horarios libres esta semana desde {precio} la hora.\n"
                  "Reserva en la app o en {url} y paga en línea.\n\n#Pichangol #{deporte_tag} #Lima"),
    },
    "libre": {"nombre": "Texto libre", "titulo": "", "subtitulo": "", "texto": ""},
}


# ── fuentes / marca ───────────────────────────────────────────────────────────
def _font(peso: str, tam: int):
    from PIL import ImageFont
    for ruta in (os.path.join(_DIR, "assets", f"DMSans-{peso}.ttf"), os.path.join(_DIR, "assets", "DejaVuSans-Bold.ttf" if peso == "Bold" else "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(ruta, tam)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _limpiar(t: str) -> str:
    """Sin emojis en la IMAGEN (la fuente no los tiene); en el texto del post sí van."""
    return " ".join("".join(c for c in (t or "") if ord(c) < 0x2190).split()).strip()


def _logo_disco(diam: int):
    from PIL import Image, ImageDraw
    ruta = os.path.join(_STATIC, "logo_pin.png")
    lg = Image.open(ruta).convert("RGBA").resize((diam - 2 * (diam // 9), diam - 2 * (diam // 9)), Image.LANCZOS)
    disco = Image.new("RGBA", (diam, diam), (255, 255, 255, 255))
    disco.paste(lg, (diam // 9, diam // 9), lg)
    mask = Image.new("L", (diam * 4, diam * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diam * 4 - 1, diam * 4 - 1], fill=255)
    disco.putalpha(mask.resize((diam, diam), Image.LANCZOS))
    return disco


# ── fotos ─────────────────────────────────────────────────────────────────────
def _abrir_url(url: str) -> bytes:
    """Bytes de una foto: URL https (bucket del app, etc.) o data:image (subida
    desde la computadora del operador). Tope de tamaño; nunca lanza hacia arriba
    sin contexto."""
    u = (url or "").strip()
    if u.startswith("data:image/"):
        try:
            return base64.b64decode(u.split(",", 1)[1])
        except Exception as e:  # noqa: BLE001
            raise ValueError("Imagen adjunta inválida.") from e
    if not u.startswith("https://"):
        raise ValueError("Solo se aceptan fotos https o adjuntas.")
    req = urllib.request.Request(u, headers={"User-Agent": "Pichangol-Torre/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read(MAX_BYTES + 1)


def _cargar(urls: list[str]):
    from PIL import Image, ImageOps
    out = []
    for u in urls[:MAX_FOTOS]:
        raw = _abrir_url(u)
        if len(raw) > MAX_BYTES:
            raise ValueError("Una foto pesa más de 12 MB.")
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im).convert("RGB")
        out.append(im)
    if not out:
        raise ValueError("Elige al menos una foto.")
    return out


def _recortar(im, w: int, h: int):
    """Recorte centrado que llena w×h (cover)."""
    from PIL import ImageOps
    return ImageOps.fit(im, (w, h), method=3, centering=(0.5, 0.45))


# ── composición ───────────────────────────────────────────────────────────────
MIME = "image/jpeg"
EXTENSION = "jpg"


def componer(fotos_urls: list[str], titulo: str, subtitulo: str = "", pie: str = "www.pichangol.app",
             formato: str = "cuadrado", etiqueta: str = "") -> bytes:
    """JPEG de la publicación: fotos reales en collage + franja de marca abajo con
    título, subtítulo y pie; logo en disco arriba a la izquierda; etiqueta
    (p. ej. "Nuevo") arriba a la derecha."""
    from PIL import Image, ImageDraw, ImageFilter
    W, H = FORMATOS.get(formato, FORMATOS["cuadrado"])
    fotos = _cargar(fotos_urls)
    n = len(fotos)
    img = Image.new("RGB", (W, H), VERDE_OSC)
    gap = 6
    # Zona de fotos: todo el lienzo; el texto va sobre un degradado inferior.
    if n == 1:
        img.paste(_recortar(fotos[0], W, H), (0, 0))
    elif n == 2:
        w1 = (W - gap) // 2
        img.paste(_recortar(fotos[0], w1, H), (0, 0))
        img.paste(_recortar(fotos[1], W - w1 - gap, H), (w1 + gap, 0))
    elif n == 3:
        w1 = int(W * 0.62)
        h2 = (H - gap) // 2
        img.paste(_recortar(fotos[0], w1, H), (0, 0))
        img.paste(_recortar(fotos[1], W - w1 - gap, h2), (w1 + gap, 0))
        img.paste(_recortar(fotos[2], W - w1 - gap, H - h2 - gap), (w1 + gap, h2 + gap))
    else:
        w1 = (W - gap) // 2
        h1 = (H - gap) // 2
        pos = [(0, 0), (w1 + gap, 0), (0, h1 + gap), (w1 + gap, h1 + gap)]
        for k, f in enumerate(fotos[:4]):
            img.paste(_recortar(f, W - w1 - gap if k % 2 else w1, H - h1 - gap if k >= 2 else h1), pos[k])
    img = img.convert("RGBA")
    # Degradado inferior para legibilidad (más alto cuanto más texto).
    alto_txt = int(H * (0.40 if formato != "historia" else 0.30))
    # Degradado como columna de 1 px escalada (sin bucle por píxel: en el CPU
    # compartido de Railway el bucle + PNG optimizado tardaban ~1 minuto).
    col = Image.new("L", (1, alto_txt))
    col.putdata([int(235 * (y / alto_txt) ** 1.3) for y in range(alto_txt)])
    grad = Image.new("RGBA", (W, alto_txt), (6, 60, 30, 255))
    grad.putalpha(col.resize((W, alto_txt)))
    img.alpha_composite(grad, (0, H - alto_txt))
    d = ImageDraw.Draw(img)
    # Marca arriba a la izquierda.
    m = int(W * 0.04)
    disco = _logo_disco(int(W * 0.085))
    img.paste(disco, (m, m), disco)
    d.text((m + disco.width + int(W * 0.015), m + disco.height * 0.16), "Pichangol", font=_font("Bold", int(W * 0.05)), fill=(255, 255, 255),
           stroke_width=2, stroke_fill=(0, 0, 0, 90))
    # Etiqueta arriba a la derecha.
    et = _limpiar(etiqueta)
    if et:
        f = _font("Bold", int(W * 0.03))
        tw = d.textlength(et, font=f)
        px, py = int(W * 0.028), int(W * 0.014)
        x1 = W - m
        d.rounded_rectangle([x1 - tw - 2 * px, m, x1, m + f.size + 2 * py], radius=(f.size + 2 * py) // 2, fill=NARANJA)
        d.text((x1 - tw - px, m + py - 1), et, font=f, fill=(255, 255, 255))
    # Texto inferior.
    y = H - alto_txt + int(alto_txt * 0.30)
    tit = _limpiar(titulo)
    if tit:
        f = _font("Bold", int(W * 0.078))
        for linea in _envolver(d, tit, f, W - 2 * m)[:2]:
            d.text((m, y), linea, font=f, fill=(255, 255, 255))
            y += int(f.size * 1.12)
    sub = _limpiar(subtitulo)
    if sub:
        f = _font("Medium", int(W * 0.034))
        for linea in _envolver(d, sub, f, W - 2 * m)[:2]:
            d.text((m, y + 6), linea, font=f, fill=(255, 255, 255, 235))
            y += int(f.size * 1.35)
    pie_t = _limpiar(pie)
    if pie_t:
        f = _font("Bold", int(W * 0.03))
        tw = d.textlength(pie_t, font=f)
        px, py = int(W * 0.024), int(W * 0.012)
        d.rounded_rectangle([m, H - m - f.size - 2 * py, m + tw + 2 * px, H - m], radius=(f.size + 2 * py) // 2, fill=(255, 255, 255))
        d.text((m + px, H - m - f.size - py - 1), pie_t, font=f, fill=NOCHE)
    out = io.BytesIO()
    # JPEG (no PNG): con fotos reales el PNG pesaba 1,5-2 MB y tardaba decenas
    # de segundos en codificarse y viajar; Facebook publica JPEG igual.
    img.convert("RGB").save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out.getvalue()


def _envolver(d, texto: str, f, ancho: int) -> list[str]:
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if d.textlength(prueba, font=f) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


# ── datos para la torre ──────────────────────────────────────────────────────
def rellenar(plantilla: str, cancha: dict | None, campo: str) -> str:
    base = PLANTILLAS.get(plantilla, PLANTILLAS["libre"]).get(campo, "")
    c = cancha or {}
    sim = str(c.get("moneda") or "S/")
    try:
        precio = f"{sim} {float(c.get('precio_hora') or 0):.0f}"
    except (TypeError, ValueError):
        precio = ""
    deps = [str(x) for x in (c.get("deportes") or ([c["deporte"]] if c.get("deporte") else []))]
    nombres = {"futbol": "Fútbol", "tenis": "Tenis", "padel": "Pádel", "pickleball": "Pickleball", "voley": "Vóley", "basquet": "Básquet", "futsal": "Futsal"}
    base_url = (config.PUBLIC_BASE_URL or "https://www.pichangol.app").rstrip("/")
    valores = {
        "local": (c.get("club") or c.get("nombre") or "tu cancha").strip(),
        "zona": (c.get("barrio") or c.get("distrito") or "").strip() or "tu zona",
        "deportes": " · ".join(nombres.get(x, x.capitalize()) for x in deps) or "Canchas",
        "deporte_tag": nombres.get(deps[0], "Deporte").replace("á", "a").replace("ó", "o").replace("ú", "u") if deps else "Deporte",
        "precio": precio or "",
        "url": f"{base_url}/reservar/{c['id']}" if c.get("id") else base_url,
    }
    try:
        return base.format(**valores)
    except (KeyError, IndexError, ValueError):
        return base


# ── Facebook ─────────────────────────────────────────────────────────────────
def configurado() -> bool:
    return bool(config.FB_PAGE_ID and config.FB_PAGE_TOKEN)


def _graph_multipart(path: str, campos: dict, archivo: tuple[str, bytes, str] | None) -> dict:
    """POST multipart a Graph (foto como archivo `source`). Devuelve {ok, data|error}."""
    base = f"{config.META_GRAPH_BASE}/{config.META_GRAPH_VERSION}"
    limite = "----PichangolTorre" + uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
    if archivo:
        nombre, datos, ct = archivo
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"{nombre}\"\r\nContent-Type: {ct}\r\n\r\n".encode("utf-8") + datos + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode("utf-8"))
    cuerpo = b"".join(partes)
    req = urllib.request.Request(f"{base}/{path.lstrip('/')}", data=cuerpo, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={limite}", "Content-Length": str(len(cuerpo))})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict) and data.get("error"):
            return {"ok": False, "error": str(data["error"].get("message"))[:300]}
        return {"ok": True, "data": data}
    except urllib.error.HTTPError as e:
        try:
            cuerpo_e = e.read().decode("utf-8", "ignore")
            j = json.loads(cuerpo_e)
            detalle = str(j["error"].get("message") or cuerpo_e) if isinstance(j, dict) and j.get("error") else cuerpo_e
        except Exception:  # noqa: BLE001
            detalle = ""
        return {"ok": False, "error": f"HTTP {e.code}: {detalle[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def _graph_get(path: str, params: dict) -> dict:
    from marketing import redes
    return redes._graph(path, params)


def estado_pagina() -> dict:
    """¿Hay credenciales? ¿A qué página apuntan? (nombre y enlace, sin exponer el token)."""
    if not configurado():
        return {"configurado": False, "page_id": "", "nombre": "", "link": ""}
    r = _graph_get(config.FB_PAGE_ID, {"fields": "name,link", "access_token": config.FB_PAGE_TOKEN})
    if not r.get("ok"):
        return {"configurado": True, "page_id": config.FB_PAGE_ID, "nombre": "", "link": "", "error": r.get("error")}
    d = r.get("data") or {}
    return {"configurado": True, "page_id": config.FB_PAGE_ID, "nombre": d.get("name", ""), "link": d.get("link", "")}


def publicar_facebook(texto: str, imagen: bytes) -> dict:
    """Publica la foto con su texto en la página. Registra en el historial."""
    if not configurado():
        return {"ok": False, "error": "sin_credenciales"}
    r = _graph_multipart(f"{config.FB_PAGE_ID}/photos", {"message": texto or "", "access_token": config.FB_PAGE_TOKEN, "published": "true"},
                         (f"pichangol.{EXTENSION}", imagen, MIME))
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "error")}
    d = r.get("data") or {}
    post_id = str(d.get("post_id") or d.get("id") or "")
    url = f"https://www.facebook.com/{post_id}" if post_id else ""
    return {"ok": True, "post_id": post_id, "url": url}


def registrar(entrada: dict) -> dict:
    fila = {"id": f"pub_{int(time.time() * 1000)}", "creado_en": time.time(), **entrada}
    stores.publicaciones_redes.insert(0, fila)
    del stores.publicaciones_redes[50:]
    return fila


def historial() -> list[dict]:
    return [dict(x) for x in stores.publicaciones_redes]
