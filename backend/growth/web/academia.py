"""FICHA PÚBLICA de una ACADEMIA y MATRÍCULA desde la web (pedido del director,
sep-2026: "si hago clic en la academia debería ir a la academia, ver los
planes y poder matricularme").

- GET  /academia/{id}                       → ficha tipo anuncio (Airbnb):
  galería (logo + fotos), deporte, sede con mapa Leaflet y Cómo llegar,
  descripción, WhatsApp y redes con logo, PROGRAMAS Y TARIFARIO (precio
  socio por frecuencia + invitado si hay recargo), reglas de cobro y el
  panel "Matricúlate" con el MISMO flujo que `academia_detalle_screen.
  _matricular` del app: login con Google → para mí / para mi hijo(a) (+
  edad) → nombre + celular → mes a mes o adelantado (descuento prepago si
  cumple los meses mínimos) → pago con Culqi (Yape/tarjeta; solo soles).
- POST /web/matricular                      → cobra con Culqi y guarda la
  matrícula EXACTAMENTE como `AppState.matricular` (fila en
  `pichangol_matriculas`: `Alumno.toJson` + `cuotas` embebidas; ids
  `al_<µs>` / `cu_<µs>_i`; conceptos "Plan · Mes"; mes a mes = 1 cuota
  pagada + N-1 pendientes con `autoDebito`), registra el cobro digital en
  el backend (`/pagos/matricula`, neto "por recibir" de la academia),
  intenta la suscripción de débito automático (mes a mes) y avisa al
  profe ("Nuevo alumno 🎓"). El profe la ve en su app y en Alumnos (web).
- GET  /academia/{id}/matricula/{alumno_id} → comprobante (solo el titular).

Multi-país: el cobro web es solo en soles (Culqi); academias en $ o Bs ven
el tarifario y matriculan desde la app.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import config
import empresa
from pagos import culqi
from paises import moneda_de_pais, pais_de_coordenadas, simbolo_de_moneda
from web import catalogos, datos, sesion, ui
from web.router import (PLAY_URL, _RED_SVG, _deporte, _maps, _no_encontrada, _pago_web_disponible,
                        _url_red, e)

router = APIRouter()

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"]
_LEAFLET = ("<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''>"
            "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>")


# ── helpers de datos ──────────────────────────────────────────────────────────

def _iso(a: dict) -> str:
    return pais_de_coordenadas(a.get("lat"), a.get("lng")) if (a.get("lat") or a.get("lng")) else "PE"


def _moneda(a: dict) -> tuple[str, str]:
    """(símbolo, ISO): la moneda congelada de la academia o la del país de su sede."""
    iso_pais = _iso(a)
    iso_mon = moneda_de_pais(iso_pais)
    sim = (a.get("moneda") or "").strip() or simbolo_de_moneda(iso_mon)
    if sim == "S/":
        iso_mon = "PEN"
    elif sim == "$":
        iso_mon = "USD"
    elif sim == "Bs":
        iso_mon = "BOB"
    return sim, iso_mon


def _planes(a: dict) -> list[dict]:
    out = []
    for p in a.get("planes") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        try:
            precio = float(p.get("precioMes") or 0)
        except (TypeError, ValueError):
            precio = 0.0
        if precio <= 0:
            continue
        tipo = str(p.get("tipo") or "mensual")
        try:
            meses = int(p.get("meses") or (1 if tipo != "prepago" else 3))
        except (TypeError, ValueError):
            meses = 1
        try:
            frec = int(p.get("frecuenciaSemana") or 0)
        except (TypeError, ValueError):
            frec = 0
        out.append({"id": str(p["id"]), "nombre": str(p.get("nombre") or p.get("programa") or "Plan"), "tipo": tipo,
                    "precioMes": precio, "meses": 0 if tipo == "porClase" else max(1, meses), "programa": str(p.get("programa") or ""),
                    "frecuenciaSemana": frec, "etapaEdad": str(p.get("etapaEdad") or ""), "duracionClase": str(p.get("duracionClase") or ""),
                    "horario": str(p.get("horario") or "")})
    return out


def _plan_total(p: dict) -> float:
    """Total del plan: por clase = precio; mensual/prepago = precio × meses (como `Plan.total`)."""
    return p["precioMes"] if p["tipo"] == "porClase" else p["precioMes"] * (p["meses"] or 1)


def orden_familiar(a: dict, previas: list[dict], parentesco_nuevo: str = "") -> int:
    """ORDEN del próximo matriculado por el mismo pagador (1 = primero, 2 =
    segundo, 3 = tercero o más). `descuentoFamiliar` (default True, decisión
    del director 26-sep-2026): cuentan TODOS los que paga el titular (él, su
    pareja, sus hijos); en False solo los hijos y solo si el nuevo es hijo.
    ESPEJO de `Academia.ordenFamiliarPara`."""
    familiar = a.get("descuentoFamiliar", True) is not False
    if not familiar and parentesco_nuevo != "hijo":
        return 1
    n = sum(1 for m in previas if familiar or (m.get("parentesco") == "hijo"))
    return n + 1


def dto_familiar_pct(a: dict, orden: int) -> float:
    """`Academia.descuentoHermanoPct`: 2.º → descuentoHermano2, 3.º+ → descuentoHermano3."""
    if orden >= 3:
        return float(a.get("descuentoHermano3") or 0)
    if orden == 2:
        return float(a.get("descuentoHermano2") or 0)
    return 0.0


def _parentesco(quien: str, es_hijo: bool) -> str:
    """'' (yo) · 'hijo' · 'familiar'. `es_hijo` viene de clientes viejos."""
    q = (quien or "").strip().lower()
    if q in ("hijo", "familiar"):
        return q
    return "hijo" if es_hijo else ""


def _dto_fam_por_quien(a: dict, email: str) -> dict:
    """Para el JS de la ficha: orden y % que le tocaría a la sesión según a
    quién matricule (`C.dtoFam[quien] = {orden, pct}`)."""
    previas = datos.matriculas_de_pagador(a.get("id") or "", email) if email else []
    out = {}
    for quien in ("yo", "hijo", "familiar"):
        orden = orden_familiar(a, previas, _parentesco(quien, False))
        out[quien] = {"orden": orden, "pct": dto_familiar_pct(a, orden)}
    return out


def _total(a: dict, p: dict, cantidad: int, mes_a_mes: bool, dto_fam: float = 0.0) -> tuple[float, float, int]:
    """Lo que se cobra AHORA y el ahorro, como `_HojaDatosAlumno._total`:
    mes a mes = 1 mes (con el descuento familiar); adelantado = total ×
    cantidad − descuentos (prepago si cantidad ≥ meses mínimos + familiar,
    aditivos como `Academia.descuentoTotalPct`). Devuelve (total, ahorro, n)."""
    n = max(1, min(int(cantidad or 1), 12))
    mes_a_mes = bool(mes_a_mes) and p["tipo"] == "mensual"
    dto_fam = max(0.0, min(100.0, float(dto_fam or 0)))
    if mes_a_mes:
        base = _plan_total(p)
        ahorro = round(base * dto_fam / 100.0, 2)
        return round(base - ahorro, 2), ahorro, n
    sin_dto = _plan_total(p) * n
    dto = float(a.get("descuentoPrepago") or 0)
    mmin = int(a.get("mesesMinPrepago") or 3)
    pct = min(100.0, (dto if (dto > 0 and n >= mmin) else 0.0) + dto_fam)
    ahorro = round(sin_dto * pct / 100.0, 2) if pct > 0 else 0.0
    return round(sin_dto - ahorro, 2), ahorro, n


def _wa(a: dict) -> str:
    tel = re.sub(r"\D", "", str(a.get("whatsapp") or ""))
    pref = catalogos.TEL_PREFIJO.get(_iso(a), "51")
    if tel and not tel.startswith(pref) and len(tel) <= 10:
        tel = pref + tel
    return tel


def _fotos_academia(a: dict) -> list[str]:
    return [u for u in ([a.get("logoUrl")] + list(a.get("fotos") or [])) if isinstance(u, str) and u.startswith("http")]


# ── ficha ─────────────────────────────────────────────────────────────────────

def _galeria(a: dict) -> str:
    fs = _fotos_academia(a)
    emoji = _deporte(a.get("deporte"))[1] if a.get("deporte") else "🎓"
    if not fs:
        return f"<div class='galeria una'><div class='sinfoto principal'>{emoji}</div></div>"
    if len(fs) == 1:
        return f"<div class='galeria una'><img class='principal' src='{e(fs[0])}' alt='{e(a.get('nombre', ''))}'></div>"
    return ("<div class='galeria'>" + f"<img class='principal' src='{e(fs[0])}' alt='{e(a.get('nombre', ''))}'>"
            + "".join(f"<img src='{e(u)}' alt='' loading='lazy'>" for u in fs[1:3]) + "</div>")


def _redes_html(a: dict) -> str:
    redes = a.get("redes") if isinstance(a.get("redes"), dict) else {}
    out = []
    for red, nombre in catalogos.REDES.items():
        url = _url_red(red, str(redes.get(red) or ""))
        if url:
            out.append(f"<a class='btn sec red-{red}' href='{e(url)}' target='_blank' rel='noopener'>{_RED_SVG.get(red, '')} {e(nombre)}</a>")
    return "".join(out)


def _tarifario(a: dict, sim: str, puede: bool) -> str:
    """Programas (grupo) con sus tarifas por frecuencia; planes sin programa
    van en "Otros planes". Botón "Matricularme" por tarifa."""
    planes = _planes(a)
    if not planes:
        return "<div class='panel' style='margin-top:20px'><h2>Programas y tarifario</h2><p class='sub'>Esta academia aún no publicó sus precios. Escríbele por WhatsApp.</p></div>"
    recargo = float(a.get("recargoInvitado") or 0)
    grupos: dict[str, list[dict]] = {}
    for p in planes:
        grupos.setdefault(p["programa"], []).append(p)
    html = "<div class='panel' style='margin-top:20px'><h2>Programas y tarifario</h2>"
    html += ("<p class='sub'>Precio socio del club" + (f" · invitado: + {e(sim)} {recargo:.0f} al mes" if recargo > 0 else "") + ". Elige tu programa y frecuencia.</p>")
    for prog, lst in grupos.items():
        lst = sorted(lst, key=lambda p: (p["frecuenciaSemana"] or 99, p["nombre"]))
        meta = " · ".join(x for x in (lst[0]["etapaEdad"], lst[0]["duracionClase"], lst[0]["horario"]) if x)
        html += f"<div class='prog'><div class='prog-h'><b>{e(prog or 'Otros planes')}</b>{('<span class=sub>' + e(meta) + '</span>') if meta else ''}</div>"
        for p in lst:
            if p["tipo"] == "porClase":
                etiqueta, unidad = "Por clase", "por clase"
            elif p["tipo"] == "prepago":
                etiqueta, unidad = f"Paquete de {p['meses']} meses", f"al mes · {e(sim)} {_plan_total(p):.0f} el paquete"
            else:
                etiqueta, unidad = (f"{p['frecuenciaSemana']}x por semana" if p["frecuenciaSemana"] else "Mensualidad"), "al mes"
            inv = f"<small>invitado {e(sim)} {p['precioMes'] + recargo:.0f}</small>" if recargo > 0 else ""
            boton = (f"<button type='button' class='btn chico elegir' data-plan='{e(p['id'])}'>Matricularme</button>" if puede else "")
            html += (f"<div class='tarifa-fila' data-plan='{e(p['id'])}'><div><b>{e(etiqueta)}</b><div class='sub' style='margin:0;font-size:12.5px'>{e(p['nombre'])}</div></div>"
                     f"<div class='tp'><b>{e(sim)} {p['precioMes']:.0f}</b> <span class='sub' style='margin:0'>{unidad}</span>{inv}</div>{boton}</div>")
        html += "</div>"
    reglas = []
    fam = "de la familia" if a.get("descuentoFamiliar", True) is not False else "hermano"
    if float(a.get("descuentoHermano2") or 0) > 0:
        reglas.append(f"2.º {fam} −{float(a['descuentoHermano2']):.0f} %")
    if float(a.get("descuentoHermano3") or 0) > 0:
        reglas.append(f"3.º {fam} −{float(a['descuentoHermano3']):.0f} %")
    if float(a.get("descuentoPrepago") or 0) > 0:
        reglas.append(f"pago adelantado de {int(a.get('mesesMinPrepago') or 3)}+ meses −{float(a['descuentoPrepago']):.0f} %")
    if reglas:
        html += f"<p class='sub' style='margin-top:12px'>Descuentos: {e(' · '.join(reglas))}.</p>"
    return html + "</div>"


@router.get("/academia/{academia_id}", response_class=HTMLResponse)
def pagina_academia(request: Request, academia_id: str) -> HTMLResponse:
    a = datos.academia(academia_id)
    if not a or not a.get("nombre"):
        return _no_encontrada("Academia no disponible")
    ses = sesion.de_request(request)
    sim, iso = _moneda(a)
    pais = _iso(a)
    dep = (a.get("deporte") or "").lower()
    dep_nombre, emoji = _deporte(dep) if dep else ("Academia", "🎓")
    lugar = " · ".join(x for x in (a.get("sedeClub"), a.get("zona")) if x)
    tel = _wa(a)
    con_mapa = bool(a.get("lat") or a.get("lng"))
    puede = _pago_web_disponible(iso) and bool(_planes(a))
    landing = ""
    try:
        from db.store import stores as _st
        if academia_id in (_st.landings or {}):
            landing = f"<a class='btn sec' href='/l/{e(academia_id)}'>Página de la academia</a>"
    except Exception:  # noqa: BLE001
        pass
    datos_li = ""
    if lugar or con_mapa:
        datos_li += (f"<li>📍 <span>{e(lugar or 'Sede en la app')}"
                     + (f" · <a href='#mapaFicha' id='btnLlegar'>Cómo llegar</a>" if con_mapa else "") + "</span></li>")
    if tel:
        datos_li += f"<li>💬 <span><a href='https://wa.me/{tel}?text=Hola,%20vi%20tu%20academia%20en%20Pichangol' target='_blank' rel='noopener'>WhatsApp de la academia</a></span></li>"
    if a.get("horarioTexto"):
        datos_li += f"<li>🕒 <span>{e(a['horarioTexto'])}</span></li>"
    mapa = ""
    if con_mapa:
        mapa = (f"<div class='mapa-ficha' id='mapaFicha'><div class='mapa' id='mapaFichaMapa' aria-label='Mapa de la sede'></div>"
                f"<div class='pie-mapa'><span>📍 {e(lugar or a['nombre'])}</span><a href='{_maps(a)}' target='_blank' rel='noopener'>Abrir en Google Maps</a>"
                f"<a href='https://www.google.com/maps/dir/?api=1&destination={a.get('lat')},{a.get('lng')}' target='_blank' rel='noopener'>Indicaciones paso a paso</a></div></div>")
    ficha = (f"{_galeria(a)}"
             "<div style='display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-top:16px'>"
             f"<div><div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'><span class='pill gris'>{ui.bandera(pais)} {emoji} {e(dep_nombre)}</span><span class='pill gris'>🎓 Academia</span></div>"
             f"<h1 style='margin-top:8px'>{e(a['nombre'])}</h1><p class='sub'>{e(lugar)}</p></div></div>"
             + (f"<p style='margin-top:10px;line-height:1.55'>{e(a.get('descripcion'))}</p>" if a.get("descripcion") else "")
             + (f"<ul class='datos'>{datos_li}</ul>" if datos_li else "") + mapa
             + (f"<div class='acciones' style='margin-top:12px'>{_redes_html(a)}{landing}</div>" if (_redes_html(a) or landing) else ""))
    tarifario = _tarifario(a, sim, puede)

    # Panel de matrícula (mismo flujo que el app) o "desde la app".
    if not puede:
        motivo = ("Esta academia aún no publicó sus precios." if not _planes(a) else
                  (f"Esta academia cobra en {e(sim)} y el pago en línea desde la web está disponible por ahora solo en soles."
                   if iso != "PEN" else "El pago en línea desde la web se está habilitando."))
        panel = (f"<div class='panel' style='margin-top:20px'><h2>Matricúlate desde la app</h2><p class='sub'>{motivo} En la app Pichangol te matriculas y pagas con los medios de tu país.</p>"
                 f"<div class='acciones'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a>"
                 + (f"<a class='btn sec' href='https://wa.me/{tel}' target='_blank' rel='noopener'>💬 Escribir a la academia</a>" if tel else "") + "</div></div>")
        cuerpo = f"<div style='padding-top:22px'>{ficha}</div>{tarifario}{panel}"
        return ui.shell(a["nombre"], cuerpo, desc=f"{a['nombre']} · academia de {dep_nombre.lower()} · {lugar}", sesion=ses,
                        og_image=(_fotos_academia(a) or ["/static/brand/logo_pichangol.png"])[0], extra_head=_LEAFLET if con_mapa else "")

    if sesion.activo():
        quien = ("" if not ses else
                 f"<div class='quien' id='quien'>{('<img src=' + chr(39) + e(ses['foto']) + chr(39) + ' alt=' + chr(39) + chr(39) + '>') if ses.get('foto') else ''}"
                 f"<div><b>{e(ses.get('nombre') or ses['email'])}</b><div class='m'>{e(ses['email'])}</div></div>"
                 "<button type='button' class='btn sec' onclick='cerrarSesion()'>Cambiar cuenta</button></div>")
        login = (f"<div class='login-box' id='loginBox'{' style=display:none' if ses else ''}><b>Inicia sesión con Google para matricularte</b>"
                 "<div class='sub' style='margin:4px 0 12px'>Como en el app: la matrícula queda a nombre de tu cuenta y el profe te ve en su lista de alumnos.</div>"
                 f"{sesion.boton_google(volver=f'/academia/{academia_id}')}<div class='estado bad' id='sesionErr'></div></div>")
        datos_box_ini = "" if ses else " style=display:none"
    else:
        quien, login, datos_box_ini = "", "", ""
    panel = (
        "<div class='dos' style='margin-top:22px' id='matricula'>"
        "<div class='panel'>"
        "<div class='paso' style='margin-top:0'><span>1</span> Elige tu programa</div>"
        "<div class='sub' id='planElegido'>Toca «Matricularme» en el tarifario de arriba.</div>"
        "<div class='paso'><span>2</span> ¿Para quién es?</div>"
        "<div class='chips'><button type='button' class='chip sel' data-quien='yo'>Para mí</button><button type='button' class='chip' data-quien='hijo'>Para mi hijo(a)</button><button type='button' class='chip' data-quien='familiar'>Para otra persona</button></div>"
        "<div class='sub' id='dtoFamBox' hidden style='margin-top:8px;color:#0B7A55'></div>"
        f"<div class='paso'><span>3</span> Tus datos</div>{login}"
        f"<div id='datosBox'{datos_box_ini}>{quien}"
        "<div class='row'><div><label for='nombre' id='lblNombre'>Nombre del alumno</label>"
        f"<input id='nombre' autocomplete='name' maxlength='80' placeholder='Como en tu documento' value='{e((ses or {}).get('nombre', ''))}'></div>"
        "<div><label for='celular'>Celular de contacto</label><input id='celular' inputmode='tel' autocomplete='tel' maxlength='20' placeholder='9 dígitos'></div></div>"
        "<div id='edadBox' hidden><label for='edad'>Edad del hijo(a)</label><input id='edad' type='number' min='2' max='17' inputmode='numeric' style='max-width:140px'></div>"
        "<div id='emailPersonaBox' hidden><label for='emailPersona'>Su correo de Google <span class='req'>opcional · verá sus clases y pagos en su propia app</span></label><input id='emailPersona' type='email' autocomplete='off' maxlength='120' placeholder='correo@gmail.com'></div></div>"
        "<div class='paso'><span>4</span> ¿Cómo pagas?</div>"
        "<div class='chips' id='modo'><button type='button' class='chip' data-modo='mes'>Mes a mes</button><button type='button' class='chip sel' data-modo='adelantado'>Adelantado</button></div>"
        "<div id='cantBox' style='margin-top:10px'><label id='lblCant'>¿Cuántos meses?</label><div class='chips' id='cant'>"
        + "".join(f"<button type='button' class='chip{' sel' if n == 1 else ''}' data-n='{n}'>{n}</button>" for n in (1, 2, 3, 6, 12)) + "</div></div>"
        "<div class='estado bad' id='err'></div></div>"
        "<aside class='resumen'><div class='panel'><h3>Tu matrícula</h3>"
        f"<div class='sub' style='margin-bottom:10px'>{e(a['nombre'])}</div><div id='lineas'><div class='sub'>Sin programa elegido.</div></div>"
        "<div class='total'><span>Pagas hoy</span><span id='tot'>—</span></div>"
        "<div class='sub' id='notaModo' style='font-size:12.5px;margin-top:6px'></div>"
        "<div style='margin-top:14px'><button class='btn lg' id='btnPagar' disabled>Elige un programa</button></div>"
        f"<div style='margin-top:14px'>{ui.marcas_pago()}</div>"
        "<div class='sub' style='font-size:12.5px;margin-top:12px'>Al pagar, la matrícula queda registrada en la academia y en tu app (Mis academias). "
        f"Dudas: <a href='mailto:{e(empresa.valores()['empresa_correo'])}'>{e(empresa.valores()['empresa_correo'])}</a>.</div>"
        "</div></aside></div>"
        "<div class='barra-fija'><div><div class='sub' style='font-size:12px;margin:0'>Pagas hoy</div><div class='t' id='totBarra'>—</div></div>"
        "<button class='btn' id='btnPagarBarra' disabled>Elige un programa</button></div>")
    cfg = json.dumps({"id": academia_id, "moneda": sim, "pk": config.CULQI_PUBLIC_KEY, "planes": _planes(a),
                      "descuentoPrepago": float(a.get("descuentoPrepago") or 0), "mesesMinPrepago": int(a.get("mesesMinPrepago") or 3),
                      "dtoFam": _dto_fam_por_quien(a, (ses or {}).get("email") or ""),
                      "lat": a.get("lat"), "lng": a.get("lng"), "nombre": a.get("nombre"),
                      "login": sesion.activo(), "sesion": ses}, ensure_ascii=False)
    cuerpo = (f"<div style='padding-top:22px'>{ficha}</div>{tarifario}{panel}"
              f"<script>window.__academia={cfg};</script><script src='https://checkout.culqi.com/js/v4'></script>"
              f"<script>{sesion.JS_SESION if sesion.activo() else ''}{_JS_ACADEMIA}</script>")
    return ui.shell(a["nombre"], cuerpo, con_barra=True, desc=f"{a['nombre']} · academia de {dep_nombre.lower()} · {lugar}. Matricúlate en línea.",
                    og_image=(_fotos_academia(a) or ["/static/brand/logo_pichangol.png"])[0], sesion=ses,
                    extra_head=(_LEAFLET if con_mapa else "") + (sesion.GIS_SCRIPT if (sesion.activo() and not ses) else ""))


_JS_ACADEMIA = r"""
(function(){
  var C = window.__academia, $ = function(id){ return document.getElementById(id); };
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function fmt(v){ return C.moneda + ' ' + (Math.round(v * 100) / 100).toFixed(2); }
  var st = { plan: null, quien: 'yo', modo: 'adelantado', n: 1 };
  function planTotal(p){ return p.tipo === 'porClase' ? p.precioMes : p.precioMes * (p.meses || 1); }
  function famInfo(){ return (C.sesion && C.dtoFam && C.dtoFam[st.quien]) ? C.dtoFam[st.quien] : {orden: 1, pct: 0}; }
  function famPct(){ return famInfo().pct || 0; }
  function calc(){
    var p = st.plan; if(!p) return null;
    var mesAMes = st.modo === 'mes' && p.tipo === 'mensual';
    var fam = famPct(), prep = (C.descuentoPrepago > 0 && st.n >= C.mesesMinPrepago && !mesAMes) ? C.descuentoPrepago : 0;
    if(mesAMes){ var b = planTotal(p), af = b * fam / 100; return { total: b - af, ahorro: af, ahorroFam: af, ahorroPrep: 0, mesAMes: true, n: st.n }; }
    var sin = planTotal(p) * st.n, pct = Math.min(100, prep + fam);
    return { total: sin - sin * pct / 100, ahorro: sin * pct / 100, ahorroFam: sin * fam / 100, ahorroPrep: sin * prep / 100, mesAMes: false, n: st.n };
  }
  function unidad(p){ return p.tipo === 'porClase' ? (st.n === 1 ? 'clase' : 'clases') : (p.tipo === 'prepago' ? (st.n === 1 ? 'paquete' : 'paquetes') : (st.n === 1 ? 'mes' : 'meses')); }
  function pintar(){
    var p = st.plan, r = calc();
    document.querySelectorAll('.tarifa-fila').forEach(function(f){ f.classList.toggle('sel', !!p && f.dataset.plan === p.id); });
    $('planElegido').innerHTML = p ? '<b>' + esc(p.nombre) + '</b> · ' + fmt(p.precioMes) + (p.tipo === 'porClase' ? ' por clase' : ' al mes') : 'Toca «Matricularme» en el tarifario de arriba.';
    var modoBox = $('modo'); if(modoBox) modoBox.style.display = (p && p.tipo === 'mensual') ? '' : 'none';
    if(p && p.tipo !== 'mensual' && st.modo === 'mes') st.modo = 'adelantado';
    $('lblCant').textContent = !p ? '¿Cuántos meses?' : (p.tipo === 'porClase' ? '¿Cuántas clases pagarás?' : (p.tipo === 'prepago' ? '¿Cuántos paquetes de ' + p.meses + ' meses?' : (st.modo === 'mes' ? '¿Por cuántos meses te comprometes?' : '¿Cuántos meses adelantas?')));
    document.querySelectorAll('#modo .chip').forEach(function(b){ b.classList.toggle('sel', b.dataset.modo === st.modo); });
    document.querySelectorAll('#cant .chip').forEach(function(b){ b.classList.toggle('sel', +b.dataset.n === st.n); });
    $('lblNombre').textContent = st.quien === 'hijo' ? 'Nombre del hijo(a)' : (st.quien === 'familiar' ? 'Nombre de la persona' : 'Nombre del alumno');
    $('edadBox').hidden = st.quien !== 'hijo';
    $('emailPersonaBox').hidden = st.quien !== 'familiar';
    var fi = famInfo(), fb = $('dtoFamBox');
    fb.hidden = !(fi.pct > 0);
    if(fi.pct > 0) fb.textContent = '🎉 Descuento familiar: ' + (fi.orden === 2 ? '2.º' : '3.º o más') + ' de tu familia en esta academia → −' + fi.pct + ' %.';
    if(!p || !r){ $('lineas').innerHTML = '<div class="sub">Sin programa elegido.</div>'; $('tot').textContent = '—'; $('totBarra').textContent = '—'; $('notaModo').textContent = '';
      ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = true; $(id).textContent = 'Elige un programa'; }); return; }
    var lineas = '<div class="linea"><span>' + esc(p.nombre) + '</span><span>' + fmt(planTotal(p)) + '</span></div>';
    if(!r.mesAMes && st.n > 1) lineas += '<div class="linea"><span>× ' + st.n + ' ' + unidad(p) + '</span><span>' + fmt(planTotal(p) * st.n) + '</span></div>';
    if(r.ahorroPrep > 0) lineas += '<div class="linea"><span>Descuento por adelantar (−' + C.descuentoPrepago + ' %)</span><span>−' + fmt(r.ahorroPrep) + '</span></div>';
    if(r.ahorroFam > 0) lineas += '<div class="linea"><span>Descuento familiar (−' + famPct() + ' %)</span><span>−' + fmt(r.ahorroFam) + '</span></div>';
    $('lineas').innerHTML = lineas;
    $('tot').textContent = fmt(r.total); $('totBarra').textContent = fmt(r.total);
    $('notaModo').textContent = r.mesAMes ? ('Hoy pagas 1 mes; los ' + (st.n - 1) + ' siguientes se cobran mes a mes a la misma tarjeta.') : (st.n > 1 ? 'Pago adelantado: quedas al día ' + st.n + ' ' + unidad(p) + '.' : '');
    ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = false; $(id).textContent = 'Pagar ' + fmt(r.total); });
  }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest('.elegir'); if(!b) return;
    st.plan = (C.planes || []).filter(function(p){ return p.id === b.dataset.plan; })[0] || null; st.n = 1; pintar();
    var m = $('matricula'); if(m) m.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
  document.querySelectorAll('[data-quien]').forEach(function(b){ b.addEventListener('click', function(){ st.quien = b.dataset.quien; document.querySelectorAll('[data-quien]').forEach(function(x){ x.classList.toggle('sel', x === b); }); if(st.quien !== 'yo' && $('nombre').value === ((C.sesion || {}).nombre || '')) $('nombre').value = ''; pintar(); }); });
  document.querySelectorAll('#modo .chip').forEach(function(b){ b.addEventListener('click', function(){ st.modo = b.dataset.modo; pintar(); }); });
  document.querySelectorAll('#cant .chip').forEach(function(b){ b.addEventListener('click', function(){ st.n = +b.dataset.n; pintar(); }); });
  function mostrarError(m){ var el = $('err'); el.textContent = m; el.style.display = 'block'; el.scrollIntoView({behavior: 'smooth', block: 'center'}); }
  function ocultarError(){ $('err').style.display = 'none'; }
  window.alIniciarSesion = function(u){
    C.sesion = u;
    var lb = $('loginBox'), db = $('datosBox'); if(lb) lb.style.display = 'none'; if(db) db.style.display = '';
    if($('nombre') && !$('nombre').value && st.quien === 'yo') $('nombre').value = u.nombre || '';
    if(db && !$('quien')){ db.insertAdjacentHTML('afterbegin', '<div class="quien" id="quien">' + (u.foto ? '<img src="' + esc(u.foto) + '" alt="">' : '') + '<div><b>' + esc(u.nombre || u.email) + '</b><div class="m">' + esc(u.email) + '</div></div><button type="button" class="btn sec" onclick="cerrarSesion()">Cambiar cuenta</button></div>'); }
    // El descuento familiar depende de lo que YA paga esta cuenta: se consulta al entrar.
    fetch('/web/academia/' + encodeURIComponent(C.id) + '/descuento-familiar').then(function(x){ return x.json(); }).then(function(d){ if(d && d.dtoFam){ C.dtoFam = d.dtoFam; pintar(); } }).catch(function(){});
    pintar();
  };
  function validar(){
    if(!st.plan) return 'Elige un programa en el tarifario.';
    if(C.login && !C.sesion) return 'Inicia sesión con Google para matricularte.';
    if($('nombre').value.trim().length < 3) return st.quien === 'hijo' ? 'Escribe el nombre de tu hijo(a).' : (st.quien === 'familiar' ? 'Escribe el nombre de la persona.' : 'Escribe el nombre del alumno.');
    var ep = st.quien === 'familiar' ? $('emailPersona').value.trim() : '';
    if(ep && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(ep)) return 'Ese correo no se ve bien. Puedes dejarlo vacío.';
    if(ep && C.sesion && ep.toLowerCase() === String(C.sesion.email || '').toLowerCase()) return 'Ese es tu propio correo: elige «Para mí».';
    if($('celular').value.replace(/\D/g, '').length < 8) return 'Escribe un celular de contacto.';
    if(st.quien === 'hijo' && !(+$('edad').value >= 2 && +$('edad').value <= 17)) return 'Indica la edad de tu hijo(a) (2 a 17).';
    return '';
  }
  function pagar(){
    ocultarError();
    var v = validar(); if(v){ mostrarError(v); if(!st.plan) window.scrollTo({top: 0, behavior: 'smooth'}); return; }
    if(!C.pk){ mostrarError('El pago en línea no está disponible por ahora.'); return; }
    var r = calc();
    Culqi.publicKey = C.pk;
    Culqi.settings({ title: 'Pichangol', currency: 'PEN', amount: Math.round(r.total * 100) });
    Culqi.options({ lang: 'es', installments: false,
      paymentMethods: { tarjeta: true, yape: true, bancaMovil: false, agente: false, billetera: false, cuotealo: false },
      style: { logo: '', bannerColor: '#0F1B2D', buttonBackground: '#0E8F67', buttonText: 'Pagar', buttonTextColor: '#FFFFFF' } });
    window.culqi = function(){
      if(Culqi.token){
        var token = Culqi.token.id, medio = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
        Culqi.close();
        ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = true; $(id).textContent = 'Confirmando tu pago…'; });
        fetch('/web/matricular', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({academia_id: C.id, plan_id: st.plan.id, nombre: $('nombre').value.trim(), celular: $('celular').value.trim(),
                                es_hijo: st.quien === 'hijo', edad: st.quien === 'hijo' ? +$('edad').value : null, cantidad: st.n,
                                quien: st.quien, email_persona: st.quien === 'familiar' ? $('emailPersona').value.trim() : '',
                                mes_a_mes: st.modo === 'mes', token: token, medio: medio})})
          .then(function(x){ return x.json(); })
          .then(function(p){
            if(p.ok){ window.location.href = p.url; }
            else { pintar(); if(p.error === 'sesion_requerida'){ C.sesion = null; var lb = $('loginBox'), db = $('datosBox'); if(lb) lb.style.display = ''; if(db) db.style.display = 'none'; } mostrarError(p.mensaje || 'El pago no se pudo procesar. No se te cobró nada.'); }
          }).catch(function(){ pintar(); mostrarError('No pudimos confirmar el pago. Si te cobraron, escríbenos con tu correo.'); });
      } else if(Culqi.order){ mostrarError('Este medio de pago no está habilitado. Usa Yape o tarjeta.'); }
      else { mostrarError((Culqi.error && Culqi.error.user_message) || 'No se pudo procesar el pago.'); }
    };
    Culqi.open();
  }
  $('btnPagar').addEventListener('click', pagar); $('btnPagarBarra').addEventListener('click', pagar);
  // Mapa de la sede (Cómo llegar abre el mapa dentro de la ficha, como en las canchas).
  var bl = $('btnLlegar');
  if(bl && C.lat != null) bl.addEventListener('click', function(ev){ ev.preventDefault(); var box = $('mapaFicha'); box.classList.add('open'); box.scrollIntoView({behavior: 'smooth', block: 'center'});
    if(!window.L || box.dataset.ok) return; box.dataset.ok = '1'; var m = L.map('mapaFichaMapa').setView([C.lat, C.lng], 16);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; OpenStreetMap'}).addTo(m);
    L.marker([C.lat, C.lng]).addTo(m).bindPopup('<b>' + esc(C.nombre) + '</b>').openPopup(); setTimeout(function(){ m.invalidateSize(); }, 200); });
  pintar();
})();
"""


# ── matricular (POST) ─────────────────────────────────────────────────────────

class MatricularReq(BaseModel):
    academia_id: str
    plan_id: str
    nombre: str
    celular: str = ""
    es_hijo: bool = False
    edad: int | None = None
    cantidad: int = 1
    mes_a_mes: bool = False
    token: str
    medio: str = "tarjeta"
    quien: str = ""  # '' | 'yo' | 'hijo' | 'familiar' (otro adulto de la familia)
    email_persona: str = ""  # correo propio del familiar (opcional)


@router.get("/web/academia/{academia_id}/descuento-familiar")
def descuento_familiar(academia_id: str, request: Request = None) -> dict:
    """Orden y % del descuento familiar que le toca a la sesión en esta
    academia según a quién matricule (lo pide el JS al iniciar sesión)."""
    ses = sesion.de_request(request) if sesion.activo() else None
    a = datos.academia(academia_id)
    if not a:
        return {"ok": False, "dtoFam": None}
    return {"ok": True, "dtoFam": _dto_fam_por_quien(a, (ses or {}).get("email") or "")}


def _mes_nombre(d: datetime) -> str:
    return MESES[d.month - 1]


def _sumar_meses(d: datetime, i: int) -> datetime:
    """`DateTime(hoy.year, hoy.month + i, hoy.day)` de Dart: mismo día i meses
    después (Dart desborda al mes siguiente si el día no existe)."""
    m = d.month - 1 + i
    y, m = d.year + m // 12, m % 12 + 1
    try:
        return d.replace(year=y, month=m)
    except ValueError:
        import calendar
        extra = d.day - calendar.monthrange(y, m)[1]
        base = d.replace(year=y, month=m, day=calendar.monthrange(y, m)[1])
        from datetime import timedelta
        return base + timedelta(days=extra)


@router.post("/web/matricular")
def matricular(req: MatricularReq, request: Request = None) -> dict:
    """Cobra con Culqi y registra la matrícula como el app (ver módulo)."""
    ses = sesion.de_request(request) if sesion.activo() else None
    if sesion.activo() and not ses:
        return {"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para matricularte."}
    a = datos.academia(req.academia_id)
    if not a or not a.get("nombre"):
        return {"ok": False, "error": "academia", "mensaje": "La academia ya no está disponible."}
    sim, iso = _moneda(a)
    if not _pago_web_disponible(iso):
        return {"ok": False, "error": "moneda", "mensaje": "El pago en línea desde la web está disponible solo en soles. Matricúlate desde la app."}
    plan = next((p for p in _planes(a) if p["id"] == req.plan_id), None)
    if not plan:
        return {"ok": False, "error": "plan", "mensaje": "Ese programa ya no está disponible. Vuelve a elegirlo."}
    nombre = re.sub(r"\s+", " ", req.nombre or "").strip()[:80]
    celular = re.sub(r"\D", "", req.celular or "")[:15]
    if len(nombre) < 3:
        return {"ok": False, "error": "nombre", "mensaje": "Escribe el nombre del alumno."}
    if len(celular) < 8:
        return {"ok": False, "error": "celular", "mensaje": "Escribe un celular de contacto."}
    parentesco = _parentesco(req.quien, req.es_hijo)
    es_hijo = parentesco == "hijo"
    if es_hijo and not (req.edad and 2 <= int(req.edad) <= 17):
        return {"ok": False, "error": "edad", "mensaje": "Indica la edad de tu hijo(a)."}
    email = (ses["email"] if ses else "").strip().lower()
    email_persona = (req.email_persona or "").strip().lower()[:120] if parentesco == "familiar" else ""
    if email_persona and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_persona):
        return {"ok": False, "error": "email_persona", "mensaje": "El correo de la persona no se ve bien. Puedes dejarlo vacío."}
    if email_persona and email and email_persona == email:
        return {"ok": False, "error": "email_persona", "mensaje": "Ese es tu propio correo: elige «Para mí»."}
    # Descuento familiar (punto 3 del pedido del director, 26-sep-2026): el
    # orden se calcula en el SERVIDOR con lo que ya paga esta cuenta aquí.
    previas = datos.matriculas_de_pagador(req.academia_id, email) if email else []
    orden = orden_familiar(a, previas, parentesco)
    dto_fam = dto_familiar_pct(a, orden)
    total, ahorro, n = _total(a, plan, req.cantidad, req.mes_a_mes, dto_fam)
    mes_a_mes = bool(req.mes_a_mes) and plan["tipo"] == "mensual"
    titular = (ses or {}).get("nombre") or "Apoderado"
    nota_dto = f" (−{dto_fam:.0f}% familiar)" if dto_fam > 0 else ""
    precio_mes = round(float(plan["precioMes"]) * (1 - dto_fam / 100.0), 2)  # la cuota queda con el descuento, como el app
    concepto = f"Matrícula {a['nombre']} · {plan['nombre']}"
    monto_c = int(round(total * 100))
    cargo = culqi.crear_cargo(token=req.token.strip(), monto_centimos=monto_c, email=email or "sin-correo@pichangol.app",
                              descripcion=concepto[:80], moneda=iso,
                              metadata={"canal": "web", "academia_id": req.academia_id, "plan_id": plan["id"]})
    if not cargo.get("ok"):
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada." + (f" ({msg[:80]})" if msg else "")}
    charge_id = str(cargo.get("charge_id") or "")

    # Matrícula EXACTAMENTE como `AppState.matricular` (el profe la ve en su app).
    ahora = datetime.now()
    us = int(time.time() * 1_000_000)
    alumno_id = f"al_{us}"
    es_menor = es_hijo
    alumno = {"id": alumno_id, "academiaId": req.academia_id, "nombre": nombre, "whatsapp": "" if es_menor else celular,
              "email": email, "apoderadoNombre": titular.strip() if es_menor else "", "apoderadoWhatsapp": celular if es_menor else "",
              "esSocioSede": True, "ordenHermano": orden, "sedeId": ""}
    if parentesco:
        alumno["parentesco"] = parentesco
    if email_persona:
        alumno["emailAlumno"] = email_persona
    if (ses or {}).get("foto") and not parentesco:  # la foto del titular solo si el alumno ES el titular
        alumno["fotoUrl"] = ses["foto"]
    if es_menor and req.edad:
        alumno["edad"] = int(req.edad)
    cuotas = []
    if plan["tipo"] == "porClase":
        cuotas.append({"id": f"cu_{us}", "academiaId": req.academia_id, "alumnoId": alumno_id,
                       "concepto": f"{n} clase{'' if n == 1 else 's'} particular{'' if n == 1 else 'es'} · {plan['nombre']}",
                       "monto": plan["precioMes"] * n, "vencimiento": ahora.isoformat(), "pagada": True, "fechaPago": ahora.isoformat(),
                       "operacionId": charge_id})
    else:
        meses = (1 if plan["tipo"] == "mensual" else plan["meses"]) * n
        pagadas_n = 1 if mes_a_mes else meses
        for i in range(meses):
            venc = _sumar_meses(ahora, i)
            pagada = i < pagadas_n
            c = {"id": f"cu_{us}_{i}", "academiaId": req.academia_id, "alumnoId": alumno_id,
                 "concepto": f"{plan['nombre']} · {_mes_nombre(venc)}{nota_dto}", "monto": precio_mes, "vencimiento": venc.isoformat(), "pagada": pagada}
            if pagada:
                c["fechaPago"] = ahora.isoformat()
                c["operacionId"] = charge_id
            if mes_a_mes:
                c["autoDebito"] = True
            cuotas.append(c)
    # Lo COBRADO hoy (con descuento) se guarda aparte: las cuotas llevan el precio
    # de lista como en el app; el comprobante muestra lo que salió de la tarjeta.
    data = dict(alumno, cuotas=cuotas, canal="web",
                pagoWeb={"monto": float(total), "ahorro": float(ahorro), "operacion": charge_id, "dtoFamiliar": float(dto_fam),
                         "medio": "yape" if req.medio == "yape" else "tarjeta", "fecha": ahora.isoformat()})
    if not datos.insertar_matricula(alumno_id, req.academia_id, email, data):
        # El cobro ya se hizo: se avisa con el N.º de operación para atenderlo a mano.
        print(f"[matricula-web] cobro {charge_id} sin fila en pichangol_matriculas ({email}, {req.academia_id})", flush=True)
        return {"ok": False, "error": "guardar", "mensaje": f"Tu pago se procesó (operación {charge_id}) pero no pudimos registrar la matrícula. "
                                                             f"Escríbenos a {empresa.valores()['empresa_correo']} y la completamos."}
    # Contabilidad: el cobro digital congela la comisión del país y deja el neto "por recibir" de la academia.
    try:
        from pagos.router import MatriculaReq, post_matricula
        post_matricula(MatriculaReq(academia_id=req.academia_id, monto_soles=float(total), matricula_id=charge_id or alumno_id,
                                    pais=_iso(a).lower(), concepto=concepto))
    except Exception as ex:  # noqa: BLE001 — la contabilidad nunca deshace un cobro
        print(f"[matricula-web] contabilidad falló: {ex}", flush=True)
    try:
        from db.store import stores as _st
        _st.registrar_pago(tipo="cobro_web", monto_centimos=monto_c, moneda=iso, estado="aprobado", culqi_charge_id=charge_id,
                           email=email, medio="yape" if req.medio == "yape" else "tarjeta", concepto=f"matricula:{alumno_id}")
    except Exception:  # noqa: BLE001
        pass
    if mes_a_mes:  # débito automático de los meses siguientes (best-effort, como el app)
        try:
            from pagos.router import SuscripcionAlumnoReq, post_suscripcion_alumno
            post_suscripcion_alumno(SuscripcionAlumnoReq(alumno_id=alumno_id, academia_id=req.academia_id, email=email, token=req.token.strip(),
                                                         monto_soles=float(precio_mes), nombre=titular, pais=_iso(a).lower(),
                                                         concepto=concepto, cobros_restantes=max(0, n - 1)))
        except Exception as ex:  # noqa: BLE001
            print(f"[matricula-web] suscripción no creada ({alumno_id}): {ex}", flush=True)
    dueno = (a.get("dueno") or "").strip().lower()
    if dueno:
        try:
            from pagos.router import _aviso_push_usuario
            _aviso_push_usuario(dueno, "Nuevo alumno 🎓", f"{nombre} se matriculó en {a['nombre']} · {plan['nombre']} (pagó {sim} {total:.2f} por la web).", tipo="academia")
        except Exception:  # noqa: BLE001
            pass
    print(f"[matricula-web] {email} → {a['nombre']} · {plan['nombre']} · {sim} {total:.2f} · {alumno_id}", flush=True)
    return {"ok": True, "url": f"/academia/{req.academia_id}/matricula/{alumno_id}", "alumno_id": alumno_id, "charge_id": charge_id}


# ── comprobante ───────────────────────────────────────────────────────────────

@router.get("/academia/{academia_id}/matricula/{alumno_id}", response_class=HTMLResponse)
def comprobante_matricula(request: Request, academia_id: str, alumno_id: str) -> HTMLResponse:
    a = datos.academia(academia_id)
    m = datos.matricula(alumno_id)
    ses = sesion.de_request(request)
    if not a or not m or m.get("academiaId") != academia_id:
        return _no_encontrada("Matrícula no encontrada")
    email = (m.get("email") or "").strip().lower()
    email_alumno = (m.get("emailAlumno") or "").strip().lower()
    if sesion.activo() and (not ses or ses["email"].strip().lower() not in {x for x in (email, email_alumno) if x}):
        volver = f"/academia/{academia_id}/matricula/{alumno_id}"
        return ui.shell("Matrícula", ("<div class='panel' style='text-align:center;margin-top:24px'><h1>Esta matrícula es privada</h1>"
                                      "<p class='sub'>Inicia sesión con la cuenta de Google con la que te matriculaste.</p>"
                                      f"<div class='acciones' style='justify-content:center'><a class='btn' href='/entrar?volver={e(volver)}'>Iniciar sesión</a></div></div>"), sesion=ses)
    sim, _iso_m = _moneda(a)
    cuotas = [c for c in (m.get("cuotas") or []) if isinstance(c, dict)]
    pagadas = [c for c in cuotas if c.get("pagada")]
    pw = m.get("pagoWeb") if isinstance(m.get("pagoWeb"), dict) else {}
    total = float(pw.get("monto") or 0) or sum(float(c.get("monto") or 0) for c in pagadas)
    ahorro = float(pw.get("ahorro") or 0)
    filas = "".join(
        f"<li>{'✅' if c.get('pagada') else '⏳'} <span>{e(c.get('concepto'))} · {e(sim)} {float(c.get('monto') or 0):.2f}"
        f"{' · pagada' if c.get('pagada') else ' · vence ' + e(str(c.get('vencimiento'))[:10])}</span></li>" for c in cuotas)
    op = next((c.get("operacionId") for c in pagadas if c.get("operacionId")), "")
    tel = _wa(a)
    cuerpo = ("<div class='panel' style='margin-top:24px'><div class='check-ok'>✓</div><h1 style='text-align:center'>¡Matrícula registrada!</h1>"
              f"<p class='sub' style='text-align:center'>{e(m.get('nombre'))} ya es alumno de <b>{e(a['nombre'])}</b>. El profe lo ve en su lista y tú en la app (Mis academias).</p>"
              f"<ul class='datos'>{filas}</ul>"
              + (f"<p class='sub' style='font-size:13px'>{'Descuentos (adelanto + familiar)' if (float(pw.get('dtoFamiliar') or 0) > 0 and ahorro > 0) else 'Descuento por pago adelantado'}: −{e(sim)} {ahorro:.2f}</p>" if ahorro > 0 else "")
              + (f"<p class='sub' style='font-size:13px'>🎉 Descuento familiar aplicado: −{float(pw.get('dtoFamiliar') or 0):.0f} % ({'2.º' if int(m.get('ordenHermano') or 1) == 2 else '3.º o más'} de tu familia en esta academia).</p>" if float(pw.get('dtoFamiliar') or 0) > 0 else "")
              + f"<div class='total'><span>Pagado hoy</span><span>{e(sim)} {total:.2f}</span></div>"
              + (f"<p class='sub' style='font-size:12.5px'>N.º de operación: {e(op)}</p>" if op else "")
              + "<div class='acciones' style='margin-top:14px'>"
              + (f"<a class='btn' href='https://wa.me/{tel}?text=Hola,%20acabo%20de%20matricular%20a%20{e(m.get('nombre', ''))}%20por%20Pichangol' target='_blank' rel='noopener'>💬 Escribir a la academia</a>" if tel else "")
              + f"<a class='btn sec' href='/academia/{e(academia_id)}'>Ver la academia</a><a class='btn sec' href='{PLAY_URL}'>Abrir en la app</a></div></div>")
    return ui.shell("Matrícula registrada", cuerpo, sesion=ses)
