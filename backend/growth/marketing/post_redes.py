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
import random
import re
import tempfile
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
def pieza_desde_vista_previa(data_url: str) -> bytes:
    """La pieza que el operador YA VIO en la torre (data URL JPEG/PNG que devolvió
    `/previsualizar`). Se valida como imagen real y se recodifica a JPEG para publicar
    exactamente lo mismo aunque las fotos elegidas ya no estén (cambió de local, etc.)."""
    from PIL import Image
    u = (data_url or "").strip()
    if not u.startswith("data:image/"):
        raise ValueError("La vista previa no es una imagen válida.")
    datos = _abrir_url(u)
    if len(datos) > MAX_BYTES:
        raise ValueError("La vista previa pesa demasiado.")
    try:
        im = Image.open(io.BytesIO(datos))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ValueError("La vista previa está dañada; vuelve a generarla.") from e
    if im.size[0] < 400 or im.size[1] < 400:
        raise ValueError("La vista previa es demasiado pequeña; vuelve a generarla.")
    if im.format == "JPEG":
        return datos
    salida = io.BytesIO()
    im.convert("RGB").save(salida, "JPEG", quality=90, progressive=True)
    return salida.getvalue()


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


# ── Redactor con IA (pedido del director, 24-sep-2026: "todos los posts dicen lo
# mismo… acá debe interactuar la IA para que sea más natural") ───────────────
# Cada pieza sale con un ENFOQUE distinto, un TONO elegido y sin repetir los
# ganchos de lo ya publicado (se le pasan los últimos posts del historial y lo
# que se generó en la sesión). Usa Anthropic (`ANTHROPIC_API_KEY`,
# `MARKETING_MODEL`, el mismo motor del CM de academias); sin llave cae a un
# banco de variantes por enfoque, rotando, para que QAS siga variando.
ENFOQUES = {
    "auto": "Elige tú el ángulo más fresco distinto a los recientes.",
    "beneficio": "Un beneficio CONCRETO de reservar con Pichangol contado desde la vida real del jugador: ver horarios libres al toque, confirmación al instante, sin llamadas ni chats eternos. Nada de 'llegó' ni 'lanzamiento'.",
    "local": "El LOCAL es el protagonista: qué tiene, dónde queda, para quién es ideal y cuándo conviene ir. Pichangol aparece solo como el lugar donde se reserva.",
    "comunidad": "Habla a la comunidad de jugadores: una pregunta real, invita a armar el partido, a etiquetar al equipo o a contar su anécdota. Poca venta.",
    "tip": "Un consejo útil y breve del deporte del local (calentamiento, técnica, hidratación, qué llevar) y recién al final conecta con reservar.",
    "finde": "Plan para el fin de semana o la semana: horarios, ganas de jugar, ese partido pendiente. Concreto y con fecha relativa (este sábado, esta semana).",
    "promo": "Comunica el precio o la promo con claridad y sin exagerar (SOLO con los datos dados; si no hay promo, habla del precio por hora).",
    "duenos": "Dirigido a DUEÑOS de canchas y academias: publicar la cancha en Pichangol es gratis, reciben reservas y cobros en línea, agenda ordenada. Tono de socio, no de vendedor.",
    "academia": "Para madres y padres: clases y academias que forman, valores del deporte en niños y adolescentes, cómo empezar.",
    "humor": "Tono ligero con humor futbolero o tenístico, situaciones reconocibles (el que siempre llega tarde, el arquero rotativo), sin burlarse de nadie.",
    "historia": "Detrás de Pichangol: una app hecha en Perú para que reservar una cancha sea tan fácil como pedir un taxi; propósito y cercanía, sin inventar hitos ni cifras.",
}
TONOS = {"cercano": "cercano y natural, como un amigo que juega", "divertido": "divertido y con chispa, sin payasadas",
         "informativo": "claro, directo y útil, cero relleno", "motivador": "motivador y energético, sin gritar"}
_DEPORTE_NOMBRE = {"futbol": "fútbol", "tenis": "tenis", "padel": "pádel", "pickleball": "pickleball", "voley": "vóley", "basquet": "básquet", "futsal": "futsal", "natacion": "natación"}
_PAIS_NOMBRE = {"PE": "Perú", "BO": "Bolivia", "EC": "Ecuador"}

