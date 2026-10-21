"""Fixtures comunes de la suite."""
import os

# La suite se escribió con la marca "Pichangol" en sus asserts. Desde el
# 21-oct-2026 la marca por defecto es CanchaLibre (www.canchalibre.pe); los
# tests fijan la vieja por variable ANTES de importar la app, y
# `test_marca_configurable.py` prueba aparte el valor por defecto y otra marca.
os.environ.setdefault("MARCA_NOMBRE", "Pichangol")
os.environ.setdefault("MARCA_DOMINIO", "www.pichangol.app")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _sin_canchas_osm(monkeypatch):
    """Las canchas de OpenStreetMap (`web/osm.py`) se APAGAN por defecto en los
    tests: así los tests de Google/cosecha siguen comparando listas exactas.
    `tests/test_canchas_osm.py` pone sus propios datos."""
    from web import osm
    monkeypatch.setattr(osm, "_datos", ("", []))


@pytest.fixture(autouse=True)
def _academias_en_los_tres_paises(monkeypatch):
    """Las academias se ocultan en BO/EC por defecto en producción
    (`acad_paises`="PE"); la suite las habilita en los tres países para seguir
    probando los cobros en $/Bs. `test_academias_ocultas_en_bolivia_y_ecuador`
    prueba la regla real."""
    from db.store import stores
    monkeypatch.setitem(stores.config, "acad_paises", "PE,EC,BO")
