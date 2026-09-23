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
import time
from datetime import date, timedelta

import config
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import paises
import servicios_extra as _se
from db.store import stores
from propiedad import reclamos
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
    ("academia", "Mi academia", "Soy profe: alumnos, cuotas y cobros", "#E07A3F", "📣", "/anfitrion/academia", True),
    ("campeonatos", "Mis campeonatos", "Organiza torneos (fútbol, tenis…), invita y sortea", "#D4B048", "🏆", "/anfitrion/campeonatos", False),
    ("tienda", "Mi tienda", "Vende en el Marketplace Pichangol: raquetas, pelotas y más", "#7B61FF", "🏪", "/anfitrion/tienda", True),
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
        "<div class='kpi'><small>1 · Regístrala</small><b style='font-size:16px'>Aquí mismo o desde la app: Pon tu cancha</b></div>"
        "<div class='kpi'><small>2 · Verifícala</small><b style='font-size:16px'>Confirmamos que eres el dueño (WhatsApp / visita)</b></div>"
        "<div class='kpi'><small>3 · Recibe reservas</small><b style='font-size:16px'>Pagos en línea, agenda y cobros aquí y en la app</b></div>"
        "</div>"
        "<div class='acciones' style='margin-top:24px'><a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a>"
        f"<a class='btn sec' href='{PLAY_URL}' rel='noopener'>O desde la app</a><a class='btn sec' href='/#como'>Cómo funciona</a></div>"
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
            + (f"<button type='button' class='btn' data-pagar='{e(r.get('id'))}' data-v='1'>✅ Marcar pagada</button>" if not pagado
               else (f"<button type='button' class='btn sec' data-pagar='{e(r.get('id'))}' data-v='0'>↩ Marcar por cobrar</button>" if medio not in ("yape", "tarjeta") else ""))
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
        f"{_aviso_verificacion(canchas, ses['email'])}"
        f"<h2 style='margin-top:22px'>Tus reservas</h2><div class='anf-tabs' id='anfTabs'>{tabs}</div>{paneles}"
        "<h2 style='margin-top:30px'>Atajos</h2><div class='kpis'>"
        "<a class='kpi' href='/anfitrion/calendario' style='text-decoration:none'><small>Agenda</small><b style='font-size:16px'>Ver el calendario semanal</b></a>"
        "<a class='kpi' href='/anfitrion/ingresos' style='text-decoration:none'><small>Plata</small><b style='font-size:16px'>Saldo y por recibir</b></a>"
        "<a class='kpi' href='/anfitrion/calendario' style='text-decoration:none'><small>Operar</small><b style='font-size:16px'>Reserva manual · bloquear horas · marcar pagado</b></a>"
        "</div>"
        f"<script>{JS_PAGAR}</script>"
        "<script>window.alPagar=function(id,v){var b=document.querySelector(\"[data-pagar='\"+id+\"']\");if(!b)return;var card=b.closest('.anf-res');card.dataset.pagado=v?'1':'0';"
        "var pill=card.querySelector('.pill');if(pill){pill.className='pill '+(v?'ok':'warn');pill.textContent=v?'Cobrada':'Cobrar en la cancha'}"
        "b.disabled=false;b.dataset.v=v?'0':'1';b.className='btn'+(v?' sec':'');b.innerHTML=v?'↩ Marcar por cobrar':'✅ Marcar pagada'};</script>"
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


JS_PAGAR = r"""
function pcgToast(t){var el=document.createElement('div');el.className='toast';el.textContent=t;document.body.appendChild(el);setTimeout(function(){el.classList.add('on')},10);setTimeout(function(){el.classList.remove('on');setTimeout(function(){el.remove()},300)},2600)}
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-pagar]');if(!b||b.disabled)return;var id=b.dataset.pagar,v=b.dataset.v==='1',txt=b.innerHTML;b.disabled=true;b.innerHTML='Guardando…';
  try{var r=await fetch('/anfitrion/reserva/'+encodeURIComponent(id)+'/pagado',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pagado:v})});var j=await r.json();
    if(j.ok){pcgToast(v?'✅ Pago registrado':'↩ Marcada por cobrar');if(window.alPagar){window.alPagar(id,v);return}location.reload();return}
    pcgToast(j.error||'No se pudo guardar.')}catch(e){pcgToast('No se pudo guardar. Revisa tu conexión.')} b.disabled=false;b.innerHTML=txt});
"""


def _en_segundo_plano(fn, *args) -> None:
    """Push y otras llamadas de red a terceros NO retrasan la respuesta al
    dueño (un clic debe responder al instante). Los tests lo vuelven síncrono."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _pro_ok(email: str) -> bool:
    """Candado Pro de reserva manual / bloqueos (fail-open: solo si la env
    `WEB_MANUAL_REQUIERE_PRO=1`, igual que CM_REQUIERE_PRO)."""
    return (not config.WEB_MANUAL_REQUIERE_PRO) or stores.pro_activo(email)


_RESP_PRO = {"ok": False, "error": "requiere_pro",
             "mensaje": "La reserva manual y el bloqueo de horas son parte de Pichangol Pro. Actívalo en la app (Perfil → Hazte Pro)."}


@router.get("/anfitrion/calendario", response_class=HTMLResponse)
def pagina_calendario(request: Request, cancha: str = "", desde: str = "") -> HTMLResponse:
    """Agenda semanal de UNA cancha (chips para cambiar): reservas, bloqueos y
    turnos libres, con la misma regla de turnos que el app. Al tocar un turno
    (como el calendario de Airbnb): libre → reserva manual o bloquear;
    bloqueado → desbloquear; reservado → detalle, marcar pagada / por cobrar
    y quitar (solo las manuales)."""
    ses, canchas, resp = _contexto(request, "/anfitrion/calendario")
    if resp is not None:
        return resp
    hoy = _hoy(canchas)
    c = next((x for x in canchas if x["id"] == cancha), canchas[0])
    sim, _iso = _moneda_de(c)
    try:
        ini = date.fromisoformat(desde) if desde else hoy
    except ValueError:
        ini = hoy
    dias = [ini + timedelta(days=i) for i in range(7)]
    isos = [d.isoformat() for d in dias]
    sig_dia = (dias[-1] + timedelta(days=1)).isoformat()
    filas = datos.reservas_de_canchas([c["id"]], isos[0], sig_dia)
    bloq = datos.bloqueos_de([c["id"]], isos + [sig_dia])
    desc = datos.descuentos(c["id"], isos + [sig_dia])
    slots = horarios.slots(c["hora_apertura"], c["hora_cierre"], c["duracion_slot_min"])
    paso = c["duracion_slot_min"]
    ocup = {(str(r.get("fecha")), str(r.get("hora_inicio"))): r for r in filas}
    ahora = horarios.ahora_local(_pais_de(c))
    chips = "".join(f"<a class='chip{' sel' if x['id'] == c['id'] else ''}' href='/anfitrion/calendario?cancha={e(x['id'])}&desde={isos[0]}'>{e(x['nombre'])}</a>" for x in canchas)
    cab = "".join(f"<th class='{'hoy' if d == hoy else ''}'>{horarios.DIAS[d.weekday()]}<br>{d.day} {horarios.MESES[d.month - 1]}</th>" for d in dias)
    res_json: dict[str, dict] = {}
    filas_html = ""
    for h in slots:
        filas_html += f"<tr><td>{e(h)}</td>"
        fin = horarios.hora_fin(h, paso)
        for d in dias:
            fr = horarios.fecha_real(d.isoformat(), c["hora_apertura"], c["hora_cierre"], h)
            r = ocup.get((fr, h))
            m = horarios.hora_en_minutos(h) or 0
            pasado = fr < hoy.isoformat() or (fr == hoy.isoformat() and m < ahora.hour * 60 + ahora.minute)
            ph = horarios.precio_hora_en(c["precio_hora"], h, c["descuento_valle"], c.get("valle_desde"), c.get("valle_hasta"))
            precio = horarios.precio_slot(ph, paso, desc.get((fr, h), 0))
            base = f" data-b='{d.isoformat()}' data-f='{fr}' data-h='{h}' data-fin='{fin}' data-p='{precio}'"
            if r is not None:
                pag = bool(r.get("pagado"))
                rid = str(r.get("id") or "")
                res_json[rid] = {"id": rid, "jugador": r.get("jugador") or "", "usuario": r.get("usuario") or "", "telefono": str(r.get("telefono") or ""),
                                 "precio": int(r.get("precio") or 0), "pagado": pag, "medio": str(r.get("medio_pago") or ""), "fecha": fr, "ini": h,
                                 "fin": str(r.get("hora_fin") or fin), "web": rid.startswith("web_")}
                filas_html += (f"<td class='res{' pasado' if pasado else ''}' data-t='res' data-rid='{e(rid)}'{base}><div class='oc{'' if pag else ' ef'}' title='{e(r.get('usuario') or '')}'>{e((r.get('jugador') or r.get('usuario') or 'Reserva').split(' ')[0])}"
                               f"<small>{'pagada' if pag else 'cobrar en cancha'}</small></div></td>")
            elif (c["id"], fr, h) in bloq:
                filas_html += f"<td class='bloq{' pasado' if pasado else ''}' data-t='bloq'{base}><div class='bl'>Bloqueado</div></td>"
            elif pasado:
                filas_html += "<td class='pasado'></td>"
            else:
                filas_html += f"<td class='libre' data-t='libre'{base}><div class='li'><small>{e(sim)} {precio}</small></div></td>"
        filas_html += "</tr>"
    # Clientes recientes (para no tipear: mismo criterio que el selector del app).
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
    ant, sig = (ini - timedelta(days=7)).isoformat(), (ini + timedelta(days=7)).isoformat()
    ops_cli = "".join(f"<option value='{e(k)}'>{e(v['nombre'])}{(' · ' + e(v['email'])) if v['email'] else ''}</option>" for k, v in list(clientes.items())[:80])
    cfg = {"cancha": c["id"], "nombre": c["nombre"], "moneda": sim, "clientes": clientes, "pro": _pro_ok(ses["email"])}
    modal = f"""
