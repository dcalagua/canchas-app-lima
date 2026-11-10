"""Piezas COMPARTIDAS de la web pública (antes al inicio de `web/router.py`):
constantes (Play, días de reserva, deportes, países, extras, amenidades),
país y moneda de una cancha, firma HMAC de un bloque asegurado, qué pasarela
cobra en cada moneda, fotos (propias / de Google / OSM), galería, "Cómo
llegar" y la página 404 de "Cancha no disponible".

`web/router.py` las re-exporta: el resto del código sigue usando
`web.router._pais_de`, `PLAY_URL`, etc.
"""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import quote

from fastapi.responses import HTMLResponse

import config
from paises import pais_de_coordenadas, moneda_de_pais, simbolo_de_moneda
from web import catalogos, miniaturas, pago_hospedado, sesion, ui
from web.ui import e
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)


PLAY_URL = "https://play.google.com/store/apps/details?id=pe.ebim.pichangol"
DIAS_ADELANTE = 30
DIAS_TIRA = 14
MAX_SLOTS = 4
DEPORTES = {"futbol": ("Fútbol", "⚽"), "tenis": ("Tenis", "🎾"), "padel": ("Pádel", "🏓"),
            "pickleball": ("Pickleball", "🥒"), "voley": ("Vóley", "🏐"), "basquet": ("Básquet", "🏀"),
            "futsal": ("Futsal", "⚽")}
CIUDAD_DEFECTO = {"PE": (-12.046, -77.043), "EC": (-2.17, -79.92), "BO": (-16.5, -68.15)}
NOMBRE_PAIS = {"PE": "Perú", "EC": "Ecuador", "BO": "Bolivia"}
EXTRAS_NOMBRE = {"arbitro": "Árbitro", "pelotero": "Pelotero (recoge pelotas)",
                 "pelota": "Alquiler de pelota", "pecheras": "Petos / pecheras",
                 "hidratacion": "Hidratación"}
# Claves de amenidades = las del APP (`catalogos.AMENIDADES`; así los chips y
# el modal de filtros reconocen lo que guardan los dueños). Se conservan las
# claves viejas de la web para datos que las tuvieran.
AMENIDAD_NOMBRE = {**{k: v[0] for k, v in catalogos.AMENIDADES.items()},
                   "estacionamiento": "Estacionamiento", "vestuarios": "Vestuarios",
                   "iluminacion": "Iluminación", "techada": "Techada", "tribuna": "Tribuna", "seguridad": "Seguridad"}


# ── helpers ───────────────────────────────────────────────────────────────────

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


def _deporte(clave: str) -> tuple[str, str]:
    k = (clave or "").lower()
    return DEPORTES.get(k, ((clave or "Deporte").capitalize(), "🏟️"))


def _deportes_de(c: dict) -> list[str]:
    lst = [str(x).lower() for x in (c.get("deportes") or []) if x]
    p = (c.get("deporte") or "").lower()
    if p and p not in lst:
        lst.insert(0, p)
    return lst or ([p] if p else [])


def _zona(c: dict) -> str:
    """Zona visible = el BARRIO real (reverse-geocode), espejo de
    `Cancha.zonaMostrable` del app. El `distrito` es un enum legado de Lima
    (sanBorja/surco/laMolina, referencial) que NO se muestra: salía "Sanborja"
    en canchas de cualquier ciudad (pedido del director, sep-2026)."""
    return (c.get("barrio") or "").strip()


def _secreto() -> bytes:
    # Misma clave que las sesiones web (sin secretos configurados, una
    # aleatoria del proceso: nunca una constante conocida).
    return sesion._secreto()


def _firma(ids: list[str]) -> str:
    return hmac.new(_secreto(), "|".join(sorted(ids)).encode(), hashlib.sha256).hexdigest()[:32]


def _firma_ok(ids: list[str], firma: str) -> bool:
    return bool(ids) and hmac.compare_digest(_firma(ids), (firma or "")[:32])


def _pago_web_disponible(iso: str) -> bool:
    """¿La web puede cobrar en esa moneda? Soles: Culqi en la misma página (con
    llave pública cargada, aunque sea de prueba, el formulario se muestra: así
    lo revisa la pasarela). Dólares / bolivianos: la pasarela HOSPEDADA del
    país (`web/pago_hospedado.py`: Ecuador por la fachada `pasarela_ec`,
    Bolivia Libélula; en dev/QAS sin llaves, la simulada)."""
    if iso == "PEN":
        return bool(config.CULQI_PUBLIC_KEY)
    return bool(pago_hospedado.pasarela_para(iso))


def _pasarela_web(iso: str) -> str:
    """'culqi' en soles; la clave de la pasarela hospedada en $ / Bs."""
    return "culqi" if iso == "PEN" else pago_hospedado.pasarela_para(iso)


def _fotos(c: dict) -> list[str]:
    # FOTOS PROPIAS DE LOS LOCALES (`propiedad/fotos_locales.py`): un local que
    # ya tiene sus fotos (`ok`) o cuyo plazo venció (`vencido`) muestra SOLO
    # sus fotos propias, nunca las de Google guardadas en la fila.
    from propiedad import fotos_locales as _fl
    solo_propias = _fl.fotos_para(c)
    if solo_propias is not None:
        return solo_propias
    return _fotos_crudas(c)


