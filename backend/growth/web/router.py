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
from typing import Any
import servicios_extra as _se
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

import config
import empresa
from paises import _CAJAS, pais_de_coordenadas, moneda_de_pais, simbolo_de_moneda
from pagos import culqi
from web import catalogos, datos, descubrir, horarios, marca, sesion, ui
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
# Claves de amenidades = las del APP (`catalogos.AMENIDADES`; así los chips y
# el modal de filtros reconocen lo que guardan los dueños). Se conservan las
# claves viejas de la web para datos que las tuvieran.
AMENIDAD_NOMBRE = {**{k: v[0] for k, v in catalogos.AMENIDADES.items()},
                   "estacionamiento": "Estacionamiento", "vestuarios": "Vestuarios",
                   "iluminacion": "Iluminación", "techada": "Techada", "tribuna": "Tribuna", "seguridad": "Seguridad"}


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
    """Zona visible = el BARRIO real (reverse-geocode), espejo de
    `Cancha.zonaMostrable` del app. El `distrito` es un enum legado de Lima
    (sanBorja/surco/laMolina, referencial) que NO se muestra: salía "Sanborja"
    en canchas de cualquier ciudad (pedido del director, sep-2026)."""
    return (c.get("barrio") or "").strip()


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
  // Un local puede tener varias canchas (data-ids); sin él, la tarjeta es una sola cancha.
  function idsDe(c){ return (c.dataset.ids || c.dataset.id || '').split(' ').filter(Boolean); }
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
    if(filtro.q && c.dataset.q !== filtro.q && c.dataset.t.indexOf(filtro.q) < 0) return false;
    if(filtro.cerca && yo && c.dataset.d && parseFloat(c.dataset.d) > 30) return false;
    if(c.classList.contains('aca')) return true; // academias: solo zona/texto y cercanía
    if(filtro.hora && !abiertaA(c, filtro.hora)) return false;
    if(filtro.hora && filtro.fecha && c.dataset.ok === '1'){ var lk = libres[filtro.fecha + '|' + filtro.hora]; if(lk && idsDe(c).every(function(i){ return lk[i] === false; })) return false; }
    return true;
  }
  function aplicar(){
    var n = 0;
    cards().forEach(function(c){
      var ok = pasaBase(c) && (c.classList.contains('aca') || pasaFil(c, fil));
      c.style.display = ok ? '' : 'none'; if(ok) n++;
      if(c.dataset.base){ var qs = []; if(filtro.fecha) qs.push('fecha=' + filtro.fecha); if(filtro.hora) qs.push('hora=' + filtro.hora);
        var base = c.dataset.base; if(filtro.hora && filtro.fecha && c.dataset.ids){ var lk2 = libres[filtro.fecha + '|' + filtro.hora] || {}; var libre = idsDe(c).filter(function(i){ return lk2[i] !== false; })[0]; if(libre) base = '/reservar/' + libre; }
        c.setAttribute('href', base + (qs.length ? '?' + qs.join('&') : '')); }
    });
    document.querySelectorAll('.grupo-pais, .grupo-aca').forEach(function(g){
      var vis = Array.prototype.some.call(g.querySelectorAll('.lst'), function(c){ return c.style.display !== 'none'; });
      g.style.display = vis ? '' : 'none';
    });
    var v = $('vacio'); if(v){ v.style.display = n ? 'none' : '';
      if(!n && v.dataset.base !== undefined){
        var why = filtro.hora ? 'Ninguna cancha' + (filtro.cerca ? ' cerca de ti' : '') + ' tiene turno libre ' + (filtro.fecha ? etiquetaFecha(filtro.fecha).toLowerCase() : '') + ' a las ' + filtro.hora + '. Prueba con otra hora u otro día.'
                              : C.dep === 'academias' ? (filtro.q ? 'No encontramos academias con “' + filtro.q + '”. Prueba con otro nombre o zona.' : 'No hay academias con esa búsqueda. Prueba con otra zona.')
                              : (filtro.q && C.lugares ? (busqGoogle[filtro.q] === 'pendiente' ? 'Buscando “' + filtro.q + '” también en Google Maps…' : 'No encontramos “' + filtro.q + '” en Pichangol ni en Google Maps. Prueba con otro nombre o zona.')
                              : 'No hay canchas libres con esa búsqueda. Prueba con otra zona, día u hora.');
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
    if(ci <= ap) ci += 1440; if(h < ap && ci >= 1440) h += 1440;
    return ap <= h && h <= ci; // el último turno EMPIEZA a la hora de cierre (cierra 23:00 → 23:00–00:00)
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
        var txtCierre = function(m){ m = m % 1440; return (m < 600 ? '0' : '') + Math.floor(m / 60) + ':' + (m % 60 < 10 ? '0' : '') + (m % 60); };
        av.textContent = pend.fecha === hoyIso && cierreMax
          ? 'El último turno de hoy en estas canchas empieza a las ' + txtCierre(cierreMax) + ' y ya pasó. Elige otro día en “Cuándo”.'
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
    if(filtro.q) buscarEnGoogle(filtro.q);
    consultarLibres(); aplicar(); pintarResumenBusq();
    var g = $('grupos'); if(g) g.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  var bF = $('btnBuscar'); if(bF) bF.addEventListener('click', buscar);
  // ── buscar por NOMBRE también en Google Maps (caso "Campo deportivo Edu Jr.") ──
  // Lo escrito en "Dónde" no solo filtra las tarjetas cargadas: se busca en
  // Google (`/web/lugares`, la misma búsqueda de "Pon tu cancha") y los locales
  // que la heurística reconoce como cancha entran a "Más canchas cerca de ti"
  // como descubiertas (ficha /lugar, Cómo llegar, ¿Es tuya? Reclámala).
  var busqGoogle = {};
  function buscarEnGoogle(q){
    if(!C.lugares || C.dep === 'academias' || !q || q.length < 3 || busqGoogle[q]) return;
    busqGoogle[q] = 'pendiente';
    var ref = yo || (mapa ? mapa.getCenter() : {lat: C.centro[0], lng: C.centro[1]});
    fetch('/web/lugares?q=' + encodeURIComponent(q) + '&lat=' + ref.lat + '&lng=' + ref.lng).then(function(r){ return r.json(); })
      .then(function(j){
        busqGoogle[q] = 'listo';
        var lst = (j.lugares || []).filter(function(l){ return l.deporte && (!C.dep || l.deporte === C.dep); });
        lst.forEach(function(l){ l.q = q; if(!l.fotos) l.fotos = []; });
        if(lst.length) pintarDescubiertas(lst, false); else aplicar();
      })
      .catch(function(){ busqGoogle[q] = 'listo'; aplicar(); });
  }
  // ── Filtros tipo Airbnb (modal): amenidades, tipo, precio, superficie, duración ──
  var fil = {am: {}, tipo: '', sup: '', dur: 0, min: 0, max: 0}, filTmp = null, precioMon = '', pRango = [0, 0];
  var modal = $('modalFiltros'), bFil = $('btnFiltros');
  function copiaFil(f){ return {am: Object.assign({}, f.am), tipo: f.tipo, sup: f.sup, dur: f.dur, min: f.min, max: f.max}; }
  function pasaFil(c, f){
    for(var a in f.am){ if(f.am[a] && (' ' + (c.dataset.am || '') + ' ').indexOf(' ' + a + ' ') < 0) return false; }
    if(f.tipo === 'ok' && c.dataset.ok !== '1') return false;
    if(f.tipo === 'pend' && c.dataset.ok === '1') return false;
    if(f.sup && (' ' + (c.dataset.sup || '') + ' ').indexOf(' ' + f.sup + ' ') < 0) return false;
    if(f.dur && (' ' + (c.dataset.pasos || c.dataset.paso || '60') + ' ').indexOf(' ' + f.dur + ' ') < 0) return false;
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
    document.querySelectorAll('.grupo-pais, .grupo-aca').forEach(function(g){
      var grid = g.querySelector('.lst-grid'); if(!grid) return;
      var hijos = Array.prototype.slice.call(grid.children).sort(function(a, b){ return parseFloat(a.dataset.d) - parseFloat(b.dataset.d); });
      hijos.forEach(function(h){ grid.appendChild(h); });
    });
    var ta = document.querySelector('.grupo-aca .cerca'); if(ta) ta.textContent = '· las más cercanas a ti primero';
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
    var hrefLugar = '/lugar/' + encodeURIComponent(c.id) + '?nombre=' + encodeURIComponent(c.nombre) + '&direccion=' + encodeURIComponent(c.direccion) + '&lat=' + c.lat + '&lng=' + c.lng + '&deporte=' + encodeURIComponent(c.deporte);
    return '<a class="lst pend" href="' + hrefLugar + '" data-id="' + esc(c.id) + '" data-lat="' + c.lat + '" data-lng="' + c.lng + '" data-ok="0" data-deps="' + esc(c.deporte) + '" data-nombre="' + esc(c.nombre) + '" data-sub="' + esc(c.direccion) + '" data-precio="' + esc(c.deporte_nombre) + '" data-t="' + esc((c.nombre + ' ' + c.direccion).toLowerCase()) + '" data-q="' + esc(c.q || '') + '">' +
      '<div class="foto"><div class="fotos">' + foto + '</div><span class="badge pend">Aún sin registrar</span>' + extra + '</div>' +
      '<div class="lb"><div class="l1"><b>' + esc(c.nombre) + '</b><span class="rate">' + esc(c.deporte_nombre) + '</span></div>' +
      '<div class="l2">' + esc(c.direccion) + '</div><div class="l2"><span class="dist">' + (c.km != null ? 'a ' + fmtKm(c.km) : '') + '</span></div>' +
      '<div class="l3"><span class="app">📲 Reservar en la app</span> <span class="app">📍 <span class="ir" data-lat="' + c.lat + '" data-lng="' + c.lng + '">Cómo llegar</span></span> ' +
      '<span class="app reclamar" data-id="' + esc(c.id) + '" data-nombre="' + esc(c.nombre) + '" data-dir="' + esc(c.direccion) + '" data-lat="' + c.lat + '" data-lng="' + c.lng + '" data-dep="' + esc(c.deporte) + '">🏷️ ¿Es tuya? Reclámala</span></div></div></a>';
  }
  document.addEventListener('click', function(ev){ var g = ev.target.closest('.ir'); if(!g) return; ev.preventDefault(); ev.stopPropagation();
    window.open('https://www.google.com/maps/search/?api=1&query=' + g.dataset.lat + ',' + g.dataset.lng, '_blank'); });
  document.addEventListener('click', function(ev){ var g = ev.target.closest('.wa'); if(!g) return; ev.preventDefault(); ev.stopPropagation(); window.open(g.dataset.wa, '_blank', 'noopener'); });
  // "¿Es tuya? Reclámala": registro desde la web prellenado con el lugar de Google (mismo flujo que el app).
  document.addEventListener('click', function(ev){ var g = ev.target.closest('.reclamar'); if(!g) return; ev.preventDefault(); ev.stopPropagation();
    location.href = '/anfitrion/nueva?place=' + encodeURIComponent(g.dataset.id) + '&nombre=' + encodeURIComponent(g.dataset.nombre) + '&direccion=' + encodeURIComponent(g.dataset.dir) + '&lat=' + g.dataset.lat + '&lng=' + g.dataset.lng + '&deporte=' + encodeURIComponent(g.dataset.dep || ''); });
  // Las descubiertas se ACUMULAN por id entre búsquedas (cada celda que se
  // explora suma; la distancia se recalcula desde el usuario o el centro del mapa).
  var descAcum = {};
  function kmEntre(a, b, c, d){ var R = 6371, x = (c - a) * Math.PI / 180, y = (d - b) * Math.PI / 180; var h = Math.sin(x/2)*Math.sin(x/2) + Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(y/2)*Math.sin(y/2); return 2 * R * Math.asin(Math.sqrt(h)); }
  function pintarDescubiertas(lista, conFotos){
    var sec = $('descubiertas'), grid = $('gridDesc');
    if(!sec || !grid) return;
    (lista || []).forEach(function(c){ var prev = descAcum[c.id]; if(prev && !(c.fotos && c.fotos.length) && prev.fotos && prev.fotos.length) c.fotos = prev.fotos; descAcum[c.id] = c; });
    var ref = yo ? yo : (mapa ? {lat: mapa.getCenter().lat, lng: mapa.getCenter().lng} : null);
    lista = Object.keys(descAcum).map(function(k){ var c = descAcum[k]; if(ref) c.km = Math.round(kmEntre(ref.lat, ref.lng, c.lat, c.lng) * 100) / 100; return c; })
      .sort(function(a, b){ return (a.km == null ? 1e9 : a.km) - (b.km == null ? 1e9 : b.km); });
    if(!lista.length){ if(!conFotos) sec.style.display = 'none'; return; }
    sec.style.display = '';
    grid.innerHTML = lista.map(tarjetaDesc).join('');
    resolverFotos();
    if(mapa && window.L){
      pinesDesc.forEach(function(m){ m.remove(); }); pinesDesc = [];
      lista.forEach(function(c){
        var m = L.marker([c.lat, c.lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio pend">' + esc(c.emoji || '') + ' ' + esc(c.deporte_nombre) + '</span>', iconSize: null})}).addTo(mapa);
        m.bindPopup('<b>' + esc(c.nombre) + '</b><br>' + esc(c.direccion) + '<br><a class="btn sec" href="/lugar/' + encodeURIComponent(c.id) + '?nombre=' + encodeURIComponent(c.nombre) + '&direccion=' + encodeURIComponent(c.direccion) + '&lat=' + c.lat + '&lng=' + c.lng + '&deporte=' + encodeURIComponent(c.deporte) + '">Ver lugar</a>');
        pinesDesc.push(m);
      });
    }
    aplicar();
  }
  function descubrir(lat, lng){
    if(C.dep === 'academias' || !$('descubiertas')) return;  // pestaña Academias: sin canchas de Google
    var k = lat.toFixed(2) + ',' + lng.toFixed(2);
    if(descubiertas[k]) return; descubiertas[k] = true;
    var sec = $('descubiertas'); if(sec){ sec.style.display = ''; if(!Object.keys(descAcum).length) $('gridDesc').innerHTML = '<span class="skel"></span><span class="skel"></span><span class="skel"></span>'; }
    var qd = '&deporte=' + encodeURIComponent(C.dep || '');
    fetch('/web/descubrir?lat=' + lat + '&lng=' + lng + qd).then(function(r){ return r.json(); })
      .then(function(j){ pintarDescubiertas(j.canchas || [], false);
        if((j.canchas || []).length) fetch('/web/descubrir?lat=' + lat + '&lng=' + lng + qd + '&fotos=1').then(function(r){ return r.json(); }).then(function(j2){ if((j2.canchas || []).length) pintarDescubiertas(j2.canchas, true); }).catch(function(){}); })
      .catch(function(){ if(sec && !Object.keys(descAcum).length) sec.style.display = 'none'; });
  }
  // ── mapa (se dibuja al mostrarlo; split view en escritorio, pantalla completa en móvil) ──
  function pintarMapa(){
    if(mapa || !window.L || !$('mapa')) return;
    mapa = L.map('mapa', {scrollWheelZoom: true}).setView(C.centro, 12);
    // Al mover el mapa a otra zona se descubren también las canchas de AHÍ
    // (antes solo se buscaba alrededor del usuario: un local a 3 km no salía).
    var tMove = null;
    mapa.on('moveend', function(){ if(mapa.getZoom() < 12) return; clearTimeout(tMove); tMove = setTimeout(function(){ var c = mapa.getCenter(); descubrir(c.lat, c.lng); }, 500); });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; OpenStreetMap'}).addTo(mapa);
    var pts = [];
    cards().forEach(function(c){
      var lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng); if(!lat && !lng) return;
      if(c.classList.contains('pend') && c.dataset.id.indexOf('gp_') === 0) return;
      pts.push([lat, lng]);
      var ok = c.dataset.ok === '1', esAca = c.classList.contains('aca');
      var m = L.marker([lat, lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio' + (ok ? '' : ' pend') + (esAca ? ' aca' : '') + '">' + c.dataset.precio + '</span>', iconSize: null})});
      m._card = c;
      m.bindPopup('<b>' + esc(c.dataset.nombre) + '</b><br>' + esc(c.dataset.sub) + '<br>' + (esAca ? '' : '<span style="font-weight:800">' + esc(c.dataset.precio) + ' por hora</span><br>') + '<a class="btn' + (ok ? '' : ' sec') + '" href="' + c.getAttribute('href') + '">' + (esAca ? 'Ver academia' : (ok ? 'Ver horarios' : 'Reservar en la app')) + '</a>');
      m.on('mouseover', function(){ c.style.outline = '2px solid #0E8F67'; c.style.outlineOffset = '4px'; c.style.borderRadius = '14px'; });
      m.on('mouseout', function(){ c.style.outline = ''; });
      marcadores.push(m); m.addTo(mapa);
    });
    if(yo){ miPin = L.marker([yo.lat, yo.lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio yo">Tú</span>', iconSize: null})}).addTo(mapa); pts.push([yo.lat, yo.lng]); }
    if(pts.length) mapa.fitBounds(L.latLngBounds(pts).pad(0.25), {maxZoom: 13});
    // Las descubiertas ya pintadas también van al mapa.
    var desc = Array.prototype.slice.call(document.querySelectorAll('#gridDesc .lst'));
    desc.forEach(function(c){ var m = L.marker([parseFloat(c.dataset.lat), parseFloat(c.dataset.lng)], {icon: L.divIcon({className: '', html: '<span class="pin-precio pend">' + esc(c.dataset.precio) + '</span>', iconSize: null})}).addTo(mapa);
      m.bindPopup('<b>' + esc(c.dataset.nombre) + '</b><br>' + esc(c.dataset.sub) + '<br><a class="btn sec" href="' + c.getAttribute('href') + '">Ver lugar</a>'); pinesDesc.push(m); });
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
              ("basquet", "Básquet", "🏀"), ("academias", "Academias", "🎓")]


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
        f"<label class='seg donde'><small>Dónde</small><input id='sQ' placeholder='{'Busca academias por nombre o zona' if dep == 'academias' else 'Explora zonas, clubes o canchas'}' autocomplete='off'></label>"
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


AMENIDAD_ICONO = {**{k: v[1] for k, v in catalogos.AMENIDADES.items()},
                  "estacionamiento": "🅿️", "vestuarios": "👕", "iluminacion": "💡", "techada": "🏠",
                  "tribuna": "🪑", "seguridad": "🛡️"}
_RECOMENDADAS = ("parking", "luces", "vestuario", "techado", "estacionamiento", "iluminacion", "vestuarios", "techada")


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
        + "<section><h4>Rango de precios</h4><p class='sub' id='precioSub'>Precio por hora</p>"
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


def _hm_min(h: str, default: str) -> int:
    """'HH:MM' → minutos del día (tolerante)."""
    try:
        hh, mm = (h or default).split(":")[:2]
        return int(hh) * 60 + int(mm)
    except Exception:  # noqa: BLE001
        hh, mm = default.split(":")
        return int(hh) * 60 + int(mm)


def _agrupar_locales(lista: list[dict]) -> list[list[dict]]:
    """Agrupa las canchas por LOCAL (`club`, sin distinguir mayúsculas), como
    `Club.agrupar` del app: una tarjeta por local en el explorador. Una cancha
    sin `club` es su propio local. Conserva el orden de llegada."""
    orden: list[str] = []
    mapa: dict[str, list[dict]] = {}
    for c in lista:
        club = (c.get("club") or "").strip().lower()
        k = f"club:{club}" if club else f"id:{c['id']}"
        if k not in mapa:
            orden.append(k)
            mapa[k] = []
        mapa[k].append(c)
    return [mapa[k] for k in orden]


def _tarjeta(canchas: list[dict] | dict, ratings: dict | tuple | None = None, fecha: str = "") -> str:
    """Tarjeta del explorador = UN LOCAL con sus canchas (queja del director,
    sep-2026: "sigue saliendo el nombre de la cancha como nombre del local").
    Igual que `ClubCard` del app: título = local, debajo zona, "N canchas ·
    deportes · horario", precio "desde" el más barato y ★ promedio de todas
    sus canchas. Enlaza a la ficha de la primera cancha (la ficha ya tiene
    chips para cambiar de cancha dentro del local). Los `data-*` que usa el
    JS (hora libre, precio, duración, superficie, amenidades, mapa, fotos)
    reúnen los valores de TODAS las canchas del local (`data-ids`,
    `data-pasos`, `data-sup` con varias superficies)."""
    cs = [canchas] if isinstance(canchas, dict) else list(canchas)
    if isinstance(ratings, tuple) or ratings is None:
        ratings = {cs[0]["id"]: ratings} if ratings else {}
    c = cs[0]
    sim, _iso = _moneda_de(c)
    local = _titulo_local(c)
    deps: list[str] = []
    for x in cs:
        for d in _deportes_de(x):
            if d not in deps:
                deps.append(d)
    deps_txt = " · ".join(_deporte(d)[0] for d in deps[:3])
    nombres = " ".join(x["nombre"] for x in cs)
    texto = f"{local} {nombres} {_zona(c)} {deps_txt} {c.get('direccion', '')}".lower()
    sub = _zona(c) or (c.get("direccion") or "")
    ok = all(datos.reservable(x) for x in cs)
    fs: list[str] = []
    for x in cs:
        for u in _fotos(x):
            if u not in fs:
                fs.append(u)
    if fs:
        fotos = "".join(f"<img src='{e(u)}' alt='' loading='lazy'>" for u in fs[:5])
    else:
        fotos = f"<div class='sinfoto' data-buscar='1'>{_deporte(c.get('deporte'))[1]}</div>"
    extra = ""
    if len(fs) > 1:
        extra = ("<button class='flecha izq' aria-label='Anterior'>‹</button><button class='flecha der' aria-label='Siguiente'>›</button>"
                 f"<div class='dots'>{''.join('<i></i>' for _ in fs[:5])}</div>")
    badge = "<span class='badge'>✓ Verificada</span>" if ok else "<span class='badge pend'>Aún sin verificar</span>"
    # ★ del local = promedio ponderado de las reseñas de todas sus canchas.
    suma = 0.0
    n_res = 0
    for x in cs:
        r = ratings.get(x["id"]) if isinstance(ratings, dict) else None
        if r and r[1] > 0:
            suma += float(r[0]) * int(r[1])
            n_res += int(r[1])
    if n_res:
        rate = f"<span class='rate'>★ {suma / n_res:.1f}".replace(".", ",") + f" <span style='color:var(--tenue);font-weight:600'>({n_res})</span></span>"
    else:
        rate = "<span class='rate' style='color:var(--tenue);font-weight:600'>Nuevo</span>"
    # Horario del local: el más temprano en abrir y el último en cerrar (el
    # cierre que cruza medianoche cuenta como día siguiente).
    aps = [(_hm_min(x.get("hora_apertura"), "07:00"), x.get("hora_apertura") or "07:00") for x in cs]
    ap_txt = min(aps)[1]
    cis = []
    for x in cs:
        a = _hm_min(x.get("hora_apertura"), "07:00")
        ci = _hm_min(x.get("hora_cierre"), "23:00")
        cis.append((ci + 1440 if ci <= a else ci, x.get("hora_cierre") or "23:00"))
    ci_txt = max(cis)[1]
    pasos: list[int] = []
    for x in cs:
        pv = int(x.get("duracion_slot_min") or 60)
        if pv not in pasos:
            pasos.append(pv)
    paso_txt = "/".join(str(pv) for pv in sorted(pasos))
    ams: list[str] = []
    sups: list[str] = []
    for x in cs:
        for a in (x.get("amenidades") or []):
            if str(a) not in ams:
                ams.append(str(a))
        sp = (x.get("superficie") or "").strip().lower()
        if sp and sp not in sups:
            sups.append(sp)
    precios = [float(x.get("precio_hora") or 0) for x in cs if float(x.get("precio_hora") or 0) > 0]
    pmin = min(precios) if precios else float(c.get("precio_hora") or 0)
    desde = "desde " if len(cs) > 1 and len(set(precios)) > 1 else ""
    n = len(cs)
    n_txt = f"{n} cancha{'s' if n != 1 else ''}"
    base = f"/reservar/{c['id']}"
    href = base + (f"?fecha={fecha}" if fecha else "")
    precio_html = f"<b>{e(sim)} {pmin:.0f}</b> <span style='color:var(--tenue)'>por hora</span>"
    if desde:
        precio_html = f"<span style='color:var(--tenue)'>desde</span> " + precio_html
    l3 = (f"<div class='l3'>{precio_html}</div>" if ok else
          f"<div class='l3'>{precio_html}<br><span class='app'>📲 Reservar en la app</span></div>")
    # Debajo del local, la(s) cancha(s): una sola → su nombre; varias → "N canchas".
    canchas_txt = cs[0]["nombre"] if n == 1 and cs[0]["nombre"].strip().lower() != local.strip().lower() else n_txt
    return (f"<a class='lst{'' if ok else ' pend'}' href='{e(href)}' data-base='{e(base)}' data-id='{e(c['id'])}' data-ids='{e(' '.join(x['id'] for x in cs))}' data-t='{e(texto)}' "
            f"data-ap='{e(ap_txt)}' data-ci='{e(ci_txt)}' data-paso='{int(c.get('duracion_slot_min') or 60)}' data-pasos='{e(' '.join(str(pv) for pv in pasos))}' "
            f"data-am='{e(' '.join(ams))}' data-sup='{e(' '.join(sups))}' data-mon='{e(sim)}' "
            f"data-deps='{e(' '.join(deps))}' data-lat='{c.get('lat')}' data-lng='{c.get('lng')}' data-nombre='{e(local)}' data-club='{e(c.get('club', ''))}' "
            f"data-sub='{e(sub)}' data-precio='{e(desde)}{e(sim)} {pmin:.0f}' data-pnum='{pmin:.2f}' data-ok='{1 if ok else 0}'>"
            f"<div class='foto'><div class='fotos'>{fotos}</div>{badge}"
            f"<button class='corazon' aria-label='Guardar'>{_CORAZON}</button>{extra}</div>"
            f"<div class='lb'><div class='l1'><b>{e(local)}</b>{rate}</div>"
            f"<div class='l2'>{e(sub)}</div>"
            f"<div class='l2'>{e(canchas_txt)} · {e(deps_txt)} · {e(ap_txt)}–{e(ci_txt)} · {e(paso_txt)} min <span class='dist'></span></div>"
            f"{l3}</div></a>")


# Redes de la academia (`Academia.redes`: red → @usuario o enlace). Íconos SVG
# inline (currentColor) para no depender de fuentes ni emojis.
_RED_SVG = ui.RED_SVG  # logos compartidos con el pie (redes oficiales) y la ficha de academia


def _url_red(red: str, valor: str) -> str:
    """Enlace directo a la red: acepta URL completa o @usuario (como lo guarda
    el app). Vacío si no se puede armar."""
    v = (valor or "").strip()
    if not v:
        return ""
    if v.startswith("http://") or v.startswith("https://"):
        return v
    h = v.lstrip("@").strip("/ ")
    if not h:
        return ""
    base = {"instagram": "https://instagram.com/{h}", "facebook": "https://facebook.com/{h}", "tiktok": "https://www.tiktok.com/@{h}",
            "youtube": "https://youtube.com/@{h}", "web": "https://{h}"}.get(red)
    return base.format(h=h) if base else ""


def _botones_redes(a: dict) -> str:
    """Un botón por red registrada, con su logo y enlace directo (pedido del
    director, sep-2026). Sin redes → nada."""
    redes = a.get("redes") if isinstance(a.get("redes"), dict) else {}
    out = []
    for red, nombre in catalogos.REDES.items():
        url = _url_red(red, str(redes.get(red) or ""))
        if url:
            out.append(f" <span class='app red-{red}'><span class='wa' data-wa='{e(url)}'>{_RED_SVG.get(red, '')} {e(nombre)}</span></span>")
    return "".join(out)


def _landing_lista(academia_id: str) -> bool:
    """La página pública `/l/{id}` solo existe si el dueño la GENERÓ desde el
    app (`stores.landings`); si no, `/l/{id}` responde "Landing no disponible"."""
    try:
        from db.store import stores as _st
        return academia_id in (_st.landings or {})
    except Exception:  # noqa: BLE001
        return False


def _tarjeta_academia(a: dict) -> str:
    """Tarjeta de ACADEMIA en el explorador (pedido del director, sep-2026:
    las academias también se ven por deporte y por cercanía). Enlaza a su
    página pública `/l/{id}`; WhatsApp y Cómo llegar como las descubiertas.
    Comparte la grilla y el orden por distancia de las canchas (`.lst.aca`,
    `data-lat/lng`) pero NO entra en los filtros de hora, precio ni amenidades."""
    dep = (a.get("deporte") or "").lower()
    dep_nombre, emoji = _deporte(dep) if dep else ("Academia", "🎓")
    iso = _pais_de(a) if (a.get("lat") or a.get("lng")) else ""
    sim = (a.get("moneda") or "").strip() or (simbolo_de_moneda(moneda_de_pais(iso)) if iso else "S/")
    precios = [float(p.get("precioMes") or 0) for p in (a.get("planes") or []) if isinstance(p, dict) and float(p.get("precioMes") or 0) > 0]
    programas = {str(p.get("programa") or p.get("nombre") or "") for p in (a.get("planes") or []) if isinstance(p, dict)}
    desde = f"<b>{e(sim)} {min(precios):.0f}</b> <span style='color:var(--tenue)'>al mes desde</span>" if precios else "<span style='color:var(--tenue)'>Consulta precios</span>"
    fs = [u for u in ([a.get("logoUrl")] + list(a.get("fotos") or [])) if isinstance(u, str) and u.startswith("http")]
    foto = "".join(f"<img src='{e(u)}' alt='' loading='lazy'>" for u in fs[:3]) if fs else f"<div class='sinfoto'>{emoji}</div>"
    extra = ""
    if len(fs) > 1:
        extra = ("<button class='flecha izq' aria-label='Anterior'>‹</button><button class='flecha der' aria-label='Siguiente'>›</button>"
                 f"<div class='dots'>{''.join('<i></i>' for _ in fs[:3])}</div>")
    tel = re.sub(r"\D", "", str(a.get("whatsapp") or ""))
    pref = catalogos.TEL_PREFIJO.get(iso or "PE", "51")
    if tel and not tel.startswith(pref) and len(tel) <= 10:
        tel = pref + tel
    # OJO: la tarjeta ya es un <a>; un <a> anidado rompe el HTML (el navegador parte la tarjeta). Va como <span> con manejador, igual que "Cómo llegar".
    wa = (f" <span class='app'>💬 <span class='wa' data-wa='https://wa.me/{tel}?text=Hola,%20vi%20tu%20academia%20en%20Pichangol'>WhatsApp</span></span>" if tel else "")
    ir = (f" <span class='app'>📍 <span class='ir' data-lat='{a.get('lat')}' data-lng='{a.get('lng')}'>Cómo llegar</span></span>" if a.get("lat") or a.get("lng") else "")
    sub = " · ".join(x for x in (a.get("sedeClub"), a.get("zona")) if x)
    n_prog = len([x for x in programas if x])
    texto = f"{a.get('nombre', '')} {a.get('sedeClub', '')} {a.get('zona', '')} {dep_nombre} academia clases".lower()
    # La tarjeta abre la FICHA WEB /academia/{id} (programas, tarifario y
    # matrícula), que existe siempre; la landing /l/{id} (marketing, la genera
    # el dueño desde el app) se enlaza desde la ficha si existe.
    redes_html = _botones_redes(a)
    ver = "<span class='app'>Ver academia</span>"
    return (f"<a class='lst aca' href='/academia/{e(a['id'])}' data-id='ac:{e(a['id'])}' data-t='{e(texto)}' data-deps='{e(dep)}' "
            f"data-lat='{a.get('lat') or ''}' data-lng='{a.get('lng') or ''}' data-nombre='{e(a.get('nombre', ''))}' data-sub='{e(sub)}' "
            f"data-precio='🎓 {e(dep_nombre)}' data-ok='1'>"
            f"<div class='foto'><div class='fotos'>{foto}</div><span class='badge aca'>🎓 Academia</span>{extra}</div>"
            f"<div class='lb'><div class='l1'><b>{e(a.get('nombre', ''))}</b><span class='rate'>{emoji} {e(dep_nombre)}</span></div>"
            f"<div class='l2'>{e(sub) or e(a.get('descripcion', '')[:60])}</div>"
            f"<div class='l2'>{(str(n_prog) + ' programa' + ('s' if n_prog != 1 else '') + ' · ') if n_prog else ''}<span class='dist'></span></div>"
            f"<div class='l3'>{desde}<br>{ver}{redes_html}{wa}{ir}</div></div></a>")


def _explorar(deporte: str = "", fecha: str = "", request: Request | None = None, hora: str = "") -> HTMLResponse:
    """RAÍZ del dominio, tipo Airbnb: buscador en pastilla, categorías por
    deporte, grilla de tarjetas con foto/corazón/★, "Mostrar mapa" (split
    view en escritorio), cercanía por ubicación y canchas descubiertas en
    Google; debajo, las secciones de marca/comercio (servicios y precios,
    términos, cancelaciones, Libro de Reclamaciones) que revisan Culqi e
    INDECOPI."""
    # Solo canchas APROBADAS (verificada + dueño), como el explorador del app:
    # una cancha en verificación no sale al público hasta que la torre la
    # apruebe (regla del director, sep-2026; antes salían con "Aún sin verificar").
    todas = [c for c in datos.canchas_publicas() if datos.reservable(c)]
    dep = (deporte or "").strip().lower()
    # Pestaña "🎓 Academias" (pedido del director, sep-2026): solo academias,
    # de todos los deportes; sin canchas registradas ni descubiertas.
    solo_aca = dep == "academias"
    lista = [] if solo_aca else [c for c in todas if not dep or dep in _deportes_de(c)]
    fecha = fecha if _es_iso(fecha) else ""
    ratings = datos.ratings([c["id"] for c in lista])
    print(f"[explorar] dep={dep or '*'} {len(lista)} canchas: " + " | ".join(
        f"{c['nombre']} {c['hora_apertura']}-{c['hora_cierre']}/{c['duracion_slot_min']}m{'' if datos.reservable(c) else ' (pend)'}"
        for c in lista[:20]), flush=True)
    por_pais: dict[str, list[dict]] = {}
    for c in lista:
        por_pais.setdefault(_pais_de(c), []).append(c)
    cuerpo = ("<div class='ubic-mini'><span>📍</span><span id='ubicTxt'>Permite tu ubicación para ver primero las canchas más cercanas.</span>"
              "<button id='btnUbic'>Usar mi ubicación</button><span id='resBusq'></span></div>")
    if not solo_aca:  # amenidades / precio por hora no aplican a academias
        cuerpo += _barra_filtros(lista) + _modal_filtros(lista)
    cuerpo += "<div class='expl' id='expl'><div class='lista'><div id='grupos'>"
    for pais in ("PE", "EC", "BO"):
        lst = por_pais.get(pais) or []
        if not lst:
            continue
        cards = "".join(_tarjeta(grupo, ratings, fecha) for grupo in _agrupar_locales(lst))  # una tarjeta por LOCAL, como el app
        cuerpo += (f"<section class='grupo-pais' data-pais='{pais}'><div class='tit'><h2>{ui.bandera(pais)} Canchas en {NOMBRE_PAIS[pais]}"
                   f"<span class='cerca'></span></h2></div><div class='lst-grid'>{cards}</div></section>")
    cuerpo += "</div>"
    if solo_aca:
        cuerpo += "<div class='vacio' id='vacio' data-base='' style='display:none'>No encontramos academias con esa búsqueda. Prueba con otro nombre o zona.</div>"
    elif not lista:
        cuerpo += ("<div class='vacio' id='vacio'><h3>Todavía no hay canchas publicadas aquí</h3>"
                   "<p class='sub'>Estamos sumando locales. En la app ya puedes explorar el mapa completo.</p>"
                   f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    else:
        cuerpo += "<div class='vacio' id='vacio' data-base='' style='display:none'>No hay canchas libres con esa búsqueda. Prueba con otra zona, día u hora.</div>"
    if todas and not lista and not solo_aca:
        cuerpo += ("<div class='vacio'>Todavía no hay canchas de este deporte. "
                   "<a href='/canchas'>Ver todas las canchas</a></div>")
    dep_aca = "" if solo_aca else dep
    acads = [a for a in datos.academias_publicas() if isinstance(a, dict) and a.get("nombre") and (not dep_aca or (a.get("deporte") or "").lower() == dep_aca)]
    if acads:
        titulo_aca = "Academias" + (f" de {_deporte(dep_aca)[0].lower()}" if dep_aca else "")
        cuerpo += (f"<section id='academias' class='grupo-aca'><div class='tit'><h2>🎓 {e(titulo_aca)}<span class='cerca'></span></h2></div>"
                   "<p class='sub' style='margin:-4px 0 12px'>Clases y programas por nivel. Entra a su página, escribe por WhatsApp o matricúlate en línea.</p>"
                   f"<div class='lst-grid' id='gridAca'>{''.join(_tarjeta_academia(a) for a in acads)}</div></section>")
    elif solo_aca:
        cuerpo += ("<div class='vacio'><h3>Todavía no hay academias publicadas</h3>"
                   "<p class='sub'>Si tienes una academia, publícala desde Modo anfitrión → Mi academia.</p>"
                   "<div class='acciones' style='justify-content:center'><a class='btn' href='/anfitrion/academia'>Publicar mi academia</a>"
                   "<a class='btn sec' href='/canchas'>Ver canchas</a></div></div>")
    if not solo_aca:
        cuerpo += ("<section id='descubiertas' style='display:none'><div class='tit'><h2>Más canchas cerca de ti</h2></div>"
                   "<p class='sub' style='margin:-4px 0 12px'>Locales que aún no están en Pichangol. Reserva desde la app o, si es tu "
                   "cancha, ¡Reclámala! y empieza a recibir reservas.</p><div class='lst-grid' id='gridDesc'></div></section>")
    cuerpo += "</div><aside class='mapa-lado'><div class='mapa' id='mapa' aria-label='Mapa de canchas'></div></aside></div>"
    cuerpo += "<button class='btn-mapa' id='btnMapa'><span>Mostrar mapa</span> 🗺️</button>"
    css_m, html_m, js_m = marca.secciones()
    if html_m:
        cuerpo += f"<div class='marca'>{html_m}</div>"
    centro = list(CIUDAD_DEFECTO["PE"])
    c0 = lista[0] if lista else next((a for a in acads if a.get("lat") and a.get("lng")), None)
    if c0:
        centro = [c0.get("lat") or centro[0], c0.get("lng") or centro[1]]
    hora = hora if horarios.hora_en_minutos(hora) is not None else ""
    cfg = json.dumps({"cajas": {k: list(v) for k, v in _CAJAS.items()}, "centro": centro, "play": PLAY_URL, "dep": dep,
                      "fecha": fecha, "hora": hora, "diasAdelante": DIAS_ADELANTE, "lugares": bool(config.PLACES_API_KEY)})
    head = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
            "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>"
            + (f"<style>{css_m}</style>" if css_m else ""))
    cuerpo += f"<script>window.__explorar={cfg};</script><script>{_JS_EXPLORAR}</script>"
    if js_m:
        cuerpo += f"<script>{js_m}</script>"
    canonical = f"{config.PUBLIC_BASE_URL.rstrip('/')}/" if getattr(config, "PUBLIC_BASE_URL", "") else ""
    ses = sesion.de_request(request)
    titulo_tab = ("Pichangol · Academias deportivas cerca de ti" if solo_aca
                  else "Pichangol · Reserva canchas de fútbol, tenis y pádel")
    desc = ("Academias de tenis, fútbol, pádel y más cerca de ti: programas, tarifario y matrícula en línea." if solo_aca
            else "Reserva canchas de fútbol, tenis y pádel cerca de ti y paga con Yape o tarjeta. Perú, Ecuador y Bolivia.")
    return ui.shell("Pichangol", cuerpo, extra_head=head, nav=_nav_explorar(dep, ses, _zonas_sugeridas(lista)), ancho=True, sesion=ses,
                    titulo_tab=titulo_tab, canonical=canonical, desc=desc)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def pagina_inicio(request: Request, deporte: str = "", fecha: str = "", hora: str = "") -> HTMLResponse:
    return _explorar(deporte, fecha, request, hora)


@router.get("/canchas", response_class=HTMLResponse)
def pagina_canchas(request: Request, deporte: str = "", fecha: str = "", hora: str = "") -> HTMLResponse:
    """Alias histórico del explorador (enlaces de la app, la home y el pie)."""
    return _explorar(deporte, fecha, request, hora)


# ── descubrir (Google Places, como el APK) ────────────────────────────────────

@router.get("/web/descubrir")
def descubrir_web(lat: float, lng: float, fotos: int = 0, deporte: str = "") -> dict:
    """Canchas que Google conoce cerca del usuario y aún no están en Pichangol:
    salen en el explorador con "Reservar en la app". Misma Edge Function y
    heurística que el APK; caché por zona. `deporte` = la pestaña activa (en
    Tenis no salen canchas de fútbol; queja del director, sep-2026)."""
    region = pais_de_coordenadas(lat, lng)
    reg = [{"nombre": c.get("nombre"), "club": c.get("club"), "lat": c.get("lat"), "lng": c.get("lng")}
           for c in datos.canchas_publicas() if datos.reservable(c) or (c.get("dueno") or "").strip()]
    lista = descubrir.descubrir_cerca(lat, lng, region=region, fotos=bool(fotos), registradas=reg)
    dep = (deporte or "").strip().lower()
    if dep:
        lista = [c for c in lista if (c.get("deporte") or "").lower() == dep]
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


class SesionPruebaReq(BaseModel):
    usuario: str
    clave: str


_revision_intentos: dict[str, tuple[int, float]] = {}   # ip -> (fallos, bloqueado_hasta)


@router.post("/web/sesion/prueba")
def abrir_sesion_prueba(req: SesionPruebaReq, request: Request, response: Response) -> dict:
    """Acceso de REVISIÓN (Culqi/INDECOPI): usuario + contraseña de
    `WEB_USUARIOS_PRUEBA` → la misma cookie firmada que el login con Google, así
    el revisor reserva, paga y ve el comprobante como un cliente. Anti fuerza
    bruta por IP real (5 fallos → 5 min)."""
    if not sesion.revision_activa():
        return {"ok": False, "error": "no_configurado"}
    xff = request.headers.get("x-forwarded-for", "")
    ip = (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "?"))[:64]
    fallos, hasta = _revision_intentos.get(ip, (0, 0.0))
    if time.time() < hasta:
        return {"ok": False, "error": "demasiados_intentos"}
    if not sesion.credenciales_prueba_validas(req.usuario, req.clave):
        fallos += 1
        _revision_intentos[ip] = (0, time.time() + 300) if fallos >= 5 else (fallos, 0.0)
        print(f"[web] acceso de revisión fallido usuario={req.usuario!r} ip={ip}", flush=True)
        return {"ok": False, "error": "credenciales_invalidas"}
    _revision_intentos.pop(ip, None)
    u = {"email": req.usuario.strip().lower(), "nombre": "Cuenta de revisión", "foto": ""}
    sesion.poner_cookie(response, sesion.emitir(u))
    print(f"[web] acceso de revisión OK usuario={u['email']} ip={ip}", flush=True)
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
              "<a href='/legal/privacidad'>política de privacidad</a>.</p>"
              + (("<div id='revision' style='margin-top:18px;padding-top:16px;border-top:1px solid #eee;text-align:left'>"
                  "<b style='font-size:14px'>Acceso de revisión</b>"
                  "<div class='sub' style='font-size:12.5px;margin:2px 0 10px'>Para revisores (Culqi, INDECOPI): usa el usuario y la contraseña que te entregó Pichangol.</div>"
                  "<label for='revUsr' style='font-size:12.5px;font-weight:700'>Usuario</label>"
                  "<input id='revUsr' autocomplete='username' maxlength='120' style='width:100%;margin:4px 0 10px'>"
                  "<label for='revPwd' style='font-size:12.5px;font-weight:700'>Contraseña</label>"
                  "<input id='revPwd' type='password' autocomplete='current-password' maxlength='120' style='width:100%;margin:4px 0 12px'>"
                  "<button type='button' class='btn' style='width:100%' onclick='entrarRevision()'>Entrar como revisor</button>"
                  "<div class='estado bad' id='revErr'></div></div>") if sesion.revision_activa() else "")
              + "</div>"
              f"<script>window.alIniciarSesion=function(){{location.href={json.dumps(v)};}};{sesion.JS_SESION}"
              "window.entrarRevision=function(){var u=document.getElementById('revUsr').value.trim(),c=document.getElementById('revPwd').value,er=document.getElementById('revErr');er.textContent='';"
              "fetch('/web/sesion/prueba',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario:u,clave:c})}).then(function(r){return r.json();})"
              ".then(function(j){if(j&&j.ok){window.alIniciarSesion(j);}else{er.textContent=j&&j.error==='demasiados_intentos'?'Demasiados intentos. Espera 5 minutos.':'Usuario o contraseña incorrectos.';er.style.display='block';}})"
              ".catch(function(){er.textContent='Sin conexión. Inténtalo de nuevo.';er.style.display='block';});};"
              "var rp=document.getElementById('revPwd');if(rp)rp.addEventListener('keydown',function(e){if(e.key==='Enter')entrarRevision();});</script>")
    return ui.shell("Iniciar sesión", cuerpo, extra_head=sesion.GIS_SCRIPT, sesion=None)


@router.get("/web/lugares")
def lugares_web(q: str = "", lat: float | None = None, lng: float | None = None) -> dict:
    """Busca un local en Google por NOMBRE (para "Pon tu cancha"). Sin
    `PLACES_API_KEY` responde `disponible:false` y el formulario esconde la caja."""
    if not config.PLACES_API_KEY:
        return {"ok": True, "disponible": False, "lugares": []}
    region = pais_de_coordenadas(lat, lng) if lat is not None else "PE"
    lugares = descubrir.buscar_lugares(q, lat, lng, region=region)
    for l in lugares:  # etiqueta + emoji como las descubiertas (el explorador reusa la tarjeta)
        l["deporte_nombre"], l["emoji"] = _deporte(l["deporte"]) if l.get("deporte") else ("Cancha", "🏟️")
    return {"ok": True, "disponible": True, "lugares": lugares}


@router.get("/web/foto")
def foto_web(id: str = "", nombre: str = "", club: str = "", lat: float = 0.0, lng: float = 0.0,
             refrescar: int = 0, x_admin_token: str | None = Header(default=None)) -> dict:
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
    # Solo con la CABECERA X-Admin-Token (sesión de la torre o token clásico); el
    # token ya no se acepta en la URL, donde queda en logs y en el historial.
    from propiedad import admin_auth as _aa
    forzar = bool(refrescar) and _aa.token_admin_valido(x_admin_token)
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
    # Diagnóstico en los logs de Railway (como las líneas [foto]): horario real de cada cancha y el veredicto.
    print(f"[libres] {fecha} {hora}: " + " | ".join(
        f"{c['nombre']} {c['hora_apertura']}-{c['hora_cierre']}/{c['duracion_slot_min']}m "
        f"{'libre' if out[c['id']] else ('ocupada' if any(h == hora for _f, h in ocup.get(c['id'], set())) else 'sin turno')}"
        for c in canchas[:20]), flush=True)
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
    // precio = TOTAL de la línea: por persona × cantidad elegida, por turno × turnos reservados.
    var n = Object.keys(sel).length || 1;
    return Array.prototype.map.call(document.querySelectorAll('input[name=extra]:checked'), function(x){
      var unit = parseFloat(x.value)||0, tipo = x.dataset.tipo || 'reserva', cant = 1;
      if(tipo === 'persona'){ var sc = x.parentNode.querySelector('select.cant'); cant = sc ? (parseInt(sc.value)||1) : 1; }
      else if(tipo === 'turno'){ cant = n; }
      return {clave: x.dataset.clave, nombre: x.dataset.nombre, tipo: tipo, cantidad: cant, unitario: unit, precio: unit * cant}; });
  }
  document.addEventListener('change', function(ev){
    var t = ev.target; if(!t) return;
    if(t.name === 'extra'){ var sc = t.parentNode.querySelector('select.cant'); if(sc) sc.disabled = !t.checked; }
    if(t.name === 'extra' || (t.classList && t.classList.contains('cant'))) pintarResumen();
  });
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
      extrasSel().forEach(function(x){ h += '<div class="linea"><span>' + esc(x.nombre) + (x.cantidad > 1 ? ' × ' + x.cantidad : '') + '</span><b>' + fmt(x.precio) + '</b></div>'; });
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
        // Turnos ORDENADOS por franja (Mañana / Tarde / Noche · madrugada) con el precio de cada uno a la vista.
        var hmm = function(t){ var p = t.split(':'); return parseInt(p[0]) * 60 + parseInt(p[1]); };
        var franjas = [['Mañana', '🌅', 0], ['Tarde', '☀️', 1], ['Noche', '🌙', 2]], grupos = [[], [], []];
        slots.forEach(function(s, i){ var m = hmm(s.hora); var g = s.fecha !== fechaSel ? 2 : (m < 12 * 60 ? 0 : (m < 18 * 60 ? 1 : 2)); grupos[g].push([s, i]); });
        var precios = slots.map(function(s){ return s.precio; }), pmin = Math.min.apply(null, precios), pmax = Math.max.apply(null, precios);
        var html = '';
        franjas.forEach(function(f, g){
          if(!grupos[g].length) return;
          var lib = grupos[g].filter(function(x){ return !x[0].ocupado; }).length;
          html += '<div class="slots-grupo"><h5>' + f[1] + ' ' + f[0] + ' <small>· ' + (lib ? lib + ' libre' + (lib === 1 ? '' : 's') : 'sin turnos libres') + '</small></h5><div class="slots-grid">';
          grupos[g].forEach(function(x){ var s = x[0], i = x[1];
            var dia = s.fecha !== fechaSel ? '<span class="dia">' + esc(C.etiquetas[s.fecha] || '') + ' · madrugada</span>' : '';
            var tag = s.promo ? '<span class="tag">−' + s.promo + ' % promo</span>' : (s.valle ? '<span class="tag">⚡ hora feliz</span>' : '');
            html += '<div class="slot' + (s.ocupado ? ' off' : '') + '" data-i="' + i + '" title="' + (s.ocupado ? 'Ocupado' : 'Disponible') + '">' +
                    dia + '<b>' + s.hora + ' <small>– ' + s.fin + '</small></b><span class="pr">' + (s.ocupado ? 'Ocupado' : fmt(s.precio)) + '</span>' + tag + '</div>';
          });
          html += '</div></div>';
        });
        if(pmax > pmin) html += '<p class="slots-nota">El precio varía según la hora: desde ' + fmt(pmin) + ' hasta ' + fmt(pmax) + ' por turno.</p>';
        $('slots').innerHTML = html + (libres ? '' : '<div class="sub" style="width:100%">Todos los turnos de este día están tomados.</div>');
        document.querySelectorAll('#slots .slot').forEach(function(el){
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
            if(!slots[j].ocupado && a <= ww && ww < b){ var chip = document.querySelector('#slots .slot[data-i="' + j + '"]'); if(chip){ chip.click(); chip.scrollIntoView({behavior: 'smooth', block: 'center'}); } break; }
          }
        }
      }).catch(function(){ $('slots').innerHTML = '<span class="sub">No pudimos cargar los horarios.</span>'; });
  }
  // "Cómo llegar": el mapa se abre AQUÍ (Leaflet + OpenStreetMap), no en otra pestaña.
  var bLlegar = $('btnLlegar'), mapaFicha = null;
  if(bLlegar) bLlegar.addEventListener('click', function(ev){
    ev.preventDefault();
    var box = $('mapaFicha'), on = !box.classList.contains('open');
    box.classList.toggle('open', on); bLlegar.textContent = on ? 'Ocultar mapa' : 'Cómo llegar';
    if(on && !mapaFicha && window.L){
      var lat = parseFloat(bLlegar.dataset.lat), lng = parseFloat(bLlegar.dataset.lng);
      mapaFicha = L.map('mapaFichaMapa', {scrollWheelZoom: false}).setView([lat, lng], 16);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(mapaFicha);
      L.marker([lat, lng]).addTo(mapaFicha).bindPopup('<b>' + esc(bLlegar.dataset.nombre) + '</b>').openPopup();
      setTimeout(function(){ mapaFicha.invalidateSize(); }, 80);
    } else if(on && mapaFicha){ setTimeout(function(){ mapaFicha.invalidateSize(); }, 80); }
    if(on) box.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  });
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
    var extras = extrasSel().map(function(x){ return {clave: x.clave, cantidad: x.cantidad}; });
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
              }).catch(function(){ mostrarError('No pudimos confirmar el pago. Escríbenos a ' + CORREO_SOPORTE + ' con tu correo y horario.'); pintarResumen(); });
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


def _titulo_local(c: dict) -> str:
    """Nombre del LOCAL (club); si la cancha no tiene local, su propio nombre."""
    return (c.get("club") or "").strip() or c["nombre"]


def _hermanas(c: dict, ses: dict | None = None) -> list[dict]:
    """Canchas del MISMO local (mismo `club`), para los chips de la ficha: las
    aprobadas y, si quien mira es el dueño, también las suyas en verificación."""
    club = (c.get("club") or "").strip().lower()
    if not club:
        return [c]
    yo = ((ses or {}).get("email") or "").lower()
    out = [x for x in datos.canchas_publicas()
           if (x.get("club") or "").strip().lower() == club
           and (datos.reservable(x) or x["id"] == c["id"] or (yo and (x.get("dueno") or "").lower() == yo))]
    return out or [c]


def _ficha(c: dict, sim: str, pais: str, verificada: bool = True, hermanas: list[dict] | None = None) -> str:
    """Cabecera de la ficha pública: como `club_detalle_screen` del app, el
    TÍTULO es el LOCAL y la cancha va debajo (antes salía "Cancha-01" grande
    y el local chico; queja del director, sep-2026). Con varias canchas en el
    local, chips para cambiar de cancha."""
    sello = ui.sello_verificada() if verificada else "<span class='pill gris'>Aún sin verificar</span>"
    lugar = ", ".join(x for x in (c.get("direccion"), _zona(c)) if x)
    deps = " · ".join(_deporte(d)[0] for d in _deportes_de(c))
    amen = "".join(f"<span>{e(AMENIDAD_NOMBRE.get(str(a).lower(), str(a).replace('_', ' ').capitalize()))}</span>"
                   for a in (c.get("amenidades") or [])[:8])
    local = _titulo_local(c)
    hs = hermanas or [c]
    if len(hs) > 1:
        chips = "".join(f"<a class='chip{' sel' if x['id'] == c['id'] else ''}' href='/reservar/{quote(str(x['id']), safe='')}'>"
                        f"{_deporte(x.get('deporte'))[1]} {e(x['nombre'])}</a>" for x in hs)
        cancha_linea = (f"<div class='sub' style='margin-top:6px'>{len(hs)} canchas en este local · elige una:</div>"
                        f"<div class='chips' style='margin-top:6px'>{chips}</div>")
    else:
        cancha_linea = f"<p class='sub' style='margin-top:4px'>{_deporte(c.get('deporte'))[1]} {e(c['nombre'])}</p>"
    return (f"{_galeria(c)}"
            "<div style='display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-top:16px'>"
            f"<div style='min-width:0'><div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'>"
            f"<span class='pill gris'>{ui.bandera(pais)} {e(deps)}</span>{sello}</div>"
            f"<h1 style='margin-top:8px'>{e(local)}</h1>{cancha_linea}</div>"
            f"<div class='precio' style='font-size:22px;white-space:nowrap'>{e(sim)} {c['precio_hora']:.2f} <small>por hora</small></div></div>"
            "<ul class='datos'>"
            f"<li>📍 <span>{e(lugar or 'Dirección en la app')} · <a href='#mapaFicha' id='btnLlegar' data-lat='{c.get('lat')}' data-lng='{c.get('lng')}' data-nombre='{e(local)}'>Cómo llegar</a></span></li>"
            f"<li>🕒 <span>{e(c['hora_apertura'])} a {e(c['hora_cierre'])} · turnos de {c['duracion_slot_min']} min · último turno {e(c['hora_cierre'])}</span></li>"
            + (f"<li>⚡ <span>Hora feliz −{c['descuento_valle']} % de {e(c['valle_desde'] or '00:00')} a {e(c['valle_hasta'] or '12:00')}</span></li>" if c['descuento_valle'] > 0 else "")
            + (f"<li>🏟️ <span>{e(c['superficie'])}</span></li>" if c.get("superficie") else "")
            + "</ul>"
            "<div class='mapa-ficha' id='mapaFicha'><div class='mapa' id='mapaFichaMapa' aria-label='Mapa de la cancha'></div>"
            f"<div class='pie-mapa'><span>📍 {e(lugar or local)}</span><a href='{_maps(c)}' target='_blank' rel='noopener'>Abrir en Google Maps</a>"
            f"<a href='https://www.google.com/maps/dir/?api=1&destination={c.get('lat')},{c.get('lng')}' target='_blank' rel='noopener'>Indicaciones paso a paso</a></div></div>"
            + (f"<div class='amen'>{amen}</div>" if amen else ""))


def _jsonld_cancha(c: dict, sim: str) -> str:
    return json.dumps({
        "@context": "https://schema.org", "@type": "SportsActivityLocation",
        "name": (f"{c['club']} · {c['nombre']}" if (c.get("club") or "").strip() else c["nombre"]), "image": _fotos(c)[:1],
        "address": {"@type": "PostalAddress", "streetAddress": c.get("direccion") or "",
                    "addressLocality": _zona(c), "addressCountry": _pais_de(c)},
        "geo": {"@type": "GeoCoordinates", "latitude": c.get("lat"), "longitude": c.get("lng")},
        "priceRange": f"{sim} {c['precio_hora']:.2f} por hora",
        "url": f"{config.PUBLIC_BASE_URL.rstrip('/')}/reservar/{c['id']}" if getattr(config, 'PUBLIC_BASE_URL', '') else "",
    }, ensure_ascii=False)


@router.get("/lugar/{lugar_id}", response_class=HTMLResponse)
def pagina_lugar(request: Request, lugar_id: str, nombre: str = "", direccion: str = "", lat: float = 0.0, lng: float = 0.0, deporte: str = "") -> HTMLResponse:
    """Ficha de un lugar DESCUBIERTO en Google que aún no está en Pichangol
    (antes la tarjeta mandaba a Play y no había dónde reclamarlo): fotos del
    lugar, cómo llegar, "Reservar en la app" y, en grande, "¿Es tuya?
    Reclámala" → registro web prellenado. Si el lugar ya fue registrado, va a
    su ficha real."""
    if not lugar_id.startswith("gp_") or not nombre.strip() or not (lat or lng):
        r = _no_encontrada("Lugar no disponible"); r.status_code = 404
        return r
    ses = sesion.de_request(request)
    nombre = re.sub(r"\s+", " ", nombre).strip()[:120]
    direccion = re.sub(r"\s+", " ", direccion).strip()[:200]
    dep = deporte if deporte in DEPORTES else ""
    c = {"id": lugar_id, "nombre": nombre, "club": "", "direccion": direccion, "lat": lat, "lng": lng, "deporte": dep or "futbol", "fotos": [], "foto_url": ""}
    pais = _pais_de(c)
    q = f"place={quote(lugar_id, safe='')}&nombre={quote(nombre)}&direccion={quote(direccion)}&lat={lat}&lng={lng}&deporte={quote(dep)}"
    cuerpo = (
        f"<div style='padding-top:22px'>{_galeria(c)}"
        "<div style='display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-top:16px'>"
        f"<div><div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><span class='pill gris'>{ui.bandera(pais)} {e(_deporte(dep)[0]) if dep else 'Cancha'}</span>"
        "<span class='pill gris'>Aún sin registrar</span></div>"
        f"<h1 style='margin-top:8px'>{e(nombre)}</h1><p class='sub'>{e(direccion) or 'Lugar encontrado en Google Maps'}</p></div></div>"
        "<ul class='datos'>"
        f"<li>📍 <span>{e(direccion or nombre)} · <a href='{_maps(c)}' target='_blank' rel='noopener'>Abrir en Google Maps</a> · "
        f"<a href='https://www.google.com/maps/dir/?api=1&destination={lat},{lng}' target='_blank' rel='noopener'>Indicaciones</a></span></li>"
        "<li>🕒 <span>Horarios y precios aún no publicados: este local todavía no está en Pichangol.</span></li></ul></div>"
        "<div class='panel' style='margin-top:20px;border:1px solid var(--verde)'><h2>¿Es tuya esta cancha?</h2>"
        "<p class='sub'>Publícala en Pichangol en 5 minutos: horarios, precios y fotos. Confirmamos que eres el dueño y empiezas a recibir reservas y pagos en línea.</p>"
        f"<div class='acciones'><a class='btn' href='/anfitrion/nueva?{q}'>🏷️ Reclámala y recibe reservas</a></div></div>"
        "<div class='panel' style='margin-top:16px'><h2>¿Quieres jugar aquí?</h2>"
        "<p class='sub'>Este local aún no acepta reservas en Pichangol. Desde la app puedes guardarlo, ver cómo llegar y avisarle al local que lo estás buscando.</p>"
        f"<div class='acciones'><a class='btn sec' href='{PLAY_URL}' rel='noopener'>📲 Abrir en la app</a><a class='btn sec' href='/canchas'>Ver canchas disponibles</a></div></div>")
    return ui.shell(nombre, cuerpo, desc=f"{nombre} · {direccion}", sesion=ses, titulo_tab=f"{nombre} · Pichangol")


@router.get("/reservar/{cancha_id}", response_class=HTMLResponse)
def pagina_reservar(request: Request, cancha_id: str, fecha: str = "", hora: str = "") -> HTMLResponse:
    c = datos.cancha(cancha_id)
    ses = sesion.de_request(request)
    if not c or c.get("eliminada") or not c.get("registrada", True):
        return _no_encontrada()
    # Como el app: una cancha EN VERIFICACIÓN (con dueño, aún no aprobada) solo
    # la ve su dueño (vista previa); el público no la encuentra hasta que la
    # torre la apruebe. El legado sin dueño sí se muestra, para poder reclamarlo.
    dueno = (c.get("dueno") or "").strip().lower()
    if not datos.reservable(c) and dueno and dueno != ((ses or {}).get("email") or "").lower():
        r = _no_encontrada("Esta cancha aún está en verificación"); r.status_code = 404
        return r
    sim, iso = _moneda_de(c)
    pais = _pais_de(c)
    hermanas = _hermanas(c, ses)
    ficha = _ficha(c, sim, pais, verificada=datos.reservable(c), hermanas=hermanas)
    titulo = _titulo_local(c)
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
        reclamar = ""
        if not datos.reservable(c) and not (c.get("dueno") or "").strip():
            reclamar = ("<div class='panel' style='margin-top:16px;border:1px solid var(--verde)'><h2>¿Es tuya esta cancha?</h2>"
                        "<p class='sub'>Nadie la administra todavía. Reclámala, confirmamos que eres el dueño y empiezas a recibir reservas y pagos en línea.</p>"
                        f"<div class='acciones'><a class='btn' href='/anfitrion/nueva?cancha={quote(c['id'], safe='')}'>🏷️ Reclamar esta cancha</a></div></div>")
        cuerpo = (f"<div style='padding-top:22px'>{ficha}</div>"
                  f"<div class='panel' style='margin-top:20px'><h2>Reserva desde la app</h2>"
                  f"<p class='sub'>{motivo} En la app Pichangol reservas y pagas con los medios de tu país.</p>"
                  f"<div class='acciones'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a>"
                  f"<a class='btn sec' href='/canchas'>Ver otras canchas</a></div></div>{reclamar}")
        return ui.shell(titulo, cuerpo, desc=f"{titulo} · {c['nombre']}", canonical=canonical,
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
        s = _se.completar(s)  # nombre/emoji/tipo desde el catálogo si la fila es de un APK viejo
        clave = str(s.get("clave") or "")
        try:
            precio = float(s.get("precio") or 0)
        except (TypeError, ValueError):
            precio = 0.0
        if precio <= 0 or not clave:
            continue
        nombre, tipo = s["nombre"], s["tipo"]
        sufijo = {"persona": " por persona", "turno": " por turno"}.get(tipo, "")
        # "Por persona" (piscina, entrada general): el jugador elige cuántas.
        cant = ("<select class='cant' data-for='" + e(clave) + "' disabled aria-label='Cantidad de personas'>"
                + "".join(f"<option value='{i}'>{i} persona{'s' if i > 1 else ''}</option>" for i in range(1, 13)) + "</select>") if tipo == "persona" else ""
        filas += (f"<label class='extra' style='display:flex;gap:10px;align-items:center;font-weight:600;margin:8px 0;flex-wrap:wrap'>"
                  f"<input type='checkbox' name='extra' value='{precio:.2f}' data-clave='{e(clave)}' data-nombre='{e(nombre)}' data-tipo='{e(tipo)}' style='width:auto'>"
                  f"{s['emoji']} {e(nombre)} <small style='color:var(--tenue)'>+ {e(sim)} {precio:.2f}{sufijo}</small>{cant}</label>")
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
            f"{sesion.boton_google(volver='/reservar/' + c['id'])}<div class='estado bad' id='sesionErr'></div></div>"
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
        "<div id='slots'></div>"
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
        f"<script>window.__cancha={cfg};var CORREO_SOPORTE={json.dumps(empresa.valores()['empresa_correo'])};</script>"
        "<script src='https://checkout.culqi.com/js/v4'></script>"
        f"<script>{sesion.JS_SESION if sesion.activo() else ''}{_JS_RESERVA}</script>")
    return ui.shell(f"Reservar en {titulo}", cuerpo, con_barra=True, canonical=canonical, og_image=og,
                    desc=f"Reserva {c['nombre']} y paga en línea con Yape o tarjeta.", jsonld=_jsonld_cancha(c, sim),
                    extra_head=("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
                                "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>"
                                + (sesion.GIS_SCRIPT if (sesion.activo() and not ses) else "")), sesion=ses)


# ── asegurar / pagar / liberar ────────────────────────────────────────────────

class HoraReq(BaseModel):
    fecha: str
    hora: str


class AsegurarReq(BaseModel):
    cancha_id: str
    horas: list[HoraReq]
    extras: list[Any] = []  # claves (APK/web viejos) o {clave, cantidad}
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
        cat = {str(s.get("clave")): s for s in c.get("servicios_extra") or []}
        for it in req.extras:
            if isinstance(it, dict):
                k, cant = str(it.get("clave") or ""), it.get("cantidad") or 1
            else:
                k, cant = str(it or ""), 1
            s = cat.get(k)
            try:
                cant = int(cant)
            except (TypeError, ValueError):
                cant = 1
            if s and float(s.get("precio") or 0) > 0 and k not in [x["clave"] for x in extras_ok]:
                # Línea con el TOTAL (por persona × cantidad, por turno × turnos).
                extras_ok.append(_se.linea_reserva(s, cant, len(pedidos)))
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
    try:
        # El cargo queda en el libro (tipo cobro_web) ligado a la reserva/grupo:
        # es lo que permite REEMBOLSAR desde la web al cancelar.
        from db.store import stores as _st
        _st.registrar_pago(tipo="cobro_web", monto_centimos=total * 100, moneda=iso, estado="aprobado",
                           culqi_charge_id=str(cargo.get("charge_id") or ""), email=email, medio=medio,
                           concepto=f"web:{_ref_de(filas)}")
    except Exception:  # noqa: BLE001
        pass
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


def _ref_de(filas: list[dict]) -> str:
    g = (filas[0].get("grupo_reserva_id") or "").strip()
    return g if g else str(filas[0]["id"])


def _inicio_reserva(filas: list[dict], pais: str) -> datetime | None:
    """Fecha-hora LOCAL (zona del país de la cancha) del primer turno."""
    try:
        f = min(filas, key=lambda x: (str(x.get("fecha")), str(x.get("hora_inicio"))))
        d = date.fromisoformat(str(f["fecha"]))
        m = horarios.hora_en_minutos(str(f["hora_inicio"])) or 0
        return datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=horarios.ahora_local(pais).tzinfo)
    except (ValueError, TypeError, KeyError):
        return None


