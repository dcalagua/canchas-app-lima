"""FICHA DE RESERVA: `GET /reservar/{cancha_id}` (anuncio del LOCAL, tira de
días, turnos, datos, extras, boleador, fidelidad, pago) y la ficha de una
cancha descubierta `GET /lugar/{lugar_id}`. Incluye el JS de la reserva y los
bloques de la ficha (título del local, canchas hermanas, política, JSON-LD).

Movido tal cual desde `web/router.py`, que lo re-exporta.
"""

from __future__ import annotations

import servicios_extra as _se
import re
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import config
import empresa
from pagos import cargo_servicio as _cs
from pagos import devoluciones as _dev
from web import beneficios, datos, horarios, osm, pago_hospedado, sesion, ui
from reservas import reglas as _reglas
from pagos import cobro_directo as _cd
from web import dividir_pago as _dividir_web
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)
from web.comun import (AMENIDAD_NOMBRE, DEPORTES, DIAS_ADELANTE, DIAS_TIRA, MAX_SLOTS, PLAY_URL, _deporte, _deportes_de,
                       _fotos, _galeria, _maps, _moneda_de, _no_encontrada, _pago_web_disponible, _pais_de,
                       _pasarela_web, _zona)

router = APIRouter()


# ── página de reserva ─────────────────────────────────────────────────────────

