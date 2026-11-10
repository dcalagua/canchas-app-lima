"""Concierge de reservas: el fallback heurístico (sin ANTHROPIC_API_KEY) filtra
por deporte y ordena por distancia. Es lo que se puede probar sin llamar a la
IA real; la ruta con Claude se ejercita en vivo con la key configurada."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from concierge import service  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _sin_ia(monkeypatch):
    # Fuerza el carril heurístico (sin key) y sin exigir X-App-Key.
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    yield


@pytest.fixture
def client():
    return TestClient(app)


_CANCHAS = [
    {"id": "t1", "nombre": "Tenis Lejos", "deporte": "tenis", "distanciaKm": 8.0},
    {"id": "f1", "nombre": "Fútbol Lejos", "deporte": "futbol", "distanciaKm": 5.0},
    {"id": "f2", "nombre": "Fútbol Cerca", "deporte": "futbol", "distanciaKm": 1.2},
]


def test_fallback_filtra_por_deporte_y_ordena_por_distancia(client):
    r = client.post(
        "/concierge/reservas",
        json={"mensaje": "quiero jugar futbol mañana a las 7pm", "canchas": _CANCHAS},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["via"] == "heuristica"
    assert data["intencion"]["deporte"] == "futbol"
    ids = [s["canchaId"] for s in data["sugerencias"]]
    # Solo canchas de fútbol, la más cercana primero, y sin la de tenis.
    assert ids == ["f2", "f1"]
    assert "t1" not in ids


def test_fallback_sin_deporte_ordena_por_distancia(client):
    r = client.post(
        "/concierge/reservas",
        json={"mensaje": "algo cerca para esta tarde", "canchas": _CANCHAS},
    )
    assert r.status_code == 200
    ids = [s["canchaId"] for s in r.json()["sugerencias"]]
    assert ids[0] == "f2"  # la más cercana (1.2 km) va primero


def test_deporte_detecta_pichanga():
    # "pichanga" es sinónimo de fútbol.
    assert service._deporte_en("armamos una pichanga?") == "futbol"
    assert service._deporte_en("cancha de pádel por Miraflores") == "padel"
    assert service._deporte_en("hola") is None


def test_zona_detecta_surco_y_prioriza_distrito(client):
    canchas = [
        {"id": "m1", "nombre": "Tenis Molina", "deporte": "tenis",
         "distrito": "La Molina", "distanciaKm": 2.0},
        {"id": "s1", "nombre": "Tenis Surco", "deporte": "tenis",
         "distrito": "Surco", "distanciaKm": 6.0},
    ]
    r = client.post(
        "/concierge/reservas",
        json={"mensaje": "cancha de tenis por Surco", "canchas": canchas},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["intencion"]["zona"] == "Surco"
    # Aunque la de La Molina está más cerca del centro, se prioriza el distrito Surco.
    assert data["sugerencias"][0]["canchaId"] == "s1"
    assert "Surco" in data["sugerencias"][0]["motivo"]


def test_app_key_exigida_si_configurada(client, monkeypatch):
    monkeypatch.setattr(config, "APP_API_KEY", "clave-app")
    # Sin la cabecera → 401.
    r = client.post("/concierge/reservas", json={"mensaje": "futbol", "canchas": []})
    assert r.status_code == 401
    # Con la cabecera correcta → 200.
    r = client.post(
        "/concierge/reservas",
        json={"mensaje": "futbol", "canchas": []},
        headers={"X-App-Key": "clave-app"},
    )
    assert r.status_code == 200
