"""PEDIR A LA CANCHA en la web (lado JUGADOR): espejo de
`lib/screens/pedir_bodega_screen.dart`.

`GET /bodega/{cancha_id}/pedir` = la bodega del LOCAL (solo locales
verificados con dueño, como el botón "Bodega del local" de la ficha): tu
cuenta abierta ("llevas S/ X"), tus pedidos EN CURSO con su recorrido
(Enviado → En camino → Entregado) y Cancelar mientras siga pendiente, la
carta con +/- (solo si el dueño activó "Acepto pedidos"), la confirmación con
la ZONA de entrega y el pago "Al recibir" o "Con mi saldo" (misma moneda y
saldo suficiente), y el historial por fecha, colapsado.

Candados = los del app: "Acepto pedidos" del dueño, zona de su lista, GPS del
navegador a ≤ 250 m del local (sin permiso de ubicación NO se pide), un
pendiente sin respuesta en 10 min se muestra EXPIRADO. Prepago con saldo:
`pagos.router.cobrar_bodega_con_saldo` (= `POST /pagos/bodega-pago`) recién
con el pedido registrado; si el cobro falla el pedido se cancela. Cancelar un
prepagado → `post_bodega_reembolso` (misma función que el app).

`GET /mis-pedidos-bodega` = tus pedidos de TODOS los locales (30 días) y tus
cuentas abiertas, con enlace a la bodega de cada local.
"""

from __future__ import annotations

import json
import math
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

import paises
from db.store import stores
from pagos import router as _pagos
from web import datos, sesion, ui
from web import bodega_datos as bd
from web.anfitrion_bodega import imagen, _push, _m
from web.ui import PLAY_URL, e

router = APIRouter(tags=["web-jugador-bodega"])
RADIO_KM = 0.25  # anti-troll: debes estar EN el local para pedir
_TZ = ZoneInfo("America/Lima")
_ID_OK = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")


def distancia_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    """Haversine (= `distanciaKm` de `utils/geo.dart`)."""
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def moneda_saldo(email: str) -> str:
    """= `appState.monedaSaldoSimbolo` (país de la billetera)."""
    from web.jugador_billetera import pais_billetera
    iso, _ = pais_billetera(email)
    return paises.simbolo_de_moneda(paises.moneda_de_pais(iso))


def saldo(email: str) -> float:
    return stores.saldo_centimos(email) / 100.0


def _local(cancha_id: str) -> dict | None:
    """El local de la bodega: cancha verificada con dueño (= condición del botón del app)."""
    c = datos.cancha(cancha_id) if _ID_OK.match(cancha_id or "") else None
    if c is None or not datos.reservable(c):
        return None
    return c


def _nombre_local(c: dict) -> str:
    return c.get("club") or c.get("nombre") or "el local"


# ── Recorrido del pedido / estados (= `_recorridoPedido`, `_estadoVisual`) ────

def recorrido(p: dict) -> str:
    paso = 2 if p["estado"] == "entregado" else 1 if p["estado"] == "confirmado" else 0
    pasos = [("🛎️", "Enviado"), ("🏃", "En camino"), ("✅", "Entregado")]
    nodos = []
    for i, (ico, t) in enumerate(pasos):
        if i:
            nodos.append(f"<span class='rc-tr{' on' if i <= paso else ''}'></span>")
        nodos.append(f"<span class='rc-n{' on' if i <= paso else ''}{' act' if i == paso else ''}'><i>{ico}</i><small>{t}</small></span>")
    return "<div class='rc'>" + "".join(nodos) + "</div>"


def estado_visual(p: dict) -> tuple[str, str]:
    est = p["estado"]
    if est == "confirmado":
        t, c = "Confirmado · va en camino 🏃", "ok"
    elif est == "entregado":
        t, c = "Entregado ✅", "ok"
    elif est == "rechazado":
        t, c = "Rechazado por el local ❌", "bad"
    elif est == "cancelado":
        t, c = "Cancelado", "gris"
    elif bd.expirado(p):
        t, c = "Sin respuesta aún… pregunta en el mostrador", "bad"
    else:
        t, c = "Esperando confirmación ⏳", "warn"
    return (f"{t} · pagado 💳" if p["pagado"] else t), c


def _tarjeta_activo(p: dict, local: str = "") -> str:
    cancelar = (f"<button type='button' class='bj-canc' data-cancelar='{e(p['id'])}'>Cancelar</button>"
                if p["estado"] == "pendiente" else "")
    cuerpo = (f"<div class='bj-est bad'>{e(estado_visual(p)[0])}</div>" if p["estado"] == "pendiente" and bd.expirado(p)
              else recorrido(p) + ("<div class='bj-pag'>💳 Pagado con tu saldo</div>" if p["pagado"] else ""))
    donde = f"<div class='bj-loc'>🏟️ {e(local)}</div>" if local else ""
    return (f"<div class='bj-act'>{donde}<div class='bj-t'><b>{e(bd.resumen(p['items']))} → {e(p['zona'])}</b>{cancelar}</div>"
            f"<div class='bj-sub'>{e(_m(p['moneda'], p['total']))}</div>{cuerpo}</div>")


