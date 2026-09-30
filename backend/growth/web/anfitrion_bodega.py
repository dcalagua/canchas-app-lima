"""MI BODEGA en la web (Modo anfitrión → Mi bodega): el POS ligero del dueño,
espejo de `lib/screens/bodega_screen.dart` (función Pro).

Pestañas iguales al app: 🛒 Caja (venta en 3 s: tap = +1, ticket, "Cobrar" con
medio efectivo / Yape-Plin (o QR/transferencia fuera de Perú) / cortesía /
a la cuenta; descuenta stock), 📦 Productos (alta/edición con sugerencias POR
PAÍS, foto, stock con alerta de reposición), 📊 Reporte (hoy, 7 días, ventas de
hoy, stock valorizado, para reponer, lo más vendido), 🛎️ Pedidos (acepto
pedidos + zonas, Confirmar/Rechazar, "Entregado · cobrar" y los PREPAGADOS con
saldo verificados contra `GET /pagos/bodega-pago/{id}`) y 📒 Cuentas (cuenta
abierta con tope, cobrar y cerrar). Carta digital `/b/{carta_id}` con su QR.

La plata de la caja NO pasa por Pichangol (cero comisión): aquí solo se
registra la venta y baja el stock, como en el app. Los pedidos pagados con
saldo ya viven en la contabilidad del backend (`venta_bodega` "por recibir");
el rechazo de uno prepagado usa `POST /pagos/bodega-reembolso` (misma función).
Datos: `web/bodega_datos.py` (mismas tablas y candados que `BodegaRepo`).
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

import paises
from db.store import stores
from marketing import bodega_web
from marketing import packshot as packshot_svc
from pagos import router as _pagos
from web import almacen, datos, sesion, ui
from web import bodega_datos as bd
from web.anfitrion import _entrar
from web.ui import PLAY_URL, e

router = APIRouter(tags=["web-anfitrion-bodega"])
BASE = "/anfitrion/bodega"

CATEGORIAS = ["Bebidas", "Cervezas", "Deportivo", "Snacks", "Otros"]
# Sugerencias de un tap por categoría Y POR PAÍS (= `_sugerenciasPE/BO/EC`).
SUGERENCIAS = {
    "PE": {"Bebidas": ["Agua San Luis", "Agua San Mateo", "Coca-Cola", "Inca Kola", "Sprite", "Fanta", "Frugos", "Cifrut"],
           "Cervezas": ["Pilsen", "Cristal", "Cusqueña", "Corona", "Heineken"],
           "Deportivo": ["Gatorade", "Powerade", "Sporade", "Volt", "Alquiler de paleta", "Alquiler de pelotas", "Tubo de pelotas"],
           "Snacks": ["Papitas Lays", "Doritos", "Chifles", "Galletas", "Chocolate Sublime", "Maní", "Sandwich"],
           "Otros": ["Hielo", "Cigarros", "Toalla", "Gorra"]},
    "BO": {"Bebidas": ["Agua Vital", "Coca-Cola", "Sprite", "Fanta", "Salvietti", "Jugos Del Valle"],
           "Cervezas": ["Paceña", "Huari", "Potosina", "Corona", "Heineken"],
           "Deportivo": ["Gatorade", "Powerade", "Alquiler de paleta", "Alquiler de pelotas", "Tubo de pelotas"],
           "Snacks": ["Papitas", "Doritos", "Chizitos", "Galletas", "Maní", "Sandwich"],
           "Otros": ["Hielo", "Cigarros", "Toalla", "Gorra"]},
    "EC": {"Bebidas": ["Agua Güitig", "Agua Tesalia", "Coca-Cola", "Sprite", "Fanta", "Fioravanti"],
           "Cervezas": ["Pilsener", "Club Premium", "Corona", "Heineken"],
           "Deportivo": ["Gatorade", "Powerade", "Profit", "Alquiler de paleta", "Alquiler de pelotas", "Tubo de pelotas"],
           "Snacks": ["Papitas", "Doritos", "Kchitos", "Galletas", "Maní", "Sandwich"],
           "Otros": ["Hielo", "Cigarros", "Toalla", "Gorra"]},
}
_TZ = {"PE": "America/Lima", "BO": "America/La_Paz", "EC": "America/Guayaquil"}
TABS = [("caja", "🛒 Caja"), ("productos", "📦 Productos"), ("reporte", "📊 Reporte"),
        ("pedidos", "🛎️ Pedidos"), ("cuentas", "📒 Cuentas")]
_ID_OK = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")


def _en_fondo(fn, *args) -> None:
    """Pushes y reembolsos a terceros NO frenan la respuesta (los tests lo vuelven síncrono)."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _push(email: str, titulo: str, cuerpo: str, *, destino: str = "", dueno: str = "", tipo: str = "bodega_pedido") -> None:
    """= `appState.avisarPedidoBodega` / `avisarPuntosBodega` (fila en `pichangol_avisos`)."""
    from web.jugador_liga import aviso_push
    data = {k: v for k, v in (("destino", destino), ("dueno", (dueno or "").lower())) if v}
    _en_fondo(aviso_push, email, titulo, cuerpo, tipo, data or None)


# ── País / moneda del dueño ───────────────────────────────────────────────────

def pais_dueno(email: str, canchas: list[dict] | None = None) -> str:
    """País de sus canchas (como `paisActual` del dueño en su local); PE si no tiene."""
    for c in (canchas if canchas is not None else datos.canchas_de_dueno(email)):
        if c.get("lat") and c.get("lng"):
            return paises.pais_de_coordenadas(c["lat"], c["lng"])
    return "PE"


def _sim(iso: str) -> str:
    return paises.simbolo_de_moneda(paises.moneda_de_pais(iso))


def _m(sim: str, v: float) -> str:
    return f"{sim} {float(v or 0):.2f}"


def _medio_local(iso: str) -> str:
    """Jerga por país: Yape/Plin solo en Perú."""
    return "Yape / Plin del local" if iso == "PE" else "QR / transferencia del local"


def imagen(p: dict, clase: str = "bimg") -> str:
    """Foto real del dueño > packshot IA genérico (sin marca) > emoji (= `ImagenProductoBodega`)."""
    emo = bodega_web._emoji_producto(p["nombre"], p["categoria"])
    if p.get("foto_url"):
        return f"<span class='{clase}'><img src='{e(p['foto_url'])}' alt='' loading='lazy'></span>"
    if packshot_svc.disponible():
        tipo = bodega_web._packshot_tipo(p["nombre"], p["categoria"])
        return (f"<span class='{clase}' data-emo='{e(emo)}'><img src='/bodega/packshot/{e(tipo)}' alt='' loading='lazy' "
                "onerror=\"this.parentNode.textContent=this.parentNode.dataset.emo\"></span>")
    return f"<span class='{clase}'>{emo}</span>"


