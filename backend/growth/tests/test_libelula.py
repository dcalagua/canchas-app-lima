"""Pasarela de Bolivia (Libélula): registrar deuda → pagar → callback verificado.
Se mockean las llamadas HTTP a Libélula (registrar/consultar) para probar todo
el flujo del backend sin red ni appkey real.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores, Stores  # noqa: E402
from main import app  # noqa: E402
from pagos import libelula  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "APP_API_KEY", "")  # endpoints públicos en tests
    monkeypatch.setattr(config, "LIBELULA_APPKEY", "test-appkey")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://pg.example.com")
    stores.libelula_deudas.clear()
    yield
    stores.libelula_deudas.clear()


def test_no_configurado(monkeypatch):
    monkeypatch.setattr(config, "LIBELULA_APPKEY", "")
    r = client.post("/pagos/bo/deuda", json={"email": "a@b.com", "monto_bs": 50})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"] == "no_configurado"


def test_flujo_pago(monkeypatch):
    def fake_registrar(**kw):
        # Verifica que se arme el callback/retorno con la base pública.
        assert kw["callback_url"].endswith("/pagos/bo/callback")
        assert "/pagos/bo/retorno?id=" in kw["url_retorno"]
        return {"ok": True, "url_pasarela": "https://libelula/pay/x",
                "id_transaccion": "TX123", "qr_url": None}

    estado = {"pagado": False}
    monkeypatch.setattr(libelula, "registrar_deuda", fake_registrar)
    monkeypatch.setattr(libelula, "consultar_por_identificador",
                        lambda ident: {"ok": True, "pagado": estado["pagado"]})

    # 1) Crear deuda (el correo se normaliza a minúsculas).
    r = client.post("/pagos/bo/deuda", json={
        "email": "Cli@B.com", "monto_bs": 120.5,
        "concepto": "Reserva", "tipo": "reserva"})
    j = r.json()
    assert j["ok"] and j["url_pasarela"] == "https://libelula/pay/x"
    ident = j["identificador"]
    assert stores.libelula_deudas[ident]["pagado"] is False
    assert stores.libelula_deudas[ident]["email"] == "cli@b.com"

    # 2) Estado: aún pendiente.
    assert client.get(f"/pagos/bo/deuda/{ident}").json()["pagado"] is False

    # 3) Callback con transaction_id desconocido → no confirma.
    assert client.get("/pagos/bo/callback",
                      params={"transaction_id": "NOPE"}).json()["ok"] is False

    # 4) Callback real pero Libélula dice NO pagado → anti-spoofing, no confirma.
    assert client.get("/pagos/bo/callback",
                      params={"transaction_id": "TX123"}).json()["ok"] is False
    assert stores.libelula_deudas[ident]["pagado"] is False

    # 5) Libélula confirma pagado → el callback marca pagado.
    estado["pagado"] = True
    assert client.get("/pagos/bo/callback",
                      params={"transaction_id": "TX123"}).json()["ok"] is True
    assert stores.libelula_deudas[ident]["pagado"] is True

    # 6) El estado refleja pagado.
    assert client.get(f"/pagos/bo/deuda/{ident}").json()["pagado"] is True


def test_reconcilia_por_consulta(monkeypatch):
    """Si el callback nunca llega, consultar el estado reconcilia con Libélula."""
    monkeypatch.setattr(libelula, "registrar_deuda", lambda **kw: {
        "ok": True, "url_pasarela": "u", "id_transaccion": "TXR", "qr_url": None})
    monkeypatch.setattr(libelula, "consultar_por_identificador",
                        lambda ident: {"ok": True, "pagado": True})
    ident = client.post("/pagos/bo/deuda",
                        json={"email": "a@b.com", "monto_bs": 10}).json()["identificador"]
    assert client.get(f"/pagos/bo/deuda/{ident}").json()["pagado"] is True


def test_snapshot_roundtrip():
    stores.libelula_deudas["abc"] = {
        "identificador": "abc", "id_transaccion": "T", "email": "x@y.com",
        "monto_bs": 10.0, "concepto": "c", "tipo": "reserva", "ref": "",
        "dueno_id": "", "pagado": True, "fecha_pago": "2026-01-01",
        "creado_en": "2026-01-01"}
    state = stores.to_state()
    s2 = Stores()
    s2.load_state(state)
    assert s2.libelula_deudas["abc"]["pagado"] is True
    assert s2.libelula_deudas["abc"]["monto_bs"] == 10.0
