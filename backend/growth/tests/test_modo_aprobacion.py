"""Modo de aprobación configurable: 'marcha_blanca' (actual, activa al instante)
vs 'nuevo_flujo' (exige validación en sitio). Global + override por cancha."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from propiedad import reclamos  # noqa: E402

LAT, LNG = -12.0432, -76.9540


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", "")
    monkeypatch.setattr(config, "VALIDADOR_ACTIVA_AUTOMATICO", True)
    yield


def _crear(cancha_id="c1"):
    # Sin lat/lng: cada cancha_id es un lugar distinto (este test es sobre el
    # modo de aprobación, no sobre la ubicación).
    return reclamos.crear_reclamo(cancha_id, "due@x.com", "La Pichanga")


def test_default_es_marcha_blanca():
    assert stores.modo_aprobacion("c1") == "marcha_blanca"
    assert reclamos.config_modo()["global"] == "marcha_blanca"


def test_marcha_blanca_aprobar_directo_activa_al_instante():
    r = _crear()
    out = reclamos.aprobar_directo(r["reclamo_id"], "dennis")
    assert out["estado"] == "activada" and out["verificada"] is True
    assert stores.cancha("c1").verificada is True


def test_nuevo_flujo_aprobar_no_activa_y_exige_validacion_en_sitio():
    reclamos.set_modo_global("nuevo_flujo")
    r = _crear()
    out = reclamos.aprobar_directo(r["reclamo_id"], "dennis")
    assert out["estado"] == "pendiente_validacion"
    assert out["verificada"] is False
    assert out["requiere_validacion_sitio"] is True
    # No activa hasta validar en sitio con GPS coincidente.
    assert stores.cancha("c1").verificada is False
    val = reclamos.validar_en_sitio(r["codigo"], LAT + 0.0003, LNG, "moto1")
    assert val["ok"] and val["estado"] == "activada"
    assert stores.cancha("c1").verificada is True


def test_override_por_cancha_manda_sobre_el_global():
    # Global marcha_blanca, pero c2 con nuevo_flujo por override.
    reclamos.set_modo_global("marcha_blanca")
    reclamos.set_modo_cancha("c2", "nuevo_flujo")
    r1 = _crear("c1")
    r2 = _crear("c2")
    assert reclamos.aprobar_directo(r1["reclamo_id"])["estado"] == "activada"
    assert reclamos.aprobar_directo(r2["reclamo_id"])["estado"] == "pendiente_validacion"
    assert stores.cancha("c1").verificada is True
    assert stores.cancha("c2").verificada is False


def test_limpiar_override_vuelve_al_global():
    reclamos.set_modo_cancha("c2", "nuevo_flujo")
    assert stores.modo_aprobacion("c2") == "nuevo_flujo"
    reclamos.set_modo_cancha("c2", None)
    assert stores.modo_aprobacion("c2") == "marcha_blanca"


def test_modo_invalido_se_rechaza():
    assert reclamos.set_modo_global("xxx")["ok"] is False
    assert stores.cfg("modo_aprobacion") == "marcha_blanca"


def test_config_se_persiste_en_snapshot():
    reclamos.set_modo_global("nuevo_flujo")
    reclamos.set_modo_cancha("c9", "marcha_blanca")
    estado = stores.to_state()
    stores.load_state(estado)
    assert stores.cfg("modo_aprobacion") == "nuevo_flujo"
    assert stores.modo_aprobacion_overrides.get("c9") == "marcha_blanca"
