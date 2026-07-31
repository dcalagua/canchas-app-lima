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


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def config_cm(academia_id: str, *, activo: bool | None = None,
              cada_dias: int | None = None, contexto: str | None = None,
              datos: dict | None = None) -> dict:
    """Crea o actualiza la config del CM de una academia. Devuelve la config."""
    c = stores.cm.setdefault(academia_id, {
        "activo": False, "cada_dias": 3, "contexto": "", "datos": {},
        "ultimo_post": None, "ultimo_generado": "",
    })
    if activo is not None:
        c["activo"] = bool(activo)
    if cada_dias is not None:
        c["cada_dias"] = max(1, int(cada_dias))
    if contexto is not None:
        c["contexto"] = str(contexto)
    if datos:
        c["datos"] = dict(datos)
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


def generar_para(academia_id: str) -> dict | None:
    """Genera y guarda el post del día de una academia. Devuelve el post o None."""
    c = stores.cm.get(academia_id)
    if not c:
        return None
    post = _generar_post(c.get("datos") or {}, c.get("contexto") or "")
    c["ultimo_post"] = post
    c["ultimo_generado"] = _ahora().isoformat()
    return post


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
                generar_para(aid)
                n += 1
            except Exception:  # noqa: BLE001
                pass
    return n
