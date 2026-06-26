"""Webhook entrante de WhatsApp (Twilio): el admin aprueba/rechaza un reclamo
respondiendo el mensaje. Triple barrera: firma válida + remitente admin + código.
"""

import base64
import hashlib
import hmac
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from propiedad import reclamos  # noqa: E402

client = TestClient(app)
ADMIN = "+51999888777"
TOKEN = "testtoken"
URL = "http://testserver/propiedad/webhook/whatsapp"


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", ADMIN)
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", "")
    # Sin remitente/SID configurados -> no se envía WhatsApp real al crear.
    monkeypatch.setattr(config, "TWILIO_WHATSAPP_FROM", "")
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "")
    yield


def _firma(url: str, params: dict) -> str:
    base = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    mac = hmac.new(TOKEN.encode(), base.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


def _crear():
    return reclamos.crear_reclamo("c1", "due@x.com", "La Pichanga",
                                  telefono_contacto="987654321",
                                  lat=-12.04, lng=-76.95)


def _post(params):
    return client.post("/propiedad/webhook/whatsapp", data=params,
                       headers={"X-Twilio-Signature": _firma(URL, params)})


def test_aprobar_por_codigo_activa_la_cancha():
    r = _crear()
    out = reclamos.aprobar_por_codigo(r["codigo"], "admin")
    assert out["ok"] and out["estado"] == "activada"
    assert stores.cancha("c1").verificada is True


def test_webhook_aprueba_con_firma_y_admin():
    r = _crear()
    resp = _post({"From": f"whatsapp:{ADMIN}", "Body": f"APROBAR {r['codigo']}"})
    assert resp.status_code == 200
    assert "ACTIVADA" in resp.text
    assert stores.cancha("c1").verificada is True


def test_webhook_rechaza_firma_invalida():
    r = _crear()
    resp = client.post(
        "/propiedad/webhook/whatsapp",
        data={"From": f"whatsapp:{ADMIN}", "Body": f"APROBAR {r['codigo']}"},
        headers={"X-Twilio-Signature": "firma-falsa"},
    )
    assert resp.status_code == 403
    assert stores.cancha("c1").verificada is False


def test_webhook_rechaza_remitente_no_admin():
    r = _crear()
    resp = _post({"From": "whatsapp:+51000000000",
                  "Body": f"APROBAR {r['codigo']}"})
    assert resp.status_code == 403
    assert stores.cancha("c1").verificada is False


def test_webhook_rechazar_reclamo():
    r = _crear()
    resp = _post({"From": f"whatsapp:{ADMIN}", "Body": f"RECHAZAR {r['codigo']}"})
    assert resp.status_code == 200
    assert "RECHAZADO" in resp.text
    assert reclamos.estado("c1")["estado"] == "rechazada"


def test_webhook_codigo_inexistente():
    _crear()
    resp = _post({"From": f"whatsapp:{ADMIN}", "Body": "APROBAR 000000"})
    assert resp.status_code == 200
    assert "No encontré" in resp.text
