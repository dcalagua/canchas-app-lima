"""API del submódulo VERIFICACION DE EXISTENCIA (Pichangol).

Ejecutar (desde este directorio):
    uvicorn main:app --reload

Endpoints:
    POST /verificacion/existencia   -> score de existencia (sin datos personales)
    POST /consentimientos           -> registrar consentimiento
    GET  /consentimientos/{sujeto}/{tipo} -> ¿puede recontactarse?
    GET  /health
"""

from __future__ import annotations

from fastapi import FastAPI

from compliance.consent import consent_store
from models import (ConsentimientoRequest, ExistenciaRequest,
                    ExistenciaResponse)
from service import verificar_existencia

app = FastAPI(
    title="Pichangol — Verificación de existencia",
    description="Verificar y NO retener (Ley 29733 + DS 016-2024-JUS).",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/verificacion/existencia", response_model=ExistenciaResponse)
def post_verificacion_existencia(req: ExistenciaRequest) -> ExistenciaResponse:
    return verificar_existencia(req)


@app.post("/consentimientos")
def post_consentimiento(req: ConsentimientoRequest) -> dict:
    c = consent_store.registrar(req.sujeto_id, req.tipo, req.otorgado, req.canal)
    return {
        "sujeto_id": c.sujeto_id, "tipo": c.tipo.value, "otorgado": c.otorgado,
        "fecha": c.fecha.isoformat(),
        "vigencia_hasta": c.vigencia_hasta.isoformat() if c.vigencia_hasta else None,
        "base_legal": c.base_legal,
    }


@app.get("/consentimientos/{sujeto_id}/{tipo}")
def get_puede_recontactar(sujeto_id: str, tipo: str) -> dict:
    return {
        "sujeto_id": sujeto_id, "tipo": tipo,
        "puede_recontactar": consent_store.puede_recontactar(sujeto_id, tipo),
    }