def _cobro_web(ref: str):
    from db.store import stores as _st
    for p in reversed(_st.pagos):
        if p.tipo == "cobro_web" and p.concepto == f"web:{ref}":
            return p
    return None


def estado_cancelacion(filas: list[dict], c: dict | None, email: str) -> dict:
    """Qué pasa si el usuario cancela AHORA: si puede, cuántas horas faltan y
    si le corresponde reembolso (regla: ≥ WEB_CANCELACION_HORAS → 100 %)."""
    if not filas or not email:
        return {"puede": False, "motivo": "sin_reserva"}
    if any((f.get("usuario") or "").strip().lower() != email for f in filas):
        return {"puede": False, "motivo": "ajena"}
    if any(str(f.get("estado") or "") in ("cancelada", "noShow") for f in filas):
        return {"puede": False, "motivo": "ya_cancelada"}
    pais = _pais_de(c) if c else "PE"
    inicio = _inicio_reserva(filas, pais)
    if inicio is None:
        return {"puede": False, "motivo": "sin_fecha"}
    horas = (inicio - horarios.ahora_local(pais)).total_seconds() / 3600.0
    if horas <= 0:
        return {"puede": False, "motivo": "ya_empezo", "horas": horas}
    pagado_online = all(f.get("pagado") for f in filas) and str(filas[0].get("medio_pago") or "") in ("yape", "tarjeta")
    pagado = all(f.get("pagado") for f in filas)
    reembolsable = pagado and horas >= config.WEB_CANCELACION_HORAS
    return {"puede": True, "horas": round(horas, 1), "pagado": pagado, "pagado_online": pagado_online,
            "reembolsable": reembolsable, "minimo_horas": config.WEB_CANCELACION_HORAS,
            "monto": _total_de(filas), "moneda": filas[0].get("moneda") or "S/"}


