"""MODO ANFITRIÓN en la web (calcado de airbnb.com/hosting): el panel del
DUEÑO de canchas con su sesión de Google.

Secciones (pestañas de la cabecera, como Airbnb): **Hoy** (reservas de hoy,
mañana, próximos 7 días y las de efectivo por cobrar), **Calendario** (agenda
semanal por cancha: reservas, bloqueos y turnos libres), **Reservas** (todas,
agrupadas por día), **Ingresos** (saldo, saldo de regalo, por recibir,
liquidaciones y movimientos del backend) y **Canchas** (sus locales con su
ficha pública). Sin canchas a su nombre → onboarding con "Registrar mi
cancha" (el registro y el reclamo también se hacen aquí). Editar la cancha y
el local, reserva manual, bloqueos y marcar pagado se hacen aquí con el mismo
formulario y las mismas filas que el app; el calendario respeta las REGLAS DE
RESERVA del club (`reservas.reglas.cancha_del_dia`). Cobros del club, Pagos
por confirmar y el editor de Reglas viven en `web/anfitrion_cobros_club.py`.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, timedelta

import config
from starlette.concurrency import run_in_threadpool
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

_JSON_INVALIDO = object()


def _leer_json(v):
    """El wrapper async ya leyó el JSON en el event loop; aquí solo se valida (la lógica corre en el threadpool, sin frenar el loop)."""
    if v is _JSON_INVALIDO:
        raise ValueError("json inválido")
    return v
from urllib.parse import quote
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import paises
import servicios_extra as _se
import fidelidad as _fid
from db.store import stores
from propiedad import fotos_locales, fotos_reclamo, reclamos
from reservas import reglas as _reglas
from web import almacen, catalogos, datos, horarios, iconos, permisos, sesion, ui
from web import vista_anfitrion as va
from web.router import (PLAY_URL, _deporte, _deportes_de, _fotos, _fotos_crudas, _maps, _moneda_de, _pais_de,
                        _zona, e)

router = APIRouter(tags=["web-anfitrion"])

# Pestañas de la sección "Mis canchas" (como airbnb.com/hosting).
SECCIONES = [("hoy", "Hoy", "/anfitrion/mis-canchas", "📅"), ("calendario", "Calendario", "/anfitrion/calendario", "🗓️"),
             ("reservas", "Reservas", "/anfitrion/reservas", "📋"), ("ingresos", "Ingresos", "/anfitrion/ingresos", "💰"),
             ("canchas", "Canchas", "/anfitrion/canchas", "🏟️")]

# Menú del modo anfitrión: los mismos módulos del app (ícono en círculo de
# color, título, descripción y chevron), AGRUPADOS por tema. "Mi club" va
# arriba con los cobros y las reglas. Tupla: (clave, título, descripción,
# color, ícono, enlace, hecho_en_web).
GRUPOS_MENU = [
    ("Mi club", [
        ("mis-canchas", "Mis canchas", "Registra y administra: canchas, agenda, reservas, cuenta", "#3056ED", "🏬", "/anfitrion/mis-canchas", True),
        ("cobros-club", "Cobros del club", "Tu Culqi, tus medios de pago manuales y la comisión", "#3056ED", "💸", "/anfitrion/cobros-club", True),
        ("pagos-por-confirmar", "Pagos por confirmar", "Comprobantes de Yape, Plin o transferencia que debes revisar", "#946200", "🧾", "/anfitrion/pagos-por-confirmar", True),
        ("encargados", "Encargados", "Invita a tu recepción a operar el local: agenda, reservas y pagos", "#2F6FDE", "👥", "/anfitrion/encargados", True),
        ("reglas", "Reglas de reserva", "Horario por día, días cerrados, precios por franja y cancelación", "#2F6FDE", "⚙️", "/anfitrion/reglas", True),
        ("disponibilidad", "Disponibilidad", "Abre o cierra turnos de tus canchas", "#7E98FF", "🟢", "/anfitrion/disponibilidad", True),
        ("fijas", "Reservas fijas", "Pensionados: el mismo día y hora, cada semana", "#2442C4", "🔁", "/anfitrion/fijas", True),
    ]),
    ("Negocio", [
        ("reportes", "Reportes", "Resumen, ocupación, cobros y cancelaciones", "#2F6FDE", "📊", "/anfitrion/reportes", True),
        ("caja", "Caja del día", "Cobrado, por cobrar y cierre de caja", "#3056ED", "💵", "/anfitrion/caja", True),
        ("clientes", "Clientes", "Tu base de clientes: frecuentes, VIP, en riesgo y deudores", "#7B61FF", "👥", "/anfitrion/clientes", True),
        ("llenar", "Llenar cancha", "Horas libres de hoy y mañana: ponles promo y avisa a tus clientes", "#F28C28", "📣", "/anfitrion/llenar", True),
        ("recordatorios", "Recordar reservas", "Avisa a tus clientes de hoy y mañana por chat o WhatsApp", "#2F6FDE", "🔔", "/anfitrion/recordatorios", True),
        ("bonos", "Bonos", "Packs de horas prepagadas de tu local", "#E07A3F", "🎟️", "/anfitrion/bonos", True),
        ("campeonatos", "Mis campeonatos", "Organiza torneos (fútbol, tenis…), invita y sortea", "#D4B048", "🏆", "/anfitrion/campeonatos", True),
    ]),
    ("Academia", [
        ("academia", "Mi academia", "Soy profe: alumnos, cuotas y cobros", "#E07A3F", "🎓", "/anfitrion/academia", True),
        ("cobros", "Cobros de academia", "Quién debe, recordatorios y cobro en efectivo", "#D4B048", "💳", "/anfitrion/cobros", True),
        ("plan-academia", "Plan Academia", "Tu suscripción: prueba gratis, precio fijo al mes y tus alumnos te pagan directo", "#742284", "🗓️", "/anfitrion/academia/plan", True),
    ]),
    ("Comercio", [
        ("tienda", "Mi tienda", f"Vende en el Marketplace {MARCA}: raquetas, pelotas y más", "#7B61FF", "🏪", "/anfitrion/tienda", True),
        ("bodega", "Mi bodega", "Caja rápida, stock, pedidos a la cancha y carta con QR (Pro)", "#E07A3F", "🧃", "/anfitrion/bodega", True),
    ]),
    ("Roles", [
        ("boleador", "Soy boleador", "Peloteo por turno: pon tu categoría, tu tarifa y dónde atiendes", "#3056ED", "🎾", "/anfitrion/boleador", True),
        ("verificador", "Verificador", "Rol de campo: visitas con foto, GPS y firma", "#3056ED", "🛡️", "/anfitrion/verificador", True),
    ]),
]
MENU = [it for _g, items in GRUPOS_MENU for it in items]


def _plan_academia_activo() -> bool:
    import academia_plan
    return academia_plan.es_suscripcion()


def _sim_de_iso(iso: str | None, por_defecto: str = "S/") -> str:
    """Símbolo de la moneda de UN movimiento (no la de la primera cancha)."""
    return {"PEN": "S/", "USD": "$", "BOB": "Bs"}.get((iso or "").upper(), por_defecto)


def _pendientes_vouchers(email: str) -> int:
    try:
        from web import cobro_directo_web as _cdw
        return _cdw.pendientes_de(email)
    except Exception:  # noqa: BLE001
        return 0


def _banner_cobros(email: str) -> str:
    """Mis canchas: cobros directos suspendidos por deuda de comisión y/o
    vouchers por revisar (la misma fuente que Cobros del club)."""
    try:
        from web import cobro_directo_web as _cdw
        est = _cdw.estado_club(email)
    except Exception:  # noqa: BLE001
        return ""
    out = ""
    com = est.get("comision") or {}
    if com.get("suspendido"):
        sim = {"PEN": "S/", "USD": "$", "BOB": "Bs"}.get(est.get("moneda"), "S/")
        out += va.aviso(f"<b>Tus cobros en línea están pausados.</b> Debes {e(sim)} {int(com.get('deuda_centimos') or 0) / 100.0:.2f} de comisiones. "
                        "Recarga tu saldo y se paga sola; el pago en la cancha sigue funcionando.", "bad",
                        "<a href='/mi-billetera#recargar'>Recargar saldo ›</a><a href='/anfitrion/cobros-club'>Ver cobros del club ›</a>", ico="billete")
    n = int(est.get("pendientes") or 0)
    if n:
        out += va.aviso(f"<b>{n} pago{'s' if n != 1 else ''} por confirmar.</b> Revisa los comprobantes antes de que venzan o la reserva se libera sola.",
                        "warn", "<a href='/anfitrion/pagos-por-confirmar'>Revisar ahora ›</a>", ico="recibo")
    return out


def _anf(cuerpo: str) -> str:
    """Envoltorio de toda página del modo anfitrión: sus estilos (y el alto
    táctil mínimo de 44 px) viven en `web/estilos_anfitrion.py`."""
    return f"<div class='anf-pag'>{cuerpo}</div>"


def _cabecera(seccion: str, ses: dict | None, tabs_visibles: bool = True) -> str:
    ocultas = permisos.tabs_ocultas(ses["email"]) if tabs_visibles and ses else frozenset()  # Recepción: sin Ingresos ni Canchas
    tabs = "".join(f"<a class='cat{' sel' if k == seccion else ''}' href='{href}'><span class='ico'>{ico}</span>{n}</a>"
                   for k, n, href, ico in SECCIONES if k not in ocultas) if tabs_visibles else ""
    return ui.cabecera(tabs=tabs, ses=ses, volver="/anfitrion", modo="anfitrion")


def _sesion_o_entrar(request: Request, volver: str):
    ses = sesion.de_request(request)
    if ses:
        return ses, None
    if sesion.activo():
        return None, _entrar(volver)
    cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
              "<h1 style='font-size:22px'>Modo anfitrión</h1>"
              "<p class='sub'>En esta web aún no está activo el inicio de sesión. Administra tus canchas desde la app.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir {MARCA} en Google Play</a></div></div>")
    return None, ui.shell("Modo anfitrión", _anf(cuerpo), sesion=None)


@router.get("/anfitrion", response_class=HTMLResponse)
def pagina_menu(request: Request) -> HTMLResponse:
    """Inicio del modo anfitrión = tablero del diseñador (`web/anfitrion_inicio.py`)."""
    ses, resp = _sesion_o_entrar(request, "/anfitrion")
    if resp is not None:
        return resp
    from web import anfitrion_encargados as _enc
    enc_html, _ocultar, n_vouchers = _enc.para_menu(ses["email"])  # invitaciones + locales donde ayuda
    # Rediseño (16-nov-2026): el inicio es un TABLERO; los módulos viven en la barra
    # (`web/nav_anfitrion.py`). Las invitaciones de encargado van arriba del tablero.
    from web import anfitrion_inicio
    return anfitrion_inicio.render(ses, enc_html, n_vouchers, request.query_params.get("cancha", ""))


def _contexto(request: Request, volver: str, seccion: str = "hoy", sin_canchas_ok: bool = False, accion: str = ""):
    """(sesión, canchas del dueño) o una respuesta de redirección/onboarding.
    Sin canchas, cada pestaña muestra la bienvenida CON SU pestaña marcada (antes
    todas pintaban "Hoy" y parecía que el clic no hacía nada); [sin_canchas_ok]
    deja pasar a las que sirven igual sin canchas (Ingresos: un organizador de
    torneos o una academia también tiene plata por recibir). Con [accion]
    (`web/permisos.py`) también entran las canchas de los locales donde el
    correo es ENCARGADO; sin ella son solo las del dueño, y quien solo es
    encargado ve "tu rol no incluye esta sección" (403)."""
    ses, resp = _sesion_o_entrar(request, volver)
    if resp is not None:
        return None, None, resp
    if accion:
        canchas = permisos.canchas_para(ses["email"], accion)
    else:
        canchas = datos.canchas_de_dueno(ses["email"])
        if not canchas and permisos.es_solo_encargado(ses["email"]):
            from web import anfitrion_encargados as _enc
            return ses, [], _enc.sin_permiso(ses, seccion)
    if not canchas and not sin_canchas_ok:
        return ses, [], _onboarding(ses, seccion)
    return ses, canchas, None


_INTRO_SIN_CANCHAS = {
    "hoy": "Con esta cuenta todavía no tienes canchas registradas.",
    "calendario": "Tu calendario aparecerá aquí cuando registres tu primera cancha: turnos, reservas y bloqueos por semana.",
    "reservas": "Aquí verás las reservas de tus canchas en cuanto registres la primera.",
    "canchas": "Todavía no tienes canchas a tu nombre. Registra tu local y aquí podrás editarlo, agregar canchas y ver su ficha pública.",
}
_TITULO_SECCION = {"hoy": "Mis canchas", "calendario": "Calendario", "reservas": "Reservas", "ingresos": "Ingresos", "canchas": "Canchas"}


def _onboarding(ses: dict, seccion: str = "hoy") -> HTMLResponse:
    """Como "Conviértete en anfitrión" de Airbnb: el dueño aún no tiene canchas
    a su nombre; el registro (reclamo + verificación) se hace aquí o en el app."""
    intro = _INTRO_SIN_CANCHAS.get(seccion, _INTRO_SIN_CANCHAS["hoy"])
    titulo = _TITULO_SECCION.get(seccion, "Modo anfitrión")
    nombre = (ses.get("nombre") or ses.get("email") or "").split(" ")[0]
    cta = (f"<div class='mc-vacio-acc'><a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a>"
           f"<a class='btn sec' href='{PLAY_URL}' rel='noopener'>O desde la app</a></div>")
    cuerpo = (va.cabecera(titulo, f"Hola, {nombre}. {intro}")
              + va.panel(va.vacio("cancha", "Registra tu primera cancha",
                                  f"En {MARCA} tu cancha recibe reservas y pagos en línea, y tú la administras desde la app y desde aquí.", cta))
              + va.pasos([("edificio", "1. Regístrala", "Aquí mismo o desde la app: datos, ubicación, fotos y canchas."),
                          ("escudo", "2. La verificamos", "El equipo revisa tu reclamo con tus fotos y la ubicación del local."),
                          ("calendario", "3. Recibe reservas", "Pagos en línea, agenda y cobros aquí y en la app.")])
              + "<p class='mc-nota-c'>¿Ya registraste tu cancha con otro correo? Inicia sesión aquí con ese mismo correo de Google.</p>")
    return ui.shell(titulo, _anf(va.vista(cuerpo, "vmc")), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión · {MARCA}")


def _hoy(canchas: list[dict]) -> date:
    return horarios.ahora_local(_pais_de(canchas[0]) if canchas else "PE").date()


def _tarjeta_res(r: dict, c: dict | None, hoy: date) -> str:
    from web.anfitrion_negocio import es_noshow, grupo_medio  # filtro Online/Efectivo/Manual y no-show (reservas_dueno_screen)
    sim = r.get("moneda") or (c and _moneda_de(c)[0]) or "S/"
    pagado = bool(r.get("pagado"))
    medio = str(r.get("medio_pago") or "")
    noshow = es_noshow(r)
    if noshow:
        pill = "<span class='pill bad'>No vino (no-show)</span>"
    elif pagado and medio in ("yape", "tarjeta"):
        pill = f"<span class='pill ok'>Pagada en línea · {medio}</span>"
    elif pagado:
        pill = "<span class='pill ok'>Cobrada</span>"
    else:
        pill = "<span class='pill warn'>Cobrar en la cancha</span>"
    jugador = (r.get("jugador") or r.get("usuario") or "Jugador").strip()
    tel = str(r.get("telefono") or "").strip()
    ini = (jugador[:1] or "?").upper()
    fecha = str(r.get("fecha") or "")
    dia = horarios.etiqueta_dia(fecha, hoy)
    dia = (dia + " · ") if dia in ("Hoy", "Mañana") else ""
    web = str(r.get("id") or "").startswith("web_")
    medio_txt = {"yape": "📱 Yape", "tarjeta": "💳 Tarjeta", "efectivo": "💵 Efectivo", "sena": "🔒 Seña", "manual": "✍️ Manual", "bono": "🎟️ Bono"}.get(medio, "")
    return (f"<div class='anf-res' data-fecha='{e(fecha)}' data-pagado='{1 if pagado else 0}' data-medio='{grupo_medio(r)}'>"
            f"<div class='anf-res-cab'><span class='hora'>{e(r.get('hora_inicio'))}–{e(r.get('hora_fin'))}</span>"
            f"<span class='sub anf-res-dia'>{e(dia)}{e(horarios.fecha_larga(fecha))}</span></div>"
            f"<div class='sub anf-res-cancha'>{e((c or {}).get('nombre') or 'Cancha')}</div>"
            f"<div class='quien'><span class='av' aria-hidden='true'>{e(ini)}</span><div><b>{e(jugador)}</b>"
            f"<div class='sub anf-res-det'>{e(r.get('usuario') or '')}{(' · ' + e(tel)) if tel else ''}{' · reserva web' if web else ''}</div></div>"
            f"<b class='anf-precio'>{e(sim)} {int(r.get('precio') or 0):.2f}</b></div>"
            f"<div class='acc'>{pill}" + (f"<span class='pill gris'>{medio_txt}</span>" if medio_txt and not (pagado and medio in ("yape", "tarjeta")) else "")
            + (f"<a class='btn sec' href='https://wa.me/{e(''.join(ch for ch in tel if ch.isdigit()))}' target='_blank' rel='noopener' aria-label='WhatsApp a {e(jugador)}'>💬 WhatsApp</a>" if tel else "")
            + ("" if noshow else (f"<button type='button' class='btn' data-pagar='{e(r.get('id'))}' data-v='1'>✅ Marcar pagada</button>" if not pagado
               else (f"<button type='button' class='btn sec' data-pagar='{e(r.get('id'))}' data-v='0'>↩ Marcar por cobrar</button>" if medio not in ("yape", "tarjeta") else "")))
            + ("" if noshow or (pagado and medio in ("yape", "tarjeta")) else f"<button type='button' class='btn sec' data-noshow='{e(r.get('id'))}'>No-show</button>")
            + "</div></div>")


@router.get("/anfitrion/mis-canchas", response_class=HTMLResponse)
def pagina_hoy(request: Request, cancha: str = "", desde: str = "", vista: str = "") -> HTMLResponse:
    """Mis canchas = vista UNIFICADA del rediseño (Frames 8-10): locales y
    canchas a la izquierda; tarjeta y calendario operativo de la elegida a la
    derecha. Reemplaza a las pestañas Hoy / Calendario / Canchas."""
    return _mis_canchas(request, _volver(request), "hoy", cancha=cancha, desde=desde, vista=vista)


@router.get("/anfitrion/reservas", response_class=HTMLResponse)
def pagina_reservas(request: Request) -> HTMLResponse:
    """Lista de reservas (próximas y pasadas 30 días) con filtro por forma de
    cobro y mini libro de caja; el calendario operativo vive en Mis canchas."""
    ses, canchas, resp = _contexto(request, "/anfitrion/reservas", "reservas", accion=permisos.VER_AGENDA)
    if resp is not None:
        return resp
    hoy = _hoy(canchas)
    por_id = {c["id"]: c for c in canchas}
    filas = datos.reservas_de_canchas([c["id"] for c in canchas], (hoy - timedelta(days=30)).isoformat(), (hoy + timedelta(days=60)).isoformat())
    prox = [r for r in filas if str(r.get("fecha")) >= hoy.isoformat()]
    pas = [r for r in filas if str(r.get("fecha")) < hoy.isoformat()][::-1]

    def bloque(titulo: str, lst: list[dict], vacio: str) -> str:
        if not lst:
            return f"<h2 class='mc-h2'>{titulo}</h2><p class='mc-vacio'>{vacio}</p>"
        out, dia = f"<h2 class='mc-h2'>{titulo} <small>· {len(lst)}</small></h2>", None
        for r in lst:
            f = str(r.get("fecha"))
            if f != dia:
                dia = f
                out += f"<h3 class='anf-dia-h'>{e(horarios.etiqueta_dia(f, hoy))} · {e(horarios.fecha_larga(f))}</h3><div class='anf-grid'>"
                out += "".join(_tarjeta_res(x, por_id.get(x.get("cancha_id")), hoy) for x in lst if str(x.get("fecha")) == f) + "</div>"
        return out
    # Filtro por ORIGEN del cobro + mini libro de caja (reservas_dueno_screen); se aplica en el navegador.
    from web.anfitrion_negocio import JS_FILTRO_RESERVAS, es_noshow
    # Cobrado / por cobrar POR MONEDA (un dueño con locales en dos países no suma soles con dólares).
    cob: dict[str, int] = {}
    pen: dict[str, int] = {}
    for r in filas:
        if es_noshow(r):
            continue
        s = r.get("moneda") or (_moneda_de(por_id[r["cancha_id"]])[0] if r.get("cancha_id") in por_id else "S/")
        dest = cob if r.get("pagado") else pen
        dest[s] = dest.get(s, 0) + int(r.get("precio") or 0)
    sim = _moneda_de(canchas[0])[0] if canchas else "S/"

    def _por_moneda(d: dict) -> str:
        if not d:
            return e(ui.monto(0, sim, 0))
        orden = sorted(d, key=lambda k: (k != sim, k))
        return e(ui.monto(d[orden[0]], orden[0], 0)) + "".join(f"<small class='mc-otra'>+ {e(ui.monto(d[k], k, 0))}</small>" for k in orden[1:])
    filtros = ("<div class='chips mc-fil' id='filMedio' role='group' aria-label='Filtrar por forma de cobro'>" + "".join(
        f"<button type='button' class='chip{' sel' if k == 'todos' else ''}' data-medio='{k}'>{n}</button>"
        for k, n in (("todos", "Todos"), ("online", "Online"), ("efectivo", "Efectivo"), ("manual", "Manual"))) + "</div>")
    kp = va.kpis([va.kpi("billete", "Cobrado", _por_moneda(cob), color="verde", sub="últimos 30 días y próximas"),
                  va.kpi("recibo", "Por cobrar", _por_moneda(pen), color="naranja", tono="warn" if pen else "", sub="en la cancha")])
    cuerpo = (va.cabecera("Reservas", "Las reservas de tus canchas: en línea (web y app) y las que registraste a mano.", volver="/anfitrion/mis-canchas",
                          acciones="<a class='btn sec' href='/anfitrion/mis-canchas'>Ver calendario</a>")
              + kp + filtros + bloque("Próximas", prox, "Sin reservas próximas.") + bloque("Pasadas (30 días)", pas, "Sin reservas en los últimos 30 días.")
              + f"<script>{JS_PAGAR}{JS_FILTRO_RESERVAS}</script>")
    return ui.shell("Reservas", _anf(va.vista(cuerpo, "vmc mc-res")), sesion=ses, ancho=True, titulo_tab="Reservas · Modo anfitrión")


JS_PAGAR = r"""
function pcgToast(t){var el=document.createElement('div');el.className='toast';el.textContent=t;document.body.appendChild(el);setTimeout(function(){el.classList.add('on')},10);setTimeout(function(){el.classList.remove('on');setTimeout(function(){el.remove()},300)},2600)}
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-pagar]');if(!b||b.disabled)return;var id=b.dataset.pagar,v=b.dataset.v==='1',txt=b.innerHTML;b.disabled=true;b.innerHTML='Guardando…';
  try{var r=await fetch('/anfitrion/reserva/'+encodeURIComponent(id)+'/pagado',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pagado:v})});var j=await r.json();
    if(j.ok){pcgToast(v?'✅ Pago registrado':'↩ Marcada por cobrar');if(window.alPagar){window.alPagar(id,v);return}location.reload();return}
    pcgToast(j.error||'No se pudo guardar.')}catch(e){pcgToast('No se pudo guardar. Revisa tu conexión.')} b.disabled=false;b.innerHTML=txt});
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-noshow]');if(!b||b.disabled)return;
  var ok=await pcgConfirmar({titulo:'¿El jugador no vino?',mensaje:'Se marca como no-show: libera la cuenta de por cobrar y, si pagó seña, queda a tu favor.',confirmar:'Marcar no-show',destructivo:true,icono:'🚫'});if(!ok)return;
  b.disabled=true;try{var r=await fetch('/anfitrion/reserva/'+encodeURIComponent(b.dataset.noshow)+'/noshow',{method:'POST'});var j=await r.json();
    if(j.ok){pcgRecargar('Marcado como no-show');return}pcgAvisar({titulo:'No se pudo',mensaje:j.error||'Reintenta.'})}catch(e){pcgToast('No se pudo guardar. Revisa tu conexión.')} b.disabled=false});
"""


def _en_segundo_plano(fn, *args) -> None:
    """Push y otras llamadas de red a terceros NO retrasan la respuesta al
    dueño (un clic debe responder al instante). Los tests lo vuelven síncrono."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def verificar_existencia(cancha_id: str, direccion: str, lat, lng) -> dict | None:
    """= `AppState.verificarVenue` → `POST /verificacion-fisica/evaluar` del
    APK (carril informal): la IA del módulo de existencia puntúa el local y, si
    no concluye, agenda una visita del verificador por zona. Confirma
    EXISTENCIA, no propiedad. Best-effort: cualquier error se registra y se
    ignora (el registro ya quedó hecho)."""
    try:
        from verificacion_fisica import service as vf_service
        r = vf_service.evaluar(cancha_id, direccion or "", None,
                               float(lat) if lat is not None else None, float(lng) if lng is not None else None,
                               None, None, None, "sin_documentos")
        print(f"[existencia-web] {cancha_id}: score {r.get('score')} via {r.get('via')}", flush=True)
        try:
            from db import pg
            pg.persistir_en_segundo_plano(stores)
        except Exception:  # noqa: BLE001
            pass
        return r
    except Exception as ex:  # noqa: BLE001
        print(f"[existencia-web] {cancha_id}: no se pudo evaluar ({ex})", flush=True)
        return None


def _pro_ok(email: str) -> bool:
    """Candado Pro de reserva manual / bloqueos (fail-open: solo si la env
    `WEB_MANUAL_REQUIERE_PRO=1`, igual que CM_REQUIERE_PRO)."""
    return (not config.WEB_MANUAL_REQUIERE_PRO) or stores.pro_activo(email)


_RESP_PRO = {"ok": False, "error": "requiere_pro",
             "mensaje": f"La reserva manual y el bloqueo de horas son parte de {MARCA} Pro. Actívalo en Perfil → 👑 {MARCA} Pro."}


@router.get("/anfitrion/calendario", response_class=HTMLResponse)
def pagina_calendario(request: Request, cancha: str = "", desde: str = "", vista: str = "") -> HTMLResponse:
    """Antes era la agenda semanal suelta; desde el rediseño (16-nov-2026) es
    la MISMA vista unificada de Mis canchas (los enlaces viejos, el tablero y
    los avisos que apuntan aquí siguen funcionando)."""
    return _mis_canchas(request, _volver(request), "calendario", cancha=cancha, desde=desde, vista=vista)


# ── MIS CANCHAS UNIFICADO (rediseño del diseñador, Frames 8-10, 16-nov-2026) ──
# Izquierda: los locales con sus canchas (filtro, "Editar local", "Mapa").
# Derecha: la tarjeta de la cancha elegida y su CALENDARIO OPERATIVO (misma
# regla de turnos que la ficha y el app: reglas del club por día, fecha real
# de la madrugada, precio del turno con hora feliz y descuento puntual). Al
# tocar un turno se abre un MENÚ CONTEXTUAL junto a la celda (hoja inferior en
# el celular): libre → reserva manual / bloquear turno / bloquear todo el día;
# bloqueado → desbloquear; reserva → pagada / WhatsApp / detalle / cancelar.
# Vista "Día" = TODAS las canchas del local de la cancha elegida en columnas:
# es lo que mira la recepción ("¿qué cancha está libre a las 8?"); la vista
# "Semana" sigue siendo de una cancha.

HORA_PX = 46  # alto de una hora en el calendario (un turno de 60 min ≈ 42 px tocables)
_ICONO_DEPORTE = {"futbol", "tenis", "padel", "futsal", "pickleball", "voley", "basquet", "natacion"}


def _volver(request: Request) -> str:
    return request.url.path + (("?" + request.url.query) if request.url.query else "")


def _local_de(c: dict) -> str:
    return (c.get("club") or "").strip() or c.get("nombre") or "Local"


def _agrupar_locales(canchas: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for c in canchas:
        grupos.setdefault(_local_de(c), []).append(c)
    return grupos


def _precio_corto(c: dict) -> str:
    """"S/ 90 /h" o "S/ 22.50 /turno" (moneda de la cancha, nunca "S/" fijo)."""
    sim, _ = _moneda_de(c)
    monto, unidad = horarios.precio_publico(c)
    txt = f"{monto:.0f}" if float(monto).is_integer() else f"{monto:.2f}"
    return f"{sim} {txt} {'/h' if unidad == 'por hora' else '/turno'}"


def _sub_cancha(c: dict) -> str:
    return " · ".join((_deporte(c.get("deporte"))[0], f"{c.get('hora_apertura') or '07:00'}–{c.get('hora_cierre') or '23:00'}",
                       _precio_corto(c)))


def _icono_cancha(c: dict, color: str = "claro", tam: int = 16) -> str:
    dep = str(c.get("deporte") or "").lower()
    return va.icono(dep if dep in _ICONO_DEPORTE else "cancha", color, tam)


def _rango_txt(a: date, b: date) -> str:
    m = horarios.MESES
    if a == b:
        return f"{horarios.DIAS[a.weekday()]} {a.day} {m[a.month - 1]} {a.year}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day} – {b.day} {m[b.month - 1]} {b.year}"
    if a.year == b.year:
        return f"{a.day} {m[a.month - 1]} – {b.day} {m[b.month - 1]} {b.year}"
    return f"{a.day} {m[a.month - 1]} {a.year} – {b.day} {m[b.month - 1]} {b.year}"


def _wa_de(tel: str, iso: str) -> str:
    """Número para wa.me: solo dígitos; un celular local recibe el prefijo de
    su país (el de la cancha)."""
    d = re.sub(r"\D", "", tel or "")
    if d and len(d) == catalogos.TEL_LONGITUD.get(iso, 9):
        d = catalogos.TEL_PREFIJO.get(iso, "51") + d
    return d if len(d) >= 8 else ""


def _descuentos_varias(ids: list[str], fechas: list[str]) -> dict[str, dict]:
    """Descuentos puntuales por turno de VARIAS canchas en UNA consulta (la
    vista Día pinta todas las canchas del local)."""
    if len(ids) <= 1:
        return {i: datos.descuentos(i, fechas) for i in ids}
    from db import pg
    if not pg.habilitado:
        return {i: datos.descuentos(i, fechas) for i in ids}  # sin base (pruebas): no hay viajes
    out: dict[str, dict] = {i: {} for i in ids}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT cancha_id, fecha, hora, pct FROM pichangol_descuentos_slot "
                        "WHERE cancha_id = ANY(%s) AND fecha = ANY(%s)", (ids, fechas))
            for cid, f, h, p in cur.fetchall():
                out.setdefault(str(cid), {})[(str(f), str(h))] = int(p or 0)
    except Exception:  # noqa: BLE001
        pass
    return out


def _url_mc(cancha: str, desde: str = "", vista: str = "") -> str:
    q = f"?cancha={quote(cancha, safe='')}"
    if desde:
        q += f"&desde={desde}"
    if vista == "dia":
        q += "&vista=dia"
    return "/anfitrion/mis-canchas" + q


def _lista_locales(grupos: dict[str, list[dict]], sel: dict, email: str, vista: str, desde: str) -> str:
    """Columna izquierda "CANCHAS" (kit `va-lat`) con lo que el kit no trae:
    bajo cada local "Editar local" (solo el dueño) y "Mapa", el local plegable
    y, al pie, "+ Agregar cancha a un local" (solo locales propios)."""
    n_can = sum(len(v) for v in grupos.values())
    cuerpo = ""
    for local, cs in grupos.items():
        c0 = cs[0]
        dueno = permisos.es_dueno_de(email, c0)
        ok = all(datos.reservable(x) for x in cs)
        zona = _zona(c0)
        estado = ("✓ Verificado" if ok else "En verificación") + (f" · {zona}" if zona else "")
        items = ""
        for x in cs:
            s = x["id"] == sel["id"]
            items += (f"<a class='va-lat-it{' sel' if s else ''}' href='{e(_url_mc(x['id'], desde, vista))}'"
                      + (" aria-current='true'" if s else "")
                      + f" data-q='{e((x.get('nombre') or '') + ' ' + local + ' ' + _sub_cancha(x)).lower()}'>"
                      f"{_icono_cancha(x, 'azul' if s else 'claro')}<span class='tx'><b>{e(x.get('nombre') or 'Cancha')}</b>"
                      f"<small>{e(_sub_cancha(x))}</small></span></a>")
        acc = ((f"<a href='/anfitrion/local/{quote(c0['id'], safe='')}/editar'>Editar local</a>" if dueno else "")
               + f"<a href='{e(_maps(c0))}' target='_blank' rel='noopener'>Mapa</a>")
        abierto = any(x["id"] == sel["id"] for x in cs)
        cuerpo += (f"<details class='va-lat-g mc-loc' open data-sel='{1 if abierto else 0}'><summary class='mc-loc-cab'>"
                   f"{va.icono('edificio', 'claro', 16)}<span class='tx'><b>{e(local)}</b><small class='{'ok' if ok else 'warn'}'>{e(estado)}</small></span>"
                   f"<span class='mc-chev' aria-hidden='true'></span></summary>{items}<div class='mc-loc-acc'>{acc}</div></details>")
    propios = [(local, cs[0]) for local, cs in grupos.items() if permisos.es_dueno_de(email, cs[0])]
    pie = ""
    if len(propios) == 1:
        pie = (f"<a class='btn oscuro mc-agr' href='/anfitrion/cancha/{quote(propios[0][1]['id'], safe='')}/agregar'"
               f" aria-label='Agregar cancha a {e(propios[0][0])}'>+ Agregar cancha a este local</a>")
    elif propios:
        pie = ("<details class='mc-agr-m'><summary class='btn oscuro mc-agr'>+ Agregar cancha a un local</summary><div class='mc-agr-lista'>"
               + "".join(f"<a href='/anfitrion/cancha/{quote(c0['id'], safe='')}/agregar'>{e(local)} ›</a>" for local, c0 in propios)
               + "</div></details>")
    caja = (f"<label class='va-lat-buscar'>{iconos.svg('lupa', 18, grueso=2.2)}"
            "<input type='search' placeholder='Filtrar canchas o deportes…' aria-label='Filtrar canchas o deportes' data-va-filtro></label>")
    contar = f"{len(grupos)} local{'es' if len(grupos) != 1 else ''} · {n_can} cancha{'s' if n_can != 1 else ''}"
    return (f"<aside class='va-lat mc-lat' aria-label='Tus canchas'><div class='va-lat-cab'><b>Canchas</b><small>{contar}</small></div>"
            f"{caja}{cuerpo}{pie}</aside>")


