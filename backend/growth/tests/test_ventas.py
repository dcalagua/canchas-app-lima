"""Marketplace (escrow): pagar → retenido → entregado → recibido (libera), con
auto-liberación por vencimiento y disputa."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import ahora, stores  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "")
    yield


def _comprar(venta_id="v1", monto=200):
    return client.post("/pagos/venta", json={
        "vendedor_id": "vend@x.com", "vendedor_nombre": "Vendedor",
        "monto_soles": monto, "venta_id": venta_id,
        "producto_id": "prod_1", "producto_nombre": "Raqueta",
        "comprador_email": "comp@x.com", "comprador_nombre": "Comprador"}).json()


def test_compra_crea_orden_retenida():
    assert _comprar()["ok"] is True
    v = client.get("/ventas/comprador/comp@x.com").json()["ventas"]
    assert len(v) == 1 and v[0]["estado"] == "pagado"
    assert v[0]["liberado"] is False
    # El vendedor la ve como retenida (aún no puede cobrar).
    r = client.get("/ventas/vendedor/vend@x.com").json()
    assert r["retenido_soles"] == 190.0 and r["liberado_soles"] == 0.0


def test_entregado_y_recibido_libera_el_pago():
    _comprar()
    vid = client.get("/ventas/vendedor/vend@x.com").json()["ventas"][0]["id"]
    # Vendedor marca entregado.
    e = client.post(f"/ventas/{vid}/entregado",
                    json={"por_email": "vend@x.com"}).json()
    assert e["ok"] is True and e["venta"]["estado"] == "entregado"
    # Comprador confirma recepción → liberado.
    r = client.post(f"/ventas/{vid}/recibido",
                    json={"por_email": "comp@x.com"}).json()
    assert r["ok"] is True and r["venta"]["estado"] == "recibido"
    assert r["venta"]["liberado"] is True
    res = client.get("/ventas/vendedor/vend@x.com").json()
    assert res["liberado_soles"] == 190.0 and res["retenido_soles"] == 0.0


def test_solo_el_comprador_confirma_recepcion():
    _comprar()
    vid = client.get("/ventas/vendedor/vend@x.com").json()["ventas"][0]["id"]
    r = client.post(f"/ventas/{vid}/recibido",
                    json={"por_email": "vend@x.com"}).json()
    assert r["ok"] is False and r["error"] == "no_eres_el_comprador"


def test_auto_liberacion_por_vencimiento():
    _comprar()
    v = next(x for x in stores.ventas)
    from datetime import timedelta
    v.creado_en = ahora() - timedelta(days=10)  # mayor al plazo (7 días)
    res = client.get("/ventas/vendedor/vend@x.com").json()
    assert res["liberado_soles"] == 190.0
    assert res["ventas"][0]["auto_liberado"] is True


def test_disputa_no_libera():
    _comprar()
    vid = client.get("/ventas/vendedor/vend@x.com").json()["ventas"][0]["id"]
    d = client.post(f"/ventas/{vid}/disputa",
                    json={"por_email": "comp@x.com"}).json()
    assert d["ok"] is True and d["venta"]["estado"] == "disputado"
    res = client.get("/ventas/vendedor/vend@x.com").json()
    assert res["liberado_soles"] == 0.0