def _hace(d: datetime) -> str:
    m = int((bd.ahora() - d).total_seconds() // 60)
    if m < 1:
        return "ahora"
    if m < 60:
        return f"hace {m} min"
    h = m // 60
    return f"hace {h} h" if h < 24 else f"hace {h // 24} día(s)"


# ── Sesión / candado Pro ──────────────────────────────────────────────────────

def _ses(request: Request):
    ses = sesion.de_request(request)
    if ses and ses.get("email"):
        ses = dict(ses, email=ses["email"].strip().lower())
        return ses, None
    if sesion.activo():
        return None, _entrar(BASE)
    cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
              "<h1 style='font-size:22px'>Mi bodega</h1><p class='sub'>En esta web aún no está activo el inicio de sesión. "
              "Administra tu bodega desde la app.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    return None, ui.shell("Mi bodega", cuerpo, sesion=None)


def pro(email: str) -> bool:
    """Candado Pro = `appState.proActivo` (la bodega es parte de la suscripción)."""
    return stores.pro_activo(email)


def _dueno_json(request: Request) -> tuple[str | None, JSONResponse | None]:
    ses = sesion.de_request(request)
    email = (ses or {}).get("email", "").strip().lower()
    if not email:
        return None, JSONResponse({"ok": False, "error": "Inicia sesión para continuar."}, status_code=401)
    if not pro(email):
        return None, JSONResponse({"ok": False, "error": "La bodega es parte de Pichangol Pro.", "requiere_pro": True}, status_code=402)
    return email, None


def _cab(ses: dict | None) -> str:
    return ui.cabecera(ses=ses, volver="/anfitrion", modo="anfitrion")


# ── Página ────────────────────────────────────────────────────────────────────

CSS = r"""
.bod{max-width:980px;margin:0 auto;padding-bottom:110px}
.bod-top{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}
.bod-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 16px}
.bod-tabs .chip.sel{background:var(--noche);color:#fff;border-color:var(--noche)}
.bimg{width:46px;height:46px;border-radius:12px;background:#F4F6F8;display:inline-flex;align-items:center;justify-content:center;font-size:24px;overflow:hidden;flex:none}
.bimg img{width:100%;height:100%;object-fit:cover}
.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(170px,100%),1fr));gap:10px;margin-top:12px}
.bprod{position:relative;text-align:left;background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:12px;cursor:pointer;font-family:inherit;color:inherit;display:flex;flex-direction:column;gap:6px;min-width:0;box-shadow:0 1px 3px rgba(15,27,45,.04)}
.bprod:hover{border-color:#C9D3E0}.bprod.en{background:var(--tinte);border-color:var(--esmeralda);border-width:1.6px}
.bprod.agot{opacity:.55;cursor:not-allowed}
.bprod .nm{font-weight:800;font-size:14px;line-height:1.2;overflow-wrap:anywhere}
.bprod .pr{font-weight:900;font-size:16px}.bprod .st{font-size:12px;color:var(--tenue);font-weight:700}
.bprod .st.bajo{color:var(--rojo,#C0392B)}
.bprod .cant{position:absolute;top:8px;right:8px;background:var(--esmeralda);color:#fff;border-radius:999px;min-width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;font-weight:900;font-size:13px;padding:0 6px}
.bbusca{width:100%;border:1px solid var(--trazo);border-radius:999px;padding:11px 16px;font:inherit;background:#fff}
.bcats{display:flex;gap:8px;overflow-x:auto;padding:10px 0 2px;scrollbar-width:none}.bcats .chip{flex:none}
.bticket{border:1.4px solid var(--esmeralda);border-radius:16px;padding:14px 16px;background:#fff;margin-top:12px}
.bticket .ln{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid #F0F2F4}
.bticket .ln:last-of-type{border-bottom:0}
.bticket .ln b{display:block;font-size:14px;overflow-wrap:anywhere}.bticket .ln small{color:var(--tenue);font-size:12px}
.bstep{display:inline-flex;align-items:center;gap:4px}
.bstep button{width:30px;height:30px;border-radius:50%;border:1px solid var(--trazo);background:#fff;font-weight:900;cursor:pointer;font-family:inherit;font-size:15px;line-height:1}
.bstep span{min-width:24px;text-align:center;font-weight:900}
.btot{display:flex;justify-content:space-between;align-items:center;margin-top:10px;padding-top:10px;border-top:1px solid var(--trazo)}
.btot b{font-size:22px}
.bbarra{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--trazo);padding:12px 16px calc(12px + env(safe-area-inset-bottom));z-index:40;display:none}
.bbarra.on{display:block}.bbarra .btn{width:100%;max-width:560px;margin:0 auto;display:block}
.bfila{display:flex;gap:12px;align-items:center;background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:12px 14px;margin-bottom:8px;cursor:pointer;min-width:0}
.bfila .tx{flex:1;min-width:0}.bfila .tx b{display:block;overflow-wrap:anywhere}.bfila .tx small{color:var(--tenue);font-size:12.5px}
.bfila .stk{text-align:right;flex:none}.bfila .stk b{display:block;font-size:18px;color:var(--esmeralda)}.bfila .stk small{font-size:11px;color:var(--tenue);font-weight:700}
.bfila .stk.bajo b,.bfila .stk.bajo small{color:var(--rojo,#C0392B)}
.bfoto{position:relative;cursor:pointer;flex:none;border:0;background:none;padding:0}
.bfoto .cam{position:absolute;right:-4px;bottom:-4px;width:18px;height:18px;border-radius:50%;background:var(--esmeralda);color:#fff;font-size:10px;display:flex;align-items:center;justify-content:center}
.bsec{background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:14px 16px;margin-bottom:12px}
.bsw{display:flex;align-items:center;gap:12px;justify-content:space-between}
.bsw b{display:block}.bsw small{color:var(--tenue);font-size:12.5px}
.sw{position:relative;width:48px;height:28px;flex:none;border-radius:999px;background:#D5DBE2;border:0;cursor:pointer;transition:background .15s}
.sw::after{content:'';position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);transition:left .15s}
.sw.on{background:var(--esmeralda)}.sw.on::after{left:23px}
.bped{background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:14px;margin-bottom:10px}
.bped.pend{border-color:#E8A93B;background:#FFFBF2}
.bped .t{display:flex;justify-content:space-between;gap:10px}.bped .t b{overflow-wrap:anywhere}
.bped .sub2{color:var(--tenue);font-size:12.5px;margin-top:2px}
.bped .pag{color:var(--esmeralda);font-weight:800;font-size:12.5px;margin-top:6px}
.bped .acc{display:flex;gap:8px;margin-top:10px}.bped .acc .btn{flex:1}
.bcta{background:var(--tinte);border:1px solid var(--esmeralda);border-radius:16px;padding:14px;margin-bottom:10px}
.bcta .t{display:flex;justify-content:space-between;gap:10px}
.bcerr{display:flex;justify-content:space-between;gap:10px;background:#fff;border:1px solid var(--trazo);border-radius:12px;padding:10px 12px;margin-bottom:6px;font-size:13.5px}
.bcerr span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.brep h3{font-size:16px;margin:18px 0 6px}.brep li{margin:4px 0}.brep .bajo{color:var(--rojo,#C0392B)}
.bopc{display:flex;flex-direction:column;gap:8px}
.bopc button{display:flex;align-items:center;gap:12px;text-align:left;width:100%;border:1px solid var(--trazo);background:#fff;border-radius:14px;padding:12px 14px;cursor:pointer;font:inherit;color:inherit}
.bopc button:hover{border-color:var(--esmeralda);background:var(--tinte)}
.bopc .ic{font-size:22px;width:30px;text-align:center;flex:none}.bopc b{display:block}.bopc small{color:var(--tenue);font-size:12px}
.bopc .av{width:34px;height:34px;border-radius:50%;object-fit:cover;flex:none;background:var(--tinte);color:var(--teal);font-weight:800;display:inline-flex;align-items:center;justify-content:center}
.bform label.l{display:block;font-weight:800;margin:14px 0 6px}
.bform input[type=text],.bform input[type=number]{width:100%;border:1px solid var(--trazo);border-radius:12px;padding:11px 12px;font:inherit}
.bform .bsug{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.bform .bsug .chip{font-size:12px;padding:6px 10px}
.bform .fila{display:flex;align-items:center;gap:8px;margin-top:10px}.bform .fila span.l{flex:1;font-weight:700}
.bform .fila input{width:80px!important;text-align:center;font-weight:800}
.bform .err{color:var(--rojo,#C0392B);font-size:13px;margin-top:8px;min-height:1em}
.bform .pre{display:flex;align-items:center;border:1px solid var(--trazo);border-radius:12px;overflow:hidden}.bform .pre span{padding:0 10px;font-weight:800;color:var(--tenue)}.bform .pre input{border:0!important;border-radius:0!important}
.bqr{text-align:center}.bqr img{width:200px;max-width:100%;border-radius:12px;border:1px solid var(--trazo)}
.bticket .ln .sub3{display:flex;align-items:center;gap:12px}
@media(max-width:560px){.bticket .ln{row-gap:4px}.bticket .ln .sub3{grid-column:1/-1;justify-content:space-between}}
"""


def _tabs(sel: str, pendientes: int, abiertas: int) -> str:
    out = []
    for k, t in TABS:
        if k == "pedidos" and pendientes:
            t = f"{t} ({pendientes})"
        if k == "cuentas" and abiertas:
            t = f"{t} ({abiertas})"
        out.append(f"<a class='chip{' sel' if k == sel else ''}' href='{BASE}?tab={k}'>{e(t)}</a>")
    return "<nav class='bod-tabs' aria-label='Bodega'>" + "".join(out) + "</nav>"


def _vista_pro(ses: dict) -> HTMLResponse:
    cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
              "<div class='panel' style='max-width:560px;margin:26px auto 0;text-align:center'>"
              "<div style='font-size:44px'>🧃🍺</div><h1 style='font-size:22px;margin:10px 0 6px'>Administra tu bodega</h1>"
              "<p class='sub'>Caja rápida, stock con alertas de reposición, reportes de venta y la carta digital con QR para tus "
              "clientes. Tú cobras con tu Yape o efectivo, como siempre.</p>"
              "<p class='sub'>La bodega es parte de <b>Pichangol Pro</b>. Actívalo en la app (Perfil → Hazte Pro) y vuelve aquí.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}' rel='noopener'>👑 Activar con Pichangol Pro</a>"
              "<a class='btn sec' href='/anfitrion'>Volver al menú</a></div></div>")
    return ui.shell("Mi bodega", cuerpo, nav=_cab(ses), sesion=ses, ancho=True, titulo_tab="Mi bodega · Modo anfitrión",
                    extra_head=f"<style>{CSS}</style>")


def _vacio() -> str:
    return ("<div class='anf-vacio' style='margin-top:10px'><div style='font-size:48px'>📦</div>"
            "<h2 style='color:var(--noche);font-size:18px;margin:8px 0 4px'>Arma tu bodega en 2 minutos</h2>"
            "<p style='margin:0 0 14px'>Agrega tus productos con precio y stock; luego vendes con un tap desde la Caja.</p>"
            "<button type='button' class='btn' data-nuevo>＋ Agregar mi primer producto</button></div>")


def _vista_caja(prods: list[dict], sim: str) -> str:
    cats = ["Todo"] + [c for c in CATEGORIAS if any(p["categoria"] == c for p in prods)]
    chips = ("<div class='bcats'>" + "".join(
        f"<button type='button' class='chip{' sel' if c == 'Todo' else ''}' data-cat='{e(c)}'>{e(c)}</button>" for c in cats)
        + "</div>") if len(cats) > 2 else ""
    tarjetas = []
    for p in prods:
        agot = p["stock"] <= 0
        st = "Agotado" if agot else (f"¡Quedan {p['stock']}!" if bd.stock_bajo(p) else f"Stock: {p['stock']}")
        tarjetas.append(
            f"<button type='button' class='bprod{' agot' if agot else ''}' data-id='{e(p['id'])}' data-cat='{e(p['categoria'])}' "
            f"data-n='{e(p['nombre'].lower())}'{' disabled' if agot else ''}>"
            f"<span style='display:flex;gap:10px;align-items:center;min-width:0'>{imagen(p)}<span class='nm'>{e(p['nombre'])}</span></span>"
            f"<span class='pr'>{e(_m(p['moneda'] or sim, p['precio']))}</span>"
            f"<span class='st{' bajo' if agot or bd.stock_bajo(p) else ''}'>{e(st)}</span><span class='cant' hidden></span></button>")
    return ("<input class='bbusca' id='bBusca' type='search' placeholder='🔎 Buscar producto…' autocomplete='off'>"
            f"{chips}<div id='bTicket'></div><p class='sub' id='bTip' style='margin:12px 0 0'>Toca un producto para sumarlo al ticket.</p>"
            f"<p class='sub' id='bSinRes' hidden style='text-align:center;margin:18px 0'>Sin resultados con ese filtro.</p>"
            f"<div class='bgrid'>{''.join(tarjetas)}</div>")