def _estado_cancha(c: dict, email: str) -> str:
    """Píldora de la cancha elegida: "✓ Verificada" o el estado REAL del reclamo."""
    if datos.reservable(c):
        return va.pill("✓ Verificada", "ok")
    try:
        est = reclamos.estado(c["id"], (c.get("dueno") or email))
    except Exception:  # noqa: BLE001
        est = {}
    clase, tit, _txt = _ESTADO_RECLAMO.get(str(est.get("estado") or ""), ("warn", "Sin solicitud de verificación", ""))
    return va.pill(tit, "bad" if clase == "err" else "warn")


def _ficha_cancha(c: dict, email: str, es_dueno: bool) -> str:
    fs = next(iter(_fotos(c)), None)
    foto = (f"<img class='mc-ficha-f' src='{e(fs)}' alt='' loading='lazy'>" if fs
            else f"<span class='mc-ficha-f'>{_icono_cancha(c, 'claro', 22)}</span>")
    sub = " · ".join(x for x in (_local_de(c), f"{c.get('hora_apertura') or '07:00'}–{c.get('hora_cierre') or '23:00'}",
                                  f"turnos de {int(c.get('duracion_slot_min') or 60)} min", _precio_corto(c)) if x)
    acc = f"<a class='btn sec' href='/reservar/{quote(c['id'], safe='')}'>Ver ficha pública</a>"
    if es_dueno:
        acc += (f"<a class='btn sec' href='/anfitrion/reglas/{quote(c['id'], safe='')}'>"
                + ("Reglas de reserva ✓" if _reglas.de_cancha(c) else "Reglas de reserva") + "</a>"
                f"<a class='btn' href='/anfitrion/cancha/{quote(c['id'], safe='')}/editar'>Editar</a>")
    return (f"<section class='va-panel mc-ficha' aria-label='Cancha elegida'>{foto}<div class='mc-ficha-t'>"
            f"<h2>{e(c.get('nombre') or 'Cancha')} {_estado_cancha(c, email)}</h2><p>{e(sub)}</p></div>"
            f"<div class='mc-ficha-acc'>{acc}</div></section>")


def _avisos_mis_canchas(email: str, propias: list[dict], hoy: date) -> str:
    """UN aviso compacto (como el diseño: "3 de tus locales necesitan fotos
    tuyas · Ver detalle · Subir fotos ›"); el detalle completo de cada local
    (estado del reclamo, fotos que faltan y plazos) se despliega debajo."""
    pend = _pendientes_verificacion(propias, email)
    det = _aviso_verificacion(propias, email, pend) + fotos_locales.avisos_dueno(email, propias)
    if not det:
        return ""
    em = (email or "").strip().lower()
    try:
        fot = [x for x in fotos_locales.locales(hoy, propias) if x.get("dueno") == em and x.get("estado") in ("pendiente", "vencido")] \
            if fotos_locales.minimo() > 0 and fotos_locales.inicio() is not None else []
    except Exception:  # noqa: BLE001
        fot = []
    partes, subir, tono = [], "", "info"
    if fot:
        partes.append(f"<b>{len(fot)} de tus locales necesitan fotos tuyas</b>" if len(fot) > 1
                      else f"<b>{e(fot[0].get('local') or 'Tu local')} necesita fotos tuyas</b>")
        subir = fotos_locales.url_subir(fot[0])
        if any(x["estado"] == "vencido" for x in fot):
            tono = "bad"
    if pend:
        partes.append(f"<b>{e(_local_de(pend[0]['c']))}</b> · {e(pend[0]['tit'])}" if len(pend) == 1
                      else f"<b>{len(pend)} locales aún no están verificados</b>")
        if any(p["clase"] == "err" for p in pend):
            tono = "bad"
        if not subir:
            m = fotos_reclamo.minimo()
            for p in pend:
                rc = _cancha_del_reclamo(email, p["c"], propias)
                if m > 0 and p["estado"] not in ("rechazada", "reclamada_por_otro") and len(fotos_reclamo.de_cancha(rc)) < m:
                    subir = f"/anfitrion/cancha/{quote(rc['id'], safe='')}/editar#sec-fotos"
                    break
    texto = " · ".join(partes) + (f" <span class='mc-av-sub'>· sin fotos tuyas no se muestran bien en {e(MARCA)}</span>" if fot else "")
    acc = ("<button type='button' class='mc-av-ver' aria-expanded='false' aria-controls='mcAvDet'>Ver detalle</button>"
           + (f"<a href='{e(subir)}'>Subir fotos ›</a>" if subir else "")
           + (f"<a href='/anfitrion/verificacion/{quote(pend[0]['c']['id'], safe='')}'>Ver estado ›</a>" if pend and not subir else ""))
    return va.aviso(texto, tono, acc, ico="campana") + f"<div class='mc-av-det' id='mcAvDet' hidden>{det}</div>"


def _mis_canchas(request: Request, volver: str, seccion: str, *, cancha: str = "", desde: str = "", vista: str = "",
                 solo_dueno: bool = False, aviso_ok: str = "") -> HTMLResponse:
    """La vista unificada. [solo_dueno] = solo las canchas propias (la ruta
    vieja /anfitrion/canchas era del dueño: la recepción recibe 403)."""
    if solo_dueno:
        ses, canchas, resp = _contexto(request, volver, seccion)
    else:
        ses, canchas, resp = _contexto(request, volver, seccion, accion=permisos.VER_AGENDA)
    if resp is not None:
        return resp
    email = ses["email"]
    grupos = _agrupar_locales(canchas)
    canchas = [x for cs in grupos.values() for x in cs]
    c = next((x for x in canchas if x["id"] == cancha), canchas[0])
    es_dueno = permisos.es_dueno_de(email, c)
    ahora = horarios.ahora_local(_pais_de(c))
    hoy = ahora.date()
    hoy_iso, ahora_min = hoy.isoformat(), ahora.hour * 60 + ahora.minute
    vista = "dia" if vista == "dia" else "semana"
    try:
        ini = date.fromisoformat(desde) if desde else hoy
    except ValueError:
        ini = hoy
    if vista == "dia":
        dias = [ini]
        cols = [(x, ini) for x in grupos[_local_de(c)]]
    else:
        dias = [ini + timedelta(days=i) for i in range(7)]
        cols = [(c, d) for d in dias]
    ids = list(dict.fromkeys(x["id"] for x, _ in cols))
    isos = [d.isoformat() for d in dias]
    sig = (dias[-1] + timedelta(days=1)).isoformat()
    fechas = isos + [sig]
    filas = datos.reservas_de_canchas(ids, isos[0], sig)
    bloq = datos.bloqueos_de(ids, fechas)
    desc = _descuentos_varias(ids, fechas)
    ocup = {(str(r.get("cancha_id")), str(r.get("fecha"))[:10], str(r.get("hora_inicio"))): r for r in filas}
    from web.anfitrion_negocio import es_noshow

    # Línea de tiempo común a todas las columnas (de la primera hora a la última).
    info, ini_min, fin_min = [], 24 * 60, 0
    for x, d in cols:
        cd = _reglas.cancha_del_dia(x, d.isoformat())
        paso = int(x.get("duracion_slot_min") or 60)
        turnos = []
        for h in horarios.slots_de(cd):
            fr = horarios.fecha_real(d.isoformat(), cd["hora_apertura"], cd["hora_cierre"], h)
            m = (horarios.hora_en_minutos(h) or 0) + (1440 if fr != d.isoformat() else 0)
            turnos.append((h, fr, m))
            ini_min, fin_min = min(ini_min, m), max(fin_min, m + paso)
        info.append((x, d, cd, paso, turnos))
    if fin_min <= ini_min:
        ini_min, fin_min = 8 * 60, 22 * 60
    ini_min, fin_min = (ini_min // 60) * 60, -(-fin_min // 60) * 60
    alto = (fin_min - ini_min) * HORA_PX // 60

    def _px(m: int) -> int:
        return round((m - ini_min) * HORA_PX / 60)

    res_json: dict[str, dict] = {}
    cab = cuerpos = chips = ""
    sel_col = 0
    for i, (x, d, cd, paso, turnos) in enumerate(info):
        iso_d = d.isoformat()
        sim_x = _moneda_de(x)[0]
        es_hoy = iso_d == hoy_iso
        mot = cd.get("_cerrado")
        dia_txt = f"{horarios.DIAS[d.weekday()]} {d.day} {horarios.MESES[d.month - 1]}"
        if vista == "dia":
            if x["id"] == c["id"]:
                sel_col = i
            cab += (f"<div class='mc-ch{' sel' if x['id'] == c['id'] else ''}' data-col='{i}'><b>{e(x.get('nombre') or 'Cancha')}</b>"
                    f"<span>{e(_deporte(x.get('deporte'))[0])}" + (f" · {e(_motivo_cierre(mot))}" if mot else "") + "</span></div>")
            chips += (f"<button type='button' class='mc-dia' data-dia='{i}' aria-pressed='false'>{e(x.get('nombre') or 'Cancha')}</button>")
        else:
            if es_hoy:
                sel_col = i
            cab += (f"<div class='mc-ch{' hoy' if es_hoy else ''}{' cerr' if mot else ''}' data-col='{i}'><span>{horarios.DIAS[d.weekday()]}</span>"
                    f"<b>{d.day} {horarios.MESES[d.month - 1]}</b>" + (f"<small>{e(_motivo_cierre(mot))}</small>" if mot else "") + "</div>")
            chips += (f"<button type='button' class='mc-dia' data-dia='{i}' aria-pressed='false'>{horarios.DIAS[d.weekday()]} {d.day}"
                      + (" · cerrado" if mot else "") + "</button>")
        evs = ""
        for h, fr, m in turnos:
            fin = horarios.hora_fin(h, paso)
            pasado = fr < hoy_iso or (fr == hoy_iso and (horarios.hora_en_minutos(h) or 0) < ahora_min)
            precio = horarios.precio_turno_de(cd, h, (desc.get(x["id"]) or {}).get((fr, h), 0))
            attrs = (f" data-c='{e(x['id'])}' data-b='{iso_d}' data-f='{fr}' data-h='{h}' data-fin='{fin}' data-p='{precio}'")
            alto_t = max(paso * HORA_PX // 60 - 4, 22)
            r = ocup.get((x["id"], fr, h))
            if r is not None:
                rid = str(r.get("id") or "")
                pag = bool(r.get("pagado"))
                ns = es_noshow(r)
                fin_r = str(r.get("hora_fin") or fin)
                dur = ((horarios.hora_en_minutos(fin_r) or 0) - (horarios.hora_en_minutos(h) or 0)) % 1440 or paso
                nombre = (str(r.get("jugador") or r.get("usuario") or "").strip().split(" ") or [""])[0] or "Reserva"
                est = "no vino" if ns else ("pagada" if pag else "cobrar")
                res_json[rid] = {"id": rid, "jugador": r.get("jugador") or "", "usuario": r.get("usuario") or "",
                                 "telefono": str(r.get("telefono") or ""), "wa": _wa_de(str(r.get("telefono") or ""), _pais_de(x)),
                                 "precio": int(r.get("precio") or 0), "pagado": pag, "medio": str(r.get("medio_pago") or ""),
                                 "fecha": fr, "ini": h, "fin": fin_r, "web": rid.startswith("web_"), "noshow": ns, "empezo": pasado,
                                 "cancha": x["id"]}
                evs += (f"<button type='button' class='mc-ev res {'ns' if ns else ('ok' if pag else 'ef')}{' pas' if pasado else ''}'"
                        f" data-t='res' data-rid='{e(rid)}'{attrs} style='top:{_px(m) + 2}px;height:{max(dur * HORA_PX // 60 - 4, 22)}px'"
                        f" aria-label='{e(dia_txt)} {h}–{e(fin_r)} · {e(nombre)} · {est}'><b>{e(nombre)}</b> · <span>{est}</span></button>")
            elif (x["id"], fr, h) in bloq:
                evs += (f"<button type='button' class='mc-ev bl{' pas' if pasado else ''}' data-t='bloq'{attrs}"
                        f" style='top:{_px(m) + 2}px;height:{alto_t}px' aria-label='{e(dia_txt)} {h}–{fin} · bloqueado'"
                        + (" disabled" if pasado else "") + ">Bloqueado</button>")
            elif not pasado:
                evs += (f"<button type='button' class='mc-ev li' data-t='libre'{attrs} style='top:{_px(m) + 2}px;height:{alto_t}px'"
                        f" aria-label='{e(dia_txt)} {h}–{fin} · libre · {e(sim_x)} {precio}'><span>+ {h} · {e(sim_x)} {precio}</span></button>")
        extra = ""
        # Horas del rango común que ESTE día no tiene (horario por día de las reglas del club).
        if turnos and not mot:
            ini_c, fin_c = min(m for _h, _f, m in turnos), max(m for _h, _f, m in turnos) + paso
            if ini_c > ini_min:
                extra += f"<span class='mc-fuera' style='top:0;height:{_px(ini_c)}px'><span class='vh'>Fuera de horario</span></span>"
            if fin_c < fin_min:
                extra += f"<span class='mc-fuera' style='top:{_px(fin_c)}px;height:{alto - _px(fin_c)}px'><span class='vh'>Fuera de horario</span></span>"
        if iso_d < hoy_iso:
            extra += f"<i class='mc-pasado' style='height:{alto}px' aria-hidden='true'></i>"
        elif es_hoy and ahora_min > ini_min:
            extra += f"<i class='mc-pasado' style='height:{min(_px(ahora_min), alto)}px' aria-hidden='true'></i>"
        if es_hoy and ini_min <= ahora_min <= fin_min:
            extra += f"<i class='mc-ahora' style='top:{_px(ahora_min)}px' aria-hidden='true'></i>"
        if mot:
            extra += f"<span class='mc-cerr'>Cerrado<small>{e(MOTIVOS_CIERRE.get(str(mot).lower(), mot) if str(mot).lower() not in ('cerrado', 'otro') else 'por el club')}</small></span>"
        elif not turnos:
            extra += "<span class='mc-cerr'>Sin turnos</span>"
        cuerpos += (f"<div class='mc-col{' hoy' if es_hoy else ''}{' cerr' if mot else ''}' data-col='{i}' style='height:{alto}px'>"
                    f"{extra}{evs}</div>")
    horas = "".join(f"<span style='top:{_px(m)}px'>{m // 60 % 24:02d}:00</span>" for m in range(ini_min, fin_min, 60))
    n = len(info)
    cal = (f"<div class='mc-dias' role='group' aria-label='{'Cancha' if vista == 'dia' else 'Día'}'>{chips}</div>"
           f"<div class='mc-scroll'><div class='mc-cal {vista} mc-n{min(n, 16)}' id='mcCal' data-dia='{sel_col}'>"
           f"<div class='mc-cal-cab'><div class='mc-esq'></div>{cab}</div>"
           f"<div class='mc-cal-cuerpo'><div class='mc-horas' style='height:{alto}px'>{horas}</div>{cuerpos}</div></div></div>")

    # Barra: ‹ Hoy › · rango · Semana | Día · leyenda.
    salto = 1 if vista == "dia" else 7
    ant, sig_d = (ini - timedelta(days=salto)).isoformat(), (ini + timedelta(days=salto)).isoformat()
    txt_ant, txt_sig = ("Día anterior", "Día siguiente") if vista == "dia" else ("Semana anterior", "Semana siguiente")
    seg = va.segmentado([(_url_mc(c["id"], ini.isoformat(), "semana"), "Semana", vista == "semana"),
                         (_url_mc(c["id"], ini.isoformat(), "dia"), "Día", vista == "dia")], etiqueta="Vista del calendario")
    barra = (f"<div class='mc-barra'><div class='mc-nav'><a class='mc-nb' href='{e(_url_mc(c['id'], ant, vista))}' aria-label='{txt_ant}'>‹</a>"
             f"<a class='mc-nb' href='{e(_url_mc(c['id'], hoy_iso, vista))}'>Hoy</a>"
             f"<a class='mc-nb' href='{e(_url_mc(c['id'], sig_d, vista))}' aria-label='{txt_sig}'>›</a>"
             f"<b class='mc-rango'>{e(_rango_txt(dias[0], dias[-1]))}</b></div>{seg}"
             "<div class='mc-ley' aria-label='Leyenda'><span><i class='ok'></i>Pagada</span><span><i class='ef'></i>Cobrar en cancha</span>"
             "<span><i class='bl'></i>Bloqueado</span></div></div>")

    # Clientes recientes (para no tipear en la reserva manual; mismo criterio que el app).
    hist = datos.reservas_de_canchas([x["id"] for x in canchas], (hoy - timedelta(days=180)).isoformat(), (hoy + timedelta(days=60)).isoformat())
    clientes: dict[str, dict] = {}
    for r in hist:
        nom = str(r.get("jugador") or "").strip()
        em = str(r.get("usuario") or "").strip().lower()
        tel = str(r.get("telefono") or "").strip()
        k = em or (nom.lower() + "|" + tel)
        if not (nom or em) or k in clientes:
            continue
        clientes[k] = {"nombre": nom or em, "email": em, "telefono": tel}
    ops_cli = "".join(f"<option value='{e(k)}'>{e(v['nombre'])}{(' · ' + e(v['email'])) if v['email'] else ''}</option>" for k, v in list(clientes.items())[:80])
    pro = _pro_ok(c.get("dueno") or email)
    cfg = {"cancha": c["id"], "nombre": c["nombre"], "moneda": _moneda_de(c)[0], "clientes": clientes, "pro": pro,
           "puedeCancelar": es_dueno,
           "canchas": {x["id"]: {"nombre": x.get("nombre") or "Cancha", "moneda": _moneda_de(x)[0], "lugar": _local_de(x)} for x, _ in cols}}
    ico = {k: iconos.svg(v, 18, grueso=2.2) for k, v in (("manual", "portapapeles"), ("bloq", "escudo"), ("dia", "calendario"),
                                                          ("pagar", "billete"), ("wa", "whatsapp"), ("det", "archivo"),
                                                          ("cancelar", "intercambio"), ("noshow", "reloj"), ("quitar", "archivo"))}

    # Encabezado, avisos y armado.
    propias = [x for x in canchas if permisos.es_dueno_de(email, x)]
    acciones = "<a class='btn sec' href='/anfitrion/reservas'>Lista de reservas</a>"
    acciones += ("<a class='btn sec' href='/anfitrion/ingresos'>Ingresos</a>" if propias
                 else "<a class='btn sec' href='/anfitrion/pagos-por-confirmar'>Comprobantes por confirmar</a>")
    acciones += "<a class='btn' href='/anfitrion/nueva'>+ Agregar local</a>"
    n_ver = sum(1 for x in canchas if datos.reservable(x))
    sub = f"Tus locales y sus canchas, con el calendario de la cancha que elijas. {n_ver} de {len(canchas)} verificada{'s' if len(canchas) != 1 else ''}."
    pie = ("<div class='mc-pie'><p>Toca un turno libre para registrar una reserva manual o bloquearlo.</p>"
           + (f"<button type='button' class='mc-ical' data-ical='{e(_agenda_url(email))}'>Sincronizar con Google Calendar ›</button>" if propias else "")
           + "</div>")
    pro_aviso = ("" if pro else va.aviso(f"La reserva manual y el bloqueo de horas son parte de <b>{MARCA} Pro</b>. Actívalo en Perfil → {MARCA} Pro.",
                                         "warn", "<a href='/pro'>Ver Pro ›</a>", ico="estrella"))
    derecha = (_ficha_cancha(c, email, es_dueno) + pro_aviso
               + f"<section class='va-panel mc-calp' aria-label='Calendario de {e(c.get('nombre') or 'la cancha')}'>{barra}{cal}</section>" + pie)
    cuerpo = (va.cabecera("Mis canchas", sub, acciones=acciones)
              + aviso_ok + _banner_cobros(email) + _avisos_mis_canchas(email, propias, hoy)
              + f"<div class='mc-lado'>{_lista_locales(grupos, c, email, vista, desde)}<div class='mc-der'>{derecha}</div></div>"
              + _MODAL_MC.replace("⟦CLIENTES⟧", ops_cli).replace("⟦SIM⟧", e(_moneda_de(c)[0])).replace("⟦MARCA⟧", MARCA)
              + f"<script>var CAL={ui.json_js(cfg, ensure_ascii=False)};var RES={ui.json_js(res_json, ensure_ascii=False)};"
              f"var ICO={ui.json_js(ico)};</script><script>{va.JS}{_JS_MC}</script>")
    titulo = {"calendario": "Calendario", "canchas": "Canchas"}.get(seccion, "Mis canchas")
    return ui.shell(titulo, _anf(va.vista(cuerpo, "vmc")), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión · {MARCA}")


def _agenda_url(email: str) -> str:
    from web import anfitrion_agenda
    return anfitrion_agenda.url(email)


_MODAL_MC = """
<div class='mc-fondo' id='mcFondo' hidden></div>
<div class='mc-menu' id='mcMenu' role='menu' aria-labelledby='mcMenuT' hidden><div class='mc-menu-cab'><b id='mcMenuT'></b><small id='mcMenuS'></small></div>
 <div class='mc-menu-its' id='mcMenuIts'></div></div>
<div class='modal' id='modalCal' role='dialog' aria-modal='true' aria-labelledby='calTit'><div class='modal-caja mc-modal'>
 <div class='modal-cab'><button type='button' class='cerrar' id='calCerrar' aria-label='Cerrar'>✕</button><h3 id='calTit'>Reserva manual</h3></div>
 <div class='modal-cuerpo'>
  <p class='sub' id='calSub'></p>
  <div id='calManual' hidden>
   <label for='mCli'>Cliente reciente <span class='req'>opcional</span></label><select id='mCli'><option value=''>Elegir de tus clientes…</option>⟦CLIENTES⟧</select>
   <label for='mNom'>Nombre del cliente</label><input id='mNom' maxlength='80' placeholder='Ej. Juan Pérez' autocomplete='off'>
   <div class='row'><div><label for='mTel'>Teléfono <span class='req'>opcional</span></label><input id='mTel' inputmode='tel' maxlength='20' placeholder='999 888 777'></div>
   <div><label for='mEm'>Correo de su cuenta <span class='req'>opcional</span></label><input id='mEm' type='email' maxlength='120' placeholder='para que la vea en su app'></div></div>
   <label for='mPre'>Precio</label><div class='inp-moneda'><span id='mSim'>⟦SIM⟧</span><input id='mPre' type='number' min='0' step='0.5' inputmode='decimal'></div>
   <label class='chk'><input type='checkbox' id='mPag'> Ya pagó <small>(si no, queda "por cobrar" en tu caja)</small></label>
   <p class='sub mc-nota'>Cliente propio: sin comisión. No entra a tu billetera ⟦MARCA⟧, sí a tu caja del día.</p>
  </div>
  <div id='calRes' hidden>
   <div class='quien'><span class='av' id='rAv'>?</span><div class='mc-quien'><b id='rNom'></b><div class='sub' id='rDet'></div></div><b id='rPre' class='mc-pre'></b></div>
   <div id='rEstado' class='mc-estado'></div>
   <div class='acciones' id='rAcc'></div>
  </div>
  <div class='estado bad mc-err' id='calErr' hidden></div>
 </div>
 <div class='modal-pie'><button type='button' class='limpiar' id='calNo'>Cerrar</button><button type='button' class='btn' id='calSi'>Registrar reserva</button></div>
</div></div>"""


MOTIVOS_CIERRE = {"cerrado": "Cerrado", "feriado": "Feriado", "mantenimiento": "Mantenimiento",
                  "evento": "Evento privado", "otro": "Cerrado"}


def _motivo_cierre(mot: str) -> str:
    """"Cerrado · Feriado" (el motivo viene de las reglas del club)."""
    m = (mot or "").strip()
    nombre = MOTIVOS_CIERRE.get(m.lower(), m)
    return "Cerrado" if nombre in ("", "Cerrado") else f"Cerrado · {nombre}"


def _orden_turno(cd: dict, h: str) -> int:
    """Minutos para ordenar un turno: los de madrugada (cancha 18:00→02:00)
    van DESPUÉS de los de la noche."""
    m = horarios.hora_en_minutos(h) or 0
    return m + 24 * 60 if horarios.slot_es_madrugada(cd.get("hora_apertura") or "07:00", cd.get("hora_cierre") or "23:00", h) else m


def turno_del_dia(c: dict, base: str, hora: str) -> dict | None:
    """Cancha EFECTIVA del día `base` si `hora` es un turno real ese día
    (horario por día, cierres especiales); None si no existe."""
    cd = _reglas.cancha_del_dia(c, base)
    return cd if hora in horarios.slots_de(cd) else None


def base_de_turno(c: dict, fecha: str, hora: str, base: str = "") -> tuple[str, dict | None]:
    """El calendario y Disponibilidad mandan la fecha REAL del turno (la
    madrugada es del día siguiente). Devuelve (día base, cancha del día) del
    turno, o ("", None) si ese turno no existe con las reglas del club."""
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        return "", None
    candidatos = [base] if base else [f.isoformat(), (f - timedelta(days=1)).isoformat()]
    for b in candidatos:
        cd = turno_del_dia(c, b, hora)
        if cd is not None and horarios.fecha_real(b, cd["hora_apertura"], cd["hora_cierre"], hora) == f.isoformat():
            return b, cd
    return "", None


_JS_MC = (r"""
(function(){
var MENU=document.getElementById('mcMenu'),FONDO=document.getElementById('mcFondo'),M=document.getElementById('modalCal'),CALG=document.getElementById('mcCal'),cel=null,modo='',origen=null;
function $(id){return document.getElementById(id)}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function fechaTxt(iso){var d=new Date(iso+'T12:00:00');return d.toLocaleDateString('es-PE',{weekday:'short',day:'numeric',month:'short'})}
function cdat(id){return (CAL.canchas||{})[id]||{nombre:CAL.nombre,moneda:CAL.moneda,lugar:''}}
function online(r){return r.pagado&&(r.medio==='yape'||r.medio==='tarjeta')}
function estadoTxt(r){return r.noshow?'no vino':(online(r)?'pagada en línea':(r.pagado?'pagada':'cobrar en cancha'))}
async function post(url,body){var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});var j={};try{j=await r.json()}catch(e){}return j}
function aviso(t,m){if(window.pcgAvisar)pcgAvisar({titulo:t,mensaje:m||'Inténtalo de nuevo.'});}
// ── días (celular): una columna a la vez ──
var dias=document.querySelector('.mc-dias');
function elegirDia(i){if(!CALG)return;CALG.dataset.dia=i;if(dias)dias.querySelectorAll('[data-dia]').forEach(function(b){var on=b.dataset.dia===String(i);b.classList.toggle('sel',on);b.setAttribute('aria-pressed',on?'true':'false')})}
if(dias){dias.addEventListener('click',function(ev){var b=ev.target.closest('[data-dia]');if(b)elegirDia(b.dataset.dia)});elegirDia(CALG?CALG.dataset.dia:0)}
// ── columna de locales: en el celular solo queda abierto el local de la cancha elegida ──
if(window.matchMedia&&matchMedia('(max-width:860px)').matches){document.querySelectorAll('.mc-loc[data-sel="0"]').forEach(function(d){d.open=false})}
document.addEventListener('input',function(ev){if(ev.target.matches&&ev.target.matches('[data-va-filtro]')&&ev.target.value)document.querySelectorAll('.mc-loc').forEach(function(d){d.open=true})});
// ── avisos: ver detalle ──
document.addEventListener('click',function(ev){var b=ev.target.closest('.mc-av-ver');if(!b)return;var d=$('mcAvDet');if(!d)return;d.hidden=!d.hidden;b.setAttribute('aria-expanded',d.hidden?'false':'true');b.textContent=d.hidden?'Ver detalle':'Ocultar detalle'});
// ── agenda iCal ──
document.addEventListener('click',function(ev){var b=ev.target.closest('.mc-ical');if(!b)return;
  var html="<p>Copia este enlace privado y agrégalo en Google Calendar → «Otros calendarios» → «Desde URL» (o en Apple / Outlook como calendario suscrito). Se actualiza solo. No lo compartas: muestra tus reservas.</p>"+
    "<div class='mc-ical-c'><input readonly id='mcIcalUrl' aria-label='Enlace de tu agenda' value='"+esc(b.dataset.ical)+"'><button type='button' class='btn' data-copiar='mcIcalUrl'>Copiar</button></div>";
  if(window.pcgAvisar)pcgAvisar({titulo:'Tus reservas en Google Calendar',html:html,icono:'📆',confirmar:'Listo'})});
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-copiar]');if(!b)return;var i=$(b.dataset.copiar);if(!i)return;i.select();
  var ok=function(){if(window.pcgToast)pcgToast('Enlace copiado')};if(navigator.clipboard)navigator.clipboard.writeText(i.value).then(ok,function(){});else{try{document.execCommand('copy');ok()}catch(e){}}});
// ── menú contextual ──
function it(acc,txt,ico,tono,href){var ic="<span class='mc-mi-ic"+(tono?' '+tono:'')+"'>"+(ICO[ico]||'')+"</span>";
  if(href)return "<a role='menuitem' class='mc-mi"+(tono?' '+tono:'')+"' href='"+esc(href)+"' target='_blank' rel='noopener' data-acc='"+acc+"'>"+ic+esc(txt)+"</a>";
  return "<button type='button' role='menuitem' class='mc-mi"+(tono?' '+tono:'')+"' data-acc='"+acc+"'>"+ic+esc(txt)+"</button>"}
function waUrl(r){var c=cdat(r.cancha);var t='Hola '+(r.jugador||'').split(' ')[0]+', te recordamos tu reserva en '+(c.lugar||c.nombre)+': '+fechaTxt(r.fecha)+' de '+r.ini+' a '+r.fin+' ('+c.nombre+'). ¡Te esperamos!';
  return 'https://wa.me/'+r.wa+'?text='+encodeURIComponent(t)}
var NOPRO="<p class='mc-menu-pro'>La reserva manual y el bloqueo de horas son parte de "+'⟦MARCA⟧ Pro'+".</p>";
function abrirMenu(b){cel=b;origen=b;var t=b.dataset.t,c=cdat(b.dataset.c),tit='',sub='',its='';
  if(t==='libre'){tit=fechaTxt(b.dataset.f)+' · '+b.dataset.h+' – '+b.dataset.fin;sub=c.nombre+' · turno libre · '+c.moneda+' '+b.dataset.p;
    its=CAL.pro?it('manual','Registrar reserva manual','manual')+it('bloq','Bloquear este turno','bloq')+it('dia','Bloquear todo el día','dia'):NOPRO+"<a role='menuitem' class='mc-mi' href='/pro'><span class='mc-mi-ic'>"+(ICO.dia||'')+"</span>Ver "+'⟦MARCA⟧ Pro'+"</a>"}
  else if(t==='bloq'){tit=fechaTxt(b.dataset.f)+' · '+b.dataset.h+' – '+b.dataset.fin;sub=c.nombre+' · bloqueado: nadie puede reservarlo';
    its=CAL.pro?it('desbloq','Desbloquear este turno','bloq')+it('desdia','Desbloquear todo el día','dia'):NOPRO}
  else{var r=RES[b.dataset.rid];if(!r)return;tit=(r.jugador||r.usuario||'Reserva').split(' ')[0]+' · '+fechaTxt(r.fecha)+' · '+r.ini;sub=c.nombre+' · '+estadoTxt(r)+' · '+c.moneda+' '+r.precio;
    if(!r.noshow){if(!r.pagado)its+=it('pagar','Marcar como pagada','pagar','ok');else if(!online(r))its+=it('porcobrar','Marcar por cobrar','pagar')}
    if(r.wa)its+=it('wa','Enviar recordatorio por WhatsApp','wa','',waUrl(r));
    its+=it('detalle','Ver detalle de la reserva','det');
    if(!r.noshow&&!online(r)&&r.empezo)its+=it('noshow','Marcar no-show (no vino)','noshow');
    if(r.medio==='manual'&&!r.empezo)its+=it('quitar','Quitar reserva manual','quitar','peligro');
    if(online(r)&&CAL.puedeCancelar&&!r.empezo)its+=it('cancelar','Cancelar reserva','cancelar','peligro')}
  $('mcMenuT').textContent=tit;$('mcMenuS').textContent=sub;$('mcMenuIts').innerHTML=its;
  MENU.hidden=false;var hoja=window.matchMedia&&matchMedia('(max-width:600px)').matches;MENU.classList.toggle('hoja',hoja);FONDO.hidden=!hoja;
  if(!hoja){var rc=b.getBoundingClientRect(),w=MENU.offsetWidth,h=MENU.offsetHeight,x=rc.right+8;if(x+w>innerWidth-8)x=rc.left-w-8;if(x<8)x=Math.max(8,Math.min(innerWidth-w-8,rc.left));
    var y=rc.top;if(y+h>innerHeight-8)y=innerHeight-h-8;if(y<8)y=8;MENU.style.left=(x+scrollX)+'px';MENU.style.top=(y+scrollY)+'px'}else{MENU.style.left='';MENU.style.top=''}
  b.classList.add('act');var f=MENU.querySelector('.mc-mi');if(f)f.focus()}
function cerrarMenu(volver){if(MENU.hidden)return;MENU.hidden=true;FONDO.hidden=true;document.querySelectorAll('.mc-ev.act').forEach(function(x){x.classList.remove('act')});if(volver&&origen)origen.focus()}
document.addEventListener('click',function(ev){var b=ev.target.closest('.mc-ev');if(b&&!b.disabled){ev.preventDefault();if(!MENU.hidden&&cel===b){cerrarMenu(true);return}abrirMenu(b);return}
  if(!MENU.hidden&&!ev.target.closest('#mcMenu'))cerrarMenu(false)});
FONDO.addEventListener('click',function(){cerrarMenu(true)});
document.addEventListener('keydown',function(ev){if(ev.key==='Escape'){if(M.classList.contains('open'))cerrarModal();else cerrarMenu(true);return}
  if(MENU.hidden)return;var its=[].slice.call(MENU.querySelectorAll('.mc-mi')),i=its.indexOf(document.activeElement);
  if(ev.key==='ArrowDown'){ev.preventDefault();(its[(i+1)%its.length]||its[0]).focus()}else if(ev.key==='ArrowUp'){ev.preventDefault();(its[(i-1+its.length)%its.length]||its[0]).focus()}});
window.addEventListener('resize',function(){cerrarMenu(false)});
// ── modal (reserva manual / detalle) ──
function err(t){var el=$('calErr');el.hidden=!t;el.textContent=t||''}
function abrirModal(m){modo=m;err('');$('calManual').hidden=m!=='manual';$('calRes').hidden=m!=='detalle';var si=$('calSi'),c=cdat(cel.dataset.c);si.disabled=false;
  $('calSub').textContent=c.nombre+' · '+fechaTxt(cel.dataset.f)+' · '+cel.dataset.h+'–'+cel.dataset.fin;
  if(m==='manual'){$('calTit').textContent='Reserva manual';si.hidden=false;si.textContent='Registrar reserva';$('mSim').textContent=c.moneda;
    $('mCli').value='';$('mNom').value='';$('mTel').value='';$('mEm').value='';$('mPre').value=cel.dataset.p;$('mPag').checked=false}
  else{pintarDetalle();si.hidden=true}
  M.classList.add('open');var f=M.querySelector(m==='manual'?'#mNom':'#calCerrar');if(f)setTimeout(function(){f.focus()},30)}
function pintarDetalle(){var r=RES[cel.dataset.rid];if(!r)return;var c=cdat(r.cancha);$('calTit').textContent='Detalle de la reserva';
  $('rAv').textContent=(r.jugador||r.usuario||'?').charAt(0).toUpperCase();$('rNom').textContent=r.jugador||r.usuario||'Reserva';
  $('rDet').textContent=[r.usuario,r.telefono,r.web?'reserva web':(r.medio==='manual'?'reserva manual':'')].filter(Boolean).join(' · ');
  $('rPre').textContent=c.moneda+' '+Number(r.precio).toFixed(2);
  $('rEstado').innerHTML=r.noshow?"<span class='pill bad'>No vino (no-show)</span>":(online(r)?"<span class='pill ok'>Pagada en línea · "+esc(r.medio)+"</span>":(r.pagado?"<span class='pill ok'>Cobrada</span>":"<span class='pill warn'>Cobrar en la cancha</span>"));
  var a='';if(r.wa)a+="<a class='btn sec' href='"+esc(waUrl(r))+"' target='_blank' rel='noopener'>WhatsApp</a>";
  if(!r.noshow){if(!r.pagado)a+="<button type='button' class='btn' data-pagar='"+esc(r.id)+"' data-v='1'>Marcar pagada</button>";else if(!online(r))a+="<button type='button' class='btn sec' data-pagar='"+esc(r.id)+"' data-v='0'>Marcar por cobrar</button>"}
  if(r.medio==='manual'&&!r.empezo)a+="<button type='button' class='btn peligro' data-mc='quitar'>Quitar reserva</button>";
  if(online(r)&&CAL.puedeCancelar&&!r.empezo)a+="<button type='button' class='btn peligro' data-mc='cancelar'>Cancelar y devolver al jugador</button>";
  $('rAcc').innerHTML=a}
function cerrarModal(){M.classList.remove('open');if(origen)origen.focus()}
$('calCerrar').addEventListener('click',cerrarModal);$('calNo').addEventListener('click',cerrarModal);M.addEventListener('click',function(ev){if(ev.target===M)cerrarModal()});
$('mCli').addEventListener('change',function(){var c=CAL.clientes[this.value];if(!c)return;$('mNom').value=c.nombre;$('mTel').value=c.telefono||'';$('mEm').value=c.email||''});
$('calSi').addEventListener('click',async function(){if(!cel||modo!=='manual')return;var b=this;b.disabled=true;err('');
  try{var j=await post('/anfitrion/reserva-manual',{cancha_id:cel.dataset.c,fecha:cel.dataset.b,hora:cel.dataset.h,nombre:$('mNom').value,telefono:$('mTel').value,email:$('mEm').value,precio:parseFloat($('mPre').value),pagado:$('mPag').checked});
    if(j.ok){pcgRecargar('Reserva registrada');return}err(j.mensaje||j.error||'No se pudo guardar.')}catch(e){err('No se pudo guardar. Revisa tu conexión.')}b.disabled=false});
// pagada / por cobrar desde el detalle (JS_PAGAR) y desde el menú
window.alPagar=function(id,v){var r=RES[id];if(!r)return;r.pagado=v;var b=document.querySelector(".mc-ev[data-rid='"+id+"']");
  if(b){b.classList.toggle('ok',v);b.classList.toggle('ef',!v);var s=b.querySelector('span');if(s)s.textContent=v?'pagada':'cobrar'}
  if(M.classList.contains('open')&&modo==='detalle')pintarDetalle()};
async function accion(acc){var b=cel,c=cdat(b.dataset.c),r=RES[b.dataset.rid];
  if(acc==='manual'||acc==='detalle'){cerrarMenu(false);abrirModal(acc);return}
  if(acc==='wa'){cerrarMenu(false);return}
  cerrarMenu(false);var j;
  try{
    if(acc==='bloq'||acc==='desbloq'){pcgCargando(acc==='bloq'?'Bloqueando…':'Desbloqueando…',{demora:250});
      j=await post('/anfitrion/bloqueo',{cancha_id:b.dataset.c,fecha:b.dataset.f,base:b.dataset.b,hora:b.dataset.h,bloquear:acc==='bloq'});
      if(j.ok){pcgRecargar(acc==='bloq'?'Turno bloqueado':'Turno desbloqueado');return}}
    else if(acc==='dia'||acc==='desdia'){var bloquear=acc==='dia';
      if(!await pcgConfirmar({titulo:bloquear?'¿Bloquear todo el día?':'¿Desbloquear todo el día?',icono:'📅',confirmar:bloquear?'Bloquear el día':'Desbloquear el día',destructivo:bloquear,
        mensaje:bloquear?'Se bloquean los turnos libres que quedan del '+fechaTxt(b.dataset.b)+' en '+c.nombre+'. Las reservas que ya existen no se tocan.':'Vuelven a quedar libres los turnos bloqueados que quedan del '+fechaTxt(b.dataset.b)+' en '+c.nombre+'.'}))return;
      pcgCargando(bloquear?'Bloqueando el día…':'Desbloqueando el día…');j=await post('/anfitrion/bloqueo-dia',{cancha_id:b.dataset.c,fecha:b.dataset.b,bloquear:bloquear});
      if(j.ok){pcgRecargar(j.n?(j.n+(j.n===1?' turno ':' turnos ')+(bloquear?'bloqueado':'desbloqueado')+(j.n===1?'':'s')):'No había turnos por cambiar');return}}
    else if(acc==='pagar'||acc==='porcobrar'){var v=acc==='pagar';j=await post('/anfitrion/reserva/'+encodeURIComponent(r.id)+'/pagado',{pagado:v});
      if(j.ok){if(window.pcgToast)pcgToast(v?'Pago registrado':'Marcada por cobrar');window.alPagar(r.id,v);return}}
    else if(acc==='noshow'){if(!await pcgConfirmar({titulo:'¿El jugador no vino?',mensaje:'Se marca como no-show: libera la cuenta de por cobrar y, si pagó seña, queda a tu favor.',confirmar:'Marcar no-show',destructivo:true,icono:'🚫'}))return;
      pcgCargando('Guardando…',{demora:250});j=await post('/anfitrion/reserva/'+encodeURIComponent(r.id)+'/noshow',{});if(j.ok){pcgRecargar('Marcado como no-show');return}}
    else if(acc==='quitar'){if(!await pcgConfirmar({titulo:'Quitar reserva manual',mensaje:'El turno vuelve a quedar libre en tu calendario.',confirmar:'Quitar',destructivo:true}))return;
      pcgCargando('Quitando la reserva…');j=await post('/anfitrion/reserva/'+encodeURIComponent(r.id)+'/quitar',{});if(j.ok){pcgRecargar('Reserva quitada');return}}
    else if(acc==='cancelar'){if(!await pcgConfirmar({titulo:'Cancelar la reserva del jugador',mensaje:'Se le devuelve el 100 % de lo que pagó (cargo por servicio incluido) a su medio de pago y el turno queda libre. El costo de la pasarela de esa devolución se descuenta de tu próxima liquidación.',confirmar:'Cancelar y devolver',destructivo:true}))return;
      pcgCargando('Cancelando y devolviendo…');j=await post('/anfitrion/reserva/'+encodeURIComponent(r.id)+'/cancelar',{});if(j.ok){pcgRecargar('Reserva cancelada');return}}
  }catch(e){j={error:'No se pudo guardar. Revisa tu conexión.'}}
  pcgCargando(false);aviso('No se pudo',(j&&(j.mensaje||j.error))||'Inténtalo de nuevo.')}
MENU.addEventListener('click',function(ev){var m=ev.target.closest('.mc-mi');if(!m||!m.dataset.acc)return;if(m.dataset.acc!=='wa')ev.preventDefault();accion(m.dataset.acc)});
document.addEventListener('click',function(ev){var q=ev.target.closest('[data-mc]');if(!q||!cel)return;M.classList.remove('open');accion(q.dataset.mc)});
})();
""").replace('⟦MARCA⟧', MARCA) + JS_PAGAR


def _canchas_sesion(request: Request, accion: str = ""):
    """(sesión, canchas) para los endpoints JSON del calendario; None en ses =
    sin sesión. Con [accion] entran también las de los locales donde el correo
    es encargado con ese permiso (`web/permisos.py`); sin ella, solo las del
    dueño (cancelar con devolución)."""
    ses = sesion.de_request(request)
    if not ses:
        return None, []
    if accion:
        return ses, permisos.canchas_para(ses["email"], accion)
    return ses, datos.canchas_de_dueno(ses["email"])


@router.post("/anfitrion/bloqueo")
async def bloquear_turno(request: Request) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_bloquear_turno, request, _cuerpo_json)


def _bloquear_turno(request: Request, _cuerpo_json) -> JSONResponse:
    ses, canchas = _canchas_sesion(request, permisos.BLOQUEAR)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        b = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    c = next((x for x in canchas if x["id"] == str(b.get("cancha_id") or "")), None)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    if not _pro_ok(c.get("dueno") or ses["email"]):  # el Pro es del DUEÑO del local (también cuando opera su recepción)
        return JSONResponse(_RESP_PRO, status_code=402)
    fecha, hora = str(b.get("fecha") or ""), str(b.get("hora") or "")
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Fecha inválida."}, status_code=400)
    bloquear = bool(b.get("bloquear", True))
    if bloquear:
        # Con las reglas del club: no se bloquea un turno que ese día no existe
        # (día cerrado, horario distinto por día de la semana).
        base_b, _cd = base_de_turno(c, fecha, hora, str(b.get("base") or ""))
        if not base_b:
            mot = _reglas.cancha_del_dia(c, fecha).get("_cerrado")
            msg = (f"Ese día el club está cerrado ({_motivo_cierre(mot)}): no hay turnos que bloquear." if mot
                   else "Ese turno no existe en el horario de la cancha.")
            return JSONResponse({"ok": False, "error": msg}, status_code=400)
    elif horarios.hora_en_minutos(hora) is None:
        return JSONResponse({"ok": False, "error": "Hora inválida."}, status_code=400)
    if bloquear and (fecha, hora) in datos.ocupados(c["id"], [fecha]):
        return JSONResponse({"ok": False, "error": "Ese turno ya tiene una reserva."}, status_code=409)
    if not datos.bloquear(c["id"], fecha, hora, bloquear):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento."}, status_code=503)
    permisos.auditar(ses["email"], c, "bloquear" if bloquear else "desbloquear", f"{fecha} {hora}")
    print(f"[bloqueo-web] {ses['email']} {'bloqueó' if bloquear else 'desbloqueó'} {c['id']} {fecha} {hora}", flush=True)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/bloqueo-dia")
async def bloquear_dia(request: Request) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_bloquear_dia, request, _cuerpo_json)


def _bloquear_dia(request: Request, _cuerpo_json) -> JSONResponse:
    """"Bloquear todo el día" (menú del turno en Mis canchas): bloquea (o
    desbloquea) de una vez los turnos LIBRES y FUTUROS del día base `fecha`
    (la madrugada cuenta como de ese día, como en el calendario). Mismas
    reglas que `/anfitrion/bloqueo`: sesión, cancha del dueño o de su
    recepción, Pro del DUEÑO, reglas del club (un día cerrado no tiene turnos);
    los turnos con reserva no se tocan. Una sola escritura para todos."""
    ses, canchas = _canchas_sesion(request, permisos.BLOQUEAR)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        b = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    if not isinstance(b, dict):
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    c = next((x for x in canchas if x["id"] == str(b.get("cancha_id") or "")), None)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    if not _pro_ok(c.get("dueno") or ses["email"]):
        return JSONResponse(_RESP_PRO, status_code=402)
    fecha = str(b.get("fecha") or "")
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Fecha inválida."}, status_code=400)
    bloquear = bool(b.get("bloquear", True))
    cd = _reglas.cancha_del_dia(c, fecha)
    if cd.get("_cerrado"):
        return JSONResponse({"ok": False, "error": f"Ese día el club está cerrado ({_motivo_cierre(cd['_cerrado'])}): no hay turnos que bloquear."}, status_code=400)
    ahora = horarios.ahora_local(_pais_de(c))
    hoy, ahora_min = ahora.date().isoformat(), ahora.hour * 60 + ahora.minute
    futuros = []
    for h in horarios.slots_de(cd):
        fr = horarios.fecha_real(fecha, cd["hora_apertura"], cd["hora_cierre"], h)
        if fr < hoy or (fr == hoy and (horarios.hora_en_minutos(h) or 0) < ahora_min):
            continue
        futuros.append((fr, h))
    if not futuros:
        return JSONResponse({"ok": False, "error": "A ese día ya no le quedan turnos por delante."}, status_code=400)
    fechas = sorted({f for f, _ in futuros})
    bloq = {(f, h) for (cid, f, h) in datos.bloqueos_de([c["id"]], fechas) if cid == c["id"]}
    if bloquear:
        ocup = datos.ocupados(c["id"], fechas)  # reservas vigentes (también las web en espera de pago) + bloqueos
        objetivo = [t for t in futuros if t not in ocup]
        con_reserva = sum(1 for t in futuros if t in ocup and t not in bloq)
    else:
        objetivo = [t for t in futuros if t in bloq]
        con_reserva = 0
    if objetivo and not _bloquear_lote(c["id"], objetivo, bloquear):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento."}, status_code=503)
    if objetivo:
        permisos.auditar(ses["email"], c, "bloquear_dia" if bloquear else "desbloquear_dia", fecha, {"turnos": len(objetivo)})
        print(f"[bloqueo-web] {ses['email']} {'bloqueó' if bloquear else 'desbloqueó'} el día {fecha} de {c['id']} ({len(objetivo)} turnos)", flush=True)
    return JSONResponse({"ok": True, "n": len(objetivo), "con_reserva": con_reserva})


def _bloquear_lote(cancha_id: str, turnos: list[tuple[str, str]], bloquear: bool) -> bool:
    """Bloquea / desbloquea varios turnos en UNA sentencia (misma tabla y clave
    que `datos.bloquear` y el app: PK (cancha_id, fecha, hora), texto)."""
    from db import pg
    if not pg.habilitado:
        return all(datos.bloquear(cancha_id, f, h, bloquear) for f, h in turnos)  # sin base (pruebas)
    fs, hs = [f for f, _ in turnos], [h for _, h in turnos]
    try:
        with pg.conexion(atomica=False) as conn, conn.cursor() as cur:
            if bloquear:
                cur.execute("INSERT INTO pichangol_bloqueos (cancha_id, fecha, hora) "
                            "SELECT %s, t.f, t.h FROM unnest(%s::text[], %s::text[]) AS t(f, h) ON CONFLICT DO NOTHING",
                            (cancha_id, fs, hs))
            else:
                cur.execute("DELETE FROM pichangol_bloqueos b USING unnest(%s::text[], %s::text[]) AS t(f, h) "
                            "WHERE b.cancha_id = %s AND b.fecha = t.f AND b.hora = t.h", (fs, hs, cancha_id))
        return True
    except Exception as ex:  # noqa: BLE001
        print(f"[bloqueo-web] falló el lote de {cancha_id}: {ex}", flush=True)
        return False


@router.post("/anfitrion/reserva-manual")
async def reserva_manual(request: Request) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_reserva_manual, request, _cuerpo_json)


