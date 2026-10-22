"""API del AI Marketing Agent.

* `/admin/api/mkt/*`: torre de control (sesión admin + 2.º paso, `X-Admin-Token`).
  Bandeja de aprobación, calendario, edición, reprogramación, cancelación,
  corrida manual, métricas, aprendizajes y configuración.
* `/go/{codigo}`: short-link PÚBLICO de cada pieza. Cuenta el clic (anónimo:
  hash del navegador, sin IP ni datos personales), deja la cookie de
  atribución `pg_utm` (7 días) y redirige al destino con los UTM.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

import config

from marketing.agente_ia import creativo, orquestador as orq
from marketing.agente_ia.repo import repo

router = APIRouter(tags=["agente_ia"])
COOKIE_UTM = "pg_utm"
COOKIE_DIAS = 7


def _admin(token: str | None) -> str:
    from propiedad import admin_auth
    from propiedad.panel import _check
    _check(token)
    return admin_auth.usuario_de_sesion(token) or "operador"


def _fecha(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida (ISO 8601).")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _err(e: Exception):
    raise HTTPException(status_code=409, detail=str(e))


class ConfigReq(BaseModel):
    activo: bool | None = None
    modo: str | None = None
    hora_plan: str | None = None
    paises: list[str] | None = None
    posts_dia: int | None = None
    umbral: int | None = None
    mix_baja: float | None = None
    mix_alta: float | None = None
    arte_ia: bool | None = None
    destacar_pro: bool | None = None
    tono: str | None = None
    plataformas: list[str] | None = None
    auto_max_dia: int | None = None
    pausa: bool | None = None
    ia_ambientar: bool | None = None
    video_ia: bool | None = None
    pro_cupo_mes: int | None = None
    pro_max_dia: int | None = None
    media_tope_usd: float | None = None
    costo_imagen: float | None = None
    video_seg: int | None = None
    video_motor: str | None = None
    costo_video_seg: float | None = None


class CorrerReq(BaseModel):
    pais: str = "PE"


class EditarReq(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    etiqueta: str | None = None
    texto: str | None = None
    call_to_action: str | None = None


class AccionReq(BaseModel):
    motivo: str = ""
    cuando: str | None = None


@router.get("/admin/api/mkt")
def get_resumen(x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    return {"ok": True, **orq.resumen()}


@router.post("/admin/api/mkt/config")
def post_config(req: ConfigReq, x_admin_token: str | None = Header(default=None)) -> dict:
    usuario = _admin(x_admin_token)
    try:
        cfg = orq.guardar_configuracion({k: v for k, v in req.model_dump().items() if v is not None})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    repo().log("admin", "config", usuario=usuario, **{k: v for k, v in req.model_dump().items() if v is not None})
    return {"ok": True, "config": cfg}


@router.post("/admin/api/mkt/correr")
def post_correr(req: CorrerReq, x_admin_token: str | None = Header(default=None)) -> dict:
    """Corre el ciclo AHORA para un país (rehace la estrategia del día)."""
    usuario = _admin(x_admin_token)
    if req.pais not in orq.ZONAS_PAIS:
        raise HTTPException(status_code=400, detail="País inválido.")
    r = orq.planificar(req.pais, forzar=True)
    repo().log("admin", "correr", usuario=usuario, pais=req.pais)
    return {"ok": True, "fuente": r.get("fuente"), "piezas": [orq.pieza(p["id"]) for p in r.get("piezas", [])]}


@router.get("/admin/api/mkt/piezas")
def get_piezas(estado: str | None = None, desde: str | None = None, hasta: str | None = None,
               x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    return {"ok": True, "piezas": orq.piezas(estado=estado, desde=_fecha(desde), hasta=_fecha(hasta))}


@router.get("/admin/api/mkt/pieza/{cid}")
def get_pieza(cid: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    try:
        return {"ok": True, "pieza": orq.pieza(cid)}
    except orq.Rechazo as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/admin/api/mkt/pieza/{cid}/imagen")
def get_imagen(cid: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    c = repo().contenido(cid)
    if not c:
        raise HTTPException(status_code=404, detail="La pieza no existe.")
    datos = creativo.leer(cid, c.get("media_url"))
    if datos is None:
        receta = (c.get("oportunidad") or {}).get("media") or {}
        datos = creativo.componer(receta, titulo=c.get("title") or "", subtitulo=c.get("subtitle") or "", etiqueta=c.get("etiqueta") or "")
    return {"ok": True, "imagen": "data:image/jpeg;base64," + base64.b64encode(datos).decode()}


@router.post("/admin/api/mkt/pieza/{cid}/editar")
def post_editar(cid: str, req: EditarReq, x_admin_token: str | None = Header(default=None)) -> dict:
    usuario = _admin(x_admin_token)
    try:
        orq.editar(cid, usuario, {k: v for k, v in req.model_dump().items() if v is not None})
    except orq.Rechazo as e:
        _err(e)
    return {"ok": True, "pieza": orq.pieza(cid)}


@router.post("/admin/api/mkt/pieza/{cid}/{accion}")
def post_accion(cid: str, accion: str, req: AccionReq, x_admin_token: str | None = Header(default=None)) -> dict:
    usuario = _admin(x_admin_token)
    try:
        if accion == "aprobar":
            orq.aprobar(cid, usuario, _fecha(req.cuando))
        elif accion == "rechazar":
            orq.rechazar(cid, usuario, req.motivo)
        elif accion == "cancelar":
            orq.cancelar(cid, usuario)
        elif accion == "reprogramar":
            cuando = _fecha(req.cuando)
            if not cuando:
                raise HTTPException(status_code=400, detail="Falta la nueva fecha.")
            orq.reprogramar(cid, usuario, cuando)
        elif accion == "regenerar":
            nueva = orq.regenerar(cid, usuario)
            return {"ok": True, "pieza": orq.pieza(nueva["id"]), "reemplaza": cid}
        elif accion == "publicar":
            orq.publicar_ahora(cid, usuario)
        elif accion == "video":
            orq.pedir_video(cid, usuario)
        else:
            raise HTTPException(status_code=404, detail="Acción desconocida.")
    except orq.Rechazo as e:
        _err(e)
    return {"ok": True, "pieza": orq.pieza(cid)}


@router.get("/admin/api/mkt/logs")
def get_logs(x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    return {"ok": True, "logs": repo().logs_recientes(150)}


@router.get("/admin/api/mkt/estrategia/{eid}")
def get_estrategia(eid: str, x_admin_token: str | None = Header(default=None)) -> dict:
    _admin(x_admin_token)
    e = next((x for x in repo().estrategias_lista(60) if x["id"] == eid), None)
    if not e:
        raise HTTPException(status_code=404, detail="No existe.")
    return {"ok": True, "estrategia": e}


# ── short-link público ───────────────────────────────────────────────────────
def _visitante(request: Request) -> str:
    """Huella ANÓNIMA (no se guarda IP ni agente): sirve solo para contar
    clics únicos por pieza."""
    base = f"{request.headers.get('x-forwarded-for', '').split(',')[0].strip()}|{request.headers.get('user-agent', '')}"
    return hashlib.sha256(base.encode()).hexdigest()[:24]


@router.get("/go/{codigo}")
def go(codigo: str, request: Request) -> Response:
    import config
    base = (config.PUBLIC_BASE_URL or config.MARCA_URL).rstrip("/")
    c = repo().contenido_por_codigo(codigo[:20]) if codigo.isalnum() else None
    if not c:
        return RedirectResponse(base + "/", status_code=302)
    if c["status"] == "PUBLISHED":
        try:
            repo().registrar_clic(c["id"], _visitante(request))
        except Exception:  # noqa: BLE001
            pass
    utm = {"utm_source": c["platform"], "utm_medium": "social", "utm_campaign": c.get("campaign_id") or "agente_ia", "utm_content": codigo}
    destino = c.get("destino_url") or base + "/"
    if not destino.startswith(base):
        destino = base + "/"
    resp = RedirectResponse(f"{destino}{'&' if '?' in destino else '?'}{urlencode(utm)}", status_code=302)
    resp.set_cookie(COOKIE_UTM, codigo, max_age=COOKIE_DIAS * 86400, httponly=True, secure=True, samesite="lax")
    return resp


def utm_de_request(request: Request | None) -> dict | None:
    """Atribución para una reserva web: la pieza de la cookie, si existe y fue
    publicada en los últimos COOKIE_DIAS días."""
    if request is None:
        return None
    codigo = (request.cookies.get(COOKIE_UTM) or "")[:20]
    if not codigo.isalnum():
        return None
    try:
        c = repo().contenido_por_codigo(codigo)
    except Exception:  # noqa: BLE001
        return None
    if not c or c["status"] != "PUBLISHED" or not c.get("published_at"):
        return None
    if datetime.now(timezone.utc) - c["published_at"] > timedelta(days=COOKIE_DIAS):
        return None
    return {"content": codigo, "source": c["platform"], "medium": "social", "campaign": c.get("campaign_id") or ""}
