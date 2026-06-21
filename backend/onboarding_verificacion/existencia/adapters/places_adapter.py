"""Adaptador Google Places: ubicación, operatividad y distancia a lo declarado.

Proveedor configurable por `PLACES_PROVIDER` (google | stub). STUB por ahora: no
llama a Google. Si llegan lat/lng declaradas, simula un negocio a ~80 m para
ejercitar el cálculo de distancia.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
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

    @staticmethod
    def no_consultado(fuente: str = "google") -> "PlacesResultado":
        return PlacesResultado(False, False, False, None, None, None, None, fuente)


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
    """Adaptador REAL de Google Places (API New, `places:searchText`).

    Busca el negocio por la dirección declarada (sesgado a la coordenada si la
    hay), y devuelve si está operativo y a qué distancia de lo declarado. La key
    se lee de `GOOGLE_PLACES_API_KEY` (puede reusarse la misma del mapa/app, con
    restricción de aplicación = Ninguna para que funcione como web service).

    Fail-safe: sin key o ante error → `no_consultado` (el scoring excluye maps).
    """

    _URL = "https://places.googleapis.com/v1/places:searchText"

    def __init__(self, api_key: str | None = None, timeout: float = 8.0) -> None:
        self._key = api_key or os.getenv("GOOGLE_PLACES_API_KEY", "")
        self._timeout = timeout

    def buscar(self, direccion: str, lat: float | None = None,
               lng: float | None = None) -> PlacesResultado:
        if not self._key:
            return PlacesResultado.no_consultado("google-sin-key")

        body: dict = {
            "textQuery": direccion,
            "languageCode": "es",
            "regionCode": "PE",
            "maxResultCount": 1,
        }
        if lat is not None and lng is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": 3000,
                }
            }
        req = urllib.request.Request(
            self._URL, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self._key,
                "X-Goog-FieldMask": ("places.id,places.location,"
                                     "places.formattedAddress,"
                                     "places.businessStatus"),
            })
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return PlacesResultado.no_consultado("google")

        places = payload.get("places") or []
        if not places:
            return PlacesResultado(True, False, False, None, None, None, None,
                                   "google")
        p = places[0]
        loc = p.get("location") or {}
        biz_lat = loc.get("latitude")
        biz_lng = loc.get("longitude")
        estado = (p.get("businessStatus") or "").upper()
        # OPERATIONAL o ausente → operativo; CLOSED_* → no operativo.
        operativo = estado not in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY")
        dist = None
        if (lat is not None and lng is not None
                and biz_lat is not None and biz_lng is not None):
            dist = haversine_m(lat, lng, biz_lat, biz_lng)
        return PlacesResultado(
            consultado=True, encontrado=True, operativo=operativo,
            lat=biz_lat, lng=biz_lng,
            direccion_formateada=p.get("formattedAddress"),
            distancia_m=dist, fuente="google")


def get_places_adapter() -> PlacesAdapter:
    proveedor = os.getenv("PLACES_PROVIDER", "stub").lower()
    if proveedor == "google":
        return GooglePlacesAdapter()
    return StubPlacesAdapter()
