"""RESERVA WEB (fase 1, sep-2026). Páginas públicas del dominio de marca:

- GET  /canchas                    → catálogo de canchas verificadas (por país).
- GET  /reservar/{cancha_id}       → fecha, horarios libres, precio, datos y pago.
- GET  /web/disponibilidad/{id}    → JSON de slots del día (precio, ocupado).
- POST /web/asegurar               → toma los slots (INSERT 'nueva', hold 10 min).
- POST /web/pagar                  → cargo Culqi con el token del Checkout →
                                     confirma, liquida al dueño y avisa.
- POST /web/liberar                → el cliente cerró sin pagar: libera el hold.
- GET  /reserva/{id}               → comprobante (por id o por grupo).

Misma base y mismas reglas que el APK: las filas van a `pichangol_reservas`
con el esquema que lee el dueño en su app, el UNIQUE del slot evita la doble
reserva, la contabilidad usa `/pagos/liquidacion-online` (billetera-first) y
el dueño recibe el push "Nueva reserva 📅".

MULTI-PAÍS: el cobro web sale sólo en soles (Culqi). Canchas en \$ o Bs
muestran el detalle y mandan a reservar por la app (PayPhone / Libélula).
"""

from __future__ import annotations

import hashlib
import hmac
import html as _html
import json
import time
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import config
from paises import pais_de_coordenadas, moneda_de_pais, simbolo_de_moneda
from pagos import culqi
from web import datos, horarios

router = APIRouter()

PLAY_URL = "https://play.google.com/store/apps/details?id=pe.ebim.pichangol"
DIAS_ADELANTE = 30
MAX_SLOTS = 4
DEPORTES = {"futbol": "Fútbol", "tenis": "Tenis", "padel": "Pádel",
            "pickleball": "Pickleball", "voley": "Vóley", "basquet": "Básquet"}
