"""Configuración por entorno (no secretos en código). Las reglas de incentivos
viven en la tabla `config_incentivos` (ver db/store.py), no aquí."""

from __future__ import annotations

import os

# URL del módulo de existencia (Capa IA). Si está vacío, se usa el stub.
EXISTENCIA_API_URL = os.getenv("EXISTENCIA_API_URL", "")

# Distancia máx (m) entre la ubicación declarada y la del sitio para considerar
# que la verificación física "coincide".
COINCIDENCIA_MAX_M = float(os.getenv("VERIF_COINCIDENCIA_MAX_M", "200"))

ZONAS = ("lima_norte", "lima_sur", "lima_este", "lima_moderna", "callao")

# Mapeo distrito -> zona (parcial; lo no mapeado cae a 'lima_moderna').
DISTRITO_ZONA: dict[str, str] = {
    # Lima Norte
    "los olivos": "lima_norte", "san martin de porres": "lima_norte",
    "comas": "lima_norte", "carabayllo": "lima_norte", "puente piedra": "lima_norte",
    "independencia": "lima_norte",
    # Lima Sur
    "villa el salvador": "lima_sur", "villa maria del triunfo": "lima_sur",
    "san juan de miraflores": "lima_sur", "chorrillos": "lima_sur",
    "lurin": "lima_sur",
    # Lima Este
    "ate": "lima_este", "santa anita": "lima_este", "el agustino": "lima_este",
    "san juan de lurigancho": "lima_este", "lurigancho": "lima_este",
    "chosica": "lima_este", "la molina": "lima_este",
    # Lima Moderna
    "miraflores": "lima_moderna", "san isidro": "lima_moderna",
    "surco": "lima_moderna", "santiago de surco": "lima_moderna",
    "san borja": "lima_moderna", "barranco": "lima_moderna",
    "jesus maria": "lima_moderna", "magdalena": "lima_moderna",
    "lince": "lima_moderna", "pueblo libre": "lima_moderna",
    # Callao
    "callao": "callao", "bellavista": "callao", "la perla": "callao",
    "ventanilla": "callao",
}


def zona_de_distrito(distrito: str | None) -> str:
    if not distrito:
        return "lima_moderna"
    return DISTRITO_ZONA.get(distrito.strip().lower(), "lima_moderna")