class CancelarReq(BaseModel):
    ref: str


@router.post("/web/cancelar")
def cancelar(req: CancelarReq, request: Request = None) -> dict:
    """Cancela una reserva del usuario con sesión (grupo o turno suelto),
    libera el horario y, si corresponde (≥ WEB_CANCELACION_HORAS y pagada),
    DEVUELVE el dinero: cargo web → reembolso Culqi al instante; pagada en el
    app → queda `manual` para el operador. Revierte la liquidación del dueño
    (y su comisión, regalo incluido) si aún no se le pagó; si ya cobró, deja
    la deuda anotada para la torre. Todo queda en `stores.cancelaciones_web`."""
    from db.store import stores as _st, ahora as _ahora
    ses = sesion.de_request(request)
    if not ses:
        return {"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para cancelar."}
    email = ses["email"]
    ref = (req.ref or "").strip()
    filas = datos.reservas_por_grupo(ref) if ref.startswith("grp_") else datos.reservas_de([ref])
    filas = sorted([f for f in filas if f.get("estado") != "nueva" or f.get("pagado")],
                   key=lambda x: (str(x.get("fecha")), str(x.get("hora_inicio"))))
    c = datos.cancha(filas[0]["cancha_id"]) if filas else None
    est = estado_cancelacion(filas, c, email)
    if not est.get("puede"):
        msgs = {"sin_reserva": "No encontramos esa reserva.", "ajena": "Esa reserva no es de tu cuenta.",
                "ya_cancelada": "Esa reserva ya estaba cancelada.", "ya_empezo": "El turno ya empezó o ya pasó: no se puede cancelar.",
                "sin_fecha": "No pudimos leer la fecha de la reserva."}
        return {"ok": False, "error": est.get("motivo"), "mensaje": msgs.get(est.get("motivo"), "No se pudo cancelar.")}
    ids = [str(f["id"]) for f in filas]
    monto = int(est["monto"]); sim = est["moneda"]; iso = _moneda_de(c)[1] if c else "PEN"
    reembolso, refund_id, detalle = "no_aplica", None, ""
    if est["pagado"] and est["reembolsable"]:
        cobro = _cobro_web(ref)
        if cobro is not None and cobro.culqi_charge_id and cobro.estado == "aprobado":
            r = culqi.reembolsar(charge_id=cobro.culqi_charge_id, monto_centimos=cobro.monto_centimos)
            if r.get("ok"):
                reembolso, refund_id = "reembolsado", r.get("refund_id")
                cobro.estado = "reembolsado"
            else:
                reembolso, detalle = "fallo", str(r.get("error") or "")[:160]
        else:
            reembolso = "manual"  # pagó desde el app: el operador devuelve
    elif est["pagado"]:
        reembolso = "sin_reembolso"  # menos de N horas: sin devolución (política publicada)
    # Reversa contable del dueño solo si el cliente recupera su dinero.
    deuda = 0
    dueno = (c.get("dueno") or "").strip().lower() if c else ""
    if reembolso in ("reembolsado", "fallo", "manual") and dueno:
        liq = _st.pago_por_charge(ids[0])
        if liq is not None and liq.tipo in ("liquidacion_online", "liquidacion_full") and liq.estado == "aprobado":
            if liq.liquidado:
                from pagos.router import comision_centimos as _com
                deuda = liq.monto_centimos - (_com(liq.monto_centimos / 100.0, liq.moneda) if liq.tipo == "liquidacion_online" else 0)
                _st.registrar_pago(tipo="ajuste_cancelacion", monto_centimos=deuda, moneda=liq.moneda, estado="pendiente",
                                   dueno_id=dueno, culqi_charge_id=f"{ids[0]}_ajuste",
                                   concepto=f"Descuento por cancelación web · {c.get('nombre', '')} · {filas[0]['fecha']} {filas[0]['hora_inicio']}")
            else:
                liq.estado = "anulado"
                com = _st.pago_por_charge(f"{ids[0]}_com")
                if com is not None and com.estado == "aprobado":
                    com.estado = "anulado"
                    promo = min(int(com.promo_centimos or 0), com.monto_centimos)
                    if promo:
                        _st.acreditar_promo(dueno, promo)
                    if com.monto_centimos - promo > 0:
                        _st.acreditar(dueno, com.monto_centimos - promo)
    if not datos.eliminar_reservas(ids):
        return {"ok": False, "error": "no_se_pudo", "mensaje": "No pudimos liberar el horario. Inténtalo de nuevo."}
    reg = {"id": _st.next_id("cancelacion_web"), "ref": ref, "ids": ids, "usuario": email, "cancha_id": filas[0]["cancha_id"],
           "cancha": (c or {}).get("nombre") or "", "club": (c or {}).get("club") or "", "fecha": str(filas[0]["fecha"]),
           "hora_inicio": str(filas[0]["hora_inicio"]), "hora_fin": str(filas[-1]["hora_fin"]), "turnos": len(filas),
           "monto": monto, "moneda": sim, "moneda_iso": iso, "pagado": bool(est["pagado"]), "horas_antes": est["horas"],
           "reembolso": reembolso, "refund_id": refund_id, "detalle": detalle, "deuda_dueno_centimos": deuda,
           "dueno": dueno, "creado_en": _ahora().isoformat()}
    _st.cancelaciones_web.append(reg)
    try:
        from pagos.router import _aviso_push_usuario
        rango = f"{filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
        if dueno:
            _aviso_push_usuario(dueno, "Reserva cancelada 📅",
                                f"{filas[0].get('jugador') or email} canceló {c.get('nombre', '')} · {horarios.fecha_larga(str(filas[0]['fecha']))} {rango}. El horario quedó libre.",
                                tipo="reserva")
        txt = {"reembolsado": f"Te devolvemos {sim} {monto:.2f} al mismo medio de pago (3 a 7 días hábiles).",
               "manual": f"Te devolvemos {sim} {monto:.2f}; te escribimos para coordinar.",
               "fallo": "Tu devolución está en proceso; te escribimos en breve.",
               "sin_reembolso": "Cancelaste con menos de 6 horas: sin devolución.", "no_aplica": ""}[reembolso]
        _aviso_push_usuario(email, "Reserva cancelada", f"{c.get('nombre', '')} · {horarios.fecha_larga(str(filas[0]['fecha']))} {rango}. {txt}".strip(), tipo="reserva")
    except Exception:  # noqa: BLE001
        pass
    print(f"[cancelar] {ref} {email} {reembolso} monto={monto} horas={est['horas']} deuda={deuda} {detalle}", flush=True)
    return {"ok": True, "reembolso": reembolso, "monto": monto, "moneda": sim, "horas": est["horas"], "refund_id": refund_id}


