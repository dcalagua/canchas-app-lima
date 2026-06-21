"""Contratos de entrada/salida del endpoint de verificación de existencia.

La respuesta NO incluye datos personales: solo estado del negocio, similitudes
(números), distancias y el desglose explicable del score.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExistenciaRequest(BaseModel):
    cancha_id: str = Field(..., description="ID de la cancha a verificar")
    ruc: str | None = Field(None, description="RUC del negocio (opcional)")
    razon_social: str | None = Field(None, description="Razón social declarada")
    direccion: str = Field(..., description="Dirección declarada del local")
    lat: float | None = None
    lng: float | None = None


class SunatInfo(BaseModel):
    consultado: bool
    existe: bool
    estado: str | None = None        # ACTIVO | BAJA DE OFICIO | ...
    condicion: str | None = None     # HABIDO | NO HABIDO
    domicilio_coincide: float | None = None  # similitud [0..1], NO la dirección
    establecimientos_anexos: int = 0
    fuente: str = "n/a"


class MapsInfo(BaseModel):
    consultado: bool
    encontrado: bool
    operativo: bool
    distancia_m: float | None = None
    fuente: str = "n/a"


class Evidencia(BaseModel):
    factor: str
    peso: float
    valor: float | None
    aporte: float
    disponible: bool
    detalle: str


class ExistenciaResponse(BaseModel):
    cancha_id: str
    score_existencia: int
    nivel: str
    aprobado: bool
    justificacion: str
    sunat: SunatInfo
    maps: MapsInfo
    social: dict
    evidencias: list[Evidencia]
    fecha: str
    sin_datos_personales: bool = True


class ConsentimientoRequest(BaseModel):
    sujeto_id: str
    tipo: str = Field(..., description="verificacion | marketing | llamada")
    otorgado: bool
    canal: str = "app"
