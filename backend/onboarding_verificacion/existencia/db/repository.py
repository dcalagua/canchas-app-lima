"""Repositorio de RESULTADOS de verificación (stub en memoria).

Guarda únicamente el resultado (bool + score + fecha) y evidencias NO personales.
En producción se reemplaza por escritura a la tabla `verificaciones` (schema.sql)
sin cambiar la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from compliance.retention import TTL_RESULTADO


@dataclass
class ResultadoVerificacion:
    cancha_id: str
    score_existencia: int
    aprobado: bool
    nivel: str
    fecha: datetime
    evidencias: list[dict] = field(default_factory=list)  # solo factores/puntajes
    fuente_sunat: str | None = None
    eliminar_despues: datetime | None = None


class VerificacionesRepo:
    """Stub en memoria. NO almacena datos personales (lo garantiza el servicio)."""

    def __init__(self) -> None:
        self._items: list[ResultadoVerificacion] = []

    def guardar(self, r: ResultadoVerificacion) -> ResultadoVerificacion:
        if r.eliminar_despues is None:
            r.eliminar_despues = r.fecha + TTL_RESULTADO
        self._items.append(r)
        return r

    def ultimas(self, cancha_id: str) -> list[ResultadoVerificacion]:
        return [x for x in self._items if x.cancha_id == cancha_id]


# Singleton stub.
verificaciones_repo = VerificacionesRepo()


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)
