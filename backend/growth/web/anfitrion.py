"""MODO ANFITRIÓN en la web (calcado de airbnb.com/hosting): el panel del
DUEÑO de canchas con su sesión de Google.

Secciones (pestañas de la cabecera, como Airbnb): **Hoy** (reservas de hoy,
mañana, próximos 7 días y las de efectivo por cobrar), **Calendario** (agenda
semanal por cancha: reservas, bloqueos y turnos libres), **Reservas** (todas,
agrupadas por día), **Ingresos** (saldo, saldo de regalo, por recibir,
liquidaciones y movimientos del backend) y **Canchas** (sus locales con su
ficha pública). Sin canchas a su nombre → página "Pon tu cancha" (el registro
y la verificación siguen en el app). **Editar la cancha** (fotos, nombre,
deportes, precio, horario, servicios) SÍ se hace aquí, con el mismo formulario
que el app; reserva manual y bloqueos siguen en el app por ahora.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from db.store import stores
from web import almacen, catalogos, datos, horarios, sesion, ui
from web.router import (PLAY_URL, _deporte, _deportes_de, _fotos, _maps, _moneda_de, _pais_de,
                        _zona, e)

router = APIRouter(tags=["web-anfitrion"])

# Pestañas de la sección "Mis canchas" (como airbnb.com/hosting).
SECCIONES = [("hoy", "Hoy", "/anfitrion/mis-canchas", "📅"), ("calendario", "Calendario", "/anfitrion/calendario", "🗓️"),
             ("reservas", "Reservas", "/anfitrion/reservas", "📋"), ("ingresos", "Ingresos", "/anfitrion/ingresos", "💰"),
             ("canchas", "Canchas", "/anfitrion/canchas", "🏟️")]

# Menú del modo anfitrión: EL MISMO del app (explorar_home_screen → Modo
# anfitrión): ícono en círculo de color, título, descripción y chevron.
MENU = [
    ("mis-canchas", "Mis canchas", "Registra y administra: canchas, agenda, reservas, cuenta", "#0B7A55", "🏬", "/anfitrion/mis-canchas", True),
    ("academia", "Mi academia", "Soy profe: alumnos, cuotas y cobros", "#E07A3F", "📣", "/anfitrion/academia", False),
    ("campeonatos", "Mis campeonatos", "Organiza torneos (fútbol, tenis…), invita y sortea", "#D4B048", "🏆", "/anfitrion/campeonatos", False),
    ("tienda", "Mi tienda", "Vende en el Marketplace Pichangol: raquetas, pelotas y más", "#7B61FF", "🏪", "/anfitrion/tienda", False),
    ("verificador", "Verificador", "Rol de campo: visitas con foto, GPS y firma", "#0E8F67", "🛡️", "/anfitrion/verificador", False),
]


def _cabecera(seccion: str, ses: dict | None, tabs_visibles: bool = True) -> str:
    tabs = "".join(f"<a class='cat{' sel' if k == seccion else ''}' href='{href}'><span class='ico'>{ico}</span>{n}</a>"
                   for k, n, href, ico in SECCIONES) if tabs_visibles else ""
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
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    return None, ui.shell("Modo anfitrión", cuerpo, sesion=None)


@router.get("/anfitrion", response_class=HTMLResponse)
def pagina_menu(request: Request) -> HTMLResponse:
    """Menú del modo anfitrión, IGUAL al del app: cabecera verde con el
    subtítulo y las cinco tarjetas (Mis canchas · Mi academia · Mis campeonatos
    · Mi tienda · Verificador)."""
    ses, resp = _sesion_o_entrar(request, "/anfitrion")
    if resp is not None:
        return resp
    items = "".join(
        f"<a class='anf-item' href='{href}'><span class='ico' style='background:{color}'>{ico}</span>"
        f"<span class='txt'><b>{e(titulo)}</b><small>{e(desc)}</small></span>"
        + ("" if web else "<span class='pill gris'>En la app</span>")
        + "<span class='chev'>›</span></a>" for _k, titulo, desc, color, ico, href, web in MENU)
    cuerpo = ("<div class='anf-hero'><a class='volver' href='/' aria-label='Volver'>‹</a><h1>Modo anfitrión</h1>"
              "<p>Publica tu cancha o academia y recibe reservas y alumnos.</p></div>"
              f"<div class='anf-menu'>{items}</div>")
    return ui.shell("Modo anfitrión", cuerpo, nav=_cabecera("", ses, tabs_visibles=False), sesion=ses, ancho=True,
                    titulo_tab="Modo anfitrión · Pichangol")


def _contexto(request: Request, volver: str):
    """(sesión, canchas del dueño) o una respuesta de redirección/onboarding."""
    ses, resp = _sesion_o_entrar(request, volver)
    if resp is not None:
        return None, None, resp
    canchas = datos.canchas_de_dueno(ses["email"])
    if not canchas:
        return ses, [], _onboarding(ses)
    return ses, canchas, None


def _onboarding(ses: dict) -> HTMLResponse:
    """Como "Conviértete en anfitrión" de Airbnb: el dueño aún no tiene canchas
    a su nombre; el registro (reclamo + verificación) vive en el app."""
    cuerpo = (
        "<div style='max-width:760px;margin:30px auto 0'>"
        f"<h1 class='anf-hola'>Hola, {e((ses.get('nombre') or ses.get('email') or '').split(' ')[0])} 👋</h1>"
        "<p class='sub' style='font-size:16px'>Con esta cuenta todavía no tienes canchas registradas. En Pichangol tu cancha "
        "recibe reservas y pagos en línea, y tú la administras desde la app y desde aquí.</p>"
        "<div class='kpis' style='margin-top:22px'>"
        "<div class='kpi'><small>1 · Regístrala</small><b style='font-size:16px'>Desde la app: Modo anfitrión → Pon tu cancha</b></div>"
        "<div class='kpi'><small>2 · Verifícala</small><b style='font-size:16px'>Confirmamos que eres el dueño (WhatsApp / visita)</b></div>"
        "<div class='kpi'><small>3 · Recibe reservas</small><b style='font-size:16px'>Pagos en línea, agenda y cobros aquí y en la app</b></div>"
        "</div>"
        f"<div class='acciones' style='margin-top:24px'><a class='btn' href='{PLAY_URL}' rel='noopener'>Registrar mi cancha en la app</a>"
        "<a class='btn sec' href='/#como'>Cómo funciona</a></div>"
        "<p class='sub' style='margin-top:18px;font-size:13px'>¿Ya registraste tu cancha con otro correo? Inicia sesión aquí con ese mismo correo de Google.</p>"
        "</div>")
    return ui.shell("Modo anfitrión", cuerpo, nav=_cabecera("hoy", ses), sesion=ses, ancho=True, titulo_tab="Modo anfitrión · Pichangol")


def _hoy(canchas: list[dict]) -> date:
    return horarios.ahora_local(_pais_de(canchas[0]) if canchas else "PE").date()


def _tarjeta_res(r: dict, c: dict | None, hoy: date) -> str:
    sim = r.get("moneda") or (c and _moneda_de(c)[0]) or "S/"
    pagado = bool(r.get("pagado"))
    medio = str(r.get("medio_pago") or "")
    if pagado and medio in ("yape", "tarjeta"):
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
    return (f"<div class='anf-res' data-fecha='{e(fecha)}' data-pagado='{1 if pagado else 0}'>"
            f"<div style='display:flex;justify-content:space-between;gap:8px;align-items:baseline'><span class='hora'>{e(r.get('hora_inicio'))}–{e(r.get('hora_fin'))}</span>"
            f"<span class='sub' style='margin:0;font-weight:700'>{e(dia)}{e(horarios.fecha_larga(fecha))}</span></div>"
            f"<div class='sub' style='margin:2px 0 0;font-weight:700;color:var(--noche)'>{e((c or {}).get('nombre') or 'Cancha')}</div>"
            f"<div class='quien'><span class='av'>{e(ini)}</span><div style='min-width:0'><b>{e(jugador)}</b>"
            f"<div class='sub' style='margin:0;font-size:12.5px'>{e(r.get('usuario') or '')}{(' · ' + e(tel)) if tel else ''}{' · reserva web' if web else ''}</div></div>"
            f"<b style='margin-left:auto;white-space:nowrap'>{e(sim)} {int(r.get('precio') or 0):.2f}</b></div>"
            f"<div class='acc'>{pill}"
            + (f"<a class='btn sec' href='https://wa.me/{e(''.join(ch for ch in tel if ch.isdigit()))}' target='_blank' rel='noopener'>💬 WhatsApp</a>" if tel else "")
            + "</div></div>")


@router.get("/anfitrion/mis-canchas", response_class=HTMLResponse)
def pagina_hoy(request: Request) -> HTMLResponse:
    """Mis canchas → "Hoy" de Airbnb: las reservas que tocan hoy, mañana y en
    los próximos 7 días, más lo pendiente de cobrar en efectivo."""
    ses, canchas, resp = _contexto(request, "/anfitrion/mis-canchas")
    if resp is not None:
        return resp
    hoy = _hoy(canchas)
    ids = [c["id"] for c in canchas]
    por_id = {c["id"]: c for c in canchas}
    desde, hasta = (hoy - timedelta(days=7)).isoformat(), (hoy + timedelta(days=7)).isoformat()
    filas = datos.reservas_de_canchas(ids, desde, hasta)
    h, m = hoy.isoformat(), (hoy + timedelta(days=1)).isoformat()
    grupos = {
        "hoy": [r for r in filas if str(r.get("fecha")) == h],
        "manana": [r for r in filas if str(r.get("fecha")) == m],
        "semana": [r for r in filas if h < str(r.get("fecha")) <= hasta],
        "cobrar": [r for r in filas if not r.get("pagado") and str(r.get("fecha")) <= h],
    }
    etiquetas = [("hoy", "Hoy"), ("manana", "Mañana"), ("semana", "Próximos 7 días"), ("cobrar", "Por cobrar en efectivo")]
    tabs = "".join(f"<button type='button' class='chip{' sel' if k == 'hoy' else ''}' data-tab='{k}'>{n} <small>({len(grupos[k])})</small></button>"
                   for k, n in etiquetas)
    vacios = {"hoy": "Hoy no tienes reservas. ¡Comparte tu cancha!", "manana": "Mañana no hay reservas todavía.",
              "semana": "Sin reservas en los próximos 7 días.", "cobrar": "No tienes cobros en efectivo pendientes. 🎉"}
    paneles = "".join(
        f"<div class='anf-grid' data-panel='{k}'{'' if k == 'hoy' else ' style=display:none'}>"
        + ("".join(_tarjeta_res(r, por_id.get(r.get("cancha_id")), hoy) for r in grupos[k]) if grupos[k]
           else f"<div class='anf-vacio' style='grid-column:1/-1'>{vacios[k]}</div>")
        + "</div>" for k, _ in etiquetas)
    n_ver = sum(1 for c in canchas if datos.reservable(c))
    cuerpo = (
        "<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
        f"<h1 class='anf-hola' style='margin-top:6px'>¡Hola, {e((ses.get('nombre') or ses.get('email') or '').split(' ')[0])}!</h1>"
        f"<p class='sub'>{len(canchas)} cancha{'s' if len(canchas) != 1 else ''} · {n_ver} verificada{'s' if n_ver != 1 else ''} · "
        f"{len(grupos['hoy'])} reserva{'s' if len(grupos['hoy']) != 1 else ''} hoy</p>"
        f"<h2 style='margin-top:22px'>Tus reservas</h2><div class='anf-tabs' id='anfTabs'>{tabs}</div>{paneles}"
        "<h2 style='margin-top:30px'>Atajos</h2><div class='kpis'>"
        "<a class='kpi' href='/anfitrion/calendario' style='text-decoration:none'><small>Agenda</small><b style='font-size:16px'>Ver el calendario semanal</b></a>"
        "<a class='kpi' href='/anfitrion/ingresos' style='text-decoration:none'><small>Plata</small><b style='font-size:16px'>Saldo y por recibir</b></a>"
        f"<a class='kpi' href='{PLAY_URL}' rel='noopener' style='text-decoration:none'><small>En la app</small><b style='font-size:16px'>Reserva manual · bloquear horas · marcar pagado</b></a>"
        "</div>"
        "<script>(function(){var t=document.getElementById('anfTabs');if(!t)return;t.addEventListener('click',function(ev){var b=ev.target.closest('[data-tab]');if(!b)return;"
        "t.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('sel',x===b);});document.querySelectorAll('[data-panel]').forEach(function(p){p.style.display=p.dataset.panel===b.dataset.tab?'':'none';});});})();</script>")
    return ui.shell("Hoy", cuerpo, nav=_cabecera("hoy", ses), sesion=ses, ancho=True, titulo_tab="Modo anfitrión · Pichangol")


@router.get("/anfitrion/reservas", response_class=HTMLResponse)
def pagina_reservas(request: Request) -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/reservas")
    if resp is not None:
        return resp
    hoy = _hoy(canchas)
    por_id = {c["id"]: c for c in canchas}
    filas = datos.reservas_de_canchas([c["id"] for c in canchas], (hoy - timedelta(days=30)).isoformat(), (hoy + timedelta(days=60)).isoformat())
    prox = [r for r in filas if str(r.get("fecha")) >= hoy.isoformat()]
    pas = [r for r in filas if str(r.get("fecha")) < hoy.isoformat()][::-1]
    def bloque(titulo: str, lst: list[dict], vacio: str) -> str:
        if not lst:
            return f"<h2 style='margin-top:26px'>{titulo}</h2><div class='anf-vacio'>{vacio}</div>"
        out, dia = f"<h2 style='margin-top:26px'>{titulo} <small style='color:var(--tenue);font-size:14px;font-weight:600'>· {len(lst)}</small></h2>", None
        for r in lst:
            f = str(r.get("fecha"))
            if f != dia:
                dia = f
                out += f"<h3 style='margin:16px 0 8px'>{e(horarios.etiqueta_dia(f, hoy))} · {e(horarios.fecha_larga(f))}</h3><div class='anf-grid'>"
                out += "".join(_tarjeta_res(x, por_id.get(x.get("cancha_id")), hoy) for x in lst if str(x.get("fecha")) == f) + "</div>"
        return out
    cuerpo = ("<h1 class='anf-hola'>Reservas</h1><p class='sub'>Las reservas de tus canchas: en línea (web y app) y las que registraste a mano.</p>"
              + bloque("Próximas", prox, "Sin reservas próximas.") + bloque("Pasadas (30 días)", pas, "Sin reservas en los últimos 30 días."))
    return ui.shell("Reservas", cuerpo, nav=_cabecera("reservas", ses), sesion=ses, ancho=True, titulo_tab="Reservas · Modo anfitrión")


@router.get("/anfitrion/calendario", response_class=HTMLResponse)
def pagina_calendario(request: Request, cancha: str = "", desde: str = "") -> HTMLResponse:
    """Agenda semanal de UNA cancha (chips para cambiar): reservas, bloqueos y
    turnos libres, con la misma regla de turnos que el app."""
    ses, canchas, resp = _contexto(request, "/anfitrion/calendario")
    if resp is not None:
        return resp
    hoy = _hoy(canchas)
    c = next((x for x in canchas if x["id"] == cancha), canchas[0])
    try:
        ini = date.fromisoformat(desde) if desde else hoy
    except ValueError:
        ini = hoy
    dias = [ini + timedelta(days=i) for i in range(7)]
    isos = [d.isoformat() for d in dias]
    filas = datos.reservas_de_canchas([c["id"]], isos[0], (dias[-1] + timedelta(days=1)).isoformat())
    bloq = datos.bloqueos_de([c["id"]], isos + [(dias[-1] + timedelta(days=1)).isoformat()])
    slots = horarios.slots(c["hora_apertura"], c["hora_cierre"], c["duracion_slot_min"])
    ocup = {(str(r.get("fecha")), str(r.get("hora_inicio"))): r for r in filas}
    ahora = horarios.ahora_local(_pais_de(c))
    chips = "".join(f"<a class='chip{' sel' if x['id'] == c['id'] else ''}' href='/anfitrion/calendario?cancha={e(x['id'])}&desde={isos[0]}'>{e(x['nombre'])}</a>" for x in canchas)
    cab = "".join(f"<th class='{'hoy' if d == hoy else ''}'>{horarios.DIAS[d.weekday()]}<br>{d.day} {horarios.MESES[d.month - 1]}</th>" for d in dias)
    filas_html = ""
    for h in slots:
        filas_html += f"<tr><td>{e(h)}</td>"
        for d in dias:
            fr = horarios.fecha_real(d.isoformat(), c["hora_apertura"], c["hora_cierre"], h)
            r = ocup.get((fr, h))
            m = horarios.hora_en_minutos(h) or 0
            pasado = fr < hoy.isoformat() or (fr == hoy.isoformat() and m < ahora.hour * 60 + ahora.minute)
            cls = " class='pasado'" if pasado else ""
            if r is not None:
                pag = bool(r.get("pagado"))
                filas_html += (f"<td{cls}><div class='oc{'' if pag else ' ef'}' title='{e(r.get('usuario') or '')}'>{e((r.get('jugador') or r.get('usuario') or 'Reserva').split(' ')[0])}"
                               f"<small>{'pagada' if pag else 'cobrar en cancha'}</small></div></td>")
            elif (c["id"], fr, h) in bloq:
                filas_html += f"<td{cls}><div class='bl'>Bloqueado</div></td>"
            else:
                filas_html += f"<td{cls}></td>"
        filas_html += "</tr>"
    ant, sig = (ini - timedelta(days=7)).isoformat(), (ini + timedelta(days=7)).isoformat()
    cuerpo = (
        "<h1 class='anf-hola'>Calendario</h1><p class='sub'>Semana por cancha: verde = reserva pagada, ámbar = cobrar en la cancha, gris = bloqueado.</p>"
        f"<div class='chips' style='margin-top:12px'>{chips}</div>"
        f"<div class='cal-nav2'><a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}&desde={ant}'>‹ Semana anterior</a>"
        f"<a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}&desde={hoy.isoformat()}'>Hoy</a>"
        f"<a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}&desde={sig}'>Semana siguiente ›</a>"
        f"<span class='sub' style='margin:0 0 0 auto'>{e(c['nombre'])} · {e(c['hora_apertura'])}–{e(c['hora_cierre'])} · turnos de {c['duracion_slot_min']} min</span></div>"
        f"<div class='cal-sem'><table><thead><tr><th></th>{cab}</tr></thead><tbody>{filas_html}</tbody></table></div>"
        f"<p class='sub' style='margin-top:12px;font-size:13px'>Para bloquear horas o registrar una reserva manual usa la app (Modo anfitrión → tu cancha). "
        f"<a href='{PLAY_URL}' rel='noopener'>Abrir la app</a>.</p>")
    return ui.shell("Calendario", cuerpo, nav=_cabecera("calendario", ses), sesion=ses, ancho=True, titulo_tab="Calendario · Modo anfitrión")


@router.get("/anfitrion/ingresos", response_class=HTMLResponse)
def pagina_ingresos(request: Request) -> HTMLResponse:
    """"Ingresos" de Airbnb: la billetera del dueño tal cual el backend (saldo,
    regalo, por recibir, liquidaciones pagadas y últimos movimientos)."""
    from pagos.router import _liquidacion_dict
    ses, canchas, resp = _contexto(request, "/anfitrion/ingresos")
    if resp is not None:
        return resp
    email = ses["email"]
    sim = _moneda_de(canchas[0])[0] if canchas else "S/"
    saldo = stores.saldo_centimos(email) / 100.0
    promo = stores.saldo_promo_centimos(email) / 100.0
    liqs = [_liquidacion_dict(p) | {"liquidado": p.liquidado, "liquidado_en": p.liquidado_en.isoformat() if p.liquidado_en else "", "medio": p.medio or ""}
            for p in stores.liquidaciones(email)]
    pend = [x for x in liqs if not x["liquidado"]]
    pagadas = [x for x in liqs if x["liquidado"]][::-1][:20]
    por_recibir = sum(x["neto_soles"] for x in pend)
    movs = [p for p in stores.pagos if p.dueno_id == email][::-1][:30]
    def fila_liq(x: dict) -> str:
        return (f"<div class='mov'><div><b>{e(x['concepto'])}</b><small>{e(x['creado_en'][:10])}{(' · pagada ' + e(x['liquidado_en'][:10])) if x.get('liquidado') else ''}"
                f"{(' · ' + e(x['medio'])) if x.get('medio') else ''}</small></div>"
                f"<div style='text-align:right'><b>{e(sim)} {x['neto_soles']:.2f}</b><small>bruto {x['bruto_soles']:.2f} · comisión {x['comision_soles']:.2f}</small></div></div>")
    def fila_mov(p) -> str:
        signo = "+" if p.tipo in ("recarga", "bono_recarga", "bono_bienvenida", "cupon") else ("−" if p.tipo in ("comision_reserva", "comision_efectivo", "pro", "suscripcion") else "")
        return (f"<div class='mov'><div><b>{e(p.concepto or p.tipo)}</b><small>{e(p.tipo)} · {e(p.creado_en.isoformat()[:10])} · {e(p.estado)}</small></div>"
                f"<b>{signo}{e(sim)} {p.monto_centimos / 100.0:.2f}</b></div>")
    cuerpo = (
        "<h1 class='anf-hola'>Ingresos</h1><p class='sub'>La misma billetera que ves en la app.</p>"
        "<div class='kpis'>"
        f"<div class='kpi'><small>Por recibir (reservas en línea)</small><b>{e(sim)} {por_recibir:.2f}</b><small>{len(pend)} liquidación{'es' if len(pend) != 1 else ''} pendiente{'s' if len(pend) != 1 else ''}</small></div>"
        f"<div class='kpi'><small>Saldo Pichangol</small><b>{e(sim)} {saldo:.2f}</b><small>de aquí sale la comisión</small></div>"
        + (f"<div class='kpi'><small>Saldo de regalo 🎁</small><b>{e(sim)} {promo:.2f}</b><small>cubre comisiones</small></div>" if promo > 0 else "")
        + "</div>"
        f"<p style='margin-top:14px'><a class='btn sec' href='{PLAY_URL}' rel='noopener' style='padding:10px 16px;font-size:14px'>Recargar saldo en la app</a></p>"
        "<h2 style='margin-top:28px'>Por recibir</h2>"
        + ("".join(fila_liq(x) for x in pend) if pend else "<div class='anf-vacio'>Nada pendiente. Cuando un jugador pague en línea, el neto aparece aquí.</div>")
        + "<h2 style='margin-top:28px'>Liquidaciones pagadas</h2>"
        + ("".join(fila_liq(x) for x in pagadas) if pagadas else "<div class='anf-vacio'>Aún no te hemos transferido liquidaciones.</div>")
        + "<h2 style='margin-top:28px'>Últimos movimientos</h2>"
        + ("".join(fila_mov(p) for p in movs) if movs else "<div class='anf-vacio'>Sin movimientos todavía.</div>"))
    return ui.shell("Ingresos", cuerpo, nav=_cabecera("ingresos", ses), sesion=ses, ancho=True, titulo_tab="Ingresos · Modo anfitrión")


@router.get("/anfitrion/canchas", response_class=HTMLResponse)
def pagina_canchas(request: Request, guardado: str = "") -> HTMLResponse:
    ses, canchas, resp = _contexto(request, "/anfitrion/canchas")
    if resp is not None:
        return resp
    tarjetas = ""
    for c in canchas:
        sim, _ = _moneda_de(c)
        fs = _fotos(c)
        foto = f"<img src='{e(fs[0])}' alt=''>" if fs else _deporte(c.get("deporte"))[1]
        ok = datos.reservable(c)
        deps = " · ".join(_deporte(d)[0] for d in _deportes_de(c)[:3])
        pill = "<span class='pill ok'>✓ Verificada</span>" if ok else "<span class='pill warn'>Aún sin verificar</span>"
        tarjetas += (
            f"<div class='anf-cancha'><div class='f'>{foto}</div><div style='flex:1;min-width:0'>"
            f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><b style='font-size:16px'>{e(c['nombre'])}</b>{pill}</div>"
            f"<div class='sub' style='margin:2px 0 0'>{e(c.get('club') or '')}{(' · ' + e(_zona(c))) if _zona(c) else ''}</div>"
            f"<div class='sub' style='margin:6px 0 0;color:var(--noche);font-weight:600'>{e(deps)} · {e(c['hora_apertura'])}–{e(c['hora_cierre'])} · {c['duracion_slot_min']} min · <b>{e(sim)} {c['precio_hora']:.2f}</b>/h</div>"
            "<div class='acciones' style='margin-top:10px'>"
            f"<a class='btn sec' href='/reservar/{e(c['id'])}'>Ver ficha pública</a>"
            f"<a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}'>Calendario</a>"
            f"<a class='btn sec' href='{_maps(c)}' target='_blank' rel='noopener'>📍 Mapa</a>"
            f"<a class='btn' href='/anfitrion/cancha/{e(c['id'])}/editar'>✏️ Editar</a>"
            "</div></div></div>")
    guardada = next((c for c in canchas if c["id"] == guardado), None) if guardado else None
    aviso = (f"<div class='aviso ok' style='margin:16px 0 0'>✅ Guardamos los cambios de <b>{e(guardada['nombre'])}</b>. "
             "Ya se ven en la ficha pública y en la app.</div>") if guardada else ""
    cuerpo = ("<h1 class='anf-hola'>Canchas</h1><p class='sub'>Tus locales en Pichangol. Edita precio, horario, fotos y servicios aquí o en la app: es la misma cancha.</p>"
              f"{aviso}"
              f"<div class='anf-grid' style='grid-template-columns:repeat(auto-fill,minmax(360px,1fr));margin-top:16px'>{tarjetas}</div>"
              f"<p style='margin-top:20px'><a class='btn' href='{PLAY_URL}' rel='noopener'>Registrar otra cancha en la app</a></p>")
    return ui.shell("Canchas", cuerpo, nav=_cabecera("canchas", ses), sesion=ses, ancho=True, titulo_tab="Canchas · Modo anfitrión")



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


def _select_hora(nombre: str, valor: str) -> str:
    ops = "".join(f"<option value='{h}'{' selected' if h == valor else ''}>{h}</option>" for h in catalogos.HORAS)
    return f"<select name='{nombre}' id='{nombre}'>{ops}</select>"


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
    fotos = _fotos(c)
    servicios = {str(s.get("clave")): float(s.get("precio") or 0) for s in (c.get("servicios_extra") or [])}
    filas_serv = ""
    for k, (nombre, ico) in catalogos.SERVICIOS_EXTRA.items():
        on = k in servicios
        precio_txt = f"{servicios[k]:.2f}" if on else ""
        filas_serv += (f"<div class='serv{' sel' if on else ''}' data-serv='{k}'>"
                       f"<button type='button' class='chip{' sel' if on else ''}' data-g='servicios' data-v='{k}'>{ico} {e(nombre)}</button>"
                       f"<label class='precio-serv'{'' if on else ' hidden'}><span>{e(sim)}</span>"
                       f"<input type='number' name='serv_{k}' min='0.5' step='0.5' inputmode='decimal' value='{precio_txt}' placeholder='Precio'></label></div>")
    fotos_html = "".join(
        f"<div class='foto' data-url='{e(u)}'><img src='{e(u)}' alt=''>"
        f"<span class='portada'{'' if i == 0 else ' hidden'}>Portada</span>"
        "<div class='acc'><button type='button' class='mini' data-acc='portada' title='Usar como portada'>★</button>"
        "<button type='button' class='mini' data-acc='quitar' title='Quitar'>✕</button></div></div>" for i, u in enumerate(fotos))
    secciones = [("fotos", "Fotos"), ("nombre", "Nombre y local"), ("deportes", "Deportes y piso"), ("precio", "Precio y promociones"),
                 ("horario", "Horario"), ("amenidades", "Servicios del local"), ("extras", "Servicios extra")]
    nav = "".join(f"<a href='#sec-{k}' class='edit-nav-it'>{n}</a>" for k, n in secciones)
    cfg = {"id": c["id"], "moneda": sim, "fotos": fotos, "deportes": deps, "superficie": c.get("superficie") or "",
           "superficies": catalogos.SUPERFICIES, "activos": catalogos.DEPORTES_ACTIVOS, "maxFotos": catalogos.MAX_FOTOS,
           "storage": almacen.disponible()}
    cuerpo = f"""