def _reserva_manual(request: Request, _cuerpo_json) -> JSONResponse:
    """Reserva MANUAL del dueño desde la web = la misma fila que crea el app
    (`agregarReservaManual`): confirmada, `traida_por_app=false` (cliente
    propio, sin comisión), `medio_pago='manual'`, fecha REAL del slot."""
    ses, canchas = _canchas_sesion(request, permisos.RESERVA_MANUAL)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        b = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    c = next((x for x in canchas if x["id"] == str(b.get("cancha_id") or "")), None)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    if not _pro_ok(c.get("dueno") or ses["email"]):
        return JSONResponse(_RESP_PRO, status_code=402)
    base, hora = str(b.get("fecha") or ""), str(b.get("hora") or "")
    try:
        date.fromisoformat(base)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Fecha inválida."}, status_code=400)
    paso = c["duracion_slot_min"]
    # Cancha EFECTIVA de ese día (reglas del club): horario del día, cierres,
    # franjas y recargo de luz para el precio sugerido.
    cd = _reglas.cancha_del_dia(c, base)
    if cd.get("_cerrado"):
        return JSONResponse({"ok": False, "error": f"Ese día el club está cerrado ({_motivo_cierre(cd['_cerrado'])})."}, status_code=400)
    if hora not in horarios.slots_de(cd):
        return JSONResponse({"ok": False, "error": "Ese turno no existe en el horario de la cancha."}, status_code=400)
    fr = horarios.fecha_real(base, cd["hora_apertura"], cd["hora_cierre"], hora)
    ahora = horarios.ahora_local(_pais_de(c))
    hoy = ahora.date().isoformat()
    m = horarios.hora_en_minutos(hora) or 0
    if fr < hoy or (fr == hoy and m < ahora.hour * 60 + ahora.minute):
        return JSONResponse({"ok": False, "error": "Ese turno ya pasó."}, status_code=400)
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:80] or "Cliente"
    telefono = re.sub(r"[^\d+ ]", "", str(b.get("telefono") or "")).strip()[:20]
    email = str(b.get("email") or "").strip().lower()[:120]
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return JSONResponse({"ok": False, "error": "El correo del cliente no es válido."}, status_code=400)
    sim, _iso = _moneda_de(c)
    desc = datos.descuentos(c["id"], [fr])
    sugerido = horarios.precio_turno_de(cd, hora, desc.get((fr, hora), 0))
    try:
        precio = int(round(float(b.get("precio")))) if b.get("precio") not in (None, "") else sugerido
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "Precio inválido."}, status_code=400)
    if precio < 0 or precio > 100000:
        return JSONResponse({"ok": False, "error": "Precio inválido."}, status_code=400)
    if (c["id"], fr, hora) in datos.bloqueos_de([c["id"]], [fr]):
        return JSONResponse({"ok": False, "error": "Ese turno está bloqueado. Desbloquéalo primero."}, status_code=409)
    fila = {"id": f"man_{int(time.time() * 1000)}_w", "cancha_id": c["id"], "jugador": nombre, "nivel": "",
            "fecha": fr, "dia": horarios.etiqueta_dia(fr, ahora.date()), "hora_inicio": hora, "hora_fin": horarios.hora_fin(hora, paso),
            "estado": "confirmada", "traida_por_app": False, "precio": precio, "sena": 0, "pagado": bool(b.get("pagado")),
            "usuario": email, "deporte": c.get("deporte") or "", "moneda": sim, "extras": [], "telefono": telefono,
            "grupo_reserva_id": "", "medio_pago": "manual"}
    r = datos.insertar_reservas([fila])
    if r == "ocupado":
        return JSONResponse({"ok": False, "error": "Ese turno ya tiene una reserva."}, status_code=409)
    if r:
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento."}, status_code=503)
    if email:
        # Push al JUGADOR "te reservaron" (mismo aviso que manda el app).
        from pagos import router as pr
        lugar = (c.get("club") or "").strip() or c["nombre"]
        _en_segundo_plano(pr._aviso_push_usuario, email, "Reserva confirmada 🎾",
                          f"{lugar} · {horarios.fecha_larga(fr)} {hora}–{fila['hora_fin']}. El local te registró esta reserva. ¡Te esperamos!",
                          "reserva_manual")
    permisos.auditar(ses["email"], c, "reserva_manual", fila["id"], {"fecha": fr, "hora": hora, "cliente": nombre, "precio": precio, "pagado": fila["pagado"]})
    print(f"[manual-web] {ses['email']} registró {fila['id']} en {c['id']} {fr} {hora} · {sim} {precio} · pagado={fila['pagado']}", flush=True)
    return JSONResponse({"ok": True, "id": fila["id"], "precio": precio})


@router.post("/anfitrion/reserva/{res_id}/pagado")
async def marcar_pagado_web(request: Request, res_id: str) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_marcar_pagado_web, request, res_id, _cuerpo_json)


def _marcar_pagado_web(request: Request, res_id: str, _cuerpo_json) -> JSONResponse:
    """Marcar cobrada (efectivo) / volver a "por cobrar": igual que `marcarPago`
    del app, con el push "¡Te llegaron puntos! ⭐" al jugador en la
    transición no pagado → pagado de reservas traídas por la app."""
    ses, canchas = _canchas_sesion(request, permisos.MARCAR_PAGO)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    ids = [x["id"] for x in canchas]
    try:
        b = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        b = {}
    pagado = bool((b or {}).get("pagado", True))
    r = datos.reserva_de_dueno(res_id, ids)
    if r is None:
        return JSONResponse({"ok": False, "error": "Reserva no encontrada."}, status_code=404)
    medio = str(r.get("medio_pago") or "")
    if not pagado and r.get("pagado") and medio in ("yape", "tarjeta"):
        return JSONResponse({"ok": False, "error": "Esta reserva se pagó en línea: no se puede marcar por cobrar."}, status_code=400)
    if bool(r.get("pagado")) == pagado:
        return JSONResponse({"ok": True, "sin_cambio": True})
    if not datos.marcar_pagado(res_id, ids, pagado):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento."}, status_code=503)
    usuario = str(r.get("usuario") or "").strip().lower()
    if pagado and r.get("traida_por_app") in (True, 1, "true") and usuario and medio not in ("manual", "bono"):
        pts = int(round(float(r.get("precio") or 0) + sum(float(x.get("precio") or 0) for x in (r.get("extras") or []) if isinstance(x, dict))))
        c = next((x for x in canchas if x["id"] == r.get("cancha_id")), None)
        lugar = ((c or {}).get("club") or "").strip() or (c or {}).get("nombre") or "tu reserva"
        from pagos import router as pr
        _en_segundo_plano(pr._aviso_push_usuario, usuario, "¡Te llegaron puntos! ⭐",
                          f"El local confirmó tu pago: +{pts} puntos {MARCA} por tu reserva en {lugar}. Canjéalos como descuento en tu próxima reserva online.",
                          "puntos")
    permisos.auditar(ses["email"], next((x for x in canchas if x["id"] == r.get("cancha_id")), None),
                     "marcar_pagada" if pagado else "marcar_por_cobrar", res_id)
    print(f"[pago-web] {ses['email']} marcó {res_id} pagado={pagado}", flush=True)
    return JSONResponse({"ok": True, "pagado": pagado})


@router.post("/anfitrion/reserva/{res_id}/quitar")
async def quitar_reserva_manual(request: Request, res_id: str) -> JSONResponse:
    return await run_in_threadpool(_quitar_reserva_manual, request, res_id)


def _quitar_reserva_manual(request: Request, res_id: str) -> JSONResponse:
    ses, canchas = _canchas_sesion(request, permisos.QUITAR_MANUAL)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    ids = [x["id"] for x in canchas]
    r = datos.reserva_de_dueno(res_id, ids)
    if r is None:
        return JSONResponse({"ok": False, "error": "Reserva no encontrada."}, status_code=404)
    if str(r.get("medio_pago") or "") != "manual":
        return JSONResponse({"ok": False, "error": "Solo se quitan reservas manuales. Las pagadas por la app se cancelan con reembolso."}, status_code=400)
    if not datos.borrar_reserva_manual(res_id, ids):
        return JSONResponse({"ok": False, "error": "No pudimos quitarla en este momento."}, status_code=503)
    from web import jugador_espera as _je
    _je.avisar_liberados([(str(r.get("cancha_id")), str(r.get("fecha")), str(r.get("hora_inicio")))])
    usuario = str(r.get("usuario") or "").strip().lower()
    if usuario:
        from pagos import router as pr
        c = next((x for x in canchas if x["id"] == r.get("cancha_id")), None)
        lugar = ((c or {}).get("club") or "").strip() or (c or {}).get("nombre") or "la cancha"
        _en_segundo_plano(pr._aviso_push_usuario, usuario, "Reserva cancelada 📅",
                          f"El local quitó tu reserva en {lugar} del {horarios.fecha_larga(str(r.get('fecha')))} {r.get('hora_inicio')}. Si tienes dudas, escríbele.",
                          "reserva_manual")
    permisos.auditar(ses["email"], next((x for x in canchas if x["id"] == r.get("cancha_id")), None), "quitar_manual", res_id,
                     {"fecha": str(r.get("fecha")), "hora": str(r.get("hora_inicio")), "cliente": str(r.get("jugador") or "")})
    print(f"[manual-web] {ses['email']} quitó {res_id}", flush=True)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/reserva/{res_id}/cancelar")
async def cancelar_reserva_anfitrion(request: Request, res_id: str) -> JSONResponse:
    return await run_in_threadpool(_cancelar_reserva_anfitrion, request, res_id)