_JS_RESERVA = (r"""
(function(){
  var C = window.__cancha, sel = {}, slots = [], hold = null, fechaSel = C.fecha || C.hoy;
  // SEÑA del dueño (como el app): por defecto se adelanta la seña y el resto se paga en la
  // cancha; el cliente puede elegir "Pagar todo ahora". Con boleador todo va en línea.
  var modoPago = (C.senaPct > 0) ? 'sena' : 'total';
  function esSena(){ return C.senaPct > 0 && modoPago === 'sena' && !bolLinea() && !bonoActivo(); }
  function senaTotal(){ var t = 0; Object.keys(sel).forEach(function(k){ t += Math.floor(sel[k].precio * C.senaPct / 100 + 0.5); }); return t; }
  var $ = function(id){ return document.getElementById(id); };
  var fmt = function(n){ return C.moneda + ' ' + Number(n).toFixed(2); };
  var esc = function(s){ return String(s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  // Errores de las REGLAS DEL CLUB (`reservas/reglas.py`) con un mensaje que se entiende.
  var ERR_REGLAS = {
    min_turnos: 'Este club pide reservar al menos ' + (C.minSlots || 2) + ' turnos seguidos.',
    max_turnos: 'Este club acepta hasta ' + C.maxSlots + (C.maxSlots === 1 ? ' turno' : ' turnos') + ' por reserva.',
    tope_reservas_dia: 'Ya tienes el máximo de reservas que este club permite por día. Elige otro día.',
    anticipacion_minima: 'Ese horario está muy próximo: el club pide reservar con más anticipación.',
    anticipacion_maxima: 'Ese día todavía no abre para reservas. Elige una fecha más cercana.',
    cerrado: 'El club está cerrado ese día. Elige otra fecha.',
    hora_invalida: 'Ese horario ya no está disponible. Elige otro.',
    fecha_fuera_de_rango: 'Esa fecha no está disponible para reservar.',
    puntos_no_disponibles: 'Este club recibe el pago directo: el canje de puntos no aplica aquí.',
    pago_no_disponible: 'El pago en línea de este club no está disponible ahora. Prueba más tarde o escribe al local.',
    no_verificada: 'Esta cancha aún está en verificación y no recibe reservas.',
    monto_invalido: 'Esa reserva no tiene un monto válido. Revisa los turnos elegidos.'
  };
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
    if(t.id === 'benBono'){ usarBono = t.checked; pintarResumen(); }
    if(t.id === 'benPts'){ usarPts = t.checked; pintarResumen(); }
  });
  // BOLEADOR / SPARRING (sep-2026): la lista depende de fecha, hora y turnos (disponibilidad y
  // otras solicitudes del boleador), así que se pide al servidor cada vez que cambia la selección.
  var bolSel = null, bolLista = [], bolClave = '';
  function bolLinea(){
    if(!C.boleadores || !bolSel) return null;
    var n = Object.keys(sel).length || 1;
    return {clave: 'boleador', nombre: C.nombreBoleador + ' · ' + bolSel.nombre, cantidad: n, unitario: bolSel.tarifa, precio: bolSel.tarifa * n, slug: bolSel.slug};
  }
  function pintarBoleadores(){
    var box = $('bolBox'); if(!box) return;
    if(!bolLista.length){ box.innerHTML = '<span class="sub">' + (Object.keys(sel).length ? 'Ningún ' + C.nombreBoleador.toLowerCase() + ' disponible para ese horario.' : 'Elige un horario para ver quién puede atenderte.') + '</span>'; return; }
    box.innerHTML = bolLista.map(function(b){
      var ini = b.foto ? '<img src="' + esc(b.foto) + '" alt="">' : '<span class="ini">' + esc((b.nombre || '?').charAt(0).toUpperCase()) + '</span>';
      var det = [b.etiquetas && b.etiquetas.length ? b.etiquetas.slice(0, 3).join(' · ') : '', b.aceptadas ? b.aceptadas + ' boleos' : 'Nuevo en ⟦MARCA⟧'].filter(Boolean).join(' · ');
      return '<div class="bol-card' + (bolSel && bolSel.slug === b.slug ? ' sel' : '') + '" data-slug="' + esc(b.slug) + '" role="button" tabindex="0">' + ini +
             '<div><span class="nom">' + esc(b.nombre) + '</span><span class="cat">' + esc(b.categoria) + '</span><div class="det">' + esc(det) + '</div></div>' +
             '<div class="pre">' + fmt(b.tarifa) + '<small>por turno</small></div><span class="chk">✓</span></div>';
    }).join('');
    box.querySelectorAll('.bol-card').forEach(function(el){
      el.addEventListener('click', function(){
        var s = el.dataset.slug;
        bolSel = (bolSel && bolSel.slug === s) ? null : bolLista.filter(function(b){ return b.slug === s; })[0] || null;
        pintarBoleadores(); pintarResumen();
      });
    });
  }
  function cargarBoleadores(){
    if(!C.boleadores || !$('bolBox')) return;
    var ks = Object.keys(sel).sort();
    if(!ks.length){ bolLista = []; bolSel = null; bolClave = ''; pintarBoleadores(); return; }
    var p = sel[ks[0]], clave = p.fecha + '|' + p.hora + '|' + ks.length + '|' + deporteSel();
    if(clave === bolClave) return;
    bolClave = clave;
    fetch('/boleadores/disponibles?cancha_id=' + encodeURIComponent(C.id) + '&fecha=' + encodeURIComponent(p.fecha) + '&hora=' + encodeURIComponent(p.hora) + '&turnos=' + ks.length + '&deporte=' + encodeURIComponent(deporteSel()))
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(clave !== bolClave) return;
        bolLista = (j && j.ok && j.boleadores) || [];
        if(bolSel && !bolLista.some(function(b){ return b.slug === bolSel.slug; })){ bolSel = null; pintarResumen(); }
        pintarBoleadores();
      }).catch(function(){ bolLista = []; pintarBoleadores(); });
  }
  // TARJETA DE FIDELIDAD (sep-2026): progreso del jugador en este local y, con
  // premio disponible, la casilla "Usar mi premio" descuenta el precio de la
  // cancha (hora gratis = el turno más barato; descuento = % por turno). El
  // servidor recalcula todo en /web/asegurar; aquí solo se muestra.
  var fid = null, usarFid = true;
  function fidDescuento(){
    if(!C.fidelidad || !fid || !fid.disponible || !usarFid || esSena() || bonoActivo()) return 0;
    var ps = Object.keys(sel).map(function(k){ return sel[k].precio; });
    if(!ps.length) return 0;
    if(fid.premio === 'hora_gratis') return Math.round(Math.min.apply(null, ps));
    return ps.reduce(function(a, p){ return a + Math.round(p * fid.descuentoPct / 100); }, 0);
  }
  function pintarFidelidad(){
    var box = $('fidBox'); if(!box || !C.fidelidad) return;
    var f = C.fidelidad, h = '<b>🎁 Tarjeta de fidelidad de ' + esc((fid && fid.local) || f.local || '') + '</b>';
    if(!fid){ h += '<div class="sub" style="margin:2px 0 0">Cada ' + f.meta + ' reservas pagadas, ' + esc(f.nombrePremio) + '. Inicia sesión para ver tu progreso.</div>'; box.innerHTML = h; return; }
    var sellos = ''; for(var i = 0; i < fid.meta; i++) sellos += '<span class="sello' + (i < fid.conteo ? ' on' : '') + '">' + (i < fid.conteo ? '✓' : '') + '</span>';
    h += '<div class="sellos">' + sellos + '</div>';
    if(fid.disponible){
      h += '<div class="sub" style="margin:4px 0 0"><b style="color:var(--verde)">¡Tienes ' + esc(fid.nombrePremio) + '!</b> Se aplica en esta reserva.</div>';
      h += '<label class="fid-usar"><input type="checkbox" id="fidUsar"' + (usarFid ? ' checked' : '') + '> Usar mi premio ahora (' + esc(fid.premioCorto) + ')</label>';
    } else {
      h += '<div class="sub" style="margin:4px 0 0">' + fid.conteo + ' de ' + fid.meta + ' reservas · te falta' + (fid.faltan === 1 ? '' : 'n') + ' ' + fid.faltan + ' para ' + esc(fid.nombrePremio) + '.</div>';
    }
    box.innerHTML = h;
    var ck = $('fidUsar'); if(ck) ck.addEventListener('change', function(){ usarFid = ck.checked; pintarResumen(); });
  }
  function cargarFidelidad(){
    if(!C.fidelidad || !$('fidBox')) return;
    if(C.login && !C.sesion){ fid = null; pintarFidelidad(); return; }
    fetch('/web/fidelidad?cancha_id=' + encodeURIComponent(C.id)).then(function(r){ return r.json(); })
      .then(function(j){ if(j && j.ok){ fid = j; pintarFidelidad(); pintarResumen(); } }).catch(function(){});
  }
  // BONO DE HORAS y PUNTOS PICHANGOL (como el resumen de reserva del app): el
  // bono cubre TODOS los turnos si alcanza (1 h de bono = 1 turno) y solo se
  // pagan los extras; los puntos (100 = S/ 3) van pagando todo en línea en
  // soles, sin seña, sin bono y sin premio de fidelidad. El servidor revalida.
  var ben = null, usarBono = true, usarPts = false;
  function turnosSel(){ var t = 0; Object.keys(sel).forEach(function(k){ t += sel[k].precio; }); return t; }
  function bonoActivo(){
    var n = Object.keys(sel).length;
    return !!(C.beneficios && ben && ben.activo && ben.bono && usarBono && n > 0 && ben.bono.horas >= n && !bolSel);
  }
  function puntosMotivo(){
    if(!C.beneficios || !ben || !ben.activo || !ben.puntos || !ben.puntos.aplica) return 'no';
    if(ben.puntos.disponibles < ben.puntos.canje) return 'no';
    if(bonoActivo()) return 'con tu bono';
    if(esSena()) return 'pagando solo la seña';
    if(fidDescuento() > 0) return 'con tu premio de fidelidad';
    if(Object.keys(sel).length && total() <= ben.puntos.descuento) return 'en reservas de ' + fmt(ben.puntos.descuento) + ' o menos';
    return '';
  }
  function puntosDesc(){ return (usarPts && Object.keys(sel).length && puntosMotivo() === '') ? ben.puntos.descuento : 0; }
  function pintarBeneficios(){
    var box = $('benBox'); if(!box) return;
    var n = Object.keys(sel).length, h = '';
    if(ben && ben.activo && ben.bono && ben.bono.horas > 0){
      var hb = ben.bono.horas, hTxt = hb + (hb === 1 ? ' hora' : ' horas');
      h += '<div class="ben-it"><b>🎟️ Tienes ' + hTxt + ' de bono en ' + esc(ben.local || 'este local') + '</b>';
      if(!n) h += '<div class="sub">Elige tus turnos y úsalo aquí: cada turno descuenta 1 hora, sin volver a pagar.</div>';
      else if(bolSel) h += '<div class="sub">Para usar tu bono quita el ' + esc(C.nombreBoleador.toLowerCase()) + ': se paga en línea.</div>';
      else if(hb < n) h += '<div class="sub">Tu bono cubre hasta ' + hTxt + ': elige ' + hb + (hb === 1 ? ' turno' : ' turnos') + ' o menos para usarlo.</div>';
      else h += '<label class="fid-usar"><input type="checkbox" id="benBono"' + (usarBono ? ' checked' : '') + '> Usar mi bono · ' + n + ' h · te quedan ' + (usarBono ? hb - n : hb) + ' h</label>';
      h += '</div>';
    }
    var pm = puntosMotivo();
    if(pm !== 'no'){
      h += '<div class="ben-it"><b>⭐ Tienes ' + ben.puntos.disponibles + ' puntos ⟦MARCA⟧</b>';
      if(pm) h += '<div class="sub">Canjea ' + ben.puntos.canje + ' puntos por ' + fmt(ben.puntos.descuento) + ' de descuento pagando todo en línea (no aplica ' + esc(pm) + ').</div>';
      else h += '<label class="fid-usar"><input type="checkbox" id="benPts"' + (usarPts ? ' checked' : '') + '> Usar ' + ben.puntos.canje + ' puntos: −' + fmt(ben.puntos.descuento) + ' en esta reserva</label>';
      h += '</div>';
    }
    box.innerHTML = h; box.style.display = h ? '' : 'none';
  }
  function cargarBeneficios(){
    if(!C.beneficios || !$('benBox')) return;
    if(C.login && !C.sesion){ ben = null; pintarBeneficios(); return; }
    fetch('/web/beneficios?cancha_id=' + encodeURIComponent(C.id)).then(function(r){ return r.json(); })
      .then(function(j){ ben = (j && j.ok) ? j : null; pintarResumen(); }).catch(function(){});
  }
  function total(){
    var t = bonoActivo() ? 0 : turnosSel();
    t -= fidDescuento();
    extrasSel().forEach(function(x){ t += x.precio; });
    var bl = bolLinea(); if(bl) t += bl.precio;
    return Math.max(0, t);
  }
  // CARGO POR SERVICIO ⟦MARCA⟧ (fase 2, sep-2026): el servidor cotiza
  // (`/web/cotizar`, misma regla que al cobrar); aquí solo se pinta la línea,
  // el ⓘ con el desglose y el total. Con C.cargo=false no se cotiza nada.
  var cot = null, cotT = null, cotCache = {};
  function deporteSel(){ return ($('deporte') && $('deporte').value) || C.deporteBase || ''; }
  function cotizar(t){
    if(!C.cargo || t <= 0){ cot = null; return; }
    // MODELO 2: el cargo depende del medio (Yape es más barato que la tarjeta).
    var md = (C.pasarela && C.pasarela !== 'culqi') ? '' : (window.pcgMedioPago ? pcgMedioPago() : 'yape');
    var base = Math.round(t * 100), k = base + '|' + deporteSel() + '|' + md;
    if(cotCache[k]){ cot = cotCache[k]; return; }
    cot = null;
    if(cotT) clearTimeout(cotT);
    cotT = setTimeout(function(){
      fetch('/web/cotizar?linea=reservas&moneda=' + encodeURIComponent(C.moneda) + '&base=' + base + '&deporte=' + encodeURIComponent(k.split('|')[1]) + '&medio=' + encodeURIComponent(md))
        .then(function(r){ return r.json(); })
        .then(function(j){ if(j && j.ok){ cotCache[k] = j; pintarResumen(); } })
        .catch(function(){});
    }, 150);
  }
  var BTN_INFO = '<button type="button" class="info-cargo" id="btnCargoInfo" aria-label="Qué incluye el cargo por servicio" style="border:1px solid var(--trazo);background:#fff;color:var(--tinta);border-radius:50%;width:20px;height:20px;line-height:18px;font-size:12px;cursor:pointer;padding:0;margin-left:4px;vertical-align:middle;display:inline-block">ⓘ</button>';
  function htmlDesglose(c){
    var h = '<div style="text-align:left;display:grid;gap:8px">';
    (c.desglose || []).forEach(function(x){ h += '<div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;border-bottom:1px solid #eee;padding:6px 0"><div><b>' + esc(x.nombre) + '</b><div style="color:#717171;font-size:12.5px">' + esc(x.detalle) + '</div></div><span style="white-space:nowrap;font-weight:700">' + fmt(x.monto_centimos / 100) + '</span></div>'; });
    h += '<div style="color:#717171;font-size:12px;margin-top:4px">' + esc(c.regla) + '. El precio de la cancha va completo al local, menos su comisión.</div></div>';
    return h;
  }
  // Cambiar Yape ⇄ Tarjeta vuelve a cotizar: en el modelo 2 el total cambia.
  document.addEventListener('pcg-medio', function(){ pintarResumen(); });
  document.addEventListener('click', function(ev){
    var op = ev.target && ev.target.closest ? ev.target.closest('.op-sena') : null;
    if(op){ ev.preventDefault(); if(modoPago !== op.dataset.modo){ modoPago = op.dataset.modo; pintarResumen(); } return; }
    var b = ev.target && ev.target.closest ? ev.target.closest('#btnCargoInfo') : null;
    if(b && cot && window.pcgAvisar) pcgAvisar({titulo: cot.titulo || 'Cargo por servicio ⟦MARCA⟧', html: htmlDesglose(cot), confirmar: 'Entendido', icono: '🛡️'});
  });
  function pintarResumen(){
    var ks = Object.keys(sel).sort(), n = ks.length, t = total(), pd = puntosDesc();
    var sn = esSena() ? senaTotal() : 0, base = sn > 0 ? sn : t - pd;
    pintarBeneficios();
    cotizar(base);
    var cargo = (cot && cot.activo && cot.cargo_centimos > 0) ? cot.cargo_centimos / 100 : 0;
    var h = '';
    if(!n){ h = '<div class="linea"><span style="color:var(--tenue)">Elige un horario para ver tu resumen.</span></div>'; }
    else {
      ks.forEach(function(k){ var s = sel[k];
        h += '<div class="linea"><span>' + esc(C.etiquetas[s.fecha] || s.fecha) + ' · ' + s.hora + '–' + s.fin + '</span><b>' + fmt(s.precio) + '</b></div>'; });
      extrasSel().forEach(function(x){ h += '<div class="linea"><span>' + esc(x.nombre) + (x.cantidad > 1 ? ' × ' + x.cantidad : '') + '</span><b>' + fmt(x.precio) + '</b></div>'; });
      var bl = bolLinea(); if(bl) h += '<div class="linea"><span>🎾 ' + esc(bl.nombre) + (bl.cantidad > 1 ? ' × ' + bl.cantidad : '') + '</span><b>' + fmt(bl.precio) + '</b></div>';
      var fd = fidDescuento(); if(fd > 0) h += '<div class="linea" style="color:var(--verde)"><span>🎁 ' + esc(fid.premioCorto) + ' · fidelidad</span><b>−' + fmt(fd) + '</b></div>';
      if(bonoActivo()) h += '<div class="linea" style="color:var(--verde)"><span>🎟️ Pagado con tu bono · ' + n + (n === 1 ? ' hora' : ' horas') + '</span><b>−' + fmt(turnosSel()) + '</b></div>';
      if(pd > 0) h += '<div class="linea" style="color:var(--verde)"><span>⭐ Canje de ' + ben.puntos.canje + ' puntos</span><b>−' + fmt(pd) + '</b></div>';
      if(C.senaPct > 0 && !bonoActivo()){
        if(bl) h += '<div class="linea" style="color:var(--tenue);font-size:13px"><span>Con ' + esc(C.nombreBoleador.toLowerCase()) + ' la reserva se paga completa en línea (quítalo si prefieres solo la seña).</span></div>';
        else {
          var op = function(m, tit, sub){ var on = modoPago === m; return '<label class="op-sena" data-modo="' + m + '" style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border:1.5px solid ' + (on ? 'var(--esmeralda)' : 'var(--trazo)') + ';border-radius:14px;cursor:pointer;background:' + (on ? '#EEF8F1' : '#fff') + '"><input type="radio" name="modoPago" ' + (on ? 'checked' : '') + ' style="width:auto;flex:none;margin-top:3px;accent-color:#0B7A57"><span><b>' + tit + '</b><br><small style="color:var(--tenue)">' + sub + '</small></span></label>'; };
          h += '<div style="display:grid;gap:8px;margin:10px 0 4px">' +
            op('sena', 'Pagar seña ' + C.senaPct + ' % ahora · ' + fmt(senaTotal()), 'Asegura tu hora; el resto (' + fmt(t - senaTotal()) + ') lo pagas en la cancha.') +
            op('total', 'Pagar todo ahora · ' + fmt(t), 'No pagas nada en la cancha.') + '</div>';
          if(sn > 0) h += '<div class="linea" style="color:var(--tenue);font-size:12.5px"><span>La seña no es reembolsable: si no llegas, queda a favor de la cancha.</span></div>';
          if(sn > 0) h += '<div class="linea"><span>Seña ' + C.senaPct + ' % (pagas hoy)</span><b>' + fmt(sn) + '</b></div><div class="linea" style="color:var(--tenue)"><span>Resto en la cancha</span><b>' + fmt(t - sn) + '</b></div>';
        }
      }
      if(C.cargo && base > 0) h += '<div class="linea" id="lineaCargo"><span>Cargo por servicio ⟦MARCA⟧ ' + BTN_INFO + '</span><b>' + (cot ? fmt(cargo) : '…') + '</b></div>';
    }
    $('lineas').innerHTML = h;
    cargarBoleadores();
    var tt = base + (base > 0 ? cargo : 0);
    $('tot').textContent = fmt(tt); $('totBarra').textContent = fmt(tt);
    $('totLbl').textContent = sn > 0 ? 'A pagar hoy' : 'Total'; if($('totBarraLbl')) $('totBarraLbl').textContent = sn > 0 ? 'Seña hoy' : 'Total';
    var txt = n ? (sn > 0 ? ('Pagar seña ' + fmt(tt) + ' y reservar') : tt > 0 ? ('Reservar y pagar ' + fmt(tt)) : (bonoActivo() ? 'Reservar con mi bono 🎟️' : 'Reservar gratis 🎁')) : 'Elige un horario';
    var corto = n ? (sn > 0 ? 'Pagar seña' : tt > 0 ? 'Reservar' : (bonoActivo() ? 'Usar mi bono 🎟️' : 'Reservar gratis 🎁')) : 'Elige un horario';
    // PAGO DIVIDIDO (bloque de `web/dividir_pago.py`): cuánto paga cada uno y el texto del botón.
    if(window.pcgDividirPinta && pcgDividirPinta(tt, n, {sena: sn > 0, bono: bonoActivo(), puntos: pd > 0, fid: fidDescuento() > 0, bol: !!bl})){ txt = 'Apartar y dividir el pago'; corto = 'Dividir'; }
    $('btnPagar').disabled = !n; $('btnPagar').textContent = txt;
    $('btnPagarBarra').disabled = !n; $('btnPagarBarra').textContent = corto;
  }
  document.addEventListener('pcg-dividir', function(){ pintarResumen(); });
  function pintarDias(){
    $('dias').innerHTML = C.dias.map(function(d){
      return '<span class="chip' + (d.iso === fechaSel ? ' sel' : '') + '" data-f="' + d.iso + '"><b>' + esc(d.corto) + '</b><small>' + esc(d.sub) + '</small></span>';
    }).join('');
    document.querySelectorAll('#dias .chip').forEach(function(el){
      el.addEventListener('click', function(){ if(el.dataset.f === fechaSel) return; liberar(); fechaSel = el.dataset.f; pintarDias(); cargar(); });
    });
  }
  // LISTA DE ESPERA: un turno ocupado avisa por push si se libera (misma tabla que el app).
  function listaEspera(s, ya){
    var cuando = (C.etiquetas[s.fecha] || s.fecha) + ' a las ' + s.hora;
    if(!C.sesion){ pcgConfirmar({titulo: 'Te avisamos si se libera', icono: '🔔', mensaje: 'Inicia sesión y te mandamos un aviso si el turno de ' + cuando + ' queda libre.', confirmar: 'Iniciar sesión'})
      .then(function(ok){ if(ok) location.href = '/entrar?volver=' + encodeURIComponent(location.pathname + location.search); }); return; }
    pcgConfirmar(ya ? {titulo: 'Ya estás en la lista', icono: '🔔', mensaje: 'Te avisaremos si el turno de ' + cuando + ' se libera. ¿Quieres salir de la lista?', confirmar: 'Salir de la lista', destructivo: true}
                    : {titulo: '¿Te avisamos si se libera?', icono: '🔔', mensaje: 'El turno de ' + cuando + ' está ocupado. Si lo cancelan, te llega un aviso y lo reserva el primero que entre.', confirmar: 'Avísame'})
      .then(function(ok){ if(!ok) return;
        fetch(ya ? '/web/espera/salir' : '/web/espera', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({cancha_id: C.id, fecha: s.fecha || fechaSel, hora: s.hora})})
          .then(function(r){ return r.json(); }).then(function(j){
            if(!j.ok){ pcgAvisar({titulo: 'No se pudo', icono: '🔔', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); return; }
            if(window.pcgToast) pcgToast(ya ? 'Saliste de la lista de espera' : 'Listo: te avisamos si se libera');
            cargar();
          }); });
  }
  function cargar(){
    sel = {}; pintarResumen();
    $('slots').innerHTML = '<span class="skel"></span><span class="skel"></span><span class="skel"></span><span class="skel"></span>';
    fetch('/web/disponibilidad/' + encodeURIComponent(C.id) + '?fecha=' + fechaSel)
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){ $('slots').innerHTML = '<span class="sub">No pudimos cargar los horarios de ese día.</span>'; return; }
        slots = j.slots;
        var enEspera = {}, propia = {}; (j.espera || []).forEach(function(h){ enEspera[h] = 1; }); (j.propias || []).forEach(function(h){ propia[h] = 1; });
        var libres = slots.filter(function(s){ return !s.ocupado; }).length;
        if(j.cerrado){
          $('slots').innerHTML = '<div class="cl-aviso warn" role="status"><b>🚫 El club está cerrado este día</b><span>' + esc(j.cerrado === 'cerrado' ? 'No atiende este día.' : j.cerrado) + ' Prueba otra fecha.</span></div>'; return; }
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
            var tag = s.promo ? '<span class="tag">−' + s.promo + ' % promo</span>' : (s.franja ? '<span class="tag">⭐ ' + esc(s.franja) + '</span>' : (s.valle ? '<span class="tag">⚡ hora feliz</span>' : ''));
            if(s.luz) tag += '<span class="tag">💡 incluye luz</span>';
            // Ocupado = se puede tocar para entrar a la LISTA DE ESPERA (como el app).
            if(s.ocupado) tag = propia[s.hora] ? '<span class="tag esp on">✓ Tu reserva</span>' : (enEspera[s.hora] ? '<span class="tag esp on">🔔 Te avisamos</span>' : '<span class="tag esp">🔔 Avísame</span>');
            html += '<button type="button" class="slot' + (s.ocupado ? ' off' : '') + '" data-i="' + i + '" aria-pressed="false"' +
                    ' aria-label="' + s.hora + ' a ' + s.fin + ', ' + (s.ocupado ? (enEspera[s.hora] ? 'ocupado, estás en lista de espera' : 'ocupado, toca para que te avisemos si se libera') : fmt(s.precio)) + '">' +
                    dia + '<b>' + s.hora + ' <small>– ' + s.fin + '</small></b><span class="pr">' + (s.ocupado ? 'Ocupado' : fmt(s.precio)) + '</span>' + tag + '</button>';
          });
          html += '</div></div>';
        });
        if(pmax > pmin) html += '<p class="slots-nota">El precio varía según la hora: desde ' + fmt(pmin) + ' hasta ' + fmt(pmax) + ' por turno.</p>';
        $('slots').innerHTML = html + (libres ? '' : '<div class="sub" style="width:100%">Todos los turnos de este día están tomados.</div>');
        document.querySelectorAll('#slots .slot').forEach(function(el){
          el.addEventListener('click', function(){
            var s = slots[parseInt(el.dataset.i)];
            if(s.ocupado){ if(propia[s.hora]){ if(window.pcgToast) pcgToast('Este turno ya es tuyo: míralo en Mis reservas'); return; } listaEspera(s, !!enEspera[s.hora]); return; }
            var k = s.fecha + '|' + s.hora;
            if(sel[k]){ delete sel[k]; el.classList.remove('sel'); el.setAttribute('aria-pressed', 'false'); }
            else {
              if(Object.keys(sel).length >= C.maxSlots){ mostrarError('Este club acepta hasta ' + C.maxSlots + (C.maxSlots === 1 ? ' turno' : ' turnos') + ' por reserva.'); return; }
              sel[k] = s; el.classList.add('sel'); el.setAttribute('aria-pressed', 'true'); ocultarError();
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
    if($('celular') && !$('celular').value) $('celular').value = u.celular || '';
    if($('email')) $('email').value = u.email || '';
    if(db && !$('quien')){ db.insertAdjacentHTML('afterbegin', '<div class="quien" id="quien">' + (u.foto ? '<img src="' + esc(u.foto) + '" alt="">' : '') + '<div><b>' + esc(u.nombre || u.email) + '</b><div class="m">' + esc(u.email) + '</div></div><button type="button" class="btn sec" onclick="cerrarSesion()">Cambiar cuenta</button></div>'); }
    pintarResumen();
    cargarFidelidad();
    cargarBeneficios();
  };
  function validar(d){
    if(!Object.keys(sel).length) return 'Elige al menos un horario.';
    if(C.minSlots > 1 && Object.keys(sel).length < C.minSlots) return ERR_REGLAS.min_turnos;
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
    ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = true; $(id).textContent = id === 'btnPagar' ? 'Reservando tu horario…' : 'Reservando…'; });
    var blSel = bolLinea();
    fetch('/web/asegurar', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({cancha_id: C.id, horas: horas, extras: extras, deporte: deporte, nombre: d.nombre, celular: d.celular, email: d.email, boleador: blSel ? blSel.slug : '', fidelidad: fidDescuento() > 0, pago: esSena() ? 'sena' : 'total', bono: bonoActivo(), puntos: puntosDesc() > 0, medio: (window.pcgMedioPago ? pcgMedioPago() : ''), dividir: (window.pcgDividirN ? pcgDividirN() : 0)})})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){
          pintarResumen();
          if(j.error === 'ocupado'){ mostrarError('Alguien acaba de tomar uno de esos horarios. Elige otro, por favor.'); cargar(); }
          else if(j.error === 'boleador_no_disponible'){ bolSel = null; bolClave = ''; mostrarError('Ese ' + C.nombreBoleador.toLowerCase() + ' ya no está disponible para ese horario. Elige otro o reserva sin él.'); pintarResumen(); }
          else if(j.error === 'sesion_requerida'){ C.sesion = null; mostrarError('Tu sesión venció. Inicia sesión con Google para reservar.'); var lb = $('loginBox'), db = $('datosBox'); if(lb) lb.style.display = ''; if(db) db.style.display = 'none'; }
          else if(j.error === 'sin_premio'){ fid = null; usarFid = false; mostrarError('Tu premio de fidelidad ya no está disponible. Revisa el total y vuelve a intentar.'); cargarFidelidad(); }
          else if(j.error === 'sin_bono'){ usarBono = false; mostrarError('Tu bono ya no alcanza para esos turnos (¿lo usaste en otra pestaña?). Revisa el total y vuelve a intentar.'); cargarBeneficios(); }
          else if(j.error === 'sin_puntos'){ usarPts = false; mostrarError('Tus puntos ya no alcanzan para el canje o no aplican a esta reserva. Revisa el total y vuelve a intentar.'); cargarBeneficios(); }
          else if(ERR_REGLAS[j.error]){ mostrarError(ERR_REGLAS[j.error]); if(j.error === 'hora_invalida' || j.error === 'cerrado') cargar(); }
          else if(j.error === 'bono_con_boleador'){ mostrarError('Con tu bono no se puede contratar ' + C.nombreBoleador.toLowerCase() + ': quítalo o reserva sin el bono.'); }
          else mostrarError(j.mensaje || 'No pudimos reservar el horario. Inténtalo de nuevo.');
          return;
        }
        if(j.division){ hold = null; pcgIr(j.division.url, 'Creando el enlace para tus amigos…'); return; }
        hold = j;
        var fdTxt = j.fidelidad ? {t: '🎁 ' + esc(j.fidelidad.texto) + ' · fidelidad', m: -j.fidelidad.descuento} : null;
        var bnTxt = j.bono ? {t: '🎟️ Pagado con tu bono · ' + j.bono.horas + (j.bono.horas === 1 ? ' hora' : ' horas'), m: -j.bono.cubre} : null;
        var ptTxt = j.puntos ? {t: '⭐ Canje de ' + j.puntos.puntos + ' puntos ⟦MARCA⟧', m: -j.puntos.descuento} : null;
        if(j.sin_pago){
          // RESERVA GRATIS (hora gratis sin extras): no se abre Culqi; se confirma directo.
          var confirmarGratis = function(){
            ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).textContent = id === 'btnPagar' ? 'Confirmando tu reserva…' : 'Confirmando…'; });
            var h0 = hold; hold = null;
            fetch('/web/pagar', {method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({ids: h0.ids, firma: h0.firma, token: '', medio: j.bono ? 'bono' : 'fidelidad', email: d.email})})
              .then(function(r){ return r.json(); })
              .then(function(p){ if(p.ok){ window.location.href = p.url; } else { mostrarError(p.mensaje || 'No pudimos confirmar la reserva.'); pintarResumen(); cargar(); } })
              .catch(function(){ mostrarError('No pudimos confirmar la reserva. Inténtalo de nuevo.'); pintarResumen(); });
          };
          if(!window.pcgResumenPago){ confirmarGratis(); return; }
          var lg = Object.keys(sel).sort().map(function(k){ var s = sel[k]; return {t: esc(C.etiquetas[s.fecha] || s.fecha) + ' · ' + s.hora + '–' + s.fin, m: s.precio}; });
          if(fdTxt) lg.push(fdTxt);
          if(bnTxt) lg.push(bnTxt);
          pcgResumenPago({moneda: C.moneda, medio: j.bono ? 'bono' : 'fidelidad', lineas: lg, cargo: null, total: 0, titulo: 'Resumen de tu reserva',
                          confirmar: j.bono ? 'Confirmar con mi bono 🎟️' : 'Confirmar reserva gratis 🎁',
                          nota: j.bono ? ('Tus turnos se pagan con tu bono: se descuentan ' + j.bono.horas + ' h y te quedan ' + j.bono.quedan + ' h. No se te cobra nada.')
                                       : 'Esta reserva sale gratis por tu tarjeta de fidelidad. No se te cobra nada.'})
            .then(function(ok){ if(ok){ confirmarGratis(); } else { liberar(); pintarResumen(); } });
          return;
        }
        // COBRO DIRECTO: el dinero va a la cuenta DEL CLUB. Con su Culqi se abre con SU llave pública
        // (el servidor cobra con su llave secreta); con comprobante se muestran sus datos de pago.
        var esVoucher = !!(j.directo && (!j.directo.culqi_public_key || (window.pcgMedioPago && pcgMedioPago() === 'voucher')));
        var hosp = !j.directo && !!(C.pasarela && C.pasarela !== 'culqi');
        var pkPago = (j.directo && j.directo.culqi_public_key) || C.pk;
        if(!esVoucher && !hosp && !pkPago){ mostrarError('El pago en línea no está disponible por ahora.'); liberar(); pintarResumen(); return; }
        // El medio se elige en la página (Yape por defecto) y Culqi se abre SOLO con ese método:
        // el Checkout v4 siempre abría en Tarjeta aunque Yape fuera primero (pedido del director, 27-sep-2026).
        // En $ / Bs el medio es la pasarela HOSPEDADA del país (PayPhone, Libélula o la de prueba en QAS).
        var m = esVoucher ? 'voucher' : hosp ? C.pasarela : (window.pcgMedioPago ? pcgMedioPago() : 'yape');
        // COBRO EN USD / BOB: se crea la orden en el servidor (monto recalculado allí) y el navegador va a
        // la página de la pasarela; al volver, /web/pago/{orden} confirma y lleva al comprobante.
        var irPasarela = function(){
          ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).textContent = id === 'btnPagar' ? 'Abriendo ' + C.pasarelaNombre + '…' : 'Abriendo…'; });
          pcgCargando('Abriendo el pago seguro de ' + C.pasarelaNombre + '…');
          var h = hold;
          fetch('/web/pago/reserva', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ids: h.ids, firma: h.firma})})
            .then(function(r){ return r.json(); })
            .then(function(p){
              if(p.ok && p.url){ hold = null; try { if(p.orden) sessionStorage.setItem('pcg_orden_' + C.id, p.orden); } catch(e){} window.location.href = p.url; return; }
              pcgCargando(false); mostrarError(p.mensaje || 'No pudimos abrir el pago. Inténtalo de nuevo.');
              if(p.error !== 'en_curso'){ liberar(); cargar(); }
              pintarResumen();
            }).catch(function(){ pcgCargando(false); mostrarError('Sin conexión. Inténtalo de nuevo.'); liberar(); pintarResumen(); });
        };
        // RESUMEN DE TU PAGO (pedido del director, 28-sep-2026): Culqi solo muestra el total; aquí se
        // confirma el detalle (turnos, extras, cargo por servicio con desglose y total, tal cual lo
        // cobrará el servidor). "Volver" libera la retención del horario.
        var abrirCulqi = function(){
        Culqi.publicKey = pkPago;
        Culqi.settings({ title: '⟦MARCA⟧', currency: 'PEN', amount: j.total_centimos });
        Culqi.options({ lang: 'es', installments: false,
          paymentMethods: { yape: m === 'yape', tarjeta: m === 'tarjeta', bancaMovil: false, agente: false, billetera: false, cuotealo: false },
          style: { logo: C.logo, bannerColor: '#0F1B2D', buttonBackground: '#0B7A57', buttonText: 'Pagar', buttonTextColor: '#FFFFFF' } });
        window.culqi = function(){
          if(Culqi.token){
            var token = Culqi.token.id, medio = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
            Culqi.close();
            ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).textContent = id === 'btnPagar' ? 'Confirmando tu pago…' : 'Confirmando…'; });
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
        };
        var abrirPago = esVoucher ? function(){ pcgVoucher(j); } : hosp ? irPasarela : abrirCulqi;
        if(!window.pcgResumenPago){ abrirPago(); return; }
        var lineas = Object.keys(sel).sort().map(function(k){ var s = sel[k]; return {t: esc(C.etiquetas[s.fecha] || s.fecha) + ' · ' + s.hora + '–' + s.fin, m: s.precio}; });
        extrasSel().forEach(function(x){ lineas.push({t: esc(x.nombre) + (x.cantidad > 1 ? ' × ' + x.cantidad : ''), m: x.precio}); });
        if(blSel) lineas.push({t: '🎾 ' + esc(blSel.nombre) + (blSel.cantidad > 1 ? ' × ' + blSel.cantidad : ''), m: blSel.precio});
        if(fdTxt) lineas.push(fdTxt);
        if(bnTxt) lineas.push(bnTxt);
        if(ptTxt) lineas.push(ptTxt);
        if(j.pago === 'sena') lineas = [{t: 'Seña ' + j.sena_pct + ' % de ' + fmt(j.total) + ' (asegura tu hora)', m: j.sena}];
        var cj = j.cargo && j.cargo_centimos > 0 ? {monto: j.cargo_centimos / 100, titulo: j.cargo.titulo, html: htmlDesglose(j.cargo)} : null;
        pcgResumenPago({moneda: C.moneda, medio: m, medioNombre: hosp ? C.pasarelaNombre : '', lineas: lineas, cargo: cj, total: j.total_centimos / 100,
                        confirmar: esVoucher ? ('Ver cómo pagar · ' + fmt(j.total_centimos / 100)) : '',
                        nota: (esVoucher ? 'Pagas directo al club y subes tu comprobante; el club lo confirma. ' : '') + (j.pago === 'sena' ? 'El resto (' + fmt(j.resto) + ') lo pagas en la cancha. ' : '') + (j.bono ? 'Tus turnos van con tu bono (te quedan ' + j.bono.quedan + ' h); pagas solo los servicios extra. ' : '') + (j.puntos ? 'Los ' + j.puntos.puntos + ' puntos se descuentan solo si el pago entra. ' : '') + (hosp ? 'Te llevamos a la página segura de ' + C.pasarelaNombre + '; el horario queda apartado para ti mientras pagas.' : 'El horario queda reservado para ti mientras pagas (' + Math.round((j.hold_segundos || 600) / 60) + ' min).') + (blSel ? ' El ' + C.nombreBoleador.toLowerCase() + ' confirma después; si no puede, te devolvemos su parte.' : '')})
          .then(function(ok){ if(ok){ abrirPago(); } else { liberar(); pintarResumen(); } });
      }).catch(function(){ pintarResumen(); mostrarError('No pudimos reservar el horario. Inténtalo de nuevo.'); });
  }
  $('btnPagar').addEventListener('click', pagar);
  $('btnPagarBarra').addEventListener('click', pagar);
  document.querySelectorAll('input[name=extra]').forEach(function(x){ x.addEventListener('change', pintarResumen); });
  window.addEventListener('beforeunload', liberar);
  // ¿Volvió de la pasarela con el botón "atrás" sin terminar? Su horario sigue apartado por la
  // orden en curso: se ofrece retomarla (o cancelarla) en vez de chocar con "ocupado".
  function ordenEnCurso(){
    var oid = null; try { oid = sessionStorage.getItem('pcg_orden_' + C.id); } catch(e){}
    if(!oid) return;
    fetch('/web/pago/' + encodeURIComponent(oid) + '/estado').then(function(r){ return r.json(); }).then(function(j){
      if(!j || !j.ok || j.estado !== 'pendiente'){ try { sessionStorage.removeItem('pcg_orden_' + C.id); } catch(e){} return; }
      pcgConfirmar({titulo: 'Tienes un pago en curso', icono: '⏳', confirmar: 'Ver mi pago', cancelar: 'Ahora no',
                    mensaje: 'Empezaste a pagar una reserva en esta cancha con ' + C.pasarelaNombre + '. Retómala o cancélala para liberar el horario.'})
        .then(function(ok){ if(ok) window.location.href = '/web/pago/' + encodeURIComponent(oid); });
    }).catch(function(){});
  }
  // PAGO CON COMPROBANTE (cobro directo al club, como checkout_directo_screen del app): el jugador
  // paga al Yape / Plin / cuenta DEL CLUB, sube la foto y el N.º de operación; el club lo confirma.
  // El horario sigue apartado mientras lo sube y, ya enviado, hasta que el club lo revise.
  var VCH_ERR = {
    sesion_requerida: 'Tu sesión venció. Inicia sesión con Google y vuelve a intentarlo.',
    hold_vencido: 'Se acabó el tiempo para apartar este horario. Elige uno de nuevo.',
    firma: 'No pudimos validar tu reserva. Recarga la página e inténtalo de nuevo.',
    medio_no_disponible: 'Elige el medio con el que pagaste.',
    operacion_requerida: 'Escribe el número de operación que figura en tu comprobante.',
    imagen_invalida: 'La foto no es válida. Sube una captura o foto del comprobante (máx. 6 MB).',
    operacion_repetida: 'Ese número de operación ya se usó en otro pago. Revísalo.',
    voucher_repetido: 'Esa misma imagen ya se subió en otro pago. Sube el comprobante de este pago.',
    club_suspendido: 'Este club no está recibiendo pagos ahora. Elige otro horario o escribe al local.',
    monto_invalido: 'Esta reserva no tiene monto a pagar.'
  };
  function comprimir(file, cb){
    // Foto del comprobante: hasta 1600 px en JPEG (el servidor la vuelve a normalizar).
    var fr = new FileReader();
    fr.onload = function(){
      var img = new Image();
      img.onload = function(){
        var k = Math.min(1, 1600 / Math.max(img.width, img.height)), cv = document.createElement('canvas');
        cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k);
        cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
        cb(cv.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = function(){ cb(null); };
      img.src = fr.result;
    };
    fr.onerror = function(){ cb(null); };
    fr.readAsDataURL(file);
  }
  function datoMedio(m){
    var filas = [];
    function f(et, v){ if(v) filas.push("<div class='vch-dato'><span>" + et + "</span><b>" + esc(v) + "</b><button type='button' class='vch-copiar' data-copiar='" + esc(v) + "' aria-label='Copiar " + et + "'>Copiar</button></div>"); }
    f(m.tipo === 'transferencia' ? 'Cuenta' : 'Número', m.numero || m.cuenta);
    if(m.numero && m.cuenta) f('Cuenta', m.cuenta);
    f('CCI', m.cci);
    var h = "<div class='vch-medio'><div class='vch-mt'>" + esc(m.etiqueta || m.tipo) + (m.banco ? ' · ' + esc(m.banco) : '') + "</div>"
          + (m.titular ? "<div class='vch-tit'>A nombre de <b>" + esc(m.titular) + "</b></div>" : '') + filas.join('')
          + (m.qr_url ? "<img class='vch-qr' src='" + esc(m.qr_url) + "' alt='QR de " + esc(m.etiqueta || m.tipo) + " del club' loading='lazy'>" : '')
          + (m.nota ? "<div class='vch-nota'>" + esc(m.nota) + "</div>" : '') + "</div>";
    return h;
  }
  function pcgVoucher(j){
    var medios = (j.directo && j.directo.medios) || [];
    var monto = j.total_centimos / 100, fin = Date.now() + (j.hold_segundos || 600) * 1000, foto = null, elegido = medios.length === 1 ? medios[0].tipo : '';
    var ov = document.createElement('div');
    ov.className = 'vch-ov'; ov.setAttribute('role', 'dialog'); ov.setAttribute('aria-modal', 'true'); ov.setAttribute('aria-labelledby', 'vchTit');
    ov.innerHTML = "<div class='vch'><div class='vch-cab'><div><div class='vch-k'>Pago directo al club</div><h3 id='vchTit'>Paga " + fmt(monto) + "</h3></div>"
      + "<button type='button' class='vch-x' aria-label='Cancelar y soltar el horario'>✕</button></div>"
      + "<div class='vch-reloj' role='timer' aria-live='off'>⏳ Tu horario está apartado <b id='vchReloj'></b></div>"
      + "<ol class='vch-pasos'><li><b>Paga " + fmt(monto) + "</b> con uno de estos medios del club:"
      + medios.map(datoMedio).join('') + "</li>"
      + "<li><b>¿Con qué pagaste?</b><div class='chips' id='vchMedios'>" + medios.map(function(m){ return "<button type='button' class='chip" + (m.tipo === elegido ? ' sel' : '') + "' data-t='" + esc(m.tipo) + "' aria-pressed='" + (m.tipo === elegido) + "'>" + esc(m.etiqueta || m.tipo) + "</button>"; }).join('') + "</div></li>"
      + "<li><label for='vchOp'><b>Número de operación</b></label><input id='vchOp' inputmode='text' autocomplete='off' maxlength='30' placeholder='Figura en tu comprobante'></li>"
      + "<li><b>Foto o captura del comprobante</b><label class='vch-foto' id='vchFotoLbl'><input type='file' id='vchFoto' accept='image/*'><span id='vchFotoTxt'>📷 Elegir foto</span></label><img id='vchPrev' class='vch-prev' alt='Vista previa del comprobante' hidden></li></ol>"
      + "<div class='estado bad' id='vchErr' role='alert'></div>"
      + "<button type='button' class='btn lg' id='vchEnviar'>Enviar comprobante</button>"
      + "<div class='sub vch-pie'>El club revisa tu pago y te avisamos. Si no lo confirma, el horario se libera y no se te cobra nada por la plataforma.</div></div>";
    document.body.appendChild(ov); document.body.style.overflow = 'hidden';
    function tic(){
      var r = Math.max(0, Math.round((fin - Date.now()) / 1000)), el = document.getElementById('vchReloj');
      if(el) el.textContent = 'por ' + Math.floor(r / 60) + ':' + ('0' + (r % 60)).slice(-2) + ' min';
      if(r <= 0){ clearInterval(reloj); cerrar(true); mostrarError(VCH_ERR.hold_vencido); cargar(); }
    }
    var reloj = setInterval(tic, 1000); tic();
    function err(t){ var e = document.getElementById('vchErr'); e.textContent = t; e.style.display = t ? 'block' : 'none'; }
    function cerrar(soltar){ clearInterval(reloj); ov.remove(); document.body.style.overflow = ''; if(soltar){ liberar(); pintarResumen(); } }
    ov.querySelector('.vch-x').addEventListener('click', function(){
      pcgConfirmar({titulo: '¿Cancelar el pago?', mensaje: 'Se libera el horario que apartaste.', confirmar: 'Sí, cancelar', cancelar: 'Seguir pagando', destructivo: true})
        .then(function(ok){ if(ok) cerrar(true); });
    });
    ov.addEventListener('click', function(ev){
      var cp = ev.target.closest('[data-copiar]');
      if(cp){ try { navigator.clipboard.writeText(cp.dataset.copiar); cp.textContent = 'Copiado ✓'; setTimeout(function(){ cp.textContent = 'Copiar'; }, 1500); } catch(e){} return; }
      var ch = ev.target.closest('#vchMedios [data-t]');
      if(ch){ elegido = ch.dataset.t; ov.querySelectorAll('#vchMedios [data-t]').forEach(function(x){ x.classList.toggle('sel', x === ch); x.setAttribute('aria-pressed', x === ch); }); }
    });
    document.getElementById('vchFoto').addEventListener('change', function(ev){
      var f = ev.target.files && ev.target.files[0]; if(!f) return;
      document.getElementById('vchFotoTxt').textContent = 'Procesando…';
      comprimir(f, function(u){
        foto = u;
        document.getElementById('vchFotoTxt').textContent = u ? '📷 Cambiar foto' : '📷 Elegir foto';
        var pv = document.getElementById('vchPrev'); if(u){ pv.src = u; pv.hidden = false; } else { pv.hidden = true; err(VCH_ERR.imagen_invalida); }
      });
    });
    document.getElementById('vchEnviar').addEventListener('click', function(){
      var op = (document.getElementById('vchOp').value || '').trim();
      if(!elegido) return err(VCH_ERR.medio_no_disponible);
      if(op.replace(/[^0-9A-Za-z]/g, '').length < 4) return err(VCH_ERR.operacion_requerida);
      if(!foto) return err('Sube la foto o captura de tu comprobante.');
      err(''); var b = this; b.disabled = true; b.textContent = 'Enviando…'; pcgCargando('Enviando tu comprobante…');
      fetch('/web/voucher', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: j.ids, firma: j.firma, medio: elegido, operacion: op, imagen: foto})})
        .then(function(r){ return r.json(); })
        .then(function(p){
          if(p.ok){
            hold = null; clearInterval(reloj);
            pcgIr('/reserva/' + encodeURIComponent(j.grupo || j.ids[0]) + '?enviado=1', 'Listo, el club revisará tu pago…');
            return;
          }
          pcgCargando(false); b.disabled = false; b.textContent = 'Enviar comprobante';
          err(VCH_ERR[p.error] || 'No pudimos enviar tu comprobante. Inténtalo de nuevo.');
          if(p.error === 'hold_vencido'){ cerrar(false); hold = null; mostrarError(VCH_ERR.hold_vencido); cargar(); }
        }).catch(function(){ pcgCargando(false); b.disabled = false; b.textContent = 'Enviar comprobante'; err('Sin conexión. Inténtalo de nuevo.'); });
    });
    setTimeout(function(){ var x = ov.querySelector('.vch-x'); if(x) x.focus(); }, 50);
  }
  if(C.pasarela && C.pasarela !== 'culqi' && C.pasarela !== 'directo'){ ordenEnCurso(); window.addEventListener('pageshow', function(ev){ if(ev.persisted){ pintarResumen(); ordenEnCurso(); } }); }
  pintarDias(); cargar(); cargarFidelidad(); cargarBeneficios();
})();
""").replace('⟦MARCA⟧', MARCA)


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


