"""Logging de acceso por rol (trazabilidad / accountability).

Registra quién (rol) accede a qué recurso y con qué acción. STUB: usa el logger
estándar; en producción se envía a un almacén de auditoría append-only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

_logger = logging.getLogger("compliance.access")


def log_acceso(rol: str, recurso: str, accion: str,
               sujeto_id: str | None = None) -> None:
    _logger.info(
        "acceso rol=%s accion=%s recurso=%s sujeto=%s ts=%s",
        rol, accion, recurso, sujeto_id or "-",
        datetime.now(timezone.utc).isoformat())
