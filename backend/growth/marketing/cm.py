"""Community manager AUTÓNOMO — orquestación (Fase 0 · scheduler).

Guarda la config del CM por academia (activo, cada cuántos días, tono/contexto,
datos del negocio) y PRE-GENERA el "post del día" (copy + hashtags + flyer) en
una cadencia, para que el dueño lo encuentre LISTO al abrir la app.

El auto-publish en Meta (IG/FB) es la fase siguiente; el PUSH al dueño ("tu post
está listo") usa el camino FCM de Supabase, que se enchufa aparte. Aquí sólo se
pre-genera y se deja disponible.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import config
from db.store import stores

from .flyer import CONTEXTO_TIPO, generar_flyer
from .posts import generar_posts
from .reel import generar_reel


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def config_cm(academia_id: str, *, activo: bool | None = None,
              cada_dias: int | None = None, contexto: str | None = None,
              datos: dict | None = None, auto_publicar: bool | None = None) -> dict:
    """Crea o actualiza la config del CM de una academia. Devuelve la config."""
    c = stores.cm.setdefault(academia_id, {
        "activo": False, "cada_dias": 3, "contexto": "", "datos": {},
        "ultimo_post": None, "ultimo_generado": "", "auto_publicar": False,
        "ultima_publicacion": None,
    })
    if activo is not None:
        c["activo"] = bool(activo)
    if cada_dias is not None:
        c["cada_dias"] = max(1, int(cada_dias))
    if contexto is not None:
        c["contexto"] = str(contexto)
    if datos:
        c["datos"] = dict(datos)
    if auto_publicar is not None:
        c["auto_publicar"] = bool(auto_publicar)
    return c


def _generar_post(datos: dict, contexto: str, tipo: str | None = None) -> dict:
    """Genera copy + hashtags (IA/plantilla) + flyer (imagen en memoria). Elige un
    TIPO de post (promo/horario/logros/testimonio/tip) y orienta copy y diseño con
    él, para que texto e imagen concuerden y los posts no se repitan."""
    if tipo not in CONTEXTO_TIPO:
        tipo = random.choice(list(CONTEXTO_TIPO.keys()))
    hint = CONTEXTO_TIPO.get(tipo, "")
    ctx = f"{contexto}. {hint}".strip(". ") if contexto else hint
    posts = generar_posts(datos or {}, ctx, 1)
    post = posts[0] if posts else {"texto": "", "hashtags": [],
                                    "hora_sugerida": ""}
    imagen_id = ""
    png = generar_flyer(datos or {}, str(post.get("texto") or ""), tipo=tipo)
    if png:
        imagen_id = stores.guardar_imagen(png, "image/png",
                                          tope=config.IMG_MAX_RETENIDAS)
    return {
        "texto": post.get("texto", ""),
        "hashtags": post.get("hashtags", []),
        "hora_sugerida": post.get("hora_sugerida", ""),
        "imagen_id": imagen_id,
        "tipo": tipo,
    }


def _tiene_fotos(datos: dict) -> bool:
    fotos = datos.get("fotos")
    return isinstance(fotos, list) and any(
        str(u or "").startswith("http") for u in fotos)


def _generar_reel_id(datos: dict, gancho: str, tipo: str | None) -> str:
    """Arma el REEL y lo guarda en memoria; devuelve su id (o '' si no se pudo).
    Best-effort: pesa, así que sólo tiene sentido con fotos del negocio."""
    if not _tiene_fotos(datos):
        return ""
    try:
        mp4 = generar_reel(datos, gancho, tipo=tipo)
    except Exception:  # noqa: BLE001
        return ""
    if not mp4:
        return ""
    return stores.guardar_video(mp4, "video/mp4")


def generar_para(academia_id: str, *, con_reel: bool = False) -> dict | None:
    """Genera y guarda el post del día de una academia. Devuelve el post o None.
    [con_reel] arma TAMBIÉN el reel (sólo el scheduler lo pide, en segundo plano:
    pesa y no debe bloquear la activación desde el APK)."""
    c = stores.cm.get(academia_id)
    if not c:
        return None
    datos = c.get("datos") or {}
    post = _generar_post(datos, c.get("contexto") or "")
    if con_reel:
        post["reel_id"] = _generar_reel_id(
            datos, str(post.get("texto") or ""), post.get("tipo"))
    c["ultimo_post"] = post
    c["ultimo_generado"] = _ahora().isoformat()
    return post


def _media_urls(post: dict) -> tuple[str, str]:
    """URLs públicas ABSOLUTAS (para que Meta baje la media) del flyer y el reel
    pre-generados, si siguen en memoria. Necesita config.PUBLIC_BASE_URL."""
    base = (config.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return "", ""
    img_id = post.get("imagen_id") or ""
    vid_id = post.get("reel_id") or ""
    img = f"{base}/marketing/img/{img_id}.png" \
        if img_id and img_id in stores.imagenes else ""
    vid = f"{base}/marketing/vid/{vid_id}.mp4" \
        if vid_id and vid_id in stores.videos else ""
    return img, vid


def _auto_publicar(academia_id: str, c: dict, post: dict) -> None:
    """Publica SOLO el post recién generado en las redes conectadas del dueño (si
    el auto-publish está activo). Preferir el REEL; si no, el flyer. Best-effort:
    guarda el resultado en c['ultima_publicacion'] y nunca lanza."""
    if not c.get("auto_publicar"):
        return
    # Importación diferida para no acoplar (y no romper si falta algo).
    try:
        from . import redes as redes_svc
    except Exception:  # noqa: BLE001
        return
    conx = stores.conexiones_redes.get(academia_id)
    if not conx or conx.get("estado") != "conectado":
        return
    img_url, reel_url = _media_urls(post)
    texto = str(post.get("texto") or "")
    try:
        r = redes_svc.publicar(academia_id, texto,
                               imagen_url=img_url or None,
                               video_url=reel_url or None)
    except Exception:  # noqa: BLE001
        r = {"ok": False, "error": "excepcion"}
    c["ultima_publicacion"] = {
        "en": _ahora().isoformat(),
        "ok": bool(r.get("ok")),
        "con_reel": bool(reel_url),
    }


def _vencido(c: dict, ahora: datetime) -> bool:
    if not c.get("activo"):
        return False
    ug = c.get("ultimo_generado") or ""
    if not ug:
        return True
    try:
        t = datetime.fromisoformat(ug)
    except ValueError:
        return True
    return ahora - t >= timedelta(days=max(1, int(c.get("cada_dias", 3))))


def procesar_cm_pendientes() -> int:
    """Tick del scheduler: genera el post del día de cada academia que toque.
    Devuelve cuántas generó. Fail-safe (una academia que falla no frena al resto)."""
    ahora = _ahora()
    n = 0
    for aid, c in list(stores.cm.items()):
        if _vencido(c, ahora):
            try:
                post = generar_para(aid, con_reel=True)
                if post:
                    _auto_publicar(aid, c, post)
                n += 1
            except Exception:  # noqa: BLE001
                pass
    return n
