"""Contratos de entrada de la API (Pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- A. Puntos / premios ---
class AcreditarRequest(BaseModel):
    usuario_id: str
    accion: str = Field(..., description="traer_cancha | invitar_jugador | pedir_cancha")
    ref_tipo: str | None = None
    ref_id: str | None = None


class CanjearRequest(BaseModel):
    usuario_id: str
    puntos_usados: int
    tipo_premio: str = "descuento_reserva"
    fuente_financiamiento: str = "pichangol"  # pichangol | dueno


class PrimeraReservaRequest(BaseModel):
    cancha_id: str


# --- B. Solicitudes por zona ---
class SolicitudRequest(BaseModel):
    usuario_id: str
    nombre_cancha_libre: str
    direccion_texto: str
    distrito: str | None = None
    zona: str | None = None
    lat: float | None = None
    lng: float | None = None


class RegistrarSolicitudRequest(BaseModel):
    cancha_id: str


# --- C. Verificación física ---
class EvaluarRequest(BaseModel):
    cancha_id: str
    direccion: str
    ruc: str | None = None
    lat: float | None = None
    lng: float | None = None
    zona: str | None = None
    distrito: str | None = None
    solicitud_id: int | None = None
    motivo: str = "sin_documentos"  # sin_documentos|ia_no_concluyente|alto_valor


class CapturaRequest(BaseModel):
    fotos_geo_urls: list[str] = Field(default_factory=list)
    lat_sitio: float
    lng_sitio: float
    firma_verificador: str
    observaciones: str | None = None


# --- Transversal ---
class ConsentimientoRequest(BaseModel):
    sujeto_id: str
    tipo: str  # puntos | contacto
    otorgado: bool


class ConfigRequest(BaseModel):
    valor: str
