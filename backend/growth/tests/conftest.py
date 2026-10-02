"""Fixtures comunes de la suite."""
import pytest


@pytest.fixture(autouse=True)
def _sin_canchas_osm(monkeypatch):
    """Las canchas de OpenStreetMap (`web/osm.py`) se APAGAN por defecto en los
    tests: así los tests de Google/cosecha siguen comparando listas exactas.
    `tests/test_canchas_osm.py` pone sus propios datos."""
    from web import osm
    monkeypatch.setattr(osm, "_datos", ("", []))
