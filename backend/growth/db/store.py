"""Capa de datos en memoria (stub) de los 3 subsistemas: PUNTOS/PREMIOS,
SOLICITUDES POR ZONA y VERIFICACION FISICA.

En producción se reemplaza por Postgres/Supabase usando `db/schema.sql` sin
cambiar la interfaz de los servicios. Aquí todo vive en memoria para poder correr
y testear sin base de datos ni servicios externos reales.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def mes_de(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


# === config_incentivos (TODO configurable, nada hardcodeado en la lógica) ======
CONFIG_DEFAULT: dict[str, str] = {
    "puntos_traer_cancha": "500",
    "puntos_invitar_jugador": "100",
    "puntos_pedir_cancha": "50",
    # 100 puntos = S/ 1 de vale
    "equivalencia_puntos_por_sol": "100",
    # tope mensual de premios financiados por Pichangol (en soles)
    "tope_mensual_premios_pichangol_soles": "500",
    # tope de solicitudes que ACREDITAN puntos por usuario/mes
    "tope_solicitudes_usuario_mes": "5",
    # umbral de score de la IA para verificar SIN visita
    "umbral_ia_verificacion": "70",
}


@dataclass
class PuntosMovimiento:
    id: int
    usuario_id: str
    accion: str                 # traer_cancha | invitar_jugador | pedir_cancha
    puntos: int
    estado: str                 # pendiente | liberado | anulado
    ref_tipo: str | None
    ref_id: str | None
    creado_en: datetime
    liberado_en: datetime | None = None


@dataclass
class PremioCanje:
    id: int
    usuario_id: str
    puntos_usados: int
    tipo_premio: str
    vale_id: str
    fuente_financiamiento: str   # pichangol | dueno
    estado: str                  # emitido | aplicado | anulado
    valor_soles: float
    creado_en: datetime


@dataclass
class SolicitudCancha:
    id: int
    usuario_id: str
    nombre_cancha_libre: str
    direccion_texto: str
    lat: float | None
    lng: float | None
    distrito: str
    zona: str                    # lima_norte|lima_sur|lima_este|lima_moderna|callao
    estado: str                  # solicitada|en_captacion|registrada|descartada
    cancha_id: str | None
    creado_en: datetime


@dataclass
class VerificacionFisica:
    id: int
    cancha_id: str
    solicitud_id: int | None
    motivo: str                  # sin_documentos|ia_no_concluyente|alto_valor
    verificador_id: int | None
    estado: str                  # no_requerida|agendada|en_sitio|confirmada|rechazada
    fotos_geo_urls: list[str]
    lat_sitio: float | None
    lng_sitio: float | None
    firma_verificador: str | None
    observaciones: str | None
    metodo: str | None           # documental | en_sitio (interno)
    creado_en: datetime
    cerrada_en: datetime | None = None


@dataclass
class Verificador:
    id: int
    nombre: str
    zona: str
    tipo: str                    # por_encargo | dedicado
    activo: bool = True


@dataclass
class CanchaEstado:
    """Estado relevante de una cancha para estos subsistemas (en producción es la
    fila de `pichangol_canchas`)."""
    cancha_id: str
    verificada: bool = False
    metodo_verificacion: str | None = None   # documental | en_sitio
    verificada_en_persona: bool = False      # PLUS, nunca categoría menor
    primera_reserva: bool = False
    lat_declarada: float | None = None
    lng_declarada: float | None = None
    zona: str | None = None


class Stores:
    def __init__(self) -> None:
        self.config: dict[str, str] = dict(CONFIG_DEFAULT)
        self.movimientos: list[PuntosMovimiento] = []
        self.canjes: list[PremioCanje] = []
        self.solicitudes: list[SolicitudCancha] = []
        self.verificaciones_fisicas: list[VerificacionFisica] = []
        self.verificadores: list[Verificador] = []
        self.canchas: dict[str, CanchaEstado] = {}
        self.visitas_liquidacion: list[dict] = []   # pagos a verificadores (stub)
        self._idem: dict[tuple[str, str], dict] = {}
        self._ids: dict[str, int] = {}

    # --- utilidades ---
    def next_id(self, scope: str) -> int:
        self._ids[scope] = self._ids.get(scope, 0) + 1
        return self._ids[scope]

    def cfg(self, clave: str) -> str:
        return self.config.get(clave, CONFIG_DEFAULT.get(clave, "0"))

    def cfg_int(self, clave: str) -> int:
        try:
            return int(float(self.cfg(clave)))
        except ValueError:
            return 0

    def cancha(self, cancha_id: str) -> CanchaEstado:
        c = self.canchas.get(cancha_id)
        if c is None:
            c = CanchaEstado(cancha_id=cancha_id)
            self.canchas[cancha_id] = c
        return c

    # --- idempotencia ---
    def idem_get(self, scope: str, key: str | None) -> dict | None:
        if not key:
            return None
        return self._idem.get((scope, key))

    def idem_set(self, scope: str, key: str | None, valor: dict) -> dict:
        if key:
            self._idem[(scope, key)] = valor
        return valor

    def reset(self) -> None:
        """Reinicia todo (para tests)."""
        self.__init__()


# Singleton (en producción: repos contra Supabase).
stores = Stores()


def seed_verificadores() -> None:
    """Carga verificadores de ejemplo si no hay (para demo/tests)."""
    if stores.verificadores:
        return
    ejemplos = [
        ("Ana Quispe", "lima_norte", "dedicado"),
        ("Luis Rojas", "lima_sur", "por_encargo"),
        ("Marta Díaz", "lima_este", "por_encargo"),
        ("Jorge León", "lima_moderna", "dedicado"),
        ("Rosa Mamani", "callao", "por_encargo"),
    ]
    for nombre, zona, tipo in ejemplos:
        stores.verificadores.append(Verificador(
            id=stores.next_id("verificador"), nombre=nombre, zona=zona, tipo=tipo))


def como_dict(obj) -> dict:
    """Serializa dataclasses con fechas a ISO."""
    d = asdict(obj)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d