BANDERA = {"PE": "🇵🇪", "EC": "🇪🇨", "BO": "🇧🇴"}
NOMBRE_PAIS = {"PE": "Perú", "EC": "Ecuador", "BO": "Bolivia"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _e(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


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


def _deporte_nombre(clave: str) -> str:
    return DEPORTES.get((clave or "").lower(), (clave or "Deporte").capitalize())


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


def _foto(c: dict) -> str:
    u = (c.get("foto_url") or "").strip()
    if not u and c.get("fotos"):
        u = str(c["fotos"][0]).strip()
    if u.startswith("http"):
        return f'<img src="{_e(u)}" alt="{_e(c.get("nombre"))}" loading="lazy">'
    dep = (c.get("deporte") or "").lower()
    emoji = {"futbol": "⚽", "tenis": "🎾", "padel": "🏓", "pickleball": "🏓",
             "voley": "🏐", "basquet": "🏀"}.get(dep, "🏟️")
    return f'<div class="sinfoto">{emoji}</div>'


# ── HTML ──────────────────────────────────────────────────────────────────────

_CSS = """
:root{--lima:#AEEA94;--lima-suave:#E9F9E0;--bosque:#14463A;--tinta:#3b4a45;--texto:#222;--tenue:#667;--borde:#E4E4E4}
*{box-sizing:border-box}body{margin:0;font-family:"DM Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#F7F8F6;color:var(--texto)}
a{color:var(--bosque)}.wrap{max-width:980px;margin:0 auto;padding:0 18px}
header.nav{background:#fff;border-bottom:1px solid var(--borde);position:sticky;top:0;z-index:5}
.nav-in{display:flex;align-items:center;justify-content:space-between;height:58px}
.brand{font-weight:800;font-size:19px;color:var(--bosque);text-decoration:none;display:flex;align-items:center;gap:8px}
.dot{width:14px;height:14px;border-radius:50%;border:3px solid var(--bosque);display:inline-block;position:relative}
.dot::after{content:"";position:absolute;inset:2px;border-radius:50%;background:var(--lima)}
.links a{margin-left:16px;text-decoration:none;font-weight:600;font-size:14px;color:var(--tinta)}
h1{font-size:26px;margin:26px 0 6px}h2{font-size:20px;margin:22px 0 10px;color:var(--bosque)}
.sub{color:var(--tenue);margin:0 0 18px;font-size:15px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.grid{grid-template-columns:1fr}}
.card{background:#fff;border-radius:18px;box-shadow:0 2px 12px rgba(0,0,0,.06);overflow:hidden;display:flex;flex-direction:column}
.card img,.card .sinfoto{width:100%;height:160px;object-fit:cover;display:block}
.sinfoto{background:linear-gradient(135deg,#AEEA94,#7CC96F);display:flex;align-items:center;justify-content:center;font-size:56px}
.cb{padding:14px 16px 16px;display:flex;flex-direction:column;gap:4px;flex:1}
.cb h3{margin:0;font-size:16.5px;color:var(--bosque)}.cb .m{font-size:13px;color:var(--tenue)}
.precio{font-weight:800;font-size:17px;margin-top:6px}.precio small{font-weight:600;color:var(--tenue);font-size:12px}
.cta{display:inline-block;background:var(--lima);color:var(--bosque);font-weight:800;padding:12px 20px;border-radius:14px;text-decoration:none;border:0;cursor:pointer;font-size:15px;text-align:center}
.cta.sec{background:#fff;border:1px solid var(--borde);color:var(--bosque)}.cta:disabled{opacity:.55;cursor:default}
.chip{display:inline-flex;align-items:center;gap:6px;background:#fff;border:1px solid var(--borde);border-radius:22px;padding:9px 14px;font-weight:700;font-size:14px;cursor:pointer;box-shadow:0 1px 4px rgba(0,0,0,.05);user-select:none}
.chip.sel{background:#EBEBEB;border-color:#D6D6D6}.chip.off{opacity:.38;cursor:not-allowed;text-decoration:line-through}
.chip small{font-weight:600;color:var(--tenue)}.chips{display:flex;flex-wrap:wrap;gap:10px}
.panel{background:#fff;border-radius:18px;box-shadow:0 2px 12px rgba(0,0,0,.06);padding:18px 20px;margin:14px 0}
label{display:block;font-size:13px;font-weight:700;color:var(--bosque);margin:12px 0 5px}
input,select{width:100%;padding:12px;border:1px solid var(--borde);border-radius:12px;font-size:15px;font-family:inherit;background:#fff}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:560px){.row{grid-template-columns:1fr}}
.tot{display:flex;justify-content:space-between;align-items:center;font-weight:800;font-size:19px;margin-top:14px}
.aviso{background:var(--lima-suave);border:1px solid var(--lima);border-radius:12px;padding:12px 14px;font-size:14px;margin-top:10px}
.err{background:#FDECEC;border:1px solid #F5B5B5;border-radius:12px;padding:12px 14px;font-size:14px;margin-top:10px;display:none}
.pill{display:inline-block;background:var(--lima-suave);color:var(--bosque);font-weight:700;font-size:12.5px;padding:5px 10px;border-radius:12px}
footer{margin:40px 0 24px;color:var(--tenue);font-size:13px;text-align:center}footer a{margin:0 6px}
.hero{display:grid;grid-template-columns:1.1fr 1fr;gap:18px;align-items:start}@media(max-width:760px){.hero{grid-template-columns:1fr}}
.hero img,.hero .sinfoto{width:100%;height:240px;border-radius:18px;object-fit:cover}
ul.datos{list-style:none;padding:0;margin:8px 0 0;font-size:14px;color:var(--tinta)}ul.datos li{margin:4px 0}
.paso{display:flex;align-items:center;gap:10px;font-weight:800;color:var(--bosque);margin:18px 0 8px}
.paso span{background:var(--bosque);color:#fff;border-radius:50%;width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;font-size:13px}
.ok{background:var(--lima-suave);border:1px solid var(--lima);border-radius:18px;padding:22px;text-align:center}
.ok h1{margin-top:0}.tabla{width:100%;border-collapse:collapse;font-size:14px;margin-top:10px}.tabla td{padding:7px 4px;border-bottom:1px solid var(--borde)}
"""


def _shell(titulo: str, cuerpo: str, extra_head: str = "", desc: str = "") -> HTMLResponse:
    page = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_e(titulo)} · Pichangol</title>"
        f"<meta name='description' content='{_e(desc or titulo)}'>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link href='https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700;9..40,800&display=swap' rel='stylesheet'>"
        f"<style>{_CSS}</style>{extra_head}</head><body>"
        "<header class='nav'><div class='wrap nav-in'>"
        "<a class='brand' href='/'><span class='dot'></span> Pichangol</a>"
        "<nav class='links'><a href='/canchas'>Canchas</a><a href='/#servicios'>Servicios</a>"
        "<a href='/#contacto'>Contacto</a></nav></div></header>"
        f"<main class='wrap'>{cuerpo}</main>"
        "<footer>GRUPO EBIM S.A.C. · RUC 20602517986 · "
        "<a href='/#terminos'>Términos</a><a href='/#devoluciones'>Cancelaciones</a>"
        "<a href='/legal/privacidad'>Privacidad</a><a href='/#reclamaciones'>Libro de Reclamaciones</a>"
        "</footer></body></html>")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


