"""MODO ANFITRIÓN en la web (calcado de airbnb.com/hosting): el panel del
DUEÑO de canchas con su sesión de Google.

Secciones (pestañas de la cabecera, como Airbnb): **Hoy** (reservas de hoy,
mañana, próximos 7 días y las de efectivo por cobrar), **Calendario** (agenda
semanal por cancha: reservas, bloqueos y turnos libres), **Reservas** (todas,
agrupadas por día), **Ingresos** (saldo, saldo de regalo, por recibir,
liquidaciones y movimientos del backend) y **Canchas** (sus locales con su
ficha pública). Sin canchas a su nombre → página "Pon tu cancha" (el registro
y la verificación siguen en el app). Todo es LECTURA + enlaces a la app para
lo operativo (reserva manual, bloqueos, editar): el app sigue siendo el
panel completo; la web es el espejo cómodo desde la laptop.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from db.store import stores
from web import datos, horarios, sesion, ui
from web.router import (PLAY_URL, _deporte, _deportes_de, _fotos, _maps, _moneda_de, _pais_de,
                        _zona, e)

router = APIRouter(tags=["web-anfitrion"])

SECCIONES = [("hoy", "Hoy", "/anfitrion", "📅"), ("calendario", "Calendario", "/anfitrion/calendario", "🗓️"),
             ("reservas", "Reservas", "/anfitrion/reservas", "📋"), ("ingresos", "Ingresos", "/anfitrion/ingresos", "💰"),
             ("canchas", "Canchas", "/anfitrion/canchas", "🏟️")]


def _cabecera(seccion: str, ses: dict | None) -> str:
    tabs = "".join(f"<a class='cat{' sel' if k == seccion else ''}' href='{href}'><span class='ico'>{ico}</span>{n}</a>"
                   for k, n, href, ico in SECCIONES)
    return ui.cabecera(tabs=tabs, ses=ses, volver="/anfitrion", modo="anfitrion")


def _entrar(volver: str) -> HTMLResponse:
    from urllib.parse import quote
    return HTMLResponse("", status_code=302, headers={"Location": f"/entrar?volver={quote(volver, safe='')}"})


def _contexto(request: Request, volver: str):
    """(sesión, canchas del dueño) o una respuesta de redirección/onboarding."""
    ses = sesion.de_request(request)
    if not ses:
        if sesion.activo():
            return None, None, _entrar(volver)
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
                  "<h1 style='font-size:22px'>Modo anfitrión</h1>"
                  "<p class='sub'>En esta web aún no está activo el inicio de sesión. Administra tus canchas desde la app.</p>"
                  f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
        return None, None, ui.shell("Modo anfitrión", cuerpo, sesion=None)
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


@router.get("/anfitrion", response_class=HTMLResponse)
def pagina_hoy(request: Request) -> HTMLResponse:
    """"Hoy" de Airbnb: las reservas que tocan hoy, mañana y en los próximos 7
    días, más lo pendiente de cobrar en efectivo."""
    ses, canchas, resp = _contexto(request, "/anfitrion")
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
        f"<h1 class='anf-hola'>¡Hola, {e((ses.get('nombre') or ses.get('email') or '').split(' ')[0])}!</h1>"
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
def pagina_canchas(request: Request) -> HTMLResponse:
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
            f"<a class='btn sec' href='{PLAY_URL}' rel='noopener'>Editar en la app</a>"
            "</div></div></div>")
    cuerpo = ("<h1 class='anf-hola'>Canchas</h1><p class='sub'>Tus locales en Pichangol. Precio, horario y fotos se editan en la app y se ven aquí al instante.</p>"
              f"<div class='anf-grid' style='grid-template-columns:repeat(auto-fill,minmax(360px,1fr));margin-top:16px'>{tarjetas}</div>"
              f"<p style='margin-top:20px'><a class='btn' href='{PLAY_URL}' rel='noopener'>Registrar otra cancha en la app</a></p>")
    return ui.shell("Canchas", cuerpo, nav=_cabecera("canchas", ses), sesion=ses, ancho=True, titulo_tab="Canchas · Modo anfitrión")