def _cancelar_reserva_anfitrion(request: Request, res_id: str) -> JSONResponse:
    """El DUEÑO cancela una reserva pagada en línea (política fase 4,
    "cancela el anfitrión"): el jugador recupera el 100 % incluido el cargo
    por servicio a su medio de pago, la liquidación del dueño se revierte y el
    costo de pasarela de la devolución queda como deuda suya para la siguiente
    liquidación. Las manuales se quitan con "Quitar reserva"."""
    ses, canchas = _canchas_sesion(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    ids = [x["id"] for x in canchas]
    r = datos.reserva_de_dueno(res_id, ids)
    if r is None:
        return JSONResponse({"ok": False, "error": "Reserva no encontrada."}, status_code=404)
    if str(r.get("medio_pago") or "") == "manual":
        return JSONResponse({"ok": False, "error": "Las reservas manuales se quitan con «Quitar reserva»."}, status_code=400)
    grupo = str(r.get("grupo_reserva_id") or "").strip()
    filas = datos.reservas_por_grupo(grupo) if grupo else [r]
    filas = sorted([f for f in filas if str(f.get("cancha_id")) in ids], key=lambda x: (str(x.get("fecha")), str(x.get("hora_inicio"))))
    if not filas:
        return JSONResponse({"ok": False, "error": "Reserva no encontrada."}, status_code=404)
    c = next((x for x in canchas if x["id"] == r.get("cancha_id")), None)
    jugador = str(r.get("usuario") or "").strip().lower()
    if not jugador:
        # Sin correo del jugador no hay a quién devolver: solo se libera.
        if not datos.eliminar_reservas([str(f["id"]) for f in filas]):
            return JSONResponse({"ok": False, "error": "No pudimos liberar el horario."}, status_code=503)
        return JSONResponse({"ok": True, "reembolso": "no_aplica"})
    from web.router import _cancelar_reserva
    j = _cancelar_reserva(filas, c, jugador, medio="original", cancela_anfitrion=True, quien=ses["email"])
    print(f"[anfitrion-web] {ses['email']} canceló {res_id} → {j.get('reembolso')}", flush=True)
    return JSONResponse(j, status_code=200 if j.get("ok") else 400)


@router.get("/anfitrion/ingresos", response_class=HTMLResponse)
def pagina_ingresos(request: Request) -> HTMLResponse:
    """"Ingresos" de Airbnb: la billetera del dueño tal cual el backend (saldo,
    regalo, por recibir, liquidaciones pagadas y últimos movimientos)."""
    from pagos.router import _liquidacion_dict
    from pagos import cuentas_cobro as _cc
    ses, canchas, resp = _contexto(request, "/anfitrion/ingresos", "ingresos", sin_canchas_ok=True)
    if resp is not None:
        return resp
    email = ses["email"]
    if canchas:
        sim, pais_iso = _moneda_de(canchas[0])[0], _pais_de(canchas[0])
    else:  # sin canchas: la moneda y el país de su billetera (academia, torneos)
        from web.jugador_billetera import pais_billetera
        pais_iso = pais_billetera(email)[0] or "PE"
        sim = {"PE": "S/", "EC": "$", "BO": "Bs"}.get(pais_iso, "S/")
    cuenta = stores.cuenta_cobro(email)
    res_cta = _cc.resumen(cuenta)
    try:
        from pagos.router import moneda_billetera
        sim_bill = _sim_de_iso(moneda_billetera(email), sim)  # el saldo es de la moneda de SU billetera
    except Exception:  # noqa: BLE001
        sim_bill = sim
    saldo = stores.saldo_centimos(email) / 100.0
    promo = stores.saldo_promo_centimos(email) / 100.0
    liqs = [_liquidacion_dict(p) | {"liquidado": p.liquidado, "liquidado_en": p.liquidado_en.isoformat() if p.liquidado_en else "", "medio": p.medio or "",
                                    "sim_mov": _sim_de_iso(p.moneda, sim)}
            for p in stores.liquidaciones(email)]
    pend = [x for x in liqs if not x["liquidado"]]
    pagadas = [x for x in liqs if x["liquidado"]][::-1][:20]
    # Por recibir POR MONEDA: nunca se suman soles con dólares.
    por_mon: dict[str, float] = {}
    for x in pend:
        por_mon[x["sim_mov"]] = por_mon.get(x["sim_mov"], 0.0) + x["neto_soles"]
    por_recibir = sum(por_mon.values())
    orden = sorted(por_mon, key=lambda k: (k != sim, k)) or [sim]
    valor_pr = (f"{e(orden[0])} {por_mon.get(orden[0], 0.0):.2f}"
                + "".join(f"<small class='mc-otra'>+ {e(k)} {por_mon[k]:.2f}</small>" for k in orden[1:]))
    movs = [p for p in stores.pagos if p.dueno_id == email][::-1][:30]

    def fila_liq(x: dict) -> str:
        return (f"<div class='mc-mov'><div class='mc-mov-t'><b>{e(x['concepto'])}</b><small>{e(x['creado_en'][:10])}{(' · pagada ' + e(x['liquidado_en'][:10])) if x.get('liquidado') else ''}"
                f"{(' · ' + e(x['medio'])) if x.get('medio') else ''}</small></div>"
                f"<div class='mc-mov-m'><b>{e(x.get('sim_mov') or sim)} {x['neto_soles']:.2f}</b><small>bruto {x['bruto_soles']:.2f} · comisión {x['comision_soles']:.2f}{(' · cargo por servicio del jugador ' + format(x.get('cargo_servicio_soles') or 0, '.2f')) if x.get('cargo_servicio_soles') else ''}</small></div></div>")

    def fila_mov(p) -> str:
        signo = "+" if p.tipo in ("recarga", "bono_recarga", "bono_bienvenida", "cupon", "bono_referido") else (
            "−" if p.tipo in ("comision_reserva", "comision_efectivo", "comision_deuda", "pro", "suscripcion") else "")
        estado = {"pendiente": "por pagar", "saldada": "pagada", "anulada": "anulada"}.get(p.estado, p.estado) if p.tipo == "comision_deuda" else p.estado
        return (f"<div class='mc-mov'><div class='mc-mov-t'><b>{e(p.concepto or p.tipo)}</b><small>{e(p.tipo)} · {e(p.creado_en.isoformat()[:10])} · {e(estado)}</small></div>"
                f"<div class='mc-mov-m'><b class='{'ok' if signo == '+' else ''}'>{signo}{e(_sim_de_iso(p.moneda, sim))} {p.monto_centimos / 100.0:.2f}</b></div></div>")
    # Cobro DIRECTO al club: deuda de comisión, tope y suspensión (misma
    # fuente que Cobros del club y el APK: `cobro_directo_web.estado_club`).
    bloque_directo = ""
    try:
        from web import cobro_directo_web as _cdw
        from web.anfitrion_cobros_club import tarjeta_comision
        est = _cdw.estado_club(email)
        com = est.get("comision") or {}
        if canchas and (com.get("deuda_centimos") or com.get("suspendido") or est.get("medios")
                        or (est.get("culqi") or {}).get("configurada")):
            bloque_directo = tarjeta_comision(est, email, est.get("moneda") or "PEN")
    except Exception as ex:  # noqa: BLE001
        print(f"[ingresos-web] sin estado de cobro directo: {ex}", flush=True)
    kp = [va.kpi("billete", "Por recibir (reservas en línea)", valor_pr, color="verde",
                 sub=f"{len(pend)} {'liquidación pendiente' if len(pend) == 1 else 'liquidaciones pendientes'}"),
          va.kpi("tarjeta", f"Saldo {MARCA}", f"{e(sim_bill)} {saldo:.2f}", sub="de aquí sale la comisión")]
    if promo > 0:
        kp.append(va.kpi("bono", "Saldo de regalo", f"{e(sim_bill)} {promo:.2f}", color="morado", sub="cubre comisiones"))

    def _lista(titulo: str, filas_html: str, vacio: str) -> str:
        return va.panel(filas_html or f"<p class='mc-vacio'>{vacio}</p>", titulo)
    cuerpo = (
        va.cabecera("Ingresos", "La misma billetera que ves en la app.", volver="/anfitrion/mis-canchas",
                    acciones="<a class='btn sec' href='/mi-billetera#recargar'>Recargar saldo</a>")
        + va.kpis(kp)
        + bloque_directo
        + _tarjeta_cuenta_cobro(cuenta, res_cta, pais_iso, ses, por_recibir > 0)
        + ui.tarjeta_comision('reservas', sim, {'PE': 'PEN', 'EC': 'USD', 'BO': 'BOB'}.get(pais_iso, 'PEN'))
        + _lista("Por recibir", "".join(fila_liq(x) for x in pend), "Nada pendiente. Cuando un jugador pague en línea, el neto aparece aquí.")
        + _lista("Liquidaciones pagadas", "".join(fila_liq(x) for x in pagadas), "Aún no te hemos transferido liquidaciones.")
        + _lista("Últimos movimientos", "".join(fila_mov(p) for p in movs), "Sin movimientos todavía."))
    return ui.shell("Ingresos", _anf(va.vista(cuerpo, "vmc mc-ing") + f"<script>window.__cc={ui.json_js({'catalogo': _cc.catalogo(), 'pais': pais_iso, 'cuenta': cuenta or {}, 'nombre': ses.get('nombre') or ''}, ensure_ascii=False)};</script><script>{_JS_CUENTA_COBRO}</script>"),
                    sesion=ses, ancho=True, titulo_tab="Ingresos · Modo anfitrión")


def _tarjeta_cuenta_cobro(cuenta: dict | None, res: dict, pais_iso: str, ses: dict, hay_pendiente: bool) -> str:
    """"Cuenta de cobro": dónde le transferimos sus liquidaciones. Igual que en
    la billetera del app (pedido del director, 26-sep-2026). Todo por
    selección (tipo, banco, documento); solo números y titular se escriben."""
    if cuenta:
        estado = (f"<div class='cc-actual'><span class='ico'>{'🏦' if cuenta.get('tipo') == 'banco' else '📱'}</span>"
                  f"<div><b>{e(res['etiqueta'])}</b><small>Aquí te transferimos lo que recibes por reservas, ventas y torneos."
                  f"{' Los pagos por Yape/Plin los hacemos a mano; con cuenta bancaria entras al lote automático del banco.' if res.get('canal') == 'manual' and pais_iso == 'PE' else ''}</small></div>"
                  "<button type='button' class='btn sec' id='ccEditar'>Cambiar</button></div>")
    else:
        estado = ("<div class='cc-actual sin'><span class='ico'>⚠️</span><div><b>Aún no registraste dónde cobrar</b>"
                  f"<small>{'Ya tienes plata por recibir: ' if hay_pendiente else ''}Regístrala para que {MARCA} pueda transferirte."
                  "</small></div><button type='button' class='btn' id='ccEditar'>Registrar cuenta</button></div>")
    return (f"<section class='va-panel mc-cc' id='cuentaCobro'><h2>Cuenta de cobro</h2>{estado}"
            "<form id='ccForm' hidden>"
            "<label>¿Cómo quieres recibir tu plata?</label><div class='chips' id='ccTipo'></div>"
            "<div id='ccBancoBox' hidden><label>Banco</label><div class='chips' id='ccBanco'></div>"
            "<label>Tipo de cuenta</label><div class='chips' id='ccTipoCta'></div></div>"
            "<label for='ccNumero' id='ccNumeroLbl'>Número</label><input id='ccNumero' inputmode='numeric' autocomplete='off' maxlength='24'>"
            "<div id='ccCciBox' hidden><label for='ccCci'>CCI <span class='req'>código interbancario de 20 dígitos · en tu app del banco</span></label><input id='ccCci' inputmode='numeric' autocomplete='off' maxlength='26'></div>"
            "<label for='ccTitular'>Titular <span class='req'>tal como figura en la cuenta</span></label><input id='ccTitular' maxlength='80' autocomplete='name'>"
            "<label>Documento del titular</label><div class='chips' id='ccDoc'></div>"
            "<input id='ccDocNum' class='mc-docnum' aria-label='Número de documento' inputmode='numeric' autocomplete='off' maxlength='15' placeholder='Número de documento'>"
            "<div class='err' id='ccErr' style='display:none'></div>"
            "<div class='acciones mc-cc-acc'><button type='submit' class='btn' id='ccGuardar'>Guardar cuenta de cobro</button>"
            "<button type='button' class='btn sec' id='ccCancelar'>Cancelar</button></div>"
            "<p class='sub mc-nota'>Solo la usamos para transferirte. Nunca se muestra a jugadores.</p>"
            "</form></section>")


_JS_CUENTA_COBRO = r"""
(function(){
  var C = window.__cc, cat = C.catalogo[C.pais] || C.catalogo.PE, $ = function(id){ return document.getElementById(id); };
  var st = { tipo: (C.cuenta.tipo) || cat.tipos[0].codigo, banco: C.cuenta.banco || '', tipo_cuenta: C.cuenta.tipo_cuenta || 'ahorros', doc: C.cuenta.doc_tipo || cat.documentos[0].codigo };
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function chips(id, ops, sel, on){ var el = $(id); el.innerHTML = ops.map(function(o){ return "<button type='button' class='chip" + (o.codigo === sel ? ' sel' : '') + "' data-v='" + esc(o.codigo) + "'>" + esc(o.nombre) + '</button>'; }).join('');
    el.querySelectorAll('.chip').forEach(function(b){ b.addEventListener('click', function(){ on(b.dataset.v); pintar(); }); }); }
  function pintar(){
    chips('ccTipo', cat.tipos, st.tipo, function(v){ st.tipo = v; });
    var banco = st.tipo === 'banco';
    $('ccBancoBox').hidden = !banco;
    if(banco){ chips('ccBanco', cat.bancos, st.banco, function(v){ st.banco = v; }); chips('ccTipoCta', cat.tipos_cuenta, st.tipo_cuenta, function(v){ st.tipo_cuenta = v; }); }
    $('ccNumeroLbl').textContent = banco ? 'Número de cuenta' : ('Celular de ' + (st.tipo === 'plin' ? 'Plin' : 'Yape') + ' (' + cat.tel_longitud + ' dígitos)');
    $('ccCciBox').hidden = !(banco && cat.cci && st.banco !== 'BCP');
    chips('ccDoc', cat.documentos, st.doc, function(v){ st.doc = v; });
  }
  var form = $('ccForm'), btn = $('ccEditar');
  function abrir(){ form.hidden = false; $('ccNumero').value = C.cuenta.numero || ''; $('ccCci').value = C.cuenta.cci || ''; $('ccTitular').value = C.cuenta.titular || C.nombre || ''; $('ccDocNum').value = C.cuenta.doc_numero || ''; pintar(); form.scrollIntoView({behavior:'smooth', block:'center'}); }
  if(btn) btn.addEventListener('click', abrir);
  $('ccCancelar').addEventListener('click', function(){ form.hidden = true; });
  form.addEventListener('submit', function(ev){
    ev.preventDefault(); var err = $('ccErr'); err.style.display = 'none';
    var body = { pais: C.pais, tipo: st.tipo, banco: st.banco, tipo_cuenta: st.tipo_cuenta, numero: $('ccNumero').value, cci: $('ccCci').value, titular: $('ccTitular').value, doc_tipo: st.doc, doc_numero: $('ccDocNum').value };
    var b = $('ccGuardar'); b.disabled = true; if(window.pcgCargando) pcgCargando('Guardando…', {demora: 300});
    fetch('/anfitrion/cuenta-cobro', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function(r){ return r.json(); })
      .then(function(j){ if(window.pcgCargando) pcgCargando(false); b.disabled = false;
        if(j.ok){ if(window.pcgIr) pcgIr('/anfitrion/ingresos#cuentaCobro', 'Guardado ✓'); else location.reload(); return; }
        err.textContent = j.error || 'No se pudo guardar.'; err.style.display = 'block';
        var campo = {numero:'ccNumero', cci:'ccCci', titular:'ccTitular', doc_numero:'ccDocNum'}[j.campo]; if(campo && $(campo)) $(campo).focus(); })
      .catch(function(){ if(window.pcgCargando) pcgCargando(false); b.disabled = false; err.textContent = 'No se pudo guardar. Revisa tu conexión.'; err.style.display = 'block'; });
  });
})();
"""


@router.post("/anfitrion/cuenta-cobro")
async def guardar_cuenta_cobro(request: Request) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_guardar_cuenta_cobro, request, _cuerpo_json)


def _guardar_cuenta_cobro(request: Request, _cuerpo_json) -> JSONResponse:
    """Misma validación que `POST /pagos/cuenta-cobro` del app; el correo es
    el de la sesión de Google (nadie edita la cuenta de otro)."""
    from pagos import cuentas_cobro as _cc
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        body = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    cuenta, err, campo = _cc.validar(body if isinstance(body, dict) else {})
    if cuenta is None:
        return JSONResponse({"ok": False, "error": err, "campo": campo})
    c = stores.guardar_cuenta_cobro(ses["email"], cuenta)
    print(f"[cuenta-cobro] {ses['email']} (web) → {_cc.resumen(c)['etiqueta']}", flush=True)
    return JSONResponse({"ok": True, "resumen": _cc.resumen(c)})


@router.get("/anfitrion/canchas", response_class=HTMLResponse)
def pagina_canchas(request: Request, guardado: str = "", cancha: str = "", desde: str = "", vista: str = "") -> HTMLResponse:
    """Ruta vieja de "Canchas" (solo del dueño): la misma vista unificada de
    Mis canchas con SUS canchas, más el aviso de lo que acaba de guardar,
    registrar o agregar (los editores vuelven aquí)."""
    ses = sesion.de_request(request)
    mias = datos.canchas_de_dueno(ses["email"]) if ses else []
    por_id = {c["id"]: c for c in mias}
    aviso_ok, sel = "", cancha
    if guardado in por_id:
        sel = sel or guardado
        aviso_ok = va.aviso(f"Guardamos los cambios de <b>{e(por_id[guardado]['nombre'])}</b>. Ya se ven en la ficha pública y en la app.", "ok", ico="escudo")
    reg = por_id.get(request.query_params.get("registrada") or "")
    if reg:
        sel = sel or reg["id"]
        aviso_ok = va.aviso(f"Registramos <b>{e(reg.get('club') or reg['nombre'])}</b>. Queda en verificación: te avisamos por WhatsApp y en la app "
                            "cuando esté activa. Mientras tanto puedes completar fotos, hora feliz y servicios.", "ok", ico="escudo")
    loc = por_id.get(request.query_params.get("local_guardado") or "")
    if loc:
        sel = sel or loc["id"]
        n_loc = len(_hermanas_local(ses["email"], loc))
        aviso_ok = va.aviso(f"Guardamos los cambios de <b>{e(loc.get('club') or loc['nombre'])}</b>. Se aplicaron a sus {n_loc} cancha{'s' if n_loc != 1 else ''}.", "ok", ico="escudo")
    agr = por_id.get(request.query_params.get("agregada") or "")
    if agr:
        sel = sel or agr["id"]
        aviso_ok = va.aviso(f"Agregamos <b>{e(agr['nombre'])}</b> a <b>{e(agr.get('club') or '')}</b>. "
                            + ("Ya está activa y recibe reservas: el local ya estaba verificado." if datos.reservable(agr)
                               else "Se activará junto con el local cuando aprobemos la verificación."), "ok", ico="escudo")
    return _mis_canchas(request, _volver(request), "canchas", cancha=sel, desde=desde, vista=vista, solo_dueno=True, aviso_ok=aviso_ok)



# ── EDITAR CANCHA (como el editor de anuncios de Airbnb) ──────────────────────
# Mismo formulario, catálogos y validaciones que `editar_cancha_screen.dart`:
# fotos, nombre/local, deportes + tipo de piso, precio + hora feliz + seña,
# horario + duración, servicios del local (gratis) y servicios extra (de pago).
# Solo el DUEÑO (correo de la sesión = `dueno`) puede editar; el UPDATE lo
# vuelve a exigir en el WHERE. Lo que se guarda lo lee el app tal cual (la
# nube manda: `_sincronizarConfigLocalDesdeNube`).

_HORA_RE = re.compile(r"^([01]\d|2[0-3]):00$")


def _cancha_propia(ses: dict, cancha_id: str) -> dict | None:
    return next((c for c in datos.canchas_de_dueno(ses["email"]) if c["id"] == cancha_id), None)


def _chips(nombre: str, opciones, sel, *, multi: bool = False, fmt=None) -> str:
    out = []
    for o in opciones:
        k, txt = (o if isinstance(o, tuple) else (o, fmt(o) if fmt else str(o)))
        on = (k in sel) if multi else (k == sel)
        out.append(f"<button type='button' class='chip{' sel' if on else ''}' data-g='{e(nombre)}' data-v='{e(str(k))}'>{txt}</button>")
    return f"<div class='chips' data-grupo='{e(nombre)}' data-multi='{1 if multi else 0}'>{''.join(out)}</div>"


# ── PRECIO POR HORA o POR TURNO (pedido del director, 29-sep-2026: "debo tener
# la opción de cobrar 15 soles la hora o 15 por 1.5 h") ─────────────────────
# Espejo del bloque del APK (`editar_cancha_screen`, `_SelectorPrecio`). Con
# "Por turno" se guarda `precio_turno` y, en `precio_hora`, el equivalente por
# hora para que los APKs viejos cobren lo mismo (horarios.precio_hora_equivalente).
MODOS_PRECIO = [("hora", "Por hora"), ("turno", "Por turno")]


def _bloque_precio(sim: str, c: dict | None = None, *, mon_id: str = "", placeholder: str = "") -> str:
    c = c or {}
    turno = float(c.get("precio_turno") or 0)
    modo = "turno" if turno > 0 else "hora"
    valor = turno if turno > 0 else float(c.get("precio_hora") or 0)
    val_txt = f"{valor:.2f}" if valor > 0 else ""
    return (f"<label>¿Cómo cobras?</label>{_chips('modo_precio', MODOS_PRECIO, modo)}"
            f"<label for='precio' id='precioLbl' style='margin-top:12px'>{'Precio por turno' if modo == 'turno' else 'Precio por hora'}</label>"
            f"<div class='inp-moneda'><span{(' id=' + chr(39) + mon_id + chr(39)) if mon_id else ''}>{e(sim)}</span><input id='precio' name='precio' type='number' min='1' step='0.01' inputmode='decimal' value='{val_txt}'{(' placeholder=' + chr(39) + e(placeholder) + chr(39)) if placeholder else ''}></div>"
            f"<p class='sub' id='precioPrev' data-sim='{e(sim)}' style='font-size:13px;margin-top:6px'></p>")


# Actualiza la etiqueta y la vista previa ("Un turno de 1 h 30 cuesta S/ 22.50").
# Lee la duración de los chips `duracion_slot_min` o del select del mismo nombre.
JS_PRECIO = r"""
(function(){
  function modo(){var b=document.querySelector(".chip.sel[data-g='modo_precio']");return b?b.dataset.v:'hora'}
  function dur(){var b=document.querySelector(".chip.sel[data-g='duracion_slot_min']");if(b)return parseInt(b.dataset.v)||60;var s=document.querySelector("select[name='duracion_slot_min']");return s?(parseInt(s.value)||60):60}
  function txtDur(m){var h=Math.floor(m/60),r=m%60;return h?(h+' h'+(r?' '+(r<10?'0':'')+r:'')):(r+' min')}
  window.pcgPrecioBody=function(){var p=parseFloat((document.getElementById('precio')||{}).value)||0;return {modo_precio:modo(),precio:p,precio_hora:p}};
  function pintar(){var lbl=document.getElementById('precioLbl'),pv=document.getElementById('precioPrev'),inp=document.getElementById('precio');if(!pv||!inp)return;
    var m=modo(),d=dur(),p=parseFloat(inp.value)||0,ms=document.getElementById('monSpan'),sim=(ms&&ms.textContent)||pv.dataset.sim||'S/';
    if(lbl)lbl.textContent=m==='turno'?'Precio por turno':'Precio por hora';
    if(p<=0){pv.textContent='';return}
    var turno=m==='turno'?p:p*d/60, hora=m==='turno'?p*60/d:p;
    turno=Math.floor(turno+0.5+1e-9);
    pv.textContent=m==='turno'?('Cada turno de '+txtDur(d)+' cuesta '+sim+' '+turno.toFixed(2)+' (equivale a '+sim+' '+hora.toFixed(2)+' la hora).')
                              :('Un turno de '+txtDur(d)+' cuesta '+sim+' '+turno.toFixed(2)+'.')}
  document.addEventListener('click',function(ev){if(ev.target.closest&&ev.target.closest(".chip[data-g='modo_precio'],.chip[data-g='duracion_slot_min']"))setTimeout(pintar,0)});
  document.addEventListener('input',function(ev){if(ev.target&&ev.target.id==='precio')pintar()});
  document.addEventListener('change',function(ev){if(ev.target&&ev.target.name==='duracion_slot_min')pintar()});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',pintar);else pintar();
})();
"""


def _precio_de_body(b: dict, dur: int) -> tuple[float, float, str]:
    """(precio_hora, precio_turno, error) desde el cuerpo del editor. Acepta el
    cuerpo viejo (`precio_hora` a secas = por hora)."""
    modo = str(b.get("modo_precio") or "hora").strip().lower()
    crudo = b.get("precio") if b.get("precio") not in (None, "") else b.get("precio_hora")
    try:
        precio = round(float(crudo), 2)
    except (TypeError, ValueError):
        return 0.0, 0.0, "Pon el precio por turno." if modo == "turno" else "Pon el precio por hora."
    if not (0 < precio <= 100000):
        return 0.0, 0.0, "El precio por turno debe ser mayor a 0." if modo == "turno" else "El precio por hora debe ser mayor a 0."
    if modo == "turno":
        return horarios.precio_hora_equivalente(precio, dur), precio, ""
    return precio, 0.0, ""


def _select_hora(nombre: str, valor: str) -> str:
    ops = "".join(f"<option value='{h}'{' selected' if h == valor else ''}>{h}</option>" for h in catalogos.HORAS)
    return f"<select name='{nombre}' id='{nombre}'>{ops}</select>"


def _nota_fotos_local(c: dict) -> str:
    """Campaña de FOTOS PROPIAS DE LOS LOCALES: cuántas lleva el local y hasta
    cuándo (cuentan las fotos propias de todas sus canchas)."""
    est = fotos_locales.estado_de_cancha(c)
    if not est or est.get("estado") not in ("pendiente", "vencido"):
        return ""
    cuando = (f"antes del {fotos_locales.fecha_corta(est.get('vence'))}" if est["estado"] == "pendiente"
              else "para volver a mostrar fotos")
    return (f"<div class='aviso {'warn' if est['estado'] == 'pendiente' else 'err'}' style='margin:10px 0'>📷 Tu local lleva "
            f"<b>{est['n']} de {est['minimo']}</b> fotos propias: sube {est['faltan']} más {cuando}. "
            "Cuentan las fotos que subas en cualquiera de las canchas del local; las de Google no cuentan.</div>")


@router.get("/anfitrion/cancha/{cancha_id}/editar", response_class=HTMLResponse)
def pagina_editar_cancha(request: Request, cancha_id: str) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/cancha/{cancha_id}/editar")
    if resp is not None:
        return resp
    c = _cancha_propia(ses, cancha_id)
    if c is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Esta cancha no está a tu nombre"); r.status_code = 404
        return r
    sim, _iso = _moneda_de(c)
    deps = [d for d in _deportes_de(c) if d in catalogos.DEPORTES_ACTIVOS or d in catalogos.DEPORTES_LEGADO]
    if not deps:
        deps = ["futbol"]
    principal = catalogos.deporte_principal(deps)
    dep_ops = [(d, f"{_deporte(d)[1]} {_deporte(d)[0]}") for d in catalogos.DEPORTES_ACTIVOS + [x for x in catalogos.DEPORTES_LEGADO if x in deps]]
    superficies = catalogos.SUPERFICIES.get(principal, [])
    fotos = _fotos_crudas(c)  # el editor muestra lo que hay en la fila
    # Servicios extra DE ESTA CANCHA (árbitro, petos, clase…), filtrados por
    # sus deportes (pelotero solo en raqueta, petos solo en fútbol). Los DEL
    # LOCAL (piscina, sauna, entrada general…) y los servicios gratis del local
    # se editan UNA vez en "Editar local" (pedido del director, sep-2026: "los
    # atributos del local no deberían repetirse en cada cancha").
    actuales = {str(x.get("clave")): _se.completar(x) for x in (c.get("servicios_extra") or []) if x.get("clave")}
    cat = _se.para_cancha(deps)
    conocidas = {x["clave"] for x in cat}
    fuera = [v for k, v in actuales.items() if k not in conocidas and v.get("ambito") != "local"]
    del_local = [v for v in actuales.values() if v.get("ambito") == "local"]
    filas_serv = ""
    for x in cat + fuera:
        k = x["clave"]
        on = k in actuales
        precio_txt = f"{float(actuales[k]['precio']):.2f}" if on else ""
        filas_serv += (f"<div class='serv{' sel' if on else ''}' data-serv='{e(k)}' data-ambito='cancha'>"
                       f"<button type='button' class='chip{' sel' if on else ''}' data-g='servicios' data-v='{e(k)}'>{x['emoji']} {e(x['nombre'])}</button>"
                       f"<span class='sub' style='margin:0;font-size:12px'>{_se.etiqueta_tipo(x['tipo'])}</span>"
                       f"<label class='precio-serv'{'' if on else ' hidden'}><span>{e(sim)}</span>"
                       f"<input type='number' name='serv_{e(k)}' aria-label='Precio del servicio' min='0.5' step='0.5' inputmode='decimal' value='{precio_txt}' placeholder='Precio'></label></div>")
    local_nombre = (c.get("club") or "").strip() or c["nombre"]
    amen_txt = " · ".join(f"{catalogos.AMENIDADES[a][1]} {catalogos.AMENIDADES[a][0]}" for a in (c.get("amenidades") or []) if a in catalogos.AMENIDADES) or "ninguno configurado"
    loc_txt = " · ".join(f"{x['emoji']} {e(x['nombre'])} {e(sim)} {float(x['precio']):.2f} {_se.etiqueta_tipo(x['tipo'])}" for x in del_local) or "ninguno configurado"
    url_local = f"/anfitrion/local/{e(c['id'])}/editar"
    fotos_html = "".join(
        f"<div class='foto' data-url='{e(u)}'><img src='{e(u)}' alt=''>"
        f"<span class='portada'{'' if i == 0 else ' hidden'}>Portada</span>"
        "<div class='acc'><button type='button' class='mini' data-acc='portada' title='Usar como portada' aria-label='Usar esta foto como portada'>★</button>"
        "<button type='button' class='mini' data-acc='quitar' title='Quitar' aria-label='Quitar esta foto'>✕</button></div></div>" for i, u in enumerate(fotos))
    secciones = [("fotos", "Fotos"), ("nombre", "Nombre"), ("deportes", "Deportes y piso"), ("precio", "Precio y promociones"),
                 ("horario", "Horario"), ("extras", "Servicios extra"), ("local", "Tu local")]
    nav = "".join(f"<a href='#sec-{k}' class='edit-nav-it'>{n}</a>" for k, n in secciones)
    cfg = {"id": c["id"], "moneda": sim, "fotos": fotos, "deportes": deps, "superficie": c.get("superficie") or "",
           "superficies": catalogos.SUPERFICIES, "activos": catalogos.DEPORTES_ACTIVOS, "maxFotos": catalogos.MAX_FOTOS,
           "storage": almacen.disponible()}
    cuerpo = f"""
{va.cabecera('Editar cancha', f"{c['nombre']}{(' · ' + c.get('club')) if c.get('club') else ''} · {_zona(c) or MARCA}", volver=_url_mc(c['id']), acciones=f"<a class='btn sec' href='/reservar/{quote(c['id'], safe='')}'>Ver ficha pública</a>")}
<div class='edit-grid'>
<nav class='edit-nav'>{nav}</nav>
<form id='fEdit' class='edit-form' autocomplete='off' novalidate>
 <section class='va-panel edit-sec' id='sec-fotos'><h2>Fotos</h2><p class='sub'>La primera es la portada en Explorar y en la ficha. Hasta {catalogos.MAX_FOTOS} fotos.</p>{_nota_fotos_local(c)}
  <div class='edit-fotos' id='fotos'>{fotos_html}</div>
  <div class='acciones' style='margin-top:12px'><label class='btn sec' for='inFotos'>📷 Agregar fotos</label><input type='file' id='inFotos' accept='image/*' multiple hidden{' disabled' if not almacen.disponible() else ''}>
  <span class='sub' id='fotosMsg' style='margin:0'>{'' if almacen.disponible() else 'La subida de fotos desde la web no está disponible en este ambiente; súbelas desde la app.'}</span></div>
 </section>
 <section class='va-panel edit-sec' id='sec-nombre'><h2>Nombre</h2>
  <label for='nombre'>Nombre de la cancha</label><input id='nombre' name='nombre' maxlength='{catalogos.NOMBRE_MAX}' value='{e(c['nombre'])}' placeholder='Ej. Cancha 1 · Grass'>
  <p class='sub' style='font-size:13px'>Pertenece a <b>{e(local_nombre)}</b>. El nombre del local, la dirección y sus servicios se editan una sola vez en <a href='{url_local}'>Editar local</a>.</p>
 </section>
 <section class='va-panel edit-sec' id='sec-deportes'><h2>Deportes y tipo de piso</h2><p class='sub'>Marca todo lo que se juega en esta misma superficie (la agenda es una sola).</p>
  {_chips('deportes', dep_ops, set(deps), multi=True)}
  <label style='margin-top:18px'>Tipo de piso <span class='req'>obligatorio</span></label>
  <div id='supWrap'>{_chips('superficie', superficies, c.get('superficie') or '')}</div>
 </section>
 <section class='va-panel edit-sec' id='sec-precio'><h2>Precio y promociones</h2>
  {_bloque_precio(sim, c)}
  <label style='margin-top:18px'>⚡ Hora feliz (descuento en horas valle)</label>
  {_chips('descuento_valle', catalogos.DESCUENTOS_VALLE, int(c.get('descuento_valle') or 0), fmt=lambda v: 'Sin descuento' if v == 0 else f'−{v} %')}
  <div id='valleWrap' class='row' style='margin-top:10px'{'' if int(c.get('descuento_valle') or 0) > 0 else ' hidden'}>
   <div><label for='valle_desde'>Desde</label>{_select_hora('valle_desde', c.get('valle_desde') or '07:00')}</div>
   <div><label for='valle_hasta'>Hasta</label>{_select_hora('valle_hasta', c.get('valle_hasta') or '12:00')}</div>
   <p class='sub' id='vallePrev' style='grid-column:1/-1;margin:0'></p>
  </div>
  <label style='margin-top:18px'>Seña para reservar (anti no-show)</label>
  {_chips('sena_pct', catalogos.SENAS, int(c.get('sena_pct') or 0), fmt=lambda v: 'Sin seña' if v == 0 else f'{v} %')}
  <p class='sub' id='senaPrev' style='font-size:13px'></p>
 </section>
 <section class='va-panel edit-sec' id='sec-horario'><h2>Horario</h2>
  <div class='row'><div><label for='hora_apertura'>Abre</label>{_select_hora('hora_apertura', c['hora_apertura'])}</div>
  <div><label for='hora_cierre'>Cierra</label>{_select_hora('hora_cierre', c['hora_cierre'])}</div></div>
  <p class='sub' style='font-size:13px'>La hora de cierre es la hora en que <b>empieza el último turno</b>: si cierras a las 23:00, el último turno es 23:00–00:00. Un cierre menor o igual a la apertura cae al día siguiente (00:00 = hasta medianoche, 00:00→00:00 = 24 h).</p>
  <label style='margin-top:14px'>Duración del turno</label>
  {_chips('duracion_slot_min', catalogos.DURACIONES, int(c.get('duracion_slot_min') or 60), fmt=catalogos.etiqueta_duracion)}
 </section>
 <section class='va-panel edit-sec' id='sec-extras'><h2>Servicios extra de esta cancha</h2><p class='sub'>De pago: el jugador los agrega al reservar y suman al total. Solo los que aplican a {e(' / '.join(_deporte(d)[0] for d in deps))}. Los del local (piscina, sauna, entrada general…) van en <a href='{url_local}'>Editar local</a>.</p>
  <div class='servs'>{filas_serv}</div>
  <div style='margin-top:18px;padding-top:14px;border-top:1px solid var(--linea,#E4E4E4)'>
   <label for='sugTxt'>¿Tu local ofrece algo que no está en la lista? <span class='req'>lo revisa el equipo de {MARCA} y lo agrega al catálogo</span></label>
   <div class='acciones' style='align-items:center'><input id='sugTxt' maxlength='120' placeholder='Ej. Frontón, clases de natación, cochera techada' style='flex:1;min-width:220px'><button type='button' class='btn sec' id='btnSug'>💡 Sugerir</button></div>
   <span class='sub' id='sugMsg' style='margin:4px 0 0'></span>
  </div>
 </section>
 <section class='va-panel edit-sec' id='sec-local'><h2>Tu local</h2><p class='sub'>Lo que comparten todas las canchas de <b>{e(local_nombre)}</b>. Se edita una sola vez.</p>
  <p class='sub' style='margin:6px 0 0'><b>Dirección:</b> {e(c.get('direccion') or '—')}{(' · ' + e(_zona(c))) if _zona(c) else ''}</p>
  <p class='sub' style='margin:6px 0 0'><b>Servicios del local (gratis):</b> {amen_txt}</p>
  <p class='sub' style='margin:6px 0 0'><b>Servicios extra del local:</b> {loc_txt}</p>
  <div class='acciones' style='margin-top:10px'><a class='btn sec' href='{url_local}'>✏️ Editar local</a></div>
 </section>
</form>
</div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>Los cambios se ven al instante en la ficha pública y en la app.</span>
<button type='button' class='btn' id='btnGuardar'>Guardar cambios</button></div></div>
<script>var CFG={ui.json_js(cfg, ensure_ascii=False)};</script>
<script>{JS_PRECIO}</script><script>{_JS_EDITAR}</script>"""
    return ui.shell("Editar cancha", _anf(va.vista(cuerpo, "vmc")), sesion=ses, ancho=True,
                    titulo_tab=f"Editar {c['nombre']} · Modo anfitrión")


