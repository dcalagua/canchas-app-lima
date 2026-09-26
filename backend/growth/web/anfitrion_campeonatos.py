"""MIS CAMPEONATOS en la web (Modo anfitrión → Mis campeonatos): el MISMO flujo
y funcionamiento de `mis_campeonatos_screen`, `crear_campeonato_screen` y
`campeonato_detalle_screen` del app, desde la laptop.

Misma fila `pichangol_campeonatos` (`data` jsonb = `Campeonato.toJson`), mismo
bucket `canchas/campeonatos/<id>[.jpg|_ausp_<ms>|_foto_<ms>|_fondo_<ms>.jpg]`,
misma lógica de fixture/llave/tabla/tiempos (`web/campeonatos_logica.py`,
espejo de `TorneoFixture`). Lo que el organizador hace en el app lo hace aquí:
crear (asistente de 3 pasos, candado Pro), editar, participantes (agregar /
quitar, equipos con su plantel), generar o regenerar el fixture, cargar
resultados, pruebas y tiempos de natación, afiche (fondo propio o arte IA),
auspiciadores, galería, duplicar (nueva edición), eliminar, compartir
(WhatsApp, enlace, código). La INSCRIPCIÓN del jugador (con pago desde su
saldo) sigue en el app: la página pública `/c/{id}` lo manda ahí.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from datetime import date, datetime

from fastapi import APIRouter, Body, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

import config
import paises
from db.store import stores
from web import almacen, catalogos, datos, sesion, ui
from web import campeonatos_logica as L
from web.anfitrion import JS_PAGAR, _en_segundo_plano, _sesion_o_entrar
from web.router import PLAY_URL, e

router = APIRouter(tags=["web-anfitrion-campeonatos"])
_LEAFLET = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
            "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>")
_EMOJI = {"tenis": "🎾", "padel": "🏸", "futbol": "⚽", "pickleball": "🏓", "voley": "🏐", "basquet": "🏀", "natacion": "🏊"}
_NOMBRE = {"tenis": "Tenis", "padel": "Pádel", "futbol": "Fútbol", "pickleball": "Pickleball", "voley": "Vóley", "basquet": "Básquet", "natacion": "Natación"}
_DOC = {"PE": "DNI", "EC": "Cédula", "BO": "CI"}
BASE = "/anfitrion/campeonatos"


# ── helpers ───────────────────────────────────────────────────────────────────
def _cab(ses: dict | None) -> str:
    tabs = f"<a class='cat sel' href='{BASE}'><span class='ico'>🏆</span>Mis campeonatos</a>"
    return ui.cabecera(tabs=tabs, ses=ses, volver="/anfitrion", modo="anfitrion")


def _mios(email: str) -> list[dict]:
    return datos.campeonatos_de_dueno(email)


def _mio(email: str, cid: str) -> dict | None:
    c = datos.campeonato(cid)
    return c if c and (c.get("dueno") or "").strip().lower() == (email or "").lower() else None


def _base_url() -> str:
    return config.url_limpia(config.LANDING_BASE_URL or config.PUBLIC_BASE_URL)


def _enlace(c: dict) -> str:
    return f"{_base_url()}/c/{c['id']}"


def _moneda(c: dict) -> str:
    """`Campeonato.monedaSimbolo`: por las coordenadas de la sede; si no, la congelada; si no, S/."""
    if c.get("sedeLat") is not None and c.get("sedeLng") is not None:
        return paises.simbolo_de_moneda(paises.moneda_de_pais(paises.pais_de_coordenadas(c["sedeLat"], c["sedeLng"])))
    return c.get("moneda") or "S/"


def _pais(c: dict) -> str:
    if c.get("sedeLat") is not None and c.get("sedeLng") is not None:
        return paises.pais_de_coordenadas(c["sedeLat"], c["sedeLng"])
    return {"$": "EC", "Bs": "BO"}.get(c.get("moneda") or "", "PE")


def _pro(email: str) -> bool:
    return stores.pro_activo(email)


def _ok(c: dict, **extra) -> JSONResponse:
    return JSONResponse({"ok": True, **extra})


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def _sesion_json(request: Request):
    ses = sesion.de_request(request)
    return ses, (None if ses else _err("sesion_requerida", 401))


def _mio_json(request: Request, cid: str):
    ses, err = _sesion_json(request)
    if err is not None:
        return None, None, err
    c = _mio(ses["email"], cid)
    if c is None:
        return ses, None, _err("Este campeonato no está a tu nombre.", 404)
    return ses, c, None


def _guardar(ses: dict, c: dict) -> bool:
    return datos.guardar_campeonato(c["id"], ses["email"], c)


def _dia(v) -> str:
    return str(v or "")[:10]


def _fecha_corta(v) -> str:
    d = L._dt(v)
    return f"{d.day} {L.MESES[d.month - 1]}" if d else ""


def _estado_pill(c: dict) -> str:
    clave, txt, color = L.estado(c)
    col = {"teal": "background:#E6F4EF;color:#0B7A55", "morado": "background:#EFE9FF;color:#5B3FD8",
           "naranja": "background:#FFF1E3;color:#B25E0A", "lima": "background:#EAF7E1;color:#3E7A16"}[color]
    return f"<span class='pill' style='{col}'>{txt}</span>"


# ── Lista (`MisCampeonatosScreen`) ────────────────────────────────────────────
def _tarjeta(c: dict) -> str:
    dep = str(c.get("deporte") or "tenis")
    n = len(c.get("participantes") or [])
    sub = f"{_NOMBRE.get(dep, dep)} · {L.FORMATOS[L.formato_de(c)]} · {n} inscrito{'s' if n != 1 else ''}{'' if c.get('academiaId') else ' · sin academia'}"
    logo = f"<img src='{e(c['logoUrl'])}' alt=''>" if c.get("logoUrl") else f"<span>{_EMOJI.get(dep, '🏆')}</span>"
    return (f"<a class='anf-cancha' href='{BASE}/{e(c['id'])}' style='text-decoration:none;color:inherit;align-items:center'>"
            f"<div class='f'>{logo}</div><div style='flex:1;min-width:0'><b style='font-size:16px'>{e(c.get('nombre') or 'Campeonato')}</b>"
            f"<div class='sub' style='margin:2px 0 6px'>{e(sub)}</div>{_estado_pill(c)}</div><span style='color:var(--tenue);font-size:22px'>›</span></a>")


@router.get(BASE, response_class=HTMLResponse)
def pagina_campeonatos(request: Request, guardado: str = "", eliminado: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, BASE)
    if resp is not None:
        return resp
    lista = _mios(ses["email"])
    aviso = ("<div class='aviso ok' style='margin-top:14px'>✅ Campeonato guardado. Ya se ve en la app y en su página pública.</div>" if guardado
             else "<div class='aviso ok' style='margin-top:14px'>🗑 Campeonato eliminado.</div>" if eliminado else "")
    pro = _pro(ses["email"])
    boton = (f"<a class='btn' href='{BASE}/nuevo'>＋ Organizar</a>" if pro else
             "<button type='button' class='btn' onclick=\"document.getElementById('modalPro').classList.add('open')\">＋ Organizar</button>")
    modal_pro = ("<div class='modal' id='modalPro' role='dialog' aria-modal='true'><div class='modal-caja' style='max-width:460px'>"
                 "<div class='modal-cab'><button type='button' class='cerrar' onclick=\"this.closest('.modal').classList.remove('open')\">✕</button><h3>Es Pichangol Pro</h3></div>"
                 "<div class='modal-cuerpo'><section><p class='sub' style='margin:0 0 12px'>Crear y administrar tus propios campeonatos (fixture, inscripciones, resultados) es parte de <b>Pichangol Pro</b>. Actívalo en la app (Perfil → Hazte Pro) y vuelve aquí.</p>"
                 f"<a class='btn' href='{PLAY_URL}' rel='noopener'>Abrir la app</a></section></div></div></div>")
    if not lista:
        cuerpo = (f"<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>{aviso}<div style='max-width:760px;margin:24px auto 0;text-align:center'>"
                  "<div style='font-size:52px'>🏆</div><h1 class='anf-hola' style='margin-top:8px'>Aún no organizas campeonatos</h1>"
                  "<p class='sub' style='font-size:16px'>Toca “Organizar” para crear tu torneo (fútbol, tenis, natación…), invitar y que se inscriban.</p>"
                  f"<div class='acciones' style='margin-top:22px;justify-content:center'>{boton}</div></div>{modal_pro}")
        return ui.shell("Mis campeonatos", cuerpo, nav=_cab(ses), sesion=ses, ancho=True, titulo_tab="Mis campeonatos · Modo anfitrión")
    cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
              "<div style='display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap'>"
              f"<div><h1 class='anf-hola' style='margin-top:6px'>Mis campeonatos</h1><p class='sub'>{len(lista)} campeonato{'s' if len(lista) != 1 else ''} que organizas. Es lo mismo que ves en la app.</p></div>{boton}</div>"
              f"{aviso}<div class='anf-grid' style='grid-template-columns:repeat(auto-fill,minmax(340px,1fr));margin-top:16px'>{''.join(_tarjeta(c) for c in lista)}</div>{modal_pro}")
    return ui.shell("Mis campeonatos", cuerpo, nav=_cab(ses), sesion=ses, ancho=True, titulo_tab="Mis campeonatos · Modo anfitrión")


# ── Asistente crear / editar (`CrearCampeonatoScreen`) ───────────────────────
def _chips(g: str, ops, sel, disabled: bool = False) -> str:
    out = []
    for k, txt in ops:
        out.append(f"<button type='button' class='chip{' sel' if str(k) == str(sel) else ''}' data-g='{g}' data-v='{e(str(k))}'{' disabled' if disabled else ''}>{txt}</button>")
    return f"<div class='chips' data-grupo='{g}'>{''.join(out)}</div>"


def _editor(ses: dict, c: dict, *, nuevo: bool) -> HTMLResponse:
    dep = str(c.get("deporte") or "futbol")
    fmt = L.formato_de(c)
    fix = L.fixture_generado(c)
    iso = _pais(c)
    logo = f"<img src='{e(c['logoUrl'])}' alt=''>" if c.get("logoUrl") else f"<span>{_EMOJI.get(dep, '🏆')}</span>"
    dep_ops = [(d, f"{_EMOJI[d]} {_NOMBRE[d]}") for d in catalogos.DEPORTES_CAMPEONATO]
    cat_txt = str(c.get("categoria") or "")
    cats = [lab for lab, _a, _b in catalogos.CATEGORIAS_CAMPEONATO]
    cat_sel = cat_txt if cat_txt in cats else ("otra" if cat_txt else "")

    def _cat_lab(lab, mn, mx):
        return lab + (f" · hasta {mx} años" if mx else f" · desde {mn} años" if mn else " · sin límite de edad")
    cat_ops = "<option value=''>— Sin categoría —</option>" + "".join(
        f"<option value='{e(lab)}'{' selected' if cat_sel == lab else ''}>{e(_cat_lab(lab, mn, mx))}</option>" for lab, mn, mx in catalogos.CATEGORIAS_CAMPEONATO
    ) + f"<option value='otra'{' selected' if cat_sel == 'otra' else ''}>Otra… (escribir)</option>"
    inicio, hasta = _dia(c.get("inicio")), _dia(c.get("inscripcionHasta"))
    fin = _dia(c.get("_fin")) or inicio
    canchas = datos.canchas_para_sede()[:400]
    cfg = {"id": c["id"], "nuevo": nuevo, "deporte": dep, "formato": fmt, "fixture": fix, "logo": c.get("logoUrl") or "", "minPartidos": L.min_partidos(c),
           "sede": c.get("sede") or "", "lat": c.get("sedeLat"), "lng": c.get("sedeLng"), "iso": iso, "buscar": bool(config.PLACES_API_KEY),
           "storage": almacen.disponible(), "canchas": canchas, "formatos": {d: catalogos.formatos_de(d) for d in catalogos.DEPORTES_CAMPEONATO},
           "defecto": {d: catalogos.formato_por_defecto(d) for d in catalogos.DEPORTES_CAMPEONATO}, "sub": catalogos.FORMATO_SUB,
           "monedas": {k: paises.simbolo_de_moneda(v) for k, v in paises.MONEDA_POR_PAIS.items()}, "moneda": _moneda(c),
           "cats": {lab: [mn, mx] for lab, mn, mx in catalogos.CATEGORIAS_CAMPEONATO}, "doc": _DOC}
    cuerpo = f"""