_MODAL_CANCELAR = (
    "<div class='modal' id='modalCancelar' role='dialog' aria-modal='true'><div class='modal-caja' style='max-width:520px'>"
    "<div class='modal-cab'><button type='button' class='cerrar' id='cerrarCancelar' aria-label='Cerrar'>✕</button><h3>Cancelar reserva</h3></div>"
    "<div class='modal-cuerpo' style='padding:20px 24px'>"
    "<h4 id='cancTit' style='margin:0 0 6px'>¿Seguro que quieres cancelar?</h4>"
    "<p class='sub' id='cancTxt' style='margin:0 0 14px'></p>"
    "<div class='estado' id='cancPol' style='text-align:left'></div>"
    "<div class='estado bad' id='cancErr' style='display:none'></div></div>"
    "<div class='modal-pie'><button type='button' class='limpiar' id='cancNo'>Mantener reserva</button>"
    "<button type='button' class='btn dark' id='cancSi'>Sí, cancelar</button></div></div></div>")

JS_CANCELAR = r"""
(function(){
  var m = document.getElementById('modalCancelar'); if(!m) return;
  var ref = '', datos = null;
  function abrir(on){ m.classList.toggle('open', on); document.body.classList.toggle('sin-scroll', on); }
  function fmt(mon, n){ return mon + ' ' + Number(n).toFixed(2); }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest('[data-cancelar]'); if(!b) return;
    ev.preventDefault(); ev.stopPropagation();
    ref = b.dataset.cancelar; datos = b.dataset;
    document.getElementById('cancTit').textContent = '¿Cancelar ' + (datos.nombre || 'la reserva') + '?';
    document.getElementById('cancTxt').textContent = (datos.cuando || '') + (datos.monto ? ' · ' + fmt(datos.moneda || 'S/', datos.monto) : '');
    var pol = document.getElementById('cancPol');
    if(datos.pagado !== '1'){ pol.className = 'estado ok'; pol.textContent = 'Pagabas en la cancha: cancelar no tiene costo. El horario queda libre para otro jugador.'; }
    else if(datos.reembolsable === '1'){ pol.className = 'estado ok'; pol.textContent = 'Faltan ' + datos.horas + ' h: te devolvemos el 100 % (' + fmt(datos.moneda || 'S/', datos.monto) + ') al mismo medio de pago, en 3 a 7 días hábiles.'; }
    else { pol.className = 'estado bad'; pol.textContent = 'Faltan menos de ' + datos.minimo + ' h para el turno: la cancelación NO tiene devolución (política publicada). Puedes mantener la reserva y jugar.'; }
    document.getElementById('cancErr').style.display = 'none';
    var si = document.getElementById('cancSi'); si.disabled = false; si.textContent = datos.pagado === '1' && datos.reembolsable !== '1' ? 'Cancelar sin devolución' : 'Sí, cancelar';
    abrir(true);
  });
  document.getElementById('cerrarCancelar').addEventListener('click', function(){ abrir(false); });
  document.getElementById('cancNo').addEventListener('click', function(){ abrir(false); });
  m.addEventListener('click', function(ev){ if(ev.target === m) abrir(false); });
  document.getElementById('cancSi').addEventListener('click', function(){
    var si = this; si.disabled = true; si.textContent = 'Cancelando…';
    fetch('/web/cancelar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ref: ref})})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){ var e = document.getElementById('cancErr'); e.textContent = j.mensaje || 'No pudimos cancelar.'; e.style.display = 'block'; si.disabled = false; si.textContent = 'Reintentar'; return; }
        var msg = {reembolsado: 'Reserva cancelada. Te devolvemos ' + fmt(j.moneda, j.monto) + ' al mismo medio de pago en 3 a 7 días hábiles.',
                   manual: 'Reserva cancelada. Te devolvemos ' + fmt(j.moneda, j.monto) + '; te escribimos para coordinar.',
                   fallo: 'Reserva cancelada. Tu devolución está en proceso; te escribimos en breve.',
                   sin_reembolso: 'Reserva cancelada sin devolución.', no_aplica: 'Reserva cancelada. El horario quedó libre.'}[j.reembolso] || 'Reserva cancelada.';
        try { sessionStorage.setItem('pcg_aviso', msg); } catch(e){}
        location.href = '/mis-reservas';
      }).catch(function(){ var e = document.getElementById('cancErr'); e.textContent = 'Sin conexión. Inténtalo de nuevo.'; e.style.display = 'block'; si.disabled = false; si.textContent = 'Reintentar'; });
  });
})();
"""


