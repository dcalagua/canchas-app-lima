"""VENTAS del Marketplace (escrow simple): el comprador ya pagó (Culqi) y el
neto queda RETENIDO hasta que confirme la recepción. Estados:
pagado → entregado (vendedor) → recibido (comprador = LIBERADO) | disputado.
Si el comprador no confirma ni disputa en `ventas_liberacion_dias`, se libera
solo (auto-liberación a favor del vendedor). Público (app), protegido X-App-Key.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import config
from db.store import ahora, stores
from pagos.router import comision_centimos

router = APIRouter(prefix="/ventas", tags=["ventas"])


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


def _liberacion_dias() -> int:
    n = stores.cfg_int("ventas_liberacion_dias")
    return n if n > 0 else 7


def _auto_liberar() -> None:
    """Libera (a favor del vendedor) las ventas cuyo plazo venció sin que el
    comprador confirme ni dispute. Lazy: se llama al listar."""
    dias = _liberacion_dias()
    limite = ahora() - timedelta(days=dias)
    for v in stores.ventas:
        if v.estado in ("pagado", "entregado") and v.creado_en <= limite:
            v.estado = "recibido"
            v.recibido_en = ahora()
            v.auto_liberado = True


def _neto_soles(monto_soles: float) -> float:
    return round(monto_soles - comision_centimos(monto_soles) / 100.0, 2)


def _dict(v) -> dict:
    return {
        "id": v.id,
        "producto_id": v.producto_id,
        "producto_nombre": v.producto_nombre,
        "comprador_email": v.comprador_email,
        "comprador_nombre": v.comprador_nombre,
        "vendedor_email": v.vendedor_email,
        "vendedor_nombre": v.vendedor_nombre,
        "monto_soles": v.monto_soles,
        "neto_soles": _neto_soles(v.monto_soles),
        "estado": v.estado,
        "creado_en": v.creado_en.isoformat(),
        "entregado_en": v.entregado_en.isoformat() if v.entregado_en else None,
        "recibido_en": v.recibido_en.isoformat() if v.recibido_en else None,
        "auto_liberado": v.auto_liberado,
        # Liberado = el vendedor ya puede cobrar ese neto.
        "liberado": v.estado == "recibido",
    }


@router.get("/comprador/{email}", dependencies=_APP)
def ventas_comprador(email: str) -> dict:
    """MIS COMPRAS: las órdenes donde soy el comprador, más recientes primero."""
    _auto_liberar()
    e = email.strip().lower()
    mias = [v for v in stores.ventas if v.comprador_email == e]
    mias.sort(key=lambda v: v.creado_en, reverse=True)
    return {"ventas": [_dict(v) for v in mias]}


@router.get("/vendedor/{email}", dependencies=_APP)
def ventas_vendedor(email: str) -> dict:
    """MIS VENTAS: las órdenes donde soy el vendedor, con el resumen de dinero
    retenido vs liberado (por cobrar)."""
    _auto_liberar()
    e = email.strip().lower()
    mias = [v for v in stores.ventas if v.vendedor_email == e]
    mias.sort(key=lambda v: v.creado_en, reverse=True)
    retenido = sum(_neto_soles(v.monto_soles) for v in mias
                   if v.estado in ("pagado", "entregado"))
    liberado = sum(_neto_soles(v.monto_soles) for v in mias
                   if v.estado == "recibido")
    return {"ventas": [_dict(v) for v in mias],
            "retenido_soles": round(retenido, 2),
            "liberado_soles": round(liberado, 2)}


def _buscar(venta_id: int):
    return next((v for v in stores.ventas if v.id == venta_id), None)


class PorEmailReq(BaseModel):
    por_email: str = ""


@router.post("/{venta_id}/entregado", dependencies=_APP)
def marcar_entregado(venta_id: int, req: PorEmailReq) -> dict:
    """El VENDEDOR marca que entregó el producto (sigue retenido hasta que el
    comprador confirme)."""
    v = _buscar(venta_id)
    if v is None:
        raise HTTPException(status_code=404, detail="venta_no_encontrada")
    quien = req.por_email.strip().lower()
    if quien and quien != v.vendedor_email:
        return {"ok": False, "error": "no_eres_el_vendedor"}
    if v.estado == "pagado":
        v.estado = "entregado"
        v.entregado_en = ahora()
    return {"ok": True, "venta": _dict(v)}


@router.post("/{venta_id}/recibido", dependencies=_APP)
def marcar_recibido(venta_id: int, req: PorEmailReq) -> dict:
    """El COMPRADOR confirma la recepción → LIBERA el pago al vendedor."""
    v = _buscar(venta_id)
    if v is None:
        raise HTTPException(status_code=404, detail="venta_no_encontrada")
    quien = req.por_email.strip().lower()
    if quien and quien != v.comprador_email:
        return {"ok": False, "error": "no_eres_el_comprador"}
    if v.estado in ("pagado", "entregado"):
        v.estado = "recibido"
        v.recibido_en = ahora()
        v.auto_liberado = False
    return {"ok": True, "venta": _dict(v)}


@router.post("/{venta_id}/disputa", dependencies=_APP)
def abrir_disputa(venta_id: int, req: PorEmailReq) -> dict:
    """El COMPRADOR abre una disputa (no se libera; lo revisa el operador)."""
    v = _buscar(venta_id)
    if v is None:
        raise HTTPException(status_code=404, detail="venta_no_encontrada")
    quien = req.por_email.strip().lower()
    if quien and quien != v.comprador_email:
        return {"ok": False, "error": "no_eres_el_comprador"}
    if v.estado != "recibido":  # una vez liberado ya no se disputa aquí
        v.estado = "disputado"
    return {"ok": True, "venta": _dict(v)}