<style>
.wz{{max-width:720px;margin:0 auto}}.wz-pasos{{display:flex;gap:8px;margin:14px 0 18px}}.wz-pasos span{{flex:1;height:6px;border-radius:999px;background:var(--gris)}}.wz-pasos span.on{{background:var(--esmeralda)}}
.wz .wz-p{{display:none}}.wz .wz-p.on{{display:block}}.wz .panel{{padding:22px}}.wz label{{display:block;margin-top:16px;font-weight:700}}.wz input[type=text],.wz input[type=number],.wz input[type=date],.wz select,.wz textarea{{width:100%;margin-top:6px}}
.wz .radio{{display:flex;gap:12px;align-items:flex-start;border:1px solid var(--trazo);border-radius:14px;padding:12px 14px;margin-top:8px;cursor:pointer}}.wz .radio.sel{{border-color:var(--esmeralda);box-shadow:inset 0 0 0 1px var(--esmeralda)}}.wz .radio input{{width:auto;flex:none;margin:4px 0 0}}.wz .radio>span{{flex:1;min-width:0}}
.wz .radio.dis{{opacity:.55;cursor:not-allowed}}.sw{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:16px}}.sw label{{margin:0;flex:1}}.sw input{{width:20px;height:20px;flex:none;margin:0;accent-color:var(--esmeralda)}}
.wz .pie{{display:flex;justify-content:space-between;gap:10px;margin-top:22px}}.res-busca .res-it{{display:block;width:100%;text-align:left;border:0;background:#fff;padding:10px 12px;cursor:pointer;font-family:inherit;border-bottom:1px solid var(--trazo)}}.res-busca .res-it small{{display:block;color:var(--tenue)}}
</style>
<div class='wz'><a class='anf-back' href='{BASE if nuevo else BASE + '/' + e(c['id'])}'>‹ {'Mis campeonatos' if nuevo else 'Volver al campeonato'}</a>
<h1 class='anf-hola' style='margin-top:8px'>{'Organizar campeonato' if nuevo else 'Editar campeonato'}</h1>
<div class='wz-pasos'><span class='on' data-p='1'></span><span data-p='2'></span><span data-p='3'></span></div>
<div class='wz-p on panel' id='p1'><h2>{'Presenta tu campeonato' if nuevo else 'Edita tu campeonato'}</h2><p class='sub'>El logo y el nombre son la cara del torneo: salen en la app, en el afiche y en el enlace que compartes.</p>
 <div style='display:flex;gap:18px;align-items:center;margin-top:14px;flex-wrap:wrap'><div class='logo-pick' id='logoBox'>{logo}</div>
  <div><label class='btn sec' for='inLogo' style='margin:0'>🖼️ {'Cambiar logo' if c.get('logoUrl') else 'Subir logo'}</label><input type='file' id='inLogo' accept='image/*' hidden{'' if almacen.disponible() else ' disabled'}>
  <div class='sub' id='logoMsg' style='margin:6px 0 0;font-size:12.5px'>{'Opcional.' if almacen.disponible() else 'La subida de imágenes no está disponible en este ambiente.'}</div></div></div>
 <label for='nombre'>Nombre del campeonato</label><input id='nombre' type='text' maxlength='80' value='{e(c.get('nombre') or '')}' placeholder='Copa Verano CEANDE'>
 <label>Deporte</label>{_chips('deporte', dep_ops, dep, disabled=not nuevo)}{"<p class='sub' style='font-size:12.5px'>El deporte no se puede cambiar en un campeonato ya creado.</p>" if not nuevo else ''}
 <div class='pie'><span></span><button type='button' class='btn' data-ir='2'>Siguiente</button></div></div>
<div class='wz-p panel' id='p2'><h2>Formato y categoría</h2>
 <label>Formato</label><div id='formatos'></div>{"<p class='sub' style='font-size:12.5px'>El fixture ya fue generado: el formato no se puede cambiar.</p>" if fix else ''}
 <div id='minPartBox'{'' if fmt == 'grupos' else ' hidden'}><label>Partidos mínimos por equipo</label>{_chips('minp', [(2, 'Al menos 2'), (3, 'Al menos 3')], L.min_partidos(c), disabled=fix)}
 <p class='sub' style='font-size:12.5px' id='minPartTxt'>Se arman grupos; los 2 primeros de cada grupo pasan a la llave.</p></div>
 <div id='minJugBox'{'' if dep == 'futbol' else ' hidden'}><label for='minJug'>Mínimo de jugadores por equipo <span class='req'>opcional</span></label><input id='minJug' type='number' min='0' max='30' value='{int(c.get('minJugadoresEquipo') or 0) or ''}' placeholder='ej. 7'>
 <p class='sub' style='font-size:12.5px'>Cada equipo aparece "Completo" al llegar a este número. Vacío = solo se muestra el conteo.</p></div>
 <label for='cat'>Categoría <span class='req'>opcional</span></label><select id='cat'>{cat_ops}</select>
 <div id='catOtraBox'{'' if cat_sel == 'otra' else ' hidden'}><label for='catOtra'>Nombre de la categoría</label><input id='catOtra' type='text' maxlength='40' value='{e(cat_txt if cat_sel == 'otra' else '')}' placeholder='Ej. Damas B, Nivel intermedio, Mixto…'></div>
 <div class='pie'><button type='button' class='btn sec' data-ir='1'>Atrás</button><button type='button' class='btn' data-ir='3'>Siguiente</button></div></div>
<div class='wz-p panel' id='p3'><h2>Fechas, sede y reglas</h2>
 <div class='sw'><label>Relámpago (todo en un día)</label><input type='checkbox' id='relampago'{' checked' if c.get('relampago') else ''}></div>
 <label id='lblFechas'>{'Fecha (relámpago, un día)' if c.get('relampago') else 'Fechas de juego'}</label>
 <div class='row' style='grid-template-columns:1fr 1fr;gap:10px'><input id='desde' type='date' value='{e(inicio)}'><input id='hastaJ' type='date' value='{e(fin)}'{' disabled' if c.get('relampago') else ''}></div>
 {"<p class='sub' style='font-size:12.5px'>Actual: " + e(c.get('fechas')) + "</p>" if c.get('fechas') else ''}
 <label for='cierre'>Cierre de inscripciones <span class='req'>opcional · ese día a las 00:00 se cierran y se sortea solo</span></label><input id='cierre' type='date' value='{e(hasta)}'>
 <label for='sede'>Sede{" <span class='req'>🔎 elige una cancha de Pichangol o búscala en Google Maps</span>" if config.PLACES_API_KEY else " <span class='req'>elige una cancha de Pichangol</span>"}</label>
 <input id='sede' type='text' maxlength='80' value='{e(c.get('sede') or '')}' placeholder='Nombre de la cancha o club' autocomplete='off'><div id='resSede' class='res-busca' hidden></div>
 <div id='mapaSede' class='mapa-sede' style='margin-top:8px;height:220px'></div><div class='sub' id='ubicTxt' style='font-size:12.5px'>{'Sin ubicación: elige una sede para fijar el país y la moneda.' if c.get('sedeLat') is None else f"{float(c['sedeLat']):.5f}, {float(c['sedeLng']):.5f}"}</div>
 <label for='costo'>Costo de inscripción <span class='req'>opcional · se paga desde el saldo Pichangol del jugador</span></label><div class='inp-moneda' style='max-width:220px'><span id='monSpan'>{e(_moneda(c))}</span><input id='costo' type='number' min='0' step='0.5' value='{float(c.get('costoInscripcion') or 0) or ''}' placeholder='0'></div>
 <div class='sw'><label>Exigir <span id='docTxt'>{_DOC.get(iso, 'DNI')}</span> para inscribirse</label><input type='checkbox' id='exigeDni'{' checked' if c.get('exigeDni') else ''}></div>
 <div id='edadBox' class='row' style='grid-template-columns:1fr 1fr;gap:10px'{'' if c.get('exigeDni') else ' hidden'}><div><label for='edadMin' style='margin-top:8px'>Edad mín</label><input id='edadMin' type='number' min='0' max='99' value='{c.get('edadMin') if c.get('edadMin') is not None else ''}'></div><div><label for='edadMax' style='margin-top:8px'>Edad máx</label><input id='edadMax' type='number' min='0' max='99' value='{c.get('edadMax') if c.get('edadMax') is not None else ''}'></div></div>
 <h3 style='margin:22px 0 0'>Publicidad del torneo 📣</h3>
 <label for='ausp'>Auspiciador oficial <span class='req'>opcional</span></label><input id='ausp' type='text' maxlength='60' value='{e(c.get('auspiciador') or '')}' placeholder='Ej. JORDI MEAT BOUTIQUE' style='text-transform:uppercase'>
 <label for='premios'>Premios <span class='req'>uno por línea, opcional</span></label><textarea id='premios' rows='4' maxlength='600' placeholder='🥇 Trofeo + S/ 500&#10;🥈 Medalla'>{e(c.get('premios') or '')}</textarea>
 <div class='estado bad' id='errGuardar' style='display:none;margin-top:12px'></div>
 <div class='pie'><button type='button' class='btn sec' data-ir='2'>Atrás</button><button type='button' class='btn' id='btnGuardar'>{'Crear campeonato' if nuevo else 'Guardar cambios'}</button></div></div>
</div>
<script>var CFG={json.dumps(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{_JS_WIZARD}</script>"""
    return ui.shell("Campeonato", cuerpo, nav=_cab(ses), sesion=ses, ancho=True, extra_head=_LEAFLET,
                    titulo_tab=f"{'Organizar' if nuevo else 'Editar'} campeonato · Modo anfitrión")


_JS_WIZARD = r"""
(function(){
var dep=CFG.deporte, fmt=CFG.formato, logo=CFG.logo, lat=CFG.lat, lng=CFG.lng, iso=CFG.iso, mapa, marker, subiendo=0;
function $(id){return document.getElementById(id)}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}
function ir(n){document.querySelectorAll('.wz .wz-p').forEach(function(p){p.classList.remove('on')});$('p'+n).classList.add('on');document.querySelectorAll('.wz-pasos span').forEach(function(s){s.classList.toggle('on',+s.dataset.p<=n)});window.scrollTo({top:0,behavior:'smooth'})}
document.querySelectorAll('[data-ir]').forEach(function(b){b.addEventListener('click',function(){var n=+this.dataset.ir;if(n===2&&!$('nombre').value.trim()){pcgToast('Ponle nombre al campeonato para continuar.');$('nombre').focus();return}ir(n)})});
// deporte → formato por defecto (`_formatoDe`) y formatos ofrecidos (`_formatosDe`)
function pintarFormatos(){var ops=CFG.formatos[dep]||['eliminacion'];if(ops.indexOf(fmt)<0)fmt=CFG.defecto[dep];var lab={eliminacion:'Eliminación (llave)',liga:'Liga (tabla)',grupos:'Grupos + eliminatoria',tiempos:'Por tiempos (natación)'};
  $('formatos').innerHTML=ops.map(function(f){return "<label class='radio"+(f===fmt?' sel':'')+(CFG.fixture?' dis':'')+"'><input type='radio' name='fmt' value='"+f+"'"+(f===fmt?' checked':'')+(CFG.fixture?' disabled':'')+"><span><b>"+lab[f]+"</b><br><small class='sub'>"+esc(CFG.sub[f])+"</small></span></label>"}).join('');
  $('minJugBox').hidden=dep!=='futbol';pintarMinPart()}
var minPart=CFG.minPartidos||2;function pintarMinPart(){$('minPartBox').hidden=fmt!=='grupos';$('minPartTxt').textContent='Se arman grupos de '+(minPart+1)+' o más (cada equipo juega al menos '+minPart+' partidos); los 2 primeros de cada grupo pasan a la llave.'}
document.addEventListener('click',function(ev){var b=ev.target.closest(".chip[data-g='minp']");if(!b||b.disabled)return;b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');minPart=+b.dataset.v;pintarMinPart()});
document.addEventListener('change',function(ev){if(ev.target.name==='fmt'){fmt=ev.target.value;document.querySelectorAll('.radio').forEach(function(r){r.classList.toggle('sel',r.querySelector('input').checked)});pintarMinPart()}});
document.addEventListener('click',function(ev){var b=ev.target.closest(".chip[data-g='deporte']");if(!b||b.disabled)return;b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');dep=b.dataset.v;fmt=CFG.defecto[dep];pintarFormatos()});
pintarFormatos();
// categoría: del catálogo fija el rango de edad y exige DNI; "otra" = texto
$('cat').addEventListener('change',function(){var v=this.value;$('catOtraBox').hidden=v!=='otra';var r=CFG.cats[v];if(r){$('edadMin').value=r[0]||'';$('edadMax').value=r[1]||'';if(r[0]||r[1]){$('exigeDni').checked=true;$('edadBox').hidden=false}}});
$('exigeDni').addEventListener('change',function(){$('edadBox').hidden=!this.checked});
$('relampago').addEventListener('change',function(){$('hastaJ').disabled=this.checked;$('lblFechas').textContent=this.checked?'Fecha (relámpago, un día)':'Fechas de juego';if(this.checked)$('hastaJ').value=$('desde').value});
$('desde').addEventListener('change',function(){if($('relampago').checked||!$('hastaJ').value||$('hastaJ').value<this.value)$('hastaJ').value=this.value});
// sede: canchas de Pichangol (como `_SelectorSede`) + Google Maps
function paisDe(la,ln){var C={PE:[-18.4,-0.03,-81.4,-68.6],EC:[-5.1,1.7,-81.1,-75.1],BO:[-22.95,-9.6,-69.7,-57.4]};for(var k in C){var c=C[k];if(la>=c[0]&&la<=c[1]&&ln>=c[2]&&ln<=c[3])return k}return 'PE'}
function ponerPunto(la,ln){lat=la;lng=ln;$('ubicTxt').textContent=la.toFixed(5)+', '+ln.toFixed(5);if(mapa){if(marker)marker.setLatLng([la,ln]);else marker=L.marker([la,ln]).addTo(mapa);mapa.setView([la,ln],15)}
  iso=paisDe(la,ln);$('monSpan').textContent=CFG.monedas[iso]||'S/';$('docTxt').textContent=CFG.doc[iso]||'DNI'}
if(window.L){var c0=lat!=null?[lat,lng]:{PE:[-12.05,-77.04],EC:[-2.17,-79.92],BO:[-16.5,-68.15]}[iso];mapa=L.map('mapaSede').setView(c0,lat!=null?15:11);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(mapa);if(lat!=null)marker=L.marker([lat,lng]).addTo(mapa)}
var tSede=null,inSede=$('sede'),res=$('resSede');
function pintarRes(items,extra){res.hidden=false;res.innerHTML=items.map(function(x){return "<button type='button' class='res-it' data-nombre='"+esc(x.nombre)+"' data-lat='"+(x.lat==null?'':x.lat)+"' data-lng='"+(x.lng==null?'':x.lng)+"'><b>"+esc(x.nombre)+"</b><small>"+esc(x.direccion||x.club||'')+(x.km!=null?' · a '+x.km+' km':'')+"</small></button>"}).join('')+(extra||'')}
inSede.addEventListener('input',function(){clearTimeout(tSede);var q=this.value.trim().toLowerCase();if(q.length<2){res.hidden=true;return}
  var loc=CFG.canchas.filter(function(c){return (c.nombre+' '+c.direccion+' '+c.club).toLowerCase().indexOf(q)>=0}).slice(0,8);pintarRes(loc);
  if(CFG.buscar){tSede=setTimeout(function(){var c=mapa?mapa.getCenter():null;fetch('/web/lugares?q='+encodeURIComponent(q)+(c?'&lat='+c.lat+'&lng='+c.lng:'')).then(function(r){return r.json()}).then(function(j){if(inSede.value.trim().toLowerCase()!==q)return;pintarRes(loc.concat((j.lugares||[]).slice(0,6)))}).catch(function(){})},400)}});
res.addEventListener('click',function(ev){var b=ev.target.closest('.res-it');if(!b)return;inSede.value=b.dataset.nombre;res.hidden=true;if(b.dataset.lat)ponerPunto(parseFloat(b.dataset.lat),parseFloat(b.dataset.lng))});
document.addEventListener('click',function(ev){if(!ev.target.closest('#resSede')&&ev.target!==inSede)res.hidden=true});
// logo
function comprimir(file,M){return new Promise(function(ok,ko){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var k=Math.min(1,M/Math.max(img.width,img.height)),cv=document.createElement('canvas');cv.width=Math.round(img.width*k);cv.height=Math.round(img.height*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?ok(b):ko(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){ko(new Error('img'))};img.src=url})}
$('inLogo').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;subiendo++;$('logoMsg').textContent='Subiendo logo…';try{var blob=await comprimir(f,600);var r=await fetch('/anfitrion/campeonatos/'+encodeURIComponent(CFG.id)+'/foto?tipo=logo',{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});var j=await r.json();if(j.ok){logo=j.url;$('logoBox').innerHTML="<img src='"+esc(logo)+"' alt=''>";$('logoMsg').textContent='Listo.'}else $('logoMsg').textContent=j.error||'No se pudo subir.'}catch(e){$('logoMsg').textContent='No se pudo subir el logo.'}subiendo--});
// guardar (misma validación que el app: solo el nombre es obligatorio)
$('btnGuardar').addEventListener('click',async function(){var err=$('errGuardar');err.style.display='none';if(subiendo>0){pcgToast('Espera a que termine de subir el logo.');return}
  var cat=$('cat').value;if(cat==='otra')cat=$('catOtra').value.trim();
  var body={id:CFG.id,nombre:$('nombre').value,deporte:dep,formato:fmt,minPartidos:minPart,categoria:cat,minJugadoresEquipo:+$('minJug').value||0,desde:$('desde').value,hasta:$('relampago').checked?$('desde').value:$('hastaJ').value,cierre:$('cierre').value,
    sede:$('sede').value,lat:lat,lng:lng,costo:parseFloat(String($('costo').value).replace(',','.'))||0,relampago:$('relampago').checked,exigeDni:$('exigeDni').checked,edadMin:$('edadMin').value,edadMax:$('edadMax').value,auspiciador:$('ausp').value,premios:$('premios').value,logoUrl:logo};
  this.disabled=true;pcgCargando(CFG.nuevo?'Creando tu campeonato…':'Guardando cambios…');try{var r=await fetch('/anfitrion/campeonatos/guardar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){pcgIr('/anfitrion/campeonatos/'+encodeURIComponent(j.id)+(CFG.nuevo?'?creado=1':'?guardado=1'),'Abriendo tu campeonato…');return}pcgCargando(false);err.textContent=j.error||'No se pudo guardar.';err.style.display='block';if(j.paso)ir(j.paso)}catch(e){pcgCargando(false);err.textContent='No se pudo guardar. Revisa tu conexión.';err.style.display='block'}this.disabled=false});
})();
"""


@router.get(BASE + "/nuevo", response_class=HTMLResponse)
def pagina_nuevo(request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, BASE + "/nuevo")
    if resp is not None:
        return resp
    if not _pro(ses["email"]):
        return HTMLResponse("", status_code=302, headers={"Location": BASE})
    c = {"id": L.nuevo_id(), "academiaId": "", "dueno": ses["email"], "nombre": "", "deporte": "futbol", "formato": "liga", "categoria": "",
         "sede": "", "fechas": "", "costoInscripcion": 0, "inscripcionAbierta": True, "participantes": [], "partidos": [], "cerrado": False,
         "moneda": "", "relampago": False, "exigeDni": False, "premios": "", "auspiciador": ""}
    return _editor(ses, c, nuevo=True)


@router.get(BASE + "/{cid}/editar", response_class=HTMLResponse)
def pagina_editar(request: Request, cid: str) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"{BASE}/{cid}/editar")
    if resp is not None:
        return resp
    c = _mio(ses["email"], cid)
    if c is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Este campeonato no está a tu nombre"); r.status_code = 404
        return r
    return _editor(ses, c, nuevo=False)


def _id_ok(cid: str) -> bool:
    return bool(re.match(r"^camp_[0-9]{6,}$", cid or ""))


def _validar(b: dict, actual: dict | None, email: str) -> tuple[dict | None, str, int]:
    """`_guardar` de `crear_campeonato_screen`: la única validación es el nombre.
    Devuelve (data, error, paso del asistente donde está el error)."""
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:80]
    if not nombre:
        return None, "Ponle un nombre al campeonato.", 1
    nuevo = actual is None
    dep = str(actual.get("deporte")) if actual else str(b.get("deporte") or "")
    if dep not in catalogos.DEPORTES_CAMPEONATO:
        return None, "Elige el deporte.", 1
    if actual and L.fixture_generado(actual):
        fmt = L.formato_de(actual)
    else:
        fmt = str(b.get("formato") or "")
        if fmt not in catalogos.formatos_de(dep):
            fmt = catalogos.formato_por_defecto(dep)
    lat = lng = None
    try:
        if b.get("lat") is not None and b.get("lng") is not None and str(b.get("lat")) != "":
            lat, lng = float(b["lat"]), float(b["lng"])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
    except (TypeError, ValueError):
        return None, "Ubicación de la sede inválida.", 3

    def _d(v):
        try:
            return date.fromisoformat(str(v)[:10]) if v else None
        except ValueError:
            return None
    desde, hasta_j, cierre = _d(b.get("desde")), _d(b.get("hasta")), _d(b.get("cierre"))
    relampago = bool(b.get("relampago"))
    if desde and (relampago or not hasta_j or hasta_j < desde):
        hasta_j = desde
    if desde:
        fechas = L.fmt_rango(desde, hasta_j)
        inicio = datetime(desde.year, desde.month, desde.day).isoformat(timespec="milliseconds")
    else:
        fechas = str((actual or {}).get("fechas") or "")
        inicio = (actual or {}).get("inicio")
    try:
        costo = max(0.0, round(float(str(b.get("costo") or 0).replace(",", ".")), 2))
    except (TypeError, ValueError):
        costo = 0.0
    exige = bool(b.get("exigeDni"))

    def _int(v):
        try:
            return int(v) if str(v).strip() != "" else None
        except (TypeError, ValueError):
            return None
    edad_min, edad_max = (_int(b.get("edadMin")), _int(b.get("edadMax"))) if exige else (None, None)
    min_jug = max(0, _int(b.get("minJugadoresEquipo")) or 0) if dep == "futbol" else 0
    min_part = _int(b.get("minPartidos")) if fmt == "grupos" else None
    if fmt == "grupos" and min_part not in L.MIN_PARTIDOS:
        min_part = L.min_partidos(actual or {})
    sede = re.sub(r"\s+", " ", str(b.get("sede") or "")).strip()[:80]
    moneda = (paises.simbolo_de_moneda(paises.moneda_de_pais(paises.pais_de_coordenadas(lat, lng))) if lat is not None
              else ((actual or {}).get("moneda") or "S/"))
    carpeta = almacen.prefijo_carpeta("campeonatos") if almacen.disponible() else None
    logo = str(b.get("logoUrl") or "").strip()
    if not (logo and ((actual and logo == actual.get("logoUrl")) or (carpeta and logo.startswith(carpeta + b.get("id", "") + ".jpg")))):
        logo = str((actual or {}).get("logoUrl") or "")
    data = dict(actual or {})
    data.update({
        "id": b.get("id"), "academiaId": (actual or {}).get("academiaId") or "", "dueno": (actual or {}).get("dueno") or email,
        "nombre": nombre, "deporte": dep, "formato": fmt, "categoria": re.sub(r"\s+", " ", str(b.get("categoria") or "")).strip()[:40],
        "sede": sede, "fechas": fechas, "costoInscripcion": costo, "moneda": moneda, "relampago": relampago, "exigeDni": exige,
        "premios": str(b.get("premios") or "").strip()[:600], "auspiciador": str(b.get("auspiciador") or "").strip().upper()[:60],
        "minJugadoresEquipo": min_jug, "minPartidos": min_part,
    })
    if nuevo:
        data.update({"codigo": L.nuevo_codigo(), "inscripcionAbierta": True, "participantes": [], "partidos": [], "cerrado": False})
    for k, v in (("inicio", inicio), ("inscripcionHasta", datetime(cierre.year, cierre.month, cierre.day).isoformat(timespec="milliseconds") if cierre else None),
                 ("edadMin", edad_min), ("edadMax", edad_max), ("logoUrl", logo or None)):
        if v is None or v == "":
            data.pop(k, None)
        else:
            data[k] = v
    if lat is not None:
        data["sedeLat"], data["sedeLng"] = lat, lng
    else:
        data.pop("sedeLat", None); data.pop("sedeLng", None)
    # Claves que `toJson` omite cuando están vacías.
    for k in ("codigo", "pruebas", "premios", "auspiciador", "auspiciadoresLogos", "fotos", "aficheFondoUrl", "aficheTema"):
        if not data.get(k):
            data.pop(k, None)
    if not data.get("minJugadoresEquipo"):
        data.pop("minJugadoresEquipo", None)
    if not data.get("minPartidos"):
        data.pop("minPartidos", None)
    if not data.get("aficheVariante"):
        data.pop("aficheVariante", None)
    data.pop("_fin", None)
    return data, "", 0


@router.post(BASE + "/guardar")
def guardar(request: Request, b: dict | None = Body(None)) -> JSONResponse:
    ses, err = _sesion_json(request)
    if err is not None:
        return err
    if not isinstance(b, dict) or not _id_ok(str(b.get("id") or "")):
        return _err("Datos inválidos.")
    cid = str(b["id"])
    actual = _mio(ses["email"], cid)
    if actual is None and datos.campeonato_existe(cid):
        return _err("Este campeonato no está a tu nombre.", 404)
    if actual is None and not _pro(ses["email"]):
        return JSONResponse({"ok": False, "error": "requiere_pro", "mensaje": "Crear campeonatos es parte de Pichangol Pro. Actívalo en la app."}, status_code=402)
    data, msg, paso = _validar(b, actual, ses["email"])
    if data is None:
        return JSONResponse({"ok": False, "error": msg, "paso": paso}, status_code=400)
    if not datos.guardar_campeonato(cid, ses["email"], data):
        return _err("No pudimos guardar en este momento. Inténtalo de nuevo.", 503)
    print(f"[campeonato-web] {ses['email']} guardó {cid}: {data['nombre']} · {data['deporte']} · {data['formato']}", flush=True)
    return JSONResponse({"ok": True, "id": cid})


# ── Detalle del organizador (`CampeonatoDetalleScreen`, esDueno) ─────────────
def _publicidad(c: dict) -> str:
    """`_publicidad` del app: texto para WhatsApp mientras la inscripción está abierta."""
    dep, mon = str(c.get("deporte") or ""), _moneda(c)
    lineas = [f"🏆{_EMOJI.get(dep, '')} *{str(c.get('nombre') or '').upper()}*" + (f" by {c['auspiciador']}" if c.get("auspiciador") else ""), "",
              "¡Se viene un nuevo desafío! Inscríbete y demuestra de qué estás hecho 💪", "",
              f"⚔️ *{L.FORMATOS[L.formato_de(c)].upper()}*"]
    if c.get("fechas"):
        lineas.append(f"🏁 *Inicio*: {c['fechas']}")
    if c.get("categoria"):
        lineas.append(f"Categoría: {c['categoria']}")
    if c.get("sede"):
        lineas.append(f"📍 {c['sede']}")
    if c.get("premios"):
        lineas += ["", "🎁 *Premios*:"] + [f"✅ {p.strip()}" for p in str(c["premios"]).splitlines() if p.strip()]
    lineas.append("")
    lineas.append(f"💰 Inscripción: {mon} {float(c.get('costoInscripcion') or 0):.2f}" if float(c.get("costoInscripcion") or 0) > 0 else "Inscripción *GRATIS*")
    if c.get("auspiciador"):
        lineas.append(f"Gracias a nuestro auspiciador *{c['auspiciador']}*")
    if c.get("codigo"):
        lineas += ["", f"📲 Código para unirte: *{c['codigo']}*"]
    lineas += [f"👉 Inscríbete aquí: {_enlace(c)}", "", "vía *Pichangol* · Reserva, juega, repite."]
    return "\n".join(lineas)


def _resumen(c: dict) -> str:
    """`_resumen` del app: tabla / resultados / tiempos + enlace."""
    dep = str(c.get("deporte") or "")
    out = [f"🏆{_EMOJI.get(dep, '')} *{c.get('nombre') or ''}*"]
    fmt = L.formato_de(c)
    if fmt == "liga" and c.get("partidos"):
        out.append("📊 Tabla:")
        for i, f in enumerate(L.tabla(c)):
            out.append(f"{i + 1}. {f['nombre']} · {f['g'] * 3 + f['e']} pts")
    elif fmt == "grupos" and c.get("partidos"):
        for letra in L.grupos_de(c):
            out.append(f"📊 Grupo {letra}:")
            for i, f in enumerate(L.tabla_grupo(c, letra)):
                out.append(f"{i + 1}. {f['nombre']} · {f['g'] * 3 + f['e']} pts")
        jugados = [m for m in L.partidos_llave(c) if L.jugado(m)]
        if jugados:
            out.append("🏁 Fase final:")
            for m in jugados:
                out.append(f"• {(L.participante(c, m.get('aId')) or {}).get('nombre', '')} {m['marcadorA']}-{m['marcadorB']} {(L.participante(c, m.get('bId')) or {}).get('nombre', '')}")
    elif fmt == "tiempos":
        for p in c.get("pruebas") or []:
            out.append(f"🏊 {p.get('nombre')}:")
            for i, m in enumerate(L.ranking_prueba(p)[:3]):
                out.append(f"  {i + 1}. {(L.participante(c, m.get('participanteId')) or {}).get('nombre', '')} · {'DSQ' if m.get('dsq') else L.fmt_tiempo(m.get('centesimas'))}")
    else:
        for m in c.get("partidos") or []:
            if L.jugado(m):
                out.append(f"• {(L.participante(c, m.get('aId')) or {}).get('nombre', '')} {m['marcadorA']}-{m['marcadorB']} {(L.participante(c, m.get('bId')) or {}).get('nombre', '')}")
    out += ["", f"👉 {_enlace(c)}", "vía *Pichangol*"]
    return "\n".join(out)


def _participantes_html(c: dict) -> str:
    ps = c.get("participantes") or []
    chips = []
    for p in ps:
        if L.es_equipo(p):
            n = len(p.get("roster") or [])
            lab = (f"{p.get('nombre')} · {n}/{c.get('minJugadoresEquipo')}" + (" ✅" if L.equipo_completo(c, p) else "")) if L.usa_cupo_equipos(c) else f"{p.get('nombre')} · {n} jug."
            icono = "👥"
        elif L.es_menor(p):
            lab, icono = f"{p.get('nombre')} · apod. {p.get('apoderadoNombre')}", "🧒"
        else:
            lab, icono = str(p.get("nombre") or ""), ("✅" if p.get("email") else "👤")
        foto = f"<img src='{e(p['fotoUrl'])}' alt='' style='width:22px;height:22px;border-radius:50%;object-fit:cover'>" if p.get("fotoUrl") else f"<span>{icono}</span>"
        chips.append(f"<span class='chip part{' ok' if L.es_equipo(p) and L.equipo_completo(c, p) else ''}' data-pid='{e(p['id'])}' data-equipo='{1 if L.es_equipo(p) else 0}'>{foto} {e(lab)}<button type='button' class='x' data-quitar='{e(p['id'])}' title='Quitar'>✕</button></span>")
    return "".join(chips) or "<div class='anf-vacio'>Aún no hay inscritos. Agrega participantes o comparte el código para que se inscriban desde la app.</div>"


def _tile_partido(c: dict, m: dict) -> str:
    a, b = m.get("aId"), m.get("bId")
    na, nb = (L.participante(c, a) or {}).get("nombre") if a else None, (L.participante(c, b) or {}).get("nombre") if b else None
    r0 = int(m.get("ronda") or 0) == 0
    def _lado(pid, nombre):
        if pid is None:
            return "<i class='sub'>(bye)</i>" if (r0 and (a is None) != (b is None)) else "<i class='sub'>Por definir</i>"
        return e(nombre or "Por definir")
    g = L.ganador_id(m) if L.jugado(m) else None
    click = a is not None and b is not None
    sa = m.get("marcadorA") if L.jugado(m) else "–"
    sb = m.get("marcadorB") if L.jugado(m) else "–"
    return (f"<div class='partido{' clic' if click else ''}' data-pid='{e(m['id'])}' data-a='{e(na or '')}' data-b='{e(nb or '')}' data-ma='{'' if not L.jugado(m) else m['marcadorA']}' data-mb='{'' if not L.jugado(m) else m['marcadorB']}'>"
            f"<span class='lado{' win' if g and g == a else ''}'>{_lado(a, na)}</span><b class='mk'>{sa} - {sb}</b><span class='lado der{' win' if g and g == b else ''}'>{_lado(b, nb)}</span></div>")


def _tabla_html(filas: list[dict]) -> str:
    cuerpo = "".join(f"<tr><td>{i + 1}</td><td style='text-align:left'>{e(f['nombre'])}</td><td>{f['pj']}</td><td>{f['g']}</td><td>{f['e']}</td><td>{f['p']}</td><td>{f['gf'] - f['gc']}</td><td><b>{f['g'] * 3 + f['e']}</b></td></tr>"
                    for i, f in enumerate(filas))
    return f"<div class='tabla'><table><thead><tr><th>#</th><th style='text-align:left'>Equipo</th><th>PJ</th><th>G</th><th>E</th><th>P</th><th>Dif</th><th>Pts</th></tr></thead><tbody>{cuerpo}</tbody></table></div>"


def _llave_html(c: dict, partidos: list[dict]) -> str:
    rondas = sorted({int(p.get("ronda") or 0) for p in partidos})
    max_r = rondas[-1] if rondas else 0
    return "<div class='llave'>" + "".join(
        f"<div class='col'><h4>{e(L.etiqueta_ronda(r, max_r))}</h4>" + "".join(_tile_partido(c, m) for m in sorted((p for p in partidos if int(p.get('ronda') or 0) == r), key=lambda x: int(x.get('idx') or 0))) + "</div>"
        for r in rondas) + "</div>"


def _grupos_html(c: dict) -> str:
    """Formato grupos: una tabla + jornadas por grupo y debajo la fase final
    (la llave se siembra sola cuando terminan todos los partidos de grupo)."""
    out = []
    for letra in L.grupos_de(c):
        ms = sorted((m for m in L.partidos_grupo(c) if m.get("grupo") == letra), key=lambda x: (int(x.get("ronda") or 0), int(x.get("idx") or 0)))
        jornadas = sorted({int(p.get("ronda") or 0) for p in ms})
        js = "".join(f"<h4>Jornada {j + 1}</h4>" + "".join(_tile_partido(c, m) for m in ms if int(m.get("ronda") or 0) == j) for j in jornadas)
        out.append(f"<div class='grupo'><h3 style='margin-top:14px'>Grupo {letra}</h3>{_tabla_html(L.tabla_grupo(c, letra))}{js}</div>")
    llave = L.partidos_llave(c)
    aviso = ("" if L.grupos_completos(c) else "<p class='sub' style='margin:0 0 6px'>Los cruces se definen solos cuando termine la fase de grupos (clasifican los 2 primeros de cada grupo).</p>")
    out.append(f"<h3 style='margin-top:22px'>Fase final</h3>{aviso}{_llave_html(c, llave)}")
    return "".join(out)


def _fixture_html(c: dict) -> str:
    fmt = L.formato_de(c)
    partidos = c.get("partidos") or []
    if fmt == "grupos":
        return _grupos_html(c)
    if fmt == "liga":
        filas = "".join(f"<tr><td>{i + 1}</td><td style='text-align:left'>{e(f['nombre'])}</td><td>{f['pj']}</td><td>{f['g']}</td><td>{f['e']}</td><td>{f['p']}</td><td>{f['gf'] - f['gc']}</td><td><b>{f['g'] * 3 + f['e']}</b></td></tr>"
                        for i, f in enumerate(L.tabla(c)))
        tabla = f"<div class='tabla'><table><thead><tr><th>#</th><th style='text-align:left'>Equipo</th><th>PJ</th><th>G</th><th>E</th><th>P</th><th>Dif</th><th>Pts</th></tr></thead><tbody>{filas}</tbody></table></div>"
        jornadas = sorted({int(p.get("ronda") or 0) for p in partidos})
        js = "".join(f"<h4>Jornada {j + 1}</h4>" + "".join(_tile_partido(c, m) for m in sorted((p for p in partidos if int(p.get('ronda') or 0) == j), key=lambda x: int(x.get('idx') or 0))) for j in jornadas)
        return tabla + js
    rondas = sorted({int(p.get("ronda") or 0) for p in partidos})
    max_r = rondas[-1] if rondas else 0
    return "<div class='llave'>" + "".join(
        f"<div class='col'><h4>{e(L.etiqueta_ronda(r, max_r))}</h4>" + "".join(_tile_partido(c, m) for m in sorted((p for p in partidos if int(p.get('ronda') or 0) == r), key=lambda x: int(x.get('idx') or 0))) + "</div>"
        for r in rondas) + "</div>"


def _natacion_html(c: dict) -> str:
    pruebas = c.get("pruebas") or []
    out = []
    for p in pruebas:
        rank = L.ranking_prueba(p)
        con = {m.get("participanteId") for m in (p.get("marcas") or []) if L.marca_registrada(m)}
        filas = []
        for i, m in enumerate(rank):
            pid = m.get("participanteId")
            medalla = {0: "🥇", 1: "🥈", 2: "🥉"}.get(i, str(i + 1)) if not m.get("dsq") else "—"
            sc = " · ".join(x for x in ((f"S{m['serie']}" if m.get("serie") else ""), (f"C{m['carril']}" if m.get("carril") else "")) if x)
            filas.append(f"<div class='marca clic' data-prueba='{e(p['id'])}' data-pid='{e(pid)}' data-t='{'' if m.get('dsq') else L.fmt_tiempo(m.get('centesimas'))}' data-s='{m.get('serie') or ''}' data-c='{m.get('carril') or ''}' data-dsq='{1 if m.get('dsq') else 0}'>"
                         f"<span class='pos'>{medalla}</span><span class='nom'>{e((L.participante(c, pid) or {}).get('nombre', ''))}{(' <small class=sub>' + e(sc) + '</small>') if sc else ''}</span><b>{'DSQ' if m.get('dsq') else L.fmt_tiempo(m.get('centesimas'))}</b></div>")
        for part in c.get("participantes") or []:
            if part["id"] not in con:
                filas.append(f"<div class='marca clic sin' data-prueba='{e(p['id'])}' data-pid='{e(part['id'])}' data-t='' data-s='' data-c='' data-dsq='0'><span class='pos'>·</span><span class='nom'>{e(part.get('nombre', ''))}</span><i class='sub'>Sin tiempo</i></div>")
        out.append(f"<div class='panel prueba'><div style='display:flex;justify-content:space-between;align-items:center'><h3 style='margin:0'>🏊 {e(p.get('nombre') or 'Prueba')}</h3>"
                   f"<button type='button' class='chip' data-quitar-prueba='{e(p['id'])}'>🗑 Eliminar prueba</button></div>{''.join(filas) or '<p class=sub>Sin nadadores inscritos.</p>'}</div>")
    return "".join(out) or "<div class='anf-vacio'>Aún no hay pruebas. Agrega la primera (50m Libre, 100m Espalda…).</div>"


@router.get(BASE + "/{cid}", response_class=HTMLResponse)
def pagina_detalle(request: Request, cid: str, creado: str = "", guardado: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"{BASE}/{cid}")
    if resp is not None:
        return resp
    c = _mio(ses["email"], cid)
    if c is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Este campeonato no está a tu nombre"); r.status_code = 404
        return r
    dep, fmt, mon = str(c.get("deporte") or ""), L.formato_de(c), _moneda(c)
    tiempos = fmt == "tiempos"
    iso = _pais(c)
    aviso = ("<div class='aviso ok'>✅ Campeonato creado. Comparte el código para que se inscriban.</div>" if creado else
             "<div class='aviso ok'>✅ Cambios guardados.</div>" if guardado else "")
    chips_cab = [f"<span class='pill'>{_EMOJI.get(dep, '')} {e(_NOMBRE.get(dep, dep))}</span>", f"<span class='pill'>{e(L.FORMATOS[fmt])}</span>"]
    if c.get("categoria"):
        chips_cab.append(f"<span class='pill'>{e(c['categoria'])}</span>")
    if c.get("fechas"):
        chips_cab.append(f"<span class='pill'>📅 {e(c['fechas'])}</span>")
    if c.get("sede"):
        chips_cab.append(f"<span class='pill'>📍 {e(c['sede'])}</span>")
    chips_cab.append(f"<span class='pill'>Inscripción {e(mon)} {float(c.get('costoInscripcion') or 0):.2f}</span>")
    info = []
    if fmt == "grupos":
        tams = L.armar_grupos(len(c.get("participantes") or []), L.min_partidos(c))
        info.append(f"<span class='chip'>🧩 Grupos + llave · cada equipo juega al menos {L.min_partidos(c)} partidos" + (f" · {len(tams)} grupo{'s' if len(tams) != 1 else ''} de {'/'.join(str(t) for t in tams)}" if tams else " · con menos de 3 equipos se juega solo la final") + "</span>")
    if c.get("inscripcionHasta"):
        info.append(f"<span class='chip'>🗓️ Cierre inscrip.: {e(_fecha_corta(c['inscripcionHasta']))}</span>")
    if c.get("relampago"):
        info.append("<span class='chip'>⚡ Relámpago</span>")
    if c.get("exigeDni"):
        info.append(f"<span class='chip'>🪪 Exige {_DOC.get(iso, 'DNI')}</span>")
    if c.get("edadMin") is not None or c.get("edadMax") is not None:
        info.append(f"<span class='chip'>🎂 {('desde ' + str(c['edadMin']) + ' ') if c.get('edadMin') is not None else ''}{('hasta ' + str(c['edadMax']) + ' ') if c.get('edadMax') is not None else ''}años</span>")
    camp, sub = (None, None) if tiempos else L.campeon_y_subcampeon(c)
    podio = ""
    if not tiempos and L.terminado(c) and camp:
        podio = (f"<div class='panel podio'><b>🏁 TORNEO FINALIZADO</b><div>🥇 {e((L.participante(c, camp) or {}).get('nombre', ''))}</div>"
                 f"{('<div>🥈 ' + e((L.participante(c, sub) or {}).get('nombre', '')) + '</div>') if sub else ''}</div>")
    enlace = _enlace(c)
    texto_wa = _publicidad(c) if (not c.get("cerrado") and not L.fixture_generado(c) and not tiempos) else _resumen(c)
    boton_wa = ui.boton_whatsapp(texto_wa)  # PC sin emojis · móvil completo (ver ui.boton_whatsapp)
    logo = f"<img src='{e(c['logoUrl'])}' alt=''>" if c.get("logoUrl") else f"<span>{_EMOJI.get(dep, '🏆')}</span>"
    ausp = "".join(f"<div class='foto' data-url='{e(u)}'><img src='{e(u)}' alt=''><div class='acc'><button type='button' class='mini' data-quitar-img='ausp' title='Quitar'>✕</button></div></div>" for u in (c.get("auspiciadoresLogos") or []))
    fotos = "".join(f"<div class='foto' data-url='{e(u)}'><img src='{e(u)}' alt=''><div class='acc'><a class='mini' href='{e(u)}' target='_blank' rel='noopener' title='Ver' style='text-decoration:none;display:flex;align-items:center;justify-content:center'>🔍</a><button type='button' class='mini' data-quitar-img='foto' title='Quitar'>✕</button></div></div>" for u in (c.get("fotos") or []))
    circuito = dep in catalogos.DEPORTES_CIRCUITO
    ubic = (f"<a class='btn sec' href='https://www.google.com/maps/search/?api=1&query={c['sedeLat']},{c['sedeLng']}' target='_blank' rel='noopener'>📍 Ubicación · cómo llegar</a>"
            if c.get("sedeLat") is not None else "")
    cfg = {"id": c["id"], "nombre": c.get("nombre") or "", "deporte": dep, "formato": fmt, "codigo": c.get("codigo") or "", "enlace": enlace, "temas": catalogos.AFICHE_TEMAS,
           "variantes": catalogos.AFICHE_VARIANTES, "variante": int(c.get("aficheVariante") or 0), "tema": c.get("aficheTema") or "",
           "fondo": c.get("aficheFondoUrl") or "", "storage": almacen.disponible(), "distancias": L.DISTANCIAS, "estilos": L.ESTILOS,
           "participantes": [{"id": p["id"], "nombre": p.get("nombre"), "email": p.get("email") or "", "contacto": p.get("contacto") or "", "capitanEmail": p.get("capitanEmail") or "",
                              "codigo": p.get("codigo") or "", "roster": p.get("roster") or []} for p in (c.get("participantes") or [])],
           "minJug": int(c.get("minJugadoresEquipo") or 0), "fixture": L.fixture_generado(c), "arte": _base_url() or ""}
    cuerpo = f"""
<style>
.det{{max-width:920px;margin:0 auto}}.det .panel{{margin-top:14px;padding:18px 20px}}.det h3{{margin:0 0 8px;font-size:17px}}
.cab-camp{{display:flex;gap:16px;align-items:center;flex-wrap:wrap}}.cab-camp .logo-pick{{cursor:pointer}}.cab-camp h1{{margin:0;font-size:26px}}
.podio{{background:#E6F4EF;border:0;text-align:center;font-size:17px}}.podio b{{display:block;color:#0B7A55;margin-bottom:6px}}
.codigo{{font-family:ui-monospace,Menlo,monospace;font-size:34px;font-weight:800;letter-spacing:.14em;text-align:center;background:var(--gris);border-radius:16px;padding:14px;cursor:pointer;user-select:all}}
.chip.part{{position:relative;padding-right:34px}}.chip.part.ok{{background:#EAF7E1;border-color:#9CD47A}}.chip.part .x{{position:absolute;right:6px;top:50%;transform:translateY(-50%);border:0;background:transparent;font-weight:800;cursor:pointer;color:var(--tenue);font-family:inherit}}
.partido{{display:grid;grid-template-columns:1fr auto 1fr;gap:10px;align-items:center;border:1px solid var(--trazo);border-radius:12px;padding:10px 14px;margin-top:8px}}.partido.clic{{cursor:pointer}}.partido.clic:hover{{border-color:var(--noche)}}
.partido .lado{{font-weight:600}}.partido .lado.der{{text-align:right}}.partido .lado.win{{font-weight:900}}.partido .mk{{font-family:ui-monospace,Menlo,monospace;font-size:16px;white-space:nowrap}}
.llave{{display:flex;gap:16px;overflow-x:auto;padding-bottom:6px}}.llave .col{{min-width:260px;flex:1}}.llave h4,.det h4{{margin:14px 0 4px;font-size:14px;color:var(--tenue)}}
.marca{{display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--trazo);padding:8px 2px}}.marca .pos{{width:28px;text-align:center}}.marca .nom{{flex:1}}.marca.clic{{cursor:pointer}}.marca.sin .nom{{color:var(--tenue)}}
.edit-fotos{{margin-top:10px}}.galeria-arte{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}}.galeria-arte img{{width:100%;border-radius:12px;cursor:pointer;border:3px solid transparent}}.galeria-arte img.sel{{border-color:var(--esmeralda)}}
.mod-form label{{display:block;margin-top:12px;font-weight:700}}.mod-form input,.mod-form select{{width:100%;margin-top:6px}}
</style>
<div class='det'><a class='anf-back' href='{BASE}'>‹ Mis campeonatos</a>{aviso}
<div class='panel cab-camp'><label class='logo-pick' for='inLogo' id='logoBox' title='Cambiar logo'>{logo}</label><input type='file' id='inLogo' accept='image/*' hidden{'' if almacen.disponible() else ' disabled'}>
 <div style='flex:1;min-width:220px'><h1>{e(c.get('nombre') or '')}</h1><div class='chips' style='margin-top:8px;gap:6px'>{''.join(chips_cab)}</div><div style='margin-top:10px'>{_estado_pill(c)}</div></div></div>
{podio}
{("<div class='acciones' style='margin-top:12px'>" + ubic + "</div>") if ubic else ''}
<div class='panel'><h3>Invitar</h3>{("<div class='codigo' id='codigo' title='Copiar código'>" + e(c['codigo']) + "</div><p class='sub' style='text-align:center;font-size:12.5px'>Código para unirse desde la app · toca para copiar</p>") if c.get('codigo') else ''}
 <div class='acciones' style='flex-wrap:wrap'>{boton_wa}<button type='button' class='btn sec' id='btnEnlace'>🔗 Copiar enlace</button>
 <a class='btn sec' href='{enlace}/afiche.png' target='_blank' rel='noopener'>🖼️ Ver afiche</a><button type='button' class='btn sec' id='btnFondo'>🎨 Cambiar fondo del afiche</button><a class='btn sec' href='{e(enlace)}' target='_blank' rel='noopener'>🌐 Página pública</a></div></div>
<div class='panel'><h3>Auspiciadores</h3><p class='sub' style='margin:0'>Logos de tus auspiciadores: salen en el afiche y en la página pública.</p>
 <div class='edit-fotos' id='ausp'>{ausp}</div><div class='acciones' style='margin-top:10px'><label class='btn sec' for='inAusp'>＋ Agregar logo</label><input type='file' id='inAusp' accept='image/*' hidden{'' if almacen.disponible() else ' disabled'}><span class='sub' id='auspMsg' style='margin:0'></span></div></div>
{("<div class='chips' style='margin-top:12px'>" + ''.join(info) + "</div>") if info else ''}
<div class='panel'><div style='display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap'><h3 style='margin:0'>Participantes ({len(c.get('participantes') or [])})</h3><button type='button' class='btn sec' id='btnAgregar'>＋ {'Nuevo equipo' if dep == 'futbol' else 'Agregar'}</button></div>
 <div class='chips' id='participantes' style='margin-top:12px'>{_participantes_html(c)}</div>
 {'' if tiempos else "<div class='acciones' style='margin-top:14px'><button type='button' class='btn' id='btnFixture'>" + ('🔁 Regenerar fixture' if L.fixture_generado(c) else '🎲 Generar fixture') + "</button></div>"}</div>
{'' if tiempos or not L.fixture_generado(c) else "<div class='panel'><h3>" + ('Tabla y partidos' if fmt == 'liga' else 'Grupos y fase final' if fmt == 'grupos' else 'Llave') + "</h3><p class='sub' style='margin:0 0 6px'>Toca un partido para cargar el resultado.</p>" + _fixture_html(c) + ("<div class='acciones' style='margin-top:14px'><button type='button' class='btn sec' id='btnRanking'>📈 Sumar resultados al ranking</button></div>" if circuito and c.get('academiaId') else '') + "</div>"}
{("<div class='panel'><div style='display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap'><h3 style='margin:0'>Pruebas</h3><button type='button' class='btn sec' id='btnPrueba'>＋ Agregar prueba</button></div><p class='sub' style='margin:6px 0 0'>Toca un nadador para registrar su tiempo, serie y carril.</p><div id='pruebas' style='margin-top:10px'>" + _natacion_html(c) + "</div></div>") if tiempos else ''}
<div class='panel'><h3>Galería del torneo</h3><div class='edit-fotos' id='fotos'>{fotos}</div><div class='acciones' style='margin-top:10px'><label class='btn sec' for='inFotos'>📷 Agregar fotos</label><input type='file' id='inFotos' accept='image/*' multiple hidden{'' if almacen.disponible() else ' disabled'}><span class='sub' id='fotosMsg' style='margin:0'></span></div></div>
<div class='acciones' style='margin-top:18px;flex-wrap:wrap'><a class='btn' href='{BASE}/{e(c['id'])}/editar'>✏️ Editar campeonato</a><button type='button' class='btn sec' id='btnDuplicar'>📄 Duplicar campeonato (nueva edición)</button><button type='button' class='btn sec' id='btnEliminar' style='color:var(--rojo)'>🗑 Eliminar campeonato</button></div>
</div>
<div class='modal' id='modal' role='dialog' aria-modal='true'><div class='modal-caja' style='max-width:520px'><div class='modal-cab'><button type='button' class='cerrar' id='modalCerrar'>✕</button><h3 id='modalTit'></h3></div><div class='modal-cuerpo mod-form' id='modalCuerpo'></div></div></div>
<script>var CFG={json.dumps(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{_JS_DETALLE}</script>"""
    return ui.shell(c.get("nombre") or "Campeonato", cuerpo, nav=_cab(ses), sesion=ses, ancho=True, titulo_tab=f"{c.get('nombre') or 'Campeonato'} · Mis campeonatos")


_JS_DETALLE = r"""
(function(){
function $(id){return document.getElementById(id)}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}
var B='/anfitrion/campeonatos/'+encodeURIComponent(CFG.id);
async function post(ruta,body,msg){pcgCargando(msg||'Guardando…',{demora:300});try{var r=await fetch(B+ruta,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});var j=await r.json().catch(function(){return {}});if(!j.ok)throw new Error(j.error||j.mensaje||'No se pudo.');return j}finally{pcgCargando(false)}}
function modal(tit,html,onOk){$('modalTit').textContent=tit;$('modalCuerpo').innerHTML=html;$('modal').classList.add('open');var f=$('modalCuerpo').querySelector('input,select');if(f)setTimeout(function(){f.focus()},60);var ok=$('modalOk');if(ok)ok.onclick=onOk}
function cerrar(){$('modal').classList.remove('open')}
$('modalCerrar').addEventListener('click',cerrar);$('modal').addEventListener('click',function(ev){if(ev.target===$('modal'))cerrar()});
function pie(txt){return "<div class='acciones' style='margin-top:16px'><button type='button' class='btn' id='modalOk'>"+txt+"</button></div><div class='estado bad' id='modalErr' style='display:none'></div>"}
function err(m){var el=$('modalErr');if(el){el.textContent=m;el.style.display='block'}else pcgToast(m)}
// código / enlace
var cod=$('codigo');if(cod)cod.addEventListener('click',function(){navigator.clipboard&&navigator.clipboard.writeText(CFG.codigo).then(function(){pcgToast('Código copiado')})});
document.addEventListener('click',function(ev){var b=ev.target.closest('[data-copiar-eq]');if(!b)return;navigator.clipboard&&navigator.clipboard.writeText(b.dataset.copiarEq).then(function(){pcgToast('Enlace del equipo copiado')})});
$('btnEnlace').addEventListener('click',function(){navigator.clipboard&&navigator.clipboard.writeText(CFG.enlace).then(function(){pcgToast('Enlace copiado')})});
// imágenes
function comprimir(file,M){return new Promise(function(ok,ko){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var k=Math.min(1,M/Math.max(img.width,img.height)),cv=document.createElement('canvas');cv.width=Math.round(img.width*k);cv.height=Math.round(img.height*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?ok(b):ko(new Error('img'))},'image/jpeg',0.86)};img.onerror=function(){ko(new Error('img'))};img.src=url})}
async function subir(file,tipo,M,msg){pcgCargando(msg||'Subiendo imagen…');try{var blob=await comprimir(file,M);var r=await fetch(B+'/foto?tipo='+tipo,{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});return await r.json()}finally{pcgCargando(false)}}
$('inLogo').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;try{var j=await subir(f,'logo',600,'Subiendo logo…');if(j.ok){pcgRecargar();return}pcgToast(j.error||'No se pudo subir.')}catch(e){pcgToast('No se pudo subir el logo.')}});
$('inAusp').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;$('auspMsg').textContent='Subiendo…';try{var j=await subir(f,'ausp',800,'Subiendo logo del auspiciador…');if(j.ok){pcgRecargar();return}$('auspMsg').textContent=j.error||'No se pudo subir.'}catch(e){$('auspMsg').textContent='No se pudo subir.'}});
$('inFotos').addEventListener('change',async function(){var files=Array.prototype.slice.call(this.files||[]);this.value='';for(var i=0;i<files.length;i++){$('fotosMsg').textContent='Subiendo foto '+(i+1)+' de '+files.length+'…';try{var j=await subir(files[i],'foto',1400,'Subiendo foto '+(i+1)+' de '+files.length+'…');if(!j.ok){$('fotosMsg').textContent=j.error||'No se pudo subir.';return}}catch(e){$('fotosMsg').textContent='No se pudo subir.';return}}pcgRecargar()});
document.addEventListener('click',async function(ev){var b=ev.target.closest('[data-quitar-img]');if(!b)return;var url=b.closest('.foto').dataset.url;if(!await pcgConfirmar({titulo:'Quitar imagen',mensaje:'La imagen se borra del campeonato y del afiche.',confirmar:'Quitar',destructivo:true}))return;try{await post('/imagen/quitar',{tipo:b.dataset.quitarImg,url:url},'Quitando…');pcgRecargar()}catch(e){pcgToast(e.message)}});
// afiche: fondo propio / arte IA por tema / quitar
$('btnFondo').addEventListener('click',function(){var r=Math.floor(Math.random()*1e6);
  var temas=CFG.temas.map(function(t){return "<button type='button' class='chip"+(t[0]===CFG.tema?' sel':'')+"' data-tema='"+esc(t[0])+"'>"+esc(t[1])+"</button>"}).join('')+"<button type='button' class='chip' data-tema='__mi'>Mi idea ✍️</button>";
  modal('Fondo del afiche',"<section><label class='btn sec' for='inFondo' style='margin-top:12px'>📷 Usar una foto mía</label><input type='file' id='inFondo' accept='image/*' hidden"+(CFG.storage?'':' disabled')+"><div class='sub' id='fondoMsg' style='margin:6px 0 0'></div></section>"+
    "<section><b>Elegir el arte IA (galería)</b><div class='chips' id='temas' style='margin-top:10px'>"+temas+"</div><input id='miIdea' type='text' maxlength='140' placeholder='Describe tu idea (máx. 140)' hidden style='margin-top:8px'><div class='galeria-arte' id='arte'></div></section>"+
    (CFG.fondo?"<section><button type='button' class='btn sec' id='btnQuitarFondo'>🗑 Quitar mi foto</button></section>":''),null);
  var tema=CFG.tema;function pintar(){$('arte').innerHTML='';for(var v=0;v<CFG.variantes;v++){var img=document.createElement('img');img.src=CFG.arte+'/afiche/fondo/'+CFG.deporte+'/'+v+'?r='+r+'&tema='+encodeURIComponent(tema);img.dataset.v=v;if(!CFG.fondo&&tema===CFG.tema&&(CFG.variante%CFG.variantes)===v)img.className='sel';img.onerror=function(){this.style.display='none'};$('arte').appendChild(img)}}
  $('temas').addEventListener('click',function(ev){var b=ev.target.closest('[data-tema]');if(!b)return;$('temas').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel');if(b.dataset.tema==='__mi'){$('miIdea').hidden=false;$('miIdea').focus()}else{$('miIdea').hidden=true;tema=b.dataset.tema;pintar()}});
  $('miIdea').addEventListener('change',function(){tema=this.value.trim();pintar()});
  $('arte').addEventListener('click',async function(ev){var img=ev.target.closest('img');if(!img)return;try{await post('/afiche',{variante:+img.dataset.v,tema:tema});pcgRecargar('Aplicando el fondo…')}catch(e){pcgToast(e.message)}});
  $('inFondo').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;$('fondoMsg').textContent='Subiendo…';try{var j=await subir(f,'fondo',1600,'Subiendo tu foto…');if(j.ok){pcgRecargar();return}$('fondoMsg').textContent=j.error||'No se pudo subir.'}catch(e){$('fondoMsg').textContent='No se pudo subir.'}});
  var q=$('btnQuitarFondo');if(q)q.addEventListener('click',async function(){try{await post('/afiche',{quitar:true},'Quitando…');pcgRecargar()}catch(e){pcgToast(e.message)}});
  pintar()});
// participantes
$('btnAgregar').addEventListener('click',function(){var eq=CFG.deporte==='futbol';
  modal(eq?'Nuevo equipo':'Nuevo participante',"<label>"+(eq?'Nombre del equipo':'Nombre (jugador o pareja "A / B")')+"</label><input id='pNombre' type='text' maxlength='80'><label>WhatsApp <span class='req'>opcional</span></label><input id='pTel' type='text' inputmode='tel' maxlength='20'>"+pie('Agregar'),
    async function(){try{await post('/participante',{nombre:$('pNombre').value,contacto:$('pTel').value});pcgRecargar()}catch(e){err(e.message)}})});
document.addEventListener('click',async function(ev){var q=ev.target.closest('[data-quitar]');if(q){ev.stopPropagation();var pq=CFG.participantes.filter(function(x){return x.id===q.dataset.quitar})[0];if(!await pcgConfirmar({titulo:'Quitar participante',mensaje:'¿Quitas a '+(pq?pq.nombre:'este participante')+' del campeonato?',confirmar:'Quitar',destructivo:true}))return;try{await post('/participante/'+encodeURIComponent(q.dataset.quitar)+'/eliminar',{},'Quitando…');pcgRecargar()}catch(e){pcgToast(e.message)}return}
  var ch=ev.target.closest('.chip.part[data-equipo="1"]');if(ch){var p=CFG.participantes.filter(function(x){return x.id===ch.dataset.pid})[0];if(!p)return;
    var falta=CFG.minJug>0?(p.roster.length>=CFG.minJug?"<span class='pill'>Completo</span>":"<span class='pill' style='background:#FFF1E3;color:#B25E0A'>Faltan "+(CFG.minJug-p.roster.length)+"</span>"):'';
    var enlaceEq=p.codigo?CFG.enlace+'?equipo='+encodeURIComponent(p.codigo):'';
    var invitar=enlaceEq?"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:8px'><button type='button' class='btn sec' data-copiar-eq='"+esc(enlaceEq)+"'>🔗 Copiar enlace del equipo</button><a class='btn sec' target='_blank' rel='noopener' href='https://wa.me/?text="+encodeURIComponent('Únete a mi equipo «'+p.nombre+'» en "'+CFG.nombre+'" (Pichangol). Toca y quedas inscrito: '+enlaceEq)+"'>💬 WhatsApp</a></div><p class='sub' style='margin:6px 0 0;font-size:12px'>Quien abra el enlace con la app entra directo al equipo, sin escribir el código.</p>":'';
    modal(p.nombre,"<section><div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><b>Código: "+esc(p.codigo||'—')+"</b>"+falta+"</div><p class='sub' style='margin:6px 0 0'>Capitán: "+esc(p.capitanEmail||'—')+"</p>"+invitar+"</section><section><b>Plantel ("+p.roster.length+")</b>"+
      (p.roster.map(function(i){return "<div class='marca'><span class='pos'>"+(i.email?'✅':'👤')+"</span><span class='nom'>"+esc(i.nombre)+(i.email&&i.email===p.capitanEmail?" <span class='pill'>Capitán</span>":'')+"</span></div>"}).join('')||"<p class='sub'>Sin jugadores aún. El capitán los agrega desde la app.</p>")+"</section>",null)}});
var bf=$('btnFixture');if(bf)bf.addEventListener('click',async function(){if(CFG.participantes.length<2){pcgToast('Agrega al menos 2 participantes.');return}
  if(CFG.fixture&&!await pcgConfirmar({titulo:'Regenerar fixture',mensaje:'Se sortea de nuevo y se BORRAN los resultados cargados.',confirmar:'Regenerar',destructivo:true,icono:'🔁'}))return;try{await post('/fixture',{},'Sorteando el fixture…');pcgRecargar()}catch(e){pcgToast(e.message)}});
// resultado
document.addEventListener('click',function(ev){var t=ev.target.closest('.partido.clic');if(!t)return;
  modal('Cargar resultado',"<div class='row' style='grid-template-columns:1fr 1fr;gap:10px'><div><label>"+esc(t.dataset.a)+"</label><input id='mA' type='number' min='0' inputmode='numeric' value='"+esc(t.dataset.ma)+"'></div><div><label>"+esc(t.dataset.b)+"</label><input id='mB' type='number' min='0' inputmode='numeric' value='"+esc(t.dataset.mb)+"'></div></div>"+pie('Guardar'),
    async function(){var a=$('mA').value,b=$('mB').value;if(a===''||b===''){err('Escribe ambos marcadores.');return}try{await post('/resultado',{partido:t.dataset.pid,a:+a,b:+b});pcgRecargar()}catch(e){err(e.message)}})});
var br=$('btnRanking');if(br)br.addEventListener('click',async function(){try{var j=await post('/ranking',{},'Sumando al ranking…');pcgToast(j.n?j.n+' partido(s) sumado(s) al ranking de la academia.':'Aún no hay partidos jugados para sumar.')}catch(e){pcgToast(e.message)}});
// natación
var bp=$('btnPrueba');if(bp)bp.addEventListener('click',function(){
  modal('Agregar prueba',"<label>Distancia</label><div class='chips' id='dist'>"+CFG.distancias.map(function(d){return "<button type='button' class='chip"+(d===50?' sel':'')+"' data-v='"+d+"'>"+d+" m</button>"}).join('')+"</div><label>Estilo</label><div class='chips' id='est'>"+CFG.estilos.map(function(s){return "<button type='button' class='chip"+(s==='Libre'?' sel':'')+"' data-v='"+esc(s)+"'>"+esc(s)+"</button>"}).join('')+"</div>"+pie('Agregar prueba'),
    async function(){var d=$('dist').querySelector('.sel').dataset.v,s=$('est').querySelector('.sel').dataset.v;try{await post('/prueba',{distancia:+d,estilo:s});pcgRecargar()}catch(e){err(e.message)}});
  $('modalCuerpo').addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-v]');if(!b)return;b.parentNode.querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel')})});
document.addEventListener('click',async function(ev){var q=ev.target.closest('[data-quitar-prueba]');if(q){if(!await pcgConfirmar({titulo:'Eliminar prueba',mensaje:'Se borra la prueba y todos sus tiempos registrados.',confirmar:'Eliminar',destructivo:true}))return;try{await post('/prueba/'+encodeURIComponent(q.dataset.quitarPrueba)+'/eliminar',{},'Eliminando…');pcgRecargar()}catch(e){pcgToast(e.message)}return}
  var m=ev.target.closest('.marca.clic');if(!m)return;
  modal('Tiempo de '+m.querySelector('.nom').firstChild.textContent.trim(),"<label>Tiempo (mm:ss.cc)</label><input id='tT' type='text' placeholder='ej. 0:37.85' value='"+esc(m.dataset.t)+"'><div class='row' style='grid-template-columns:1fr 1fr;gap:10px'><div><label>Serie</label><input id='tS' type='number' min='0' value='"+esc(m.dataset.s)+"'></div><div><label>Carril</label><input id='tC' type='number' min='0' value='"+esc(m.dataset.c)+"'></div></div><label style='display:flex;gap:8px;align-items:center'><input type='checkbox' id='tD' style='width:auto;margin:0'"+(m.dataset.dsq==='1'?' checked':'')+"> Descalificado (DSQ)</label>"+pie('Guardar'),
    async function(){try{await post('/marca',{prueba:m.dataset.prueba,participante:m.dataset.pid,tiempo:$('tT').value,serie:+$('tS').value||0,carril:+$('tC').value||0,dsq:$('tD').checked});pcgRecargar()}catch(e){err(e.message)}})});
// duplicar / eliminar
$('btnDuplicar').addEventListener('click',async function(){if(!await pcgConfirmar({titulo:'Nueva edición',mensaje:'Se crea un campeonato nuevo con los mismos datos, sin participantes ni resultados. Luego le pones las fechas.',confirmar:'Crear nueva edición',icono:'📄'}))return;try{var j=await post('/duplicar',{},'Creando la nueva edición…');pcgIr('/anfitrion/campeonatos/'+encodeURIComponent(j.id)+'/editar','Abriendo la nueva edición…')}catch(e){pcgToast(e.message)}});
$('btnEliminar').addEventListener('click',async function(){if(!await pcgConfirmar({titulo:'Eliminar campeonato',mensaje:'Se borra con sus participantes, fixture y resultados. No se puede deshacer.',confirmar:'Eliminar',destructivo:true}))return;try{await post('/eliminar',{},'Eliminando…');pcgIr('/anfitrion/campeonatos?eliminado=1')}catch(e){pcgToast(e.message)}});
})();
"""


# ── Acciones JSON del organizador ─────────────────────────────────────────────
@router.post(BASE + "/{cid}/foto")
async def subir_imagen(request: Request, cid: str, tipo: str = "foto") -> JSONResponse:
    """La subida a Storage y la BD son bloqueantes: van al threadpool para no
    frenar el event loop mientras Supabase responde."""
    cuerpo = await request.body()
    return await run_in_threadpool(_subir_imagen, request, cid, tipo, cuerpo)


def _subir_imagen(request: Request, cid: str, tipo: str, cuerpo: bytes) -> JSONResponse:
    ses, err = _sesion_json(request)
    if err is not None:
        return err
    if not _id_ok(cid):
        return _err("Campeonato inválido.")
    c = _mio(ses["email"], cid)
    if c is None and datos.campeonato_existe(cid):
        return _err("Este campeonato no está a tu nombre.", 404)
    if not almacen.disponible():
        return _err("La subida de imágenes no está disponible en este ambiente.", 503)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp"):
        return _err("Formato no admitido (usa JPG, PNG o WebP).", 415)
    if not cuerpo or len(cuerpo) > almacen.MAX_BYTES:
        return _err("La imagen pesa demasiado (máx. 6 MB).", 413)
    ms = int(time.time() * 1000)
    ruta = {"logo": f"campeonatos/{cid}.jpg", "ausp": f"campeonatos/{cid}_ausp_{ms}.jpg", "foto": f"campeonatos/{cid}_foto_{ms}.jpg",
            "fondo": f"campeonatos/{cid}_fondo_{ms}.jpg"}.get(tipo)
    if not ruta:
        return _err("Tipo de imagen inválido.")
    url = almacen.subir(almacen.BUCKET, ruta, cuerpo, ctype)
    if not url:
        return _err("No se pudo subir la imagen. Inténtalo de nuevo.", 502)
    if tipo == "logo":
        url = f"{url}?v={ms}"
    if c is not None:  # el logo de un campeonato NUEVO se guarda con el asistente
        if tipo == "logo":
            c["logoUrl"] = url
        elif tipo == "ausp":
            c["auspiciadoresLogos"] = list(c.get("auspiciadoresLogos") or []) + [url]
        elif tipo == "foto":
            c["fotos"] = list(c.get("fotos") or []) + [url]
        else:
            c["aficheFondoUrl"] = url
        if not _guardar(ses, c):
            return _err("No pudimos guardar en este momento.", 503)
    return JSONResponse({"ok": True, "url": url})


@router.post(BASE + "/{cid}/imagen/quitar")
def quitar_imagen(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    b = b if isinstance(b, dict) else {}
    url, tipo = str(b.get("url") or ""), str(b.get("tipo") or "")
    clave = {"ausp": "auspiciadoresLogos", "foto": "fotos"}.get(tipo)
    if not clave or url not in (c.get(clave) or []):
        return _err("Imagen no encontrada.", 404)
    c[clave] = [u for u in c[clave] if u != url]
    if not c[clave]:
        c.pop(clave, None)
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    _en_segundo_plano(almacen.borrar_foto, url)
    return _ok(c)


@router.post(BASE + "/{cid}/afiche")
def elegir_afiche(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    """`elegirArteAfiche` / `quitarFondoAfiche`."""
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    b = b if isinstance(b, dict) else {}
    viejo = c.get("aficheFondoUrl") or ""
    if b.get("quitar"):
        c.pop("aficheFondoUrl", None)
    else:
        try:
            variante = int(b.get("variante") or 0)
        except (TypeError, ValueError):
            return _err("Variante inválida.")
        c.pop("aficheFondoUrl", None)
        c["aficheVariante"] = variante
        tema = str(b.get("tema") or "").strip()[:140]
        if tema:
            c["aficheTema"] = tema
        else:
            c.pop("aficheTema", None)
        if not variante:
            c.pop("aficheVariante", None)
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    if viejo and not c.get("aficheFondoUrl"):
        _en_segundo_plano(almacen.borrar_foto, viejo)
    return _ok(c)


@router.post(BASE + "/{cid}/participante")
def agregar_participante(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    """`agregarParticipante` (organizador): id `part_<µs>`, no regenera el fixture."""
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    b = b if isinstance(b, dict) else {}
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:80]
    if not nombre:
        return _err("Escribe el nombre.")
    p = {"id": f"part_{int(time.time() * 1_000_000)}", "nombre": nombre, "contacto": re.sub(r"[^\d+ ]", "", str(b.get("contacto") or ""))[:20],
         "email": str(b.get("email") or "").strip().lower()[:120], "apoderadoNombre": ""}
    c["participantes"] = list(c.get("participantes") or []) + [p]
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    return _ok(c, id=p["id"])


@router.post(BASE + "/{cid}/participante/{pid}/eliminar")
def eliminar_participante(request: Request, cid: str, pid: str) -> JSONResponse:
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    antes = len(c.get("participantes") or [])
    c["participantes"] = [p for p in (c.get("participantes") or []) if p.get("id") != pid]
    if len(c["participantes"]) == antes:
        return _err("Participante no encontrado.", 404)
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    return _ok(c)


@router.post(BASE + "/{cid}/fixture")
def generar_fixture(request: Request, cid: str) -> JSONResponse:
    """`generarFixture`: (re)genera y BORRA los resultados. No aplica a tiempos."""
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    if L.formato_de(c) == "tiempos":
        return _err("Un torneo por tiempos no tiene fixture: agrega pruebas.")
    if len(c.get("participantes") or []) < 2:
        return _err("Agrega al menos 2 participantes.")
    c["partidos"] = L.generar_fixture(c)
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    return _ok(c, partidos=len(c["partidos"]))


@router.post(BASE + "/{cid}/resultado")
def cargar_resultado(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    b = b if isinstance(b, dict) else {}
    try:
        a, bb = int(b.get("a")), int(b.get("b"))
        if a < 0 or bb < 0:
            raise ValueError
    except (TypeError, ValueError):
        return _err("Marcador inválido.")
    m = next((x for x in (c.get("partidos") or []) if x.get("id") == str(b.get("partido") or "")), None)
    if m is None or m.get("aId") is None or m.get("bId") is None:
        return _err("Ese partido aún no tiene los dos lados definidos.")
    if L.es_partido_llave(c, m) and a == bb:
        return _err("En una llave no puede haber empate: define un ganador.")
    L.set_resultado(c, m["id"], a, bb)
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    return _ok(c)


@router.post(BASE + "/{cid}/prueba")
def agregar_prueba(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    b = b if isinstance(b, dict) else {}
    try:
        dist = int(b.get("distancia"))
    except (TypeError, ValueError):
        return _err("Distancia inválida.")
    estilo = str(b.get("estilo") or "")
    if dist not in L.DISTANCIAS or estilo not in L.ESTILOS:
        return _err("Elige distancia y estilo del catálogo.")
    p = {"id": f"pr_{int(time.time() * 1_000_000)}", "nombre": f"{dist}m {estilo}", "marcas": []}
    c["pruebas"] = list(c.get("pruebas") or []) + [p]
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    return _ok(c, id=p["id"])


@router.post(BASE + "/{cid}/prueba/{pid}/eliminar")
def eliminar_prueba(request: Request, cid: str, pid: str) -> JSONResponse:
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    antes = len(c.get("pruebas") or [])
    c["pruebas"] = [p for p in (c.get("pruebas") or []) if p.get("id") != pid]
    if len(c["pruebas"]) == antes:
        return _err("Prueba no encontrada.", 404)
    if not c["pruebas"]:
        c.pop("pruebas", None)
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    return _ok(c)


@router.post(BASE + "/{cid}/marca")
def registrar_marca(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    """Diálogo de tiempo del app: tiempo vacío borra la marca; inválido → error;
    se conserva si tiene tiempo, DSQ, serie o carril."""
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    b = b if isinstance(b, dict) else {}
    prueba = next((p for p in (c.get("pruebas") or []) if p.get("id") == str(b.get("prueba") or "")), None)
    pid = str(b.get("participante") or "")
    if prueba is None or L.participante(c, pid) is None:
        return _err("Prueba o nadador no encontrado.", 404)
    txt = str(b.get("tiempo") or "").strip()
    cent = 0
    if txt:
        parsed = L.parse_tiempo(txt)
        if parsed is None:
            return _err("Formato inválido (usa mm:ss.cc)")
        cent = parsed
    try:
        serie, carril = max(0, int(b.get("serie") or 0)), max(0, int(b.get("carril") or 0))
    except (TypeError, ValueError):
        return _err("Serie o carril inválidos.")
    dsq = bool(b.get("dsq"))
    marcas = [m for m in (prueba.get("marcas") or []) if m.get("participanteId") != pid]
    if cent > 0 or dsq or serie or carril:
        marcas.append(L.marca_json(pid, cent, serie, carril, dsq))
    prueba["marcas"] = marcas
    if not _guardar(ses, c):
        return _err("No pudimos guardar.", 503)
    return _ok(c)


@router.post(BASE + "/{cid}/ranking")
def sumar_ranking(request: Request, cid: str) -> JSONResponse:
    """`importarCampeonatoAlRanking`: solo campeonatos de una academia del mismo dueño."""
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    aid = str(c.get("academiaId") or "")
    academia = datos.academia(aid) if aid else None
    if not academia or (academia.get("dueno") or "").lower() != ses["email"].lower():
        return _ok(c, n=0)
    nueva, n = L.importar_al_ranking(c, academia)
    if n and not datos.guardar_academia(aid, ses["email"], nueva):
        return _err("No pudimos guardar el ranking.", 503)
    return _ok(c, n=n)


@router.post(BASE + "/{cid}/duplicar")
def duplicar(request: Request, cid: str) -> JSONResponse:
    """`duplicarCampeonato`: nueva edición con los mismos datos, sin participantes, fixture, pruebas, fotos ni fechas."""
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    if not _pro(ses["email"]):
        return JSONResponse({"ok": False, "error": "Crear campeonatos es parte de Pichangol Pro. Actívalo en la app."}, status_code=402)
    nuevo = {k: c[k] for k in ("academiaId", "nombre", "deporte", "formato", "categoria", "sede", "sedeLat", "sedeLng", "costoInscripcion", "moneda",
                               "relampago", "exigeDni", "edadMin", "edadMax", "logoUrl", "minJugadoresEquipo", "premios", "auspiciador",
                               "auspiciadoresLogos", "aficheFondoUrl", "aficheVariante", "aficheTema") if c.get(k) not in (None, "", [], 0, False)}
    nuevo.update({"id": L.nuevo_id(), "dueno": ses["email"], "codigo": L.nuevo_codigo(), "fechas": "", "inscripcionAbierta": True,
                  "participantes": [], "partidos": [], "cerrado": False, "academiaId": c.get("academiaId") or "", "deporte": c.get("deporte"),
                  "formato": L.formato_de(c), "categoria": c.get("categoria") or "", "sede": c.get("sede") or "", "costoInscripcion": float(c.get("costoInscripcion") or 0),
                  "moneda": c.get("moneda") or "", "relampago": bool(c.get("relampago")), "exigeDni": bool(c.get("exigeDni"))})
    if not datos.guardar_campeonato(nuevo["id"], ses["email"], nuevo):
        return _err("No pudimos crear la nueva edición.", 503)
    return JSONResponse({"ok": True, "id": nuevo["id"]})


@router.post(BASE + "/{cid}/eliminar")
def eliminar(request: Request, cid: str) -> JSONResponse:
    ses, c, err = _mio_json(request, cid)
    if err is not None:
        return err
    if not datos.eliminar_campeonato(cid, ses["email"]):
        return _err("No pudimos eliminarlo en este momento.", 503)
    if c.get("logoUrl"):
        _en_segundo_plano(almacen.borrar_foto, str(c["logoUrl"]).split("?")[0])
    print(f"[campeonato-web] {ses['email']} eliminó {cid}", flush=True)
    return _ok(c)
