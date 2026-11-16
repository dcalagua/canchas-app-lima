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
from web import vista_anfitrion as _va
from web.anfitrion import _sesion_o_entrar
from web.router import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

router = APIRouter(tags=["web-anfitrion-boleadores"])
_JSON_INVALIDO = object()


_SUB = "Peloteo por turno: eliges tu categoría, tarifa y zona, y los jugadores te reservan."


def _pasos(paso: int, nombre: str) -> str:
    """Línea de tiempo 1·2·3 (captura Frame 37). [paso] = el que toca ahora
    (los anteriores salen hechos)."""
    from web import estilos_v_academia as sva
    items = (("escudo_ok", "1. Verifica tu identidad", "Documento validado"),
             ("boleador", "2. Arma tu perfil", "Categoría, tarifa y zona"),
             ("calendario", "3. Recibe turnos", f"Los jugadores te reservan como {nombre.lower()}"))
    li = ""
    for n, (ico, t, d) in enumerate(items, start=1):
        cls = "ok" if n < paso else ("sel" if n == paso else "")
        li += (f"<li class='{cls}'" + (" aria-current='step'" if n == paso else "") + f"><span class='n'>{sva.svg('check' if n < paso else ico, 16)}</span>"
               f"<div><b>{e(t)}</b><small>{e(d)}</small></div></li>")
    return f"<ol class='vac-tl'>{li}</ol>"


_JS_ID = r"""
(function(){
  var C = window.__bolId, $ = function(i){ return document.getElementById(i); }, pais = C.pais;
  function pintar(){
    var d = C.docs[pais];
    document.querySelectorAll('[data-bol-pais]').forEach(function(b){ var on = b.dataset.bolPais === pais; b.classList.toggle('sel', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
    $('bolForm').hidden = !d.web; $('bolBo').hidden = !!d.web;
    $('bolSubId').textContent = d.web ? ('Validamos tu ' + d.doc + ' contra ' + d.registro + '. Es rápido y da confianza a los dueños de cancha.')
                                      : ('En ' + d.nombre + ' tu ' + d.doc + ' se valida en la app.');
    if(d.web){ $('bolLblNum').textContent = 'Número de ' + d.doc; var n = $('bolNum'); n.maxLength = d.largo; n.placeholder = d.largo + ' dígitos'; n.value = '';
      $('bolVerTxt').textContent = 'Verificar ' + d.doc; $('bolNotaDoc').textContent = d.doc; }
    $('bolErr').textContent = '';
  }
  document.querySelectorAll('[data-bol-pais]').forEach(function(b){ b.addEventListener('click', function(){ pais = b.dataset.bolPais; pintar(); }); });
  $('bolNum').addEventListener('input', function(){ this.value = this.value.replace(/\D/g, ''); $('bolErr').textContent = ''; });
  $('bolApp').addEventListener('click', function(){ window.open(C.play, '_blank', 'noopener'); });
  $('bolVer').addEventListener('click', function(){
    var btn = this, d = C.docs[pais], n = $('bolNum').value.trim(); if(btn.disabled) return;
    if(!n){ $('bolErr').textContent = 'Escribe tu número de ' + d.doc + '.'; $('bolNum').focus(); return; }
    if(n.length !== d.largo){ $('bolErr').textContent = 'El ' + d.doc + ' tiene ' + d.largo + ' dígitos.'; $('bolNum').focus(); return; }
    btn.disabled = true; pcgCargando('Validando tu ' + d.doc + '…');
    fetch('/web/cuenta/identidad', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({pais: pais, numero: n})})
      .then(function(r){ return r.json(); }).then(function(j){ btn.disabled = false; pcgCargando(false);
        if(!j.ok){ $('bolErr').textContent = j.mensaje || 'No se pudo. Reintenta.'; return; }
        pcgAvisar({titulo: '¡Identidad verificada! ✓', icono: '✅', confirmar: 'Armar mi perfil',
                   mensaje: 'Listo: ahora arma tu perfil (categoría, tarifa y locales) para recibir turnos.'})
          .then(function(){ pcgRecargar('Abriendo tu perfil…'); }); })
      .catch(function(){ btn.disabled = false; pcgCargando(false); $('bolErr').textContent = 'No pudimos conectar. Revisa tu conexión.'; });
  });
  pintar();
})();
"""