def _boton_cancelar(filas: list[dict], c: dict | None, ses: dict | None, clase: str = "btn sec") -> str:
    """Botón "Cancelar reserva" (solo si la reserva es del usuario con sesión
    y aún no empieza); lleva los datos que el modal necesita explicar."""
    if not ses:
        return ""
    filas = sorted(filas, key=lambda x: (str(x.get("fecha")), str(x.get("hora_inicio"))))
    est = estado_cancelacion(filas, c, ses["email"])
    if not est.get("puede"):
        return ""
    cuando = f"{horarios.fecha_larga(str(filas[0]['fecha']))} · {filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
    return (f"<button type='button' class='{clase}' data-cancelar='{e(_ref_de(filas))}' data-nombre='{e((c or {}).get('nombre') or 'la reserva')}' "
            f"data-cuando='{e(cuando)}' data-monto='{est['monto']}' data-moneda='{e(est['moneda'])}' data-pagado='{1 if est['pagado'] else 0}' "
            f"data-reembolsable='{1 if est['reembolsable'] else 0}' data-horas='{est['horas']}' data-minimo='{int(est['minimo_horas'])}'>Cancelar reserva</button>")


def _url_comprobante(filas: list[dict]) -> str:
    g = (filas[0].get("grupo_reserva_id") or "").strip()
    return f"/reserva/{g if g else filas[0]['id']}"


