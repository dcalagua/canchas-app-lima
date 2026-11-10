"""Lugares y fotos: `GET /web/lugares` (buscar un local en Google por
nombre) y `GET /web/foto` (PRIMERA FOTO de una cancha sin fotos propias, con
sus miniaturas).

Movido tal cual desde `web/router.py`, que lo re-exporta.
"""

from __future__ import annotations

from fastapi import APIRouter, Header

import config
from paises import pais_de_coordenadas
from web import datos, descubrir, miniaturas
from web.comun import _deporte, _es_osm, _fotos, _sin_google

router = APIRouter()


@router.get("/web/lugares")
def lugares_web(q: str = "", lat: float | None = None, lng: float | None = None) -> dict:
    """Busca un local en Google por NOMBRE (para "Pon tu cancha"). Sin
    `PLACES_API_KEY` responde `disponible:false` y el formulario esconde la caja."""
    if not config.PLACES_API_KEY:
        return {"ok": True, "disponible": False, "lugares": []}
    region = pais_de_coordenadas(lat, lng) if lat is not None else "PE"
    lugares = descubrir.buscar_lugares(q, lat, lng, region=region)
    for l in lugares:  # etiqueta + emoji como las descubiertas (el explorador reusa la tarjeta)
        l["deporte_nombre"], l["emoji"] = _deporte(l["deporte"]) if l.get("deporte") else ("Cancha", "🏟️")
    return {"ok": True, "disponible": True, "lugares": lugares}


def _minis(fotos: list[str]) -> dict:
    """Miniaturas alineadas con `fotos` para el JS que las pinta: `minis`
    (tarjetas, 480 px) y `minis_g` (foto principal de la ficha, 960 px). El APK
    sigue leyendo solo `fotos` (las URLs de siempre)."""
    return {"minis": miniaturas.para_js(fotos), "minis_g": miniaturas.para_js(fotos[:1], 960)}


@router.get("/web/foto")
def foto_web(id: str = "", nombre: str = "", club: str = "", lat: float = 0.0, lng: float = 0.0,
             refrescar: int = 0, x_admin_token: str | None = Header(default=None)) -> dict:
    """PRIMERA FOTO de una cancha sin fotos propias (regla del director: la web
    muestra siempre la primera foto, como el app). Para una cancha registrada
    (`id`) usa sus fotos si las tiene; si no, resuelve las de Google en su
    ubicación (mismo criterio que `enriquecerSembradas` del APK). Para una
    descubierta (`gp_…`) o cualquier lugar, por nombre + coordenadas.
    Un lugar de OpenStreetMap (`osm_…`) NUNCA pide nada a Google: sin foto
    (placeholder del deporte), sin tocar la base ni la Edge."""
    if _es_osm(id):
        return {"ok": True, "fotos": [], "origen": "osm"}
    c = datos.cancha(id) if id and not id.startswith("gp_") else None
    if c:
        propias = _fotos(c)
        if propias:
            return {"ok": True, "fotos": propias[:5], "origen": "propias", **_minis(propias[:5])}
        if _sin_google(c):
            # FOTOS PROPIAS DE LOS LOCALES: plazo vencido sin fotos → nunca
            # se le pide a Google (ahorro; placeholder del deporte).
            return {"ok": True, "fotos": [], "origen": "sin_google"}
        nombre, club = c.get("nombre") or nombre, c.get("club") or club
        lat, lng = c.get("lat") or lat, c.get("lng") or lng
    if not (nombre or club) or (not lat and not lng):
        return {"ok": False, "fotos": []}
    region = pais_de_coordenadas(lat, lng)
    place_id = id[3:] if id.startswith("gp_") else ""
    # `refrescar=1` + token de admin: salta cachés y cosecha (diagnóstico).
    # Solo con la CABECERA X-Admin-Token (sesión de la torre o token clásico); el
    # token ya no se acepta en la URL, donde queda en logs y en el historial.
    from propiedad import admin_auth as _aa
    forzar = bool(refrescar) and _aa.token_admin_valido(x_admin_token)
    fotos = descubrir.fotos_de_lugar(nombre, club, lat, lng, region=region, place_id=place_id,
                                     cancha_id="" if place_id else id, forzar=forzar)
    return {"ok": True, "fotos": fotos, "origen": "google" if fotos else "", **_minis(fotos)}
