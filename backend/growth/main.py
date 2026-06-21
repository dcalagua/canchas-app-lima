"""API de crecimiento de Pichangol: PUNTOS/PREMIOS + SOLICITUDES POR ZONA +
VERIFICACION FISICA. Tres subsistemas conectados.

Ejecutar (desde este directorio):
    uvicorn main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from compliance.consent import consent_store
from db.store import seed_verificadores, stores
from models import ConfigRequest, ConsentimientoRequest
from puntos.router import router as puntos_router
from solicitudes.router import router as solicitudes_router
from verificacion_fisica.router import router as vf_router

app = FastAPI(
    title="Pichangol — Crecimiento (puntos, zonas, verificación física)",
    description="No-retención de datos personales (Ley 29733). Integraciones en STUB.",
    version="0.1.0",
)

seed_verificadores()

app.include_router(puntos_router)
app.include_router(solicitudes_router)
app.include_router(vf_router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


# --- config_incentivos (configurable en caliente; nada hardcodeado) ---
@app.get("/config/incentivos")
def get_config() -> dict:
    return dict(stores.config)


@app.put("/config/incentivos/{clave}")
def put_config(clave: str, req: ConfigRequest) -> dict:
    stores.config[clave] = req.valor
    return {"clave": clave, "valor": req.valor}


# --- consentimientos SEPARADOS (puntos vs contacto) ---
@app.post("/consentimientos")
def post_consentimiento(req: ConsentimientoRequest) -> dict:
    c = consent_store.registrar(req.sujeto_id, req.tipo, req.otorgado)
    return {"sujeto_id": c.sujeto_id, "tipo": c.tipo.value,
            "otorgado": c.otorgado, "fecha": c.fecha.isoformat()}
