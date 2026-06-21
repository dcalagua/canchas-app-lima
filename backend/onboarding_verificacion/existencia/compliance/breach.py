"""Protocolo de brecha de seguridad (STUB).

Ante una brecha que afecte datos personales, se debe notificar a la Autoridad
(APDP) y a los titulares afectados dentro del plazo legal. Aquí solo se registra
y se devuelve el protocolo iniciado; en producción dispara el flujo real.
"""

from __future__ import annotations

import logging

# Plazo de notificación de brechas (referencia DS 016-2024-JUS).
PLAZO_NOTIFICACION_HORAS = 48

_logger = logging.getLogger("compliance.breach")


def notificar_brecha(descripcion: str, afectados: int = 0) -> dict:
    """STUB: registra la brecha y deja constancia del plazo de notificación."""
    _logger.critical(
        "BRECHA detectada: %s | afectados=%s | notificar a APDP+titulares <= %sh",
        descripcion, afectados, PLAZO_NOTIFICACION_HORAS)
    # TODO(real): generar incidente, notificar APDP y titulares, registrar evidencia.
    return {
        "protocolo": "iniciado",
        "plazo_horas": PLAZO_NOTIFICACION_HORAS,
        "afectados": afectados,
    }
