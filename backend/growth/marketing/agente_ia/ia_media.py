"""MEDIOS CON IA para los locales Pro (decisión del director, 20-oct-2026).

Dos productos, ambos A PARTIR DE LAS FOTOS REALES que subió el dueño:

* **Foto ambientada** (`ia_ambientada`): OpenAI Images *edits* (gpt-image-1)
  toma la foto del local y le agrega jugadores, luz y ambiente de partido. El
  prompt exige conservar el lugar tal cual (cerco, líneas, paredes, techos,
  edificios): la IA ambienta, no inventa otra cancha.
* **Video** (`video_ia`): la foto ambientada + las reales con movimiento, logo,
  rótulo, cierre y música original, armado EN CASA con FFmpeg (gratis; la API
  de Sora de OpenAI cerró el 24-sep-2026). Se PIDE al crear la pieza y
  `procesar_videos()` (cron del agente, cada minuto) lo renderiza y lo deja en
  Storage. Mientras tanto la pieza no se aprueba ni se publica; si falla, la
  pieza sale con la foto ambientada.

Todo lo generado lleva el aviso "contenido generado con IA" en el texto (lo
exige el guardrail) y queda en Storage `canchas/marketing/` para no re-pagarlo.

**Tope de gasto mensual** (`ai_mkt_media_tope_usd`, torre): cada imagen se
RESERVA antes de pedirla; si no alcanza, el creativo usa las fotos reales sin
IA. Costo por imagen editable en la torre (`ai_mkt_costo_imagen`).
"""
from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

_TIMEOUT = 180
_lock = threading.Lock()

MOTIVO_TOPE = "tope"

PROMPT_AMBIENTAR = (
    "Edit this real photo of a {deporte} venue in {pais}. Keep the venue EXACTLY as it is: the same court or pitch, "
    "lines, surface, nets, goals, fences, walls, roof, lights, buildings and camera angle. Do not add or remove "
    "any structure, sign, logo or text. Only add life: {escena}, natural {luz}, realistic shadows. "
    "Photorealistic sports photography, candid, faces small and not recognizable, no text, no watermark."
)
_ESCENAS = {
    "fútbol": "friends playing a casual 7-a-side football match, one player shooting at goal",
    "futsal": "friends playing a fast futsal match",
    "tenis": "two players rallying, one hitting a forehand",
    "pádel": "four players playing a doubles padel point near the glass walls",
    "pickleball": "four players playing pickleball at the net",
    "vóley": "players playing a volleyball rally",
    "básquet": "friends playing a pickup basketball game",
}
_PAIS = {"PE": "Peru", "BO": "Bolivia", "EC": "Ecuador"}


# ── configuración y gasto ────────────────────────────────────────────────────
def _cfg(clave: str, defecto: str) -> str:
    from db.store import stores
    v = stores.config.get(clave)
    return defecto if v is None or str(v).strip() == "" else str(v)


def _num(clave: str, defecto: float) -> float:
    try:
        return max(0.0, float(_cfg(clave, str(defecto))))
    except ValueError:
        return defecto


def costo_imagen() -> float:
    return _num("ai_mkt_costo_imagen", 0.07)


def segundos_video() -> int:
    s = int(_num("ai_mkt_video_seg", 12))
    return s if s in VIDEO_SEGUNDOS else 12


VIDEO_SEGUNDOS = (8, 12, 16)


def tope_usd() -> float:
    return _num("ai_mkt_media_tope_usd", 20)


def _mes() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _gasto_crudo() -> dict:
    try:
        g = json.loads(_cfg("ai_mkt_media_gasto", "{}"))
    except ValueError:
        g = {}
    if not isinstance(g, dict) or g.get("mes") != _mes():
        g = {"mes": _mes(), "usd": 0.0, "imagenes": 0, "videos": 0, "segundos": 0}
    return g


def gasto() -> dict:
    g = _gasto_crudo()
    tope = tope_usd()
    return {**g, "usd": round(float(g.get("usd") or 0), 2), "tope_usd": tope,
            "disponible_usd": round(max(0.0, tope - float(g.get("usd") or 0)), 2)}


def _reservar(usd: float, tipo: str, unidades: int = 1) -> bool:
    """Descuenta del tope ANTES de pedir. False = no alcanza."""
    from db.store import stores
    with _lock:
        g = _gasto_crudo()
        if float(g.get("usd") or 0) + usd > tope_usd() + 1e-9:
            return False
        g["usd"] = round(float(g.get("usd") or 0) + usd, 4)
        if tipo == "imagen":
            g["imagenes"] = int(g.get("imagenes") or 0) + unidades
        else:
            g["videos"] = int(g.get("videos") or 0) + 1
            g["segundos"] = int(g.get("segundos") or 0) + unidades
        stores.config["ai_mkt_media_gasto"] = json.dumps(g)
    return True