# ── comprobante ───────────────────────────────────────────────────────────────

ESTADO_RESERVA = {"confirmada": ("Confirmada", "ok"), "cancelada": ("Cancelada", "bad"), "noShow": ("No asististe", "bad"),
                  "nueva": ("Pendiente de pago", "warn"), "completada": ("Jugada", "ok")}


def _tarjeta_viaje(r: dict, c: dict | None, hoy: str, ses: dict | None) -> str:
    """Tarjeta tipo "Viajes" de Airbnb: foto cuadrada · cancha · fecha y hora ·
    avatar del jugador · estado; clic = detalle/comprobante. Las próximas llevan
    "Cancelar"."""
    sim = r.get("moneda") or (c and _moneda_de(c)[0]) or "S/"
    estado = str(r.get("estado") or "")
    if estado == "noShow":
        pill = "<span class='pill bad'>No asististe</span>"
    elif r.get("pagado"):
        pill = "<span class='pill ok'>Pagada</span>"
    else:
        pill = "<span class='pill warn'>Pagas en la cancha</span>"
    ref = r.get("grupo_reserva_id") or r.get("id")
    pasada = str(r.get("fecha") or "") < hoy
    nombre = (c or {}).get("nombre") or "Cancha"
    con_comprobante = bool(r.get("pagado") or estado == "confirmada")
    href = f"/reserva/{e(ref)}" if con_comprobante else (f"/reservar/{e(c['id'])}" if c else "#")
    fs = _fotos(c) if c else []
    if fs:
        foto = f"<img src='{e(fs[0])}' alt='' loading='lazy'>"
    elif c:
        foto = (f"<div class='sinfoto' data-buscar='1' data-id='{e(c['id'])}' data-nombre='{e(c.get('nombre'))}' data-club='{e(c.get('club') or '')}' "
                f"data-lat='{c.get('lat')}' data-lng='{c.get('lng')}'>{_deporte(c.get('deporte'))[1]}</div>")
    else:
        foto = "<div class='sinfoto'>🏟️</div>"
    avatar = (f"<img class='av' src='{e(ses.get('foto'))}' alt=''>" if ses and ses.get("foto")
              else f"<span class='av ini'>{e(((ses or {}).get('nombre') or (ses or {}).get('email') or '?')[:1].upper())}</span>")
    cuando = f"{horarios.fecha_larga(str(r.get('fecha') or ''))} · {e(r.get('hora_inicio'))}–{e(r.get('hora_fin'))}"
    if int(r.get("turnos") or 1) > 1:
        cuando += f" · {r['turnos']} turnos"
    filas_r = r.get("_filas") or [r]
    cancelar = _boton_cancelar(filas_r, c, ses, "lnk") if not pasada else ""
    return (f"<a class='viaje{' pasada' if pasada else ''}' href='{href}' data-lat='{(c or {}).get('lat') or ''}' data-lng='{(c or {}).get('lng') or ''}' "
            f"data-nombre='{e(nombre)}' data-cuando='{e(cuando)}'>"
            f"<div class='vfoto'>{foto}</div>"
            f"<div class='vtxt'><b>{e(nombre)}</b><div class='sub' style='margin:2px 0 0;font-size:13.5px'>{e((c or {}).get('club') or '')}</div>"
            f"<div class='vcuando'>{cuando}</div>"
            f"<div class='vpie'>{avatar}{pill}<span class='vprecio'>{e(sim)} {int(r.get('precio') or 0):.2f}</span>"
            + (f"<span class='vacc'>{cancelar}</span>" if cancelar else "") + "</div></div></a>")