<div class='edit-top'><a class='volver-lnk' href='/anfitrion/canchas'>‹ Canchas</a>
<h1 class='anf-hola' style='margin-top:8px'>Editar cancha</h1><p class='sub'>{e(c['nombre'])}{(' · ' + e(c.get('club'))) if c.get('club') else ''} · {e(_zona(c)) if _zona(c) else 'Pichangol'}</p></div>
<div class='edit-grid'>
<nav class='edit-nav'>{nav}</nav>
<form id='fEdit' class='edit-form' autocomplete='off' novalidate>
 <section class='panel edit-sec' id='sec-fotos'><h2>Fotos</h2><p class='sub'>La primera es la portada en Explorar y en la ficha. Hasta {catalogos.MAX_FOTOS} fotos.</p>
  <div class='edit-fotos' id='fotos'>{fotos_html}</div>
  <div class='acciones' style='margin-top:12px'><label class='btn sec' for='inFotos'>📷 Agregar fotos</label><input type='file' id='inFotos' accept='image/*' multiple hidden{' disabled' if not almacen.disponible() else ''}>
  <span class='sub' id='fotosMsg' style='margin:0'>{'' if almacen.disponible() else 'La subida de fotos desde la web no está disponible en este ambiente; súbelas desde la app.'}</span></div>
 </section>
 <section class='panel edit-sec' id='sec-nombre'><h2>Nombre y local</h2>
  <label for='nombre'>Nombre de la cancha</label><input id='nombre' name='nombre' maxlength='{catalogos.NOMBRE_MAX}' value='{e(c['nombre'])}' placeholder='Ej. Cancha 1 · Grass'>
  <label for='club'>Local / club</label><input id='club' name='club' maxlength='{catalogos.NOMBRE_MAX}' value='{e(c.get('club') or '')}' placeholder='Ej. Complejo Los Olivos'>
  <p class='sub' style='font-size:13px'>El local agrupa tus canchas en la ficha. Si lo cambias aquí, solo cambia en esta cancha.</p>
 </section>
 <section class='panel edit-sec' id='sec-deportes'><h2>Deportes y tipo de piso</h2><p class='sub'>Marca todo lo que se juega en esta misma superficie (la agenda es una sola).</p>
  {_chips('deportes', dep_ops, set(deps), multi=True)}
  <label style='margin-top:18px'>Tipo de piso <span class='req'>obligatorio</span></label>
  <div id='supWrap'>{_chips('superficie', superficies, c.get('superficie') or '')}</div>
 </section>
 <section class='panel edit-sec' id='sec-precio'><h2>Precio y promociones</h2>
  <label for='precio'>Precio por hora</label>
  <div class='inp-moneda'><span>{e(sim)}</span><input id='precio' name='precio' type='number' min='1' step='0.01' inputmode='decimal' value='{c['precio_hora']:.2f}'></div>
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
 <section class='panel edit-sec' id='sec-horario'><h2>Horario</h2>
  <div class='row'><div><label for='hora_apertura'>Abre</label>{_select_hora('hora_apertura', c['hora_apertura'])}</div>
  <div><label for='hora_cierre'>Cierra</label>{_select_hora('hora_cierre', c['hora_cierre'])}</div></div>
  <p class='sub' style='font-size:13px'>La hora de cierre es la hora en que <b>empieza el último turno</b>: si cierras a las 23:00, el último turno es 23:00–00:00. Un cierre menor o igual a la apertura cae al día siguiente (00:00 = hasta medianoche, 00:00→00:00 = 24 h).</p>
  <label style='margin-top:14px'>Duración del turno</label>
  {_chips('duracion_slot_min', catalogos.DURACIONES, int(c.get('duracion_slot_min') or 60), fmt=catalogos.etiqueta_duracion)}
 </section>
 <section class='panel edit-sec' id='sec-amenidades'><h2>Servicios del local</h2><p class='sub'>Gratis para el jugador. Salen como filtros en Explorar.</p>
  {_chips('amenidades', [(k, f'{ico} {e(n)}') for k, (n, ico) in catalogos.AMENIDADES.items()], set(str(a) for a in (c.get('amenidades') or [])), multi=True)}
 </section>
 <section class='panel edit-sec' id='sec-extras'><h2>Servicios extra</h2><p class='sub'>De pago: el jugador los agrega al reservar y suman al total.</p>
  <div class='servs'>{filas_serv}</div>
 </section>
