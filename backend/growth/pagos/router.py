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
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
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


def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Auth de operador (torre de control) para marcar liquidaciones pagadas y
    ver las pendientes. Sin token configurado → fail-closed (503)."""
    if not config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=503, detail="admin_no_configurado")
    if x_admin_token != config.ADMIN_PANEL_TOKEN:
        raise HTTPException(status_code=401, detail="token_invalido")


_ADMIN = [Depends(_require_admin)]


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


@router.get("/saldo/{dueno_id}", dependencies=_APP)
def get_saldo(dueno_id: str) -> dict:
    c = stores.saldo_centimos(dueno_id)
    return {"dueno_id": dueno_id, "saldo_centimos": c, "saldo_soles": c / 100.0}


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
    comision = comision_centimos(req.monto_soles)
    # Idempotencia: si esta reserva ya generó comisión, no la cobres de nuevo.
    ya = stores.pago_por_charge(req.reserva_id)
    if ya is not None and ya.tipo == "comision_reserva":
        c = stores.saldo_centimos(req.dueno_id)
        return {"ok": True, "duplicada": True,
                "comision_centimos": ya.monto_centimos,
                "saldo_centimos": c, "saldo_soles": c / 100.0}
    nuevo = stores.debitar(req.dueno_id, comision)
    stores.registrar_pago(
        tipo="comision_reserva", monto_centimos=comision, moneda="PEN",
        estado="aprobado", dueno_id=req.dueno_id,
        culqi_charge_id=req.reserva_id,
        concepto=req.concepto or "Comisión de reserva")
    return {"ok": True, "duplicada": False, "comision_centimos": comision,
            "saldo_centimos": nuevo, "saldo_soles": nuevo / 100.0}


@router.post("/liquidacion-online", dependencies=_APP)
def post_liquidacion_online(req: LiquidacionOnlineReq) -> dict:
    """Registra la LIQUIDACIÓN de una reserva pagada ONLINE (dueño sin saldo):
    el jugador le pagó a Pichangol; se descuenta la comisión y el NETO se le debe
    al dueño (se le transfiere aparte). NO toca el saldo prepago — es otra
    contabilidad. Idempotente por `reserva_id`. Sirve para la trazabilidad del
    dueño (ve cuánto le cobró Pichangol y cuánto le queda por recibir)."""
    bruto = _soles_a_centimos(req.monto_soles)
    comision = comision_centimos(req.monto_soles)
    ya = stores.pago_por_charge(req.reserva_id)
    if ya is not None and ya.tipo == "liquidacion_online":
        return {"ok": True, "duplicada": True, "bruto_centimos": ya.monto_centimos,
                "comision_centimos": comision_centimos(ya.monto_centimos / 100.0),
                "neto_centimos": ya.monto_centimos
                - comision_centimos(ya.monto_centimos / 100.0)}
    stores.registrar_pago(
        tipo="liquidacion_online", monto_centimos=bruto, moneda="PEN",
        estado="aprobado", dueno_id=req.dueno_id,
        culqi_charge_id=req.reserva_id,
        concepto=req.concepto or "Reserva online")
    return {"ok": True, "duplicada": False, "bruto_centimos": bruto,
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
    comision = comision_centimos(bruto / 100.0)
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
def get_movimientos(dueno_id: str) -> dict:
    """Historial de movimientos de saldo del dueño (recargas aprobadas), del más
    reciente al más antiguo. El saldo vive en el backend, así que este historial
    SOBREVIVE a reinstalar la app (a diferencia del historial local del teléfono).
    """
    # Trazabilidad del dueño (3 tipos):
    #  - recarga            → entra saldo (+)
    #  - comision_reserva   → sale de su saldo por reserva en efectivo (−)
    #  - liquidacion_online → reserva online: Pichangol cobró al jugador, se queda
    #                         la comisión y le debe el NETO al dueño (no toca saldo).
    # Historial COMPLETO de la billetera única del usuario: entradas (recargas,
    # ingresos por torneo) y salidas (comisión de reserva, servicios, Pichangol
    # Pro, inscripción a torneo). Cada fila lleva su N.º de comprobante (p.id).
    _EGRESOS = ("comision_reserva", "suscripcion", "suscripcion_pro",
                "inscripcion_torneo")
    _INCLUIR = ("recarga", "liquidacion_online",
                "inscripcion_torneo_ingreso") + _EGRESOS
    propios = [
        p for p in stores.pagos
        if p.dueno_id == dueno_id and p.estado == "aprobado"
        and p.tipo in _INCLUIR
    ]
    _NOMBRE = {
        "recarga": "Recarga de saldo",
        "comision_reserva": "Comisión de reserva",
        "suscripcion": "Servicio de marketing",
        "suscripcion_pro": "Pichangol Pro",
        "inscripcion_torneo": "Inscripción a torneo",
        "inscripcion_torneo_ingreso": "Inscripción a torneo (ingreso)",
    }

    def _fila(p) -> dict:
        base = {"tipo": p.tipo, "creado_en": p.creado_en.isoformat(),
                "comprobante": p.id,
                "concepto": p.concepto or _NOMBRE.get(p.tipo, "Movimiento")}
        if p.tipo == "recarga":
            return {**base, "monto_soles": p.monto_centimos / 100.0}
        if p.tipo in _EGRESOS:
            # Egreso de saldo: negativo.
            return {**base, "monto_soles": -(p.monto_centimos / 100.0)}
        # liquidacion_online / inscripcion_torneo_ingreso: entrada NETA (bruto −
        # comisión); para torneo la comisión ya está congelada en el pago.
        bruto = p.monto_centimos
        comision = (p.comision_centimos if p.tipo == "inscripcion_torneo_ingreso"
                    else comision_centimos(bruto / 100.0))
        neto = bruto - comision
        return {**base,
                "monto_soles": neto / 100.0,
                "bruto_soles": bruto / 100.0,
                "comision_soles": comision / 100.0,
                "neto_soles": neto / 100.0,
                "liquidado": (p.liquidado if p.tipo == "liquidacion_online"
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