def _vista_productos(prods: list[dict], sim: str) -> str:
    filas = []
    for p in prods:
        bajo = bd.stock_bajo(p)
        cam = "" if p.get("foto_url") else "<span class='cam'>📷</span>"
        filas.append(
            f"<div class='bfila' data-editar='{e(p['id'])}'>"
            f"<button type='button' class='bfoto' data-foto='{e(p['id'])}' aria-label='Cambiar foto'>{imagen(p)}{cam}</button>"
            f"<div class='tx'><b>{e(p['nombre'])}</b><small>{e(p['categoria'])} · {e(_m(p['moneda'] or sim, p['precio']))}</small></div>"
            f"<div class='stk{' bajo' if bajo else ''}'><b>{p['stock']}</b><small>{'¡reponer!' if bajo else 'en stock'}</small></div></div>")
    return (f"<div class='acciones' style='margin:0 0 12px'><button type='button' class='btn' data-nuevo>＋ Producto</button>"
            + ("" if almacen.disponible() else "<span class='sub' style='margin:0'>Las fotos se suben desde la app en este ambiente.</span>")
            + "</div>" + "".join(filas)
            + "<input type='file' id='bInFoto' accept='image/*' hidden>")


def _vista_reporte(prods: list[dict], ventas: list[dict], sim: str, iso: str) -> str:
    tz = ZoneInfo(_TZ.get(iso, "America/Lima"))
    hoy = datetime.now(tz).date()
    semana = bd.ahora() - timedelta(days=7)
    ventas_hoy = [v for v in ventas if v["creado"].astimezone(tz).date() == hoy]
    ventas7 = [v for v in ventas if v["creado"] > semana]
    unidades: dict[str, int] = {}
    for v in ventas7:
        for i in v["items"]:
            unidades[i["nombre"]] = unidades.get(i["nombre"], 0) + i["cantidad"]
    top = sorted(unidades.items(), key=lambda kv: kv[1], reverse=True)[:5]
    bajos = [p for p in prods if bd.stock_bajo(p)]
    valorizado = sum(p["stock"] * p["precio"] for p in prods)
    kpis = ("<div class='kpis' style='margin-top:0'>"
            f"<div class='kpi'><small>Hoy</small><b>{e(_m(sim, sum(v['total'] for v in ventas_hoy)))}</b></div>"
            f"<div class='kpi'><small>Últimos 7 días</small><b>{e(_m(sim, sum(v['total'] for v in ventas7)))}</b></div>"
            f"<div class='kpi'><small>Ventas hoy</small><b>{len(ventas_hoy)}</b></div>"
            f"<div class='kpi'><small>Stock valorizado</small><b>{e(_m(sim, valorizado))}</b></div></div>")
    out = [f"<div class='brep'>{kpis}"]
    if bajos:
        out.append("<h3>⚠️ Para reponer</h3><ul>" + "".join(
            f"<li class='bajo'>{e(p['nombre'])}: quedan {p['stock']}</li>" for p in bajos) + "</ul>")
    if top:
        out.append("<h3>🏆 Lo más vendido (7 días)</h3><ul>" + "".join(
            f"<li>{e(n)} — {u} und.</li>" for n, u in top) + "</ul>")
    if not ventas:
        out.append("<p class='sub' style='text-align:center;margin-top:24px'>Aún no registras ventas. Ve a la Caja y prueba una.</p>")
    return "".join(out) + "</div>"


def _vista_pedidos(pedidos: list[dict], cfg: dict) -> str:
    orden = sorted(pedidos, key=lambda p: (0 if p["estado"] == "pendiente" else 1 if p["estado"] == "confirmado" else 2,
                                           -p["creado"].timestamp()))
    zonas = " · ".join(cfg["zonas"])
    out = [("<div class='bsec'><div class='bsw'><div><b>Acepto pedidos a la cancha</b>"
            "<small>Tus clientes piden desde su cancha y tú confirmas.</small></div>"
            f"<button type='button' class='sw{' on' if cfg['acepta_pedidos'] else ''}' data-sw='acepta_pedidos' "
            f"role='switch' aria-checked='{'true' if cfg['acepta_pedidos'] else 'false'}' aria-label='Acepto pedidos'></button></div>"
            f"<div style='display:flex;justify-content:space-between;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap'>"
            f"<small class='sub' style='margin:0'>📍 Zonas: {e(zonas)}</small>"
            "<button type='button' class='btn sec' data-zonas style='padding:8px 14px'>📍 Zonas de entrega</button></div></div>")]
    if not orden:
        out.append("<div class='anf-vacio'>🛎️ Sin pedidos aún. Activa el switch y tus clientes podrán pedir desde su cancha 🍺</div>")
    for p in orden:
        est = p["estado"]
        cab = (f"<div class='t'><b>{e(bd.resumen(p['items']))} → {e(p['zona'])}</b><b style='white-space:nowrap'>{e(_m(p['moneda'], p['total']))}</b></div>"
               f"<div class='sub2'>{e(p['cliente_nombre'] or p['cliente'])} · {e(_hace(p['creado']))}</div>")
        if p["pagado"]:
            cab += "<div class='pag'>💳 PAGADO con saldo Pichangol · solo entrégalo</div>"
        if est == "pendiente":
            acc = (f"<div class='acc'><button type='button' class='btn' data-resp='{e(p['id'])}' data-v='1'>Confirmar ✅</button>"
                   f"<button type='button' class='btn sec' data-resp='{e(p['id'])}' data-v='0' style='color:var(--rojo,#C0392B)'>Rechazar</button></div>")
        elif est == "confirmado":
            acc = (f"<div class='acc'><button type='button' class='btn' data-entregar='{e(p['id'])}' data-pagado='{1 if p['pagado'] else 0}' "
                   f"data-total='{p['total']:.2f}' data-mon='{e(p['moneda'])}' data-zona='{e(p['zona'])}' data-cli='{e(p['cliente'])}'>"
                   f"{'Entregado ✓ (ya pagado con saldo)' if p['pagado'] else '✅ Entregado · cobrar y descontar stock'}</button></div>")
        else:
            acc = "<div class='sub2' style='margin-top:8px;font-weight:700'>" + e({
                "entregado": "Entregado ✅ (venta registrada)", "rechazado": "Rechazado",
                "cancelado": "Cancelado por el cliente"}.get(est, "Sin respuesta (expiró)")) + "</div>"
        out.append(f"<div class='bped{' pend' if est == 'pendiente' else ''}'>{cab}{acc}</div>")
    return "".join(out)


def _vista_cuentas(cuentas: list[dict], cfg: dict, sim: str) -> str:
    abiertas = [c for c in cuentas if c["estado"] == "abierta"]
    cerradas = [c for c in cuentas if c["estado"] != "abierta"]
    topes = "".join(
        f"<button type='button' class='chip{' sel' if abs(cfg['tope_cuenta'] - v) < 0.001 else ''}' data-tope='{v:g}'>"
        f"{'Sin tope' if v == 0 else e(f'{sim} {v:.0f}')}</button>" for v in bd.TOPES)
    out = [("<div class='bsec'><div class='bsw'><div><b>Permito cuenta abierta 📒</b>"
            "<small>El cliente identificado consume y paga todo al retirarse. La abres con «A la cuenta» al entregar o cobrar.</small></div>"
            f"<button type='button' class='sw{' on' if cfg['permite_cuenta'] else ''}' data-sw='permite_cuenta' role='switch' "
            f"aria-checked='{'true' if cfg['permite_cuenta'] else 'false'}' aria-label='Permito cuenta abierta'></button></div>"
            + (f"<p class='sub' style='margin:12px 0 8px'>Tope por cuenta (pasado el tope, se cobra al entregar)</p><div class='chips'>{topes}</div>"
               if cfg["permite_cuenta"] else "") + "</div>")]
    if not abiertas:
        out.append("<div class='anf-vacio'>📒 Sin cuentas abiertas. Al entregar un pedido (o cobrar en caja) elige «A la cuenta 📒» y el cliente paga al salir.</div>")
    for c in abiertas:
        out.append(f"<div class='bcta'><div class='t'><b>📒 {e(c['cliente_nombre'] or c['cliente'])}</b><b>{e(_m(c['moneda'], c['total']))}</b></div>"
                   f"<div style='font-size:13px;margin-top:4px'>{e(bd.resumen(c['items']))}</div>"
                   f"<div class='sub2' style='color:var(--tenue);font-size:12px;margin-top:2px'>Abierta {e(_hace(c['creado']))}</div>"
                   f"<button type='button' class='btn' style='width:100%;margin-top:10px' data-cerrar='{e(c['id'])}' "
                   f"data-total='{c['total']:.2f}' data-mon='{e(c['moneda'])}' data-nom='{e(c['cliente_nombre'])}'>🧾 Cobrar y cerrar cuenta</button></div>")
    if cerradas:
        out.append("<h3 style='font-size:15px;margin:18px 0 8px'>Cerradas (últimos 30 días)</h3>")
        for c in cerradas:
            val = "Cortesía" if c["medio_pago"] == "cortesia" else _m(c["moneda"], c["total"])
            out.append(f"<div class='bcerr'><span>{e(c['cliente_nombre'])} · {e(bd.resumen(c['items']))}</span><b style='color:var(--tenue)'>{e(val)}</b></div>")
    return "".join(out)


