"""Comisión configurable cuando se cobra del SALDO (billetera-first).

La torre de control puede fijar una tarifa DISTINTA (típicamente menor) para el
camino en que la comisión sale del saldo prepago del dueño — incentivo por
mantener billetera. Sin configurar, aplica la comisión estándar (5% mín S/2).
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402

_ADM = {"X-Admin-Token": "adm_test"}
client = TestClient(app, headers=_ADM)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "")  # sin app-key en tests
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm_test")
    yield


def _configurar(pct, min_soles=0.0):
    r = client.post("/admin/api/margenes/comision-saldo",
                    json={"pct": pct, "min_soles": min_soles})
    assert r.status_code == 200
    return r.json()


def test_sin_configurar_el_saldo_paga_la_comision_estandar():
    stores.acreditar("due@x.com", 5000)
    r = client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "cs_1"}).json()
    assert r["fuente"] == "saldo"
    assert r["comision_centimos"] == 600          # 5% de 120 (estándar)
    assert r["neto_centimos"] == 12000            # bruto completo
    assert stores.saldo_centimos("due@x.com") == 5000 - 600


def test_tarifa_configurada_menor_aplica_al_camino_saldo():
    _configurar(pct=2, min_soles=1)               # 2% mín S/1 (menos que 5%/S/2)
    stores.acreditar("due@x.com", 5000)
    r = client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "cs_2"}).json()
    assert r["fuente"] == "saldo"
    assert r["comision_centimos"] == 240          # 2% de 120 = S/2.40
    assert r["neto_centimos"] == 12000
    assert stores.saldo_centimos("due@x.com") == 5000 - 240


def test_minimo_configurado_aplica_en_montos_chicos():
    _configurar(pct=2, min_soles=1)
    stores.acreditar("due@x.com", 5000)
    r = client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 30, "reserva_id": "cs_3"}).json()
    assert r["comision_centimos"] == 100          # 2% de 30 = 0.60 < mín S/1


def test_sin_saldo_sigue_la_estandar_sobre_la_transaccion():
    # La tarifa de billetera NO aplica al fallback sin saldo: ahí la comisión
    # sale de la transacción con la tarifa estándar.
    _configurar(pct=2, min_soles=1)
    r = client.post("/pagos/liquidacion-online", json={
        "dueno_id": "sin@x.com", "monto_soles": 120, "reserva_id": "cs_4"}).json()
    assert r["fuente"] == "transaccion"
    assert r["comision_centimos"] == 600          # estándar 5%
    assert r["neto_centimos"] == 11400


def test_comision_de_reserva_en_efectivo_usa_la_tarifa_de_saldo():
    # /pagos/comision-reserva (efectivo) también sale del saldo → misma tarifa.
    _configurar(pct=2, min_soles=1)
    stores.acreditar("due@x.com", 5000)
    r = client.post("/pagos/comision-reserva", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "cs_5"}).json()
    assert r["comision_centimos"] == 240
    assert stores.saldo_centimos("due@x.com") == 5000 - 240


def test_reset_vuelve_a_la_estandar_y_margenes_lo_reporta():
    m = _configurar(pct=2, min_soles=1)
    assert m["comision_saldo_pct"] == 2.0
    assert m["comision_saldo_min_soles"] == 1.0
    r = client.post("/admin/api/margenes/comision-saldo", json={"reset": True})
    m = r.json()
    assert m["comision_saldo_pct"] is None
    assert m["comision_saldo_min_soles"] is None
    stores.acreditar("due@x.com", 5000)
    r = client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "cs_6"}).json()
    assert r["comision_centimos"] == 600          # estándar de nuevo


def test_margenes_expone_la_tarifa_estandar_de_referencia():
    m = client.get("/admin/api/margenes").json()
    assert m["comision_std_pct"] == config.COMISION_PORC
    assert m["comision_std_min_soles"] == config.COMISION_MIN_SOLES
    assert m["comision_saldo_pct"] is None        # sin configurar
