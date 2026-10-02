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
import re
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


# País → (código, ciudad por defecto) para el bloque antifraude cuando el
# cliente no dio dirección. Culqi exige country_code ISO-2 y address_city 2–30.
_PAIS_CIUDAD = {"PE": "Lima", "EC": "Quito", "BO": "La Paz"}
_MONEDA_PAIS = {"PEN": "PE", "USD": "EC", "BOB": "BO"}


def _campo(v: str, fallback: str, minimo: int, maximo: int) -> str:
    """Culqi valida largos MÍNIMOS: first/last_name 2–50, address 5–100,
    address_city 2–30, phone_number 5–15, email ≤50. Un valor corto dispara
    `parameter_error`, así que se recorta y, si no alcanza, cae al fallback."""
    t = (v or "").strip()[:maximo]
    return t if len(t) >= minimo else fallback


def partir_nombre(nombre_completo: str) -> tuple[str, str]:
    """"Dennis Calagua" → ("Dennis", "Calagua"); "Dennis Calagua Ruiz" →
    ("Dennis", "Calagua Ruiz"); "Ana María Pérez Soto" → ("Ana María", "Pérez
    Soto"). Regla: los apellidos son la SEGUNDA mitad (redondeando hacia los
    apellidos), que es lo usual en nombres hispanos. Una sola palabra → sin
    apellido."""
    partes = [w for w in (nombre_completo or "").replace("\u00a0", " ").split() if w]
    if not partes:
        return "", ""
    if len(partes) == 1:
        return partes[0], ""
    corte = max(1, len(partes) // 2)
    return " ".join(partes[:corte]), " ".join(partes[corte:])


def datos_cliente(*, email: str = "", nombre: str = "", apellido: str = "",
                  telefono: str = "", direccion: str = "", ciudad: str = "",
                  pais: str = "", moneda: str = "PEN") -> dict:
    """Arma `antifraud_details` de un cargo con lo que sabemos del cliente
    (queja del director, 27-sep-2026: en el panel de Culqi el cargo salía con
    "first_last_name" y sin teléfono). `nombre` puede venir completo ("Dennis
    Calagua") y sin `apellido`: se parte solo. Sin nombre alguno se usa la
    parte local del correo (mejor que nada para identificar al pagador en el
    panel). Todo cumple los largos que exige Culqi."""
    nom = (nombre or "").strip()
    ape = (apellido or "").strip()
    if nom and not ape:
        nom, ape = partir_nombre(nom)
    if not nom:
        local = (email or "").split("@")[0]
        local = " ".join(w for w in re.split(r"[._\-+0-9]+", local) if w).title()
        nom, ape2 = partir_nombre(local)
        ape = ape or ape2
    iso = (pais or "").strip().upper()[:2] or _MONEDA_PAIS.get((moneda or "PEN").upper(), "PE")
    if iso not in _PAIS_CIUDAD:
        iso = "PE"
    ciu = _campo(ciudad, _PAIS_CIUDAD[iso], 2, 30)
    dire = _campo(direccion, f"{ciu} - {iso}", 5, 100)
    tel = "".join(c for c in (telefono or "") if c.isdigit())
    d = {
        "first_name": _campo(nom, "Cliente", 2, 50),
        "last_name": _campo(ape, "Pichangol", 2, 50),
        "address": dire,
        "address_city": ciu,
        "country_code": iso,
    }
    if 5 <= len(tel) <= 15:
        d["phone_number"] = tel
    return d


def crear_cargo(
    *,
    token: str,
    monto_centimos: int,
    email: str,
    descripcion: str,
    metadata: dict | None = None,
    moneda: str = "PEN",
    cliente: dict | None = None,
) -> dict:
    """Crea un cargo en Culqi. Devuelve {ok, charge_id, capturado, raw} o
    {ok: False, error}. El `token` es el source_id que generó el APK (tarjeta o
    Yape) con la llave pública. `cliente` = {nombre, apellido, telefono,
    direccion, ciudad, pais} (lo que se sepa) → viaja como `antifraud_details`
    para que el panel de Culqi muestre a la persona real y no "first_last_name";
    si es None se arma igual a partir del correo."""
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
    c = dict(cliente or {})
    body["antifraud_details"] = datos_cliente(
        email=email, nombre=str(c.get("nombre") or ""), apellido=str(c.get("apellido") or ""),
        telefono=str(c.get("telefono") or ""), direccion=str(c.get("direccion") or ""),
        ciudad=str(c.get("ciudad") or ""), pais=str(c.get("pais") or ""), moneda=moneda)
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


def reembolsar(*, charge_id: str, monto_centimos: int,
               motivo: str = "solicitud_comprador") -> dict:
    """Devuelve [monto_centimos] de un cargo (total o parcial). Culqi acepta
    reembolsos sobre cargos capturados, en test y en live. Devuelve
    {ok, refund_id, raw} o {ok: False, error}."""
    if not disponible():
        return {"ok": False, "error": "culqi_no_configurado"}
    if not charge_id or monto_centimos <= 0:
        return {"ok": False, "error": "reembolso_invalido"}
    r = _request("POST", "/refunds", {
        "amount": int(monto_centimos), "charge_id": charge_id, "reason": motivo})
    if not r["ok"]:
        return r
    data = r["data"]
    return {"ok": True, "refund_id": data.get("id"), "raw": data}


def crear_customer(*, email: str, nombre: str = "", apellido: str = "",
                   telefono: str = "") -> dict:
    """Crea un cliente Culqi (necesario para guardar tarjetas / One Click).
    Devuelve {ok, customer_id} o {ok:false, error}."""
    if not disponible():
        return {"ok": False, "error": "culqi_no_configurado"}

    # Largos mínimos de Culqi: ver `_campo` (address="Lima", 4 chars, daba
    # `parameter_error`). Un nombre completo sin apellido se parte solo.
    if nombre and not apellido:
        nombre, apellido = partir_nombre(nombre)
    solo_digitos = "".join(c for c in (telefono or "") if c.isdigit())
    body = {
        "first_name": _campo(nombre, "Cliente", 2, 50),
        "last_name": _campo(apellido, "Pichangol", 2, 50),
        "email": (email or "").strip()[:50],
        "address": "Lima - Peru",     # ≥ 5 chars (Culqi lo exige)
        "address_city": "Lima",
        "country_code": "PE",
        "phone_number": solo_digitos[:15] if len(solo_digitos) >= 5 else "999999999",
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
        **_fees_de(data),
    }


def _entero(v) -> int:
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def _fees_de(data: dict) -> dict:
    """Lo que Culqi informa de SU comisión en el objeto del cargo: `total_fee`
    (comisión, en céntimos), `net_amount` (lo que abona) y `fee_details`.
    Culqi los completa DESPUÉS de crear el cargo (su panel avisa "el cálculo
    real de las comisiones y el IGV se mostrará en ~12 h"), por eso se
    re-consulta más tarde (`comision_real`)."""
    fd = data.get("fee_details") if isinstance(data.get("fee_details"), dict) else {}
    return {"total_fee_centimos": _entero(data.get("total_fee")),
            "net_amount_centimos": _entero(data.get("net_amount")),
            "fee_details": fd}


def comision_real(charge_id: str) -> dict:
    """Comisión REAL de la pasarela por un cargo, tomada de Culqi (no
    estimada). Devuelve {ok, conocida, pasarela_centimos, neto_centimos,
    monto_centimos, detalle}. `conocida=False` = Culqi aún no la calculó
    (reintentar más tarde). Preferimos `monto − net_amount` (incluye IGV y
    redondeos de Culqi: es lo que de verdad falta en el abono); si solo
    viene `total_fee`, se usa ese."""
    info = obtener_cargo(charge_id)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error"), "conocida": False}
    monto = int(info.get("monto_centimos") or 0)
    neto = int(info.get("net_amount_centimos") or 0)
    fee = int(info.get("total_fee_centimos") or 0)
    if monto > 0 and 0 < neto < monto:
        pas = monto - neto
    elif fee > 0:
        pas = fee
    else:
        return {"ok": True, "conocida": False, "monto_centimos": monto, "pasarela_centimos": 0, "neto_centimos": 0,
                "detalle": info.get("fee_details") or {}}
    return {"ok": True, "conocida": True, "monto_centimos": monto, "pasarela_centimos": pas, "neto_centimos": monto - pas,
            "detalle": info.get("fee_details") or {}}