def _historial(hist: list[dict], locales: dict[str, str] | None = None) -> str:
    if not hist:
        return ""
    from datetime import datetime, timedelta
    hoy = datetime.now(_TZ).date()
    filas, previa = [], None
    for p in hist:
        d = p["creado"].astimezone(_TZ)
        g = "Hoy" if d.date() == hoy else "Ayer" if d.date() == hoy - timedelta(days=1) else ui_fecha(d.date())
        if g != previa:
            previa = g
            filas.append(f"<div class='bj-g'>{e(g)}</div>")
        eti, cls = {"entregado": ("Entregado ✅", "ok"), "rechazado": ("Rechazado", "bad"),
                    "cancelado": ("Cancelado", "gris")}.get(p["estado"], ("Sin respuesta", "bad"))
        loc = f"{e((locales or {}).get(p['dueno'], ''))} · " if locales else ""
        filas.append(f"<div class='bj-h'><div class='tx'><b>{e(bd.resumen(p['items']))} → {e(p['zona'])}</b>"
                     f"<small>{loc}{d:%H:%M} · {e(_m(p['moneda'], p['total']))}{' · 💳 saldo' if p['pagado'] else ''}</small></div>"
                     f"<span class='bj-est {cls}'>{eti}</span></div>")
    return (f"<details class='bj-hist'><summary>🧾 Pedidos anteriores <span>{len(hist)}</span></summary>{''.join(filas)}</details>")


_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
_DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def ui_fecha(d) -> str:
    return f"{_DIAS[d.weekday()]} {d.day} {_MESES[d.month - 1]}"


CSS = r"""
.bj{max-width:720px;margin:0 auto;padding-bottom:120px}
.bj h1{font-size:26px;margin:8px 0 4px}
.bj-cta{background:var(--tinte);border:1px solid var(--esmeralda);border-radius:16px;padding:14px 16px;margin:14px 0 10px}
.bj-cta .t{display:flex;justify-content:space-between;gap:10px}.bj-cta .t b:last-child{color:var(--teal);font-size:16px}
.bj-cta p{margin:4px 0 0;font-size:13px}.bj-cta small{color:var(--tenue)}
.bj-act{background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:14px;margin-bottom:10px}
.bj-t{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.bj-t b{overflow-wrap:anywhere}
.bj-sub{color:var(--tenue);font-size:13px;margin-top:2px}.bj-loc{font-size:12.5px;font-weight:800;color:var(--teal);margin-bottom:4px}
.bj-canc{border:0;background:none;color:var(--rojo,#C0392B);font-weight:800;cursor:pointer;font:inherit;flex:none}
.bj-pag{color:var(--esmeralda);font-weight:800;font-size:12.5px;margin-top:8px}
.rc{display:flex;align-items:flex-start;margin-top:12px}
.rc-n{display:flex;flex-direction:column;align-items:center;gap:4px;flex:none;width:64px}
.rc-n i{font-style:normal;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:1px solid var(--trazo);background:#fff;opacity:.4;font-size:15px}
.rc-n.on i{opacity:1;background:var(--tinte);border-color:var(--esmeralda)}.rc-n.act i{border-width:2px}
.rc-n small{font-size:11px;font-weight:800;color:var(--tenue)}.rc-n.on small{color:var(--teal)}
.rc-tr{flex:1;height:3px;border-radius:2px;background:var(--trazo);margin-top:16px}.rc-tr.on{background:var(--esmeralda)}
.bj-est{font-size:12.5px;font-weight:800;margin-top:6px}.bj-est.ok{color:var(--esmeralda)}.bj-est.bad{color:var(--rojo,#C0392B)}
.bj-est.warn{color:#C77700}.bj-est.gris{color:var(--tenue)}
.bj-aviso{background:#F4F6F8;border-radius:12px;padding:12px 14px;font-size:14px;margin:10px 0}
.bj-prod{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:10px 12px;margin-bottom:8px;min-width:0}
.bj-prod.en{background:var(--tinte);border-color:var(--esmeralda)}.bj-prod.tap{cursor:pointer}
.bj-prod .tx{flex:1;min-width:0}.bj-prod .tx b{display:block;overflow-wrap:anywhere}.bj-prod .tx small{color:var(--tenue);font-weight:700}
.bimg{width:46px;height:46px;border-radius:12px;background:#F4F6F8;display:inline-flex;align-items:center;justify-content:center;font-size:24px;overflow:hidden;flex:none}
.bimg img{width:100%;height:100%;object-fit:cover}
.bstep{display:inline-flex;align-items:center;gap:6px;flex:none}
.bstep button{width:32px;height:32px;border-radius:50%;border:1px solid var(--trazo);background:#fff;font-weight:900;cursor:pointer;font-family:inherit;font-size:16px;line-height:1}
.bstep .mas{background:var(--esmeralda);color:#fff;border-color:var(--esmeralda)}
.bstep span{min-width:18px;text-align:center;font-weight:900}
.bj-hist{margin-top:18px}.bj-hist summary{cursor:pointer;font-weight:800;font-size:15px;padding:8px 0;list-style:none;display:flex;justify-content:space-between}
.bj-hist summary span{color:var(--tenue)}.bj-g{color:var(--tenue);font-size:12.5px;font-weight:800;margin:10px 0 6px}
.bj-h{display:flex;gap:10px;justify-content:space-between;align-items:center;background:#fff;border:1px solid var(--trazo);border-radius:12px;padding:10px 12px;margin-bottom:6px}
.bj-h .tx{min-width:0}.bj-h b{display:block;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.bj-h small{color:var(--tenue);font-size:11.5px}
.bj-h .bj-est{margin:0;flex:none;font-size:12px}
.bbarra{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--trazo);padding:12px 16px calc(12px + env(safe-area-inset-bottom));z-index:40;display:none}
.bbarra.on{display:block}.bbarra .btn{width:100%;max-width:560px;margin:0 auto;display:block}
.bj-conf .ln{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding:3px 0;text-align:left}
.bj-conf .tot{border-top:1px solid var(--trazo);margin-top:8px;padding-top:8px;font-weight:900}
.bj-conf h4{margin:14px 0 8px;font-size:14px;text-align:left}.bj-conf .chips{justify-content:flex-start}
.bj-conf .chip{font-size:13px;padding:8px 12px}.bj-conf .nota{font-size:12.5px;color:var(--teal);font-weight:800;margin-top:8px;text-align:left}
.bj-conf .pie{font-size:12px;color:var(--tenue);margin-top:10px}
.bj-local{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:22px 0 8px}
.bj-local h2{font-size:17px;margin:0}
"""


