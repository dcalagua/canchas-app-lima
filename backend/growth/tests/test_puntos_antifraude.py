"""Anti-fraude: el premio NO se libera sin verificación + primera reserva."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import stores  # noqa: E402
from puntos import service as puntos  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    yield


def test_traer_cancha_no_libera_sin_verificacion_ni_reserva():
    puntos.acreditar("u1", "traer_cancha", "cancha", "c1")
    # nace pendiente: no canjeable
    assert puntos.saldo("u1")["disponible"] == 0
    assert puntos.saldo("u1")["pendiente"] == stores.cfg_int("puntos_traer_cancha")

    # solo verificada (sin reserva) → NO libera
    stores.cancha("c1").verificada = True
    assert puntos.intentar_liberar_traer_cancha("c1") == 0
    assert puntos.saldo("u1")["disponible"] == 0

    # verificada + primera reserva → SÍ libera
    puntos.evento_primera_reserva("c1")
    assert puntos.saldo("u1")["disponible"] == stores.cfg_int("puntos_traer_cancha")


def test_solo_reserva_sin_verificacion_no_libera():
    puntos.acreditar("u1", "traer_cancha", "cancha", "c2")
    puntos.evento_primera_reserva("c2")  # reserva pero NO verificada
    assert puntos.saldo("u1")["disponible"] == 0


def test_acreditar_es_idempotente():
    a = puntos.acreditar("u1", "traer_cancha", "cancha", "c3", idem_key="k1")
    b = puntos.acreditar("u1", "traer_cancha", "cancha", "c3", idem_key="k1")
    assert a["id"] == b["id"]
    assert len(stores.movimientos) == 1
