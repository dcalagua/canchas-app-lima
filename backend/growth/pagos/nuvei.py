"""Cliente mínimo de NUVEI Ecuador (plataforma ex-Paymentez) — LinkToPay.

Pasarela de pagos de ECUADOR (USD) desde oct-2026 (decisión del director:
reemplaza a PayPhone; PayPhone queda en el código como respaldo, se elige con
`PASARELA_EC`). Modelo "enlace de pago hospedado":

  1. INIT_ORDER — el backend crea la orden (`POST /linktopay/init_order/` en el
     host NO-PCI) con el `dev_reference` = nuestro identificador y Nuvei
     devuelve `payment_url`, la página hospedada donde el cliente paga
     (tarjeta y los medios que tenga habilitados el comercio).
  2. El cliente paga en esa página (navegador real del celular / la web).
  3. Nuvei avisa el resultado por WEBHOOK (POST a la URL de callback que se
     registra en la aplicación de Nuvei) con `transaction.status`,
     `dev_reference`, `id` y `stoken` = md5(`{id}_{application_code}_
     {user_id}_{app_key}`). Ese webhook es la fuente de verdad: un GET al
     `success_url` no aprueba nada. De respaldo se puede VERIFICAR la
     transacción por su id (`GET /v2/transaction/{id}/`).
  4. Devolución: `POST /v2/transaction/refund/` (total o parcial).

Autenticación del API de servidor: cabecera `Auth-Token` =
base64("{application_code};{unix_ts};{sha256(app_key + unix_ts)}").

Montos en DÓLARES con 2 decimales (Nuvei recibe float); internamente
manejamos centavos enteros y comparamos en centavos.

Sin `NUVEI_APP_CODE` + `NUVEI_APP_KEY` el módulo queda inactivo
(`disponible()` False). Las credenciales del SERVIDOR nunca van al APK.

OJO: los nombres de campos y rutas siguen la documentación de Paymentez/
Nuvei LinkToPay; la documentación oficial no se pudo abrir desde el entorno de
desarrollo (proxy), por eso los hosts son configurables (`NUVEI_BASE_URL`,
`NUVEI_LINKTOPAY_URL`) y cada respuesta inesperada queda en los logs
`[nuvei] …`. La primera orden en STAGING es la validación.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("nuvei")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False

# Estados de `transaction.status` en el webhook / verificación.
ESTADO_APROBADO = "1"
ESTADO_CANCELADO = "2"
ESTADO_RECHAZADO = "4"
_TEXTO_ESTADO = {"0": "pendiente", "1": "aprobado", "2": "cancelado",
                 "4": "rechazado"}


def _env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d).strip()


def _staging() -> bool:
    return _env("NUVEI_ENTORNO", "stg").lower() not in ("prod", "produccion", "live")


def app_code() -> str:
    return _env("NUVEI_APP_CODE")


def _app_key() -> str:
    return _env("NUVEI_APP_KEY")


def disponible() -> bool:
    return bool(app_code() and _app_key())


def base_url() -> str:
    """Host PCI del API (transacciones, verificación, devoluciones)."""
    return _env("NUVEI_BASE_URL") or (
        "https://ccapi-stg.paymentez.com" if _staging() else "https://ccapi.paymentez.com")


def linktopay_url() -> str:
    """Host NO-PCI donde vive LinkToPay."""
    return _env("NUVEI_LINKTOPAY_URL") or (
        "https://noccapi-stg.paymentez.com" if _staging() else "https://noccapi.paymentez.com")


def centavos(monto_usd: float) -> int:
    return int(round(float(monto_usd) * 100))


def auth_token(ahora: int | None = None) -> str:
    ts = str(int(ahora if ahora is not None else time.time()))
    uniq = hashlib.sha256((_app_key() + ts).encode("utf-8")).hexdigest()
    return base64.b64encode(f"{app_code()};{ts};{uniq}".encode("utf-8")).decode("ascii")


def _http(metodo: str, url: str, payload: dict | None = None) -> dict:
    """Llama al API. Devuelve el JSON (con `_http` = código si fue 4xx/5xx).
    Lanza en error de red (los llamadores lo convierten en {ok: False})."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=metodo, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "Auth-Token": auth_token(),
        "User-Agent": "Pichangol-Backend/1.0 (+https://www.pichangol.app)"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            cuerpo = resp.read().decode("utf-8")
            j = json.loads(cuerpo) if cuerpo.strip() else {}
            return j if isinstance(j, dict) else {"data": j}
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(cuerpo)
        except ValueError:
            j = {"detail": cuerpo[:200]}
        if not isinstance(j, dict):
            j = {"data": j}
        j["_http"] = e.code
        return j


