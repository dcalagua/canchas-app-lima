"""Adaptador SUNAT: consulta de RUC (existencia, estado, domicilio, anexos).

Proveedor configurable por entorno `SUNAT_PROVIDER` (factiliza | oficial | stub).
El adaptador es intercambiable: el resto del código solo depende de la interfaz
`SunatAdapter` y del dataclass `SunatResultado`.

STUB: no se llama a ningún servicio real. Los datos se derivan de forma
determinista del propio RUC, solo para pruebas y demo.

Cumplimiento: la consulta de RUC es de un IDENTIFICADOR DE NEGOCIO, no de datos
personales. No se solicita ni almacena DNI ni documentos de personas.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EstablecimientoAnexo:
    codigo: str
    tipo: str
    direccion: str


@dataclass
class SunatResultado:
    consultado: bool                # ¿se llegó a consultar?
    existe: bool                    # ¿el RUC existe?
    ruc: str | None
    razon_social: str | None
    estado: str | None              # ACTIVO | BAJA DE OFICIO | SUSPENSION TEMPORAL | ...
    condicion: str | None           # HABIDO | NO HABIDO
    domicilio_fiscal: str | None
    establecimientos_anexos: list[EstablecimientoAnexo] = field(default_factory=list)
    fuente: str = "stub"

    @staticmethod
    def no_consultado(ruc: str | None = None) -> "SunatResultado":
        return SunatResultado(False, False, ruc, None, None, None, None, [], "n/a")


class SunatAdapter(ABC):
    @abstractmethod
    def consultar_ruc(self, ruc: str) -> SunatResultado:
        ...


def _ruc_valido(ruc: str | None) -> bool:
    return bool(ruc) and ruc.isdigit() and len(ruc) == 11


class StubSunatAdapter(SunatAdapter):
    """STUB determinista. El último dígito del RUC decide el estado (solo demo)."""

    def consultar_ruc(self, ruc: str) -> SunatResultado:
        if not _ruc_valido(ruc):
            return SunatResultado(True, False, ruc, None, None, None, None, [], "stub")
        ultimo = int(ruc[-1])
        if ultimo in (0, 9):
            estado, condicion = "BAJA DE OFICIO", "NO HABIDO"
        elif ultimo == 1:
            estado, condicion = "SUSPENSION TEMPORAL", "HABIDO"
        else:
            estado, condicion = "ACTIVO", "HABIDO"
        domicilio = "AV. AVIACION 2345 SAN BORJA LIMA"
        return SunatResultado(
            consultado=True, existe=True, ruc=ruc,
            razon_social=f"RAZON SOCIAL DEMO {ruc[-4:]} S.A.C.",
            estado=estado, condicion=condicion, domicilio_fiscal=domicilio,
            establecimientos_anexos=[
                EstablecimientoAnexo("0001", "LOCAL ANEXO - CANCHA", domicilio)],
            fuente="stub")


class FactilizaSunatAdapter(SunatAdapter):
    """STUB del proveedor Factiliza. Cuando se active, leería FACTILIZA_API_TOKEN
    y llamaría su API REST. Hoy delega en el stub para no llamar servicios reales."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.getenv("FACTILIZA_API_TOKEN", "")
        self._stub = StubSunatAdapter()

    def consultar_ruc(self, ruc: str) -> SunatResultado:
        # TODO(real): requests.get(f"{FACTILIZA_URL}/ruc/{ruc}",
        #             headers={"Authorization": f"Bearer {self._token}"})
        res = self._stub.consultar_ruc(ruc)
        res.fuente = "factiliza-stub"
        return res


class OficialSunatAdapter(SunatAdapter):
    """STUB del padrón / API oficial de SUNAT. Hoy delega en el stub."""

    def __init__(self) -> None:
        self._stub = StubSunatAdapter()

    def consultar_ruc(self, ruc: str) -> SunatResultado:
        # TODO(real): integración con el servicio oficial (padrón reducido / API).
        res = self._stub.consultar_ruc(ruc)
        res.fuente = "sunat-oficial-stub"
        return res


def get_sunat_adapter() -> SunatAdapter:
    """Fábrica: devuelve el adaptador según `SUNAT_PROVIDER` (default: stub)."""
    proveedor = os.getenv("SUNAT_PROVIDER", "stub").lower()
    if proveedor == "factiliza":
        return FactilizaSunatAdapter()
    if proveedor == "oficial":
        return OficialSunatAdapter()
    return StubSunatAdapter()
