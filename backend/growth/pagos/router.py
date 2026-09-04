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

import html as _html
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from propiedad import admin_auth
from db.store import stores

from . import culqi
from . import libelula
from . import payphone

router = APIRouter(prefix="/pagos", tags=["pagos"])


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    """Sólo el APK oficial (X-App-Key) puede iniciar cobros. Si APP_API_KEY no
    está configurada, no se exige (despliegue gradual)."""
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Auth de operador (torre de control) para marcar liquidaciones pagadas y
    ver las pendientes. Sin token configurado → fail-closed (503)."""
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="admin_no_configurado")
    # Acepta el token clásico O una sesión firmada del login usuario+contraseña.
    if not admin_auth.token_admin_valido(x_admin_token):
        raise HTTPException(status_code=401, detail="token_invalido")


_ADMIN = [Depends(_require_admin)]


# ── AUTH POR USUARIO (endurecimiento PROD) ──────────────────────────────────
# La billetera está keyeada por CORREO: con solo la X-App-Key (que viaja en el
# APK) alguien podría consultar el saldo/movimientos de OTRO usuario o resetear
# su billetera. Con `PAGOS_AUTH_USUARIO=1` (env), esos endpoints exigen además
# el ID TOKEN de Google del usuario (header `X-User-Token`): se verifica contra
# Google (tokeninfo) y el correo del token debe COINCIDIR con el consultado.
# Apagado por defecto (piloto / APKs viejos); en PROD se prende.

# Caché token→(email, expira): un token de Google dura ~1 h; así no se llama a
# Google en cada request.
_tokens_cache: dict[str, tuple[str, datetime]] = {}


def _email_de_token(token: str) -> str | None:
    """Email verificado del ID token de Google, o None si es inválido. Usa
    tokeninfo (sin dependencias de crypto) + caché en memoria."""
    ahora = datetime.now(timezone.utc)
    en_cache = _tokens_cache.get(token)
    if en_cache is not None and en_cache[1] > ahora:
        return en_cache[0]
    import json as _json
    import urllib.parse as _up
    import urllib.request as _ur
    try:
        q = _up.urlencode({"id_token": token})
        with _ur.urlopen(  # noqa: S310
                f"https://oauth2.googleapis.com/tokeninfo?{q}",
                timeout=8) as resp:
            info = _json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    email = (info.get("email") or "").strip().lower()
    if not email or str(info.get("email_verified")).lower() not in (
            "true", "1"):
        return None
    # Si se configuraron los client ids permitidos, exige que el token sea
    # de NUESTRA app (audiencia), no de cualquier app con login de Google.
    permitidos = [a.strip() for a in
                  (config.GOOGLE_OAUTH_CLIENT_IDS or "").split(",")
                  if a.strip()]
    if permitidos and info.get("aud") not in permitidos:
        return None
    try:
        exp = datetime.fromtimestamp(int(info.get("exp", 0)), tz=timezone.utc)
    except (TypeError, ValueError):
        exp = ahora + timedelta(minutes=10)
    # Poda simple del caché para que no crezca sin límite.
    if len(_tokens_cache) > 500:
        _tokens_cache.clear()
    _tokens_cache[token] = (email, min(exp, ahora + timedelta(hours=1)))
    return email


def _require_usuario(dueno_id: str, x_user_token: str | None) -> None:
    """Con PAGOS_AUTH_USUARIO=1: el token debe ser válido y SU correo debe ser
    el consultado. Apagado (default): no exige nada (rollout gradual)."""
    if (config.PAGOS_AUTH_USUARIO or "").strip() not in ("1", "true", "on"):
        return
    email = _email_de_token((x_user_token or "").strip()) \
        if (x_user_token or "").strip() else None
    if email is None or email != dueno_id.strip().lower():
        raise HTTPException(status_code=403, detail="usuario_no_autorizado")


def _soles_a_centimos(soles: float) -> int:
    return int(round(float(soles) * 100))


def comision_centimos(monto_soles: float) -> int:
    """Comisión de Pichangol por una reserva: COMISION_PORC % con mínimo
    COMISION_MIN_SOLES. Devuelve céntimos."""
    bruto = float(monto_soles) * config.COMISION_PORC / 100.0
    con_min = max(bruto, config.COMISION_MIN_SOLES)
    return int(round(con_min * 100))


def comision_saldo_centimos(monto_soles: float) -> int:
    """Comisión cuando se cobra del SALDO prepago del dueño (billetera-first).
    Configurable desde la torre de control (cfg `comision_saldo_pct` y
    `comision_saldo_min_soles`) — puede ser MENOR que la estándar, como
    incentivo por mantener saldo. Sin configurar → usa la comisión estándar.

    OJO: `stores.cfg()` devuelve "0" para claves ausentes, así que aquí se lee
    `stores.config` directo — ausente ≠ 0% (0% sí es configurable a propósito)."""
    try:
        pct = float(stores.config.get("comision_saldo_pct"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return comision_centimos(monto_soles)
    if pct < 0:
        return comision_centimos(monto_soles)
    try:
        min_s = max(0.0, float(stores.config.get("comision_saldo_min_soles", 0)))
    except (TypeError, ValueError):
        min_s = 0.0
    return int(round(max(float(monto_soles) * pct / 100.0, min_s) * 100))


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


class CobroReq(BaseModel):
    token: str                 # tkn_ (tarjeta nueva) o crd_ (tarjeta guardada)
    email: str
    monto_soles: float
    concepto: str = "Pago Pichangol"
    tipo: str = "cobro"        # reserva | academia | cobro


class ComisionReservaReq(BaseModel):
    dueno_id: str              # correo del dueño de la cancha (de cuyo saldo sale)
    monto_soles: float         # precio de la reserva (base para calcular comisión)
    reserva_id: str            # id de la reserva (idempotencia: no cobrar 2 veces)
    concepto: str | None = None


class LiquidacionOnlineReq(BaseModel):
    dueno_id: str              # dueño a quien Pichangol le debe el neto
    monto_soles: float         # precio BRUTO que pagó el jugador online
    reserva_id: str            # idempotencia
    concepto: str | None = None
    # MEDIO con el que pagó el jugador (yape | tarjeta | sena): trazabilidad
    # para el estado de cuenta del dueño. Vacío = no informado (APKs viejos).
    medio: str = ""


class VentaProductoReq(BaseModel):
    vendedor_id: str           # vendedor (dueño/academia) a quien se le debe el neto
    monto_soles: float         # precio BRUTO que pagó el comprador (Culqi)
    venta_id: str              # idempotencia (id de la venta/producto+comprador)
    concepto: str | None = None
    # Datos de la ORDEN (escrow) — para "marcar entregado/recibido".
    producto_id: str = ""
    producto_nombre: str = ""
    comprador_email: str = ""
    comprador_nombre: str = ""
    vendedor_nombre: str = ""


class MarcarLiquidacionReq(BaseModel):
    metodo: str | None = None       # yape | transferencia | efectivo
    referencia: str | None = None   # nº de operación / nota


class MetodoReq(BaseModel):
    token: str                 # token temporal (tkn_) de tokenizar la tarjeta
    user_id: str               # a quién pertenece (correo del jugador)
    email: str
    nombre: str = ""
    apellido: str = ""
    telefono: str = ""


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


@router.get("/checkout", response_class=HTMLResponse)
def get_checkout(amount: int, email: str, title: str = "Pichangol",
                 desc: str = "Pago") -> HTMLResponse:
    """Sirve la página de Culqi Checkout (culqi.js v4) desde el propio backend,
    con la llave PÚBLICA inyectada del lado servidor. El APK la abre en un
    WebView; al generarse el token, la página redirige a un esquema propio
    `pichangol://culqi?...` que el APK intercepta (no expone el token en red)."""
    pk = config.CULQI_PUBLIC_KEY or ""
    amount = max(int(amount), 100)  # mínimo S/ 1.00
    title_s = _html.escape(title)[:40]
    desc_s = _html.escape(desc)[:80]
    email_s = _html.escape(email)[:120]
    page = f"""<!doctype html><html lang="es"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Pago Pichangol</title>
