"""Endpoints del subsistema VERIFICACION FISICA + la mini-app del verificador."""

from __future__ import annotations

from fastapi import APIRouter

from db.store import como_dict, stores
from models import CapturaRequest, EvaluarRequest
from verificacion_fisica import service

router = APIRouter(prefix="/verificacion-fisica", tags=["verificacion-fisica"])


@router.post("/evaluar")
def post_evaluar(req: EvaluarRequest) -> dict:
    """IA primero: verifica sin visita si el score supera el umbral; si no,
    agenda una visita asignada por zona."""
    return service.evaluar(
        req.cancha_id, req.direccion, req.ruc, req.lat, req.lng, req.zona,
        req.distrito, req.solicitud_id, req.motivo)


@router.get("/visitas")
def get_visitas(zona: str | None = None,
                verificador_id: int | None = None,
                lat: float | None = None,
                lng: float | None = None,
                radio_km: float | None = None) -> list[dict]:
    """Cola de visitas del verificador. Si el verificador manda su GPS
    (lat/lng), cada visita trae la distancia a él y —si se pasa radio_km— se
    filtran las que quedan dentro de ese radio (cola por CERCANÍA, no por zonas
    fijas de Lima). Dentro del radio siguen priorizadas por demanda."""
    return service.visitas(zona, verificador_id, lat, lng, radio_km)


@router.post("/{vf_id}/captura")
def post_captura(vf_id: int, req: CapturaRequest) -> dict:
    return service.captura(vf_id, req.fotos_geo_urls, req.lat_sitio,
                           req.lng_sitio, req.firma_verificador,
                           req.observaciones)


@router.get("/verificadores")
def get_verificadores() -> list[dict]:
    return [como_dict(v) for v in stores.verificadores]
