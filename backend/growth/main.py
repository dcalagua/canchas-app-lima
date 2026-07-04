"""API de crecimiento de Pichangol: PUNTOS/PREMIOS + SOLICITUDES POR ZONA +
VERIFICACION FISICA. Tres subsistemas conectados.

Ejecutar (desde este directorio):
    uvicorn main:app --reload
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request

from compliance.consent import consent_store
from db import pg
from db.store import seed_verificadores, stores
from models import ConfigRequest, ConsentimientoRequest
from propiedad.panel import router as panel_router
from propiedad.router import _require_admin
from propiedad.router import router as propiedad_router
from puntos.router import router as puntos_router
from solicitudes.router import router as solicitudes_router
from verificacion_fisica.router import router as vf_router

app = FastAPI(
    title="Pichangol — Crecimiento (puntos, zonas, verificación física)",
    description="No-retención de datos personales (Ley 29733). Integraciones en STUB.",
    version="0.1.0",
)

# Persistencia: carga el snapshot guardado (si hay BD) y siembra verificadores.
_snapshot = pg.init_y_cargar()
if _snapshot:
    stores.load_state(_snapshot)
if not stores.verificadores:
    seed_verificadores()


@app.middleware("http")
async def _persistir(request: Request, call_next):
    """Tras cada request que muta estado, guarda el snapshot (fail-safe)."""
    response = await call_next(request)
    if pg.habilitado and request.method in ("POST", "PUT", "DELETE"):
        try:
            pg.guardar(stores.to_state())
        except Exception:  # noqa: BLE001
            pass
    return response

app.include_router(puntos_router)
app.include_router(solicitudes_router)
app.include_router(vf_router)
app.include_router(propiedad_router)
app.include_router(panel_router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


# --- config_incentivos (configurable en caliente; nada hardcodeado) ---
@app.get("/config/incentivos")
def get_config() -> dict:
    return dict(stores.config)


@app.put("/config/incentivos/{clave}", dependencies=[Depends(_require_admin)])
def put_config(clave: str, req: ConfigRequest) -> dict:
    """ADMIN: reescribe una clave de config (modo_aprobacion, exigir_ubicacion,
    topes de puntos, etc.). Protegido por token: mutar esto sin auth permitía a
    cualquiera cambiar reglas del sistema."""
    stores.config[clave] = req.valor
    return {"clave": clave, "valor": req.valor}


# --- consentimientos SEPARADOS (puntos vs contacto) ---
@app.post("/consentimientos")
def post_consentimiento(req: ConsentimientoRequest) -> dict:
    c = consent_store.registrar(req.sujeto_id, req.tipo, req.otorgado)
    return {"sujeto_id": c.sujeto_id, "tipo": c.tipo.value,
            "otorgado": c.otorgado, "fecha": c.fecha.isoformat()}