def _agrupar_reservas(filas: list[dict]) -> list[dict]:
    """Los turnos de UNA misma reserva (mismo `grupo_reserva_id`, mismo día)
    se muestran como una sola tarjeta: 19:00–21:00 · 2 turnos, precio sumado."""
    grupos: dict[str, dict] = {}
    out: list[dict] = []
    for r in filas:
        g = r.get("grupo_reserva_id")
        clave = f"{g}|{r.get('fecha')}" if g else ""
        if clave and clave in grupos:
            a = grupos[clave]
            a["hora_inicio"] = min(a["hora_inicio"], r["hora_inicio"]) if a["hora_inicio"] and r.get("hora_inicio") else a["hora_inicio"]
            a["hora_fin"] = max(a["hora_fin"], r["hora_fin"]) if a["hora_fin"] and r.get("hora_fin") else a["hora_fin"]
            a["precio"] = int(a.get("precio") or 0) + int(r.get("precio") or 0)
            a["turnos"] = a.get("turnos", 1) + 1
            a["extras"] = (a.get("extras") or []) + (r.get("extras") or [])
            a["_filas"].append(r)
            continue
        d = dict(r); d["turnos"] = 1; d["_filas"] = [r]
        out.append(d)
        if clave:
            grupos[clave] = d
    return out


