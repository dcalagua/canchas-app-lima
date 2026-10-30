"""EXPLORADOR (portada tipo Airbnb): `GET /`, `GET /canchas`, las páginas SEO
por deporte y zona `GET /canchas/{deporte}/{zona}` y `GET /web/descubrir`
(canchas de Google cerca, como el APK). Aquí viven el JS del explorador, la
cabecera con buscador, la barra y el modal de filtros, la tarjeta de un LOCAL
y la de una academia.

Movido tal cual desde `web/router.py`, que lo re-exporta.
"""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import config
from paises import _CAJAS, pais_de_coordenadas, moneda_de_pais, simbolo_de_moneda
from web import catalogos, datos, descubrir, horarios, marca, miniaturas, sesion, ui
from web.ui import e
import academia_plan as _ap
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)
from web.comun import (AMENIDAD_NOMBRE, CIUDAD_DEFECTO, DEPORTES, DIAS_ADELANTE, NOMBRE_PAIS, PLAY_URL, _deporte,
                       _deportes_de, _fotos, _moneda_de, _no_encontrada, _pais_de, _sin_google, _zona)
from web.disponibilidad import _es_iso
from web.ficha import _titulo_local

router = APIRouter()


# ── catálogo ──────────────────────────────────────────────────────────────────

# Leaflet del mapa del explorador (se carga bajo demanda; SRI = el archivo de
# unpkg no puede cambiar, mismas huellas que la ficha).
LEAFLET = {"css": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
           "cssSri": "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=",
           "js": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
           "jsSri": "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="}

