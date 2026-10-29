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
def _sin_limites_por_ip(monkeypatch):
    """Toda la suite pega desde la misma IP ('testclient'): los límites por IP
    de la web (`web/seguridad_web.py`) se prueban aparte, en su propio test."""
    from web import seguridad_web
    monkeypatch.setattr(seguridad_web, "ACTIVO", False)


def con_assets(cli, html: str) -> str:
    """HTML + el CSS y el JS compartidos que la página enlaza (ya no van en
    línea: se sirven versionados desde /web/a/)."""
    import re as _re
    extra = [cli.get(u).text for u in _re.findall(r"(/web/a/(?:estilo|nav)\.[0-9a-f]+\.(?:css|js))", html)]
    return html + "\n".join(extra)


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


@pytest.fixture(autouse=True)
def _liquidaciones_sin_exigir_cargo(monkeypatch, request):
    """La suite histórica de contabilidad registra liquidaciones sin un cobro
    real detrás; la regla de seguridad C2 (`liq_exige_cargo`, default "1" en
    producción) se prueba aparte en `test_liquidacion_segura.py` y en los
    tests marcados `cargo_real`."""
    if "cargo_real" in request.keywords or request.module.__name__.endswith(("test_liquidacion_segura", "test_web_reservas")):
        return
    from pagos import router as pr
    monkeypatch.setattr(pr, "_verificar_cargo_liquidacion", lambda req: "")
