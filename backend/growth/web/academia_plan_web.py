"""PLAN ACADEMIA en la WEB (decisión del director, 10-oct-2026): las academias
pagan a Pichangol una suscripción mensual tipo Spotify y sus alumnos les pagan
DIRECTO por Yape. Pichangol NO toca esa plata: el alumno reporta el CÓDIGO DE
SEGURIDAD de 3 dígitos de su comprobante de Yape y la academia lo compara con
la notificación de su Yape y confirma con un toque.

Solo aplica con `academia_plan.es_suscripcion()`; con el modelo "comision"
nada de esto se muestra y la web sigue exactamente como antes.

Piezas (la lógica vive en `academia_plan.py`, compartida con el APK):

- `bloque_pago_directo(a, items)`  → caja "Paga a la academia" (Yape de la
  academia con copiar, pasos, mini comprobante de Yape marcando el código,
  formulario "Ya yapeé"). La usan el comprobante de matrícula
  (`web/academia.py`) y Mis clases (`web/jugador_clases.py`).
- POST /web/academia/pago-directo/reportar       → el alumno avisa que yapeó
  (`academia_plan.reportar_pago`, una o varias personas de la MISMA academia).
- GET  /anfitrion/academia/plan                   → tarjeta del plan por
  academia (estado, precio, beneficios, pagar con saldo, renovación).
- POST /anfitrion/academia/plan/pagar             → `academia_plan.pagar`.
- POST /anfitrion/academia/plan/renovacion        → `academia_plan.cambiar_renovacion`.
- POST /anfitrion/academia/pago-directo/resolver  → la academia confirma o
  rechaza (`academia_plan.resolver_pago`); SIEMPRE permitido, aunque el plan
  esté vencido (son pagos de sus alumnos).
- `seccion_por_confirmar(acads)`   → "💜 Pagos por confirmar" en Cobros.
- `paywall(a)` / `banner_plan(acads)` → candado de las páginas de gestión y
  avisos de prueba / vencimiento en Mi academia.
"""
from __future__ import annotations

import json
import re
import urllib.parse as up

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

import academia_plan as ap
from web import datos, sesion, ui
from web.router import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

router = APIRouter(tags=["web-academia-plan"])

# Motivos de rechazo por SELECCIÓN (regla del app: nada de texto libre).
MOTIVOS_RECHAZO = ["No llegó ese yapeo", "El código no coincide", "El monto no coincide"]
MOTIVOS_RECHAZO_QR = ["No llegó ese pago", "El monto no coincide"]

BENEFICIOS = [
    ("🔔", "Recordatorios automáticos a tus alumnos", "Push y correo antes de que venza cada cuota, el día y al vencer."),
    ("📝", "Matrícula en línea", f"Desde tu ficha en {MARCA} y la app, con descuentos familiares y por adelantar."),
    ("📊", "Panel de gestión", "Alumnos, cobros, asistencia, evaluaciones, ranking, reportes, chats y sedes."),
    ("💜", "Tus alumnos te pagan directo", "0 % de comisión. En Perú por Yape (confirmas con el código de seguridad); en Ecuador y Bolivia con tu QR de cobro y un monto único. Tu celular Android lo confirma solo (actívalo en la app → Plan Academia)."),
]


def activo() -> bool:
    return ap.es_suscripcion()


def beneficios(a: dict | None) -> bool:
    """¿La academia tiene el plan vigente? Con el modelo comisión, siempre."""
    return ap.beneficios(a)


def yape_bonito(numero: str) -> str:
    n = re.sub(r"\D", "", numero or "")
    return f"{n[:3]} {n[3:6]} {n[6:]}" if len(n) == 9 else n


def estado_cuota(c: dict) -> str:
    """pagada | por_confirmar | rechazado | esperando_pago (QR iniciado) | pendiente."""
    if c.get("pagada"):
        return "pagada"
    est = str((c.get("reporte") or {}).get("estado") or "")
    return est if est in ("por_confirmar", "rechazado", "esperando_pago") else "pendiente"


def pill_cuota(c: dict) -> str:
    est = estado_cuota(c)
    if est == "pagada":
        return "<span class='pill ok'>✅ Pagado</span>"
    if est == "por_confirmar":
        if (c.get("reporte") or {}).get("medio") == "qr":
            return "<span class='pill warn'>⏳ Esperando que llegue tu pago a la academia</span>"
        return "<span class='pill warn'>⏳ Por confirmar por la academia</span>"
    if est == "esperando_pago":
        return "<span class='pill warn'>📷 Pago con QR en curso</span>"
    if est == "rechazado":
        motivo = str((c.get("reporte") or {}).get("motivo") or "La academia no encontró ese yapeo")
        return f"<span class='pill bad'>Rechazado: {e(motivo)} · vuelve a reportar</span>"
    return "<span class='pill gris'>Pendiente</span>"


def seleccionable(c: dict) -> bool:
    return estado_cuota(c) in ("pendiente", "rechazado", "esperando_pago")


# ── Caja "Paga a la academia" (lado alumno) ───────────────────────────────────