# ── catálogo ──────────────────────────────────────────────────────────────────

@router.get("/canchas", response_class=HTMLResponse)
def pagina_canchas(deporte: str = "") -> HTMLResponse:
    todas = datos.canchas_verificadas()
    dep = (deporte or "").strip().lower()
    if dep:
        todas = [c for c in todas
                 if (c.get("deporte") or "").lower() == dep
                 or dep in [str(x).lower() for x in c.get("deportes") or []]]
    por_pais: dict[str, list[dict]] = {}
    for c in todas:
        por_pais.setdefault(_pais_de(c), []).append(c)
    filtros = "".join(
        f"<a class='chip{' sel' if dep == k else ''}' href='/canchas?deporte={k}'>{v}</a>"
        for k, v in DEPORTES.items() if any(
            (c.get("deporte") or "").lower() == k or k in [str(x).lower() for x in c.get("deportes") or []]
            for c in datos.canchas_verificadas()))
    cuerpo = ("<h1>Reserva tu cancha</h1>"
              "<p class='sub'>Canchas verificadas por Pichangol. Elige, mira los horarios "
              "libres y paga en línea. Recibes tu comprobante al instante.</p>"
              f"<div class='chips'><a class='chip{' sel' if not dep else ''}' href='/canchas'>Todas</a>{filtros}</div>")
    if not todas:
        cuerpo += ("<div class='panel'>Todavía no hay canchas publicadas para este filtro. "
                   f"Descárgate la app para ver todas: <a href='{PLAY_URL}'>Pichangol en Google Play</a>.</div>")
    for pais in ("PE", "EC", "BO"):
        lst = por_pais.get(pais) or []
        if not lst:
            continue
        cards = ""
        for c in lst:
            sim, _iso = _moneda_de(c)
            lugar = ", ".join(x for x in (c.get("barrio"), c.get("distrito").replace("_", " ").title()) if x)
            cards += (f"<div class='card'>{_foto(c)}<div class='cb'>"
                      f"<h3>{_e(c['nombre'])}</h3>"
                      f"<div class='m'>{_e(c.get('club'))}{' · ' if c.get('club') else ''}{_e(lugar)}</div>"
                      f"<div class='m'>{_deporte_nombre(c.get('deporte'))} · turnos de {c['duracion_slot_min']} min</div>"
                      f"<div class='precio'>{_e(sim)} {c['precio_hora']:.2f} <small>por hora</small></div>"
                      f"<a class='cta' href='/reservar/{_e(c['id'])}'>Ver horarios y reservar</a></div></div>")
        cuerpo += f"<h2>{BANDERA[pais]} {NOMBRE_PAIS[pais]}</h2><div class='grid'>{cards}</div>"
    return _shell("Canchas", cuerpo, desc="Reserva canchas de fútbol, tenis y pádel en línea.")


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
        })
    return out


@router.get("/web/disponibilidad/{cancha_id}")
def disponibilidad(cancha_id: str, fecha: str = "") -> dict:
    c = datos.cancha(cancha_id)
    if not c:
        return {"ok": False, "error": "no_encontrada"}
    d_min, d_max = _fechas_validas(_pais_de(c))
    if not fecha or not (d_min <= fecha <= d_max):
        return {"ok": False, "error": "fecha_fuera_de_rango", "min": d_min, "max": d_max}
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return {"ok": False, "error": "fecha_invalida"}
    sim, iso = _moneda_de(c)
    return {"ok": True, "fecha": fecha, "moneda": sim, "moneda_iso": iso,
            "slots": _slots_del_dia(c, fecha)}


# ── página de reserva ─────────────────────────────────────────────────────────

