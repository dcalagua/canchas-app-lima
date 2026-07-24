"""Circuito: onboarding de jugadores (declararse disponible para retar),
directorio filtrable y salida."""

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
    yield


def _unirse(email="ana@x.com", nombre="Ana", deporte="tenis", zona="San Borja",
            categoria="Intermedio"):
    return client.post("/circuito/unirse", json={
        "email": email, "nombre": nombre, "deporte": deporte,
        "zona": zona, "categoria": categoria}).json()


def test_unirse_y_aparece_en_directorio():
    r = _unirse()
    assert r["ok"] is True and r["jugador"]["email"] == "ana@x.com"
    js = client.get("/circuito/jugadores").json()["jugadores"]
    assert len(js) == 1 and js[0]["nombre"] == "Ana"


def test_directorio_filtra_por_deporte_y_zona():
    _unirse(email="ana@x.com", deporte="tenis", zona="San Borja")
    _unirse(email="luis@x.com", deporte="futbol", zona="Surco")
    solo_tenis = client.get("/circuito/jugadores?deporte=tenis").json()["jugadores"]
    assert [j["email"] for j in solo_tenis] == ["ana@x.com"]
    solo_surco = client.get("/circuito/jugadores?zona=Surco").json()["jugadores"]
    assert [j["email"] for j in solo_surco] == ["luis@x.com"]


def test_unirse_actualiza_no_duplica():
    _unirse(categoria="Intermedio")
    _unirse(categoria="Avanzado")
    js = client.get("/circuito/jugadores").json()["jugadores"]
    assert len(js) == 1 and js[0]["categoria"] == "Avanzado"


def test_perfil_y_salir():
    _unirse()
    assert client.get("/circuito/perfil/ana@x.com").json()["jugador"] is not None
    r = client.post("/circuito/salir", json={"email": "ana@x.com"}).json()
    assert r["ok"] is True and r["estaba"] is True
    assert client.get("/circuito/perfil/ana@x.com").json()["jugador"] is None