_JS_EXPLORAR = (r"""
(function(){
  var C = window.__explorar, $ = function(id){ return document.getElementById(id); };
  var cards = function(){ return Array.prototype.slice.call(document.querySelectorAll('.lst[data-lat]')); };
  var yo = null, mapa = null, marcadores = [], miPin = null, pinesDesc = [], descubiertas = {}, fotosConocidas = {}, minisConocidas = {};
  // Foto de tarjeta = MINIATURA (`web/miniaturas.py`): el servidor manda
  // {s: src, ss: srcset} alineado con cada foto; sin eso, la URL de siempre.
  function fotoImg(u, m){
    m = m || {};
    return '<img src="' + esc(m.s || u) + '"' + (m.ss ? ' srcset="' + esc(m.ss) + '" sizes="' + C.sizesTarjeta + '"' : '') + ' alt="" loading="lazy" decoding="async">';
  }
  var filtro = {q: '', dep: C.dep || '', fecha: '', hora: '', cerca: false};
  // Radio de cercanía (como el APK: 5/10/20/30 km, 10 por defecto). Con tu
  // ubicación SOLO salen canchas/academias dentro del radio (nunca las de otro
  // país); al buscar por zona/nombre el radio no aplica.
  var RADIOS = [5, 10, 20, 30], radio = 10;
  try { var rg = parseInt(localStorage.getItem('pcg_radio') || '', 10); if(RADIOS.indexOf(rg) >= 0) radio = rg; } catch(e){}
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
    var id = b.closest('.lst').dataset.id, on = !favs[id]; if(on) favs[id] = 1; else delete favs[id];
    try { localStorage.setItem('pcg_fav', JSON.stringify(favs)); } catch(e){}
    pintarFavs();
    // Con sesión, el ♥ queda en la CUENTA (se ve en cualquier equipo y en /mis-favoritos).
    if(conCuenta) fetch('/web/favoritos', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: id, on: on})}).catch(function(){});
    if(on && window.pcgToast) pcgToast(conCuenta ? 'Guardado en tus favoritos ♥' : 'Guardado en este navegador. Inicia sesión para tenerlo en tu cuenta.');
  });
  // Al cargar: trae los de la cuenta y le suma los que este navegador guardó antes de iniciar sesión.
  var conCuenta = false;
  fetch('/web/favoritos').then(function(r){ return r.ok ? r.json() : null; }).then(function(j){
    if(!j || !j.ok) return;
    conCuenta = true;
    var locales = Object.keys(favs), nube = {};
    (j.ids || []).forEach(function(i){ nube[i] = 1; });
    var faltan = locales.filter(function(i){ return !nube[i]; });
    if(faltan.length) fetch('/web/favoritos/unir', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ids: faltan})}).catch(function(){});
    Object.keys(nube).forEach(function(i){ favs[i] = 1; });
    try { localStorage.setItem('pcg_fav', JSON.stringify(favs)); } catch(e){}
    pintarFavs();
  }).catch(function(){});
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
    if(yo && !filtro.q && c.dataset.d && parseFloat(c.dataset.d) > radio) return false;
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
    // Los pines del mapa siguen a la lista: lo que no se muestra (fuera del
    // radio o filtrado) tampoco se pinta.
    if(mapa) marcadores.concat(pinesDesc).forEach(function(m){ if(!m._card) return; var on = m._card.style.display !== 'none';
      if(on && !mapa.hasLayer(m)) m.addTo(mapa); else if(!on && mapa.hasLayer(m)) m.remove(); });
    document.querySelectorAll('.grupo-pais, .grupo-aca').forEach(function(g){
      var vis = Array.prototype.some.call(g.querySelectorAll('.lst'), function(c){ return c.style.display !== 'none'; });
      g.style.display = vis ? '' : 'none';
    });
    var sd = $('descubiertas'); if(sd){ var ls = sd.querySelectorAll('.lst');
      if(ls.length) sd.style.display = Array.prototype.some.call(ls, function(c){ return c.style.display !== 'none'; }) ? '' : 'none';
      // Solo las DESC_MAX más cercanas; el resto con "Ver más" (con búsqueda por nombre, todas).
      var visD = Array.prototype.filter.call(ls, function(c){ return c.style.display !== 'none'; });
      var abiertoD = descAbierto || !!filtro.q;
      visD.forEach(function(c, i){ c.classList.toggle('desc-extra', !abiertoD && i >= DESC_MAX); });
      var bm = $('descMas'), restoD = visD.length - DESC_MAX;
      if(bm){ bm.style.display = (!abiertoD && restoD > 0) ? '' : 'none';
        if(restoD > 0) $('btnDescMas').textContent = 'Ver ' + restoD + ' cancha' + (restoD === 1 ? '' : 's') + ' más'; } }
    var v = $('vacio'); if(v){ v.style.display = n ? 'none' : '';
      if(!n && v.dataset.base !== undefined){
        var why = (yo && !filtro.q && !filtro.hora) ? (C.dep === 'academias' ? 'No hay academias a ' + radio + ' km de ti.' : 'No hay canchas a ' + radio + ' km de ti.') + (radio < 30 ? ' Amplía la distancia o busca otra zona.' : ' Busca otra zona por nombre.')
                : filtro.hora ? 'Ninguna cancha' + (filtro.cerca ? ' cerca de ti' : '') + ' tiene turno libre ' + (filtro.fecha ? etiquetaFecha(filtro.fecha).toLowerCase() : '') + ' a las ' + filtro.hora + '. Prueba con otra hora u otro día.'
                              : C.dep === 'academias' ? (filtro.q ? 'No encontramos academias con “' + filtro.q + '”. Prueba con otro nombre o zona.' : 'No hay academias con esa búsqueda. Prueba con otra zona.')
                              : (filtro.q && C.lugares ? (busqGoogle[filtro.q] === 'pendiente' ? 'Buscando “' + filtro.q + '” también en Google Maps…' : 'No encontramos “' + filtro.q + '” en ⟦MARCA⟧ ni en Google Maps. Prueba con otro nombre o zona.')
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
    // Academias ocultas en los países que la torre no habilitó (BO/EC hoy).
    if(C.acadPaises && C.acadPaises.indexOf(pais) < 0){
      document.querySelectorAll('.cat[data-dep="academias"]').forEach(function(x){ x.style.display = 'none'; });
      var ga = $('academias'); if(ga) ga.remove();
    }
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
    pintarRadio();
    aplicar();
    var bu = $('btnUbic'); if(bu) bu.style.display = 'none';
    descubrir(yo.lat, yo.lng);
    if(mapa){ if(miPin) miPin.remove(); miPin = L.marker([yo.lat, yo.lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio yo">Tú</span>', iconSize: null})}).addTo(mapa);
      ajustarMapa(); }
  }
  function pintarRadio(){
    var u = $('ubicTxt'); if(!u || !yo) return;
    u.innerHTML = (C.dep === 'academias' ? 'Academias' : 'Canchas') + ' a <select id="selRadio" aria-label="Distancia máxima">' +
      RADIOS.map(function(r){ return '<option value="' + r + '"' + (r === radio ? ' selected' : '') + '>' + r + ' km</option>'; }).join('') + '</select> de ti, las más cercanas primero.';
    $('selRadio').addEventListener('change', function(){ radio = parseInt(this.value, 10) || 10; try { localStorage.setItem('pcg_radio', String(radio)); } catch(e){} aplicar(); ajustarMapa(); });
  }
  function ajustarMapa(){
    if(!mapa || !yo) return;
    var pts = cards().filter(function(c){ return parseFloat(c.dataset.d) <= radio; }).map(function(c){ return [parseFloat(c.dataset.lat), parseFloat(c.dataset.lng)]; });
    pts.push([yo.lat, yo.lng]); mapa.fitBounds(L.latLngBounds(pts).pad(0.2), {maxZoom: 14});
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
    var propias = c.fotos && c.fotos.length;
    var fs = propias ? c.fotos : (fotosConocidas[c.id] || []);
    var ms = propias ? (c.minis || []) : (minisConocidas[c.id] || []);
    if(fs.length){ fotosConocidas[c.id] = fs; minisConocidas[c.id] = ms; }
    // OpenStreetMap: nunca se pide foto a Google (placeholder del deporte) y
    // va la atribución de la licencia ODbL.
    var esOsm = c.fuente === 'osm';
    var foto = fs.length ? fs.slice(0, 3).map(function(u, i){ return fotoImg(u, ms[i]); }).join('') : '<div class="sinfoto"' + (esOsm ? '' : ' data-buscar="1"') + '>' + (c.emoji || '🏟️') + '</div>';
    var extra = fs.length > 1 ? '<button class="flecha izq" aria-label="Anterior">‹</button><button class="flecha der" aria-label="Siguiente">›</button><div class="dots">' + fs.slice(0, 3).map(function(){ return '<i></i>'; }).join('') + '</div>' : '';
    var hrefLugar = '/lugar/' + encodeURIComponent(c.id) + '?nombre=' + encodeURIComponent(c.nombre) + '&direccion=' + encodeURIComponent(c.direccion) + '&lat=' + c.lat + '&lng=' + c.lng + '&deporte=' + encodeURIComponent(c.deporte);
    return '<a class="lst pend" href="' + hrefLugar + '" data-id="' + esc(c.id) + '" data-lat="' + c.lat + '" data-lng="' + c.lng + '" data-ok="0" data-deps="' + esc(c.deporte) + '" data-nombre="' + esc(c.nombre) + '" data-sub="' + esc(c.direccion) + '" data-precio="' + esc(c.deporte_nombre) + '" data-emoji="' + esc(c.emoji || '') + '" data-t="' + esc((c.nombre + ' ' + c.direccion).toLowerCase()) + '" data-q="' + esc(c.q || '') + '"' + (yo && c.km != null ? ' data-d="' + c.km + '"' : '') + '>' +
      '<div class="foto"><div class="fotos">' + foto + '</div><span class="badge pend">Aún sin registrar</span>' + extra + '</div>' +
      '<div class="lb"><div class="l1"><b>' + esc(c.nombre) + '</b><span class="rate">' + esc(c.deporte_nombre) + '</span></div>' +
      '<div class="l2">' + esc(c.direccion) + '</div><div class="l2"><span class="dist">' + (c.km != null ? 'a ' + fmtKm(c.km) : '') + '</span>' +
      (esOsm ? ' <span class="wa osm-atrib" data-wa="https://www.openstreetmap.org/copyright" style="font-size:12px;color:#717171">© OpenStreetMap</span>' : '') + '</div>' +
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
  var DESC_MAX = 8, descAbierto = false;
  document.addEventListener('click', function(ev){ if(!ev.target.closest('#btnDescMas')) return; descAbierto = true; aplicar(); });
  function kmEntre(a, b, c, d){ var R = 6371, x = (c - a) * Math.PI / 180, y = (d - b) * Math.PI / 180; var h = Math.sin(x/2)*Math.sin(x/2) + Math.cos(a*Math.PI/180)*Math.cos(c*Math.PI/180)*Math.sin(y/2)*Math.sin(y/2); return 2 * R * Math.asin(Math.sqrt(h)); }
  // Pin de una cancha descubierta: ícono del deporte + NOMBRE del local
  // (recortado por CSS; con el mapa alejado queda solo el ícono, así no se
  // enciman). El nombre completo va en el title y en el popup.
  function pinDesc(nombre, emoji, deporte){
    var n = (nombre || '').trim() || deporte || 'Cancha';
    return '<span class="pin-precio pend pin-desc" title="' + esc(n) + '"><i>' + esc(emoji || '🏟️') + '</i><span class="nom">' + esc(n) + '</span></span>';
  }
  function zoomPines(){ var el = $('mapa'); if(el && mapa) el.classList.toggle('mapa-lejos', mapa.getZoom() < 13); }
  function pintarDescubiertas(lista, conFotos){
    var sec = $('descubiertas'), grid = $('gridDesc');
    if(!sec || !grid) return;
    (lista || []).forEach(function(c){ var prev = descAcum[c.id]; if(prev && !(c.fotos && c.fotos.length) && prev.fotos && prev.fotos.length){ c.fotos = prev.fotos; c.minis = prev.minis; } descAcum[c.id] = c; });
    var ref = yo ? yo : (mapa ? {lat: mapa.getCenter().lat, lng: mapa.getCenter().lng} : null);
    lista = Object.keys(descAcum).map(function(k){ var c = descAcum[k]; if(ref) c.km = Math.round(kmEntre(ref.lat, ref.lng, c.lat, c.lng) * 100) / 100; return c; })
      .sort(function(a, b){ return (a.km == null ? 1e9 : a.km) - (b.km == null ? 1e9 : b.km); });
    if(!lista.length){ if(!conFotos) sec.style.display = 'none'; return; }
    sec.style.display = '';
    grid.innerHTML = lista.map(tarjetaDesc).join('');
    resolverFotos();
    if(mapa && window.L){
      pinesDesc.forEach(function(m){ m.remove(); }); pinesDesc = [];
      var hijosDesc = grid.children;
      lista.forEach(function(c, i){
        var m = L.marker([c.lat, c.lng], {icon: L.divIcon({className: '', html: pinDesc(c.nombre, c.emoji, c.deporte_nombre), iconSize: null})}).addTo(mapa);
        m.bindPopup('<b>' + esc(c.nombre) + '</b><br>' + esc(c.direccion) + '<br><a class="btn sec" href="/lugar/' + encodeURIComponent(c.id) + '?nombre=' + encodeURIComponent(c.nombre) + '&direccion=' + encodeURIComponent(c.direccion) + '&lat=' + c.lat + '&lng=' + c.lng + '&deporte=' + encodeURIComponent(c.deporte) + '">Ver lugar</a>');
        m._card = hijosDesc[i]; pinesDesc.push(m);
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
    // UNA sola llamada (antes había una 2.ª con fotos=1: el doble de Google).
    // Las fotos de cada tarjeta visible las trae /web/foto (guardadas 30 días).
    fetch('/web/descubrir?lat=' + lat + '&lng=' + lng + qd).then(function(r){ return r.json(); })
      .then(function(j){ pintarDescubiertas(j.canchas || [], false); })
      .catch(function(){ if(sec && !Object.keys(descAcum).length) sec.style.display = 'none'; });
  }
  // ── mapa (se dibuja al mostrarlo; split view en escritorio, pantalla completa en móvil) ──
  // Leaflet (≈150 KB de unpkg) se pide RECIÉN al abrir el mapa: antes iba en
  // <head> y frenaba la portada aunque casi nadie abre el mapa.
  var leafletP = null;
  function cargarLeaflet(){
    if(window.L) return Promise.resolve();
    if(leafletP) return leafletP;
    leafletP = new Promise(function(res, rej){
      var n = 0, fin = function(){ if(++n === 2) res(); };
      var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = C.leaflet.css; l.integrity = C.leaflet.cssSri;
      l.crossOrigin = ''; l.onload = fin; l.onerror = fin; document.head.appendChild(l);
      var s = document.createElement('script'); s.src = C.leaflet.js; s.integrity = C.leaflet.jsSri; s.crossOrigin = '';
      s.onload = fin; s.onerror = function(){ leafletP = null; rej(); }; document.head.appendChild(s);
    });
    return leafletP;
  }
  function pintarMapa(){
    if(mapa || !$('mapa')) return;
    if(!window.L){
      cargarLeaflet().then(function(){ pintarMapa(); setTimeout(function(){ if(mapa) mapa.invalidateSize(); }, 60); })
        .catch(function(){ if(window.pcgToast) pcgToast('No se pudo cargar el mapa. Revisa tu conexión.'); });
      return;
    }
    mapa = L.map('mapa', {scrollWheelZoom: true}).setView(C.centro, 12);
    // Mover el mapa NO busca solo (cada búsqueda nueva en Google cuesta): sale
    // el botón "Buscar en esta zona", como en Airbnb (oct-2026, factura Places).
    var btnZona = document.createElement('button');
    btnZona.type = 'button'; btnZona.className = 'btn-zona'; btnZona.textContent = '🔎 Buscar canchas en esta zona';
    btnZona.style.display = 'none';
    $('mapa').appendChild(btnZona);
    L.DomEvent.disableClickPropagation(btnZona);
    btnZona.addEventListener('click', function(){ var c = mapa.getCenter(); btnZona.style.display = 'none'; descubrir(c.lat, c.lng); });
    mapa.on('zoomend', zoomPines); zoomPines();
    mapa.on('moveend', function(){ if(mapa.getZoom() < 12) { btnZona.style.display = 'none'; return; } var c = mapa.getCenter(); btnZona.style.display = descubiertas[c.lat.toFixed(2) + ',' + c.lng.toFixed(2)] ? 'none' : ''; });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; OpenStreetMap'}).addTo(mapa);
    var pts = [];
    cards().forEach(function(c){
      var lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng); if(!lat && !lng) return;
      if(c.classList.contains('pend') && (c.dataset.id.indexOf('gp_') === 0 || c.dataset.id.indexOf('osm_') === 0)) return;
      pts.push([lat, lng]);
      var ok = c.dataset.ok === '1', esAca = c.classList.contains('aca');
      var m = L.marker([lat, lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio' + (ok ? '' : ' pend') + (esAca ? ' aca' : '') + '">' + c.dataset.precio + '</span>', iconSize: null})});
      m._card = c;
      m.bindPopup('<b>' + esc(c.dataset.nombre) + '</b><br>' + esc(c.dataset.sub) + '<br>' + (esAca ? '' : '<span style="font-weight:800">' + esc(c.dataset.precio) + ' por hora</span><br>') + '<a class="btn' + (ok ? '' : ' sec') + '" href="' + c.getAttribute('href') + '">' + (esAca ? 'Ver academia' : (ok ? 'Ver horarios' : 'Reservar en la app')) + '</a>');
      m.on('mouseover', function(){ c.style.outline = '2px solid #0B7A57'; c.style.outlineOffset = '4px'; c.style.borderRadius = '14px'; });
      m.on('mouseout', function(){ c.style.outline = ''; });
      marcadores.push(m); m.addTo(mapa);
    });
    if(yo){ miPin = L.marker([yo.lat, yo.lng], {icon: L.divIcon({className: '', html: '<span class="pin-precio yo">Tú</span>', iconSize: null})}).addTo(mapa); pts.push([yo.lat, yo.lng]); }
    if(yo) ajustarMapa(); else if(pts.length) mapa.fitBounds(L.latLngBounds(pts).pad(0.25), {maxZoom: 13});
    // Las descubiertas ya pintadas también van al mapa.
    var desc = Array.prototype.slice.call(document.querySelectorAll('#gridDesc .lst'));
    desc.forEach(function(c){ var m; m = L.marker([parseFloat(c.dataset.lat), parseFloat(c.dataset.lng)], {icon: L.divIcon({className: '', html: pinDesc(c.dataset.nombre, c.dataset.emoji, c.dataset.precio), iconSize: null})}).addTo(mapa);
      m.bindPopup('<b>' + esc(c.dataset.nombre) + '</b><br>' + esc(c.dataset.sub) + '<br><a class="btn sec" href="' + c.getAttribute('href') + '">Ver lugar</a>'); m._card = c; pinesDesc.push(m); });
    aplicar();
  }
  // ── PRIMERA FOTO siempre (como el app): las tarjetas sin foto propia piden
  // la de Google en su ubicación (/web/foto, cacheado en el servidor). ──
  var colaFotos = [], enVuelo = 0, pedidas = {};
  function pintarFotos(card, fotos, minis){
    var box = card.querySelector('.fotos'); if(!box || !fotos || !fotos.length) return;
    minis = minis || [];
    fotosConocidas[card.dataset.id] = fotos; minisConocidas[card.dataset.id] = minis;
    box.innerHTML = fotos.slice(0, 3).map(function(u, i){ return fotoImg(u, minis[i]); }).join('');
    if(fotos.length > 1){
      var f = card.querySelector('.foto');
      f.insertAdjacentHTML('beforeend', '<button class="flecha izq" aria-label="Anterior">‹</button><button class="flecha der" aria-label="Siguiente">›</button><div class="dots">' + fotos.slice(0, 3).map(function(){ return '<i></i>'; }).join('') + '</div>');
    }
  }
  function pedirFoto(card){
    var q = 'id=' + encodeURIComponent(card.dataset.id || '') + '&nombre=' + encodeURIComponent(card.dataset.nombre || '') +
            '&club=' + encodeURIComponent(card.dataset.club || '') + '&lat=' + card.dataset.lat + '&lng=' + card.dataset.lng;
    fetch('/web/foto?' + q).then(function(r){ return r.json(); }).then(function(j){ pintarFotos(card, (j && j.fotos) || [], (j && j.minis) || []); })
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
""").replace('⟦MARCA⟧', MARCA)

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
    hoy = date.today().isoformat()
    # Pestañas: solo los deportes prendidos en la torre (y la que llegó por URL).
    activos = set(catalogos.deportes_activos())
    cats = [c for c in CATEGORIAS if (c[0] in ("", "academias") or c[0] in activos or c[0] == dep)
            and (c[0] != "academias" or _ap.paises_habilitados())]
    ops = "".join(f"<option value='{k}'{' selected' if k == dep else ''}>{n}</option>" for k, n, _ in cats)
    tabs = "".join(f"<a class='cat{' sel' if k == dep else ''}' href='/canchas{('?deporte=' + k) if k else ''}' data-dep='{k}'>"
                   f"<span class='ico'>{ico}</span>{n}</a>" for k, n, ico in cats)
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
        "<div class='rango'><input type='range' id='rMin' aria-label='Precio mínimo' min='0' max='100' value='0'><input type='range' id='rMax' aria-label='Precio máximo' min='0' max='100' value='100'></div>"
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


