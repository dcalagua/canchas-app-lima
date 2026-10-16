"""SOY BOLEADOR en la web (Modo anfitrión → Soy boleador): el mismo perfil de
boleador del app (`boleadores.py`) desde la laptop: registro por selección
(deporte, categoría de la Liga Pichangol, tarifa por turno, locales donde
atiende, disponibilidad, etiquetas), pausar/activar, y las SOLICITUDES con
Aceptar / Rechazar (pendientes con su plazo) y los boleos confirmados con
Cancelar. Candado: identidad verificada (como el marketplace).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

import boleadores as _bol
import paises
from web import datos, horarios, ui
from web.anfitrion import _entrar, _sesion_o_entrar
from web.router import PLAY_URL, e

router = APIRouter(tags=["web-anfitrion-boleadores"])
_JSON_INVALIDO = object()


def _cab(ses: dict | None) -> str:
    tabs = ("<a class='cat sel' href='/anfitrion/boleador'><span class='ico'>🎾</span>Soy boleador</a>"
            "<a class='cat' href='/anfitrion/ingresos'><span class='ico'>💰</span>Ingresos</a>")
    return ui.cabecera(tabs=tabs, ses=ses, volver="/anfitrion", modo="anfitrion")


def _candado(ses: dict, nombre: str) -> HTMLResponse:
    cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
              "<div class='panel' style='max-width:640px;margin:22px auto 0;text-align:center'>"
              "<span class='anf-item-ico' style='background:#0E8F67'>🎾</span>"
              f"<h2 style='margin-top:12px'>Verifica tu identidad para ser {nombre.lower()}</h2>"
              f"<p class='sub'>Vas a estar en una cancha con jugadores que no te conocen: por eso todo {nombre.lower()} de Pichangol tiene "
              "identidad verificada (DNI validado). Verifícate desde la app: Perfil → Verificar identidad. Toma un minuto.</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}' rel='noopener'>Abrir en la app</a>"
              "<a class='btn sec' href='/anfitrion'>Volver al menú</a></div></div>")
    return ui.shell(f"Soy {nombre.lower()}", cuerpo, nav=_cab(ses), sesion=ses, ancho=True)


def _locales_para(deporte: str) -> list[dict]:
    """Locales verificados de Pichangol con canchas de ese deporte, agrupados
    por `club` (elegir un local = todas sus canchas de ese deporte)."""
    grupos: dict[str, dict] = {}
    for c in datos.canchas_verificadas():
        deps = [str(x).lower() for x in (c.get("deportes") or [c.get("deporte")]) if x]
        if deporte not in deps or not datos.permite_boleadores(c["id"]):
            continue
        club = str(c.get("club") or c.get("nombre") or "")
        g = grupos.setdefault(club.lower(), {"club": club, "zona": str(c.get("barrio") or c.get("distrito") or ""),
                                              "ids": [], "pais": paises.pais_de_coordenadas(c.get("lat"), c.get("lng"))})
        g["ids"].append(c["id"])
    return sorted(grupos.values(), key=lambda g: g["club"].lower())


def _fecha_corta(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso)
        return d.astimezone(timezone(horarios.ahora_local("PE").utcoffset())).strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return ""


def _tarjeta_sol(s: dict, sim: str) -> str:
    neto = (int(s["monto_centimos"]) - int(s["comision_centimos"])) / 100.0
    pend = s["estado"] == "pendiente"
    acc = ""
    if pend:
        acc = (f"<div class='acc'><button class='btn' data-bol-acc='aceptar' data-id='{e(s['id'])}'>✅ Aceptar · ganas {e(sim)} {neto:.2f}</button>"
               f"<button class='btn sec' data-bol-acc='rechazar' data-id='{e(s['id'])}'>No puedo</button></div>"
               f"<div class='sub' style='font-size:12px'>Responde antes de las {e(_fecha_corta(s.get('vence_en') or ''))}; si no, se le devuelve al jugador.</div>")
    elif s["estado"] == "aceptada":
        acc = f"<div class='acc'><button class='btn sec' data-bol-acc='cancelar' data-id='{e(s['id'])}' style='color:var(--rojo)'>Cancelar este boleo</button></div>"
    cliente = e(s.get("cliente_nombre") or s.get("cliente_email") or "Jugador")
    return (f"<div class='bol-sol{' pend' if pend else ''}'>"
            f"<div style='display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap'><b>{e(horarios.fecha_larga(s['fecha']))} · {e(s['hora_inicio'])}–{e(s['hora_fin'])}</b>"
            f"<span class='pill{' ok' if s['estado'] == 'aceptada' else ''}'>{e(_bol.estado_visible(s) or s['estado'])}</span></div>"
            f"<div class='sub' style='margin:0'>{e(s.get('club') or (s.get('data') or {}).get('cancha') or 'Cancha')} · {cliente} · {s['turnos']} turno{'s' if s['turnos'] != 1 else ''}</div>"
            f"<div class='sub' style='margin:0'>Cobras {e(sim)} {int(s['monto_centimos']) / 100.0:.2f} − comisión Pichangol {e(sim)} {int(s['comision_centimos']) / 100.0:.2f} = <b>{e(sim)} {neto:.2f}</b> por recibir al terminar el turno.</div>"
            f"{acc}</div>")


_JS_BOL = r"""
(function(){
  var C = window.__bol, sel = new Set(C.canchas || []);
  var $ = function(id){ return document.getElementById(id); };
  function chips(cont, name, ops, val, multi){
    var box = $(cont); if(!box) return;
    box.innerHTML = ops.map(function(o){ var v = typeof o === 'object' ? o.v : o, t = typeof o === 'object' ? o.t : o;
      var on = multi ? (val.indexOf(v) >= 0) : (String(val) === String(v));
      return '<span class="chip' + (on ? ' sel' : '') + '" data-' + name + '="' + v + '">' + t + '</span>'; }).join('');
    box.querySelectorAll('.chip').forEach(function(ch){ ch.addEventListener('click', function(){
      if(multi){ ch.classList.toggle('sel'); } else { box.querySelectorAll('.chip').forEach(function(x){ x.classList.remove('sel'); }); ch.classList.add('sel'); }
      if(name === 'dep') cargarLocales();
      if(name === 'tarifa' && $('tarifaOtra')) $('tarifaOtra').value = '';
    }); });
  }
  function val(cont, name){ var el = document.querySelector('#' + cont + ' .chip.sel'); return el ? el.getAttribute('data-' + name) : ''; }
  function vals(cont, name){ return Array.prototype.map.call(document.querySelectorAll('#' + cont + ' .chip.sel'), function(x){ return x.getAttribute('data-' + name); }); }
  chips('deps', 'dep', C.deportes.map(function(d){ return {v: d, t: (d === 'tenis' ? '🎾 Tenis' : '🏓 Pádel')}; }), C.deporte || 'tenis');
  chips('cats', 'cat', C.categorias, C.categoria);
  chips('tarifas', 'tarifa', C.tarifas.map(function(t){ return {v: t, t: C.simbolo + ' ' + t}; }), C.tarifa && C.tarifas.indexOf(C.tarifa) >= 0 ? C.tarifa : '');
  if(C.tarifa && C.tarifas.indexOf(C.tarifa) < 0 && $('tarifaOtra')) $('tarifaOtra').value = C.tarifa;
  chips('dias', 'dia', [[1,'Lun'],[2,'Mar'],[3,'Mié'],[4,'Jue'],[5,'Vie'],[6,'Sáb'],[7,'Dom']].map(function(x){ return {v: x[0], t: x[1]}; }), (C.disponibilidad.dias || [1,2,3,4,5,6,7]).map(String), true);
  chips('etqs', 'etq', C.etiquetas, C.etiquetasSel || [], true);
  function cargarLocales(){
    var dep = val('deps', 'dep') || 'tenis', box = $('locales');
    box.innerHTML = '<span class="sub">Cargando locales…</span>';
    fetch('/anfitrion/boleador/locales?deporte=' + encodeURIComponent(dep)).then(function(r){ return r.json(); }).then(function(j){
      var ls = (j && j.locales) || [];
      if(!ls.length){ box.innerHTML = '<span class="sub">Aún no hay locales verificados de ' + dep + ' en Pichangol.</span>'; return; }
      box.innerHTML = ls.map(function(l){ var on = l.ids.some(function(i){ return sel.has(i); });
        return '<label class="bol-card' + (on ? ' sel' : '') + '" data-ids="' + l.ids.join(',') + '"><span class="ini">🏟️</span><div><span class="nom">' + esc(l.club) + '</span><div class="det">' + esc(l.zona || '') + ' · ' + l.ids.length + ' cancha' + (l.ids.length === 1 ? '' : 's') + '</div></div><span class="chk">✓</span></label>'; }).join('');
      box.querySelectorAll('.bol-card').forEach(function(el){ el.addEventListener('click', function(){ var ids = el.dataset.ids.split(','); var on = el.classList.toggle('sel'); ids.forEach(function(i){ if(on) sel.add(i); else sel.delete(i); }); }); });
    }).catch(function(){ box.innerHTML = '<span class="sub">No pudimos cargar los locales.</span>'; });
  }
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  cargarLocales();
  $('btnGuardar').addEventListener('click', function(){
    var tarifa = parseFloat(($('tarifaOtra') && $('tarifaOtra').value) || val('tarifas', 'tarifa') || '0');
    var body = {deporte: val('deps', 'dep'), categoria: val('cats', 'cat'), tarifa: tarifa, canchas: Array.from(sel),
                disponibilidad: {dias: vals('dias', 'dia').map(Number), desde: $('desde').value, hasta: $('hasta').value},
                etiquetas: vals('etqs', 'etq'), celular: $('celular').value, nombre: $('nombreBol').value, activo: $('activo').checked};
    if(!body.categoria){ pcgAvisar({titulo: 'Falta tu categoría', mensaje: 'Elige tu categoría de la Liga Pichangol (5P, 5A, 5B, 4ta…).'}); return; }
    if(!(tarifa > 0)){ pcgAvisar({titulo: 'Falta tu tarifa', mensaje: 'Elige cuánto cobras por turno.'}); return; }
    if(!body.canchas.length){ pcgAvisar({titulo: 'Elige tus locales', mensaje: 'Marca al menos un local donde atiendes.'}); return; }
    pcgCargando('Guardando…');
    fetch('/anfitrion/boleador/guardar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function(r){ return r.json(); }).then(function(j){
        if(j.ok){ pcgRecargar('Listo…'); return; }
        pcgCargando(false);
        var m = {verificacion_requerida: 'Primero verifica tu identidad desde la app.', categoria_requerida: 'Elige tu categoría.', canchas_requeridas: 'Marca al menos un local.',
                 tarifa_invalida: 'La tarifa no es válida.', cancha_invalida: 'Uno de los locales ya no está disponible.'}[j.error] || 'No se pudo guardar.';
        pcgAvisar({titulo: 'Revisa tu perfil', mensaje: m});
      }).catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', mensaje: 'No se pudo guardar. Inténtalo de nuevo.'}); });
  });
  document.addEventListener('click', function(ev){
    var b = ev.target.closest && ev.target.closest('[data-bol-acc]'); if(!b) return;
    var acc = b.dataset.bolAcc, id = b.dataset.id;
    var go = function(){
      pcgCargando(acc === 'aceptar' ? 'Confirmando…' : 'Enviando…');
      fetch('/anfitrion/boleador/solicitud/' + encodeURIComponent(id) + '/' + acc, {method: 'POST'}).then(function(r){ return r.json(); }).then(function(j){
        if(j.ok){ pcgRecargar(); return; }
        pcgCargando(false); pcgAvisar({titulo: 'No se pudo', mensaje: ({vencida: 'El plazo para aceptar ya venció y se le devolvió al jugador.', ajena: 'Esa solicitud no es tuya.'}[j.error] || 'Inténtalo de nuevo.')});
      }).catch(function(){ pcgCargando(false); });
    };
    if(acc === 'aceptar'){ go(); return; }
    pcgConfirmar({titulo: acc === 'cancelar' ? '¿Cancelar este boleo?' : '¿No puedes ese día?',
                  mensaje: acc === 'cancelar' ? 'Se le devuelve su parte al jugador y cuenta como una falta en tu perfil (2 faltas en 90 días lo pausan).' : 'Se le devuelve su parte al jugador y tu reserva queda libre.',
                  confirmar: acc === 'cancelar' ? 'Sí, cancelar' : 'No puedo', destructivo: acc === 'cancelar'}).then(function(ok){ if(ok) go(); });
  });
})();
"""


@router.get("/anfitrion/boleador", response_class=HTMLResponse)
def pagina_boleador(request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/boleador")
    if resp is not None:
        return resp
    email = ses["email"]
    b = datos.boleador(email)
    pais = _bol._pais_de_boleador(b)
    nombre = _bol.nombre_por_pais(pais)
    if not datos.esta_verificado(email):
        return _candado(ses, nombre)
    cfg = _bol._cfg_publica(pais)
    sim = cfg["simbolo"]
    sols = datos.solicitudes_de_boleador(email)
    pend = [s for s in sols if s["estado"] == "pendiente"]
    prox = [s for s in sols if s["estado"] == "aceptada"]
    hist = [s for s in sols if s["estado"] not in ("pendiente", "aceptada")][:20]
    b = b or {}
    disp = b.get("disponibilidad") or {}
    js_cfg = json.dumps({"deportes": cfg["deportes"], "categorias": cfg["categorias"], "tarifas": cfg["tarifas"], "simbolo": sim,
                         "etiquetas": cfg["etiquetas"], "deporte": b.get("deporte") or "tenis", "categoria": b.get("categoria") or "",
                         "tarifa": b.get("tarifa") or 0, "canchas": b.get("canchas") or [], "disponibilidad": disp,
                         "etiquetasSel": b.get("etiquetas") or []}, ensure_ascii=False)
    horas = "".join(f"<option value='{h:02d}:00'>{h:02d}:00</option>" for h in range(5, 24))
    estado = ("<span class='pill ok'>Activo · recibes solicitudes</span>" if b.get("activo") else
              ("<span class='pill'>Pausado</span>" if b else "<span class='pill'>Aún no registrado</span>"))
    cuerpo = (
        "<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
        f"<h1 class='anf-hola' style='margin-top:6px'>Soy {nombre.lower()} {estado}</h1>"
        f"<p class='sub'>Los jugadores te contratan por turno al reservar la cancha. Tú aceptas o rechazas cada solicitud. "
        f"Pichangol descuenta {sim} {cfg['comision']:.2f} por turno y el resto queda por recibir en tu billetera al terminar el boleo.</p>"
        + (f"<h2 style='margin-top:22px'>Solicitudes pendientes <span class='pill'>{len(pend)}</span></h2><div style='display:grid;gap:10px'>"
           + "".join(_tarjeta_sol(s, paises.simbolo_de_moneda(s['moneda'])) for s in pend) + "</div>" if pend else "")
        + (f"<h2 style='margin-top:22px'>Boleos confirmados</h2><div style='display:grid;gap:10px'>"
           + "".join(_tarjeta_sol(s, paises.simbolo_de_moneda(s['moneda'])) for s in prox) + "</div>" if prox else "")
        + "<h2 style='margin-top:26px'>Mi perfil</h2><div class='panel' style='display:grid;gap:16px'>"
        "<div><label>Deporte</label><div class='chips' id='deps'></div></div>"
        "<div><label>Mi categoría (Liga Pichangol)</label><div class='chips' id='cats'></div></div>"
        "<div><label>Tarifa por turno</label><div class='chips' id='tarifas'></div>"
        f"<div class='row' style='margin-top:8px'><div><label for='tarifaOtra'>Otro monto ({sim})</label><input id='tarifaOtra' inputmode='decimal' placeholder='p. ej. 35'></div></div></div>"
        "<div><label>Locales donde atiendes</label><div class='sub' style='margin:0 0 8px;font-size:13px'>Solo locales verificados en Pichangol. Marca todos los que te queden bien.</div><div class='bol-box' id='locales'></div></div>"
        "<div><label>Disponibilidad</label><div class='chips' id='dias'></div>"
        f"<div class='row' style='margin-top:8px'><div><label for='desde'>Desde</label><select id='desde'>{horas}</select></div><div><label for='hasta'>Hasta</label><select id='hasta'>{horas}</select></div></div></div>"
        "<div><label>Sobre ti (elige)</label><div class='chips' id='etqs'></div></div>"
        f"<div class='row'><div><label for='nombreBol'>Nombre que ven los jugadores</label><input id='nombreBol' maxlength='60' value='{e(b.get('nombre') or ses.get('nombre') or '')}'></div>"
        f"<div><label for='celular'>Celular (WhatsApp)</label><input id='celular' inputmode='tel' maxlength='15' value='{e(b.get('celular') or '')}'></div></div>"
        f"<label style='display:flex;gap:10px;align-items:center;font-weight:600'><input type='checkbox' id='activo' style='width:auto;flex:none'{' checked' if (b.get('activo') if b else True) else ''}> Recibir solicitudes</label>"
        "<div class='acciones'><button type='button' class='btn' id='btnGuardar'>Guardar mi perfil</button></div></div>"
        + ("<h2 style='margin-top:26px'>Historial</h2><div style='display:grid;gap:10px'>"
           + "".join(_tarjeta_sol(s, paises.simbolo_de_moneda(s['moneda'])) for s in hist) + "</div>" if hist else "")
        + f"<script>window.__bol={js_cfg};</script><script>{_JS_BOL}</script>"
        f"<script>document.getElementById('desde').value={json.dumps(disp.get('desde') or '06:00')};document.getElementById('hasta').value={json.dumps(disp.get('hasta') or '23:00')};</script>")
    return ui.shell(f"Soy {nombre.lower()}", cuerpo, nav=_cab(ses), sesion=ses, ancho=True, titulo_tab=f"Soy {nombre.lower()} · Modo anfitrión")


@router.get("/anfitrion/boleador/locales")
def locales(request: Request, deporte: str = "tenis") -> JSONResponse:
    ses = _sesion_o_entrar(request, "/anfitrion/boleador")[0]
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion"}, status_code=401)
    dep = (deporte or "tenis").lower()
    if dep not in _bol.DEPORTES:
        dep = "tenis"
    return JSONResponse({"ok": True, "locales": _locales_para(dep)})


def _guardar(ses: dict, body) -> dict:
    if body is _JSON_INVALIDO or not isinstance(body, dict):
        return {"ok": False, "error": "datos_invalidos"}
    try:
        tarifa = float(body.get("tarifa") or 0)
    except (TypeError, ValueError):
        tarifa = 0
    req = _bol.PerfilReq(email=ses["email"], nombre=str(body.get("nombre") or ses.get("nombre") or ""), foto=str(ses.get("foto") or ""),
                         celular=str(body.get("celular") or ""), deporte=str(body.get("deporte") or "tenis"),
                         categoria=str(body.get("categoria") or ""), tarifa=tarifa,
                         canchas=[str(x) for x in (body.get("canchas") or [])], disponibilidad=(body.get("disponibilidad") or {}),
                         etiquetas=[str(x) for x in (body.get("etiquetas") or [])], activo=bool(body.get("activo", True)))
    r = _bol.guardar_perfil(req)
    if r.get("ok"):
        r["boleador"] = _bol.publico(r["boleador"]) if r.get("boleador") else None
    return r


@router.post("/anfitrion/boleador/guardar")
async def guardar(request: Request) -> JSONResponse:
    ses = _sesion_o_entrar(request, "/anfitrion/boleador")[0]
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion"}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = _JSON_INVALIDO
    return JSONResponse(await run_in_threadpool(_guardar, ses, body))


@router.post("/anfitrion/boleador/solicitud/{sol_id}/{accion}")
async def responder(sol_id: str, accion: str, request: Request) -> JSONResponse:
    ses = _sesion_o_entrar(request, "/anfitrion/boleador")[0]
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion"}, status_code=401)
    fn = {"aceptar": _bol.aceptar, "rechazar": _bol.rechazar, "cancelar": _bol.cancelar_boleador}.get(accion)
    if fn is None:
        return JSONResponse({"ok": False, "error": "accion"}, status_code=404)
    return JSONResponse(await run_in_threadpool(fn, sol_id, ses["email"]))