def _candado(ses: dict, nombre: str, iso: str) -> HTMLResponse:
    """Sin identidad verificada: explicación + el MISMO formulario de
    `/cuenta/identidad` dentro de la página (POST /web/cuenta/identidad, sus
    reglas y su tope de intentos). Bolivia: se verifica en el app (CI + selfie)."""
    from web import estilos_v_academia as sva
    from web import vista_anfitrion as va
    from web.jugador_cuenta import DOC, PAISES
    from web.router import PLAY_URL
    iso = iso if iso in DOC else "PE"
    docs = {i: {"doc": DOC[i][0], "largo": DOC[i][1] or 0, "registro": DOC[i][2], "web": i != "BO", "nombre": n} for i, n in PAISES}
    seg = "".join(f"<button type='button' data-bol-pais='{i}' class='{'sel' if i == iso else ''}' aria-pressed='{'true' if i == iso else 'false'}'>{e(n)}</button>"
                  for i, n in PAISES)
    doc, largo, registro = DOC[iso]
    izq = (f"<section class='va-panel'><span class='vac-bol-ic'>{sva.svg('escudo_ok', 26)}</span><h2>Tu identidad, verificada</h2>"
           f"<p class='vac-bol-intro'>Vas a estar en una cancha con jugadores que no te conocen: por eso todo {nombre.lower()} de {MARCA} tiene "
           "identidad verificada. Toma un minuto.</p>" + _pasos(1, nombre) + "</section>")
    der = ("<section class='va-panel'><h2>Verificar identidad</h2>"
           f"<p class='vac-bol-intro' id='bolSubId'>Validamos tu {e(doc)} contra {e(registro or 'el registro')}. Es rápido y da confianza a los dueños de cancha.</p>"
           f"<span class='vac-lbl'>País</span><div class='va-seg' role='group' aria-label='País de tu documento'>{seg}</div>"
           f"<div id='bolForm'><label class='vac-lbl' for='bolNum' id='bolLblNum'>Número de {e(doc)}</label>"
           f"<div class='vac-doc'>{sva.svg('documento', 20)}<input id='bolNum' inputmode='numeric' autocomplete='off' maxlength='{largo or 10}' placeholder='{largo or 8} dígitos'></div>"
           "<div class='vac-err' id='bolErr' role='alert'></div>"
           f"<button type='button' class='btn ancho' id='bolVer'>{sva.svg('escudo_ok', 18)}<span id='bolVerTxt'>Verificar {e(doc)}</span></button>"
           f"<div class='vac-nota'>{sva.svg('candado', 18)}<span>Solo usamos tu <span id='bolNotaDoc'>{e(doc)}</span> para confirmar tu identidad y tu edad. "
           "No guardamos foto de tu documento ni lo mostramos a nadie.</span></div></div>"
           "<div id='bolBo' class='vac-bo' hidden><b>En Bolivia tu CI se valida en la app</b>"
           "La app lee tu documento con la cámara del teléfono (no se envía a ningún lado para leerlo) y suma una selfie. Ese paso no se puede "
           "hacer desde el navegador sin bajar la seguridad. Cuando termines, vuelve aquí y arma tu perfil."
           "<div><button type='button' class='btn' id='bolApp'>Verificar en la app</button></div></div></section>")
    cfg = ui.json_js({"pais": iso, "docs": docs, "play": PLAY_URL}, ensure_ascii=False)
    cuerpo = va.vista(va.cabecera(f"Soy {nombre.lower()}", _SUB, volver="/anfitrion", volver_txt="Roles")
                      + f"<div class='vac-bol'>{izq}{der}</div><script>window.__bolId={cfg};</script><script>{_JS_ID}</script>", "vac")
    return ui.shell(f"Soy {nombre.lower()}", cuerpo, sesion=ses, ancho=True, titulo_tab=f"Soy {nombre.lower()} · Modo anfitrión")


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
               f"<div class='aco-n'>Responde antes de las {e(_fecha_corta(s.get('vence_en') or ''))}; si no, se le devuelve al jugador.</div>")
    elif s["estado"] == "aceptada":
        acc = f"<div class='acc'><button class='btn peligro' data-bol-acc='cancelar' data-id='{e(s['id'])}'>Cancelar este boleo</button></div>"
    cliente = e(s.get("cliente_nombre") or s.get("cliente_email") or "Jugador")
    return (f"<div class='bol-sol{' pend' if pend else ''}'>"
            f"<div class='vac-sol-cab'><b>{e(horarios.fecha_larga(s['fecha']))} · {e(s['hora_inicio'])}–{e(s['hora_fin'])}</b>"
            f"{_va.pill(_bol.estado_visible(s) or s['estado'], 'ok' if s['estado'] == 'aceptada' else ('warn' if pend else 'gris'))}</div>"
            f"<div class='aco-n'>{e(s.get('club') or (s.get('data') or {}).get('cancha') or 'Cancha')} · {cliente} · {s['turnos']} turno{'s' if s['turnos'] != 1 else ''}</div>"
            f"<div class='aco-n'>Cobras {e(sim)} {int(s['monto_centimos']) / 100.0:.2f} − comisión {MARCA} {e(sim)} {int(s['comision_centimos']) / 100.0:.2f} = <b>{e(sim)} {neto:.2f}</b> por recibir al terminar el turno.</div>"
            f"{acc}</div>")