_JS_EDITAR = r"""
(function(){
var f=document.getElementById('fEdit'), fotos=CFG.fotos.slice(), dep=CFG.deportes.slice(), sup=CFG.superficie, subiendo=0;
function $(id){return document.getElementById(id)}
function sel(g){return Array.prototype.slice.call(document.querySelectorAll(".chip.sel[data-g='"+g+"']")).map(function(b){return b.dataset.v})}
function principal(){for(var i=0;i<CFG.activos.length;i++){if(dep.indexOf(CFG.activos[i])>=0)return CFG.activos[i]}return dep[0]||'futbol'}
function pintarSup(){var ops=CFG.superficies[principal()]||[];if(ops.indexOf(sup)<0)sup='';
  $('supWrap').innerHTML="<div class='chips' data-grupo='superficie'>"+ops.map(function(o){return "<button type='button' class='chip"+(o===sup?' sel':'')+"' data-g='superficie' data-v='"+o.replace(/'/g,'&#39;')+"'>"+o+"</button>"}).join('')+"</div>"}
function pintarFotos(){$('fotos').innerHTML=fotos.map(function(u,i){return "<div class='foto' data-url='"+u.replace(/'/g,'&#39;')+"'><img src='"+u.replace(/'/g,'&#39;')+"' alt=''><span class='portada'"+(i?' hidden':'')+">Portada</span><div class='acc'><button type='button' class='mini' data-acc='portada' title='Usar como portada' aria-label='Usar esta foto como portada'>★</button><button type='button' class='mini' data-acc='quitar' title='Quitar' aria-label='Quitar esta foto'>✕</button></div></div>"}).join('')}
function prev(){var p=parseFloat($('precio').value)||0, m=CFG.moneda, d=parseInt(sel('descuento_valle')[0]||'0'), s=parseInt(sel('sena_pct')[0]||'0');
  $('valleWrap').hidden=!(d>0);
  if(d>0){var a=$('valle_desde').value,b=$('valle_hasta').value;$('vallePrev').textContent='De '+a+' a '+b+(b<=a?' (del día siguiente)':'')+' la hora sale a '+m+' '+(p*(100-d)/100).toFixed(2)+' en vez de '+m+' '+p.toFixed(2)+'.'}
  $('senaPrev').textContent=s>0?'El jugador paga '+m+' '+(p*s/100).toFixed(2)+' al reservar y el resto en la cancha. Requiere pago en línea activo.':'Sin seña: el jugador puede reservar y pagar todo en la cancha.'}
document.addEventListener('click',function(ev){
  var b=ev.target.closest('.chip[data-g]'); if(b){var g=b.dataset.g, wrap=b.closest('.chips'), multi=wrap&&wrap.dataset.multi==='1';
    if(g==='deportes'){var i=dep.indexOf(b.dataset.v);if(i>=0){if(dep.length>1){dep.splice(i,1);b.classList.remove('sel')}}else{dep.push(b.dataset.v);b.classList.add('sel')}pintarSup();return}
    if(g==='superficie'){sup=(sup===b.dataset.v)?'':b.dataset.v;pintarSup();return}
    if(g==='servicios'){var row=b.closest('.serv');row.classList.toggle('sel');b.classList.toggle('sel');row.querySelector('.precio-serv').hidden=!row.classList.contains('sel');if(row.classList.contains('sel'))row.querySelector('input').focus();return}
    if(multi){b.classList.toggle('sel')}else{wrap.querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel')}
    prev();return}
  var a=ev.target.closest('.foto .mini'); if(a){var u=a.closest('.foto').dataset.url, i=fotos.indexOf(u);
    if(a.dataset.acc==='quitar'&&i>=0)fotos.splice(i,1); if(a.dataset.acc==='portada'&&i>0){fotos.splice(i,1);fotos.unshift(u)} pintarFotos()}
});
['precio','valle_desde','valle_hasta'].forEach(function(id){$(id).addEventListener('input',prev);$(id).addEventListener('change',prev)});
function comprimir(file){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var M=1600,w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
$('inFotos').addEventListener('change',async function(){var files=Array.prototype.slice.call(this.files||[]);this.value='';var msg=$('fotosMsg');
  for(var i=0;i<files.length;i++){if(fotos.length>=CFG.maxFotos){msg.textContent='Máximo '+CFG.maxFotos+' fotos.';break}
    subiendo++;msg.textContent='Subiendo foto '+(i+1)+' de '+files.length+'…';
    try{var blob=await comprimir(files[i]);var r=await fetch('/anfitrion/cancha/'+encodeURIComponent(CFG.id)+'/foto',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});var j=await r.json();
      if(j.ok&&j.url){fotos.push(j.url);pintarFotos();msg.textContent=''}else{msg.textContent=j.error||'No se pudo subir la foto.'}}
    catch(e){msg.textContent='No se pudo subir la foto. Revisa tu conexión.'}
    subiendo--}});
(function(){var pb=$('fidPctBox');if(pb)pb.style.display=(sel('fid_premio')[0]==='descuento')?'':'none'})();
$('btnSug').addEventListener('click',async function(){var t=$('sugTxt').value.trim(),m=$('sugMsg');if(t.length<3){m.textContent='Cuéntanos qué servicio ofrece tu local.';return}
  try{var r=await fetch('/anfitrion/servicios/sugerir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texto:t,cancha_id:CFG.id})});var j=await r.json();m.textContent=j.ok?'✅ ¡Gracias! Lo revisamos y te avisamos cuando esté disponible.':(j.error||'No se pudo enviar.');if(j.ok)$('sugTxt').value=''}catch(e){m.textContent='No se pudo enviar. Revisa tu conexión.'}});
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo>0){msg.textContent='Espera a que terminen de subir las fotos.';return}
  var serv=[];document.querySelectorAll('.serv.sel').forEach(function(r){serv.push({clave:r.dataset.serv,precio:parseFloat(r.querySelector('input').value)||0})});
  var body=Object.assign({nombre:$('nombre').value,deportes:dep,superficie:sup},pcgPrecioBody(),{
    descuento_valle:parseInt(sel('descuento_valle')[0]||'0'),valle_desde:$('valle_desde').value,valle_hasta:$('valle_hasta').value,
    sena_pct:parseInt(sel('sena_pct')[0]||'0'),hora_apertura:$('hora_apertura').value,hora_cierre:$('hora_cierre').value,
    duracion_slot_min:parseInt(sel('duracion_slot_min')[0]||'60'),servicios_extra:serv,fotos:fotos});
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Guardando…';
  try{var r=await fetch('/anfitrion/cancha/'+encodeURIComponent(CFG.id)+'/editar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){location.href='/anfitrion/canchas?guardado='+encodeURIComponent(CFG.id);return}
    msg.classList.add('err');msg.textContent=j.error||'No se pudo guardar.';if(j.campo){var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth',block:'start'})}}
  catch(e){msg.classList.add('err');msg.textContent='No se pudo guardar. Revisa tu conexión.'}
  btn.disabled=false});
prev();
})();
"""


def _validar_edicion(c: dict, b: dict) -> tuple[dict | None, str, str]:
    """Aplica las MISMAS reglas que `editar_cancha_screen._guardar`. Devuelve
    (campos a guardar, error, sección del error)."""
    if not isinstance(b, dict):
        return None, "Datos inválidos.", ""
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:catalogos.NOMBRE_MAX]
    if not nombre:
        return None, "Ponle un nombre a la cancha.", "nombre"
    club = re.sub(r"\s+", " ", str(b.get("club") or "")).strip()[:catalogos.NOMBRE_MAX] or (c.get("club") or nombre)
    deps_ok = catalogos.DEPORTES_ACTIVOS + catalogos.DEPORTES_LEGADO
    deps = []
    for d in (b.get("deportes") or []):
        d = str(d).lower()
        if d in deps_ok and d not in deps:
            deps.append(d)
    if not deps:
        return None, "Marca al menos un deporte.", "deportes"
    principal = catalogos.deporte_principal(deps)
    superficie = str(b.get("superficie") or "").strip()
    if superficie not in catalogos.SUPERFICIES.get(principal, []):
        return None, "Marca el tipo de piso de la cancha (obligatorio).", "deportes"
    try:
        desc = int(b.get("descuento_valle") or 0)
        sena = int(b.get("sena_pct") or 0)
        dur = int(b.get("duracion_slot_min") or 60)
    except (TypeError, ValueError):
        return None, "Datos inválidos.", "precio"
    if desc not in catalogos.DESCUENTOS_VALLE:
        return None, "Descuento de hora feliz no válido.", "precio"
    if sena not in catalogos.SENAS:
        return None, "Seña no válida.", "precio"
    if dur not in catalogos.DURACIONES:
        return None, "Duración del turno no válida.", "horario"
    precio, precio_turno, err_precio = _precio_de_body(b, dur)
    if err_precio:
        return None, err_precio, "precio"
    horas = {}
    for k, defecto in (("hora_apertura", "07:00"), ("hora_cierre", "23:00"), ("valle_desde", "07:00"), ("valle_hasta", "12:00")):
        v = str(b.get(k) or c.get(k) or defecto)
        if not _HORA_RE.match(v):
            return None, "Hora no válida (usa horas en punto).", "horario" if k.startswith("hora") else "precio"
        horas[k] = v
    if desc > 0 and horas["valle_desde"] == horas["valle_hasta"]:
        return None, "La hora feliz necesita un rango (desde y hasta distintos).", "precio"
    # Servicios del local (gratis): se editan en "Editar local"; si el cuerpo no
    # los trae (editor de cancha nuevo) se conservan los que la cancha ya tiene.
    amen = [str(a) for a in (c.get("amenidades") or []) if str(a) in catalogos.AMENIDADES] if "amenidades" not in b else []
    for a in (b.get("amenidades") or []):
        a = str(a)
        if a in catalogos.AMENIDADES and a not in amen:
            amen.append(a)
    servicios = []
    vistos = set()
    for s in (b.get("servicios_extra") or []):
        if not isinstance(s, dict):
            continue
        k = str(s.get("clave") or "")
        fila = _se.congelar(k, 0) if (k and k not in vistos) else None
        if fila is None:
            continue  # clave desconocida o repetida
        try:
            p = round(float(s.get("precio")), 2)
        except (TypeError, ValueError):
            p = 0
        if p <= 0:
            return None, f"Pon el precio de «{fila['nombre']}» o quítalo.", "extras"
        vistos.add(k)
        fila["precio"] = p
        servicios.append(fila)  # {clave, precio, nombre, emoji, tipo, ambito} congelados
    # Los servicios DEL LOCAL (piscina, sauna…) se administran en "Editar
    # local": si el cuerpo no trae ninguno, se conservan los que ya tenía.
    locales_body = [x for x in servicios if x.get("ambito") == "local"]
    if not locales_body:
        servicios += [_se.completar(x) for x in (c.get("servicios_extra") or [])
                      if x.get("clave") and _se.completar(x).get("ambito") == "local" and str(x.get("clave")) not in vistos]
    # Fotos: solo las que ya tenía la cancha o las subidas a SU carpeta del
    # bucket (nadie cuela una URL ajena en la galería).
    actuales = set(_fotos_crudas(c))
    prefijo = almacen.prefijo_cancha(c["id"]) if almacen.disponible() else None
    fotos = []
    for u in (b.get("fotos") or []):
        u = str(u).strip()
        if u and u not in fotos and (u in actuales or (prefijo and u.startswith(prefijo))):
            fotos.append(u)
    fotos = fotos[:catalogos.MAX_FOTOS]
    return {
        "nombre": nombre, "club": club, "deporte": principal, "deportes": deps, "superficie": superficie,
        "precio_hora": precio, "precio_turno": precio_turno or None, "descuento_valle": desc, "valle_desde": horas["valle_desde"], "valle_hasta": horas["valle_hasta"],
        "sena_pct": sena, "hora_apertura": horas["hora_apertura"], "hora_cierre": horas["hora_cierre"], "duracion_slot_min": dur,
        "amenidades": amen, "servicios_extra": servicios, "fotos": fotos, "foto_url": fotos[0] if fotos else "",
        "_propagar_locales": bool(locales_body),
    }, "", ""


# ── EDITAR LOCAL (pedido del director, sep-2026: "los atributos del local no
# deberían repetirse al editar cada cancha") ─────────────────────────────────
# Lo que comparten TODAS las canchas del local se edita UNA vez aquí: nombre
# del local, dirección, servicios del local (gratis, `amenidades`) y servicios
# extra de ámbito local (piscina, sauna, entrada general…). Al guardar se
# escribe en cada cancha del local (mismo `club`, mismo dueño), conservando en
# cada una sus servicios extra propios de cancha.

def _galeria_local(c: dict, hermanas: list[dict]) -> list[dict]:
    """Fotos de TODAS las canchas del local (la abierta primero), sin repetir,
    marcando cuáles son PROPIAS (subidas a Pichangol) y cuáles de Google u
    otro origen (no cuentan para la campaña y se pueden quitar)."""
    orden = [c] + [h for h in hermanas if h.get("id") != c.get("id")]
    out, vistos = [], set()
    for h in orden:
        for u in _fotos_crudas(h):
            if u in vistos:
                continue
            vistos.add(u)
            out.append({"url": u, "propia": fotos_reclamo.es_foto_propia(u, str(h.get("id") or ""))})
    return out


@router.get("/anfitrion/local/{cancha_id}/editar", response_class=HTMLResponse)
def pagina_editar_local(request: Request, cancha_id: str) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/local/{cancha_id}/editar")
    if resp is not None:
        return resp
    c = _cancha_propia(ses, cancha_id)
    if c is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Esta cancha no está a tu nombre"); r.status_code = 404
        return r
    hermanas = _hermanas_local(ses["email"], c)
    local = (c.get("club") or "").strip() or c["nombre"]
    sim, _ = _moneda_de(c)
    # Unión de lo configurado en las canchas del local (deberían coincidir).
    amen: list[str] = []
    locales_act: dict[str, dict] = {}
    for h in hermanas:
        for a in (h.get("amenidades") or []):
            if str(a) in catalogos.AMENIDADES and str(a) not in amen:
                amen.append(str(a))
        for x in (h.get("servicios_extra") or []):
            x = _se.completar(x)
            if x.get("clave") and x.get("ambito") == "local" and x["clave"] not in locales_act:
                locales_act[x["clave"]] = x
    cat = [x for x in _se.catalogo() if x["ambito"] == "local"]
    conocidas = {x["clave"] for x in cat}
    fuera = [v for k, v in locales_act.items() if k not in conocidas]
    filas_serv = ""
    for x in cat + fuera:
        k = x["clave"]
        on = k in locales_act
        precio_txt = f"{float(locales_act[k]['precio']):.2f}" if on else ""
        filas_serv += (f"<div class='serv{' sel' if on else ''}' data-serv='{e(k)}' data-ambito='local'>"
                       f"<button type='button' class='chip{' sel' if on else ''}' data-g='servicios' data-v='{e(k)}'>{x['emoji']} {e(x['nombre'])}</button>"
                       f"<span class='sub' style='margin:0;font-size:12px'>{_se.etiqueta_tipo(x['tipo'])}</span>"
                       f"<label class='precio-serv'{'' if on else ' hidden'}><span>{e(sim)}</span>"
                       f"<input type='number' name='serv_{e(k)}' aria-label='Precio del servicio' min='0.5' step='0.5' inputmode='decimal' value='{precio_txt}' placeholder='Precio'></label></div>")
    lista = "".join(f"<li>{_deporte(h.get('deporte'))[1]} <a href='/anfitrion/cancha/{e(h['id'])}/editar'>{e(h['nombre'])}</a> · {e(_deporte(h.get('deporte'))[0])}</li>" for h in hermanas)
    # TARJETA DE FIDELIDAD del local (sep-2026): cada N reservas pagadas, una
    # hora gratis o un % de descuento. Se guarda igual en todas las canchas.
    fid = _fid.config_de(next((h for h in hermanas if _fid.activa_en(h)), c))
    ventana_txt = {0: "Sin límite", 90: "90 días", 180: "6 meses", 365: "1 año"}
    fid_html = (
        "<p class='sub'>Como una tarjeta de sellos: el jugador ve su progreso en la ficha y, al llegar a la meta, el premio se aplica solo al reservar (app y web). "
        "Cuentan las reservas PAGADAS del jugador en cualquiera de tus canchas; el premio lo asumes tú (sale de tu liquidación).</p>"
        "<label>¿Activar la tarjeta?</label>" + _chips("fid_activa", [("1", "✅ Sí, premiar a mis clientes"), ("0", "No por ahora")], {"1" if fid["activa"] else "0"}) +
        "<label style='margin-top:14px'>Cada cuántas reservas</label>" + _chips("fid_meta", [(str(m), f"{m} reservas") for m in _fid.METAS], {str(fid["meta"])}) +
        "<label style='margin-top:14px'>Premio</label>" + _chips("fid_premio", [("hora_gratis", "🎁 Una hora gratis (el turno más barato del bloque)"), ("descuento", "🏷️ Descuento en la siguiente reserva")], {fid["premio"]}) +
        "<div id='fidPctBox'><label style='margin-top:14px'>Descuento</label>" + _chips("fid_pct", [(str(d), f"{d} %") for d in _fid.DESCUENTOS], {str(fid["descuentoPct"])}) + "</div>"
        "<label style='margin-top:14px'>Cuentan las reservas de los últimos</label>" + _chips("fid_ventana", [(str(v), ventana_txt[v]) for v in _fid.VENTANAS], {str(fid["ventanaDias"])}) +
        "<label style='margin-top:14px'>Qué reservas cuentan</label>" + _chips("fid_aplica", [("todas", "Todas las pagadas (en línea o en la cancha)"), ("online", "Solo las pagadas en línea")], {fid["aplica"]}) +
        "<p class='sub' style='margin-top:10px;font-size:12.5px'>Las reservas manuales que registras tú no cuentan. Si el jugador cancela una reserva premiada, recupera su premio.</p>")
    galeria = _galeria_local(c, hermanas)
    min_local = fotos_locales.minimo()
    est_local = fotos_locales.estado_de_cancha(c) or {}
    plazo_txt = ""
    if est_local.get("estado") == "pendiente" and est_local.get("vence"):
        plazo_txt = f" Tienes hasta el <b>{fotos_locales.fecha_corta(est_local.get('vence'))}</b>."
    elif est_local.get("estado") == "vencido":
        plazo_txt = " <b>El plazo venció:</b> mientras no las subas, tu local se muestra sin fotos."
    secciones = [("fotos", "Fotos del local"), ("local", "Nombre y dirección"), ("amenidades", "Servicios del local"),
                 ("extras", "Servicios extra del local"), ("fidelidad", "Fidelidad"), ("canchas", "Canchas")]
    from web import anfitrion_encargados as _enc
    enc_sec = _enc.seccion_editar_local(ses["email"], c)  # 👥 Encargados de este local ("" sin la migración 0005)
    secciones += [("encargados", "Encargados")] if enc_sec else []
    nav = "".join(f"<a href='#sec-{k}' class='edit-nav-it'>{n}</a>" for k, n in secciones)
    cfg = {"id": c["id"], "fotos": galeria, "minFotos": min_local, "maxFotos": catalogos.MAX_FOTOS,
           "storage": almacen.disponible()}
    cuerpo = f"""
{va.cabecera('Editar local', f"{local} · {len(hermanas)} cancha{'s' if len(hermanas) != 1 else ''}. Lo que cambies aquí se aplica a todas sus canchas; precio, horario, piso y servicios propios se editan en cada cancha.", volver=_url_mc(c['id']))}
<div class='edit-grid'>
<nav class='edit-nav'>{nav}</nav>
<form id='fLocal' class='edit-form' autocomplete='off' novalidate>
 <section class='va-panel edit-sec' id='sec-fotos'><h2>📷 Fotos del local</h2>
  <p class='sub'>Sube fotos reales de tu local (cancha, ingreso, vestuarios…). {MARCA} necesita al menos <b>{min_local or 3}</b> fotos tuyas.{plazo_txt}
  Las marcadas <b>Google</b> son temporales: no cuentan y se quitarán; puedes quitarlas tú cuando subas las tuyas. La primera foto es la portada.</p>
  <div id='contFotos' class='aviso' style='margin:10px 0'></div>
  <div class='edit-fotos' id='fotos'></div>
  <div class='acciones' style='margin-top:12px'><label class='btn sec' for='inFotos'>📷 Subir fotos del local</label><input type='file' id='inFotos' accept='image/*' multiple hidden{' disabled' if not almacen.disponible() else ''}>
  <button type='button' class='btn sec' id='btnSinGoogle' hidden>🧹 Quitar las de Google</button>
  <span class='sub' id='fotosMsg' style='margin:0'>{'' if almacen.disponible() else 'La subida de fotos desde la web no está disponible en este ambiente; súbelas desde la app.'}</span></div>
 </section>
 <section class='va-panel edit-sec' id='sec-local'><h2>Nombre y dirección</h2>
  <label for='local'>Nombre del local / club</label><input id='local' maxlength='{catalogos.NOMBRE_MAX}' value='{e(local)}' placeholder='Ej. Complejo Los Olivos'>
  <label for='direccion'>Dirección</label><input id='direccion' maxlength='160' value='{e(c.get('direccion') or '')}' placeholder='Av. Aviación 1234, San Borja'>
  <label>Ubicación del local <span class='req'>arrastra el pin si quedó corrido (hasta {PIN_MAX_M} m)</span></label>
  <div id='mapaLocal' style='height:260px;border-radius:var(--r-sm);margin-top:6px' aria-label='Mapa del local: arrastra el pin para ajustar la ubicación'></div>
  <p class='sub' style='font-size:13px' id='pinTxt'>Zona: {e(_zona(c)) or '—'}. Los jugadores llegan con este punto (Cómo llegar).</p>
 </section>
 <section class='va-panel edit-sec' id='sec-amenidades'><h2>Servicios del local</h2><p class='sub'>Gratis para el jugador. Salen como filtros en Explorar y se aplican a todas las canchas.</p>
  {_chips('amenidades', [(k, f'{ico} {e(n)}') for k, (n, ico) in catalogos.AMENIDADES.items()], set(amen), multi=True)}
 </section>
 <section class='va-panel edit-sec' id='sec-extras'><h2>Servicios extra del local</h2><p class='sub'>De pago, del recinto (piscina, sauna, entrada general…): el jugador los agrega al reservar cualquiera de tus canchas. Por reserva, por persona (el jugador elige cuántas) o por turno.</p>
  <div class='servs'>{filas_serv}</div>
  <div style='margin-top:18px;padding-top:14px;border-top:1px solid var(--linea,#E4E4E4)'>
   <label for='sugTxt'>¿Tu local ofrece algo que no está en la lista? <span class='req'>lo revisa el equipo de {MARCA} y lo agrega al catálogo</span></label>
   <div class='acciones' style='align-items:center'><input id='sugTxt' maxlength='120' placeholder='Ej. Frontón, clases de natación, cochera techada' style='flex:1;min-width:220px'><button type='button' class='btn sec' id='btnSug'>💡 Sugerir</button></div>
   <span class='sub' id='sugMsg' style='margin:4px 0 0'></span>
  </div>
 </section>
 <section class='va-panel edit-sec' id='sec-fidelidad'><h2>🎁 Tarjeta de fidelidad</h2>{fid_html}</section>
 <section class='va-panel edit-sec' id='sec-canchas'><h2>Canchas de este local</h2><p class='sub'>Precio, horario, piso, fotos y servicios propios (árbitro, petos…) se editan en cada una.</p>
  <ul class='sub' style='margin:0 0 0 18px'>{lista}</ul>
  <div class='acciones' style='margin-top:10px'><a class='btn sec' href='/anfitrion/cancha/{e(c['id'])}/agregar'>＋ Agregar cancha a este local</a></div>
 </section>
 {enc_sec}
</form>
</div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>Se aplica a las {len(hermanas)} cancha{'s' if len(hermanas) != 1 else ''} del local.</span>
<button type='button' class='btn' id='btnGuardar'>Guardar local</button></div></div>
<script>var CFG={ui.json_js(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{_JS_LOCAL}</script>
<script>{_JS_PIN.replace('⟦LAT⟧', ui.json_js(c.get('lat'))).replace('⟦LNG⟧', ui.json_js(c.get('lng'))).replace('⟦MAX⟧', str(PIN_MAX_M))}</script>"""
    return ui.shell("Editar local", _anf(va.vista(cuerpo, "vmc")), sesion=ses, ancho=True, extra_head=_LEAFLET,
                    titulo_tab=f"Editar {local} · Modo anfitrión")


# Ajustar el pin del local desde la web (antes: "se ajusta desde la app"). Solo
# un AJUSTE: más lejos que esto sería otro lugar (y otra verificación).
PIN_MAX_M = 300

_JS_PIN = r"""
(function(){
  var lat0 = ⟦LAT⟧, lng0 = ⟦LNG⟧, MAX = ⟦MAX⟧, el = document.getElementById('mapaLocal');
  if(!el || !window.L || lat0 == null || lng0 == null){ if(el) el.style.display = 'none'; return; }
  var mapa = L.map(el).setView([lat0, lng0], 17);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(mapa);
  L.circle([lat0, lng0], {radius: MAX, color: '#3056ED', weight: 1, fillOpacity: .05}).addTo(mapa);
  var pin = L.marker([lat0, lng0], {draggable: true, keyboard: true, title: 'Ubicación del local'}).addTo(mapa);
  pin.on('dragend', function(){
    var p = pin.getLatLng(), d = mapa.distance([lat0, lng0], p), t = document.getElementById('pinTxt');
    if(d > MAX){ pin.setLatLng([lat0, lng0]); window.__pinLocal = null;
      if(window.pcgAvisar) pcgAvisar({titulo: 'Muy lejos', icono: '📍', mensaje: 'Solo puedes ajustar el pin hasta ' + MAX + ' m. Si tu local se mudó, escríbenos.'}); return; }
    window.__pinLocal = {lat: Math.round(p.lat * 1e7) / 1e7, lng: Math.round(p.lng * 1e7) / 1e7};
    if(t) t.textContent = 'Pin movido ' + Math.round(d) + ' m. Guarda para aplicarlo a todas las canchas del local.';
  });
})();
"""

_JS_LOCAL = r"""
(function(){
function $(id){return document.getElementById(id)}
function sel(g){return Array.prototype.map.call(document.querySelectorAll(".chip.sel[data-g='"+g+"']"),function(b){return b.dataset.v})}
document.addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-g]');if(!b)return;var g=b.dataset.g;
  if(g.indexOf('fid_')===0){document.querySelectorAll(".chip[data-g='"+g+"']").forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');
    var pb=$('fidPctBox');if(pb)pb.style.display=(sel('fid_premio')[0]==='descuento')?'':'none';return}
  if(g==='servicios'){var row=b.closest('.serv');row.classList.toggle('sel');b.classList.toggle('sel');row.querySelector('.precio-serv').hidden=!row.classList.contains('sel');if(row.classList.contains('sel'))row.querySelector('input').focus();return}
  b.classList.toggle('sel')});
$('btnSug').addEventListener('click',async function(){var t=$('sugTxt').value.trim(),m=$('sugMsg');if(t.length<3){m.textContent='Cuéntanos qué servicio ofrece tu local.';return}
  try{var r=await fetch('/anfitrion/servicios/sugerir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texto:t,cancha_id:CFG.id})});var j=await r.json();m.textContent=j.ok?'✅ ¡Gracias! Lo revisamos y te avisamos cuando esté disponible.':(j.error||'No se pudo enviar.');if(j.ok)$('sugTxt').value=''}catch(e){m.textContent='No se pudo enviar. Revisa tu conexión.'}});
// ── FOTOS DEL LOCAL: propias (cuentan) y de Google (temporales, se quitan) ──
var fotos=(CFG.fotos||[]).slice(),subiendo=0;
function esc(t){return String(t).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function pintarFotos(){var box=$('fotos');if(!box)return;
  box.innerHTML=fotos.map(function(f,i){return "<div class='foto' data-url='"+esc(f.url)+"'><img src='"+esc(f.url)+"' alt=''>"+
    (i===0?"<span class='portada'>Portada</span>":"")+(f.propia?"":"<span class='portada' style='left:auto;right:8px;top:auto;bottom:8px;background:#5F6368;color:#fff'>Google</span>")+
    "<div class='acc'><button type='button' class='mini' data-acc='portada' title='Usar como portada' aria-label='Usar esta foto como portada'>★</button><button type='button' class='mini' data-acc='quitar' title='Quitar' aria-label='Quitar esta foto'>✕</button></div></div>"}).join('')||
    "<p class='sub' style='margin:0'>Aún no hay fotos. Sube las de tu local.</p>";
  var n=fotos.filter(function(f){return f.propia}).length,g=fotos.length-n,m=CFG.minFotos||0,c=$('contFotos');
  if(c){if(m>0&&n<m){c.className='aviso warn';c.innerHTML='📷 Llevas <b>'+n+' de '+m+'</b> fotos propias: sube '+(m-n)+' más.'}
        else{c.className='aviso ok';c.innerHTML='✅ Tu local tiene <b>'+n+'</b> fotos propias'+(g?' · aún muestras '+g+' de Google: quítalas para usar solo las tuyas.':'.')}}
  var bg=$('btnSinGoogle');if(bg)bg.hidden=!(g>0&&n>0)}
pintarFotos();
document.addEventListener('click',function(ev){var a=ev.target.closest('#fotos .mini');if(!a)return;var u=a.closest('.foto').dataset.url,i=-1;
  fotos.forEach(function(f,k){if(f.url===u)i=k});if(i<0)return;
  if(a.dataset.acc==='quitar')fotos.splice(i,1);if(a.dataset.acc==='portada'&&i>0){var f=fotos.splice(i,1)[0];fotos.unshift(f)}pintarFotos()});
if($('btnSinGoogle'))$('btnSinGoogle').addEventListener('click',async function(){
  var ok=await pcgConfirmar({titulo:'¿Quitar las fotos de Google?',mensaje:'Tu local quedará solo con las fotos que subiste. Se aplica al guardar.',confirmar:'Quitar',icono:'🧹'});
  if(ok){fotos=fotos.filter(function(f){return f.propia});pintarFotos()}});
function comprimir(file){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var M=1600,w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
if($('inFotos'))$('inFotos').addEventListener('change',async function(){var files=Array.prototype.slice.call(this.files||[]);this.value='';var msg=$('fotosMsg');
  for(var i=0;i<files.length;i++){if(fotos.filter(function(f){return f.propia}).length>=CFG.maxFotos){msg.textContent='Máximo '+CFG.maxFotos+' fotos.';break}
    subiendo++;msg.textContent='Subiendo foto '+(i+1)+' de '+files.length+'…';
    try{var blob=await comprimir(files[i]);var r=await fetch('/anfitrion/cancha/'+encodeURIComponent(CFG.id)+'/foto',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});var j=await r.json();
      if(j.ok&&j.url){var pos=fotos.filter(function(f){return f.propia}).length;fotos.splice(pos,0,{url:j.url,propia:true});pintarFotos();msg.textContent='Foto lista. No olvides «Guardar local».'}else{msg.textContent=j.error||'No se pudo subir la foto.'}}
    catch(e){msg.textContent='No se pudo subir la foto. Revisa tu conexión.'}
    subiendo--}});
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo>0){msg.textContent='Espera a que terminen de subir las fotos.';return}
  var serv=[];document.querySelectorAll('.serv.sel').forEach(function(r){serv.push({clave:r.dataset.serv,precio:parseFloat(r.querySelector('input').value)||0})});
  var fid={activa:sel('fid_activa')[0]==='1',meta:parseInt(sel('fid_meta')[0]||'5',10),premio:sel('fid_premio')[0]||'hora_gratis',descuentoPct:parseInt(sel('fid_pct')[0]||'20',10),ventanaDias:parseInt(sel('fid_ventana')[0]||'180',10),aplica:sel('fid_aplica')[0]||'todas'};
  var body={nombre_local:$('local').value,direccion:$('direccion').value,amenidades:sel('amenidades'),servicios_extra:serv,fidelidad:fid,fotos_local:fotos.map(function(f){return f.url})};
  if(window.__pinLocal){body.lat=window.__pinLocal.lat;body.lng=window.__pinLocal.lng;}
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Guardando…';
  try{var r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){location.href=j.url||'/anfitrion/canchas';return}msg.classList.add('err');msg.textContent=j.error||'No se pudo guardar.';if(j.campo){var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth'})}}
  catch(e){msg.classList.add('err');msg.textContent='No se pudo guardar. Revisa tu conexión.'}btn.disabled=false});
})();
"""


@router.post("/anfitrion/local/{cancha_id}/editar")
async def guardar_edicion_local(request: Request, cancha_id: str) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_guardar_edicion_local, request, cancha_id, _cuerpo_json)


