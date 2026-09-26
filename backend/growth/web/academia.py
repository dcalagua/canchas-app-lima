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
        # CARRITO (pedido del director, 26-sep-2026): varias personas de la familia, un solo pago.
        "<div class='paso'><span>5</span> ¿Matriculas a más personas?</div>"
        "<div class='sub' style='margin-top:4px'>Tu pareja, tus hijos… cada uno con su programa y su forma de pago. Todo se paga en un solo cobro y el descuento familiar se aplica solo por orden (1.º completo, 2.º y 3.º con descuento).</div>"
        "<div style='margin-top:10px'><button type='button' class='btn sec' id='btnAgregar' hidden>➕ Guardar a esta persona y agregar otra</button></div>"
        "<div class='estado bad' id='err'></div></div>"
        "<aside class='resumen'><div class='panel'><h3>Tu matrícula <span class='sub' id='nPersonas' style='font-weight:600;font-size:13px'></span></h3>"
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
                      "dtoFam": _dto_fam_por_quien(a, (ses or {}).get("email") or ""), "fam": _fam_base(a, (ses or {}).get("email") or ""),
                      "lat": a.get("lat"), "lng": a.get("lng"), "nombre": a.get("nombre"),
                      "login": sesion.activo(), "sesion": ses}, ensure_ascii=False)
    cuerpo = (f"<div style='padding-top:22px'>{ficha}</div>{tarifario}{panel}"
              f"<script>window.__academia={cfg};</script><script src='https://checkout.culqi.com/js/v4'></script>"
              f"<script>{sesion.JS_SESION if sesion.activo() else ''}{_JS_ACADEMIA}</script>")
    return ui.shell(a["nombre"], cuerpo, con_barra=True, desc=f"{a['nombre']} · academia de {dep_nombre.lower()} · {lugar}. Matricúlate en línea.",
                    og_image=(_fotos_academia(a) or ["/static/brand/logo_pichangol.png"])[0], sesion=ses,
                    extra_head=(_LEAFLET if con_mapa else "") + _CSS_CARRITO + (sesion.GIS_SCRIPT if (sesion.activo() and not ses) else ""))


# Carrito en el resumen: una tarjeta por persona guardada con ✕ para quitarla.
_CSS_CARRITO = ("<style>.cart-it{border:1px solid var(--trazo);border-radius:14px;padding:10px 12px;margin-bottom:8px;background:#fff}"
                ".cart-it .ci-t{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.cart-it .ci-t .sub{margin:0;font-size:12.5px}"
                ".cart-it .ci-d{display:flex;align-items:center;gap:8px;white-space:nowrap}.cart-it .ok{color:#0B7A55;font-weight:700}"
                ".cart-it .quitar{border:0;background:#F4F7FA;color:#555;border-radius:50%;width:26px;height:26px;cursor:pointer;font-size:13px;line-height:26px;padding:0}"
                ".cart-it .quitar:hover{background:#FDE8E8;color:#B3261E}.cart-h{font-weight:800;margin:12px 0 4px;font-size:14px}.cart-h .sub{font-weight:600;font-size:12.5px}"
                "[data-quien]:disabled{opacity:.45;cursor:not-allowed}</style>")