</form>
</div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>Los cambios se ven al instante en la ficha pública y en la app.</span>
<button type='button' class='btn' id='btnGuardar'>Guardar cambios</button></div></div>
<script>var CFG={json.dumps(cfg, ensure_ascii=False)};</script>
<script>{_JS_EDITAR}</script>"""
    return ui.shell("Editar cancha", cuerpo, nav=_cabecera("canchas", ses), sesion=ses, ancho=True,
                    titulo_tab=f"Editar {c['nombre']} · Modo anfitrión")


_JS_EDITAR = r"""
(function(){
var f=document.getElementById('fEdit'), fotos=CFG.fotos.slice(), dep=CFG.deportes.slice(), sup=CFG.superficie, subiendo=0;
function $(id){return document.getElementById(id)}
function sel(g){return Array.prototype.slice.call(document.querySelectorAll(".chip.sel[data-g='"+g+"']")).map(function(b){return b.dataset.v})}
function principal(){for(var i=0;i<CFG.activos.length;i++){if(dep.indexOf(CFG.activos[i])>=0)return CFG.activos[i]}return dep[0]||'futbol'}
function pintarSup(){var ops=CFG.superficies[principal()]||[];if(ops.indexOf(sup)<0)sup='';
  $('supWrap').innerHTML="<div class='chips' data-grupo='superficie'>"+ops.map(function(o){return "<button type='button' class='chip"+(o===sup?' sel':'')+"' data-g='superficie' data-v='"+o.replace(/'/g,'&#39;')+"'>"+o+"</button>"}).join('')+"</div>"}
function pintarFotos(){$('fotos').innerHTML=fotos.map(function(u,i){return "<div class='foto' data-url='"+u.replace(/'/g,'&#39;')+"'><img src='"+u.replace(/'/g,'&#39;')+"' alt=''><span class='portada'"+(i?' hidden':'')+">Portada</span><div class='acc'><button type='button' class='mini' data-acc='portada' title='Usar como portada'>★</button><button type='button' class='mini' data-acc='quitar' title='Quitar'>✕</button></div></div>"}).join('')}
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
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo>0){msg.textContent='Espera a que terminen de subir las fotos.';return}
  var serv=[];document.querySelectorAll('.serv.sel').forEach(function(r){serv.push({clave:r.dataset.serv,precio:parseFloat(r.querySelector('input').value)||0})});
  var body={nombre:$('nombre').value,club:$('club').value,deportes:dep,superficie:sup,precio_hora:parseFloat($('precio').value),
    descuento_valle:parseInt(sel('descuento_valle')[0]||'0'),valle_desde:$('valle_desde').value,valle_hasta:$('valle_hasta').value,
    sena_pct:parseInt(sel('sena_pct')[0]||'0'),hora_apertura:$('hora_apertura').value,hora_cierre:$('hora_cierre').value,
    duracion_slot_min:parseInt(sel('duracion_slot_min')[0]||'60'),amenidades:sel('amenidades'),servicios_extra:serv,fotos:fotos};
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
        precio = round(float(b.get("precio_hora")), 2)
    except (TypeError, ValueError):
        return None, "Pon el precio por hora.", "precio"
    if not (0 < precio <= 100000):
        return None, "El precio por hora debe ser mayor a 0.", "precio"
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
    horas = {}
    for k, defecto in (("hora_apertura", "07:00"), ("hora_cierre", "23:00"), ("valle_desde", "07:00"), ("valle_hasta", "12:00")):
        v = str(b.get(k) or c.get(k) or defecto)
        if not _HORA_RE.match(v):
            return None, "Hora no válida (usa horas en punto).", "horario" if k.startswith("hora") else "precio"
        horas[k] = v
    if desc > 0 and horas["valle_desde"] == horas["valle_hasta"]:
        return None, "La hora feliz necesita un rango (desde y hasta distintos).", "precio"
    amen = []
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
        if k not in catalogos.SERVICIOS_EXTRA or k in vistos:
            continue
        try:
            p = round(float(s.get("precio")), 2)
        except (TypeError, ValueError):
            p = 0
        if p <= 0:
            return None, f"Pon el precio de «{catalogos.SERVICIOS_EXTRA[k][0]}» o quítalo.", "extras"
        vistos.add(k)
        servicios.append({"clave": k, "precio": p})
    # Fotos: solo las que ya tenía la cancha o las subidas a SU carpeta del
    # bucket (nadie cuela una URL ajena en la galería).
    actuales = set(_fotos(c))
    prefijo = almacen.prefijo_cancha(c["id"]) if almacen.disponible() else None
    fotos = []
    for u in (b.get("fotos") or []):
        u = str(u).strip()
        if u and u not in fotos and (u in actuales or (prefijo and u.startswith(prefijo))):
            fotos.append(u)
    fotos = fotos[:catalogos.MAX_FOTOS]
    return {
        "nombre": nombre, "club": club, "deporte": principal, "deportes": deps, "superficie": superficie,
        "precio_hora": precio, "descuento_valle": desc, "valle_desde": horas["valle_desde"], "valle_hasta": horas["valle_hasta"],
        "sena_pct": sena, "hora_apertura": horas["hora_apertura"], "hora_cierre": horas["hora_cierre"], "duracion_slot_min": dur,
        "amenidades": amen, "servicios_extra": servicios, "fotos": fotos, "foto_url": fotos[0] if fotos else "",
    }, "", ""


@router.post("/anfitrion/cancha/{cancha_id}/editar")
async def guardar_edicion_cancha(request: Request, cancha_id: str) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    c = _cancha_propia(ses, cancha_id)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    campos, err, seccion = _validar_edicion(c, body)
    if campos is None:
        return JSONResponse({"ok": False, "error": err, "campo": seccion}, status_code=400)
    quitadas = [u for u in _fotos(c) if u not in campos["fotos"]]  # antes del UPDATE (c puede ser la misma fila)
    if not datos.actualizar_cancha(cancha_id, ses["email"], campos):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento. Inténtalo de nuevo."}, status_code=503)
    if quitadas:
        threading.Thread(target=lambda: [almacen.borrar_foto(u) for u in quitadas], daemon=True).start()
    print(f"[editar-web] {ses['email']} guardó {cancha_id}: {campos['nombre']} · {campos['precio_hora']} · "
          f"{campos['hora_apertura']}-{campos['hora_cierre']}/{campos['duracion_slot_min']}m · fotos={len(campos['fotos'])}", flush=True)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/cancha/{cancha_id}/foto")
async def subir_foto_cancha(request: Request, cancha_id: str) -> JSONResponse:
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
    cuerpo = await request.body()
    if not cuerpo or len(cuerpo) > almacen.MAX_BYTES:
        return JSONResponse({"ok": False, "error": "La foto pesa demasiado (máx. 6 MB)."}, status_code=413)
    url = almacen.subir_foto(cancha_id, cuerpo, ctype)
    if not url:
        return JSONResponse({"ok": False, "error": "No se pudo subir la foto. Inténtalo de nuevo."}, status_code=502)
    return JSONResponse({"ok": True, "url": url})


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
              "<p class='sub'>Esta sección se administra desde la app de Pichangol con la misma cuenta de Google. "
              "La versión web llegará más adelante.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}' rel='noopener'>Abrir en la app</a>"
              "<a class='btn sec' href='/anfitrion'>Volver al menú</a></div></div>")
    return ui.shell(titulo, cuerpo, nav=_cabecera("", ses, tabs_visibles=False), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión")


def _entrar(volver: str) -> HTMLResponse:
    from urllib.parse import quote
    return HTMLResponse("", status_code=302, headers={"Location": f"/entrar?volver={quote(volver, safe='')}"})