def _modal_carta(carta: str, base: str) -> str:
    enlace = f"{base}/b/{carta}"
    wa = ui.boton_whatsapp(f"Mira la carta de mi bodega 🧃🍺: {enlace}", "💬 Compartir", "btn sec")
    return ("<div class='modal' id='modalCarta' role='dialog' aria-modal='true'><div class='modal-caja' style='max-width:460px'>"
            "<div class='modal-cab'><button type='button' class='cerrar' data-cerrar-modal>✕</button><h3>Carta digital de tu bodega 🧾</h3></div>"
            "<div class='modal-cuerpo'><section class='bqr'><p class='sub' style='margin:0 0 14px'>Imprime el QR y pégalo junto a tu Yape: tus "
            "clientes ven la carta con precios siempre al día. Pagan contigo, como siempre.</p>"
            f"<img src='/b/{e(carta)}/qr.png' alt='QR de la carta' loading='lazy'>"
            "<div class='acciones' style='justify-content:center;margin-top:14px'>"
            f"<a class='btn' href='/b/{e(carta)}/qr.png' target='_blank' rel='noopener'>🖨️ Ver QR (imprimir)</a>"
            f"<a class='btn sec' href='/b/{e(carta)}' target='_blank' rel='noopener'>👀 Ver mi carta</a>{wa}"
            f"<button type='button' class='btn sec' data-copiar='{e(enlace)}'>🔗 Copiar enlace</button></div></section></div></div></div>")


@router.get(BASE, response_class=HTMLResponse)
def pagina_bodega(request: Request, tab: str = "caja") -> HTMLResponse:
    ses, resp = _ses(request)
    if resp is not None:
        return resp
    email = ses["email"]
    if not pro(email):
        return _vista_pro(ses)
    tab = tab if tab in dict(TABS) else "caja"
    canchas = datos.canchas_de_dueno(email)
    iso = pais_dueno(email, canchas)
    sim = _sim(iso)
    prods = bd.productos_de(email)
    pedidos = bd.pedidos_de_dueno(email)
    cuentas = bd.cuentas_de(email)
    cfg = bd.config_de(email)
    pendientes = sum(1 for p in pedidos if p["estado"] == "pendiente" and not bd.expirado(p))
    abiertas = sum(1 for c in cuentas if c["estado"] == "abierta")
    if tab == "pedidos":
        cuerpo_tab = _vista_pedidos(pedidos, cfg)
    elif tab == "cuentas":
        cuerpo_tab = _vista_cuentas(cuentas, cfg, sim)
    elif not prods:
        cuerpo_tab = _vacio()
    elif tab == "productos":
        cuerpo_tab = _vista_productos(prods, sim)
    elif tab == "reporte":
        cuerpo_tab = _vista_reporte(prods, bd.ventas_de(email, 30), sim, iso)
    else:
        cuerpo_tab = _vista_caja(prods, sim)
    carta = bd.carta_id_de(email)
    from marketing.router import _base_landing
    cfg_js = {
        "tab": tab, "sim": sim, "pais": iso, "medioLocal": _medio_local(iso),
        "permiteCuenta": cfg["permite_cuenta"], "tope": cfg["tope_cuenta"], "zonas": cfg["zonas"],
        "cats": CATEGORIAS, "sug": SUGERENCIAS.get(iso, SUGERENCIAS["PE"]), "storage": almacen.disponible(),
        "prods": [{k: p[k] for k in ("id", "nombre", "categoria", "precio", "stock", "stock_min", "moneda")} for p in prods],
        "abiertas": [{"id": c["id"], "cliente": c["cliente"], "nombre": c["cliente_nombre"], "total": c["total"], "moneda": c["moneda"]}
                     for c in cuentas if c["estado"] == "abierta"],
        "firma": [[p["id"], p["estado"]] for p in pedidos],
    }
    cuerpo = (
        "<div class='bod'><a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
        "<div class='bod-top'><div><h1 class='anf-hola' style='margin-top:6px'>Mi bodega</h1>"
        "<p class='sub' style='margin:0'>Tu POS: vende, controla stock y recibe pedidos a la cancha. La plata de la caja es tuya: "
        "cero comisión.</p></div>"
        "<button type='button' class='btn sec' data-abrir='modalCarta'>🧾 Carta digital y QR</button></div>"
        f"{_tabs(tab, pendientes, abiertas)}{cuerpo_tab}</div>"
        "<div class='bbarra' id='bBarra'><button type='button' class='btn lg' id='bCobrar'>Cobrar</button></div>"
        f"{_modal_carta(carta, _base_landing(request))}"
        "<div class='modal' id='bModal' role='dialog' aria-modal='true'><div class='modal-caja' style='max-width:480px'>"
        "<div class='modal-cab'><button type='button' class='cerrar' data-cerrar-modal>✕</button><h3 id='bModalTit'></h3></div>"
        "<div class='modal-cuerpo' id='bModalCuerpo'></div></div></div>"
        f"<script>var BOD={json.dumps(cfg_js, ensure_ascii=False)};</script><script>{JS}</script>")
    return ui.shell("Mi bodega", cuerpo, nav=_cab(ses), sesion=ses, ancho=True, titulo_tab="Mi bodega · Modo anfitrión",
                    extra_head=f"<style>{CSS}</style>")


@router.get(BASE + "/pedidos.json")
def pedidos_json(request: Request) -> JSONResponse:
    """Sondeo de la pestaña Pedidos (respaldo del push: el pedido aparece solo)."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    ps = bd.pedidos_de_dueno(email)
    return JSONResponse({"ok": True, "firma": [[p["id"], p["estado"]] for p in ps],
                         "pendientes": sum(1 for p in ps if p["estado"] == "pendiente" and not bd.expirado(p))})


@router.get(BASE + "/clientes.json")
def clientes_json(request: Request) -> JSONResponse:
    """Clientes REGISTRADOS del local para abrir cuenta (= `_elegirClienteRegistrado`)."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    con_cuenta = {c["cliente"] for c in bd.cuentas_de(email) if c["estado"] == "abierta"}
    lista = [c for c in bd.clientes_registrados(email) if c["email"] not in con_cuenta and c["email"] != email]
    from web.jugador_market import perfiles
    fotos = perfiles([c["email"] for c in lista[:300]])
    return JSONResponse({"ok": True, "clientes": [dict(c, foto=(fotos.get(c["email"]) or {}).get("foto_url", "")) for c in lista]})


# ── Productos ─────────────────────────────────────────────────────────────────

def _entero(v, maximo: int = 99999) -> int:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return 0
    return max(0, min(n, maximo))