def _guardar_edicion_local(request: Request, cancha_id: str, _cuerpo_json) -> JSONResponse:
    """Aplica nombre del local, dirección, servicios del local y servicios
    extra de ámbito local a TODAS las canchas del local del dueño."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    c = _cancha_propia(ses, cancha_id)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    try:
        b = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    if not isinstance(b, dict):
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    local = re.sub(r"\s+", " ", str(b.get("nombre_local") or "")).strip()[:catalogos.NOMBRE_MAX]
    if len(local) < 3:
        return JSONResponse({"ok": False, "error": "Pon el nombre de tu local.", "campo": "local"}, status_code=400)
    direccion = re.sub(r"\s+", " ", str(b.get("direccion") or "")).strip()[:160]
    amen = []
    for a in (b.get("amenidades") or []):
        a = str(a)
        if a in catalogos.AMENIDADES and a not in amen:
            amen.append(a)
    locales, vistos = [], set()
    for x in (b.get("servicios_extra") or []):
        if not isinstance(x, dict):
            continue
        k = str(x.get("clave") or "")
        fila = _se.congelar(k, 0) if (k and k not in vistos) else None
        if fila is None or fila.get("ambito") != "local":
            continue
        try:
            p = round(float(x.get("precio")), 2)
        except (TypeError, ValueError):
            p = 0
        if p <= 0:
            return JSONResponse({"ok": False, "error": f"Pon el precio de «{fila['nombre']}» o quítalo.", "campo": "extras"}, status_code=400)
        vistos.add(k)
        fila["precio"] = p
        locales.append(fila)
    fid_cfg = None
    if isinstance(b.get("fidelidad"), dict):
        err, fid_cfg = _fid.validar(b.get("fidelidad"))
        if err:
            msgs = {"meta_invalida": "Elige cada cuántas reservas se gana el premio.", "premio_invalido": "Elige el premio.",
                    "descuento_invalido": "Elige el porcentaje de descuento."}
            return JSONResponse({"ok": False, "error": msgs.get(err, "Revisa la tarjeta de fidelidad."), "campo": "fidelidad"}, status_code=400)
        if not datos.col_fidelidad_disponible():
            fid_cfg = None  # la base aún no tiene la columna: no se rompe el resto del guardado
    pin = None
    if b.get("lat") is not None and b.get("lng") is not None:
        from propiedad.reclamos import _distancia_m
        try:
            nlat, nlng = float(b["lat"]), float(b["lng"])
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "Ubicación inválida.", "campo": "ubicacion"}, status_code=400)
        if c.get("lat") is None or c.get("lng") is None or _distancia_m(c["lat"], c["lng"], nlat, nlng) > PIN_MAX_M:
            return JSONResponse({"ok": False, "error": f"Solo puedes ajustar el pin hasta {PIN_MAX_M} m. Si tu local se mudó, escríbenos.",
                                 "campo": "ubicacion"}, status_code=400)
        pin = (round(nlat, 7), round(nlng, 7))
    hermanas = _hermanas_local(ses["email"], c)
    fotos_por, quitadas = _repartir_fotos_local(c, hermanas, b.get("fotos_local"))
    n = 0
    for h in hermanas:
        propios = [_se.completar(x) for x in (h.get("servicios_extra") or []) if x.get("clave")]
        nuevos = [x for x in propios if x.get("ambito") != "local"] + [dict(x) for x in locales]
        campos = {"club": local, "direccion": direccion or None, "amenidades": amen, "servicios_extra": nuevos}
        if pin:
            campos["lat"], campos["lng"] = pin
        if fid_cfg is not None:
            campos["fidelidad"] = fid_cfg
        if fotos_por is not None and h["id"] in fotos_por:
            fs = fotos_por[h["id"]]
            campos["fotos"] = fs
            campos["foto_url"] = fs[0] if fs else None
        if datos.actualizar_cancha(h["id"], ses["email"], campos):
            n += 1
    if not n:
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento. Inténtalo de nuevo."}, status_code=503)
    if fotos_por is not None:
        fotos_locales.invalidar()  # el local pudo pasar a "ok" (campaña de fotos propias)
        if quitadas:
            _en_segundo_plano(lambda: [almacen.borrar_foto(u) for u in quitadas])
    print(f"[editar-local-web] {ses['email']} guardó {local!r}: {n} canchas · amen={amen} · extras_local={[x['clave'] for x in locales]} · fidelidad={fid_cfg}", flush=True)
    return JSONResponse({"ok": True, "url": f"/anfitrion/canchas?local_guardado={c['id']}", "canchas": n})


def _repartir_fotos_local(c: dict, hermanas: list[dict], lista) -> tuple[dict | None, list[str]]:
    """Aplica la galería de "Fotos del local" (Editar local) a las filas.

    Cada foto que el dueño conserva se queda en la(s) cancha(s) donde ya estaba
    (en el orden que eligió: la 1.ª es la portada); lo NUEVO solo se acepta si
    se subió a la carpeta de la cancha abierta (`fotos_reclamo.es_foto_propia`)
    y se guarda en esa cancha. Lo que quitó desaparece de todas las filas; las
    propias quitadas que ya ninguna fila usa se borran del bucket. Devuelve
    ({cancha_id: fotos} solo de las que cambian, urls a borrar) o (None, []) si
    el cuerpo no trajo la galería (clientes viejos)."""
    if not isinstance(lista, list):
        return None, []
    keep: list[str] = []
    for u in lista:
        u = str(u or "").strip()
        if u.startswith("http") and u not in keep:
            keep.append(u)
    antes = {h["id"]: _fotos_crudas(h) for h in hermanas}
    todas = {u for fs in antes.values() for u in fs}
    keep = [u for u in keep if u in todas or fotos_reclamo.es_foto_propia(u, str(c["id"]))]
    por: dict[str, list[str]] = {}
    for h in hermanas:
        viejas = antes[h["id"]]
        nuevas = [u for u in keep if u in viejas or (h["id"] == c["id"] and u not in todas)][:catalogos.MAX_FOTOS]
        if nuevas != viejas:
            por[h["id"]] = nuevas
    quedan = {u for h in hermanas for u in por.get(h["id"], antes[h["id"]])}
    quitadas = [u for u in todas if u not in quedan and any(fotos_reclamo.es_foto_propia(u, h["id"]) for h in hermanas)]
    return por, quitadas


def _propagar_servicios_local(email: str, cancha_id: str, club: str, servicios: list[dict]) -> int:
    """Los servicios de ÁMBITO LOCAL (piscina, sauna, entrada general…) son del
    recinto: al guardarlos en una cancha se copian a las demás canchas del
    mismo local (mismo `club`, mismo dueño), conservando en cada hermana sus
    servicios propios de cancha (árbitro, petos…). Devuelve cuántas se tocaron."""
    club = (club or "").strip().lower()
    if not club:
        return 0
    locales = [x for x in servicios if x.get("ambito") == "local"]
    n = 0
    for h in datos.canchas_de_dueno(email):
        if h["id"] == cancha_id or (h.get("club") or "").strip().lower() != club:
            continue
        propios = [_se.completar(x) for x in (h.get("servicios_extra") or []) if x.get("clave")]
        nuevos = [x for x in propios if x.get("ambito") != "local"] + [dict(x) for x in locales]
        if [(x["clave"], round(float(x["precio"]), 2)) for x in nuevos] == [(x["clave"], round(float(x["precio"]), 2)) for x in propios]:
            continue
        if datos.actualizar_cancha(h["id"], email, {"servicios_extra": nuevos}):
            n += 1
    return n


@router.post("/anfitrion/servicios/sugerir")
async def sugerir_servicio(request: Request) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_sugerir_servicio, request, _cuerpo_json)


def _sugerir_servicio(request: Request, _cuerpo_json) -> JSONResponse:
    """El dueño sugiere un servicio que no está en el catálogo; lo atiende el
    operador en la torre (Comunicación → Servicios extra). Texto libre SOLO
    hacia el equipo: nunca se publica."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        body = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    c = _cancha_propia(ses, str(body.get("cancha_id") or "")) if isinstance(body, dict) else None
    try:
        sug = _se.sugerir(ses["email"], str((body or {}).get("texto") or ""), cancha_id=c["id"] if c else "",
                          local=((c or {}).get("club") or (c or {}).get("nombre") or ""))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    print(f"[sugerencia-servicio] {ses['email']}: {sug['texto']!r} ({sug['local']})", flush=True)
    return JSONResponse({"ok": True, "id": sug["id"]})


@router.post("/anfitrion/cancha/{cancha_id}/editar")
async def guardar_edicion_cancha(request: Request, cancha_id: str) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_guardar_edicion_cancha, request, cancha_id, _cuerpo_json)


def _guardar_edicion_cancha(request: Request, cancha_id: str, _cuerpo_json) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    c = _cancha_propia(ses, cancha_id)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    try:
        body = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    campos, err, seccion = _validar_edicion(c, body)
    if campos is None:
        return JSONResponse({"ok": False, "error": err, "campo": seccion}, status_code=400)
    propagar = bool(campos.pop("_propagar_locales", False))
    quitadas = [u for u in _fotos_crudas(c) if u not in campos["fotos"]]  # antes del UPDATE (c puede ser la misma fila)
    if not datos.actualizar_cancha(cancha_id, ses["email"], campos):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento. Inténtalo de nuevo."}, status_code=503)
    fotos_locales.invalidar()  # el local pudo pasar a "ok" (campaña de fotos propias)
    if quitadas:
        _en_segundo_plano(lambda: [almacen.borrar_foto(u) for u in quitadas])
    if propagar:  # solo si el cuerpo trajo servicios del local (clientes que aún los mandan por cancha)
        _propagar_servicios_local(ses["email"], cancha_id, campos.get("club") or c.get("club") or "", campos.get("servicios_extra") or [])
    print(f"[editar-web] {ses['email']} guardó {cancha_id}: {campos['nombre']} · {campos['precio_hora']} · "
          f"{campos['hora_apertura']}-{campos['hora_cierre']}/{campos['duracion_slot_min']}m · fotos={len(campos['fotos'])}", flush=True)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/cancha/{cancha_id}/foto")
async def subir_foto_cancha(request: Request, cancha_id: str) -> JSONResponse:
    _cuerpo_bytes = await request.body()
    return await run_in_threadpool(_subir_foto_cancha, request, cancha_id, _cuerpo_bytes)


