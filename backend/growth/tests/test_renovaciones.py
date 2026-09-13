"""Renovación mensual de suscripciones: cobra del saldo o, si no alcanza, de la
tarjeta de débito automático guardada. La ejecuta el cron interno."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import stores  # noqa: E402
import pagos.culqi as culqi_mod  # noqa: E402
from pagos.router import procesar_renovaciones  # noqa: E402

VENCIDA = "2020-01-01T00:00:00+00:00"  # próximo cobro en el pasado


def _sub(aca="a1", dueno="d@x", monto=9900, prox=VENCIDA):
    stores.suscripciones[f"{aca}:redes"] = {
        "academia_id": aca, "dueno_id": dueno, "servicio": "redes",
        "monto_centimos": monto, "estado": "activa",
        "proximo_cobro": prox}


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    yield


def test_renueva_con_saldo():
    stores.acreditar("d@x", 20000)
    _sub()
    r = procesar_renovaciones()
    assert r["cobradas"] == 1
    assert stores.saldo_centimos("d@x") == 20000 - 9900
    assert stores.suscripciones["a1:redes"]["estado"] == "activa"
    assert stores.suscripciones["a1:redes"]["proximo_cobro"] != VENCIDA


def test_renueva_con_tarjeta_si_no_hay_saldo(monkeypatch):
    monkeypatch.setattr(culqi_mod, "disponible", lambda: True)
    monkeypatch.setattr(culqi_mod, "crear_cargo",
                        lambda **k: {"ok": True, "charge_id": "chg_1"})
    _sub()  # sin saldo
    stores.metodo_suscripcion["a1"] = {
        "card_id": "crd_1", "email": "d@x", "marca": "visa", "ultimos4": "1111"}
    r = procesar_renovaciones()
    assert r["por_tarjeta"] == 1
    assert stores.suscripciones["a1:redes"]["estado"] == "activa"


def test_pendiente_si_no_hay_saldo_ni_tarjeta():
    _sub()  # sin saldo, sin tarjeta
    r = procesar_renovaciones()
    assert r["pendientes"] == 1
    assert stores.suscripciones["a1:redes"]["estado"] == "pendiente_pago"


def test_no_renueva_si_no_vencio():
    _sub(prox="2999-01-01T00:00:00+00:00")
    r = procesar_renovaciones()
    assert r["cobradas"] == 0 and r["pendientes"] == 0
