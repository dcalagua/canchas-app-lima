"""Página pública del campeonato servida por el backend (`GET /c/{id}`)."""

from fastapi.testclient import TestClient

import config
from main import app
from marketing import campeonato_web

client = TestClient(app)


def test_sin_configuracion_avisa(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "")
    r = client.get("/c/camp_x")
    assert r.status_code == 503
    assert "text/html" in r.headers["content-type"]
    assert "no disponible" in r.text


def test_no_encontrado(monkeypatch):
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: None)
    r = client.get("/c/camp_x")
    assert r.status_code == 404
    assert "no existe" in r.text


def test_render_liga_html(monkeypatch):
    data = {
        "nombre": "Liga Este",
        "deporte": "tenis",
        "formato": "liga",
        "categoria": "Abierta",
        "moneda": "S/",
        "inscripcionAbierta": True,
        "costoInscripcion": 0,
        "participantes": [
            {"id": "p1", "nombre": "Ana"},
            {"id": "p2", "nombre": "Luis"},
        ],
        "partidos": [],
    }
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_1")
    assert r.status_code == 200
    # Content-Type correcto: era el bug de la Edge Function (texto plano).
    assert r.headers["content-type"].startswith("text/html")
    assert "charset=utf-8" in r.headers["content-type"]
    assert "Liga Este" in r.text
    assert "Ana" in r.text and "Luis" in r.text
    assert "Inscripciones abiertas" in r.text
    assert "<!doctype html>" in r.text


def test_tabla_ordena_por_puntos():
    c = {
        "participantes": [
            {"id": "a", "nombre": "A"},
            {"id": "b", "nombre": "B"},
        ],
        "partidos": [
            {"aId": "a", "bId": "b", "marcadorA": 2, "marcadorB": 1},
        ],
    }
    filas = campeonato_web._tabla(c)
    assert filas[0]["nombre"] == "A" and filas[0]["g"] == 1
    assert filas[1]["nombre"] == "B" and filas[1]["p"] == 1


def test_cta_unirse_en_la_app(monkeypatch):
    data = {"nombre": "Liga", "deporte": "tenis", "formato": "liga",
            "inscripcionAbierta": True, "participantes": [], "partidos": []}
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_9")
    assert "intent://c/camp_9" in r.text          # abre la app si está
    assert "browser_fallback_url" in r.text        # o lleva a descargarla
    assert "Unirme en la app" in r.text


def test_assetlinks(monkeypatch):
    monkeypatch.setattr(config, "ANDROID_CERT_SHA256", "")
    assert client.get("/.well-known/assetlinks.json").status_code == 404
    monkeypatch.setattr(config, "ANDROID_CERT_SHA256", "aa:bb")
    j = client.get("/.well-known/assetlinks.json").json()
    assert j[0]["target"]["package_name"] == "pe.ebim.pichangol"
    assert j[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB"]


def test_premios_y_auspiciador(monkeypatch):
    data = {"nombre": "Rally Challenge", "deporte": "tenis",
            "formato": "eliminacion", "inscripcionAbierta": True,
            "premios": "Trofeos\nTarros de pelotas",
            "auspiciador": "JORDI MEAT BOUTIQUE",
            "participantes": [], "partidos": []}
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_r")
    assert "Premios" in r.text and "Trofeos" in r.text
    assert "JORDI MEAT BOUTIQUE" in r.text
    assert "auspiciador oficial" in r.text
    assert 'property="og:title"' in r.text  # vista previa rica en WhatsApp
