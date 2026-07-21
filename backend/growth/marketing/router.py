"""Endpoints de MARKETING (fulfillment del servicio de landing/redes).

- POST /marketing/landing  → el APK manda los datos de la academia; el backend
                             los guarda y deja la landing publicada.
- GET  /l/{academia_id}    → PÚBLICO: sirve la landing renderizada (compartible).

El POST exige X-App-Key (igual que pagos/propiedad); el GET es público.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from db.store import stores

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
    datos: dict = {}
    contexto: str = ""
    cantidad: int = 3


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
    aprobar y compartir. Usa Anthropic si hay key; si no, plantillas."""
    posts = generar_posts(req.datos or {}, req.contexto, req.cantidad)
    return {"ok": True, "posts": posts,
            "via": "ia" if config.ANTHROPIC_API_KEY else "plantilla"}


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
