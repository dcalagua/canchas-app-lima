"""Endpoints de VERIFICACIÓN DE PROPIEDAD (OTP por WhatsApp + aprobación manual)."""

from __future__ import annotations

from fastapi import APIRouter

from models import (
    AprobarManualRequest,
    OtpConfirmarRequest,
    OtpSolicitarRequest,
)
from propiedad import service, whatsapp_adapter

router = APIRouter(prefix="/propiedad", tags=["propiedad"])


@router.get("/estado/{cancha_id}")
def get_estado(cancha_id: str) -> dict:
    return service.estado(cancha_id)


@router.post("/otp/solicitar")
def post_solicitar(req: OtpSolicitarRequest) -> dict:
    """Envía un código al teléfono del local. Si WhatsApp no está configurado,
    corre en modo stub (no envía nada real)."""
    return service.solicitar(req.cancha_id, req.telefono)


@router.post("/otp/confirmar")
def post_confirmar(req: OtpConfirmarRequest) -> dict:
    """Valida el código. Si coincide (y el número prueba propiedad), marca la
    cancha como verificada por su dueño."""
    return service.confirmar(
        req.cancha_id, req.codigo, req.solicitante_id, req.telefono_publico)


@router.post("/aprobar-manual")
def post_aprobar_manual(req: AprobarManualRequest) -> dict:
    """Aprobación/rechazo manual de propiedad (uso interno del equipo)."""
    return service.aprobar_manual(
        req.cancha_id, req.solicitante_id, req.aprobado, req.revisor, req.nota)


@router.get("/canal")
def get_canal() -> dict:
    """Informativo: qué canal de OTP está activo en esta build."""
    return {"whatsapp": whatsapp_adapter.disponible()}
