"""Tope mensual: al límite, bloquea canjes financiados por Pichangol pero permite
los cofinanciados por el dueño."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import PuntosMovimiento, ahora, stores  # noqa: E402
from puntos import service as puntos  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    yield


def _dar_puntos_liberados(usuario: str, pts: int):
    stores.movimientos.append(PuntosMovimiento(
        id=stores.next_id("movimiento"), usuario_id=usuario, accion="traer_cancha",
        puntos=pts, estado="liberado", ref_tipo=None, ref_id=None,
        creado_en=ahora(), liberado_en=ahora()))


def test_tope_bloquea_pichangol_y_permite_dueno():
    stores.config["tope_mensual_premios_pichangol_soles"] = "5"   # S/ 5
    # Regla de valor vigente (fidelidad): aquí 100 pts = S/ 1 para el cálculo.
    stores.config["fidelidad_valor_100_puntos"] = "1"
    _dar_puntos_liberados("u1", 2000)  # S/ 20 disponibles

    r1 = puntos.canjear("u1", 500, "descuento", "pichangol")  # S/5 (llega al tope)
    assert r1["ok"] is True
    assert r1["fuente_financiamiento"] == "pichangol"

    r2 = puntos.canjear("u1", 100, "descuento", "pichangol")  # +S/1 > tope
    assert r2.get("bloqueado") is True
    assert r2["ok"] is False

    r3 = puntos.canjear("u1", 100, "descuento", "dueno")      # cofinanciado: OK
    assert r3["ok"] is True
    assert r3["fuente_financiamiento"] == "dueno"


def test_canjear_es_idempotente():
    stores.config["equivalencia_puntos_por_sol"] = "100"
    _dar_puntos_liberados("u2", 1000)
    a = puntos.canjear("u2", 300, "descuento", "dueno", idem_key="cj1")
    b = puntos.canjear("u2", 300, "descuento", "dueno", idem_key="cj1")
    assert a["vale_id"] == b["vale_id"]
    assert len(stores.canjes) == 1
