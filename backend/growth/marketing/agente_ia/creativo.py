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

Locales Pro (cupo mensual, ver `estratega.pro_del_dia`): si el operador lo
encendió y el tope de gasto alcanza, la foto REAL del dueño se AMBIENTA con IA
(`ia_ambientada`: jugadores, luz; el lugar no cambia) y, opcionalmente, se
pide un video con movimiento y música a partir de esas fotos (`video_ia`, ver
`ia_media`; se arma en casa: la API de Sora cerró el 24-sep-2026). Si la
IA falla o no alcanza el tope, sale con las fotos reales (`foto_dueno`).

El resultado guarda la RECETA (fotos + formato) para poder recomponer la imagen
si el operador edita el título (va impreso sobre la foto). La imagen final se
sube a Storage (`canchas/marketing/<id>.jpg`) para que sobreviva a redeploys.
"""
from __future__ import annotations

import base64
import io
import threading
import urllib.request
import uuid

from collections import OrderedDict
from config import MARCA, MARCA_DOMINIO  # noqa: E402 — nombre y dominio de marca (un solo lugar)

FORMATO = {"story": "historia", "reel": "cuadrado"}
from marketing.agente_ia.guardrails import AVISO_IA, ORIGENES_IA_MEDIA  # noqa: E402,F401
_HORA_FRANJA = {"mañana": 9, "manana": 9, "tarde": 16, "noche": 20}
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


def _media_pro(op: dict, fotos: list[str], formato: str, pais: str, *, ambientar: bool, video: bool) -> dict | None:
    """Foto ambientada (+ video con movimiento) a partir de la primera foto REAL del local."""
    from marketing.agente_ia import ia_media
    if not (ambientar and fotos and ia_media.alcanza_imagen()):
        return None
    h = op.get("hechos") or {}
    deportes = (h.get("cancha") or {}).get("deportes") or []
    deporte = deportes[0] if deportes else "fútbol"
    hora = _HORA_FRANJA.get(str(h.get("franja") or "").lower(), 19)
    jpg, motivo = ia_media.ambientar(fotos[0], deporte=deporte, pais=pais, hora=hora)
    if not jpg:
        print(f"[agente_ia] sin foto ambientada ({motivo}); se usan las fotos reales", flush=True)
        return None
    url = guardar(f"amb_{uuid.uuid4().hex[:16]}", jpg)
    receta = {"origen": "ia_ambientada", "fotos": [url] + fotos[1:3], "formato": formato, "biblioteca_ids": [],
              "fotos_reales": fotos[:3], "ia": {"modelo": "imagen", "deporte": deporte}}
    if video and ia_media.alcanza_video():
        v = ia_media.encargar_video(receta["fotos"], mood="energetico" if op.get("audiencia") == "jugadores" else "chill",
                                    deporte=deporte, pais=pais, hora=hora)
        if v.get("estado") == "generando":
            receta.update(origen="video_ia", video_ia=v, formato_foto=formato)
        else:
            print(f"[agente_ia] video IA no encargado ({v.get('motivo')}); sale con la foto ambientada", flush=True)
    return receta


def elegir(op: dict, snapshot: dict, *, permitir_ia: bool = False, permitir_video: bool = True,
           ambientar: bool = False, video_ia: bool = False) -> dict:
    """Receta de medios: {origen, fotos, formato, video_id?, video_ia?, biblioteca_ids}."""
    formato = FORMATO.get(op.get("content_type"), "cuadrado")
    lista = {c["id"]: c for c in snapshot.get("canchas_lista") or []}
    if op.get("destacadas"):
        fotos = [u for cid in op["destacadas"] for u in (lista.get(cid) or {}).get("fotos", [])][:3]
        con_ia = _media_pro(op, fotos, formato, snapshot.get("pais") or "PE", ambientar=ambientar, video=video_ia)
        if con_ia:
            return con_ia
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
        elif u.startswith("mem:"):
            datos = leer(u[4:], None)
            u = ("data:image/jpeg;base64," + base64.b64encode(datos).decode()) if datos else None
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
    return _pr.componer(_resolver_fotos(receta), titulo or MARCA, subtitulo or "", MARCA_DOMINIO, formato, etiqueta or "")


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


VIDEO_MAX_BYTES = 150 * 1024 * 1024


def guardar_video(content_id: str, mp4: bytes | None) -> str | None:
    """MP4 del video IA → Storage `canchas/marketing/<id>.mp4`. Sin Storage
    (tests) queda en memoria como `mem:<id>.mp4`. None si no se pudo."""
    if not mp4:
        return None
    from web import almacen
    if not almacen.disponible():
        _cachear(f"{content_id}.mp4", mp4)
        return f"mem:{content_id}.mp4"
    url = almacen.subir("canchas", f"marketing/{content_id}.mp4", mp4, "video/mp4", max_bytes=VIDEO_MAX_BYTES)
    if url:
        _cachear(f"{content_id}.mp4", mp4)
    return url


def leer_video(url: str) -> bytes | None:
    if url.startswith("mem:"):
        return leer(url[4:], None)
    return leer(url.rsplit("/", 1)[-1].split("?")[0], url)


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
