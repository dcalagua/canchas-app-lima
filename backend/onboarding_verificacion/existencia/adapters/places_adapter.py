"""Adaptador Google Places: ubicación, operatividad y distancia a lo declarado.

Proveedor configurable por `PLACES_PROVIDER` (google | stub). STUB por ahora: no
llama a Google. Si llegan lat/lng declaradas, simula un negocio a ~80 m para
ejercitar el cálculo de distancia.
"""

from __future__ import annotations

import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PlacesResultado:
    consultado: bool
    encontrado: bool
    operativo: bool                 # business_status == OPERATIONAL
    lat: float | None
    lng: float | None
    direccion_formateada: str | None
    distancia_m: float | None       # distancia a la ubicación declarada (si la hay)
    fuente: str = "stub"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en metros entre dos coordenadas."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return round(2 * r * math.asin(min(1.0, math.sqrt(a))), 1)


class PlacesAdapter(ABC):
    @abstractmethod
    def buscar(self, direccion: str, lat: float | None = None,
               lng: float | None = None) -> PlacesResultado:
        ...


class StubPlacesAdapter(PlacesAdapter):
    """STUB determinista. No llama a Google Places."""

    def buscar(self, direccion: str, lat: float | None = None,
               lng: float | None = None) -> PlacesResultado:
        if lat is not None and lng is not None:
            biz_lat, biz_lng = lat + 0.0006, lng - 0.0004  # ~80 m
            dist = haversine_m(lat, lng, biz_lat, biz_lng)
        else:
            biz_lat = biz_lng = None
            dist = None
        return PlacesResultado(
            consultado=True, encontrado=True, operativo=True,
            lat=biz_lat, lng=biz_lng, direccion_formateada=direccion,
            distancia_m=dist, fuente="stub")


class GooglePlacesAdapter(PlacesAdapter):
    """STUB del proveedor Google Places (API New). Hoy delega en el stub."""

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or os.getenv("GOOGLE_PLACES_API_KEY", "")
        self._stub = StubPlacesAdapter()

    def buscar(self, direccion: str, lat: float | None = None,
               lng: float | None = None) -> PlacesResultado:
        # TODO(real): places:searchText + Place Details (businessStatus, location).
        res = self._stub.buscar(direccion, lat, lng)
        res.fuente = "google-stub"
        return res


def get_places_adapter() -> PlacesAdapter:
    proveedor = os.getenv("PLACES_PROVIDER", "stub").lower()
    if proveedor == "google":
        return GooglePlacesAdapter()
    return StubPlacesAdapter()
