"""Endpoints del subsistema PUNTOS Y PREMIOS. Idempotentes vía header
'Idempotency-Key'."""

from __future__ import annotations

from fastapi import APIRouter, Header

from models import AcreditarRequest, CanjearRequest, PrimeraReservaRequest
from puntos import service

router = APIRouter(prefix="/puntos", tags=["puntos"])


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


@router.post("/canjear")
def post_canjear(req: CanjearRequest,
                 idempotency_key: str | None = Header(default=None)) -> dict:
    return service.canjear(req.usuario_id, req.puntos_usados, req.tipo_premio,
                           req.fuente_financiamiento, idem_key=idempotency_key)


@router.post("/eventos/primera-reserva")
def post_primera_reserva(req: PrimeraReservaRequest) -> dict:
    return service.evento_primera_reserva(req.cancha_id)
