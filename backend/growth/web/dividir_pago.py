"""CADA UNO PAGA SU PARTE en la web (ronda 3, oct-2026). La plata y las reglas
viven en `pagos/division.py`; aquí van las páginas y los endpoints JSON:

- Ficha `/reservar/{id}`: `bloque_ficha` (¿dividen el pago? chips 2…12 con lo
  que paga cada uno). Con N elegido, `/web/asegurar` aparta y devuelve el
  enlace; el navegador va a `/dividir/{token}`.
- `GET /dividir/{token}`: la página del enlace (login con Google): resumen de la
  reserva, "3 de 6 pagaron" en vivo, partes, plazo y "Pagar mi parte" con los
  medios DEL CLUB (su Culqi o comprobante). El organizador ve además
  "Compartir por WhatsApp", "Pagar lo que falta" y "Cancelar".
- `GET /web/dividir/{token}/estado` (sondeo), `POST …/tomar | soltar | pagar |
  voucher | cancelar`.
- Mis reservas: `seccion_mis_reservas` (pagos divididos donde organizo o pagué;
  a los amigos les sale "Jugada con <organizador>").
- Club: `/anfitrion/cobros-club/devoluciones` (partes que debe devolver a mano)
  y `aviso_devoluciones` en Pagos por confirmar.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import config
from pagos import division as dv
from web import datos, horarios, sesion, ui
from web.ui import e

router = APIRouter(tags=["web-dividir-pago"])

es_ref = dv.es_ref


def _wr():
    from web import router as wr
    return wr


def _sim(iso: str) -> str:
    from paises import simbolo_de_moneda
    return simbolo_de_moneda(iso)


def _plata(centimos: int, iso: str) -> str:
    return ui.monto(int(centimos or 0) / 100.0, _sim(iso))


# ── ficha: ¿dividen el pago? ─────────────────────────────────────────────────

_CSS_FICHA = (".div-box{margin-top:14px;border:1px solid var(--trazo);border-radius:16px;padding:12px 14px;background:var(--blanco)}"
              ".div-box .dv-t{font-weight:800;font-size:14px}.div-box .chips{gap:8px;margin-top:8px}"
              ".div-box .chip{padding:8px 12px;font-size:13px}.div-box .dv-r{font-size:13px;margin:8px 0 0;color:var(--tenue)}"
              ".div-box .dv-r b{color:var(--noche)}")

_JS_FICHA = r"""
(function(){
  var B = document.getElementById('divBox'); if(!B) return;
  var N = 0, MIN = +B.dataset.min || 300, MON = B.dataset.mon || '';
  function fmt(c){ return MON + ' ' + (c / 100).toFixed(2); }
  window.pcgDividirN = function(){ return N > 1 ? N : 0; };
  window.pcgDividirPinta = function(tt, n, f){
    var total = Math.round((tt || 0) * 100), max = Math.min(12, Math.floor(total / MIN));
    var bloq = f && (f.sena || f.bono || f.puntos || f.fid || f.bol);
    var nota = document.getElementById('divNota');
    if(!n || max < 2 || bloq){
      N = 0; B.hidden = !(n && bloq);
      if(n && bloq && nota) nota.innerHTML = f.sena ? 'Para dividir el pago elige <b>Pagar todo ahora</b>.' : 'El pago dividido no se combina con bono, puntos, premio de fidelidad ni boleador.';
      var ch = document.getElementById('divChips'); if(ch) ch.innerHTML = '';
      return false;
    }
    B.hidden = false; if(N > max) N = 0;
    var h = "<button type='button' class='chip" + (N ? '' : ' sel') + "' data-div='0' aria-pressed='" + (!N) + "'>Pago yo todo</button>";
    for(var i = 2; i <= max; i++) h += "<button type='button' class='chip" + (N === i ? ' sel' : '') + "' data-div='" + i + "' aria-pressed='" + (N === i) + "' aria-label='Dividir entre " + i + " personas'>÷ " + i + "</button>";
    document.getElementById('divChips').innerHTML = h;
    if(N > 1){
      var base = Math.floor(total / N), org = total - base * (N - 1);
      nota.innerHTML = 'Tú pagas <b>' + fmt(org) + '</b> y cada amigo <b>' + fmt(base) + '</b>, directo al club. Te damos un enlace para compartir; tienen hasta <b>' + B.dataset.horas + '</b> para pagar (y nunca después de ' + B.dataset.margen + ' antes del turno).';
    } else nota.innerHTML = 'Elige entre cuántas personas (tú incluido) se divide. Cada uno paga su parte con su propia cuenta.';
    return N > 1;
  };
  B.addEventListener('click', function(ev){
    var b = ev.target.closest('[data-div]'); if(!b) return;
    N = +b.dataset.div || 0; document.dispatchEvent(new Event('pcg-dividir'));
  });
})();
"""


def _horas_txt() -> str:
    h = dv.horas_plazo()
    return f"{int(h)} h" if float(h).is_integer() else f"{int(h * 60)} min"


def _margen_txt() -> str:
    m = int(dv.margen_min())
    return f"{m // 60} h" if m and m % 60 == 0 else f"{m} min"


def bloque_ficha(c: dict, directo: dict | None, sim: str, ses: dict | None) -> str:
    """Selector "¿Dividen el pago?" de la ficha (solo clubes con cobro directo
    y con las tablas de la migración 0006). '' si no aplica."""
    if not directo or not dv.disponible():
        return ""
    return (f"<div class='div-box' id='divBox' hidden data-min='{dv.MIN_PARTE_CENTIMOS}' data-mon='{e(sim)}' "
            f"data-horas='{e(_horas_txt())}' data-margen='{e(_margen_txt())}' role='group' aria-labelledby='divTit'>"
            "<div class='dv-t' id='divTit'>👥 ¿Dividen el pago entre amigos?</div>"
            "<div class='chips' id='divChips'></div><p class='dv-r' id='divNota' aria-live='polite'></p></div>"
            f"<style>{_CSS_FICHA}</style><script>{_JS_FICHA}</script>")


# ── página del enlace ────────────────────────────────────────────────────────

def _div_o_404(token: str) -> dict | None:
    if not token or len(token) > 64 or not dv.disponible():
        return None
    try:
        return dv.repo().por_token(token)
    except Exception:  # noqa: BLE001
        return None


def _base(request: Request) -> str:
    return (config.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")


def _estado_json(div: dict, email: str) -> dict:
    v = dv.vista(div, email)
    if v["estado"] == "confirmada" and v["organizador"]:
        v["comprobante"] = f"/reserva/{quote(div['reserva_ref'], safe='')}"
    return v


_CSS_PAG = """
.dv-wrap{max-width:720px;margin:0 auto;padding:22px 0 40px;display:grid;gap:16px}
.dv-wrap .panel h1{font-size:22px;margin:0 0 4px}
.dv-k{font-size:12px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:var(--esmeralda)}
.dv-res{display:grid;gap:4px;margin-top:8px;font-size:14px}.dv-res b{font-weight:800}
.dv-prog{margin-top:14px}.dv-prog .dv-num{font-size:20px;font-weight:800}
.dv-barra{height:10px;border-radius:999px;background:var(--gris);overflow:hidden;margin-top:8px}
.dv-barra i{display:block;height:100%;background:var(--esmeralda);border-radius:999px;transition:width .4s}
.dv-reloj{font-size:13px;margin-top:8px;color:var(--tenue)}.dv-reloj b{color:var(--noche)}
.dv-partes{display:grid;gap:8px;margin-top:6px}
.dv-p{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--trazo);border-radius:14px;min-width:0}
.dv-p .av{flex:none;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;background:var(--tinte);color:var(--teal)}
.dv-p .q{flex:1;min-width:0}.dv-p .q b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dv-p .q small{color:var(--tenue)}.dv-p .m{font-weight:800;white-space:nowrap}
.dv-p.yo{border-color:var(--esmeralda)}
.dv-acc{display:grid;gap:10px;margin-top:14px}
.dv-link{display:flex;gap:8px;align-items:center;margin-top:10px;min-width:0}
.dv-link input{flex:1;min-width:0;font-size:13px}
.dv-link .btn{flex:none;padding:10px 14px}
.dv-wa{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.dv-wrap .medio-pago{margin-top:4px}
"""

_JS_PAG = r"""
(function(){
  var C = window.__div, T = C.token, S = C.estado, ocupado = false;
  var $ = function(id){ return document.getElementById(id); };
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(ch){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]; }); }
  function fmt(c){ return C.moneda + ' ' + (c / 100).toFixed(2); }
  function post(ruta, cuerpo){
    return fetch('/web/dividir/' + encodeURIComponent(T) + '/' + ruta, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo || {})})
      .then(function(r){ return r.json(); });
  }
  var ESTADO = {libre: ['Sin pagar', 'gris'], cobrando: ['Pagando…', 'warn'], en_revision: ['Comprobante en revisión', 'warn'], pagada: ['Pagada ✓', 'ok'],
                devolver: ['Por devolver', 'warn'], reembolsada: ['Devuelta', 'ok'], devuelta: ['Devuelta', 'ok'], no_recibido: ['Sin pago', 'gris']};
  function mias(){ return S.partes.filter(function(p){ return p.mia; }); }
  function render(){
    var pct = S.n ? Math.round(100 * S.pagadas / S.n) : 0;
    $('dvNum').textContent = S.pagadas + ' de ' + S.n + ' pagaron';
    $('dvBarra').style.width = pct + '%';
    $('dvBarra').parentNode.setAttribute('aria-valuenow', String(S.pagadas));
    $('dvRev').textContent = S.en_revision ? (S.en_revision + (S.en_revision === 1 ? ' comprobante' : ' comprobantes') + ' en revisión del club (cuentan cuando el club los apruebe).') : '';
    $('dvPartes').innerHTML = S.partes.map(function(p){
      var est = ESTADO[p.estado] || [p.estado, 'gris'];
      var quien = p.quien ? esc(p.quien) : (p.organizador ? esc(S.organizador_nombre) : 'Libre');
      var sub = p.organizador ? 'Organizador' + (p.estado === 'libre' ? '' : '') : (p.por_organizador ? 'Cubierta por el organizador' : 'Parte ' + (p.n + 1));
      return "<div class='dv-p" + (p.mia ? ' yo' : '') + "'><span class='av' aria-hidden='true'>" + esc((p.quien || (p.organizador ? S.organizador_nombre : '?')).charAt(0).toUpperCase() || '?') + "</span>"
        + "<div class='q'><b>" + quien + "</b><small>" + sub + "</small></div><span class='pill " + est[1] + "'>" + est[0] + "</span><span class='m'>" + fmt(p.monto_centimos) + "</span></div>";
    }).join('');
    var acc = '', mis = mias(), yaPague = mis.some(function(p){ return p.estado === 'pagada'; }), enRev = mis.some(function(p){ return p.estado === 'en_revision'; });
    var libres = S.partes.filter(function(p){ return p.estado === 'libre'; });
    var mia0 = S.partes[0];
    if(S.estado === 'abierta'){
      if(S.organizador){
        if(mia0.estado === 'libre' || (mia0.estado === 'cobrando' && mia0.mia)) acc += "<button type='button' class='btn lg' data-pagar='mia'>Pagar mi parte · " + fmt(mia0.monto_centimos) + "</button>";
        if(libres.length && (libres.length > 1 || libres[0].n !== 0)) acc += "<button type='button' class='btn sec' data-pagar='falta'>Pagar lo que falta · " + fmt(S.falta_centimos) + " (" + libres.length + (libres.length === 1 ? ' parte' : ' partes') + ")</button>";
      } else if(!yaPague && !enRev){
        var libreAmigo = libres.filter(function(p){ return p.n !== 0; })[0];
        if(libreAmigo || mis.some(function(p){ return p.estado === 'cobrando'; })) acc += "<button type='button' class='btn lg' data-pagar='mia'>Pagar mi parte · " + fmt(C.parte) + "</button>";
        else acc += "<div class='aviso warn'>Ya se tomaron todas las partes. Si alguien no paga a tiempo, vuelve a quedar libre aquí.</div>";
      }
      if(enRev) acc += "<div class='aviso warn'>🧾 Tu comprobante está en revisión del club. Tu parte cuenta como pagada cuando lo apruebe.</div>";
      if(yaPague && !S.organizador) acc += "<div class='aviso ok'>✅ Pagaste tu parte. Te avisamos cuando todos paguen y la reserva quede confirmada.</div>";
      if(acc.indexOf('data-pagar') >= 0) acc = C.puede ? C.selector + acc : "<div class='aviso warn'>Este club no está recibiendo pagos ahora. Escríbele al local.</div>";
      if(S.organizador) acc += "<button type='button' class='btn sec' data-cancelar='1'>Cancelar y liberar el horario</button>";
    } else if(S.estado === 'confirmada' || S.estado === 'completa'){
      acc = "<div class='aviso ok'>✅ ¡Todos pagaron! La reserva quedó confirmada en la agenda del club.</div>"
          + (S.comprobante ? "<a class='btn lg' href='" + esc(S.comprobante) + "'>Ver mi comprobante</a>" : '');
    } else {
      var dev = mis.filter(function(p){ return ['reembolsada', 'devolver', 'devuelta'].indexOf(p.estado) >= 0; });
      acc = "<div class='aviso bad'>" + (S.estado === 'cancelada' ? 'El organizador canceló el pago dividido' : 'No se juntaron todas las partes a tiempo') + " y el horario se liberó.</div>";
      if(dev.length) acc += "<div class='aviso warn'>" + (dev.every(function(p){ return p.estado === 'reembolsada'; }) ? 'Te devolvimos tu parte al mismo medio de pago (3 a 7 días hábiles).'
                                                       : dev.every(function(p){ return p.estado === 'devuelta'; }) ? 'El club marcó tu parte como devuelta.' : 'El club te devolverá lo que pagaste; te avisamos.') + "</div>";
    }
    $('dvAcc').innerHTML = acc;
    $('dvCompartir').hidden = !(S.organizador && S.estado === 'abierta');
    tic();
  }
  var fin = Date.now() + (S.segundos || 0) * 1000;
  function tic(){
    var el = $('dvReloj'); if(!el) return;
    if(S.estado !== 'abierta'){ el.textContent = ''; return; }
    var r = Math.max(0, Math.round((fin - Date.now()) / 1000)), h = Math.floor(r / 3600), m = Math.floor((r % 3600) / 60), s = r % 60;
    el.innerHTML = '⏳ El horario está apartado por <b>' + (h ? h + ' h ' : '') + m + ' min ' + ('0' + s).slice(-2) + ' s</b> más. Si no pagan todos, se libera y se devuelve lo pagado.';
  }
  setInterval(tic, 1000);
  function refrescar(forzar){
    if(document.hidden && !forzar) return;
    fetch('/web/dividir/' + encodeURIComponent(T) + '/estado').then(function(r){ return r.json(); }).then(function(j){
      if(!j || !j.ok) return;
      var cambio = j.version !== S.version || j.estado !== S.estado;
      S = j; fin = Date.now() + (j.segundos || 0) * 1000;
      if(cambio && !ocupado) render();
    }).catch(function(){});
  }
  setInterval(refrescar, 5000);
  document.addEventListener('visibilitychange', function(){ if(!document.hidden) refrescar(true); });

  // ── pagar ──
  var ERR = {cerrada: 'Este pago dividido ya se cerró.', sin_partes: 'Ya se tomaron todas las partes. Si alguien no paga a tiempo, vuelve a quedar libre.',
             ya_pagaste: 'Ya tienes tu parte de esta reserva.', no_tomada: 'Tu parte ya no estaba reservada para ti. Vuelve a intentarlo.',
             sesion_requerida: 'Tu sesión venció. Vuelve a iniciar sesión.', medio_no_disponible: 'Elige el medio con el que pagaste.',
             operacion_requerida: 'Escribe el número de operación que figura en tu comprobante.', imagen_invalida: 'La foto no es válida. Sube una captura o foto del comprobante (máx. 6 MB).',
             operacion_repetida: 'Ese número de operación ya se usó en otro pago. Revísalo.', voucher_repetido: 'Esa misma imagen ya se subió en otro pago.',
             club_suspendido: 'Este club no está recibiendo pagos ahora.'};
  function aviso(t){ pcgAvisar({titulo: 'No se pudo', mensaje: t, icono: '⚠️'}); }
  function soltar(toma){ post('soltar', {partes: toma.partes}).catch(function(){}); }
  function pagar(falta){
    var m = window.pcgMedioPago ? pcgMedioPago() : 'voucher';
    if(m !== 'voucher' && !C.pk) m = 'voucher';
    ocupado = true; pcgCargando('Apartando tu parte…', {demora: 250});
    post('tomar', {lo_que_falta: !!falta}).then(function(t){
      pcgCargando(false);
      if(!t.ok){ ocupado = false; aviso(t.mensaje || ERR[t.error] || 'No pudimos apartar tu parte.'); refrescar(true); return; }
      var lineas = [{t: falta ? ('Lo que falta · ' + t.n.length + (t.n.length === 1 ? ' parte' : ' partes')) : ('Tu parte de la reserva (' + (t.n[0] + 1) + ' de ' + S.n + ')'), m: t.monto_centimos / 100}];
      pcgResumenPago({moneda: C.moneda, medio: m, lineas: lineas, cargo: null, total: t.monto_centimos / 100, titulo: 'Resumen de tu pago',
                      confirmar: m === 'voucher' ? ('Ver cómo pagar · ' + fmt(t.monto_centimos)) : '',
                      nota: 'Pagas directo al club. Tu parte queda apartada para ti ' + Math.round(t.segundos / 60) + ' min mientras pagas.' + (m === 'voucher' ? ' Con comprobante, cuenta cuando el club lo apruebe.' : '')})
        .then(function(ok){
          if(!ok){ ocupado = false; soltar(t); refrescar(true); return; }
          if(m === 'voucher') abrirVoucher(t); else abrirCulqi(t, m);
        });
    }).catch(function(){ pcgCargando(false); ocupado = false; aviso('Sin conexión. Inténtalo de nuevo.'); });
  }
  function abrirCulqi(t, m){
    if(!window.Culqi){ ocupado = false; soltar(t); aviso('El pago con tarjeta no cargó. Recarga la página o paga con comprobante.'); return; }
    Culqi.publicKey = C.pk;
    Culqi.settings({title: C.marca, currency: 'PEN', amount: t.monto_centimos});
    Culqi.options({lang: 'es', installments: false, paymentMethods: {yape: m === 'yape', tarjeta: m === 'tarjeta', bancaMovil: false, agente: false, billetera: false, cuotealo: false},
                   style: {bannerColor: '#0F1B2D', buttonBackground: '#0B7A57', buttonText: 'Pagar', buttonTextColor: '#FFFFFF'}});
    var listo = false;
    window.culqi = function(){
      if(Culqi.token){
        listo = true; var tok = Culqi.token.id, medio = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
        Culqi.close(); pcgCargando('Confirmando tu pago…');
        post('pagar', {partes: t.partes, token: tok, medio: medio}).then(function(p){
          pcgCargando(false); ocupado = false;
          if(p.ok){ pcgToast ? pcgToast('¡Listo! Pagaste tu parte ✅') : null; refrescar(true); }
          else { aviso(p.mensaje || ERR[p.error] || 'El pago no se pudo procesar.'); refrescar(true); }
        }).catch(function(){ pcgCargando(false); ocupado = false; aviso('No pudimos confirmar el pago. Recarga la página para ver su estado.'); });
      } else if(Culqi.error){ aviso((Culqi.error && Culqi.error.user_message) || 'No se pudo procesar el pago.'); }
    };
    Culqi.open();
    var chk = setInterval(function(){
      var abierto = document.getElementById('culqi-container') || document.querySelector('iframe[src*="culqi"]');
      if(!abierto){ clearInterval(chk); if(!listo){ ocupado = false; soltar(t); refrescar(true); } }
    }, 1500);
  }
  function comprimir(file, cb){
    var fr = new FileReader();
    fr.onload = function(){ var img = new Image(); img.onload = function(){ var k = Math.min(1, 1600 / Math.max(img.width, img.height)), cv = document.createElement('canvas');
      cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k); cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); cb(cv.toDataURL('image/jpeg', 0.85)); };
      img.onerror = function(){ cb(null); }; img.src = fr.result; };
    fr.onerror = function(){ cb(null); }; fr.readAsDataURL(file);
  }
  function datoMedio(m){
    var filas = [];
    function f(et, v){ if(v) filas.push("<div class='vch-dato'><span>" + et + "</span><b>" + esc(v) + "</b><button type='button' class='vch-copiar' data-copiar='" + esc(v) + "' aria-label='Copiar " + et + "'>Copiar</button></div>"); }
    f(m.tipo === 'transferencia' ? 'Cuenta' : 'Número', m.numero || m.cuenta); if(m.numero && m.cuenta) f('Cuenta', m.cuenta); f('CCI', m.cci);
    return "<div class='vch-medio'><div class='vch-mt'>" + esc(m.etiqueta || m.tipo) + (m.banco ? ' · ' + esc(m.banco) : '') + "</div>"
      + (m.titular ? "<div class='vch-tit'>A nombre de <b>" + esc(m.titular) + "</b></div>" : '') + filas.join('')
      + (m.qr_url ? "<img class='vch-qr' src='" + esc(m.qr_url) + "' alt='QR de " + esc(m.etiqueta || m.tipo) + " del club' loading='lazy'>" : '')
      + (m.nota ? "<div class='vch-nota'>" + esc(m.nota) + "</div>" : '') + "</div>";
  }
  function abrirVoucher(t){
    var medios = C.medios || [], foto = null, elegido = medios.length === 1 ? medios[0].tipo : '', monto = fmt(t.monto_centimos);
    var ov = document.createElement('div');
    ov.className = 'vch-ov'; ov.setAttribute('role', 'dialog'); ov.setAttribute('aria-modal', 'true'); ov.setAttribute('aria-labelledby', 'vchTit');
    ov.innerHTML = "<div class='vch'><div class='vch-cab'><div><div class='vch-k'>Pago directo al club</div><h3 id='vchTit'>Paga " + monto + "</h3></div>"
      + "<button type='button' class='vch-x' aria-label='Cancelar y soltar mi parte'>✕</button></div>"
      + "<ol class='vch-pasos'><li><b>Paga " + monto + "</b> con uno de estos medios del club:" + medios.map(datoMedio).join('') + "</li>"
      + "<li><b>¿Con qué pagaste?</b><div class='chips' id='vchMedios'>" + medios.map(function(m){ return "<button type='button' class='chip" + (m.tipo === elegido ? ' sel' : '') + "' data-t='" + esc(m.tipo) + "' aria-pressed='" + (m.tipo === elegido) + "'>" + esc(m.etiqueta || m.tipo) + "</button>"; }).join('') + "</div></li>"
      + "<li><label for='vchOp'><b>Número de operación</b></label><input id='vchOp' inputmode='text' autocomplete='off' maxlength='30' placeholder='Figura en tu comprobante'></li>"
      + "<li><b>Foto o captura del comprobante</b><label class='vch-foto'><input type='file' id='vchFoto' accept='image/*'><span id='vchFotoTxt'>📷 Elegir foto</span></label><img id='vchPrev' class='vch-prev' alt='Vista previa del comprobante' hidden></li></ol>"
      + "<div class='estado bad' id='vchErr' role='alert'></div><button type='button' class='btn lg' id='vchEnviar'>Enviar comprobante</button>"
      + "<div class='sub vch-pie'>El club revisa tu pago; tu parte cuenta cuando lo apruebe.</div></div>";
    document.body.appendChild(ov); document.body.style.overflow = 'hidden';
    function err(x){ var el = document.getElementById('vchErr'); el.textContent = x; el.style.display = x ? 'block' : 'none'; }
    function cerrar(sol){ ov.remove(); document.body.style.overflow = ''; ocupado = false; if(sol) soltar(t); refrescar(true); }
    ov.querySelector('.vch-x').addEventListener('click', function(){
      pcgConfirmar({titulo: '¿Cancelar el pago?', mensaje: 'Tu parte vuelve a quedar libre.', confirmar: 'Sí, cancelar', cancelar: 'Seguir pagando', destructivo: true}).then(function(ok){ if(ok) cerrar(true); });
    });
    ov.addEventListener('click', function(ev){
      var cp = ev.target.closest('[data-copiar]');
      if(cp){ try { navigator.clipboard.writeText(cp.dataset.copiar); cp.textContent = 'Copiado ✓'; setTimeout(function(){ cp.textContent = 'Copiar'; }, 1500); } catch(x){} return; }
      var ch = ev.target.closest('#vchMedios [data-t]');
      if(ch){ elegido = ch.dataset.t; ov.querySelectorAll('#vchMedios [data-t]').forEach(function(x){ x.classList.toggle('sel', x === ch); x.setAttribute('aria-pressed', x === ch); }); }
    });
    document.getElementById('vchFoto').addEventListener('change', function(ev){
      var f = ev.target.files && ev.target.files[0]; if(!f) return;
      document.getElementById('vchFotoTxt').textContent = 'Procesando…';
      comprimir(f, function(u){ foto = u; document.getElementById('vchFotoTxt').textContent = u ? '📷 Cambiar foto' : '📷 Elegir foto';
        var pv = document.getElementById('vchPrev'); if(u){ pv.src = u; pv.hidden = false; } else { pv.hidden = true; err(ERR.imagen_invalida); } });
    });
    document.getElementById('vchEnviar').addEventListener('click', function(){
      var op = (document.getElementById('vchOp').value || '').trim();
      if(!elegido) return err(ERR.medio_no_disponible);
      if(op.replace(/[^0-9A-Za-z]/g, '').length < 4) return err(ERR.operacion_requerida);
      if(!foto) return err('Sube la foto o captura de tu comprobante.');
      err(''); var b = this; b.disabled = true; b.textContent = 'Enviando…'; pcgCargando('Enviando tu comprobante…');
      post('voucher', {partes: t.partes, medio: elegido, operacion: op, imagen: foto}).then(function(p){
        pcgCargando(false);
        if(p.ok){ cerrar(false);
          if(p.tardio) pcgAvisar({titulo: 'Recibimos tu comprobante 🧾', mensaje: p.mensaje, icono: '🧾'});
          else if(window.pcgToast) pcgToast('Recibimos tu comprobante 🧾');
          refrescar(true); return; }
        b.disabled = false; b.textContent = 'Enviar comprobante'; err(p.mensaje || ERR[p.error] || 'No pudimos enviar tu comprobante.');
        if(p.error === 'cerrada' || p.error === 'no_tomada') cerrar(false);
      }).catch(function(){ pcgCargando(false); b.disabled = false; b.textContent = 'Enviar comprobante'; err('Sin conexión. Inténtalo de nuevo.'); });
    });
    setTimeout(function(){ var x = ov.querySelector('.vch-x'); if(x) x.focus(); }, 50);
  }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest('[data-pagar]'); if(b){ pagar(b.dataset.pagar === 'falta'); return; }
    var c = ev.target.closest('[data-cancelar]');
    if(c){
      pcgConfirmar({titulo: '¿Cancelar el pago dividido?', icono: '⚠️', destructivo: true, confirmar: 'Sí, liberar el horario', cancelar: 'Volver',
                    mensaje: 'El horario se libera para otros y a cada uno se le devuelve lo que ya pagó.'}).then(function(ok){
        if(!ok) return; pcgCargando('Cancelando…');
        post('cancelar', {}).then(function(p){ pcgCargando(false); if(!p.ok) aviso(p.mensaje || 'No se pudo cancelar.'); refrescar(true); }).catch(function(){ pcgCargando(false); });
      });
      return;
    }
    var cp = ev.target.closest('#dvCopiar');
    if(cp){ var inp = $('dvUrl'); try { navigator.clipboard.writeText(inp.value); } catch(x){ inp.select(); } cp.textContent = 'Copiado ✓'; setTimeout(function(){ cp.textContent = 'Copiar'; }, 1500); }
  });
  render();
})();
"""


def _resumen_html(div: dict, c: dict, filas: list[dict]) -> str:
    wr = _wr()
    lugar = wr._titulo_local(c) if c else "Cancha"
    cuando = ""
    if filas:
        cuando = (f"{horarios.fecha_larga(str(filas[0]['fecha']))} · {filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
                  + (f" · {len(filas)} turnos" if len(filas) > 1 else ""))
    return (f"<div class='dv-k'>Cada uno paga su parte</div><h1>{e(lugar)}</h1>"
            f"<div class='dv-res'><span>{e(c.get('nombre') or '')}</span>"
            + (f"<span>📅 <b>{e(cuando)}</b></span>" if cuando else "")
            + f"<span>Organiza <b>{e(dv._nombre_corto(div['organizador_nombre'], ''))}</b> · total "
              f"<b>{e(_plata(div['total_centimos'], div['moneda']))}</b> entre {div['partes']}</span></div>")


@router.get("/dividir/{token}", response_class=HTMLResponse)
def pagina_dividir(request: Request, token: str) -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return RedirectResponse(f"/entrar?volver={quote('/dividir/' + token, safe='')}", status_code=302)
    div = _div_o_404(token)
    if not div:
        return ui.shell("Enlace no disponible", "<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
                        "<h1 style='font-size:22px'>Este enlace no existe</h1><p class='sub'>Pídele a quien organiza la reserva "
                        "que te lo vuelva a enviar.</p><a class='btn' href='/canchas'>Explorar canchas</a></div>", sesion=ses)
    from pagos import cobro_directo as cd
    email = ses["email"]
    c = datos.cancha(div["cancha_id"]) or {}
    filas = datos.reservas_de(list(div["reserva_ids"]))
    directo = cd.checkout(c, div["moneda"]) if c else {"directo": False}
    pk = directo.get("culqi_public_key") or "" if directo.get("directo") else ""
    url = f"{_base(request)}/dividir/{token}"
    sim = _sim(div["moneda"])
    texto_wa = (f"¡Hola! Reservé {(_wr()._titulo_local(c) if c else 'la cancha')}"
                + (f" el {horarios.fecha_larga(str(filas[0]['fecha']))} a las {filas[0]['hora_inicio']}" if filas else "")
                + f". Cada uno paga {ui.monto(div['parte_centimos'] / 100.0, sim)}: entra aquí y paga tu parte → {url}")
    cfg = {"token": token, "estado": _estado_json(div, email), "moneda": sim, "pk": pk,
           "medios": directo.get("medios") or [] if directo.get("directo") else [], "parte": div["parte_centimos"],
           "marca": config.MARCA, "puede": bool(directo.get("directo")), "selector": (ui.selector_medio_directo(directo) if directo.get("directo") else "")}
    cuerpo = (
        "<div class='dv-wrap'>"
        f"<section class='panel'>{_resumen_html(div, c, filas)}"
        "<div class='dv-prog'><div class='dv-num' id='dvNum'></div>"
        f"<div class='dv-barra' role='progressbar' aria-label='Partes pagadas' aria-valuemin='0' aria-valuemax='{div['partes']}'><i id='dvBarra'></i></div>"
        "<div class='dv-reloj' id='dvReloj' aria-live='off'></div><div class='sub' id='dvRev' style='font-size:13px;margin:4px 0 0'></div></div>"
        "<div class='dv-acc' id='dvAcc'></div></section>"
        "<section class='panel' id='dvCompartir' hidden><h2 style='font-size:17px;margin:0'>Comparte el enlace</h2>"
        "<p class='sub' style='margin:4px 0 0;font-size:13px'>Cada amigo entra con su cuenta de Google y paga su parte directo al club.</p>"
        f"<div class='dv-link'><input id='dvUrl' readonly value='{e(url)}' aria-label='Enlace para tus amigos'>"
        "<button type='button' class='btn sec' id='dvCopiar'>Copiar</button></div>"
        f"<div class='dv-wa'>{ui.boton_whatsapp(texto_wa, etiqueta='💬 Enviar por WhatsApp')}</div></section>"
        "<section class='panel'><h2 style='font-size:17px;margin:0 0 6px'>Partes</h2><div class='dv-partes' id='dvPartes'></div>"
        "<p class='sub' style='font-size:12.5px;margin:10px 0 0'>La reserva se confirma cuando TODAS las partes están pagadas. Si el plazo "
        "vence antes, el horario se libera y a cada uno se le devuelve lo que pagó (con tarjeta o Yape, al mismo medio; con comprobante, "
        "lo devuelve el club).</p></section></div>"
        f"<style>{_CSS_PAG}</style>"
        f"<script>window.__div={ui.json_js(cfg, ensure_ascii=False)};</script>"
        + ("<script src='https://checkout.culqi.com/js/v4'></script>" if pk else "")
        + f"<script>{_JS_PAG}</script>")
    return ui.shell("Cada uno paga su parte", cuerpo, sesion=ses, titulo_tab=f"Pago dividido · {config.MARCA}")


# ── JSON ─────────────────────────────────────────────────────────────────────

def _ctx(request: Request, token: str):
    """(sesión, división, respuesta de error)."""
    ses = _wr()._sesion_o_token(request)
    if not ses:
        return None, None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": dv.mensaje("sesion_requerida")},
                                        status_code=401)
    div = _div_o_404(token)
    if not div:
        return ses, None, JSONResponse({"ok": False, "error": "no_encontrado"}, status_code=404)
    return ses, div, None


def _ids(b: dict | None) -> list[str]:
    v = (b or {}).get("partes")
    return [str(x)[:80] for x in v][:12] if isinstance(v, list) else []


def _con_mensaje(r: dict) -> dict:
    if not r.get("ok") and not r.get("mensaje"):
        r = {**r, "mensaje": dv.mensaje(str(r.get("error") or ""))}
    return r


@router.get("/web/dividir/{token}/estado")
def estado(request: Request, token: str):
    ses, div, malo = _ctx(request, token)
    if malo is not None:
        return malo
    return _estado_json(div, ses["email"])


@router.post("/web/dividir/{token}/tomar")
def tomar(request: Request, token: str, b: dict = Body(default={})):
    ses, div, malo = _ctx(request, token)
    if malo is not None:
        return malo
    return _con_mensaje(dv.tomar(div, ses["email"], ses.get("nombre") or "", bool((b or {}).get("lo_que_falta"))))


@router.post("/web/dividir/{token}/soltar")
def soltar(request: Request, token: str, b: dict = Body(default={})):
    ses, div, malo = _ctx(request, token)
    if malo is not None:
        return malo
    return dv.soltar(div, ses["email"], _ids(b))


@router.post("/web/dividir/{token}/pagar")
def pagar(request: Request, token: str, b: dict = Body(default={})):
    ses, div, malo = _ctx(request, token)
    if malo is not None:
        return malo
    tok = str((b or {}).get("token") or "").strip()[:200]
    if not tok:
        return {"ok": False, "error": "token", "mensaje": "No recibimos el pago. Inténtalo de nuevo."}
    return _con_mensaje(dv.pagar_culqi(div, ses["email"], ses.get("nombre") or "", _ids(b), tok,
                                       str((b or {}).get("medio") or "")))


@router.post("/web/dividir/{token}/voucher")
def voucher(request: Request, token: str, b: dict = Body(default={})):
    ses, div, malo = _ctx(request, token)
    if malo is not None:
        return malo
    img = str((b or {}).get("imagen") or "")
    if len(img) > 9_000_000:
        return {"ok": False, "error": "imagen_invalida"}
    return _con_mensaje(dv.subir_voucher(div, ses["email"], ses.get("nombre") or "", _ids(b),
                                         str((b or {}).get("medio") or "")[:20], str((b or {}).get("operacion") or "")[:40], img))


@router.post("/web/dividir/{token}/cancelar")
def cancelar(request: Request, token: str):
    ses, div, malo = _ctx(request, token)
    if malo is not None:
        return malo
    return _con_mensaje(dv.cancelar(div, ses["email"]))


# ── Mis reservas ─────────────────────────────────────────────────────────────

_PILL_DIV = {"abierta": ("Juntando las partes", "warn"), "completa": ("Confirmando…", "ok"), "confirmada": ("Confirmada", "ok"),
             "vencida": ("No se completó", "bad"), "cancelada": ("Cancelada", "bad")}
_PILL_PARTE = {"pagada": "pagaste", "en_revision": "comprobante en revisión", "reembolsada": "te la devolvimos",
               "devolver": "el club te la devuelve", "devuelta": "el club la devolvió", "cobrando": "pagando…"}


def seccion_mis_reservas(email: str) -> str:
    """Pagos divididos donde organizo o pagué una parte (Mis reservas). La
    reserva confirmada es del organizador (`usuario`): a los amigos les sale
    aquí como "Jugada con <organizador>", sin tocar las filas que lee el APK."""
    lst = dv.de_email(email)
    if not lst:
        return ""
    hoy = horarios.ahora_local("PE").date().isoformat()
    filas = ""
    n = 0
    for d in lst:
        res = datos.reservas_de(list(d["reserva_ids"])) if d["estado"] in ("abierta", "completa", "confirmada") else []
        if res and str(res[0].get("fecha") or "") < hoy:
            continue
        if d["estado"] in ("vencida", "cancelada") and (dv._ahora() - (d.get("cerrado_en") or d["creado_en"])).days > 14:
            continue
        c = datos.cancha(d["cancha_id"]) or {}
        partes = dv.repo().partes(d["id"])
        mias = [p for p in partes if p["pagador_email"].lower() == email]
        org = d["organizador_email"].lower() == email
        pill, cls = _PILL_DIV.get(d["estado"], (d["estado"], "gris"))
        pagadas = sum(1 for p in partes if p["estado"] == "pagada")
        quien = "Tú organizas" if org else f"Jugada con {dv._nombre_corto(d['organizador_nombre'], '')}"
        mi = ""
        if mias:
            monto = sum(p["monto_centimos"] for p in mias)
            mi = f" · tu parte {_plata(monto, d['moneda'])} ({_PILL_PARTE.get(mias[0]['estado'], 'sin pagar')})"
        cuando = (f"{horarios.fecha_larga(str(res[0]['fecha']))} · {res[0]['hora_inicio']}" if res else "")
        filas += (f"<a class='dvm' href='/dividir/{quote(d['token'], safe='')}'><span class='em' aria-hidden='true'>👥</span>"
                  f"<div style='min-width:0'><b>{e(_wr()._titulo_local(c) if c else 'Cancha')}</b>"
                  f"<div class='sub' style='margin:0;font-size:13px'>{e(quien)}{(' · ' + e(cuando)) if cuando else ''}"
                  f" · {pagadas} de {d['partes']} pagaron{e(mi)}</div></div><span class='pill {cls}'>{e(pill)}</span></a>")
        n += 1
    if not n:
        return ""
    return ("<details class='viajes-det' open><summary><span class='ico'>👥</span> Pagos divididos <small>· " + str(n) + "</small></summary>"
            + filas + "<style>.dvm{display:flex;align-items:center;gap:10px;padding:10px 4px;border-top:1px solid var(--trazo);"
            "color:inherit;text-decoration:none}.dvm>div{flex:1}.dvm .em{font-size:20px}.dvm .pill{flex:none}</style></details>")


# ── club: devoluciones de partes ─────────────────────────────────────────────

def aviso_devoluciones(email: str) -> str:
    """Banner para "Pagos por confirmar": partes que el club debe devolver."""
    n = len(dv.devoluciones_pendientes(email))
    if not n:
        return ""
    return (f"<div class='aviso warn' style='margin:10px 0'>💸 Tienes {n} pago(s) de reservas divididas por devolver. "
            "<a href='/anfitrion/cobros-club/devoluciones'><b>Ver devoluciones</b></a></div>")


_NOTA = {"vencida": "La reserva dividida no se completó a tiempo.", "cancelada": "El organizador canceló el pago dividido.",
         "reserva_cancelada": "Se canceló la reserva ya confirmada.", "apartado_perdido": "El horario se perdió antes de confirmar.",
         "aprobado_tarde": "Aprobaste el comprobante cuando el plazo ya había vencido.",
         "sin_revisar": "El comprobante no se revisó a tiempo: devuélvelo solo si lo recibiste."}
_NOTA_TARDIO = {"aprobado_tarde": "Pago fuera de plazo: lo confirmaste, pero no cuenta para la reserva. Devuélvelo.",
                "sin_revisar": "Pago fuera de plazo que no revisaste: devuélvelo solo si lo recibiste."}


@router.get("/anfitrion/cobros-club/devoluciones", response_class=HTMLResponse)
def pagina_devoluciones(request: Request) -> HTMLResponse:
    from web.anfitrion import _sesion_o_entrar
    from web.anfitrion_cobros_club import _pagina
    ses, resp = _sesion_o_entrar(request, "/anfitrion/cobros-club/devoluciones")
    if resp is not None:
        return resp
    lst = dv.devoluciones_pendientes(ses["email"])
    filas = ""
    for p in lst:
        d = p["division"]
        c = datos.cancha(d["cancha_id"]) or {}
        nota = next((v for k, v in _NOTA.items() if str(p.get("nota") or "").startswith(k)), "")
        if str(p.get("nota") or "") == "sin_revisar":
            nota = _NOTA["sin_revisar"]
        if p.get("tardio"):
            nota = _NOTA_TARDIO.get(str(p.get("nota") or ""), _NOTA_TARDIO["aprobado_tarde"])
        ver = (f"<a class='btn sec' href='/anfitrion/pagos-por-confirmar/{e(p['pago_manual_id'])}/imagen' target='_blank' "
               "rel='noopener'>🧾 Ver comprobante</a>") if p.get("pago_manual_id") else ""
        botones = (f"<button type='button' class='btn' data-dev='{e(p['id'])}' data-acc='devuelta'>✅ Ya lo devolví</button>"
                   + (f"<button type='button' class='btn sec' data-dev='{e(p['id'])}' data-acc='no_recibido'>No recibí ese pago</button>"
                      if p.get("nota") == "sin_revisar" else "") + ver)
        donde = "pago fuera de plazo" if p.get("tardio") else f"parte {p['n'] + 1} de {d['partes']}"
        medio = str(p.get("medio") or "").replace("voucher_", "")
        filas += (f"<article class='panel dvd'><div class='dvd-m'>{e(_plata(p['devolver_centimos'] or p['monto_centimos'], d['moneda']))}</div>"
                  f"<div><b>{e(p.get('pagador_nombre') or p.get('pagador_email'))}</b> <small class='sub'>{e(p.get('pagador_email'))}</small></div>"
                  f"<div class='sub' style='margin:4px 0 0'>{e(c.get('nombre') or '')} · {donde}"
                  f"{(' · pagó con ' + e(medio)) if medio else ''}</div>"
                  f"<div class='sub' style='margin:4px 0 0'>{e(nota)}</div><div class='dvd-acc'>{botones}</div></article>")
    cuerpo = ("<h1 class='anf-hola'>Devoluciones de pagos divididos</h1>"
              "<p class='sub'>Estas partes llegaron a tu Yape, Plin o cuenta pero la reserva no se completó. Devuélvelas por el mismo "
              "medio y márcalas aquí; avisamos al jugador.</p>"
              + ("<div style='display:grid;gap:12px;margin-top:14px'>" + filas + "</div>" if filas
                 else "<div class='anf-vacio'>No tienes devoluciones pendientes.</div>")
              + "<style>.dvd-m{font-size:22px;font-weight:800}.dvd-acc{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}</style>"
              "<script>document.addEventListener('click',function(ev){var b=ev.target.closest('[data-dev]');if(!b)return;"
              "var acc=b.dataset.acc;pcgConfirmar({titulo:acc==='devuelta'?'¿Ya lo devolviste?':'¿No recibiste ese pago?',"
              "mensaje:acc==='devuelta'?'Le avisamos al jugador que le devolviste su parte.':'La parte se cierra sin devolución: solo si ese dinero nunca llegó.',"
              "confirmar:'Sí, confirmar',cancelar:'Volver'}).then(function(ok){if(!ok)return;pcgCargando('Guardando…');"
              "fetch('/anfitrion/cobros-club/devoluciones/'+encodeURIComponent(b.dataset.dev),{method:'POST',headers:{'Content-Type':'application/json'},"
              "body:JSON.stringify({accion:acc})}).then(function(r){return r.json();}).then(function(j){if(j.ok){pcgRecargar('Actualizando…');}"
              "else{pcgCargando(false);pcgAvisar({titulo:'No se pudo',mensaje:'Recarga la página e inténtalo de nuevo.'});}})"
              ".catch(function(){pcgCargando(false);});});});</script>")
    return _pagina("Devoluciones", cuerpo, ses, "/anfitrion/pagos-por-confirmar", "Pagos por confirmar")


@router.post("/anfitrion/cobros-club/devoluciones/{parte_id}")
def resolver_devolucion(request: Request, parte_id: str, b: dict = Body(default={})):
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    r = dv.resolver_devolucion(parte_id[:80], ses["email"], str((b or {}).get("accion") or ""))
    return JSONResponse(r, status_code=200 if r.get("ok") else (404 if r.get("error") == "no_encontrado" else 409))