_JS_ACADEMIA = r"""
(function(){
  var C = window.__academia, $ = function(id){ return document.getElementById(id); };
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function fmt(v){ return C.moneda + ' ' + (Math.round(v * 100) / 100).toFixed(2); }
  // CARRITO DE MATRÍCULA: `carrito` = personas ya guardadas; el formulario es la
  // persona "en edición". Todo se paga en UN solo cobro (/web/matricular-varios).
  var st = { plan: null, quien: 'yo', modo: 'adelantado', n: 1, carrito: [] };
  var MAX_PERSONAS = 8;
  function planTotal(p){ return p.tipo === 'porClase' ? p.precioMes : p.precioMes * (p.meses || 1); }
  function parentesco(q){ return q === 'hijo' ? 'hijo' : (q === 'familiar' ? 'familiar' : ''); }
  function quienTxt(par){ return par === 'hijo' ? 'Mi hijo(a)' : (par === 'familiar' ? 'Familiar' : 'Yo'); }
  // ORDEN FAMILIAR EN SECUENCIA (espejo de web/academia.py::_preparar_personas):
  // a lo que YA paga esta cuenta (C.fam.previas) se suman las personas del
  // carrito que van ANTES de esta. Sin sesión no hay descuento aún.
  function ordenPara(par, previos){
    var f = C.fam;
    if(!C.sesion) return 1;
    if(!f){ var d = (C.dtoFam || {})[par === 'hijo' ? 'hijo' : (par === 'familiar' ? 'familiar' : 'yo')]; return d ? d.orden : 1; }
    if(!f.familiar && par !== 'hijo') return 1;
    var n = f.familiar ? f.previas : f.previasHijos;
    (previos || []).forEach(function(it){ if(f.familiar || it.parentesco === 'hijo') n++; });
    return n + 1;
  }
  function pctPara(orden, par){
    var f = C.fam;
    if(!f){ var d = (C.dtoFam || {})[par === 'hijo' ? 'hijo' : (par === 'familiar' ? 'familiar' : 'yo')]; return (C.sesion && d) ? (d.pct || 0) : 0; }
    return orden >= 3 ? (f.h3 || 0) : (orden === 2 ? (f.h2 || 0) : 0);
  }
  function famInfo(){ var par = parentesco(st.quien), o = ordenPara(par, st.carrito); return {orden: o, pct: pctPara(o, par)}; }
  function calcItem(p, modo, n, fam){
    var mesAMes = modo === 'mes' && p.tipo === 'mensual';
    var prep = (C.descuentoPrepago > 0 && n >= C.mesesMinPrepago && !mesAMes) ? C.descuentoPrepago : 0;
    if(mesAMes){ var b = planTotal(p), af = b * fam / 100; return { total: b - af, ahorro: af, ahorroFam: af, ahorroPrep: 0, mesAMes: true, n: n }; }
    var sin = planTotal(p) * n, pct = Math.min(100, prep + fam);
    return { total: sin - sin * pct / 100, ahorro: sin * pct / 100, ahorroFam: sin * fam / 100, ahorroPrep: sin * prep / 100, mesAMes: false, n: n };
  }
  function calc(){ if(!st.plan) return null; return calcItem(st.plan, st.modo, st.n, famInfo().pct); }
  // Recalcula cada persona del carrito con su orden (si se quita una, las demás se reacomodan).
  function totalCarrito(){
    var suma = 0;
    st.carrito.forEach(function(it, i){ it.orden = ordenPara(it.parentesco, st.carrito.slice(0, i)); it.pct = pctPara(it.orden, it.parentesco); it.r = calcItem(it.plan, it.modo, it.n, it.pct); suma += it.r.total; });
    return suma;
  }
  function unidadDe(p, n){ return p.tipo === 'porClase' ? (n === 1 ? 'clase' : 'clases') : (p.tipo === 'prepago' ? (n === 1 ? 'paquete' : 'paquetes') : (n === 1 ? 'mes' : 'meses')); }
  function unidad(p){ return unidadDe(p, st.n); }
  function modoTxt(it){ return it.r.mesAMes ? ('mes a mes · ' + it.n + ' ' + unidadDe(it.plan, it.n)) : (it.n + ' ' + unidadDe(it.plan, it.n) + (it.n > 1 ? ' adelantados' : '')); }
  function yaVaYo(){ return st.carrito.some(function(it){ return it.parentesco === ''; }); }
  function pintar(){
    var p = st.plan, r = calc(), nCar = st.carrito.length, sumaCar = totalCarrito();
    document.querySelectorAll('.tarifa-fila').forEach(function(f){ f.classList.toggle('sel', !!p && f.dataset.plan === p.id); });
    $('planElegido').innerHTML = p ? '<b>' + esc(p.nombre) + '</b> · ' + fmt(p.precioMes) + (p.tipo === 'porClase' ? ' por clase' : ' al mes') : (nCar ? 'Toca «Matricularme» en el tarifario para agregar a otra persona, o paga lo que ya tienes.' : 'Toca «Matricularme» en el tarifario de arriba.');
    var modoBox = $('modo'); if(modoBox) modoBox.style.display = (p && p.tipo === 'mensual') ? '' : 'none';
    if(p && p.tipo !== 'mensual' && st.modo === 'mes') st.modo = 'adelantado';
    $('lblCant').textContent = !p ? '¿Cuántos meses?' : (p.tipo === 'porClase' ? '¿Cuántas clases pagarás?' : (p.tipo === 'prepago' ? '¿Cuántos paquetes de ' + p.meses + ' meses?' : (st.modo === 'mes' ? '¿Por cuántos meses te comprometes?' : '¿Cuántos meses adelantas?')));
    document.querySelectorAll('#modo .chip').forEach(function(b){ b.classList.toggle('sel', b.dataset.modo === st.modo); });
    document.querySelectorAll('#cant .chip').forEach(function(b){ b.classList.toggle('sel', +b.dataset.n === st.n); });
    // "Para mí" solo una vez por carrito.
    var chipYo = document.querySelector('[data-quien="yo"]'); if(chipYo){ chipYo.disabled = yaVaYo(); chipYo.title = yaVaYo() ? 'Tú ya estás en esta matrícula' : ''; }
    $('lblNombre').textContent = st.quien === 'hijo' ? 'Nombre del hijo(a)' : (st.quien === 'familiar' ? 'Nombre de la persona' : 'Nombre del alumno');
    $('edadBox').hidden = st.quien !== 'hijo';
    $('emailPersonaBox').hidden = st.quien !== 'familiar';
    var fi = famInfo(), fb = $('dtoFamBox');
    fb.hidden = !(fi.pct > 0);
    if(fi.pct > 0) fb.textContent = '🎉 Descuento familiar: ' + (fi.orden === 2 ? '2.º' : '3.º o más') + ' de tu familia en esta academia → −' + fi.pct + ' %.';
    var ba = $('btnAgregar'); if(ba){ ba.hidden = !p; ba.disabled = nCar >= MAX_PERSONAS - 1; }
    var np = $('nPersonas'); if(np) np.textContent = (nCar + (p ? 1 : 0)) > 1 ? ((nCar + (p ? 1 : 0)) + ' personas · un solo pago') : '';
    var lineas = '';
    st.carrito.forEach(function(it, i){
      lineas += '<div class="cart-it"><div class="ci-t"><div><b>' + esc(it.nombre) + '</b> <span class="sub">' + quienTxt(it.parentesco) + '</span>' +
        '<div class="sub">' + esc(it.plan.nombre) + ' · ' + modoTxt(it) + (it.pct > 0 ? ' · <span class="ok">−' + it.pct + ' % familiar</span>' : '') + '</div></div>' +
        '<div class="ci-d"><b>' + fmt(it.r.total) + '</b><button type="button" class="quitar" data-i="' + i + '" aria-label="Quitar a ' + esc(it.nombre) + '">✕</button></div></div></div>';
    });
    if(p && r){
      if(nCar) lineas += '<div class="cart-h">Persona ' + (nCar + 1) + ' <span class="sub">(en edición)</span></div>';
      lineas += '<div class="linea"><span>' + esc(p.nombre) + '</span><span>' + fmt(planTotal(p)) + '</span></div>';
      if(!r.mesAMes && st.n > 1) lineas += '<div class="linea"><span>× ' + st.n + ' ' + unidad(p) + '</span><span>' + fmt(planTotal(p) * st.n) + '</span></div>';
      if(r.ahorroPrep > 0) lineas += '<div class="linea"><span>Descuento por adelantar (−' + C.descuentoPrepago + ' %)</span><span>−' + fmt(r.ahorroPrep) + '</span></div>';
      if(r.ahorroFam > 0) lineas += '<div class="linea"><span>Descuento familiar (−' + fi.pct + ' %)</span><span>−' + fmt(r.ahorroFam) + '</span></div>';
    }
    if(!lineas){ $('lineas').innerHTML = '<div class="sub">Sin programa elegido.</div>'; $('tot').textContent = '—'; $('totBarra').textContent = '—'; $('notaModo').textContent = '';
      ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = true; $(id).textContent = 'Elige un programa'; }); return; }
    $('lineas').innerHTML = lineas;
    var total = sumaCar + (r ? r.total : 0), personas = nCar + (p ? 1 : 0);
    $('tot').textContent = fmt(total); $('totBarra').textContent = fmt(total);
    var mesAMesNombres = st.carrito.filter(function(it){ return it.r.mesAMes; }).map(function(it){ return it.nombre; });
    if(r && r.mesAMes) mesAMesNombres.push($('nombre').value.trim() || 'esta persona');
    var nota = '';
    if(personas === 1 && r) nota = r.mesAMes ? ('Hoy pagas 1 mes; los ' + (st.n - 1) + ' siguientes se cobran mes a mes a la misma tarjeta.') : (st.n > 1 ? 'Pago adelantado: quedas al día ' + st.n + ' ' + unidad(p) + '.' : '');
    else if(personas === 1 && nCar) nota = st.carrito[0].r.mesAMes ? 'Hoy pagas 1 mes; los siguientes se cobran mes a mes a la misma tarjeta.' : '';
    else if(mesAMesNombres.length) nota = 'Un solo cobro hoy. Los meses siguientes de ' + mesAMesNombres.join(', ') + ' se cobran mes a mes a la misma tarjeta.';
    else nota = 'Un solo cobro por las ' + personas + ' personas.';
    $('notaModo').textContent = nota;
    ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = false; $(id).textContent = 'Pagar ' + fmt(total) + (personas > 1 ? ' · ' + personas + ' personas' : ''); });
  }
  document.addEventListener('click', function(ev){
    var q = ev.target.closest('.quitar');
    if(q){ st.carrito.splice(+q.dataset.i, 1); if(!yaVaYo() && st.quien === 'yo'){} pintar(); return; }
    var b = ev.target.closest('.elegir'); if(!b) return;
    st.plan = (C.planes || []).filter(function(p){ return p.id === b.dataset.plan; })[0] || null; st.n = 1; pintar();
    var m = $('matricula'); if(m) m.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
  document.querySelectorAll('[data-quien]').forEach(function(b){ b.addEventListener('click', function(){ if(b.disabled) return; st.quien = b.dataset.quien; document.querySelectorAll('[data-quien]').forEach(function(x){ x.classList.toggle('sel', x === b); }); if(st.quien !== 'yo' && $('nombre').value === ((C.sesion || {}).nombre || '')) $('nombre').value = ''; if(st.quien === 'yo' && !$('nombre').value) $('nombre').value = (C.sesion || {}).nombre || ''; pintar(); }); });
  document.querySelectorAll('#modo .chip').forEach(function(b){ b.addEventListener('click', function(){ st.modo = b.dataset.modo; pintar(); }); });
  document.querySelectorAll('#cant .chip').forEach(function(b){ b.addEventListener('click', function(){ st.n = +b.dataset.n; pintar(); }); });
  function mostrarError(m){ var el = $('err'); el.textContent = m; el.style.display = 'block'; el.scrollIntoView({behavior: 'smooth', block: 'center'}); }
  function ocultarError(){ $('err').style.display = 'none'; }
  function cargarFam(){
    // El descuento familiar depende de lo que YA paga esta cuenta: se consulta al entrar.
    fetch('/web/academia/' + encodeURIComponent(C.id) + '/descuento-familiar').then(function(x){ return x.json(); }).then(function(d){ if(d && d.dtoFam){ C.dtoFam = d.dtoFam; C.fam = d.fam || C.fam; pintar(); } }).catch(function(){});
  }
  window.alIniciarSesion = function(u){
    C.sesion = u;
    var lb = $('loginBox'), db = $('datosBox'); if(lb) lb.style.display = 'none'; if(db) db.style.display = '';
    if($('nombre') && !$('nombre').value && st.quien === 'yo') $('nombre').value = u.nombre || '';
    if(db && !$('quien')){ db.insertAdjacentHTML('afterbegin', '<div class="quien" id="quien">' + (u.foto ? '<img src="' + esc(u.foto) + '" alt="">' : '') + '<div><b>' + esc(u.nombre || u.email) + '</b><div class="m">' + esc(u.email) + '</div></div><button type="button" class="btn sec" onclick="cerrarSesion()">Cambiar cuenta</button></div>'); }
    cargarFam();
    pintar();
  };
  // Valida a la persona EN EDICIÓN (la del formulario).
  function validarActual(){
    if(!st.plan) return 'Elige un programa en el tarifario.';
    if(C.login && !C.sesion) return 'Inicia sesión con Google para matricularte.';
    var nombre = $('nombre').value.trim();
    if(nombre.length < 3) return st.quien === 'hijo' ? 'Escribe el nombre de tu hijo(a).' : (st.quien === 'familiar' ? 'Escribe el nombre de la persona.' : 'Escribe el nombre del alumno.');
    if(st.carrito.some(function(it){ return it.nombre.toLowerCase() === nombre.toLowerCase(); })) return nombre + ' ya está en tu matrícula. Cada persona va una sola vez.';
    var ep = st.quien === 'familiar' ? $('emailPersona').value.trim() : '';
    if(ep && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(ep)) return 'Ese correo no se ve bien. Puedes dejarlo vacío.';
    if(ep && C.sesion && ep.toLowerCase() === String(C.sesion.email || '').toLowerCase()) return 'Ese es tu propio correo: elige «Para mí».';
    if($('celular').value.replace(/\D/g, '').length < 8) return 'Escribe un celular de contacto.';
    if(st.quien === 'hijo' && !(+$('edad').value >= 2 && +$('edad').value <= 17)) return 'Indica la edad de tu hijo(a) (2 a 17).';
    return '';
  }
  function itemActual(){
    return { plan: st.plan, parentesco: parentesco(st.quien), modo: st.modo, n: st.n, nombre: $('nombre').value.trim(), celular: $('celular').value.trim(),
             edad: st.quien === 'hijo' ? +$('edad').value : null, email: st.quien === 'familiar' ? $('emailPersona').value.trim() : '' };
  }
  function aReq(it){
    return { plan_id: it.plan.id, nombre: it.nombre, celular: it.celular, es_hijo: it.parentesco === 'hijo', edad: it.parentesco === 'hijo' ? it.edad : null,
             cantidad: it.n, quien: it.parentesco === '' ? 'yo' : it.parentesco, email_persona: it.email || '', mes_a_mes: it.modo === 'mes' };
  }
  // "Guardar a esta persona y agregar otra": pasa la persona en edición al carrito y limpia el formulario.
  function agregar(){
    ocultarError();
    var v = validarActual(); if(v){ mostrarError(v); return; }
    if(st.carrito.length >= MAX_PERSONAS - 1){ mostrarError('Puedes matricular hasta ' + MAX_PERSONAS + ' personas en un solo pago.'); return; }
    var it = itemActual(); st.carrito.push(it);
    st.plan = null; st.n = 1; st.modo = 'adelantado';
    $('nombre').value = ''; $('edad').value = ''; $('emailPersona').value = '';
    if(st.quien === 'yo'){ st.quien = 'hijo'; document.querySelectorAll('[data-quien]').forEach(function(x){ x.classList.toggle('sel', x.dataset.quien === 'hijo'); }); }
    pintar();
    if(window.pcgToast) pcgToast(it.nombre + ' quedó en tu matrícula. Ahora elige el programa de la siguiente persona.');
    var prog = document.querySelector('.prog'); if(prog) prog.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  var ba = $('btnAgregar'); if(ba) ba.addEventListener('click', agregar);
  function pagar(){
    ocultarError();
    if(C.login && !C.sesion){ mostrarError('Inicia sesión con Google para matricularte.'); return; }
    var personas = st.carrito.map(aReq);
    if(st.plan){ var v = validarActual(); if(v){ mostrarError(v); return; } personas.push(aReq(itemActual())); }
    if(!personas.length){ mostrarError('Elige un programa en el tarifario.'); window.scrollTo({top: 0, behavior: 'smooth'}); return; }
    if(!C.pk){ mostrarError('El pago en línea no está disponible por ahora.'); return; }
    var total = totalCarrito() + (st.plan ? calc().total : 0);
    Culqi.publicKey = C.pk;
    Culqi.settings({ title: 'Pichangol', currency: 'PEN', amount: Math.round(total * 100) });
    Culqi.options({ lang: 'es', installments: false,
      paymentMethods: { tarjeta: true, yape: true, bancaMovil: false, agente: false, billetera: false, cuotealo: false },
      style: { logo: '', bannerColor: '#0F1B2D', buttonBackground: '#0E8F67', buttonText: 'Pagar', buttonTextColor: '#FFFFFF' } });
    window.culqi = function(){
      if(Culqi.token){
        var token = Culqi.token.id, medio = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
        Culqi.close();
        ['btnPagar','btnPagarBarra'].forEach(function(id){ $(id).disabled = true; $(id).textContent = 'Confirmando tu pago…'; });
        var url, body;
        if(personas.length === 1){ url = '/web/matricular'; body = Object.assign({academia_id: C.id, token: token, medio: medio}, personas[0]); }
        else { url = '/web/matricular-varios'; body = {academia_id: C.id, token: token, medio: medio, personas: personas}; }
        fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
          .then(function(x){ return x.json(); })
          .then(function(p){
            if(p.ok){ if(p.aviso){ try{ sessionStorage.setItem('pcg_aviso_mat', p.aviso); }catch(e){} } window.location.href = p.url; }
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


class PersonaReq(BaseModel):
    """Una persona del CARRITO DE MATRÍCULA (pedido del director, 26-sep-2026:
    "quiero matricularme con mi esposa en bola verde, mi hijo en bola naranja y
    yo pago todo"). Mismos campos que `MatricularReq` sin el pago."""
    plan_id: str
    nombre: str
    celular: str = ""
    es_hijo: bool = False
    edad: int | None = None
    cantidad: int = 1
    mes_a_mes: bool = False
    quien: str = ""
    email_persona: str = ""


class MatricularVariosReq(BaseModel):
    academia_id: str
    token: str
    medio: str = "tarjeta"
    personas: list[PersonaReq]


def _fam_base(a: dict, email: str) -> dict:
    """Base del descuento familiar para el JS del carrito: cuántas matrículas
    YA paga esta cuenta en la academia (todas y solo hijos), si la academia
    descuenta a toda la familia y los % del 2.º y 3.º. Con eso el navegador
    calcula el orden de CADA persona del carrito en secuencia (la 1.ª del
    carrito sigue a las previas, la 2.ª a la 1.ª…), igual que el servidor."""
    previas = datos.matriculas_de_pagador(a.get("id") or "", email) if email else []
    return {"familiar": a.get("descuentoFamiliar", True) is not False,
            "previas": len(previas), "previasHijos": sum(1 for m in previas if m.get("parentesco") == "hijo"),
            "h2": float(a.get("descuentoHermano2") or 0), "h3": float(a.get("descuentoHermano3") or 0)}


@router.get("/web/academia/{academia_id}/descuento-familiar")
def descuento_familiar(academia_id: str, request: Request = None) -> dict:
    """Orden y % del descuento familiar que le toca a la sesión en esta
    academia según a quién matricule (lo pide el JS al iniciar sesión), más
    la base `fam` con la que el carrito calcula el orden de varias personas."""
    ses = sesion.de_request(request) if sesion.activo() else None
    a = datos.academia(academia_id)
    if not a:
        return {"ok": False, "dtoFam": None}
    email = (ses or {}).get("email") or ""
    return {"ok": True, "dtoFam": _dto_fam_por_quien(a, email), "fam": _fam_base(a, email)}


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


def _quien_txt(parentesco: str) -> str:
    return {"hijo": "tu hijo(a)", "familiar": "la persona"}.get(parentesco, "el alumno")


def _preparar_personas(a: dict, email: str, personas: list[PersonaReq]) -> tuple[list[dict], dict | None]:
    """Valida cada persona del carrito (en orden) y calcula su ORDEN FAMILIAR
    EN SECUENCIA: la 1.ª sigue a las matrículas que YA paga esta cuenta, la
    2.ª cuenta también a la 1.ª, etc. (así la esposa es 2.ª y el hijo 3.º en
    un solo pago, como si se hubieran matriculado uno tras otro). Devuelve
    (items, None) o ([], error) SIN cobrar nada."""
    def err(codigo: str, mensaje: str, i: int) -> tuple[list[dict], dict]:
        pref = f"Persona {i + 1}: " if len(personas) > 1 else ""
        return [], {"ok": False, "error": codigo, "mensaje": pref + mensaje, "persona": i}

    planes = _planes(a)
    previas = datos.matriculas_de_pagador(a.get("id") or "", email) if email else []
    acumuladas = [{"parentesco": m.get("parentesco") or ""} for m in previas]
    items: list[dict] = []
    nombres_vistos: set[str] = set()
    for i, p in enumerate(personas):
        plan = next((x for x in planes if x["id"] == p.plan_id), None)
        if not plan:
            return err("plan", "Ese programa ya no está disponible. Vuelve a elegirlo.", i)
        nombre = re.sub(r"\s+", " ", p.nombre or "").strip()[:80]
        celular = re.sub(r"\D", "", p.celular or "")[:15]
        parentesco = _parentesco(p.quien, p.es_hijo)
        if len(nombre) < 3:
            return err("nombre", f"Escribe el nombre de {_quien_txt(parentesco)}.", i)
        if len(celular) < 8:
            return err("celular", "Escribe un celular de contacto.", i)
        es_hijo = parentesco == "hijo"
        if es_hijo and not (p.edad and 2 <= int(p.edad) <= 17):
            return err("edad", "Indica la edad de tu hijo(a).", i)
        email_persona = (p.email_persona or "").strip().lower()[:120] if parentesco == "familiar" else ""
        if email_persona and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_persona):
            return err("email_persona", "El correo de la persona no se ve bien. Puedes dejarlo vacío.", i)
        if email_persona and email and email_persona == email:
            return err("email_persona", "Ese es tu propio correo: elige «Para mí».", i)
        clave = nombre.lower()
        if clave in nombres_vistos:
            return err("repetida", f"{nombre} ya está en tu matrícula. Cada persona va una sola vez.", i)
        nombres_vistos.add(clave)
        orden = orden_familiar(a, acumuladas, parentesco)
        dto_fam = dto_familiar_pct(a, orden)
        total, ahorro, n = _total(a, plan, p.cantidad, p.mes_a_mes, dto_fam)
        items.append({"plan": plan, "nombre": nombre, "celular": celular, "parentesco": parentesco, "es_hijo": es_hijo,
                      "edad": int(p.edad) if (es_hijo and p.edad) else None, "email_persona": email_persona,
                      "orden": orden, "dto_fam": dto_fam, "total": total, "ahorro": ahorro, "n": n,
                      "mes_a_mes": bool(p.mes_a_mes) and plan["tipo"] == "mensual"})
        acumuladas.append({"parentesco": parentesco})
    return items, None