@router.post(BASE + "/producto")
def guardar_producto(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `_editarProducto` → `guardarProducto` (mismas validaciones y textos)."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    nombre = re.sub(r"\s+", " ", str(body.get("nombre") or "")).strip()[:60]
    categoria = str(body.get("categoria") or "")
    if categoria not in CATEGORIAS:
        categoria = "Otros"
    if not nombre:
        return JSONResponse({"ok": False, "error": "Ponle nombre al producto."}, status_code=400)
    try:
        precio = round(float(str(body.get("precio") or "").replace(",", ".")), 2)
    except ValueError:
        precio = 0
    if not precio or precio <= 0 or precio > 100000:
        return JSONResponse({"ok": False, "error": "Ponle el precio de venta."}, status_code=400)
    pid = str(body.get("id") or "").strip()
    actual = None
    if pid:
        if not _ID_OK.match(pid):
            return JSONResponse({"ok": False, "error": "Producto inválido."}, status_code=400)
        actual = bd.producto_de(pid, email)
        if actual is None:
            return JSONResponse({"ok": False, "error": "Este producto no es tuyo."}, status_code=404)
    else:
        pid = bd.nuevo_id("bp")
    p = {"id": pid, "dueno": email, "carta_id": bd.carta_id_de(email), "nombre": nombre, "categoria": categoria,
         "precio": precio, "stock": _entero(body.get("stock")), "stock_min": _entero(body.get("stock_min")),
         "foto_url": (actual or {}).get("foto_url") or "",
         # Moneda: la del producto si ya existe; si es nuevo, la del país del local (= `paisActual.moneda`).
         "moneda": (actual or {}).get("moneda") or _sim(pais_dueno(email))}
    if not bd.guardar_producto(p):
        return JSONResponse({"ok": False, "error": "No se pudo guardar. Inténtalo de nuevo."}, status_code=502)
    return JSONResponse({"ok": True, "id": pid})


@router.post(BASE + "/producto/{pid}/eliminar")
def eliminar_producto(request: Request, pid: str) -> JSONResponse:
    email, err = _dueno_json(request)
    if err is not None:
        return err
    if not _ID_OK.match(pid) or not bd.eliminar_producto(pid, email):
        return JSONResponse({"ok": False, "error": "No se pudo eliminar."}, status_code=404)
    # Borra SU foto del bucket (misma ruta que el app); los packshots IA son compartidos y no se tocan.
    if almacen.disponible():
        _en_fondo(almacen.borrar_foto, almacen.url_publica(f"bodega/{pid}.jpg"))
    return JSONResponse({"ok": True})


@router.post(BASE + "/producto/{pid}/foto")
async def subir_foto(request: Request, pid: str) -> JSONResponse:
    cuerpo = await request.body()
    return await run_in_threadpool(_subir_foto, request, pid, cuerpo)


def _subir_foto(request: Request, pid: str, cuerpo: bytes) -> JSONResponse:
    """= `_cambiarFoto` → `subirFoto`: bucket `canchas`, ruta `bodega/<id>.jpg` (upsert)."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    if not _ID_OK.match(pid) or bd.producto_de(pid, email) is None:
        return JSONResponse({"ok": False, "error": "Este producto no es tuyo."}, status_code=404)
    if not almacen.disponible():
        return JSONResponse({"ok": False, "error": "La subida de fotos no está disponible en este ambiente."}, status_code=503)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp"):
        return JSONResponse({"ok": False, "error": "Formato no admitido (usa JPG, PNG o WebP)."}, status_code=415)
    if not cuerpo or len(cuerpo) > almacen.MAX_BYTES:
        return JSONResponse({"ok": False, "error": "La foto pesa demasiado (máx. 6 MB)."}, status_code=413)
    url = almacen.subir(almacen.BUCKET, f"bodega/{pid}.jpg", cuerpo, ctype)
    if not url or not bd.poner_foto(pid, email, url):
        return JSONResponse({"ok": False, "error": "No se pudo subir la foto. Inténtalo de nuevo."}, status_code=502)
    return JSONResponse({"ok": True, "url": url})


# ── Caja rápida ───────────────────────────────────────────────────────────────

def _armar_items(email: str, pedidos_items) -> tuple[list[dict] | None, str]:
    """Ítems del ticket con precio y nombre del SERVIDOR (nunca los del navegador)."""
    prods = {p["id"]: p for p in bd.productos_de(email)}
    cant: dict[str, int] = {}
    for it in pedidos_items if isinstance(pedidos_items, list) else []:
        pid = str((it or {}).get("id") or "")
        n = _entero((it or {}).get("cantidad"), 999)
        if pid and n > 0:
            cant[pid] = cant.get(pid, 0) + n
    if not cant:
        return None, "El ticket está vacío."
    items = []
    for pid, n in cant.items():
        p = prods.get(pid)
        if p is None:
            return None, "Un producto del ticket ya no existe. Refresca la página."
        if n > p["stock"]:
            return None, f"Solo te quedan {p['stock']} de {p['nombre']}."
        items.append({"producto_id": pid, "nombre": p["nombre"], "cantidad": n, "precio": p["precio"]})
    return items, ""


def _bajos_tras(email: str, descuentos: dict[str, int]) -> list[str]:
    return [f"{p['nombre']} ({p['stock']})" for p in bd.productos_de(email) if p["id"] in descuentos and bd.stock_bajo(p)]


def _anotar(email: str, cliente: str, nombre: str, items: list[dict], moneda: str, tope: float) -> tuple[dict | None, dict | None]:
    """Anota a la cuenta con el candado del TOPE (= `_anotarTicketACuenta`)."""
    abierta = bd.cuenta_abierta(cliente, email)
    previo = abierta["total"] if abierta else 0.0
    agregado = bd.total_items(items)
    if tope > 0 and previo + agregado > tope + 1e-9:
        sim = (abierta or {}).get("moneda") or moneda
        return None, {"titulo": "Tope de cuenta alcanzado",
                      "mensaje": f"La cuenta de {nombre} llegaría a {_m(sim, previo + agregado)} y tu tope es {sim} {tope:.0f}. "
                                 "Cobra este consumo al entregar (o cierra la cuenta primero)."}
    res = bd.anotar_a_cuenta(dueno=email, cliente=cliente, cliente_nombre=nombre, items=items, moneda=(abierta or {}).get("moneda") or moneda)
    return res, None


@router.post(BASE + "/vender")
def vender(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `_cobrar`: registra la venta y descuenta stock; 'cuenta' → anota a la
    cuenta abierta de un cliente REGISTRADO (el stock baja ya, la venta al cerrar)."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    medio = str(body.get("medio") or "")
    if medio not in bd.MEDIOS_CAJA + ("cuenta",):
        return JSONResponse({"ok": False, "error": "Elige cómo pagó."}, status_code=400)
    items, msg = _armar_items(email, body.get("items"))
    if items is None:
        return JSONResponse({"ok": False, "error": msg}, status_code=409)
    descuentos = bd.descuentos_de(items)
    sim = _sim(pais_dueno(email))
    if medio == "cuenta":
        cfg = bd.config_de(email)
        if not cfg["permite_cuenta"]:
            return JSONResponse({"ok": False, "error": "Activa la cuenta abierta en la pestaña Cuentas."}, status_code=409)
        cliente = str(body.get("cliente") or "").strip().lower()
        abiertas = {c["cliente"]: c for c in bd.cuentas_de(email) if c["estado"] == "abierta"}
        if cliente in abiertas:
            nombre = abiertas[cliente]["cliente_nombre"]
        else:
            reg = next((c for c in bd.clientes_registrados(email) if c["email"] == cliente), None)
            if reg is None or cliente == email:
                return JSONResponse({"ok": False, "error": "La cuenta abierta es solo para clientes registrados del local."}, status_code=400)
            nombre = reg["nombre"]
        res, aviso = _anotar(email, cliente, nombre, items, sim, cfg["tope_cuenta"])
        if aviso:
            return JSONResponse({"ok": False, "aviso": aviso}, status_code=409)
        if res is None:
            return JSONResponse({"ok": False, "error": "No se pudo anotar (¿la cuenta se cerró?). Refresca e intenta de nuevo."}, status_code=409)
        bd.descontar_stock(descuentos, email)
        _push(res["cliente"], "Anotado en tu cuenta 📒",
              f"Se agregó {bd.resumen(items)}. Llevas {_m(res['moneda'], res['total'])}; pagas al salir.",
              destino="cliente", dueno=email)
        return JSONResponse({"ok": True, "mensaje": f"Anotado a la cuenta de {res['cliente_nombre']} 📒 · lleva {_m(res['moneda'], res['total'])}"})
    venta = {"id": bd.nuevo_id("bv"), "dueno": email, "items": items,
             "total": 0.0 if medio == "cortesia" else bd.total_items(items), "medio_pago": medio}
    if not bd.registrar_venta(venta, descuentos):
        return JSONResponse({"ok": False, "error": "No se pudo registrar. Revisa tu conexión e intenta."}, status_code=502)
    bajos = _bajos_tras(email, descuentos)
    return JSONResponse({"ok": True, "mensaje": "Venta registrada ✅ · stock actualizado" if not bajos
                         else f"Venta registrada ✅ · ¡Repón: {', '.join(bajos)}!"})


# ── Configuración ─────────────────────────────────────────────────────────────

@router.post(BASE + "/config")
def guardar_config(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `_toggleAceptaPedidos`, `_editarZonas`, `_togglePermiteCuenta`, `_ponerTope`."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    cfg = bd.config_de(email)
    if "acepta_pedidos" in body:
        cfg["acepta_pedidos"] = bool(body["acepta_pedidos"])
    if "permite_cuenta" in body:
        cfg["permite_cuenta"] = bool(body["permite_cuenta"])
    if "tope_cuenta" in body:
        try:
            tope = float(body["tope_cuenta"])
        except (TypeError, ValueError):
            tope = -1
        if tope not in bd.TOPES:
            return JSONResponse({"ok": False, "error": "Tope inválido."}, status_code=400)
        cfg["tope_cuenta"] = tope
    if "zonas" in body:
        zonas = []
        for z in body["zonas"] if isinstance(body["zonas"], list) else []:
            z = re.sub(r"\s+", " ", str(z or "")).strip()[:20]
            if z and z not in zonas:
                zonas.append(z)
        if not zonas or len(zonas) > 20:
            return JSONResponse({"ok": False, "error": "Deja al menos una zona de entrega."}, status_code=400)
        cfg["zonas"] = zonas
    if not bd.guardar_config(cfg):
        return JSONResponse({"ok": False, "error": "No se pudo guardar. Inténtalo de nuevo."}, status_code=502)
    if "permite_cuenta" in body and bd.config_de(email)["permite_cuenta"] != cfg["permite_cuenta"]:
        # El guardado cayó al modo sin columnas nuevas: el toggle se perdería en silencio.
        return JSONResponse({"ok": False, "aviso": {"titulo": "Falta actualizar la base",
                             "mensaje": "Para activar la cuenta abierta hay que correr el script supabase_bodega_cuentas.sql "
                                        "en Supabase (avísale a tu admin)."}}, status_code=409)
    return JSONResponse({"ok": True})


# ── Pedidos a la cancha ───────────────────────────────────────────────────────

def _mio(email: str, pid: str) -> dict | None:
    p = bd.pedido(pid) if _ID_OK.match(pid or "") else None
    return p if p is not None and p["dueno"] == email else None


def _reembolsar(pid: str) -> None:
    try:
        _pagos.post_bodega_reembolso(_pagos.BodegaReembolsoReq(pedido_id=pid))
    except Exception as ex:  # noqa: BLE001
        print(f"[bodega] reembolso {pid} falló: {ex}", flush=True)


@router.post(BASE + "/pedido/{pid}/responder")
def responder_pedido(request: Request, pid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `_responderPedido` (candado: solo si SIGUE pendiente)."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    p = _mio(email, pid)
    if p is None:
        return JSONResponse({"ok": False, "error": "Pedido no encontrado."}, status_code=404)
    confirmar = bool(body.get("confirmar"))
    ok, actual = bd.cambiar_estado_si(pid, "confirmado" if confirmar else "rechazado", desde="pendiente", dueno=email)
    if not ok:
        if actual == "cancelado":
            return JSONResponse({"ok": False, "estado": actual, "aviso": {
                "titulo": "El cliente lo canceló", "mensaje": "Este pedido fue cancelado por el cliente antes de que lo confirmaras. No hay nada que llevar."}})
        if actual is None:
            return JSONResponse({"ok": False, "error": "Sin conexión: no se pudo guardar."}, status_code=502)
        return JSONResponse({"ok": False, "estado": actual})
    if not confirmar and p["pagado"]:
        _en_fondo(_reembolsar, pid)  # prepagado rechazado → reembolso automático
    if confirmar:
        _push(p["cliente"], "Pedido confirmado 🏃",
              f"Tu pedido ({bd.resumen(p['items'])}) va en camino a la {p['zona']}. "
              + ("Ya está pagado 💳" if p["pagado"] else "Pagas al recibirlo."), destino="cliente", dueno=email)
    else:
        _push(p["cliente"], "Pedido rechazado 😔",
              f"El local no pudo tomar tu pedido ({bd.resumen(p['items'])}). "
              + ("Tu saldo se devuelve solo 💸" if p["pagado"] else "Acércate al mostrador."), destino="cliente", dueno=email)
    return JSONResponse({"ok": True})


@router.post(BASE + "/pedido/{pid}/entregar")
def entregar_pedido(request: Request, pid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `_entregarPedido` / `_entregarPedidoPagado`: RECLAMA el pedido
    (confirmado → entregado) ANTES de registrar la venta; con dos equipos
    solo uno cobra."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    p = _mio(email, pid)
    if p is None:
        return JSONResponse({"ok": False, "error": "Pedido no encontrado."}, status_code=404)
    descuentos = bd.descuentos_de(p["items"])
    if p["pagado"]:
        try:
            pagado = bool(_pagos.get_bodega_pago(pid).get("pagado"))
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "Sin conexión: no se pudo verificar el pago. Intenta de nuevo."}, status_code=502)
        if not pagado:
            return JSONResponse({"ok": False, "aviso": {"titulo": "Pago no confirmado",
                                 "mensaje": "Este pedido figura pagado pero el sistema no confirma el cobro (pudo reembolsarse). "
                                            "Cóbralo al entregar como un pedido normal."}}, status_code=409)
        ok, actual = bd.cambiar_estado_si(pid, "entregado", desde="confirmado", dueno=email)
        if not ok:
            return JSONResponse({"ok": False, "estado": actual, "error": None if actual else "Sin conexión."})
        bd.registrar_venta({"id": bd.nuevo_id("bv"), "dueno": email, "items": p["items"], "total": p["total"],
                            "medio_pago": "saldo"}, descuentos)
        _push(p["cliente"], "Pedido entregado ✅", "¡Que lo disfrutes! Ya estaba pagado con tu saldo 💳", destino="cliente", dueno=email)
        puntos = int(round(p["total"]))
        if puntos > 0:  # FIDELIDAD: pagar con saldo suma puntos, se acreditan al ENTREGARSE
            _push(p["cliente"], "¡Te llegaron puntos! ⭐",
                  f"Ganaste +{puntos} puntos Pichangol por tu pedido pagado con saldo. Canjéalos como descuento en tu próxima reserva online.",
                  tipo="puntos")
        return JSONResponse({"ok": True, "mensaje": "Entregado ✅ · ya estaba pagado con saldo (el monto entra a tu «por recibir»)"})
    medio = str(body.get("medio") or "")
    if medio not in bd.MEDIOS_CAJA + ("cuenta",):
        return JSONResponse({"ok": False, "error": "Elige cómo pagó."}, status_code=400)
    cfg = bd.config_de(email)
    if medio == "cuenta" and not (cfg["permite_cuenta"] and p["cliente"]):
        return JSONResponse({"ok": False, "error": "La cuenta abierta no está activa."}, status_code=409)
    ok, actual = bd.cambiar_estado_si(pid, "entregado", desde="confirmado", dueno=email)
    if not ok:
        if actual == "entregado":
            return JSONResponse({"ok": False, "estado": actual, "aviso": {"titulo": "Ya estaba cobrado",
                                 "mensaje": "Este pedido ya fue entregado y cobrado desde otro equipo. No se registró una segunda venta."}})
        if actual is None:
            return JSONResponse({"ok": False, "error": "Sin conexión: no se pudo registrar. Vuelve a intentarlo."}, status_code=502)
        return JSONResponse({"ok": False, "estado": actual})
    if medio == "cuenta":
        res, aviso = _anotar(email, p["cliente"], p["cliente_nombre"], p["items"], p["moneda"], cfg["tope_cuenta"])
        if res is None:
            bd.forzar_estado(pid, "confirmado", email)
            if aviso:
                return JSONResponse({"ok": False, "aviso": aviso}, status_code=409)
            return JSONResponse({"ok": False, "error": "No se pudo anotar a la cuenta. Vuelve a intentarlo."}, status_code=502)
        bd.descontar_stock(descuentos, email)
        _push(p["cliente"], "Anotado en tu cuenta 📒",
              f"Tu pedido ({bd.resumen(p['items'])}) quedó en tu cuenta. Llevas {_m(res['moneda'], res['total'])}; pagas al salir.",
              destino="cliente", dueno=email)
        return JSONResponse({"ok": True, "mensaje": f"Anotado a la cuenta de {res['cliente_nombre']} 📒"})
    venta = {"id": bd.nuevo_id("bv"), "dueno": email, "items": p["items"],
             "total": 0.0 if medio == "cortesia" else p["total"], "medio_pago": medio}
    if not bd.registrar_venta(venta, descuentos):
        bd.forzar_estado(pid, "confirmado", email)  # la venta no entró: se puede volver a cobrar
        return JSONResponse({"ok": False, "error": "No se pudo registrar la venta. Vuelve a intentarlo."}, status_code=502)
    _push(p["cliente"], "Pedido entregado ✅", "¡Que lo disfrutes! Gracias por pedir en la bodega.", destino="cliente", dueno=email)
    return JSONResponse({"ok": True, "mensaje": "Entregado ✅ · venta registrada y stock actualizado"})


# ── Cuenta abierta: cobrar y cerrar ───────────────────────────────────────────

@router.post(BASE + "/cuenta/{cid}/cerrar")
def cerrar_cuenta(request: Request, cid: str, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """= `_cerrarCuenta`: cobra TODO junto y recién registra UNA venta (el stock ya bajó)."""
    email, err = _dueno_json(request)
    if err is not None:
        return err
    medio = str(body.get("medio") or "")
    if medio not in bd.MEDIOS_CAJA:
        return JSONResponse({"ok": False, "error": "Elige cómo pagó."}, status_code=400)
    c = bd.cuenta_de(cid, email) if _ID_OK.match(cid or "") else None
    if c is None:
        return JSONResponse({"ok": False, "error": "Cuenta no encontrada."}, status_code=404)
    if not bd.cerrar_cuenta_si(cid, medio, email):
        return JSONResponse({"ok": False, "aviso": {"titulo": "Ya estaba cerrada",
                             "mensaje": "Esta cuenta ya fue cerrada desde otro equipo. No se cobró dos veces."}})
    ok = bd.registrar_venta({"id": bd.nuevo_id("bv"), "dueno": email, "items": c["items"],
                             "total": 0.0 if medio == "cortesia" else c["total"], "medio_pago": medio}, {})
    if c["cliente"]:
        _push(c["cliente"], "Cuenta cerrada ✅",
              "Tu cuenta quedó como cortesía del local. ¡Gracias!" if medio == "cortesia"
              else f"Pagaste {_m(c['moneda'], c['total'])}. ¡Gracias, vuelve pronto!", destino="cliente", dueno=email)
    return JSONResponse({"ok": True, "mensaje": "Cuenta cerrada y venta registrada ✅" if ok
                         else "Cuenta cerrada, pero la venta no entró al reporte (sin conexión). Revisa el reporte más tarde."})


JS = r"""
(function(){
var B=BOD, ticket={}, catSel='Todo', q='';
function $(id){return document.getElementById(id)}
function esc(s){return String(s==null?'':s).replace(/[&<>'"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]})}
function fmt(m,v){return (m||B.sim)+' '+Number(v||0).toFixed(2)}
function prod(id){for(var i=0;i<B.prods.length;i++)if(B.prods[i].id===id)return B.prods[i];return null}
function total(){var t=0;for(var id in ticket){var p=prod(id);if(p)t+=p.precio*ticket[id]}return t}
function items(){var n=0;for(var id in ticket)n+=ticket[id];return n}
async function post(url,body,msg){pcgCargando(msg||'Guardando…',{demora:250});try{var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});var j={};try{j=await r.json()}catch(e){}pcgCargando(false);return j}catch(e){pcgCargando(false);return {ok:false,error:'Revisa tu conexión e intenta.'}}}
async function tras(j,okMsg){if(j.ok){try{sessionStorage.setItem('bod_msg',j.mensaje||okMsg||'Listo ✅')}catch(e){}pcgRecargar();return true}
  if(j.aviso){await pcgAvisar({titulo:j.aviso.titulo,mensaje:j.aviso.mensaje,icono:'ℹ️'});pcgRecargar();return false}
  if(j.estado){pcgRecargar('Actualizando…');return false}
  pcgToast(j.error||'No se pudo guardar.');return false}
try{var m=sessionStorage.getItem('bod_msg');if(m){sessionStorage.removeItem('bod_msg');setTimeout(function(){pcgToast(m)},200)}}catch(e){}
// Modal genérico de opciones (hoja de medios, cuentas, clientes): sin diálogos nativos del navegador.
var modal=$('bModal'), resolver=null;
function abrirModal(tit,html){$('bModalCuerpo').onclick=null;$('bModalTit').textContent=tit;$('bModalCuerpo').innerHTML=html;modal.classList.add('open')}
function cerrarModal(v){modal.classList.remove('open');var r=resolver;resolver=null;if(r)r(v)}
function opciones(tit,ops,extra){return new Promise(function(res){resolver=res;abrirModal(tit,"<section><div class='bopc'>"+ops.map(function(o,i){return "<button type='button' data-op='"+i+"'>"+(o.foto?"<img class='av' src='"+esc(o.foto)+"' alt='' referrerpolicy='no-referrer'>":(o.ini?"<span class='av'>"+esc(o.ini)+"</span>":"<span class='ic'>"+(o.ico||'')+"</span>"))+"<span><b>"+esc(o.t)+"</b>"+(o.sub?"<small>"+esc(o.sub)+"</small>":"")+"</span></button>"}).join('')+"</div>"+(extra||'')+"</section>");
  $('bModalCuerpo').querySelectorAll('[data-op]').forEach(function(b){b.onclick=function(){cerrarModal(ops[+b.dataset.op].v)}})})}
document.addEventListener('click',function(ev){var c=ev.target.closest('[data-cerrar-modal]');if(c){var m=c.closest('.modal');if(m===modal)cerrarModal(null);else m.classList.remove('open')}
  var a=ev.target.closest('[data-abrir]');if(a)$(a.dataset.abrir).classList.add('open');
  var cp=ev.target.closest('[data-copiar]');if(cp){(navigator.clipboard?navigator.clipboard.writeText(cp.dataset.copiar):Promise.reject()).then(function(){pcgToast('Enlace copiado.')},function(){pcgToast(cp.dataset.copiar)})}});
document.querySelectorAll('.modal').forEach(function(m){m.addEventListener('click',function(ev){if(ev.target===m){if(m===modal)cerrarModal(null);else m.classList.remove('open')}})});
document.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&modal.classList.contains('open'))cerrarModal(null)});
function mediosPago(extraCuenta){var o=[{v:'efectivo',ico:'💵',t:'Efectivo'},{v:'yape',ico:'📱',t:B.medioLocal},{v:'cortesia',ico:'🎁',t:'Cortesía (no se cobra)'}];if(extraCuenta)o.push(extraCuenta);return o}

// ── CAJA ──
function pintarCaja(){
  var grid=document.querySelectorAll('.bprod'),vis=0;
  grid.forEach(function(b){var ok=(catSel==='Todo'||b.dataset.cat===catSel)&&(!q||b.dataset.n.indexOf(q)>=0);b.style.display=ok?'':'none';if(ok)vis++;
    var n=ticket[b.dataset.id]||0,c=b.querySelector('.cant');b.classList.toggle('en',n>0);c.hidden=!n;c.textContent=n});
  if($('bSinRes'))$('bSinRes').hidden=vis>0;
  var t=$('bTicket');if(!t)return;var ids=Object.keys(ticket);
  if($('bTip'))$('bTip').hidden=ids.length>0;
  if(!ids.length){t.innerHTML='';$('bBarra').classList.remove('on');return}
  var h="<div class='bticket'><div style='display:flex;justify-content:space-between;align-items:center'><b>Ticket · "+ids.length+" línea(s)</b><button type='button' class='btn sec' id='bVaciar' style='padding:6px 12px'>Vaciar</button></div>";
  ids.forEach(function(id){var p=prod(id);if(!p)return;h+="<div class='ln'><div><b>"+esc(p.nombre)+"</b><small>"+esc(fmt(p.moneda,p.precio))+" c/u</small></div><div class='sub3'><span class='bstep'><button type='button' data-menos='"+esc(id)+"' aria-label='Quitar uno'>−</button><span>"+ticket[id]+"</span><button type='button' data-mas='"+esc(id)+"' aria-label='Sumar uno'>+</button></span>"
    +"<b style='min-width:78px;text-align:right'>"+esc(fmt(p.moneda,p.precio*ticket[id]))+"</b><button type='button' data-quitar='"+esc(id)+"' aria-label='Quitar' style='border:0;background:none;cursor:pointer;color:var(--tenue)'>✕</button></div></div>"});
  h+="<div class='btot'><span class='sub' style='margin:0;font-weight:800'>TOTAL</span><b>"+esc(fmt(B.sim,total()))+"</b></div></div>";
  t.innerHTML=h;
  $('bCobrar').textContent='Cobrar '+fmt(B.sim,total())+' · '+items()+' ítem(s)';$('bBarra').classList.add('on');
}
function sumar(id,d){var p=prod(id);if(!p)return;var n=(ticket[id]||0)+d;if(d>0&&n>p.stock){pcgToast('Solo te quedan '+p.stock+' de '+p.nombre+'.');return}if(n<=0)delete ticket[id];else ticket[id]=n;pintarCaja()}
if(B.tab==='caja'&&$('bTicket')){
  document.addEventListener('click',function(ev){var b=ev.target.closest('.bprod');if(b&&!b.disabled){sumar(b.dataset.id,1);return}
    var m=ev.target.closest('[data-menos]');if(m){sumar(m.dataset.menos,-1);return}var s=ev.target.closest('[data-mas]');if(s){sumar(s.dataset.mas,1);return}
    var x=ev.target.closest('[data-quitar]');if(x){delete ticket[x.dataset.quitar];pintarCaja();return}
    if(ev.target.id==='bVaciar'){ticket={};pintarCaja();return}
    var c=ev.target.closest('.bcats .chip');if(c){catSel=c.dataset.cat;document.querySelectorAll('.bcats .chip').forEach(function(z){z.classList.toggle('sel',z===c)});pintarCaja()}});
  $('bBusca').addEventListener('input',function(){q=this.value.trim().toLowerCase();pintarCaja()});
  $('bCobrar').addEventListener('click',cobrar);
}
async function cobrar(){if(!Object.keys(ticket).length)return;
  var cta=B.permiteCuenta?{v:'cuenta',ico:'📒',t:'A la cuenta (paga al salir)',sub:B.abiertas.length?B.abiertas.length+' cuenta(s) abierta(s)':'Abrir cuenta a un cliente registrado'}:null;
  var medio=await opciones('Cobrar '+fmt(B.sim,total())+' — ¿cómo pagó?',mediosPago(cta));if(!medio)return;
  var its=Object.keys(ticket).map(function(id){return {id:id,cantidad:ticket[id]}}),body={items:its,medio:medio};
  if(medio==='cuenta'){var cli=await elegirCuenta();if(!cli)return;body.cliente=cli}
  await tras(await post('/anfitrion/bodega/vender',body,'Registrando venta…'))}
async function elegirCuenta(){
  if(B.abiertas.length){var ops=B.abiertas.map(function(c){return {v:c.cliente,ico:'📒',t:c.nombre||c.cliente,sub:'Lleva '+fmt(c.moneda,c.total)}});ops.push({v:'__nueva',ico:'➕',t:'Abrir cuenta nueva',sub:'A un cliente registrado del local'});
    var v=await opciones('¿A la cuenta de quién?',ops);if(v!=='__nueva')return v}
  return await elegirCliente()}
async function elegirCliente(){pcgCargando('Buscando tus clientes…',{demora:250});var j={};try{j=await (await fetch('/anfitrion/bodega/clientes.json')).json()}catch(e){}pcgCargando(false);
  var lista=(j&&j.clientes)||[];
  if(!lista.length){await pcgAvisar({titulo:'Sin clientes registrados',mensaje:'La cuenta abierta es solo para clientes registrados (así sabes quién te debe). Aparecerán aquí cuando reserven en tus canchas con la app.',icono:'🪪'});return null}
  return new Promise(function(res){resolver=res;
    abrirModal('Abrir cuenta · ¿para quién?',"<section><input class='bbusca' id='bCliQ' type='search' placeholder='🔎 Buscar por nombre…' autocomplete='off'><div class='bopc' id='bCliL' style='margin-top:10px'></div></section>");
    function pinta(f){f=(f||'').toLowerCase();var vis=lista.filter(function(c){return !f||c.nombre.toLowerCase().indexOf(f)>=0||c.email.indexOf(f)>=0});
      $('bCliL').innerHTML=vis.length?vis.map(function(c,i){return "<button type='button' data-cli='"+esc(c.email)+"'>"+(c.foto?"<img class='av' src='"+esc(c.foto)+"' alt='' referrerpolicy='no-referrer'>":"<span class='av'>"+esc((c.nombre||'?').charAt(0).toUpperCase())+"</span>")+"<span><b>"+esc(c.nombre)+"</b>"+(c.hoy?"<small style='color:var(--esmeralda)'>Con reserva hoy · está en el local</small>":"")+"</span></button>"}).join(''):"<p class='sub' style='text-align:center'>Nadie coincide con esa búsqueda.</p>";
      $('bCliL').querySelectorAll('[data-cli]').forEach(function(b){b.onclick=function(){cerrarModal(b.dataset.cli)}})}
    pinta('');$('bCliQ').addEventListener('input',function(){pinta(this.value.trim())})})}

// ── PRODUCTOS ──
function editor(p){var nuevo=!p;p=p||{id:'',nombre:'',categoria:'Bebidas',precio:'',stock:0,stock_min:2};var cat=p.categoria;
  function sugs(){return (B.sug[cat]||[]).map(function(s){return "<button type='button' class='chip' data-sug='"+esc(s)+"'>"+esc(s)+"</button>"}).join('')}
  var h="<section class='bform'><label class='l'>Categoría</label><div class='chips' id='bfCat'>"+B.cats.map(function(c){return "<button type='button' class='chip"+(c===cat?' sel':'')+"' data-c='"+esc(c)+"'>"+esc(c)+"</button>"}).join('')+"</div>"
   +"<label class='l' for='bfNom'>Producto</label><input type='text' id='bfNom' maxlength='60' value='"+esc(p.nombre)+"' placeholder='Toca una sugerencia o escribe la marca'><div class='bsug' id='bfSug'>"+sugs()+"</div>"
   +"<label class='l' for='bfPre'>Precio de venta</label><div class='pre'><span>"+esc(p.moneda||B.sim)+"</span><input type='number' id='bfPre' min='0' step='0.10' inputmode='decimal' value='"+(p.precio?Number(p.precio).toFixed(2):'')+"'></div>"
   +"<div class='fila'><span class='l'>Stock actual</span><span class='bstep'><button type='button' data-st='bfSt' data-d='-1'>−</button></span><input type='number' id='bfSt' min='0' max='99999' value='"+(p.stock||0)+"'><span class='bstep'><button type='button' data-st='bfSt' data-d='1'>+</button></span></div>"
   +"<div class='fila'><span class='l'>Avisarme cuando queden</span><span class='bstep'><button type='button' data-st='bfMin' data-d='-1'>−</button></span><input type='number' id='bfMin' min='0' max='99999' value='"+(p.stock_min==null?2:p.stock_min)+"'><span class='bstep'><button type='button' data-st='bfMin' data-d='1'>+</button></span></div>"
   +"<div class='err' id='bfErr'></div><div class='acciones' style='justify-content:space-between;margin-top:12px'>"+(nuevo?"<span></span>":"<button type='button' class='btn sec' id='bfDel' style='color:var(--rojo,#C0392B)'>Eliminar</button>")
   +"<span style='display:flex;gap:8px'><button type='button' class='btn sec' data-cerrar-modal>Cancelar</button><button type='button' class='btn' id='bfOk'>Guardar</button></span></div></section>";
  resolver=null;abrirModal(nuevo?'Nuevo producto':'Editar producto',h);
  var cu=$('bModalCuerpo');
  cu.onclick=async function(ev){var c=ev.target.closest('[data-c]');if(c){cat=c.dataset.c;cu.querySelectorAll('#bfCat .chip').forEach(function(z){z.classList.toggle('sel',z===c)});$('bfSug').innerHTML=sugs();return}
    var s=ev.target.closest('[data-sug]');if(s){$('bfNom').value=s.dataset.sug;return}
    var st=ev.target.closest('[data-st]');if(st){var i=$(st.dataset.st),v=(parseInt(i.value)||0)+(+st.dataset.d);i.value=v<0?0:v;return}
    if(ev.target.id==='bfDel'){if(!await pcgConfirmar({titulo:'Eliminar producto',mensaje:'¿Quitar "'+p.nombre+'" de tu bodega?',confirmar:'Eliminar',destructivo:true}))return;
      var j=await post('/anfitrion/bodega/producto/'+encodeURIComponent(p.id)+'/eliminar',{},'Eliminando…');if(j.ok){modal.classList.remove('open');tras({ok:true,mensaje:'Producto eliminado.'})}else $('bfErr').textContent=j.error||'No se pudo eliminar.';return}
    if(ev.target.id==='bfOk'){var n=$('bfNom').value.trim(),pr=parseFloat(($('bfPre').value||'').replace(',','.'));
      if(!n){$('bfErr').textContent='Ponle nombre al producto.';return}if(!(pr>0)){$('bfErr').textContent='Ponle el precio de venta.';return}
      var j2=await post('/anfitrion/bodega/producto',{id:p.id,nombre:n,categoria:cat,precio:pr,stock:parseInt($('bfSt').value)||0,stock_min:parseInt($('bfMin').value)||0},'Guardando…');
      if(j2.ok){modal.classList.remove('open');tras({ok:true,mensaje:'Producto guardado ✅'})}else $('bfErr').textContent=j2.error||'No se pudo guardar.'}}}
document.addEventListener('click',function(ev){if(ev.target.closest('[data-nuevo]')){editor(null);return}
  var f=ev.target.closest('[data-foto]');if(f){ev.stopPropagation();if(!B.storage){pcgToast('Las fotos se suben desde la app en este ambiente.');return}fotoDe=f.dataset.foto;$('bInFoto').click();return}
  var ed=ev.target.closest('[data-editar]');if(ed)editor(prod(ed.dataset.editar))},true);
var fotoDe=null;
function comprimir(file){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var M=900,w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
if($('bInFoto'))$('bInFoto').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f||!fotoDe)return;pcgCargando('Subiendo foto…');
  try{var blob=await comprimir(f);var r=await fetch('/anfitrion/bodega/producto/'+encodeURIComponent(fotoDe)+'/foto',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});var j=await r.json();pcgCargando(false);
    if(j.ok){tras({ok:true,mensaje:'Foto actualizada 📷'})}else pcgToast(j.error||'No se pudo subir la foto.')}catch(e){pcgCargando(false);pcgToast('No se pudo subir la foto. Revisa tu conexión.')}});

