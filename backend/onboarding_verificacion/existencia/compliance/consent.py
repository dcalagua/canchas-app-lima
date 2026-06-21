"""Consentimientos (verificacion | marketing | llamada).

Registra el otorgamiento/denegación de consentimiento por sujeto y tipo, y
permite BLOQUEAR el recontacto (marketing/llamada) si el titular lo denegó o si
el consentimiento venció. Stub en memoria; en producción → tabla
`consentimientos` (ver db/schema.sql).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class TipoConsentimiento(str, Enum):
    VERIFICACION = "verificacion"
    MARKETING = "marketing"
    LLAMADA = "llamada"


@dataclass
class Consentimiento:
    sujeto_id: str
    tipo: TipoConsentimiento
    otorgado: bool
    fecha: datetime
    canal: str
    base_legal: str
    vigencia_hasta: datetime | None


class ConsentStore:
    """Stub en memoria del registro de consentimientos."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, TipoConsentimiento], Consentimiento] = {}

    def registrar(self, sujeto_id: str, tipo: str | TipoConsentimiento,
                  otorgado: bool, canal: str = "app",
                  base_legal: str = "Art. 5 Ley 29733 (consentimiento informado)",
                  meses_vigencia: int = 24) -> Consentimiento:
        tipo = TipoConsentimiento(tipo)
        ahora = datetime.now(timezone.utc)
        vigencia = ahora + timedelta(days=30 * meses_vigencia) if otorgado else None
        c = Consentimiento(sujeto_id, tipo, otorgado, ahora, canal,
                           base_legal, vigencia)
        self._items[(sujeto_id, tipo)] = c
        return c

    def estado(self, sujeto_id: str,
               tipo: str | TipoConsentimiento) -> Consentimiento | None:
        return self._items.get((sujeto_id, TipoConsentimiento(tipo)))

    def puede_recontactar(self, sujeto_id: str,
                          tipo: str | TipoConsentimiento) -> bool:
        """True solo si hay consentimiento OTORGADO y vigente. Si se denegó o
        venció (o no existe), se bloquea el recontacto."""
        c = self.estado(sujeto_id, tipo)
        if c is None or not c.otorgado:
            return False
        if c.vigencia_hasta and c.vigencia_hasta < datetime.now(timezone.utc):
            return False
        return True


# Singleton stub (en producción se inyecta un repositorio real).
consent_store = ConsentStore()
