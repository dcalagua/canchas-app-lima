"""Adaptador social: antigüedad/actividad en redes y reseñas.

Señal de respaldo: un negocio real suele tener presencia con cierta antigüedad,
reseñas y actividad. Proveedor configurable por `SOCIAL_PROVIDER` (stub por ahora).
No se recolectan datos personales de terceros; solo señales agregadas del negocio.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SocialResultado:
    consultado: bool
    encontrado: bool
    antiguedad_meses: int | None
    actividad_score: float | None   # [0..1] actividad/consistencia
    resenas: int | None
    rating: float | None
    fuente: str = "stub"


class SocialAdapter(ABC):
    @abstractmethod
    def consultar(self, razon_social: str | None,
                  direccion: str | None) -> SocialResultado:
        ...


class StubSocialAdapter(SocialAdapter):
    """STUB determinista. No llama a ninguna red social."""

    def consultar(self, razon_social: str | None,
                  direccion: str | None) -> SocialResultado:
        return SocialResultado(
            consultado=True, encontrado=True, antiguedad_meses=18,
            actividad_score=0.7, resenas=42, rating=4.3, fuente="stub")


def get_social_adapter() -> SocialAdapter:
    # Solo stub disponible por ahora; se deja la fábrica para futuros proveedores.
    _ = os.getenv("SOCIAL_PROVIDER", "stub").lower()
    return StubSocialAdapter()
