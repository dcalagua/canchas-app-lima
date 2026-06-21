"""Endpoints del subsistema SOLICITUDES POR ZONA."""

from __future__ import annotations

from fastapi import APIRouter, Header

from models import RegistrarSolicitudRequest, SolicitudRequest
from solicitudes import service

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])


@router.post("")
def post_solicitud(req: SolicitudRequest,
                   idempotency_key: str | None = Header(default=None)) -> dict:
    return service.crear(
        req.usuario_id, req.nombre_cancha_libre, req.direccion_texto,
        distrito=req.distrito, zona=req.zona, lat=req.lat, lng=req.lng,
        idem_key=idempotency_key)


@router.get("/ranking")
def get_ranking(zona: str | None = None) -> list[dict]:
    """Ranking de canchas más pedidas (prioriza verificadores)."""
    return service.ranking(zona)


@router.post("/{solicitud_id}/registrar")
def post_registrar(solicitud_id: int, req: RegistrarSolicitudRequest) -> dict:
    return service.marcar_registrada(solicitud_id, req.cancha_id)