_SYSTEM_REDACTOR = (
    "Eres quien maneja la página de Facebook de Pichangol, una app (Android y web www.pichangol.app) para reservar "
    "canchas de fútbol, tenis, pádel y pickleball y matricularse en academias, hecha en Perú y presente también en "
    "Bolivia y Ecuador. Escribes en español latinoamericano natural (peruano si el local está en Perú), como una persona, "
    "no como una marca gritando. REGLAS: (1) cada post debe sonar DISTINTO a los recientes que te paso: otro gancho, otra "
    "primera frase, otra estructura; prohibido empezar con '¡Llegó Pichangol!' o '¡Ya llegó!' salvo que el enfoque lo pida; "
    "(2) usa SOLO los datos del local que te doy (nombre, zona, deportes, precio, horario); no inventes promociones, "
    "resultados, testimonios ni cifras; (3) 0 a 3 emojis en todo el texto, nunca uno por línea; (4) un solo llamado a la "
    "acción, natural (reserva en la app o en la web); (5) 3 a 6 hashtags al final, en minúsculas, con #pichangol y el "
    "deporte; (6) largo variable: entre 280 y 650 caracteres; (7) moneda y ciudad del país del local; (8) no menciones que "
    "eres una IA ni pongas comillas alrededor del texto. Devuelves SOLO JSON válido: {\"titulo\": \"<= 36 caracteres, va "
    "impreso sobre la foto, sin emoji, con gancho>\", \"subtitulo\": \"<= 80 caracteres, complementa al título>\", "
    "\"etiqueta\": \"<= 14 caracteres, 1 o 2 palabras tipo Nuevo / Este finde / Tip / Para dueños, o vacío>\", "
    "\"texto\": \"el post completo con saltos de línea\", \"enfoque\": \"clave del enfoque usado\"}."
)


def _contexto_local(c: dict | None) -> dict:
    """Los HECHOS del local que la IA puede usar (y nada más)."""
    c = c or {}
    from paises import pais_de_coordenadas
    deps = [str(x) for x in (c.get("deportes") or ([c["deporte"]] if c.get("deporte") else []))]
    iso = pais_de_coordenadas(c.get("lat"), c.get("lng")) if c.get("lat") or c.get("lng") else "PE"
    sim = str(c.get("moneda") or ("$" if iso == "EC" else "Bs" if iso == "BO" else "S/"))
    try:
        precio = f"{sim} {float(c.get('precio_hora') or 0):.0f} la hora" if float(c.get("precio_hora") or 0) > 0 else ""
    except (TypeError, ValueError):
        precio = ""
    horario = ""
    if c.get("hora_apertura") and c.get("hora_cierre"):
        horario = f"{c['hora_apertura']}–{c['hora_cierre']}"
    return {"local": (c.get("club") or c.get("nombre") or "").strip(), "zona": (c.get("barrio") or c.get("distrito") or "").strip(),
            "deportes": [_DEPORTE_NOMBRE.get(d, d) for d in deps], "precio": precio, "horario": horario,
            "pais": _PAIS_NOMBRE.get(iso, "Perú"), "iso": iso, "verificada": bool(c.get("verificada", True)),
            "url": f"{(config.PUBLIC_BASE_URL or 'https://www.pichangol.app').rstrip('/')}/reservar/{c['id']}" if c.get("id") else "https://www.pichangol.app"}


def _recientes(evitar: list[str] | None, n: int = 10) -> list[str]:
    """Primeras frases de lo ya publicado + lo generado en la sesión, para no repetir."""
    vistos = []
    for h in stores.publicaciones_redes[:n]:
        t = str(h.get("texto") or "").strip().splitlines()
        if t:
            vistos.append((str(h.get("titulo") or "").strip() + " · " + t[0][:140]).strip(" ·"))
    for e in evitar or []:
        lineas = [x for x in str(e or "").strip().splitlines() if x.strip()]
        if lineas:
            vistos.append(lineas[0].strip()[:140])
    return vistos[:16]


def _enfoques_usados(n: int = 4) -> list[str]:
    return [str(h.get("enfoque") or "") for h in stores.publicaciones_redes[:n] if h.get("enfoque")]


