"""Normalización y comparación de direcciones con tolerancia de formato.

Permite comparar la dirección declarada por el dueño contra el domicilio fiscal
de SUNAT y/o la dirección de Google Maps, sin fallar por abreviaturas, acentos,
mayúsculas o puntuación distinta.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Abreviaturas comunes de direcciones en Perú → forma canónica.
ABREVIATURAS = {
    "AV": "AVENIDA", "AVDA": "AVENIDA", "JR": "JIRON", "CL": "CALLE",
    "CLL": "CALLE", "PSJE": "PASAJE", "PJE": "PASAJE", "PJ": "PASAJE",
    "MZ": "MANZANA", "MZA": "MANZANA", "LT": "LOTE", "LTE": "LOTE",
    "URB": "URBANIZACION", "NRO": "NUMERO", "NR": "NUMERO", "N": "NUMERO",
    "DPTO": "DEPARTAMENTO", "INT": "INTERIOR",
}
STOPWORDS = {"DE", "LA", "EL", "LOS", "LAS", "Y", "DEL"}


def quitar_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(direccion: str | None) -> str:
    """Mayúsculas, sin acentos, sin puntuación, abreviaturas expandidas, sin
    'stopwords' ni espacios redundantes."""
    if not direccion:
        return ""
    s = quitar_acentos(direccion).upper()
    s = s.replace("#", " NUMERO ").replace("°", " ").replace("º", " ")
    s = re.sub(r"[.,;:_\-/]", " ", s)
    tokens: list[str] = []
    for t in s.split():
        t = t.strip()
        if not t:
            continue
        t = ABREVIATURAS.get(t, t)
        if t in STOPWORDS:
            continue
        tokens.append(t)
    return " ".join(tokens)


def similitud(a: str | None, b: str | None) -> float:
    """Similitud [0..1] entre dos direcciones, tolerante al formato.

    Combina Jaccard de tokens (0.6) + ratio de secuencia (0.4).
    """
    na, nb = normalizar(a), normalizar(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    secuencia = SequenceMatcher(None, na, nb).ratio()
    return round(0.6 * jaccard + 0.4 * secuencia, 4)
