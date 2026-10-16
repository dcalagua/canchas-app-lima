"""Endpoints del subsistema PUNTOS Y PREMIOS. Idempotentes vía header
'Idempotency-Key'."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

import config
from models import (AcreditarRequest, AcreditarReservaRequest, CanjearRequest,
                    PrimeraReservaRequest)
from puntos import service

router = APIRouter(prefix="/puntos", tags=["puntos"])


def _require_app(x_app_key: str | None = Header(default=None)) -> None:
    """Solo el APK oficial acredita/canjea puntos de fidelidad (son plata).
    Mismo esquema fail-open de pagos: sin APP_API_KEY configurada no se exige
    (rollout gradual)."""
    esperado = (config.APP_API_KEY or "").strip()
    if esperado and (x_app_key or "").strip() != esperado:
        raise HTTPException(status_code=403, detail="app_key_invalida")


_APP = [Depends(_require_app)]


@router.get("/saldo/{usuario_id}")
def get_saldo(usuario_id: str) -> dict:
    return service.saldo(usuario_id)


@router.get("/movimientos/{usuario_id}")
def get_movimientos(usuario_id: str) -> list[dict]:
    return service.movimientos(usuario_id)


@router.post("/acreditar")
def post_acreditar(req: AcreditarRequest,
                   idempotency_key: str | None = Header(default=None)) -> dict:
    return service.acreditar(req.usuario_id, req.accion, req.ref_tipo,
                             req.ref_id, idem_key=idempotency_key)


@router.post("/acreditar-reserva", dependencies=_APP)
def post_acreditar_reserva(req: AcreditarReservaRequest) -> dict:
    """FIDELIDAD: puntos por una reserva efectivamente PAGADA (online al
    pagar; efectivo cuando el dueño la marca pagada). Idempotente por
    reserva_id — reintentos del APK no duplican puntos."""
    return service.acreditar_reserva(
        req.usuario_id, req.monto, req.moneda, req.reserva_id)


@router.post("/canjear", dependencies=_APP)
def post_canjear(req: CanjearRequest,
                 idempotency_key: str | None = Header(default=None)) -> dict:
    return service.canjear(req.usuario_id, req.puntos_usados, req.tipo_premio,
                           req.fuente_financiamiento, idem_key=idempotency_key)


@router.post("/eventos/primera-reserva")
def post_primera_reserva(req: PrimeraReservaRequest) -> dict:
    return service.evento_primera_reserva(req.cancha_id)
