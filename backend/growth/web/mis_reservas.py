"""MIS RESERVAS en la web (= "Viajes" de Airbnb): `GET /mis-reservas`, con
la tarjeta de cada reserva, la lista de espera y los estados visibles.

Movido tal cual desde `web/router.py`, que lo re-exporta.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import empresa
from paises import simbolo_de_moneda
from web import datos, horarios, miniaturas, sesion, ui
from pagos import cobro_directo as _cd
from web import dividir_pago as _dividir_web
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)
from web.comun import PLAY_URL, _deporte, _fotos, _moneda_de, _pais_de
from web.ficha import _titulo_local
from web.cancelacion import JS_CANCELAR, _MODAL_CANCELAR, _boton_cancelar

router = APIRouter()


# ── comprobante ───────────────────────────────────────────────────────────────

# Motivos con los que el club rechaza un comprobante (selección en "Pagos por
# confirmar"); un motivo libre de APKs viejos se muestra tal cual.
MOTIVO_RECHAZO = {"no_llego": "El club no recibió el pago.", "monto": "El monto no coincide con la reserva.",
                  "ilegible": "No se pudo leer el comprobante.", "otro": "El club no pudo confirmarlo."}

ESTADO_RESERVA = {"confirmada": ("Confirmada", "ok"), "cancelada": ("Cancelada", "bad"), "noShow": ("No asististe", "bad"),
                  "nueva": ("Pendiente de pago", "warn"), "completada": ("Jugada", "ok")}


def _seccion_espera(email: str) -> str:
    """Mis turnos en LISTA DE ESPERA (Mis reservas): ir a la ficha o salir."""
    from web import jugador_espera as _je
    lst = _je.mias(email)
    if not lst:
        return ""
    filas = ""
    datos.canchas_por_ids([x["cancha_id"] for x in lst])  # una consulta; `cancha()` lee de la memoria
    for x in lst:
        c = datos.cancha(x["cancha_id"]) or {}
        filas += (f"<div class='esp-fila'><span class='em'>🔔</span><div style='min-width:0'><b>{e(_titulo_local(c) if c else 'Cancha')}</b>"
                  f"<div class='sub' style='margin:0;font-size:13px'>{e(c.get('nombre') or '')} · {e(horarios.fecha_larga(x['fecha']))} · {e(x['hora'])}</div></div>"
                  f"<a class='btn sec' href='/reservar/{quote(x['cancha_id'], safe='')}?fecha={e(x['fecha'])}'>Ver</a>"
                  f"<button type='button' class='btn sec' data-esp-salir='{e(json.dumps(x))}'>Salir</button></div>")
    return ("<details class='viajes-det' open><summary><span class='ico'>🔔</span> Lista de espera <small>· " + str(len(lst)) + "</small></summary>"
            "<p class='sub' style='font-size:12.5px;padding:4px 4px 6px;margin:0'>Si alguno de estos turnos se libera, te llega un aviso. "
            "Lo reserva el primero que entre.</p>" + filas +
            "<style>.esp-fila{display:flex;align-items:center;gap:10px;padding:10px 4px;border-top:1px solid var(--trazo)}"
            ".esp-fila>div{flex:1}.esp-fila .em{font-size:20px}.esp-fila .btn{padding:8px 12px;font-size:13px;flex:none}</style>"
            "<script>document.addEventListener('click',function(ev){var b=ev.target.closest('[data-esp-salir]');if(!b)return;"
            "fetch('/web/espera/salir',{method:'POST',headers:{'Content-Type':'application/json'},body:b.dataset.espSalir})"
            ".then(function(r){return r.json();}).then(function(j){if(j.ok){b.closest('.esp-fila').remove();if(window.pcgToast)pcgToast('Saliste de la lista de espera');}});});</script>"
            "</details>")


def _jr_css() -> str:
    from web import jugador_resenas
    return jugador_resenas.CSS


def _jr_js() -> str:
    from web import jugador_resenas
    return jugador_resenas.js()


def _tarjeta_viaje(r: dict, c: dict | None, hoy: str, ses: dict | None, pago_club: dict | None = None,
                   mis_est: dict | None = None) -> str:
    """Tarjeta tipo "Viajes" de Airbnb: foto cuadrada · cancha · fecha y hora ·
    avatar del jugador · estado; clic = detalle/comprobante. Las próximas llevan
    "Cancelar"."""
    sim = r.get("moneda") or (c and _moneda_de(c)[0]) or "S/"
    estado = str(r.get("estado") or "")
    en_revision = estado == "nueva" and not r.get("pagado") and str(r.get("medio_pago") or "") == datos.MEDIO_HOLD_VOUCHER
    if estado == "noShow":
        pill = "<span class='pill bad'>No asististe</span>"
    elif en_revision:
        pill = "<span class='pill warn'>Pago en revisión del club</span>"
    elif r.get("pagado") and str(r.get("medio_pago") or "") == "bono":
        pill = "<span class='pill ok'>Pagada con bono 🎟️</span>"
    elif r.get("pagado"):
        pill = "<span class='pill ok'>Pagada</span>"
    else:
        pill = "<span class='pill warn'>Pagas en la cancha</span>"
    ref = r.get("grupo_reserva_id") or r.get("id")
    pasada = str(r.get("fecha") or "") < hoy
    nombre = (c or {}).get("nombre") or "Cancha"
    con_comprobante = bool(r.get("pagado") or estado == "confirmada" or en_revision)
    href = f"/reserva/{e(ref)}" if con_comprobante else (f"/reservar/{e(c['id'])}" if c else "#")
    fs = _fotos(c) if c else []
    if fs:
        foto = miniaturas.img(fs[0], sizes=miniaturas.SIZES_MINI, dims=False)
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
    cancelar = _boton_cancelar(filas_r, c, ses, "lnk") if (not pasada and not en_revision) else ""
    if pasada and c and mis_est is not None and estado not in ("noShow", "cancelada", "nueva"):
        from web import jugador_resenas as _jr
        cancelar = _jr.boton(c["id"], _titulo_local(c), int(mis_est.get(c["id"]) or 0))
    return (f"<a class='viaje{' pasada' if pasada else ''}' href='{href}' data-lat='{(c or {}).get('lat') or ''}' data-lng='{(c or {}).get('lng') or ''}' "
            f"data-nombre='{e(nombre)}' data-cuando='{e(cuando)}'>"
            f"<div class='vfoto'>{foto}</div>"
            f"<div class='vtxt'><b>{e(nombre)}</b><div class='sub' style='margin:2px 0 0;font-size:13.5px'>{e((c or {}).get('club') or '')}</div>"
            f"<div class='vcuando'>{cuando}</div>"
            f"<div class='vpie'>{avatar}{pill}<span class='vprecio'>"
            + (f"🎟️ {int(r.get('turnos') or 1)} h de bono" if str(r.get("medio_pago") or "") == "bono" else f"{e(sim)} {int(r.get('precio') or 0):.2f}")
            + "</span>"
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
                  f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir {MARCA} en Google Play</a></div></div>")
        return ui.shell("Mis reservas", cuerpo, sesion=None)
    email = ses["email"]
    from db.store import stores as _st
    filas = _agrupar_reservas(datos.reservas_de_usuario(email))
    # COBRO DIRECTO: comprobantes que subió el jugador (se leen antes para traer
    # sus canchas en la MISMA consulta que las de las reservas).
    vouchers = _cd.pagos_del_jugador(email)
    canchas = {cid: c for cid, c in datos.canchas_por_ids(
        [r.get("cancha_id") for r in filas] + [v.get("cancha_id") for v in vouchers]).items()
        if cid in {r.get("cancha_id") for r in filas}}
    # "Hoy" en la zona horaria del país de CADA cancha (Bolivia va una hora adelante de Perú).
    hoy_de = {cid: horarios.ahora_local(_pais_de(c) if c else "PE").date().isoformat() for cid, c in canchas.items()}
    hoy = horarios.ahora_local("PE").date().isoformat()
    def _hoy(r): return hoy_de.get(r.get("cancha_id")) or hoy
    proximas = sorted([r for r in filas if str(r.get("fecha") or "") >= _hoy(r)], key=lambda r: (r.get("fecha"), r.get("hora_inicio")))
    pasadas = [r for r in filas if str(r.get("fecha") or "") < _hoy(r)]
    # El botón "Cancelar" de cada próxima mira sus canjes (bono / puntos): todos
    # en dos consultas en vez de dos por reserva.
    datos.precargar_canjes_web([str(r.get("grupo_reserva_id") or "").strip() or str(r.get("id")) for r in proximas])
    datos.precargar_puntos_canjes(email)
    # Los comprobantes rechazados o vencidos (su reserva ya se soltó) se listan
    # aparte para que sepa qué pasó.
    refs_vivas = {str(r.get("grupo_reserva_id") or r.get("id")) for r in filas}
    # (Las partes de un PAGO DIVIDIDO van en su propia sección: su rechazo no suelta el horario.)
    caidos = [v for v in vouchers if v.get("estado") in ("rechazado", "vencido") and str(v.get("reserva_ref")) not in refs_vivas
              and not _dividir_web.es_ref(str(v.get("reserva_ref")))][:10]
    # Solo reservas: un pago devuelto de una matrícula o compra (pasarela $ / Bs) no es una cancha cancelada.
    canceladas = sorted([x for x in _st.cancelaciones_web if x.get("usuario") == email and (x.get("tipo") or "reserva") == "reserva"], key=lambda x: x.get("creado_en", ""), reverse=True)
    lista = "".join(_tarjeta_viaje(r, canchas.get(r.get("cancha_id")), _hoy(r), ses) for r in proximas) if proximas else (
        "<div class='viaje-vacio'><b>Todavía no tienes reservas próximas</b>"
        "<p class='sub'>Cuando reserves una cancha, aparecerá aquí con su mapa y su comprobante.</p>"
        "<a class='btn' href='/canchas'>Explorar canchas</a></div>")
    mis_est = datos.mis_resenas(email, list({str(r.get("cancha_id")) for r in pasadas})) if pasadas else {}
    pasadas_html = "".join(_tarjeta_viaje(r, canchas.get(r.get("cancha_id")), _hoy(r), ses, mis_est=mis_est) for r in pasadas)
    def _fila_voucher(v: dict) -> str:
        c_v = canchas.get(v.get("cancha_id")) or datos.cancha(str(v.get("cancha_id") or "")) or {}
        sim_v = simbolo_de_moneda(v.get("moneda") or "PEN")
        motivo = (MOTIVO_RECHAZO.get(v.get("motivo_rechazo") or "", v.get("motivo_rechazo") or "")
                  if v.get("estado") == "rechazado" else "El club no lo revisó a tiempo.")
        return (f"<div class='cancelada'><div><b>{e(c_v.get('nombre') or 'Cancha')}</b><div class='sub' style='font-size:13px;margin:0'>"
                f"{e(motivo)} El horario se liberó.</div></div>"
                f"<div style='text-align:right'><span class='pill bad'>{'Pago rechazado' if v.get('estado') == 'rechazado' else 'Pago vencido'}</span>"
                f"<div class='sub' style='font-size:12.5px;margin:4px 0 0'>{e(sim_v)} {int(v.get('monto_centimos') or 0) / 100:.2f}</div></div></div>")
    def _fila_cancel(x: dict) -> str:
        est = {"reembolsado": ("Devolución en camino", "ok"), "saldo": ("Devuelto a tu saldo", "ok"), "reembolsado_manual": ("Devuelto", "ok"),
               "manual": ("Devolución en proceso", "warn"), "fallo": ("Devolución en proceso", "warn"),
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
        + _seccion_espera(email)
        + _dividir_web.seccion_mis_reservas(email)
        + (f"<details class='viajes-det'><summary>Dónde has jugado <small>· {len(pasadas)}</small></summary><div class='viajes-cards'>{pasadas_html}</div></details>" if pasadas else "")
        + f"<details class='viajes-det'{' open' if canceladas else ''}><summary><span class='ico'>🗓️</span> Reservaciones canceladas <small>· {len(canceladas)}</small></summary>"
        + ("".join(_fila_cancel(x) for x in canceladas) if canceladas else "<p class='sub' style='padding:8px 4px 2px'>No has cancelado ninguna reserva.</p>")
        + "</details>"
        + (f"<details class='viajes-det' open><summary><span class='ico'>🧾</span> Pagos que el club no confirmó <small>· {len(caidos)}</small></summary>"
           + "".join(_fila_voucher(v) for v in caidos) + "<p class='sub' style='font-size:12.5px;padding:8px 4px 2px'>"
           "Si ya pagaste, escribe al local con tu comprobante: el dinero lo recibió el club.</p></details>" if caidos else "")
        + "<p class='sub' style='font-size:12.5px;margin-top:18px'>Cada club define su política de cancelación: la ves en la ficha de la cancha y en tu comprobante. "
        f"Dudas: <a href='mailto:{empresa.datos()['correo']}'>{empresa.datos()['correo']}</a>.</p>"
        "</div><aside class='viajes-mapa'><div class='mapa' id='mapaViajes' aria-label='Mapa de tus reservas'></div></aside></div>"
        + _MODAL_CANCELAR
        + (f"<style>{_jr_css()}</style><script>{_jr_js()}</script>" if pasadas else "")
        + "<script>" + JS_CANCELAR + r"""