<div class='modal' id='modalCal' role='dialog' aria-modal='true'><div class='modal-caja' style='max-width:520px'>
 <div class='modal-cab'><button type='button' class='cerrar' id='calCerrar' aria-label='Cerrar'>✕</button><h3 id='calTit'>Turno</h3></div>
 <div class='modal-cuerpo' style='padding:18px 24px'>
  <p class='sub' id='calSub' style='margin:0 0 14px'></p>
  <div id='calLibre' hidden>
   <div class='chips' id='calAcc'><button type='button' class='chip sel' data-acc='manual'>📝 Reserva manual</button><button type='button' class='chip' data-acc='bloq'>⛔ Bloquear turno</button></div>
   <div id='calManual' style='margin-top:14px'>
    <label for='mCli' style='margin-top:0'>Cliente reciente <span class='req'>opcional</span></label><select id='mCli'><option value=''>Elegir de tus clientes…</option>{ops_cli}</select>
    <label for='mNom'>Nombre del cliente</label><input id='mNom' maxlength='80' placeholder='Ej. Juan Pérez'>
    <div class='row'><div><label for='mTel'>Teléfono <span class='req'>opcional</span></label><input id='mTel' inputmode='tel' maxlength='20' placeholder='999 888 777'></div>
    <div><label for='mEm'>Correo de su cuenta <span class='req'>opcional</span></label><input id='mEm' type='email' maxlength='120' placeholder='para que la vea en su app'></div></div>
    <label for='mPre'>Precio</label><div class='inp-moneda'><span>{e(sim)}</span><input id='mPre' type='number' min='0' step='0.5' inputmode='decimal'></div>
    <label class='chk' style='margin-top:14px'><input type='checkbox' id='mPag'> Ya pagó <small>(si no, queda "por cobrar" en tu caja)</small></label>
    <p class='sub' style='font-size:12.5px;margin-top:10px'>Cliente propio: sin comisión. No entra a tu billetera Pichangol, sí a tu caja del día.</p>
   </div>
   <div id='calBloq' hidden style='margin-top:14px'><p class='sub' style='margin:0'>El turno deja de aparecer libre en la app y en la web (mantenimiento, uso propio, clases…). Puedes desbloquearlo cuando quieras.</p></div>
  </div>
  <div id='calBloqueado' hidden><p class='sub' style='margin:0'>Este turno está bloqueado: nadie puede reservarlo.</p></div>
  <div id='calRes' hidden>
   <div class='quien' style='margin-top:0'><span class='av' id='rAv'>?</span><div style='min-width:0'><b id='rNom'></b><div class='sub' id='rDet' style='margin:0;font-size:12.5px'></div></div><b id='rPre' style='margin-left:auto;white-space:nowrap'></b></div>
   <div id='rEstado' style='margin-top:12px'></div>
   <div class='acciones' id='rAcc' style='margin-top:12px'></div>
  </div>
  <div class='estado bad' id='calErr' style='display:none;margin-top:12px'></div>
 </div>
 <div class='modal-pie'><button type='button' class='limpiar' id='calNo'>Cerrar</button><button type='button' class='btn' id='calSi'>Guardar</button></div>