_JS_BOL = (r"""
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
      if(!ls.length){ box.innerHTML = '<span class="sub">Aún no hay locales verificados de ' + dep + ' en ⟦MARCA⟧.</span>'; return; }
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
    if(!body.categoria){ pcgAvisar({titulo: 'Falta tu categoría', mensaje: 'Elige tu categoría de la Liga ⟦MARCA⟧ (5P, 5A, 5B, 4ta…).'}); return; }
    if(!(tarifa > 0)){ pcgAvisar({titulo: 'Falta tu tarifa', mensaje: 'Elige cuánto cobras por turno.'}); return; }
    if(!body.canchas.length){ pcgAvisar({titulo: 'Elige tus locales', mensaje: 'Marca al menos un local donde atiendes.'}); return; }
    pcgCargando('Guardando…');
    fetch('/anfitrion/boleador/guardar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function(r){ return r.json(); }).then(function(j){
        if(j.ok){ pcgRecargar('Listo…'); return; }
        pcgCargando(false);
        var m = {verificacion_requerida: 'Primero verifica tu identidad (Perfil → Verificar identidad).', categoria_requerida: 'Elige tu categoría.', canchas_requeridas: 'Marca al menos un local.',
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
""").replace('⟦MARCA⟧', MARCA)


@router.get("/anfitrion/boleador", response_class=HTMLResponse)
def pagina_boleador(request: Request) -> HTMLResponse:
    from web import vista_anfitrion as va
    ses, resp = _sesion_o_entrar(request, "/anfitrion/boleador")
    if resp is not None:
        return resp
    email = ses["email"]
    b = datos.boleador(email)
    if not datos.esta_verificado(email):
        from web.jugador_cuenta import partir_celular, perfil_completo
        iso = _bol._pais_de_boleador(b) if b else partir_celular(perfil_completo(email).get("celular") or "")[0]
        return _candado(ses, _bol.nombre_por_pais(iso), iso)
    pais = _bol._pais_de_boleador(b)
    nombre = _bol.nombre_por_pais(pais)
    cfg = _bol._cfg_publica(pais)
    sim = cfg["simbolo"]
    sols = datos.solicitudes_de_boleador(email)
    pend = [s for s in sols if s["estado"] == "pendiente"]
    prox = [s for s in sols if s["estado"] == "aceptada"]
    hist = [s for s in sols if s["estado"] not in ("pendiente", "aceptada")][:20]
    b = b or {}
    disp = b.get("disponibilidad") or {}
    js_cfg = ui.json_js({"deportes": cfg["deportes"], "categorias": cfg["categorias"], "tarifas": cfg["tarifas"], "simbolo": sim,
                         "etiquetas": cfg["etiquetas"], "deporte": b.get("deporte") or "tenis", "categoria": b.get("categoria") or "",
                         "tarifa": b.get("tarifa") or 0, "canchas": b.get("canchas") or [], "disponibilidad": disp,
                         "etiquetasSel": b.get("etiquetas") or []}, ensure_ascii=False)
    horas = "".join(f"<option value='{h:02d}:00'>{h:02d}:00</option>" for h in range(5, 24))
    estado = (va.pill("Activo · recibes solicitudes", "ok") if b.get("activo") else
              (va.pill("Pausado", "warn") if b else va.pill("Aún no registrado", "gris")))
    paso = 3 if b.get("activo") else 2

    def _bloque(titulo: str, lista: list[dict], tono: str = "gris") -> str:
        if not lista:
            return ""
        return (f"<section class='va-panel'><h2 class='vac-h2'>{e(titulo)}{va.pill(str(len(lista)), tono)}</h2><div class='vac-lista'>"
                + "".join(_tarjeta_sol(s, paises.simbolo_de_moneda(s['moneda'])) for s in lista) + "</div></section>")
    sols_html = (_bloque("Solicitudes pendientes", pend, "warn") + _bloque("Boleos confirmados", prox, "ok")
                 + ("" if (pend or prox) else va.panel(va.vacio("calendario", "Sin solicitudes por ahora",
                                                                 "Cuando un jugador te contrate al reservar, aquí aceptas o rechazas.")))
                 + _bloque("Historial", hist))
    perfil = va.panel(
        "<label class='vac-lbl'>Deporte</label><div class='chips' id='deps'></div>"
        f"<label class='vac-lbl'>Mi categoría (Liga {MARCA})</label><div class='chips' id='cats'></div>"
        "<label class='vac-lbl'>Tarifa por turno</label><div class='chips' id='tarifas'></div>"
        f"<div class='row'><div><label class='vac-lbl' for='tarifaOtra'>Otro monto ({e(sim)})</label><input id='tarifaOtra' inputmode='decimal' placeholder='p. ej. 35'></div></div>"
        f"<label class='vac-lbl'>Locales donde atiendes</label><p class='aco-n'>Solo locales verificados en {MARCA}. Marca todos los que te queden bien.</p><div class='bol-box' id='locales'></div>"
        "<label class='vac-lbl'>Disponibilidad</label><div class='chips' id='dias'></div>"
        f"<div class='row'><div><label class='vac-lbl' for='desde'>Desde</label><select id='desde'>{horas}</select></div><div><label class='vac-lbl' for='hasta'>Hasta</label><select id='hasta'>{horas}</select></div></div>"
        "<label class='vac-lbl'>Sobre ti (elige)</label><div class='chips' id='etqs'></div>"
        f"<div class='row'><div><label class='vac-lbl' for='nombreBol'>Nombre que ven los jugadores</label><input id='nombreBol' maxlength='60' value='{e(b.get('nombre') or ses.get('nombre') or '')}'></div>"
        f"<div><label class='vac-lbl' for='celular'>Celular (WhatsApp)</label><input id='celular' inputmode='tel' maxlength='15' value='{e(b.get('celular') or '')}'></div></div>"
        f"<label class='vac-check'><input type='checkbox' id='activo'{' checked' if (b.get('activo') if b else True) else ''}> Recibir solicitudes</label>"
        "<div class='vac-acc vac-acc-fin'><button type='button' class='btn' id='btnGuardar'>Guardar mi perfil</button></div>",
        "Mi perfil", f"Los jugadores te ven así al reservar una cancha de tenis o pádel.", clase="vac-perfil")
    intro = va.aviso(f"Los jugadores te contratan por turno al reservar la cancha y tú aceptas o rechazas cada solicitud. {MARCA} descuenta "
                     f"<b>{e(sim)} {cfg['comision']:.2f} por turno</b> y el resto queda por recibir en tu billetera al terminar el boleo.", "info", ico="billete")
    cuerpo = va.vista(
        va.cabecera(f"Soy {nombre.lower()}", _SUB, volver="/anfitrion", volver_txt="Roles", acciones=estado)
        + f"<div class='va-panel vac-pasos-h'>{_pasos(paso, nombre)}</div>" + intro
        + f"<div class='vac-bol-ops'><div class='vac-sols'>{sols_html}</div><div class='vac-perfil'>{perfil}</div></div>"
        + f"<script>window.__bol={js_cfg};</script><script>{_JS_BOL}</script>"
        f"<script>document.getElementById('desde').value={ui.json_js(disp.get('desde') or '06:00')};document.getElementById('hasta').value={ui.json_js(disp.get('hasta') or '23:00')};</script>",
        "vac")
    return ui.shell(f"Soy {nombre.lower()}", cuerpo, sesion=ses, ancho=True, titulo_tab=f"Soy {nombre.lower()} · Modo anfitrión")


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
