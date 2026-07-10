"""Endpoints de PAGOS (Culqi) — modelo inDrive.

- POST /pagos/recarga     → el dueño recarga su saldo prepago (Yape/tarjeta).
- POST /pagos/fee-reserva → el jugador paga la comisión de Pichangol (fallback
                            saldo cero). Es ingreso de Pichangol, no acredita
                            saldo de nadie.
- GET  /pagos/saldo/{id}  → saldo del dueño (céntimos y soles).
- POST /pagos/webhook     → confirmación de Culqi (idempotente; re-consulta el
                            cargo con la sk como fuente de verdad).
- GET  /pagos/config      → llave pública + modo (test/live) para el APK.

La llave secreta vive sólo en el backend. Los POST del APK exigen X-App-Key
(igual que propiedad), salvo el webhook (lo llama Culqi, no el APK).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

import config
from db.store import stores

from . import culqi

router = APIRouter(prefix="/pagos", tags=["pagos"])


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    """Sólo el APK oficial (X-App-Key) puede iniciar cobros. Si APP_API_KEY no
    está configurada, no se exige (despliegue gradual)."""
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


def _soles_a_centimos(soles: float) -> int:
    return int(round(float(soles) * 100))


def comision_centimos(monto_soles: float) -> int:
    """Comisión de Pichangol por una reserva: COMISION_PORC % con mínimo
    COMISION_MIN_SOLES. Devuelve céntimos."""
    bruto = float(monto_soles) * config.COMISION_PORC / 100.0
    con_min = max(bruto, config.COMISION_MIN_SOLES)
    return int(round(con_min * 100))


class RecargaReq(BaseModel):
    token: str                 # source_id de Culqi (tkn_...) generado en el APK
    dueno_id: str              # a quién se le acredita el saldo (correo del dueño)
    email: str                 # correo del pagador (lo exige Culqi)
    monto_soles: float


class FeeReq(BaseModel):
    token: str
    email: str
    monto_soles: float         # la comisión a cobrar (la calcula el APK o aquí)
    concepto: str = "Fee de reserva Pichangol"
    reserva_id: str | None = None


@router.get("/config")
def get_config() -> dict:
    """Datos públicos para el APK (nunca la llave secreta)."""
    return {
        "disponible": culqi.disponible(),
        "modo": culqi.modo(),                 # test | live | off
        "public_key": config.CULQI_PUBLIC_KEY,
        "comision_porc": config.COMISION_PORC,
        "comision_min_soles": config.COMISION_MIN_SOLES,
    }


@router.get("/saldo/{dueno_id}", dependencies=_APP)
def get_saldo(dueno_id: str) -> dict:
    c = stores.saldo_centimos(dueno_id)
    return {"dueno_id": dueno_id, "saldo_centimos": c, "saldo_soles": c / 100.0}


@router.post("/recarga", dependencies=_APP)
def post_recarga(req: RecargaReq) -> dict:
    """Cobra la recarga por Culqi y, si se aprueba, acredita el saldo del dueño."""
    if not culqi.disponible():
        raise HTTPException(status_code=503, detail="pagos_no_configurados")
    centimos = _soles_a_centimos(req.monto_soles)
    if centimos < 100:
        raise HTTPException(status_code=400, detail="monto_minimo_1_sol")

    r = culqi.crear_cargo(
        token=req.token,
        monto_centimos=centimos,
        email=req.email,
        descripcion=f"Recarga saldo Pichangol · {req.dueno_id}",
        metadata={"tipo": "recarga", "dueno_id": req.dueno_id},
    )
    if not r["ok"]:
        stores.registrar_pago(
            tipo="recarga", monto_centimos=centimos, moneda="PEN",
            estado="rechazado", dueno_id=req.dueno_id, email=req.email,
            concepto="Recarga (rechazada)")
        return {"ok": False, "error": r.get("error", "cargo_rechazado")}

    charge_id = r["charge_id"]
    # Idempotencia: si el webhook ya acreditó este cargo, no dupliques.
    if stores.pago_por_charge(charge_id) is None:
        stores.acreditar(req.dueno_id, centimos)
        stores.registrar_pago(
            tipo="recarga", monto_centimos=centimos, moneda="PEN",
            estado="aprobado", dueno_id=req.dueno_id, email=req.email,
            culqi_charge_id=charge_id, concepto="Recarga de saldo")
    saldo = stores.saldo_centimos(req.dueno_id)
    return {
        "ok": True,
        "charge_id": charge_id,
        "saldo_centimos": saldo,
        "saldo_soles": saldo / 100.0,
    }


@router.post("/fee-reserva", dependencies=_APP)
def post_fee(req: FeeReq) -> dict:
    """Cobra al jugador SÓLO la comisión de Pichangol (fallback saldo cero). No
    acredita saldo: es ingreso de Pichangol a su propia cuenta."""
    if not culqi.disponible():
        raise HTTPException(status_code=503, detail="pagos_no_configurados")
    centimos = _soles_a_centimos(req.monto_soles)
    if centimos < 100:
        raise HTTPException(status_code=400, detail="monto_minimo_1_sol")

    r = culqi.crear_cargo(
        token=req.token,
        monto_centimos=centimos,
        email=req.email,
        descripcion=req.concepto,
        metadata={"tipo": "fee_reserva", "reserva_id": req.reserva_id or ""},
    )
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "cargo_rechazado")}

    charge_id = r["charge_id"]
    if stores.pago_por_charge(charge_id) is None:
        stores.registrar_pago(
            tipo="fee_reserva", monto_centimos=centimos, moneda="PEN",
            estado="aprobado", email=req.email, culqi_charge_id=charge_id,
            concepto=req.concepto)
    return {"ok": True, "charge_id": charge_id}


@router.post("/webhook")
async def post_webhook(request: Request, t: str | None = None) -> dict:
    """Confirmación de Culqi. Filtro ligero por token (?t=) y, sobre todo,
    re-consulta el cargo con la sk para no confiar en el payload. Idempotente:
    acredita la recarga una sola vez."""
    if config.CULQI_WEBHOOK_TOKEN and t != config.CULQI_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="webhook_token_invalido")
    try:
        evento = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "payload_invalido"}

    # El id del cargo puede venir en data.id o en el objeto raíz.
    data = evento.get("data") if isinstance(evento, dict) else None
    charge_id = None
    if isinstance(data, dict):
        charge_id = data.get("id")
    if not charge_id and isinstance(evento, dict):
        charge_id = evento.get("id")
    if not charge_id:
        return {"ok": False, "error": "sin_charge_id"}

    if stores.pago_por_charge(charge_id) is not None:
        return {"ok": True, "duplicado": True}  # ya procesado

    info = culqi.obtener_cargo(charge_id)
    if not info["ok"] or not info["capturado"]:
        return {"ok": False, "error": info.get("error", "cargo_no_capturado")}

    meta = info.get("metadata") or {}
    if meta.get("tipo") == "recarga" and meta.get("dueno_id"):
        stores.acreditar(meta["dueno_id"], info["monto_centimos"])
        stores.registrar_pago(
            tipo="recarga", monto_centimos=info["monto_centimos"], moneda="PEN",
            estado="aprobado", dueno_id=meta["dueno_id"],
            culqi_charge_id=charge_id, concepto="Recarga (webhook)")
    else:
        # fee u otro: sólo lo registramos (idempotencia/auditoría).
        stores.registrar_pago(
            tipo=meta.get("tipo", "fee_reserva"),
            monto_centimos=info["monto_centimos"], moneda="PEN",
            estado="aprobado", culqi_charge_id=charge_id,
            concepto="Confirmado por webhook")
    return {"ok": True}