def _tarjeta(canchas: list[dict] | dict, ratings: dict | tuple | None = None, fecha: str = "",
             prioridad: bool = False) -> str:
    """Tarjeta del explorador = UN LOCAL con sus canchas (queja del director,
    sep-2026: "sigue saliendo el nombre de la cancha como nombre del local").
    Igual que `ClubCard` del app: título = local, debajo zona, "N canchas ·
    deportes · horario", precio "desde" el más barato y ★ promedio de todas
    sus canchas. Enlaza a la ficha de la primera cancha (la ficha ya tiene
    chips para cambiar de cancha dentro del local). Los `data-*` que usa el
    JS (hora libre, precio, duración, superficie, amenidades, mapa, fotos)
    reúnen los valores de TODAS las canchas del local (`data-ids`,
    `data-pasos`, `data-sup` con varias superficies). Fotos = miniaturas
    (`web/miniaturas.py`); `prioridad` = tarjeta visible al abrir (su primera
    foto no espera al scroll)."""
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
    sub = _zona(c) or ui.direccion_legible(c.get("direccion") or "")
    ok = all(datos.reservable(x) for x in cs)
    fs: list[str] = []
    for x in cs:
        for u in _fotos(x):
            if u not in fs:
                fs.append(u)
    if fs:
        fotos = "".join(miniaturas.img(u, prioridad=prioridad and i == 0) for i, u in enumerate(fs[:5]))
    elif _sin_google(c):  # plazo de fotos propias vencido: sin Google
        fotos = f"<div class='sinfoto'>{_deporte(c.get('deporte'))[1]}</div>"
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
    # Todas las canchas del local cobran POR TURNO → se muestra el turno más
    # barato ("S/ 15 por turno de 1 h 30"); si no, el precio por hora. El filtro
    # de precios (`data-pnum`) siempre compara por hora.
    todos_turno = all(float(x.get("precio_turno") or 0) > 0 for x in cs)
    if todos_turno:
        barato = min(cs, key=lambda x: float(x.get("precio_turno") or 0))
        pvis, unidad = horarios.precio_publico(barato)
        vistos = {float(x.get("precio_turno") or 0) for x in cs}
    else:
        pvis, unidad, vistos = pmin, "por hora", set(precios)
    desde = "desde " if len(cs) > 1 and len(vistos) > 1 else ""
    n = len(cs)
    n_txt = f"{n} cancha{'s' if n != 1 else ''}"
    base = f"/reservar/{c['id']}"
    href = base + (f"?fecha={fecha}" if fecha else "")
    ptxt = f"{pvis:.0f}" if abs(pvis - round(pvis)) < 0.005 else f"{pvis:.2f}"
    precio_html = f"<b>{e(sim)} {ptxt}</b> <span style='color:var(--tenue)'>{e(unidad)}</span>"
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
            f"data-sub='{e(sub)}' data-precio='{e(desde)}{e(sim)} {ptxt}' data-pnum='{pmin:.2f}' data-ok='{1 if ok else 0}'>"
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
    foto = "".join(miniaturas.img(u) for u in fs[:3]) if fs else f"<div class='sinfoto'>{emoji}</div>"
    extra = ""
    if len(fs) > 1:
        extra = ("<button class='flecha izq' aria-label='Anterior'>‹</button><button class='flecha der' aria-label='Siguiente'>›</button>"
                 f"<div class='dots'>{''.join('<i></i>' for _ in fs[:3])}</div>")
    tel = re.sub(r"\D", "", str(a.get("whatsapp") or ""))
    pref = catalogos.TEL_PREFIJO.get(iso or "PE", "51")
    if tel and not tel.startswith(pref) and len(tel) <= 10:
        tel = pref + tel
    # OJO: la tarjeta ya es un <a>; un <a> anidado rompe el HTML (el navegador parte la tarjeta). Va como <span> con manejador, igual que "Cómo llegar".
    wa = (f" <span class='app'>💬 <span class='wa' data-wa='https://wa.me/{tel}?text=' + quote(f'Hola, vi tu academia en {MARCA}') + '>WhatsApp</span></span>" if tel else "")
    ir = (f" <span class='app'>📍 <span class='ir' data-lat='{a.get('lat')}' data-lng='{a.get('lng')}'>Cómo llegar</span></span>" if a.get("lat") or a.get("lng") else "")
    sub = ui.unir_lugar(a.get("sedeClub"), a.get("zona"), sep=" · ")
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