def _elegir_enfoque(pedido: str, ctx: dict, evitar_enfoques: list[str]) -> str:
    if pedido in ENFOQUES and pedido != "auto":
        return pedido
    candidatos = [k for k in ENFOQUES if k != "auto"]
    if not ctx.get("precio"):
        candidatos.remove("promo")
    if not ctx.get("local"):          # sin local elegido no hay protagonista ni plan concreto
        candidatos.remove("local"); candidatos.remove("finde")
    if "tenis" not in ctx.get("deportes", []) and "pádel" not in ctx.get("deportes", []) and "natación" not in ctx.get("deportes", []):
        candidatos.remove("academia")
    frescos = [k for k in candidatos if k not in evitar_enfoques] or candidatos
    return random.choice(frescos)


def _limpiar_campo(v, tope: int) -> str:
    t = re.sub(r"\s+", " ", str(v or "")).strip().strip('"“”')
    return t[:tope].rstrip() if len(t) > tope else t


def _con_claude_redactor(payload: dict) -> dict | None:
    try:
        import anthropic
    except Exception:  # noqa: BLE001
        return None
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(model=config.MARKETING_MODEL, max_tokens=900, temperature=1.0, system=_SYSTEM_REDACTOR,
                                      messages=[{"role": "user", "content": "Redacta la publicación (JSON):\n" + json.dumps(payload, ensure_ascii=False)}])
        texto = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        m = re.search(r"\{.*\}", texto or "", re.DOTALL)
        data = json.loads(m.group(0)) if m else None
        return data if isinstance(data, dict) and str(data.get("texto") or "").strip() else None
    except Exception as e:  # noqa: BLE001
        print(f"[redes] IA no respondió, se usa el banco de variantes: {str(e)[:120]}", flush=True)
        return None