</div></div>"""
    cuerpo = (
        "<h1 class='anf-hola'>Calendario</h1><p class='sub'>Semana por cancha: verde = reserva pagada, ámbar = cobrar en la cancha, gris = bloqueado. "
        "<b>Toca un turno</b> para registrar una reserva manual, bloquearlo o marcar el pago.</p>"
        f"<div class='chips' style='margin-top:12px'>{chips}</div>"
        f"<div class='cal-nav2'><a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}&desde={ant}'>‹ Semana anterior</a>"
        f"<a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}&desde={hoy.isoformat()}'>Hoy</a>"
        f"<a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}&desde={sig}'>Semana siguiente ›</a>"
        f"<span class='sub' style='margin:0 0 0 auto'>{e(c['nombre'])} · {e(c['hora_apertura'])}–{e(c['hora_cierre'])} · turnos de {c['duracion_slot_min']} min</span></div>"
        f"<div class='cal-sem cal-act'><table><thead><tr><th></th>{cab}</tr></thead><tbody>{filas_html}</tbody></table></div>"
        + ("" if cfg["pro"] else "<p class='aviso warn' style='margin-top:12px'>📝 La reserva manual y el bloqueo de horas son parte de <b>Pichangol Pro</b>. Actívalo en la app (Perfil → Hazte Pro).</p>")
        + modal
        + f"<script>var CAL={json.dumps(cfg, ensure_ascii=False)};var RES={json.dumps(res_json, ensure_ascii=False)};</script><script>{_JS_CAL}</script>")
    return ui.shell("Calendario", cuerpo, nav=_cabecera("calendario", ses), sesion=ses, ancho=True, titulo_tab="Calendario · Modo anfitrión")


_JS_CAL = r"""
(function(){
var M=document.getElementById('modalCal'), cel=null, modo='', acc='manual';
function $(id){return document.getElementById(id)}
function err(t){var el=$('calErr');el.style.display=t?'block':'none';el.textContent=t||''}
function fechaTxt(iso){var d=new Date(iso+'T12:00:00');return d.toLocaleDateString('es-PE',{weekday:'short',day:'numeric',month:'short'})}
function abrir(td){cel=td;modo=td.dataset.t;err('');['calLibre','calBloqueado','calRes'].forEach(function(k){$(k).hidden=true});
  $('calSub').textContent=CAL.nombre+' · '+fechaTxt(td.dataset.f)+' · '+td.dataset.h+'–'+td.dataset.fin;
  var si=$('calSi');si.hidden=false;si.disabled=false;
  if(modo==='libre'){$('calTit').textContent='Turno libre';$('calLibre').hidden=false;setAcc('manual');$('mCli').value='';$('mNom').value='';$('mTel').value='';$('mEm').value='';$('mPre').value=td.dataset.p;$('mPag').checked=false;
    if(!CAL.pro){$('calLibre').hidden=true;si.hidden=true;err('La reserva manual y el bloqueo de horas son parte de Pichangol Pro. Actívalo en la app.')}}
  else if(modo==='bloq'){$('calTit').textContent='Turno bloqueado';$('calBloqueado').hidden=false;si.textContent='Desbloquear'}
  else{var r=RES[td.dataset.rid];$('calTit').textContent='Reserva';$('calRes').hidden=false;si.hidden=true;
    $('rAv').textContent=(r.jugador||r.usuario||'?').charAt(0).toUpperCase();$('rNom').textContent=r.jugador||r.usuario||'Reserva';
    $('rDet').textContent=[r.usuario,r.telefono,r.web?'reserva web':(r.medio==='manual'?'reserva manual':'')].filter(Boolean).join(' · ');
    $('rPre').textContent=CAL.moneda+' '+r.precio.toFixed(2);
    var online=r.pagado&&(r.medio==='yape'||r.medio==='tarjeta');
    $('rEstado').innerHTML=online?"<span class='pill ok'>Pagada en línea · "+r.medio+"</span>":(r.pagado?"<span class='pill ok'>Cobrada</span>":"<span class='pill warn'>Cobrar en la cancha</span>");
    var a='';if(r.telefono)a+="<a class='btn sec' href='https://wa.me/"+r.telefono.replace(/\D/g,'')+"' target='_blank' rel='noopener'>💬 WhatsApp</a>";
    if(!r.pagado)a+="<button type='button' class='btn' data-pagar='"+r.id+"' data-v='1'>✅ Marcar pagada</button>";else if(!online)a+="<button type='button' class='btn sec' data-pagar='"+r.id+"' data-v='0'>↩ Marcar por cobrar</button>";
    if(r.medio==='manual'&&!td.classList.contains('pasado'))a+="<button type='button' class='btn sec' id='rQuitar' style='color:var(--rojo)'>🗑 Quitar reserva</button>";
    $('rAcc').innerHTML=a}
  M.classList.add('open')}
function cerrar(){M.classList.remove('open');cel=null}
function setAcc(k){acc=k;document.querySelectorAll('#calAcc .chip').forEach(function(b){b.classList.toggle('sel',b.dataset.acc===k)});$('calManual').hidden=k!=='manual';$('calBloq').hidden=k!=='bloq';$('calSi').textContent=k==='manual'?'Registrar reserva':'Bloquear turno'}
window.alPagar=function(id,v){var r=RES[id];if(!r)return;r.pagado=v;var td=document.querySelector("td[data-rid='"+id+"']");if(td){var oc=td.querySelector('.oc');if(oc){oc.classList.toggle('ef',!v);oc.querySelector('small').textContent=v?'pagada':'cobrar en cancha'}}if(cel&&cel.dataset.rid===id)abrir(cel)};
document.querySelector('.cal-act').addEventListener('click',function(ev){var td=ev.target.closest('td[data-t]');if(!td||(td.dataset.t!=='res'&&td.classList.contains('pasado')))return;abrir(td)});
$('calAcc').addEventListener('click',function(ev){var b=ev.target.closest('[data-acc]');if(b)setAcc(b.dataset.acc)});
$('mCli').addEventListener('change',function(){var c=CAL.clientes[this.value];if(!c)return;$('mNom').value=c.nombre;$('mTel').value=c.telefono||'';$('mEm').value=c.email||''});
$('calCerrar').addEventListener('click',cerrar);$('calNo').addEventListener('click',cerrar);M.addEventListener('click',function(ev){if(ev.target===M)cerrar()});
document.addEventListener('keydown',function(ev){if(ev.key==='Escape')cerrar()});
async function post(url,body){var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json()}
$('calSi').addEventListener('click',async function(){if(!cel)return;var b=this;b.disabled=true;err('');
  try{var j;
    if(modo==='bloq')j=await post('/anfitrion/bloqueo',{cancha_id:CAL.cancha,fecha:cel.dataset.f,hora:cel.dataset.h,bloquear:false});
    else if(acc==='bloq')j=await post('/anfitrion/bloqueo',{cancha_id:CAL.cancha,fecha:cel.dataset.f,hora:cel.dataset.h,bloquear:true});
    else j=await post('/anfitrion/reserva-manual',{cancha_id:CAL.cancha,fecha:cel.dataset.b,hora:cel.dataset.h,nombre:$('mNom').value,telefono:$('mTel').value,email:$('mEm').value,precio:parseFloat($('mPre').value),pagado:$('mPag').checked});
    if(j.ok){location.reload();return} err(j.mensaje||j.error||'No se pudo guardar.')}
  catch(e){err('No se pudo guardar. Revisa tu conexión.')} b.disabled=false});
document.addEventListener('click',async function(ev){var q=ev.target.closest('#rQuitar');if(!q||!cel)return;if(!confirm('¿Quitar esta reserva manual? El turno vuelve a quedar libre.'))return;q.disabled=true;
  try{var j=await post('/anfitrion/reserva/'+encodeURIComponent(cel.dataset.rid)+'/quitar',{});if(j.ok){location.reload();return}err(j.error||'No se pudo quitar.')}catch(e){err('No se pudo quitar.')}q.disabled=false});
})();
""" + JS_PAGAR


def _canchas_sesion(request: Request):
    """(sesión, canchas del dueño) para los endpoints JSON del calendario; None
    en ses = sin sesión."""
    ses = sesion.de_request(request)
    if not ses:
        return None, []
    return ses, datos.canchas_de_dueno(ses["email"])


@router.post("/anfitrion/bloqueo")
async def bloquear_turno(request: Request) -> JSONResponse:
    ses, canchas = _canchas_sesion(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    if not _pro_ok(ses["email"]):
        return JSONResponse(_RESP_PRO, status_code=402)
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    c = next((x for x in canchas if x["id"] == str(b.get("cancha_id") or "")), None)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    fecha, hora = str(b.get("fecha") or ""), str(b.get("hora") or "")
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Fecha inválida."}, status_code=400)
    if hora not in horarios.slots(c["hora_apertura"], c["hora_cierre"], c["duracion_slot_min"]):
        return JSONResponse({"ok": False, "error": "Ese turno no existe en el horario de la cancha."}, status_code=400)
    bloquear = bool(b.get("bloquear", True))
    if bloquear and (fecha, hora) in datos.ocupados(c["id"], [fecha]):
        return JSONResponse({"ok": False, "error": "Ese turno ya tiene una reserva."}, status_code=409)
    if not datos.bloquear(c["id"], fecha, hora, bloquear):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento."}, status_code=503)
    print(f"[bloqueo-web] {ses['email']} {'bloqueó' if bloquear else 'desbloqueó'} {c['id']} {fecha} {hora}", flush=True)
    return JSONResponse({"ok": True})


@router.post("/anfitrion/reserva-manual")
async def reserva_manual(request: Request) -> JSONResponse:
    """Reserva MANUAL del dueño desde la web = la misma fila que crea el app
    (`agregarReservaManual`): confirmada, `traida_por_app=false` (cliente
    propio, sin comisión), `medio_pago='manual'`, fecha REAL del slot."""
    ses, canchas = _canchas_sesion(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    if not _pro_ok(ses["email"]):
        return JSONResponse(_RESP_PRO, status_code=402)
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    c = next((x for x in canchas if x["id"] == str(b.get("cancha_id") or "")), None)
    if c is None:
        return JSONResponse({"ok": False, "error": "Esta cancha no está a tu nombre."}, status_code=404)
    base, hora = str(b.get("fecha") or ""), str(b.get("hora") or "")
    try:
        date.fromisoformat(base)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Fecha inválida."}, status_code=400)
    paso = c["duracion_slot_min"]
    if hora not in horarios.slots(c["hora_apertura"], c["hora_cierre"], paso):
        return JSONResponse({"ok": False, "error": "Ese turno no existe en el horario de la cancha."}, status_code=400)
    fr = horarios.fecha_real(base, c["hora_apertura"], c["hora_cierre"], hora)
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
    ph = horarios.precio_hora_en(c["precio_hora"], hora, c["descuento_valle"], c.get("valle_desde"), c.get("valle_hasta"))
    sugerido = horarios.precio_slot(ph, paso, desc.get((fr, hora), 0))
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
    print(f"[manual-web] {ses['email']} registró {fila['id']} en {c['id']} {fr} {hora} · {sim} {precio} · pagado={fila['pagado']}", flush=True)
    return JSONResponse({"ok": True, "id": fila["id"], "precio": precio})


@router.post("/anfitrion/reserva/{res_id}/pagado")
async def marcar_pagado_web(request: Request, res_id: str) -> JSONResponse:
    """Marcar cobrada (efectivo) / volver a "por cobrar": igual que `marcarPago`
    del app, con el push "¡Te llegaron puntos! ⭐" al jugador en la
    transición no pagado → pagado de reservas traídas por la app."""
    ses, canchas = _canchas_sesion(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    ids = [x["id"] for x in canchas]
    try:
        b = await request.json()
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
                          f"El local confirmó tu pago: +{pts} puntos Pichangol por tu reserva en {lugar}. Canjéalos como descuento en tu próxima reserva online.",
                          "puntos")
    print(f"[pago-web] {ses['email']} marcó {res_id} pagado={pagado}", flush=True)
    return JSONResponse({"ok": True, "pagado": pagado})


@router.post("/anfitrion/reserva/{res_id}/quitar")
async def quitar_reserva_manual(request: Request, res_id: str) -> JSONResponse:
    ses, canchas = _canchas_sesion(request)
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
    usuario = str(r.get("usuario") or "").strip().lower()
    if usuario:
        from pagos import router as pr
        c = next((x for x in canchas if x["id"] == r.get("cancha_id")), None)
        lugar = ((c or {}).get("club") or "").strip() or (c or {}).get("nombre") or "la cancha"
        _en_segundo_plano(pr._aviso_push_usuario, usuario, "Reserva cancelada 📅",
                          f"El local quitó tu reserva en {lugar} del {horarios.fecha_larga(str(r.get('fecha')))} {r.get('hora_inicio')}. Si tienes dudas, escríbele.",
                          "reserva_manual")
    print(f"[manual-web] {ses['email']} quitó {res_id}", flush=True)
    return JSONResponse({"ok": True})


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
    # Como "Mis canchas" del app (`_LocalCard`): UNA tarjeta por LOCAL (club)
    # con el nombre del local de título y sus canchas como filas. Antes salía
    # una tarjeta por cancha con el nombre de la cancha grande y el local
    # chico, y el director leyó "Cancha-01" como si fuera el nombre del local.
    locales: dict[str, list[dict]] = {}
    for c in canchas:
        locales.setdefault((c.get("club") or "").strip() or c["nombre"], []).append(c)
    tarjetas = ""
    for local, lst in locales.items():
        c0 = lst[0]
        fs = next((f for c in lst for f in _fotos(c)), None)
        foto = f"<img src='{e(fs)}' alt=''>" if fs else _deporte(c0.get("deporte"))[1]
        zona = _zona(c0)
        n = len(lst)
        todas_ok = all(datos.reservable(c) for c in lst)
        pill = "<span class='pill ok'>✓ Verificado</span>" if todas_ok else ""
        filas = ""
        for c in lst:
            sim, _ = _moneda_de(c)
            ok = datos.reservable(c)
            deps = " · ".join(_deporte(d)[0] for d in _deportes_de(c)[:3])
            filas += (
                f"<div class='anf-fila'><span class='ico'>{_deporte(c.get('deporte'))[1]}</span><div style='flex:1;min-width:0'>"
                f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><b>{e(c['nombre'])}</b>"
                + ("<span class='pill ok' style='font-size:11px'>✓ Verificada</span>" if ok else "<span class='pill warn' style='font-size:11px'>Aún sin verificar</span>") + "</div>"
                f"<div class='sub' style='margin:2px 0 0'>{e(deps)} · {e(c['hora_apertura'])}–{e(c['hora_cierre'])} · {c['duracion_slot_min']} min · <b>{e(sim)} {c['precio_hora']:.2f}</b>/h</div>"
                "<div class='acciones' style='margin-top:8px'>"
                f"<a class='btn sec' href='/reservar/{e(c['id'])}'>Ver ficha pública</a>"
                f"<a class='btn sec' href='/anfitrion/calendario?cancha={e(c['id'])}'>Calendario</a>"
                f"<a class='btn' href='/anfitrion/cancha/{e(c['id'])}/editar'>✏️ Editar</a>"
                "</div></div></div>")
        tarjetas += (
            f"<div class='anf-local'><div class='cab'><div class='f'>{foto}</div><div style='flex:1;min-width:0'>"
            f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><span class='tit'><span class='ico'>{ui.LOCAL_SVG}</span><b style='font-size:17px'>{e(local)}</b></span>{pill}</div>"
            f"<div class='sub' style='margin:2px 0 0'>{e(c0.get('direccion') or '')}{(' · ' if c0.get('direccion') and zona else '')}{e(zona)}</div>"
            f"<div class='sub' style='margin:2px 0 0'>{n} {'cancha' if n == 1 else 'canchas'}</div></div></div>"
            f"<div class='filas'>{filas}</div>"
            "<div class='acciones' style='margin-top:10px'>"
            f"<a class='btn sec' href='/anfitrion/cancha/{e(c0['id'])}/agregar'>＋ Agregar cancha a este local</a>"
            f"<a class='btn sec' href='{_maps(c0)}' target='_blank' rel='noopener'>📍 Mapa</a>"
            "</div></div>")
    guardada = next((c for c in canchas if c["id"] == guardado), None) if guardado else None
    aviso = (f"<div class='aviso ok' style='margin:16px 0 0'>✅ Guardamos los cambios de <b>{e(guardada['nombre'])}</b>. "
             "Ya se ven en la ficha pública y en la app.</div>") if guardada else ""
    registrada = next((c for c in canchas if c["id"] == request.query_params.get("registrada")), None)
    if registrada:
        aviso = (f"<div class='aviso ok' style='margin:16px 0 0'>✅ Registramos <b>{e(registrada.get('club') or registrada['nombre'])}</b>. "
                 "Queda en verificación: te avisamos por WhatsApp y en la app cuando esté activa. Mientras tanto puedes completar fotos, hora feliz y servicios.</div>")
    agregada = next((c for c in canchas if c["id"] == request.query_params.get("agregada")), None)
    if agregada:
        aviso = (f"<div class='aviso ok' style='margin:16px 0 0'>✅ Agregamos <b>{e(agregada['nombre'])}</b> a <b>{e(agregada.get('club') or '')}</b>. "
                 + ("Ya está activa y recibe reservas: el local ya estaba verificado." if datos.reservable(agregada)
                    else "Se activará junto con el local cuando aprobemos la verificación.") + "</div>")
    cuerpo = ("<h1 class='anf-hola'>Mis canchas</h1><p class='sub'>Tus locales en Pichangol, con sus canchas. Edita precio, horario, fotos y servicios aquí o en la app: es la misma cancha.</p>"
              f"{aviso}{_aviso_verificacion(canchas, ses['email'])}"
              f"<div class='anf-grid' style='grid-template-columns:repeat(auto-fill,minmax(420px,1fr));margin-top:16px'>{tarjetas}</div>"
              "<p style='margin-top:20px'><a class='btn' href='/anfitrion/nueva'>＋ Registrar otro local</a></p>")
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
    # Servicios extra = CATÁLOGO GLOBAL de la torre (`servicios_extra.py`),
    # agrupado en "Del local" (se propaga a todas las canchas del local) y
    # "De esta cancha". Los que la cancha ya tiene pero salieron del catálogo
    # se muestran igual, para poder quitarlos o mantener su precio.
    actuales = {str(s.get("clave")): _se.completar(s) for s in (c.get("servicios_extra") or []) if s.get("clave")}
    cat = _se.catalogo()
    conocidas = {x["clave"] for x in cat}
    fuera = [v for k, v in actuales.items() if k not in conocidas]
    filas_serv = ""
    for amb, tit, ayuda in (("local", "Del local", "Se aplican a TODAS las canchas de este local (piscina, sauna, entrada general…). Al guardar se copian a las demás canchas del local."),
                            ("cancha", "De esta cancha", "Solo de esta cancha (árbitro, petos, clase con entrenador…).")):
        items = [x for x in cat if x["ambito"] == amb] + [x for x in fuera if x.get("ambito") == amb]
        filas_serv += f"<h3 style='font-size:14px;margin:14px 0 2px'>{tit}</h3><p class='sub' style='margin:0 0 6px;font-size:12.5px'>{ayuda}</p>"
        for x in items:
            k = x["clave"]
            on = k in actuales
            precio_txt = f"{float(actuales[k]['precio']):.2f}" if on else ""
            filas_serv += (f"<div class='serv{' sel' if on else ''}' data-serv='{e(k)}' data-ambito='{amb}'>"
                           f"<button type='button' class='chip{' sel' if on else ''}' data-g='servicios' data-v='{e(k)}'>{x['emoji']} {e(x['nombre'])}</button>"
                           f"<span class='sub' style='margin:0;font-size:12px'>{_se.etiqueta_tipo(x['tipo'])}</span>"
                           f"<label class='precio-serv'{'' if on else ' hidden'}><span>{e(sim)}</span>"
                           f"<input type='number' name='serv_{e(k)}' min='0.5' step='0.5' inputmode='decimal' value='{precio_txt}' placeholder='Precio'></label></div>")
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
 <section class='panel edit-sec' id='sec-extras'><h2>Servicios extra</h2><p class='sub'>De pago: el jugador los agrega al reservar y suman al total. Por reserva, por persona (el jugador elige cuántas) o por turno.</p>
  <div class='servs'>{filas_serv}</div>
  <div style='margin-top:18px;padding-top:14px;border-top:1px solid var(--linea,#E4E4E4)'>
   <label for='sugTxt'>¿Tu local ofrece algo que no está en la lista? <span class='req'>lo revisa el equipo de Pichangol y lo agrega al catálogo</span></label>
   <div class='acciones' style='align-items:center'><input id='sugTxt' maxlength='120' placeholder='Ej. Frontón, clases de natación, cochera techada' style='flex:1;min-width:220px'><button type='button' class='btn sec' id='btnSug'>💡 Sugerir</button></div>
   <span class='sub' id='sugMsg' style='margin:4px 0 0'></span>
  </div>
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
$('btnSug').addEventListener('click',async function(){var t=$('sugTxt').value.trim(),m=$('sugMsg');if(t.length<3){m.textContent='Cuéntanos qué servicio ofrece tu local.';return}
  try{var r=await fetch('/anfitrion/servicios/sugerir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texto:t,cancha_id:CFG.id})});var j=await r.json();m.textContent=j.ok?'✅ ¡Gracias! Lo revisamos y te avisamos cuando esté disponible.':(j.error||'No se pudo enviar.');if(j.ok)$('sugTxt').value=''}catch(e){m.textContent='No se pudo enviar. Revisa tu conexión.'}});
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
    """El dueño sugiere un servicio que no está en el catálogo; lo atiende el
    operador en la torre (Comunicación → Servicios extra). Texto libre SOLO
    hacia el equipo: nunca se publica."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        body = await request.json()
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
        _en_segundo_plano(lambda: [almacen.borrar_foto(u) for u in quitadas])
    _propagar_servicios_local(ses["email"], cancha_id, campos.get("club") or c.get("club") or "", campos.get("servicios_extra") or [])
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


