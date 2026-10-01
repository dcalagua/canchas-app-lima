"""Nuvei Ecuador (ex-Paymentez, LinkToPay): cliente del API."""
import base64
import hashlib

import pytest

from pagos import nuvei


@pytest.fixture(autouse=True)
def _cred(monkeypatch):
    monkeypatch.setenv("NUVEI_APP_CODE", "PCG-EC-SERVER")
    monkeypatch.setenv("NUVEI_APP_KEY", "llave-secreta")
    monkeypatch.delenv("NUVEI_ENTORNO", raising=False)
    monkeypatch.delenv("NUVEI_BASE_URL", raising=False)
    monkeypatch.delenv("NUVEI_LINKTOPAY_URL", raising=False)


def test_inactivo_sin_credenciales(monkeypatch):
    monkeypatch.delenv("NUVEI_APP_KEY")
    assert not nuvei.disponible()
    assert nuvei.preparar(ident="x", monto_usd=5, concepto="c", email="a@b.ec",
                          success_url="s", failure_url="f")["error"] == "no_configurado"


def test_auth_token_formato():
    t = base64.b64decode(nuvei.auth_token(1700000000)).decode()
    code, ts, uniq = t.split(";")
    assert code == "PCG-EC-SERVER" and ts == "1700000000"
    assert uniq == hashlib.sha256(b"llave-secreta1700000000").hexdigest()


def test_hosts_por_entorno(monkeypatch):
    assert "stg" in nuvei.linktopay_url() and "stg" in nuvei.base_url()
    monkeypatch.setenv("NUVEI_ENTORNO", "prod")
    assert nuvei.linktopay_url() == "https://noccapi.paymentez.com"
    monkeypatch.setenv("NUVEI_BASE_URL", "https://otro.host")
    assert nuvei.base_url() == "https://otro.host"


def test_preparar_manda_orden_y_devuelve_url(monkeypatch):
    llamadas = []

    def falso(metodo, url, payload=None):
        llamadas.append((metodo, url, payload))
        return {"success": True, "data": {"order": {"id": "ord_1"},
                                          "payment": {"payment_url": "https://pay/x"}}}
    monkeypatch.setattr(nuvei, "_http", falso)
    r = nuvei.preparar(ident="abc123", monto_usd=12.5, concepto="Reserva",
                       email="Ana@Mail.ec", nombre="Ana María Pérez Ruiz",
                       telefono="+593 99 123 4567", success_url="https://s",
                       failure_url="https://f")
    assert r == {"ok": True, "url": "https://pay/x", "order_id": "ord_1"}
    metodo, url, body = llamadas[0]
    assert metodo == "POST" and url.endswith("/linktopay/init_order/")
    assert body["order"]["dev_reference"] == "abc123"
    assert body["order"]["amount"] == 12.5 and body["order"]["currency"] == "USD"
    assert body["user"]["email"] == "ana@mail.ec"
    assert body["user"]["name"] == "Ana María" and body["user"]["last_name"] == "Pérez Ruiz"
    assert body["user"]["phone_number"] == "593991234567"
    assert body["configuration"]["success_url"] == "https://s"


def test_preparar_rechazo(monkeypatch):
    monkeypatch.setattr(nuvei, "_http", lambda *a, **k: {
        "_http": 400, "error": {"type": "Invalid", "description": "amount invalido"}})
    r = nuvei.preparar(ident="a", monto_usd=1, concepto="c", email="a@b.ec",
                       success_url="s", failure_url="f")
    assert r == {"ok": False, "error": "amount invalido"}


def _webhook(status="1", firma=None, monto=12.5):
    tid, uid = "CB-123", "ana@mail.ec"
    return {"transaction": {
        "status": status, "id": tid, "dev_reference": "abc123", "amount": monto,
        "authorization_code": "AUT1", "application_code": "PCG-EC-SERVER",
        "stoken": firma or nuvei.stoken_esperado(tid, uid)},
        "user": {"id": uid, "email": uid}}


def test_webhook_valido_aprobado():
    r = nuvei.leer_webhook(_webhook())
    assert r["ok"] and r["aprobado"] and r["ident"] == "abc123"
    assert r["transaction_id"] == "CB-123" and r["monto_centavos"] == 1250
    assert r["estado"] == "aprobado"


def test_webhook_firma_mala_o_rechazado():
    assert nuvei.leer_webhook(_webhook(firma="0" * 32))["error"] == "firma_invalida"
    assert nuvei.leer_webhook({"x": 1})["error"] == "sin_transaccion"
    r = nuvei.leer_webhook(_webhook(status="4"))
    assert r["ok"] and not r["aprobado"] and r["estado"] == "rechazado"


def test_verificar_y_reembolsar(monkeypatch):
    def falso(metodo, url, payload=None):
        if metodo == "GET":
            return {"transaction": {"status": "1", "id": "CB-9", "amount": 3,
                                    "dev_reference": "z"}}
        return {"status": "success", "detail": "ok"}
    monkeypatch.setattr(nuvei, "_http", falso)
    v = nuvei.verificar("CB-9")
    assert v["aprobado"] and v["monto_centavos"] == 300
    assert nuvei.reembolsar(transaction_id="CB-9", monto_centavos=150)["ok"]
    monkeypatch.setattr(nuvei, "_http", lambda *a, **k: {"status": "failure"})
    assert not nuvei.reembolsar(transaction_id="CB-9")["ok"]
