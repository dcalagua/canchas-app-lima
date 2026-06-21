"""Scoring EXPLICABLE de existencia de un negocio (cancha).

Combina señales de varias fuentes (SUNAT, Google Places, redes) con pesos
configurables que **suman 1.0**. Cada factor aporta una porción justificable del
puntaje final (0–100), de modo que el resultado siempre se puede explicar.

Principio: el scoring NO recibe ni guarda datos personales; solo trabaja con
señales numéricas [0..1] ya derivadas por el servicio.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Factor:
    """Un factor del puntaje, con su peso (porción de 1.0) y descripción."""
    clave: str
    peso: float
    descripcion: str


# Pesos por defecto. DEBEN sumar 1.0 (se valida). Configurables por entorno con
# VERIF_PESOS="sunat_activo:0.3,sunat_domicilio:0.2,maps_operativo:0.15,maps_distancia:0.2,social:0.15"
FACTORES_DEFAULT: list[Factor] = [
    Factor("sunat_activo", 0.30, "RUC existe, ACTIVO y HABIDO en SUNAT"),
    Factor("sunat_domicilio", 0.20,
           "Domicilio fiscal SUNAT coincide con la dirección declarada"),
    Factor("maps_operativo", 0.15, "El negocio figura OPERATIVO en Google Maps"),
    Factor("maps_distancia", 0.20,
           "Cercanía entre la ubicación declarada y la de Maps"),
    Factor("social", 0.15, "Antigüedad / actividad en redes y reseñas"),
]

UMBRAL_ALTO = int(os.getenv("VERIF_UMBRAL_ALTO", "70"))   # >= : aprobado
UMBRAL_MEDIO = int(os.getenv("VERIF_UMBRAL_MEDIO", "40"))  # >= : revisión manual


@dataclass
class Senales:
    """Señales [0..1] por factor. `None` = sin dato (se excluye y se redistribuye
    su peso entre los factores disponibles, para no penalizar lo no evaluable)."""
    sunat_activo: float | None = None
    sunat_domicilio: float | None = None
    maps_operativo: float | None = None
    maps_distancia: float | None = None
    social: float | None = None

    def como_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass
class Aporte:
    """Contribución de un factor al puntaje (para explicar el resultado)."""
    factor: str
    peso: float            # peso EFECTIVO (renormalizado si hubo factores sin dato)
    valor: float | None    # señal [0..1] o None si no se evaluó
    aporte: float          # puntos que sumó al total (0..100)
    disponible: bool
    detalle: str


@dataclass
class ResultadoScore:
    score: int                 # 0..100
    nivel: str                 # alto | medio | bajo
    aprobado: bool             # score >= UMBRAL_ALTO
    desglose: list[Aporte]
    justificacion: str


def cargar_factores_desde_env() -> list[Factor]:
    """Lee VERIF_PESOS si está definido; si no, usa los pesos por defecto."""
    crudo = os.getenv("VERIF_PESOS", "").strip()
    if not crudo:
        return FACTORES_DEFAULT
    descripciones = {f.clave: f.descripcion for f in FACTORES_DEFAULT}
    factores: list[Factor] = []
    for parte in crudo.split(","):
        clave, _, peso = parte.partition(":")
        clave = clave.strip()
        factores.append(
            Factor(clave, float(peso), descripciones.get(clave, clave)))
    return factores


def _validar_pesos(factores: list[Factor]) -> None:
    total = round(sum(f.peso for f in factores), 6)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"Los pesos de los factores deben sumar 1.0 (suman {total}).")


def _detalle(factor: Factor, valor: float) -> str:
    if valor >= 0.85:
        calidad = "señal fuerte a favor"
    elif valor >= 0.5:
        calidad = "señal parcial"
    elif valor > 0.0:
        calidad = "señal débil"
    else:
        calidad = "señal en contra"
    return f"{factor.descripcion}: {calidad} ({round(valor * 100)}%)."


def _justificar(score: int, nivel: str, desglose: list[Aporte],
                disponibles: list[Aporte]) -> str:
    if not disponibles:
        return ("No hay señales suficientes para verificar la existencia "
                "(sin datos de SUNAT, Maps ni redes).")
    ordenados = sorted(disponibles, key=lambda a: a.aporte, reverse=True)
    fuertes = [a.factor for a in ordenados if a.valor and a.valor >= 0.6][:3]
    debiles = [a.factor for a in ordenados if a.valor is not None and a.valor < 0.4]
    partes = [f"Puntaje {score}/100 (nivel {nivel})."]
    if fuertes:
        partes.append("Sustentado por: " + ", ".join(fuertes) + ".")
    if debiles:
        partes.append("Penalizado por: " + ", ".join(debiles) + ".")
    excluidos = [a.factor for a in desglose if not a.disponible]
    if excluidos:
        partes.append("No evaluado (peso redistribuido): "
                      + ", ".join(excluidos) + ".")
    return " ".join(partes)


def calcular_score(senales: Senales,
                   factores: list[Factor] | None = None) -> ResultadoScore:
    """Calcula el puntaje de existencia combinando las señales de forma explicable.

    Los factores sin dato (`None`) se excluyen y su peso se **redistribuye** entre
    los disponibles, de modo que el puntaje siempre se interpreta sobre lo que sí
    se pudo verificar.
    """
    factores = factores or cargar_factores_desde_env()
    _validar_pesos(factores)
    valores = senales.como_dict()

    disponibles_factores = [f for f in factores if valores.get(f.clave) is not None]
    peso_disponible = sum(f.peso for f in disponibles_factores)

    desglose: list[Aporte] = []
    score_acc = 0.0
    for f in factores:
        v = valores.get(f.clave)
        if v is None:
            desglose.append(Aporte(
                factor=f.clave, peso=0.0, valor=None, aporte=0.0,
                disponible=False,
                detalle=(f"Sin dato — {f.descripcion}; peso redistribuido entre "
                         "los factores disponibles.")))
            continue
        v = max(0.0, min(1.0, float(v)))
        peso_efectivo = (f.peso / peso_disponible) if peso_disponible > 0 else 0.0
        aporte = peso_efectivo * v * 100.0
        score_acc += aporte
        desglose.append(Aporte(
            factor=f.clave, peso=round(peso_efectivo, 4), valor=round(v, 4),
            aporte=round(aporte, 2), disponible=True, detalle=_detalle(f, v)))

    score = int(round(score_acc)) if disponibles_factores else 0
    nivel = "alto" if score >= UMBRAL_ALTO else "medio" if score >= UMBRAL_MEDIO else "bajo"
    aprobado = score >= UMBRAL_ALTO
    disponibles_aportes = [a for a in desglose if a.disponible]
    justificacion = _justificar(score, nivel, desglose, disponibles_aportes)
    return ResultadoScore(score=score, nivel=nivel, aprobado=aprobado,
                          desglose=desglose, justificacion=justificacion)