def _acciones_local(c: dict, ses: dict | None) -> str:
    """"Escribir al local" (mensajería web) y "Bodega del local" (pedir a la
    cancha), como en `club_detalle` del app: solo en locales verificados con
    dueño y nunca al propio dueño."""
    dueno = (c.get("dueno") or "").strip().lower()
    yo = ((ses or {}).get("email") or "").strip().lower()
    if not datos.reservable(c) or not dueno or dueno == yo:
        return ""
    cid = quote(c["id"], safe="")
    # "Bodega del local" solo si el dueño la abrió a pedidos (si no, el botón
    # llevaba a una pantalla que decía "este local no recibe pedidos").
    try:
        from web import bodega_datos
        con_bodega = bool(bodega_datos.config_de(dueno).get("acepta_pedidos"))
    except Exception:  # noqa: BLE001
        con_bodega = False
    return ("<div class='acciones acc-local'>"
            f"<a class='btn sec' href='/mensajes/nuevo?cancha={cid}'>💬 Escribir al local</a>"
            + (f"<a class='btn sec' href='/bodega/{cid}/pedir'>🧃 Bodega del local</a>" if con_bodega else "")
            + "</div>")


def _ficha(c: dict, sim: str, pais: str, verificada: bool = True, hermanas: list[dict] | None = None,
          ses: dict | None = None) -> str:
    """Cabecera de la ficha pública: como `club_detalle_screen` del app, el
    TÍTULO es el LOCAL y la cancha va debajo (antes salía "Cancha-01" grande
    y el local chico; queja del director, sep-2026). Con varias canchas en el
    local, chips para cambiar de cancha."""
    sello = ui.sello_verificada() if verificada else "<span class='pill gris'>Aún sin verificar</span>"
    lugar = ui.unir_lugar(ui.direccion_legible(c.get("direccion") or ""), _zona(c))
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
            f"<div class='precio' style='font-size:22px;white-space:nowrap'>{e(sim)} {horarios.precio_publico(c)[0]:.2f} <small>{e(horarios.precio_publico(c)[1])}</small></div></div>"
            "<ul class='datos'>"
            f"<li>📍 <span>{e(lugar or 'Dirección en la app')} · <a href='#mapaFicha' id='btnLlegar' data-lat='{c.get('lat')}' data-lng='{c.get('lng')}' data-nombre='{e(local)}'>Cómo llegar</a></span></li>"
            f"<li>🕒 <span>{e(c['hora_apertura'])} a {e(c['hora_cierre'])} · turnos de {c['duracion_slot_min']} min · último turno {e(c['hora_cierre'])}</span></li>"
            + (f"<li>⚡ <span>Hora feliz −{c['descuento_valle']} % de {e(c['valle_desde'] or '00:00')} a {e(c['valle_hasta'] or '12:00')}</span></li>" if c['descuento_valle'] > 0 else "")
            + (f"<li>🏟️ <span>{e(c['superficie'])}</span></li>" if c.get("superficie") else "")
            + "</ul>"
            + _acciones_local(c, ses) +
            "<div class='mapa-ficha' id='mapaFicha'><div class='mapa' id='mapaFichaMapa' aria-label='Mapa de la cancha'></div>"
            f"<div class='pie-mapa'><span>📍 {e(lugar or local)}</span><a href='{_maps(c)}' target='_blank' rel='noopener'>Abrir en Google Maps</a>"
            f"<a href='https://www.google.com/maps/dir/?api=1&destination={c.get('lat')},{c.get('lng')}' target='_blank' rel='noopener'>Indicaciones paso a paso</a></div></div>"
            + (f"<div class='amen'>{amen}</div>" if amen else ""))