def _devolver(usd: float, tipo: str, unidades: int = 1) -> None:
    """La petición falló antes de generar nada: OpenAI no la cobra."""
    from db.store import stores
    with _lock:
        g = _gasto_crudo()
        g["usd"] = round(max(0.0, float(g.get("usd") or 0) - usd), 4)
        if tipo == "imagen":
            g["imagenes"] = max(0, int(g.get("imagenes") or 0) - unidades)
        else:
            g["videos"] = max(0, int(g.get("videos") or 0) - 1)
            g["segundos"] = max(0, int(g.get("segundos") or 0) - unidades)
        stores.config["ai_mkt_media_gasto"] = json.dumps(g)


def disponible() -> bool:
    import config
    return bool(config.OPENAI_API_KEY)


def alcanza_imagen() -> bool:
    return disponible() and gasto()["disponible_usd"] + 1e-9 >= costo_imagen()


def alcanza_video() -> bool:
    """El video se arma en casa (sin costo): basta con poder pagar la foto ambientada."""
    return alcanza_imagen()


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _multipart(campos: dict, archivos: dict) -> tuple[bytes, str]:
    limite = f"----pichangol{uuid.uuid4().hex}"
    buf = io.BytesIO()
    for k, v in campos.items():
        buf.write(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (nombre, datos, tipo) in archivos.items():
        buf.write(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{nombre}\"\r\n"
                  f"Content-Type: {tipo}\r\n\r\n".encode())
        buf.write(datos)
        buf.write(b"\r\n")
    buf.write(f"--{limite}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={limite}"


def _openai(metodo: str, ruta: str, *, cuerpo: bytes | None = None, tipo: str | None = None, timeout: int = _TIMEOUT,
            crudo: bool = False):
    import config
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    if tipo:
        headers["Content-Type"] = tipo
    req = urllib.request.Request(f"https://api.openai.com/v1/{ruta}", data=cuerpo, method=metodo, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        datos = r.read()
    return datos if crudo else json.loads(datos.decode() or "{}")


def _error(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        try:
            j = json.loads(e.read().decode() or "{}")
            return f"HTTP {e.code}: {str((j.get('error') or {}).get('message') or j)[:200]}"
        except Exception:  # noqa: BLE001
            return f"HTTP {e.code}"
    return str(e)[:200]


def _descargar(url: str) -> bytes | None:
    if url.startswith("mem:"):
        from marketing.agente_ia import creativo
        return creativo.leer(url[4:], None)
    if url.startswith("data:"):
        import base64
        return base64.b64decode(url.split(",", 1)[1])
    if not url.startswith("https://"):
        return None
    try:
        with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310
            return r.read()
    except Exception:  # noqa: BLE001
        return None


def _a_jpeg(datos: bytes, tam: tuple[int, int] | None = None, max_lado: int = 1536) -> bytes:
    """Normaliza la foto del dueño: JPEG RGB; con `tam`, recorte centrado exacto
    (para el video)."""
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    if tam:
        img = ImageOps.fit(img, tam, Image.LANCZOS)
    else:
        img.thumbnail((max_lado, max_lado), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def _prompt(plantilla: str, deporte: str, pais: str, hora: int) -> str:
    escena = _ESCENAS.get(deporte, "friends playing a casual match")
    luz = "evening floodlights" if hora >= 18 or hora < 6 else "late afternoon sunlight"
    return plantilla.format(deporte=deporte or "sports", pais=_PAIS.get(pais, "Peru"), escena=escena, luz=luz)


# ── foto ambientada ──────────────────────────────────────────────────────────
def ambientar(foto_url: str, *, deporte: str, pais: str = "PE", hora: int = 19) -> tuple[bytes | None, str]:
    """(JPEG, motivo). La foto REAL del dueño con jugadores y ambiente."""
    import config
    if not disponible():
        return None, "sin_llave"
    original = _descargar(foto_url)
    if not original:
        return None, "sin_foto"
    if not _reservar(costo_imagen(), "imagen"):
        return None, MOTIVO_TOPE
    try:
        foto = _a_jpeg(original)
        cuerpo, tipo = _multipart({"model": config.IMAGE_EDIT_MODEL, "prompt": _prompt(PROMPT_AMBIENTAR, deporte, pais, hora),
                                   "size": "1536x1024", "quality": "medium", "input_fidelity": "high", "n": "1"},
                                  {"image": ("cancha.jpg", foto, "image/jpeg")})
        j = _openai("POST", "images/edits", cuerpo=cuerpo, tipo=tipo)
        dato = (j.get("data") or [{}])[0]
        if dato.get("b64_json"):
            import base64
            crudo = base64.b64decode(dato["b64_json"])
        elif dato.get("url"):
            crudo = _descargar(dato["url"])
        else:
            crudo = None
        if not crudo:
            return None, "sin_respuesta"
        return _a_jpeg(crudo), "ok"
    except Exception as e:  # noqa: BLE001
        motivo = _error(e)
        if isinstance(e, urllib.error.HTTPError):
            _devolver(costo_imagen(), "imagen")          # OpenAI respondió error: no se generó ni se cobra
        print(f"[agente_ia] ambientar falló: {motivo}", flush=True)
        return None, motivo


# ── video con movimiento (en casa) ───────────────────────────────────────────
# OpenAI APAGÓ la API de Sora (/v1/videos) el 24-sep-2026 sin reemplazo: el 1.er
# pedido real en QAS respondió 404. El video se arma aquí, gratis, con las
# mismas piezas de la torre de Facebook: las fotos (la ambientada + las reales)
# con movimiento tipo Ken Burns (`marketing/foto_video.py`) y luego el pulido
# Pichangol (`video_pulido.pulir`: logo, intro, rótulo con el título, cierre con
# www.pichangol.app y música original). Si algún día se contrata un generador de
# video con IA (p. ej. Veo de Google), entra como otro `proveedor` aquí.
PROVEEDOR_VIDEO = "movimiento"
SEG_POR_FOTO = (1.5, 6.0)


def encargar_video(fotos: list[str], *, mood: str = "energetico") -> dict:
    """Deja el video PEDIDO (el render corre en el cron, no en la corrida del
    plan ni en la request de la torre)."""
    fotos = [u for u in fotos or [] if u][:5]
    if not fotos:
        return {"estado": "fallo", "motivo": "sin_foto"}
    return {"estado": "generando", "proveedor": PROVEEDOR_VIDEO, "fotos": fotos, "segundos": segundos_video(),
            "mood": mood if mood in ("chill", "energetico", "epico") else "energetico", "pedido_en": time.time()}


def consultar_video(v: dict, *, titulo: str = "") -> dict:
    """Renderiza el video pedido. Con 'listo' trae `_mp4` (bytes) para que el
    llamador lo suba; con 'fallo', el motivo (la pieza sale con la foto)."""
    import os
    import tempfile
    from marketing import foto_video
    from marketing import video_pulido as vp
    if v.get("proveedor") != PROVEEDOR_VIDEO:
        return {**v, "estado": "fallo", "motivo": "Proveedor de video no disponible (la API de Sora fue cerrada por OpenAI)."}
    datos = [d for d in (_descargar(u) for u in v.get("fotos") or []) if d]
    if not datos:
        return {**v, "estado": "fallo", "motivo": "No se pudieron leer las fotos del local."}
    tmp = tempfile.mkdtemp(prefix="pcg_mkt_video_")
    crudo, final = os.path.join(tmp, "fotos.mp4"), os.path.join(tmp, "final.mp4")
    try:
        lo, hi = SEG_POR_FOTO
        foto_video.generar([_a_jpeg(d) for d in datos], crudo, formato="cuadrado",
                           segundos=max(lo, min(hi, float(v.get("segundos") or 12) / len(datos))))
        vp.pulir(crudo, final, {"formato": "cuadrado", "logo": True, "intro": True, "cierre": True, "rotulo": bool(titulo),
                                "titulo": titulo, "segmentos": [], "musica_modo": "protagonista", "mood": v.get("mood") or "energetico"})
        with open(final, "rb") as f:
            mp4 = f.read()
        return {**v, "estado": "listo", "_mp4": mp4, "bytes": len(mp4)}
    except Exception as e:  # noqa: BLE001
        print(f"[agente_ia] no se pudo armar el video: {str(e)[:200]}", flush=True)
        return {**v, "estado": "fallo", "motivo": f"No se pudo armar el video: {str(e)[:160]}"}
    finally:
        for r in (crudo, final):
            try:
                os.remove(r)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def procesar_videos() -> int:
    """Cron: avanza los videos en curso de las piezas abiertas. Devuelve cuántos cambiaron."""
    from marketing.agente_ia import creativo
    from marketing.agente_ia.repo import repo
    n = 0
    for c in repo().listar_contenidos(estados=("PENDING_APPROVAL", "APPROVED", "DRAFT"), limite=100):
        op = c.get("oportunidad") or {}
        receta = op.get("media") or {}
        v = receta.get("video_ia") or {}
        if v.get("estado") != "generando":
            continue
        nuevo = consultar_video(v, titulo=c.get("title") or "")
        if nuevo == v:
            continue
        mp4 = nuevo.pop("_mp4", None)
        if nuevo.get("estado") == "listo":
            url = creativo.guardar_video(c["id"], mp4)
            if not url:
                nuevo = {**v, "motivo": "No se pudo guardar el video en Storage; reintento."}
            else:
                nuevo["url"] = url
                _reservar(0.0, "video", int(nuevo.get("segundos") or 0))     # solo cuenta: el video es gratis
        receta = {**receta, "video_ia": nuevo}
        if nuevo.get("estado") == "fallo":
            receta["formato"] = receta.get("formato_foto") or "cuadrado"
        estado_actual = c["status"]
        if repo().cambiar_estado(c["id"], (estado_actual,), estado_actual, oportunidad={**op, "media": receta}):
            repo().log("creative", f"video_{nuevo.get('estado')}", content_id=c["id"], motivo=nuevo.get("motivo", ""))
            n += 1
    return n
