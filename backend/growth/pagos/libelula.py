"""Cliente mínimo de Libélula (pasarela de pagos de BOLIVIA).

Modelo "deuda": el backend REGISTRA una deuda con el `appkey` y Libélula
devuelve una `url_pasarela_pagos` a la que se redirige al cliente para pagar
(QR interoperable · tarjeta · Tigo Money). Al confirmarse el pago, Libélula
hace un GET al `callback_url` con `?transaction_id=...`. Para reconciliar, se
puede consultar la deuda por identificador (`pagado` bool).

Sin `LIBELULA_APPKEY` el módulo queda inactivo (`disponible()` False) y el
flujo cae a lo que corresponda (fail-safe). El appkey nunca va en el APK.

Ref: Guía de Integración Libélula v2.145 (REGISTRAR DEUDA / PAGO EXITOSO /
CONSULTAR DEUDAS POR IDENTIFICADOR).
"""

from __future__ import annotations

import json
import urllib.request

import config


def disponible() -> bool:
    return bool(config.LIBELULA_APPKEY)


def _post(path: str, payload: dict) -> dict:
    """POST JSON al REST de Libélula. Lanza en error de red/HTTP."""
    url = f"{config.LIBELULA_BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _error(r: dict) -> bool:
    """Libélula marca error con `error` = true/1 (0/false = OK)."""
    e = r.get("error")
    if isinstance(e, bool):
        return e
    if isinstance(e, (int, float)):
        return e != 0
    if isinstance(e, str):
        return e.strip().lower() in ("true", "1", "error")
    return False


def registrar_deuda(
    *,
    identificador: str,
    email: str,
    monto_bs: float,
    concepto: str,
    callback_url: str,
    url_retorno: str,
    nombre: str = "",
    apellido: str = "",
) -> dict:
    """Registra la deuda y devuelve {ok, url_pasarela, id_transaccion, qr_url} o
    {ok: False, error}. Nunca lanza."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    monto = round(float(monto_bs), 2)
    if monto <= 0:
        return {"ok": False, "error": "monto_invalido"}
    payload = {
        "appkey": config.LIBELULA_APPKEY,
        "email_cliente": email,
        # El example de la guía usa "identificador"; lo mandamos y también su
        # alias por si la instancia exige el nombre largo.
        "identificador": identificador,
        "identificador_deuda": identificador,
        "callback_url": callback_url,
        "url_retorno": url_retorno,
        "descripcion": (concepto or "Pago Pichangol")[:150],
        "nombre_cliente": (nombre or "Cliente")[:60],
        "apellido_cliente": (apellido or "Pichangol")[:60],
        "moneda": "BOB",
        "lineas_detalle_deuda": [
            {
                "concepto": (concepto or "Pago Pichangol")[:120],
                "cantidad": 1,
                "costo_unitario": monto,
            }
        ],
    }
    try:
        r = _post("/rest/deuda/registrar", payload)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}
    if _error(r):
        return {"ok": False, "error": (r.get("mensaje") or "no_registrado")[:160]}
    url = r.get("url_pasarela_pagos")
    if not url:
        return {"ok": False, "error": "sin_url_pasarela"}
    return {
        "ok": True,
        "url_pasarela": url,
        "id_transaccion": r.get("id_transaccion"),
        "qr_url": r.get("qr_simple_url"),
    }


def consultar_por_identificador(identificador: str) -> dict:
    """Consulta la deuda por su identificador (el que registramos). Devuelve
    {ok, pagado, valor_total, fecha_pago, forma_pago} o {ok: False, error}."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    payload = {"appkey": config.LIBELULA_APPKEY, "identificador": identificador}
    try:
        r = _post("/rest/deuda/consultar_deudas/por_identificador", payload)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}
    if _error(r):
        return {"ok": False, "error": (r.get("mensaje") or "no_encontrado")[:160]}
    datos = r.get("datos")
    d: dict = {}
    if isinstance(datos, list) and datos:
        d = datos[0] if isinstance(datos[0], dict) else {}
    elif isinstance(datos, dict):
        d = datos
    return {
        "ok": True,
        "pagado": bool(d.get("pagado")),
        "valor_total": d.get("valor_total"),
        "fecha_pago": d.get("fecha_pago"),
        "forma_pago": d.get("forma_pago"),
    }