CSS_PD = """
.pd-box{background:#fff;border:1px solid var(--trazo);border-radius:18px;padding:16px 18px;box-shadow:var(--sombra);margin-top:16px;min-width:0}
.pd-box h2{font-size:19px;margin:0 0 4px}
.pd-f{display:flex;align-items:center;gap:10px;padding:8px 4px;border-radius:10px;min-width:0}
label.pd-f{cursor:pointer}label.pd-f:hover{background:#F7F7F7}
.pd-f input{width:18px;height:18px;flex:none;accent-color:#742284;margin:0}
.pd-f .tx{flex:1;min-width:0}.pd-f .tx b{display:block;font-size:13.5px;font-weight:600;overflow-wrap:anywhere}
.pd-f .tx small{color:var(--tenue);font-size:12px}.pd-f .tx .pill{margin-top:4px;white-space:normal;line-height:1.3}
.pd-f .m{font-weight:800;font-size:13.5px;white-space:nowrap}
.pd-per{font-weight:800;font-size:13px;margin-top:10px;overflow-wrap:anywhere}
.pd-yape{display:flex;gap:14px;align-items:center;background:#F6EEF8;border-radius:16px;padding:14px;margin-top:12px;flex-wrap:wrap}
.pd-yape .logo{width:46px;height:46px;border-radius:12px;background:#742284;color:#fff;font-weight:900;display:flex;align-items:center;justify-content:center;font-size:15px;flex:none}
.pd-yape .tx{flex:1 1 160px;min-width:0}.pd-yape .num{font-size:22px;font-weight:900;letter-spacing:.5px;color:#4A1257}
.pd-yape .pd-tit{font-size:13px;color:#5b3a63;overflow-wrap:anywhere}
.pd-yape .btn{flex:none}
.pd-qr{display:flex;gap:14px;align-items:center;margin-top:12px;padding:12px;border:1px solid var(--trazo);border-radius:16px;flex-wrap:wrap}
.pd-qr img{width:150px;height:150px;object-fit:contain;border-radius:12px;background:#fff;flex:none}
.pd-qr .tx{flex:1 1 160px;min-width:0;display:flex;flex-direction:column;gap:6px;align-items:flex-start}
.pd-qr .tx small{color:var(--tenue);font-size:12.5px}
.pd-total{display:flex;justify-content:space-between;gap:10px;align-items:baseline;margin-top:12px;font-weight:800}
.pd-total b{font-size:20px;color:#4A1257}
.pd-pasos{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;margin-top:14px}
.pd-pasos ol{margin:0;padding-left:20px;font-size:14px;line-height:1.55}
.pd-mock{width:150px;border-radius:16px;background:#742284;color:#fff;padding:12px 12px 10px;font-size:11px;box-shadow:0 8px 20px rgba(116,34,132,.25);text-align:center}
.pd-mock .t{font-weight:800;font-size:13px}.pd-mock .mo{font-size:20px;font-weight:900;margin:4px 0}
.pd-mock .cod{background:#fff;color:#4A1257;border-radius:10px;padding:6px 4px;margin-top:8px;outline:3px solid #F2C94C;outline-offset:2px;position:relative}
.pd-mock .cod b{display:block;font-size:18px;letter-spacing:4px}
.pd-mock .cod:after{content:'← este';position:absolute;right:-50px;top:50%;transform:translateY(-50%);color:#B7791F;font-weight:800;font-size:11px}
.pd-mock .op{opacity:.85;margin-top:8px;font-size:10px}
.pd-form{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;margin-top:14px}
.pd-form label{display:block;font-weight:700;font-size:13px;margin-bottom:4px}
.pd-form input{width:100%;box-sizing:border-box}
.pd-cod{font-size:22px;letter-spacing:8px;text-align:center;font-weight:800}
.pd-enviar{width:100%;margin-top:12px;background:#742284}
.pd-nota{color:var(--tenue);font-size:12px;margin-top:8px}
.pq-app{display:flex;gap:12px;align-items:center;background:#EEF6F1;border-radius:16px;padding:12px 14px;margin-top:12px}
.pq-app .logo{width:46px;height:46px;border-radius:12px;background:#0B7A57;color:#fff;font-size:22px;display:flex;align-items:center;justify-content:center;flex:none}
.pq-app .tx{min-width:0;flex:1}.pq-app b{display:block;overflow-wrap:anywhere}.pq-app small{color:var(--tenue);font-size:12.5px}
.pq-iniciar{width:100%;margin-top:12px}
.pq-panel{margin-top:14px;border:2px solid #0B7A57;border-radius:18px;padding:16px;text-align:center;background:#fff}
.pq-panel img{width:100%;max-width:260px;aspect-ratio:1;object-fit:contain;border-radius:14px;border:1px solid var(--trazo);background:#fff}
.pq-monto{font-size:34px;font-weight:900;color:#0A1B3D;margin:8px 0 0;letter-spacing:.3px}
.pq-extra{font-size:12.5px;color:#5b6575;margin:2px 0 8px}
.pq-extra b{color:#B54708}
.pq-pasos{text-align:left;margin:10px auto 0;max-width:420px;padding-left:20px;font-size:14px;line-height:1.55}
.pq-acc{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:12px}.pq-acc .btn{flex:1 1 150px}
.pq-est{display:flex;gap:8px;align-items:center;justify-content:center;font-size:13px;color:#344054;margin-top:12px}
.pq-est .sp{width:14px;height:14px;border-radius:50%;border:2px solid #CFE7D8;border-top-color:#0B7A57;animation:pqg 1s linear infinite;flex:none}
@keyframes pqg{to{transform:rotate(360deg)}}
@media(max-width:560px){.pd-pasos{grid-template-columns:minmax(0,1fr)}.pd-mock{margin:0 auto}.pd-form{grid-template-columns:minmax(0,1fr)}}
"""