def _fila_matricula(a: dict, ses: dict | None, email: str, it: dict, charge_id: str, medio: str, ahora: datetime, us: int) -> tuple[str, dict]:
    """La fila de `pichangol_matriculas` EXACTAMENTE como `AppState.matricular`
    (el profe la ve en su app): `Alumno.toJson` + `cuotas` + extras web."""
    plan, n = it["plan"], it["n"]
    alumno_id = f"al_{us}"
    es_menor = it["es_hijo"]
    titular = (ses or {}).get("nombre") or "Apoderado"
    nota_dto = f" (−{it['dto_fam']:.0f}% familiar)" if it["dto_fam"] > 0 else ""
    precio_mes = round(float(plan["precioMes"]) * (1 - it["dto_fam"] / 100.0), 2)  # la cuota queda con el descuento, como el app
    alumno = {"id": alumno_id, "academiaId": a["id"], "nombre": it["nombre"], "whatsapp": "" if es_menor else it["celular"],
              "email": email, "apoderadoNombre": titular.strip() if es_menor else "", "apoderadoWhatsapp": it["celular"] if es_menor else "",
              "esSocioSede": True, "ordenHermano": it["orden"], "sedeId": ""}
    if it["parentesco"]:
        alumno["parentesco"] = it["parentesco"]
    if it["email_persona"]:
        alumno["emailAlumno"] = it["email_persona"]
    if (ses or {}).get("foto") and not it["parentesco"]:  # la foto del titular solo si el alumno ES el titular
        alumno["fotoUrl"] = ses["foto"]
    if es_menor and it["edad"]:
        alumno["edad"] = it["edad"]
    cuotas = []
    if plan["tipo"] == "porClase":
        cuotas.append({"id": f"cu_{us}", "academiaId": a["id"], "alumnoId": alumno_id,
                       "concepto": f"{n} clase{'' if n == 1 else 's'} particular{'' if n == 1 else 'es'} · {plan['nombre']}",
                       "monto": plan["precioMes"] * n, "vencimiento": ahora.isoformat(), "pagada": True, "fechaPago": ahora.isoformat(),
                       "operacionId": charge_id})
    else:
        meses = (1 if plan["tipo"] == "mensual" else plan["meses"]) * n
        pagadas_n = 1 if it["mes_a_mes"] else meses
        for i in range(meses):
            venc = _sumar_meses(ahora, i)
            pagada = i < pagadas_n
            c = {"id": f"cu_{us}_{i}", "academiaId": a["id"], "alumnoId": alumno_id,
                 "concepto": f"{plan['nombre']} · {_mes_nombre(venc)}{nota_dto}", "monto": precio_mes, "vencimiento": venc.isoformat(), "pagada": pagada}
            if pagada:
                c["fechaPago"] = ahora.isoformat()
                c["operacionId"] = charge_id
            if it["mes_a_mes"]:
                c["autoDebito"] = True
            cuotas.append(c)
    # Lo COBRADO hoy (con descuento) se guarda aparte: las cuotas llevan el precio
    # de lista como en el app; el comprobante muestra lo que salió de la tarjeta.
    data = dict(alumno, cuotas=cuotas, canal="web",
                pagoWeb={"monto": float(it["total"]), "ahorro": float(it["ahorro"]), "operacion": charge_id, "dtoFamiliar": float(it["dto_fam"]),
                         "medio": "yape" if medio == "yape" else "tarjeta", "fecha": ahora.isoformat()})
    return alumno_id, data