def _fotos_crudas(c: dict) -> list[str]:
    """Portada + galería TAL CUAL están en la fila (el editor del dueño)."""
    out = []
    for u in [c.get("foto_url")] + list(c.get("fotos") or []):
        u = str(u or "").strip()
        if u.startswith("http") and u not in out:
            out.append(u)
    return out


def _foto_card(c: dict) -> str:
    fs = _fotos(c)
    if fs:
        return miniaturas.img(fs[0], c.get("nombre") or "")
    return f"<div class='sinfoto'>{_deporte(c.get('deporte'))[1]}</div>"


def _sin_google(c: dict) -> bool:
    """¿El local de la cancha ya no usa fotos de Google? (ok / vencido)."""
    from propiedad import fotos_locales as _fl
    est = _fl.estado_de_cancha(c)
    return bool(est and est.get("sin_google"))


def _es_osm(lugar_id) -> bool:
    """Lugar de OpenStreetMap (`osm_n123`; el APK puede mandar `gp_osm_…`)."""
    i = str(lugar_id or "")
    return i.startswith("osm_") or i.startswith("gp_osm_")


def _galeria(c: dict) -> str:
    fs = _fotos(c)
    if not fs and _es_osm(c.get("id")):
        # Lugar de OpenStreetMap: nunca se le pide foto a Google.
        return f"<div class='galeria una' id='galeria'><div class='sinfoto principal'>{_deporte(c.get('deporte'))[1]}</div></div>"
    if not fs and _sin_google(c):
        # Local cuyo plazo para subir fotos propias venció: placeholder, sin
        # pedirle nada a Google (`propiedad/fotos_locales.py`).
        return f"<div class='galeria una' id='galeria'><div class='sinfoto principal'>{_deporte(c.get('deporte'))[1]}</div></div>"
    if not fs:
        # Sin fotos propias: la galería arranca con el placeholder y un script
        # pide a /web/foto la PRIMERA FOTO de Google del lugar (como el app).
        q = (f"id={quote(str(c.get('id') or ''))}&nombre={quote(str(c.get('nombre') or ''))}"
             f"&club={quote(str(c.get('club') or ''))}&lat={c.get('lat') or 0}&lng={c.get('lng') or 0}")
        return (f"<div class='galeria una' id='galeria'><div class='sinfoto principal'>{_deporte(c.get('deporte'))[1]}</div></div>"
                "<script>(function(){fetch('/web/foto?" + q + "').then(function(r){return r.json();}).then(function(j){"
                "var f=(j&&j.fotos)||[];if(!f.length)return;var g=document.getElementById('galeria');if(!g)return;"
                "var esc=function(s){return String(s).replace(/[&<>\"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c];});};"
                "var g9=(j&&j.minis_g)||[],m=(j&&j.minis)||[];"
                "var im=function(i,cl,sz,ms){var x=ms[i]||{};return '<img'+(cl?' class='+cl:'')+' src=\"'+esc(x.s||f[i])+'\"'+(x.ss?' srcset=\"'+esc(x.ss)+'\" sizes=\"'+sz+'\"':'')+' alt=\"\" decoding=async'+(cl?'':' loading=lazy')+'>';};"
                "var P='" + miniaturas.SIZES_PRINCIPAL + "',S='" + miniaturas.SIZES_CHICA + "';"
                "if(f.length===1){g.innerHTML=im(0,'principal',P,g9);return;}"
                "g.className='galeria';g.innerHTML=im(0,'principal',P,g9)+f.slice(1,3).map(function(u,i){return im(i+1,'',S,m);}).join('');"
                "}).catch(function(){});})();</script>")
    principal = miniaturas.img(fs[0], c.get("nombre") or "", w=960, sizes=miniaturas.SIZES_PRINCIPAL,
                               clase="principal", prioridad=True)
    if len(fs) == 1:
        return f"<div class='galeria una'>{principal}</div>"
    partes = [principal]
    for u in fs[1:3]:
        partes.append(miniaturas.img(u, sizes=miniaturas.SIZES_CHICA))
    while len(partes) < 3 and len(fs) > 1:
        partes.append(f"<div class='sinfoto'>{_deporte(c.get('deporte'))[1]}</div>")
    return f"<div class='galeria'>{''.join(partes)}</div>"


def _maps(c: dict) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={c.get('lat')},{c.get('lng')}"


def _no_encontrada(que: str = "Cancha no disponible") -> HTMLResponse:
    r = ui.shell(que, (f"<div class='panel' style='text-align:center;margin-top:24px'><h1>{e(que)}</h1>"
                          "<p class='sub'>Puede que el enlace sea viejo o que el local haya dejado de "
                          f"publicar en {MARCA}.</p><div class='acciones' style='justify-content:center'>"
                          "<a class='btn' href='/canchas'>Ver canchas disponibles</a></div></div>"))
    r.status_code = 404   # nunca un "soft 404" (Google lo indexaría como página válida)
    return r
