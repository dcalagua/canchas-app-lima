"""RESERVA WEB (sep-2026). Páginas públicas del dominio de marca, con el mismo
look & feel del APK (`web/ui.py`):

- GET  /canchas                    → catálogo de canchas verificadas (por país,
                                     filtro por deporte y buscador).
- GET  /reservar/{cancha_id}       → ficha + día (tira de 14 días) + horarios
                                     libres con precio + datos + extras + pago
                                     (Culqi Checkout: Yape y tarjeta) con
                                     "Resumen de tu reserva" fijo.
- GET  /web/disponibilidad/{id}    → JSON de slots del día (precio, ocupado).
- POST /web/asegurar               → toma los slots (INSERT 'nueva', hold 10 min).
- POST /web/pagar                  → cargo Culqi → confirma, liquida al dueño
                                     y le avisa.
- POST /web/liberar                → el cliente cerró sin pagar: libera el hold.
- GET  /reserva/{id}               → comprobante (por id o por grupo).
- GET  /reserva/{id}.ics           → evento para el calendario del cliente.

Misma base y mismas reglas que el APK: las filas van a `pichangol_reservas`
con el esquema que lee el dueño en su app, el UNIQUE del slot evita la doble
reserva, la contabilidad usa `/pagos/liquidacion-online` (billetera-first) y
el dueño recibe el push "Nueva reserva 📅".

MULTI-PAÍS: el cobro web sale sólo en soles (Culqi). Canchas en \\$ o Bs
muestran la ficha completa y mandan a reservar por la app (PayPhone /
Libélula).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

import config
from paises import _CAJAS, pais_de_coordenadas, moneda_de_pais, simbolo_de_moneda
from pagos import culqi
from web import datos, descubrir, horarios, marca, sesion, ui
from web.ui import e

router = APIRouter()

PLAY_URL = "https://play.google.com/store/apps/details?id=pe.ebim.pichangol"
DIAS_ADELANTE = 30
DIAS_TIRA = 14
MAX_SLOTS = 4
DEPORTES = {"futbol": ("Fútbol", "⚽"), "tenis": ("Tenis", "🎾"), "padel": ("Pádel", "🏓"),
            "pickleball": ("Pickleball", "🥒"), "voley": ("Vóley", "🏐"), "basquet": ("Básquet", "🏀"),
            "futsal": ("Futsal", "⚽")}
CIUDAD_DEFECTO = {"PE": (-12.046, -77.043), "EC": (-2.17, -79.92), "BO": (-16.5, -68.15)}
NOMBRE_PAIS = {"PE": "Perú", "EC": "Ecuador", "BO": "Bolivia"}
EXTRAS_NOMBRE = {"arbitro": "Árbitro", "pelotero": "Pelotero (recoge pelotas)",
                 "pelota": "Alquiler de pelota", "pecheras": "Petos / pecheras",
                 "hidratacion": "Hidratación"}
AMENIDAD_NOMBRE = {"estacionamiento": "Estacionamiento", "vestuarios": "Vestuarios", "duchas": "Duchas",
                   "iluminacion": "Iluminación", "techada": "Techada", "cafeteria": "Cafetería",
                   "wifi": "Wi-Fi", "tribuna": "Tribuna", "seguridad": "Seguridad"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _pais_de(c: dict) -> str:
    return pais_de_coordenadas(c.get("lat"), c.get("lng"))


def _moneda_de(c: dict) -> tuple[str, str]:
    """(símbolo, ISO) de la cancha: su moneda congelada o la del país."""
    iso = moneda_de_pais(_pais_de(c))
    sim = (c.get("moneda") or "").strip() or simbolo_de_moneda(iso)
    if sim == "S/":
        iso = "PEN"
    elif sim == "$":
        iso = "USD"
    elif sim.lower().startswith("bs"):
        iso = "BOB"
    return sim, iso


def _deporte(clave: str) -> tuple[str, str]:
    k = (clave or "").lower()
    return DEPORTES.get(k, ((clave or "Deporte").capitalize(), "🏟️"))


def _deportes_de(c: dict) -> list[str]:
    lst = [str(x).lower() for x in (c.get("deportes") or []) if x]
    p = (c.get("deporte") or "").lower()
    if p and p not in lst:
        lst.insert(0, p)
    return lst or ([p] if p else [])


def _zona(c: dict) -> str:
    return ", ".join(x for x in (c.get("barrio"), (c.get("distrito") or "").replace("_", " ").title()) if x)


def _secreto() -> bytes:
    return (config.ADMIN_PANEL_TOKEN or config.APP_API_KEY or "pichangol-web").encode()


def _firma(ids: list[str]) -> str:
    return hmac.new(_secreto(), "|".join(sorted(ids)).encode(), hashlib.sha256).hexdigest()[:32]


def _firma_ok(ids: list[str], firma: str) -> bool:
    return bool(ids) and hmac.compare_digest(_firma(ids), (firma or "")[:32])


def _pago_web_disponible(iso: str) -> bool:
    """El checkout web cobra con Culqi (soles). Con llave pública cargada, aunque
    sea de prueba, el formulario se muestra (así lo revisa la pasarela)."""
    return iso == "PEN" and bool(config.CULQI_PUBLIC_KEY)


def _fotos(c: dict) -> list[str]:
    out = []
    for u in [c.get("foto_url")] + list(c.get("fotos") or []):
        u = str(u or "").strip()
        if u.startswith("http") and u not in out:
            out.append(u)
    return out


def _foto_card(c: dict) -> str:
    fs = _fotos(c)
    if fs:
        return f"<img src='{e(fs[0])}' alt='{e(c.get('nombre'))}' loading='lazy'>"
    return f"<div class='sinfoto'>{_deporte(c.get('deporte'))[1]}</div>"


def _galeria(c: dict) -> str:
    fs = _fotos(c)
    if not fs:
        # Sin fotos propias: la galería arranca con el placeholder y un script
        # pide a /web/foto la PRIMERA FOTO de Google del lugar (como el app).
        q = (f"id={quote(str(c.get('id') or ''))}&nombre={quote(str(c.get('nombre') or ''))}"
             f"&club={quote(str(c.get('club') or ''))}&lat={c.get('lat') or 0}&lng={c.get('lng') or 0}")
        return (f"<div class='galeria una' id='galeria'><div class='sinfoto principal'>{_deporte(c.get('deporte'))[1]}</div></div>"
                "<script>(function(){fetch('/web/foto?" + q + "').then(function(r){return r.json();}).then(function(j){"
                "var f=(j&&j.fotos)||[];if(!f.length)return;var g=document.getElementById('galeria');if(!g)return;"
                "var esc=function(s){return String(s).replace(/[&<>\"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c];});};"
                "if(f.length===1){g.innerHTML='<img class=principal src=\"'+esc(f[0])+'\" alt=\"\">';return;}"
                "g.className='galeria';g.innerHTML='<img class=principal src=\"'+esc(f[0])+'\" alt=\"\">'+f.slice(1,3).map(function(u){return '<img src=\"'+esc(u)+'\" alt=\"\" loading=lazy>';}).join('');"
                "}).catch(function(){});})();</script>")
    if len(fs) == 1:
        return f"<div class='galeria una'><img class='principal' src='{e(fs[0])}' alt='{e(c['nombre'])}'></div>"
    partes = [f"<img class='principal' src='{e(fs[0])}' alt='{e(c['nombre'])}'>"]
    for u in fs[1:3]:
        partes.append(f"<img src='{e(u)}' alt='' loading='lazy'>")
    while len(partes) < 3 and len(fs) > 1:
        partes.append(f"<div class='sinfoto'>{_deporte(c.get('deporte'))[1]}</div>")
    return f"<div class='galeria'>{''.join(partes)}</div>"


def _maps(c: dict) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={c.get('lat')},{c.get('lng')}"


def _no_encontrada(que: str = "Cancha no disponible") -> HTMLResponse:
    return ui.shell(que, (f"<div class='panel' style='text-align:center;margin-top:24px'><h1>{e(que)}</h1>"
                          "<p class='sub'>Puede que el enlace sea viejo o que el local haya dejado de "
                          "publicar en Pichangol.</p><div class='acciones' style='justify-content:center'>"
                          "<a class='btn' href='/canchas'>Ver canchas disponibles</a></div></div>"))


# ── catálogo ──────────────────────────────────────────────────────────────────

_JS_EXPLORAR = r"""
(function(){
  var C = window.__explorar, $ = function(id){ return document.getElementById(id); };
  var cards = function(){ return Array.prototype.slice.call(document.querySelectorAll('.lst[data-lat]')); };
  var yo = null, mapa = null, marcadores = [], miPin = null, pinesDesc = [], descubiertas = {}, fotosConocidas = {};
  var filtro = {q: '', dep: C.dep || '', fecha: '', hora: '', cerca: false};
  var pend = {q: '', fecha: '', hora: '', cerca: false}; // lo elegido en el buscador; se aplica al pulsar Buscar (como Airbnb)
  var favs = {};
  try { favs = JSON.parse(localStorage.getItem('pcg_fav') || '{}') || {}; } catch(e){}
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function km(a, b, c, d){ var R = 6371, dLat = (c-a)*Math.PI/180, dLng = (d-b)*Math.PI/180;
    var x = Math.sin(dLat/2)*Math.sin(dLat/2) + Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(dLng/2)*Math.sin(dLng/2);
    return 2*R*Math.asin(Math.sqrt(x)); }
  function fmtKm(d){ return d < 1 ? (Math.round(d*1000) + ' m') : (d < 10 ? d.toFixed(1) + ' km' : Math.round(d) + ' km'); }
  function paisDe(lat, lng){
    var dentro = [], best = null, bd = 1e9;
    Object.keys(C.cajas).forEach(function(k){ var c = C.cajas[k]; if(lat >= c[0] && lat <= c[1] && lng >= c[2] && lng <= c[3]) dentro.push(k); });
    (dentro.length ? dentro : Object.keys(C.cajas)).forEach(function(k){ var c = C.cajas[k]; var d = Math.hypot(lat-c[4], lng-c[5]); if(d < bd){ bd = d; best = k; } });
    return best;
  }
  // ── corazones (favoritos en este navegador) ──
  function pintarFavs(){ cards().forEach(function(c){ var b = c.querySelector('.corazon'); if(b) b.classList.toggle('on', !!favs[c.dataset.id]); }); }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest('.corazon'); if(!b) return;
    ev.preventDefault(); ev.stopPropagation();
    var id = b.closest('.lst').dataset.id; if(favs[id]) delete favs[id]; else favs[id] = 1;
    try { localStorage.setItem('pcg_fav', JSON.stringify(favs)); } catch(e){}
    pintarFavs();
  });
  // ── carrusel de fotos de cada tarjeta ──
  document.addEventListener('click', function(ev){
    var f = ev.target.closest('.flecha'); if(!f) return;
    ev.preventDefault(); ev.stopPropagation();
    var box = f.closest('.foto').querySelector('.fotos'); var w = box.clientWidth;
    box.scrollBy({left: f.classList.contains('der') ? w : -w, behavior: 'smooth'});
  });
  document.addEventListener('scroll', function(ev){
    var box = ev.target; if(!box.classList || !box.classList.contains('fotos')) return;
    var i = Math.round(box.scrollLeft / Math.max(1, box.clientWidth));
    var dots = box.parentNode.querySelectorAll('.dots i'); dots.forEach(function(d, j){ d.style.background = j === i ? '#fff' : 'rgba(255,255,255,.6)'; });
  }, true);
  // ── filtros (buscador, deporte, fecha, solo verificadas, precio máx) ──
  function pasaBase(c){
    if(filtro.q && c.dataset.t.indexOf(filtro.q) < 0) return false;
    if(filtro.cerca && yo && c.dataset.d && parseFloat(c.dataset.d) > 30) return false;
    if(filtro.hora && !abiertaA(c, filtro.hora)) return false;
    if(filtro.hora && filtro.fecha && c.dataset.ok === '1'){ var lk = libres[filtro.fecha + '|' + filtro.hora]; if(lk && lk[c.dataset.id] === false) return false; }
    return true;
  }
  function aplicar(){
    var n = 0;
    cards().forEach(function(c){
      var ok = pasaBase(c) && pasaFil(c, fil);
      c.style.display = ok ? '' : 'none'; if(ok) n++;
      if(c.dataset.base){ var qs = []; if(filtro.fecha) qs.push('fecha=' + filtro.fecha); if(filtro.hora) qs.push('hora=' + filtro.hora); c.setAttribute('href', c.dataset.base + (qs.length ? '?' + qs.join('&') : '')); }
    });
    document.querySelectorAll('.grupo-pais').forEach(function(g){
      var vis = Array.prototype.some.call(g.querySelectorAll('.lst'), function(c){ return c.style.display !== 'none'; });
      g.style.display = vis ? '' : 'none';
    });
    var v = $('vacio'); if(v){ v.style.display = n ? 'none' : '';
      if(!n && v.dataset.base !== undefined){
        var why = filtro.hora ? 'Ninguna cancha' + (filtro.cerca ? ' cerca de ti' : '') + ' tiene turno libre ' + (filtro.fecha ? etiquetaFecha(filtro.fecha).toLowerCase() : '') + ' a las ' + filtro.hora + '. Prueba con otra hora u otro día.'
                              : 'No hay canchas libres con esa búsqueda. Prueba con otra zona, día u hora.';
        v.textContent = why; } }
    if(mapa) marcadores.forEach(function(m){ var ok = m._card.style.display !== 'none'; if(ok){ m.addTo(mapa); } else { m.remove(); } });
  }
  // Deporte: lo filtra el SERVIDOR (?deporte=), las pestañas son enlaces normales (SEO, sin JS).
  var sQ = $('sQ'), sF = $('sF'), sH = $('sH');
  if(sQ) sQ.addEventListener('input', function(){ pend.cerca = false; pend.q = sQ.value.trim().toLowerCase(); });
  // ── fecha + hora: calendario tipo Airbnb y panel de horas ──
  var DIAS = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'], MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  var MESES_L = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  function iso(d){ return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }
  function deIso(s){ var p = s.split('-'); return new Date(parseInt(p[0]), parseInt(p[1])-1, parseInt(p[2])); }
  var hoy = new Date(); hoy.setHours(0,0,0,0); var hoyIso = iso(hoy);
  var maxD = new Date(hoy); maxD.setDate(maxD.getDate() + (C.diasAdelante || 30)); var maxIso = iso(maxD);
  var calBase = new Date(hoy.getFullYear(), hoy.getMonth(), 1), libres = {}, modoLibre = false;
  function etiquetaFecha(s){ if(!s) return ''; if(s === hoyIso) return 'Hoy'; var d = deIso(s); var m = new Date(hoy); m.setDate(m.getDate()+1); if(s === iso(m)) return 'Mañana'; return DIAS[d.getDay()] + ' ' + d.getDate() + ' ' + MESES[d.getMonth()]; }
  function hm(t){ if(!t) return null; var p = t.split(':'); return parseInt(p[0]) * 60 + parseInt(p[1]); }
  function abiertaA(c, hora){
    var ap = hm(c.dataset.ap || '07:00'), ci = hm(c.dataset.ci || '23:00'), h = hm(hora); if(h == null) return true;
    if(ci <= ap) ci += 1440; if(h < ap && ci > 1440) h += 1440;
    return ap <= h && h + Math.min(60, parseInt(c.dataset.paso || '60')) <= ci;
  }
  function mesHtml(y, m){
    var primero = new Date(y, m, 1), n = new Date(y, m+1, 0).getDate(), off = (primero.getDay() + 6) % 7;
    var h = '<div class="cal-mes"><div class="cal-tit">' + MESES_L[m] + ' ' + y + '</div><div class="cal-grid">';
    ['L','Ma','Mi','J','V','S','D'].forEach(function(d){ h += '<span class="cal-dn">' + d + '</span>'; });
    for(var i = 0; i < off; i++) h += '<span></span>';
    for(var d = 1; d <= n; d++){ var s = iso(new Date(y, m, d)); var off2 = s < hoyIso || s > maxIso;
      h += '<button type="button" class="cal-d' + (off2 ? ' off' : '') + (s === pend.fecha ? ' sel' : '') + (s === hoyIso ? ' hoy' : '') + '" data-f="' + s + '"' + (off2 ? ' disabled' : '') + '>' + d + '</button>'; }
    return h + '</div></div>';
  }
  function pintarCal(){
    var box = $('calMeses'); if(!box) return;
    var y = calBase.getFullYear(), m = calBase.getMonth();
    var dos = window.innerWidth > 900;
    box.innerHTML = mesHtml(y, m) + (dos ? mesHtml(y + (m === 11 ? 1 : 0), (m + 1) % 12) : '');
    var ant = document.querySelector('#panCuando .cal-ant'), sig = document.querySelector('#panCuando .cal-sig');
    if(ant) ant.disabled = calBase <= new Date(hoy.getFullYear(), hoy.getMonth(), 1);
    if(sig) sig.disabled = new Date(y, m + (dos ? 2 : 1), 1) > maxD;
    var at = $('calAtajos'); if(at && !at.children.length){
      var man = new Date(hoy); man.setDate(man.getDate()+1);
      var sab = new Date(hoy); sab.setDate(sab.getDate() + ((6 - sab.getDay() + 7) % 7 || 7));
      var dom = new Date(hoy); dom.setDate(dom.getDate() + ((7 - dom.getDay()) % 7 || 7));
      at.innerHTML = [['Hoy', hoyIso], ['Mañana', iso(man)], ['Sábado ' + sab.getDate(), iso(sab)], ['Domingo ' + dom.getDate(), iso(dom)]]
        .map(function(x){ return '<button type="button" class="chip" data-f="' + x[1] + '">' + x[0] + '</button>'; }).join('');
    }
    document.querySelectorAll('#calAtajos .chip').forEach(function(b){ b.classList.toggle('sel', b.dataset.f === pend.fecha); });
    document.querySelectorAll('#panCuando .cal-modo button').forEach(function(b){ b.classList.toggle('on', (b.dataset.modo === 'libre') === modoLibre); });
  }
  function ponerFecha(f, abrirHora){
    pend.fecha = f || ''; modoLibre = !pend.fecha; if(sF){ sF.value = etiquetaFecha(pend.fecha); sF.dataset.iso = pend.fecha; }
    pintarCal();
    // Si la hora elegida ya pasó para HOY, se descarta (no se alquila en el pasado).
    if(pend.hora && horaPasada(pend.hora)) ponerHora('', true);
    if(abrirHora){ abrirPanel('panHora'); } else { abrirPanel(null); }
  }
  function horaPasada(h){
    // Con "Hoy" solo valen los turnos que EMPIEZAN después de este momento (misma regla que la ficha).
    if(pend.fecha !== hoyIso) return false;
    var n = new Date(); return hm(h) <= n.getHours() * 60 + n.getMinutes();
  }
  function pintarHoras(){
    var grupos = document.querySelectorAll('#panHora .hgrupo'), todas = true;
    grupos.forEach(function(g){
      var alguna = false;
      g.querySelectorAll('.hchip').forEach(function(b){
        var pasada = horaPasada(b.dataset.hora);
        // Solo se ofrecen horas en las que ALGUNA cancha de la lista tiene turno (una que cierra 23:00 termina su último turno a las 23:00).
        var sinTurno = !pasada && !cards().some(function(c){ return abiertaA(c, b.dataset.hora); });
        var off = pasada || sinTurno;
        b.classList.toggle('off', off); b.disabled = off; b.title = pasada ? 'Esta hora ya pasó' : (sinTurno ? 'Ninguna cancha tiene turno a esta hora' : '');
        b.classList.toggle('sel', !off && b.dataset.hora === pend.hora); if(!off) alguna = true; });
      g.classList.toggle('off', !alguna); if(alguna) todas = false;
    });
    var av = $('horaAviso'); if(av){
      av.style.display = todas ? '' : 'none';
      if(todas){
        // Explica el motivo real: ¿ya pasaron todas las horas, o las canchas cierran antes de las horas que quedan?
        var cierres = cards().map(function(c){ var ci = hm(c.dataset.ci || '23:00'), ap = hm(c.dataset.ap || '07:00'); return ci <= ap ? ci + 1440 : ci; });
        var cierreMax = cierres.length ? Math.max.apply(null, cierres) : 0;
        var ultimo = cierreMax ? cierreMax - 60 : 0, txtCierre = function(m){ m = m % 1440; return (m < 600 ? '0' : '') + Math.floor(m / 60) + ':' + (m % 60 < 10 ? '0' : '') + (m % 60); };
        av.textContent = pend.fecha === hoyIso && cierreMax
          ? 'Las canchas de esta lista cierran a las ' + txtCierre(cierreMax) + ' como máximo: su último turno de hoy (' + txtCierre(ultimo) + ') ya empezó. Elige otro día en “Cuándo”.'
          : (pend.fecha === hoyIso ? 'Hoy ya no quedan turnos por delante. Elige otro día en “Cuándo”.' : 'Ninguna cancha de la lista tiene turnos a estas horas.');
      } }
  }
  function ponerHora(h, sinCerrar){
    pend.hora = h || ''; if(sH){ sH.value = pend.hora; sH.dataset.hora = pend.hora; }
    pintarHoras();
    if(!sinCerrar) abrirPanel(null);
  }
  function consultarLibres(){
    // Con fecha + hora, el servidor dice qué canchas tienen un turno LIBRE que cubra esa hora.
    if(!filtro.fecha || !filtro.hora) return;
    var k = filtro.fecha + '|' + filtro.hora; if(libres[k]) return;
    fetch('/web/libres?fecha=' + filtro.fecha + '&hora=' + filtro.hora).then(function(r){ return r.json(); })
      .then(function(j){ if(j && j.ok){ libres[k] = j.libres || {}; aplicar(); } }).catch(function(){});
  }
  var paneles = ['sugDonde', 'panCuando', 'panHora'];
  function abrirPanel(id){ paneles.forEach(function(p){ var el = $(p); if(el) el.classList.toggle('open', p === id); }); if(id === 'panCuando') pintarCal(); if(id === 'panHora') pintarHoras(); }
  document.addEventListener('click', function(ev){
    // Un clic fuera del buscador cierra los desplegables (si el nodo clicado ya
    // se repintó —día del calendario— no cuenta como "fuera").
    if(!ev.target.isConnected) return;
    if(!ev.target.closest('.busq')) abrirPanel(null);
  });
  if(sF){ sF.addEventListener('click', function(){ abrirPanel('panCuando'); }); sF.addEventListener('focus', function(){ abrirPanel('panCuando'); }); }
  if(sH){ sH.addEventListener('click', function(){ abrirPanel('panHora'); }); sH.addEventListener('focus', function(){ abrirPanel('panHora'); }); }
  var pc = $('panCuando');
  if(pc){
    pc.addEventListener('click', function(ev){
      var d = ev.target.closest('.cal-d'); if(d && !d.disabled){ ponerFecha(d.dataset.f, true); return; }
      var a = ev.target.closest('#calAtajos .chip'); if(a){ ponerFecha(a.dataset.f, true); return; }
      if(ev.target.closest('.cal-ant')){ calBase = new Date(calBase.getFullYear(), calBase.getMonth() - 1, 1); pintarCal(); return; }
      if(ev.target.closest('.cal-sig')){ calBase = new Date(calBase.getFullYear(), calBase.getMonth() + 1, 1); pintarCal(); return; }
      var mo = ev.target.closest('.cal-modo button'); if(mo){ if(mo.dataset.modo === 'libre') ponerFecha('', false); else { modoLibre = false; pintarCal(); } }
    });
    window.addEventListener('resize', function(){ if(pc.classList.contains('open')) pintarCal(); });
  }
  var ph = $('panHora');
  if(ph) ph.addEventListener('click', function(ev){ var b = ev.target.closest('[data-hora]'); if(b && !b.disabled) ponerHora(b.dataset.hora); });
  // Fecha/hora que vienen en la URL (?fecha=&hora=) arrancan seleccionadas.
  if(C.fecha && C.fecha >= hoyIso && C.fecha <= maxIso){ filtro.fecha = pend.fecha = C.fecha; if(sF){ sF.value = etiquetaFecha(C.fecha); sF.dataset.iso = C.fecha; } }
  if(C.hora && !horaPasada(C.hora)){ filtro.hora = pend.hora = C.hora; if(sH){ sH.value = C.hora; sH.dataset.hora = C.hora; } consultarLibres(); }
  function pintarResumenBusq(){
    var r = $('resBusq'); if(!r) return;
    var partes = []; if(filtro.cerca) partes.push('Cerca de ti'); if(filtro.q) partes.push('“' + filtro.q + '”'); if(filtro.fecha) partes.push(etiquetaFecha(filtro.fecha)); if(filtro.hora) partes.push(filtro.hora);
    r.innerHTML = partes.length ? '· Buscando: <b>' + esc(partes.join(' · ')) + '</b> <button type="button" id="btnLimpiar">Limpiar</button>' : '';
    var bl = $('btnLimpiar'); if(bl) bl.addEventListener('click', function(){ pend = {q: '', fecha: '', hora: '', cerca: false}; if(sQ) sQ.value = ''; ponerFecha('', false); ponerHora('', true); buscar(); });
  }
  // ── desplegable bajo "Dónde": búsquedas recientes (este navegador) + zonas sugeridas ──
  var sug = $('sugDonde'), recientes = [];
  try { recientes = JSON.parse(localStorage.getItem('pcg_busq') || '[]') || []; } catch(e){}
  function pintarRecientes(){
    var box = $('sugRecientes'), lst = $('sugRecientesLista'); if(!box || !lst) return;
    lst.innerHTML = recientes.map(function(q){ return '<button type="button" class="it" data-zona="' + esc(q) + '"><span class="ic">🕘</span><div><b>' + esc(q) + '</b><small>Búsqueda reciente</small></div></button>'; }).join('');
    box.style.display = recientes.length ? '' : 'none';
  }
  function recordar(q){
    q = (q || '').trim(); if(!q) return;
    recientes = [q].concat(recientes.filter(function(x){ return x.toLowerCase() !== q.toLowerCase(); })).slice(0, 5);
    try { localStorage.setItem('pcg_busq', JSON.stringify(recientes)); } catch(e){}
    pintarRecientes();
  }
  function abrirSug(on){ abrirPanel(on ? 'sugDonde' : null); }
  if(sQ && sug){
    sQ.addEventListener('focus', function(){ pintarRecientes(); abrirSug(true); });
    sQ.addEventListener('click', function(){ pintarRecientes(); abrirSug(true); });
    sQ.addEventListener('keydown', function(ev){ if(ev.key === 'Enter'){ ev.preventDefault(); buscar(); } });
    sug.addEventListener('click', function(ev){
      var it = ev.target.closest('.it'); if(!it) return;
      if(it.dataset.cerca){ pend.cerca = true; pend.q = ''; sQ.value = 'Cerca de ti'; abrirPanel('panCuando'); return; }
      sQ.value = it.dataset.zona || ''; pend.q = sQ.value.trim().toLowerCase(); abrirPanel('panCuando');
    });
  }
  function buscar(){
    // Aquí recién se APLICA lo elegido (zona, fecha, hora), como el botón de Airbnb.
    abrirPanel(null);
    if(sQ && !pend.cerca){ pend.q = sQ.value.trim().toLowerCase(); recordar(sQ.value); }
    if(pend.hora && horaPasada(pend.hora)) ponerHora('', true);
    filtro.q = pend.cerca ? '' : pend.q; filtro.cerca = pend.cerca; filtro.fecha = pend.fecha; filtro.hora = pend.hora;
    if(filtro.cerca){ if(yo) ordenar(); else ubicar(true); }
    consultarLibres(); aplicar(); pintarResumenBusq();
    var g = $('grupos'); if(g) g.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  var bF = $('btnBuscar'); if(bF) bF.addEventListener('click', buscar);
  // ── Filtros tipo Airbnb (modal): amenidades, tipo, precio, superficie, duración ──
  var fil = {am: {}, tipo: '', sup: '', dur: 0, min: 0, max: 0}, filTmp = null, precioMon = '', pRango = [0, 0];
  var modal = $('modalFiltros'), bFil = $('btnFiltros');
  function copiaFil(f){ return {am: Object.assign({}, f.am), tipo: f.tipo, sup: f.sup, dur: f.dur, min: f.min, max: f.max}; }
  function pasaFil(c, f){
    for(var a in f.am){ if(f.am[a] && (' ' + (c.dataset.am || '') + ' ').indexOf(' ' + a + ' ') < 0) return false; }
    if(f.tipo === 'ok' && c.dataset.ok !== '1') return false;
    if(f.tipo === 'pend' && c.dataset.ok === '1') return false;
    if(f.sup && (c.dataset.sup || '') !== f.sup) return false;
    if(f.dur && parseInt(c.dataset.paso || '60') !== f.dur) return false;
    if((f.min || f.max) && c.dataset.mon === precioMon){ var p = parseFloat(c.dataset.pnum || '0'); if(f.min && p < f.min) return false; if(f.max && p > f.max) return false; }
    return true;
  }
  function nFiltros(f){ var n = 0; for(var a in f.am){ if(f.am[a]) n++; } if(f.tipo) n++; if(f.sup) n++; if(f.dur) n++; if(f.min || f.max) n++; return n; }
  function pintarBadge(){ var b = $('nFiltros'); if(!b) return; var n = nFiltros(fil); b.textContent = n; b.style.display = n ? '' : 'none'; if(bFil) bFil.classList.toggle('on', n > 0); }
  function pintarQuick(){ document.querySelectorAll('.qam').forEach(function(b){ b.classList.toggle('sel', !!fil.am[b.dataset.am]); }); }
  document.querySelectorAll('.qam').forEach(function(b){ b.addEventListener('click', function(){ fil.am[b.dataset.am] = !fil.am[b.dataset.am]; pintarQuick(); pintarBadge(); aplicar(); }); });
  function cuentaModal(){
    var n = cards().filter(function(c){ return pasaBase(c) && pasaFil(c, filTmp); }).length;
    var m = $('mostrarFiltros'); if(m) m.textContent = n ? 'Mostrar ' + n + ' cancha' + (n === 1 ? '' : 's') : 'Sin canchas con estos filtros';
  }
  function pintarModal(){
    document.querySelectorAll('#modalFiltros .tile, #modalFiltros .fam').forEach(function(b){ b.classList.toggle('sel', !!filTmp.am[b.dataset.am]); });
    document.querySelectorAll('#fTipo button').forEach(function(b){ b.classList.toggle('on', b.dataset.tipo === filTmp.tipo); });
    document.querySelectorAll('#modalFiltros .fsup').forEach(function(b){ b.classList.toggle('sel', b.dataset.sup === filTmp.sup); });
    document.querySelectorAll('#modalFiltros .fdur').forEach(function(b){ b.classList.toggle('sel', parseInt(b.dataset.dur) === filTmp.dur); });
    var rMin = $('rMin'), rMax = $('rMax'), pMin = $('pMin'), pMax = $('pMax');
    if(rMin){ rMin.value = filTmp.min || pRango[0]; rMax.value = filTmp.max || pRango[1]; pMin.value = filTmp.min || pRango[0]; pMax.value = filTmp.max || pRango[1]; pintarHisto(); }
    cuentaModal();
  }
  function pintarHisto(){
    var h = $('histo'); if(!h) return;
    var vals = cards().filter(function(c){ return c.dataset.mon === precioMon && c.dataset.pnum; }).map(function(c){ return parseFloat(c.dataset.pnum); });
    var lo = pRango[0], hi = pRango[1], nb = 24, bins = []; for(var i = 0; i < nb; i++) bins.push(0);
    vals.forEach(function(v){ var i = hi > lo ? Math.min(nb - 1, Math.floor((v - lo) / (hi - lo) * nb)) : 0; bins[i]++; });
    var mx = Math.max.apply(null, bins.concat([1])), a = parseFloat($('rMin').value), b = parseFloat($('rMax').value);
    h.innerHTML = bins.map(function(n, i){ var v = lo + (i + .5) / nb * (hi - lo); return '<i style="height:' + Math.max(5, Math.round(n / mx * 100)) + '%" class="' + (v >= a && v <= b ? 'on' : '') + '"></i>'; }).join('');
    var mm = $('monMin'), mM = $('monMax'); if(mm) mm.textContent = precioMon; if(mM) mM.textContent = precioMon;
    var ps = $('precioSub'); if(ps) ps.textContent = 'Precio por hora en ' + precioMon + (vals.length ? ' · ' + vals.length + ' canchas' : '');
  }
  function abrirModal(on){
    if(!modal) return;
    if(on){
      var cs = cards().filter(function(c){ return c.dataset.pnum; });
      var pais = yo ? paisDe(yo.lat, yo.lng) : null;
      var grupo = pais ? document.querySelector('.grupo-pais[data-pais="' + pais + '"] .lst[data-mon]') : null;
      precioMon = (grupo || cs[0] || {dataset: {}}).dataset.mon || 'S/';
      var vals = cs.filter(function(c){ return c.dataset.mon === precioMon; }).map(function(c){ return parseFloat(c.dataset.pnum); });
      pRango = vals.length ? [Math.floor(Math.min.apply(null, vals)), Math.ceil(Math.max.apply(null, vals))] : [0, 0];
      ['rMin', 'rMax'].forEach(function(id){ var r = $(id); if(r){ r.min = pRango[0]; r.max = pRango[1]; } });
      filTmp = copiaFil(fil); pintarModal();
    }
    modal.classList.toggle('open', on); document.body.classList.toggle('sin-scroll', on);
  }
  if(bFil) bFil.addEventListener('click', function(){ abrirModal(true); });
  if(modal){
    $('cerrarFiltros').addEventListener('click', function(){ abrirModal(false); });
    modal.addEventListener('click', function(ev){ if(ev.target === modal) abrirModal(false); });
    document.addEventListener('keydown', function(ev){ if(ev.key === 'Escape' && modal.classList.contains('open')) abrirModal(false); });
    modal.addEventListener('click', function(ev){
      var t = ev.target.closest('.tile, .fam'); if(t){ filTmp.am[t.dataset.am] = !filTmp.am[t.dataset.am]; pintarModal(); return; }
      var ty = ev.target.closest('#fTipo button'); if(ty){ filTmp.tipo = ty.dataset.tipo; pintarModal(); return; }
      var su = ev.target.closest('.fsup'); if(su){ filTmp.sup = filTmp.sup === su.dataset.sup ? '' : su.dataset.sup; pintarModal(); return; }
      var du = ev.target.closest('.fdur'); if(du){ var d = parseInt(du.dataset.dur); filTmp.dur = filTmp.dur === d ? 0 : d; pintarModal(); return; }
    });
    function leerRango(desdeCaja){
      var rMin = $('rMin'), rMax = $('rMax'), pMin = $('pMin'), pMax = $('pMax');
      var a = parseFloat(desdeCaja ? pMin.value : rMin.value), b = parseFloat(desdeCaja ? pMax.value : rMax.value);
      if(isNaN(a)) a = pRango[0]; if(isNaN(b)) b = pRango[1];
      a = Math.max(pRango[0], Math.min(a, pRango[1])); b = Math.max(pRango[0], Math.min(b, pRango[1]));
      if(a > b){ if(desdeCaja) b = a; else a = b; }
      rMin.value = a; rMax.value = b; pMin.value = a; pMax.value = b;
      filTmp.min = a > pRango[0] ? a : 0; filTmp.max = b < pRango[1] ? b : 0;
      pintarHisto(); cuentaModal();
    }
    ['rMin', 'rMax'].forEach(function(id){ var r = $(id); if(r) r.addEventListener('input', function(){ leerRango(false); }); });
    ['pMin', 'pMax'].forEach(function(id){ var r = $(id); if(r) r.addEventListener('change', function(){ leerRango(true); }); });
    $('limpiarFiltros').addEventListener('click', function(){ filTmp = {am: {}, tipo: '', sup: '', dur: 0, min: 0, max: 0}; pintarModal(); });
    $('mostrarFiltros').addEventListener('click', function(){ fil = copiaFil(filTmp); pintarQuick(); pintarBadge(); aplicar(); abrirModal(false); var g = $('grupos'); if(g) g.scrollIntoView({behavior: 'smooth', block: 'start'}); });
  }
  // ── cercanía ──
  function ordenar(){
    if(!yo) return;
    var pais = paisDe(yo.lat, yo.lng);
    cards().forEach(function(c){ var d = km(yo.lat, yo.lng, parseFloat(c.dataset.lat), parseFloat(c.dataset.lng)); c.dataset.d = d;
      var el = c.querySelector('.dist'); if(el) el.textContent = 'a ' + fmtKm(d); });
    document.querySelectorAll('.grupo-pais').forEach(function(g){
      var grid = g.querySelector('.lst-grid'); if(!grid) return;
      var hijos = Array.prototype.slice.call(grid.children).sort(function(a, b){ return parseFloat(a.dataset.d) - parseFloat(b.dataset.d); });
      hijos.forEach(function(h){ grid.appendChild(h); });
    });
    var propio = document.querySelector('.grupo-pais[data-pais="' + pais + '"]');
    if(propio && propio.parentNode){ propio.parentNode.insertBefore(propio, $('grupos').firstChild); var t = propio.querySelector('.cerca'); if(t) t.textContent = '· las más cercanas a ti primero'; }
    var u = $('ubicTxt'); if(u) u.textContent = 'Mostrando las canchas más cercanas a ti.';
    if(filtro.cerca) aplicar();
    var bu = $('btnUbic'); if(bu) bu.style.display = 'none';
    descubrir(yo.lat, yo.lng);
    if(mapa){ if(miPin) miPin.remove(); miPin = L.marker([yo.lat, yo.lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio yo">Tú</span>', iconSize: null})}).addTo(mapa);
      var pts = cards().filter(function(c){ return parseFloat(c.dataset.d) < 60; }).map(function(c){ return [parseFloat(c.dataset.lat), parseFloat(c.dataset.lng)]; });
      pts.push([yo.lat, yo.lng]); mapa.fitBounds(L.latLngBounds(pts).pad(0.2), {maxZoom: 14}); }
  }
  function ubicar(interactivo){
    var u = $('ubicTxt'), bu = $('btnUbic');
    if(!navigator.geolocation){ if(u) u.textContent = 'Tu navegador no permite ubicación. Busca por zona.'; return; }
    if(u) u.textContent = 'Buscando tu ubicación…';
    navigator.geolocation.getCurrentPosition(function(pos){
      yo = {lat: pos.coords.latitude, lng: pos.coords.longitude};
      try { localStorage.setItem('pcg_ubic', JSON.stringify(yo)); } catch(e){}
      ordenar();
    }, function(){
      if(u) u.textContent = interactivo ? 'No pudimos leer tu ubicación. Revisa el permiso del navegador o busca por zona.' : 'Permite tu ubicación para ver primero las canchas más cercanas.';
      if(bu) bu.style.display = '';
    }, {enableHighAccuracy: false, timeout: 8000, maximumAge: 300000});
  }
  // ── descubiertas (Google Places, como el APK) ──
  function tarjetaDesc(c){
    // Fotos: las que trae la Edge, o las que ya resolvió /web/foto antes de
    // este re-pintado (nunca se "esconde" una foto ya mostrada).
    var fs = (c.fotos && c.fotos.length) ? c.fotos : (fotosConocidas[c.id] || []);
    if(fs.length) fotosConocidas[c.id] = fs;
    var foto = fs.length ? fs.slice(0, 3).map(function(u){ return '<img src="' + esc(u) + '" alt="" loading="lazy">'; }).join('') : '<div class="sinfoto" data-buscar="1">' + (c.emoji || '🏟️') + '</div>';
    var extra = fs.length > 1 ? '<button class="flecha izq" aria-label="Anterior">‹</button><button class="flecha der" aria-label="Siguiente">›</button><div class="dots">' + fs.slice(0, 3).map(function(){ return '<i></i>'; }).join('') + '</div>' : '';
    return '<a class="lst pend" href="' + C.play + '" rel="noopener" data-id="' + esc(c.id) + '" data-lat="' + c.lat + '" data-lng="' + c.lng + '" data-ok="0" data-deps="' + esc(c.deporte) + '" data-nombre="' + esc(c.nombre) + '" data-sub="' + esc(c.direccion) + '" data-precio="' + esc(c.deporte_nombre) + '" data-t="' + esc((c.nombre + ' ' + c.direccion).toLowerCase()) + '">' +
      '<div class="foto"><div class="fotos">' + foto + '</div><span class="badge pend">Aún sin registrar</span>' + extra + '</div>' +
      '<div class="lb"><div class="l1"><b>' + esc(c.nombre) + '</b><span class="rate">' + esc(c.deporte_nombre) + '</span></div>' +
      '<div class="l2">' + esc(c.direccion) + '</div><div class="l2"><span class="dist">' + (c.km != null ? 'a ' + fmtKm(c.km) : '') + '</span></div>' +
      '<div class="l3"><span class="app">📲 Reservar en la app</span> <span class="app">📍 <span class="ir" data-lat="' + c.lat + '" data-lng="' + c.lng + '">Cómo llegar</span></span></div></div></a>';
  }
  document.addEventListener('click', function(ev){ var g = ev.target.closest('.ir'); if(!g) return; ev.preventDefault(); ev.stopPropagation();
    window.open('https://www.google.com/maps/search/?api=1&query=' + g.dataset.lat + ',' + g.dataset.lng, '_blank'); });
  function pintarDescubiertas(lista, conFotos){
    var sec = $('descubiertas'), grid = $('gridDesc');
    if(!sec || !grid) return;
    if(!lista.length){ if(!conFotos) sec.style.display = 'none'; return; }
    sec.style.display = '';
    grid.innerHTML = lista.map(tarjetaDesc).join('');
    resolverFotos();
    if(mapa && window.L){
      pinesDesc.forEach(function(m){ m.remove(); }); pinesDesc = [];
      lista.forEach(function(c){
        var m = L.marker([c.lat, c.lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio pend">' + esc(c.emoji || '') + ' ' + esc(c.deporte_nombre) + '</span>', iconSize: null})}).addTo(mapa);
        m.bindPopup('<b>' + esc(c.nombre) + '</b><br>' + esc(c.direccion) + '<br><a class="btn sec" href="' + C.play + '">Reservar en la app</a>');
        pinesDesc.push(m);
      });
    }
    aplicar();
  }
  function descubrir(lat, lng){
    var k = lat.toFixed(2) + ',' + lng.toFixed(2);
    if(descubiertas[k]) return; descubiertas[k] = true;
    var sec = $('descubiertas'); if(sec){ sec.style.display = ''; $('gridDesc').innerHTML = '<span class="skel"></span><span class="skel"></span><span class="skel"></span>'; }
    fetch('/web/descubrir?lat=' + lat + '&lng=' + lng).then(function(r){ return r.json(); })
      .then(function(j){ pintarDescubiertas(j.canchas || [], false);
        if((j.canchas || []).length) fetch('/web/descubrir?lat=' + lat + '&lng=' + lng + '&fotos=1').then(function(r){ return r.json(); }).then(function(j2){ if((j2.canchas || []).length) pintarDescubiertas(j2.canchas, true); }).catch(function(){}); })
      .catch(function(){ if(sec) sec.style.display = 'none'; });
  }
  // ── mapa (se dibuja al mostrarlo; split view en escritorio, pantalla completa en móvil) ──
  function pintarMapa(){
    if(mapa || !window.L || !$('mapa')) return;
    mapa = L.map('mapa', {scrollWheelZoom: true}).setView(C.centro, 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; OpenStreetMap'}).addTo(mapa);
    var pts = [];
    cards().forEach(function(c){
      var lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng); if(!lat && !lng) return;
      if(c.classList.contains('pend') && c.dataset.id.indexOf('gp_') === 0) return;
      pts.push([lat, lng]);
      var ok = c.dataset.ok === '1';
      var m = L.marker([lat, lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio' + (ok ? '' : ' pend') + '">' + c.dataset.precio + '</span>', iconSize: null})});
      m._card = c;
      m.bindPopup('<b>' + esc(c.dataset.nombre) + '</b><br>' + esc(c.dataset.sub) + '<br><span style="font-weight:800">' + esc(c.dataset.precio) + ' por hora</span><br><a class="btn' + (ok ? '' : ' sec') + '" href="' + c.getAttribute('href') + '">' + (ok ? 'Ver horarios' : 'Reservar en la app') + '</a>');
      m.on('mouseover', function(){ c.style.outline = '2px solid #0E8F67'; c.style.outlineOffset = '4px'; c.style.borderRadius = '14px'; });
      m.on('mouseout', function(){ c.style.outline = ''; });
      marcadores.push(m); m.addTo(mapa);
    });
    if(yo){ miPin = L.marker([yo.lat, yo.lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio yo">Tú</span>', iconSize: null})}).addTo(mapa); pts.push([yo.lat, yo.lng]); }
    if(pts.length) mapa.fitBounds(L.latLngBounds(pts).pad(0.25), {maxZoom: 13});
    // Las descubiertas ya pintadas también van al mapa.
    var desc = Array.prototype.slice.call(document.querySelectorAll('#gridDesc .lst'));
    desc.forEach(function(c){ var m = L.marker([parseFloat(c.dataset.lat), parseFloat(c.dataset.lng)], {icon: L.divIcon({className: '', html: '<span class="pin-precio pend">' + esc(c.dataset.precio) + '</span>', iconSize: null})}).addTo(mapa);
      m.bindPopup('<b>' + esc(c.dataset.nombre) + '</b><br>' + esc(c.dataset.sub) + '<br><a class="btn sec" href="' + C.play + '">Reservar en la app</a>'); pinesDesc.push(m); });
    aplicar();
  }
  // ── PRIMERA FOTO siempre (como el app): las tarjetas sin foto propia piden
  // la de Google en su ubicación (/web/foto, cacheado en el servidor). ──
  var colaFotos = [], enVuelo = 0, pedidas = {};
  function pintarFotos(card, fotos){
    var box = card.querySelector('.fotos'); if(!box || !fotos || !fotos.length) return;
    fotosConocidas[card.dataset.id] = fotos;
    box.innerHTML = fotos.slice(0, 3).map(function(u){ return '<img src="' + esc(u) + '" alt="" loading="lazy">'; }).join('');
    if(fotos.length > 1){
      var f = card.querySelector('.foto');
      f.insertAdjacentHTML('beforeend', '<button class="flecha izq" aria-label="Anterior">‹</button><button class="flecha der" aria-label="Siguiente">›</button><div class="dots">' + fotos.slice(0, 3).map(function(){ return '<i></i>'; }).join('') + '</div>');
    }
  }
  function pedirFoto(card){
    var q = 'id=' + encodeURIComponent(card.dataset.id || '') + '&nombre=' + encodeURIComponent(card.dataset.nombre || '') +
            '&club=' + encodeURIComponent(card.dataset.club || '') + '&lat=' + card.dataset.lat + '&lng=' + card.dataset.lng;
    fetch('/web/foto?' + q).then(function(r){ return r.json(); }).then(function(j){ pintarFotos(card, (j && j.fotos) || []); })
      .catch(function(){}).then(function(){ enVuelo--; siguienteFoto(); });
  }
  function siguienteFoto(){
    while(enVuelo < 2 && colaFotos.length){ enVuelo++; pedirFoto(colaFotos.shift()); }
  }
  function encolar(c){
    if(pedidas[c.dataset.id]) return;
    if(!parseFloat(c.dataset.lat) && !parseFloat(c.dataset.lng)) return;
    pedidas[c.dataset.id] = 1; colaFotos.push(c); siguienteFoto();
  }
  // Solo se piden las fotos de las tarjetas que ENTRAN en pantalla (cuota de
  // Google): una página con 60 descubiertas no dispara 60 consultas de golpe.
  var obs = ('IntersectionObserver' in window) ? new IntersectionObserver(function(entries){
    entries.forEach(function(en){ if(en.isIntersecting){ obs.unobserve(en.target); encolar(en.target); } });
  }, {rootMargin: '200px 0px'}) : null;
  function resolverFotos(){
    cards().forEach(function(c){
      if(pedidas[c.dataset.id] || c.dataset.obs || !c.querySelector('.sinfoto[data-buscar]')) return;
      c.dataset.obs = '1';
      if(obs) obs.observe(c); else encolar(c);
    });
  }
  var expl = $('expl'), btnMapa = $('btnMapa');
  function verMapa(on){
    expl.classList.toggle('con-mapa', on);
    btnMapa.innerHTML = on ? '<span>Mostrar lista</span> ☰' : '<span>Mostrar mapa</span> 🗺️';
    try { localStorage.setItem('pcg_mapa', on ? '1' : '0'); } catch(e){}
    if(on){ pintarMapa(); setTimeout(function(){ if(mapa) mapa.invalidateSize(); }, 60); }
  }
  if(btnMapa) btnMapa.addEventListener('click', function(){ verMapa(!expl.classList.contains('con-mapa')); });
  var bu = $('btnUbic'); if(bu) bu.addEventListener('click', function(){ ubicar(true); });
  pintarFavs();
  resolverFotos();
  try { var g = JSON.parse(localStorage.getItem('pcg_ubic') || 'null'); if(g && g.lat){ yo = g; ordenar(); } } catch(e){}
  ubicar(false);
  if(!yo) descubrir(C.centro[0], C.centro[1]);
  aplicar();
  try { if(localStorage.getItem('pcg_mapa') === '1' && window.innerWidth > 900) verMapa(true); } catch(e){}
})();
"""

_LUPA = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='3' stroke-linecap='round'>"
         "<circle cx='11' cy='11' r='7'/><path d='M20 20l-3.5-3.5'/></svg>")
_CORAZON = "<svg viewBox='0 0 24 24'><path d='M12 21s-7.5-4.6-9.5-9.2C1.2 8.6 3.2 5 6.8 5c2 0 3.4 1.1 5.2 3 1.8-1.9 3.2-3 5.2-3 3.6 0 5.6 3.6 4.3 6.8C19.5 16.4 12 21 12 21z'/></svg>"
CATEGORIAS = [("", "Todas", "🏟️"), ("futbol", "Fútbol", "⚽"), ("tenis", "Tenis", "🎾"), ("padel", "Pádel", "🏓"),
              ("futsal", "Futsal", "🥅"), ("pickleball", "Pickleball", "🥒"), ("voley", "Vóley", "🏐"),
              ("basquet", "Básquet", "🏀")]


def _zonas_sugeridas(lista: list[dict], n: int = 6) -> list[tuple[str, int]]:
    """Zonas (barrio, distrito) con más canchas, para el desplegable del
    buscador (como "Destinos sugeridos" de Airbnb)."""
    cuenta: dict[str, int] = {}
    for c in lista:
        z = _zona(c)
        if z:
            cuenta[z] = cuenta.get(z, 0) + 1
    return sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def _nav_explorar(dep: str, ses: dict | None = None, zonas: list[tuple[str, int]] | None = None) -> str:
    """Cabecera tal cual airbnb.com: logo · pestañas por deporte con ícono
    (centradas) · "Modo dueño" + avatar + ☰ · buscador grande centrado
    (Dónde · Deporte · Cuándo · Buscar) con desplegable de búsquedas
    recientes y zonas sugeridas bajo "Dónde"."""
    ops = "".join(f"<option value='{k}'{' selected' if k == dep else ''}>{n}</option>" for k, n, _ in CATEGORIAS)
    hoy = date.today().isoformat()
    tabs = "".join(f"<a class='cat{' sel' if k == dep else ''}' href='/canchas{('?deporte=' + k) if k else ''}' data-dep='{k}'>"
                   f"<span class='ico'>{ico}</span>{n}</a>" for k, n, ico in CATEGORIAS)
    sug_zonas = "".join(
        f"<button type='button' class='it' data-zona='{e(z)}'><span class='ic'>📍</span>"
        f"<div><b>{e(z)}</b><small>{n} cancha{'s' if n != 1 else ''}</small></div></button>"
        for z, n in (zonas or []))
    horas = "".join(
        f"<div class='hgrupo'><h5>{t}</h5><div class='hchips'>"
        + "".join(f"<button type='button' class='chip hchip' data-hora='{h:02d}:00'>{h:02d}:00</button>" for h in rango)
        + "</div></div>"
        for t, rango in (("Mañana", range(6, 12)), ("Tarde", range(12, 18)), ("Noche", range(18, 24))))
    busq = (
        "<div class='busq' role='search'>"
        "<label class='seg donde'><small>Dónde</small><input id='sQ' placeholder='Explora zonas, clubes o canchas' autocomplete='off'></label>"
        "<label class='seg cuando'><small>Cuándo</small><input id='sF' placeholder='Agrega fecha' readonly data-iso=''></label>"
        "<label class='seg hora'><small>Hora</small><input id='sH' placeholder='¿A qué hora?' readonly data-hora=''></label>"
        f"<button class='lupa' id='btnBuscar' aria-label='Buscar'>{_LUPA}<span>Buscar</span></button>"
        # Desplegable bajo "Dónde": recientes + zonas sugeridas
        "<div class='sug' id='sugDonde'>"
        "<div id='sugRecientes' style='display:none'><h5>Búsquedas recientes</h5><div id='sugRecientesLista'></div></div>"
        "<h5>Zonas sugeridas</h5>"
        "<button type='button' class='it cerca' data-cerca='1'><span class='ic'>🧭</span>"
        "<div><b>Cerca de ti</b><small>Descubre canchas a tu alrededor</small></div></button>"
        f"{sug_zonas}</div>"
        # Calendario bajo "Cuándo" (dos meses, como Airbnb)
        "<div class='sug centro cal-panel' id='panCuando'>"
        "<div class='cal-modo'><button type='button' class='on' data-modo='fecha'>Fecha</button>"
        "<button type='button' data-modo='libre'>Cualquier día</button></div>"
        "<div class='cal-nav'><button type='button' class='cal-ant' aria-label='Mes anterior'>‹</button>"
        "<button type='button' class='cal-sig' aria-label='Mes siguiente'>›</button></div>"
        "<div class='cal-meses' id='calMeses'></div>"
        "<div class='cal-atajos' id='calAtajos'></div></div>"
        # Horas bajo "Hora"
        "<div class='sug der hora-panel' id='panHora'>"
        "<button type='button' class='it' data-hora=''><span class='ic'>🕐</span>"
        "<div><b>Cualquier hora</b><small>Muestra todas las canchas abiertas</small></div></button>"
        "<div class='hora-aviso' id='horaAviso' style='display:none'>Hoy ya no quedan horas por delante. Elige otro día en “Cuándo”.</div>"
        f"{horas}</div>"
        "</div>")
    return ui.cabecera(tabs=tabs, busq=busq, ses=ses, volver="/")


AMENIDAD_ICONO = {"estacionamiento": "🅿️", "vestuarios": "👕", "duchas": "🚿", "iluminacion": "💡", "techada": "🏠",
                  "cafeteria": "☕", "wifi": "📶", "tribuna": "🪑", "seguridad": "🛡️"}
_RECOMENDADAS = ("estacionamiento", "iluminacion", "vestuarios", "techada")


def _amenidades_de(lista: list[dict]) -> list[tuple[str, int]]:
    """Amenidades presentes en las canchas listadas, de más a menos común."""
    cuenta: dict[str, int] = {}
    for c in lista:
        for a in c.get("amenidades") or []:
            a = str(a).strip().lower()
            if a:
                cuenta[a] = cuenta.get(a, 0) + 1
    return sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0]))


def _barra_filtros(lista: list[dict]) -> str:
    """Como la barra de Airbnb bajo el buscador: botón "Filtros" + chips
    rápidos con las amenidades más comunes (aplican al instante)."""
    chips = "".join(
        f"<button type='button' class='chip qam' data-am='{e(a)}'>{AMENIDAD_ICONO.get(a, '✓')} {e(AMENIDAD_NOMBRE.get(a, a.capitalize()))}</button>"
        for a, _n in _amenidades_de(lista)[:6])
    return ("<div class='barra-filtros'>"
            "<button type='button' class='filtros' id='btnFiltros'><span class='ico'>⚙️</span> Filtros<span class='n' id='nFiltros' style='display:none'></span></button>"
            f"<div class='qchips'>{chips}</div></div>")


def _modal_filtros(lista: list[dict]) -> str:
    """Modal "Filtros" tal cual Airbnb: recomendados (tarjetas con ícono),
    tipo de local, rango de precios con histograma y dos topes, servicios del
    local, superficie y duración del turno; pie con "Limpiar filtros" y
    "Mostrar N canchas". Todo se cuenta en vivo y se aplica al pulsar Mostrar."""
    ams = _amenidades_de(lista)
    presentes = {a for a, _ in ams}
    recomendadas = [a for a in _RECOMENDADAS if a in presentes] or [a for a, _ in ams[:4]]
    tiles = "".join(
        f"<button type='button' class='tile' data-am='{e(a)}'><span class='ico'>{AMENIDAD_ICONO.get(a, '✓')}</span>"
        f"<span>{e(AMENIDAD_NOMBRE.get(a, a.capitalize()))}</span></button>" for a in recomendadas)
    servicios = "".join(
        f"<button type='button' class='chip fam' data-am='{e(a)}'>{AMENIDAD_ICONO.get(a, '✓')} {e(AMENIDAD_NOMBRE.get(a, a.capitalize()))}"
        f" <small>({n})</small></button>" for a, n in ams)
    sups = sorted({(c.get("superficie") or "").strip().lower() for c in lista} - {""})
    superficies = "".join(f"<button type='button' class='chip fsup' data-sup='{e(x)}'>{e(x.capitalize())}</button>" for x in sups)
    durs = sorted({int(c.get("duracion_slot_min") or 60) for c in lista})
    duraciones = "".join(f"<button type='button' class='chip fdur' data-dur='{d}'>{d} min</button>" for d in durs)
    return (
        "<div class='modal' id='modalFiltros' role='dialog' aria-modal='true' aria-labelledby='modalTit'>"
        "<div class='modal-caja'>"
        "<div class='modal-cab'><button type='button' class='cerrar' id='cerrarFiltros' aria-label='Cerrar'>✕</button><h3 id='modalTit'>Filtros</h3></div>"
        "<div class='modal-cuerpo'>"
        + (f"<section><h4>Recomendado para ti</h4><div class='tiles'>{tiles}</div></section>" if tiles else "")
        + "<section><h4>Tipo de local</h4><div class='segm' id='fTipo'>"
        "<button type='button' class='on' data-tipo=''>Cualquier tipo</button>"
        "<button type='button' data-tipo='ok'>Verificadas</button>"
        "<button type='button' data-tipo='pend'>Aún sin verificar</button></div></section>"
        "<section><h4>Rango de precios</h4><p class='sub' id='precioSub'>Precio por hora</p>"
        "<div class='histo' id='histo'></div>"
        "<div class='rango'><input type='range' id='rMin' min='0' max='100' value='0'><input type='range' id='rMax' min='0' max='100' value='100'></div>"
        "<div class='topes'><label>Mínimo<div class='tope'><span id='monMin'></span><input type='number' id='pMin' min='0'></div></label>"
        "<label>Máximo<div class='tope'><span id='monMax'></span><input type='number' id='pMax' min='0'></div></label></div></section>"
        + (f"<section><h4>Servicios del local</h4><div class='chips'>{servicios}</div></section>" if servicios else "")
        + (f"<section><h4>Superficie</h4><div class='chips'>{superficies}</div></section>" if superficies else "")
        + (f"<section><h4>Duración del turno</h4><div class='chips'>{duraciones}</div></section>" if len(durs) > 1 else "")
        + "</div>"
        "<div class='modal-pie'><button type='button' class='limpiar' id='limpiarFiltros'>Limpiar filtros</button>"
        "<button type='button' class='btn dark' id='mostrarFiltros'>Mostrar canchas</button></div>"
        "</div></div>")


def _tarjeta(c: dict, rating: tuple[float, int] | None, fecha: str = "") -> str:
    sim, _iso = _moneda_de(c)
    deps = _deportes_de(c)
    deps_txt = " · ".join(_deporte(d)[0] for d in deps[:3])
    texto = f"{c['nombre']} {c.get('club', '')} {_zona(c)} {deps_txt} {c.get('direccion', '')}".lower()
    sub = " · ".join(x for x in (c.get("club"), _zona(c)) if x)
    ok = datos.reservable(c)
    fs = _fotos(c)
    if fs:
        fotos = "".join(f"<img src='{e(u)}' alt='' loading='lazy'>" for u in fs[:5])
    else:
        fotos = f"<div class='sinfoto' data-buscar='1'>{_deporte(c.get('deporte'))[1]}</div>"
    extra = ""
    if len(fs) > 1:
        extra = ("<button class='flecha izq' aria-label='Anterior'>‹</button><button class='flecha der' aria-label='Siguiente'>›</button>"
                 f"<div class='dots'>{''.join('<i></i>' for _ in fs[:5])}</div>")
    badge = "<span class='badge'>✓ Verificada</span>" if ok else "<span class='badge pend'>Aún sin verificar</span>"
    if rating and rating[1] > 0:
        rate = f"<span class='rate'>★ {rating[0]:.1f}".replace(".", ",") + f" <span style='color:var(--tenue);font-weight:600'>({rating[1]})</span></span>"
    else:
        rate = "<span class='rate' style='color:var(--tenue);font-weight:600'>Nuevo</span>"
    base = f"/reservar/{c['id']}"
    href = base + (f"?fecha={fecha}" if fecha else "")
    l3 = (f"<div class='l3'><b>{e(sim)} {c['precio_hora']:.0f}</b> <span style='color:var(--tenue)'>por hora</span></div>"
          if ok else
          f"<div class='l3'><b>{e(sim)} {c['precio_hora']:.0f}</b> <span style='color:var(--tenue)'>por hora</span>"
          "<br><span class='app'>📲 Reservar en la app</span></div>")
    return (f"<a class='lst{'' if ok else ' pend'}' href='{e(href)}' data-base='{e(base)}' data-id='{e(c['id'])}' data-t='{e(texto)}' "
            f"data-ap='{e(c.get('hora_apertura') or '07:00')}' data-ci='{e(c.get('hora_cierre') or '23:00')}' data-paso='{int(c.get('duracion_slot_min') or 60)}' "
            f"data-am='{e(' '.join(str(a) for a in (c.get('amenidades') or [])))}' data-sup='{e((c.get('superficie') or '').strip().lower())}' data-mon='{e(sim)}' "
            f"data-deps='{e(' '.join(deps))}' data-lat='{c.get('lat')}' data-lng='{c.get('lng')}' data-nombre='{e(c['nombre'])}' data-club='{e(c.get('club', ''))}' "
            f"data-sub='{e(sub)}' data-precio='{e(sim)} {c['precio_hora']:.0f}' data-pnum='{c['precio_hora']:.2f}' data-ok='{1 if ok else 0}'>"
            f"<div class='foto'><div class='fotos'>{fotos}</div>{badge}"
            f"<button class='corazon' aria-label='Guardar'>{_CORAZON}</button>{extra}</div>"
            f"<div class='lb'><div class='l1'><b>{e(c['nombre'])}</b>{rate}</div>"
            f"<div class='l2'>{e(sub) or e(c.get('direccion', ''))}</div>"
            f"<div class='l2'>{e(deps_txt)} · {e(c.get('hora_apertura') or '07:00')}–{e(c.get('hora_cierre') or '23:00')} · {c['duracion_slot_min']} min <span class='dist'></span></div>"
            f"{l3}</div></a>")


def _explorar(deporte: str = "", fecha: str = "", request: Request | None = None, hora: str = "") -> HTMLResponse:
    """RAÍZ del dominio, tipo Airbnb: buscador en pastilla, categorías por
    deporte, grilla de tarjetas con foto/corazón/★, "Mostrar mapa" (split
    view en escritorio), cercanía por ubicación y canchas descubiertas en
    Google; debajo, las secciones de marca/comercio (servicios y precios,
    términos, cancelaciones, Libro de Reclamaciones) que revisan Culqi e
    INDECOPI."""
    todas = datos.canchas_publicas()
    dep = (deporte or "").strip().lower()
    lista = [c for c in todas if not dep or dep in _deportes_de(c)]
    fecha = fecha if _es_iso(fecha) else ""
    ratings = datos.ratings([c["id"] for c in lista])
    por_pais: dict[str, list[dict]] = {}
    for c in lista:
        por_pais.setdefault(_pais_de(c), []).append(c)
    cuerpo = ("<div class='ubic-mini'><span>📍</span><span id='ubicTxt'>Permite tu ubicación para ver primero las canchas más cercanas.</span>"
              "<button id='btnUbic'>Usar mi ubicación</button><span id='resBusq'></span></div>")
    cuerpo += _barra_filtros(lista) + _modal_filtros(lista)
    cuerpo += "<div class='expl' id='expl'><div class='lista'><div id='grupos'>"
    for pais in ("PE", "EC", "BO"):
        lst = por_pais.get(pais) or []
        if not lst:
            continue
        cards = "".join(_tarjeta(c, ratings.get(c["id"]), fecha) for c in lst)
        cuerpo += (f"<section class='grupo-pais' data-pais='{pais}'><div class='tit'><h2>{ui.bandera(pais)} Canchas en {NOMBRE_PAIS[pais]}"
                   f"<span class='cerca'></span></h2></div><div class='lst-grid'>{cards}</div></section>")
    cuerpo += "</div>"
    if not lista:
        cuerpo += ("<div class='vacio' id='vacio'><h3>Todavía no hay canchas publicadas aquí</h3>"
                   "<p class='sub'>Estamos sumando locales. En la app ya puedes explorar el mapa completo.</p>"
                   f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    else:
        cuerpo += "<div class='vacio' id='vacio' data-base='' style='display:none'>No hay canchas libres con esa búsqueda. Prueba con otra zona, día u hora.</div>"
    if todas and not lista:
        cuerpo += ("<div class='vacio'>Todavía no hay canchas de este deporte. "
                   "<a href='/canchas'>Ver todas las canchas</a></div>")
    cuerpo += ("<section id='descubiertas' style='display:none'><div class='tit'><h2>Más canchas cerca de ti</h2></div>"
               "<p class='sub' style='margin:-4px 0 12px'>Locales que aún no están en Pichangol. Reserva desde la app o, si es tu "
               "cancha, ¡Reclámala! y empieza a recibir reservas.</p><div class='lst-grid' id='gridDesc'></div></section>")
    cuerpo += "</div><aside class='mapa-lado'><div class='mapa' id='mapa' aria-label='Mapa de canchas'></div></aside></div>"
    cuerpo += "<button class='btn-mapa' id='btnMapa'><span>Mostrar mapa</span> 🗺️</button>"
    css_m, html_m, js_m = marca.secciones()
    if html_m:
        cuerpo += f"<div class='marca'>{html_m}</div>"
    centro = list(CIUDAD_DEFECTO["PE"])
    if lista:
        c0 = lista[0]
        centro = [c0.get("lat") or centro[0], c0.get("lng") or centro[1]]
    hora = hora if horarios.hora_en_minutos(hora) is not None else ""
    cfg = json.dumps({"cajas": {k: list(v) for k, v in _CAJAS.items()}, "centro": centro, "play": PLAY_URL, "dep": dep,
                      "fecha": fecha, "hora": hora, "diasAdelante": DIAS_ADELANTE})
    head = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
            "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>"
            + (f"<style>{css_m}</style>" if css_m else ""))
    cuerpo += f"<script>window.__explorar={cfg};</script><script>{_JS_EXPLORAR}</script>"
    if js_m:
        cuerpo += f"<script>{js_m}</script>"
    canonical = f"{config.PUBLIC_BASE_URL.rstrip('/')}/" if getattr(config, "PUBLIC_BASE_URL", "") else ""
    ses = sesion.de_request(request)
    return ui.shell("Pichangol", cuerpo, extra_head=head, nav=_nav_explorar(dep, ses, _zonas_sugeridas(lista)), ancho=True, sesion=ses,
                    titulo_tab="Pichangol · Reserva canchas de fútbol, tenis y pádel", canonical=canonical,
                    desc="Reserva canchas de fútbol, tenis y pádel cerca de ti y paga con Yape o tarjeta. Perú, Ecuador y Bolivia.")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def pagina_inicio(request: Request, deporte: str = "", fecha: str = "", hora: str = "") -> HTMLResponse:
    return _explorar(deporte, fecha, request, hora)


@router.get("/canchas", response_class=HTMLResponse)
def pagina_canchas(request: Request, deporte: str = "", fecha: str = "", hora: str = "") -> HTMLResponse:
    """Alias histórico del explorador (enlaces de la app, la home y el pie)."""
    return _explorar(deporte, fecha, request, hora)


# ── descubrir (Google Places, como el APK) ────────────────────────────────────

@router.get("/web/descubrir")
def descubrir_web(lat: float, lng: float, fotos: int = 0) -> dict:
    """Canchas que Google conoce cerca del usuario y aún no están en Pichangol:
    salen en el explorador con "Reservar en la app". Misma Edge Function y
    heurística que el APK; caché por zona."""
    region = pais_de_coordenadas(lat, lng)
    reg = [{"nombre": c.get("nombre"), "club": c.get("club"), "lat": c.get("lat"), "lng": c.get("lng")}
           for c in datos.canchas_publicas()]
    lista = descubrir.descubrir_cerca(lat, lng, region=region, fotos=bool(fotos), registradas=reg)
    for c in lista:
        c["deporte_nombre"], c["emoji"] = _deporte(c["deporte"])
        if c.get("fotos"):
            descubrir.recordar_fotos_edge(c)  # cosecha gratis: ya las pagó la Edge
    return {"ok": True, "region": region, "canchas": lista}


# ── sesión con Google (mismo flujo que el APK) ────────────────────────────────

class SesionReq(BaseModel):
    credential: str


@router.post("/web/sesion")
def abrir_sesion(req: SesionReq, response: Response) -> dict:
    """Recibe el ID token del botón de Google, lo verifica y deja la cookie
    firmada de sesión (30 días). Sin `GOOGLE_WEB_CLIENT_ID` → no disponible."""
    if not sesion.activo():
        return {"ok": False, "error": "no_configurado"}
    u = sesion.verificar_id_token(req.credential)
    if not u:
        return {"ok": False, "error": "token_invalido"}
    sesion.poner_cookie(response, sesion.emitir(u))
    return {"ok": True, **u}


@router.post("/web/salir")
def cerrar_sesion(response: Response) -> dict:
    sesion.borrar_cookie(response)
    return {"ok": True}


@router.get("/web/sesion")
def ver_sesion(request: Request) -> dict:
    u = sesion.de_request(request)
    return {"ok": True, "activo": sesion.activo(), "sesion": u}


def _volver_seguro(volver: str) -> str:
    v = (volver or "").strip()
    return v if v.startswith("/") and not v.startswith("//") else "/"


@router.get("/entrar", response_class=HTMLResponse)
def pagina_entrar(request: Request, volver: str = "/") -> HTMLResponse:
    """Inicio de sesión con Google (como en el app). Al entrar vuelve a la
    página desde la que se pidió (`volver`)."""
    v = _volver_seguro(volver)
    ses = sesion.de_request(request)
    if ses or not sesion.activo():
        return HTMLResponse("", status_code=302, headers={"Location": v})
    cuerpo = ("<div class='panel' style='max-width:460px;margin:40px auto;text-align:center'>"
              f"<div style='margin-bottom:8px'>{ui.wordmark(26, '/')}</div>"
              "<h1 style='font-size:22px'>Inicia sesión para reservar</h1>"
              "<p class='sub'>Usa tu cuenta de Google, la misma del app: tus reservas quedan en "
              "\"Mis reservas\" y el comprobante llega a tu correo.</p>"
              f"<div style='display:flex;justify-content:center;margin:22px 0 10px'>{sesion.boton_google()}</div>"
              "<div class='estado bad' id='sesionErr'></div>"
              "<p class='sub' style='font-size:12.5px'>Al continuar aceptas los <a href='/legal/terminos'>términos</a> y la "
              "<a href='/legal/privacidad'>política de privacidad</a>.</p></div>"
              f"<script>window.alIniciarSesion=function(){{location.href={json.dumps(v)};}};{sesion.JS_SESION}</script>")
    return ui.shell("Iniciar sesión", cuerpo, extra_head=sesion.GIS_SCRIPT, sesion=None)


@router.get("/web/foto")
def foto_web(id: str = "", nombre: str = "", club: str = "", lat: float = 0.0, lng: float = 0.0,
             refrescar: int = 0, token: str = "") -> dict:
    """PRIMERA FOTO de una cancha sin fotos propias (regla del director: la web
    muestra siempre la primera foto, como el app). Para una cancha registrada
    (`id`) usa sus fotos si las tiene; si no, resuelve las de Google en su
    ubicación (mismo criterio que `enriquecerSembradas` del APK). Para una
    descubierta (`gp_…`) o cualquier lugar, por nombre + coordenadas."""
    c = datos.cancha(id) if id and not id.startswith("gp_") else None
    if c:
        propias = _fotos(c)
        if propias:
            return {"ok": True, "fotos": propias[:5], "origen": "propias"}
        nombre, club = c.get("nombre") or nombre, c.get("club") or club
        lat, lng = c.get("lat") or lat, c.get("lng") or lng
    if not (nombre or club) or (not lat and not lng):
        return {"ok": False, "fotos": []}
    region = pais_de_coordenadas(lat, lng)
    place_id = id[3:] if id.startswith("gp_") else ""
    # `refrescar=1` + token de admin: salta cachés y cosecha (diagnóstico).
    forzar = bool(refrescar) and bool(config.ADMIN_PANEL_TOKEN) and hmac.compare_digest(token or "", config.ADMIN_PANEL_TOKEN)
    fotos = descubrir.fotos_de_lugar(nombre, club, lat, lng, region=region, place_id=place_id,
                                     cancha_id="" if place_id else id, forzar=forzar)
    return {"ok": True, "fotos": fotos, "origen": "google" if fotos else ""}


# ── disponibilidad ────────────────────────────────────────────────────────────

def _fechas_validas(pais: str) -> tuple[str, str]:
    hoy = horarios.ahora_local(pais).date()
    return hoy.isoformat(), (hoy + timedelta(days=DIAS_ADELANTE)).isoformat()


def _slots_del_dia(c: dict, fecha: str) -> list[dict]:
    """Slots del día con precio y estado. Hoy: se omiten los que ya pasaron."""
    pais = _pais_de(c)
    ahora = horarios.ahora_local(pais)
    desde = None
    if fecha == ahora.date().isoformat():
        desde = ahora.hour * 60 + ahora.minute + 1
    paso = c["duracion_slot_min"]
    horas = horarios.slots(c["hora_apertura"], c["hora_cierre"], paso, desde)
    fechas = sorted({horarios.fecha_real(fecha, c["hora_apertura"], c["hora_cierre"], h) for h in horas} | {fecha})
    ocup = datos.ocupados(c["id"], fechas)
    desc = datos.descuentos(c["id"], fechas)
    out = []
    for h in horas:
        fr = horarios.fecha_real(fecha, c["hora_apertura"], c["hora_cierre"], h)
        ph = horarios.precio_hora_en(c["precio_hora"], h, c["descuento_valle"],
                                     c["valle_desde"], c["valle_hasta"])
        out.append({
            "hora": h, "fin": horarios.hora_fin(h, paso), "fecha": fr,
            "precio": horarios.precio_slot(ph, paso, desc.get((fr, h), 0)),
            "ocupado": (fr, h) in ocup,
            "valle": c["descuento_valle"] > 0 and horarios.es_valle(h, c["valle_desde"], c["valle_hasta"]),
            "promo": desc.get((fr, h), 0),
        })
    return out


@router.get("/web/disponibilidad/{cancha_id}")
def disponibilidad(cancha_id: str, fecha: str = "") -> dict:
    c = datos.cancha(cancha_id)
    if not c:
        return {"ok": False, "error": "no_encontrada"}
    d_min, d_max = _fechas_validas(_pais_de(c))
    if not fecha or not _es_iso(fecha):
        return {"ok": False, "error": "fecha_invalida"}
    if not (d_min <= fecha <= d_max):
        return {"ok": False, "error": "fecha_fuera_de_rango", "min": d_min, "max": d_max}
    sim, iso = _moneda_de(c)
    return {"ok": True, "fecha": fecha, "moneda": sim, "moneda_iso": iso,
            "slots": _slots_del_dia(c, fecha)}


def _hora_libre(c: dict, fecha: str, hora: str, ocup: set[tuple[str, str]]) -> bool:
    """¿Hay un turno LIBRE que cubra [hora] ese día? (inicio <= hora < fin,
    misma lógica de slots, madrugada y turnos ya pasados que la ficha)."""
    h = horarios.hora_en_minutos(hora)
    if h is None:
        return False
    ap, ci = c["hora_apertura"], c["hora_cierre"]
    ini = horarios.hora_en_minutos(ap)
    if ini is not None and h < ini and horarios.slot_es_madrugada(ap, ci, hora):
        h += 24 * 60  # 00:30 en una cancha 18:00→02:00 es la madrugada del día siguiente
    ahora = horarios.ahora_local(_pais_de(c))
    desde = ahora.hour * 60 + ahora.minute + 1 if fecha == ahora.date().isoformat() else None
    paso = c["duracion_slot_min"]
    for s_ in horarios.slots(ap, ci, paso, desde):
        m = horarios.hora_en_minutos(s_)
        if m is None:
            continue
        if m < (ini or 0):
            m += 24 * 60
        if m <= h < m + paso:
            return (horarios.fecha_real(fecha, ap, ci, s_), s_) not in ocup
    return False


@router.get("/web/libres")
def libres(fecha: str = "", hora: str = "") -> dict:
    """Buscador de la portada: qué canchas reservables tienen un turno libre
    que cubra [hora] el día [fecha] (una sola consulta de ocupados para todas)."""
    if not fecha or not _es_iso(fecha) or horarios.hora_en_minutos(hora) is None:
        return {"ok": False, "error": "parametros_invalidos"}
    hoy = horarios.ahora_local("PE").date()
    try:
        d = date.fromisoformat(fecha)
    except ValueError:
        return {"ok": False, "error": "parametros_invalidos"}
    if not (hoy - timedelta(days=1) <= d <= hoy + timedelta(days=DIAS_ADELANTE + 1)):
        return {"ok": False, "error": "fecha_fuera_de_rango"}
    canchas = [c for c in datos.canchas_publicas() if datos.reservable(c)]
    fechas = [fecha, (d + timedelta(days=1)).isoformat()]
    ocup = datos.ocupados_varias([c["id"] for c in canchas], fechas)
    out = {c["id"]: _hora_libre(c, fecha, hora, ocup.get(c["id"], set())) for c in canchas}
    return {"ok": True, "fecha": fecha, "hora": hora, "libres": out}


def _es_iso(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


# ── página de reserva ─────────────────────────────────────────────────────────

_JS_RESERVA = r"""
(function(){
  var C = window.__cancha, sel = {}, slots = [], hold = null, fechaSel = C.fecha || C.hoy;
  var $ = function(id){ return document.getElementById(id); };
  var fmt = function(n){ return C.moneda + ' ' + Number(n).toFixed(2); };
  var esc = function(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  function extrasSel(){
    return Array.prototype.map.call(document.querySelectorAll('input[name=extra]:checked'), function(x){
      return {clave: x.dataset.clave, nombre: x.dataset.nombre, precio: parseFloat(x.value)||0}; });
  }
  function total(){
    var t = 0; Object.keys(sel).forEach(function(k){ t += sel[k].precio; });
    extrasSel().forEach(function(x){ t += x.precio; });
    return t;
  }
  function pintarResumen(){
    var ks = Object.keys(sel).sort(), n = ks.length, t = total();
    var h = '';
    if(!n){ h = '<div class="linea"><span style="color:var(--tenue)">Elige un horario para ver tu resumen.</span></div>'; }
    else {
      ks.forEach(function(k){ var s = sel[k];
        h += '<div class="linea"><span>' + esc(C.etiquetas[s.fecha] || s.fecha) + ' · ' + s.hora + '–' + s.fin + '</span><b>' + fmt(s.precio) + '</b></div>'; });
      extrasSel().forEach(function(x){ h += '<div class="linea"><span>' + esc(x.nombre) + '</span><b>' + fmt(x.precio) + '</b></div>'; });
    }
    $('lineas').innerHTML = h;
    $('tot').textContent = fmt(t); $('totBarra').textContent = fmt(t);
    var txt = n ? ('Reservar y pagar ' + fmt(t)) : 'Elige un horario';
    ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = !n; $(id).textContent = txt; });
  }
  function pintarDias(){
    $('dias').innerHTML = C.dias.map(function(d){
      return '<span class="chip' + (d.iso === fechaSel ? ' sel' : '') + '" data-f="' + d.iso + '"><b>' + esc(d.corto) + '</b><small>' + esc(d.sub) + '</small></span>';
    }).join('');
    document.querySelectorAll('#dias .chip').forEach(function(el){
      el.addEventListener('click', function(){ if(el.dataset.f === fechaSel) return; liberar(); fechaSel = el.dataset.f; pintarDias(); cargar(); });
    });
  }
  function cargar(){
    sel = {}; pintarResumen();
    $('slots').innerHTML = '<span class="skel"></span><span class="skel"></span><span class="skel"></span><span class="skel"></span>';
    fetch('/web/disponibilidad/' + encodeURIComponent(C.id) + '?fecha=' + fechaSel)
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){ $('slots').innerHTML = '<span class="sub">No pudimos cargar los horarios de ese día.</span>'; return; }
        slots = j.slots;
        var libres = slots.filter(function(s){ return !s.ocupado; }).length;
        if(!slots.length){
          if(fechaSel === C.hoy && !C.fecha && !C._salto && C.dias[1]){ C._salto = true; fechaSel = C.dias[1].iso; pintarDias(); cargar(); return; }
          $('slots').innerHTML = '<span class="sub">No quedan turnos para este día. Prueba otra fecha.</span>'; return; }
        $('slots').innerHTML = slots.map(function(s, i){
          var cls = 'chip' + (s.ocupado ? ' off' : '');
          var extra = s.fecha !== fechaSel ? ' <small>' + esc(C.etiquetas[s.fecha] || '') + '</small>' : '';
          var tag = s.promo ? ' · −' + s.promo + '%' : (s.valle ? ' · hora feliz' : '');
          return '<span class="' + cls + '" data-i="' + i + '" title="' + (s.ocupado ? 'Ocupado' : 'Disponible') + '">' + s.hora + '–' + s.fin + extra +
                 ' <small>' + fmt(s.precio) + tag + '</small></span>';
        }).join('') + (libres ? '' : '<div class="sub" style="width:100%">Todos los turnos de este día están tomados.</div>');
        document.querySelectorAll('#slots .chip').forEach(function(el){
          el.addEventListener('click', function(){
            var s = slots[parseInt(el.dataset.i)];
            if(s.ocupado) return;
            var k = s.fecha + '|' + s.hora;
            if(sel[k]){ delete sel[k]; el.classList.remove('sel'); }
            else {
              if(Object.keys(sel).length >= C.maxSlots){ mostrarError('Puedes reservar hasta ' + C.maxSlots + ' turnos por pedido.'); return; }
              sel[k] = s; el.classList.add('sel'); ocultarError();
            }
            pintarResumen();
          });
        });
        if(C.hora && !C._horaOk){
          C._horaOk = true;
          var hm = function(t){ var p = t.split(':'); return parseInt(p[0]) * 60 + parseInt(p[1]); };
          var want = hm(C.hora);
          for(var j = 0; j < slots.length; j++){
            var a = hm(slots[j].hora), b = hm(slots[j].fin); if(b <= a) b += 1440;
            var ww = want < a && b > 1440 ? want + 1440 : want;
            if(!slots[j].ocupado && a <= ww && ww < b){ var chip = document.querySelector('#slots .chip[data-i="' + j + '"]'); if(chip){ chip.click(); chip.scrollIntoView({behavior: 'smooth', block: 'center'}); } break; }
          }
        }
      }).catch(function(){ $('slots').innerHTML = '<span class="sub">No pudimos cargar los horarios.</span>'; });
  }
  function mostrarError(m){ var el = $('err'); el.textContent = m; el.style.display = 'block'; el.scrollIntoView({behavior:'smooth', block:'center'}); }
  function ocultarError(){ $('err').style.display = 'none'; }
  function datos(){
    var email = (C.login && C.sesion) ? C.sesion.email : $('email').value.trim().toLowerCase();
    return { nombre: $('nombre').value.trim(), celular: $('celular').value.trim(), email: email };
  }
  // Login con Google (como el app): al entrar, se muestran los datos sin recargar.
  window.alIniciarSesion = function(u){
    C.sesion = u;
    var lb = $('loginBox'), db = $('datosBox'); if(lb) lb.style.display = 'none'; if(db) db.style.display = '';
    if($('nombre') && !$('nombre').value) $('nombre').value = u.nombre || '';
    if($('email')) $('email').value = u.email || '';
    if(db && !$('quien')){ db.insertAdjacentHTML('afterbegin', '<div class="quien" id="quien">' + (u.foto ? '<img src="' + esc(u.foto) + '" alt="">' : '') + '<div><b>' + esc(u.nombre || u.email) + '</b><div class="m">' + esc(u.email) + '</div></div><button type="button" class="btn sec" onclick="cerrarSesion()">Cambiar cuenta</button></div>'); }
    pintarResumen();
  };
  function validar(d){
    if(!Object.keys(sel).length) return 'Elige al menos un horario.';
    if(C.login && !C.sesion) return 'Inicia sesión con Google para reservar.';
    if(d.nombre.length < 3) return 'Escribe tu nombre.';
    if(d.celular.replace(/\D/g,'').length < 8) return 'Escribe un celular válido.';
    if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email)) return 'Escribe un correo válido: ahí va tu comprobante.';
    return '';
  }
  function liberar(){
    if(!hold) return;
    var h = hold; hold = null;
    fetch('/web/liberar', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ids: h.ids, firma: h.firma})}).catch(function(){});
  }
  function pagar(){
    ocultarError();
    var d = datos(), v = validar(d);
    if(v){ mostrarError(v); if(!Object.keys(sel).length) $('slots').scrollIntoView({behavior:'smooth', block:'center'}); else ($('loginBox') && !C.sesion ? $('loginBox') : $('nombre')).scrollIntoView({behavior:'smooth', block:'center'}); return; }
    var extras = extrasSel().map(function(x){ return x.clave; });
    var horas = Object.keys(sel).map(function(k){ return {fecha: sel[k].fecha, hora: sel[k].hora}; });
    var deporte = ($('deporte') && $('deporte').value) || '';
    ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = true; $(id).textContent = 'Reservando tu horario…'; });
    fetch('/web/asegurar', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({cancha_id: C.id, horas: horas, extras: extras, deporte: deporte, nombre: d.nombre, celular: d.celular, email: d.email})})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){
          pintarResumen();
          if(j.error === 'ocupado'){ mostrarError('Alguien acaba de tomar uno de esos horarios. Elige otro, por favor.'); cargar(); }
          else if(j.error === 'sesion_requerida'){ C.sesion = null; mostrarError('Tu sesión venció. Inicia sesión con Google para reservar.'); var lb = $('loginBox'), db = $('datosBox'); if(lb) lb.style.display = ''; if(db) db.style.display = 'none'; }
          else mostrarError('No pudimos reservar el horario. Inténtalo de nuevo.');
          return;
        }
        hold = j;
        if(!C.pk){ mostrarError('El pago en línea no está disponible por ahora.'); liberar(); pintarResumen(); return; }
        Culqi.publicKey = C.pk;
        Culqi.settings({ title: 'Pichangol', currency: 'PEN', amount: j.total_centimos });
        Culqi.options({ lang: 'es', installments: false,
          paymentMethods: { tarjeta: true, yape: true, bancaMovil: false, agente: false, billetera: false, cuotealo: false },
          style: { logo: C.logo, bannerColor: '#0F1B2D', buttonBackground: '#0E8F67', buttonText: 'Pagar ' + fmt(j.total), buttonTextColor: '#FFFFFF' } });
        window.culqi = function(){
          if(Culqi.token){
            var token = Culqi.token.id, medio = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
            Culqi.close();
            ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).textContent = 'Confirmando tu pago…'; });
            var h = hold; hold = null;
            fetch('/web/pagar', {method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({ids: h.ids, firma: h.firma, token: token, medio: medio, email: d.email})})
              .then(function(r){ return r.json(); })
              .then(function(p){
                if(p.ok){ window.location.href = p.url; }
                else { hold = null; mostrarError(p.mensaje || 'El pago no se pudo procesar. No se te cobró nada.'); pintarResumen(); cargar(); }
              }).catch(function(){ mostrarError('No pudimos confirmar el pago. Escríbenos a contacto@ebim.pe con tu correo y horario.'); pintarResumen(); });
          } else if(Culqi.order){
            mostrarError('Este medio de pago no está habilitado. Usa Yape o tarjeta.');
          } else {
            mostrarError((Culqi.error && Culqi.error.user_message) || 'No se pudo procesar el pago.');
          }
        };
        Culqi.open();
        var chk = setInterval(function(){
          var abierto = document.getElementById('culqi-container') || document.querySelector('iframe[src*="culqi"]');
          if(!abierto && hold){ clearInterval(chk); liberar(); pintarResumen(); }
          if(!hold) clearInterval(chk);
        }, 1500);
      }).catch(function(){ pintarResumen(); mostrarError('No pudimos reservar el horario. Inténtalo de nuevo.'); });
  }
  $('btnPagar').addEventListener('click', pagar);
  $('btnPagarBarra').addEventListener('click', pagar);
  document.querySelectorAll('input[name=extra]').forEach(function(x){ x.addEventListener('change', pintarResumen); });
  window.addEventListener('beforeunload', liberar);
  pintarDias(); cargar();
})();
"""


def _tira_dias(pais: str) -> tuple[list[dict], dict]:
    hoy = horarios.ahora_local(pais).date()
    dias, etiquetas = [], {}
    for i in range(DIAS_TIRA):
        d = hoy + timedelta(days=i)
        iso = d.isoformat()
        et = horarios.etiqueta_dia(iso, hoy)
        corto = et if i < 2 else horarios.DIAS[d.weekday()]
        sub = f"{d.day} {horarios.MESES[d.month - 1]}"
        dias.append({"iso": iso, "corto": corto, "sub": sub})
        etiquetas[iso] = et if i < 2 else f"{horarios.DIAS[d.weekday()]} {d.day}"
    for i in range(DIAS_TIRA, DIAS_ADELANTE + 2):
        d = hoy + timedelta(days=i)
        etiquetas[d.isoformat()] = f"{horarios.DIAS[d.weekday()]} {d.day}"
    return dias, etiquetas


def _ficha(c: dict, sim: str, pais: str, verificada: bool = True) -> str:
    sello = ui.sello_verificada() if verificada else "<span class='pill gris'>Aún sin verificar</span>"
    lugar = ", ".join(x for x in (c.get("direccion"), _zona(c)) if x)
    deps = " · ".join(_deporte(d)[0] for d in _deportes_de(c))
    amen = "".join(f"<span>{e(AMENIDAD_NOMBRE.get(str(a).lower(), str(a).replace('_', ' ').capitalize()))}</span>"
                   for a in (c.get("amenidades") or [])[:8])
    return (f"{_galeria(c)}"
            "<div style='display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-top:16px'>"
            f"<div><div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'>"
            f"<span class='pill gris'>{ui.bandera(pais)} {e(deps)}</span>{sello}</div>"
            f"<h1 style='margin-top:8px'>{e(c['nombre'])}</h1>"
            f"<p class='sub'>{e(c.get('club'))}</p></div>"
            f"<div class='precio' style='font-size:22px;white-space:nowrap'>{e(sim)} {c['precio_hora']:.2f} <small>por hora</small></div></div>"
            "<ul class='datos'>"
            f"<li>📍 <span>{e(lugar or 'Dirección en la app')} · <a href='{_maps(c)}' target='_blank' rel='noopener'>Cómo llegar</a></span></li>"
            f"<li>🕒 <span>{e(c['hora_apertura'])} a {e(c['hora_cierre'])} · turnos de {c['duracion_slot_min']} min</span></li>"
            + (f"<li>⚡ <span>Hora feliz −{c['descuento_valle']} % de {e(c['valle_desde'] or '00:00')} a {e(c['valle_hasta'] or '12:00')}</span></li>" if c['descuento_valle'] > 0 else "")
            + (f"<li>🏟️ <span>{e(c['superficie'])}</span></li>" if c.get("superficie") else "")
            + "</ul>" + (f"<div class='amen'>{amen}</div>" if amen else ""))


def _jsonld_cancha(c: dict, sim: str) -> str:
    return json.dumps({
        "@context": "https://schema.org", "@type": "SportsActivityLocation",
        "name": c["nombre"], "image": _fotos(c)[:1],
        "address": {"@type": "PostalAddress", "streetAddress": c.get("direccion") or "",
                    "addressLocality": _zona(c), "addressCountry": _pais_de(c)},
        "geo": {"@type": "GeoCoordinates", "latitude": c.get("lat"), "longitude": c.get("lng")},
        "priceRange": f"{sim} {c['precio_hora']:.2f} por hora",
        "url": f"{config.PUBLIC_BASE_URL.rstrip('/')}/reservar/{c['id']}" if getattr(config, 'PUBLIC_BASE_URL', '') else "",
    }, ensure_ascii=False)


@router.get("/reservar/{cancha_id}", response_class=HTMLResponse)
def pagina_reservar(request: Request, cancha_id: str, fecha: str = "", hora: str = "") -> HTMLResponse:
    c = datos.cancha(cancha_id)
    ses = sesion.de_request(request)
    if not c or c.get("eliminada") or not c.get("registrada", True):
        return _no_encontrada()
    sim, iso = _moneda_de(c)
    pais = _pais_de(c)
    ficha = _ficha(c, sim, pais, verificada=datos.reservable(c))
    canonical = (f"{config.PUBLIC_BASE_URL.rstrip('/')}/reservar/{c['id']}"
                 if getattr(config, "PUBLIC_BASE_URL", "") else "")
    og = _fotos(c)[0] if _fotos(c) else "/static/brand/logo_pichangol.png"

    if not datos.reservable(c) or not _pago_web_disponible(iso):
        if not datos.reservable(c):
            motivo = ("Este local todavía está en proceso de verificación con Pichangol. Desde la app puedes "
                      "reservar y pagar en la cancha, y te avisamos cuando acepte pagos en línea.")
        else:
            motivo = (f"Esta cancha cobra en {e(sim)} y el pago en línea desde la web está disponible por "
                      "ahora solo en soles." if iso != "PEN" else "El pago en línea desde la web se está habilitando.")
        cuerpo = (f"<div style='padding-top:22px'>{ficha}</div>"
                  f"<div class='panel' style='margin-top:20px'><h2>Reserva desde la app</h2>"
                  f"<p class='sub'>{motivo} En la app Pichangol reservas y pagas con los medios de tu país.</p>"
                  f"<div class='acciones'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a>"
                  "<a class='btn sec' href='/canchas'>Ver otras canchas</a></div></div>")
        return ui.shell(c["nombre"], cuerpo, desc=f"{c['nombre']} · {c.get('club', '')}", canonical=canonical,
                        og_image=og, jsonld=_jsonld_cancha(c, sim), sesion=ses)

    dias, etiquetas = _tira_dias(pais)
    deps = _deportes_de(c)
    selector_dep = ""
    if len(deps) > 1:
        ops = "".join(f"<option value='{e(d)}'>{_deporte(d)[1]} {_deporte(d)[0]}</option>" for d in deps)
        selector_dep = f"<label for='deporte'>¿Qué vas a jugar?</label><select id='deporte'>{ops}</select>"
    extras_html = ""
    filas = ""
    for s in c.get("servicios_extra") or []:
        clave = str(s.get("clave") or "")
        try:
            precio = float(s.get("precio") or 0)
        except (TypeError, ValueError):
            precio = 0.0
        if precio <= 0 or not clave:
            continue
        nombre = EXTRAS_NOMBRE.get(clave, clave.capitalize())
        filas += (f"<label style='display:flex;gap:10px;align-items:center;font-weight:600;margin:8px 0'>"
                  f"<input type='checkbox' name='extra' value='{precio:.2f}' data-clave='{e(clave)}' data-nombre='{e(nombre)}' style='width:auto'>"
                  f"{e(nombre)} <small style='color:var(--tenue)'>+ {e(sim)} {precio:.2f}</small></label>")
    if filas:
        extras_html = f"<div class='paso'><span>3</span> Servicios extra <small style='color:var(--tenue);font-weight:600'>(opcional)</small></div>{filas}"

    cfg = json.dumps({"id": c["id"], "moneda": sim, "pk": config.CULQI_PUBLIC_KEY, "maxSlots": MAX_SLOTS,
                      "logo": "", "hoy": dias[0]["iso"], "dias": dias, "etiquetas": etiquetas,
                      # Día preseleccionado desde el buscador de la portada (solo si cae en la tira).
                      "fecha": fecha if any(d["iso"] == fecha for d in dias) else "",
                      # Hora buscada en la portada: se marca el turno libre que la cubre.
                      "hora": hora if horarios.hora_en_minutos(hora) is not None else "",
                      # Login con Google (como el app): con client id configurado, reservar
                      # exige sesión; la reserva queda a nombre del correo de Google.
                      "login": sesion.activo(), "sesion": ses}, ensure_ascii=False)
    if sesion.activo():
        quien = ("" if not ses else
                 f"<div class='quien' id='quien'>{('<img src=' + chr(39) + e(ses['foto']) + chr(39) + ' alt=' + chr(39) + chr(39) + '>') if ses.get('foto') else ''}"
                 f"<div><b>{e(ses.get('nombre') or ses['email'])}</b><div class='m'>{e(ses['email'])}</div></div>"
                 "<button type='button' class='btn sec' onclick='cerrarSesion()'>Cambiar cuenta</button></div>")
        paso_datos = (
            "<div class='paso'><span>2</span> Tus datos</div>"
            f"<div class='login-box' id='loginBox'{' style=display:none' if ses else ''}>"
            "<b>Inicia sesión con Google para reservar</b>"
            "<div class='sub' style='margin:4px 0 12px'>Como en el app: tu reserva queda en \"Mis reservas\" y el comprobante llega a tu correo.</div>"
            f"{sesion.boton_google()}<div class='estado bad' id='sesionErr'></div></div>"
            f"<div id='datosBox'{'' if ses else ' style=display:none'}>{quien}"
            "<div class='row'><div><label for='nombre'>Nombre y apellido</label>"
            f"<input id='nombre' autocomplete='name' maxlength='80' placeholder='Como en tu documento' value='{e((ses or {}).get('nombre', ''))}'></div>"
            "<div><label for='celular'>Celular</label><input id='celular' inputmode='tel' autocomplete='tel' maxlength='20' placeholder='9 dígitos'></div></div>"
            f"<input id='email' type='hidden' value='{e((ses or {}).get('email', ''))}'></div>")
    else:
        paso_datos = (
            "<div class='paso'><span>2</span> Tus datos</div>"
            "<div class='row'><div><label for='nombre'>Nombre y apellido</label><input id='nombre' autocomplete='name' maxlength='80' placeholder='Como en tu documento'></div>"
            "<div><label for='celular'>Celular</label><input id='celular' inputmode='tel' autocomplete='tel' maxlength='20' placeholder='9 dígitos'></div></div>"
            "<label for='email'>Correo</label><input id='email' type='email' autocomplete='email' maxlength='120' placeholder='Aquí va tu comprobante'>")
    cuerpo = (
        f"<div style='padding-top:22px'>{ficha}</div>"
        "<div class='dos' style='margin-top:22px'>"
        "<div class='panel'>"
        "<div class='paso' style='margin-top:0'><span>1</span> Elige el día y el horario</div>"
        "<div class='strip' id='dias'></div>"
        f"{selector_dep}"
        f"<div class='sub' style='margin:6px 0 12px;font-size:13px'>Hasta {MAX_SLOTS} turnos por pedido. Toca un horario para agregarlo; vuelve a tocarlo para quitarlo.</div>"
        "<div class='chips' id='slots'></div>"
        f"{paso_datos}"
        f"{extras_html}"
        "<div class='estado bad' id='err'></div>"
        "</div>"
        "<aside class='resumen'><div class='panel'>"
        "<h3>Resumen de tu reserva</h3>"
        f"<div class='sub' style='margin-bottom:10px'>{e(c['nombre'])}{(' · ' + e(c.get('club'))) if c.get('club') else ''}</div>"
        "<div id='lineas'></div>"
        "<div class='total'><span>Total</span><span id='tot'></span></div>"
        "<div style='margin-top:14px'><button class='btn lg' id='btnPagar' disabled>Elige un horario</button></div>"
        f"<div style='margin-top:14px'>{ui.marcas_pago()}</div>"
        "<div class='sub' style='font-size:12.5px;margin-top:12px'>Reserva confirmada al instante; el local la ve en su agenda. "
        "Cancelación con más de 6 horas de anticipación: devolución del 100 %. <a href='/#devoluciones'>Ver política</a>.</div>"
        "</div></aside></div>"
        "<div class='barra-fija'><div><div class='sub' style='font-size:12px;margin:0'>Total</div><div class='t' id='totBarra'></div></div>"
        "<button class='btn' id='btnPagarBarra' disabled>Elige un horario</button></div>"
        f"<script>window.__cancha={cfg};</script>"
        "<script src='https://checkout.culqi.com/js/v4'></script>"
        f"<script>{sesion.JS_SESION if sesion.activo() else ''}{_JS_RESERVA}</script>")
    return ui.shell(f"Reservar {c['nombre']}", cuerpo, con_barra=True, canonical=canonical, og_image=og,
                    desc=f"Reserva {c['nombre']} y paga en línea con Yape o tarjeta.", jsonld=_jsonld_cancha(c, sim),
                    extra_head=sesion.GIS_SCRIPT if (sesion.activo() and not ses) else "", sesion=ses)


# ── asegurar / pagar / liberar ────────────────────────────────────────────────

class HoraReq(BaseModel):
    fecha: str
    hora: str


class AsegurarReq(BaseModel):
    cancha_id: str
    horas: list[HoraReq]
    extras: list[str] = []
    deporte: str = ""
    nombre: str
    celular: str = ""
    email: str


_contador = {"n": 0}


def _nuevo_id() -> str:
    _contador["n"] = (_contador["n"] + 1) % 100000
    return f"{datos.PREFIJO_ID_WEB}{int(time.time() * 1000)}_{_contador['n']}"


@router.post("/web/asegurar")
def asegurar(req: AsegurarReq, request: Request = None) -> dict:
    """Toma los slots (INSERT 'nueva') ANTES de cobrar, igual que el APK
    (`insertarSegura`): así el UNIQUE decide quién se queda con la hora. Si el
    cliente no paga, `/web/liberar` (o el vencimiento del hold) los suelta."""
    c = datos.cancha(req.cancha_id)
    if not c or c.get("eliminada"):
        return {"ok": False, "error": "no_encontrada"}
    if not datos.reservable(c):
        return {"ok": False, "error": "no_verificada"}
    sim, iso = _moneda_de(c)
    if not _pago_web_disponible(iso):
        return {"ok": False, "error": "pago_no_disponible"}
    # Con login configurado, la reserva es del CORREO de la sesión de Google
    # (como en el app); sin sesión no se reserva.
    ses = sesion.de_request(request) if sesion.activo() else None
    if sesion.activo() and not ses:
        return {"ok": False, "error": "sesion_requerida"}
    nombre = (req.nombre.strip() or (ses or {}).get("nombre", ""))[:80]
    email = (ses["email"] if ses else req.email.strip().lower())[:120]
    if len(nombre) < 3 or "@" not in email:
        return {"ok": False, "error": "datos_invalidos"}
    if not req.horas or len(req.horas) > MAX_SLOTS:
        return {"ok": False, "error": "horas_invalidas"}
    for h in req.horas:
        if not _es_iso(h.fecha):
            return {"ok": False, "error": "fecha_invalida"}
    datos.liberar_holds_vencidos(c["id"])
    pais = _pais_de(c)
    d_min, d_max = _fechas_validas(pais)
    pedidos = {(h.fecha, h.hora) for h in req.horas}
    # Un slot de madrugada pertenece a la grilla del día ANTERIOR: se evalúan
    # ambos días base y se valida cada hora contra la grilla real.
    bases = set()
    for fb in {h.fecha for h in req.horas}:
        bases.add(fb)
        bases.add((date.fromisoformat(fb) - timedelta(days=1)).isoformat())
    validos: dict[tuple[str, str], dict] = {}
    for fb in sorted(bases):
        if d_min <= fb <= d_max:
            for s in _slots_del_dia(c, fb):
                validos[(s["fecha"], s["hora"])] = s
    deporte = (req.deporte or "").strip().lower()
    if deporte and deporte not in _deportes_de(c):
        deporte = ""
    extras_ok = []
    if req.extras:
        cat = {str(s.get("clave")): float(s.get("precio") or 0) for s in c.get("servicios_extra") or []}
        for k in req.extras:
            if k in cat and cat[k] > 0 and k not in [x["clave"] for x in extras_ok]:
                extras_ok.append({"clave": k, "precio": cat[k]})
    hoy = horarios.ahora_local(pais).date()
    grupo = f"grp_web_{int(time.time() * 1000)}" if len(pedidos) > 1 else ""
    filas, total = [], 0
    for i, key in enumerate(sorted(pedidos)):
        s = validos.get(key)
        if not s or s["ocupado"]:
            return {"ok": False, "error": "ocupado" if s else "hora_invalida"}
        total += s["precio"]
        filas.append({
            "id": _nuevo_id(), "cancha_id": c["id"], "jugador": nombre, "nivel": "",
            "fecha": s["fecha"], "dia": horarios.etiqueta_dia(s["fecha"], hoy),
            "hora_inicio": s["hora"], "hora_fin": s["fin"], "estado": "nueva",
            "traida_por_app": True, "precio": s["precio"], "sena": 0, "pagado": False,
            "usuario": email, "deporte": deporte, "moneda": sim,
            "extras": extras_ok if i == 0 else [],
            "telefono": req.celular.strip()[:20], "grupo_reserva_id": grupo,
            "medio_pago": "web_hold",
        })
    total = int(round(total + sum(x["precio"] for x in extras_ok)))
    if total < 1:
        return {"ok": False, "error": "monto_invalido"}
    r = datos.insertar_reservas(filas)
    if r:
        return {"ok": False, "error": r}
    ids = [f["id"] for f in filas]
    return {"ok": True, "ids": ids, "grupo": grupo, "firma": _firma(ids),
            "total": total, "total_centimos": total * 100, "moneda": sim,
            "hold_segundos": datos.HOLD_SEGUNDOS}


class LiberarReq(BaseModel):
    ids: list[str]
    firma: str


@router.post("/web/liberar")
def liberar(req: LiberarReq) -> dict:
    if not _firma_ok(req.ids, req.firma):
        return {"ok": False, "error": "firma"}
    return {"ok": datos.borrar_reservas(req.ids)}


class PagarReq(BaseModel):
    ids: list[str]
    firma: str
    token: str
    medio: str = "tarjeta"
    email: str = ""


@router.post("/web/pagar")
def pagar(req: PagarReq, request: Request = None) -> dict:
    """Cobra con Culqi el TOTAL del bloque asegurado y confirma las filas.
    Fallo del cargo → las filas se liberan y no se cobró nada. Éxito →
    confirmada + pagado + liquidación al dueño (billetera-first) + push."""
    ses = sesion.de_request(request) if sesion.activo() else None
    if sesion.activo() and not ses:
        return {"ok": False, "error": "sesion_requerida",
                "mensaje": "Inicia sesión con Google para pagar tu reserva."}
    if not _firma_ok(req.ids, req.firma):
        return {"ok": False, "error": "firma",
                "mensaje": "La sesión de pago venció. Vuelve a elegir el horario."}
    filas = datos.reservas_de(req.ids)
    if not filas or len(filas) != len(req.ids):
        return {"ok": False, "error": "hold_vencido",
                "mensaje": "El horario ya no está reservado para ti (pasaron más de 10 minutos). Vuelve a elegirlo."}
    if all(f.get("pagado") for f in filas):
        return {"ok": True, "url": _url_comprobante(filas)}
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim, iso = _moneda_de(c) if c else ("S/", "PEN")
    total = _total_de(filas)
    email = (ses["email"] if ses else (req.email or filas[0].get("usuario") or "")).strip().lower()
    concepto = f"Reserva {c.get('nombre', 'cancha')} {filas[0]['fecha']} {filas[0]['hora_inicio']}"
    cargo = culqi.crear_cargo(
        token=req.token.strip(), monto_centimos=total * 100, email=email,
        descripcion=concepto[:80], moneda=iso,
        metadata={"canal": "web", "reserva_id": filas[0]["id"], "cancha_id": filas[0]["cancha_id"]})
    if not cargo.get("ok"):
        datos.borrar_reservas(req.ids)
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada y el "
                           "horario quedó libre para que lo intentes de nuevo." + (f" ({msg[:80]})" if msg else "")}
    medio = "yape" if req.medio == "yape" else "tarjeta"
    datos.confirmar_reservas(req.ids, medio)
    dueno = (c.get("dueno") or "").strip().lower()
    if dueno:
        try:
            from pagos.router import LiquidacionOnlineReq, post_liquidacion_online, _aviso_push_usuario
            post_liquidacion_online(LiquidacionOnlineReq(
                dueno_id=dueno, monto_soles=float(total), reserva_id=filas[0]["id"],
                concepto=f"Reserva web · {c.get('nombre', '')} · {filas[0]['fecha']} {filas[0]['hora_inicio']}",
                medio=medio, moneda=iso))
            rango = f"{filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
            _aviso_push_usuario(
                dueno, "Nueva reserva 📅",
                f"{filas[0]['jugador']} · {c.get('nombre', '')} · {horarios.fecha_larga(filas[0]['fecha'])} {rango} · "
                f"pagó {sim} {total:.2f} por la web", tipo="reserva")
        except Exception:  # noqa: BLE001 — la contabilidad nunca deshace un cobro
            pass
    return {"ok": True, "url": _url_comprobante(filas), "charge_id": cargo.get("charge_id")}


def _total_de(filas: list[dict]) -> int:
    total = sum(int(f["precio"]) for f in filas)
    total += int(round(sum(float(x.get("precio") or 0) for f in filas for x in (f.get("extras") or []))))
    return total


def _url_comprobante(filas: list[dict]) -> str:
    g = (filas[0].get("grupo_reserva_id") or "").strip()
    return f"/reserva/{g if g else filas[0]['id']}"


# ── comprobante ───────────────────────────────────────────────────────────────

def _filas_comprobante(ref: str) -> list[dict]:
    filas = datos.reservas_por_grupo(ref) if ref.startswith("grp_") else datos.reservas_de([ref])
    return [f for f in filas if f.get("pagado") or f.get("estado") == "confirmada"]


@router.get("/reserva/{ref}.ics")
def comprobante_ics(ref: str) -> Response:
    """Evento(s) para el calendario del cliente (Google/Apple/Outlook)."""
    filas = _filas_comprobante(ref)
    if not filas:
        return Response("No encontrada", status_code=404)
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    pais = _pais_de(c) if c else "PE"
    tz = horarios.ahora_local(pais).tzinfo
    lugar = ", ".join(x for x in (c.get("nombre"), c.get("direccion"), _zona(c)) if x)
    ahora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ev = []
    for f in filas:
        try:
            d = date.fromisoformat(f["fecha"])
            hi = horarios.hora_en_minutos(f["hora_inicio"]) or 0
            hf = horarios.hora_en_minutos(f["hora_fin"]) or hi + 60
            if hf <= hi:
                hf += 24 * 60
            ini = datetime(d.year, d.month, d.day, tzinfo=tz) + timedelta(minutes=hi)
            fin = datetime(d.year, d.month, d.day, tzinfo=tz) + timedelta(minutes=hf)
        except (ValueError, TypeError):
            continue
        ev.append("BEGIN:VEVENT\r\n"
                  f"UID:{f['id']}@pichangol.app\r\nDTSTAMP:{ahora}\r\n"
                  f"DTSTART:{ini.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
                  f"DTEND:{fin.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
                  f"SUMMARY:Pichangol · {_ics(c.get('nombre') or 'Reserva')}\r\n"
                  f"LOCATION:{_ics(lugar)}\r\n"
                  f"DESCRIPTION:Reserva {_ics(ref)}. Comprobante: {_ics((config.PUBLIC_BASE_URL or '').rstrip('/'))}/reserva/{_ics(ref)}\r\n"
                  "END:VEVENT\r\n")
    body = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Pichangol//Reserva web//ES\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n"
            + "".join(ev) + "END:VCALENDAR\r\n")
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=pichangol-{ref}.ics"})


def _ics(s) -> str:
    return str(s or "").replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")


@router.get("/reserva/{ref}", response_class=HTMLResponse)
def pagina_comprobante(ref: str) -> HTMLResponse:
    filas = _filas_comprobante(ref)
    if not filas:
        return _no_encontrada("Reserva no encontrada")
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim = filas[0].get("moneda") or "S/"
    total = _total_de(filas)
    extras = [x for f in filas for x in (f.get("extras") or [])]
    lineas = "".join(
        f"<div class='linea'><span>{e(horarios.fecha_larga(f['fecha']))} · {e(f['hora_inicio'])}–{e(f['hora_fin'])}</span>"
        f"<b>{e(sim)} {int(f['precio']):.2f}</b></div>" for f in filas)
    lineas += "".join(
        f"<div class='linea'><span>{e(EXTRAS_NOMBRE.get(str(x.get('clave')), str(x.get('clave')).capitalize()))}</span>"
        f"<b>{e(sim)} {float(x.get('precio') or 0):.2f}</b></div>" for x in extras)
    lugar = ", ".join(x for x in (c.get("direccion"), _zona(c)) if x)
    base = (config.PUBLIC_BASE_URL or "").rstrip("/")
    texto_wa = quote(f"Reservé en {c.get('nombre', 'una cancha')} por Pichangol: "
                     f"{horarios.fecha_larga(filas[0]['fecha'])} {filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}. "
                     f"Comprobante: {base}/reserva/{ref}")
    medio = {"yape": "Yape", "tarjeta": "tarjeta"}.get(str(filas[0].get("medio_pago") or ""), "en línea")
    cuerpo = (
        "<div style='max-width:640px;margin:26px auto 0'>"
        f"<div class='panel' style='text-align:center'>{ui.check_svg()}"
        "<h1>¡Reserva confirmada!</h1>"
        f"<p class='sub'>Comprobante <b>{e(ref)}</b> · pagado con {e(medio)}</p>"
        f"<h3 style='margin-top:16px'>{e(c.get('nombre') or 'Cancha')}</h3>"
        f"<div class='sub'>{e(c.get('club'))}{(' · ' + e(lugar)) if lugar else ''}</div>"
        f"<div style='text-align:left;margin-top:16px'>{lineas}"
        f"<div class='total'><span>Total pagado</span><span>{e(sim)} {total:.2f}</span></div></div>"
        f"<div class='sub' style='margin-top:12px'>A nombre de <b>{e(filas[0].get('jugador'))}</b> · {e(filas[0].get('usuario'))}. "
        "Guarda este enlace: es tu comprobante.</div>"
        "<div class='acciones'>"
        f"<a class='btn sec' href='/reserva/{e(ref)}.ics'>📅 Agregar al calendario</a>"
        + (f"<a class='btn sec' href='{_maps(c)}' target='_blank' rel='noopener'>📍 Cómo llegar</a>" if c else "")
        + f"<a class='btn sec' href='https://wa.me/?text={texto_wa}' target='_blank' rel='noopener'>💬 Compartir</a>"
        "</div>"
        "<div class='estado ok' style='text-align:left'>Cancelación con más de 6 horas de anticipación: devolución del 100 %. "
        "Escríbenos a <a href='mailto:contacto@ebim.pe'>contacto@ebim.pe</a> citando el número de comprobante.</div>"
        "</div>"
        "<div class='panel' style='margin-top:16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap'>"
        "<img src='/static/brand/logo_pin.png' alt='' style='width:56px;height:56px;border-radius:14px;border:1px solid var(--trazo)'>"
        "<div style='flex:1;min-width:200px'><b>Lleva tus reservas contigo</b>"
        "<div class='sub' style='font-size:13px'>Con la app ves tu agenda, acumulas puntos y reservas en dos toques.</div></div>"
        f"<a class='btn' href='{PLAY_URL}'>Descargar la app</a></div>"
        "<div style='text-align:center;margin-top:16px'><a href='/canchas'>Reservar otra cancha</a></div>"
        "</div>")
    return ui.shell("Reserva confirmada", cuerpo)