// ── CONFIG (switches, zonas, tope) ──
document.addEventListener('click',async function(ev){var sw=ev.target.closest('[data-sw]');if(sw){var v=!sw.classList.contains('on'),b={};b[sw.dataset.sw]=v;var j=await post('/anfitrion/bodega/config',b);
    if(j.ok){sw.classList.toggle('on',v);sw.setAttribute('aria-checked',v?'true':'false');if(sw.dataset.sw==='permite_cuenta')pcgRecargar()}else if(j.aviso){await pcgAvisar({titulo:j.aviso.titulo,mensaje:j.aviso.mensaje,icono:'🗄️'})}else pcgToast(j.error||'No se pudo guardar.');return}
  var t=ev.target.closest('[data-tope]');if(t){var j2=await post('/anfitrion/bodega/config',{tope_cuenta:parseFloat(t.dataset.tope)});if(j2.ok){document.querySelectorAll('[data-tope]').forEach(function(z){z.classList.toggle('sel',z===t)});pcgToast('Tope guardado.')}else pcgToast(j2.error||'No se pudo guardar.');return}
  if(ev.target.closest('[data-zonas]'))zonas()});
function zonas(){var zs=B.zonas.slice();
  function pinta(){$('bzL').innerHTML=zs.map(function(z,i){return "<span class='chip sel'>"+esc(z)+(zs.length>1?" <button type='button' data-zq='"+i+"' aria-label='Quitar' style='border:0;background:none;cursor:pointer;font-weight:900'>✕</button>":"")+"</span>"}).join('')}
  resolver=null;abrirModal('Zonas de entrega 📍',"<section class='bform'><p class='sub' style='margin:0 0 12px'>El cliente elige a dónde le llevas su pedido.</p><div class='chips' id='bzL'></div>"
    +"<label class='l' for='bzN'>Agregar zona</label><div style='display:flex;gap:8px'><input type='text' id='bzN' maxlength='20' placeholder='Ej.: Cancha 3'><button type='button' class='btn sec' id='bzAdd'>＋</button></div>"
    +"<div class='acciones' style='justify-content:flex-end;margin-top:14px'><button type='button' class='btn' id='bzOk'>Guardar</button></div></section>");pinta();
  $('bModalCuerpo').onclick=async function(ev){var qz=ev.target.closest('[data-zq]');if(qz){zs.splice(+qz.dataset.zq,1);pinta();return}
    if(ev.target.id==='bzAdd'){var z=$('bzN').value.trim();if(z&&zs.indexOf(z)<0){zs.push(z);$('bzN').value='';pinta()}return}
    if(ev.target.id==='bzOk'){var j=await post('/anfitrion/bodega/config',{zonas:zs});if(j.ok){modal.classList.remove('open');tras({ok:true,mensaje:'Zonas guardadas 📍'})}else pcgToast(j.error||'No se pudo guardar.')}}}

