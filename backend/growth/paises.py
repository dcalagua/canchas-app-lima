"""País y moneda a partir de coordenadas (espejo de `lib/config/pais.dart`).

Pichangol opera en Perú, Bolivia y Ecuador. Cuando el backend necesita saber en
qué país está una cancha (p. ej. para acreditar el regalo de bienvenida en su
moneda) usa las mismas cajas que el APK: primero los países cuya caja contiene
el punto y, entre ellos, el de centro más cercano. Nunca devuelve None: sin
coordenadas cae a Perú (comportamiento histórico).
"""

from __future__ import annotations

import math

# (lat_min, lat_max, lng_min, lng_max, centro_lat, centro_lng)
_CAJAS = {
    "PE": (-18.4, 0.05, -81.4, -68.6, -9.19, -75.02),
    "BO": (-23.0, -9.6, -69.7, -57.4, -16.29, -63.59),
    "EC": (-5.1, 1.7, -81.1, -75.1, -1.83, -78.18),
}

MONEDA_POR_PAIS = {"PE": "PEN", "EC": "USD", "BO": "BOB"}
SIMBOLO_POR_MONEDA = {"PEN": "S/", "USD": "$", "BOB": "Bs"}


def _dist(caja, lat: float, lng: float) -> float:
    return math.hypot(lat - caja[4], lng - caja[5])


def pais_de_coordenadas(lat: float | None, lng: float | None) -> str:
    """ISO ('PE' | 'BO' | 'EC') del país de la coordenada. Sin coordenadas → PE."""
    if lat is None or lng is None:
        return "PE"
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return "PE"
    dentro = [iso for iso, c in _CAJAS.items()
              if c[0] <= la <= c[1] and c[2] <= ln <= c[3]]
    candidatos = dentro or list(_CAJAS)
    return min(candidatos, key=lambda iso: _dist(_CAJAS[iso], la, ln))


def moneda_de_pais(iso: str) -> str:
    return MONEDA_POR_PAIS.get((iso or "").upper(), "PEN")


def simbolo_de_moneda(moneda: str) -> str:
    return SIMBOLO_POR_MONEDA.get((moneda or "").upper(), "S/")