def _banco(enfoque: str, ctx: dict, tono: str) -> list[dict]:
    """Variantes SIN IA por enfoque (QAS sin llave o fallo del modelo). Solo hechos del local."""
    L = ctx.get("local") or "una cancha cerca de ti"
    Z = ctx.get("zona") or "tu zona"
    D = ctx.get("deportes") or ["fútbol"]
    d0 = D[0]
    dep_tag = "#" + d0.replace("á", "a").replace("ó", "o").replace("ú", "u").replace(" ", "")
    precio = ctx.get("precio") or ""
    horario = ctx.get("horario") or ""
    url = ctx.get("url") or "https://www.pichangol.app"
    tags = f"#pichangol {dep_tag} #reservajuegarepite"
    B = {
        "beneficio": [
            {"titulo": "Horarios libres, al toque", "subtitulo": f"Mira qué hay en {L} y reserva en un minuto", "etiqueta": "",
             "texto": f"¿Cuántos mensajes mandas para conseguir cancha un viernes? En Pichangol abres el mapa, ves los horarios libres de {L} ({Z}) y reservas. Confirmación al instante, sin llamadas.\n\nReserva aquí: {url}\n\n{tags}"},
            {"titulo": "Sin llamar, sin esperar", "subtitulo": "Elige la hora, confirma y listo", "etiqueta": "",
             "texto": f"Lo más difícil del partido no debería ser conseguir la cancha. {L} ya tiene sus horarios en Pichangol{(' (' + horario + ')') if horario else ''}: eliges la hora, pagas si quieres y te llega la confirmación.\n\n{url}\n\n{tags}"},
        ],
        "local": [
            {"titulo": L[:36], "subtitulo": f"{' · '.join(x.capitalize() for x in D)} en {Z}", "etiqueta": "Conócelo",
             "texto": f"{L}, en {Z}: {' y '.join(D)}{(', ' + precio) if precio else ''}{(', de ' + horario) if horario else ''}. Buen piso, buena luz y horarios en vivo para no llegar a ver si hay sitio.\n\nReserva tu turno: {url}\n\n{tags}"},
        ],
        "comunidad": [
            {"titulo": "¿Con quién juegas este finde?", "subtitulo": "Etiqueta a tu equipo y arma el partido", "etiqueta": "",
             "texto": f"Confiesa: ¿quién de tu grupo es el que siempre confirma y nunca llega? 😅 Etiquétalo y arma el partido de una vez. En {L} ({Z}) hay horarios libres esta semana.\n\n{url}\n\n{tags}"},
            {"titulo": "Se busca rival", "subtitulo": f"Partidos de {d0} en {Z}", "etiqueta": "",
             "texto": f"¿Tu equipo necesita rival para el sábado? Comenta la hora y el nivel, y que se arme. La cancha ya está: {L}, en {Z}, con horarios en Pichangol.\n\n{url}\n\n{tags}"},
        ],
        "tip": [
            {"titulo": "5 minutos que evitan lesiones", "subtitulo": "Calienta antes de entrar a la cancha", "etiqueta": "Tip",
             "texto": f"Antes del primer sprint: 5 minutos de trote suave, movilidad de tobillos y caderas, y dos series cortas de aceleración. Tu cuerpo llega listo y el partido se disfruta entero.\n\n¿Dónde? En {L} ({Z}) hay turnos libres esta semana: {url}\n\n{tags} #calentamiento"},
            {"titulo": "Hidrátate antes, no después", "subtitulo": "Un tip simple que cambia tu partido", "etiqueta": "Tip",
             "texto": f"Toma agua desde una hora antes de jugar, no solo cuando ya tienes sed. Rinde más el segundo tiempo y baja el riesgo de calambres.\n\nY el turno lo aseguras en Pichangol: {L}, {Z}. {url}\n\n{tags}"},
        ],
        "finde": [
            {"titulo": "Este sábado sí se juega", "subtitulo": f"Turnos libres en {L}", "etiqueta": "Este finde",
             "texto": f"El partido que vienen postergando hace un mes: este sábado. {L} ({Z}) tiene horarios libres{(' de ' + horario) if horario else ''}. Entra, elige la hora y avísale al grupo que ya está.\n\n{url}\n\n{tags}"},
        ],
        "promo": [
            {"titulo": precio.split(" la hora")[0] + " la hora" if precio else "Precio claro", "subtitulo": f"{L} · {Z}", "etiqueta": "Precio",
             "texto": f"Sin sorpresas: en {L} ({Z}) la hora de {d0} está a {precio} y lo ves antes de reservar. Eliges turno, pagas en línea o en la cancha, y listo.\n\n{url}\n\n{tags}"},
        ],
        "duenos": [
            {"titulo": "¿Tienes una cancha?", "subtitulo": "Publícala gratis y recibe reservas", "etiqueta": "Para dueños",
             "texto": f"Si administras una cancha o una academia, Pichangol te ordena la agenda: publicas gratis, los jugadores ven tus horarios libres y reservan solos; tú recibes el aviso y el cobro en línea si quieres.\n\nEmpieza en www.pichangol.app → Modo anfitrión.\n\n#pichangol #duenosdecancha #canchas"},
        ],
        "academia": [
            {"titulo": "Su primera raqueta", "subtitulo": "Academias para niños y adolescentes", "etiqueta": "Academias",
             "texto": f"El deporte enseña a perder, a esperar el turno y a volver a intentar. En Pichangol encuentras academias de {d0} con sus programas, horarios y tarifas claras, y matriculas desde la app.\n\nwww.pichangol.app/canchas?deporte=academias\n\n#pichangol #academias {dep_tag} #niños"},
        ],
        "humor": ([
            {"titulo": "\"Esa iba fuera\"", "subtitulo": "Lo único que Pichangol no puede arbitrar", "etiqueta": "",
             "texto": f"Cosas que Pichangol sí resuelve: encontrar cancha, ver horarios libres, confirmar al instante.\nCosas que no: si esa bola picó dentro o fuera. 🎾\n\n{L} ({Z}) tiene turnos libres esta semana: {url}\n\n{tags}"},
        ] if d0 in ("tenis", "pádel", "pickleball") else [
            {"titulo": "El arquero rotativo", "subtitulo": "Una tradición que Pichangol no puede arreglar", "etiqueta": "",
             "texto": f"Cosas que Pichangol sí resuelve: encontrar cancha, ver horarios libres, confirmar al instante.\nCosas que no: quién va al arco. 🧤\n\n{L} ({Z}) tiene turnos libres esta semana: {url}\n\n{tags}"},
        ]),
        "historia": [
            {"titulo": "Hecha para jugar más", "subtitulo": "Una app peruana para reservar canchas", "etiqueta": "",
             "texto": f"Pichangol nació de algo simple: conseguir cancha no debería ser más difícil que pedir un taxi. Por eso juntamos en un mapa las canchas con sus horarios reales, como {L} en {Z}, para que reservar tome un minuto.\n\nwww.pichangol.app\n\n{tags} #hechoenperu"},
        ],
    }
    return B.get(enfoque) or B["beneficio"]