_JS_RESERVA = r"""
(function(){
  var C = window.__cancha, sel = {}, slots = [];
  var $ = function(id){ return document.getElementById(id); };
  var fmt = function(n){ return C.moneda + ' ' + Number(n).toFixed(2); };
  function total(){
    var t = 0; Object.keys(sel).forEach(function(k){ t += sel[k].precio; });
    document.querySelectorAll('input[name=extra]:checked').forEach(function(x){ t += parseFloat(x.value)||0; });
    return t;
  }
  function pintarTotal(){
    var n = Object.keys(sel).length;
    $('tot').textContent = fmt(total());
    $('btnPagar').disabled = !n;
    $('btnPagar').textContent = n ? ('Reservar y pagar ' + fmt(total())) : 'Elige un horario';
  }
  function cargar(){
    var f = $('fecha').value; sel = {}; pintarTotal();
    $('slots').innerHTML = '<span class="m">Cargando horarios…</span>';
    fetch('/web/disponibilidad/' + encodeURIComponent(C.id) + '?fecha=' + f)
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){ $('slots').innerHTML = '<span class="m">No pudimos cargar los horarios de ese día.</span>'; return; }
        slots = j.slots;
        if(!slots.length){ $('slots').innerHTML = '<span class="m">No quedan turnos para este día. Prueba otra fecha.</span>'; return; }
        $('slots').innerHTML = slots.map(function(s, i){
          var cls = 'chip' + (s.ocupado ? ' off' : '');
          var extra = s.fecha !== f ? ' <small>(' + s.fecha.slice(5).split('-').reverse().join('/') + ')</small>' : '';
          return '<span class="' + cls + '" data-i="' + i + '">' + s.hora + '–' + s.fin + extra +
                 ' <small>' + fmt(s.precio) + (s.valle ? ' · hora feliz' : '') + '</small></span>';
        }).join('');
        document.querySelectorAll('#slots .chip').forEach(function(el){
          el.addEventListener('click', function(){
            var s = slots[parseInt(el.dataset.i)];
            if(s.ocupado) return;
            var k = s.fecha + '|' + s.hora;
            if(sel[k]){ delete sel[k]; el.classList.remove('sel'); }
            else {
              if(Object.keys(sel).length >= C.maxSlots){ mostrarError('Puedes reservar hasta ' + C.maxSlots + ' turnos por pedido.'); return; }
              sel[k] = s; el.classList.add('sel');
            }
            pintarTotal();
          });
        });
      }).catch(function(){ $('slots').innerHTML = '<span class="m">No pudimos cargar los horarios.</span>'; });
  }
  function mostrarError(m){ var e = $('err'); e.textContent = m; e.style.display = 'block'; e.scrollIntoView({behavior:'smooth', block:'center'}); }
  function ocultarError(){ $('err').style.display = 'none'; }
  function datos(){
    return { nombre: $('nombre').value.trim(), celular: $('celular').value.trim(), email: $('email').value.trim().toLowerCase() };
  }
  function validar(d){
    if(d.nombre.length < 3) return 'Escribe tu nombre.';
    if(d.celular.replace(/\D/g,'').length < 8) return 'Escribe un celular válido.';
    if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email)) return 'Escribe un correo válido (ahí va tu comprobante).';
    if(!Object.keys(sel).length) return 'Elige al menos un horario.';
    return '';
  }
  var hold = null;
  function liberar(){
    if(!hold) return;
    var h = hold; hold = null;
    fetch('/web/liberar', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ids: h.ids, firma: h.firma})}).catch(function(){});
  }
  $('btnPagar').addEventListener('click', function(){
    ocultarError();
    var d = datos(), v = validar(d); if(v){ mostrarError(v); return; }
    var extras = Array.prototype.map.call(document.querySelectorAll('input[name=extra]:checked'), function(x){ return x.dataset.clave; });
    var horas = Object.keys(sel).map(function(k){ return {fecha: sel[k].fecha, hora: sel[k].hora}; });
    $('btnPagar').disabled = true; $('btnPagar').textContent = 'Reservando tu horario…';
    fetch('/web/asegurar', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({cancha_id: C.id, horas: horas, extras: extras, nombre: d.nombre, celular: d.celular, email: d.email})})
      .then(function(r){ return r.json(); })
      .then(function(j){
        if(!j.ok){
          pintarTotal();
          if(j.error === 'ocupado'){ mostrarError('Alguien acaba de tomar uno de esos horarios. Elige otro, por favor.'); cargar(); }
          else mostrarError('No pudimos reservar el horario. Inténtalo de nuevo.');
          return;
        }
        hold = j;
        if(!C.pk){ mostrarError('El pago en línea no está disponible por ahora.'); liberar(); pintarTotal(); return; }
        Culqi.publicKey = C.pk;
        Culqi.settings({ title: 'Pichangol', currency: 'PEN', amount: j.total_centimos });
        Culqi.options({ lang: 'es', installments: false,
          paymentMethods: { tarjeta: true, yape: true, bancaMovil: false, agente: false, billetera: false, cuotealo: false },
          style: { logo: C.logo, bannerColor: '#14463A', buttonBackground: '#AEEA94', buttonText: 'Pagar ' + fmt(j.total), buttonTextColor: '#14463A' } });
        window.culqi = function(){
          if(Culqi.token){
            var token = Culqi.token.id, medio = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
            Culqi.close();
            $('btnPagar').textContent = 'Confirmando tu pago…';
            var h = hold; hold = null;
            fetch('/web/pagar', {method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({ids: h.ids, firma: h.firma, token: token, medio: medio, email: d.email})})
              .then(function(r){ return r.json(); })
              .then(function(p){
                if(p.ok){ window.location.href = p.url; }
                else { hold = h; mostrarError(p.mensaje || 'El pago no se pudo procesar. No se te cobró nada.'); pintarTotal(); }
              }).catch(function(){ hold = h; mostrarError('No pudimos confirmar el pago. Escríbenos con tu correo y horario.'); pintarTotal(); });
          } else if(Culqi.order){
            mostrarError('Este medio de pago no está habilitado. Usa Yape o tarjeta.');
          } else {
            mostrarError((Culqi.error && Culqi.error.user_message) || 'No se pudo procesar el pago.');
          }
        };
        Culqi.open();
        // Si cierra el checkout sin pagar, el horario se libera al toque.
        var chk = setInterval(function(){
          var abierto = document.getElementById('culqi-container') || document.querySelector('iframe[src*="culqi"]');
          if(!abierto && hold){ clearInterval(chk); liberar(); pintarTotal(); }
          if(!hold) clearInterval(chk);
        }, 1500);
      }).catch(function(){ pintarTotal(); mostrarError('No pudimos reservar el horario. Inténtalo de nuevo.'); });
  });
  document.querySelectorAll('input[name=extra]').forEach(function(x){ x.addEventListener('change', pintarTotal); });
  $('fecha').addEventListener('change', function(){ liberar(); cargar(); });
  window.addEventListener('beforeunload', liberar);
  cargar();
})();
"""


