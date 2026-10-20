"""CREATIVE AGENT: qué imagen (o video) acompaña a la pieza.

Prioridad (principio 7 del agente):

1. **Fotos reales de Pichangol** (`foto_real`): la biblioteca de marca que el
   director eligió en Google Fotos (`marketing/biblioteca.py`), o un video de
   esa biblioteca para un reel.
2. **Fotos del dueño** (`foto_dueno`): las que el dueño subió de SU cancha.
   Son las únicas válidas cuando la pieza destaca un local concreto.
3. **Diseño de marca** (`diseno`): composición con la portada de Pichangol.
4. **Arte IA** (`ia_conceptual`): solo si el operador lo habilitó y NUNCA para
   una cancha concreta; es una imagen conceptual, no la foto de un lugar.

El resultado guarda la RECETA (fotos + formato) para poder recomponer la imagen
si el operador edita el título (va impreso sobre la foto). La imagen final se
sube a Storage (`canchas/marketing/<id>.jpg`) para que sobreviva a redeploys.
"""
from __future__ import annotations

import base64
import io
import threading
import urllib.request

from collections import OrderedDict

FORMATO = {"story": "historia", "reel": "cuadrado"}
CACHE_MAX = 64                  # imágenes en memoria (la fuente de verdad es Storage)
_cache: "OrderedDict[str, bytes]" = OrderedDict()
_lock = threading.Lock()


def _biblioteca_fotos(n: int) -> list[dict]:
    try:
        from marketing import biblioteca
        return biblioteca.elegir_fotos(n) or []
    except Exception:  # noqa: BLE001
        return []


def _biblioteca_video() -> dict | None:
    try:
        from marketing import biblioteca
        from marketing.agente_redes import VIDEO_DESCANSO_DIAS
        return biblioteca.elegir_video(VIDEO_DESCANSO_DIAS)
    except Exception:  # noqa: BLE001
        return None


def _arte_ia(deporte: str) -> str | None:
    try:
        from marketing import arte_ia
        if not arte_ia.disponible():
            return None
        img = arte_ia.fondo_para(deporte or "futbol", 0, "")
        if img is None:
            return None
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return None


def elegir(op: dict, snapshot: dict, *, permitir_ia: bool = False, permitir_video: bool = True) -> dict:
    """Receta de medios: {origen, fotos, formato, video_id?, biblioteca_ids}."""
    formato = FORMATO.get(op.get("content_type"), "cuadrado")
    lista = {c["id"]: c for c in snapshot.get("canchas_lista") or []}
    if op.get("destacadas"):
        fotos = [u for cid in op["destacadas"] for u in (lista.get(cid) or {}).get("fotos", [])][:3]
        return {"origen": "foto_dueno" if fotos else "diseno", "fotos": fotos or ["brand:portada"], "formato": formato, "biblioteca_ids": []}
    if op.get("content_type") == "reel" and permitir_video:
        v = _biblioteca_video()
        if v:
            return {"origen": "foto_real", "fotos": [], "formato": "video", "video_id": v["id"], "video_url": v.get("url", ""),
                    "video_nombre": v.get("nombre", ""), "biblioteca_ids": [v["id"]]}
    elegidas = _biblioteca_fotos(3 if op["audiencia"] == "jugadores" else 1)
    if elegidas:
        return {"origen": "foto_real", "fotos": [x["url"] for x in elegidas], "formato": formato,
                "biblioteca_ids": [x["id"] for x in elegidas]}
    if permitir_ia:
        deps = [d for c in [op.get("hechos", {}).get("cancha")] if c for d in c.get("deportes") or []]
        arte = _arte_ia(deps[0] if deps else "futbol")
        if arte:
            return {"origen": "ia_conceptual", "fotos": ["brand:arte"], "formato": formato, "biblioteca_ids": [], "_data": arte}
    return {"origen": "diseno", "fotos": ["brand:portada"], "formato": formato, "biblioteca_ids": []}


