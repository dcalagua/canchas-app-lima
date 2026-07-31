"""API de crecimiento de Pichangol: PUNTOS/PREMIOS + SOLICITUDES POR ZONA +
VERIFICACION FISICA. Tres subsistemas conectados.

Ejecutar (desde este directorio):
    uvicorn main:app --reload
"""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, Request

from compliance.consent import consent_store
from concierge.router import router as concierge_router
from convocatorias.router import router as convocatorias_router
from db import pg
from db.store import seed_verificadores, stores
from legal.router import router as legal_router
from models import ConfigRequest, ConsentimientoRequest
from marketing.router import router as marketing_router
from pagos.router import (procesar_renovaciones, procesar_renovaciones_alumnos,
                          procesar_renovaciones_pro)
from pagos.router import router as pagos_router
from retos.router import router as retos_router
from ventas.router import router as ventas_router
from circuito.router import router as circuito_router
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

# Persistencia: carga el snapshot y, encima, las tablas normalizadas (saldos/
# pagos/vistas/reclamos) que ganan si tienen datos. En el primer deploy las
# tablas están vacías → se conserva el snapshot y se hace *backfill* a las tablas.
_snapshot = pg.init_y_cargar()
if _snapshot:
    stores.load_state(_snapshot)
pg.cargar_normalizado(stores)   # tablas reales = fuente de verdad de lo crítico
if pg.habilitado:               # backfill inicial (snapshot -> tablas) idempotente
    try:
        pg.guardar_normalizado(stores)
    except Exception:  # noqa: BLE001
        pass
if not stores.verificadores:
    seed_verificadores()

# Unificación de servicios: migra suscripciones del plan retirado "gestion" a
# "redes", y cancela solapamientos (Presencia ya incluye Landing/Manejo).
_cambios = stores.migrar_suscripciones_legacy()
_cambios += stores.resolver_solapamiento_servicios()
if _cambios and pg.habilitado:
    try:
        pg.guardar(stores.to_state())
    except Exception:  # noqa: BLE001
        pass


@app.middleware("http")
async def _persistir(request: Request, call_next):
    """Tras cada request que muta estado, guarda el snapshot completo (respaldo)
    y vuelca lo crítico a sus tablas normalizadas. Todo fail-safe."""
    response = await call_next(request)
    if pg.habilitado and request.method in ("POST", "PUT", "DELETE"):
        try:
            pg.guardar(stores.to_state())
        except Exception:  # noqa: BLE001
            pass
        try:
            pg.guardar_normalizado(stores)
        except Exception:  # noqa: BLE001
            pass
    return response

app.include_router(puntos_router)
app.include_router(solicitudes_router)
app.include_router(vf_router)
app.include_router(propiedad_router)
app.include_router(panel_router)
app.include_router(convocatorias_router)
app.include_router(pagos_router)
app.include_router(retos_router)
app.include_router(ventas_router)
app.include_router(circuito_router)
app.include_router(marketing_router)
app.include_router(legal_router)
app.include_router(concierge_router)


@app.on_event("startup")
async def _iniciar_cron_renovaciones() -> None:
    """Cron INTERNO: cada 12 h renueva las suscripciones vencidas (cobra del saldo
    o de la tarjeta de débito automático). Corre dentro del mismo proceso (una
    sola réplica en Railway), fail-safe, y persiste si cambió algo."""
    async def _loop() -> None:
        await asyncio.sleep(60)  # deja arrancar el servicio
        while True:
            try:
                r = procesar_renovaciones()
                ra = procesar_renovaciones_alumnos()  # mensualidades mes a mes
                rp = procesar_renovaciones_pro()  # membresías Pichangol Pro
                cambio = (r.get("cobradas") or r.get("por_tarjeta")
                          or r.get("pendientes")
                          or ra.get("cobradas") or ra.get("pendientes")
                          or rp.get("renovadas"))
                if cambio and pg.habilitado:
                    pg.guardar(stores.to_state())
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(12 * 3600)  # cada 12 horas

    asyncio.create_task(_loop())


@app.on_event("startup")
async def _iniciar_cron_cm() -> None:
    """Community manager AUTÓNOMO (Fase 0): cada 30 min pre-genera el "post del
    día" de cada academia suscrita que toca por cadencia, para que el dueño lo
    encuentre listo. Una sola réplica en Railway; fail-safe; persiste si generó."""
    async def _loop() -> None:
        await asyncio.sleep(90)  # deja arrancar el servicio
        while True:
            try:
                from marketing.cm import procesar_cm_pendientes
                n = procesar_cm_pendientes()
                if n and pg.habilitado:
                    pg.guardar(stores.to_state())
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(30 * 60)  # cada 30 minutos

    asyncio.create_task(_loop())


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
