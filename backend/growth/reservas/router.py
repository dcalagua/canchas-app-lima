"""Endpoints de REGLAS DE RESERVA (plan nocturno A2).

- `GET  /reservas/politica/{cancha_id}` (público): lo que el jugador debe ver
  antes de pagar (horario por día, franjas, cancelación del club…).
- `GET  /reservas/reglas/{cancha_id}` (dueño): reglas completas para editar.
- `PUT  /reservas/reglas` (dueño): guarda las reglas en una o varias canchas
  SUYAS (p. ej. "aplicar a todas las canchas del local").

El dueño se identifica con `auth_usuario.requiere_usuario` (ID token de Google
verificado o sesión web), NUNCA con un correo en el cuerpo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import auth_usuario
import config
from reservas import reglas
from web import datos

router = APIRouter(prefix="/reservas", tags=["reservas"])


class ReglasReq(BaseModel):
    cancha_ids: list[str] = Field(default_factory=list, max_length=50)
    reglas: dict = Field(default_factory=dict)


def _es_dueno(c: dict | None, email: str) -> bool:
    return bool(c) and not c.get("eliminada") and (c.get("dueno") or "").strip().lower() == email


@router.get("/politica/{cancha_id}", dependencies=auth_usuario.APP)
def politica(cancha_id: str) -> dict:
    c = datos.cancha(cancha_id)
    if not c or c.get("eliminada"):
        raise HTTPException(status_code=404, detail="no_encontrada")
    from pagos import devoluciones
    return {"ok": True, "cancha_id": cancha_id, **reglas.resumen_publico(c),
            "cancelacion_horas": devoluciones.horas_minimas(c),
            "cancelacion_global_horas": float(config.WEB_CANCELACION_HORAS)}


@router.get("/reglas/{cancha_id}", dependencies=auth_usuario.APP)
def ver_reglas(cancha_id: str, email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    c = datos.cancha(cancha_id)
    if not _es_dueno(c, email):
        raise HTTPException(status_code=403, detail="no_es_tu_cancha")
    return {"ok": True, "cancha_id": cancha_id, "reglas": reglas.de_cancha(c),
            "disponible": datos.col_reglas_disponible(),
            "base": {k: c.get(k) for k in ("hora_apertura", "hora_cierre", "duracion_slot_min",
                                           "precio_hora", "precio_turno", "descuento_valle",
                                           "valle_desde", "valle_hasta", "moneda")}}


@router.put("/reglas", dependencies=auth_usuario.APP)
def guardar_reglas(req: ReglasReq, email: str = Depends(auth_usuario.requiere_usuario)) -> dict:
    ids = list(dict.fromkeys(i.strip() for i in req.cancha_ids if i and i.strip()))
    if not ids:
        raise HTTPException(status_code=400, detail="sin_canchas")
    if not datos.col_reglas_disponible():
        raise HTTPException(status_code=503, detail="reglas_no_disponibles")
    for cid in ids:
        if not _es_dueno(datos.cancha(cid), email):
            raise HTTPException(status_code=403, detail="no_es_tu_cancha")
    norm = reglas.normalizar(req.reglas)
    n = datos.guardar_reglas(ids, email, norm)
    if n != len(ids):
        raise HTTPException(status_code=409, detail="no_se_guardo")
    return {"ok": True, "canchas": n, "reglas": norm}