JS_PD = r"""
(function(){
  if(window.__pdListo) return; window.__pdListo = true;
  function fmt(mon, v){ return mon + ' ' + (Math.round(v * 100) / 100).toFixed(2); }
  try{ var av = sessionStorage.getItem('pcg_aviso_pd'); if(av){ sessionStorage.removeItem('pcg_aviso_pd'); setTimeout(function(){ pcgAvisar({titulo: '¡Listo!', mensaje: av, icono: '💜', confirmar: 'Entendido'}); }, 200); } }catch(e){}
  function total(box){
    var t = 0, n = 0;
    box.querySelectorAll('input[data-pdc]:checked').forEach(function(x){ t += parseFloat(x.dataset.m) || 0; n++; });
    var el = box.querySelector('[data-pd-total]'); if(el) el.textContent = fmt(box.dataset.mon, t);
    var b = box.querySelector('.pd-enviar'); if(b){ b.disabled = !n; }
    var q = box.querySelector('.pq-iniciar'); if(q){ q.disabled = !n; }
    return {t: t, n: n};
  }
  document.querySelectorAll('.pd-box').forEach(total);
  // ── Pago por QR con monto único (Ecuador / Bolivia) ──
  var sondeos = {};
  function pintarQr(box, i){
    var p = box.querySelector('.pq-panel'); if(!p) return;
    p.hidden = false; box.dataset.pqViva = i.id;
    var esp = i.estado === 'esperando', rep = i.estado === 'reportado';
    p.innerHTML = '<div style="font-weight:800;font-size:15px">Escanea y paga a ' + esc(i.titular) + '</div>' +
      '<img src="' + esc(i.qr_url) + '" alt="Código QR de cobro de la academia">' +
      '<div class="pq-monto">' + esc(i.monto_txt) + '</div>' +
      '<div class="pq-extra">Paga <b>exactamente</b> este monto: incluye ' + esc(i.extra_txt) + ' de identificación para que tu pago se confirme solo.</div>' +
      '<ol class="pq-pasos"><li>Abre ' + esc(i.app_nombre || 'tu app del banco') + ' (o tu banco) y escanea el QR. En el celular: guarda la imagen y elígela desde tu galería.</li>' +
      '<li>Escribe el monto <b>' + esc(i.monto_txt) + '</b> tal cual, con los centavos.</li>' +
      '<li>Paga. Apenas le llegue a la academia, tu cuota queda pagada sola.</li></ol>' +
      '<div class="pq-acc"><a class="btn sec" href="' + esc(i.qr_url) + '" target="_blank" rel="noopener" download>⬇️ Guardar QR</a>' +
      '<button type="button" class="btn sec" data-pq-copiar="' + esc(String(i.monto.toFixed ? i.monto.toFixed(2) : i.monto)) + '">⧉ Copiar monto</button>' +
      (esp ? '<button type="button" class="btn pq-pague">✅ Ya pagué</button>' : '') + '</div>' +
      '<div class="pq-est"><span class="sp"></span><span>' + (rep ? 'Esperando que el pago llegue a la academia… Si su celular no lo confirma, la academia lo revisa a mano.' : 'Esperando tu pago… se confirma solo cuando llegue.') + '</span></div>';
    vigilar(box, i.id);
  }
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function vigilar(box, id){
    if(sondeos[id]) return;
    sondeos[id] = setInterval(function(){
      if(document.hidden) return;
      fetch('/web/academia/pago-qr/' + encodeURIComponent(id), {cache: 'no-store'})
        .then(function(r){ return r.json(); }).then(function(j){
          var i = j && j.intencion; if(!i) return;
          if(i.estado === 'confirmado'){ clearInterval(sondeos[id]); try{ sessionStorage.setItem('pcg_aviso_pd', '¡Pago recibido! La academia ya tiene tu pago de ' + i.monto_txt + ' y tu cuota quedó pagada.'); }catch(e){} pcgRecargar('¡Pago confirmado!'); return; }
          if(i.estado === 'vencido' || i.estado === 'reemplazado' || i.estado === 'rechazado'){ clearInterval(sondeos[id]);
            pcgAvisar({titulo: i.estado === 'rechazado' ? 'La academia no encontró tu pago' : 'Este QR ya no está vigente', mensaje: 'Vuelve a tocar «Pagar con QR» para generar un monto nuevo.', icono: '⏳'}).then(function(){ pcgRecargar('Actualizando…'); }); }
        }).catch(function(){});
    }, 5000);
  }
  document.querySelectorAll('.pd-box[data-pq-viva]').forEach(function(box){
    fetch('/web/academia/pago-qr/' + encodeURIComponent(box.dataset.pqViva), {cache: 'no-store'})
      .then(function(r){ return r.json(); }).then(function(j){ if(j && j.ok && j.intencion && (j.intencion.estado === 'esperando' || j.intencion.estado === 'reportado')) pintarQr(box, j.intencion); })
      .catch(function(){});
  });
  document.addEventListener('change', function(ev){ var x = ev.target; if(x && x.dataset && x.dataset.pdc !== undefined){ total(x.closest('.pd-box')); } });
  document.addEventListener('input', function(ev){ var x = ev.target; if(x && x.classList && x.classList.contains('pd-cod')){ x.value = x.value.replace(/\D/g, '').slice(0, 3); } });
  document.addEventListener('click', function(ev){
    var cm = ev.target.closest && ev.target.closest('[data-pq-copiar]');
    if(cm){ var mo = cm.dataset.pqCopiar; var okm = function(){ if(window.pcgToast) pcgToast('Monto copiado: ' + mo); };
      try{ navigator.clipboard.writeText(mo).then(okm, okm); }catch(e){ okm(); } return; }
    var qi = ev.target.closest && ev.target.closest('.pq-iniciar');
    if(qi){ var bq = qi.closest('.pd-box'), sq = total(bq);
      if(!sq.n){ pcgAvisar({titulo: 'Elige qué vas a pagar', mensaje: 'Marca la cuota o cuotas que vas a pagar.', icono: '☝️'}); return; }
      var porq = {};
      bq.querySelectorAll('input[data-pdc]:checked').forEach(function(x){ (porq[x.dataset.al] = porq[x.dataset.al] || []).push(x.dataset.cu); });
      pcgCargando('Preparando tu QR…');
      fetch('/web/academia/pago-qr/iniciar', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({items: Object.keys(porq).map(function(k){ return {alumno_id: k, cuota_ids: porq[k]}; })})})
        .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); })
        .then(function(j){ pcgCargando(false);
          if(!j.ok){ pcgAvisar({titulo: 'No se pudo preparar el pago', mensaje: j.mensaje || 'Inténtalo de nuevo.', icono: '⚠️'}); return; }
          pintarQr(bq, j.intencion); var pn = bq.querySelector('.pq-panel'); if(pn && pn.scrollIntoView) pn.scrollIntoView({behavior: 'smooth', block: 'center'});
        }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', mensaje: 'Inténtalo de nuevo.'}); });
      return; }
    var pg = ev.target.closest && ev.target.closest('.pq-pague');
    if(pg){ var bp = pg.closest('.pd-box'), iid = bp.dataset.pqViva;
      pcgConfirmar({titulo: '¿Ya pagaste?', icono: '✅', confirmar: 'Sí, ya pagué', cancelar: 'Aún no',
                    mensaje: 'Le avisamos a ' + bp.dataset.acad + '. Si su celular está vinculado, tu pago se confirma solo apenas llegue; si no, la academia lo revisa.'})
        .then(function(ok){ if(!ok) return; pcgCargando('Avisando a la academia…');
          fetch('/web/academia/pago-qr/' + encodeURIComponent(iid) + '/pagado', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
            .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); })
            .then(function(j){ pcgCargando(false);
              if(j.ok && j.intencion){ if(j.intencion.estado === 'confirmado'){ try{ sessionStorage.setItem('pcg_aviso_pd', '¡Pago recibido! Tu cuota quedó pagada.'); }catch(e){} pcgRecargar('¡Pago confirmado!'); return; }
                pintarQr(bp, j.intencion); return; }
              pcgAvisar({titulo: 'No se pudo avisar', mensaje: j.mensaje || 'Inténtalo de nuevo.', icono: '⚠️'});
            }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', mensaje: 'Inténtalo de nuevo.'}); });
        });
      return; }
    var c = ev.target.closest && ev.target.closest('[data-pd-copiar]');
    if(c){ var num = c.dataset.pdCopiar;
      var ok = function(){ if(window.pcgToast) pcgToast('Número copiado: ' + num); };
      try{ navigator.clipboard.writeText(num).then(ok, ok); }catch(e){ ok(); }
      return; }
    var b = ev.target.closest && ev.target.closest('.pd-enviar');
    if(!b) return;
    var box = b.closest('.pd-box'), st = total(box);
    var cod = (box.querySelector('.pd-cod') || {}).value || '', op = ((box.querySelector('.pd-op') || {}).value || '').trim();
    if(!st.n){ pcgAvisar({titulo: 'Elige qué pagaste', mensaje: 'Marca la cuota o cuotas que yapeaste.', icono: '☝️'}); return; }
    if(!/^\d{3}$/.test(cod)){ pcgAvisar({titulo: 'Falta el código de seguridad', mensaje: 'Escribe los 3 dígitos del código de seguridad que sale en tu comprobante de Yape.', icono: '🔢'}); return; }
    var por = {};
    box.querySelectorAll('input[data-pdc]:checked').forEach(function(x){ (por[x.dataset.al] = por[x.dataset.al] || []).push(x.dataset.cu); });
    var items = Object.keys(por).map(function(k){ return {alumno_id: k, cuota_ids: por[k]}; });
    pcgConfirmar({titulo: '¿Ya yapeaste ' + fmt(box.dataset.mon, st.t) + '?', icono: '💜', confirmar: 'Sí, avisar a la academia', cancelar: 'Volver',
                  mensaje: 'Le avisamos a ' + box.dataset.acad + ' con tu código ' + cod + '. Ella lo compara con la notificación de su Yape y confirma tu pago.'})
      .then(function(ok){ if(!ok) return;
        pcgCargando('Avisando a la academia…');
        fetch('/web/academia/pago-directo/reportar', {method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({items: items, codigo: cod, operacion: op})})
          .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); })
          .then(function(j){
            if(j.ok){ try{ sessionStorage.setItem('pcg_aviso_pd', 'Le avisamos a la academia. Tu pago queda «por confirmar» hasta que lo compare con su Yape.'); }catch(e){} pcgRecargar('Actualizando…'); return; }
            pcgCargando(false);
            pcgAvisar({titulo: 'No se pudo avisar', mensaje: j.mensaje || 'Inténtalo de nuevo.', icono: '⚠️'});
          }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', mensaje: 'No pudimos avisar a la academia. Inténtalo de nuevo.'}); });
      });
  });
})();
"""


def _sim(a: dict) -> str:
    return ap.SIMBOLO.get(ap.moneda_de(a), "S/")


