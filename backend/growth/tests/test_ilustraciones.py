"""ILUSTRACIONES de marca (estados vacíos del APK): catálogo y fail-safe."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import main  # noqa: E402
from marketing import ilustracion  # noqa: E402

cli = TestClient(main.app)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    monkeypatch.setattr(ilustracion, "_cache", {})
    yield


def test_claves_del_catalogo():
    # Las claves que usa el APK existen en el catálogo.
    for clave in ("billetera_vacia", "puntos_vacio", "bodega_vacia",
                  "pedidos_vacio", "cuentas_vacio", "reservas_vacias",
                  "clases_vacias", "entrenador_vacio"):
        assert clave in ilustracion.claves()


def test_sin_proveedor_es_404(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "REPLICATE_API_TOKEN", "", raising=False)
    monkeypatch.setattr(ilustracion, "_storage_leer", lambda c: None)
    assert cli.get("/ilustracion/billetera_vacia").status_code == 404
    # Clave desconocida → 404 siempre.
    assert cli.get("/ilustracion/loquesea").status_code == 404


def test_cacheada_se_sirve(monkeypatch):
    monkeypatch.setattr(ilustracion, "_cache",
                        {"billetera_vacia": b"JPEGFALSO"})
    r = cli.get("/ilustracion/billetera_vacia")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == b"JPEGFALSO"
    assert "max-age=604800" in r.headers.get("cache-control", "")
