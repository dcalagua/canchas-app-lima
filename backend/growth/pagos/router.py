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


@router.get("/movimientos/{dueno_id}", dependencies=_APP)
def get_movimientos(dueno_id: str) -> dict:
    """Historial de movimientos de saldo del dueño (recargas aprobadas), del más
    reciente al más antiguo. El saldo vive en el backend, así que este historial
    SOBREVIVE a reinstalar la app (a diferencia del historial local del teléfono).
    """
    recargas = [
        p
        for p in stores.pagos
        if p.tipo == "recarga"
        and p.dueno_id == dueno_id
        and p.estado == "aprobado"
    ]
    movimientos = [
        {
            "tipo": "recarga",
            "monto_soles": p.monto_centimos / 100.0,
            "concepto": p.concepto or "Recarga de saldo",
            "creado_en": p.creado_en.isoformat(),
        }
        # stores.pagos está en orden de inserción (viejo→nuevo); lo invertimos
        # para mostrar el más reciente primero.
        for p in reversed(recargas)
    ]
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
            return {"ok": False, "error": rc.get("error", "no_se_pudo_crear_cliente")}
        cus = rc["customer_id"]
        stores.customers[req.user_id] = cus
    rcard = culqi.crear_card(customer_id=cus, token=req.token)
    if not rcard["ok"]:
        return {"ok": False, "error": rcard.get("error", "no_se_pudo_guardar_tarjeta")}
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
