"""Tests del scoring de existencia (casos clave).

Ejecutar desde el directorio del submódulo:
    cd backend/onboarding_verificacion/existencia && python -m pytest
"""

import os
import sys

import pytest

# Permite importar los módulos del submódulo al correr pytest desde aquí.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scoring import (FACTORES_DEFAULT, Factor, Senales,  # noqa: E402
                     calcular_score)


def _aporte(res, factor):
    return next(a for a in res.desglose if a.factor == factor)


def test_cancha_real_coincidente_score_alto():
    """Negocio activo, domicilio coincide, en Maps y cerca → score alto, aprobado."""
    senales = Senales(
        sunat_activo=1.0, sunat_domicilio=0.95, maps_operativo=1.0,
        maps_distancia=0.95, social=0.8)
    res = calcular_score(senales)
    assert res.score >= 70
    assert res.nivel == "alto"
    assert res.aprobado is True
    # El resultado es explicable: hay desglose por factor.
    assert len(res.desglose) == len(FACTORES_DEFAULT)
    assert res.justificacion


def test_direccion_que_no_cuadra_score_bajo():
    """Existe el negocio, pero la dirección no coincide y está lejos → bajo."""
    senales = Senales(
        sunat_activo=0.9, sunat_domicilio=0.0, maps_operativo=0.3,
        maps_distancia=0.0, social=0.2)
    res = calcular_score(senales)
    assert res.score < 40
    assert res.nivel == "bajo"
    assert res.aprobado is False


def test_negocio_en_baja_sunat_penaliza():
    """Un negocio en BAJA en SUNAT (sunat_activo=0) debe puntuar mucho menos que
    el mismo caso ACTIVO, y su factor SUNAT no aporta nada."""
    comunes = dict(sunat_domicilio=0.6, maps_operativo=0.8,
                   maps_distancia=0.8, social=0.5)
    activo = calcular_score(Senales(sunat_activo=1.0, **comunes))
    baja = calcular_score(Senales(sunat_activo=0.0, **comunes))

    assert baja.score < activo.score
    assert baja.score <= activo.score - 25   # penalización significativa
    assert baja.aprobado is False
    assert _aporte(baja, "sunat_activo").aporte == 0.0


def test_sin_dato_redistribuye_peso():
    """Si falta un factor (None), su peso se redistribuye y el resto se evalúa."""
    senales = Senales(
        sunat_activo=None, sunat_domicilio=None, maps_operativo=1.0,
        maps_distancia=1.0, social=1.0)
    res = calcular_score(senales)
    # Con todo lo disponible en 1.0, el score debe ser 100 pese a faltar SUNAT.
    assert res.score == 100
    excluidos = [a for a in res.desglose if not a.disponible]
    assert {a.factor for a in excluidos} == {"sunat_activo", "sunat_domicilio"}


def test_sin_ninguna_senal_score_cero():
    res = calcular_score(Senales())
    assert res.score == 0
    assert res.nivel == "bajo"
    assert res.aprobado is False


def test_pesos_deben_sumar_uno():
    malos = [Factor("a", 0.5, ""), Factor("b", 0.2, "")]  # suman 0.7
    with pytest.raises(ValueError):
        calcular_score(Senales(maps_operativo=1.0), factores=malos)
