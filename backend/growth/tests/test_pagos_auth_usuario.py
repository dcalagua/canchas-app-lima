"""AUTH POR USUARIO de la billetera (endurecimiento PROD): con
PAGOS_AUTH_USUARIO=1, saldo/movimientos/reset exigen el ID token de Google del
PROPIO usuario; apagado (default), todo sigue como en el piloto."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import main  # noqa: E402
from db.store import stores  # noqa: E402
from pagos import router as pagos_router  # noqa: E402

cli = TestClient(main.app)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    yield


def test_apagado_no_exige_token():
    r = cli.get("/pagos/saldo/ana@x.com")
    assert r.status_code == 200
    r2 = cli.get("/pagos/movimientos/ana@x.com")
    assert r2.status_code == 200


def test_prendido_sin_token_es_403(monkeypatch):
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "1", raising=False)
    assert cli.get("/pagos/saldo/ana@x.com").status_code == 403
    assert cli.get("/pagos/movimientos/ana@x.com").status_code == 403
    r = cli.post("/pagos/reset-mi-billetera",
                 json={"dueno_id": "ana@x.com"})
    assert r.status_code == 403


def test_prendido_token_del_propio_usuario_pasa(monkeypatch):
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "1", raising=False)
    monkeypatch.setattr(pagos_router, "_email_de_token",
                        lambda t: "ana@x.com" if t == "tok_ana" else None)
    ok = cli.get("/pagos/saldo/ana@x.com",
                 headers={"X-User-Token": "tok_ana"})
    assert ok.status_code == 200
    # Token válido pero de OTRO usuario → 403 (no mira billeteras ajenas).
    mal = cli.get("/pagos/saldo/otro@x.com",
                  headers={"X-User-Token": "tok_ana"})
    assert mal.status_code == 403
    # Token inválido → 403.
    inv = cli.get("/pagos/movimientos/ana@x.com",
                  headers={"X-User-Token": "cualquiera"})
    assert inv.status_code == 403
    # Reset: solo su propia billetera.
    r = cli.post("/pagos/reset-mi-billetera",
                 json={"dueno_id": "ana@x.com"},
                 headers={"X-User-Token": "tok_ana"})
    assert r.status_code == 200
    r2 = cli.post("/pagos/reset-mi-billetera",
                  json={"dueno_id": "otro@x.com"},
                  headers={"X-User-Token": "tok_ana"})
    assert r2.status_code == 403


def test_case_insensitive_en_correo(monkeypatch):
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "1", raising=False)
    monkeypatch.setattr(pagos_router, "_email_de_token",
                        lambda t: "ana@x.com")
    ok = cli.get("/pagos/saldo/Ana@X.com", headers={"X-User-Token": "t"})
    assert ok.status_code == 200