def _wa_academia(a: dict) -> str:
    from web.academia import _wa
    return _wa(a)


def bloque_pago_directo(a: dict, items: list[tuple[dict, list[dict]]], *, titulo: str = "Paga a la academia",
                        intro: str = "") -> str:
    """Caja "Paga a la academia" con las cuotas de una o varias personas de la
    MISMA academia. `items` = [(matrícula, cuotas a mostrar)]. Las que están
    pendientes o rechazadas se pueden marcar; las "por confirmar" se muestran
    con su estado. Sin nada que pagar ni por confirmar → ''."""
    sim = _sim(a)
    cd = ap.cobro_directo(a)
    filas, n_sel, varias = "", 0, len([1 for _m, cs in items if cs]) > 1
    hoy = _hoy()
    for m, cuotas in items:
        cs = sorted([c for c in cuotas if isinstance(c, dict) and not c.get("pagada")], key=lambda c: str(c.get("vencimiento") or ""))
        if not cs:
            continue
        if varias:
            filas += f"<div class='pd-per'>{e(m.get('nombre') or 'Alumno')}</div>"
        # Marcadas por defecto: lo vencido o que vence en 7 días; si nada, la más próxima.
        sel_ids = {str(c.get("id")) for c in cs if seleccionable(c) and str(c.get("vencimiento") or "")[:10] <= hoy[1]}
        if not sel_ids:
            primera = next((c for c in cs if seleccionable(c)), None)
            if primera:
                sel_ids = {str(primera.get("id"))}
        for c in cs:
            monto = float(c.get("monto") or 0)
            venc = str(c.get("vencimiento") or "")[:10]
            sub = (f"<small>Vence {e(_fecha_corta(venc))}</small>" if venc else "")
            if seleccionable(c):
                n_sel += 1
                marc = " checked" if str(c.get("id")) in sel_ids else ""
                extra = pill_cuota(c) if estado_cuota(c) == "rechazado" else ""
                filas += (f"<label class='pd-f'><input type='checkbox' data-pdc='' data-al='{e(m.get('id'))}' data-cu='{e(c.get('id'))}' data-m='{monto:.2f}'{marc}>"
                          f"<span class='tx'><b>{e(c.get('concepto') or 'Cuota')}</b>{sub}{(' ' + extra) if extra else ''}</span>"
                          f"<span class='m'>{e(sim)} {monto:.2f}</span></label>")
            else:
                filas += (f"<div class='pd-f'><span style='width:18px;flex:none'></span><span class='tx'><b>{e(c.get('concepto') or 'Cuota')}</b>{sub} {pill_cuota(c)}</span>"
                          f"<span class='m'>{e(sim)} {monto:.2f}</span></div>")
    if not filas:
        return ""
    nombre = a.get("nombre") or "la academia"
    tel = _wa_academia(a)
    h = (f"<div class='pd-box' data-mon='{e(sim)}' data-acad='{e(nombre)}'><h2>💜 {e(titulo)}</h2>"
         f"<p class='sub' style='margin:0 0 6px'>{e(intro or ('Le pagas directo a ' + nombre + f'. {MARCA} no cobra comisión ni toca tu plata.'))}</p>{filas}")
    if not n_sel:
        return h + "<p class='pd-nota'>La academia está revisando tu pago. Te avisamos apenas lo confirme.</p></div>"
    if not cd:
        wa = ui.enlace_whatsapp(f"Hola, soy alumno de {nombre} en {MARCA}. ¿Cómo te pago mi cuota?", tel) if tel else ""
        return (h + f"<div class='aviso warn' style='margin-top:12px'>Coordina el pago con la academia: aún no registró su Yape en {MARCA}.</div>"
                "<div class='acciones' style='margin-top:10px'>"
                + (f"<a class='btn' href='{e(wa)}' target='_blank' rel='noopener'>💬 WhatsApp de la academia</a>" if wa else "")
                + f"<a class='btn sec' href='/mensajes/nuevo?academia={e(up.quote(str(a.get('id') or '')))}'>✉️ Escribir al profe</a></div></div>")
    if cd.get("tipo") == "qr":
        viva = _intencion_viva(items)
        if viva:
            h = h.replace("<div class='pd-box' ", f"<div class='pd-box' data-pq-viva='{e(viva)}' ", 1)
        return h + _bloque_qr(cd, sim) + "</div>"
    num = yape_bonito(cd["yape"])
    h += (f"<div class='pd-total'><span>Yapea</span><b data-pd-total>{e(sim)} 0.00</b></div>"
          "<div class='pd-yape'><div class='logo'>yape</div><div class='tx'><div class='sub' style='margin:0;font-size:12px'>Yape de la academia</div>"
          f"<div class='num'>{e(num)}</div><div class='pd-tit'>A nombre de <b>{e(cd['titular'])}</b></div></div>"
          f"<button type='button' class='btn sec' data-pd-copiar='{e(cd['yape'])}'>⧉ Copiar número</button></div>"
          + ((f"<div class='pd-qr'><img src='{e(cd['qr_url'])}' alt='QR de Yape de la academia' loading='lazy'>"
              "<div class='tx'><b>O escanea su QR</b><small>Desde otro celular, o guárdalo y en Yape elige «Escanear» → galería.</small>"
              f"<a class='btn sec' href='{e(cd['qr_url'])}' target='_blank' rel='noopener' download>⬇️ Guardar QR</a></div></div>")
             if cd.get("qr_url") else "")
          + "<div class='pd-pasos'><ol>"
          f"<li>Abre tu Yape y yapea el <b>monto exacto</b> a <b>{e(num)}</b> ({e(cd['titular'])}){' o escanea su QR' if cd.get('qr_url') else ''}.</li>"
          "<li>En tu comprobante de Yape copia el <b>código de seguridad</b> de 3 dígitos.</li>"
          "<li>Escríbelo aquí abajo y toca «Ya yapeé». La academia lo compara con su Yape y confirma tu pago.</li></ol>"
          f"<div class='pd-mock' aria-hidden='true'><div class='t'>¡Yapeaste!</div><div class='mo'>{e(sim)} 250</div><div>{e(cd['titular'][:18])}</div>"
          "<div class='cod'><span>Código de seguridad</span><b>701</b></div><div class='op'>Nro. de operación 05775701</div></div></div>"
          "<div class='pd-form'><div><label>Código de seguridad <span class='req'>3 dígitos</span></label>"
          "<input class='pd-cod' inputmode='numeric' autocomplete='one-time-code' maxlength='3' placeholder='• • •' aria-label='Código de seguridad de Yape'></div>"
          "<div><label>N.º de operación <span class='req'>opcional</span></label>"
          "<input class='pd-op' inputmode='numeric' maxlength='20' placeholder='Ej. 05775701' aria-label='Número de operación de Yape'></div></div>"
          "<button type='button' class='btn pd-enviar'>💜 Ya yapeé · avisar a la academia</button>"
          "<p class='pd-nota'>Tu cuota queda «por confirmar» hasta que la academia lo vea en su Yape. Si no lo encuentra, te avisamos para que lo revises.</p></div>")
    return h