_DIA_NOMBRE = {"lun": "Lunes", "mar": "Martes", "mie": "Miércoles", "jue": "Jueves", "vie": "Viernes",
               "sab": "Sábado", "dom": "Domingo"}
_MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")


def _num_txt(v) -> str:
    v = float(v or 0)
    return str(int(v)) if v == int(v) else f"{v:g}"


def _rango_dias(dias: list[str]) -> str:
    orden = list(_DIA_NOMBRE)
    if len(dias) == 7:
        return "todos los días"
    idx = sorted(orden.index(d) for d in dias if d in orden)
    if idx and idx == list(range(idx[0], idx[-1] + 1)) and len(idx) > 2:
        return f"{_DIA_NOMBRE[orden[idx[0]]].lower()} a {_DIA_NOMBRE[orden[idx[-1]]].lower()}"
    return ", ".join(_DIA_NOMBRE[orden[i]].lower()[:3] for i in idx)


def _ayuda_turnos(c: dict) -> str:
    """'Hasta N turnos por pedido…' con los límites del CLUB (no el 4 fijo)."""
    pol = _reglas.de_cancha(c)
    mx = min(MAX_SLOTS, int(pol.get("max_turnos") or MAX_SLOTS))
    mn = int(pol.get("min_turnos") or 0)
    rango = f"Entre {mn} y {mx} turnos seguidos" if mn > 1 else f"Hasta {mx} turno{'s' if mx != 1 else ''}"
    return f"{rango} por pedido. Toca un horario para agregarlo; vuelve a tocarlo para quitarlo."