def _cobrar_y_matricular(a: dict, ses: dict | None, token: str, medio: str, items: list[dict]) -> dict:
    """UN cargo de Culqi por la suma y una matrícula por persona (mismo N.º de
    operación). Contabilidad UNA vez por el total (la comisión del país se
    congela sobre lo cobrado), suscripción mes a mes por persona (la 2.ª en
    adelante reusa la tarjeta de la 1.ª) y un push al dueño."""
    sim, iso = _moneda(a)
    email = (ses["email"] if ses else "").strip().lower()
    total = round(sum(float(it["total"]) for it in items), 2)
    monto_c = sum(int(round(float(it["total"]) * 100)) for it in items)
    if len(items) == 1:
        concepto = f"Matrícula {a['nombre']} · {items[0]['plan']['nombre']}"
    else:
        concepto = f"Matrícula {a['nombre']} · {len(items)} personas"
    cargo = culqi.crear_cargo(token=token.strip(), monto_centimos=monto_c, email=email or "sin-correo@pichangol.app",
                              descripcion=concepto[:80], moneda=iso,
                              metadata={"canal": "web", "academia_id": a["id"], "plan_id": items[0]["plan"]["id"], "personas": len(items)})
    if not cargo.get("ok"):
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada." + (f" ({msg[:80]})" if msg else "")}
    charge_id = str(cargo.get("charge_id") or "")

    ahora = datetime.now()
    base_us = int(time.time() * 1_000_000)
    guardadas: list[tuple[str, dict]] = []
    fallidas: list[str] = []
    for k, it in enumerate(items):
        alumno_id, data = _fila_matricula(a, ses, email, it, charge_id, medio, ahora, base_us + k)
        if datos.insertar_matricula(alumno_id, a["id"], email, data):
            guardadas.append((alumno_id, it))
        else:
            # El cobro ya se hizo: se avisa con el N.º de operación para atenderlo a mano.
            print(f"[matricula-web] cobro {charge_id} sin fila en pichangol_matriculas ({email}, {a['id']}, {it['nombre']})", flush=True)
            fallidas.append(it["nombre"])
    if not guardadas:
        return {"ok": False, "error": "guardar", "mensaje": f"Tu pago se procesó (operación {charge_id}) pero no pudimos registrar la matrícula. "
                                                             f"Escríbenos a {empresa.valores()['empresa_correo']} y la completamos."}
    # Contabilidad: el cobro digital congela la comisión del país y deja el neto "por recibir" de la academia.
    try:
        from pagos.router import MatriculaReq, post_matricula
        post_matricula(MatriculaReq(academia_id=a["id"], monto_soles=float(total), matricula_id=charge_id or guardadas[0][0],
                                    pais=_iso(a).lower(), concepto=concepto))
    except Exception as ex:  # noqa: BLE001 — la contabilidad nunca deshace un cobro
        print(f"[matricula-web] contabilidad falló: {ex}", flush=True)
    try:
        from db.store import stores as _st
        _st.registrar_pago(tipo="cobro_web", monto_centimos=monto_c, moneda=iso, estado="aprobado", culqi_charge_id=charge_id,
                           email=email, medio="yape" if medio == "yape" else "tarjeta", concepto="matricula:" + ",".join(aid for aid, _ in guardadas))
    except Exception:  # noqa: BLE001
        pass
    titular = (ses or {}).get("nombre") or "Apoderado"
    primera_susc = ""
    for alumno_id, it in guardadas:
        if not it["mes_a_mes"]:
            continue
        # Débito automático de los meses siguientes (best-effort, como el app).
        try:
            from pagos.router import SuscripcionAlumnoReq, post_suscripcion_alumno
            precio_mes = round(float(it["plan"]["precioMes"]) * (1 - it["dto_fam"] / 100.0), 2)
            r = post_suscripcion_alumno(SuscripcionAlumnoReq(alumno_id=alumno_id, academia_id=a["id"], email=email, token=token.strip(),
                                                             monto_soles=float(precio_mes), nombre=titular, pais=_iso(a).lower(),
                                                             concepto=f"Matrícula {a['nombre']} · {it['plan']['nombre']}", cobros_restantes=max(0, it["n"] - 1),
                                                             reusar_tarjeta_de=primera_susc))
            if not primera_susc and isinstance(r, dict) and r.get("ok"):
                primera_susc = alumno_id
        except Exception as ex:  # noqa: BLE001
            print(f"[matricula-web] suscripción no creada ({alumno_id}): {ex}", flush=True)
    dueno = (a.get("dueno") or "").strip().lower()
    if dueno:
        try:
            from pagos.router import _aviso_push_usuario
            if len(guardadas) == 1:
                it = guardadas[0][1]
                _aviso_push_usuario(dueno, "Nuevo alumno 🎓", f"{it['nombre']} se matriculó en {a['nombre']} · {it['plan']['nombre']} (pagó {sim} {total:.2f} por la web).", tipo="academia")
            else:
                lista = ", ".join(f"{it['nombre']} ({it['plan']['nombre']})" for _, it in guardadas)
                _aviso_push_usuario(dueno, f"{len(guardadas)} alumnos nuevos 🎓", f"{titular} matriculó a {lista} en {a['nombre']} en un solo pago de {sim} {total:.2f} por la web.", tipo="academia")
        except Exception:  # noqa: BLE001
            pass
    ids = [aid for aid, _ in guardadas]
    print(f"[matricula-web] {email} → {a['nombre']} · {len(ids)} persona(s) · {sim} {total:.2f} · {','.join(ids)}", flush=True)
    url = f"/academia/{a['id']}/matricula/{ids[0]}" if len(ids) == 1 else f"/academia/{a['id']}/matriculas?ids={','.join(ids)}"
    out = {"ok": True, "url": url, "alumno_id": ids[0], "alumno_ids": ids, "charge_id": charge_id, "total": total}
    if fallidas:
        out["aviso"] = (f"Tu pago se procesó (operación {charge_id}) pero no pudimos registrar a {', '.join(fallidas)}. "
                        f"Escríbenos a {empresa.valores()['empresa_correo']} y lo completamos.")
    return out