// ── PEDIDOS ──
document.addEventListener('click',async function(ev){var r=ev.target.closest('[data-resp]');if(r){r.disabled=true;var j=await post('/anfitrion/bodega/pedido/'+encodeURIComponent(r.dataset.resp)+'/responder',{confirmar:r.dataset.v==='1'});
    await tras(j,r.dataset.v==='1'?'Pedido confirmado 🏃':'Pedido rechazado');r.disabled=false;return}
  var d=ev.target.closest('[data-entregar]');if(d){var body={};
    if(d.dataset.pagado!=='1'){var ab=null;for(var i=0;i<B.abiertas.length;i++)if(B.abiertas[i].cliente===d.dataset.cli)ab=B.abiertas[i];var tot=parseFloat(d.dataset.total)||0;
      var cabe=B.permiteCuenta&&d.dataset.cli&&(B.tope<=0||((ab?ab.total:0)+tot<=B.tope+1e-9));
      var m=await opciones('Entregado a la '+d.dataset.zona+' · cobrar '+fmt(d.dataset.mon,tot)+' — ¿cómo pagó?',mediosPago(cabe?{v:'cuenta',ico:'📒',t:'A la cuenta (paga al salir)',sub:ab?'Lleva '+fmt(ab.moneda,ab.total):'Le abre su cuenta en la bodega'}:null));if(!m)return;body.medio=m}
    d.disabled=true;await tras(await post('/anfitrion/bodega/pedido/'+encodeURIComponent(d.dataset.entregar)+'/entregar',body,d.dataset.pagado==='1'?'Verificando pago…':'Registrando…'));d.disabled=false;return}
  var c=ev.target.closest('[data-cerrar]');if(c){var m2=await opciones('Cerrar la cuenta de '+c.dataset.nom+' · cobrar '+fmt(c.dataset.mon,c.dataset.total)+' — ¿cómo pagó?',mediosPago(null));if(!m2)return;
    await tras(await post('/anfitrion/bodega/cuenta/'+encodeURIComponent(c.dataset.cerrar)+'/cerrar',{medio:m2},'Registrando…'))}});
// Respaldo del push: en Pedidos, sondeo cada 20 s; si algo cambió (y no hay un diálogo abierto) se refresca solo.
if(B.tab==='pedidos'){var firma=JSON.stringify(B.firma);setInterval(async function(){if(document.hidden||document.querySelector('.modal.open,.pcg-dlg.open'))return;
  try{var j=await (await fetch('/anfitrion/bodega/pedidos.json')).json();if(j.ok&&JSON.stringify(j.firma)!==firma){firma=JSON.stringify(j.firma);pcgRecargar('Nuevo pedido…')}}catch(e){}},20000)}
})();
"""