def _resenas_ficha(hermanas: list[dict]) -> str:
    from web import jugador_resenas as _jr
    html = _jr.seccion_ficha([h["id"] for h in hermanas])
    return f"<style>{_jr.CSS}</style>{html}" if html else ""


def _politica_html(c: dict, sim: str) -> str:
    """POLÍTICA DEL CLUB en la ficha (lo que el jugador debe saber ANTES de
    pagar): cancelación con las horas del club, horarios especiales, cierres,
    franjas, luz, anticipación y límites. Sin reglas, solo la cancelación."""
    pol = _reglas.resumen_publico(c)
    items = []
    horas = _dev.horas_minimas(c)
    items.append(("↩️", f"Cancela con más de {_num_txt(horas)} h de anticipación y te devolvemos el 100 %."))
    for ci in pol.get("cierres") or []:
        try:
            d = date.fromisoformat(ci["fecha"])
            f = f"{d.day} {_MESES_CORTOS[d.month - 1]}"
        except ValueError:
            continue
        items.append(("🚫", f"Cerrado el {f}" + (f" · {e(ci['motivo'])}" if ci.get("motivo") else "")))
    semana = pol.get("horario_semana") or {}
    for d, v in semana.items():
        if d in _DIA_NOMBRE:
            items.append(("🗓️", f"{_DIA_NOMBRE[d]}: " + ("cerrado" if not v else f"{v['apertura']} a {v['cierre']}")))
    for fr in pol.get("franjas") or []:
        precio = (f"{sim} {fr['precio_turno']:.2f} por turno" if fr.get("precio_turno")
                  else f"{sim} {fr['precio_hora']:.2f} por hora")
        items.append(("⭐", f"{e(fr.get('nombre') or 'Tarifa especial')}: {_rango_dias(fr.get('dias') or [])}, "
                            f"{fr['desde']} a {fr['hasta']} · {precio}"))
    rl = pol.get("recargo_luz")
    if rl:
        items.append(("💡", f"Desde las {rl['desde']} cada turno suma {sim} {float(rl['monto']):.2f} de iluminación."))
    if pol.get("anticipacion_min_horas"):
        items.append(("⏱️", f"Reserva con al menos {_num_txt(pol['anticipacion_min_horas'])} h de anticipación."))
    if pol.get("anticipacion_max_dias"):
        items.append(("📆", f"Puedes reservar hasta {_num_txt(pol['anticipacion_max_dias'])} días antes."))
    mn, mx = pol.get("min_turnos"), pol.get("max_turnos")
    if mn and mx:
        items.append(("🔢", f"Entre {mn} y {mx} turnos seguidos por reserva."))
    elif mn:
        items.append(("🔢", f"Mínimo {mn} turnos seguidos por reserva."))
    elif mx:
        items.append(("🔢", f"Máximo {mx} turnos seguidos por reserva."))
    if pol.get("max_reservas_dia_jugador"):
        n = pol["max_reservas_dia_jugador"]
        items.append(("👤", f"Hasta {n} reserva{'s' if n != 1 else ''} por día por jugador."))
    lis = "".join(f"<li><span aria-hidden='true'>{i}</span><span>{t}</span></li>" for i, t in items)
    return (f"<details class='politica' id='politica'{' open' if len(items) > 1 else ''}>"
            "<summary>Política del club</summary>"
            f"<ul>{lis}</ul><a href='/legal/devoluciones'>Cómo funcionan las devoluciones</a></details>")


