"""Endpoint del CONCIERGE de reservas (primer agente de IA).

Público (app del jugador): un POST con el mensaje en lenguaje natural + las
canchas que la app ya conoce. Protegido con X-App-Key igual que el resto de
endpoints públicos (solo el APK oficial). No expone la API key de Anthropic
(vive como secret en Railway).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import config
from concierge import service

router = APIRouter(prefix="/concierge", tags=["concierge"])


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    """Solo el APK oficial (que trae X-App-Key). Si APP_API_KEY no está seteada,
    no se exige (rollout gradual)."""
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


class CanchaCtx(BaseModel):
    id: str
    nombre: str = ""
    deporte: str = ""
    distrito: str = ""
    club: str = ""
    direccion: str = ""
    precioHora: float = 0.0
    distanciaKm: float | None = None


class ReservasRequest(BaseModel):
    mensaje: str
    canchas: list[CanchaCtx] = []
    ahora: str | None = None
    presupuesto: float | None = None


@router.post("/reservas", dependencies=[Depends(_require_app_key)])
def reservas(req: ReservasRequest) -> dict:
    canchas = [c.model_dump() for c in req.canchas]
    return service.recomendar(
        req.mensaje, canchas, ahora=req.ahora, presupuesto=req.presupuesto
    )
