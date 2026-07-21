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

from . import redes as redes_svc
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


@router.get("/l/{academia_id}", response_class=HTMLResponse)
def ver_landing(academia_id: str) -> str:
    d = stores.landings.get(academia_id)
    if not d:
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<div style='font-family:system-ui;text-align:center;padding:60px'>"
            "<h2>Landing no disponible</h2>"
            "<p>Esta página aún no fue generada.</p></div>",
            status_code=404,
        )
    return render_landing(d)