def fondo_marca(formato: str = "cuadrado") -> str:
    """DISEÑO de marca sin texto (la portada de Facebook ya trae letras y el
    título se le encimaría): degradado bosque → verde Pichangol con las líneas
    de una cancha en blanco translúcido. Data URL JPEG."""
    from PIL import Image, ImageDraw
    from marketing import post_redes as _pr
    W, H = _pr.FORMATOS.get(formato, _pr.FORMATOS["cuadrado"])
    a, b = (0x14, 0x46, 0x3A), (0x12, 0x8C, 0x7E)
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(0, W, 4):
            t = min(1.0, (x / W) * 0.45 + (y / H) * 0.75)
            col = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
            for dx in range(4):
                if x + dx < W:
                    px[x + dx, y] = col
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    linea, g = (255, 255, 255, 46), max(4, W // 180)
    m = int(min(W, H) * 0.07)
    d.rectangle([m, m, W - m, H - m], outline=linea, width=g)
    d.line([W // 2, m, W // 2, H - m], fill=linea, width=g)
    r = int(min(W, H) * 0.14)
    d.ellipse([W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r], outline=linea, width=g)
    aw, ah = int(W * 0.14), int(H * 0.36)
    d.rectangle([m, H // 2 - ah // 2, m + aw, H // 2 + ah // 2], outline=linea, width=g)
    d.rectangle([W - m - aw, H // 2 - ah // 2, W - m, H // 2 + ah // 2], outline=linea, width=g)
    d.ellipse([int(W * 0.72), int(H * -0.12), int(W * 1.12), int(H * 0.28)], fill=(0xAE, 0xEA, 0x94, 38))
    img = Image.alpha_composite(img.convert("RGBA"), capa).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _resolver_fotos(receta: dict) -> list[str]:
    out = []
    for u in receta.get("fotos") or []:
        if u == "brand:arte":
            u = receta.get("_data") or _arte_ia("futbol") or fondo_marca(receta.get("formato") or "cuadrado")
        elif u == "brand:portada":
            u = fondo_marca(receta.get("formato") or "cuadrado")
        if u:
            out.append(u)
    return out


def componer(receta: dict, *, titulo: str, subtitulo: str, etiqueta: str) -> bytes:
    """Imagen final (JPEG). Para un reel, el póster (primer frame + marca)."""
    from marketing import post_redes as _pr
    if receta.get("video_id"):
        from marketing import agente_redes
        v = {"id": receta["video_id"], "url": receta.get("video_url", "")}
        return agente_redes._poster_video(v, {"titulo": titulo, "subtitulo": subtitulo})
    formato = receta.get("formato") if receta.get("formato") in _pr.FORMATOS else "cuadrado"
    return _pr.componer(_resolver_fotos(receta), titulo or "Pichangol", subtitulo or "", "www.pichangol.app", formato, etiqueta or "")


def guardar(content_id: str, imagen: bytes) -> str:
    """Sube la imagen a Storage y devuelve su URL pública. Sin Storage
    (tests / sin llaves) queda en memoria y se sirve por la torre."""
    _cachear(content_id, imagen)
    import config
    base = (config.SUPABASE_URL or "").strip().rstrip("/")
    if not base or not config.SUPABASE_ANON_KEY:
        return f"mem:{content_id}"
    if not base.startswith("http"):
        base = f"https://{base}"
    ruta = f"marketing/{content_id}.jpg"
    try:
        req = urllib.request.Request(f"{base}/storage/v1/object/canchas/{ruta}", data=imagen, method="POST",
                                     headers={"Authorization": f"Bearer {config.SUPABASE_ANON_KEY}", "apikey": config.SUPABASE_ANON_KEY,
                                              "Content-Type": "image/jpeg", "x-upsert": "true"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            r.read()
        return f"{base}/storage/v1/object/public/canchas/{ruta}"
    except Exception as e:  # noqa: BLE001
        print(f"[agente_ia] no se pudo subir la imagen a Storage: {str(e)[:120]}", flush=True)
        return f"mem:{content_id}"


def _cachear(content_id: str, datos: bytes) -> None:
    with _lock:
        _cache[content_id] = datos
        _cache.move_to_end(content_id)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)


def leer(content_id: str, media_url: str | None) -> bytes | None:
    """Bytes de la imagen de una pieza (caché → Storage)."""
    with _lock:
        if content_id in _cache:
            return _cache[content_id]
    if media_url and media_url.startswith("https://"):
        try:
            with urllib.request.urlopen(media_url, timeout=20) as r:  # noqa: S310
                datos = r.read()
            _cachear(content_id, datos)
            return datos
        except Exception:  # noqa: BLE001
            return None
    return None
