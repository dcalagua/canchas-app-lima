"""Páginas legales + Data Deletion Callback de Meta (verifica firma y borra)."""

import base64
import hashlib
import hmac
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402


SECRET = "app-secret-de-prueba"


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "META_APP_SECRET", SECRET)
    yield


@pytest.fixture
def client():
    import main
    return TestClient(main.app)


def _signed_request(payload: dict, secret: str) -> str:
    p = base64.urlsafe_b64encode(
        json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), p.encode(), hashlib.sha256).digest()
    s = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{s}.{p}"


def test_paginas_publicas(client):
    for path in ("/legal/privacidad", "/legal/eliminacion-datos"):
        r = client.get(path)
        assert r.status_code == 200
        assert "Pichangol" in r.text


def test_callback_borra_conexion_del_usuario(client):
    # Simula una conexión de un usuario de Meta.
    stores.conexiones_redes["ac1"] = {
        "academia_id": "ac1", "estado": "conectado", "meta_user_id": "USER123"}
    stores.conexiones_redes["ac2"] = {
        "academia_id": "ac2", "estado": "conectado", "meta_user_id": "OTRO"}

    sr = _signed_request({"user_id": "USER123"}, SECRET)
    r = client.post("/legal/eliminacion-datos",
                    data={"signed_request": sr},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    j = r.json()
    assert j["confirmation_code"].startswith("del_")
    assert "/legal/eliminacion-datos/estado" in j["url"]
    # Borró la del usuario USER123, no la del otro.
    assert "ac1" not in stores.conexiones_redes
    assert "ac2" in stores.conexiones_redes

    # La página de estado responde.
    assert client.get("/legal/eliminacion-datos/estado",
                      params={"code": j["confirmation_code"]}).status_code == 200


def test_callback_rechaza_firma_invalida(client):
    stores.conexiones_redes["ac1"] = {
        "academia_id": "ac1", "estado": "conectado", "meta_user_id": "USER123"}
    # Firmado con otro secreto → no valida → no borra.
    sr = _signed_request({"user_id": "USER123"}, "secreto-equivocado")
    r = client.post("/legal/eliminacion-datos",
                    data={"signed_request": sr},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200  # responde igual (formato Meta)
    assert "ac1" in stores.conexiones_redes  # pero NO borró