def _intencion_viva(items: list[tuple[dict, list[dict]]]) -> str:
    """Id de un pago por QR en curso de estas cuotas (para reabrirlo al volver)."""
    from db.store import stores
    from datetime import datetime, timezone
    ahora = datetime.now(timezone.utc)
    for _m, cs in items:
        for c in cs:
            rep = (c or {}).get("reporte") or {}
            iid = str(rep.get("intencion") or "")
            i = stores.qr_intenciones.get(iid) if iid else None
            if i and ap._viva(i, ahora):
                return iid
    return ""


def _bloque_qr(cd: dict, sim: str) -> str:
    """Ecuador / Bolivia: el alumno paga el QR de la academia con un MONTO
    ÚNICO y la notificación del celular de la academia lo confirma sola."""
    return (f"<div class='pd-total'><span>Vas a pagar</span><b data-pd-total>{e(sim)} 0.00</b></div>"
            "<div class='pq-app'><div class='logo'>▦</div><div class='tx'><small>Paga con el QR de la academia</small>"
            f"<b>{e(cd['app_nombre'])} · {e(cd['titular'])}</b>"
            "<small>Te damos un monto único (tu cuota + unos centavos) para reconocer tu pago al instante.</small></div></div>"
            "<button type='button' class='btn pq-iniciar'>📷 Pagar con QR</button>"
            "<div class='pq-panel' hidden></div>"
            f"<p class='pd-nota'>{MARCA} no toca tu plata: le pagas directo a la academia y tu cuota se marca pagada sola.</p>")


def _hoy() -> tuple[str, str]:
    """(hoy, hoy + 7 días) en Lima, ISO."""
    from datetime import timedelta
    d = ap._hoy_lima()
    return d.isoformat(), (d + timedelta(days=7)).isoformat()


def _fecha_corta(iso: str) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
    try:
        y, mth, d = iso[:10].split("-")
        return f"{int(d)} {meses[int(mth) - 1]} {y}"
    except (ValueError, IndexError):
        return iso


class _Err(Exception):
    pass