def _subir_foto_cancha(request: Request, cancha_id: str, _cuerpo_bytes: bytes = b"") -> JSONResponse:
    """Recibe la imagen (ya comprimida por el navegador) en el cuerpo y la sube
    al bucket `canchas` del app. Devuelve la URL pública para la galería."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    if _cancha_propia(ses, cancha_id) is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    if not almacen.disponible():
        return JSONResponse({"ok": False, "error": "La subida de fotos no está disponible en este ambiente."}, status_code=503)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp"):
        return JSONResponse({"ok": False, "error": "Formato no admitido (usa JPG, PNG o WebP)."}, status_code=415)
    cuerpo = _cuerpo_bytes
    if not cuerpo or len(cuerpo) > almacen.MAX_BYTES:
        return JSONResponse({"ok": False, "error": "La foto pesa demasiado (máx. 6 MB)."}, status_code=413)
    url = almacen.subir_foto(cancha_id, cuerpo, ctype)
    if not url:
        return JSONResponse({"ok": False, "error": "No se pudo subir la foto. Inténtalo de nuevo."}, status_code=502)
    return JSONResponse({"ok": True, "url": url})


# ── REGISTRAR / RECLAMAR CANCHA DESDE LA WEB (decisión del director, sep-2026:
# "web = vender y atender") ───────────────────────────────────────────────────
# Mismo flujo que `registrar_cancha_screen.dart`: la cancha nace en
# `pichangol_canchas` con `verificada=false` y `dueno` = correo de Google, y se
# crea un RECLAMO en el backend (`reclamos.crear_reclamo`, en proceso) que el
# operador aprueba en la torre. Nada queda activo sin esa aprobación; al
# aprobar, `reclamos._nube_verificada` marca `verificada=true` en la nube (el
# dueño web no necesita abrir el app). Catálogos y validaciones = las del app.

_LEAFLET = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
            "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>")
_ID_NUEVA_RE = re.compile(r"^u\d{12,14}$")
RELACIONES = [("dueno", "Dueño / propietario"), ("administrador", "Administrador"), ("encargado", "Encargado / socio")]
DOC_NOMBRE = {"PE": "DNI", "EC": "Cédula", "BO": "CI"}
DOC_LONGITUD = {"PE": 8, "EC": 10}  # BO: sin longitud fija (espejo de PaisConfig.docLongitud)


def _tel_completo(iso: str, local: str) -> str:
    return catalogos.TEL_PREFIJO.get(iso, "51") + re.sub(r"\D", "", local or "")


def _legado_cerca(nombre: str, lat, lng) -> dict | None:
    """Legado reclamable (registrada, sin dueño, sin verificar) a ≤120 m del
    punto que trae "Reclámala" desde una cancha DESCUBIERTA en Google: se
    ADOPTA esa fila en vez de crear otra (el explorador ya no lista las
    pendientes, así que el camino natural para reclamar el legado es el pin
    de Google → /lugar → Reclámala)."""
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    from web import descubrir as _d
    mejor, dist = None, 0.12
    for c in datos.canchas_publicas():
        if c.get("verificada") or (c.get("dueno") or "").strip() or not (c.get("lat") and c.get("lng")):
            continue
        d = _d._km(la, ln, float(c["lat"]), float(c["lng"]))
        if d <= dist:
            mejor, dist = c, d
    return mejor


def _legado_reclamable(cancha_id: str) -> dict | None:
    """Cancha ya registrada SIN dueño y sin verificar (mismo criterio que el
    "legado reclamable" de `AppState.misCanchas`): cualquiera puede reclamarla."""
    if not cancha_id or cancha_id.startswith("gp_"):
        return None
    c = datos.cancha(cancha_id)
    if not c or c.get("eliminada") or c.get("verificada") or (c.get("dueno") or "").strip():
        return None
    return c


def _texto_fotos_obligatorias(minimo: int) -> str:
    """Por qué pedimos fotos propias (decisión del director, 2-oct-2026)."""
    if minimo <= 0:
        return "Sube fotos reales de tu local; puedes agregarlas después."
    return (f"<b>Obligatorio: al menos {minimo} foto{'s' if minimo != 1 else ''} tuya{'s' if minimo != 1 else ''} del local.</b> "
            "Las fotos de Google no se pueden guardar (sus términos no lo permiten); las tuyas quedan para siempre en tu ficha y nos "
            "prueban que el local existe.")


def _error_faltan_fotos(minimo: int, n: int) -> str:
    return (f"Sube al menos {minimo} foto{'s' if minimo != 1 else ''} propia{'s' if minimo != 1 else ''} de tu local (llevas {n}). "
            "Las fotos de Google no cuentan: no se pueden guardar y las tuyas prueban que el local existe.")


@router.get("/anfitrion/nueva", response_class=HTMLResponse)
def pagina_nueva_cancha(request: Request, nombre: str = "", direccion: str = "", lat: str = "", lng: str = "", place: str = "",
                        deporte: str = "", cancha: str = "") -> HTMLResponse:
    """"Agregar local" = ASISTENTE de 4 pasos del rediseño (Frames 11-13):
    datos y ubicación · fotos y servicios · canchas · revisar y publicar (con
    TODA la verificación que exige el servidor: WhatsApp, relación, documento,
    prueba y ubicación del dispositivo). Es un stepper en el navegador sobre el
    MISMO formulario y el MISMO POST de siempre; vista previa "Así lo verán los
    jugadores", lista "Para publicar necesitas" y borrador en el navegador.
    Llega vacío, PRELLENADO desde una cancha descubierta en Google ("¿Es tuya?
    Reclámala": nombre, dirección, punto) o para reclamar un legado (?cancha=)."""
    ses, resp = _sesion_o_entrar(request, "/anfitrion/nueva" + (("?" + request.url.query) if request.url.query else ""))
    if resp is not None:
        return resp
    try:
        la, ln = (float(lat), float(lng)) if lat and lng else (None, None)
    except ValueError:
        la, ln = None, None
    # Cancha de LEGADO (registrada, sin dueño): se prellena todo y el envío la
    # ADOPTA (misma fila) en vez de crear otra.
    # Si el dueño YA tiene ese local en Pichangol (mismo nombre o a ≤120 m del
    # punto), la cancha nueva se AGREGA al local (hereda dirección, fotos,
    # servicios y verificación, como `AgregarCanchaScreen` del app) en vez de
    # registrar otro local con otro reclamo. Va ANTES del legado cercano: su
    # propio local manda sobre una fila huérfana vecina.
    if not cancha:
        propio = _local_propio(ses["email"], nombre, la, ln)
        if propio:
            return RedirectResponse(f"/anfitrion/cancha/{propio['id']}/agregar" + (f"?deporte={deporte}" if deporte in catalogos.DEPORTES_ACTIVOS else ""), status_code=303)
    existente = _legado_reclamable(cancha) or (_legado_cerca(nombre, la, ln) if (la is not None and ln is not None and not cancha) else None)
    pre = {"deportes": [], "superficie": "", "precio": "", "apertura": "07:00", "cierre": "23:00", "dur": 60, "nombre_cancha": "", "zona": ""}
    if existente:
        nombre = existente.get("club") or existente.get("nombre") or nombre
        direccion = existente.get("direccion") or direccion
        la, ln = (existente.get("lat"), existente.get("lng")) if existente.get("lat") or existente.get("lng") else (la, ln)
        pre = {"deportes": [d for d in _deportes_de(existente) if d in catalogos.DEPORTES_ACTIVOS], "superficie": existente.get("superficie") or "",
               "precio": f"{existente['precio_hora']:.2f}" if existente.get("precio_hora") else "", "precio_turno": float(existente.get("precio_turno") or 0), "apertura": existente.get("hora_apertura") or "07:00",
               "cierre": existente.get("hora_cierre") or "23:00", "dur": int(existente.get("duracion_slot_min") or 60),
               "nombre_cancha": existente.get("nombre") or "", "zona": existente.get("barrio") or ""}
    elif deporte in catalogos.DEPORTES_ACTIVOS:
        pre["deportes"] = [deporte]
    iso = paises.pais_de_coordenadas(la, ln) if la is not None else "PE"
    nuevo_id = existente["id"] if existente else f"u{int(time.time() * 1000)}"
    # FOTOS PROPIAS obligatorias (decisión del director, 2-oct-2026): al reclamar
    # un legado se precargan solo las fotos que ya están en SU carpeta.
    min_fotos = fotos_reclamo.minimo()
    previas_propias = fotos_reclamo.de_cancha(existente) if existente else []
    dep_ops = [(d, f"{_deporte(d)[1]} {_deporte(d)[0]}") for d in catalogos.DEPORTES_ACTIVOS]
    cfg = {"id": nuevo_id, "existente": bool(existente), "pre": pre, "lat": la, "lng": ln, "iso": iso, "place": place[:120], "superficies": catalogos.SUPERFICIES,
           "activos": catalogos.DEPORTES_ACTIVOS, "nombres": {d: _deporte(d)[0] for d in catalogos.DEPORTES_ACTIVOS},
           "maxFotos": catalogos.MAX_FOTOS, "storage": almacen.disponible(), "tel": catalogos.TEL_PREFIJO,
           "telLen": catalogos.TEL_LONGITUD, "labels": catalogos.GEO_LABELS, "doc": DOC_NOMBRE, "docLen": DOC_LONGITUD,
           "monedas": {k: paises.simbolo_de_moneda(v) for k, v in paises.MONEDA_POR_PAIS.items()},
           "minFotos": min_fotos, "fotosPrevias": previas_propias[:fotos_reclamo.maximo()],
           "exigirUbic": reclamos.exigir_ubicacion(), "ubicMaxM": config.RECLAMO_UBICACION_MAX_M}
    cfg["maxFotos"] = fotos_reclamo.maximo()
    # Asistente de 4 pasos (Frames 11-13) sobre el MISMO formulario y el MISMO
    # POST de siempre. Borrador en el navegador por cuenta y por contexto
    # (local nuevo, lugar de Google o cancha de legado).
    import hashlib
    ctx_b = ("legado:" + nuevo_id) if existente else (("place:" + place[:120]) if place else "nuevo")
    cfg["borrador"] = "pcg_borrador_local:" + hashlib.sha256(ses["email"].lower().encode()).hexdigest()[:12] + ":" + ctx_b
    cfg["prellenado"] = bool(nombre or direccion or la is not None)
    cfg["amen"] = {k: f"{ico} {n}" for k, (n, ico) in catalogos.AMENIDADES.items()}
    cfg["exigirUbic"] = bool(cfg["exigirUbic"])
    sim0 = paises.simbolo_de_moneda(paises.moneda_de_pais(iso))
    titulo = "Reclama tu cancha" if existente else "Agregar local"
    pasos_def = [("Datos y ubicación", "Nombre, dirección y mapa"),
                 ("Fotos y servicios", f"Mínimo {min_fotos} fotos tuyas" if min_fotos else "Fotos de tu local"),
                 ("Canchas", "Deporte, horario y precio"), ("Revisar y publicar", "Pasa a verificación")]
    pasos_html = "".join(
        f"<li><button type='button' class='wz-p' data-ir='{i}' aria-controls='wzPaso{i}'><span class='wz-n' aria-hidden='true'>{i}</span>"
        f"<span class='wz-pt'><b>{e(t)}</b><small>{e(s)}</small></span></button></li>" for i, (t, s) in enumerate(pasos_def, start=1))
    busca = ("" if existente or not config.PLACES_API_KEY else
             "<label for='busca'>Busca tu local en Google Maps <span class='req'>rellena nombre, dirección y ubicación</span></label>"
             "<input id='busca' maxlength='80' placeholder='Ej. Campo deportivo Edu Jr.' autocomplete='off'><div id='resBusca' class='res-busca' hidden></div>")
    amen = ("" if existente else
            va.panel(_chips('amenidades', [(k, f"{ico} {e(n)}") for k, (n, ico) in catalogos.AMENIDADES.items()], set(), multi=True),
                     "Servicios del local", "Marca lo que ofrece tu local (gratis para el jugador). Salen como filtros en Explorar."))
    ubic = (f"<p class='wz-txt'>Para enviar tienes que estar <b>en el local</b> con la ubicación activada (a menos de {int(config.RECLAMO_UBICACION_MAX_M)} m "
            "del punto del mapa): así confirmamos que el local existe y que estás ahí. Hazlo desde tu celular.</p>"
            "<div class='wz-fila'><button type='button' class='btn sec' id='wzUbicar'>Comprobar mi ubicación</button><span class='wz-txt' id='wzUbicTxt' role='status'></span></div>"
            ) if cfg["exigirUbic"] else "<p class='wz-txt'>Al enviar te pediremos tu ubicación (si la permites) para que el equipo la compare con el punto del local.</p>"
    cuerpo = f"""
{va.cabecera(titulo, '', volver='/anfitrion/mis-canchas', acciones="<button type='button' class='btn sec' id='wzBorrador'>Guardar borrador</button>")}
<p class='wz-miga'><a href='/anfitrion/mis-canchas'>Mis canchas</a> / {e(titulo)}</p>
<div id='wzRest'></div>
<div class='wz'>
 <aside class='wz-izq'>
  <nav class='va-panel wz-pasos' aria-label='Pasos'><small class='wz-eti'>Pasos</small><ol>{pasos_html}</ol></nav>
  <div class='wz-que'><b>¿Qué pasa al publicar?</b><p>{'Esta cancha ya está en ' + MARCA + ' pero nadie la administra. ' if existente else ''}Tu local queda <b>“En verificación”</b>. El equipo de {MARCA} revisa tu reclamo con tus fotos propias y la ubicación del local; al aprobarlo aparece con el sello ✓ Verificado y empieza a recibir reservas. Te avisamos por WhatsApp y en la app.</p></div>
 </aside>
 <form id='fNueva' class='wz-centro' autocomplete='off' novalidate>
  <div class='wz-paso' id='wzPaso1' data-paso='1'>
   <section class='va-panel edit-sec' id='sec-local'><h2>Datos del local</h2><p class='wz-txt'>Así aparecerá en {MARCA} y en tus reportes.</p>
    {busca}
    <label for='local'>Nombre del local <span class='req'>obligatorio</span></label><input id='local' maxlength='{catalogos.NOMBRE_MAX}' value='{e(nombre[:catalogos.NOMBRE_MAX])}' placeholder='Ej. Complejo Deportivo Los Olivos'>
   </section>
   <section class='va-panel edit-sec'><h2>Ubicación</h2><p class='wz-txt'>Los jugadores te encuentran por zona y por mapa. De este punto salen el país y la moneda.</p>
    <label>Zona</label>
    <div class='row wz-geo' id='geoRow'><select id='g1' aria-label='Zona: nivel 1'><option value=''>—</option></select><select id='g2' aria-label='Zona: nivel 2'><option value=''>—</option></select><select id='g3' aria-label='Zona: nivel 3'><option value=''>—</option></select></div>
    <label for='direccion'>Dirección <span class='req'>opcional</span></label><input id='direccion' maxlength='160' value='{e(direccion[:160])}' placeholder='Av. Aviación 1234, San Borja'>
    <label>Ubicación exacta <span class='req'>obligatoria · toca el mapa en la entrada del local</span></label>
    <div id='mapaSede' class='mapa-sede wz-mapa'></div>
    <div class='wz-fila'><button type='button' class='btn sec' id='btnUbic'>Usar mi ubicación</button><span class='wz-txt' id='ubicTxt'>{'Toca el mapa para fijar tu cancha.' if la is None else f'{la:.5f}, {ln:.5f}'}</span></div>
   </section>
  </div>
  <div class='wz-paso' id='wzPaso2' data-paso='2' hidden>
   <section class='va-panel edit-sec' id='sec-fotos'><h2>Fotos del local</h2><p class='wz-txt'>{_texto_fotos_obligatorias(min_fotos)} La primera es la portada. Hasta {fotos_reclamo.maximo()}.</p>
    {"" if not min_fotos else f"<div class='pill warn' id='fotosCont'>0 de {min_fotos} fotos</div>"}
    <div class='edit-fotos' id='fotos'></div>
    <label class='wz-subir' for='inFotos'><span>{iconos.svg('archivo', 22, grueso=2.2)}</span><b>Elige fotos desde tu equipo</b><small>JPG o PNG · fachada, canchas, vestuarios, estacionamiento</small></label>
    <input type='file' id='inFotos' accept='image/*' multiple hidden{'' if almacen.disponible() else ' disabled'}>
    <span class='wz-txt' id='fotosMsg' role='status'>{'' if almacen.disponible() else 'La subida de fotos no está disponible en este ambiente; súbelas desde la app.'}</span>
   </section>
   {amen}
  </div>
  <div class='wz-paso' id='wzPaso3' data-paso='3' hidden>
   <section class='va-panel'><h2>Canchas de este local</h2><p class='wz-txt'>Lo que se va a crear con lo que marques abajo. Puedes sumar más canchas después desde Mis canchas.</p><div id='wzCanchas' class='wz-canchas'></div></section>
   <section class='va-panel edit-sec' id='sec-deportes'><h2>Deportes y tipo de piso</h2><p class='wz-txt'>Marca todo lo que se juega en tu local.</p>
    {_chips('deportes', dep_ops, set(pre['deportes']), multi=True)}
    <div id='modoWrap' hidden><label>¿Cómo son tus canchas?</label>
     {_chips('modo', [('unica', 'Una sola loza multiuso (una agenda)'), ('separadas', 'Canchas separadas (una por deporte)')], 'separadas')}</div>
    <label>Tipo de piso <span class='req'>obligatorio</span></label>
    <div id='supWrap'><p class='wz-txt'>Marca primero un deporte.</p></div>
    <div id='nombreWrap'><label for='nombreCancha'>Nombre de la cancha <span class='req'>opcional</span></label><input id='nombreCancha' maxlength='{catalogos.NOMBRE_MAX}' value='{e(pre['nombre_cancha'])}' placeholder='Ej. Cancha 1 · Grass'></div>
   </section>
   <section class='va-panel edit-sec' id='sec-precio'><h2>Precio y horario</h2>
    {_bloque_precio(sim0, {"precio_hora": float(pre['precio'] or 0), "precio_turno": pre.get('precio_turno') or 0}, mon_id='monSpan', placeholder='120.00')}
    <div class='row'><div><label for='hora_apertura'>Abre</label>{_select_hora('hora_apertura', pre['apertura'])}</div>
    <div><label for='hora_cierre'>Cierra</label>{_select_hora('hora_cierre', pre['cierre'])}</div></div>
    <p class='wz-txt'>La hora de cierre es la hora en que <b>empieza el último turno</b>: si cierras a las 23:00, el último turno es 23:00–00:00. Un cierre menor o igual a la apertura cae al día siguiente.</p>
    <label>Duración del turno</label>
    {_chips('duracion_slot_min', catalogos.DURACIONES, pre['dur'] if pre['dur'] in catalogos.DURACIONES else 60, fmt=catalogos.etiqueta_duracion)}
    <p class='wz-txt'>Días que atiende, precios por franja, hora feliz, seña y servicios extra los configuras después en Reglas de reserva y Editar cancha.</p>
   </section>
  </div>
  <div class='wz-paso' id='wzPaso4' data-paso='4' hidden>
   <section class='va-panel'><h2>Revisa tu local</h2><div id='wzResumen' class='wz-resumen'></div></section>
   <section class='va-panel edit-sec' id='sec-dueno'><h2>Verificación de propiedad</h2><p class='wz-txt'>Existir no es ser dueño: con estos datos el equipo de {MARCA} confirma que la cancha es tuya antes de activarla. No se publican.</p>
    <label for='wa'>WhatsApp del local o del dueño <span class='req'>obligatorio</span></label><div class='inp-moneda wz-wa'><span id='telPre'>+{catalogos.TEL_PREFIJO.get(iso, '51')}</span><input id='wa' inputmode='tel' maxlength='15' placeholder='999 888 777'></div>
    <label>Tu relación con el local</label>{_chips('relacion', RELACIONES, 'dueno')}
    <label for='doc'><span id='docNombre'>{DOC_NOMBRE.get(iso, 'Documento')}</span> del titular <span class='req'>opcional, ayuda a aprobar más rápido</span></label><input id='doc' class='wz-doc' inputmode='numeric' maxlength='12' placeholder='Solo números'>
    <label for='nota'>Algo que debamos saber <span class='req'>opcional</span></label><input id='nota' maxlength='200' placeholder='Ej. El local está a nombre de mi socio, yo lo administro.'>
    <label>Prueba de propiedad <span class='req'>opcional: recibo de luz, licencia, contrato</span></label>
    <div class='wz-fila'><label class='btn sec' for='inEvid'>Subir foto</label><input type='file' id='inEvid' accept='image/*' hidden{'' if almacen.disponible() else ' disabled'}><span class='wz-txt' id='evidMsg'></span></div>
   </section>
   <section class='va-panel'><h2>Tu ubicación</h2>{ubic}</section>
  </div>
  <div class='wz-nav'><button type='button' class='btn sec' id='wzAtras'>‹ Atrás</button><span class='wz-gap'></span>
   <button type='button' class='btn' id='wzSig'>Continuar ›</button><button type='button' class='btn' id='btnGuardar' hidden>{'Reclamar mi cancha' if existente else 'Publicar mi local'}</button></div>
  <p class='wz-msg' id='msgGuardar' role='status'>Al enviar, tu local queda <b>en verificación</b> y te avisamos por WhatsApp y en la app cuando esté activo.</p>
 </form>
 <aside class='wz-der' aria-label='Vista previa'>
  <small class='wz-eti'>Así lo verán los jugadores</small>
  <div class='wz-prev'><div class='wz-prev-f' id='wzFoto'><span class='wz-prev-ph'>{iconos.svg('cancha', 40, grueso=1.8)}</span><span class='wz-prev-est'>Pendiente de verificar</span><span class='wz-prev-n' id='wzFotoN' hidden></span></div>
   <div class='wz-prev-c'><b id='wzNom'>Tu local</b><small id='wzDir'>Dirección y zona</small><div class='wz-prev-s' id='wzServ'></div>
   <div class='wz-prev-pie'><span id='wzCan'>Sin canchas todavía</span><b id='wzDesde'></b></div></div></div>
  <div class='va-panel wz-check'><b>Para publicar necesitas</b><ul id='wzCheck'></ul></div>
 </aside>
</div>
<script>var CFG={ui.json_js(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{JS_PRECIO}</script><script>{_JS_NUEVA}</script>"""
    return ui.shell("Pon tu cancha", _anf(va.vista(cuerpo, "vmc wz-pag")), sesion=ses, ancho=True,
                    extra_head=_LEAFLET, titulo_tab=f"{titulo} · {MARCA}")


_JS_NUEVA = r"""
(function(){
function $(id){return document.getElementById(id)}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}
// ── borrador guardado en este navegador (se recupera al volver y se borra al publicar) ──
var BOR=null;try{if(window.localStorage){var raw=localStorage.getItem(CFG.borrador);if(raw)BOR=JSON.parse(raw)}}catch(e){BOR=null}
if(BOR&&CFG.prellenado&&CFG.borrador.slice(-6)===':nuevo')BOR=null; // llegó con otro local prellenado: no se mezcla
if(BOR&&!CFG.existente&&/^u\d{12,14}$/.test(BOR.id||''))CFG.id=BOR.id; // sus fotos ya están en la carpeta de ese id
var fotos=(BOR&&BOR.fotos?BOR.fotos:(CFG.fotosPrevias||[])).slice(),evid=(BOR&&BOR.evid)||'',dep=(BOR&&BOR.dep?BOR.dep:(CFG.pre.deportes||[])).slice(),
    sups=(BOR&&BOR.sups)||{},sup=(BOR?BOR.sup:CFG.pre.superficie)||'',lat=BOR&&BOR.lat!=null?BOR.lat:CFG.lat,lng=BOR&&BOR.lng!=null?BOR.lng:CFG.lng,
    iso=CFG.iso,arbol=null,subiendo=0,mapa,marker,solLat=null,solLng=null,paso=1;
if(!BOR)dep.forEach(function(d){sups[d]=sup});
function marcar(g,vals,multi){document.querySelectorAll(".chip[data-g='"+g+"']").forEach(function(b){var on=multi?vals.indexOf(b.dataset.v)>=0:b.dataset.v===String(vals);b.classList.toggle('sel',on)})}
if(BOR){
  if(BOR.local!=null)$('local').value=BOR.local;if(BOR.direccion!=null)$('direccion').value=BOR.direccion;if(BOR.nombreCancha!=null)$('nombreCancha').value=BOR.nombreCancha;
  if(BOR.precio)$('precio').value=BOR.precio;if(BOR.ap)$('hora_apertura').value=BOR.ap;if(BOR.ci)$('hora_cierre').value=BOR.ci;
  if(BOR.wa)$('wa').value=BOR.wa;if(BOR.nota)$('nota').value=BOR.nota;if(BOR.zona)CFG.pre.zona=BOR.zona;
  marcar('deportes',dep,true);if(BOR.modo)marcar('modo',BOR.modo);if(BOR.dur)marcar('duracion_slot_min',String(BOR.dur));if(BOR.modoPrecio)marcar('modo_precio',BOR.modoPrecio);
  if(BOR.amen)marcar('amenidades',BOR.amen,true);if(BOR.relacion)marcar('relacion',BOR.relacion);
  if(BOR.place)CFG.place=BOR.place;
  var cuando=new Date(BOR.t||Date.now()).toLocaleString('es-PE',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
  $('wzRest').innerHTML="<div class='va-aviso info' role='status'><div class='va-aviso-t'><b>Recuperamos tu borrador</b> del "+esc(cuando)+".</div><div class='va-aviso-acc'><button type='button' class='mc-av-ver' id='wzDescartar'>Descartar borrador</button></div></div>"}
function sel(g){var b=document.querySelector(".chip.sel[data-g='"+g+"']");return b?b.dataset.v:''}
function selTodos(g){return [].map.call(document.querySelectorAll(".chip.sel[data-g='"+g+"']"),function(b){return b.dataset.v})}
function modo(){return dep.length>1?sel('modo'):'unica'}
function union(){var out=[];dep.forEach(function(d){(CFG.superficies[d]||[]).forEach(function(s){if(out.indexOf(s)<0)out.push(s)})});return out}
function chips(g,lista,val){return "<div class='chips'>"+lista.map(function(s){return "<button type='button' class='chip"+(s===val?' sel':'')+"' data-g='"+g+"' data-v='"+esc(s)+"'>"+esc(s)+"</button>"}).join('')+"</div>"}
function pintarSup(){var w=$('supWrap');$('modoWrap').hidden=dep.length<2;$('nombreWrap').hidden=modo()==='separadas'&&!CFG.existente;
  if(!dep.length){w.innerHTML="<p class='wz-txt'>Marca primero un deporte.</p>";return}
  if(modo()==='separadas'&&!CFG.existente){w.innerHTML=dep.map(function(d){return "<div class='wz-sup'><b>"+esc(CFG.nombres[d]||d)+"</b>"+chips('sup_'+d,CFG.superficies[d]||[],sups[d]||'')+"</div>"}).join('')}
  else{var u=union();if(u.indexOf(sup)<0)sup='';w.innerHTML=chips('sup',u,sup)}}
document.addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-g]');if(!b)return;var g=b.dataset.g,v=b.dataset.v;
  if(g==='deportes'){b.classList.toggle('sel');var i=dep.indexOf(v);if(i>=0)dep.splice(i,1);else dep.push(v);pintarSup();vivo();return}
  if(g==='amenidades'){b.classList.toggle('sel');vivo();return}
  b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');
  if(g==='modo'){pintarSup()}else if(g==='sup'){sup=v}else if(g.indexOf('sup_')===0){sups[g.slice(4)]=v}
  setTimeout(vivo,0)});
// ── buscar el local en Google por nombre (rellena nombre, dirección, punto y place) ──
var place=CFG.place||'',tBusca=null,inBusca=$('busca');
if(inBusca){
  inBusca.addEventListener('input',function(){clearTimeout(tBusca);var q=this.value.trim(),box=$('resBusca');if(q.length<3){box.hidden=true;box.innerHTML='';return}
    tBusca=setTimeout(function(){var c=mapa?mapa.getCenter():null;var qs='/web/lugares?q='+encodeURIComponent(q)+(c?'&lat='+c.lat+'&lng='+c.lng:'');
      fetch(qs).then(function(r){return r.json()}).then(function(j){var l=j.lugares||[];box.hidden=false;
        box.innerHTML=l.length?l.map(function(x){return "<button type='button' class='res-it' data-id='"+esc(x.id)+"' data-nombre='"+esc(x.nombre)+"' data-dir='"+esc(x.direccion)+"' data-lat='"+x.lat+"' data-lng='"+x.lng+"' data-dep='"+esc(x.deporte)+"'><b>"+esc(x.nombre)+"</b><small>"+esc(x.direccion)+(x.km!=null?' · a '+x.km+' km':'')+"</small></button>"}).join('')
          :"<div class='wz-txt'>No encontramos ese local en Google. Escribe el nombre abajo y marca el punto en el mapa.</div>"}).catch(function(){box.hidden=true})},400)});
  $('resBusca').addEventListener('click',function(ev){var b=ev.target.closest('.res-it');if(!b)return;
    $('local').value=b.dataset.nombre;$('direccion').value=b.dataset.dir;place=b.dataset.id;inBusca.value=b.dataset.nombre;$('resBusca').hidden=true;
    ponerPunto(parseFloat(b.dataset.lat),parseFloat(b.dataset.lng),true);
    if(!dep.length&&b.dataset.dep&&CFG.superficies[b.dataset.dep]){var ch=document.querySelector(".chip[data-g='deportes'][data-v='"+b.dataset.dep+"']");if(ch)ch.click()}vivo()});
}
// ── mapa + país + zona ──
function paisDe(la,ln){var C={PE:[-18.4,-0.03,-81.4,-68.6],EC:[-5.1,1.7,-81.1,-75.1],BO:[-22.95,-9.6,-69.7,-57.4]};for(var k in C){var c=C[k];if(la>=c[0]&&la<=c[1]&&ln>=c[2]&&ln<=c[3])return k}return 'PE'}
function ponerPunto(la,ln,centrar){lat=la;lng=ln;$('ubicTxt').textContent=la.toFixed(5)+', '+ln.toFixed(5);if(mapa){if(marker)marker.setLatLng([la,ln]);else marker=L.marker([la,ln]).addTo(mapa);if(centrar)mapa.setView([la,ln],16)}
  var p=paisDe(la,ln);if(p!==iso||!arbol){iso=p;$('telPre').textContent='+'+CFG.tel[iso];$('monSpan').textContent=CFG.monedas[iso]||'S/';$('docNombre').textContent=CFG.doc[iso]||'Documento';cargarGeo()}vivo()}
if(window.L){var c0=lat!=null?[lat,lng]:{PE:[-12.05,-77.04],EC:[-2.17,-79.92],BO:[-16.5,-68.15]}[iso];mapa=L.map('mapaSede').setView(c0,lat!=null?16:11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(mapa);
  if(lat!=null)marker=L.marker([lat,lng]).addTo(mapa);mapa.on('click',function(ev){ponerPunto(ev.latlng.lat,ev.latlng.lng,false)})}
$('btnUbic').addEventListener('click',function(){if(!navigator.geolocation){pcgToast('Tu navegador no permite ubicación.');return}navigator.geolocation.getCurrentPosition(function(p){solLat=p.coords.latitude;solLng=p.coords.longitude;ponerPunto(p.coords.latitude,p.coords.longitude,true)},function(){pcgToast('No pudimos leer tu ubicación.')})});
if(lat!=null){iso=paisDe(lat,lng);$('telPre').textContent='+'+CFG.tel[iso];$('monSpan').textContent=CFG.monedas[iso]||'S/';$('docNombre').textContent=CFG.doc[iso]||'Documento'}
function opts(s,lista,val,ph){s.innerHTML="<option value=''>"+ph+"</option>"+lista.map(function(o){return "<option value='"+esc(o)+"'"+(o===val?' selected':'')+">"+esc(o)+"</option>"}).join('')}
function cargarGeo(){fetch('/web/geo/'+iso).then(function(r){return r.json()}).then(function(j){if(!j.ok)return;arbol=j.arbol;var lb=j.labels,pre=['','',''];
  if(CFG.pre.zona){for(var a in arbol){for(var b in arbol[a]){if(arbol[a][b].indexOf(CFG.pre.zona)>=0){pre=[a,b,CFG.pre.zona]}}}}
  opts($('g1'),Object.keys(arbol),pre[0],lb[0]);opts($('g2'),pre[0]?Object.keys(arbol[pre[0]]):[],pre[1],lb[1]);opts($('g3'),pre[1]?arbol[pre[0]][pre[1]]:[],pre[2],lb[2]);vivo()}).catch(function(){})}
pintarSup();
$('g1').addEventListener('change',function(){opts($('g2'),this.value?Object.keys(arbol[this.value]):[],'',CFG.labels[iso][1]);opts($('g3'),[],'',CFG.labels[iso][2]);vivo()});
$('g2').addEventListener('change',function(){opts($('g3'),this.value?arbol[$('g1').value][this.value]:[],'',CFG.labels[iso][2]);vivo()});
$('g3').addEventListener('change',vivo);
cargarGeo();
// GPS del que reclama (anti-fraude de la torre): se intenta en silencio, sin bloquear.
if(navigator.geolocation){try{navigator.geolocation.getCurrentPosition(function(p){solLat=p.coords.latitude;solLng=p.coords.longitude},function(){},{timeout:6000,maximumAge:300000})}catch(e){}}
// ── fotos y evidencia ──
function comprimir(file,M){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
async function subir(file,tipo){var blob=await comprimir(file,1600);var r=await fetch('/anfitrion/nueva/foto?id='+encodeURIComponent(CFG.id)+'&tipo='+tipo,{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});return r.json()}
var msgBase=$('msgGuardar').innerHTML;
// FOTOS PROPIAS obligatorias: contador "3 de 3 fotos ✓" y botón deshabilitado con la explicación.
function actualizarEnvio(){var m=CFG.minFotos||0,n=fotos.length,ok=n>=m,c=$('fotosCont'),btn=$('btnGuardar'),msg=$('msgGuardar');
  if(c){c.textContent=(ok?Math.min(n,m)+' de '+m+' fotos ✓':n+' de '+m+' fotos');c.className='pill '+(ok?'ok':'warn')}
  if(!m)return;btn.disabled=!ok;
  if(!ok){msg.classList.remove('err');if(paso===4)msg.innerHTML='Sube al menos <b>'+m+' fotos de tu local</b> para enviar (llevas '+n+'). Las de Google no cuentan: no se pueden guardar y las tuyas prueban que el local existe.'}
  else if(msg.innerHTML.indexOf('Sube al menos')===0)msg.innerHTML=msgBase}
function pintarFotos(){$('fotos').innerHTML=fotos.map(function(u,i){return "<div class='foto' data-url='"+esc(u)+"'><img src='"+esc(u)+"' alt=''><span class='portada'"+(i?' hidden':'')+">Portada</span><div class='acc'><button type='button' class='mini' data-acc='portada' title='Usar como portada' aria-label='Usar esta foto como portada'>★</button><button type='button' class='mini' data-acc='quitar' title='Quitar' aria-label='Quitar esta foto'>✕</button></div></div>"}).join('');actualizarEnvio();vivo()}
document.addEventListener('click',function(ev){var a=ev.target.closest('.foto .mini');if(!a)return;var u=a.closest('.foto').dataset.url,i=fotos.indexOf(u);if(a.dataset.acc==='quitar'&&i>=0)fotos.splice(i,1);if(a.dataset.acc==='portada'&&i>0){fotos.splice(i,1);fotos.unshift(u)}pintarFotos()});
$('inFotos').addEventListener('change',async function(){var files=Array.prototype.slice.call(this.files||[]);this.value='';var msg=$('fotosMsg');
  for(var i=0;i<files.length;i++){if(fotos.length>=CFG.maxFotos){msg.textContent='Máximo '+CFG.maxFotos+' fotos.';break}subiendo++;msg.textContent='Subiendo foto '+(i+1)+' de '+files.length+'…';
    try{var j=await subir(files[i],'foto');if(j.ok){fotos.push(j.url);pintarFotos();msg.textContent='';guardarBorrador(true)}else msg.textContent=j.error||'No se pudo subir.'}catch(e){msg.textContent='No se pudo subir la foto.'}subiendo--}});
$('inEvid').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;subiendo++;$('evidMsg').textContent='Subiendo…';
  try{var j=await subir(f,'evidencia');if(j.ok){evid=j.url;$('evidMsg').textContent='Prueba adjunta ✓'}else $('evidMsg').textContent=j.error||'No se pudo subir.'}catch(e){$('evidMsg').textContent='No se pudo subir.'}subiendo--});
// ── vista previa "Así lo verán los jugadores" + "Para publicar necesitas" (en vivo) ──
function sim(){return $('monSpan').textContent||'S/'}
function precioN(){return parseFloat(($('precio')||{}).value)||0}
function supOk(){if(!dep.length)return false;if(modo()==='separadas'&&!CFG.existente)return dep.every(function(d){return !!sups[d]});return !!sup}
function canchas(){if(!dep.length)return [];var dur=+sel('duracion_slot_min')||60,h=$('hora_apertura').value+'–'+$('hora_cierre').value;
  if(modo()==='separadas'&&!CFG.existente)return dep.map(function(d){return {n:(CFG.nombres[d]||d)+' 1',s:[CFG.nombres[d]||d,sups[d]||'piso por elegir',h,dur+' min'].join(' · ')}});
  var nom=$('nombreCancha').value.trim()||(CFG.existente?(CFG.pre.nombre_cancha||'Cancha 1'):(dep.length===1?(CFG.nombres[dep[0]]+' 1'):'Cancha 1'));
  return [{n:nom,s:[dep.map(function(d){return CFG.nombres[d]||d}).join(' / '),sup||'piso por elegir',h,dur+' min'].join(' · ')}]}
function txtPrecio(){var p=precioN();if(!p)return '';var t=Math.round(p*100)/100;return 'desde '+sim()+' '+(t%1?t.toFixed(2):t)+(sel('modo_precio')==='turno'?' /turno':' /h')}
var checks=[['nombre','Nombre del local'],['ubic','Ubicación en el mapa']].concat(CFG.minFotos?[['fotos','Al menos '+CFG.minFotos+' fotos tuyas']]:[]).concat([['cancha','Al menos 1 cancha con piso y precio'],['wa','WhatsApp para verificarte']]);
function estado(){var wa=($('wa').value||'').replace(/\D/g,'');var cod=CFG.tel[iso]||'';if(wa.indexOf(cod)===0&&wa.length>CFG.telLen[iso])wa=wa.slice(cod.length);
  return {nombre:$('local').value.trim().length>=3,ubic:lat!=null,fotos:fotos.length>=(CFG.minFotos||0),cancha:supOk()&&precioN()>0,wa:wa.length===CFG.telLen[iso]}}
function vivo(){var st=estado(),f=$('wzFoto');
  $('wzNom').textContent=$('local').value.trim()||'Tu local';
  var z=$('g3')&&$('g3').value,dir=$('direccion').value.trim();$('wzDir').textContent=[dir,z].filter(Boolean).join(' · ')||'Dirección y zona';
  var ph=f.querySelector('img');if(fotos.length){if(!ph){ph=document.createElement('img');ph.alt='';f.insertBefore(ph,f.firstChild)}ph.src=fotos[0];$('wzFotoN').hidden=false;$('wzFotoN').textContent='1 / '+fotos.length}
  else{if(ph)ph.remove();$('wzFotoN').hidden=true}
  $('wzServ').innerHTML=selTodos('amenidades').map(function(k){return "<span>"+esc((CFG.amen[k]||k).replace(/^\S+\s/,''))+"</span>"}).join('');
  var cs=canchas();$('wzCan').textContent=cs.length?cs.map(function(c){return c.n}).join(' · '):'Sin canchas todavía';$('wzDesde').textContent=cs.length?txtPrecio():'';
  $('wzCanchas').innerHTML=cs.length?cs.map(function(c){return "<div class='wz-ca'><span class='wz-ca-ic'></span><div><b>"+esc(c.n)+"</b><small>"+esc(c.s)+(precioN()?' · '+esc(txtPrecio().replace('desde ','')):'')+"</small></div></div>"}).join(''):"<p class='wz-txt'>Marca un deporte para ver la cancha que se crea.</p>";
  $('wzCheck').innerHTML=checks.map(function(c){return "<li class='"+(st[c[0]]?'ok':'')+"'><i aria-hidden='true'></i>"+esc(c[1])+"<span class='vh'>"+(st[c[0]]?' (listo)':' (falta)')+"</span></li>"}).join('');
  var lp=document.querySelectorAll('.wz-p');[st.nombre&&st.ubic,st.fotos,st.cancha,st.wa].forEach(function(ok,i){if(lp[i])lp[i].classList.toggle('hecho',ok&&paso!==i+1)});
  if(paso===4){$('wzResumen').innerHTML=[['Local',$('local').value.trim()||'—'],['Dirección',[dir,z].filter(Boolean).join(' · ')||'Sin dirección'],['Ubicación',lat!=null?lat.toFixed(5)+', '+lng.toFixed(5):'Falta marcar el punto'],
    ['Fotos',fotos.length+' foto'+(fotos.length===1?'':'s')+' tuyas'],['Servicios',selTodos('amenidades').map(function(k){return (CFG.amen[k]||k).replace(/^\S+\s/,'')}).join(', ')||'Ninguno marcado'],
    ['Canchas',cs.length?cs.map(function(c){return c.n}).join(', ')+' · '+txtPrecio():'Falta marcar el deporte']].map(function(r){return "<div><small>"+esc(r[0])+"</small><b>"+esc(r[1])+"</b></div>"}).join('')}}
['local','direccion','nombreCancha','precio','wa','hora_apertura','hora_cierre'].forEach(function(id){var el=$(id);if(el){el.addEventListener('input',vivo);el.addEventListener('change',vivo)}});
// ── pasos ──
var SIG=['','Continuar: Fotos y servicios ›','Continuar: Canchas ›','Continuar: Revisar y publicar ›',''];
var CAMPO_PASO={local:1,fotos:2,deportes:3,precio:3,dueno:4};
function ir(n,foco){paso=n;document.querySelectorAll('.wz-paso').forEach(function(p){p.hidden=+p.dataset.paso!==n});
  document.querySelectorAll('.wz-p').forEach(function(b){var on=+b.dataset.ir===n;b.classList.toggle('act',on);if(on){b.setAttribute('aria-current','step');var ol=b.closest('ol');if(ol&&ol.scrollWidth>ol.clientWidth)ol.scrollLeft=b.parentNode.offsetLeft-8}else b.removeAttribute('aria-current')});
  $('wzAtras').hidden=n===1;$('wzSig').hidden=n===4;$('wzSig').textContent=SIG[n];$('btnGuardar').hidden=n!==4;
  var msg=$('msgGuardar');msg.classList.remove('err');msg.innerHTML=n===4?msgBase:'';if(n===4)actualizarEnvio();
  if(n===1&&mapa)setTimeout(function(){mapa.invalidateSize()},30);vivo();
  if(foco!==false){var t=document.querySelector('.wz-paso[data-paso="'+n+'"] h2');if(t){t.tabIndex=-1;t.focus({preventScroll:true})}window.scrollTo({top:0,behavior:'smooth'})}}
function falta(n){var st=estado();if(n===1&&!st.nombre)return ['Pon el nombre de tu local (al menos 3 letras).','local'];if(n===1&&!st.ubic)return ['Marca la ubicación exacta de tu local en el mapa.','mapaSede'];
  if(n===2&&!st.fotos&&CFG.storage)return ['Sube al menos '+CFG.minFotos+' fotos de tu local para seguir (llevas '+fotos.length+').','inFotos'];
  if(n===3&&!dep.length)return ['Marca al menos un deporte.','sec-deportes'];if(n===3&&!supOk())return ['Marca el tipo de piso de la cancha.','supWrap'];
  if(n===3&&!(precioN()>0))return ['Pon el precio de la cancha.','precio'];return null}
$('wzSig').addEventListener('click',function(){var f=falta(paso),msg=$('msgGuardar');if(f){msg.classList.add('err');msg.textContent=f[0];var el=$(f[1]);if(el&&el.scrollIntoView)el.scrollIntoView({behavior:'smooth',block:'center'});return}
  guardarBorrador(true);ir(paso+1)});
$('wzAtras').addEventListener('click',function(){if(paso>1)ir(paso-1)});
document.querySelectorAll('.wz-p').forEach(function(b){b.addEventListener('click',function(){ir(+b.dataset.ir)})});
// ── borrador ──
function datosBorrador(){return {v:1,t:Date.now(),id:CFG.existente?'':CFG.id,place:place,local:$('local').value,direccion:$('direccion').value,lat:lat,lng:lng,zona:$('g3').value||CFG.pre.zona||'',
  dep:dep,modo:sel('modo'),sup:sup,sups:sups,nombreCancha:$('nombreCancha').value,modoPrecio:sel('modo_precio'),precio:$('precio').value,ap:$('hora_apertura').value,ci:$('hora_cierre').value,
  dur:+sel('duracion_slot_min')||60,amen:selTodos('amenidades'),fotos:fotos,evid:evid,wa:$('wa').value,relacion:sel('relacion'),nota:$('nota').value}}
function guardarBorrador(silencio){try{localStorage.setItem(CFG.borrador,JSON.stringify(datosBorrador()));if(!silencio&&window.pcgToast)pcgToast('Borrador guardado en este navegador');return true}
  catch(e){if(!silencio&&window.pcgAvisar)pcgAvisar({titulo:'No se pudo guardar el borrador',mensaje:'Tu navegador no permite guardar datos (modo privado o almacenamiento lleno).'});return false}}
function borrarBorrador(){try{localStorage.removeItem(CFG.borrador)}catch(e){}}
$('wzBorrador').addEventListener('click',function(){guardarBorrador(false)});
document.addEventListener('click',async function(ev){if(!ev.target.closest('#wzDescartar'))return;
  if(!await pcgConfirmar({titulo:'¿Descartar el borrador?',mensaje:'Se borra lo que guardaste en este navegador y el formulario vuelve a empezar.',confirmar:'Descartar',destructivo:true}))return;
  borrarBorrador();pcgRecargar()});
// ── ubicación del dispositivo (paso 4) y envío ──
function ubicacionAhora(){return new Promise(function(res){if(!navigator.geolocation){res(null);return}
  try{navigator.geolocation.getCurrentPosition(function(p){res({lat:p.coords.latitude,lng:p.coords.longitude})},function(){res(null)},{enableHighAccuracy:true,timeout:15000,maximumAge:60000})}catch(e){res(null)}})}
function distM(a,b,c,d){var R=6371000,x=(c-a)*Math.PI/180,y=(d-b)*Math.PI/180,h=Math.sin(x/2)*Math.sin(x/2)+Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(y/2)*Math.sin(y/2);return 2*R*Math.asin(Math.sqrt(h))}
function txtDist(dm){return dm>=1000?(dm/1000).toFixed(1)+' km':Math.round(dm)+' m'}
if($('wzUbicar'))$('wzUbicar').addEventListener('click',async function(){var t=$('wzUbicTxt');t.textContent='Leyendo tu ubicación…';var u=await ubicacionAhora();
  if(!u){t.textContent='No pudimos leer tu ubicación. Actívala y permite el acceso.';return}solLat=u.lat;solLng=u.lng;
  if(lat==null){t.textContent='Primero marca el punto del local en el paso 1.';return}var dm=distM(lat,lng,u.lat,u.lng);
  t.textContent=dm<=CFG.ubicMaxM?'✓ Estás en el local ('+txtDist(dm)+' del punto).':'Estás a '+txtDist(dm)+' del punto: tienes que estar en el local (a menos de '+Math.round(CFG.ubicMaxM)+' m).'});
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo>0){msg.textContent='Espera a que terminen de subir las fotos.';return}
  if(fotos.length<(CFG.minFotos||0)){actualizarEnvio();ir(2);return}
  // UBICACIÓN obligatoria: el celular debe estar en el local (≤ CFG.ubicMaxM del punto).
  if(CFG.exigirUbic){msg.classList.remove('err');msg.textContent='Confirmando que estás en el local…';
    var u=await ubicacionAhora();
    if(!u){msg.textContent='';await pcgAvisar({icono:'📍',titulo:'Necesitamos tu ubicación',mensaje:'Para reclamar tu cancha tienes que estar en el local con la ubicación activada. Hazlo desde tu celular estando en la cancha y permite el acceso a tu ubicación.'});return}
    solLat=u.lat;solLng=u.lng;var dm=distM(lat,lng,u.lat,u.lng);
    if(lat!=null&&dm>CFG.ubicMaxM){msg.textContent='';await pcgAvisar({icono:'📍',titulo:'Estás lejos de la cancha',mensaje:'Estás a '+txtDist(dm)+' del punto que marcaste. Para reclamarla tienes que estar en el local (a menos de '+Math.round(CFG.ubicMaxM)+' m). Si el punto está mal, corrígelo en el mapa (paso 1).'});return}
    msg.textContent=''}
  var body={id:CFG.id,existente:CFG.existente,place:place,nombre_local:$('local').value,direccion:$('direccion').value,lat:lat,lng:lng,zona:$('g3').value,deportes:dep,modo:modo(),superficie:sup,superficies:sups,
    nombre_cancha:$('nombreCancha').value,modo_precio:pcgPrecioBody().modo_precio,precio:pcgPrecioBody().precio,precio_hora:parseFloat($('precio').value)||0,hora_apertura:$('hora_apertura').value,hora_cierre:$('hora_cierre').value,duracion_slot_min:+sel('duracion_slot_min')||60,
    amenidades:selTodos('amenidades'),fotos:fotos,whatsapp:$('wa').value,relacion:sel('relacion'),documento:$('doc').value,nota:$('nota').value,evidencia:evid,sol_lat:solLat,sol_lng:solLng};
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Registrando…';if(window.pcgCargando)pcgCargando('Registrando tu local…',{demora:300});
  try{var r=await fetch('/anfitrion/nueva',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){borrarBorrador();if(window.pcgIr)pcgIr(j.url||'/anfitrion/canchas','¡Listo! Tu local quedó en verificación');else location.href=j.url||'/anfitrion/canchas';return}
    if(window.pcgCargando)pcgCargando(false);var p=CAMPO_PASO[j.campo];if(p&&p!==paso)ir(p,false);msg.classList.add('err');msg.textContent=j.error||'No se pudo registrar.';
    var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth'})}
  catch(e){if(window.pcgCargando)pcgCargando(false);msg.classList.add('err');msg.textContent='No se pudo registrar. Revisa tu conexión.'}btn.disabled=false;var m=CFG.minFotos||0;if(m&&fotos.length<m)btn.disabled=true});
pintarFotos();ir(1,false);
})();
"""


def _validar_registro(b: dict, email: str) -> tuple[list[dict] | None, dict, str, str]:
    """Aplica las MISMAS reglas que `registrar_cancha_screen._publicar`.
    Devuelve (filas para `pichangol_canchas`, datos del reclamo, error, sección)."""
    if not isinstance(b, dict):
        return None, {}, "Datos inválidos.", ""
    nuevo_id = str(b.get("id") or "")
    existente = _legado_reclamable(nuevo_id) if b.get("existente") else None
    if not existente and not _ID_NUEVA_RE.match(nuevo_id):
        return None, {}, "Recarga la página e inténtalo de nuevo.", "local"
    local = re.sub(r"\s+", " ", str(b.get("nombre_local") or "")).strip()[:catalogos.NOMBRE_MAX]
    if len(local) < 3:
        return None, {}, "Pon el nombre de tu local.", "local"
    direccion = re.sub(r"\s+", " ", str(b.get("direccion") or "")).strip()[:160]
    try:
        la, ln = float(b.get("lat")), float(b.get("lng"))
    except (TypeError, ValueError):
        return None, {}, "Ubica tu cancha en el mapa (toca el punto exacto o usa tu ubicación).", "local"
    if not any(c[0] <= la <= c[1] and c[2] <= ln <= c[3] for c in paises._CAJAS.values()):
        return None, {}, "El punto debe estar en Perú, Ecuador o Bolivia.", "local"
    iso = paises.pais_de_coordenadas(la, ln)
    zona = re.sub(r"\s+", " ", str(b.get("zona") or "")).strip()[:80]
    deps = []
    for d in (b.get("deportes") or []):
        d = str(d).lower()
        if d in catalogos.DEPORTES_ACTIVOS and d not in deps:
            deps.append(d)
    if not deps:
        return None, {}, "Marca al menos un deporte.", "deportes"
    modo = "separadas" if (len(deps) > 1 and str(b.get("modo")) == "separadas") else "unica"
    sups_por_dep: dict[str, str] = {}
    if modo == "separadas":
        raw = b.get("superficies") if isinstance(b.get("superficies"), dict) else {}
        for d in deps:
            s = str(raw.get(d) or "").strip()
            if s not in catalogos.SUPERFICIES.get(d, []):
                return None, {}, f"Marca el tipo de piso de {_deporte(d)[0]}.", "deportes"
            sups_por_dep[d] = s
    else:
        union = [s for d in deps for s in catalogos.SUPERFICIES.get(d, [])]
        s = str(b.get("superficie") or "").strip()
        if s not in union:
            return None, {}, "Marca el tipo de piso de la cancha (obligatorio).", "deportes"
        sups_por_dep = {d: s for d in deps}
    ap, ci = str(b.get("hora_apertura") or "07:00"), str(b.get("hora_cierre") or "23:00")
    if not (_HORA_RE.match(ap) and _HORA_RE.match(ci)):
        return None, {}, "Hora no válida (usa horas en punto).", "precio"
    try:
        dur = int(b.get("duracion_slot_min") or 60)
    except (TypeError, ValueError):
        dur = 0
    if dur not in catalogos.DURACIONES:
        return None, {}, "Duración del turno no válida.", "precio"
    precio, precio_turno, err_precio = _precio_de_body(b, dur)
    if err_precio:
        return None, {}, err_precio, "precio"
    prefijo = almacen.prefijo_cancha(nuevo_id) if almacen.disponible() else None
    previas = set(fotos_reclamo.de_cancha(existente)) if existente else set()
    fotos = []
    for u in (b.get("fotos") or []):
        u = str(u).strip()
        if u and u not in fotos and (u in previas or (prefijo and u.startswith(prefijo))):
            fotos.append(u)
    # Solo cuentan (y se guardan) fotos PROPIAS: subidas a la carpeta de esta
    # cancha en NUESTRO bucket. Google / googleusercontent / evidencia no.
    fotos = fotos_reclamo.propias(fotos, nuevo_id)[:fotos_reclamo.maximo()]
    min_fotos = fotos_reclamo.minimo()
    if len(fotos) < min_fotos:
        return None, {}, _error_faltan_fotos(min_fotos, len(fotos)), 'fotos'
    wa_local = re.sub(r"\D", "", str(b.get("whatsapp") or ""))
    cod = catalogos.TEL_PREFIJO[iso]
    if wa_local.startswith(cod) and len(wa_local) > catalogos.TEL_LONGITUD[iso]:
        wa_local = wa_local[len(cod):]
    if len(wa_local) != catalogos.TEL_LONGITUD[iso]:
        return None, {}, f"El WhatsApp debe tener {catalogos.TEL_LONGITUD[iso]} dígitos (sin el +{cod}).", "dueno"
    relacion = str(b.get("relacion") or "dueno")
    if relacion not in {k for k, _ in RELACIONES}:
        relacion = "dueno"
    doc = re.sub(r"\D", "", str(b.get("documento") or ""))
    if doc and iso in DOC_LONGITUD and len(doc) != DOC_LONGITUD[iso]:
        return None, {}, f"Si pones tu {DOC_NOMBRE[iso]}, debe tener {DOC_LONGITUD[iso]} dígitos (o déjalo vacío).", "dueno"
    nota = re.sub(r"\s+", " ", str(b.get("nota") or "")).strip()[:200]
    evid = str(b.get("evidencia") or "").strip()
    pref_ev = almacen.prefijo_cancha(f"ev{nuevo_id}") if almacen.disponible() else None
    if evid and not (pref_ev and evid.startswith(pref_ev)):
        evid = ""
    try:
        sol = (float(b.get("sol_lat")), float(b.get("sol_lng"))) if b.get("sol_lat") is not None and b.get("sol_lng") is not None else (None, None)
    except (TypeError, ValueError):
        sol = (None, None)
    # UBICACIÓN obligatoria (2-oct-2026): el dispositivo debe estar en el local.
    err_ubic = reclamos.validar_ubicacion_envio(la, ln, sol[0], sol[1])
    if err_ubic is not None:
        return None, {}, err_ubic["mensaje"], "dueno"
    moneda = paises.simbolo_de_moneda(paises.moneda_de_pais(iso))
    nombre_cancha = re.sub(r"\s+", " ", str(b.get("nombre_cancha") or "")).strip()[:catalogos.NOMBRE_MAX]
    # Servicios del local (gratis) del paso 2 del asistente: solo claves del catálogo del app; opcional.
    amen = list(dict.fromkeys(str(a) for a in (b.get("amenidades") or []) if str(a) in catalogos.AMENIDADES)) if isinstance(b.get("amenidades"), list) else []
    base = {"club": local, "distrito": "", "barrio": zona, "precio_hora": precio, "precio_turno": precio_turno or None, "lat": la, "lng": ln, "club_fundador": False,
            "digitalizada": True, "direccion": direccion or None, "registrada": True, "foto_url": fotos[0] if fotos else None,
            "fotos": fotos, "dueno": email, "verificada": False, "hora_apertura": ap, "hora_cierre": ci, "duracion_slot_min": dur,
            "eliminada": False, "amenidades": amen, "moneda": moneda, "servicios_extra": [], "descuento_valle": 0,
            "valle_desde": "07:00", "valle_hasta": "12:00", "sena_pct": 0}
    filas = []
    if existente:
        # Adopción: UNA fila (la existente); si marcó varios deportes, van en
        # la misma loza (agenda compartida), como el editor del app.
        principal = catalogos.deporte_principal(deps)
        nombre = nombre_cancha or existente.get("nombre") or f"{_deporte(principal)[0]} 1"
        filas.append({**base, "id": nuevo_id, "nombre": nombre, "deporte": principal, "deportes": deps, "superficie": sups_por_dep[principal], "_adoptar": True})
    elif modo == "unica":
        principal = catalogos.deporte_principal(deps)
        nombre = nombre_cancha or (f"{_deporte(principal)[0]} 1" if len(deps) == 1 else "Cancha 1")
        filas.append({**base, "id": nuevo_id, "nombre": nombre, "deporte": principal, "deportes": deps, "superficie": sups_por_dep[principal]})
    else:
        for d in deps:
            filas.append({**base, "id": f"{nuevo_id}_{d}", "nombre": f"{_deporte(d)[0]} 1", "deporte": d, "deportes": [d], "superficie": sups_por_dep[d]})
    reclamo = {"cancha_id": filas[0]["id"], "nombre_local": local, "telefono_contacto": cod + wa_local, "dni": doc or None,
               "relacion": relacion, "lat": la, "lng": ln, "solicitante_lat": sol[0], "solicitante_lng": sol[1],
               "foto_evidencia_url": evid, "nota_reclamante": nota, "place": str(b.get("place") or "")[:120]}
    return filas, reclamo, "", ""


@router.post("/anfitrion/nueva")
async def registrar_cancha_web(request: Request) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_registrar_cancha_web, request, _cuerpo_json)