@router.get("/anfitrion/nueva", response_class=HTMLResponse)
def pagina_nueva_cancha(request: Request, nombre: str = "", direccion: str = "", lat: str = "", lng: str = "", place: str = "",
                        deporte: str = "", cancha: str = "") -> HTMLResponse:
    """Formulario "Pon tu cancha" (calcado del alta de anuncio de Airbnb, en una
    sola página con secciones). Llega vacío o PRELLENADO desde una cancha
    descubierta en Google ("¿Es tuya? Reclámala": nombre, dirección, punto)."""
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
               "precio": f"{existente['precio_hora']:.2f}" if existente.get("precio_hora") else "", "apertura": existente.get("hora_apertura") or "07:00",
               "cierre": existente.get("hora_cierre") or "23:00", "dur": int(existente.get("duracion_slot_min") or 60),
               "nombre_cancha": existente.get("nombre") or "", "zona": existente.get("barrio") or ""}
    elif deporte in catalogos.DEPORTES_ACTIVOS:
        pre["deportes"] = [deporte]
    iso = paises.pais_de_coordenadas(la, ln) if la is not None else "PE"
    nuevo_id = existente["id"] if existente else f"u{int(time.time() * 1000)}"
    dep_ops = [(d, f"{_deporte(d)[1]} {_deporte(d)[0]}") for d in catalogos.DEPORTES_ACTIVOS]
    cfg = {"id": nuevo_id, "existente": bool(existente), "pre": pre, "lat": la, "lng": ln, "iso": iso, "place": place[:120], "superficies": catalogos.SUPERFICIES,
           "activos": catalogos.DEPORTES_ACTIVOS, "nombres": {d: _deporte(d)[0] for d in catalogos.DEPORTES_ACTIVOS},
           "maxFotos": catalogos.MAX_FOTOS, "storage": almacen.disponible(), "tel": catalogos.TEL_PREFIJO,
           "telLen": catalogos.TEL_LONGITUD, "labels": catalogos.GEO_LABELS, "doc": DOC_NOMBRE, "docLen": DOC_LONGITUD,
           "monedas": {k: paises.simbolo_de_moneda(v) for k, v in paises.MONEDA_POR_PAIS.items()}}
    secciones = [("local", "Tu local"), ("deportes", "Deportes y piso"), ("precio", "Precio y horario"), ("fotos", "Fotos"), ("dueno", "Verificación")]
    nav = "".join(f"<a href='#sec-{k}' class='edit-nav-it'>{n}</a>" for k, n in secciones)
    cuerpo = f"""
<div class='edit-top'><a class='volver-lnk' href='/anfitrion'>‹ Modo anfitrión</a>
<h1 class='anf-hola' style='margin-top:8px'>{'Reclama tu cancha' if existente else 'Pon tu cancha en Pichangol'}</h1><p class='sub'>{'Esta cancha ya está en Pichangol pero nadie la administra. Completa los datos y confirmamos que es tuya antes de activarla.' if existente else 'Publícala y empieza a recibir reservas. Confirmamos que eres el dueño antes de activarla (WhatsApp o visita), igual que en la app.'}</p></div>
<div class='edit-grid'><nav class='edit-nav'>{nav}</nav>
<form id='fNueva' class='edit-form' autocomplete='off' novalidate>
 <section class='panel edit-sec' id='sec-local'><h2>Tu local</h2>
  {"" if existente or not config.PLACES_API_KEY else "<label for='busca'>🔎 Busca tu local en Google Maps <span class='req'>rellena nombre, dirección y ubicación</span></label><input id='busca' maxlength='80' placeholder='Ej. Campo deportivo Edu Jr.' autocomplete='off'><div id='resBusca' class='res-busca' hidden></div>"}
  <label for='local'>Nombre del local / club</label><input id='local' maxlength='{catalogos.NOMBRE_MAX}' value='{e(nombre[:catalogos.NOMBRE_MAX])}' placeholder='Ej. Complejo Deportivo Los Olivos'>
  <label for='direccion'>Dirección <span class='req'>opcional</span></label><input id='direccion' maxlength='160' value='{e(direccion[:160])}' placeholder='Av. Aviación 1234, San Borja'>
  <label>Ubicación exacta <span class='req'>obligatoria: de aquí salen el país, la moneda y la distancia para los jugadores</span></label>
  <div id='mapaSede' class='mapa-sede' style='margin-top:6px'></div>
  <div class='acciones' style='margin-top:8px'><button type='button' class='btn sec' id='btnUbic'>📍 Usar mi ubicación</button><span class='sub' id='ubicTxt' style='margin:0'>{'Toca el mapa para fijar tu cancha.' if la is None else f'{la:.5f}, {ln:.5f}'}</span></div>
  <label>Zona</label>
  <div class='row' id='geoRow' style='grid-template-columns:1fr 1fr 1fr'><select id='g1'><option value=''>—</option></select><select id='g2'><option value=''>—</option></select><select id='g3'><option value=''>—</option></select></div>
 </section>
 <section class='panel edit-sec' id='sec-deportes'><h2>Deportes y tipo de piso</h2><p class='sub'>Marca todo lo que se juega en tu local.</p>
  {_chips('deportes', dep_ops, set(pre['deportes']), multi=True)}
  <div id='modoWrap' hidden><label style='margin-top:18px'>¿Cómo son tus canchas?</label>
   {_chips('modo', [('unica', '🏟️ Una sola loza multiuso (una agenda)'), ('separadas', '🏟️🏟️ Canchas separadas (una por deporte)')], 'separadas')}</div>
  <label style='margin-top:18px'>Tipo de piso <span class='req'>obligatorio</span></label>
  <div id='supWrap'><p class='sub'>Marca primero un deporte.</p></div>
  <label for='nombreCancha' style='margin-top:18px'>Nombre de la cancha <span class='req'>opcional</span></label><input id='nombreCancha' maxlength='{catalogos.NOMBRE_MAX}' value='{e(pre['nombre_cancha'])}' placeholder='Ej. Cancha 1 · Grass'>
 </section>
 <section class='panel edit-sec' id='sec-precio'><h2>Precio y horario</h2>
  <label for='precio'>Precio por hora</label>
  <div class='inp-moneda'><span id='monSpan'>{e(paises.simbolo_de_moneda(paises.moneda_de_pais(iso)))}</span><input id='precio' type='number' min='1' step='0.01' inputmode='decimal' value='{pre['precio']}' placeholder='120.00'></div>
  <div class='row' style='margin-top:14px'><div><label for='hora_apertura'>Abre</label>{_select_hora('hora_apertura', pre['apertura'])}</div>
  <div><label for='hora_cierre'>Cierra</label>{_select_hora('hora_cierre', pre['cierre'])}</div></div>
  <p class='sub' style='font-size:13px'>La hora de cierre es la hora en que <b>empieza el último turno</b>: si cierras a las 23:00, el último turno es 23:00–00:00. Un cierre menor o igual a la apertura cae al día siguiente.</p>
  <label style='margin-top:14px'>Duración del turno</label>
  {_chips('duracion_slot_min', catalogos.DURACIONES, pre['dur'] if pre['dur'] in catalogos.DURACIONES else 60, fmt=catalogos.etiqueta_duracion)}
  <p class='sub' style='font-size:12.5px'>Hora feliz, seña, servicios del local y servicios extra los configuras después en Editar cancha.</p>
 </section>
 <section class='panel edit-sec' id='sec-fotos'><h2>Fotos</h2><p class='sub'>La primera es la portada. Hasta {catalogos.MAX_FOTOS}. Puedes agregarlas después.</p>
  <div class='edit-fotos' id='fotos'></div>
  <div class='acciones' style='margin-top:12px'><label class='btn sec' for='inFotos'>📷 Agregar fotos</label><input type='file' id='inFotos' accept='image/*' multiple hidden{'' if almacen.disponible() else ' disabled'}>
  <span class='sub' id='fotosMsg' style='margin:0'>{'' if almacen.disponible() else 'La subida de fotos no está disponible en este ambiente; súbelas desde la app.'}</span></div>
 </section>
 <section class='panel edit-sec' id='sec-dueno'><h2>Verificación de propiedad</h2><p class='sub'>Existir no es ser dueño: con estos datos el equipo de Pichangol confirma que la cancha es tuya antes de activarla. No se publican.</p>
  <label for='wa'>WhatsApp del local o del dueño <span class='req'>obligatorio</span></label><div class='inp-moneda' style='max-width:300px'><span id='telPre'>+{catalogos.TEL_PREFIJO.get(iso, '51')}</span><input id='wa' inputmode='tel' maxlength='15' placeholder='999 888 777'></div>
  <label style='margin-top:14px'>Tu relación con el local</label>{_chips('relacion', RELACIONES, 'dueno')}
  <label for='doc' style='margin-top:14px'><span id='docNombre'>{DOC_NOMBRE.get(iso, 'Documento')}</span> del titular <span class='req'>opcional, ayuda a aprobar más rápido</span></label><input id='doc' inputmode='numeric' maxlength='12' style='max-width:220px' placeholder='Solo números'>
  <label for='nota' style='margin-top:14px'>Algo que debamos saber <span class='req'>opcional</span></label><input id='nota' maxlength='200' placeholder='Ej. El local está a nombre de mi socio, yo lo administro.'>
  <label style='margin-top:14px'>Prueba de propiedad <span class='req'>opcional: recibo de luz, licencia, contrato</span></label>
  <div class='acciones'><label class='btn sec' for='inEvid'>📎 Subir foto</label><input type='file' id='inEvid' accept='image/*' hidden{'' if almacen.disponible() else ' disabled'}><span class='sub' id='evidMsg' style='margin:0'></span></div>
 </section>
</form></div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>Al enviar, tu cancha queda <b>en verificación</b> y te avisamos por WhatsApp y en la app cuando esté activa.</span>
<button type='button' class='btn' id='btnGuardar'>{'Reclamar mi cancha' if existente else 'Registrar mi cancha'}</button></div></div>
<script>var CFG={json.dumps(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{_JS_NUEVA}</script>"""
    return ui.shell("Pon tu cancha", cuerpo, nav=_cabecera("canchas", ses, tabs_visibles=False), sesion=ses, ancho=True,
                    extra_head=_LEAFLET, titulo_tab="Pon tu cancha · Pichangol")


