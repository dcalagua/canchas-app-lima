"""Pagos con Culqi (modelo inDrive): recarga del dueño, fee de reserva, saldo,
webhook idempotente. Se mockea la llamada HTTP a Culqi (culqi._request) para
probar todo el flujo sin red ni llaves reales.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402

client = TestClient(app)


class _FakeCulqi:
    """Simula la API de Culqi en memoria: crea cargos y los devuelve al
    consultarlos (para el webhook)."""

    def __init__(self):
        self.cargos = {}
        self.n = 0
        self.forzar_error = False

    def request(self, metodo, path, body=None):
        if self.forzar_error:
            return {"ok": False, "status": 402, "error": "Tarjeta rechazada"}
        if metodo == "POST" and path == "/charges":
            self.n += 1
            cid = f"chr_test_{self.n}"
            data = {
                "id": cid,
                "amount": body["amount"],
                "currency_code": body["currency_code"],
                "captured": True,
                "metadata": body.get("metadata", {}),
            }
            self.cargos[cid] = data
            return {"ok": True, "data": data}
        if metodo == "GET" and path.startswith("/charges/"):
            cid = path.split("/charges/")[1]
            if cid in self.cargos:
                return {"ok": True, "data": self.cargos[cid]}
            return {"ok": False, "status": 404, "error": "no encontrado"}
        return {"ok": False, "error": "ruta_desconocida"}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_xxx")
    monkeypatch.setattr(config, "APP_API_KEY", "")  # sin app-key en tests
    fake = _FakeCulqi()
    monkeypatch.setattr(culqi, "_request", fake.request)
    yield fake


def test_config_expone_pk_y_modo():
    r = client.get("/pagos/config").json()
    assert r["disponible"] is True
    assert r["modo"] == "test"
    assert r["public_key"] == "pk_test_xxx"


def test_recarga_acredita_saldo():
    r = client.post("/pagos/recarga", json={
        "token": "tkn_1", "dueno_id": "due@x.com",
        "email": "due@x.com", "monto_soles": 30,
    }).json()
    assert r["ok"] is True
    assert r["saldo_centimos"] == 3000
    assert r["saldo_soles"] == 30.0
    assert stores.saldo_centimos("due@x.com") == 3000


def test_recarga_suma_sobre_saldo_existente():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 20})
    r = client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 10}).json()
    assert r["saldo_centimos"] == 3000


def test_recarga_monto_minimo():
    resp = client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 0.5})
    assert resp.status_code == 400


def test_recarga_rechazada_no_acredita(_setup):
    _setup.forzar_error = True
    r = client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 30}).json()
    assert r["ok"] is False
    assert stores.saldo_centimos("d") == 0


def test_fee_reserva_no_acredita_saldo():
    r = client.post("/pagos/fee-reserva", json={
        "token": "t", "email": "j@x.com", "monto_soles": 2,
        "concepto": "Fee reserva", "reserva_id": "r1"}).json()
    assert r["ok"] is True
    assert stores.saldo_centimos("j@x.com") == 0
    assert any(p.tipo == "fee_reserva" for p in stores.pagos)


def test_saldo_endpoint():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 15})
    r = client.get("/pagos/saldo/d").json()
    assert r["saldo_centimos"] == 1500 and r["saldo_soles"] == 15.0


def test_webhook_es_idempotente(_setup):
    # Cargo directo en Culqi (como si el APK hubiera cobrado) sin pasar por el
    # endpoint, para que el webhook sea quien acredite.
    culqi.crear_cargo(token="t", monto_centimos=5000, email="d@x.com",
                      descripcion="x",
                      metadata={"tipo": "recarga", "dueno_id": "d"})
    cid = list(_setup.cargos.keys())[0]
    ev = {"data": {"id": cid}}
    r1 = client.post("/pagos/webhook", json=ev).json()
    assert r1["ok"] is True
    assert stores.saldo_centimos("d") == 5000
    # Segundo golpe del mismo cargo: no duplica.
    r2 = client.post("/pagos/webhook", json=ev).json()
    assert r2.get("duplicado") is True
    assert stores.saldo_centimos("d") == 5000


def test_webhook_token_invalido(monkeypatch):
    monkeypatch.setattr(config, "CULQI_WEBHOOK_TOKEN", "secreto")
    resp = client.post("/pagos/webhook?t=malo", json={"data": {"id": "x"}})
    assert resp.status_code == 401


def test_comision_calculo():
    from pagos.router import comision_centimos
    assert comision_centimos(60) == 300     # 5% de 60 = 3.00
    assert comision_centimos(20) == 200      # 5% de 20 = 1.00 → mínimo 2.00