@router.get("/reservar/{cancha_id}", response_class=HTMLResponse)
def pagina_reservar(cancha_id: str) -> HTMLResponse:
    c = datos.cancha(cancha_id)
    if not c or not c.get("verificada") or c.get("eliminada") or not c.get("dueno"):
        return _shell("Cancha no disponible",
                      "<h1>Cancha no disponible</h1><p class='sub'>Esta cancha no está "
                      "publicada para reservas en línea.</p><a class='cta' href='/canchas'>Ver canchas</a>")
    sim, iso = _moneda_de(c)
    pais = _pais_de(c)
    d_min, d_max = _fechas_validas(pais)
    lugar = ", ".join(x for x in (c.get("direccion"), c.get("distrito").replace("_", " ").title()) if x)
    extras_html = ""
    if c.get("servicios_extra"):
        filas = ""
        for s in c["servicios_extra"]:
            clave = str(s.get("clave") or "")
            nombre = {"arbitro": "Árbitro", "pelotero": "Pelotero", "pelota": "Alquiler de pelota",
                      "pecheras": "Petos / pecheras", "hidratacion": "Hidratación"}.get(clave, clave.capitalize())
            try:
                precio = float(s.get("precio") or 0)
            except (TypeError, ValueError):
                precio = 0.0
            if precio <= 0 or not clave:
                continue
            filas += (f"<label style='display:flex;gap:10px;align-items:center;font-weight:600'>"
                      f"<input type='checkbox' name='extra' value='{precio:.2f}' data-clave='{_e(clave)}' style='width:auto'>"
                      f"{_e(nombre)} <small style='color:var(--tenue)'>+ {_e(sim)} {precio:.2f}</small></label>")
        if filas:
            extras_html = f"<div class='paso'><span>3</span> Servicios extra (opcional)</div>{filas}"

    cab = (f"<div class='hero'><div>{_foto(c)}</div><div>"
           f"<span class='pill'>{BANDERA[pais]} {_deporte_nombre(c.get('deporte'))} · verificada ✓</span>"
           f"<h1 style='margin-top:10px'>{_e(c['nombre'])}</h1>"
           f"<p class='sub' style='margin-bottom:6px'>{_e(c.get('club'))}</p>"
           f"<ul class='datos'><li>📍 {_e(lugar or 'Dirección en la app')}</li>"
           f"<li>🕒 {_e(c['hora_apertura'])} a {_e(c['hora_cierre'])} · turnos de {c['duracion_slot_min']} min</li>"
           f"<li>💵 <b>{_e(sim)} {c['precio_hora']:.2f}</b> por hora"
           + (f" · hora feliz −{c['descuento_valle']}% de {_e(c['valle_desde'] or '00:00')} a {_e(c['valle_hasta'] or '12:00')}" if c['descuento_valle'] > 0 else "")
           + "</li>"
           + (f"<li>🏟️ {_e(c['superficie'])}</li>" if c.get("superficie") else "")
           + "</ul></div></div>")

    if not _pago_web_disponible(iso):
        motivo = ("Esta cancha cobra en " + _e(sim) + " y el pago en línea desde la web está "
                  "disponible por ahora solo en soles." if iso != "PEN" else
                  "El pago en línea desde la web se está habilitando.")
        cuerpo = (cab + f"<div class='panel'><h2 style='margin-top:0'>Reserva desde la app</h2>"
                  f"<p>{motivo} Desde la app Pichangol reservas y pagas con los medios de tu país.</p>"
                  f"<a class='cta' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a> "
                  "<a class='cta sec' href='/canchas'>Ver otras canchas</a></div>")
        return _shell(c["nombre"], cuerpo)

    cfg = json.dumps({"id": c["id"], "moneda": sim, "pk": config.CULQI_PUBLIC_KEY,
                      "maxSlots": MAX_SLOTS, "logo": ""})
    cuerpo = (cab +
              "<div class='panel'>"
              "<div class='paso'><span>1</span> Elige el día y el horario</div>"
              f"<input type='date' id='fecha' value='{d_min}' min='{d_min}' max='{d_max}'>"
              f"<div class='m' style='margin:8px 0 10px;font-size:13px;color:var(--tenue)'>Hasta {MAX_SLOTS} turnos por pedido. "
              "Los horarios marcados con (fecha) son de la madrugada del día siguiente.</div>"
              "<div class='chips' id='slots'></div>"
              "<div class='paso'><span>2</span> Tus datos</div>"
              "<div class='row'><div><label for='nombre'>Nombre y apellido</label><input id='nombre' autocomplete='name' maxlength='80'></div>"
              "<div><label for='celular'>Celular</label><input id='celular' inputmode='tel' autocomplete='tel' maxlength='20'></div></div>"
              "<label for='email'>Correo (para tu comprobante)</label><input id='email' type='email' autocomplete='email' maxlength='120'>"
              f"{extras_html}"
              "<div class='tot'><span>Total</span><span id='tot'></span></div>"
              "<div class='aviso'>Pagas con <b>Yape o tarjeta</b> a través de Culqi. Tu reserva queda confirmada al instante "
              "y el local la ve en su agenda. Cancelación con más de 6 horas de anticipación: devolución del 100 %. "
              "<a href='/#devoluciones'>Ver política</a>.</div>"
              "<div class='err' id='err'></div>"
              "<div style='margin-top:14px'><button class='cta' id='btnPagar' disabled>Elige un horario</button></div>"
              "</div>"
              f"<script>window.__cancha={cfg};</script>"
              "<script src='https://checkout.culqi.com/js/v4'></script>"
              f"<script>{_JS_RESERVA}</script>")
    return _shell(f"Reservar {c['nombre']}", cuerpo,
                  desc=f"Reserva {c['nombre']} y paga en línea con Yape o tarjeta.")