def _jsonld_cancha(c: dict, sim: str) -> str:
    return ui.json_js({
        "@context": "https://schema.org", "@type": "SportsActivityLocation",
        "name": (f"{c['club']} · {c['nombre']}" if (c.get("club") or "").strip() else c["nombre"]), "image": _fotos(c)[:1],
        "address": {"@type": "PostalAddress", "streetAddress": c.get("direccion") or "",
                    "addressLocality": _zona(c), "addressCountry": _pais_de(c)},
        "geo": {"@type": "GeoCoordinates", "latitude": c.get("lat"), "longitude": c.get("lng")},
        "priceRange": f"{sim} {horarios.precio_publico(c)[0]:.2f} {horarios.precio_publico(c)[1]}",
        "url": f"{config.PUBLIC_BASE_URL.rstrip('/')}/reservar/{c['id']}" if getattr(config, 'PUBLIC_BASE_URL', '') else "",
    }, ensure_ascii=False)


@router.get("/lugar/{lugar_id}", response_class=HTMLResponse)
def pagina_lugar(request: Request, lugar_id: str, nombre: str = "", direccion: str = "", lat: float = 0.0, lng: float = 0.0, deporte: str = "") -> HTMLResponse:
    """Ficha de un lugar DESCUBIERTO en Google que aún no está en Pichangol
    (antes la tarjeta mandaba a Play y no había dónde reclamarlo): fotos del
    lugar, cómo llegar, "Reservar en la app" y, en grande, "¿Es tuya?
    Reclámala" → registro web prellenado. Si el lugar ya fue registrado, va a
    su ficha real."""
    es_osm = lugar_id.startswith("osm_")
    if not (lugar_id.startswith("gp_") or es_osm) or not nombre.strip() or not (lat or lng):
        r = _no_encontrada("Lugar no disponible"); r.status_code = 404
        return r
    ses = sesion.de_request(request)
    nombre = re.sub(r"\s+", " ", nombre).strip()[:120]
    direccion = ui.direccion_legible(re.sub(r"\s+", " ", direccion).strip()[:200])
    dep = deporte if deporte in DEPORTES else ""
    c = {"id": lugar_id, "nombre": nombre, "club": "", "direccion": direccion, "lat": lat, "lng": lng, "deporte": dep or "futbol", "fotos": [], "foto_url": ""}
    pais = _pais_de(c)
    q = f"place={quote(lugar_id, safe='')}&nombre={quote(nombre)}&direccion={quote(direccion)}&lat={lat}&lng={lng}&deporte={quote(dep)}"
    cuerpo = (
        f"<div style='padding-top:22px'>{_galeria(c)}"
        "<div style='display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-top:16px'>"
        f"<div><div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><span class='pill gris'>{ui.bandera(pais)} {e(_deporte(dep)[0]) if dep else 'Cancha'}</span>"
        "<span class='pill gris'>Aún sin registrar</span></div>"
        f"<h1 style='margin-top:8px'>{e(nombre)}</h1><p class='sub'>{e(direccion) or ('Lugar del mapa de OpenStreetMap' if es_osm else 'Lugar encontrado en Google Maps')}</p></div></div>"
        "<ul class='datos'>"
        f"<li>📍 <span>{e(direccion or nombre)} · <a href='{_maps(c)}' target='_blank' rel='noopener'>Abrir en Google Maps</a> · "
        f"<a href='https://www.google.com/maps/dir/?api=1&destination={lat},{lng}' target='_blank' rel='noopener'>Indicaciones</a></span></li>"
        f"<li>🕒 <span>Horarios y precios aún no publicados: este local todavía no está en {MARCA}.</span></li></ul>"
        + (f"<p class='osm-atrib' style='font-size:12px;color:#717171;margin-top:8px'>Datos del lugar: "
           f"<a href='{osm.ATRIBUCION_URL}' target='_blank' rel='noopener'>© colaboradores de OpenStreetMap</a></p>" if es_osm else "")
        + "</div>"
        "<div class='panel' style='margin-top:20px;border:1px solid var(--verde)'><h2>¿Es tuya esta cancha?</h2>"
        f"<p class='sub'>Publícala en {MARCA} en 5 minutos: horarios, precios y fotos. Confirmamos que eres el dueño y empiezas a recibir reservas y pagos en línea.</p>"
        f"<div class='acciones'><a class='btn' href='/anfitrion/nueva?{q}'>🏷️ Reclámala y recibe reservas</a></div></div>"
        "<div class='panel' style='margin-top:16px'><h2>¿Quieres jugar aquí?</h2>"
        f"<p class='sub'>Este local aún no acepta reservas en {MARCA}. Desde la app puedes guardarlo, ver cómo llegar y avisarle al local que lo estás buscando.</p>"
        f"<div class='acciones'><a class='btn sec' href='{PLAY_URL}' rel='noopener'>📲 Abrir en la app</a><a class='btn sec' href='/canchas'>Ver canchas disponibles</a></div></div>")
    return ui.shell(nombre, cuerpo, desc=f"{nombre} · {direccion}", sesion=ses, titulo_tab=f"{nombre} · {MARCA}")


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
    ficha = _ficha(c, sim, pais, verificada=datos.reservable(c), hermanas=hermanas, ses=ses)
    titulo = _titulo_local(c)
    canonical = (f"{config.PUBLIC_BASE_URL.rstrip('/')}/reservar/{c['id']}"
                 if getattr(config, "PUBLIC_BASE_URL", "") else "")
    og = _fotos(c)[0] if _fotos(c) else "/marca/logo-og.png"

    # Un club con COBRO DIRECTO (sus medios) cobra en la web aunque la plataforma no tenga pasarela en esa moneda.
    if not datos.reservable(c) or not (_pago_web_disponible(iso) or _cd.checkout(c, iso).get("directo")):
        if not datos.reservable(c):
            motivo = (f"Este local todavía está en proceso de verificación con {MARCA}. Desde la app puedes "
                      "reservar y pagar en la cancha, y te avisamos cuando acepte pagos en línea.")
        else:
            motivo = (f"El pago en línea en {e(sim)} desde la web se está habilitando." if iso != "PEN"
                      else "El pago en línea desde la web se está habilitando.")
        reclamar = ""
        if not datos.reservable(c) and not (c.get("dueno") or "").strip():
            reclamar = ("<div class='panel' style='margin-top:16px;border:1px solid var(--verde)'><h2>¿Es tuya esta cancha?</h2>"
                        "<p class='sub'>Nadie la administra todavía. Reclámala, confirmamos que eres el dueño y empiezas a recibir reservas y pagos en línea.</p>"
                        f"<div class='acciones'><a class='btn' href='/anfitrion/nueva?cancha={quote(c['id'], safe='')}'>🏷️ Reclamar esta cancha</a></div></div>")
        cuerpo = (f"<div style='padding-top:22px'>{ficha}</div>"
                  f"<div class='panel' style='margin-top:20px'><h2>Reserva desde la app</h2>"
                  f"<p class='sub'>{motivo} En la app {MARCA} reservas y pagas con los medios de tu país.</p>"
                  f"<div class='acciones'><a class='btn' href='{PLAY_URL}'>Abrir {MARCA} en Google Play</a>"
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
        filas += (f"<label class='extra'>"
                  f"<input type='checkbox' name='extra' value='{precio:.2f}' data-clave='{e(clave)}' data-nombre='{e(nombre)}' data-tipo='{e(tipo)}'>"
                  f"<span class='ex-n'>{s['emoji']} {e(nombre)}</span><small>+ {e(sim)} {precio:.2f}{sufijo}</small>{cant}</label>")
    if filas:
        extras_html = f"<div class='paso'><span>3</span> Servicios extra <small style='color:var(--tenue);font-weight:600'>(opcional)</small></div>{filas}"
    # BOLEADOR / SPARRING (sep-2026): solo canchas de tenis/pádel cuyo local lo
    # permite; la lista se pide al elegir el horario (depende de fecha y hora).
    import boleadores as _bol
    con_bol = (_bol.activo() and any(d in _bol.DEPORTES for d in _deportes_de(c)) and datos.permite_boleadores(c["id"]))
    nombre_bol = _bol.nombre_por_pais(pais)
    if con_bol:
        extras_html += (f"<div class='paso'><span>{'4' if filas else '3'}</span> 🎾 ¿Quieres un {nombre_bol.lower()}? "
                        "<small style='color:var(--tenue);font-weight:600'>(opcional)</small></div>"
                        f"<div class='sub' style='margin:-4px 0 10px;font-size:13px'>Jugadores de la Liga {MARCA} que pelotean contigo en este local. "
                        f"Eliges por categoría y precio por turno; el {nombre_bol.lower()} confirma y, si no puede, te devolvemos su parte.</div>"
                        "<div id='bolBox' class='bol-box'><span class='sub'>Elige un horario para ver quién puede atenderte.</span></div>")

    # TARJETA DE FIDELIDAD del local (sep-2026): progreso y premio del jugador
    # con sesión; el JS la pinta con `/web/fidelidad` y aplica el premio en el
    # resumen. Sin sesión, solo explica la promo.
    import fidelidad as _fid
    fid_cfg = _fid.publico_config(c) if _fid.activa_en(c) else None
    if fid_cfg:
        extras_html = ("<div id='fidBox' class='fid-box'><b>🎁 Tarjeta de fidelidad de "
                       f"{e(_titulo_local(c))}</b><div class='sub' style='margin:2px 0 0'>Cada {fid_cfg['meta']} reservas pagadas, "
                       f"{e(fid_cfg['nombrePremio'])}. Inicia sesión para ver tu progreso.</div></div>") + extras_html
    # BONO DE HORAS y PUNTOS (como el app): la caja se llena con
    # `/web/beneficios` para el jugador con sesión; sin nada que ofrecer, oculta.
    con_ben = sesion.activo() and beneficios.disponible()
    if con_ben:
        extras_html = "<div id='benBox' class='fid-box ben-box' style='display:none'></div>" + extras_html
    # COBRO DIRECTO (el dinero va a la cuenta DEL CLUB): con su Culqi el
    # checkout se abre con la llave pública DEL CLUB (el servidor cobra con su
    # llave secreta); con medios manuales el jugador sube su comprobante. Sin
    # cargo por servicio ni puntos (no hay de dónde compensarlos al club).
    dir_info = _cd.checkout(c, iso)
    directo = dir_info if dir_info.get("directo") else None
    if directo:
        pasarela = "culqi" if directo.get("culqi_public_key") else "directo"
        pk_ficha = directo.get("culqi_public_key") or ""
    else:
        pasarela = _pasarela_web(iso)
        pk_ficha = config.CULQI_PUBLIC_KEY if pasarela == "culqi" else ""
    cfg = ui.json_js({"id": c["id"], "moneda": sim, "pk": pk_ficha,
                      "maxSlots": min(MAX_SLOTS, int(_reglas.de_cancha(c).get("max_turnos") or MAX_SLOTS)),
                      "minSlots": int(_reglas.de_cancha(c).get("min_turnos") or 0),
                      "directo": ({"culqi": bool(directo.get("culqi_public_key")), "medios": directo.get("medios") or [],
                                   "plazo": int(directo.get("voucher_plazo_min") or 0)} if directo else None),
                      # Pasarela del checkout: 'culqi' (soles, en la página) o la HOSPEDADA del país
                      # ($ / Bs: se va a pagar a su página y vuelve a /web/pago/{orden}).
                      "pasarela": pasarela, "pasarelaNombre": ("" if pasarela == "culqi" else pago_hospedado.nombre_pasarela(pasarela)),
                      "boleadores": con_bol, "nombreBoleador": nombre_bol, "fidelidad": dict(fid_cfg, local=_titulo_local(c)) if fid_cfg else None, "beneficios": con_ben,
                      "logo": "", "hoy": dias[0]["iso"], "dias": dias, "etiquetas": etiquetas,
                      # Cargo por servicio (fase 2): con el flag apagado el JS no cotiza ni pinta la línea.
                      "cargo": _cs.activo("reservas") and not directo, "deporteBase": (_deportes_de(c) or [""])[0],
                      # SEÑA que configuró el dueño (% del precio de los turnos), como el app.
                      "senaPct": int(c.get("sena_pct") or 0),
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
            f"<div><label for='celular'>Celular</label><input id='celular' inputmode='tel' autocomplete='tel' maxlength='20' placeholder='9 dígitos' value='{e(datos.celular_de_perfil(ses['email']) if ses else '')}'></div></div>"
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
        "<div class='strip-wrap'><button type='button' class='strip-fl izq' aria-label='Días anteriores' hidden>‹</button>"
        "<div class='strip' id='dias'></div>"
        "<button type='button' class='strip-fl der' aria-label='Más días'>›</button></div>"
        f"{selector_dep}"
        f"<div class='sub' id='ayudaTurnos' style='margin:6px 0 12px;font-size:13px'>{_ayuda_turnos(c)}</div>"
        "<div id='slots'></div>"
        f"{_politica_html(c, sim)}"
        f"{_resenas_ficha(hermanas)}"
        f"{paso_datos}"
        f"{extras_html}"
        "<div class='estado bad' id='err'></div>"
        "</div>"
        "<aside class='resumen'><div class='panel'>"
        "<h3>Resumen de tu reserva</h3>"
        f"<div class='sub' style='margin-bottom:10px'>{e(c['nombre'])}{(' · ' + e(c.get('club'))) if c.get('club') else ''}</div>"
        "<div id='lineas'></div>"
        "<div class='total'><span id='totLbl'>Total</span><span id='tot'></span></div>"
        f"<div style='margin-top:14px'>{ui.selector_medio_directo(directo) if directo else (ui.selector_medio_pago() if pasarela == 'culqi' else pago_hospedado.selector(pasarela))}</div>"
        + _dividir_web.bloque_ficha(c, directo, sim, ses) +
        "<div style='margin-top:14px'><button class='btn lg' id='btnPagar' disabled>Elige un horario</button></div>"
        "<div class='sub' style='font-size:12.5px;margin-top:12px'>"
        + ("El club confirma tu pago y la reserva aparece en su agenda." if directo else "Reserva confirmada al instante; el local la ve en su agenda.")
        + f" Cancelación con más de {_num_txt(_dev.horas_minimas(c))} h de anticipación: devolución del 100 %. <a href='#politica'>Ver política del club</a>.</div>"
        "</div></aside></div>"
        "<div class='barra-fija'><div><div class='sub' style='font-size:12px;margin:0' id='totBarraLbl'>Total</div><div class='t' id='totBarra'></div></div>"
        f"{ui.medio_pago_mini('voucher' if pasarela == 'directo' else pasarela)}<button class='btn' id='btnPagarBarra' disabled>Elige un horario</button></div>"
        f"<script>window.__cancha={cfg};var CORREO_SOPORTE={ui.json_js(empresa.valores()['empresa_correo'])};</script>"
        + ("<script src='https://checkout.culqi.com/js/v4'></script>" if pasarela == "culqi" else "")
        + f"<script>{sesion.JS_SESION if sesion.activo() else ''}{_JS_RESERVA}</script>")
    return ui.shell(f"Reservar en {titulo}", cuerpo, con_barra=True, canonical=canonical, og_image=og,
                    desc=(f"Reserva {c['nombre']} y paga en línea con Yape o tarjeta." if pasarela == "culqi"
                          else f"Reserva {c['nombre']} y paga en línea con {pago_hospedado.nombre_pasarela(pasarela)}."),
                    jsonld=_jsonld_cancha(c, sim),
                    # Leaflet DIFERIDO: en la ficha el mapa solo se dibuja al tocar "Cómo llegar"
                    # (no bloquea la primera pintura). SRI = el archivo de unpkg no puede cambiar.
                    extra_head=("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' "
                                "integrity='sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=' crossorigin=''>"
                                "<script defer src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' "
                                "integrity='sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=' crossorigin=''></script>"
                                + (sesion.GIS_SCRIPT if (sesion.activo() and not ses) else "")), sesion=ses)