# ── /bodega/{cancha_id}/pedir ─────────────────────────────────────────────────

def _no_disponible(ses) -> HTMLResponse:
    cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><div style='font-size:44px'>🧃</div>"
              "<h1 style='font-size:22px'>Esta bodega no está disponible</h1>"
              "<p class='sub'>Solo los locales verificados de Pichangol reciben pedidos a la cancha.</p>"
              "<div class='acciones' style='justify-content:center'><a class='btn' href='/canchas'>Explorar canchas</a></div></div>")
    resp = ui.shell("Bodega", cuerpo, sesion=ses, nav=ui.nav_simple(ses))
    resp.status_code = 404
    return resp


@router.get("/bodega/{cancha_id}/pedir", response_class=HTMLResponse)
def pagina_pedir(request: Request, cancha_id: str) -> HTMLResponse:
    ses = sesion.de_request(request)
    email = ((ses or {}).get("email") or "").strip().lower()
    c = _local(cancha_id)
    if c is None:
        return _no_disponible(ses)
    dueno = c["dueno"].strip().lower()
    local = _nombre_local(c)
    volver = f"/reservar/{quote(cancha_id)}"
    if email and email == dueno:
        cuerpo = (f"<div class='bj'><a class='anf-back' href='{volver}'>‹ {e(local)}</a>"
                  "<div class='panel' style='margin-top:20px;text-align:center'><div style='font-size:40px'>🧃🍺</div>"
                  "<h1 style='font-size:22px'>Esta es tu bodega</h1><p class='sub'>Los pedidos de tus clientes llegan a Mi bodega → Pedidos.</p>"
                  "<div class='acciones' style='justify-content:center'><a class='btn' href='/anfitrion/bodega?tab=pedidos'>Ir a Mi bodega</a></div></div></div>")
        return ui.shell(f"Bodega · {local}", cuerpo, sesion=ses, nav=ui.nav_simple(ses), extra_head=f"<style>{CSS}</style>")
    cfg = bd.config_de(dueno)
    prods = [p for p in bd.productos_de(dueno) if p["stock"] > 0]
    mios = bd.pedidos_de_cliente(email, dueno) if email else []
    cuenta = bd.cuenta_abierta(email, dueno) if email else None
    activos = [p for p in mios if p["estado"] in ("pendiente", "confirmado")]
    hist = [p for p in mios if p["estado"] not in ("pendiente", "confirmado")]
    mon = prods[0]["moneda"] if prods else "S/"
    partes = [f"<div class='bj'><a class='anf-back' href='{volver}'>‹ {e(local)}</a>",
              f"<h1>Bodega · {e(local)}</h1><p class='sub' style='margin:0'>Pide a tu cancha sin moverte: te lo llevan y pagas como siempre.</p>"]
    if cuenta is not None:
        partes.append(f"<div class='bj-cta'><div class='t'><b>📒 Tu cuenta abierta</b><b>{e(_m(cuenta['moneda'], cuenta['total']))}</b></div>"
                      f"<p>{e(bd.resumen(cuenta['items']))}</p><small>La pagas al salir, en el mostrador.</small></div>")
    partes += [_tarjeta_activo(p) for p in activos]
    if not cfg["acepta_pedidos"]:
        partes.append("<div class='bj-aviso'>🛒 Este local aún no recibe pedidos a la cancha: mira la carta y compra en el mostrador.</div>")
    if not prods:
        partes.append("<p class='sub' style='text-align:center;margin:24px 0'>La bodega aún no tiene productos.</p>")
    else:
        if cfg["acepta_pedidos"]:
            partes.append("<p style='font-weight:800;margin:16px 0 8px'>Toca para agregar a tu pedido</p>")
        for p in prods:
            paso = ("<span class='bstep'><button type='button' data-menos='{0}' aria-label='Quitar uno' hidden>−</button>"
                    "<span data-n='{0}' hidden></span><button type='button' class='mas' data-mas='{0}' aria-label='Agregar'>+</button></span>"
                    .format(e(p["id"])) if cfg["acepta_pedidos"] else "")
            partes.append(f"<div class='bj-prod{' tap' if cfg['acepta_pedidos'] else ''}' data-id='{e(p['id'])}'>{imagen(p)}"
                          f"<div class='tx'><b>{e(p['nombre'])}</b><small>{e(_m(p['moneda'], p['precio']))}</small></div>{paso}</div>")
        partes.append("<p class='sub' style='margin-top:10px'>Pagas al recibir tu pedido (efectivo o el QR del local), como siempre.</p>")
    partes.append(_historial(hist))
    partes.append("<p style='margin-top:18px'><a class='anf-back' style='margin:0' href='/mis-pedidos-bodega'>🧾 Ver todos mis pedidos a la cancha</a></p></div>")
    partes.append("<div class='bbarra' id='bjBarra'><button type='button' class='btn lg' id='bjPedir'>Pedir</button></div>")
    cfg_js = {
        "cancha": cancha_id, "local": local, "acepta": cfg["acepta_pedidos"], "zonas": cfg["zonas"], "mon": mon,
        "sesion": bool(email), "entrar": f"/entrar?volver={quote(f'/bodega/{cancha_id}/pedir', safe='')}",
        "saldo": saldo(email) if email else 0, "monSaldo": moneda_saldo(email) if email else "",
        "gps": bool(c.get("lat") and c.get("lng")),
        "prods": [{"id": p["id"], "nombre": p["nombre"], "precio": p["precio"], "stock": p["stock"], "moneda": p["moneda"]} for p in prods],
        "firma": [[p["id"], p["estado"]] for p in activos],
    }
    partes.append(f"<script>var BJ={json.dumps(cfg_js, ensure_ascii=False)};</script><script>{JS}</script>")
    return ui.shell(f"Bodega · {local}", "".join(partes), sesion=ses, nav=ui.nav_simple(ses),
                    titulo_tab=f"Bodega · {local}", extra_head=f"<style>{CSS}</style>")


