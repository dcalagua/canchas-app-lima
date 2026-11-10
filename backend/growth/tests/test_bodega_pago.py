"""BODEGA fase 3: pago del pedido con saldo Pichangol (cero comisión) y
reembolso automático cuando el pedido no procede."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import main  # noqa: E402
from db.store import stores  # noqa: E402

cli = TestClient(main.app)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    yield


def _pagar(monto=18.0, pedido="ped_1", cliente="ana@x.com"):
    return cli.post("/pagos/bodega-pago",
                    json={"cliente": cliente, "dueno_id": "dueno@x.com",
                          "monto_soles": monto, "pedido_id": pedido,
                          "concepto": "2 Pilsen + 1 agua"})


def test_pago_debita_y_deja_por_recibir_sin_comision():
    stores.acreditar("ana@x.com", 5000)  # S/ 50 de saldo
    r = _pagar(monto=18.0)
    assert r.json()["ok"] is True
    assert stores.saldo_centimos("ana@x.com") == 3200  # 50 − 18
    # El dueño tiene S/ 18 COMPLETOS por recibir (cero comisión).
    liq = stores.liquidaciones(dueno_id="dueno@x.com", solo_pendientes=True)
    assert len(liq) == 1 and liq[0].monto_centimos == 1800
    movs = cli.get("/pagos/movimientos/dueno@x.com").json()["movimientos"]
    v = next(m for m in movs if m["tipo"] == "venta_bodega")
    assert v["comision_soles"] == 0.0 and v["neto_soles"] == 18.0
    # Y el cliente lo ve como egreso.
    movc = cli.get("/pagos/movimientos/ana@x.com").json()["movimientos"]
    assert any(m["tipo"] == "bodega_pago" and m["monto_soles"] == -18.0
               for m in movc)
    # Verificación del dueño antes de entregar.
    assert cli.get("/pagos/bodega-pago/ped_1").json()["pagado"] is True


def test_pago_idempotente_y_saldo_insuficiente():
    stores.acreditar("ana@x.com", 2000)
    assert _pagar(monto=18.0).json()["ok"]
    # Reintento del mismo pedido: no debita doble.
    r2 = _pagar(monto=18.0)
    assert r2.json()["duplicada"] is True
    assert stores.saldo_centimos("ana@x.com") == 200
    # Otro pedido sin saldo → error claro, sin tocar el saldo.
    r3 = _pagar(monto=18.0, pedido="ped_2")
    assert r3.json()["error"] == "saldo_insuficiente"
    assert stores.saldo_centimos("ana@x.com") == 200


def test_reembolso_devuelve_todo_y_es_idempotente():
    stores.acreditar("ana@x.com", 5000)
    _pagar(monto=18.0)
    r = cli.post("/pagos/bodega-reembolso", json={"pedido_id": "ped_1"})
    assert r.json()["ok"] is True
    assert stores.saldo_centimos("ana@x.com") == 5000  # íntegro de vuelta
    # Ya no está por recibir del dueño ni figura pagado.
    assert stores.liquidaciones(dueno_id="dueno@x.com",
                                solo_pendientes=True) == []
    assert cli.get("/pagos/bodega-pago/ped_1").json()["pagado"] is False
    # Reembolsar de nuevo: no duplica.
    r2 = cli.post("/pagos/bodega-reembolso", json={"pedido_id": "ped_1"})
    assert r2.json()["duplicada"] is True
    assert stores.saldo_centimos("ana@x.com") == 5000


def test_reembolso_bloqueado_si_ya_se_liquido():
    stores.acreditar("ana@x.com", 5000)
    _pagar(monto=18.0)
    venta = stores.pago_por_charge("bod_ped_1")
    venta.liquidado = True  # el operador ya le pagó al dueño
    r = cli.post("/pagos/bodega-reembolso", json={"pedido_id": "ped_1"})
    assert r.json()["ok"] is False
    assert r.json()["error"] == "ya_liquidada_al_dueno"
    assert stores.saldo_centimos("ana@x.com") == 3200  # no se devolvió


def test_validaciones():
    assert cli.post("/pagos/bodega-pago",
                    json={"cliente": "", "dueno_id": "d@x.com",
                          "monto_soles": 10,
                          "pedido_id": "p"}).status_code == 400
    assert cli.post("/pagos/bodega-reembolso",
                    json={"pedido_id": "no_existe"}).status_code == 404