def _validar_cabecera(request: Request | None, academia_id: str) -> tuple[dict | None, dict | None, dict | None]:
    """(ses, academia, error): sesión (si el login está activo), academia
    existente y pago web disponible en su moneda."""
    ses = sesion.de_request(request) if sesion.activo() else None
    if sesion.activo() and not ses:
        return None, None, {"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para matricularte."}
    a = datos.academia(academia_id)
    if not a or not a.get("nombre"):
        return ses, None, {"ok": False, "error": "academia", "mensaje": "La academia ya no está disponible."}
    a.setdefault("id", academia_id)
    _sim, iso = _moneda(a)
    if not _pago_web_disponible(iso):
        return ses, a, {"ok": False, "error": "moneda", "mensaje": "El pago en línea desde la web está disponible solo en soles. Matricúlate desde la app."}
    return ses, a, None


@router.post("/web/matricular")
def matricular(req: MatricularReq, request: Request = None) -> dict:
    """Cobra con Culqi y registra la matrícula como el app (ver módulo). Una
    sola persona: es el carrito con un solo elemento."""
    ses, a, error = _validar_cabecera(request, req.academia_id)
    if error:
        return error
    persona = PersonaReq(plan_id=req.plan_id, nombre=req.nombre, celular=req.celular, es_hijo=req.es_hijo, edad=req.edad,
                         cantidad=req.cantidad, mes_a_mes=req.mes_a_mes, quien=req.quien, email_persona=req.email_persona)
    items, error = _preparar_personas(a, (ses["email"] if ses else "").strip().lower(), [persona])
    if error:
        return error
    return _cobrar_y_matricular(a, ses, req.token, req.medio, items)


