"""Endpoints de MARKETING (fulfillment del servicio de landing/redes).

- POST /marketing/landing  → el APK manda los datos de la academia; el backend
                             los guarda y deja la landing publicada.
- GET  /l/{academia_id}    → PÚBLICO: sirve la landing renderizada (compartible).

El POST exige X-App-Key (igual que pagos/propiedad); el GET es público.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

import config
from db.store import stores

from . import link_preview as link_preview_svc
from . import redes as redes_svc
from .flyer import generar_flyer
from .landing import render_landing
from .posts import generar_posts

router = APIRouter(tags=["marketing"])


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


class LandingReq(BaseModel):
    academia_id: str
    datos: dict


class PostsReq(BaseModel):
    academia_id: str = ""
    datos: dict = {}
    contexto: str = ""
    cantidad: int = 3


class RedesConectarReq(BaseModel):
    academia_id: str
    dueno_id: str = ""


class RedesAccionReq(BaseModel):
    academia_id: str


class RedesPublicarReq(BaseModel):
    academia_id: str
    texto: str
    imagen_url: str | None = None


class ImagenReq(BaseModel):
    academia_id: str = ""
    data_b64: str
    content_type: str = "image/jpeg"


_IMG_TIPOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _base_publica(request: Request) -> str:
    """URL absoluta base del backend (para que Meta pueda descargar la imagen)."""
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.post("/marketing/landing", dependencies=_APP)
def generar_landing(req: LandingReq) -> dict:
    """Guarda/actualiza los datos de la landing de una academia. La página queda
    publicada al instante en /l/{academia_id}."""
    if not req.academia_id:
        raise HTTPException(status_code=400, detail="academia_id_requerido")
    stores.landings[req.academia_id] = dict(req.datos or {})
    return {"ok": True, "path": f"/l/{req.academia_id}"}


@router.post("/marketing/posts", dependencies=_APP)
def generar_posts_endpoint(req: PostsReq) -> dict:
    """Community manager con IA: devuelve posts (texto + hashtags + hora) para
    aprobar y compartir. Usa Anthropic si hay key; si no, plantillas.

    Aplica un TOPE mensual de generaciones por academia (config
    MARKETING_POSTS_LIMITE_MES) para proteger el costo de Anthropic ante clics
    repetidos."""
    periodo = datetime.now(timezone.utc).strftime("%Y-%m")
    # Tope editable desde la torre de control (config), con respaldo al env.
    lim = stores.cfg_int("marketing_posts_limite_mes")
    aid = req.academia_id
    usados = int((stores.marketing_uso.get(aid, {}) or {}).get(periodo, 0)) if aid else 0
    if aid and lim > 0 and usados >= lim:
        return {"ok": False, "limite": True, "usados": usados,
                "limite_mes": lim, "posts": []}
    posts = generar_posts(req.datos or {}, req.contexto, req.cantidad)
    if aid:
        u = stores.marketing_uso.setdefault(aid, {})
        u[periodo] = usados + 1
    return {"ok": True, "posts": posts, "usados": usados + 1, "limite_mes": lim,
            "via": "ia" if config.ANTHROPIC_API_KEY else "plantilla"}


@router.post("/marketing/cm/post-del-dia", dependencies=_APP)
def cm_post_del_dia(req: PostsReq, request: Request) -> dict:
    """Community manager AUTÓNOMO (Fase 0): genera UN post LISTO — copy +
    hashtags (IA o plantilla) + un FLYER de marca (imagen) — para publicar en 1
    toque. Es el mismo pipeline que luego auto-publica (Fase 1/2 con Meta)."""
    from . import cm as cm_svc
    post = cm_svc._generar_post(req.datos or {}, req.contexto)
    imagen_url = ""
    img_id = post.get("imagen_id") or ""
    if img_id and img_id in stores.imagenes:
        imagen_url = f"{_base_publica(request)}/marketing/img/{img_id}.png"
    return {
        "ok": True,
        "texto": post.get("texto", ""),
        "hashtags": post.get("hashtags", []),
        "hora_sugerida": post.get("hora_sugerida", ""),
        "imagen_url": imagen_url,
        "via": "ia" if config.ANTHROPIC_API_KEY else "plantilla",
    }


class CmConfigReq(BaseModel):
    academia_id: str
    activo: bool = True
    cada_dias: int = 3
    contexto: str = ""
    datos: dict = {}


def _cm_estado(academia_id: str, request: Request) -> dict:
    """Config del CM + el post del día ya pre-generado (con la URL del flyer). Si
    la imagen se perdió (reinicio del backend), la regenera con el texto guardado."""
    c = stores.cm.get(academia_id)
    if not c:
        return {"activo": False, "cada_dias": 3, "contexto": "",
                "ultimo_generado": "", "post": None}
    post = c.get("ultimo_post")
    imagen_url = ""
    if post:
        img_id = post.get("imagen_id") or ""
        if img_id and img_id in stores.imagenes:
            imagen_url = f"{_base_publica(request)}/marketing/img/{img_id}.png"
        elif c.get("datos"):
            png = generar_flyer(c.get("datos") or {},
                                str(post.get("texto") or ""),
                                tipo=post.get("tipo"))
            if png:
                img_id = stores.guardar_imagen(png, "image/png",
                                               tope=config.IMG_MAX_RETENIDAS)
                post["imagen_id"] = img_id
                imagen_url = f"{_base_publica(request)}/marketing/img/{img_id}.png"
    return {
        "activo": bool(c.get("activo", False)),
        "cada_dias": int(c.get("cada_dias", 3)),
        "contexto": c.get("contexto", ""),
        "ultimo_generado": c.get("ultimo_generado", ""),
        "post": None if not post else {
            "texto": post.get("texto", ""),
            "hashtags": post.get("hashtags", []),
            "hora_sugerida": post.get("hora_sugerida", ""),
            "imagen_url": imagen_url,
        },
    }


@router.post("/marketing/cm/config", dependencies=_APP)
def cm_config(req: CmConfigReq, request: Request) -> dict:
    """Activa/configura el CM AUTÓNOMO de una academia (cada cuántos días, tono,
    datos del negocio). Al activar, genera un post de una vez para que lo vea ya.
    El scheduler del backend lo va renovando en la cadencia."""
    from . import cm as cm_svc
    c = cm_svc.config_cm(req.academia_id, activo=req.activo,
                         cada_dias=req.cada_dias, contexto=req.contexto,
                         datos=req.datos or None)
    if c["activo"] and not c.get("ultimo_post"):
        cm_svc.generar_para(req.academia_id)
    return {"ok": True, **_cm_estado(req.academia_id, request)}


@router.get("/marketing/cm/estado/{academia_id}", dependencies=_APP)
def cm_estado(academia_id: str, request: Request) -> dict:
    """El post del día PRE-GENERADO + la config del CM (para el APK)."""
    return _cm_estado(academia_id, request)


@router.post("/marketing/cm/reel-del-dia", dependencies=_APP)
def cm_reel_del_dia(req: PostsReq, request: Request) -> dict:
    """Auto-arma un REEL vertical (video 9:16) con las FOTOS del negocio + marca,
    listo para subir a Instagram/Facebook (el dueño le pone la música ahí). On-
    demand (pesa): el flyer sigue siendo lo instantáneo. Fail-safe: si no se puede
    generar (sin ffmpeg/Pillow), devuelve ok=False y el APK muestra un aviso."""
    from .reel import generar_reel

    datos = req.datos or {}
    # Reusa el copy/tipo del post del día si ya existe (mismo mensaje que el flyer).
    gancho = req.contexto or ""
    tipo = None
    c = stores.cm.get(req.academia_id)
    if c and c.get("ultimo_post"):
        up = c["ultimo_post"]
        gancho = gancho or str(up.get("texto") or "")
        tipo = up.get("tipo")
        if not datos:
            datos = c.get("datos") or {}
    if not gancho:
        posts = generar_posts(datos, "", 1)
        gancho = str((posts[0].get("texto") if posts else "") or "")

    mp4 = generar_reel(datos, gancho, tipo=tipo)
    if not mp4:
        return {"ok": False, "motivo": "no_disponible", "reel_url": ""}
    vid_id = stores.guardar_video(mp4, "video/mp4")
    reel_url = f"{_base_publica(request)}/marketing/vid/{vid_id}.mp4"
    return {"ok": True, "reel_url": reel_url}


@router.get("/marketing/vid/{nombre}")
def ver_video(nombre: str) -> Response:
    """PÚBLICO: sirve un reel (video) alojado en memoria (hosting transitorio)."""
    vid_id = nombre.split(".")[0]
    vid = stores.videos.get(vid_id)
    if not vid:
        raise HTTPException(status_code=404, detail="no_encontrado")
    return Response(content=vid["bytes"],
                    media_type=vid.get("content_type", "video/mp4"),
                    headers={"Cache-Control": "public, max-age=86400"})


# ------ Gestión de redes (Nivel 2): conexión OAuth + publicación ------------
@router.get("/marketing/redes/diag")
def redes_diag() -> dict:
    """Diagnóstico PÚBLICO (sin secretos): qué config de Meta ve el backend en
    caliente. Sirve para confirmar que Railway aplicó las variables nuevas.
    No expone el App Secret (solo si está o no)."""
    return {
        "modo": redes_svc.modo(),
        "redirect_uri": config.META_REDIRECT_URI,
        "public_base_url": config.PUBLIC_BASE_URL,
        "config_id": config.META_LOGIN_CONFIG_ID,
        "app_id": config.META_APP_ID,
        "tiene_app_secret": bool(config.META_APP_SECRET),
        "graph_version": config.META_GRAPH_VERSION,
        "credenciales_validas": redes_svc.verificar_credenciales(),
        "login_url_ejemplo": redes_svc.login_url("DIAG"),
    }


@router.get("/marketing/redes/estado/{academia_id}", dependencies=_APP)
def redes_estado(academia_id: str) -> dict:
    """Estado de la conexión de redes del dueño (enmascarado, sin token)."""
    return {"ok": True, "modo": redes_svc.modo(), **redes_svc.estado(academia_id)}


@router.post("/marketing/redes/conectar", dependencies=_APP)
def redes_conectar(req: RedesConectarReq) -> dict:
    """Inicia la conexión. produccion → devuelve login_url (el APK la abre en el
    navegador); sandbox → conecta simulado para probar el flujo."""
    return redes_svc.conectar(req.academia_id, req.dueno_id)


@router.get("/marketing/redes/callback", response_class=HTMLResponse)
def redes_callback(code: str = "", state: str = "",
                   error: str = "", error_description: str = "") -> str:
    """PÚBLICO: Meta redirige aquí tras el permiso del dueño. Intercambia el
    código, guarda la conexión y muestra una página de 'vuelve a la app'."""
    if error:
        msg = error_description or error
        ok = False
    else:
        r = redes_svc.procesar_callback(code, state)
        ok = r.get("ok", False)
        msg = "¡Listo! Ya puedes volver a Pichangol." if ok else \
            (r.get("error") or "No se pudo conectar.")
        # El callback es GET, así que el middleware NO persiste: guardamos el
        # snapshot a mano para que la conexión SOBREVIVA a reinicios/redeploys.
        if ok:
            try:
                from db import pg
                if pg.habilitado:
                    pg.guardar(stores.to_state())
            except Exception:  # noqa: BLE001
                pass
    color = "#14463A" if ok else "#B23B3B"
    icono = "✅" if ok else "⚠️"
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<div style='font-family:system-ui;text-align:center;padding:56px 22px;color:{color}'>"
        f"<div style='font-size:46px'>{icono}</div>"
        f"<h2 style='margin:10px 0'>Conexión de redes</h2>"
        f"<p style='color:#555;font-size:15px'>{msg}</p>"
        "<p style='color:#999;font-size:13px;margin-top:24px'>Puedes cerrar esta ventana.</p>"
        "</div>")


@router.post("/marketing/redes/desconectar", dependencies=_APP)
def redes_desconectar(req: RedesAccionReq) -> dict:
    """Revoca la conexión (deja de publicar por el dueño)."""
    return redes_svc.desconectar(req.academia_id)


@router.post("/marketing/redes/publicar", dependencies=_APP)
def redes_publicar(req: RedesPublicarReq) -> dict:
    """Publica un post aprobado en las redes conectadas del dueño (IG/FB)."""
    return redes_svc.publicar(req.academia_id, req.texto, req.imagen_url)


@router.get("/marketing/link-preview", dependencies=_APP)
def link_preview(url: str) -> dict:
    """Previsualización Open Graph de un enlace (para los posts de canales):
    devuelve título, descripción, imagen y dominio. Cacheado en memoria."""
    return link_preview_svc.obtener(url)


@router.post("/marketing/img", dependencies=_APP)
def subir_imagen(req: ImagenReq, request: Request) -> dict:
    """Aloja una imagen (base64) y devuelve su URL pública ABSOLUTA, para que
    Instagram/Facebook la descarguen al publicar. Hosting transitorio (memoria):
    Meta la baja al instante; no se persiste."""
    ct = req.content_type if req.content_type in _IMG_TIPOS else "image/jpeg"
    try:
        datos = base64.b64decode(req.data_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="imagen_invalida")
    if not datos:
        raise HTTPException(status_code=400, detail="imagen_vacia")
    if len(datos) > config.IMG_MAX_BYTES:
        raise HTTPException(status_code=413, detail="imagen_muy_grande")
    img_id = stores.guardar_imagen(datos, ct, tope=config.IMG_MAX_RETENIDAS)
    ext = _IMG_TIPOS[ct]
    url = f"{_base_publica(request)}/marketing/img/{img_id}.{ext}"
    return {"ok": True, "id": img_id, "url": url}


@router.get("/marketing/img/{nombre}")
def ver_imagen(nombre: str) -> Response:
    """PÚBLICO: sirve una imagen alojada (para el fetch de Meta al publicar)."""
    img_id = nombre.split(".")[0]
    img = stores.imagenes.get(img_id)
    if not img:
        raise HTTPException(status_code=404, detail="no_encontrada")
    return Response(content=img["bytes"], media_type=img.get("content_type",
                                                             "image/jpeg"),
                    headers={"Cache-Control": "public, max-age=86400"})


def _base_landing(request: Request) -> str:
    """Base de MARCA para la URL canónica de la landing: LANDING_BASE_URL si está
    seteado, si no PUBLIC_BASE_URL, y como último recurso el host de la request."""
    if config.LANDING_BASE_URL:
        return config.LANDING_BASE_URL.rstrip("/")
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get("/l/{academia_id}", response_class=HTMLResponse)
def ver_landing(academia_id: str, request: Request) -> str:
    d = stores.landings.get(academia_id)
    if not d:
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<div style='font-family:system-ui;text-align:center;padding:60px'>"
            "<h2>Landing no disponible</h2>"
            "<p>Esta página aún no fue generada.</p></div>",
            status_code=404,
        )
    canonical = f"{_base_landing(request)}/l/{academia_id}"
    return render_landing(d, canonical=canonical)
