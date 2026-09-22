"""MI ACADEMIA en la web (Modo anfitrión → Mi academia): la misma academia del
app (`crear_academia_screen` / `mi_academia_screen`) desde la laptop.

Lista de academias del profe, crear/editar (logo, deporte, nombre,
descripción, sede en el mapa, zona por país para el ranking, WhatsApp, fotos
del feed, redes, planes y tarifario, reglas de cobro) y la página de ALUMNOS
con sus cuotas (por cobrar / vencidas / cobrado). Misma tabla
`pichangol_academias` (`data` jsonb = `Academia.toJson`) y bucket `canchas/
academia_<id>/` que el app. Lo que la web aún no edita (sedes adicionales,
horarios y precios por sede, ranking interno) se CONSERVA tal cual al
guardar. Los cobros de cuotas siguen en el app.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import config
import paises
from web import almacen, catalogos, datos, sesion, ui
from web.anfitrion import JS_PAGAR, _en_segundo_plano, _sesion_o_entrar
from web.router import DEPORTES, PLAY_URL, e

router = APIRouter(tags=["web-anfitrion-academia"])
_GEO_DIR = Path(__file__).parent / "geo"
_LEAFLET = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
            "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>")
_EMOJI = {**{k: v[1] for k, v in DEPORTES.items()}, "natacion": "🏊"}
_NOMBRE = {**{k: v[0] for k, v in DEPORTES.items()}, "natacion": "Natación"}
# Claves de `Academia.toJson` que la web NO edita y conserva tal cual.
_CONSERVAR = ("sedes", "horarios", "preciosSede", "partidos", "categorias", "landingUrl")


def _cab(ses: dict | None, sel: str = "") -> str:
    tabs = (f"<a class='cat{' sel' if sel == 'academias' else ''}' href='/anfitrion/academia'><span class='ico'>📣</span>Mis academias</a>"
            f"<a class='cat{' sel' if sel == 'alumnos' else ''}' href='/anfitrion/academia/alumnos'><span class='ico'>🎓</span>Alumnos</a>")
    return ui.cabecera(tabs=tabs, ses=ses, volver="/anfitrion", modo="anfitrion")


def _mias(email: str) -> list[dict]:
    return datos.academias_de_dueno(email)


def _mia(email: str, aid: str) -> dict | None:
    return next((a for a in _mias(email) if a.get("id") == aid), None)


def _pais_de(a: dict) -> str:
    return paises.pais_de_coordenadas(a.get("lat"), a.get("lng"))


def _moneda(a: dict) -> str:
    return a.get("moneda") or paises.simbolo_de_moneda(paises.moneda_de_pais(_pais_de(a)))


@router.get("/web/geo/{iso}")
def geo_pais(iso: str) -> JSONResponse:
    """Árbol político-administrativo del país (mismo JSON que `assets/geo` del
    app) para el selector de zona en cascada."""
    iso = (iso or "").upper()
    f = _GEO_DIR / f"{iso.lower()}_geo.json"
    if iso not in catalogos.GEO_LABELS or not f.exists():
        return JSONResponse({"ok": False, "error": "pais_no_soportado"}, status_code=404)
    r = JSONResponse({"ok": True, "labels": catalogos.GEO_LABELS[iso], "arbol": json.loads(f.read_text(encoding="utf-8"))})
    r.headers["Cache-Control"] = "public, max-age=86400"
    return r


# ── Lista ─────────────────────────────────────────────────────────────────────

def _tarjeta(a: dict, n_alumnos: int) -> str:
    dep = str(a.get("deporte") or "tenis")
    logo = f"<img src='{e(a['logoUrl'])}' alt=''>" if a.get("logoUrl") else f"<span>{_EMOJI.get(dep, '🏟️')}</span>"
    planes = a.get("planes") or []
    sede = a.get("sedeClub") or "Sin sede"
    zona = a.get("zona") or ""
    return (f"<div class='anf-cancha'><div class='f'>{logo}</div><div style='flex:1;min-width:0'>"
            f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><b style='font-size:16px'>{e(a.get('nombre') or 'Academia')}</b>"
            f"<span class='pill'>{_EMOJI.get(dep, '')} {e(_NOMBRE.get(dep, dep.capitalize()))}</span></div>"
            f"<div class='sub' style='margin:2px 0 0'>📍 {e(sede)}{(' · ' + e(zona)) if zona else ''}</div>"
            f"<div class='sub' style='margin:6px 0 0;color:var(--noche);font-weight:600'>{n_alumnos} alumno{'s' if n_alumnos != 1 else ''} · {len(planes)} plan{'es' if len(planes) != 1 else ''}"
            f"{(' · ' + e(_moneda(a)) + ' ' + format(min(float(p.get('precioMes') or 0) for p in planes), '.2f') + '/mes desde') if planes else ''}</div>"
            "<div class='acciones' style='margin-top:10px'>"
            f"<a class='btn' href='/anfitrion/academia/{e(a['id'])}/editar'>✏️ Editar</a>"
            f"<a class='btn sec' href='/anfitrion/academia/alumnos?academia={e(a['id'])}'>🎓 Alumnos</a>"
            f"<a class='btn sec' href='/l/{e(a['id'])}' target='_blank' rel='noopener'>🌐 Landing</a>"
            "</div></div></div>")


@router.get("/anfitrion/academia", response_class=HTMLResponse)
def pagina_academias(request: Request, guardado: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/academia")
    if resp is not None:
        return resp
    acads = _mias(ses["email"])
    mats = datos.matriculas_de_academias([a["id"] for a in acads]) if acads else []
    por_ac: dict[str, int] = {}
    for m in mats:
        por_ac[str(m.get("academiaId"))] = por_ac.get(str(m.get("academiaId")), 0) + 1
    aviso = "<div class='aviso ok' style='margin-top:14px'>✅ Academia guardada. Ya se ve en la app y en tu landing.</div>" if guardado else ""
    if not acads:
        cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
                  f"{aviso}<div style='max-width:760px;margin:24px auto 0'>"
                  f"<h1 class='anf-hola'>Hola, {e((ses.get('nombre') or ses.get('email') or '').split(' ')[0])} 👋</h1>"
                  "<p class='sub' style='font-size:16px'>Con esta cuenta todavía no tienes una academia. Créala aquí y administra alumnos, cuotas y tu landing desde la app y desde la web.</p>"
                  "<div class='kpis' style='margin-top:22px'>"
                  "<div class='kpi'><small>1 · Créala</small><b style='font-size:16px'>Deporte, sede, planes y tarifario</b></div>"
                  "<div class='kpi'><small>2 · Matricula</small><b style='font-size:16px'>Tus alumnos y sus cuotas, desde la app</b></div>"
                  "<div class='kpi'><small>3 · Difunde</small><b style='font-size:16px'>Landing y redes con Pichangol</b></div></div>"
                  "<div class='acciones' style='margin-top:24px'><a class='btn' href='/anfitrion/academia/nueva'>＋ Crear mi academia</a></div></div>")
        return ui.shell("Mi academia", cuerpo, nav=_cab(ses, "academias"), sesion=ses, ancho=True, titulo_tab="Mi academia · Modo anfitrión")
    cuerpo = ("<a class='anf-back' href='/anfitrion'>‹ Modo anfitrión</a>"
              "<div style='display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap'>"
              "<div><h1 class='anf-hola' style='margin-top:6px'>Mi academia</h1>"
              f"<p class='sub'>{len(acads)} academia{'s' if len(acads) != 1 else ''} · {len(mats)} alumno{'s' if len(mats) != 1 else ''}. Edita aquí o en la app: es la misma academia.</p></div>"
              "<a class='btn sec' href='/anfitrion/academia/nueva'>＋ Otra academia</a></div>"
              f"{aviso}"
              f"<div class='anf-grid' style='grid-template-columns:repeat(auto-fill,minmax(360px,1fr));margin-top:16px'>{''.join(_tarjeta(a, por_ac.get(a['id'], 0)) for a in acads)}</div>")
    return ui.shell("Mi academia", cuerpo, nav=_cab(ses, "academias"), sesion=ses, ancho=True, titulo_tab="Mi academia · Modo anfitrión")


# ── Alumnos y cuotas ──────────────────────────────────────────────────────────

def _fecha(v) -> str:
    return str(v or "")[:10]


@router.get("/anfitrion/academia/alumnos", response_class=HTMLResponse)
def pagina_alumnos(request: Request, academia: str = "") -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/academia/alumnos")
    if resp is not None:
        return resp
    acads = _mias(ses["email"])
    if not acads:
        return HTMLResponse("", status_code=302, headers={"Location": "/anfitrion/academia"})
    a = next((x for x in acads if x["id"] == academia), acads[0])
    sim = _moneda(a)
    mats = datos.matriculas_de_academias([a["id"]])
    hoy = date.today().isoformat()
    mes = hoy[:7]
    por_cobrar = vencido = cobrado_mes = 0.0
    filas = ""
    for m in sorted(mats, key=lambda x: str(x.get("nombre") or "").lower()):
        cuotas = [c for c in (m.get("cuotas") or []) if isinstance(c, dict)]
        pend = [c for c in cuotas if not c.get("pagada")]
        venc = [c for c in pend if _fecha(c.get("vencimiento")) < hoy]
        deuda = sum(float(c.get("monto") or 0) for c in pend)
        por_cobrar += deuda
        vencido += sum(float(c.get("monto") or 0) for c in venc)
        cobrado_mes += sum(float(c.get("monto") or 0) for c in cuotas if c.get("pagada") and _fecha(c.get("fechaPago")).startswith(mes))
        estado = ("<span class='pill bad'>Vencida</span>" if venc else ("<span class='pill warn'>Por cobrar</span>" if pend else "<span class='pill ok'>Al día</span>"))
        tel = str(m.get("apoderadoWhatsapp") or m.get("whatsapp") or "")
        quien = e(m.get("nombre") or "Alumno") + (f"<div class='sub' style='margin:0;font-size:12px'>Apoderado: {e(m.get('apoderadoNombre'))}</div>" if m.get("apoderadoNombre") else "")
        prox = min((_fecha(c.get("vencimiento")) for c in pend), default="")
        filas += (f"<tr><td><b>{quien}</b></td><td>{e(str(m.get('edad') or '—'))}</td><td>{e(tel or '—')}</td>"
                  f"<td>{len(cuotas) - len(pend)}/{len(cuotas)}</td><td>{e(sim)} {deuda:.2f}{(' · vence ' + e(prox)) if prox else ''}</td><td>{estado}</td>"
                  f"<td>{('<a class=chip href=https://wa.me/' + ''.join(ch for ch in tel if ch.isdigit()) + ' target=_blank rel=noopener>💬</a>') if tel else ''}</td></tr>")
    chips = "".join(f"<a class='chip{' sel' if x['id'] == a['id'] else ''}' href='/anfitrion/academia/alumnos?academia={e(x['id'])}'>{e(x.get('nombre') or 'Academia')}</a>" for x in acads)
    cuerpo = ("<a class='anf-back' href='/anfitrion/academia'>‹ Mi academia</a>"
              "<h1 class='anf-hola' style='margin-top:6px'>Alumnos</h1><p class='sub'>Matrículas y cuotas de tu academia. Los cobros y recordatorios se registran en la app.</p>"
              f"<div class='chips' style='margin-top:12px'>{chips}</div>"
              "<div class='kpis' style='margin-top:16px'>"
              f"<div class='kpi'><small>Alumnos</small><b>{len(mats)}</b></div>"
              f"<div class='kpi'><small>Cobrado este mes</small><b>{e(sim)} {cobrado_mes:.2f}</b></div>"
              f"<div class='kpi'><small>Por cobrar</small><b>{e(sim)} {por_cobrar:.2f}</b></div>"
              f"<div class='kpi'><small>Vencido</small><b style='color:var(--bad-fg)'>{e(sim)} {vencido:.2f}</b></div></div>"
              + (f"<div class='tabla' style='margin-top:18px'><table><thead><tr><th>Alumno</th><th>Edad</th><th>WhatsApp</th><th>Cuotas pagadas</th><th>Deuda</th><th>Estado</th><th></th></tr></thead><tbody>{filas}</tbody></table></div>"
                 if mats else "<div class='anf-vacio' style='margin-top:18px'>Aún no hay alumnos matriculados en esta academia. Matricúlalos desde la app (Mi academia → Alumnos).</div>")
              + f"<p style='margin-top:18px'><a class='btn sec' href='{PLAY_URL}' rel='noopener'>Registrar cobros en la app</a></p>")
    return ui.shell("Alumnos", cuerpo, nav=_cab(ses, "alumnos"), sesion=ses, ancho=True, titulo_tab="Alumnos · Mi academia")


# ── Editor ────────────────────────────────────────────────────────────────────

@router.get("/anfitrion/academia/nueva", response_class=HTMLResponse)
def pagina_nueva_academia(request: Request) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, "/anfitrion/academia/nueva")
    if resp is not None:
        return resp
    a = {"id": f"ac_{int(time.time() * 1_000_000)}", "nombre": "", "deporte": "tenis", "dueno": ses["email"], "whatsapp": "",
         "descripcion": "", "sedeClub": "", "zona": "", "planes": [], "redes": {}, "fotos": [], "moneda": "", "recargoInvitado": 0,
         "descuentoHermano2": 0, "descuentoHermano3": 0, "descuentoPrepago": 0, "mesesMinPrepago": 3, "retribucionClubPct": 0}
    return _editor(ses, a, nueva=True)


@router.get("/anfitrion/academia/{aid}/editar", response_class=HTMLResponse)
def pagina_editar_academia(request: Request, aid: str) -> HTMLResponse:
    ses, resp = _sesion_o_entrar(request, f"/anfitrion/academia/{aid}/editar")
    if resp is not None:
        return resp
    a = _mia(ses["email"], aid)
    if a is None:
        from web.router import _no_encontrada
        r = _no_encontrada("Esta academia no está a tu nombre"); r.status_code = 404
        return r
    return _editor(ses, a, nueva=False)


def _chips(g: str, ops, sel, fmt=None, multi: bool = False) -> str:
    out = []
    for o in ops:
        k, txt = (o if isinstance(o, tuple) else (o, fmt(o) if fmt else str(o)))
        on = (str(k) in {str(x) for x in sel}) if multi else (str(k) == str(sel))
        out.append(f"<button type='button' class='chip{' sel' if on else ''}' data-g='{g}' data-v='{e(str(k))}'>{txt}</button>")
    return f"<div class='chips' data-grupo='{g}' data-multi='{1 if multi else 0}'>{''.join(out)}</div>"


def _editor(ses: dict, a: dict, *, nueva: bool) -> HTMLResponse:
    iso = _pais_de(a) if a.get("lat") is not None else "PE"
    dep = str(a.get("deporte") or "tenis")
    logo = f"<img src='{e(a['logoUrl'])}' alt=''>" if a.get("logoUrl") else f"<span>{_EMOJI.get(dep, '🏟️')}</span>"
    fotos = [str(u) for u in (a.get("fotos") or []) if str(u).startswith("http")]
    fotos_html = "".join(f"<div class='foto' data-url='{e(u)}'><img src='{e(u)}' alt=''><div class='acc'><button type='button' class='mini' data-acc='quitar' title='Quitar'>✕</button></div></div>" for u in fotos)
    redes = {k: str(v) for k, v in (a.get("redes") or {}).items() if v}
    redes_html = "".join(
        f"<div class='serv{' sel' if k in redes else ''}' data-red='{k}'><button type='button' class='chip{' sel' if k in redes else ''}' data-g='redes' data-v='{k}'>{e(n)}</button>"
        f"<label class='precio-serv'{'' if k in redes else ' hidden'}><input type='text' name='red_{k}' maxlength='120' value='{e(redes.get(k, ''))}' placeholder='{'https://…' if k == 'web' else '@usuario o enlace'}' style='width:260px'></label></div>"
        for k, n in catalogos.REDES.items())
    cfg = {"id": a["id"], "nueva": nueva, "lat": a.get("lat"), "lng": a.get("lng"), "iso": iso, "zona": a.get("zona") or "", "buscar": bool(config.PLACES_API_KEY), "recargo": float(a.get("recargoInvitado") or 0),
           "planes": [p for p in (a.get("planes") or []) if isinstance(p, dict)], "fotos": fotos, "logo": a.get("logoUrl") or "",
           "moneda": _moneda(a), "storage": almacen.disponible(), "tipos": catalogos.TIPOS_PLAN, "meses": catalogos.MESES_PREPAGO,
           "frec": catalogos.FRECUENCIAS, "durs": catalogos.DURACIONES_CLASE, "tel": catalogos.TEL_PREFIJO, "telLen": catalogos.TEL_LONGITUD,
           "monedas": {k: paises.simbolo_de_moneda(v) for k, v in paises.MONEDA_POR_PAIS.items()}, "labels": catalogos.GEO_LABELS}
    secciones = [("identidad", "Identidad"), ("sede", "Sede y contacto"), ("fotos", "Fotos"), ("redes", "Redes"), ("planes", "Programas y tarifario"), ("reglas", "Reglas de cobro")]
    nav = "".join(f"<a href='#sec-{k}' class='edit-nav-it'>{n}</a>" for k, n in secciones)
    dep_ops = [(d, f"{_EMOJI.get(d, '')} {_NOMBRE.get(d, d.capitalize())}") for d in catalogos.DEPORTES_ACADEMIA]
    pct = lambda v: "Sin descuento" if v == 0 else f"{v} %"  # noqa: E731
    cuerpo = f"""