def _error(r: dict, defecto: str) -> str:
    e = r.get("error")
    if isinstance(e, dict):
        m = e.get("description") or e.get("type") or e.get("help")
    else:
        m = e or r.get("detail") or r.get("message")
    return str(m or defecto)[:160]


def _partir_nombre(nombre: str) -> tuple[str, str]:
    p = (nombre or "").split()
    if not p:
        return "Cliente", "Pichangol"
    if len(p) == 1:
        return p[0], p[0]
    if len(p) == 2:
        return p[0], p[1]
    return " ".join(p[:-2]), " ".join(p[-2:])


def preparar(*, ident: str, monto_usd: float, concepto: str, email: str,
             success_url: str, failure_url: str, pending_url: str = "",
             nombre: str = "", telefono: str = "", documento: str = "",
             expira_min: int = 30) -> dict:
    """Crea la orden LinkToPay. Devuelve {ok, url, order_id} o {ok: False,
    error}. `ident` viaja como `dev_reference` (así vuelve en el webhook)."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    monto = round(float(monto_usd), 2)
    if monto <= 0:
        return {"ok": False, "error": "monto_invalido"}
    nom, ape = _partir_nombre(nombre or (email or "").split("@")[0])
    usuario = {"id": (email or ident).strip().lower()[:100],
               "email": (email or "").strip().lower(),
               "name": nom[:50], "last_name": ape[:50]}
    tel = "".join(c for c in (telefono or "") if c.isdigit())
    if tel:
        usuario["phone_number"] = tel[:15]
    doc = "".join(c for c in (documento or "") if c.isalnum())
    if doc:
        usuario["fiscal_number"] = doc[:20]
    cuerpo = {
        "user": usuario,
        "order": {
            "dev_reference": ident,
            "description": (concepto or "Pago Pichangol")[:240],
            "amount": monto,
            "installments_type": 0,
            "currency": "USD",
            # Pichangol manda el total sin desglose de IVA (el comprobante
            # fiscal es propio, no de la pasarela), igual que con PayPhone.
            "vat": 0,
            "taxable_amount": 0,
            "tax_percentage": 0,
        },
        "configuration": {
            "partial_payment": False,
            "expiration_time": max(300, int(expira_min) * 60),
            "allowed_payment_methods": ["All"],
            "success_url": success_url,
            "failure_url": failure_url,
            "pending_url": pending_url or success_url,
            "review_url": pending_url or success_url,
        },
    }
    try:
        r = _http("POST", f"{linktopay_url().rstrip('/')}/linktopay/init_order/", cuerpo)
    except Exception as e:  # noqa: BLE001 — red caída
        log.warning("[nuvei] init_order sin respuesta: %s", e)
        return {"ok": False, "error": "nuvei_sin_respuesta"}
    data = r.get("data") if isinstance(r.get("data"), dict) else {}
    pago = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    url = pago.get("payment_url") or ""
    if not url or r.get("_http"):
        log.warning("[nuvei] init_order rechazada ident=%s http=%s resp=%s",
                    ident, r.get("_http"), json.dumps(r)[:400])
        return {"ok": False, "error": _error(r, "nuvei_rechazo")}
    orden = data.get("order") if isinstance(data.get("order"), dict) else {}
    log.info("[nuvei] orden %s ident=%s $%.2f", orden.get("id"), ident, monto)
    return {"ok": True, "url": url, "order_id": str(orden.get("id") or "")}


def stoken_esperado(transaction_id: str, user_id: str) -> str:
    base = f"{transaction_id}_{app_code()}_{user_id}_{_app_key()}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _resultado(tx: dict) -> dict:
    estado = str(tx.get("status") if tx.get("status") is not None else "").strip()
    try:
        monto_c = centavos(float(tx.get("amount")))
    except (TypeError, ValueError):
        monto_c = None
    return {
        "ok": True,
        "ident": str(tx.get("dev_reference") or ""),
        "transaction_id": str(tx.get("id") or ""),
        "aprobado": estado == ESTADO_APROBADO,
        "estado": _TEXTO_ESTADO.get(estado, f"estado_{estado}" if estado else "desconocido"),
        "detalle": str(tx.get("status_detail") or ""),
        "monto_centavos": monto_c,
        "autorizacion": tx.get("authorization_code"),
    }


def leer_webhook(payload: dict) -> dict:
    """Valida el `stoken` del webhook y normaliza. {ok: False, error} si no
    viene de Nuvei (firma mala o faltan datos)."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    tx = payload.get("transaction") if isinstance(payload, dict) else None
    if not isinstance(tx, dict):
        return {"ok": False, "error": "sin_transaccion"}
    usuario = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    tid = str(tx.get("id") or "")
    uid = str(usuario.get("id") or "")
    firma = str(tx.get("stoken") or "")
    if not tid or not firma or not hmac.compare_digest(
            firma.lower(), stoken_esperado(tid, uid)):
        return {"ok": False, "error": "firma_invalida"}
    if str(tx.get("application_code") or app_code()) != app_code():
        return {"ok": False, "error": "otra_aplicacion"}
    return _resultado(tx)


