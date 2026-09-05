"""Verificación de identidad por DNI con la regla anti-fraude 1 DNI = 1 cuenta."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "test-admin")
    # Simula Factiliza OK (no llamamos a la API real en tests).
    from propiedad import identidad
    monkeypatch.setattr(identidad, "consultar_dni", lambda dni: {
        "ok": True, "dni": dni, "nombre_completo": "Ana Pérez",
        "fecha_nacimiento": "01/01/1990"})
    yield


def test_verificar_dni_un_dni_una_cuenta():
    # 1ª cuenta: verifica OK.
    r1 = client.post("/propiedad/verificar-dni",
                     json={"dni": "12345678", "email": "ana@x.com"}).json()
    assert r1["ok"] is True and r1["fecha_nacimiento"] == "01/01/1990"
    # Misma cuenta, mismo DNI: idempotente, sigue OK.
    r2 = client.post("/propiedad/verificar-dni",
                     json={"dni": "12345678", "email": "ana@x.com"}).json()
    assert r2["ok"] is True
    # OTRA cuenta con el MISMO DNI: rechazado (anti-fraude).
    r3 = client.post("/propiedad/verificar-dni",
                     json={"dni": "12345678", "email": "otro@x.com"}).json()
    assert r3["ok"] is False and r3["error"] == "dni_en_uso"


def test_verificar_dni_otro_dni_si_puede():
    client.post("/propiedad/verificar-dni",
                json={"dni": "12345678", "email": "ana@x.com"})
    # Otra persona con OTRO DNI en otra cuenta: OK.
    r = client.post("/propiedad/verificar-dni",
                    json={"dni": "87654321", "email": "otro@x.com"}).json()
    assert r["ok"] is True


def test_admin_revocar_dni_libera_para_reverificar():
    tok = {"X-Admin-Token": "test-admin"}
    # Ana verifica; otro queda bloqueado con el mismo DNI.
    client.post("/propiedad/verificar-dni",
                json={"dni": "12345678", "email": "ana@x.com"})
    bloq = client.post("/propiedad/verificar-dni",
                       json={"dni": "12345678", "email": "otro@x.com"}).json()
    assert bloq["error"] == "dni_en_uso"
    # El admin revoca la verificación de Ana → libera el DNI.
    rev = client.post("/admin/api/dni/revocar",
                      json={"email": "ana@x.com"}, headers=tok).json()
    assert rev["ok"] is True and rev["revocados"] == 1
    # Ahora la cuenta correcta sí puede verificar ese DNI.
    ok = client.post("/propiedad/verificar-dni",
                     json={"dni": "12345678", "email": "otro@x.com"}).json()
    assert ok["ok"] is True
    # Y aparece en el listado del panel.
    lst = client.get("/admin/api/dni/verificaciones", headers=tok).json()
    assert lst["total"] == 1
    assert any(c["email"] == "otro@x.com" for c in lst["cuentas"])
