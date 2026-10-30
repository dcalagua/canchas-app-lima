"""RECARGAS POR QR (Yape directo): solicitud del usuario + aprobación del
operador en la torre (acredita saldo, registra pago, idempotente)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import main  # noqa: E402
from db.store import stores  # noqa: E402

cli = TestClient(main.app)
_ADMIN = {"X-Admin-Token": "tok_admin"}


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok_admin",
                        raising=False)
    yield


def _crear(email="ana@x.com", monto=50.0):
    return cli.post("/pagos/recarga-qr",
                    json={"email": email, "monto_soles": monto,
                          "foto_url": "http://x/constancia.jpg"})


def test_config_apagada_sin_qr(monkeypatch):
    monkeypatch.setattr(config, "RECARGA_YAPE_QR_URL", "", raising=False)
    r = cli.get("/pagos/recarga-qr/config")
    assert r.status_code == 200 and r.json()["activo"] is False
    monkeypatch.setattr(config, "RECARGA_YAPE_QR_URL", "http://x/qr.png",
                        raising=False)
    assert cli.get("/pagos/recarga-qr/config").json()["activo"] is True


def test_solicitud_y_una_pendiente_por_usuario():
    r = _crear()
    assert r.status_code == 200 and r.json()["ok"]
    # Segunda pendiente del mismo usuario → rechazada con la existente.
    r2 = _crear()
    assert r2.json()["ok"] is False
    assert r2.json()["error"] == "ya_tienes_una_pendiente"
    # El estado del usuario la muestra.
    est = cli.get("/pagos/recarga-qr/estado/ana@x.com").json()
    assert len(est["solicitudes"]) == 1
    assert est["solicitudes"][0]["estado"] == "pendiente"


def test_aprobar_acredita_e_idempotente():
    sid = _crear(monto=80.0).json()["solicitud"]["id"]
    r = cli.post(f"/pagos/recarga-qr/{sid}/aprobar", headers=_ADMIN)
    assert r.status_code == 200 and r.json()["ok"]
    assert stores.saldo_centimos("ana@x.com") == 8000
    # El pago quedó en el libro con su medio.
    p = stores.pagos[-1]
    assert p.tipo == "recarga" and p.medio == "yape_qr"
    # Aprobar de nuevo NO acredita doble.
    r2 = cli.post(f"/pagos/recarga-qr/{sid}/aprobar", headers=_ADMIN)
    assert r2.json()["duplicada"] is True
    assert stores.saldo_centimos("ana@x.com") == 8000


def test_rechazar_no_acredita():
    sid = _crear().json()["solicitud"]["id"]
    r = cli.post(f"/pagos/recarga-qr/{sid}/rechazar",
                 json={"motivo": "monto_no_coincide"}, headers=_ADMIN)
    assert r.status_code == 200 and r.json()["ok"]
    assert stores.saldo_centimos("ana@x.com") == 0
    est = cli.get("/pagos/recarga-qr/estado/ana@x.com").json()
    assert est["solicitudes"][0]["estado"] == "rechazada"
    # Tras el rechazo puede volver a intentar.
    assert _crear().json()["ok"] is True


def test_admin_lista_y_requiere_token():
    _crear()
    assert cli.get("/pagos/recargas-qr").status_code in (401, 503)
    r = cli.get("/pagos/recargas-qr", headers=_ADMIN)
    assert r.status_code == 200
    assert r.json()["pendientes"] == 1


def test_validaciones():
    assert cli.post("/pagos/recarga-qr",
                    json={"email": "", "monto_soles": 50}).status_code == 400
    assert cli.post("/pagos/recarga-qr",
                    json={"email": "a@x.com",
                          "monto_soles": 5000}).status_code == 400
