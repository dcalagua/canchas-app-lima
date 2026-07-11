"""Cliente mínimo de Culqi (pasarela de pagos). Crea y consulta cargos con la
llave SECRETA que vive sólo en el backend (Railway), nunca en el APK.

El APK tokeniza la tarjeta/Yape en el celular con la llave PÚBLICA y manda sólo
el `token` (source_id, ej. `tkn_...`) al backend; aquí se hace el cargo real.

Sin `CULQI_SECRET_KEY` el módulo queda inactivo (`disponible()` False) y el
router responde 503. Usa `urllib` (sin dependencias extra), como el resto del
backend. Nunca lanza: devuelve dicts {ok: bool, ...}.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import config


def disponible() -> bool:
    return bool(config.CULQI_SECRET_KEY)


def modo() -> str:
    """'live' | 'test' | 'off' según el prefijo de la llave secreta."""
    k = config.CULQI_SECRET_KEY
    if not k:
        return "off"
    return "live" if k.startswith("sk_live") else "test"


def _request(metodo: str, path: str, body: dict | None = None) -> dict:
    """Llama a la API de Culqi. Devuelve {ok, data} o {ok: False, error, ...}."""
    url = f"{config.CULQI_API_BASE}{path}"
    datos = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=datos,
        headers={
            "Authorization": f"Bearer {config.CULQI_SECRET_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=metodo,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "data": payload}
    except urllib.error.HTTPError as e:
        # Culqi devuelve un JSON de error con user_message / merchant_message.
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            err = {}
        return {
            "ok": False,
            "status": e.code,
            "error": err.get("user_message") or err.get("merchant_message")
            or f"culqi_http_{e.code}",
            "codigo": err.get("code") or err.get("type"),
            "merchant": err.get("merchant_message"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}


def crear_cargo(
    *,
    token: str,
    monto_centimos: int,
    email: str,
    descripcion: str,
    metadata: dict | None = None,
    moneda: str = "PEN",
) -> dict:
    """Crea un cargo en Culqi. Devuelve {ok, charge_id, capturado, raw} o
    {ok: False, error}. El `token` es el source_id que generó el APK (tarjeta o
    Yape) con la llave pública."""
    if not disponible():
        return {"ok": False, "error": "culqi_no_configurado"}
    if monto_centimos < 100:  # Culqi exige mínimo S/ 1.00 (100 céntimos)
        return {"ok": False, "error": "monto_minimo_1_sol"}
    # Descripción SOLO ASCII y de largo válido (Culqi exige 5–80 chars): evita
    # que caracteres especiales o textos cortos generen errores.
    desc = "".join(c for c in descripcion if 32 <= ord(c) < 127).strip()
    if len(desc) < 5:
        desc = "Pago Pichangol"
    desc = desc[:80]
    body = {
        "amount": int(monto_centimos),
        "currency_code": moneda,
        "email": email,
        "source_id": token,
        "description": desc,
    }
    if metadata:
        # Culqi acepta metadata con valores string.
        body["metadata"] = {k: str(v) for k, v in metadata.items()}
    r = _request("POST", "/charges", body)
    if not r["ok"]:
        return r
    data = r["data"]
    return {
        "ok": True,
        "charge_id": data.get("id"),
        "capturado": bool(data.get("capture") or data.get("captured", True)),
        "raw": data,
    }


def crear_customer(*, email: str, nombre: str = "", apellido: str = "",
                   telefono: str = "") -> dict:
    """Crea un cliente Culqi (necesario para guardar tarjetas / One Click).
    Devuelve {ok, customer_id} o {ok:false, error}."""
    if not disponible():
        return {"ok": False, "error": "culqi_no_configurado"}
    body = {
        "first_name": (nombre or "Cliente").strip()[:50] or "Cliente",
        "last_name": (apellido or "Pichangol").strip()[:50] or "Pichangol",
        "email": email,
        "address": "Lima",
        "address_city": "Lima",
        "country_code": "PE",
        "phone_number": (telefono or "999999999").strip()[:15],
    }
    r = _request("POST", "/customers", body)
    if not r["ok"]:
        return r
    return {"ok": True, "customer_id": r["data"].get("id")}


def crear_card(*, customer_id: str, token: str) -> dict:
    """Guarda una tarjeta (token temporal → tarjeta permanente `crd_...`) contra
    un customer. Devuelve {ok, card_id, marca, ultimos4}."""
    if not disponible():
        return {"ok": False, "error": "culqi_no_configurado"}
    r = _request("POST", "/cards",
                 {"customer_id": customer_id, "token_id": token})
    if not r["ok"]:
        return r
    data = r["data"]
    source = data.get("source") or {}
    iin = source.get("iin") or {}
    ultimos = source.get("last_four") or ""
    if not ultimos:
        num = str(source.get("card_number") or "")
        ultimos = num[-4:] if len(num) >= 4 else ""
    return {
        "ok": True,
        "card_id": data.get("id"),
        "marca": iin.get("card_brand") or source.get("card_brand") or "Tarjeta",
        "ultimos4": ultimos,
    }


def eliminar_card(card_id: str) -> dict:
    if not disponible():
        return {"ok": False, "error": "culqi_no_configurado"}
    r = _request("DELETE", f"/cards/{card_id}")
    return {"ok": r["ok"], "error": r.get("error")}


def obtener_cargo(charge_id: str) -> dict:
    """Re-consulta un cargo (fuente de verdad para el webhook). Devuelve
    {ok, charge_id, capturado, monto_centimos, metadata, raw}."""
    if not disponible():
        return {"ok": False, "error": "culqi_no_configurado"}
    r = _request("GET", f"/charges/{charge_id}")
    if not r["ok"]:
        return r
    data = r["data"]
    return {
        "ok": True,
        "charge_id": data.get("id"),
        "capturado": bool(data.get("capture") or data.get("captured", True)),
        "monto_centimos": int(data.get("amount") or 0),
        "metadata": data.get("metadata") or {},
        "raw": data,
    }
