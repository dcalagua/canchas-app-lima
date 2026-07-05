"""Endpoints de CONVOCATORIAS ("pichangas" programadas con cupos + 3 modos).

Público (app del jugador/dueño, identificado por email/Google): crear, listar,
inscribir, cancelar, cerrar, asistencia y ranking. El admin del club es el rol
"dueño" del APK; NO usa el token de la torre de control para el día a día.

Sólo el DEFAULT GLOBAL del modo (config SaaS) se protege con X-Admin-Token, igual
que el modo de aprobación de propiedad. El modo por convocatoria lo elige el
dueño al crearla (campo `modo_asignacion`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

import config
from convocatorias import service
from models import (
    AsistenciaRequest,
    CancelarInscripcionRequest,
    CerrarConvocatoriaRequest,
    CrearConvocatoriaRequest,
    InscribirRequest,
    ModoAsignacionRequest,
)

router = APIRouter(prefix="/convocatorias", tags=["convocatorias"])


def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Auth de operador (torre de control): protege sólo el default global del
    modo. Sin token configurado, fail-closed (503)."""
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="admin_no_configurado")
    if x_admin_token != config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=401, detail="token_invalido")


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    """Gatea los endpoints PÚBLICOS de la app: solo el APK oficial (que envía
    X-App-Key) puede llamarlos. Mismo esquema que propiedad. Si APP_API_KEY no
    está configurada, no se exige (despliegue gradual)."""
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_ADMIN = [Depends(_require_admin)]
_APP = [Depends(_require_app_key)]


@router.post("", dependencies=_APP)
def post_crear(req: CrearConvocatoriaRequest,
               idempotency_key: str | None = Header(default=None)) -> dict:
    return service.crear(
        req.club_id, req.titulo, req.deporte, req.cupos,
        categoria=req.categoria, fecha_partido=req.fecha_partido,
        apertura=req.apertura, cierre=req.cierre,
        modo_asignacion=req.modo_asignacion, creado_por=req.creado_por,
        idem_key=idempotency_key)


@router.get("", dependencies=_APP)
def get_listar(club_id: str | None = None, estado: str | None = None) -> list[dict]:
    return service.listar(club_id, estado)


# Rutas estáticas ANTES de /{conv_id} para que no las capture el path param.
@router.get("/ranking", dependencies=_APP)
def get_ranking(club_id: str | None = None) -> list[dict]:
    """Ranking de recurrencia por socio (trazabilidad)."""
    return service.ranking_socios(club_id)


@router.get("/config/modo", dependencies=_APP)
def get_config_modo() -> dict:
    return service.config_modo()


@router.put("/config/modo", dependencies=_ADMIN)
def put_config_modo(req: ModoAsignacionRequest) -> dict:
    return service.set_modo_global(req.modo)


@router.get("/{conv_id}", dependencies=_APP)
def get_detalle(conv_id: int, socio: str = "") -> dict:
    d = service.detalle(conv_id)
    if socio and d.get("ok"):
        d["mi_estado"] = service.estado_socio(conv_id, socio)
    return d


@router.post("/{conv_id}/inscribir", dependencies=_APP)
def post_inscribir(conv_id: int, req: InscribirRequest,
                   idempotency_key: str | None = Header(default=None)) -> dict:
    return service.inscribir(conv_id, req.socio_id, req.socio_nombre,
                             idem_key=idempotency_key)


@router.post("/{conv_id}/cancelar", dependencies=_APP)
def post_cancelar(conv_id: int, req: CancelarInscripcionRequest) -> dict:
    return service.cancelar(conv_id, req.socio_id)


@router.post("/{conv_id}/cerrar", dependencies=_APP)
def post_cerrar(conv_id: int, req: CerrarConvocatoriaRequest) -> dict:
    return service.cerrar(conv_id, req.semilla)


@router.post("/{conv_id}/reabrir", dependencies=_APP)
def post_reabrir(conv_id: int) -> dict:
    return service.reabrir(conv_id)


@router.post("/{conv_id}/asistencia", dependencies=_APP)
def post_asistencia(conv_id: int, req: AsistenciaRequest) -> dict:
    return service.marcar_asistencia(
        conv_id, [a.model_dump() for a in req.asistencias])