def _n_locales(n: int) -> str:
    return "1 local verificado" if n == 1 else f"{n} locales verificados"


def slug(texto: str) -> str:
    """"Santiago de Surco" → "santiago-de-surco" (URLs de las páginas por zona)."""
    import unicodedata
    t = "".join(ch for ch in unicodedata.normalize("NFD", str(texto or "").lower()) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _explorar(deporte: str = "", fecha: str = "", request: Request | None = None, hora: str = "",
              zona: str = "") -> HTMLResponse:
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
    # Página por ZONA (SEO: /canchas/futbol/miraflores): solo los locales de esa zona.
    zona_nombre = ""
    if zona:
        lista = [c for c in lista if slug(_zona(c)) == zona]
        zona_nombre = _zona(lista[0]) if lista else ""
    fecha = fecha if _es_iso(fecha) else ""
    ratings = datos.ratings([c["id"] for c in lista])
    print(f"[explorar] dep={dep or '*'} {len(lista)} canchas: " + " | ".join(
        f"{c['nombre']} {c['hora_apertura']}-{c['hora_cierre']}/{c['duracion_slot_min']}m{'' if datos.reservable(c) else ' (pend)'}"
        for c in lista[:20]), flush=True)
    por_pais: dict[str, list[dict]] = {}
    for c in lista:
        por_pais.setdefault(_pais_de(c), []).append(c)
    dep_txt = catalogos.NOMBRE_DEPORTE.get(dep, "") if dep and not solo_aca else ""
    if zona_nombre:
        h1 = f"Canchas de {dep_txt} en {zona_nombre}" if dep_txt else f"Canchas en {zona_nombre}"
        encabezado = (f"<h1 style='font-size:26px;margin:18px 0 2px'>{e(h1)}</h1>"
                      f"<p class='sub' style='margin:0 0 6px'>{_n_locales(len(_agrupar_locales(lista)))} con turnos y precios "
                      f"a la vista. Reserva y paga en línea en {e(MARCA)}.</p>")
    else:
        # Título para buscadores y lectores de pantalla (la portada no tenía h1).
        h1 = ("Academias deportivas cerca de ti" if solo_aca else
              f"Reserva canchas de {dep_txt or catalogos.frase_deportes(catalogos.deportes_activos())} cerca de ti")
        encabezado = f"<h1 class='sr-only'>{e(h1)}</h1>"
    cuerpo = (encabezado + "<div class='ubic-mini'><span>📍</span><span id='ubicTxt'>Permite tu ubicación para ver primero las canchas más cercanas.</span>"
              "<button id='btnUbic'>Usar mi ubicación</button><span id='resBusq'></span></div>")
    if not solo_aca:  # amenidades / precio por hora no aplican a academias
        cuerpo += _barra_filtros(lista) + _modal_filtros(lista)
    cuerpo += "<div class='expl' id='expl'><div class='lista'><div id='grupos'>"
    primeras = 4  # tarjetas cuya foto se pide con prioridad (las que se ven al abrir)
    for pais in ("PE", "EC", "BO"):
        lst = por_pais.get(pais) or []
        if not lst:
            continue
        # Una tarjeta por LOCAL, como el app. Sin ubicación todavía (el JS
        # reordena por cercanía al tenerla), los locales con foto van primero:
        # la portada no abre con un cuadro vacío.
        grupos = sorted(_agrupar_locales(lst), key=lambda g: 0 if any(_fotos(x) for x in g) else 1)
        cards = "".join(_tarjeta(grupo, ratings, fecha, prioridad=(primeras > 0 and i < primeras))
                        for i, grupo in enumerate(grupos))
        primeras = 0  # solo las primeras tarjetas del PRIMER país pintado
        cuerpo += (f"<section class='grupo-pais' data-pais='{pais}'><div class='tit'><h2>{ui.bandera(pais)} Canchas en {NOMBRE_PAIS[pais]}"
                   f"<span class='cerca'></span></h2></div><div class='lst-grid'>{cards}</div></section>")
    cuerpo += "</div>"
    if solo_aca:
        cuerpo += "<div class='vacio' id='vacio' data-base='' style='display:none'>No encontramos academias con esa búsqueda. Prueba con otro nombre o zona.</div>"
    elif not lista:
        cuerpo += ("<div class='vacio' id='vacio'><h3>Todavía no hay canchas publicadas aquí</h3>"
                   "<p class='sub'>Estamos sumando locales. En la app ya puedes explorar el mapa completo.</p>"
                   f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir {MARCA} en Google Play</a></div></div>")
    else:
        cuerpo += "<div class='vacio' id='vacio' data-base='' style='display:none'>No hay canchas libres con esa búsqueda. Prueba con otra zona, día u hora.</div>"
    if todas and not lista and not solo_aca:
        cuerpo += ("<div class='vacio'>Todavía no hay canchas de este deporte. "
                   "<a href='/canchas'>Ver todas las canchas</a></div>")
    dep_aca = "" if solo_aca else dep
    # Academias solo de los países habilitados en la torre (decisión del
    # director, 10-oct-2026: ocultas en Bolivia y Ecuador).
    acads = [a for a in datos.academias_publicas() if isinstance(a, dict) and a.get("nombre")
             and (not dep_aca or (a.get("deporte") or "").lower() == dep_aca) and _ap.habilitada(a)]
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
                   f"<p class='sub' style='margin:-4px 0 12px'>Locales que aún no están en {MARCA}. Reserva desde la app o, si es tu "
                   "cancha, ¡Reclámala! y empieza a recibir reservas.</p><div class='lst-grid' id='gridDesc'></div>"
                   "<div class='desc-mas' id='descMas' style='display:none'><button type='button' class='btn sec' id='btnDescMas'>"
                   "Ver más</button></div></section>")
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
    cfg = ui.json_js({"cajas": {k: list(v) for k, v in _CAJAS.items()}, "centro": centro, "play": PLAY_URL, "dep": dep, "sizesTarjeta": miniaturas.SIZES_TARJETA,
                      "fecha": fecha, "hora": hora, "diasAdelante": DIAS_ADELANTE, "lugares": bool(config.PLACES_API_KEY),
                      "acadPaises": _ap.paises_habilitados(), "leaflet": LEAFLET})
    # Leaflet ya no va aquí: el JS lo carga al abrir el mapa (`cargarLeaflet`).
    head = (f"<style>{css_m}</style>" if css_m else "")
    cuerpo += f"<script>window.__explorar={cfg};</script><script>{_JS_EXPLORAR}</script>"
    if js_m:
        cuerpo += f"<script>{js_m}</script>"
    base_pub = config.PUBLIC_BASE_URL.rstrip('/') if getattr(config, "PUBLIC_BASE_URL", "") else ""
    canonical = (f"{base_pub}/canchas/{dep or 'todas'}/{zona}" if zona else f"{base_pub}/") if base_pub else ""
    ses = sesion.de_request(request)
    deps = catalogos.frase_deportes(catalogos.deportes_activos())
    titulo_tab = (f"{MARCA} · Academias deportivas cerca de ti" if solo_aca
                  else f"{MARCA} · Reserva canchas de {deps}")
    desc = (f"Academias de {catalogos.frase_deportes(catalogos.deportes_activos()[:3])} y más cerca de ti: programas, "
            "tarifario y matrícula en línea." if solo_aca
            else f"Reserva canchas de {deps} cerca de ti y paga con Yape o tarjeta. Perú, Ecuador y Bolivia.")
    if zona_nombre:
        titulo_tab = f"{h1} · {MARCA}"
        desc = f"{h1}: turnos libres, precios y fotos. Reserva y paga en línea con Yape o tarjeta en {MARCA}."
    return ui.shell(MARCA, cuerpo, extra_head=head, nav=_nav_explorar(dep, ses, _zonas_sugeridas(lista)), ancho=True, sesion=ses,
                    titulo_tab=titulo_tab, canonical=canonical, desc=desc)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def pagina_inicio(request: Request, deporte: str = "", fecha: str = "", hora: str = "") -> HTMLResponse:
    return _explorar(deporte, fecha, request, hora)


@router.get("/canchas", response_class=HTMLResponse)
def pagina_canchas(request: Request, deporte: str = "", fecha: str = "", hora: str = "") -> HTMLResponse:
    """Alias histórico del explorador (enlaces de la app, la home y el pie)."""
    return _explorar(deporte, fecha, request, hora)


@router.get("/canchas/{deporte}/{zona}", response_class=HTMLResponse)
def pagina_zona(request: Request, deporte: str, zona: str) -> HTMLResponse:
    """Página por deporte y zona para buscadores ("canchas de fútbol en
    Miraflores"). `todas` = cualquier deporte. Sin locales → 404."""
    dep = "" if deporte == "todas" else deporte.strip().lower()
    if dep and dep not in DEPORTES:
        return _no_encontrada("Página no encontrada")
    zona = slug(zona)
    if not any(datos.reservable(c) and slug(_zona(c)) == zona and (not dep or dep in _deportes_de(c))
               for c in datos.canchas_publicas()):
        r = _no_encontrada("Aún no hay canchas en esta zona")
        r.status_code = 404
        return r
    return _explorar(dep, "", request, "", zona=zona)


def paginas_zona() -> list[str]:
    """Rutas /canchas/{deporte}/{zona} con al menos un local (para el sitemap)."""
    rutas = set()
    for c in datos.canchas_publicas():
        if not datos.reservable(c) or not _zona(c):
            continue
        z = slug(_zona(c))
        rutas.add(f"/canchas/todas/{z}")
        for d in _deportes_de(c):
            rutas.add(f"/canchas/{d}/{z}")
    return sorted(rutas)


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
            c["minis"] = miniaturas.para_js(c["fotos"][:3])
    return {"ok": True, "region": region, "canchas": lista}