@router.post("/web/academia/pago-directo/reportar")
def reportar(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """El alumno (o quien paga) avisa que yapeó: una o varias personas de la
    MISMA academia con un solo código de seguridad."""
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para avisar tu pago."}, status_code=401)
    email = (ses.get("email") or "").strip().lower()
    items = body.get("items") if isinstance(body.get("items"), list) else [
        {"alumno_id": body.get("alumno_id"), "cuota_ids": body.get("cuota_ids")}]
    items = [x for x in items if isinstance(x, dict) and str(x.get("alumno_id") or "").strip()][:8]
    codigo = re.sub(r"\D", "", str(body.get("codigo") or ""))
    operacion = str(body.get("operacion") or "")
    if not re.fullmatch(r"\d{3}", codigo):
        return JSONResponse({"ok": False, "error": "codigo", "mensaje": "Escribe los 3 dígitos del código de seguridad que sale en tu Yape."})
    if not items:
        return JSONResponse({"ok": False, "error": "cuotas", "mensaje": "Elige qué cuota pagaste."})
    academias = {str((datos.matricula(str(x["alumno_id"])) or {}).get("academiaId") or "") for x in items}
    if len(academias) > 1:
        return JSONResponse({"ok": False, "error": "academias", "mensaje": "Reporta un yapeo por academia: cada una tiene su propio Yape."})
    hechas, total, error = [], 0.0, None
    for x in items:
        ids = [str(c) for c in (x.get("cuota_ids") or []) if str(c).strip()]
        r = ap.reportar_pago(str(x["alumno_id"]), email, ids, codigo, operacion)
        if r.get("ok"):
            hechas += r.get("cuotas") or []
            total += float(r.get("total") or 0)
        elif error is None:
            error = r
    if not hechas:
        return JSONResponse(error or {"ok": False, "error": "nada", "mensaje": "No se pudo avisar el pago."})
    return JSONResponse({"ok": True, "cuotas": hechas, "total": round(total, 2)})


def _ses_alumno(request: Request):
    ses = sesion.de_request(request)
    if not ses:
        return None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para pagar."}, status_code=401)
    return (ses.get("email") or "").strip().lower(), None


@router.post("/web/academia/pago-qr/iniciar")
def qr_iniciar(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """Monto único para pagar por QR una o varias cuotas de la MISMA academia."""
    email, err = _ses_alumno(request)
    if err:
        return err
    items = body.get("items") if isinstance(body.get("items"), list) else []
    return JSONResponse(ap.iniciar_pago_qr(email, items))


@router.post("/web/academia/pago-qr/{iid}/pagado")
def qr_pagado(iid: str, request: Request) -> JSONResponse:
    email, err = _ses_alumno(request)
    if err:
        return err
    return JSONResponse(ap.marcar_pagado_qr(iid, email))


@router.get("/web/academia/pago-qr/{iid}")
def qr_estado(iid: str, request: Request) -> JSONResponse:
    email, err = _ses_alumno(request)
    if err:
        return err
    return JSONResponse(ap.estado_qr(iid, email))


# ── Lado academia: plan, candado y pagos por confirmar ───────────────────────

CSS_PLAN = """
.pl-card{background:#fff;border:1px solid var(--trazo);border-radius:22px;box-shadow:var(--sombra2);overflow:hidden;max-width:620px;margin:18px auto 0}
.pl-top{background:linear-gradient(135deg,#0A1B3D,#08654A);color:#fff;padding:20px 22px}
.pl-top .pill{background:rgba(255,255,255,.18);color:#fff}
.pl-top h2{margin:10px 0 2px;font-size:22px;color:#fff;overflow-wrap:anywhere}
.pl-precio{font-size:34px;font-weight:900;margin-top:10px}.pl-precio small{font-size:15px;font-weight:600;opacity:.85}
.pl-body{padding:18px 22px 22px}
.pl-ben{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-top:1px solid var(--trazo)}
.pl-ben:first-child{border-top:0}.pl-ben .ic{font-size:20px;flex:none;width:28px;text-align:center}
.pl-ben b{display:block;font-size:14.5px}.pl-ben small{color:var(--tenue);font-size:12.5px}
.pl-sw{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:16px;padding:12px 14px;border-radius:14px;background:var(--gris)}
.pl-sw input{width:46px;height:26px;flex:none;accent-color:var(--esmeralda)}
.pl-sw .tx{min-width:0}.pl-sw small{display:block;color:var(--tenue);font-size:12px}
.pl-banner{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-top:14px}
.pl-banner .btn{flex:none}
.pw-card{text-align:center;max-width:560px;margin:22px auto 0}
.pw-card .em{font-size:44px}
.pc-card{border:1px solid #E5D3EA;background:#FCF7FD;border-radius:18px;padding:14px 16px;min-width:0}
.pc-cod{font-size:34px;font-weight:900;letter-spacing:8px;color:#4A1257;text-align:center;background:#fff;border-radius:14px;padding:8px;margin:10px 0;border:2px dashed #C9A5D3}
.pc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:12px;margin-top:12px}
.pc-acc{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.pc-acc .btn{flex:1 1 auto}
.pc-mot .chip{margin:4px 4px 0 0}
"""


def banner_plan(acads: list[dict]) -> str:
    """Avisos arriba de Mi academia: prueba (días que quedan) o plan vencido."""
    if not activo():
        return ""
    out = ""
    for a in acads:
        est = ap.estado(a)
        url = f"/anfitrion/academia/plan?academia={up.quote(str(a.get('id') or ''))}"
        nombre = e(a.get("nombre") or "Tu academia")
        if est["estado"] == "prueba":
            d = int(est.get("dias_restantes") or 0)
            out += (f"<div class='aviso warn pl-banner'><span>🎁 <b>{nombre}</b>: te quedan {d} día{'s' if d != 1 else ''} de prueba gratis del Plan Academia.</span>"
                    f"<a class='btn sec' href='{url}'>Ver plan</a></div>")
        elif est["estado"] == "vencida":
            out += (f"<div class='aviso bad pl-banner'><span><b>{nombre}</b> · Tu plan venció: tus alumnos no reciben recordatorios y no aceptas matrículas.</span>"
                    f"<a class='btn' href='{url}'>Activar por {e(est['simbolo'])} {est['precio']:.2f}</a></div>")
    return f"<style>{CSS_PLAN}</style>{out}" if out else ""


def pill_plan(a: dict) -> str:
    if not activo():
        return ""
    est = ap.estado(a)
    if est["estado"] == "prueba":
        return f"<span class='pill dorado'>🎁 Prueba · {int(est.get('dias_restantes') or 0)} d</span>"
    if est["estado"] == "activa":
        return "<span class='pill ok'>✓ Plan activo</span>"
    return "<span class='pill bad'>Plan vencido</span>"


def paywall(a: dict) -> str:
    """Tarjeta que reemplaza a una página de gestión sin plan vigente."""
    est = ap.estado(a)
    url = f"/anfitrion/academia/plan?academia={up.quote(str(a.get('id') or ''))}"
    ben = "".join(f"<div class='pl-ben' style='text-align:left'><span class='ic'>{ic}</span><div><b>{e(t)}</b><small>{e(d)}</small></div></div>"
                  for ic, t, d in BENEFICIOS)
    return (f"<style>{CSS_PLAN}</style><div class='panel pw-card'><div class='em'>🔒</div><h2>Activa tu Plan Academia</h2>"
            f"<p class='sub'>El plan de <b>{e(a.get('nombre') or 'tu academia')}</b> venció. Mientras tanto tu academia solo muestra su ficha pública "
            "y los pagos que ya te reportaron tus alumnos siguen en «Cobros» para que los confirmes.</p>"
            f"<div style='margin-top:12px'>{ben}</div>"
            f"<div class='acciones' style='justify-content:center;margin-top:14px'><a class='btn' href='{url}'>Activar por {e(est['simbolo'])} {est['precio']:.2f} al mes</a>"
            f"<a class='btn sec' href='/anfitrion/cobros?academia={e(up.quote(str(a.get('id') or '')))}'>💜 Pagos por confirmar</a></div></div>")


def _mias(email: str) -> list[dict]:
    acads = datos.academias_de_dueno(email)
    for a in acads:
        a.setdefault("dueno", (email or "").strip().lower())
    return acads


def _tarjeta_plan(a: dict, email: str) -> str:
    from db.store import stores
    est = ap.estado(a)
    sim, precio = est["simbolo"], float(est["precio"])
    if est["estado"] == "prueba":
        d = int(est.get("dias_restantes") or 0)
        estado = f"<span class='pill'>🎁 Prueba gratis · quedan {d} día{'s' if d != 1 else ''}</span>"
        detalle = f"Tu prueba gratis termina el {e(est.get('vence_txt') or '')}. Si activas ahora, el mes se suma al final de la prueba: no pierdes días."
        boton = f"Activar ya · {sim} {precio:.2f}"
    elif est["estado"] == "activa":
        estado = f"<span class='pill'>✓ Activo hasta el {e(est.get('vence_txt') or '')}</span>"
        detalle = ("Se renueva solo con tu saldo al vencer." if est.get("auto_renovar") else
                   "La renovación automática está apagada: al vencer, tu academia se queda solo con su ficha pública.")
        boton = f"Pagar un mes más · {sim} {precio:.2f}"
    else:
        estado = "<span class='pill' style='background:#C13515'>Vencido</span>"
        detalle = "Tu academia solo muestra su ficha pública: sin matrículas nuevas, sin recordatorios a tus alumnos y sin panel."
        boton = f"Pagar con mi saldo · {sim} {precio:.2f}"
    ben = "".join(f"<div class='pl-ben'><span class='ic'>{ic}</span><div><b>{e(t)}</b><small>{e(d)}</small></div></div>" for ic, t, d in BENEFICIOS)
    try:
        from pagos.router import moneda_billetera
        mon_b = moneda_billetera(email)
    except Exception:  # noqa: BLE001
        mon_b = est["moneda"]
    saldo = stores.saldo_centimos(email) / 100.0
    cd = ap.cobro_directo(a)
    aviso_yape = ("" if cd else
                  f"<div class='aviso warn' style='margin-top:14px'>Registra tu Yape para que tus alumnos te paguen directo. "
                  f"<a href='/anfitrion/academia/{e(a['id'])}/editar#sec-cobro' style='font-weight:700'>Registrar mi Yape ›</a></div>")
    renueva = bool(est.get("auto_renovar"))
    return (f"<div class='pl-card' data-acad='{e(a['id'])}'><div class='pl-top'>{estado}<h2>Plan Academia · {e(a.get('nombre') or 'Academia')}</h2>"
            f"<div class='pl-precio'>{e(sim)} {precio:.2f} <small>al mes</small></div></div><div class='pl-body'>"
            f"<p class='sub' style='margin-top:0'>{detalle}</p>{ben}"
            f"<button type='button' class='btn lg' style='width:100%;margin-top:14px' data-plan-pagar='{e(a['id'])}' data-precio='{precio:.2f}' data-sim='{e(sim)}'>{e(boton)}</button>"
            f"<p class='sub' style='font-size:12.5px;text-align:center;margin-top:6px'>Tu saldo: {e(ap.SIMBOLO.get(mon_b, mon_b))} {saldo:.2f} · "
            "<a href='/mi-billetera#recargar'>Recargar</a></p>"
            f"<label class='pl-sw'><span class='tx'><b>Renovación automática</b><small>Cada {ap.DIAS_PERIODO} días con tu saldo, después de tu primer pago. "
            "Puedes apagarla cuando quieras.</small></span>"
            f"<input type='checkbox' role='switch' data-plan-renovar='{e(a['id'])}'{' checked' if renueva else ''}></label>"
            f"{aviso_yape}</div></div>")


JS_PLAN = r"""
(function(){
  try{ var av = sessionStorage.getItem('pcg_aviso_plan'); if(av){ sessionStorage.removeItem('pcg_aviso_plan'); setTimeout(function(){ pcgAvisar({titulo: '¡Listo!', mensaje: av, icono: '✅', confirmar: 'Entendido'}); }, 200); } }catch(e){}
  function post(url, body, msg){ pcgCargando(msg || 'Guardando…', {demora: 200});
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); })
      .catch(function(){ return {ok: false, mensaje: 'Revisa tu conexión e inténtalo de nuevo.'}; })
      .then(function(j){ pcgCargando(false); return j; }); }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest && ev.target.closest('[data-plan-pagar]'); if(!b) return;
    var aid = b.dataset.planPagar, monto = b.dataset.sim + ' ' + b.dataset.precio;
    pcgConfirmar({titulo: '¿Pagar ' + monto + ' de tu saldo?', icono: '🎓', confirmar: 'Pagar ' + monto, cancelar: 'Ahora no',
                  mensaje: 'Activamos 30 días más del Plan Academia. Si estás en tu prueba gratis, se suman al final: no pierdes días.'})
      .then(function(ok){ if(!ok) return;
        post('/anfitrion/academia/plan/pagar', {academia_id: aid}, 'Pagando tu plan…').then(function(j){
          if(j.ok){ try{ sessionStorage.setItem('pcg_aviso_plan', 'Plan Academia activo hasta el ' + (j.vence_txt || 'próximo mes') + '.'); }catch(e){} pcgRecargar('Actualizando…'); return; }
          if(j.error === 'falta_saldo'){
            pcgConfirmar({titulo: 'Te falta saldo', icono: '👛', confirmar: 'Recargar saldo', cancelar: 'Ahora no', mensaje: j.mensaje || 'Recarga tu saldo y vuelve a intentar.'})
              .then(function(r){ if(r) pcgIr('/mi-billetera#recargar', 'Abriendo tu billetera…'); });
            return; }
          pcgAvisar({titulo: j.error === 'moneda_distinta' ? 'Otra moneda' : 'No se pudo pagar', mensaje: j.mensaje || 'Inténtalo de nuevo.', icono: '⚠️'});
        }); });
  });
  document.addEventListener('change', function(ev){
    var x = ev.target; if(!x || !x.dataset || !x.dataset.planRenovar) return;
    var renovar = x.checked;
    var seguir = renovar ? Promise.resolve(true) : pcgConfirmar({titulo: '¿Apagar la renovación automática?', icono: '🔁', confirmar: 'Sí, apagar', cancelar: 'No', destructivo: true,
      mensaje: 'Al vencer, tu academia se queda solo con su ficha pública: sin matrículas nuevas ni recordatorios a tus alumnos.'});
    seguir.then(function(ok){
      if(!ok){ x.checked = true; return; }
      post('/anfitrion/academia/plan/renovacion', {academia_id: x.dataset.planRenovar, renovar: renovar}).then(function(j){
        if(j.ok){ if(window.pcgToast) pcgToast(renovar ? 'Renovación automática encendida.' : 'Renovación automática apagada.'); return; }
        x.checked = !renovar; pcgAvisar({titulo: 'No se pudo cambiar', mensaje: j.mensaje || 'Inténtalo de nuevo.', icono: '⚠️'});
      }); });
  });
})();
"""


@router.get("/anfitrion/academia/plan", response_class=HTMLResponse)
def pagina_plan(request: Request, academia: str = "") -> HTMLResponse:
    from web.anfitrion import _sesion_o_entrar
    from web.anfitrion_academia import _cab
    ses, resp = _sesion_o_entrar(request, "/anfitrion/academia/plan" + (f"?academia={up.quote(academia)}" if academia else ""))
    if resp is not None:
        return resp
    email = (ses.get("email") or "").strip().lower()
    acads = _mias(email)
    if not acads:
        return HTMLResponse("", status_code=302, headers={"Location": "/anfitrion/academia"})
    if not activo():
        cuerpo = ("<a class='anf-back' href='/anfitrion/academia'>‹ Mi academia</a><div class='panel pw-card' style='max-width:560px;margin:22px auto 0;text-align:center'>"
                  f"<h1 style='font-size:22px'>Plan Academia</h1><p class='sub'>Hoy tu academia no paga plan: {MARCA} cobra una comisión solo cuando tus alumnos pagan en línea.</p></div>")
        return ui.shell("Plan Academia", cuerpo, nav=_cab(ses, "academias"), sesion=ses, ancho=True, titulo_tab="Plan Academia · Modo anfitrión")
    a = next((x for x in acads if x.get("id") == academia), acads[0])
    chips = ("<div class='chips' style='margin-top:12px;justify-content:center'>" + "".join(
        f"<a class='chip{' sel' if x['id'] == a['id'] else ''}' href='/anfitrion/academia/plan?academia={e(up.quote(x['id']))}'>{e(x.get('nombre') or 'Academia')}</a>"
        for x in acads) + "</div>") if len(acads) > 1 else ""
    cuerpo = (f"<style>{CSS_PLAN}</style><a class='anf-back' href='/anfitrion/academia'>‹ Mi academia</a>"
              "<div style='text-align:center;margin-top:8px'><h1 class='anf-hola' style='margin:0'>Plan Academia</h1>"
              f"<p class='sub'>Un precio fijo al mes. {ap.prueba_dias()} días de prueba gratis. Tus alumnos te pagan directo: {MARCA} no cobra comisión.</p></div>"
              f"{chips}{_tarjeta_plan(a, email)}<script>{JS_PLAN}</script>")
    return ui.shell("Plan Academia", cuerpo, nav=_cab(ses, "academias"), sesion=ses, ancho=True, titulo_tab="Plan Academia · Modo anfitrión")


def _ses_json(request: Request):
    ses = sesion.de_request(request)
    if not ses:
        return None, JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para continuar."}, status_code=401)
    return ses, None


def _mia(email: str, aid: str) -> dict | None:
    return next((x for x in _mias(email) if x.get("id") == aid), None)


@router.post("/anfitrion/academia/plan/pagar")
def plan_pagar(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, resp = _ses_json(request)
    if resp is not None:
        return resp
    email = (ses.get("email") or "").strip().lower()
    a = _mia(email, str(body.get("academia_id") or ""))
    if a is None:
        return JSONResponse({"ok": False, "error": "no_encontrada", "mensaje": "No encontramos esa academia en tu cuenta."}, status_code=404)
    r = ap.pagar(a, email)
    if r.get("ok"):
        r["vence_txt"] = ap.fecha_txt(r.get("hasta"))
    return JSONResponse(r)


@router.post("/anfitrion/academia/plan/renovacion")
def plan_renovacion(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    ses, resp = _ses_json(request)
    if resp is not None:
        return resp
    email = (ses.get("email") or "").strip().lower()
    a = _mia(email, str(body.get("academia_id") or ""))
    if a is None:
        return JSONResponse({"ok": False, "error": "no_encontrada", "mensaje": "No encontramos esa academia en tu cuenta."}, status_code=404)
    return JSONResponse(ap.cambiar_renovacion(a, email, bool(body.get("renovar"))))


@router.post("/anfitrion/academia/pago-directo/resolver")
def resolver(request: Request, body: dict = Body(default_factory=dict)) -> JSONResponse:
    """La academia confirma o rechaza un yapeo reportado. Siempre permitido
    (aunque el plan esté vencido): es plata de sus alumnos."""
    ses, resp = _ses_json(request)
    if resp is not None:
        return resp
    aceptar = bool(body.get("aceptar"))
    motivo = str(body.get("motivo") or "").strip()
    if not aceptar and motivo not in MOTIVOS_RECHAZO + MOTIVOS_RECHAZO_QR:
        return JSONResponse({"ok": False, "error": "motivo", "mensaje": "Elige por qué no lo confirmas."})
    ids = [str(c) for c in (body.get("cuota_ids") or []) if str(c).strip()]
    return JSONResponse(ap.resolver_pago(str(body.get("academia_id") or ""), str(body.get("alumno_id") or ""), ids,
                                         ses.get("email") or "", aceptar, motivo))


def seccion_por_confirmar(acads: list[dict]) -> str:
    """"💜 Pagos por confirmar" de todas las academias del dueño (arriba de
    Cobros). Vacía si no hay nada que confirmar."""
    pend = ap.por_confirmar(acads) if acads else []
    if not pend:
        return ""
    tarjetas = ""
    for g in pend:
        qr = g.get("medio") == "qr"
        dato = {"academia_id": g["academia_id"], "alumno_id": g["alumno_id"], "cuota_ids": [c["id"] for c in g["cuotas"]],
                "total": f"{g['simbolo']} {float(g.get('monto_unico') or g['total']) if qr else g['total']:.2f}",
                "codigo": g["codigo"], "alumno": g["alumno"], "qr": qr}
        lineas = "".join(f"<div style='display:flex;justify-content:space-between;gap:8px;font-size:13px'><span style='min-width:0;overflow-wrap:anywhere'>{e(c['concepto'])}</span>"
                         f"<b style='white-space:nowrap'>{e(g['simbolo'])} {c['monto']:.2f}</b></div>" for c in g["cuotas"])
        tarjetas += (f"<div class='pc-card'><div style='display:flex;justify-content:space-between;gap:10px;align-items:flex-start'>"
                     f"<div style='min-width:0'><b style='overflow-wrap:anywhere'>{e(g['alumno'])}</b>"
                     f"<div class='sub' style='margin:0;font-size:12px;overflow-wrap:anywhere'>{e(g['academia'])}"
                     + (f" · paga {e(g['pagador'])}" if g.get("pagador") else "") + f"</div></div><b style='font-size:18px;white-space:nowrap'>{e(g['simbolo'])} {g['total']:.2f}</b></div>"
                     f"<div style='margin-top:8px'>{lineas}</div>"
                     + ((f"<div class='sub' style='margin:10px 0 0;font-size:12px;text-align:center'>Monto exacto por QR (con centavos de identificación)</div>"
                         f"<div class='pc-cod' style='letter-spacing:1px'>{e(g['simbolo'])} {float(g.get('monto_unico') or g['total']):.2f}</div>")
                        if g.get("medio") == "qr" else
                        f"<div class='sub' style='margin:10px 0 0;font-size:12px;text-align:center'>Código de seguridad</div><div class='pc-cod'>{e(g['codigo'])}</div>")
                     + (f"<div class='sub' style='margin:0;font-size:12.5px;text-align:center'>N.º de operación: <b>{e(g['operacion'])}</b></div>" if g.get("operacion") else "")
                     + f"<div class='sub' style='margin:4px 0 0;font-size:12px;text-align:center'>Reportado el {e(ap.fecha_txt(g.get('fecha')))}</div>"
                     f"<div class='pc-acc'><button type='button' class='btn' data-pc-ok='{e(ui.json_js(dato, ensure_ascii=False))}'>✅ Confirmar</button>"
                     f"<button type='button' class='btn sec' data-pc-no='{e(ui.json_js(dato, ensure_ascii=False))}'>No lo encontré</button></div></div>")
    motivos = ui.json_js(MOTIVOS_RECHAZO, ensure_ascii=False)
    motivos_qr = ui.json_js(MOTIVOS_RECHAZO_QR, ensure_ascii=False)
    return (f"<style>{CSS_PLAN}</style><section id='porConfirmar' style='margin-top:16px'><h2 class='ng-h2' style='margin-bottom:2px'>💜 Pagos por confirmar</h2>"
            "<p class='sub' style='margin:0'>Tus alumnos te pagaron directo. Compara el código (Yape) o el monto exacto (QR) con la notificación de tu app y confirma con un toque.</p>"
            f"<div class='pc-grid'>{tarjetas}</div></section><script>window.__pcMotivos={motivos};window.__pcMotivosQr={motivos_qr};{JS_POR_CONFIRMAR}</script>")


JS_POR_CONFIRMAR = r"""
(function(){
  if(window.__pcListo) return; window.__pcListo = true;
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function enviar(d, aceptar, motivo){
    pcgCargando(aceptar ? 'Confirmando…' : 'Avisando al alumno…');
    fetch('/anfitrion/academia/pago-directo/resolver', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({academia_id: d.academia_id, alumno_id: d.alumno_id, cuota_ids: d.cuota_ids, aceptar: aceptar, motivo: motivo || ''})})
      .then(function(r){ return r.json().catch(function(){ return {ok: false}; }); })
      .then(function(j){
        if(j.ok){ if(window.pcgToast) pcgToast(aceptar ? 'Pago confirmado. Le avisamos a ' + d.alumno + '.' : 'Le avisamos a ' + d.alumno + ' para que lo revise.'); pcgRecargar('Actualizando…'); return; }
        pcgCargando(false); pcgAvisar({titulo: 'No se pudo', mensaje: j.mensaje || 'Inténtalo de nuevo.', icono: '⚠️'});
      }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', mensaje: 'Inténtalo de nuevo.'}); });
  }
  document.addEventListener('click', function(ev){
    var m = ev.target.closest && ev.target.closest('.pc-mot .chip');
    if(m){ m.parentNode.querySelectorAll('.chip').forEach(function(x){ x.classList.toggle('sel', x === m); }); return; }
    var ok = ev.target.closest && ev.target.closest('[data-pc-ok]');
    if(ok){ var d = JSON.parse(ok.dataset.pcOk);
      pcgConfirmar({titulo: '¿Te llegó ' + d.total + '?', icono: '💜', confirmar: 'Sí, confirmar pago', cancelar: 'Volver',
                    mensaje: d.qr ? 'Confirma solo si en tu app de cobros ves un pago de exactamente ' + d.total + '. La cuota de ' + d.alumno + ' queda pagada.'
                                  : 'Confirma solo si en tu Yape ves un yapeo de ' + d.total + ' con el código ' + d.codigo + '. La cuota de ' + d.alumno + ' queda pagada.'})
        .then(function(r){ if(r) enviar(d, true); });
      return; }
    var no = ev.target.closest && ev.target.closest('[data-pc-no]');
    if(no){ var d2 = JSON.parse(no.dataset.pcNo);
      var chips = '<div style="text-align:left">¿Qué pasó? Se lo diremos a ' + esc(d2.alumno) + ' para que lo revise y vuelva a reportarlo.<div class="chips pc-mot" style="margin-top:10px">' +
        ((d2.qr ? window.__pcMotivosQr : window.__pcMotivos) || []).map(function(t, i){ return '<button type="button" class="chip' + (i === 0 ? ' sel' : '') + '" data-v="' + esc(t) + '">' + esc(t) + '</button>'; }).join('') + '</div></div>';
      pcgConfirmar({titulo: d2.qr ? 'No encontraste el pago' : 'No encontraste el yapeo', html: chips, icono: '🔎', confirmar: 'Avisar al alumno', cancelar: 'Volver', destructivo: true})
        .then(function(r){ if(!r) return; var s = document.querySelector('#pcgDlgMsg .pc-mot .chip.sel') || document.querySelector('.pc-mot .chip.sel');
          enviar(d2, false, s ? s.dataset.v : (window.__pcMotivos || [''])[0]); });
    }
  });
})();
"""