# ── asegurar / pagar / liberar ────────────────────────────────────────────────

class HoraReq(BaseModel):
    fecha: str
    hora: str


class AsegurarReq(BaseModel):
    cancha_id: str
    horas: list[HoraReq]
    extras: list[str] = []
    nombre: str
    celular: str = ""
    email: str


_contador = {"n": 0}


def _nuevo_id() -> str:
    _contador["n"] = (_contador["n"] + 1) % 100000
    return f"{datos.PREFIJO_ID_WEB}{int(time.time() * 1000)}_{_contador['n']}"


@router.post("/web/asegurar")
def asegurar(req: AsegurarReq) -> dict:
    """Toma los slots (INSERT 'nueva') ANTES de cobrar, igual que el APK
    (`insertarSegura`): así el UNIQUE decide quién se queda con la hora. Si el
    cliente no paga, `/web/liberar` (o el vencimiento del hold) los suelta."""
    c = datos.cancha(req.cancha_id)
    if not c or not c.get("verificada") or c.get("eliminada") or not c.get("dueno"):
        return {"ok": False, "error": "no_encontrada"}
    sim, iso = _moneda_de(c)
    if not _pago_web_disponible(iso):
        return {"ok": False, "error": "pago_no_disponible"}
    nombre = req.nombre.strip()[:80]
    email = req.email.strip().lower()[:120]
    if len(nombre) < 3 or "@" not in email:
        return {"ok": False, "error": "datos_invalidos"}
    if not req.horas or len(req.horas) > MAX_SLOTS:
        return {"ok": False, "error": "horas_invalidas"}
    datos.liberar_holds_vencidos(c["id"])
    pais = _pais_de(c)
    # Recalcular precio y validar cada hora contra la grilla real del día.
    pedidos = {(h.fecha, h.hora) for h in req.horas}
    fechas_base = sorted({h.fecha for h in req.horas})
    validos: dict[tuple[str, str], dict] = {}
    for fb in fechas_base + [(date.fromisoformat(fb) - timedelta(days=1)).isoformat()
                             for fb in fechas_base if _es_iso(fb)]:
        if not _es_iso(fb):
            return {"ok": False, "error": "fecha_invalida"}
        d_min, d_max = _fechas_validas(pais)
        if not (d_min <= fb <= d_max):
            continue
        for s in _slots_del_dia(c, fb):
            validos[(s["fecha"], s["hora"])] = s
    filas, total = [], 0
    hoy = horarios.ahora_local(pais).date()
    grupo = f"grp_web_{int(time.time() * 1000)}" if len(pedidos) > 1 else ""
    extras_ok = []
    if req.extras:
        cat = {str(s.get("clave")): float(s.get("precio") or 0) for s in c.get("servicios_extra") or []}
        for k in req.extras:
            if k in cat and cat[k] > 0:
                extras_ok.append({"clave": k, "precio": cat[k]})
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
            "usuario": email, "deporte": "", "moneda": sim,
            "extras": extras_ok if i == 0 else [],
            "telefono": req.celular.strip()[:20], "grupo_reserva_id": grupo,
            "medio_pago": "web_hold",
        })
    total_extras = sum(x["precio"] for x in extras_ok)
    total = int(round(total + total_extras))
    if total < 1:
        return {"ok": False, "error": "monto_invalido"}
    r = datos.insertar_reservas(filas)
    if r:
        return {"ok": False, "error": r}
    ids = [f["id"] for f in filas]
    return {"ok": True, "ids": ids, "grupo": grupo, "firma": _firma(ids),
            "total": total, "total_centimos": total * 100, "moneda": sim,
            "hold_segundos": datos.HOLD_SEGUNDOS}


