"""Consentimientos SEPARADOS: 'puntos' (participar en el programa de incentivos)
y 'contacto' (que se le contacte). Negar uno no implica el otro.

Las fotos de verificación física son del ESTABLECIMIENTO (sitio), no documentos
personales: por eso no requieren tratamiento de datos personales del titular, y
NUNCA se piden ni guardan DNI/recibos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class TipoConsentimiento(str, Enum):
    PUNTOS = "puntos"
    CONTACTO = "contacto"


@dataclass
class Consentimiento:
    sujeto_id: str
    tipo: TipoConsentimiento
    otorgado: bool
    fecha: datetime


class ConsentStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, TipoConsentimiento], Consentimiento] = {}

    def registrar(self, sujeto_id: str, tipo: str | TipoConsentimiento,
                  otorgado: bool) -> Consentimiento:
        tipo = TipoConsentimiento(tipo)
        c = Consentimiento(sujeto_id, tipo, otorgado,
                           datetime.now(timezone.utc))
        self._items[(sujeto_id, tipo)] = c
        return c

    def tiene(self, sujeto_id: str, tipo: str | TipoConsentimiento) -> bool:
        c = self._items.get((sujeto_id, TipoConsentimiento(tipo)))
        return bool(c and c.otorgado)


consent_store = ConsentStore()