<style>
 html,body{{margin:0;height:100%;background:#F4F6F1;font-family:system-ui,Segoe UI,Roboto,sans-serif;color:#14463A}}
 .c{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:14px;padding:20px;text-align:center}}
 .b{{background:#14463A;color:#AEEA94;border:none;padding:14px 22px;border-radius:14px;font-size:16px;font-weight:700}}
 .m{{color:#7C8A80;font-size:14px}}
</style></head><body>
<div class="c">
  <div id="msg" class="m">Cargando pago seguro…</div>
  <button class="b" id="pay" style="display:none" onclick="abrir()">Pagar</button>
</div>
<script src="https://checkout.culqi.com/js/v4"></script>
<script>
  function volver(qs){{ window.location.href = "pichangol://culqi?" + qs; }}
  try {{ Culqi.publicKey = "{pk}"; }} catch(e) {{}}
  function config(){{
    Culqi.settings({{ title: "{title_s}", currency: "PEN", amount: {amount}, description: "{desc_s}" }});
    Culqi.options({{
      lang: "es",
      installments: false,
      paymentMethods: {{ tarjeta: true, yape: true, bancaMovil: false, agente: false, billetera: false, cuotealo: false }},
      style: {{ buttonBackground: "#14463A", menuColor: "#14463A", buttonText: "Pagar" }}
    }});
  }}
  window.culqi = function(){{
    if (Culqi.token && Culqi.token.id) {{
      volver("status=ok&token=" + encodeURIComponent(Culqi.token.id));
    }} else if (Culqi.error) {{
      volver("status=error&msg=" + encodeURIComponent(Culqi.error.user_message || "error"));
    }}
  }};
  function abrir(){{ try {{ config(); Culqi.open(); }} catch(e) {{ volver("status=error&msg=" + encodeURIComponent(String(e))); }} }}
  // Autoabre; si Culqi aún no cargó, muestra el botón para reintentar.
  var t = setInterval(function(){{
    if (window.Culqi) {{ clearInterval(t); document.getElementById('msg').textContent = 'Elige tu método de pago'; document.getElementById('pay').style.display='block'; abrir(); }}
  }}, 300);
  setTimeout(function(){{ if(!window.Culqi){{ document.getElementById('msg').textContent='No se pudo cargar el pago. Revisa tu conexión.'; }} }}, 8000);
</script>
</body></html>"""
    # No cachear (la página lleva parámetros del cobro).
    return HTMLResponse(content=page, headers={"Cache-Control": "no-store"})


# ── LIBÉLULA (Bolivia): registrar deuda → pagar en la pasarela → callback ─────
class DeudaBoReq(BaseModel):
    email: str
    monto_bs: float
    concepto: str = "Pago Pichangol"
    nombre: str = ""
    apellido: str = ""
    tipo: str = ""       # reserva | sena | matricula | producto | pro | recarga
    ref: str = ""        # id de la reserva/matrícula/… (trazabilidad)
    dueno_id: str = ""   # a quién se liquidará (opcional)


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/bo/config", dependencies=_APP)
def get_bo_config() -> dict:
    """¿Está activa la pasarela de Bolivia? (el APK decide si puede cobrar)."""
    return {"disponible": libelula.disponible(), "moneda": "BOB"}


@router.post("/bo/deuda", dependencies=_APP)
def post_bo_deuda(req: DeudaBoReq) -> dict:
    """Registra una deuda en Libélula y devuelve la URL de la pasarela donde el
    APK (WebView) manda a pagar. Guarda la deuda como PENDIENTE."""
    if not libelula.disponible():
        return {"ok": False, "error": "no_configurado"}
    email = (req.email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "correo_requerido"}
    ident = uuid.uuid4().hex
    base = (config.PUBLIC_BASE_URL or "").rstrip("/")
    callback = f"{base}/pagos/bo/callback" if base else ""
    retorno = f"{base}/pagos/bo/retorno?id={ident}" if base else ""
    r = libelula.registrar_deuda(
        identificador=ident, email=email, monto_bs=req.monto_bs,
        concepto=req.concepto, callback_url=callback, url_retorno=retorno,
        nombre=req.nombre, apellido=req.apellido)
    if not r.get("ok"):
        return r
    stores.libelula_deudas[ident] = {
        "identificador": ident,
        "id_transaccion": r.get("id_transaccion"),
        "email": email,
        "monto_bs": round(float(req.monto_bs), 2),
        "concepto": req.concepto,
        "tipo": req.tipo,
        "ref": req.ref,
        "dueno_id": (req.dueno_id or "").strip().lower(),
        "pagado": False,
        "fecha_pago": None,
        "creado_en": _ahora_iso(),
    }
    return {
        "ok": True,
        "identificador": ident,
        "url_pasarela": r.get("url_pasarela"),
        "qr_url": r.get("qr_url"),
        "retorno": retorno,
    }


def _marcar_pagada(ident: str) -> dict | None:
    """Marca una deuda como pagada (idempotente). Si es una RECARGA de saldo,
    acredita al dueño (una sola vez, guardado por el flag `pagado`)."""
    d = stores.libelula_deudas.get(ident)
    if not d:
        return None
    if not d.get("pagado"):
        d["pagado"] = True
        d["fecha_pago"] = _ahora_iso()
        # Recarga de billetera: el saldo lo acredita el BACKEND (no el APK) al
        # confirmarse el pago. Bolivianos en Bs (moneda BOB).
        if d.get("tipo") == "recarga" and d.get("dueno_id"):
            centimos = int(round(float(d.get("monto_bs") or 0) * 100))
            if centimos > 0:
                stores.acreditar(d["dueno_id"], centimos)
                stores.registrar_pago(
                    tipo="recarga", monto_centimos=centimos, moneda="BOB",
                    estado="aprobado", dueno_id=d["dueno_id"],
                    email=d.get("email", ""), concepto="Recarga (Libélula)")
                # PROMO bono de recarga (los umbrales aplican en Bs).
                _aplicar_bono_recarga(
                    d["dueno_id"], centimos / 100.0, f"lib_{ident}")
    return d


@router.api_route("/bo/callback", methods=["GET", "POST"])
def bo_callback(transaction_id: str = "") -> dict:
    """PAGO EXITOSO de Libélula (GET con ?transaction_id=<id_transaccion>). Antes
    de marcar pagado se VERIFICA con Libélula (consultar por identificador), para
    que un GET falso no confirme un pago. Público (lo llama Libélula)."""
    tx = (transaction_id or "").strip()
    if not tx:
        return {"ok": False}
    ident = None
    for k, d in stores.libelula_deudas.items():
        if str(d.get("id_transaccion")) == tx:
            ident = k
            break
    if not ident:
        return {"ok": False}
    est = libelula.consultar_por_identificador(ident)
    if est.get("ok") and est.get("pagado"):
        _marcar_pagada(ident)
        return {"ok": True}
    return {"ok": False}


@router.get("/bo/deuda/{identificador}", dependencies=_APP)
def get_bo_deuda(identificador: str) -> dict:
    """Estado de una deuda (el APK consulta si ya se pagó). Si sigue pendiente
    localmente, RECONCILIA con Libélula (por si el callback no llegó)."""
    d = stores.libelula_deudas.get(identificador)
    if not d:
        return {"ok": False, "error": "no_encontrada"}
    if not d.get("pagado"):
        est = libelula.consultar_por_identificador(identificador)
        if est.get("ok") and est.get("pagado"):
            _marcar_pagada(identificador)
    return {"ok": True, "pagado": bool(d.get("pagado")),
            "monto_bs": d.get("monto_bs"), "concepto": d.get("concepto")}


@router.get("/bo/retorno", response_class=HTMLResponse)
def bo_retorno(id: str = "") -> HTMLResponse:
    """Página a la que Libélula devuelve al cliente tras pagar. El WebView del
    APK la detecta y cierra confirmando; si abrió en el navegador, muestra un
    mensaje claro para volver a la app."""
    page = ("<!doctype html><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Pago Pichangol</title>"
            "<div style='font-family:system-ui;text-align:center;padding:44px;color:#14463A'>"
            "<h2>¡Pago recibido! ✅</h2>"
            "<p>Ya puedes volver a Pichangol.</p></div>")
    return HTMLResponse(content=page, headers={"Cache-Control": "no-store"})


# ── PAYPHONE (Ecuador): preparar → pagar en la página hospedada → CONFIRMAR ──
# El cobro NO existe hasta que PayPhone lo confirma (Confirm es la única fuente
# de verdad) y si no se confirma en 5 minutos PayPhone lo revierte solo. Por eso
# el retorno confirma al instante y el APK, además, manda el transaction_id al
# consultar el estado (doble vía, idempotente).
class PagoEcReq(BaseModel):
    email: str
    monto_usd: float
    concepto: str = "Pago Pichangol"
    nombre: str = ""
    telefono: str = ""
    documento: str = ""
    tipo: str = ""       # reserva | sena | matricula | producto | pro | recarga
    ref: str = ""        # id de la reserva/matrícula/… (trazabilidad)
    dueno_id: str = ""   # a quién se liquidará / acredita (recarga)


@router.get("/ec/config", dependencies=_APP)
def get_ec_config() -> dict:
    """¿Está activa la pasarela de Ecuador? (el APK decide si puede cobrar)."""
    return {"disponible": payphone.disponible(), "moneda": "USD"}


@router.post("/ec/pago", dependencies=_APP)
def post_ec_pago(req: PagoEcReq) -> dict:
    """Prepara el pago en PayPhone y devuelve las URLs hospedadas donde el APK
    (WebView) manda a pagar. Guarda el pago como PENDIENTE."""
    if not payphone.disponible():
        return {"ok": False, "error": "no_configurado"}
    email = (req.email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "correo_requerido"}
    monto = round(float(req.monto_usd), 2)
    if monto <= 0:
        return {"ok": False, "error": "monto_invalido"}
    ident = uuid.uuid4().hex[:16]  # PayPhone sugiere ids cortos y únicos
    base = (config.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "sin_base_url"}
    r = payphone.preparar(
        client_tx_id=ident, monto_usd=monto, concepto=req.concepto,
        response_url=f"{base}/pagos/ec/retorno",
        cancel_url=f"{base}/pagos/ec/cancelado",
        email=email, telefono=req.telefono, documento=req.documento)
    if not r.get("ok"):
        return r
    stores.payphone_pagos[ident] = {
        "identificador": ident,
        "payment_id": r.get("payment_id"),
        "transaction_id": None,
        # URLs hospedadas de PayPhone: las sirve la página PUENTE (/ec/ir).
        "url_tarjeta": r.get("url_tarjeta"),
        "url_payphone": r.get("url_payphone"),
        "email": email,
        "monto_usd": monto,
        "concepto": req.concepto,
        "tipo": req.tipo,
        "ref": req.ref,
        "dueno_id": (req.dueno_id or "").strip().lower(),
        "pagado": False,
        "estado": "pendiente",
        "autorizacion": None,
        "fecha_pago": None,
        "creado_en": _ahora_iso(),
    }
    return {
        "ok": True,
        "identificador": ident,
        "url_pasarela": r.get("url_tarjeta") or r.get("url_payphone"),
        "url_payphone": r.get("url_payphone"),
        # El APK abre ESTA (nuestro dominio), no la de PayPhone directo: la
        # página de PayPhone exige llegar desde un dominio autorizado.
        "url_lanzador": f"{base}/pagos/ec/ir/{ident}",
        "retorno": f"{base}/pagos/ec/retorno",
    }


@router.get("/ec/ir/{identificador}", response_class=HTMLResponse)
def ec_ir(identificador: str, medio: str = "tarjeta") -> HTMLResponse:
    """Página PUENTE hacia la pasarela de PayPhone, servida desde NUESTRO
    dominio. PayPhone rechaza su página de pago ("No autorizado… intenta desde
    la página de origen") si el navegador llega sin un origen autorizado; un
    WebView que abre la URL a pelo no lo tiene. Esta página está en el dominio
    registrado en la app de PayPhone (AuthDomains) y navega por JavaScript a
    la pasarela, con lo que el Referer/origen es el nuestro. Sin JS, queda el
    botón. Pública: sólo redirige a una URL que PayPhone ya emitió."""
    d = stores.payphone_pagos.get(identificador)
    if not d or d.get("pagado"):
        return _pagina_ec("Pago no disponible",
                          "Vuelve a Pichangol e inicia el pago otra vez.")
    url = (d.get("url_payphone") if medio == "payphone" else None) \
        or d.get("url_tarjeta") or d.get("url_payphone") or ""
    if not url:
        return _pagina_ec("Pago no disponible",
                          "Vuelve a Pichangol e inicia el pago otra vez.")
    u = _html.escape(url, quote=True)
    page = ("<!doctype html><html lang=es><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta name=referrer content=origin>"
            "<title>Pago Pichangol</title></head>"
            "<body style='font-family:system-ui;text-align:center;padding:44px;"
            "color:#14463A'><p>Abriendo el pago seguro de PayPhone…</p>"
            f"<p><a href=\"{u}\" style='display:inline-block;margin-top:12px;"
            "padding:12px 20px;border-radius:12px;background:#AEEA94;"
            "color:#14463A;font-weight:700;text-decoration:none'>"
            "Continuar al pago</a></p>"
            f"<script>setTimeout(function(){{window.location.href={_json_str(url)};}},150);"
            "</script></body></html>")
    return HTMLResponse(content=page, headers={"Cache-Control": "no-store"})


def _json_str(s: str) -> str:
    """String JS seguro (comillas y </script> escapados)."""
    import json as _json
    return _json.dumps(s).replace("</", "<\\/")


def _confirmar_ec(ident: str, transaction_id: str) -> dict | None:
    """Confirma con PayPhone y, si aprobó, marca pagado (idempotente). Si es
    una RECARGA, acredita el saldo al dueño una sola vez. Devuelve el pago o
    None si no existe."""
    d = stores.payphone_pagos.get(ident)
    if not d:
        return None
    if d.get("pagado"):
        return d
    tx = str(transaction_id or d.get("transaction_id") or "").strip()
    if not tx:
        return d
    d["transaction_id"] = tx
    c = payphone.confirmar(transaction_id=tx, client_tx_id=ident)
    if not c.get("ok"):
        d["estado"] = f"error: {c.get('error', '')}"[:80]
        return d
    d["estado"] = str(c.get("estado") or "")[:40]
    d["autorizacion"] = c.get("autorizacion")
    if not c.get("aprobado"):
        return d
    # Defensa: si PayPhone reporta un monto y no cuadra, NO se da por pagado.
    mc = c.get("monto_centavos")
    if isinstance(mc, (int, float)) and int(mc) != payphone.centavos(d["monto_usd"]):
        d["estado"] = "monto_no_cuadra"
        return d
    d["pagado"] = True
    d["fecha_pago"] = _ahora_iso()
    if d.get("tipo") == "recarga" and d.get("dueno_id"):
        cts = payphone.centavos(d["monto_usd"])
        if cts > 0:
            stores.acreditar(d["dueno_id"], cts)
            stores.registrar_pago(
                tipo="recarga", monto_centimos=cts, moneda="USD",
                estado="aprobado", dueno_id=d["dueno_id"],
                email=d.get("email", ""), concepto="Recarga (PayPhone)")
            # PROMO bono de recarga (los umbrales aplican en USD).
            _aplicar_bono_recarga(d["dueno_id"], cts / 100.0, f"pp_{ident}")
    return d


def _pagina_ec(titulo: str, cuerpo: str) -> HTMLResponse:
    page = ("<!doctype html><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Pago Pichangol</title>"
            "<div style='font-family:system-ui;text-align:center;padding:44px;"
            f"color:#14463A'><h2>{_html.escape(titulo)}</h2>"
            f"<p>{_html.escape(cuerpo)}</p></div>")
    return HTMLResponse(content=page, headers={"Cache-Control": "no-store"})


@router.get("/ec/retorno", response_class=HTMLResponse)
def ec_retorno(id: str = "", clientTransactionId: str = "") -> HTMLResponse:
    """Página a la que PayPhone devuelve al cliente tras pagar (con ?id=<tx>&
    clientTransactionId=<ident>). CONFIRMA de inmediato (regla de los 5 min).
    Pública (la abre el navegador/WebView). Un GET con datos falsos no aprueba
    nada: la verdad la dice Confirm."""
    ident = (clientTransactionId or "").strip()
    d = _confirmar_ec(ident, id) if ident else None
    if d and d.get("pagado"):
        return _pagina_ec("¡Pago recibido! ✅", "Ya puedes volver a Pichangol.")
    if d:
        return _pagina_ec("Pago no aprobado",
                          "PayPhone no aprobó el cobro. Puedes intentarlo de "
                          "nuevo desde la app; no se te cobró nada.")
    return _pagina_ec("Pago no encontrado",
                      "Vuelve a Pichangol e intenta otra vez.")


@router.get("/ec/cancelado", response_class=HTMLResponse)
def ec_cancelado(clientTransactionId: str = "") -> HTMLResponse:
    """PayPhone manda aquí si el cliente cancela en la pasarela."""
    d = stores.payphone_pagos.get((clientTransactionId or "").strip())
    if d and not d.get("pagado"):
        d["estado"] = "cancelado"
    return _pagina_ec("Pago cancelado", "No se te cobró nada. Puedes volver a "
                      "Pichangol e intentarlo cuando quieras.")


@router.get("/ec/pago/{identificador}", dependencies=_APP)
def get_ec_pago(identificador: str, transaction_id: str = "") -> dict:
    """Estado de un pago (el APK consulta si ya se pagó). Si el APK trae el
    transaction_id que vio en la URL de retorno, CONFIRMA aquí mismo — así el
    cobro se confirma aunque el retorno nunca haya llegado al backend."""
    d = stores.payphone_pagos.get(identificador)
    if not d:
        return {"ok": False, "error": "no_encontrado"}
    if not d.get("pagado") and (transaction_id or d.get("transaction_id")):
        d = _confirmar_ec(identificador, transaction_id) or d
    return {"ok": True, "pagado": bool(d.get("pagado")),
            "estado": d.get("estado"), "monto_usd": d.get("monto_usd"),
            "concepto": d.get("concepto"), "autorizacion": d.get("autorizacion")}


@router.get("/saldo/{dueno_id}", dependencies=_APP)
def get_saldo(dueno_id: str,
              x_user_token: str | None = Header(default=None)) -> dict:
    _require_usuario(dueno_id, x_user_token)  # PROD: solo su propio saldo
    c = stores.saldo_centimos(dueno_id)
    promo = stores.saldo_promo_centimos(dueno_id)
    return {"dueno_id": dueno_id, "saldo_centimos": c, "saldo_soles": c / 100.0,
            # Regalo de bienvenida (solo comisiones): el APK lo muestra aparte.
            "saldo_promo_centimos": promo, "saldo_promo_soles": promo / 100.0}


class ResetBilleteraReq(BaseModel):
    dueno_id: str


@router.post("/reset-mi-billetera", dependencies=_APP)
def post_reset_mi_billetera(
        req: ResetBilleteraReq,
        x_user_token: str | None = Header(default=None)) -> dict:
    """El DUEÑO deja SU billetera en virgen (saldo 0 y sin movimientos) al 'dejar
    en virgen' desde la app. Como el saldo/pagos viven en el backend, sin esto
    volverían al re-sincronizar. Solo toca al usuario que se manda; no borra la
    plata de otros (por eso no exige token admin). Con PAGOS_AUTH_USUARIO=1
    exige el ID token de Google del PROPIO usuario (nadie resetea billeteras
    ajenas con solo la app key). El middleware persiste el snapshot."""
    _require_usuario(req.dueno_id, x_user_token)
    r = stores.reset_billetera_de(req.dueno_id)
    return {"ok": True, **r}


# ── RECARGAS POR QR (Yape directo, sin comisión de pasarela) ────────────────
# El usuario yapea al QR de Pichangol, sube su constancia y el OPERADOR la
# aprueba en la torre (modelo concierge, como los reclamos): al aprobar se
# acredita el saldo, se registra el pago (medio yape_qr) y le llega el push
# "Recarga acreditada". Cero comisión mientras el volumen es chico.


def _aviso_push_usuario(email: str, titulo: str, cuerpo: str,
                        tipo: str = "aviso") -> None:
    """Encola un push al usuario vía la tabla `pichangol_avisos` de Supabase
    (Database Webhook → Edge Function push-aviso). Best-effort: sin Supabase
    configurado o con error de red, no rompe el flujo."""
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        return
    base = config.SUPABASE_URL
    if not base.startswith("http"):
        base = f"https://{base}"
    try:
        import json as _json
        import urllib.request as _ur
        req = _ur.Request(
            f"{base}/rest/v1/pichangol_avisos",
            data=_json.dumps({
                "email": email.strip().lower(),
                "titulo": titulo,
                "cuerpo": cuerpo,
                "tipo": tipo,
                "creado": datetime.now(timezone.utc).isoformat(),
            }).encode(),
            method="POST",
            headers={
                "apikey": config.SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            })
        with _ur.urlopen(req, timeout=8) as r:  # noqa: S310
            r.read()
    except Exception:  # noqa: BLE001
        pass


class RecargaQrReq(BaseModel):
    email: str                 # billetera a recargar (el propio usuario)
    monto_soles: float
    foto_url: str = ""         # constancia del Yape (subida al Storage)


@router.get("/recarga-qr/config", dependencies=_APP)
def get_recarga_qr_config() -> dict:
    """Config para el APK: si la recarga por QR está activa (hay QR subido) y
    qué mostrar (imagen del QR, número y nombre del titular)."""
    return {
        "activo": bool(config.RECARGA_YAPE_QR_URL),
        "qr_url": config.RECARGA_YAPE_QR_URL,
        "numero": config.RECARGA_YAPE_NUMERO,
        "nombre": config.RECARGA_YAPE_NOMBRE,
    }


@router.post("/recarga-qr", dependencies=_APP)
def post_recarga_qr(req: RecargaQrReq,
                    x_user_token: str | None = Header(default=None)) -> dict:
    """Crea la SOLICITUD de recarga por QR (queda pendiente de aprobación del
    operador). Una pendiente por usuario a la vez (anti-spam)."""
    email = req.email.strip().lower()
    if not email or req.monto_soles <= 0:
        raise HTTPException(status_code=400, detail="datos_invalidos")
    if req.monto_soles > 1000:
        raise HTTPException(status_code=400, detail="monto_maximo_1000")
    _require_usuario(email, x_user_token)  # PROD: solo su propia billetera
    for r in stores.recargas_qr:
        if r.get("email") == email and r.get("estado") == "pendiente":
            return {"ok": False, "error": "ya_tienes_una_pendiente",
                    "solicitud": r}
    sol = {
        "id": stores.next_id("recarga_qr"),
        "email": email,
        "monto_soles": round(float(req.monto_soles), 2),
        "foto_url": (req.foto_url or "").strip(),
        "estado": "pendiente",
        "creado_en": _ahora_iso(),
        "resuelto_en": None,
        "motivo": None,
    }
    stores.recargas_qr.append(sol)
    return {"ok": True, "solicitud": sol}


@router.get("/recarga-qr/estado/{email}", dependencies=_APP)
def get_recarga_qr_estado(email: str) -> dict:
    """Solicitudes del usuario (la pendiente y las últimas resueltas), para
    que la billetera muestre 'En revisión ⏳' y el desenlace."""
    e = email.strip().lower()
    mias = [r for r in stores.recargas_qr if r.get("email") == e]
    return {"solicitudes": list(reversed(mias[-5:]))}


@router.get("/recargas-qr", dependencies=_ADMIN)
def get_recargas_qr_admin(estado: str | None = None) -> dict:
    """TORRE: lista de solicitudes de recarga por QR (pendientes primero)."""
    sols = [r for r in stores.recargas_qr
            if estado is None or r.get("estado") == estado]
    orden = sorted(sols, key=lambda r: (r.get("estado") != "pendiente",
                                        -(r.get("id") or 0)))
    return {"solicitudes": orden,
            "pendientes": sum(1 for r in stores.recargas_qr
                              if r.get("estado") == "pendiente")}


class ResolverRecargaQrReq(BaseModel):
    motivo: str = ""           # al rechazar: no_llego | monto_no_coincide |
    #                            constancia_ilegible (selección en la torre)


@router.post("/recarga-qr/{solicitud_id}/aprobar", dependencies=_ADMIN)
def post_recarga_qr_aprobar(solicitud_id: int) -> dict:
    """TORRE: el operador VERIFICÓ el Yape en su app → acredita el saldo,
    registra el pago (recarga, medio yape_qr) y avisa al usuario con push.
    Idempotente: aprobar dos veces no acredita doble."""
    for r in stores.recargas_qr:
        if r.get("id") == solicitud_id:
            if r.get("estado") != "pendiente":
                return {"ok": True, "duplicada": True, "solicitud": r}
            centimos = _soles_a_centimos(r["monto_soles"])
            nuevo = stores.acreditar(r["email"], centimos)
            stores.registrar_pago(
                tipo="recarga", monto_centimos=centimos, moneda="PEN",
                estado="aprobado", dueno_id=r["email"],
                culqi_charge_id=f"qr_{solicitud_id}",
                concepto="Recarga por Yape (QR)", medio="yape_qr")
            r["estado"] = "aprobada"
            r["resuelto_en"] = _ahora_iso()
            _aviso_push_usuario(
                r["email"], "Recarga acreditada ✅",
                f"+S/ {r['monto_soles']:.2f} a tu saldo Pichangol por tu "
                "Yape al QR. ¡Gracias!", tipo="recarga")
            bono = _aplicar_bono_recarga(
                r["email"], r["monto_soles"], f"qr_{solicitud_id}")
            return {"ok": True, "duplicada": False, "solicitud": r,
                    "bono_soles": bono, "saldo_centimos": nuevo}
    raise HTTPException(status_code=404, detail="solicitud_no_encontrada")


@router.post("/recarga-qr/{solicitud_id}/rechazar", dependencies=_ADMIN)
def post_recarga_qr_rechazar(solicitud_id: int,
                             req: ResolverRecargaQrReq) -> dict:
    """TORRE: rechaza la solicitud (con motivo por selección) y avisa al
    usuario con push para que corrija o pregunte."""
    _MOTIVOS = {
        "no_llego": "no encontramos tu Yape",
        "monto_no_coincide": "el monto no coincide con tu Yape",
        "constancia_ilegible": "la constancia no se puede leer",
    }
    for r in stores.recargas_qr:
        if r.get("id") == solicitud_id:
            if r.get("estado") != "pendiente":
                return {"ok": True, "duplicada": True, "solicitud": r}
            r["estado"] = "rechazada"
            r["motivo"] = req.motivo or "no_llego"
            r["resuelto_en"] = _ahora_iso()
            detalle = _MOTIVOS.get(r["motivo"], "no se pudo validar")
            _aviso_push_usuario(
                r["email"], "Recarga no acreditada ❌",
                f"Tu recarga de S/ {r['monto_soles']:.2f} no se acreditó: "
                f"{detalle}. Vuelve a intentarlo o escríbenos.",
                tipo="recarga")
            return {"ok": True, "duplicada": False, "solicitud": r}
    raise HTTPException(status_code=404, detail="solicitud_no_encontrada")


# ── BODEGA fase 3: pagar el PEDIDO con saldo Pichangol ──────────────────────
# El cliente PREPAGA su pedido a la cancha con su saldo (billetera única): se
# le debita y el dueño queda con el monto COMPLETO "por recibir" (la bodega es
# CERO COMISIÓN por decisión de producto — comisión congelada en 0). Si el
# pedido se cancela/rechaza/expira, el reembolso devuelve el saldo íntegro.


class BodegaPagoReq(BaseModel):
    cliente: str               # quien paga (su saldo)
    dueno_id: str              # dueño de la bodega (recibe el neto)
    monto_soles: float
    pedido_id: str             # idempotencia (un cobro por pedido)
    concepto: str | None = None


@router.post("/bodega-pago", dependencies=_APP)
def post_bodega_pago(req: BodegaPagoReq,
                     x_user_token: str | None = Header(default=None)) -> dict:
    """Debita el saldo del cliente y deja el monto completo por recibir del
    dueño. Idempotente por pedido_id."""
    cliente = req.cliente.strip().lower()
    dueno = req.dueno_id.strip().lower()
    pid = req.pedido_id.strip()
    if not cliente or not dueno or not pid or req.monto_soles <= 0:
        raise HTTPException(status_code=400, detail="datos_invalidos")
    _require_usuario(cliente, x_user_token)  # PROD: solo su propio saldo
    ref = f"bod_{pid}"
    ya = stores.pago_por_charge(ref)
    if ya is not None:
        return {"ok": ya.estado == "aprobado", "duplicada": True,
                "estado": ya.estado}
    cent = _soles_a_centimos(req.monto_soles)
    if stores.saldo_centimos(cliente) < cent:
        return {"ok": False, "error": "saldo_insuficiente",
                "saldo_soles": stores.saldo_centimos(cliente) / 100.0}
    stores.debitar(cliente, cent)
    # Egreso del CLIENTE (visible en su billetera).
    stores.registrar_pago(
        tipo="bodega_pago", monto_centimos=cent, moneda="PEN",
        estado="aprobado", dueno_id=cliente,
        culqi_charge_id=f"{ref}_deb",
        concepto=req.concepto or "Pedido de bodega", medio="saldo")
    # POR RECIBIR del DUEÑO, monto completo (comisión congelada en 0).
    stores.registrar_pago(
        tipo="venta_bodega", monto_centimos=cent, moneda="PEN",
        estado="aprobado", dueno_id=dueno, culqi_charge_id=ref,
        comision_centimos=0,
        concepto=req.concepto or "Pedido de bodega (pagado con saldo)",
        medio="saldo")
    return {"ok": True, "duplicada": False,
            "saldo_centimos": stores.saldo_centimos(cliente)}


class BodegaReembolsoReq(BaseModel):
    pedido_id: str


@router.post("/bodega-reembolso", dependencies=_APP)
def post_bodega_reembolso(req: BodegaReembolsoReq) -> dict:
    """Reembolsa un pedido PAGADO con saldo que no procedió (cancelado,
    rechazado o expirado): anula ambos asientos y devuelve el saldo íntegro
    al cliente. Idempotente. Si el dueño ya cobró su liquidación, se corta
    (resolución manual del operador)."""
    ref = f"bod_{req.pedido_id.strip()}"
    venta = stores.pago_por_charge(ref)
    if venta is None or venta.tipo != "venta_bodega":
        raise HTTPException(status_code=404, detail="pago_no_encontrado")
    if venta.estado != "aprobado":
        return {"ok": True, "duplicada": True}  # ya reembolsado
    if venta.liquidado:
        return {"ok": False, "error": "ya_liquidada_al_dueno"}
    deb = stores.pago_por_charge(f"{ref}_deb")
    venta.estado = "anulado"
    cliente = deb.dueno_id if deb is not None else None
    if deb is not None:
        deb.estado = "anulado"
        stores.acreditar(deb.dueno_id, deb.monto_centimos)
        _aviso_push_usuario(
            deb.dueno_id, "Te devolvimos tu saldo 💸",
            f"Tu pedido de bodega no procedió: +S/ "
            f"{deb.monto_centimos / 100:.2f} de vuelta en tu saldo.",
            tipo="recarga")
    return {"ok": True, "duplicada": False, "cliente": cliente}


@router.get("/bodega-pago/{pedido_id}", dependencies=_APP)
def get_bodega_pago(pedido_id: str) -> dict:
    """¿Este pedido está realmente PAGADO con saldo? (El dueño lo verifica
    antes de entregar sin cobrar — cierra la ventana de fraude/fallas.)"""
    ya = stores.pago_por_charge(f"bod_{pedido_id.strip()}")
    return {"pagado": ya is not None and ya.tipo == "venta_bodega"
            and ya.estado == "aprobado"}


# ── PROMOCIONES de la billetera: bono de recarga + cupones ─────────────────
# Lo paga Pichangol (costo de marketing), todo editable en la torre. El bono
# se aplica SOLO en recargas (no en liquidaciones) y es idempotente por cargo.


def _promo_bono_cfg() -> tuple[float, float, float]:
    def _f(clave: str) -> float:
        try:
            return float(stores.cfg(clave))
        except (TypeError, ValueError):
            return 0.0
    return (_f("promo_bono_recarga_pct"), _f("promo_bono_recarga_min"),
            _f("promo_bono_recarga_tope"))


def _aplicar_bono_recarga(dueno_id: str, monto_soles: float,
                          ref: str) -> float:
    """Si el bono de recarga está activo (pct > 0) y la recarga alcanza el
    mínimo, acredita el extra. Idempotente por [ref] (un bono por cargo).
    Devuelve el bono acreditado en soles (0 = no aplicó)."""
    pct, minimo, tope = _promo_bono_cfg()
    if pct <= 0 or monto_soles < minimo or not dueno_id:
        return 0.0
    bono = round(monto_soles * pct / 100, 2)
    if tope > 0:
        bono = min(bono, tope)
    if bono <= 0:
        return 0.0
    ref_bono = f"{ref}_bono"
    if stores.pago_por_charge(ref_bono) is not None:
        return 0.0  # ya se dio el bono de este cargo
    cent = _soles_a_centimos(bono)
    stores.acreditar(dueno_id, cent)
    stores.registrar_pago(
        tipo="bono_recarga", monto_centimos=cent, moneda="PEN",
        estado="aprobado", dueno_id=dueno_id, culqi_charge_id=ref_bono,
        concepto=f"Bono de recarga (+{pct:g}%)")
    _aviso_push_usuario(
        dueno_id, "¡Bono de recarga! 🎁",
        f"Te regalamos +{bono:.2f} extra en tu saldo por tu recarga. "
        "¡A jugar!", tipo="recarga")
    return bono


@router.get("/promos", dependencies=_APP)
def get_promos() -> dict:
    """Promos vigentes para mostrar en la billetera del APK (banner)."""
    pct, minimo, tope = _promo_bono_cfg()
    return {"bono_recarga": {
        "activo": pct > 0, "pct": pct, "min": minimo, "tope": tope}}


class PromoBonoReq(BaseModel):
    pct: float = 0
    minimo: float = 50
    tope: float = 20


@router.get("/promos/admin", dependencies=_ADMIN)
def get_promos_admin() -> dict:
    pct, minimo, tope = _promo_bono_cfg()
    return {"pct": pct, "min": minimo, "tope": tope}


@router.post("/promos/admin", dependencies=_ADMIN)
def set_promos_admin(req: PromoBonoReq) -> dict:
    """TORRE: configura el bono de recarga (pct 0 = apagado)."""
    if req.pct < 0 or req.pct > 100 or req.minimo < 0 or req.tope < 0:
        raise HTTPException(status_code=400, detail="valores_invalidos")
    stores.config["promo_bono_recarga_pct"] = str(req.pct)
    stores.config["promo_bono_recarga_min"] = str(req.minimo)
    stores.config["promo_bono_recarga_tope"] = str(req.tope)
    return {"ok": True, **get_promos_admin()}


class CuponCrearReq(BaseModel):
    codigo: str = ""           # vacío = se genera (PCG-XXXXXX)
    valor_soles: float
    usos_max: int = 100


class CuponCanjeReq(BaseModel):
    email: str
    codigo: str


def _cupon_norm(codigo: str) -> str:
    return codigo.strip().upper().replace(" ", "")


@router.get("/cupones", dependencies=_ADMIN)
def get_cupones() -> dict:
    """TORRE: cupones con sus usos."""
    return {"cupones": [
        {"codigo": k, "valor_soles": v.get("valor_soles", 0),
         "usos_max": v.get("usos_max", 0),
         "usados": len(v.get("usados", [])),
         "activo": v.get("activo", True),
         "creado_en": v.get("creado_en")}
        for k, v in sorted(stores.cupones.items())
    ]}


@router.post("/cupones", dependencies=_ADMIN)
def post_cupon_crear(req: CuponCrearReq) -> dict:
    """TORRE: crea un cupón de saldo (campañas con academias, sorteos…)."""
    if req.valor_soles <= 0 or req.valor_soles > 500:
        raise HTTPException(status_code=400, detail="valor_invalido")
    if req.usos_max <= 0 or req.usos_max > 10000:
        raise HTTPException(status_code=400, detail="usos_invalidos")
    codigo = _cupon_norm(req.codigo) or f"PCG-{uuid.uuid4().hex[:6].upper()}"
    if codigo in stores.cupones:
        raise HTTPException(status_code=409, detail="codigo_ya_existe")
    stores.cupones[codigo] = {
        "valor_soles": round(req.valor_soles, 2),
        "usos_max": req.usos_max,
        "usados": [],
        "activo": True,
        "creado_en": _ahora_iso(),
    }
    return {"ok": True, "codigo": codigo}


@router.post("/cupones/{codigo}/desactivar", dependencies=_ADMIN)
def post_cupon_desactivar(codigo: str) -> dict:
    c = stores.cupones.get(_cupon_norm(codigo))
    if c is None:
        raise HTTPException(status_code=404, detail="cupon_no_encontrado")
    c["activo"] = False
    return {"ok": True}


@router.post("/cupon/canjear", dependencies=_APP)
def post_cupon_canjear(req: CuponCanjeReq,
                       x_user_token: str | None = Header(default=None)) -> dict:
    """El usuario canjea un cupón: acredita el valor a SU saldo. Un canje por
    usuario por cupón; respeta el candado de identidad de PROD."""
    email = req.email.strip().lower()
    codigo = _cupon_norm(req.codigo)
    if not email or not codigo:
        raise HTTPException(status_code=400, detail="datos_invalidos")
    _require_usuario(email, x_user_token)
    c = stores.cupones.get(codigo)
    if c is None or not c.get("activo", True):
        return {"ok": False, "error": "cupon_invalido"}
    usados = c.setdefault("usados", [])
    if email in usados:
        return {"ok": False, "error": "ya_lo_canjeaste"}
    if len(usados) >= int(c.get("usos_max", 0)):
        return {"ok": False, "error": "cupon_agotado"}
    valor = float(c.get("valor_soles", 0))
    cent = _soles_a_centimos(valor)
    usados.append(email)
    nuevo = stores.acreditar(email, cent)
    stores.registrar_pago(
        tipo="cupon", monto_centimos=cent, moneda="PEN", estado="aprobado",
        dueno_id=email, culqi_charge_id=f"cupon_{codigo}_{email}",
        concepto=f"Cupón {codigo}")
    return {"ok": True, "valor_soles": valor,
            "saldo_centimos": nuevo, "saldo_soles": nuevo / 100.0}


class ConsolidarReq(BaseModel):
    desde_id: str              # llave secundaria (p. ej. id de una academia)
    hacia_id: str              # billetera del dueño (su correo)


@router.post("/consolidar", dependencies=_APP)
def post_consolidar(req: ConsolidarReq) -> dict:
    """BILLETERA ÚNICA por usuario: mueve el saldo prepago que quedó bajo una
    llave secundaria (el id de una academia) a la billetera del dueño (su
    correo), para que vea UN solo saldo en 'Mi cuenta' y en cada academia.
    Idempotente (tras mover, la llave secundaria queda en 0). El APK lo llama al
    abrir el panel de la academia. OJO: `hacia_id` debe ser EXACTAMENTE la misma
    llave con la que el APK lee la billetera del dueño (su correo, sin
    transformar), para no partir el saldo en dos llaves por diferencias de caja."""
    hacia = req.hacia_id.strip()
    desde = req.desde_id.strip()
    nuevo = stores.transferir_saldo(desde, hacia)
    return {"ok": True, "hacia_id": hacia,
            "saldo_centimos": nuevo, "saldo_soles": nuevo / 100.0}


# ─────────────────────── PICHANGOL PRO (membresía jugador) ────────────────────
# Membresía mensual del JUGADOR que se cobra de su BILLETERA ÚNICA (saldo del
# email). Suscribir debita 1 mes y extiende la vigencia +30 días; el cron
# `/pro/renovar-vencidas` renueva desde el saldo. Si no hay saldo, no renueva
# (la membresía vence) y el APK lo manda a recargar.

def _pro_precio_centimos(pais: str = "PE") -> int:
    """Precio Pro en céntimos según el país: override por país (EC/BO) o el base
    (Perú) si el override está vacío."""
    iso = (pais or "PE").upper()
    val = ""
    if iso == "EC":
        val = stores.cfg("pro_precio_soles_ec")
    elif iso == "BO":
        val = stores.cfg("pro_precio_soles_bo")
    if not val:
        val = stores.cfg("pro_precio_soles")
    try:
        return max(0, int(round(float(val) * 100)))
    except (TypeError, ValueError):
        return 1200


def _pro_estado(email: str) -> tuple[bool, str | None]:
    m = stores.membresias_pro.get(email.strip().lower())
    if not m:
        return (False, None)
    hasta = m.get("hasta")
    try:
        dt = datetime.fromisoformat(hasta) if hasta else None
    except (TypeError, ValueError):
        dt = None
    return (dt is not None and dt > datetime.now(timezone.utc), hasta)


@router.get("/pro/config", dependencies=_APP)
def get_pro_config(pais: str = "PE") -> dict:
    c = _pro_precio_centimos(pais)
    return {"pais": pais, "precio_centimos": c, "precio_soles": c / 100.0}


@router.get("/pro/estado/{email}", dependencies=_APP)
def get_pro_estado(email: str, pais: str = "PE") -> dict:
    activa, hasta = _pro_estado(email)
    c = _pro_precio_centimos(pais)
    return {"email": email, "activa": activa, "hasta": hasta,
            "precio_centimos": c, "precio_soles": c / 100.0}


@router.get("/pro/miembros", dependencies=_APP)
def get_pro_miembros() -> dict:
    """Correos con Pichangol Pro vigente. El APK los usa para pintar la insignia
    PRO en el ranking global (prueba social). Solo correos, sin datos sensibles."""
    return {"emails": stores.pro_emails_activos()}


class ProSuscribirReq(BaseModel):
    email: str
    pais: str = "PE"


@router.post("/pro/suscribir", dependencies=_APP)
def post_pro_suscribir(req: ProSuscribirReq) -> dict:
    """Activa/renueva Pichangol Pro debitando 1 mes de la billetera única del
    jugador (su saldo). Si no le alcanza, devuelve falta_saldo (el APK lo manda a
    recargar). Extiende la vigencia +30 días desde hoy o desde el vencimiento
    vigente (lo que sea mayor), para no perder días al renovar anticipado."""
    email = req.email.strip().lower()
    if not email:
        return {"ok": False, "error": "email_requerido"}
    pais = (req.pais or "PE").upper()
    precio = _pro_precio_centimos(pais)
    saldo = stores.saldo_centimos(email)
    if saldo < precio:
        return {"ok": False, "falta_saldo": True,
                "requerido_centimos": precio, "requerido_soles": precio / 100.0,
                "saldo_centimos": saldo}
    stores.debitar(email, precio)
    ahora_dt = datetime.now(timezone.utc)
    base = ahora_dt
    m = stores.membresias_pro.get(email) or {}
    try:
        cur = datetime.fromisoformat(m["hasta"]) if m.get("hasta") else None
        if cur and cur > base:
            base = cur
    except (KeyError, TypeError, ValueError):
        pass
    hasta = (base + timedelta(days=30)).isoformat()
    stores.membresias_pro[email] = {
        "hasta": hasta, "ultimo_cobro": ahora_dt.isoformat(), "pais": pais}
    stores.registrar_pago(
        tipo="suscripcion_pro", monto_centimos=precio, moneda="PEN",
        estado="aprobado", dueno_id=email, concepto="Pichangol Pro (1 mes)")
    nuevo = stores.saldo_centimos(email)
    return {"ok": True, "hasta": hasta,
            "saldo_centimos": nuevo, "saldo_soles": nuevo / 100.0}


def procesar_renovaciones_pro() -> dict:
    """Renueva las membresías Pro vencidas debitando de la billetera del jugador.
    Sin saldo suficiente → no renueva (queda vencida). La usan el endpoint
    `/pro/renovar-vencidas` y el cron interno."""
    ahora_dt = datetime.now(timezone.utc)
    renovadas, sin_saldo = 0, 0
    for email, m in list(stores.membresias_pro.items()):
        try:
            cur = datetime.fromisoformat(m.get("hasta")) if m.get("hasta") else None
        except (TypeError, ValueError):
            cur = None
        if cur and cur > ahora_dt:
            continue  # aún vigente
        if m.get("cortesia"):
            # Pro de CORTESÍA (marcha blanca): lo regaló el operador, NUNCA se
            # renueva solo debitando la billetera del dueño (ahí está la plata
            # de sus liquidaciones). Vencida la cortesía, simplemente expira;
            # si quiere seguir, se suscribe pagando como cualquier usuario.
            continue
        precio = _pro_precio_centimos(m.get("pais", "PE"))
        if stores.saldo_centimos(email) >= precio:
            stores.debitar(email, precio)
            m["hasta"] = (ahora_dt + timedelta(days=30)).isoformat()
            m["ultimo_cobro"] = ahora_dt.isoformat()
            stores.registrar_pago(
                tipo="suscripcion_pro", monto_centimos=precio, moneda="PEN",
                estado="aprobado", dueno_id=email,
                concepto="Pichangol Pro (renovación)")
            renovadas += 1
        else:
            sin_saldo += 1
    return {"ok": True, "renovadas": renovadas, "sin_saldo": sin_saldo}


@router.post("/pro/renovar-vencidas", dependencies=_ADMIN)
def post_pro_renovar() -> dict:
    """Cron/manual: renueva las membresías Pro vencidas (cobra del saldo)."""
    return procesar_renovaciones_pro()


# ─────────────── PRO DE CORTESÍA (marcha blanca, torre de control) ────────────
class ProCortesiaReq(BaseModel):
    email: str
    dias: int = 90          # 0 = revocar (la membresía vence al instante)
    pais: str = "PE"


@router.post("/pro/cortesia", dependencies=_ADMIN)
def post_pro_cortesia(req: ProCortesiaReq) -> dict:
    """MARCHA BLANCA: el OPERADOR regala Pichangol Pro a un correo por N días,
    sin cobrar nada (canchas aliadas del lanzamiento). La cortesía NUNCA se
    auto-renueva del saldo (ver procesar_renovaciones_pro): al vencer expira y
    el dueño decide si paga. `dias=0` la revoca. Extiende desde el vencimiento
    vigente si es mayor (regalar 2 veces no pisa días)."""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "email_invalido"}
    dias = max(0, min(int(req.dias), 365))
    ahora_dt = datetime.now(timezone.utc)
    if dias == 0:
        stores.membresias_pro.pop(email, None)
        return {"ok": True, "email": email, "revocada": True}
    base = ahora_dt
    m = stores.membresias_pro.get(email) or {}
    try:
        cur = datetime.fromisoformat(m["hasta"]) if m.get("hasta") else None
        if cur and cur > base:
            base = cur
    except (KeyError, TypeError, ValueError):
        pass
    hasta = (base + timedelta(days=dias)).isoformat()
    stores.membresias_pro[email] = {
        "hasta": hasta, "cortesia": True, "pais": (req.pais or "PE").upper()}
    # Registro auditable (monto 0): quién recibió cortesía y cuándo.
    stores.registrar_pago(
        tipo="pro_cortesia", monto_centimos=0, moneda="PEN",
        estado="aprobado", dueno_id=email,
        concepto=f"Pichangol Pro cortesía ({dias} días)")
    return {"ok": True, "email": email, "hasta": hasta, "cortesia": True}


class RegaloSaldoReq(BaseModel):
    email: str
    soles: float


@router.post("/regalo-saldo", dependencies=_ADMIN)
def post_regalo_saldo(req: RegaloSaldoReq) -> dict:
    """El OPERADOR regala saldo PROMOCIONAL manualmente (marcha blanca: p. ej.
    a las canchas aliadas que ya estaban activadas antes de la bienvenida
    automática). Mismo bolsillo que la bienvenida: SOLO cubre comisiones, no se
    liquida ni transfiere. Auditable (pago `bono_bienvenida`) + push 🎁."""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "email_invalido"}
    soles = max(0.0, min(float(req.soles), 1000.0))
    if soles <= 0:
        return {"ok": False, "error": "monto_invalido"}
    cent = _soles_a_centimos(soles)
    total = stores.acreditar_promo(email, cent)
    stores.registrar_pago(
        tipo="bono_bienvenida", monto_centimos=cent, moneda="PEN",
        estado="aprobado", dueno_id=email,
        concepto="Regalo de saldo (cubre tus comisiones)")
    _aviso_push_usuario(
        email, "🎁 Te regalamos saldo",
        f"Pichangol te regaló S/ {soles:.2f} de saldo: tus comisiones se "
        "descuentan de ahí primero, sin tocar tu plata.")
    return {"ok": True, "email": email, "saldo_promo_centimos": total,
            "saldo_promo_soles": total / 100.0}


def otorgar_bienvenida(email: str) -> dict:
    """BIENVENIDA automática de la marcha blanca: cuando a un dueño NUEVO se le
    ACTIVA su primera cancha, recibe lo configurado en la torre — días de Pro de
    cortesía y/o un saldo de REGALO que solo absorbe comisiones. Idempotente
    (un regalo por correo, aunque registre varias canchas). Con la config en 0
    no hace nada. La llama el flujo de reclamos al activar."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "email_invalido"}

    def _num(clave: str) -> float:
        try:
            return float(stores.cfg(clave) or 0)
        except (TypeError, ValueError):
            return 0.0

    dias = int(_num("bienvenida_pro_dias"))
    saldo_soles = _num("bienvenida_saldo_soles")
    if dias <= 0 and saldo_soles <= 0:
        return {"ok": False, "apagada": True}
    if email in stores.bienvenidas:
        return {"ok": False, "ya_otorgada": True}
    ahora_dt = datetime.now(timezone.utc)
    stores.bienvenidas[email] = ahora_dt.isoformat()
    partes = []
    if dias > 0:
        base = ahora_dt
        m = stores.membresias_pro.get(email) or {}
        try:
            cur = datetime.fromisoformat(m["hasta"]) if m.get("hasta") else None
            if cur and cur > base:
                base = cur
        except (KeyError, TypeError, ValueError):
            pass
        stores.membresias_pro[email] = {
            "hasta": (base + timedelta(days=dias)).isoformat(),
            "cortesia": True, "pais": "PE"}
        partes.append(f"{dias} días de Pichangol Pro")
    if saldo_soles > 0:
        cent = _soles_a_centimos(saldo_soles)
        stores.acreditar_promo(email, cent)
        stores.registrar_pago(
            tipo="bono_bienvenida", monto_centimos=cent, moneda="PEN",
            estado="aprobado", dueno_id=email,
            concepto="Regalo de bienvenida (cubre tus comisiones)")
        partes.append(f"S/ {saldo_soles:.0f} de saldo de regalo para "
                      "tus comisiones")
    _aviso_push_usuario(
        email, "🎁 ¡Bienvenido a Pichangol!",
        "Por activar tu cancha te regalamos " + " y ".join(partes) +
        ". Ya está en tu cuenta.")
    return {"ok": True, "email": email, "pro_dias": dias,
            "saldo_soles": saldo_soles}


@router.get("/pro/miembros-admin", dependencies=_ADMIN)
def get_pro_miembros_admin() -> dict:
    """Detalle de TODAS las membresías Pro para la torre: correo, vencimiento,
    si es cortesía y si sigue vigente."""
    ahora_dt = datetime.now(timezone.utc)
    filas = []
    for email, m in sorted(stores.membresias_pro.items()):
        hasta = m.get("hasta")
        try:
            dt = datetime.fromisoformat(hasta) if hasta else None
        except (TypeError, ValueError):
            dt = None
        filas.append({
            "email": email,
            "hasta": hasta,
            "cortesia": bool(m.get("cortesia")),
            "pais": m.get("pais", "PE"),
            "vigente": dt is not None and dt > ahora_dt,
        })
    return {"miembros": filas}


# ─────────────────────── INSCRIPCIÓN A TORNEO (billetera única) ───────────────
class TorneoInscribirReq(BaseModel):
    email: str                 # jugador que paga (de su saldo)
    academia_dueno: str        # correo del profe (recibe el neto en su billetera)
    cuota_soles: float
    concepto: str = ""


@router.post("/torneo/inscribir", dependencies=_APP)
def post_torneo_inscribir(req: TorneoInscribirReq) -> dict:
    """Cobra la inscripción a un torneo del SALDO del jugador (billetera única) y
    acredita el NETO al profe (menos la comisión POS). Si no le alcanza, devuelve
    falta_saldo (el APK lo manda a recargar). Movimiento interno saldo→saldo."""
    email = req.email.strip().lower()
    dueno = req.academia_dueno.strip().lower()
    if not email:
        return {"ok": False, "error": "email_requerido"}
    cuota = _soles_a_centimos(req.cuota_soles)
    if cuota <= 0:
        return {"ok": False, "error": "cuota_invalida"}
    if stores.saldo_centimos(email) < cuota:
        return {"ok": False, "falta_saldo": True,
                "requerido_centimos": cuota, "requerido_soles": cuota / 100.0,
                "saldo_centimos": stores.saldo_centimos(email)}
    comision = comision_centimos(req.cuota_soles)
    neto = max(0, cuota - comision)
    stores.debitar(email, cuota)
    # Débito del JUGADOR (aparece en su historial de billetera como egreso).
    stores.registrar_pago(
        tipo="inscripcion_torneo", monto_centimos=cuota, moneda="PEN",
        estado="aprobado", dueno_id=email,
        concepto=req.concepto or "Inscripción a torneo")
    # Ingreso NETO del profe (su historial lo ve como entrada).
    if dueno and dueno != email:
        stores.acreditar(dueno, neto)
        stores.registrar_pago(
            tipo="inscripcion_torneo_ingreso", monto_centimos=cuota, moneda="PEN",
            estado="aprobado", dueno_id=dueno, comision_centimos=comision,
            concepto=req.concepto or "Inscripción a torneo (ingreso)")
    return {"ok": True, "cuota_centimos": cuota, "comision_centimos": comision,
            "neto_centimos": neto,
            "saldo_centimos": stores.saldo_centimos(email),
            "saldo_soles": stores.saldo_centimos(email) / 100.0}


@router.post("/comision-reserva", dependencies=_APP)
def post_comision_reserva(req: ComisionReservaReq) -> dict:
    """Descuenta la comisión de Pichangol del SALDO del dueño cuando entra una
    reserva pagada EN EFECTIVO (el jugador paga la cancha; PCG cobra su comisión
    del saldo prepago del dueño). Es la contraparte de que el efectivo solo se
    ofrece al jugador si el dueño tiene saldo. Idempotente por `reserva_id`: no
    cobra dos veces la misma reserva."""
    # Sale del saldo → aplica la tarifa configurable de billetera (torre).
    comision = comision_saldo_centimos(req.monto_soles)
    # Idempotencia: si esta reserva ya generó comisión, no la cobres de nuevo.
    ya = stores.pago_por_charge(req.reserva_id)
    if ya is not None and ya.tipo == "comision_reserva":
        c = stores.saldo_centimos(req.dueno_id)
        return {"ok": True, "duplicada": True,
                "comision_centimos": ya.monto_centimos,
                "saldo_centimos": c, "saldo_soles": c / 100.0}
    # El REGALO de bienvenida absorbe la comisión primero (marcha blanca): el
    # dueño no toca su plata hasta agotar el regalo.
    promo_usado, nuevo = stores.debitar_comision(req.dueno_id, comision)
    sufijo = (" · cubierta por tu saldo de regalo 🎁" if promo_usado >= comision
              and comision > 0 else
              f" · S/ {promo_usado / 100.0:.2f} de tu regalo 🎁"
              if promo_usado > 0 else "")
    stores.registrar_pago(
        tipo="comision_reserva", monto_centimos=comision, moneda="PEN",
        estado="aprobado", dueno_id=req.dueno_id,
        culqi_charge_id=req.reserva_id,
        concepto=(req.concepto or "Comisión de reserva") + sufijo)
    return {"ok": True, "duplicada": False, "comision_centimos": comision,
            "promo_usado_centimos": promo_usado,
            "saldo_centimos": nuevo, "saldo_soles": nuevo / 100.0}


@router.post("/liquidacion-online", dependencies=_APP)
def post_liquidacion_online(req: LiquidacionOnlineReq) -> dict:
    """Reserva pagada ONLINE, modelo **BILLETERA-FIRST**:

    - Si el dueño tiene SALDO suficiente: la comisión sale de su **billetera
      prepago** (movimiento `comision_reserva`, saldo −) y el dueño recibe el
      **BRUTO completo** por recibir (`liquidacion_full`, neto = bruto). Así la
      billetera es la fuente de la comisión y el dueño cobra el 100%.
    - Si NO le alcanza el saldo: fallback → la comisión se toma de la
      **transacción** (neto por recibir, `liquidacion_online`) y se avisa que
      recargue (`requiere_recarga`).

    Idempotente por `reserva_id`."""
    bruto = _soles_a_centimos(req.monto_soles)
    comision = comision_centimos(req.monto_soles)
    # Tarifa de BILLETERA (configurable en la torre, puede ser menor): es la que
    # aplica cuando la comisión sale del saldo.
    com_saldo = comision_saldo_centimos(req.monto_soles)
    ya = stores.pago_por_charge(req.reserva_id)
    if ya is not None and ya.tipo in ("liquidacion_online", "liquidacion_full"):
        d = _liquidacion_dict(ya)
        return {"ok": True, "duplicada": True,
                "fuente": "saldo" if ya.tipo == "liquidacion_full"
                else "transaccion",
                "bruto_centimos": ya.monto_centimos,
                "comision_centimos": round(d["comision_soles"] * 100),
                "neto_centimos": round(d["neto_soles"] * 100)}

    saldo = stores.saldo_centimos(req.dueno_id)
    promo = stores.saldo_promo_centimos(req.dueno_id)
    if saldo + promo >= com_saldo:
        # BILLETERA-FIRST: comisión del saldo (el REGALO de bienvenida primero);
        # el dueño recibe el bruto completo.
        promo_usado, nuevo = stores.debitar_comision(req.dueno_id, com_saldo)
        sufijo = (" · cubierta por tu saldo de regalo 🎁"
                  if promo_usado >= com_saldo and com_saldo > 0 else
                  f" · S/ {promo_usado / 100.0:.2f} de tu regalo 🎁"
                  if promo_usado > 0 else "")
        stores.registrar_pago(
            tipo="comision_reserva", monto_centimos=com_saldo, moneda="PEN",
            estado="aprobado", dueno_id=req.dueno_id,
            culqi_charge_id=f"{req.reserva_id}_com",
            concepto=f"Comisión · {req.concepto or 'Reserva online'}{sufijo}")
        stores.registrar_pago(
            tipo="liquidacion_full", monto_centimos=bruto, moneda="PEN",
            estado="aprobado", dueno_id=req.dueno_id,
            culqi_charge_id=req.reserva_id,
            concepto=req.concepto or "Reserva online",
            medio=req.medio.strip() or None)
        return {"ok": True, "duplicada": False, "fuente": "saldo",
                "bruto_centimos": bruto, "comision_centimos": com_saldo,
                "neto_centimos": bruto, "saldo_centimos": nuevo,
                "saldo_soles": nuevo / 100.0}

    # Sin saldo suficiente → comisión de la transacción (neto), como antes.
    stores.registrar_pago(
        tipo="liquidacion_online", monto_centimos=bruto, moneda="PEN",
        estado="aprobado", dueno_id=req.dueno_id,
        culqi_charge_id=req.reserva_id,
        concepto=req.concepto or "Reserva online",
        medio=req.medio.strip() or None)
    return {"ok": True, "duplicada": False, "fuente": "transaccion",
            "requiere_recarga": True, "bruto_centimos": bruto,
            "comision_centimos": comision, "neto_centimos": bruto - comision}


@router.post("/venta", dependencies=_APP)
def post_venta(req: VentaProductoReq) -> dict:
    """MARKETPLACE: registra una VENTA de producto pagada online. El comprador ya
    le pagó a Pichangol (Culqi, vía /pagos/cobrar); aquí se descuenta la comisión
    y el NETO queda como "por recibir" del vendedor (misma contabilidad que una
    reserva online). Idempotente por `venta_id`."""
    from db.store import Venta, ahora  # local para no ensuciar el import global

    bruto = _soles_a_centimos(req.monto_soles)
    comision = comision_centimos(req.monto_soles)
    ya = stores.pago_por_charge(req.venta_id)
    if ya is not None and ya.tipo == "venta_producto":
        com = comision_centimos(ya.monto_centimos / 100.0)
        return {"ok": True, "duplicada": True, "bruto_centimos": ya.monto_centimos,
                "comision_centimos": com, "neto_centimos": ya.monto_centimos - com}
    stores.registrar_pago(
        tipo="venta_producto", monto_centimos=bruto, moneda="PEN",
        estado="aprobado", dueno_id=req.vendedor_id,
        culqi_charge_id=req.venta_id,
        concepto=req.concepto or "Venta de producto (marketplace)")
    # Crea la ORDEN (escrow): retenida hasta que el comprador confirme recepción.
    stores.ventas.append(Venta(
        id=stores.next_id("venta"),
        producto_id=req.producto_id,
        producto_nombre=req.producto_nombre or (req.concepto or "Producto"),
        comprador_email=req.comprador_email.strip().lower(),
        comprador_nombre=req.comprador_nombre.strip(),
        vendedor_email=req.vendedor_id.strip().lower(),
        vendedor_nombre=req.vendedor_nombre.strip(),
        monto_soles=req.monto_soles,
        creado_en=ahora(), estado="pagado"))
    return {"ok": True, "duplicada": False, "bruto_centimos": bruto,
            "comision_centimos": comision, "neto_centimos": bruto - comision}


# ------ Servicios de marketing (landing/redes): SUSCRIPCIÓN recurrente --------
# Se debita del mismo saldo prepago del dueño (Culqi). Precios editables en la
# torre de control (config). Catálogo:
_SERVICIOS = {
    "landing": ("Landing web", "servicio_landing_soles",
                "Tu página web para difundir la academia/cancha."),
    "redes": ("Manejo de redes", "servicio_redes_soles",
              "Community manager con IA: creamos tu contenido y lo publicamos en "
              "tu Instagram/Facebook si conectas tus cuentas (o lo compartes con "
              "un tap)."),
    "presencia": ("Presencia digital", "servicio_presencia_soles",
                  "Landing + manejo de redes, todo incluido."),
}

# Servicios RETIRADOS del catálogo pero reconocidos para mostrar suscripciones
# antiguas: "Gestión de redes" se unificó dentro de "Manejo de redes".
_SERVICIOS_LEGACY = {"gestion": "Manejo de redes"}


def _nombre_servicio(clave: str) -> str:
    if clave in _SERVICIOS:
        return _SERVICIOS[clave][0]
    return _SERVICIOS_LEGACY.get(clave, "?")


# "Presencia digital" es un PAQUETE que engloba landing + manejo de redes.
INCLUYE_SERVICIOS = {"presencia": ("landing", "redes")}


def _plan_mayor_activo(academia_id: str, servicio: str) -> str | None:
    """Devuelve el plan MAYOR activo de la academia que ya incluye `servicio`
    (p.ej. 'presencia' incluye 'landing'), o None."""
    for s in stores.suscripciones.values():
        if s.get("academia_id") != academia_id:
            continue
        if s.get("estado") not in ("activa", "pendiente_pago"):
            continue
        if servicio in INCLUYE_SERVICIOS.get(s.get("servicio"), ()):
            return s.get("servicio")
    return None


def _servicio_soles(clave: str, tipo: str | None = None) -> float:
    """Precio mensual del servicio. Con `tipo='club'` usa el override por tipo si
    está configurado (>0); si no, cae al precio base (academia). El negocio
    unificado ('mixto') usa el precio base."""
    try:
        base = float(stores.cfg(_SERVICIOS[clave][1]))
    except (KeyError, TypeError, ValueError):
        return 0.0
    if tipo == "club":
        try:
            override = stores.cfg(f"{_SERVICIOS[clave][1]}_club").strip()
            if override:
                v = float(override)
                if v > 0:
                    return v
        except (KeyError, TypeError, ValueError):
            pass
    return base


def _mas_un_mes(d: datetime) -> datetime:
    """Fecha + 1 mes (día tope 28 para no desbordar en meses cortos)."""
    m = d.month + 1
    y = d.year + (1 if m > 12 else 0)
    m = m - 12 if m > 12 else m
    return d.replace(year=y, month=m, day=min(d.day, 28))


def _sub_dict(s: dict) -> dict:
    serv = s.get("servicio")
    return {
        "academia_id": s.get("academia_id"),
        "servicio": serv,
        "nombre": _nombre_servicio(serv),
        "monto_soles": s.get("monto_centimos", 0) / 100.0,
        "estado": s.get("estado"),
        "proximo_cobro": s.get("proximo_cobro"),
        "ultimo_cobro": s.get("ultimo_cobro"),
    }


class ContratarServicioReq(BaseModel):
    dueno_id: str
    academia_id: str
    servicio: str
    tipo: str | None = None  # 'academia' | 'club' | 'mixto' (Fase 3: precio por tipo)


class CancelarServicioReq(BaseModel):
    academia_id: str
    servicio: str


@router.get("/servicios/planes")
def get_servicios_planes(tipo: str | None = None) -> dict:
    """Catálogo de servicios de marketing con su precio mensual (público). Con
    `tipo=club` devuelve la tarifa del club si la torre de control la configuró;
    academia/mixto usan la tarifa base."""
    return {"planes": [
        {"clave": k, "nombre": nom, "desc": desc,
         "soles": _servicio_soles(k, tipo)}
        for k, (nom, _cfg, desc) in _SERVICIOS.items()
    ]}


@router.post("/servicios/contratar", dependencies=_APP)
def post_contratar_servicio(req: ContratarServicioReq) -> dict:
    """Contrata un servicio: cobra el 1.er mes del SALDO del dueño y deja la
    suscripción activa con su próximo cobro. Si no hay saldo, devuelve
    falta_saldo (el APK lo manda a recargar)."""
    if req.servicio not in _SERVICIOS:
        raise HTTPException(status_code=400, detail="servicio_invalido")
    # Ya cubierto por un plan mayor (p.ej. Presencia incluye Landing/Manejo):
    # no se cobra de nuevo.
    mayor = _plan_mayor_activo(req.academia_id, req.servicio)
    if mayor:
        return {"ok": False, "incluido": True, "por": mayor,
                "nombre_por": _nombre_servicio(mayor)}
    monto = _soles_a_centimos(_servicio_soles(req.servicio, req.tipo))
    saldo = stores.saldo_centimos(req.dueno_id)
    if saldo < monto:
        return {"ok": False, "falta_saldo": True, "requerido_centimos": monto,
                "requerido_soles": monto / 100.0,
                "saldo_centimos": saldo, "saldo_soles": saldo / 100.0}
    nuevo = stores.debitar(req.dueno_id, monto)
    ahora = datetime.now(timezone.utc)
    clave = f"{req.academia_id}:{req.servicio}"
    stores.suscripciones[clave] = {
        "academia_id": req.academia_id, "dueno_id": req.dueno_id,
        "servicio": req.servicio, "monto_centimos": monto, "estado": "activa",
        "creado_en": ahora.isoformat(), "ultimo_cobro": ahora.isoformat(),
        "proximo_cobro": _mas_un_mes(ahora).isoformat(),
    }
    stores.registrar_pago(
        tipo="suscripcion", monto_centimos=monto, moneda="PEN",
        estado="aprobado", dueno_id=req.dueno_id,
        concepto=f"Suscripción {req.servicio} · {req.academia_id}")
    # Al contratar un PAQUETE (Presencia), cancela los planes que engloba para
    # que no haya doble cobro.
    canceladas = []
    for incl in INCLUYE_SERVICIOS.get(req.servicio, ()):
        s = stores.suscripciones.get(f"{req.academia_id}:{incl}")
        if s and s.get("estado") in ("activa", "pendiente_pago"):
            s["estado"] = "cancelada"
            canceladas.append(incl)
    return {"ok": True, "suscripcion": _sub_dict(stores.suscripciones[clave]),
            "reemplaza": canceladas,
            "saldo_centimos": nuevo, "saldo_soles": nuevo / 100.0}


@router.post("/servicios/cancelar", dependencies=_APP)
def post_cancelar_servicio(req: CancelarServicioReq) -> dict:
    """Cancela la renovación (no reembolsa el mes en curso)."""
    s = stores.suscripciones.get(f"{req.academia_id}:{req.servicio}")
    if not s:
        return {"ok": False, "error": "no_existe"}
    s["estado"] = "cancelada"
    return {"ok": True, "suscripcion": _sub_dict(s)}


@router.get("/servicios/estado/{academia_id}", dependencies=_APP)
def get_servicios_estado(academia_id: str) -> dict:
    """Suscripciones de una academia (para el panel del dueño)."""
    subs = [_sub_dict(s) for s in stores.suscripciones.values()
            if s.get("academia_id") == academia_id]
    return {"academia_id": academia_id, "suscripciones": subs}


@router.get("/servicios/todas", dependencies=_ADMIN)
def get_servicios_todas() -> dict:
    """Todas las suscripciones + MRR (para la torre de control)."""
    subs = [_sub_dict(s) for s in stores.suscripciones.values()]
    activas = [s for s in subs if s["estado"] == "activa"]
    return {"suscripciones": subs, "activas": len(activas),
            "mrr_soles": round(sum(s["monto_soles"] for s in activas), 2)}


def _renovar_ok(s: dict, ahora: datetime) -> None:
    s["ultimo_cobro"] = ahora.isoformat()
    s["proximo_cobro"] = _mas_un_mes(ahora).isoformat()
    s["estado"] = "activa"


def procesar_renovaciones() -> dict:
    """Renueva las suscripciones vencidas. Orden de cobro:
    1) SALDO prepago del dueño; 2) si no alcanza, la TARJETA de débito automático
    guardada de la academia (Culqi). Si ninguna funciona → 'pendiente_pago'.
    La usan el endpoint /servicios/cobrar-vencidas y el cron interno."""
    ahora = datetime.now(timezone.utc)
    cobradas = por_tarjeta = pendientes = 0
    for s in stores.suscripciones.values():
        if s.get("estado") not in ("activa", "pendiente_pago"):
            continue
        prox = s.get("proximo_cobro")
        try:
            venc = datetime.fromisoformat(prox) if prox else None
        except (TypeError, ValueError):
            venc = None
        if venc is not None and venc > ahora:
            continue
        monto = s.get("monto_centimos", 0)
        aca = s.get("academia_id")
        concepto = f"Suscripción {s['servicio']} · {aca}"
        # 1) Saldo prepago.
        if stores.saldo_centimos(s["dueno_id"]) >= monto:
            stores.debitar(s["dueno_id"], monto)
            stores.registrar_pago(
                tipo="suscripcion", monto_centimos=monto, moneda="PEN",
                estado="aprobado", dueno_id=s["dueno_id"], concepto=concepto)
            _renovar_ok(s, ahora)
            cobradas += 1
            continue
        # 2) Tarjeta de débito automático guardada.
        metodo = stores.metodo_suscripcion.get(aca)
        if metodo and metodo.get("card_id") and culqi.disponible():
            r = culqi.crear_cargo(
                token=metodo["card_id"], monto_centimos=monto,
                email=metodo.get("email") or "", descripcion=concepto,
                metadata={"tipo": "suscripcion", "academia_id": aca})
            if r.get("ok"):
                stores.registrar_pago(
                    tipo="suscripcion", monto_centimos=monto, moneda="PEN",
                    estado="aprobado", dueno_id=s["dueno_id"],
                    culqi_charge_id=r.get("charge_id"),
                    concepto=concepto + " (tarjeta)")
                _renovar_ok(s, ahora)
                por_tarjeta += 1
                continue
        s["estado"] = "pendiente_pago"
        pendientes += 1
    return {"ok": True, "cobradas": cobradas, "por_tarjeta": por_tarjeta,
            "pendientes": pendientes}


@router.post("/servicios/cobrar-vencidas", dependencies=_ADMIN)
def post_cobrar_vencidas() -> dict:
    """Dispara la renovación de suscripciones vencidas (torre de control). El cron
    interno hace lo mismo automáticamente."""
    return procesar_renovaciones()


class MetodoSuscripcionReq(BaseModel):
    academia_id: str
    token: str                 # tkn_ (tarjeta tokenizada en el APK)
    email: str
    nombre: str = ""
    apellido: str = ""


def _metodo_sus_publico(m: dict | None) -> dict:
    if not m:
        return {"tiene_tarjeta": False}
    return {"tiene_tarjeta": True, "marca": m.get("marca"),
            "ultimos4": m.get("ultimos4")}


@router.get("/servicios/metodo/{academia_id}", dependencies=_APP)
def get_metodo_suscripcion(academia_id: str) -> dict:
    """¿La academia tiene tarjeta de débito automático? (enmascarada)."""
    return _metodo_sus_publico(stores.metodo_suscripcion.get(academia_id))


@router.post("/servicios/metodo", dependencies=_APP)
def set_metodo_suscripcion(req: MetodoSuscripcionReq) -> dict:
    """Guarda la tarjeta de débito automático de una academia (Culqi One-Click):
    crea/reusa el customer, convierte el token en tarjeta permanente (crd_) y la
    guarda con el email para cobrarla en cada renovación."""
    if not culqi.disponible():
        raise HTTPException(status_code=503, detail="pagos_no_configurados")
    key = f"aca:{req.academia_id}"
    cus = stores.customers.get(key)
    if not cus:
        rc = culqi.crear_customer(email=req.email, nombre=req.nombre,
                                  apellido=req.apellido)
        if not rc["ok"]:
            return {"ok": False, "error": rc.get("error", "no_se_pudo_crear_cliente")}
        cus = rc["customer_id"]
        stores.customers[key] = cus
    rcard = culqi.crear_card(customer_id=cus, token=req.token)
    if not rcard["ok"]:
        return {"ok": False, "error": rcard.get("error", "no_se_pudo_guardar_tarjeta")}
    stores.metodo_suscripcion[req.academia_id] = {
        "card_id": rcard["card_id"], "email": req.email,
        "marca": rcard["marca"], "ultimos4": rcard["ultimos4"]}
    return {"ok": True, **_metodo_sus_publico(stores.metodo_suscripcion[req.academia_id])}


@router.delete("/servicios/metodo/{academia_id}", dependencies=_APP)
def del_metodo_suscripcion(academia_id: str) -> dict:
    m = stores.metodo_suscripcion.pop(academia_id, None)
    if m and m.get("card_id"):
        culqi.eliminar_card(m["card_id"])  # best-effort
    return {"ok": True}


# ── Suscripción MENSUAL del ALUMNO (pago "mes a mes") ──────────────────────────
class SuscripcionAlumnoReq(BaseModel):
    alumno_id: str
    academia_id: str
    email: str
    token: str                 # tkn_ tokenizado en el APK (tarjeta del alumno)
    monto_soles: float         # mensualidad
    nombre: str = ""
    apellido: str = ""
    pais: str = "pe"
    concepto: str | None = None
    # Cobros AUTOMÁTICOS restantes (meses comprometidos menos el 1.º ya pagado).
    # None = indefinido (cobra hasta que el alumno cancele).
    cobros_restantes: int | None = None


def _suscripcion_alumno_publica(s: dict | None) -> dict:
    if not s:
        return {"activa": False}
    return {
        "activa": s.get("estado") == "activa",
        "estado": s.get("estado"),
        "monto_soles": s.get("monto_centimos", 0) / 100.0,
        "proximo_cobro": s.get("proximo_cobro"),
        "marca": s.get("marca"), "ultimos4": s.get("ultimos4"),
        # Cobros AUTOMÁTICOS ya realizados (sin contar el 1.er mes del signup).
        # La app lo usa para RECONCILIAR: marcar pagadas las cuotas cobradas.
        "cobros_hechos": int(s.get("cobros_hechos", 0)),
    }


@router.get("/matricula/suscripcion/{alumno_id}", dependencies=_APP)
def get_suscripcion_alumno(alumno_id: str) -> dict:
    """Estado de la suscripción mensual del alumno (enmascarada, sin tarjeta)."""
    return _suscripcion_alumno_publica(stores.suscripciones_alumno.get(alumno_id))


@router.post("/matricula/suscripcion", dependencies=_APP)
def post_suscripcion_alumno(req: SuscripcionAlumnoReq) -> dict:
    """Crea la suscripción MENSUAL del alumno (pago mes a mes): guarda su tarjeta
    (Culqi One-Click) y programa el próximo cobro a un mes. El 1.er mes lo cobró el
    APK aparte (con /matricula). El cron cobra los meses siguientes."""
    if not culqi.disponible():
        raise HTTPException(status_code=503, detail="pagos_no_configurados")
    # El token puede venir como tarjeta guardada (crd_) —se usa tal cual— o como
    # token temporal (tkn_) que hay que convertir en tarjeta permanente (crd_).
    if req.token.startswith("crd_"):
        card_id, marca, ultimos4 = req.token, "", ""
    else:
        key = f"al:{req.alumno_id}"
        cus = stores.customers.get(key)
        if not cus:
            rc = culqi.crear_customer(email=req.email, nombre=req.nombre,
                                      apellido=req.apellido)
            if not rc["ok"]:
                return {"ok": False, "error": rc.get("error", "no_se_pudo_crear_cliente")}
            cus = rc["customer_id"]
            stores.customers[key] = cus
        rcard = culqi.crear_card(customer_id=cus, token=req.token)
        if not rcard["ok"]:
            return {"ok": False, "error": rcard.get("error", "no_se_pudo_guardar_tarjeta")}
        card_id, marca, ultimos4 = rcard["card_id"], rcard["marca"], rcard["ultimos4"]
    ahora = datetime.now(timezone.utc)
    stores.suscripciones_alumno[req.alumno_id] = {
        "alumno_id": req.alumno_id, "academia_id": req.academia_id,
        "email": req.email, "card_id": card_id,
        "marca": marca, "ultimos4": ultimos4,
        "monto_centimos": _soles_a_centimos(req.monto_soles),
        "pais": req.pais, "estado": "activa",
        "concepto": req.concepto or "Mensualidad (mes a mes)",
        "creado_en": ahora.isoformat(),
        "proximo_cobro": _mas_un_mes(ahora).isoformat(),
        "cobros_restantes": req.cobros_restantes,
        "cobros_hechos": 0,
    }
    return {"ok": True, **_suscripcion_alumno_publica(
        stores.suscripciones_alumno[req.alumno_id])}


@router.delete("/matricula/suscripcion/{alumno_id}", dependencies=_APP)
def del_suscripcion_alumno(alumno_id: str) -> dict:
    """Cancela la suscripción mensual del alumno (deja de cobrar cada mes)."""
    s = stores.suscripciones_alumno.pop(alumno_id, None)
    if s and s.get("card_id"):
        culqi.eliminar_card(s["card_id"])  # best-effort
    return {"ok": True}


def procesar_renovaciones_alumnos() -> dict:
    """Cobra las MENSUALIDADES vencidas (alumnos con pago mes a mes) contra su
    tarjeta guardada (Culqi) y acredita el neto (menos comisión POS del país) a la
    academia como 'por recibir'. Fail-safe. La usa el cron interno."""
    ahora = datetime.now(timezone.utc)
    cobradas = pendientes = 0
    for s in stores.suscripciones_alumno.values():
        if s.get("estado") not in ("activa", "pendiente_pago"):
            continue
        prox = s.get("proximo_cobro")
        try:
            venc = datetime.fromisoformat(prox) if prox else None
        except (TypeError, ValueError):
            venc = None
        if venc is not None and venc > ahora:
            continue
        if not culqi.disponible() or not s.get("card_id"):
            s["estado"] = "pendiente_pago"
            pendientes += 1
            continue
        monto = s.get("monto_centimos", 0)
        aca = s.get("academia_id")
        concepto = s.get("concepto") or "Mensualidad"
        r = culqi.crear_cargo(
            token=s["card_id"], monto_centimos=monto,
            email=s.get("email") or "", descripcion=concepto,
            metadata={"tipo": "mensualidad_alumno", "academia_id": aca,
                      "alumno_id": s.get("alumno_id")})
        if r.get("ok"):
            pct = _comision_matricula_pct(s.get("pais"))
            comision = int(round(monto * pct / 100.0))
            stores.registrar_pago(
                tipo="matricula_online", monto_centimos=monto, moneda="PEN",
                estado="aprobado", dueno_id=aca,
                culqi_charge_id=r.get("charge_id"), comision_centimos=comision,
                concepto=concepto + " (mes a mes)")
            s["ultimo_cobro"] = ahora.isoformat()
            s["proximo_cobro"] = _mas_un_mes(ahora).isoformat()
            s["cobros_hechos"] = int(s.get("cobros_hechos", 0)) + 1
            # Descuenta los cobros comprometidos; al llegar a 0, se completa
            # (deja de cobrar). None = indefinido (sigue hasta cancelar).
            rest = s.get("cobros_restantes")
            if rest is not None:
                rest = int(rest) - 1
                s["cobros_restantes"] = rest
                s["estado"] = "completada" if rest <= 0 else "activa"
            else:
                s["estado"] = "activa"
            cobradas += 1
        else:
            s["estado"] = "pendiente_pago"
            pendientes += 1
    return {"ok": True, "cobradas": cobradas, "pendientes": pendientes}


@router.post("/matricula/cobrar-vencidas", dependencies=_ADMIN)
def post_cobrar_mensualidades() -> dict:
    """Dispara el cobro de mensualidades vencidas (torre de control). El cron
    interno hace lo mismo automáticamente."""
    return procesar_renovaciones_alumnos()


# ------ Comisión por COBRO DIGITAL de matrícula (tarifa "tipo POS") ----------
# El alumno paga el precio limpio por la app; la academia absorbe una comisión
# única por país (editable en la torre de control). Efectivo = 0% (no pasa por
# aquí). El NETO (bruto − comisión) queda como "por recibir" de la academia.
_PAISES_COMISION = ("pe", "ec", "bo")


def _comision_matricula_pct(pais: str | None) -> float:
    iso = (pais or "pe").strip().lower()
    if iso not in _PAISES_COMISION:
        iso = "pe"
    try:
        return max(0.0, float(stores.cfg(f"comision_matricula_pct_{iso}")))
    except (TypeError, ValueError):
        return 0.0


class MatriculaReq(BaseModel):
    academia_id: str          # la academia (su billetera/“por recibir”)
    monto_soles: float        # lo que pagó el alumno (precio limpio)
    matricula_id: str         # idempotencia: no registrar 2 veces
    pais: str = "pe"
    concepto: str | None = None


@router.get("/comision-matricula")
def get_comision_matricula(pais: str = "pe") -> dict:
    """Tarifa (%) por cobro digital de matrícula para un país. Público: el APK la
    muestra al profe ('es como tu POS'). Efectivo = 0%."""
    return {"pais": pais, "pct": _comision_matricula_pct(pais)}


@router.post("/matricula", dependencies=_APP)
def post_matricula(req: MatriculaReq) -> dict:
    """Registra un cobro digital de matrícula: congela la comisión del país y deja
    el NETO como 'por recibir' de la academia. Idempotente por matricula_id. El
    alumno ya pagó el bruto a Pichangol (Culqi); esto es la contabilidad del neto
    que se le debe a la academia."""
    bruto = _soles_a_centimos(req.monto_soles)
    pct = _comision_matricula_pct(req.pais)
    comision = int(round(bruto * pct / 100.0))
    ya = stores.pago_por_charge(req.matricula_id)
    if ya is not None and ya.tipo == "matricula_online":
        return {"ok": True, "duplicada": True, "bruto_centimos": ya.monto_centimos,
                "comision_centimos": ya.comision_centimos,
                "neto_centimos": ya.monto_centimos - ya.comision_centimos,
                "pct": pct}
    stores.registrar_pago(
        tipo="matricula_online", monto_centimos=bruto, moneda="PEN",
        estado="aprobado", dueno_id=req.academia_id,
        culqi_charge_id=req.matricula_id, comision_centimos=comision,
        concepto=req.concepto or "Matrícula (cobro digital)")
    return {"ok": True, "duplicada": False, "bruto_centimos": bruto,
            "comision_centimos": comision, "neto_centimos": bruto - comision,
            "pct": pct}


def _parse_utc(s: str | None) -> datetime | None:
    """Parsea una fecha ISO (query param) a UTC-aware para comparar con
    creado_en. Si no trae zona, asume UTC. Devuelve None si no se puede."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    except ValueError:
        return None


@router.get("/matricula/resumen/{academia_id}", dependencies=_APP)
def get_matricula_resumen(academia_id: str, desde: str | None = None,
                          hasta: str | None = None) -> dict:
    """Resumen de cobros digitales de matrícula de una academia (para el reporte
    del profe): bruto, comisión y neto acumulados por cobro por la app. Con
    [desde]/[hasta] (ISO) filtra por fecha del cobro, para que cuadre con el
    período que muestran las tarjetas de arriba (Este mes / Mes pasado / …)."""
    d0, d1 = _parse_utc(desde), _parse_utc(hasta)
    ms = [p for p in stores.pagos
          if p.tipo == "matricula_online" and p.dueno_id == academia_id
          and (d0 is None or p.creado_en >= d0)
          and (d1 is None or p.creado_en <= d1)]
    bruto = sum(p.monto_centimos for p in ms)
    comision = sum(p.comision_centimos for p in ms)
    return {"academia_id": academia_id, "cobros": len(ms),
            "bruto_soles": bruto / 100.0, "comision_soles": comision / 100.0,
            "neto_soles": (bruto - comision) / 100.0}


def _liquidacion_dict(p) -> dict:
    """Serializa una liquidación con su desglose y estado de pago."""
    bruto = p.monto_centimos
    # 'liquidacion_full' (billetera-first): la comisión ya salió del SALDO del
    # dueño → neto = bruto. 'venta_bodega' (pago con saldo): SIN comisión por
    # decisión de producto (la bodega es cero comisión) → usa la congelada (0).
    comision = (p.comision_centimos
                if p.tipo in ("liquidacion_full", "venta_bodega")
                else comision_centimos(bruto / 100.0))
    neto = bruto - comision
    return {
        "reserva_id": p.culqi_charge_id,
        "dueno_id": p.dueno_id,
        "concepto": p.concepto or "Reserva online",
        "creado_en": p.creado_en.isoformat(),
        "bruto_soles": bruto / 100.0,
        "comision_soles": comision / 100.0,
        "neto_soles": neto / 100.0,
        "liquidado": p.liquidado,
        "liquidado_en": p.liquidado_en.isoformat() if p.liquidado_en else None,
        "metodo_liquidacion": p.metodo_liquidacion,
        "referencia_liquidacion": p.referencia_liquidacion,
    }


@router.get("/liquidaciones/pendientes", dependencies=_ADMIN)
def get_liquidaciones_pendientes() -> dict:
    """OPERADOR: liquidaciones online PENDIENTES de pagar al dueño (Pichangol le
    debe el neto). Para saber a quién transferir y cuánto. Más antiguas primero."""
    pend = stores.liquidaciones(solo_pendientes=True)
    total = sum(_liquidacion_dict(p)["neto_soles"] for p in pend)
    return {"pendientes": [_liquidacion_dict(p) for p in pend],
            "total_neto_soles": round(total, 2)}


@router.post("/liquidaciones/{reserva_id}/pagar", dependencies=_ADMIN)
def post_liquidacion_pagar(reserva_id: str, req: MarcarLiquidacionReq) -> dict:
    """OPERADOR: marca una liquidación como PAGADA (ya transfirió el neto al
    dueño). Idempotente."""
    p = stores.marcar_liquidacion_pagada(reserva_id, req.metodo, req.referencia)
    if p is None:
        raise HTTPException(status_code=404, detail="liquidacion_no_encontrada")
    return {"ok": True, **_liquidacion_dict(p)}


@router.get("/por-recibir/{dueno_id}", dependencies=_APP)
def get_por_recibir(dueno_id: str) -> dict:
    """DUEÑO: total NETO que Pichangol le debe por reservas online aún no
    liquidadas (su "por recibir"). Complementa el saldo prepago."""
    pend = stores.liquidaciones(dueno_id=dueno_id, solo_pendientes=True)
    total = sum(_liquidacion_dict(p)["neto_soles"] for p in pend)
    return {"dueno_id": dueno_id, "por_recibir_soles": round(total, 2),
            "reservas": len(pend)}


def _nivel_destacado(centimos: int) -> int:
    """Nivel de destacado según el saldo (más saldo = más visibilidad).
    3 = premium, 2 = medio, 1 = base. Umbrales en soles (tunables)."""
    s = centimos / 100.0
    if s >= 200:
        return 3
    if s >= 50:
        return 2
    return 1


@router.get("/destacados", dependencies=_APP)
def get_destacados() -> dict:
    """Conjunto de dueños DESTACADOS: los que tienen saldo prepago > 0. El APK
    lo usa para resaltar sus canchas en 'Explorar' (más saldo = más visibilidad,
    el beneficio que la plataforma le da al dueño). Se devuelve solo el id del
    dueño y un NIVEL coarse (1-3), no el saldo exacto (no se expone la plata de
    cada dueño a los demás usuarios)."""
    destacados = [
        {"dueno_id": d, "nivel": _nivel_destacado(c)}
        for d, c in stores.saldos.items()
        if c > 0
    ]
    return {"destacados": destacados}


class VistasReq(BaseModel):
    ids: list[str] = []


@router.post("/vistas/registrar", dependencies=_APP)
def post_vistas_registrar(req: VistasReq) -> dict:
    """Registra una IMPRESIÓN (vista) por cada id mostrado como destacado
    (dueno_id de canchas o id de academia). El APK lo llama cuando muestra los
    destacados. Es la métrica de impacto del boost que paga el dueño."""
    n = 0
    for id_ in req.ids:
        if id_:
            stores.registrar_vista(id_)
            n += 1
    return {"ok": True, "registradas": n}


@router.post("/vistas/consultar", dependencies=_APP)
def post_vistas_consultar(req: VistasReq) -> dict:
    """Impresiones agregadas de [ids]: {semana, total}. El dueño ve cuánta gente
    vio sus canchas (o su academia) destacadas."""
    r = stores.vistas_resumen([i for i in req.ids if i])
    return {"ok": True, **r}


@router.get("/movimientos/{dueno_id}", dependencies=_APP)
def get_movimientos(dueno_id: str,
                    x_user_token: str | None = Header(default=None)) -> dict:
    """Historial de movimientos de saldo del dueño (recargas aprobadas), del más
    reciente al más antiguo. El saldo vive en el backend, así que este historial
    SOBREVIVE a reinstalar la app (a diferencia del historial local del teléfono).
    Con PAGOS_AUTH_USUARIO=1 (PROD) solo el propio usuario ve sus movimientos.
    """
    _require_usuario(dueno_id, x_user_token)
    # Trazabilidad del dueño (3 tipos):
    #  - recarga            → entra saldo (+)
    #  - comision_reserva   → sale de su saldo por reserva en efectivo (−)
    #  - liquidacion_online → reserva online: Pichangol cobró al jugador, se queda
    #                         la comisión y le debe el NETO al dueño (no toca saldo).
    # Historial COMPLETO de la billetera única del usuario: entradas (recargas,
    # ingresos por torneo) y salidas (comisión de reserva, servicios, Pichangol
    # Pro, inscripción a torneo). Cada fila lleva su N.º de comprobante (p.id).
    _EGRESOS = ("comision_reserva", "suscripcion", "suscripcion_pro",
                "inscripcion_torneo", "bodega_pago")
    # `venta_producto` = venta del marketplace Y canje/compra de BONO de horas:
    # Pichangol cobró al comprador y le debe el NETO al dueño (misma
    # contabilidad que una reserva online). DEBE aparecer en el historial.
    _INCLUIR = ("recarga", "bono_recarga", "bono_bienvenida", "cupon",
                "liquidacion_online", "liquidacion_full",
                "venta_producto", "venta_bodega",
                "inscripcion_torneo_ingreso") + _EGRESOS
    propios = [
        p for p in stores.pagos
        if p.dueno_id == dueno_id and p.estado == "aprobado"
        and p.tipo in _INCLUIR
    ]
    _NOMBRE = {
        "recarga": "Recarga de saldo",
        "bono_recarga": "Bono de recarga 🎁",
        "bono_bienvenida": "Regalo de bienvenida 🎁",
        "cupon": "Cupón canjeado 🎁",
        "comision_reserva": "Comisión de reserva",
        "suscripcion": "Servicio de marketing",
        "suscripcion_pro": "Pichangol Pro",
        "inscripcion_torneo": "Inscripción a torneo",
        "inscripcion_torneo_ingreso": "Inscripción a torneo (ingreso)",
        "liquidacion_online": "Reserva online (neto)",
        "liquidacion_full": "Reserva online (recibes 100%)",
        "venta_producto": "Venta / bono (neto)",
        "venta_bodega": "Venta de bodega (pagada con saldo)",
        "bodega_pago": "Bodega · pagado con saldo",
    }

    def _fila(p) -> dict:
        base = {"tipo": p.tipo, "creado_en": p.creado_en.isoformat(),
                "comprobante": p.id,
                "concepto": p.concepto or _NOMBRE.get(p.tipo, "Movimiento")}
        # Medio con el que pagó el jugador (yape/tarjeta/sena), si se conoce:
        # el APK lo muestra en el estado de cuenta.
        if getattr(p, "medio", None):
            base["medio"] = p.medio
        if p.tipo in ("recarga", "bono_recarga", "bono_bienvenida", "cupon"):
            return {**base, "monto_soles": p.monto_centimos / 100.0}
        if p.tipo in _EGRESOS:
            # Egreso de saldo: negativo.
            return {**base, "monto_soles": -(p.monto_centimos / 100.0)}
        # liquidacion_online / inscripcion_torneo_ingreso: entrada NETA (bruto −
        # comisión); para torneo la comisión ya está congelada en el pago.
        bruto = p.monto_centimos
        if p.tipo == "liquidacion_full":
            comision = 0  # la comisión ya salió del saldo (billetera-first)
        elif p.tipo in ("inscripcion_torneo_ingreso", "venta_bodega"):
            comision = p.comision_centimos  # bodega: 0 (cero comisión)
        else:
            comision = comision_centimos(bruto / 100.0)
        neto = bruto - comision
        return {**base,
                "monto_soles": neto / 100.0,
                "bruto_soles": bruto / 100.0,
                "comision_soles": comision / 100.0,
                "neto_soles": neto / 100.0,
                "liquidado": (p.liquidado if p.tipo in
                              ("liquidacion_online", "liquidacion_full",
                               "venta_producto", "venta_bodega")
                              else True)}

    # stores.pagos está en orden de inserción (viejo→nuevo); lo invertimos para
    # mostrar el más reciente primero.
    movimientos = [_fila(p) for p in reversed(propios)]
    return {"dueno_id": dueno_id, "movimientos": movimientos}


# --- Cobro genérico al jugador (reservas, academias) ---------------------
@router.post("/cobrar", dependencies=_APP)
def post_cobrar(req: CobroReq) -> dict:
    """Cobra [monto_soles] al jugador (tarjeta nueva tkn_ o guardada crd_) a la
    cuenta de Pichangol. Sirve para reservas y matrículas de academia."""
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
    )
    if not r["ok"]:
        return {
            "ok": False,
            "error": r.get("error", "cargo_rechazado"),
            "codigo": r.get("codigo"),
            "merchant": r.get("merchant"),
        }
    charge_id = r["charge_id"]
    if stores.pago_por_charge(charge_id) is None:
        stores.registrar_pago(
            tipo=req.tipo, monto_centimos=centimos, moneda="PEN",
            estado="aprobado", email=req.email, culqi_charge_id=charge_id,
            concepto=req.concepto)
    return {"ok": True, "charge_id": charge_id}


# --- Métodos de pago guardados (Culqi One Click) -------------------------
@router.get("/metodos/{user_id}", dependencies=_APP)
def get_metodos(user_id: str) -> dict:
    return {"metodos": stores.metodos.get(user_id, [])}


@router.post("/metodos", dependencies=_APP)
def post_metodo(req: MetodoReq) -> dict:
    """Guarda una tarjeta del usuario (One Click). Crea/reusa el customer Culqi y
    convierte el token temporal en una tarjeta permanente (crd_...). Sólo guarda
    marca + últimos 4 (nunca el número completo)."""
    if not culqi.disponible():
        raise HTTPException(status_code=503, detail="pagos_no_configurados")
    cus = stores.customers.get(req.user_id)
    if not cus:
        rc = culqi.crear_customer(
            email=req.email, nombre=req.nombre, apellido=req.apellido,
            telefono=req.telefono)
        if not rc["ok"]:
            return {"ok": False, "paso": "cliente",
                    "error": rc.get("error", "no_se_pudo_crear_cliente"),
                    "codigo": rc.get("codigo"), "merchant": rc.get("merchant")}
        cus = rc["customer_id"]
        stores.customers[req.user_id] = cus
    rcard = culqi.crear_card(customer_id=cus, token=req.token)
    if not rcard["ok"]:
        return {"ok": False, "paso": "tarjeta",
                "error": rcard.get("error", "no_se_pudo_guardar_tarjeta"),
                "codigo": rcard.get("codigo"), "merchant": rcard.get("merchant")}
    metodo = {
        "id": rcard["card_id"],
        "marca": rcard["marca"],
        "ultimos4": rcard["ultimos4"],
    }
    stores.metodos.setdefault(req.user_id, []).append(metodo)
    return {"ok": True, "metodo": metodo}


@router.delete("/metodos/{user_id}/{card_id}", dependencies=_APP)
def del_metodo(user_id: str, card_id: str) -> dict:
    culqi.eliminar_card(card_id)  # best-effort en Culqi
    lst = stores.metodos.get(user_id, [])
    stores.metodos[user_id] = [m for m in lst if m.get("id") != card_id]
    return {"ok": True}


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
        descripcion="Recarga Pichangol",
        # Sin metadata por ahora: la recarga acredita de forma síncrona (no
        # depende del webhook). Se aísla un posible parameter_error de Culqi.
    )
    if not r["ok"]:
        stores.registrar_pago(
            tipo="recarga", monto_centimos=centimos, moneda="PEN",
            estado="rechazado", dueno_id=req.dueno_id, email=req.email,
            concepto="Recarga (rechazada)")
        return {
            "ok": False,
            "error": r.get("error", "cargo_rechazado"),
            "codigo": r.get("codigo"),
            "merchant": r.get("merchant"),
        }

    charge_id = r["charge_id"]
    # Idempotencia: si el webhook ya acreditó este cargo, no dupliques.
    bono = 0.0
    if stores.pago_por_charge(charge_id) is None:
        stores.acreditar(req.dueno_id, centimos)
        stores.registrar_pago(
            tipo="recarga", monto_centimos=centimos, moneda="PEN",
            estado="aprobado", dueno_id=req.dueno_id, email=req.email,
            culqi_charge_id=charge_id, concepto="Recarga de saldo")
        # PROMO: bono de recarga (si está activa en la torre).
        bono = _aplicar_bono_recarga(
            req.dueno_id, centimos / 100.0, charge_id)
    saldo = stores.saldo_centimos(req.dueno_id)
    return {
        "ok": True,
        "charge_id": charge_id,
        "bono_soles": bono,
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
        _aplicar_bono_recarga(
            meta["dueno_id"], info["monto_centimos"] / 100.0, charge_id)
    else:
        # fee u otro: sólo lo registramos (idempotencia/auditoría).
        stores.registrar_pago(
            tipo=meta.get("tipo", "fee_reserva"),
            monto_centimos=info["monto_centimos"], moneda="PEN",
            estado="aprobado", culqi_charge_id=charge_id,
            concepto="Confirmado por webhook")
    return {"ok": True}