def redactar(cancha: dict | None, tono: str = "cercano", enfoque: str = "auto", tema: str = "", evitar: list[str] | None = None) -> dict:
    """Redacta título/subtítulo/etiqueta/texto para la pieza, variando el enfoque y sin
    repetir lo reciente. Devuelve también `fuente` ('ia' | 'banco') y el `enfoque` usado."""
    ctx = _contexto_local(cancha)
    tono = tono if tono in TONOS else "cercano"
    recientes = _recientes(evitar)
    usados = _enfoques_usados()
    elegido = _elegir_enfoque(enfoque, ctx, usados)
    fuente = "banco"
    data = None
    if config.ANTHROPIC_API_KEY:
        payload = {"local": ctx, "tono": TONOS[tono], "enfoque": {"clave": elegido, "instruccion": ENFOQUES[elegido]},
                   "tema_del_operador": (tema or "").strip()[:300], "recientes_no_repetir": recientes,
                   "enfoques_recientes": usados, "fecha": time.strftime("%Y-%m-%d")}
        data = _con_claude_redactor(payload)
        if data:
            fuente = "ia"
    if not data:
        # Banco: primero el enfoque elegido; si todas sus variantes ya salieron (en el
        # historial o en esta sesión), pasa a otro enfoque fresco antes de repetir.
        inicios = {r.split(" · ")[-1][:60] for r in recientes}
        # Un enfoque pedido a mano se respeta aunque haya que repetir variante; en "auto" se rota.
        orden = [elegido] + (random.sample([k for k in ENFOQUES if k not in ("auto", elegido)], len(ENFOQUES) - 2) if enfoque == "auto" else [])
        frescas, usado = [], elegido
        for k in orden:
            frescas = [o for o in _banco(k, ctx, tono) if o["texto"].splitlines()[0][:60] not in inicios]
            if frescas:
                usado = k
                break
        if not frescas:
            frescas = _banco(elegido, ctx, tono)
        elegido = usado
        data = dict(random.choice(frescas))
        if (tema or "").strip():
            data["texto"] = data["texto"].rstrip() + f"\n\n{tema.strip()[:200]}"
    texto = str(data.get("texto") or "").strip()
    if "#pichangol" not in texto.lower():
        texto = texto.rstrip() + "\n\n#pichangol"
    return {"titulo": _limpiar_campo(data.get("titulo"), 36), "subtitulo": _limpiar_campo(data.get("subtitulo"), 80),
            "etiqueta": _limpiar_campo(data.get("etiqueta"), 14), "texto": texto[:1200],
            "enfoque": str(data.get("enfoque") or elegido) if str(data.get("enfoque") or "") in ENFOQUES else elegido,
            "tono": tono, "fuente": fuente}


# ── Facebook ─────────────────────────────────────────────────────────────────
def configurado() -> bool:
    return bool(config.FB_PAGE_ID and config.FB_PAGE_TOKEN)