def _es_iso(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


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
def pagar(req: PagarReq) -> dict:
    """Cobra con Culqi el TOTAL del bloque asegurado y confirma las filas.
    Fallo del cargo → las filas se liberan y no se cobró nada. Éxito →
    confirmada + pagado + liquidación al dueño (billetera-first) + push."""
    if not _firma_ok(req.ids, req.firma):
        return {"ok": False, "error": "firma", "mensaje": "La sesión de pago venció. Vuelve a elegir el horario."}
    filas = datos.reservas_de(req.ids)
    if not filas or len(filas) != len(req.ids):
        return {"ok": False, "error": "hold_vencido",
                "mensaje": "El horario ya no está reservado para ti (pasaron más de 10 minutos). Vuelve a elegirlo."}
    if all(f.get("pagado") for f in filas):
        return {"ok": True, "url": _url_comprobante(filas)}
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim, iso = _moneda_de(c) if c else ("S/", "PEN")
    total = sum(int(f["precio"]) for f in filas)
    total += int(round(sum(float(x.get("precio") or 0) for f in filas for x in (f.get("extras") or []))))
    email = (req.email or filas[0].get("usuario") or "").strip().lower()
    concepto = f"Reserva {c.get('nombre', 'cancha')} {filas[0]['fecha']} {filas[0]['hora_inicio']}"
    cargo = culqi.crear_cargo(
        token=req.token.strip(), monto_centimos=total * 100, email=email,
        descripcion=concepto[:80], moneda=iso,
        metadata={"canal": "web", "reserva_id": filas[0]["id"], "cancha_id": filas[0]["cancha_id"]})
    if not cargo.get("ok"):
        datos.borrar_reservas(req.ids)
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada; "
                           "el horario quedó libre para que lo intentes de nuevo." + (f" ({msg[:80]})" if msg else "")}
    medio = "yape" if req.medio == "yape" else "tarjeta"
    datos.confirmar_reservas(req.ids, medio)
    # Contabilidad y aviso al dueño: mismos caminos que una reserva online del APK.
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


