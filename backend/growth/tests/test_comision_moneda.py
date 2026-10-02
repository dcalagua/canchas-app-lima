"""Mínimo de comisión POR MONEDA (decisión del director, sep-2026): 5 % con
mínimo S/ 2 en Perú, $ 0.50 en Ecuador y Bs 3 en Bolivia. Un mínimo único
de "2" era 20 % de una reserva de $10 en Guayaquil."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos.router import comision_centimos, comision_saldo_centimos, moneda_iso  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "APP_API_KEY", "")
    stores.config.pop("comision_saldo_pct", None)
    stores.config.pop("comision_saldo_min_soles", None)
    yield


def test_minimo_por_moneda():
    # 5 % de 10 = 0.50 → PEN sube al mínimo 2; USD queda en 0.50; BOB sube a 3.
    assert comision_centimos(10, "PEN") == 200
    assert comision_centimos(10, "USD") == 50
    assert comision_centimos(10, "BOB") == 300
    # Por encima del mínimo, el 5 % manda en todas.
    assert comision_centimos(100, "USD") == 500
    assert comision_centimos(100, "BOB") == 500
    # Símbolos también valen; vacío = PEN (APKs viejos).
    assert moneda_iso("$") == "USD" and moneda_iso("Bs") == "BOB"
    assert moneda_iso("S/") == "PEN" and moneda_iso("") == "PEN"
    assert comision_centimos(10, "$") == 50
    assert comision_centimos(10) == 200


def test_tarifa_de_billetera_respeta_minimo_por_moneda():
    """El % de la torre aplica a todas las monedas; su mínimo en soles solo a PEN."""
    stores.config["comision_saldo_pct"] = "3"
    stores.config["comision_saldo_min_soles"] = "1"
    assert comision_saldo_centimos(10, "PEN") == 100   # max(0.30, 1.00)
    assert comision_saldo_centimos(10, "USD") == 50    # max(0.30, 0.50 USD)
    assert comision_saldo_centimos(10, "BOB") == 300   # max(0.30, 3 Bs)


def test_liquidacion_online_en_dolares_guarda_moneda_y_minimo():
    stores.saldos.pop("ec@b.com", None)
    stores.saldos_promo.pop("ec@b.com", None)
    r = client.post("/pagos/liquidacion-online", json={
        "dueno_id": "ec@b.com", "monto_soles": 10, "reserva_id": "res_usd_1",
        "concepto": "Reserva Guayaquil", "moneda": "USD"}).json()
    assert r["ok"] and r["comision_centimos"] == 50 and r["neto_centimos"] == 950
    p = stores.pago_por_charge("res_usd_1")
    assert p.moneda == "USD"
    # El desglose que ve la torre recalcula con la moneda GUARDADA, no en soles.
    from pagos.router import _liquidacion_dict
    d = _liquidacion_dict(p)
    assert round(d["comision_soles"], 2) == 0.5 and round(d["neto_soles"], 2) == 9.5


def test_comision_reserva_efectivo_en_dolares():
    stores.saldos["ec2@b.com"] = 1000
    stores.saldos_promo.pop("ec2@b.com", None)
    r = client.post("/pagos/comision-reserva", json={
        "dueno_id": "ec2@b.com", "monto_soles": 8, "reserva_id": "res_usd_2",
        "moneda": "$"}).json()
    assert r["ok"] and r["comision_centimos"] == 50  # 5 % de 8 = 0.40 → mín $0.50
    assert stores.saldo_centimos("ec2@b.com") == 950
    assert stores.pago_por_charge("res_usd_2").moneda == "USD"


def test_sin_moneda_sigue_siendo_soles():
    stores.saldos["pe@b.com"] = 1000
    r = client.post("/pagos/comision-reserva", json={
        "dueno_id": "pe@b.com", "monto_soles": 8, "reserva_id": "res_pen_1"}).json()
    assert r["comision_centimos"] == 200
    assert stores.pago_por_charge("res_pen_1").moneda == "PEN"