<div class='edit-top'><a class='volver-lnk' href='/anfitrion/academia'>‹ Mi academia</a>
<h1 class='anf-hola' style='margin-top:8px'>{'Crear academia' if nueva else 'Editar academia'}</h1><p class='sub'>{'Tu marca independiente: puede rotar de sede sin perder alumnos ni historia.' if nueva else e(a.get('nombre') or '')}</p></div>
<div class='edit-grid'><nav class='edit-nav'>{nav}</nav>
<form id='fAc' class='edit-form' autocomplete='off' novalidate>
 <section class='panel edit-sec' id='sec-identidad'><h2>Identidad</h2>
  <div style='display:flex;gap:18px;align-items:center;margin-top:14px;flex-wrap:wrap'><div class='logo-pick' id='logoBox'>{logo}</div>
   <div><label class='btn sec' for='inLogo' style='margin:0'>🖼️ {'Subir logo' if not a.get('logoUrl') else 'Cambiar logo'}</label><input type='file' id='inLogo' accept='image/*' hidden{'' if almacen.disponible() else ' disabled'}>
   <div class='sub' id='logoMsg' style='margin:6px 0 0;font-size:12.5px'>{'Opcional. Se ve en la app, el chat y tu landing.' if almacen.disponible() else 'La subida de imágenes no está disponible en este ambiente; súbelas desde la app.'}</div></div></div>
  <label>Deporte</label>{_chips('deporte', dep_ops, dep)}
  <label for='nombre'>Nombre de la academia</label><input id='nombre' maxlength='80' value='{e(a.get('nombre') or '')}' placeholder='Ej. Academia de Tenis Baseline'>
  <label for='desc'>Descripción <span class='req'>opcional</span></label><textarea id='desc' rows='3' maxlength='600' placeholder='Niveles, horarios, para quién es…'>{e(a.get('descripcion') or '')}</textarea>
 </section>
 <section class='panel edit-sec' id='sec-sede'><h2>Sede y contacto</h2><p class='sub'>Dónde entrenas ahora. Del punto en el mapa salen el país, la moneda y la zona del ranking.</p>
  <label for='sede'>Club / local donde entrenas{" <span class='req'>🔎 escribe y elige tu club de Google Maps: el pin se pone solo</span>" if config.PLACES_API_KEY else ''}</label><input id='sede' maxlength='80' value='{e(a.get('sedeClub') or '')}' placeholder='Ej. ESMON, Club Lawn Tennis de la Exposición' autocomplete='off'><div id='resSede' class='res-busca' hidden></div>
  <label>Ubicación de la sede</label><div id='mapaSede' class='mapa-sede' style='margin-top:6px'></div>
  <div class='acciones' style='margin-top:8px'><button type='button' class='btn sec' id='btnUbic'>📍 Usar mi ubicación</button><span class='sub' id='ubicTxt' style='margin:0'>{'Toca el mapa para fijar la sede.' if a.get('lat') is None else f"{float(a['lat']):.5f}, {float(a['lng']):.5f}"}</span></div>
  <label>Zona <span class='req'>para el ranking por ciudad</span></label>
  <div class='row' id='geoRow' style='grid-template-columns:1fr 1fr 1fr'><select id='g1'><option value=''>—</option></select><select id='g2'><option value=''>—</option></select><select id='g3'><option value=''>—</option></select></div>
  <label for='wa'>WhatsApp de contacto</label><div class='inp-moneda' style='max-width:300px'><span id='telPre'>+{catalogos.TEL_PREFIJO.get(iso, '51')}</span><input id='wa' inputmode='tel' maxlength='15' value='{e(a.get('whatsapp') or '')}' placeholder='999 888 777'></div>
 </section>
 <section class='panel edit-sec' id='sec-fotos'><h2>Fotos</h2><p class='sub'>Feed de tu academia dentro de Pichangol (hasta 8).</p>
  <div class='edit-fotos' id='fotos'>{fotos_html}</div>
  <div class='acciones' style='margin-top:12px'><label class='btn sec' for='inFotos'>📷 Agregar fotos</label><input type='file' id='inFotos' accept='image/*' multiple hidden{'' if almacen.disponible() else ' disabled'}><span class='sub' id='fotosMsg' style='margin:0'></span></div>
 </section>
 <section class='panel edit-sec' id='sec-redes'><h2>Redes sociales</h2><p class='sub'>Elige las que usas y pon tu usuario o enlace.</p><div class='servs'>{redes_html}</div></section>
 <section class='panel edit-sec' id='sec-planes'><h2>Programas y tarifario</h2><p class='sub'>Igual que en la app: un <b>programa</b> agrupa a los alumnos de un mismo nivel o etapa (Bola Roja y Naranja, Avanzados…) y dentro va el <b>precio socio por frecuencia</b> (2x, 3x, 4x o 5x por semana). Cada frecuencia con precio es un plan que el alumno elige al matricularse; el invitado se calcula con el recargo de la academia.</p>
  <div id='programas' class='planes'></div>
  <div class='acciones' style='margin-top:12px'><button type='button' class='btn sec' id='btnPrograma'>＋ Agregar programa</button></div>
  <div id='sueltos' class='sueltos' hidden></div>
 </section>
 <section class='panel edit-sec' id='sec-reglas'><h2>Reglas de cobro</h2>
  <label for='recargo'>Recargo para invitados (no socios de la sede) <span class='req'>0 = un solo precio</span></label><div class='inp-moneda' style='max-width:220px'><span id='monSpan'>{e(_moneda(a))}</span><input id='recargo' type='number' min='0' step='1' value='{float(a.get('recargoInvitado') or 0):.0f}'></div>
  <label>Descuento 2.º hermano</label>{_chips('descuentoHermano2', catalogos.DESCUENTOS_ACADEMIA, int(float(a.get('descuentoHermano2') or 0)), pct)}
  <label>Descuento 3.º hermano en adelante</label>{_chips('descuentoHermano3', catalogos.DESCUENTOS_ACADEMIA, int(float(a.get('descuentoHermano3') or 0)), pct)}
  <label>Descuento por prepago</label>{_chips('descuentoPrepago', catalogos.DESCUENTOS_ACADEMIA, int(float(a.get('descuentoPrepago') or 0)), pct)}
  <label>Desde cuántos meses adelantados aplica</label>{_chips('mesesMinPrepago', catalogos.MESES_MIN_PREPAGO, int(a.get('mesesMinPrepago') or 3), lambda v: f"{v} mes{'es' if v != 1 else ''}")}
  <label for='retri'>Retribución al club / sede <span class='req'>% de lo cobrado · 0 = no aplica</span></label><div class='inp-moneda' style='max-width:160px'><input id='retri' type='number' min='0' max='50' step='1' value='{float(a.get('retribucionClubPct') or 0):.0f}'><span>%</span></div>
  <p class='sub' style='font-size:12.5px;margin-top:14px'>Sedes adicionales, horarios y precios por sede y el ranking interno se configuran en la app y se conservan al guardar aquí.</p>
 </section>
