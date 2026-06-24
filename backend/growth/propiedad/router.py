"""Endpoints de VERIFICACIÓN DE PROPIEDAD (OTP por WhatsApp + aprobación manual)."""

from __future__ import annotations

from fastapi import APIRouter

from models import (
    AprobarManualRequest,
    OtpConfirmarRequest,
    OtpSolicitarRequest,
    ReclamoRequest,
    TriageRequest,
    ValidarReclamoRequest,
)
from propiedad import identidad, reclamos, service, twilio_adapter, whatsapp_adapter

router = APIRouter(prefix="/propiedad", tags=["propiedad"])


# --- Consulta de identidad (DNI persona / RUC negocio) vía Factiliza ---
@router.get("/dni/{dni}")
def get_dni(dni: str) -> dict:
    return identidad.consultar_dni(dni)


@router.get("/ruc/{ruc}")
def get_ruc(ruc: str) -> dict:
    return identidad.consultar_ruc(ruc)


# --- Reclamo con intervención humana + validación en sitio ---
@router.post("/reclamo")
def post_reclamo(req: ReclamoRequest) -> dict:
    """El dueño presiona 'Reclamar': avisa al admin por WhatsApp con un código."""
    return reclamos.crear_reclamo(
        req.cancha_id, req.solicitante_id, req.nombre_local,
        req.telefono_contacto, req.dni, req.ruc, req.relacion,
        req.lat, req.lng)


@router.get("/reclamo/{cancha_id}")
def get_reclamo(cancha_id: str) -> dict:
    return reclamos.estado(cancha_id)


@router.post("/reclamo/{reclamo_id}/triage")
def post_triage(reclamo_id: int, req: TriageRequest) -> dict:
    """El admin vetea al reclamante y aprueba/rechaza (desbloquea el panel)."""
    return reclamos.triage(reclamo_id, req.aprobado, req.revisor, req.nota)


@router.post("/reclamo/{reclamo_id}/aprobar")
def post_aprobar_directo(reclamo_id: int, req: TriageRequest) -> dict:
    """Aprobación DIRECTA (piloto): el admin aprueba y la cancha queda ACTIVA al
    instante (verificada=True), sin validación en sitio. Mismo efecto que el
    botón 'Aprobar y activar' del panel web."""
    return reclamos.aprobar_directo(reclamo_id, req.revisor)


@router.post("/reclamo/{reclamo_id}/listo-para-validar")
def post_listo(reclamo_id: int) -> dict:
    """El dueño guardó su info: pasa a pendiente de validación en sitio."""
    return reclamos.listo_para_validar(reclamo_id)


@router.post("/reclamo/validar")
def post_validar(req: ValidarReclamoRequest) -> dict:
    """El motorizado ingresa el código en el sitio; su GPS debe coincidir."""
    return reclamos.validar_en_sitio(
        req.codigo, req.lat, req.lng, req.validador, req.fotos_urls)


@router.post("/reclamo/{reclamo_id}/activar")
def post_activar(reclamo_id: int) -> dict:
    """Activación manual por el admin (si VALIDADOR_ACTIVA_AUTOMATICO=0)."""
    return reclamos.activar_admin(reclamo_id)


@router.get("/reclamos")
def get_reclamos(estado: str | None = None) -> list[dict]:
    return reclamos.listar(estado)


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
    """Informativo: qué canales de OTP están activos en esta build. El canal
    'activo' respeta OTP_CANAL_PREFERIDO y cae al siguiente disponible."""
    import config

    wa = whatsapp_adapter.disponible()
    twa = twilio_adapter.disponible_whatsapp()
    sms = twilio_adapter.disponible()
    disp = {"whatsapp": wa, "twilio_whatsapp": twa, "sms": sms}
    orden = sorted(disp, key=lambda k: 0 if k == config.OTP_CANAL_PREFERIDO else 1)
    activo = next((k for k in orden if disp[k]), "stub")
    return {"whatsapp": wa, "twilio_whatsapp": twa, "sms": sms, "activo": activo}