_JS_NUEVA = r"""
(function(){
var fotos=[], evid='', dep=(CFG.pre.deportes||[]).slice(), sups={}, sup=CFG.pre.superficie||'', lat=CFG.lat, lng=CFG.lng, iso=CFG.iso, arbol=null, subiendo=0, mapa, marker, solLat=null, solLng=null;
dep.forEach(function(d){sups[d]=sup});
function $(id){return document.getElementById(id)}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}
function sel(g){var b=document.querySelector(".chip.sel[data-g='"+g+"']");return b?b.dataset.v:''}
function modo(){return dep.length>1?sel('modo'):'unica'}
function union(){var out=[];dep.forEach(function(d){(CFG.superficies[d]||[]).forEach(function(s){if(out.indexOf(s)<0)out.push(s)})});return out}
function chips(g,lista,val){return "<div class='chips' style='margin-top:6px'>"+lista.map(function(s){return "<button type='button' class='chip"+(s===val?' sel':'')+"' data-g='"+g+"' data-v='"+esc(s)+"'>"+esc(s)+"</button>"}).join('')+"</div>"}
function pintarSup(){var w=$('supWrap');if(!dep.length){w.innerHTML="<p class='sub'>Marca primero un deporte.</p>";return}
  if(modo()==='separadas'){w.innerHTML=dep.map(function(d){return "<div style='margin-top:8px'><b style='font-size:13px'>"+esc(CFG.nombres[d]||d)+"</b>"+chips('sup_'+d,CFG.superficies[d]||[],sups[d]||'')+"</div>"}).join('')}
  else{var u=union();if(u.indexOf(sup)<0)sup='';w.innerHTML=chips('sup',u,sup)}}
document.addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-g]');if(!b)return;var g=b.dataset.g,v=b.dataset.v;
  if(g==='deportes'){b.classList.toggle('sel');var i=dep.indexOf(v);if(i>=0)dep.splice(i,1);else dep.push(v);$('modoWrap').hidden=dep.length<2;pintarSup();return}
  b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');
  if(g==='modo'){pintarSup();return}if(g==='sup'){sup=v;return}if(g.indexOf('sup_')===0){sups[g.slice(4)]=v}});
// ── buscar el local en Google por nombre (rellena nombre, dirección, punto y place) ──
var place = CFG.place || '', tBusca = null, inBusca = $('busca');
if(inBusca){
  inBusca.addEventListener('input', function(){ clearTimeout(tBusca); var q = this.value.trim(), box = $('resBusca'); if(q.length < 3){ box.hidden = true; box.innerHTML = ''; return; }
    tBusca = setTimeout(function(){ var c = mapa ? mapa.getCenter() : null; var qs = '/web/lugares?q=' + encodeURIComponent(q) + (c ? '&lat=' + c.lat + '&lng=' + c.lng : '');
      fetch(qs).then(function(r){ return r.json(); }).then(function(j){ var l = j.lugares || []; box.hidden = false;
        box.innerHTML = l.length ? l.map(function(x){ return "<button type='button' class='res-it' data-id='" + esc(x.id) + "' data-nombre='" + esc(x.nombre) + "' data-dir='" + esc(x.direccion) + "' data-lat='" + x.lat + "' data-lng='" + x.lng + "' data-dep='" + esc(x.deporte) + "'><b>" + esc(x.nombre) + "</b><small>" + esc(x.direccion) + (x.km != null ? ' · a ' + x.km + ' km' : '') + "</small></button>"; }).join('')
          : "<div class='sub' style='padding:8px 12px'>No encontramos ese local en Google. Escribe el nombre abajo y marca el punto en el mapa.</div>"; }).catch(function(){ box.hidden = true; }); }, 400); });
  $('resBusca').addEventListener('click', function(ev){ var b = ev.target.closest('.res-it'); if(!b) return;
    $('local').value = b.dataset.nombre; $('direccion').value = b.dataset.dir; place = b.dataset.id; inBusca.value = b.dataset.nombre; $('resBusca').hidden = true;
    ponerPunto(parseFloat(b.dataset.lat), parseFloat(b.dataset.lng), true);
    if(!dep.length && b.dataset.dep && CFG.superficies[b.dataset.dep]){ var ch = document.querySelector(".chip[data-g='deportes'][data-v='" + b.dataset.dep + "']"); if(ch) ch.click(); } });
}
// ── mapa + país + zona (mismo patrón que Mi academia) ──
function paisDe(la,ln){var C={PE:[-18.4,-0.03,-81.4,-68.6],EC:[-5.1,1.7,-81.1,-75.1],BO:[-22.95,-9.6,-69.7,-57.4]};for(var k in C){var c=C[k];if(la>=c[0]&&la<=c[1]&&ln>=c[2]&&ln<=c[3])return k}return 'PE'}
function ponerPunto(la,ln,centrar){lat=la;lng=ln;$('ubicTxt').textContent=la.toFixed(5)+', '+ln.toFixed(5);if(mapa){if(marker)marker.setLatLng([la,ln]);else marker=L.marker([la,ln]).addTo(mapa);if(centrar)mapa.setView([la,ln],16)}
  var p=paisDe(la,ln);if(p!==iso||!arbol){iso=p;$('telPre').textContent='+'+CFG.tel[iso];$('monSpan').textContent=CFG.monedas[iso]||'S/';$('docNombre').textContent=CFG.doc[iso]||'Documento';cargarGeo()}}
if(window.L){var c0=lat!=null?[lat,lng]:{PE:[-12.05,-77.04],EC:[-2.17,-79.92],BO:[-16.5,-68.15]}[iso];mapa=L.map('mapaSede').setView(c0,lat!=null?16:11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(mapa);
  if(lat!=null)marker=L.marker([lat,lng]).addTo(mapa);mapa.on('click',function(ev){ponerPunto(ev.latlng.lat,ev.latlng.lng,false)});
  $('btnUbic').addEventListener('click',function(){if(!navigator.geolocation){pcgToast('Tu navegador no permite ubicación.');return}navigator.geolocation.getCurrentPosition(function(p){solLat=p.coords.latitude;solLng=p.coords.longitude;ponerPunto(p.coords.latitude,p.coords.longitude,true)},function(){pcgToast('No pudimos leer tu ubicación.')})})}
function opts(s,lista,val,ph){s.innerHTML="<option value=''>"+ph+"</option>"+lista.map(function(o){return "<option value='"+esc(o)+"'"+(o===val?' selected':'')+">"+esc(o)+"</option>"}).join('')}
function cargarGeo(){fetch('/web/geo/'+iso).then(function(r){return r.json()}).then(function(j){if(!j.ok)return;arbol=j.arbol;var lb=j.labels,pre=['','',''];
  if(CFG.pre.zona){for(var a in arbol){for(var b in arbol[a]){if(arbol[a][b].indexOf(CFG.pre.zona)>=0){pre=[a,b,CFG.pre.zona]}}}}
  opts($('g1'),Object.keys(arbol),pre[0],lb[0]);opts($('g2'),pre[0]?Object.keys(arbol[pre[0]]):[],pre[1],lb[1]);opts($('g3'),pre[1]?arbol[pre[0]][pre[1]]:[],pre[2],lb[2])}).catch(function(){})}
$('modoWrap').hidden=dep.length<2;pintarSup();
$('g1').addEventListener('change',function(){opts($('g2'),this.value?Object.keys(arbol[this.value]):[],'',CFG.labels[iso][1]);opts($('g3'),[],'',CFG.labels[iso][2])});
$('g2').addEventListener('change',function(){opts($('g3'),this.value?arbol[$('g1').value][this.value]:[],'',CFG.labels[iso][2])});
cargarGeo();
// GPS del que reclama (anti-fraude de la torre): se intenta en silencio, sin bloquear.
if(navigator.geolocation){try{navigator.geolocation.getCurrentPosition(function(p){solLat=p.coords.latitude;solLng=p.coords.longitude},function(){},{timeout:6000,maximumAge:300000})}catch(e){}}
// ── fotos y evidencia ──
function comprimir(file,M){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
async function subir(file,tipo){var blob=await comprimir(file,1600);var r=await fetch('/anfitrion/nueva/foto?id='+encodeURIComponent(CFG.id)+'&tipo='+tipo,{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});return r.json()}
function pintarFotos(){$('fotos').innerHTML=fotos.map(function(u,i){return "<div class='foto' data-url='"+esc(u)+"'><img src='"+esc(u)+"' alt=''><span class='portada'"+(i?' hidden':'')+">Portada</span><div class='acc'><button type='button' class='mini' data-acc='portada' title='Usar como portada'>★</button><button type='button' class='mini' data-acc='quitar' title='Quitar'>✕</button></div></div>"}).join('')}
document.addEventListener('click',function(ev){var a=ev.target.closest('.foto .mini');if(!a)return;var u=a.closest('.foto').dataset.url,i=fotos.indexOf(u);if(a.dataset.acc==='quitar'&&i>=0)fotos.splice(i,1);if(a.dataset.acc==='portada'&&i>0){fotos.splice(i,1);fotos.unshift(u)}pintarFotos()});
$('inFotos').addEventListener('change',async function(){var files=Array.prototype.slice.call(this.files||[]);this.value='';var msg=$('fotosMsg');
  for(var i=0;i<files.length;i++){if(fotos.length>=CFG.maxFotos){msg.textContent='Máximo '+CFG.maxFotos+' fotos.';break}subiendo++;msg.textContent='Subiendo foto '+(i+1)+' de '+files.length+'…';
    try{var j=await subir(files[i],'foto');if(j.ok){fotos.push(j.url);pintarFotos();msg.textContent=''}else msg.textContent=j.error||'No se pudo subir.'}catch(e){msg.textContent='No se pudo subir la foto.'}subiendo--}});
$('inEvid').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;subiendo++;$('evidMsg').textContent='Subiendo…';
  try{var j=await subir(f,'evidencia');if(j.ok){evid=j.url;$('evidMsg').textContent='✅ Prueba adjunta.'}else $('evidMsg').textContent=j.error||'No se pudo subir.'}catch(e){$('evidMsg').textContent='No se pudo subir.'}subiendo--});
// ── enviar ──
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo>0){msg.textContent='Espera a que terminen de subir las fotos.';return}
  var body={id:CFG.id,existente:CFG.existente,place:place,nombre_local:$('local').value,direccion:$('direccion').value,lat:lat,lng:lng,zona:$('g3').value,deportes:dep,modo:modo(),superficie:sup,superficies:sups,
    nombre_cancha:$('nombreCancha').value,precio_hora:parseFloat($('precio').value)||0,hora_apertura:$('hora_apertura').value,hora_cierre:$('hora_cierre').value,duracion_slot_min:+sel('duracion_slot_min')||60,
    fotos:fotos,whatsapp:$('wa').value,relacion:sel('relacion'),documento:$('doc').value,nota:$('nota').value,evidencia:evid,sol_lat:solLat,sol_lng:solLng};
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Registrando…';
  try{var r=await fetch('/anfitrion/nueva',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){location.href=j.url||'/anfitrion/canchas';return}msg.classList.add('err');msg.textContent=j.error||'No se pudo registrar.';if(j.campo){var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth'})}}
  catch(e){msg.classList.add('err');msg.textContent='No se pudo registrar. Revisa tu conexión.'}btn.disabled=false});
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
    try:
        precio = round(float(b.get("precio_hora")), 2)
    except (TypeError, ValueError):
        precio = 0
    if not (0 < precio <= 100000):
        return None, {}, "Pon el precio por hora.", "precio"
    ap, ci = str(b.get("hora_apertura") or "07:00"), str(b.get("hora_cierre") or "23:00")
    if not (_HORA_RE.match(ap) and _HORA_RE.match(ci)):
        return None, {}, "Hora no válida (usa horas en punto).", "precio"
    try:
        dur = int(b.get("duracion_slot_min") or 60)
    except (TypeError, ValueError):
        dur = 0
    if dur not in catalogos.DURACIONES:
        return None, {}, "Duración del turno no válida.", "precio"
    prefijo = almacen.prefijo_cancha(nuevo_id) if almacen.disponible() else None
    previas = set(_fotos(existente)) if existente else set()
    fotos = []
    for u in (b.get("fotos") or []):
        u = str(u).strip()
        if u and u not in fotos and (u in previas or (prefijo and u.startswith(prefijo))):
            fotos.append(u)
    if existente and not fotos:
        fotos = _fotos(existente)
    fotos = fotos[:catalogos.MAX_FOTOS]
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
    moneda = paises.simbolo_de_moneda(paises.moneda_de_pais(iso))
    nombre_cancha = re.sub(r"\s+", " ", str(b.get("nombre_cancha") or "")).strip()[:catalogos.NOMBRE_MAX]
    base = {"club": local, "distrito": "", "barrio": zona, "precio_hora": precio, "lat": la, "lng": ln, "club_fundador": False,
            "digitalizada": True, "direccion": direccion or None, "registrada": True, "foto_url": fotos[0] if fotos else None,
            "fotos": fotos, "dueno": email, "verificada": False, "hora_apertura": ap, "hora_cierre": ci, "duracion_slot_min": dur,
            "eliminada": False, "amenidades": [], "moneda": moneda, "servicios_extra": [], "descuento_valle": 0,
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
    """Crea la(s) cancha(s) en `pichangol_canchas` (sin verificar, a nombre
    del correo de la sesión) y el RECLAMO en el backend; la torre lo aprueba.
    Si el lugar ya tiene un reclamo ACTIVO de otra persona, no se registra."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        body = await request.json()
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
    return JSONResponse({"ok": True, "url": f"/anfitrion/canchas?registrada={filas[0]['id']}", "reclamo_id": r.get("reclamo_id"), "ids": [f["id"] for f in filas]})