def _registrar_cancha_web(request: Request, _cuerpo_json) -> JSONResponse:
    """Crea la(s) cancha(s) en `pichangol_canchas` (sin verificar, a nombre
    del correo de la sesión) y el RECLAMO en el backend; la torre lo aprueba.
    Si el lugar ya tiene un reclamo ACTIVO de otra persona, no se registra."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        body = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    filas, rec, err, seccion = _validar_registro(body, ses["email"])
    if filas is None:
        return JSONResponse({"ok": False, "error": err, "campo": seccion}, status_code=400)
    # Anti doble-reclamo ANTES de escribir: mismo criterio que crear_reclamo.
    activo = reclamos.lugar_reclamado(rec["lat"], rec["lng"], rec["cancha_id"], ses["email"])
    if activo.get("reclamada") and not activo.get("por_mi"):
        return JSONResponse({"ok": False, "error": "Este lugar ya tiene un reclamo en curso de otra persona. Si es tu cancha, escríbenos por WhatsApp.", "campo": "local"}, status_code=409)
    adoptar = bool(filas[0].get("_adoptar"))
    if adoptar:
        campos = {k: v for k, v in filas[0].items() if k in datos.COLS_ADOPCION}
        ok = datos.adoptar_cancha(filas[0]["id"], ses["email"], campos)
    else:
        ok = datos.insertar_canchas(filas)
    if not ok:
        return JSONResponse({"ok": False, "error": "No pudimos guardar tu cancha en este momento. Inténtalo de nuevo."}, status_code=503)
    r = reclamos.crear_reclamo(
        rec["cancha_id"], ses["email"], rec["nombre_local"], rec["telefono_contacto"], rec["dni"], None, rec["relacion"],
        rec["lat"], rec["lng"], rec["solicitante_lat"], rec["solicitante_lng"],
        solicitante_nombre=ses.get("nombre") or "", foto_evidencia_url=rec["foto_evidencia_url"],
        nota_reclamante=(rec["nota_reclamante"] + (f" [web · place {rec['place']}]" if rec["place"] else " [web]")).strip())
    if not r.get("ok"):
        if adoptar:
            datos.desadoptar_cancha(filas[0]["id"], ses["email"])
        else:
            datos.borrar_canchas([f["id"] for f in filas], ses["email"])
        msg = ("Este lugar ya tiene un reclamo en curso de otra persona. Si es tu cancha, escríbenos por WhatsApp."
               if r.get("error") == "ya_reclamada" else "No pudimos registrar el reclamo. Inténtalo de nuevo.")
        return JSONResponse({"ok": False, "error": msg, "campo": "local"}, status_code=409)
    print(f"[registro-web] {ses['email']} registró {rec['nombre_local']!r}: {[f['id'] for f in filas]} · reclamo #{r.get('reclamo_id')}", flush=True)
    # Verificación de EXISTENCIA (IA) en segundo plano, como `verificarVenue`
    # del APK: confirma que el local es real; NO da la propiedad (eso sigue
    # siendo el reclamo). Nunca bloquea ni hace fallar el registro.
    _en_segundo_plano(verificar_existencia, rec["cancha_id"], str(filas[0].get("direccion") or rec["nombre_local"] or ""),
                      rec["lat"], rec["lng"])
    return JSONResponse({"ok": True, "url": f"/anfitrion/canchas?registrada={filas[0]['id']}", "reclamo_id": r.get("reclamo_id"), "ids": [f["id"] for f in filas]})


@router.post("/anfitrion/nueva/foto")
async def subir_foto_nueva(request: Request, id: str = "", tipo: str = "foto") -> JSONResponse:
    _cuerpo_bytes = await request.body()
    return await run_in_threadpool(_subir_foto_nueva, request, id, tipo, _cuerpo_bytes)


def _subir_foto_nueva(request: Request, id: str = "", tipo: str = "foto", _cuerpo_bytes: bytes = b"") -> JSONResponse:
    """Fotos del registro ANTES de que exista la fila: van a `canchas/<id>/`
    (misma carpeta que tendrá la cancha) o `canchas/ev<id>/` (evidencia)."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    if not _ID_NUEVA_RE.match(id or "") and _legado_reclamable(id) is None:
        return JSONResponse({"ok": False, "error": "Recarga la página e inténtalo de nuevo."}, status_code=400)
    if not almacen.disponible():
        return JSONResponse({"ok": False, "error": "La subida de fotos no está disponible en este ambiente."}, status_code=503)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp"):
        return JSONResponse({"ok": False, "error": "Formato no admitido (usa JPG, PNG o WebP)."}, status_code=415)
    cuerpo = _cuerpo_bytes
    if not cuerpo or len(cuerpo) > almacen.MAX_BYTES:
        return JSONResponse({"ok": False, "error": "La foto pesa demasiado (máx. 6 MB)."}, status_code=413)
    url = almacen.subir_foto(f"ev{id}" if tipo == "evidencia" else id, cuerpo, ctype)
    if not url:
        return JSONResponse({"ok": False, "error": "No se pudo subir la foto. Inténtalo de nuevo."}, status_code=502)
    return JSONResponse({"ok": True, "url": url})


_ESTADO_RECLAMO = {
    "pendiente_triage": ("warn", "En verificación", "Estamos confirmando que eres el dueño. Te avisamos por WhatsApp y en la app cuando esté activa."),
    "aprobado_triage": ("warn", "Aprobada, falta validar", "Falta la validación en sitio (código + ubicación) para activarla."),
    "pendiente_validacion": ("warn", "Aprobada, falta validar", "Falta la validación en sitio (código + ubicación) para activarla."),
    "validada_pendiente_admin": ("warn", "Validada, activación pendiente", "El equipo la activa en breve."),
    "rechazada": ("err", "No aprobada", "No pudimos confirmar la propiedad. Escríbenos por WhatsApp o vuelve a enviarla desde «Ver estado y opciones»."),
    "reclamada_por_otro": ("err", "Reclamada por otra cuenta", "Otra persona ya tiene este local a su nombre. Si es tuyo, escríbenos."),
}


# ── AGREGAR CANCHA A UN LOCAL EXISTENTE (= `AgregarCanchaScreen` del app) ────
# El dueño ya tiene el local: la cancha nueva HEREDA club, dirección, punto,
# zona, fotos, servicios del local, moneda, dueño y ESTADO DE VERIFICACIÓN (si
# el local ya está activo, la cancha entra activa al instante; no se vuelve a
# validar la propiedad ni se crea otro reclamo). Solo se pide lo propio de la
# cancha: deporte, tipo de piso, nombre (opcional), precio, horario y duración.
# Permite varias canchas del mismo deporte y de deportes distintos.

def _local_propio(email: str, nombre: str, lat, lng) -> dict | None:
    """Cancha del propio dueño cuyo local coincide con `nombre` (sin
    mayúsculas) o está a ≤120 m del punto: plantilla para agregar."""
    mias = datos.canchas_de_dueno(email)
    if not mias:
        return None
    n = re.sub(r"\s+", " ", (nombre or "")).strip().lower()
    if n:
        for c in mias:
            if (c.get("club") or "").strip().lower() == n:
                return c
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    from web import descubrir as _d
    mejor, dist = None, 0.12
    for c in mias:
        if not (c.get("lat") and c.get("lng")):
            continue
        d = _d._km(la, ln, float(c["lat"]), float(c["lng"]))
        if d <= dist:
            mejor, dist = c, d
    return mejor


def _hermanas_local(email: str, plantilla: dict) -> list[dict]:
    club = (plantilla.get("club") or "").strip().lower()
    return [c for c in datos.canchas_de_dueno(email) if (c.get("club") or "").strip().lower() == club] or [plantilla]


def _nombre_auto(email: str, plantilla: dict, deporte: str) -> str:
    """Como el app: "Fútbol 2" = siguiente número del deporte dentro del local."""
    n = sum(1 for c in _hermanas_local(email, plantilla) if (c.get("deporte") or "").lower() == deporte) + 1
    return f"{_deporte(deporte)[0]} {n}"


@router.get("/anfitrion/cancha/{cancha_id}/agregar", response_class=HTMLResponse)
def pagina_agregar_cancha(request: Request, cancha_id: str, deporte: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/cancha/{cancha_id}/agregar")
    if resp is not None:
        return resp
    l = _cancha_propia(ses, cancha_id)
    if not l:
        from web.router import _no_encontrada
        r = _no_encontrada("Esta cancha no está a tu nombre"); r.status_code = 404
        return r
    local = (l.get("club") or "").strip() or l["nombre"]
    hermanas = _hermanas_local(ses["email"], l)
    activo = datos.reservable(l)
    sim, _ = _moneda_de(l)
    dep_ini = deporte if deporte in catalogos.DEPORTES_ACTIVOS else ""
    dep_ops = [(d, f"{_deporte(d)[1]} {_deporte(d)[0]}") for d in catalogos.DEPORTES_ACTIVOS]
    auto = {d: _nombre_auto(ses["email"], l, d) for d in catalogos.DEPORTES_ACTIVOS}
    # FOTOS PROPIAS (decisión del director, 2-oct-2026): la cancha hereda las
    # fotos del local; si el local tiene menos del mínimo, se piden las que faltan.
    min_fotos = fotos_reclamo.minimo()
    heredadas = fotos_reclamo.de_cancha(l)
    faltan_fotos = max(0, min_fotos - len(heredadas))
    cfg = {"id": l["id"], "superficies": catalogos.SUPERFICIES, "auto": auto, "dep": dep_ini,
           "nuevoId": f"u{int(time.time() * 1000)}", "faltanFotos": faltan_fotos, "maxFotos": catalogos.MAX_FOTOS}
    sec_fotos = "" if not faltan_fotos else f"""
 <section class='va-panel edit-sec' id='sec-fotos'><h2>Fotos de tu local</h2>
  <p class='sub'>{_texto_fotos_obligatorias(min_fotos)} Tu local tiene {len(heredadas)}: <b>sube {faltan_fotos} más</b> para agregar esta cancha.</p>
  <div class='pill warn' id='fotosCont' style='display:inline-block;margin:2px 0 10px'>0 de {faltan_fotos} fotos</div>
  <div class='edit-fotos' id='fotos'></div>
  <div class='acciones' style='margin-top:12px'><label class='btn sec' for='inFotos'>📷 Agregar fotos</label><input type='file' id='inFotos' accept='image/*' multiple hidden{'' if almacen.disponible() else ' disabled'}>
  <span class='sub' id='fotosMsg' style='margin:0'>{'' if almacen.disponible() else 'La subida de fotos no está disponible en este ambiente; súbelas desde la app.'}</span></div>
 </section>"""
    lista = "".join(f"<li>{_deporte(c.get('deporte'))[1]} {e(c['nombre'])} · {e(_deporte(c.get('deporte'))[0])}"
                    + ("" if datos.reservable(c) else " <span class='pill warn'>Aún sin verificar</span>") + "</li>" for c in hermanas)
    estado = ("<div class='aviso ok'>✓ El local ya está verificado: la cancha nueva queda <b>activa al instante</b> y recibe reservas.</div>" if activo else
              "<div class='aviso'>⏳ El local está en verificación: la cancha nueva se <b>activará junto con él</b> cuando lo aprobemos. No hace falta otro reclamo.</div>")
    cuerpo = f"""
{va.cabecera(f'Agrega una cancha a {local}', 'Se suma al local (misma dirección, fotos, servicios y dueño). Solo dinos qué cancha es. Puedes agregar varias del mismo deporte o de otro deporte.', volver=_url_mc(l['id']))}
<div class='edit-grid'><nav class='edit-nav'><a href='#sec-cancha' class='edit-nav-it'>¿Qué cancha agregas?</a><a href='#sec-precio' class='edit-nav-it'>Precio y horario</a></nav>
<form id='fAgregar' class='edit-form' autocomplete='off' novalidate>
 <section class='va-panel edit-sec' id='sec-local'><h2>{e(local)}</h2>
  <p class='sub' style='margin:0'>{e(l.get('direccion') or '')}{(' · ' if l.get('direccion') and _zona(l) else '')}{e(_zona(l))}</p>
  <p class='sub' style='margin:8px 0 4px'>Canchas que ya tiene este local:</p><ul class='sub' style='margin:0 0 0 18px'>{lista}</ul>
  {estado}
 </section>
 <section class='va-panel edit-sec' id='sec-cancha'><h2>¿Qué cancha agregas?</h2>
  <label>Deporte <span class='req'>una cancha = un deporte</span></label>
  {_chips('deporte', dep_ops, dep_ini)}
  <label style='margin-top:18px'>Tipo de piso <span class='req'>obligatorio</span></label>
  <div id='supWrap'><p class='sub'>Marca primero el deporte.</p></div>
  <label for='nombreCancha' style='margin-top:18px'>Nombre de la cancha <span class='req'>opcional</span></label>
  <input id='nombreCancha' maxlength='{catalogos.NOMBRE_MAX}' placeholder='{e(auto.get(dep_ini) or "Ej. Fútbol 2")}'>
  <p class='sub' style='font-size:12.5px'>Si lo dejas vacío, la nombramos sola por deporte con el siguiente número del local.</p>
 </section>
 <section class='va-panel edit-sec' id='sec-precio'><h2>Precio y horario</h2><p class='sub'>Vienen del local; cámbialos si esta cancha es distinta.</p>
  {_bloque_precio(sim, l)}
  <div class='row' style='margin-top:14px'><div><label for='hora_apertura'>Abre</label>{_select_hora('hora_apertura', l.get('hora_apertura') or '07:00')}</div>
  <div><label for='hora_cierre'>Cierra</label>{_select_hora('hora_cierre', l.get('hora_cierre') or '23:00')}</div></div>
  <p class='sub' style='font-size:13px'>La hora de cierre es la hora en que <b>empieza el último turno</b>.</p>
  <label style='margin-top:14px'>Duración del turno</label>
  {_chips('duracion_slot_min', catalogos.DURACIONES, int(l.get('duracion_slot_min') or 60) if int(l.get('duracion_slot_min') or 60) in catalogos.DURACIONES else 60, fmt=catalogos.etiqueta_duracion)}
  <p class='sub' style='font-size:12.5px'>Hora feliz, seña, fotos propias y servicios extra los ajustas después en Editar cancha.</p>
 </section>{sec_fotos}
</form></div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>{'Queda activa al instante.' if activo else 'Se activa junto con el local.'}</span>
<button type='button' class='btn' id='btnGuardar'>Agregar cancha</button></div></div>
<script>var CFG={ui.json_js(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{JS_PRECIO}</script><script>{_JS_AGREGAR}</script>"""
    return ui.shell("Agregar cancha", _anf(va.vista(cuerpo, "vmc")), sesion=ses, ancho=True,
                    titulo_tab=f"Agregar cancha · {local}")


_JS_AGREGAR = r"""
(function(){
var dep=CFG.dep||'', sup='', fotos=[], subiendo=0;
function $(id){return document.getElementById(id)}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}
// Fotos que le FALTAN al local para el mínimo (van a la carpeta de la cancha nueva).
var msgBase=$('msgGuardar').innerHTML;
function actualizarEnvio(){var m=CFG.faltanFotos||0;if(!m)return;var n=fotos.length,ok=n>=m,c=$('fotosCont'),btn=$('btnGuardar'),msg=$('msgGuardar');
  if(c){c.textContent=(ok?m+' de '+m+' fotos ✓':n+' de '+m+' fotos');c.className='pill '+(ok?'ok':'warn')}
  btn.disabled=!ok;if(!ok){msg.classList.remove('err');msg.innerHTML='📷 Sube <b>'+m+' foto'+(m>1?'s':'')+' de tu local</b> para agregar la cancha (llevas '+n+').'}else if(msg.innerHTML.indexOf('📷')===0)msg.innerHTML=msgBase}
if(CFG.faltanFotos){
  function comprimir(file,M){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
  var pintarFotos=function(){$('fotos').innerHTML=fotos.map(function(u){return "<div class='foto' data-url='"+esc(u)+"'><img src='"+esc(u)+"' alt=''><div class='acc'><button type='button' class='mini' data-acc='quitar' title='Quitar' aria-label='Quitar esta foto'>✕</button></div></div>"}).join('');actualizarEnvio()};
  document.addEventListener('click',function(ev){var a=ev.target.closest('.foto .mini');if(!a)return;var i=fotos.indexOf(a.closest('.foto').dataset.url);if(i>=0)fotos.splice(i,1);pintarFotos()});
  $('inFotos').addEventListener('change',async function(){var files=Array.prototype.slice.call(this.files||[]);this.value='';var msg=$('fotosMsg');
    for(var i=0;i<files.length;i++){if(fotos.length>=CFG.maxFotos){msg.textContent='Máximo '+CFG.maxFotos+' fotos.';break}subiendo++;msg.textContent='Subiendo foto '+(i+1)+' de '+files.length+'…';
      try{var blob=await comprimir(files[i],1600);var r=await fetch('/anfitrion/nueva/foto?id='+encodeURIComponent(CFG.nuevoId)+'&tipo=foto',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});var j=await r.json();
        if(j.ok){fotos.push(j.url);pintarFotos();msg.textContent=''}else msg.textContent=j.error||'No se pudo subir.'}catch(e){msg.textContent='No se pudo subir la foto.'}subiendo--}});
  pintarFotos();
}
function sel(g){var b=document.querySelector(".chip.sel[data-g='"+g+"']");return b?b.dataset.v:''}
function pintarSup(){var w=$('supWrap');if(!dep){w.innerHTML="<p class='sub'>Marca primero el deporte.</p>";return}
  var l=CFG.superficies[dep]||[];if(l.indexOf(sup)<0)sup='';
  w.innerHTML="<div class='chips' style='margin-top:6px'>"+l.map(function(s){return "<button type='button' class='chip"+(s===sup?' sel':'')+"' data-g='sup' data-v='"+esc(s)+"'>"+esc(s)+"</button>"}).join('')+"</div>";
  $('nombreCancha').placeholder=CFG.auto[dep]||'Ej. Fútbol 2'}
document.addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-g]');if(!b)return;var g=b.dataset.g,v=b.dataset.v;
  b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');
  if(g==='deporte'){dep=v;pintarSup()}else if(g==='sup'){sup=v}});
pintarSup();
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo>0){msg.textContent='Espera a que terminen de subir las fotos.';return}
  if(fotos.length<(CFG.faltanFotos||0)){actualizarEnvio();return}
  var body={id:CFG.nuevoId,fotos:fotos,deporte:dep,superficie:sup,nombre:$('nombreCancha').value,modo_precio:pcgPrecioBody().modo_precio,precio:pcgPrecioBody().precio,precio_hora:parseFloat($('precio').value)||0,hora_apertura:$('hora_apertura').value,hora_cierre:$('hora_cierre').value,duracion_slot_min:+sel('duracion_slot_min')||60};
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Agregando…';
  try{var r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){location.href=j.url||'/anfitrion/canchas';return}msg.classList.add('err');msg.textContent=j.error||'No se pudo agregar.';if(j.campo){var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth'})}}
  catch(e){msg.classList.add('err');msg.textContent='No se pudo agregar. Revisa tu conexión.'}btn.disabled=fotos.length<(CFG.faltanFotos||0)});
})();
"""


def _validar_agregada(b: dict, l: dict, email: str) -> tuple[dict | None, str, str]:
    """Reglas de `AgregarCanchaScreen._guardar`: piso obligatorio, precio > 0,
    horario válido, duración del catálogo. Devuelve (fila, error, sección)."""
    if not isinstance(b, dict):
        return None, "Datos inválidos.", ""
    dep = str(b.get("deporte") or "").lower()
    if dep not in catalogos.DEPORTES_ACTIVOS:
        return None, "Marca el deporte de la cancha.", "cancha"
    sup = str(b.get("superficie") or "").strip()
    if sup not in catalogos.SUPERFICIES.get(dep, []):
        return None, "Marca el tipo de piso de la cancha (obligatorio).", "cancha"
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:catalogos.NOMBRE_MAX] or _nombre_auto(email, l, dep)
    ap, ci = str(b.get("hora_apertura") or "07:00"), str(b.get("hora_cierre") or "23:00")
    if not (_HORA_RE.match(ap) and _HORA_RE.match(ci)):
        return None, "Hora no válida (usa horas en punto).", "precio"
    try:
        dur = int(b.get("duracion_slot_min") or 60)
    except (TypeError, ValueError):
        dur = 0
    if dur not in catalogos.DURACIONES:
        return None, "Duración del turno no válida.", "precio"
    precio, precio_turno, err_precio = _precio_de_body(b, dur)
    if err_precio:
        return None, err_precio, "precio"
    # Hereda las fotos PROPIAS del local (las de Google no se guardan) y, si el
    # local tiene menos del mínimo, exige las que faltan subidas a la carpeta de
    # la cancha nueva (`/anfitrion/nueva/foto?id=<id nuevo>`).
    nuevo_id = str(b.get("id") or "")
    if not _ID_NUEVA_RE.match(nuevo_id) or datos.cancha(nuevo_id):
        nuevo_id = f"u{int(time.time() * 1000)}"
        for _ in range(20):  # dos altas en el mismo milisegundo no chocan
            if not datos.cancha(nuevo_id):
                break
            nuevo_id = f"u{int(nuevo_id[1:]) + 1}"
    heredadas = fotos_reclamo.de_cancha(l)
    nuevas = fotos_reclamo.propias([str(u) for u in (b.get("fotos") or [])], nuevo_id)
    fotos = (heredadas + [u for u in nuevas if u not in heredadas])[:catalogos.MAX_FOTOS]
    min_fotos = fotos_reclamo.minimo()
    if len(fotos) < min_fotos:
        return None, _error_faltan_fotos(min_fotos, len(fotos)), "fotos"
    fila = {"id": nuevo_id, "nombre": nombre, "club": (l.get("club") or "").strip() or l["nombre"],
            "distrito": l.get("distrito") or "", "barrio": l.get("barrio") or "", "deporte": dep, "deportes": [dep], "superficie": sup,
            "precio_hora": precio, "precio_turno": precio_turno or None, "lat": l.get("lat"), "lng": l.get("lng"), "club_fundador": bool(l.get("club_fundador")),
            "digitalizada": True, "direccion": l.get("direccion") or None, "registrada": True,
            "foto_url": fotos[0] if fotos else None, "fotos": fotos, "dueno": email,
            "verificada": bool(l.get("verificada")),  # hereda: si el local ya está activo, esta también
            "hora_apertura": ap, "hora_cierre": ci, "duracion_slot_min": dur, "eliminada": False,
            "amenidades": list(l.get("amenidades") or []),  # los servicios son del local
            "moneda": l.get("moneda") or _moneda_de(l)[0],
            # Los servicios extra DEL LOCAL (piscina, sauna…) también se heredan; los de la cancha no.
            "servicios_extra": [x for x in (_se.completar(y) for y in (l.get("servicios_extra") or []) if y.get("clave")) if x.get("ambito") == "local"],
            "descuento_valle": 0, "valle_desde": "07:00", "valle_hasta": "12:00", "sena_pct": 0}
    return fila, "", ""


@router.post("/anfitrion/cancha/{cancha_id}/agregar")
async def agregar_cancha_web(request: Request, cancha_id: str) -> JSONResponse:
    try:
        _cuerpo_json = await request.json()
    except Exception:  # noqa: BLE001
        _cuerpo_json = _JSON_INVALIDO
    return await run_in_threadpool(_agregar_cancha_web, request, cancha_id, _cuerpo_json)


def _agregar_cancha_web(request: Request, cancha_id: str, _cuerpo_json) -> JSONResponse:
    """INSERT de la cancha nueva heredando del local; sin reclamo nuevo."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    l = _cancha_propia(ses, cancha_id)
    if not l:
        return JSONResponse({"ok": False, "error": "no_encontrada"}, status_code=404)
    try:
        body = _leer_json(_cuerpo_json)
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    fila, err, seccion = _validar_agregada(body, l, ses["email"])
    if fila is None:
        return JSONResponse({"ok": False, "error": err, "campo": seccion}, status_code=400)
    if not datos.insertar_canchas([fila]):
        return JSONResponse({"ok": False, "error": "No pudimos guardar la cancha en este momento. Inténtalo de nuevo."}, status_code=503)
    print(f"[agregar-web] {ses['email']} agregó {fila['nombre']!r} ({fila['deporte']}) a {fila['club']!r}: {fila['id']} · verificada={fila['verificada']}", flush=True)
    return JSONResponse({"ok": True, "url": f"/anfitrion/canchas?agregada={fila['id']}", "id": fila["id"], "verificada": fila["verificada"]})


def _cancha_del_reclamo(email: str, c: dict, mias: list[dict] | None = None) -> dict:
    """La cancha sobre la que está el RECLAMO de esta cuenta para el lugar de
    `c` (en un registro con canchas separadas el reclamo va en la primera; en
    un legado, en la fila adoptada). Es la que debe tener las fotos propias."""
    em = (email or "").strip().lower()
    pool = [r for r in reclamos._reclamos_del_lugar(c["id"]) if (r.solicitante_id or "").strip().lower() == em]
    if pool:
        rid = max(pool, key=lambda r: r.id).cancha_id
        mias = mias if mias is not None else datos.canchas_de_dueno(email)
        x = next((m for m in mias if m.get("id") == rid), None)
        if x:
            return x
    return c


def aviso_fotos_reclamo(email: str, c: dict, mias: list[dict] | None = None) -> str:
    """Aviso ámbar "Sube N fotos de tu local para que podamos aprobarlo" con
    acceso directo a Editar cancha (decisión del director, 2-oct-2026). Vacío
    si la cancha ya está activa, no se exige o ya tiene las fotos."""
    m = fotos_reclamo.minimo()
    if m <= 0 or datos.reservable(c):
        return ""
    rc = _cancha_del_reclamo(email, c, mias)
    falta = max(0, m - len(fotos_reclamo.de_cancha(rc)))
    if not falta:
        return ""
    return (f"<div class='aviso warn' style='margin:12px 0 0'>📷 <b>{fotos_reclamo.texto_faltan(falta)}.</b> "
            "<span class='sub' style='margin:0'>Las fotos de Google no cuentan: sus términos no permiten guardarlas, y las tuyas prueban que el local existe.</span> "
            f"<a href='/anfitrion/cancha/{quote(rc['id'], safe='')}/editar#sec-fotos' style='font-weight:700;white-space:nowrap'>Subir fotos ›</a></div>")


def _pendientes_verificacion(canchas: list[dict], email: str) -> list[dict]:
    """Locales del dueño AÚN sin verificar (uno por reclamo), con el estado
    real del reclamo: {c, estado, clase, tit, txt}."""
    vistos, out = set(), []
    for c in canchas:
        if datos.reservable(c):
            continue
        base = c["id"].split("_")[0]
        if base in vistos:
            continue
        vistos.add(base)
        try:
            est = reclamos.estado(c["id"], email)
        except Exception:  # noqa: BLE001
            est = {}
        estado = str(est.get("estado") or "")
        clase, tit, txt = _ESTADO_RECLAMO.get(estado, ("warn", "Sin solicitud de verificación", "No encontramos tu solicitud. Toca «Ver estado y opciones» para reenviarla."))
        out.append({"c": c, "estado": estado, "clase": clase, "tit": tit, "txt": txt})
    return out


def _aviso_verificacion(canchas: list[dict], email: str, pend: list[dict] | None = None) -> str:
    """Banner del panel para las canchas del dueño AÚN sin verificar (espejo
    del cartel "pendiente" de la ficha del app): estado real del reclamo."""
    filas = []
    for p in (pend if pend is not None else _pendientes_verificacion(canchas, email)):
        c = p["c"]
        filas.append(f"<div class='aviso {p['clase']}' style='margin:12px 0 0'><b>{e(c.get('club') or c['nombre'])}</b> · {p['tit']}. <span class='sub' style='margin:0'>{p['txt']}</span> <a href='/anfitrion/verificacion/{quote(c['id'], safe='')}' style='font-weight:700;white-space:nowrap'>Ver estado y opciones ›</a></div>")
        if p["estado"] not in ("rechazada", "reclamada_por_otro"):
            filas.append(aviso_fotos_reclamo(email, c, canchas))
    return "".join(filas)


@router.get("/anfitrion/{modulo}", response_class=HTMLResponse)
def pagina_modulo_app(request: Request, modulo: str) -> HTMLResponse:
    """Mi academia · Mis campeonatos · Mi tienda · Verificador: hoy viven en
    el app (mismos datos que allí); la web muestra la sección y manda a la app."""
    it = next((m for m in MENU if m[0] == modulo and not m[6]), None)
    if it is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Sección no encontrada"); r.status_code = 404
        return r
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/{modulo}")
    if resp is not None:
        return resp
    _k, titulo, desc, color, ico, _href, _web = it
    cuerpo = (f"<div class='anf-hero'><a class='volver' href='/anfitrion' aria-label='Volver'>‹</a><h1>{e(titulo)}</h1><p>{e(desc)}</p></div>"
              "<div class='panel' style='max-width:640px;margin:22px auto 0;text-align:center'>"
              f"<span class='anf-item-ico' style='background:{color}'>{ico}</span>"
              f"<h2 style='margin-top:12px'>{e(titulo)} está en la app</h2>"
              f"<p class='sub'>Esta sección se administra desde la app de {MARCA} con la misma cuenta de Google. "
              "La versión web llegará más adelante.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}' rel='noopener'>Abrir en la app</a>"
              "<a class='btn sec' href='/anfitrion'>Volver al menú</a></div></div>")
    return ui.shell(titulo, _anf(cuerpo), nav=_cabecera("", ses, tabs_visibles=False), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión")


def _entrar(volver: str) -> HTMLResponse:
    from urllib.parse import quote
    return HTMLResponse("", status_code=302, headers={"Location": f"/entrar?volver={quote(volver, safe='')}"})
