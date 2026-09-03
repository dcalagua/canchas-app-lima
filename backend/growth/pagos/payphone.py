"""Cliente mínimo de PayPhone (pasarela de pagos de ECUADOR).

Modelo "Botón de pagos por redirección":
  1. PREPARE — el backend prepara la transacción (token de Developer + storeId)
     y PayPhone devuelve URLs hospedadas: `payWithCard` (tarjeta Visa /
     Mastercard / Diners / Discover) y `payWithPayPhone` (saldo de la app).
  2. El cliente paga en esa página (WebView del APK).
  3. PayPhone lo devuelve al `responseUrl` con `?id=<transactionId>&
     clientTransactionId=<nuestro identificador>`.
  4. CONFIRM — hay que confirmar con PayPhone DENTRO DE 5 MINUTOS; si no, el
     cobro se REVIERTE solo (protección para cliente y comercio). Confirm es
     además la ÚNICA fuente de verdad del estado: un GET al responseUrl no
     confirma nada por sí mismo.

Montos en CENTAVOS de dólar (enteros). La regla de PayPhone es
`amount = amountWithoutTax + amountWithTax + tax + service + tip`; Pichangol
manda el total como `amountWithoutTax` (el desglose fiscal lo lleva el
comprobante propio, no la pasarela).

Sin `PAYPHONE_TOKEN` + `PAYPHONE_STORE_ID` el módulo queda inactivo
(`disponible()` False) y el flujo cae a lo que corresponda (fail-safe). El
token nunca va en el APK.

Ref: docs.payphone.app → "Botón de pago por redirección" (Prepare / Confirm).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import config

PREPARE_PATH = "/api/button/Prepare"
CONFIRM_PATH = "/api/button/V2/Confirm"

# Estados que PayPhone reporta en Confirm (`transactionStatus`). Sólo Approved
# es plata cobrada; todo lo demás se trata como NO pagado.
ESTADO_APROBADO = "approved"


def disponible() -> bool:
    return bool(config.PAYPHONE_TOKEN and config.PAYPHONE_STORE_ID)


def _post(path: str, payload: dict) -> dict:
    """POST JSON al API de PayPhone con el Bearer token. Lanza en error de
    red/HTTP (los llamadores lo convierten en {ok: False})."""
    url = f"{config.PAYPHONE_BASE_URL.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {config.PAYPHONE_TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            cuerpo = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:  # PayPhone responde JSON aun en 4xx
        cuerpo = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(cuerpo)
        except ValueError:
            j = {}
        j.setdefault("_http", e.code)
        return j
    return json.loads(cuerpo) if cuerpo.strip() else {}


def _mensaje_error(r: dict, defecto: str) -> str:
    """PayPhone devuelve el motivo en `message` y, a veces, `errors[]`."""
    m = r.get("message") or r.get("Message")
    if not m and isinstance(r.get("errors"), list) and r["errors"]:
        e0 = r["errors"][0]
        m = e0.get("message") if isinstance(e0, dict) else str(e0)
    return str(m or defecto)[:160]


def centavos(monto_usd: float) -> int:
    return int(round(float(monto_usd) * 100))


def preparar(
    *,
    client_tx_id: str,
    monto_usd: float,
    concepto: str,
    response_url: str,
    cancel_url: str,
    email: str = "",
    telefono: str = "",
    documento: str = "",
) -> dict:
    """Prepara la transacción. Devuelve {ok, payment_id, url_tarjeta,
    url_payphone} o {ok: False, error}. Nunca lanza."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    cts = centavos(monto_usd)
    if cts <= 0:
        return {"ok": False, "error": "monto_invalido"}
    payload: dict = {
        "amount": cts,
        "amountWithoutTax": cts,
        "amountWithTax": 0,
        "tax": 0,
        "service": 0,
        "tip": 0,
        "currency": "USD",
        "clientTransactionId": client_tx_id,
        "reference": (concepto or "Pago Pichangol")[:100],
        "responseUrl": response_url,
        "cancellationUrl": cancel_url,
        "storeId": config.PAYPHONE_STORE_ID,
        "lang": "es",
    }
    # Opcionales: sólo si vienen (PayPhone valida formato cuando están).
    if email:
        payload["email"] = email[:120]
    if telefono:
        payload["phoneNumber"] = telefono[:20]
    if documento:
        payload["documentId"] = documento[:20]
    try:
        r = _post(PREPARE_PATH, payload)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}
    url_tarjeta = r.get("payWithCard")
    url_payphone = r.get("payWithPayPhone")
    if not url_tarjeta and not url_payphone:
        return {"ok": False, "error": _mensaje_error(r, "sin_url_pasarela")}
    return {
        "ok": True,
        "payment_id": r.get("paymentId"),
        "url_tarjeta": url_tarjeta,
        "url_payphone": url_payphone,
    }


def confirmar(*, transaction_id: str, client_tx_id: str) -> dict:
    """Confirma la transacción (obligatorio, y antes de 5 min). Devuelve
    {ok, aprobado, estado, transaction_id, autorizacion, monto_centavos,
    tarjeta, ultimos, mensaje} o {ok: False, error}. Nunca lanza."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    tx = str(transaction_id or "").strip()
    if not tx:
        return {"ok": False, "error": "transaction_id_requerido"}
    payload = {"id": int(tx) if tx.isdigit() else tx, "clientTxId": client_tx_id}
    try:
        r = _post(CONFIRM_PATH, payload)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}
    estado = str(r.get("transactionStatus") or "").strip()
    if not estado and r.get("_http"):
        return {"ok": False, "error": _mensaje_error(r, f"http_{r['_http']}")}
    aprobado = estado.lower() == ESTADO_APROBADO or r.get("statusCode") == 3
    return {
        "ok": True,
        "aprobado": bool(aprobado),
        "estado": estado or "Desconocido",
        "transaction_id": r.get("transactionId", tx),
        "autorizacion": r.get("authorizationCode"),
        "monto_centavos": r.get("amount"),
        "tarjeta": r.get("cardBrand"),
        "ultimos": r.get("lastDigits"),
        "mensaje": r.get("message"),
    }
