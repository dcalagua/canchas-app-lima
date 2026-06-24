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
class OtpPropiedad:
    """Código OTP transitorio para validar la PROPIEDAD de una cancha. NO se
    persiste (seguridad): vive en memoria con TTL y se borra al usarse/vencer.
    Sólo guardamos el hash del código, nunca el texto plano."""
    cancha_id: str
    telefono: str                # E.164 sin '+', sólo en memoria
    codigo_hash: str
    expira_en: datetime
    creado_en: datetime
    intentos: int = 0
    enviado_via: str = "stub"     # whatsapp | stub


@dataclass
class ConfirmacionPropiedad:
    """Registro durable de la DECISIÓN de propiedad (auditable). No guarda el
    teléfono completo, sólo enmascarado."""
    id: int
    cancha_id: str
    solicitante_id: str
    metodo: str                  # otp_whatsapp | manual | en_sitio
    estado: str                  # confirmada | pendiente_revision | rechazada
    telefono_enmascarado: str | None
    creado_en: datetime
    decidido_en: datetime | None = None
    nota: str | None = None


@dataclass
class ReclamoPropiedad:
    """Solicitud de reclamo con intervención humana primero (modelo concierge):
    el reclamante pide la cancha → Pichangol (admin) recibe un WhatsApp con el
    código y lo vetea → tras aprobar, el dueño configura → al guardar queda
    pendiente de validación EN SITIO por un motorizado que ingresa el código y
    cuyo GPS debe coincidir con la cancha → recién ahí se activa."""
    id: int
    cancha_id: str
    solicitante_id: str
    nombre_local: str
    codigo: str
    estado: str  # pendiente_triage|aprobado_triage|pendiente_validacion|activada|rechazada
    creado_en: datetime
    telefono_contacto: str | None = None
    lat: float | None = None
    lng: float | None = None
    decidido_en: datetime | None = None
    validado_en: datetime | None = None
    validador: str | None = None
    nota: str | None = None


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
        # OTP de propiedad: transitorio, NO se persiste (uno activo por cancha).
        self.otps: dict[str, OtpPropiedad] = {}
        self.confirmaciones_propiedad: list[ConfirmacionPropiedad] = []
        self.reclamos: list[ReclamoPropiedad] = []
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

    # --- persistencia por snapshot (JSON) -----------------------------------
    def to_state(self) -> dict:
        """Serializa TODO el estado durable a un dict JSON-able."""
        return {
            "ids": dict(self._ids),
            "config": dict(self.config),
            "movimientos": [como_dict(m) for m in self.movimientos],
            "canjes": [como_dict(c) for c in self.canjes],
            "solicitudes": [como_dict(s) for s in self.solicitudes],
            "vfs": [como_dict(v) for v in self.verificaciones_fisicas],
            "verificadores": [como_dict(v) for v in self.verificadores],
            "canchas": {k: como_dict(v) for k, v in self.canchas.items()},
            "visitas_liquidacion": list(self.visitas_liquidacion),
            # OTPs NO se persisten (transitorios/seguridad). Sólo las decisiones.
            "confirmaciones_propiedad": [
                como_dict(c) for c in self.confirmaciones_propiedad
            ],
            "reclamos": [como_dict(r) for r in self.reclamos],
        }

    def load_state(self, data: dict) -> None:
        """Reconstruye el estado desde un snapshot (al arrancar)."""
        self.reset()
        self._ids = {k: int(v) for k, v in (data.get("ids") or {}).items()}
        self.config = {**CONFIG_DEFAULT, **(data.get("config") or {})}
        self.movimientos = [_mov_from(d) for d in data.get("movimientos", [])]
        self.canjes = [_canje_from(d) for d in data.get("canjes", [])]
        self.solicitudes = [_sol_from(d) for d in data.get("solicitudes", [])]
        self.verificaciones_fisicas = [_vf_from(d) for d in data.get("vfs", [])]
        self.verificadores = [Verificador(**d) for d in data.get("verificadores", [])]
        self.canchas = {
            k: CanchaEstado(**v) for k, v in (data.get("canchas") or {}).items()
        }
        self.visitas_liquidacion = list(data.get("visitas_liquidacion") or [])
        self.confirmaciones_propiedad = [
            _conf_from(d) for d in data.get("confirmaciones_propiedad", [])
        ]
        self.reclamos = [_reclamo_from(d) for d in data.get("reclamos", [])]


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


def _dt(s):
    return datetime.fromisoformat(s) if s else None


def _mov_from(d: dict) -> PuntosMovimiento:
    return PuntosMovimiento(
        id=d["id"], usuario_id=d["usuario_id"], accion=d["accion"],
        puntos=d["puntos"], estado=d["estado"], ref_tipo=d.get("ref_tipo"),
        ref_id=d.get("ref_id"), creado_en=_dt(d["creado_en"]),
        liberado_en=_dt(d.get("liberado_en")))


def _canje_from(d: dict) -> PremioCanje:
    return PremioCanje(
        id=d["id"], usuario_id=d["usuario_id"], puntos_usados=d["puntos_usados"],
        tipo_premio=d["tipo_premio"], vale_id=d["vale_id"],
        fuente_financiamiento=d["fuente_financiamiento"], estado=d["estado"],
        valor_soles=d["valor_soles"], creado_en=_dt(d["creado_en"]))


def _sol_from(d: dict) -> SolicitudCancha:
    return SolicitudCancha(
        id=d["id"], usuario_id=d["usuario_id"],
        nombre_cancha_libre=d["nombre_cancha_libre"],
        direccion_texto=d["direccion_texto"], lat=d.get("lat"), lng=d.get("lng"),
        distrito=d["distrito"], zona=d["zona"], estado=d["estado"],
        cancha_id=d.get("cancha_id"), creado_en=_dt(d["creado_en"]))


def _conf_from(d: dict) -> ConfirmacionPropiedad:
    return ConfirmacionPropiedad(
        id=d["id"], cancha_id=d["cancha_id"], solicitante_id=d["solicitante_id"],
        metodo=d["metodo"], estado=d["estado"],
        telefono_enmascarado=d.get("telefono_enmascarado"),
        creado_en=_dt(d["creado_en"]), decidido_en=_dt(d.get("decidido_en")),
        nota=d.get("nota"))


def _reclamo_from(d: dict) -> ReclamoPropiedad:
    return ReclamoPropiedad(
        id=d["id"], cancha_id=d["cancha_id"], solicitante_id=d["solicitante_id"],
        nombre_local=d["nombre_local"], codigo=d["codigo"], estado=d["estado"],
        creado_en=_dt(d["creado_en"]), telefono_contacto=d.get("telefono_contacto"),
        lat=d.get("lat"), lng=d.get("lng"), decidido_en=_dt(d.get("decidido_en")),
        validado_en=_dt(d.get("validado_en")), validador=d.get("validador"),
        nota=d.get("nota"))


def _vf_from(d: dict) -> VerificacionFisica:
    return VerificacionFisica(
        id=d["id"], cancha_id=d["cancha_id"], solicitud_id=d.get("solicitud_id"),
        motivo=d["motivo"], verificador_id=d.get("verificador_id"),
        estado=d["estado"], fotos_geo_urls=list(d.get("fotos_geo_urls") or []),
        lat_sitio=d.get("lat_sitio"), lng_sitio=d.get("lng_sitio"),
        firma_verificador=d.get("firma_verificador"),
        observaciones=d.get("observaciones"), metodo=d.get("metodo"),
        creado_en=_dt(d["creado_en"]), cerrada_en=_dt(d.get("cerrada_en")))