@router.post("/anfitrion/nueva/foto")
async def subir_foto_nueva(request: Request, id: str = "", tipo: str = "foto") -> JSONResponse:
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
    cuerpo = await request.body()
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
    "rechazada": ("err", "No aprobada", "No pudimos confirmar la propiedad. Escríbenos por WhatsApp o vuelve a enviar la solicitud desde la app."),
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
    cfg = {"id": l["id"], "superficies": catalogos.SUPERFICIES, "auto": auto, "dep": dep_ini}
    lista = "".join(f"<li>{_deporte(c.get('deporte'))[1]} {e(c['nombre'])} · {e(_deporte(c.get('deporte'))[0])}"
                    + ("" if datos.reservable(c) else " <span class='pill warn' style='font-size:11px'>Aún sin verificar</span>") + "</li>" for c in hermanas)
    estado = ("<div class='aviso ok'>✓ El local ya está verificado: la cancha nueva queda <b>activa al instante</b> y recibe reservas.</div>" if activo else
              "<div class='aviso'>⏳ El local está en verificación: la cancha nueva se <b>activará junto con él</b> cuando lo aprobemos. No hace falta otro reclamo.</div>")
    cuerpo = f"""
<div class='edit-top'><a class='volver-lnk' href='/anfitrion/canchas'>‹ Mis canchas</a>
<h1 class='anf-hola' style='margin-top:8px'>Agrega una cancha a {e(local)}</h1>
<p class='sub'>Se suma al local (misma dirección, fotos, servicios y dueño). Solo dinos qué cancha es. Puedes agregar varias del mismo deporte o de otro deporte.</p></div>
<div class='edit-grid'><nav class='edit-nav'><a href='#sec-cancha' class='edit-nav-it'>¿Qué cancha agregas?</a><a href='#sec-precio' class='edit-nav-it'>Precio y horario</a></nav>
<form id='fAgregar' class='edit-form' autocomplete='off' novalidate>
 <section class='panel edit-sec' id='sec-local'><h2>{e(local)}</h2>
  <p class='sub' style='margin:0'>{e(l.get('direccion') or '')}{(' · ' if l.get('direccion') and _zona(l) else '')}{e(_zona(l))}</p>
  <p class='sub' style='margin:8px 0 4px'>Canchas que ya tiene este local:</p><ul class='sub' style='margin:0 0 0 18px'>{lista}</ul>
  {estado}
 </section>
 <section class='panel edit-sec' id='sec-cancha'><h2>¿Qué cancha agregas?</h2>
  <label>Deporte <span class='req'>una cancha = un deporte</span></label>
  {_chips('deporte', dep_ops, dep_ini)}
  <label style='margin-top:18px'>Tipo de piso <span class='req'>obligatorio</span></label>
  <div id='supWrap'><p class='sub'>Marca primero el deporte.</p></div>
  <label for='nombreCancha' style='margin-top:18px'>Nombre de la cancha <span class='req'>opcional</span></label>
  <input id='nombreCancha' maxlength='{catalogos.NOMBRE_MAX}' placeholder='{e(auto.get(dep_ini) or "Ej. Fútbol 2")}'>
  <p class='sub' style='font-size:12.5px'>Si lo dejas vacío, la nombramos sola por deporte con el siguiente número del local.</p>
 </section>
 <section class='panel edit-sec' id='sec-precio'><h2>Precio y horario</h2><p class='sub'>Vienen del local; cámbialos si esta cancha es distinta.</p>
  <label for='precio'>Precio por hora</label>
  <div class='inp-moneda'><span>{e(sim)}</span><input id='precio' type='number' min='1' step='0.01' inputmode='decimal' value='{float(l.get("precio_hora") or 0):.2f}'></div>
  <div class='row' style='margin-top:14px'><div><label for='hora_apertura'>Abre</label>{_select_hora('hora_apertura', l.get('hora_apertura') or '07:00')}</div>
  <div><label for='hora_cierre'>Cierra</label>{_select_hora('hora_cierre', l.get('hora_cierre') or '23:00')}</div></div>
  <p class='sub' style='font-size:13px'>La hora de cierre es la hora en que <b>empieza el último turno</b>.</p>
  <label style='margin-top:14px'>Duración del turno</label>
  {_chips('duracion_slot_min', catalogos.DURACIONES, int(l.get('duracion_slot_min') or 60) if int(l.get('duracion_slot_min') or 60) in catalogos.DURACIONES else 60, fmt=catalogos.etiqueta_duracion)}
  <p class='sub' style='font-size:12.5px'>Hora feliz, seña, fotos propias y servicios extra los ajustas después en Editar cancha.</p>
 </section>
</form></div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>{'Queda activa al instante.' if activo else 'Se activa junto con el local.'}</span>
<button type='button' class='btn' id='btnGuardar'>Agregar cancha</button></div></div>
<script>var CFG={json.dumps(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{_JS_AGREGAR}</script>"""
    return ui.shell("Agregar cancha", cuerpo, nav=_cabecera("canchas", ses, tabs_visibles=False), sesion=ses, ancho=True,
                    titulo_tab=f"Agregar cancha · {local}")


