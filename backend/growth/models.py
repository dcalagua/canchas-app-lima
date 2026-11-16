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


class AcreditarReservaRequest(BaseModel):
    """Fidelidad: puntos por una reserva efectivamente pagada."""
    usuario_id: str
    monto: float
    moneda: str = "S/"  # S/ | Bs | $ (define el factor de puntos)
    reserva_id: str


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


# --- D. Verificación de PROPIEDAD (OTP WhatsApp + manual) ---
class OtpSolicitarRequest(BaseModel):
    cancha_id: str
    telefono: str  # del local; se normaliza a E.164 (Perú por defecto)


class OtpConfirmarRequest(BaseModel):
    cancha_id: str
    codigo: str
    solicitante_id: str
    # Teléfono público del local (Places/redes), si se conoce, para contrastar.
    telefono_publico: str | None = None


class AprobarManualRequest(BaseModel):
    cancha_id: str
    solicitante_id: str
    aprobado: bool = True
    revisor: str | None = None
    nota: str | None = None


# --- Reclamo de propiedad (concierge + validación en sitio) ---
class ReclamoRequest(BaseModel):
    cancha_id: str
    solicitante_id: str            # correo del reclamante (login; obligatorio)
    solicitante_nombre: str = ""   # nombre del reclamante (de su cuenta Google)
    nombre_local: str
    # Prueba de propiedad (opcional): foto (fachada/cartel/recibo) + nota libre
    # que el reclamante deja para acelerar el triage del operador.
    foto_evidencia_url: str = ""
    nota_reclamante: str = ""
    telefono_contacto: str | None = None
    dni: str | None = None
    ruc: str | None = None
    relacion: str | None = None  # dueño | concesionario | arrendatario
    lat: float | None = None     # ubicación de la cancha (pin / Google)
    lng: float | None = None
    # GPS del dispositivo desde donde se envía la solicitud (para contrastar que
    # el reclamante está en el lugar).
    solicitante_lat: float | None = None
    solicitante_lng: float | None = None


class TriageRequest(BaseModel):
    aprobado: bool = True
    revisor: str | None = None
    nota: str | None = None


class ValidarReclamoRequest(BaseModel):
    codigo: str
    lat: float
    lng: float
    validador: str | None = None
    fotos_urls: list[str] = Field(default_factory=list)


# --- E. Convocatorias ("pichangas" programadas con cupos + 3 modos) ---
class CrearConvocatoriaRequest(BaseModel):
    club_id: str
    titulo: str
    deporte: str = "futbol"
    cupos: int = 14
    categoria: str | None = None
    fecha_partido: str | None = None    # ISO/texto del partido (display)
    apertura: str | None = None         # ISO; si vacío, abre al crear
    cierre: str | None = None           # ISO; si vacío, no cierra por tiempo
    modo_asignacion: str | None = None  # orden_llegada|sorteo|equidad (None=global)
    creado_por: str = ""


class InscribirRequest(BaseModel):
    socio_id: str
    socio_nombre: str = ""


class CancelarInscripcionRequest(BaseModel):
    socio_id: str


class CerrarConvocatoriaRequest(BaseModel):
    semilla: str | None = None          # opcional; fija el sorteo


class AsistenciaItem(BaseModel):
    socio_id: str
    asistio: bool


class AsistenciaRequest(BaseModel):
    asistencias: list[AsistenciaItem] = Field(default_factory=list)


class ModoAsignacionRequest(BaseModel):
    modo: str                           # orden_llegada|sorteo|equidad


# --- Transversal ---
class ConsentimientoRequest(BaseModel):
    sujeto_id: str
    tipo: str  # puntos | contacto
    otorgado: bool


class ConfigRequest(BaseModel):
    valor: str