@router.post("/web/matricular-varios")
def matricular_varios(req: MatricularVariosReq, request: Request = None) -> dict:
    """CARRITO DE MATRÍCULA (pedido del director, 26-sep-2026): varias personas
    de la familia (yo, mi pareja, mis hijos), cada una con su programa y su
    forma de pago, en UN solo cobro. El servidor recalcula cada total con el
    descuento familiar en secuencia; si algo no valida, no se cobra nada."""
    ses, a, error = _validar_cabecera(request, req.academia_id)
    if error:
        return error
    if not req.personas:
        return {"ok": False, "error": "vacio", "mensaje": "Agrega al menos una persona a tu matrícula."}
    if len(req.personas) > 8:
        return {"ok": False, "error": "tope", "mensaje": "Puedes matricular hasta 8 personas en un solo pago."}
    items, error = _preparar_personas(a, (ses["email"] if ses else "").strip().lower(), req.personas)
    if error:
        return error
    return _cobrar_y_matricular(a, ses, req.token, req.medio, items)


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


# ── comprobante FAMILIAR (carrito: varias personas en un solo pago) ───────────

@router.get("/academia/{academia_id}/matriculas", response_class=HTMLResponse)
def comprobante_matriculas(request: Request, academia_id: str, ids: str = "") -> HTMLResponse:
    """Comprobante de un pago con VARIAS matrículas (`?ids=al_1,al_2`): lo ve el
    titular que pagó; un familiar con correo propio ve solo la suya."""
    a = datos.academia(academia_id)
    lista = [x.strip() for x in (ids or "").split(",") if x.strip()][:8]
    ms = [m for m in (datos.matricula(x) for x in lista) if m and m.get("academiaId") == academia_id]
    if not a or not ms:
        return _no_encontrada("Matrícula no encontrada")
    ses = sesion.de_request(request)
    yo = (ses or {}).get("email", "").strip().lower()
    pagador = (ms[0].get("email") or "").strip().lower()
    if sesion.activo():
        if not ses or (yo != pagador and any((m.get("email") or "").strip().lower() != pagador for m in ms)):
            volver = f"/academia/{academia_id}/matriculas?ids={e(','.join(lista))}"
            return ui.shell("Matrícula", ("<div class='panel' style='text-align:center;margin-top:24px'><h1>Esta matrícula es privada</h1>"
                                          "<p class='sub'>Inicia sesión con la cuenta de Google con la que pagaste.</p>"
                                          f"<div class='acciones' style='justify-content:center'><a class='btn' href='/entrar?volver={e(volver)}'>Iniciar sesión</a></div></div>"), sesion=ses)
        if yo != pagador:
            mia = next((m for m in ms if (m.get("emailAlumno") or "").strip().lower() == yo), None)
            if not mia:
                return ui.shell("Matrícula", ("<div class='panel' style='text-align:center;margin-top:24px'><h1>Esta matrícula es privada</h1>"
                                              "<p class='sub'>Solo la ve quien la pagó.</p></div>"), sesion=ses)
            return comprobante_matricula(request, academia_id, mia["id"])
    sim, _iso_m = _moneda(a)
    total = ahorro = 0.0
    bloques = ""
    op = ""
    for m in ms:
        cuotas = [c for c in (m.get("cuotas") or []) if isinstance(c, dict)]
        pagadas = [c for c in cuotas if c.get("pagada")]
        pw = m.get("pagoWeb") if isinstance(m.get("pagoWeb"), dict) else {}
        t = float(pw.get("monto") or 0) or sum(float(c.get("monto") or 0) for c in pagadas)
        total += t
        ahorro += float(pw.get("ahorro") or 0)
        op = op or next((c.get("operacionId") for c in pagadas if c.get("operacionId")), "")
        quien = {"hijo": "Mi hijo(a)", "familiar": "Familiar"}.get(m.get("parentesco") or "", "Yo")
        dto = float(pw.get("dtoFamiliar") or 0)
        filas = "".join(
            f"<li>{'✅' if c.get('pagada') else '⏳'} <span>{e(c.get('concepto'))} · {e(sim)} {float(c.get('monto') or 0):.2f}"
            f"{' · pagada' if c.get('pagada') else ' · vence ' + e(str(c.get('vencimiento'))[:10])}</span></li>" for c in cuotas)
        bloques += (f"<div class='cart-it' style='margin-top:12px'><div class='ci-t'><div><b>{e(m.get('nombre'))}</b> <span class='sub'>{quien}</span>"
                    + (f"<div class='sub' style='color:#0B7A55'>🎉 Descuento familiar −{dto:.0f} % ({'2.º' if int(m.get('ordenHermano') or 1) == 2 else '3.º o más'} de tu familia)</div>" if dto > 0 else "")
                    + f"</div><div class='ci-d'><b>{e(sim)} {t:.2f}</b></div></div><ul class='datos' style='margin-top:8px'>{filas}</ul></div>")
    nombres = ", ".join(str(m.get("nombre") or "") for m in ms)
    tel = _wa(a)
    wa = ui.enlace_whatsapp(f"Hola, acabo de matricular a {nombres} en {a['nombre']} por Pichangol.", tel) if tel else ""
    cuerpo = ("<div class='panel' style='margin-top:24px'><div class='check-ok'>✓</div><h1 style='text-align:center'>¡Matrícula familiar registrada!</h1>"
              f"<p class='sub' style='text-align:center'>{len(ms)} personas ya son alumnos de <b>{e(a['nombre'])}</b> con un solo pago. El profe los ve en su lista y tú en la app (Mis academias).</p>"
              "<div class='estado' id='avisoMat' style='display:none;background:#FFF4E5;color:#7A4B00'></div>"
              f"{bloques}"
              + (f"<p class='sub' style='font-size:13px;margin-top:10px'>Descuentos aplicados en total: −{e(sim)} {ahorro:.2f}</p>" if ahorro > 0 else "")
              + f"<div class='total'><span>Pagado hoy</span><span>{e(sim)} {total:.2f}</span></div>"
              + (f"<p class='sub' style='font-size:12.5px'>N.º de operación: {e(op)}</p>" if op else "")
              + "<div class='acciones' style='margin-top:14px'>"
              + (f"<a class='btn' href='{wa}' target='_blank' rel='noopener'>💬 Escribir a la academia</a>" if tel else "")
              + f"<a class='btn sec' href='/academia/{e(academia_id)}'>Ver la academia</a><a class='btn sec' href='{PLAY_URL}'>Abrir en la app</a></div></div>"
              "<script>(function(){try{var a=sessionStorage.getItem('pcg_aviso_mat');if(a){var el=document.getElementById('avisoMat');el.textContent=a;el.style.display='block';sessionStorage.removeItem('pcg_aviso_mat');}}catch(e){}})();</script>")
    return ui.shell("Matrícula registrada", cuerpo, sesion=ses, extra_head=_CSS_CARRITO)