def _url_comprobante(filas: list[dict]) -> str:
    g = (filas[0].get("grupo_reserva_id") or "").strip()
    return f"/reserva/{g if g else filas[0]['id']}"


# ── comprobante ───────────────────────────────────────────────────────────────

@router.get("/reserva/{ref}", response_class=HTMLResponse)
def pagina_comprobante(ref: str) -> HTMLResponse:
    filas = datos.reservas_por_grupo(ref) if ref.startswith("grp_") else datos.reservas_de([ref])
    filas = [f for f in filas if f.get("pagado") or f.get("estado") == "confirmada"]
    if not filas:
        return _shell("Reserva no encontrada",
                      "<h1>Reserva no encontrada</h1><p class='sub'>Revisa el enlace de tu comprobante "
                      "o escríbenos a contacto@ebim.pe.</p><a class='cta' href='/canchas'>Ver canchas</a>")
    c = datos.cancha(filas[0]["cancha_id"]) or {}
    sim = filas[0].get("moneda") or "S/"
    total = sum(int(f["precio"]) for f in filas)
    extras = [x for f in filas for x in (f.get("extras") or [])]
    total += int(round(sum(float(x.get("precio") or 0) for x in extras)))
    horas = "".join(f"<tr><td>{horarios.fecha_larga(f['fecha'])}</td><td>{_e(f['hora_inicio'])}–{_e(f['hora_fin'])}</td>"
                    f"<td style='text-align:right'>{_e(sim)} {int(f['precio']):.2f}</td></tr>" for f in filas)
    horas += "".join(f"<tr><td colspan='2'>Extra: {_e(x.get('clave'))}</td>"
                     f"<td style='text-align:right'>{_e(sim)} {float(x.get('precio') or 0):.2f}</td></tr>" for x in extras)
    lugar = ", ".join(x for x in (c.get("direccion"), (c.get("distrito") or "").replace("_", " ").title()) if x)
    cuerpo = (f"<div class='ok'><h1>¡Reserva confirmada! ✅</h1>"
              f"<p>Comprobante <b>{_e(ref)}</b> · pagado por {_e(filas[0].get('medio_pago') or 'web')}</p>"
              f"<p>Te esperamos en <b>{_e(c.get('nombre') or 'la cancha')}</b>{(' · ' + _e(c.get('club'))) if c.get('club') else ''}"
              f"{(' · ' + _e(lugar)) if lugar else ''}.</p></div>"
              f"<div class='panel'><table class='tabla'>{horas}"
              f"<tr><td colspan='2'><b>Total pagado</b></td><td style='text-align:right'><b>{_e(sim)} {total:.2f}</b></td></tr></table>"
              f"<p class='sub' style='margin-top:12px'>A nombre de {_e(filas[0].get('jugador'))} · {_e(filas[0].get('usuario'))}. "
              "Guarda este enlace: es tu comprobante. Para cancelar con devolución (más de 6 horas antes) "
              "escríbenos a <a href='mailto:contacto@ebim.pe'>contacto@ebim.pe</a> con este número.</p>"
              f"<a class='cta' href='{PLAY_URL}'>Descarga la app y lleva tus reservas contigo</a> "
              "<a class='cta sec' href='/canchas'>Reservar otra cancha</a></div>")
    return _shell("Reserva confirmada", cuerpo)