def verificar(transaction_id: str) -> dict:
    """Consulta la transacción en Nuvei (respaldo del webhook)."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    tid = (transaction_id or "").strip()
    if not tid:
        return {"ok": False, "error": "sin_transaccion"}
    try:
        r = _http("GET", f"{base_url().rstrip('/')}/v2/transaction/{tid}/")
    except Exception as e:  # noqa: BLE001
        log.warning("[nuvei] verificar %s sin respuesta: %s", tid, e)
        return {"ok": False, "error": "nuvei_sin_respuesta"}
    tx = r.get("transaction") if isinstance(r.get("transaction"), dict) else None
    if r.get("_http") or not tx:
        log.warning("[nuvei] verificar %s http=%s resp=%s", tid, r.get("_http"),
                    json.dumps(r)[:300])
        return {"ok": False, "error": _error(r, "nuvei_rechazo")}
    return _resultado(tx)


def reembolsar(*, transaction_id: str, monto_centavos: int | None = None) -> dict:
    """Devuelve una transacción (total o parcial). {ok, estado} o {ok: False}."""
    if not disponible():
        return {"ok": False, "error": "no_configurado"}
    tid = (transaction_id or "").strip()
    if not tid:
        return {"ok": False, "error": "reembolso_invalido"}
    cuerpo: dict = {"transaction": {"id": tid}}
    if monto_centavos:
        cuerpo["order"] = {"amount": round(int(monto_centavos) / 100.0, 2)}
    try:
        r = _http("POST", f"{base_url().rstrip('/')}/v2/transaction/refund/", cuerpo)
    except Exception as e:  # noqa: BLE001
        log.warning("[nuvei] refund %s sin respuesta: %s", tid, e)
        return {"ok": False, "error": "nuvei_sin_respuesta"}
    estado = str(r.get("status") or "").lower()
    if r.get("_http") or estado not in ("success", "pending"):
        log.warning("[nuvei] refund %s http=%s resp=%s", tid, r.get("_http"),
                    json.dumps(r)[:300])
        return {"ok": False, "error": _error(r, "reembolso_rechazado")}
    log.info("[nuvei] refund %s %s", tid, estado)
    return {"ok": True, "estado": estado, "raw": r}
