"""FIDELIDAD del jugador: puntos por reservas pagadas, caducidad y canje."""

import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import ahora, stores  # noqa: E402
from puntos import service as puntos  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    yield


def test_acreditar_reserva_basico_e_idempotente():
    r = puntos.acreditar_reserva("ana@x.com", 120, "S/", "res_1")
    assert r["ok"] and not r["duplicada"]
    assert r["puntos"] == 120  # 1 punto por S/ 1
    assert puntos.saldo("ana@x.com")["disponible"] == 120
    # Reintento con la misma reserva: NO duplica.
    r2 = puntos.acreditar_reserva("ana@x.com", 120, "S/", "res_1")
    assert r2["ok"] and r2["duplicada"]
    assert puntos.saldo("ana@x.com")["disponible"] == 120


def test_acreditar_usd_ecuador_vale_triple():
    r = puntos.acreditar_reserva("ec@x.com", 10, "$", "res_ec")
    assert r["puntos"] == 30  # $1 = 3 puntos


def test_acreditar_datos_invalidos():
    assert not puntos.acreditar_reserva("", 100, "S/", "r")["ok"]
    assert not puntos.acreditar_reserva("a@x.com", 0, "S/", "r")["ok"]
    assert not puntos.acreditar_reserva("a@x.com", 100, "S/", "")["ok"]


def test_canje_100_puntos_vale_3():
    puntos.acreditar_reserva("ana@x.com", 200, "S/", "res_2")
    r = puntos.canjear("ana@x.com", 100, "descuento_reserva")
    assert r["ok"]
    assert r["valor_soles"] == 3.0  # 100 puntos = S/ 3
    assert puntos.saldo("ana@x.com")["disponible"] == 100


def test_caducidad_seis_meses_fifo():
    # Lote viejo (7 meses atrás) + lote fresco.
    puntos.acreditar_reserva("ana@x.com", 100, "S/", "res_vieja")
    viejo = stores.movimientos[-1]
    viejo.creado_en = ahora() - timedelta(days=210)
    viejo.liberado_en = viejo.creado_en
    puntos.acreditar_reserva("ana@x.com", 50, "S/", "res_nueva")
    # El lote viejo ya venció (180 días): solo cuenta el fresco.
    s = puntos.saldo("ana@x.com")
    assert s["disponible"] == 50
    # Y no se puede canjear más de lo vivo.
    assert not puntos.canjear("ana@x.com", 100, "descuento_reserva")["ok"]
    assert puntos.canjear("ana@x.com", 50, "descuento_reserva")["ok"]


def test_canje_consume_fifo_lo_mas_viejo_primero():
    # Dos lotes vivos: 100 (hace 5 meses, por vencer) + 100 (hoy).
    puntos.acreditar_reserva("ana@x.com", 100, "S/", "res_a")
    lote_a = stores.movimientos[-1]
    lote_a.creado_en = ahora() - timedelta(days=150)
    lote_a.liberado_en = lote_a.creado_en
    puntos.acreditar_reserva("ana@x.com", 100, "S/", "res_b")
    # Canjea 100: debe consumir el lote VIEJO (FIFO).
    assert puntos.canjear("ana@x.com", 100, "descuento_reserva")["ok"]
    s = puntos.saldo("ana@x.com")
    assert s["disponible"] == 100
    # Nada por vencer en 30 días: el lote viejo ya se gastó.
    assert s["por_vencer_30d"] == 0


def test_saldo_reporta_por_vencer():
    puntos.acreditar_reserva("ana@x.com", 80, "S/", "res_pv")
    lote = stores.movimientos[-1]
    lote.creado_en = ahora() - timedelta(days=160)  # vence en ~20 días
    lote.liberado_en = lote.creado_en
    s = puntos.saldo("ana@x.com")
    assert s["disponible"] == 80
    assert s["por_vencer_30d"] == 80
    assert s["vence_proximo"] is not None
    assert s["valor_100_puntos"] == 3.0


def test_incentivos_growth_siguen_funcionando():
    # El motor histórico (traer_cancha pendiente→liberado) no se rompe.
    puntos.acreditar("u1", "traer_cancha", "cancha", "c1")
    assert puntos.saldo("u1")["pendiente"] == stores.cfg_int(
        "puntos_traer_cancha")
    stores.cancha("c1").verificada = True
    puntos.evento_primera_reserva("c1")
    assert puntos.saldo("u1")["disponible"] == stores.cfg_int(
        "puntos_traer_cancha")