</form></div>
<div class='barra-guardar'><div class='wrap-xl'><span class='sub' id='msgGuardar' style='margin:0'>Los cambios se ven al instante en la app y en tu landing.</span>
{'' if nueva else "<button type='button' class='btn sec' id='btnEliminar' style='color:var(--rojo);margin-right:8px'>🗑 Eliminar</button>"}<button type='button' class='btn' id='btnGuardar'>{'Crear academia' if nueva else 'Guardar cambios'}</button></div></div>
<script>var CFG={json.dumps(cfg, ensure_ascii=False)};</script><script>{JS_PAGAR}</script><script>{_JS_EDITOR}</script>"""
    return ui.shell("Academia", cuerpo, nav=_cab(ses, "academias"), sesion=ses, ancho=True, extra_head=_LEAFLET,
                    titulo_tab=f"{'Crear' if nueva else 'Editar'} academia · Modo anfitrión")


_JS_EDITOR = r"""
(function(){
var fotos=CFG.fotos.slice(), logo=CFG.logo, planes=CFG.planes.slice(), lat=CFG.lat, lng=CFG.lng, iso=CFG.iso, arbol=null, subiendo=0, mapa, marker;
function $(id){return document.getElementById(id)}
function sel(g){var b=document.querySelector(".chip.sel[data-g='"+g+"']");return b?b.dataset.v:''}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}
// ── deporte / descuentos (chips simples) + redes ──
document.addEventListener('click',function(ev){var b=ev.target.closest('.chip[data-g]');if(!b)return;var g=b.dataset.g;
  if(g==='redes'){var row=b.closest('.serv');row.classList.toggle('sel');b.classList.toggle('sel');row.querySelector('.precio-serv').hidden=!row.classList.contains('sel');return}
  if(g.indexOf('plan_')===0)return;
  b.closest('.chips').querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel')});
// ── mapa de la sede ──
function paisDe(la,ln){var C={PE:[-18.4,-0.03,-81.4,-68.6],EC:[-5.1,1.7,-81.1,-75.1],BO:[-22.95,-9.6,-69.7,-57.4]};for(var k in C){var c=C[k];if(la>=c[0]&&la<=c[1]&&ln>=c[2]&&ln<=c[3])return k}return 'PE'}
function ponerPunto(la,ln,centrar){lat=la;lng=ln;$('ubicTxt').textContent=la.toFixed(5)+', '+ln.toFixed(5);if(mapa){if(marker)marker.setLatLng([la,ln]);else marker=L.marker([la,ln]).addTo(mapa);if(centrar)mapa.setView([la,ln],15)}
  var p=paisDe(la,ln);if(p!==iso){iso=p;$('telPre').textContent='+'+CFG.tel[iso];if(CFG.nueva)$('monSpan').textContent=CFG.monedas[iso]||'S/';cargarGeo()}}
if(window.L){var c0=lat!=null?[lat,lng]:{PE:[-12.05,-77.04],EC:[-2.17,-79.92],BO:[-16.5,-68.15]}[iso];mapa=L.map('mapaSede').setView(c0,lat!=null?15:11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(mapa);
  if(lat!=null)marker=L.marker([lat,lng]).addTo(mapa);mapa.on('click',function(ev){ponerPunto(ev.latlng.lat,ev.latlng.lng,false)});
  $('btnUbic').addEventListener('click',function(){if(!navigator.geolocation){pcgToast('Tu navegador no permite ubicación.');return}navigator.geolocation.getCurrentPosition(function(p){ponerPunto(p.coords.latitude,p.coords.longitude,true)},function(){pcgToast('No pudimos leer tu ubicación.')})})}
// ── buscador de la sede (Google Maps vía /web/lugares, el mismo de "Pon tu cancha") ──
// El campo "Club / local" AUTOCOMPLETA: al elegir un resultado se pone el nombre y el pin.
var tSede=null, inSede=$('sede'), resSede=$('resSede');
if(CFG.buscar&&inSede&&resSede){
  inSede.addEventListener('input',function(){clearTimeout(tSede);var q=this.value.trim();if(q.length<3){resSede.hidden=true;resSede.innerHTML='';return}
    tSede=setTimeout(function(){var c=mapa?mapa.getCenter():null;var qs='/web/lugares?q='+encodeURIComponent(q)+(c?'&lat='+c.lat+'&lng='+c.lng:'');
      fetch(qs).then(function(r){return r.json()}).then(function(j){if(inSede.value.trim()!==q)return;var l=j.lugares||[];resSede.hidden=false;
        resSede.innerHTML=l.length?l.map(function(x){return "<button type='button' class='res-it' data-nombre='"+esc(x.nombre)+"' data-lat='"+x.lat+"' data-lng='"+x.lng+"'><b>"+esc(x.nombre)+"</b><small>"+esc(x.direccion)+(x.km!=null?' · a '+x.km+' km':'')+"</small></button>"}).join('')
          :"<div class='sub' style='padding:8px 12px'>No encontramos ese local en Google. Deja el nombre escrito y marca el punto en el mapa.</div>"}).catch(function(){resSede.hidden=true})},400)});
  resSede.addEventListener('click',function(ev){var b=ev.target.closest('.res-it');if(!b)return;inSede.value=b.dataset.nombre;resSede.hidden=true;resSede.innerHTML='';
    ponerPunto(parseFloat(b.dataset.lat),parseFloat(b.dataset.lng),true)});
  document.addEventListener('click',function(ev){if(!ev.target.closest('#resSede')&&ev.target!==inSede)resSede.hidden=true});
  inSede.addEventListener('keydown',function(ev){if(ev.key==='Escape')resSede.hidden=true});
}
// ── zona en cascada (mismo árbol que el app) ──
function opts(sel,lista,val,ph){sel.innerHTML="<option value=''>"+ph+"</option>"+lista.map(function(o){return "<option value='"+esc(o)+"'"+(o===val?' selected':'')+">"+esc(o)+"</option>"}).join('')}
function cargarGeo(){fetch('/web/geo/'+iso).then(function(r){return r.json()}).then(function(j){if(!j.ok)return;arbol=j.arbol;var lb=j.labels,n1=Object.keys(arbol),pre=['','',''];
  if(CFG.zona){for(var a in arbol){for(var b in arbol[a]){if(arbol[a][b].indexOf(CFG.zona)>=0){pre=[a,b,CFG.zona]}}}}
  opts($('g1'),n1,pre[0],lb[0]);opts($('g2'),pre[0]?Object.keys(arbol[pre[0]]):[],pre[1],lb[1]);opts($('g3'),pre[1]?arbol[pre[0]][pre[1]]:[],pre[2],lb[2])}).catch(function(){})}
$('g1').addEventListener('change',function(){opts($('g2'),this.value?Object.keys(arbol[this.value]):[],'',CFG.labels[iso][1]);opts($('g3'),[],'',CFG.labels[iso][2])});
$('g2').addEventListener('change',function(){opts($('g3'),this.value?arbol[$('g1').value][this.value]:[],'',CFG.labels[iso][2])});
cargarGeo();
// ── fotos + logo ──
function comprimir(file,M){return new Promise(function(res,rej){var img=new Image(),url=URL.createObjectURL(file);img.onload=function(){var w=img.width,h=img.height,k=Math.min(1,M/Math.max(w,h));var cv=document.createElement('canvas');cv.width=Math.round(w*k);cv.height=Math.round(h*k);cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(url);cv.toBlob(function(b){b?res(b):rej(new Error('img'))},'image/jpeg',0.85)};img.onerror=function(){URL.revokeObjectURL(url);rej(new Error('img'))};img.src=url})}
async function subir(file,tipo,M){var blob=await comprimir(file,M);var r=await fetch('/anfitrion/academia/'+encodeURIComponent(CFG.id)+'/foto?tipo='+tipo,{method:'POST',body:blob,headers:{'Content-Type':'image/jpeg'}});return r.json()}
function pintarFotos(){$('fotos').innerHTML=fotos.map(function(u){return "<div class='foto' data-url='"+esc(u)+"'><img src='"+esc(u)+"' alt=''><div class='acc'><button type='button' class='mini' data-acc='quitar' title='Quitar'>✕</button></div></div>"}).join('')}
document.addEventListener('click',function(ev){var a=ev.target.closest('.foto .mini');if(!a)return;var u=a.closest('.foto').dataset.url,i=fotos.indexOf(u);if(i>=0)fotos.splice(i,1);pintarFotos()});
$('inLogo').addEventListener('change',async function(){var f=this.files&&this.files[0];this.value='';if(!f)return;subiendo++;$('logoMsg').textContent='Subiendo logo…';try{var j=await subir(f,'logo',600);if(j.ok){logo=j.url;$('logoBox').innerHTML="<img src='"+esc(logo)+"' alt=''>";$('logoMsg').textContent='Listo.'}else $('logoMsg').textContent=j.error||'No se pudo subir.'}catch(e){$('logoMsg').textContent='No se pudo subir el logo.'}subiendo--});
$('inFotos').addEventListener('change',async function(){var files=Array.prototype.slice.call(this.files||[]);this.value='';var msg=$('fotosMsg');
  for(var i=0;i<files.length;i++){if(fotos.length>=8){msg.textContent='Máximo 8 fotos.';break}subiendo++;msg.textContent='Subiendo foto '+(i+1)+' de '+files.length+'…';
    try{var j=await subir(files[i],'foto',1600);if(j.ok){fotos.push(j.url);pintarFotos();msg.textContent=''}else msg.textContent=j.error||'No se pudo subir.'}catch(e){msg.textContent='No se pudo subir la foto.'}subiendo--}});
// ── planes ──
function chips(g,ops,val,fmt){return "<div class='chips' style='margin-top:6px'>"+ops.map(function(o){var k=typeof o==='object'?o[0]:o,t=typeof o==='object'?o[1]:(fmt?fmt(o):o);return "<button type='button' class='chip"+(String(k)===String(val)?' sel':'')+"' data-g='"+g+"' data-v='"+esc(k)+"'>"+esc(t)+"</button>"}).join('')+"</div>"}
// PROGRAMAS DEL TARIFARIO = el MISMO editor del app (`_EditorPrograma`): un
// programa (Bola Roja y Naranja, Avanzados…) con etapa/edad, duración de clase,
// días y horario, y el PRECIO SOCIO por frecuencia (2x…5x por semana; vacío = no
// se ofrece). Cada frecuencia con precio se guarda como un plan mensual con el
// mismo id/nombre que genera el app (`prog | 2x`, `prog · 2x/sem`). Los planes
// que no encajan (sin programa, sin frecuencia 2-5 o no mensuales, creados con
// el editor web anterior) se listan aparte como "planes sueltos" para verlos y
// poder quitarlos; se conservan tal cual si no se tocan.
var FRECS=[2,3,4,5];
function agrupar(pl){var out=[],idx={},sueltos=[];pl.forEach(function(p){var prog=(p.programa||'').trim(),f=+p.frecuenciaSemana||0;
  if(!prog||FRECS.indexOf(f)<0||(p.tipo||'mensual')!=='mensual'){sueltos.push(p);return}
  if(!(prog in idx)){idx[prog]=out.length;out.push({nombre:prog,etapaEdad:p.etapaEdad||'',duracionClase:p.duracionClase||'',horario:p.horario||'',precios:{}})}
  var g=out[idx[prog]];if(!g.etapaEdad)g.etapaEdad=p.etapaEdad||'';if(!g.duracionClase)g.duracionClase=p.duracionClase||'';if(!g.horario)g.horario=p.horario||'';g.precios[f]=+p.precioMes||0});return {programas:out,sueltos:sueltos}}
var agr=agrupar(planes), programas=agr.programas, sueltos=agr.sueltos;
function pintarProgramas(){
  $('programas').innerHTML=programas.length?programas.map(function(g,i){return "<div class='prog-card' data-i='"+i+"'>"+
    "<div class='prog-head'><b class='prog-tit'>"+(g.nombre?esc(g.nombre):'Programa '+(i+1))+"</b><button type='button' class='mini' data-quitar-prog='"+i+"' title='Quitar programa'>✕</button></div>"+
    "<label>Programa</label><input data-k='nombre' maxlength='60' value='"+esc(g.nombre)+"' placeholder='Ej. Bola Roja y Naranja'>"+
    "<label>Etapa / edad</label><input data-k='etapaEdad' maxlength='80' value='"+esc(g.etapaEdad)+"' placeholder='Ej. Iniciación e intermedio · 5 a 10 años'>"+
    "<label>Duración de clase</label>"+chips('prog_dur_'+i,[''].concat(CFG.durs),g.duracionClase||'',function(v){return v||'—'})+
    "<label>Días y horario <span class='req'>opcional · cuándo son las clases de este programa</span></label><input data-k='horario' maxlength='80' value='"+esc(g.horario)+"' placeholder='Ej. Lun, Mié y Vie · 5:00–6:30 pm'>"+
    "<label style='margin-top:14px'>Precio socio por frecuencia <span class='req'>veces por semana · deja en blanco las que no ofreces</span></label>"+
    "<div class='frecs'>"+FRECS.map(function(f){return "<div class='frec'><b>"+f+"x/sem</b><div class='inp-moneda'><span>"+esc(CFG.moneda)+"</span><input data-f='"+f+"' type='number' min='0' step='1' inputmode='numeric' placeholder='socio / mes' value='"+(g.precios[f]>0?esc(g.precios[f]):'')+"'></div></div>"}).join('')+"</div>"+
    (CFG.recargo>0?"<p class='sub' style='margin:8px 0 0;font-size:12.5px'>El precio de invitado se calcula sumando el recargo de la academia ("+esc(CFG.moneda)+" "+esc(CFG.recargo)+").</p>":"")+"</div>"}).join('')
  :"<div class='anf-vacio'>Aún no agregas programas. Ejemplo: «Bola Roja y Naranja» con precio para 2x y 3x por semana.</div>";
  var sb=$('sueltos');if(sb){sb.hidden=!sueltos.length;sb.innerHTML=sueltos.length?"<label>Planes sueltos <span class='req'>creados con el editor anterior; vuelve a armarlos como programa y quítalos</span></label>"+sueltos.map(function(p,i){return "<div class='suelto'><span><b>"+esc(p.nombre||'Plan')+"</b> · "+esc(CFG.moneda)+" "+esc(p.precioMes||0)+(p.programa?" · "+esc(p.programa):"")+"</span><button type='button' class='mini' data-quitar-suelto='"+i+"' title='Quitar'>✕</button></div>"}).join(''):''}}
function leerProgramas(){document.querySelectorAll('.prog-card').forEach(function(c){var i=+c.dataset.i,g=programas[i];
  c.querySelectorAll('input[data-k]').forEach(function(inp){g[inp.dataset.k]=inp.value.trim()});
  var d=c.querySelector(".chip.sel[data-g='prog_dur_"+i+"']");g.duracionClase=d?d.dataset.v:'';
  g.precios={};c.querySelectorAll('input[data-f]').forEach(function(inp){var v=parseFloat(inp.value);if(v>0)g.precios[+inp.dataset.f]=v})})}
function aplanar(){var out=[];programas.forEach(function(g){FRECS.forEach(function(f){var v=g.precios[f];if(!(v>0))return;
  out.push({id:g.nombre+' | '+f+'x',nombre:g.nombre+' · '+f+'x/sem',tipo:'mensual',precioMes:v,meses:1,programa:g.nombre,frecuenciaSemana:f,etapaEdad:g.etapaEdad,duracionClase:g.duracionClase,horario:g.horario})})});return out.concat(sueltos)}
$('programas').addEventListener('input',function(ev){var inp=ev.target;if(inp.dataset.k!=='nombre')return;var c=inp.closest('.prog-card');c.querySelector('.prog-tit').textContent=inp.value.trim()||('Programa '+(+c.dataset.i+1))});
$('programas').addEventListener('click',function(ev){
  var q=ev.target.closest('[data-quitar-prog]');if(q){leerProgramas();var g=programas[+q.dataset.quitarProg];if(Object.keys(g.precios).length&&!confirm('¿Quitar el programa «'+(g.nombre||'')+'» y sus tarifas?'))return;programas.splice(+q.dataset.quitarProg,1);pintarProgramas();return}
  var b=ev.target.closest('.chip[data-g]');if(!b)return;var wrap=b.closest('.chips');wrap.querySelectorAll('.chip').forEach(function(x){x.classList.remove('sel')});b.classList.add('sel')});
var sbox=$('sueltos');if(sbox)sbox.addEventListener('click',function(ev){var q=ev.target.closest('[data-quitar-suelto]');if(!q)return;leerProgramas();sueltos.splice(+q.dataset.quitarSuelto,1);pintarProgramas()});
$('btnPrograma').addEventListener('click',function(){leerProgramas();programas.push({nombre:'',etapaEdad:'',duracionClase:'',horario:'',precios:{}});pintarProgramas();var last=$('programas').lastElementChild;if(last)last.querySelector('input').focus()});
function validarProgramas(){for(var i=0;i<programas.length;i++){var g=programas[i];if(!g.nombre)return 'Ponle nombre al programa '+(i+1)+'.';if(!Object.keys(g.precios).length)return 'Pon al menos un precio por frecuencia en «'+g.nombre+'».'}return ''}
pintarProgramas();
// ── guardar / eliminar ──
$('btnGuardar').addEventListener('click',async function(){var btn=this,msg=$('msgGuardar');if(subiendo>0){msg.textContent='Espera a que terminen de subir las imágenes.';return}leerProgramas();var errP=validarProgramas();if(errP){msg.textContent=errP;var sp=$('sec-planes');if(sp)sp.scrollIntoView({behavior:'smooth',block:'start'});return}planes=aplanar();
  var redes={};document.querySelectorAll('.serv.sel[data-red]').forEach(function(r){var v=r.querySelector('input').value.trim();if(v)redes[r.dataset.red]=v});
  var body={id:CFG.id,nombre:$('nombre').value,deporte:sel('deporte'),descripcion:$('desc').value,sedeClub:$('sede').value,lat:lat,lng:lng,zona:$('g3').value,whatsapp:$('wa').value,
    logoUrl:logo,fotos:fotos,redes:redes,planes:planes,recargoInvitado:parseFloat($('recargo').value)||0,descuentoHermano2:+sel('descuentoHermano2'),descuentoHermano3:+sel('descuentoHermano3'),
    descuentoPrepago:+sel('descuentoPrepago'),mesesMinPrepago:+sel('mesesMinPrepago'),retribucionClubPct:parseFloat($('retri').value)||0};
  btn.disabled=true;msg.classList.remove('err');msg.textContent='Guardando…';
  try{var r=await fetch('/anfitrion/academia/guardar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});var j=await r.json();
    if(j.ok){location.href='/anfitrion/academia?guardado=1';return}msg.classList.add('err');msg.textContent=j.error||'No se pudo guardar.';if(j.campo){var el=document.getElementById('sec-'+j.campo);if(el)el.scrollIntoView({behavior:'smooth'})}}
  catch(e){msg.classList.add('err');msg.textContent='No se pudo guardar. Revisa tu conexión.'}btn.disabled=false});
var del=$('btnEliminar');if(del)del.addEventListener('click',async function(){if(!confirm('¿Eliminar esta academia? Deja de verse en la app y en tu landing (los alumnos y cuotas quedan guardados).'))return;this.disabled=true;
  try{var j=await (await fetch('/anfitrion/academia/'+encodeURIComponent(CFG.id)+'/eliminar',{method:'POST'})).json();if(j.ok){location.href='/anfitrion/academia';return}pcgToast(j.error||'No se pudo eliminar.')}catch(e){pcgToast('No se pudo eliminar.')}this.disabled=false});
})();
"""


def _id_ok(aid: str) -> bool:
    return bool(re.match(r"^ac_[0-9]{6,}(_w)?$", aid or ""))


def _validar(b: dict, actual: dict | None, email: str) -> tuple[dict | None, str, str]:
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:80]
    if not nombre:
        return None, "Ponle un nombre a tu academia.", "identidad"
    dep = str(b.get("deporte") or "")
    if dep not in catalogos.DEPORTES_ACADEMIA:
        return None, "Elige el deporte.", "identidad"
    sede = re.sub(r"\s+", " ", str(b.get("sedeClub") or "")).strip()[:80]
    if not sede:
        return None, "Indica dónde entrenas (sede actual).", "sede"
    lat = lng = None
    try:
        if b.get("lat") is not None and b.get("lng") is not None:
            lat, lng = float(b["lat"]), float(b["lng"])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
    except (TypeError, ValueError):
        return None, "Ubicación inválida.", "sede"
    iso = paises.pais_de_coordenadas(lat, lng)
    tel = re.sub(r"\D", "", str(b.get("whatsapp") or ""))
    if len(tel) < catalogos.TEL_LONGITUD.get(iso, 9):
        return None, f"Pon un WhatsApp válido ({catalogos.TEL_LONGITUD.get(iso, 9)} dígitos).", "sede"
    planes = []
    for i, p in enumerate(b.get("planes") or []):
        if not isinstance(p, dict):
            continue
        pn = re.sub(r"\s+", " ", str(p.get("nombre") or "")).strip()[:60]
        prog = re.sub(r"\s+", " ", str(p.get("programa") or "")).strip()[:60]
        tipo = str(p.get("tipo") or "mensual")
        try:
            precio = round(float(p.get("precioMes") or 0), 2)
        except (TypeError, ValueError):
            precio = 0
        try:
            frec = int(p.get("frecuenciaSemana") or 0)
        except (TypeError, ValueError):
            frec = 0
        if not pn and prog:  # tarifa de un programa: el nombre del plan se deriva
            pn = (prog + (f" · {frec}x/sem" if frec else "") + (" · por clase" if tipo == "porClase" else ""))[:60]
        if not pn or precio <= 0:
            return None, (f"La tarifa {i + 1} de «{prog}» necesita un precio." if prog else f"El plan {i + 1} necesita nombre y precio válido."), "planes"
        if tipo not in catalogos.TIPOS_PLAN:
            tipo = "mensual"
        try:
            meses = int(p.get("meses") or 1)
        except (TypeError, ValueError):
            meses = 1
        meses = 0 if tipo == "porClase" else (meses if tipo == "prepago" and meses in catalogos.MESES_PREPAGO else 1)
        planes.append({"id": str(p.get("id") or f"pl_{int(time.time() * 1000)}_{i}")[:40], "nombre": pn, "tipo": tipo, "precioMes": precio, "meses": meses,
                       "programa": prog, "frecuenciaSemana": frec if frec in catalogos.FRECUENCIAS else 0,
                       "etapaEdad": str(p.get("etapaEdad") or "").strip()[:80],
                       "duracionClase": str(p.get("duracionClase") or "") if str(p.get("duracionClase") or "") in catalogos.DURACIONES_CLASE else "",
                       "horario": str(p.get("horario") or "").strip()[:80]})
    redes = {}
    for k, v in (b.get("redes") or {}).items() if isinstance(b.get("redes"), dict) else []:
        if k in catalogos.REDES and str(v).strip():
            redes[k] = str(v).strip()[:120]
    # Imágenes: solo las que ya tenía o las subidas a SU carpeta.
    carpeta = almacen.prefijo_carpeta(f"academia_{b.get('id')}") if almacen.disponible() else None
    viejas = set([str(u) for u in ((actual or {}).get("fotos") or [])] + ([str((actual or {}).get("logoUrl"))] if (actual or {}).get("logoUrl") else []))
    ok_img = lambda u: bool(u) and (u in viejas or (carpeta and u.startswith(carpeta)))  # noqa: E731
    fotos = [str(u).strip() for u in (b.get("fotos") or []) if ok_img(str(u).strip())][:8]
    logo = str(b.get("logoUrl") or "").strip()
    logo = logo if ok_img(logo) else ""

    def _pct(k, ops):
        try:
            v = int(float(b.get(k) or 0))
        except (TypeError, ValueError):
            v = 0
        return v if v in ops else 0

    try:
        recargo = max(0.0, min(round(float(b.get("recargoInvitado") or 0), 2), 10000))
        retri = max(0.0, min(round(float(b.get("retribucionClubPct") or 0), 2), 50))
    except (TypeError, ValueError):
        return None, "Reglas de cobro inválidas.", "reglas"
    mmin = _pct("mesesMinPrepago", catalogos.MESES_MIN_PREPAGO) or 3
    data = dict(actual or {})
    data.update({
        "id": b.get("id"), "nombre": nombre, "deporte": dep, "dueno": email, "whatsapp": tel, "descripcion": str(b.get("descripcion") or "").strip()[:600],
        "sedeClub": sede, "zona": str(b.get("zona") or "").strip()[:60], "planes": planes, "redes": redes, "fotos": fotos,
        "moneda": (actual or {}).get("moneda") or paises.simbolo_de_moneda(paises.moneda_de_pais(iso)),
        "recargoInvitado": recargo, "descuentoHermano2": _pct("descuentoHermano2", catalogos.DESCUENTOS_ACADEMIA),
        "descuentoHermano3": _pct("descuentoHermano3", catalogos.DESCUENTOS_ACADEMIA), "descuentoPrepago": _pct("descuentoPrepago", catalogos.DESCUENTOS_ACADEMIA),
        "mesesMinPrepago": mmin, "retribucionClubPct": retri,
    })
    if logo:
        data["logoUrl"] = logo
    else:
        data.pop("logoUrl", None)
    if lat is not None:
        data["lat"], data["lng"] = lat, lng
    else:
        data.pop("lat", None); data.pop("lng", None)
    for k in _CONSERVAR:
        data.setdefault(k, {} if k in ("horarios", "preciosSede", "categorias") else ([] if k in ("sedes", "partidos") else ""))
    return data, "", ""


@router.post("/anfitrion/academia/guardar")
async def guardar_academia(request: Request) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    if not isinstance(b, dict) or not _id_ok(str(b.get("id") or "")):
        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=400)
    aid = str(b["id"])
    actual = _mia(ses["email"], aid)
    data, err, campo = _validar(b, actual, ses["email"])
    if data is None:
        return JSONResponse({"ok": False, "error": err, "campo": campo}, status_code=400)
    quitadas = [u for u in ((actual or {}).get("fotos") or []) if u not in data["fotos"]]
    if actual and actual.get("logoUrl") and actual.get("logoUrl") != data.get("logoUrl"):
        quitadas.append(actual["logoUrl"])
    if not datos.guardar_academia(aid, ses["email"], data):
        return JSONResponse({"ok": False, "error": "No pudimos guardar en este momento. Inténtalo de nuevo."}, status_code=503)
    if quitadas:
        _en_segundo_plano(lambda: [almacen.borrar_foto(u) for u in quitadas])
    print(f"[academia-web] {ses['email']} guardó {aid}: {data['nombre']} · {data['deporte']} · {len(data['planes'])} planes", flush=True)
    return JSONResponse({"ok": True, "id": aid})


@router.post("/anfitrion/academia/{aid}/foto")
async def subir_imagen_academia(request: Request, aid: str, tipo: str = "foto") -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    if not _id_ok(aid):
        return JSONResponse({"ok": False, "error": "Academia inválida."}, status_code=400)
    # Una academia NUEVA aún no existe (se sube el logo antes de crearla); si
    # el id ya existe, debe ser mía.
    if _mia(ses["email"], aid) is None and datos.academia_existe(aid):
        return JSONResponse({"ok": False, "error": "Esta academia no está a tu nombre."}, status_code=404)
    if not almacen.disponible():
        return JSONResponse({"ok": False, "error": "La subida de imágenes no está disponible en este ambiente."}, status_code=503)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in ("image/jpeg", "image/png", "image/webp"):
        return JSONResponse({"ok": False, "error": "Formato no admitido (usa JPG, PNG o WebP)."}, status_code=415)
    cuerpo = await request.body()
    if not cuerpo or len(cuerpo) > almacen.MAX_BYTES:
        return JSONResponse({"ok": False, "error": "La imagen pesa demasiado (máx. 6 MB)."}, status_code=413)
    nombre = "logo_web.jpg" if tipo == "logo" else f"web_{int(time.time() * 1000)}.jpg"
    url = almacen.subir(almacen.BUCKET, f"academia_{aid}/{nombre}", cuerpo, ctype)
    if not url:
        return JSONResponse({"ok": False, "error": "No se pudo subir la imagen. Inténtalo de nuevo."}, status_code=502)
    return JSONResponse({"ok": True, "url": url})


@router.post("/anfitrion/academia/{aid}/eliminar")
async def eliminar_academia(request: Request, aid: str) -> JSONResponse:
    ses = sesion.de_request(request)
    if not ses:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    if _mia(ses["email"], aid) is None:
        return JSONResponse({"ok": False, "error": "Academia no encontrada."}, status_code=404)
    if not datos.eliminar_academia(aid, ses["email"]):
        return JSONResponse({"ok": False, "error": "No pudimos eliminarla en este momento."}, status_code=503)
    print(f"[academia-web] {ses['email']} eliminó {aid}", flush=True)
    return JSONResponse({"ok": True})
