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

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Base de la API de Factiliza. El TOKEN nunca se hardcodea: se lee de
# FACTILIZA_API_TOKEN (en .env del host / variable del despliegue).
FACTILIZA_BASE_URL = os.getenv("FACTILIZA_BASE_URL", "https://api.factiliza.com/v1")


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
    """Adaptador REAL de Factiliza para consulta de **RUC** (negocio).

    Usa el endpoint de RUC (`/ruc/info/{ruc}`), NO el de DNI: este submódulo
    verifica la existencia del negocio y, por diseño de cumplimiento, no consulta
    datos personales (DNI). El token se lee de `FACTILIZA_API_TOKEN` (nunca se
    hardcodea ni se versiona).

    Fail-safe: ante error de red/timeout/respuesta inesperada devuelve
    `no_consultado` (el scoring excluye SUNAT y redistribuye su peso).
    """

    def __init__(self, token: str | None = None, base_url: str | None = None,
                 timeout: float = 8.0) -> None:
        self._token = token or os.getenv("FACTILIZA_API_TOKEN", "")
        self._base = (base_url or FACTILIZA_BASE_URL).rstrip("/")
        self._timeout = timeout

    def consultar_ruc(self, ruc: str) -> SunatResultado:
        if not _ruc_valido(ruc):
            return SunatResultado(True, False, ruc, None, None, None, None, [],
                                  "factiliza")
        if not self._token:
            # Sin token configurado no se puede consultar de verdad: no consultado.
            return SunatResultado.no_consultado(ruc)

        url = f"{self._base}/ruc/info/{ruc}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # RUC no encontrado → existe=False (penaliza)
                return SunatResultado(True, False, ruc, None, None, None, None,
                                      [], "factiliza")
            return SunatResultado.no_consultado(ruc)  # 401/5xx → fail-safe
        except Exception:
            return SunatResultado.no_consultado(ruc)   # timeout/parse → fail-safe

        return self._mapear(ruc, payload)

    @staticmethod
    def _mapear(ruc: str, payload: dict) -> SunatResultado:
        if payload.get("success") is False:
            return SunatResultado(True, False, ruc, None, None, None, None, [],
                                  "factiliza")
        data = payload.get("data") or payload  # tolera variaciones de formato
        razon = (data.get("nombre_o_razon_social") or data.get("razon_social")
                 or data.get("nombre"))
        estado = (data.get("estado") or "").upper() or None
        condicion = (data.get("condicion") or "").upper() or None
        domicilio = (data.get("direccion_completa") or data.get("direccion")
                     or None)
        return SunatResultado(
            consultado=True, existe=True, ruc=ruc, razon_social=razon,
            estado=estado, condicion=condicion, domicilio_fiscal=domicilio,
            establecimientos_anexos=[], fuente="factiliza")


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