(function(){
  try { var av = sessionStorage.getItem('pcg_aviso'); if(av){ var el = document.getElementById('avisoCancel'); el.textContent = av; el.style.display = 'block'; sessionStorage.removeItem('pcg_aviso'); } } catch(e){}
  // Fotos que faltan (canchas sembradas): la primera foto, como en el explorador.
  document.querySelectorAll('.viaje .sinfoto[data-buscar]').forEach(function(ph){
    var q = '/web/foto?id=' + encodeURIComponent(ph.dataset.id) + '&nombre=' + encodeURIComponent(ph.dataset.nombre) + '&club=' + encodeURIComponent(ph.dataset.club) + '&lat=' + ph.dataset.lat + '&lng=' + ph.dataset.lng;
    fetch(q).then(function(r){ return r.json(); }).then(function(j){ if(j && j.fotos && j.fotos.length){ var m = (j.minis || [])[0] || {}; var im = document.createElement('img'); im.src = m.s || j.fotos[0]; if(m.ss){ im.srcset = m.ss; im.sizes = '120px'; } im.alt = ''; im.decoding = 'async'; ph.replaceWith(im); } }).catch(function(){});
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
    return ui.shell("Mis reservas", cuerpo, sesion=ses, titulo_tab=f"Mis reservas · {MARCA}", extra_head=head, ancho=True)



# --- Perfil (= pantalla Perfil del app) --------------------------------------