@router.get("/mis-reservas", response_class=HTMLResponse)
def pagina_mis_reservas(request: Request) -> HTMLResponse:
    """"Mis reservas" en la web: las reservas del correo de Google con sesión
    (las mismas que el app), próximas y pasadas, con comprobante y cancha."""
    ses = sesion.de_request(request)
    if not ses:
        if sesion.activo():
            return HTMLResponse("", status_code=302, headers={"Location": "/entrar?volver=%2Fmis-reservas"})
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
                  "<h1 style='font-size:22px'>Mis reservas</h1>"
                  "<p class='sub'>En esta web aún no está activo el inicio de sesión. Tus reservas están en la app.</p>"
                  f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
        return ui.shell("Mis reservas", cuerpo, sesion=None)
    email = ses["email"]
    from db.store import stores as _st
    filas = _agrupar_reservas(datos.reservas_de_usuario(email))
    canchas = {}
    for r in filas:
        cid = r.get("cancha_id")
        if cid and cid not in canchas:
            canchas[cid] = datos.cancha(cid)
    hoy = horarios.ahora_local("PE").date().isoformat()
    proximas = sorted([r for r in filas if str(r.get("fecha") or "") >= hoy], key=lambda r: (r.get("fecha"), r.get("hora_inicio")))
    pasadas = [r for r in filas if str(r.get("fecha") or "") < hoy]
    canceladas = sorted([x for x in _st.cancelaciones_web if x.get("usuario") == email], key=lambda x: x.get("creado_en", ""), reverse=True)
    lista = "".join(_tarjeta_viaje(r, canchas.get(r.get("cancha_id")), hoy, ses) for r in proximas) if proximas else (
        "<div class='viaje-vacio'><b>Todavía no tienes reservas próximas</b>"
        "<p class='sub'>Cuando reserves una cancha, aparecerá aquí con su mapa y su comprobante.</p>"
        "<a class='btn' href='/canchas'>Explorar canchas</a></div>")
    pasadas_html = "".join(_tarjeta_viaje(r, canchas.get(r.get("cancha_id")), hoy, ses) for r in pasadas)
    def _fila_cancel(x: dict) -> str:
        est = {"reembolsado": ("Devolución en camino", "ok"), "manual": ("Devolución en proceso", "warn"), "fallo": ("Devolución en proceso", "warn"),
               "sin_reembolso": ("Sin devolución", "bad"), "no_aplica": ("Sin costo", "ok")}.get(x.get("reembolso"), ("", ""))
        return (f"<div class='cancelada'><div><b>{e(x.get('cancha') or 'Cancha')}</b><div class='sub' style='font-size:13px;margin:0'>"
                f"{e(horarios.fecha_larga(str(x.get('fecha') or '')))} · {e(x.get('hora_inicio'))}–{e(x.get('hora_fin'))}"
                + (f" · {x.get('turnos')} turnos" if int(x.get('turnos') or 1) > 1 else "") + "</div></div>"
                f"<div style='text-align:right'><span class='pill {est[1]}'>{est[0]}</span>"
                + (f"<div class='sub' style='font-size:12.5px;margin:4px 0 0'>{e(x.get('moneda') or 'S/')} {float(x.get('monto') or 0):.2f}</div>" if x.get("pagado") else "")
                + "</div></div>")
    cuerpo = (
        "<div class='viajes'><div class='viajes-lista'>"
        "<div class='aviso ok' id='avisoCancel' style='display:none'></div>"
        "<h1>Reservas</h1>"
        f"<p class='sub' style='margin-top:2px'>{e(ses.get('nombre') or email)} · {e(email)} · las mismas que ves en la app.</p>"
        f"<div class='viajes-cards' id='proximas'>{lista}</div>"
        + (f"<details class='viajes-det'><summary>Dónde has jugado <small>· {len(pasadas)}</small></summary><div class='viajes-cards'>{pasadas_html}</div></details>" if pasadas else "")
        + f"<details class='viajes-det'{' open' if canceladas else ''}><summary><span class='ico'>🗓️</span> Reservaciones canceladas <small>· {len(canceladas)}</small></summary>"
        + ("".join(_fila_cancel(x) for x in canceladas) if canceladas else "<p class='sub' style='padding:8px 4px 2px'>No has cancelado ninguna reserva.</p>")
        + "</details>"
        f"<p class='sub' style='font-size:12.5px;margin-top:18px'>Cancelación con más de {int(config.WEB_CANCELACION_HORAS)} horas de anticipación: devolución del 100 % al mismo medio de pago. "
        f"Dudas: <a href='mailto:{empresa.datos()['correo']}'>{empresa.datos()['correo']}</a>.</p>"
        "</div><aside class='viajes-mapa'><div class='mapa' id='mapaViajes' aria-label='Mapa de tus reservas'></div></aside></div>"
        + _MODAL_CANCELAR
        + "<script>" + JS_CANCELAR + r"""
(function(){
  try { var av = sessionStorage.getItem('pcg_aviso'); if(av){ var el = document.getElementById('avisoCancel'); el.textContent = av; el.style.display = 'block'; sessionStorage.removeItem('pcg_aviso'); } } catch(e){}
  // Fotos que faltan (canchas sembradas): la primera foto, como en el explorador.
  document.querySelectorAll('.viaje .sinfoto[data-buscar]').forEach(function(ph){
    var q = '/web/foto?id=' + encodeURIComponent(ph.dataset.id) + '&nombre=' + encodeURIComponent(ph.dataset.nombre) + '&club=' + encodeURIComponent(ph.dataset.club) + '&lat=' + ph.dataset.lat + '&lng=' + ph.dataset.lng;
    fetch(q).then(function(r){ return r.json(); }).then(function(j){ if(j && j.fotos && j.fotos.length){ var im = document.createElement('img'); im.src = j.fotos[0]; im.alt = ''; ph.replaceWith(im); } }).catch(function(){});
  });
  // Mapa con un pin por reserva próxima (Leaflet + OpenStreetMap, como el explorador).
  var caja = document.getElementById('mapaViajes'); if(!caja || !window.L) return;
  var pts = Array.prototype.slice.call(document.querySelectorAll('#proximas .viaje[data-lat]')).filter(function(a){ return a.dataset.lat && a.dataset.lng; });
  var mapa = L.map('mapaViajes', {scrollWheelZoom: false});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(mapa);
  if(!pts.length){ mapa.setView([-12.05, -77.04], 11); return; }
  var b = [];
  pts.forEach(function(a){
    var lat = parseFloat(a.dataset.lat), lng = parseFloat(a.dataset.lng); b.push([lat, lng]);
    var mk = L.marker([lat, lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio">' + a.dataset.nombre.replace(/</g, '&lt;') + '</span>', iconSize: null})}).addTo(mapa);
    mk.bindPopup('<b>' + a.dataset.nombre.replace(/</g, '&lt;') + '</b><br>' + a.dataset.cuando.replace(/</g, '&lt;') + '<br><a class="btn" href="' + a.getAttribute('href') + '">Ver reserva</a>');
    a.addEventListener('mouseenter', function(){ mk.openPopup(); });
  });
  if(b.length === 1) mapa.setView(b[0], 15); else mapa.fitBounds(L.latLngBounds(b).pad(0.3));
})();
</script>""")
    head = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
            "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>")
    return ui.shell("Mis reservas", cuerpo, sesion=ses, titulo_tab="Mis reservas · Pichangol", extra_head=head, ancho=True)


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
def pagina_comprobante(ref: str, request: Request = None) -> HTMLResponse:
    filas = _filas_comprobante(ref)
    if not filas:
        return _no_encontrada("Reserva no encontrada")
    ses = sesion.de_request(request)
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim = filas[0].get("moneda") or "S/"
    total = _total_de(filas)
    extras = [x for f in filas for x in (f.get("extras") or [])]
    lineas = "".join(
        f"<div class='linea'><span>{e(horarios.fecha_larga(f['fecha']))} · {e(f['hora_inicio'])}–{e(f['hora_fin'])}</span>"
        f"<b>{e(sim)} {int(f['precio']):.2f}</b></div>" for f in filas)
    lineas += "".join(
        f"<div class='linea'><span>{e(x.get('nombre') or EXTRAS_NOMBRE.get(str(x.get('clave')), str(x.get('clave')).capitalize()))}"
        f"{(' × ' + str(int(x.get('cantidad')))) if int(x.get('cantidad') or 1) > 1 else ''}</span>"
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
        + (f"<div class='acciones'>{_boton_cancelar(filas, c, ses, 'btn sec')}</div>" if _boton_cancelar(filas, c, ses) else "")
        + f"<div class='estado ok' style='text-align:left'>Cancelación con más de {int(config.WEB_CANCELACION_HORAS)} horas de anticipación: devolución del 100 % al mismo medio de pago. "
        f"Puedes cancelar desde aquí o desde <a href='/mis-reservas'>Mis reservas</a>. Dudas: <a href='mailto:{empresa.datos()['correo']}'>{empresa.datos()['correo']}</a>.</div>"
        "</div>"
        "<div class='panel' style='margin-top:16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap'>"
        "<img src='/static/brand/logo_pin.png' alt='' style='width:56px;height:56px;border-radius:14px;border:1px solid var(--trazo)'>"
        "<div style='flex:1;min-width:200px'><b>Lleva tus reservas contigo</b>"
        "<div class='sub' style='font-size:13px'>Con la app ves tu agenda, acumulas puntos y reservas en dos toques.</div></div>"
        f"<a class='btn' href='{PLAY_URL}'>Descargar la app</a></div>"
        "<div style='text-align:center;margin-top:16px'><a href='/canchas'>Reservar otra cancha</a></div>"
        f"</div>{_MODAL_CANCELAR}<script>{JS_CANCELAR}</script>")
    return ui.shell("Reserva confirmada", cuerpo, sesion=ses)