@router.get("/web/bodega/{cancha_id}/estado")
def estado_json(request: Request, cancha_id: str) -> JSONResponse:
    """Sondeo cada 20 s con pedidos en curso (respaldo del push, como el app)."""
    ses = sesion.de_request(request)
    email = ((ses or {}).get("email") or "").strip().lower()
    c = _local(cancha_id)
    if not email or c is None:
        return JSONResponse({"ok": False}, status_code=401 if not email else 404)
    mios = bd.pedidos_de_cliente(email, c["dueno"])
    return JSONResponse({"ok": True, "firma": [[p["id"], p["estado"]] for p in mios if p["estado"] in ("pendiente", "confirmado")]})


def _err(msg: str, code: int = 400, **extra) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg, **extra}, status_code=code)


@router.post("/web/bodega/pedir")
def pedir(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `_enviar`: valida TODO en el servidor (local verificado, acepta
    pedidos, zona, stock y precios reales, GPS ≤ 250 m), registra el pedido y,
    si paga con saldo, cobra RECIÉN con el pedido registrado."""
    ses = sesion.de_request(request)
    email = ((ses or {}).get("email") or "").strip().lower()
    if not email:
        return _err("Inicia sesión para pedir a la bodega.", 401, sesion_requerida=True)
    c = _local(str(body.get("cancha_id") or ""))
    if c is None:
        return _err("Esta bodega no está disponible.", 404)
    dueno = c["dueno"].strip().lower()
    if dueno == email:
        return _err("Es tu propio local: los pedidos te llegan a Mi bodega.", 409)
    cfg = bd.config_de(dueno)
    if not cfg["acepta_pedidos"]:
        return _err("Este local aún no recibe pedidos a la cancha.", 409)
    zona = str(body.get("zona") or "")
    if zona not in cfg["zonas"]:
        return _err("Elige a dónde te lo llevamos.", 400)
    # Anti-troll: debes estar EN el local (≤ 250 m). Sin ubicación no se pide (igual que el app).
    if c.get("lat") and c.get("lng"):
        try:
            lat, lng = float(body.get("lat")), float(body.get("lng"))
        except (TypeError, ValueError):
            return _err("Activa tu ubicación: el pedido solo se puede hacer estando en el local.", 400, ubicacion=True)
        if distancia_km(lat, lng, c["lat"], c["lng"]) > RADIO_KM:
            return _err("Estás lejos del local: los pedidos a la cancha son para cuando estás ahí jugando.", 403, lejos=True)
    prods = {p["id"]: p for p in bd.productos_de(dueno)}
    cant: dict[str, int] = {}
    for it in body.get("items") if isinstance(body.get("items"), list) else []:
        pid = str((it or {}).get("id") or "")
        try:
            n = int((it or {}).get("cantidad") or 0)
        except (TypeError, ValueError):
            n = 0
        if pid and 0 < n <= 999:
            cant[pid] = cant.get(pid, 0) + n
    if not cant:
        return _err("Tu pedido está vacío.")
    items = []
    for pid, n in cant.items():
        p = prods.get(pid)
        if p is None or p["stock"] <= 0:
            return _err("Un producto ya no está disponible. Refresca la carta.", 409)
        if n > p["stock"]:
            return _err(f"Solo quedan {p['stock']} de {p['nombre']}.", 409)
        items.append({"producto_id": pid, "nombre": p["nombre"], "cantidad": n, "precio": p["precio"]})
    mon = prods[items[0]["producto_id"]]["moneda"]  # = `_mon` del app (moneda de la carta)
    total = bd.total_items(items)
    con_saldo = bool(body.get("con_saldo"))
    if con_saldo and not (total > 0 and moneda_saldo(email) == mon and saldo(email) >= total - 1e-9):
        return _err("Tu saldo no alcanza (o está en otra moneda): paga al recibir.", 409, saldo_insuficiente=True)
    nombre = (ses.get("nombre") or "").strip() or email
    ped = {"id": bd.nuevo_id("bpd"), "dueno": dueno, "cliente": email, "cliente_nombre": nombre, "zona": zona,
           "items": items, "total": total, "moneda": mon, "estado": "pendiente", "pagado": con_saldo}
    if not bd.crear_pedido(ped):
        return _err("No se pudo registrar el pedido (no se cobró nada). Intenta pagando al recibir." if con_saldo
                    else "No se pudo enviar el pedido. Revisa tu conexión.", 502)
    if con_saldo:
        try:
            pago = _pagos.cobrar_bodega_con_saldo(_pagos.BodegaPagoReq(
                cliente=email, dueno_id=dueno, monto_soles=total, pedido_id=ped["id"],
                concepto=f"Bodega · {bd.resumen(items)}", moneda=mon))
        except Exception:  # noqa: BLE001
            pago = None
        if not pago or pago.get("ok") is not True:
            bd.cambiar_estado_si(ped["id"], "cancelado", desde="pendiente", cliente=email)
            return _err("Tu saldo no alcanza: el pedido se canceló y no se cobró nada. Recarga o paga al recibir."
                        if (pago or {}).get("error") == "saldo_insuficiente"
                        else "No se pudo cobrar tu saldo: el pedido se canceló y no se cobró nada.", 409)
    _push(dueno, f"💳 Pedido PAGADO a la {zona}" if con_saldo else f"🧃 Pedido a la {zona}",
          f"{bd.resumen(items)} · {_m(mon, total)} · {nombre}. "
          + ("Ya está pagado con saldo Pichangol: solo entrégalo." if con_saldo else "Confírmalo en Mi bodega."), destino="dueno")
    return JSONResponse({"ok": True, "id": ped["id"],
                         "mensaje": "Pedido pagado y enviado 💳 Te avisamos cuando lo confirmen." if con_saldo
                         else "Pedido enviado 🏃 Te avisamos cuando lo confirmen. Pagas al recibirlo, como siempre."})


def _reembolsar(pid: str) -> bool:
    try:
        return bool(_pagos.post_bodega_reembolso(_pagos.BodegaReembolsoReq(pedido_id=pid)).get("ok"))
    except Exception:  # noqa: BLE001
        return False


@router.post("/web/bodega/pedido/{pid}/cancelar")
def cancelar(request: Request, pid: str) -> JSONResponse:
    """= `_cancelar`: solo si SIGUE pendiente (si el local lo confirmó un segundo
    antes, ya va en camino). Prepagado → reembolso automático al saldo."""
    ses = sesion.de_request(request)
    email = ((ses or {}).get("email") or "").strip().lower()
    if not email:
        return _err("Inicia sesión.", 401)
    p = bd.pedido(pid) if _ID_OK.match(pid or "") else None
    if p is None or p["cliente"] != email:
        return _err("Pedido no encontrado.", 404)
    ok, actual = bd.cambiar_estado_si(pid, "cancelado", desde="pendiente", cliente=email)
    if not ok:
        if actual in ("confirmado", "entregado"):
            return JSONResponse({"ok": False, "aviso": {"titulo": "Ya va en camino 🏃", "mensaje":
                                 "El local confirmó tu pedido justo antes de que lo cancelaras. Recíbelo y paga al recibirlo; "
                                 "cualquier cambio coordínalo en el mostrador."}})
        return JSONResponse({"ok": False, "estado": actual, "error": None if actual else "Revisa tu conexión."})
    msg = "Pedido cancelado."
    if p["pagado"]:
        msg = (f"Pedido cancelado: te devolvimos {_m(p['moneda'], p['total'])} a tu saldo 💸" if _reembolsar(pid)
               else "Pedido cancelado. La devolución a tu saldo se procesará en breve.")
    _push(p["dueno"], "Pedido cancelado", f"{p['cliente_nombre'] or email} canceló su pedido ({bd.resumen(p['items'])}).", destino="dueno")
    return JSONResponse({"ok": True, "mensaje": msg})


# ── /mis-pedidos-bodega ───────────────────────────────────────────────────────

@router.get("/mis-pedidos-bodega", response_class=HTMLResponse)
def pagina_mis_pedidos(request: Request) -> HTMLResponse:
    ses = sesion.de_request(request)
    email = ((ses or {}).get("email") or "").strip().lower()
    if not email:
        if sesion.activo():
            return HTMLResponse("", status_code=302, headers={"Location": "/entrar?volver=%2Fmis-pedidos-bodega"})
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><h1 style='font-size:22px'>Mis pedidos a la cancha</h1>"
                  "<p class='sub'>En esta web aún no está activo el inicio de sesión. Tus pedidos están en la app.</p>"
                  f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
        return ui.shell("Mis pedidos a la cancha", cuerpo, sesion=None)
    mios = bd.pedidos_de_cliente(email)
    cuentas = bd.cuentas_abiertas_cliente(email)
    locs = bd.locales_de([p["dueno"] for p in mios] + [c["dueno"] for c in cuentas])
    nombres = {d: v["club"] for d, v in locs.items()}
    activos = [p for p in mios if p["estado"] in ("pendiente", "confirmado")]
    hist = [p for p in mios if p["estado"] not in ("pendiente", "confirmado")]
    partes = ["<div class='bj'><a class='anf-back' href='/perfil'>‹ Perfil</a><h1>Mis pedidos a la cancha</h1>"
              "<p class='sub' style='margin:0'>Lo que pediste a la bodega de cada local en los últimos 30 días.</p>"]
    for ccta in cuentas:
        loc = locs.get(ccta["dueno"]) or {}
        partes.append(f"<div class='bj-cta'><div class='t'><b>📒 Tu cuenta abierta · {e(loc.get('club') or 'Local')}</b>"
                      f"<b>{e(_m(ccta['moneda'], ccta['total']))}</b></div><p>{e(bd.resumen(ccta['items']))}</p>"
                      "<small>La pagas al salir, en el mostrador.</small></div>")
    if activos:
        partes.append("<h2 style='font-size:17px;margin:20px 0 8px'>En curso</h2>")
        partes += [_tarjeta_activo(p, nombres.get(p["dueno"], "")) for p in activos]
    if not mios and not cuentas:
        partes.append("<div class='anf-vacio' style='margin-top:18px'><div style='font-size:40px'>🧃</div>Aún no pides a la cancha. "
                      "Entra a la ficha de un local verificado y toca «Bodega del local» para pedir sin moverte.</div>")
    partes.append(_historial(hist, nombres))
    enlaces = "".join(f"<a class='chip' href='/bodega/{quote(v['cancha_id'])}/pedir'>🧃 {e(v['club'])}</a>" for v in locs.values() if v.get("cancha_id"))
    if enlaces:
        partes.append(f"<div class='bj-local'><h2>Pedir otra vez</h2></div><div class='chips'>{enlaces}</div>")
    partes.append("</div>")
    cfg_js = {"firma": [[p["id"], p["estado"]] for p in activos], "global": True}
    partes.append(f"<script>var BJ={json.dumps(cfg_js)};</script><script>{JS}</script>")
    return ui.shell("Mis pedidos a la cancha", "".join(partes), sesion=ses, nav=ui.nav_simple(ses),
                    extra_head=f"<style>{CSS}</style>")


@router.get("/web/bodega/mis-pedidos.json")
def mis_pedidos_json(request: Request) -> JSONResponse:
    ses = sesion.de_request(request)
    email = ((ses or {}).get("email") or "").strip().lower()
    if not email:
        return JSONResponse({"ok": False}, status_code=401)
    return JSONResponse({"ok": True, "firma": [[p["id"], p["estado"]] for p in bd.pedidos_de_cliente(email)
                                               if p["estado"] in ("pendiente", "confirmado")]})


JS = r"""
(function(){
var C=BJ, ticket={};
function $(id){return document.getElementById(id)}
function esc(s){return String(s==null?'':s).replace(/[&<>'"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]})}
function fmt(m,v){return m+' '+Number(v||0).toFixed(2)}
function prod(id){for(var i=0;i<(C.prods||[]).length;i++)if(C.prods[i].id===id)return C.prods[i];return null}
function total(){var t=0;for(var id in ticket){var p=prod(id);if(p)t+=p.precio*ticket[id]}return Math.round(t*100)/100}
function nitems(){var n=0;for(var id in ticket)n+=ticket[id];return n}
try{var m=sessionStorage.getItem('bj_msg');if(m){sessionStorage.removeItem('bj_msg');setTimeout(function(){pcgToast(m)},200)}}catch(e){}
function pinta(){document.querySelectorAll('.bj-prod').forEach(function(r){var n=ticket[r.dataset.id]||0;r.classList.toggle('en',n>0);
    var mn=r.querySelector('[data-menos]'),sp=r.querySelector('[data-n]');if(mn){mn.hidden=!n;sp.hidden=!n;sp.textContent=n}});
  var b=$('bjBarra');if(!b)return;if(!nitems()){b.classList.remove('on');return}
  $('bjPedir').textContent='Pedir · '+fmt(C.mon,total())+' · '+nitems()+' ítem(s)';b.classList.add('on')}
function sumar(id,d){var p=prod(id);if(!p)return;var n=(ticket[id]||0)+d;if(d>0&&n>p.stock){pcgToast('Solo quedan '+p.stock+' de '+p.nombre+'.');return}if(n<=0)delete ticket[id];else ticket[id]=n;pinta()}
document.addEventListener('click',async function(ev){
  var mn=ev.target.closest('[data-menos]');if(mn){ev.stopPropagation();sumar(mn.dataset.menos,-1);return}
  var r=ev.target.closest('.bj-prod.tap');if(r){sumar(r.dataset.id,1);return}
  var c=ev.target.closest('[data-cancelar]');if(c){c.disabled=true;pcgCargando('Cancelando…',{demora:250});var j={};
    try{j=await (await fetch('/web/bodega/pedido/'+encodeURIComponent(c.dataset.cancelar)+'/cancelar',{method:'POST'})).json()}catch(e){j={error:'Revisa tu conexión.'}}pcgCargando(false);
    if(j.ok){try{sessionStorage.setItem('bj_msg',j.mensaje)}catch(e){}pcgRecargar();return}
    if(j.aviso){await pcgAvisar({titulo:j.aviso.titulo,mensaje:j.aviso.mensaje,icono:'🏃'});pcgRecargar();return}
    if(j.estado){pcgRecargar();return}pcgToast(j.error||'No se pudo cancelar.');c.disabled=false}});
function ubicar(){return new Promise(function(res){if(!navigator.geolocation){res(null);return}
  navigator.geolocation.getCurrentPosition(function(p){res({lat:p.coords.latitude,lng:p.coords.longitude})},function(){res(null)},{enableHighAccuracy:true,timeout:15000,maximumAge:60000})})}
if($('bjPedir'))$('bjPedir').addEventListener('click',async function(){if(!nitems())return;var btn=this;
  if(!C.sesion){if(await pcgConfirmar({titulo:'Inicia sesión para pedir',mensaje:'Tu pedido va a tu nombre (con tu cuenta de Google) para que el local sepa a quién llevárselo.',confirmar:'Iniciar sesión',icono:'🔐'}))pcgIr(C.entrar);return}
  var t=total(),puedeSaldo=C.saldo>=t&&t>0&&C.monSaldo===C.mon,z=C.zonas[0]||'',conSaldo=false;
  var h="<div class='bj-conf'>";Object.keys(ticket).forEach(function(id){var p=prod(id);if(p)h+="<div class='ln'><span>"+ticket[id]+" × "+esc(p.nombre)+"</span><b>"+esc(fmt(p.moneda,p.precio*ticket[id]))+"</b></div>"});
  h+="<div class='ln tot'><span>Total</span><b>"+esc(fmt(C.mon,t))+"</b></div><h4>¿Dónde te lo llevamos? 🏃</h4><div class='chips' id='bjZ'>"+C.zonas.map(function(zz,i){return "<button type='button' class='chip"+(i?'':' sel')+"' data-z='"+esc(zz)+"'>"+esc(zz)+"</button>"}).join('')+"</div>";
  if(puedeSaldo){h+="<h4>¿Cómo pagas? 💳</h4><div class='chips' id='bjP'><button type='button' class='chip sel' data-p='0'>Al recibir (efectivo/"+(C.mon==='S/'?'Yape':'QR')+")</button><button type='button' class='chip' data-p='1'>Con mi saldo ("+esc(fmt(C.monSaldo,C.saldo))+")</button></div>"
    +"<div class='nota' id='bjNota'>⭐ Págalo con tu saldo y ganas +"+Math.round(t)+" puntos</div>"}
  h+="<div class='pie' id='bjPie'>Pagas al recibirlo, como siempre.</div></div>";
  var sel=function(ev){var zb=ev.target.closest('[data-z]');if(zb){z=zb.dataset.z;document.querySelectorAll('#bjZ .chip').forEach(function(x){x.classList.toggle('sel',x===zb)})}
    var pb=ev.target.closest('[data-p]');if(pb){conSaldo=pb.dataset.p==='1';document.querySelectorAll('#bjP .chip').forEach(function(x){x.classList.toggle('sel',x===pb)});
      $('bjNota').textContent=conSaldo?'⭐ Ganas +'+Math.round(t)+' puntos con este pedido':'⭐ Págalo con tu saldo y ganas +'+Math.round(t)+' puntos';
      $('bjPie').textContent=conSaldo?'Se descuenta de tu saldo; si el local no lo toma, se te devuelve solo.':'Pagas al recibirlo, como siempre.';
      var ok=$('pcgDlgOk');if(ok)ok.textContent=conSaldo?'Pagar y enviar pedido 💳':'Enviar pedido 🛎️'}};
  document.addEventListener('click',sel);
  var si=await pcgConfirmar({titulo:'Confirma tu pedido 🧾',html:h,confirmar:'Enviar pedido 🛎️',cancelar:'Volver',icono:'🧾'});
  document.removeEventListener('click',sel);if(!si||!z)return;
  btn.disabled=true;var pos=null;
  if(C.gps){pcgCargando('Confirmando que estás en el local…');pos=await ubicar();pcgCargando(false);
    if(!pos){btn.disabled=false;await pcgAvisar({titulo:'Activa tu ubicación',mensaje:'El pedido solo se puede hacer estando en el local. Permite la ubicación en tu navegador e inténtalo otra vez.',icono:'📍'});return}}
  pcgCargando(conSaldo?'Cobrando y enviando…':'Enviando pedido…');var j={};
  try{j=await (await fetch('/web/bodega/pedir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cancha_id:C.cancha,zona:z,con_saldo:conSaldo,lat:pos&&pos.lat,lng:pos&&pos.lng,
    items:Object.keys(ticket).map(function(id){return {id:id,cantidad:ticket[id]}})})})).json()}catch(e){j={error:'No se pudo enviar el pedido. Revisa tu conexión.'}}
  pcgCargando(false);btn.disabled=false;
  if(j.ok){ticket={};try{sessionStorage.setItem('bj_msg',j.mensaje)}catch(e){}pcgRecargar();return}
  if(j.sesion_requerida){pcgIr(C.entrar);return}
  await pcgAvisar({titulo:j.lejos?'Estás lejos del local':'No se pudo enviar',mensaje:j.error||'Inténtalo otra vez.',icono:j.lejos?'📍':'⚠️'})});
// RESPALDO del push: con pedidos en curso, sondeo cada 20 s; el recorrido avanza solo.
if((C.firma||[]).length){var firma=JSON.stringify(C.firma),url=C.global?'/web/bodega/mis-pedidos.json':'/web/bodega/'+encodeURIComponent(C.cancha)+'/estado';
  setInterval(async function(){if(document.hidden||document.querySelector('.pcg-dlg.open'))return;try{var j=await (await fetch(url)).json();if(j.ok&&JSON.stringify(j.firma)!==firma)pcgRecargar()}catch(e){}},20000)}
})();
"""