def _graph_multipart(path: str, campos: dict, archivo: tuple[str, bytes, str] | None, *,
                     campo_archivo: str = "source", timeout: int = 60) -> dict:
    """POST multipart a Graph (foto como archivo `source`; video por trozos como
    `video_file_chunk`). Devuelve {ok, data|error}."""
    base = f"{config.META_GRAPH_BASE}/{config.META_GRAPH_VERSION}"
    limite = "----PichangolTorre" + uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
    if archivo:
        nombre, datos, ct = archivo
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo_archivo}\"; filename=\"{nombre}\"\r\nContent-Type: {ct}\r\n\r\n".encode("utf-8") + datos + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode("utf-8"))
    cuerpo = b"".join(partes)
    req = urllib.request.Request(f"{base}/{path.lstrip('/')}", data=cuerpo, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={limite}", "Content-Length": str(len(cuerpo))})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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


PERMISO_PUBLICAR = "pages_manage_posts"
_PERMISOS_PAGINA = ("pages_manage_posts", "pages_read_engagement", "pages_show_list")
_token_cache: dict = {"clave": "", "hasta": 0.0, "res": {}}
_TOKEN_TTL = 600


def _resolver_token() -> dict:
    """Averigua QUÉ token puso el operador y consigue el de PÁGINA.

    Trampa real (sep-2026): Meta responde ``(#200) publish_actions … deprecated``
    cuando ``/{page}/photos`` recibe un token de USUARIO en vez del de la página,
    o uno de página sin ``pages_manage_posts``. Para no adivinar, la torre:
    (1) pregunta ``/me`` con el token: si el id es la página → token de página;
    (2) si es una persona → lee sus permisos (``/me/permissions``) y pide el token
    de página con ``/{page}?fields=access_token`` (funciona si administra la
    página y dio ``pages_show_list``); (3) avisa si falta ``pages_manage_posts``.
    Devuelve ``{token, tipo, usuario, permisos, faltan, error}``; caché 10 min.
    """
    clave = f"{config.FB_PAGE_ID}:{config.FB_PAGE_TOKEN[-12:]}:{len(config.FB_PAGE_TOKEN)}"
    if _token_cache["clave"] == clave and _token_cache["hasta"] > time.time():
        return dict(_token_cache["res"])
    tok = config.FB_PAGE_TOKEN
    res: dict = {"token": "", "tipo": "", "usuario": "", "permisos": None, "faltan": [], "error": ""}
    yo = _graph_get("me", {"fields": "id,name", "access_token": tok})
    if not yo.get("ok"):
        res["error"] = f"Facebook no reconoce el token: {yo.get('error', 'error')}"
    else:
        d = yo.get("data") or {}
        if str(d.get("id", "")) == str(config.FB_PAGE_ID):
            res.update(tipo="pagina", token=tok)
            # Con un token de página, `debug_token` (mismo token) devuelve los scopes; si no, quedan desconocidos.
            dbg = _graph_get("debug_token", {"input_token": tok, "access_token": tok})
            scopes = ((dbg.get("data") or {}).get("data") or {}).get("scopes") if dbg.get("ok") else None
            if isinstance(scopes, list):
                res["permisos"] = [str(x) for x in scopes]
        else:
            res.update(tipo="usuario", usuario=str(d.get("name", "")))
            perm = _graph_get("me/permissions", {"access_token": tok})
            if perm.get("ok"):
                filas = (perm.get("data") or {}).get("data") or []
                res["permisos"] = [str(f.get("permission")) for f in filas if f.get("status") == "granted"]
            pag = _graph_get(config.FB_PAGE_ID, {"fields": "access_token", "access_token": tok})
            token_pag = ((pag.get("data") or {}).get("access_token") or "") if pag.get("ok") else ""
            if token_pag:
                res["token"] = token_pag
            else:
                res["error"] = (f"El token es de la cuenta de {res['usuario'] or 'un usuario'}, no de la página, y Facebook no "
                                f"entregó el de la página {config.FB_PAGE_ID} ({pag.get('error', 'sin acceso')}). Verifica que esa "
                                f"cuenta administre la página y que el token tenga pages_show_list.")
        if isinstance(res["permisos"], list):
            res["faltan"] = [p for p in _PERMISOS_PAGINA if p not in res["permisos"]]
    _token_cache.update(clave=clave, hasta=time.time() + _TOKEN_TTL, res=dict(res))
    return dict(res)


def _pista_error(err: str) -> str:
    """Traduce los rechazos típicos de Graph a qué hacer."""
    e = (err or "").lower()
    if "publish_actions" in e or "(#200)" in e or "permission" in e:
        return (" → El token no puede publicar en la página. Genera en el Explorador de la API Graph un token de PÁGINA "
                f"(no de usuario) con {', '.join(_PERMISOS_PAGINA)}, extiéndelo y reemplaza FB_PAGE_TOKEN en Railway.")
    if "(#190)" in e or "expired" in e or "session has been invalidated" in e:
        return " → El token caducó o fue invalidado (cambio de contraseña / cierre de sesión). Genera uno nuevo de larga duración."
    return ""


def estado_pagina() -> dict:
    """¿Hay credenciales? ¿A qué página apuntan? ¿Sirve el token para publicar? (sin exponer el token)."""
    base = {"configurado": False, "page_id": "", "nombre": "", "link": "", "token_tipo": "", "usuario": "", "faltan": [], "advertencia": ""}
    if not configurado():
        return base
    base.update(configurado=True, page_id=config.FB_PAGE_ID)
    r = _graph_get(config.FB_PAGE_ID, {"fields": "name,link", "access_token": config.FB_PAGE_TOKEN})
    if not r.get("ok"):
        return {**base, "error": r.get("error")}
    d = r.get("data") or {}
    base.update(nombre=d.get("name", ""), link=d.get("link", ""))
    t = _resolver_token()
    base.update(token_tipo=t.get("tipo", ""), usuario=t.get("usuario", ""), faltan=list(t.get("faltan") or []))
    if t.get("error"):
        base["advertencia"] = t["error"]
    elif PERMISO_PUBLICAR in base["faltan"]:
        base["advertencia"] = (f"Al token le falta el permiso {PERMISO_PUBLICAR}: Facebook rechazará la publicación. "
                               "Vuelve a generarlo marcando ese permiso.")
    elif t.get("tipo") == "usuario":
        base["advertencia"] = (f"El token es de la cuenta de {t.get('usuario') or 'usuario'}; la torre obtiene sola el de la "
                               "página para publicar.")
    return base


def publicar_facebook(texto: str, imagen: bytes) -> dict:
    """Publica la foto con su texto en la página. Registra en el historial."""
    if not configurado():
        return {"ok": False, "error": "sin_credenciales"}
    t = _resolver_token()
    if t.get("error") or not t.get("token"):
        return {"ok": False, "error": t.get("error") or "No se pudo obtener el token de la página."}
    if PERMISO_PUBLICAR in (t.get("faltan") or []):
        return {"ok": False, "error": f"Al token le falta el permiso {PERMISO_PUBLICAR}." + _pista_error("permission")}
    r = _graph_multipart(f"{config.FB_PAGE_ID}/photos", {"message": texto or "", "access_token": t["token"], "published": "true"},
                         (f"pichangol.{EXTENSION}", imagen, MIME))
    if not r.get("ok"):
        err = str(r.get("error", "error"))
        if "(#190)" in err or "expired" in err.lower():
            _token_cache["hasta"] = 0.0
        return {"ok": False, "error": err + _pista_error(err)}
    d = r.get("data") or {}
    post_id = str(d.get("post_id") or d.get("id") or "")
    url = f"https://www.facebook.com/{post_id}" if post_id else ""
    return {"ok": True, "post_id": post_id, "url": url}


# ── Videos (pedido del director, 24-sep-2026: "también debe permitir subir videos") ──
# El operador sube el archivo a la torre (streaming a disco, con progreso en el
# navegador); queda en una carpeta temporal del backend un rato (VIDEO_TTL) y al
# publicar se manda a la PÁGINA con la subida REANUDABLE de Graph
# (`/{page}/videos` start → transfer por trozos → finish). Facebook lo procesa
# unos minutos y lo publica con `description` = texto del post.
VIDEO_MAX_MB = int(os.getenv("FB_VIDEO_MAX_MB", "300") or 300)
VIDEO_TTL = 2 * 3600
VIDEO_EXTENSIONES = {"mp4", "mov", "m4v", "webm", "avi", "mkv", "3gp"}
VIDEO_MIME = {"mp4": "video/mp4", "mov": "video/quicktime", "m4v": "video/x-m4v", "webm": "video/webm",
              "avi": "video/x-msvideo", "mkv": "video/x-matroska", "3gp": "video/3gpp"}
_VIDEO_DIR = os.path.join(tempfile.gettempdir(), "pichangol_redes_videos")
_videos: dict[str, dict] = {}


def extension_video(nombre: str) -> str:
    ext = (nombre or "").rsplit(".", 1)[-1].lower().strip() if "." in (nombre or "") else ""
    return ext if ext in VIDEO_EXTENSIONES else ""


def _limpiar_videos() -> None:
    """Borra los videos temporales vencidos (y huérfanos en disco de arranques anteriores)."""
    ahora = time.time()
    for vid, v in list(_videos.items()):
        if ahora - v.get("creado_en", 0) > VIDEO_TTL:
            descartar_video(vid)
    try:
        for nombre in os.listdir(_VIDEO_DIR):
            ruta = os.path.join(_VIDEO_DIR, nombre)
            if ahora - os.path.getmtime(ruta) > VIDEO_TTL and not any(v["ruta"] == ruta for v in _videos.values()):
                os.remove(ruta)
    except OSError:
        pass


def iniciar_video(nombre: str) -> dict:
    """Reserva id + ruta temporal para un video que se está subiendo (el router escribe el archivo)."""
    ext = extension_video(nombre)
    if not ext:
        raise ValueError("Formato no admitido. Sube un video MP4 o MOV (también M4V, WEBM, AVI, MKV, 3GP).")
    _limpiar_videos()
    os.makedirs(_VIDEO_DIR, exist_ok=True)
    vid = "vid_" + uuid.uuid4().hex[:16]
    v = {"id": vid, "nombre": (nombre or "video")[:120], "ext": ext, "ruta": os.path.join(_VIDEO_DIR, f"{vid}.{ext}"),
         "bytes": 0, "creado_en": time.time(), "listo": False}
    _videos[vid] = v
    return dict(v)


def confirmar_video(vid: str, total: int) -> dict:
    v = _videos[vid]
    v.update(bytes=int(total), listo=True)
    return dict(v)


def video(vid: str) -> dict | None:
    v = _videos.get(vid or "")
    if not v or not v.get("listo") or not os.path.exists(v["ruta"]):
        return None
    return dict(v)


def anotar_video(vid: str, **campos) -> None:
    """Guarda datos derivados del video temporal (versión pulida, transcripción…)."""
    v = _videos.get(vid or "")
    if v:
        v.update({k: val for k, val in campos.items() if val is not None})


def descartar_video(vid: str) -> None:
    v = _videos.pop(vid or "", None)
    if v:
        for ruta in (v.get("ruta"), v.get("pulido")):
            if ruta:
                try:
                    os.remove(ruta)
                except OSError:
                    pass


def publicar_video_facebook(texto: str, titulo: str, ruta: str) -> dict:
    """Sube el video a la página con la API reanudable de Graph y lo publica con el texto."""
    if not configurado():
        return {"ok": False, "error": "sin_credenciales"}
    t = _resolver_token()
    if t.get("error") or not t.get("token"):
        return {"ok": False, "error": t.get("error") or "No se pudo obtener el token de la página."}
    if PERMISO_PUBLICAR in (t.get("faltan") or []):
        return {"ok": False, "error": f"Al token le falta el permiso {PERMISO_PUBLICAR}." + _pista_error("permission")}
    tok = t["token"]
    ruta_api = f"{config.FB_PAGE_ID}/videos"
    tam = os.path.getsize(ruta)
    r = _graph_multipart(ruta_api, {"upload_phase": "start", "file_size": str(tam), "access_token": tok}, None, timeout=120)
    if not r.get("ok"):
        err = str(r.get("error", "error"))
        return {"ok": False, "error": err + _pista_error(err)}
    d = r.get("data") or {}
    sesion, video_id = str(d.get("upload_session_id", "")), str(d.get("video_id", ""))
    ini, fin = int(d.get("start_offset", 0) or 0), int(d.get("end_offset", 0) or 0)
    if not sesion:
        return {"ok": False, "error": "Facebook no abrió la sesión de subida del video."}
    trozos = 0
    with open(ruta, "rb") as f:
        while ini < fin:
            f.seek(ini)
            datos = f.read(fin - ini)
            r = _graph_multipart(ruta_api, {"upload_phase": "transfer", "upload_session_id": sesion, "start_offset": str(ini), "access_token": tok},
                                 (f"trozo_{trozos}.bin", datos, "application/octet-stream"), campo_archivo="video_file_chunk", timeout=600)
            if not r.get("ok"):
                return {"ok": False, "error": f"Se cortó la subida del video en el trozo {trozos + 1}: {r.get('error', 'error')}"}
            d = r.get("data") or {}
            trozos += 1
            nuevo_ini, nuevo_fin = int(d.get("start_offset", fin) or 0), int(d.get("end_offset", fin) or 0)
            if nuevo_ini == ini and nuevo_fin == fin:   # Facebook no avanzó: evitar bucle infinito
                return {"ok": False, "error": "Facebook no aceptó el trozo del video (sin avance). Inténtalo de nuevo."}
            ini, fin = nuevo_ini, nuevo_fin
    campos = {"upload_phase": "finish", "upload_session_id": sesion, "description": texto or "", "access_token": tok, "published": "true"}
    if (titulo or "").strip():
        campos["title"] = titulo.strip()[:255]
    r = _graph_multipart(ruta_api, campos, None, timeout=120)
    if not r.get("ok"):
        err = str(r.get("error", "error"))
        return {"ok": False, "error": err + _pista_error(err)}
    url = f"https://www.facebook.com/{video_id}" if video_id else ""
    return {"ok": True, "post_id": video_id, "url": url, "trozos": trozos, "bytes": tam}


def registrar(entrada: dict) -> dict:
    fila = {"id": f"pub_{int(time.time() * 1000)}", "creado_en": time.time(), **entrada}
    stores.publicaciones_redes.insert(0, fila)
    del stores.publicaciones_redes[50:]
    return fila


def historial() -> list[dict]:
    return [dict(x) for x in stores.publicaciones_redes]