_JS_AGREGAR = r"""
(function(){
var dep=CFG.dep||'', sup='';
function $(id){return document.getElementById(id)}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}
function sel(g){var b=document.querySelector(".chip.sel[data-g='"+g+"']");return b?b.dataset.v:''}
function pintarSup(){var w=$('supWrap');if(!dep){w.innerHTML="<p class='sub'>Marca primero el deporte.</p>";return}
  var l=CFG.superficies[dep]||[];if(l.indexOf(sup)<0)sup='';
  w.innerHTML="<div class='chips' style='margin-top:6px'>"+l.map(function(s){return "<button type='button' class='chip"+(s===sup?' sel':'')+"' data-g='sup' data-v='"+esc(s)+"'>"+esc(s)+"</button>"}).join('')+"</div>";
  $('nombreCancha').placeholder=CFG.auto[dep]||'Ej. Fútbol 2'}
document.addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-g]');if(!b)return;var g=b.dataset.g,v=b.dataset.v;
  b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');
  if(g==='deporte'){dep=v;pintarSup()}else if(g==='sup'){sup=v}});
pintarSup();
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');
  var body={deporte:dep,superficie:sup,nombre:$('nombreCancha').value,precio_hora:parseFloat($('precio').value)||0,hora_apertura:$('hora_apertura').value,hora_cierre:$('hora_cierre').value,duracion_slot_min:+sel('duracion_slot_min')||60};
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Agregando…';
  try{var r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){location.href=j.url||'/anfitrion/canchas';return}msg.classList.add('err');msg.textContent=j.error||'No se pudo agregar.';if(j.campo){var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth'})}}
  catch(e){msg.classList.add('err');msg.textContent='No se pudo agregar. Revisa tu conexión.'}btn.disabled=false});
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
    try:
        precio = round(float(b.get("precio_hora")), 2)
    except (TypeError, ValueError):
        precio = 0
    if not (0 < precio <= 100000):
        return None, "Pon un precio por hora válido.", "precio"
    ap, ci = str(b.get("hora_apertura") or "07:00"), str(b.get("hora_cierre") or "23:00")
    if not (_HORA_RE.match(ap) and _HORA_RE.match(ci)):
        return None, "Hora no válida (usa horas en punto).", "precio"
    try:
        dur = int(b.get("duracion_slot_min") or 60)
    except (TypeError, ValueError):
        dur = 0
    if dur not in catalogos.DURACIONES:
        return None, "Duración del turno no válida.", "precio"
    fotos = list(_fotos(l))
    fila = {"id": f"u{int(time.time() * 1000)}", "nombre": nombre, "club": (l.get("club") or "").strip() or l["nombre"],
            "distrito": l.get("distrito") or "", "barrio": l.get("barrio") or "", "deporte": dep, "deportes": [dep], "superficie": sup,
            "precio_hora": precio, "lat": l.get("lat"), "lng": l.get("lng"), "club_fundador": bool(l.get("club_fundador")),
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
    """INSERT de la cancha nueva heredando del local; sin reclamo nuevo."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    l = _cancha_propia(ses, cancha_id)
    if not l:
        return JSONResponse({"ok": False, "error": "no_encontrada"}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    fila, err, seccion = _validar_agregada(body, l, ses["email"])
    if fila is None:
        return JSONResponse({"ok": False, "error": err, "campo": seccion}, status_code=400)
    if not datos.insertar_canchas([fila]):
        return JSONResponse({"ok": False, "error": "No pudimos guardar la cancha en este momento. Inténtalo de nuevo."}, status_code=503)
    print(f"[agregar-web] {ses['email']} agregó {fila['nombre']!r} ({fila['deporte']}) a {fila['club']!r}: {fila['id']} · verificada={fila['verificada']}", flush=True)
    return JSONResponse({"ok": True, "url": f"/anfitrion/canchas?agregada={fila['id']}", "id": fila["id"], "verificada": fila["verificada"]})


def _aviso_verificacion(canchas: list[dict], email: str) -> str:
    """Banner del panel para las canchas del dueño AÚN sin verificar (espejo
    del cartel "pendiente" de la ficha del app): estado real del reclamo."""
    pend = [c for c in canchas if not datos.reservable(c)]
    if not pend:
        return ""
    vistos, filas = set(), []
    for c in pend:
        base = c["id"].split("_")[0]
        if base in vistos:
            continue
        vistos.add(base)
        try:
            est = reclamos.estado(c["id"], email)
        except Exception:  # noqa: BLE001
            est = {}
        clase, tit, txt = _ESTADO_RECLAMO.get(str(est.get("estado") or ""), ("warn", "Sin solicitud de verificación", "No encontramos tu solicitud. Vuelve a enviarla desde la app (ficha de la cancha → Reenviar solicitud)."))
        filas.append(f"<div class='aviso {clase}' style='margin:12px 0 0'><b>{e(c.get('club') or c['nombre'])}</b> · {tit}. <span class='sub' style='margin:0'>{txt}</span></div>")
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
              "<p class='sub'>Esta sección se administra desde la app de Pichangol con la misma cuenta de Google. "
              "La versión web llegará más adelante.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}' rel='noopener'>Abrir en la app</a>"
              "<a class='btn sec' href='/anfitrion'>Volver al menú</a></div></div>")
    return ui.shell(titulo, cuerpo, nav=_cabecera("", ses, tabs_visibles=False), sesion=ses, ancho=True, titulo_tab=f"{titulo} · Modo anfitrión")


def _entrar(volver: str) -> HTMLResponse:
    from urllib.parse import quote
    return HTMLResponse("", status_code=302, headers={"Location": f"/entrar?volver={quote(volver, safe='')}"})
