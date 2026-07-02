"""Reclamo concierge + validación en sitio: el código y la coincidencia de GPS
son la prueba; la activación depende de la validación, no de un temporizador."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import ReclamoPropiedad, ahora, stores  # noqa: E402
from propiedad import reclamos  # noqa: E402

# Cancha de referencia en Lima (Ate, cerca de "La Pichanga").
LAT, LNG = -12.0432, -76.9540


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", "")  # no envía nada
    monkeypatch.setattr(config, "VALIDADOR_ACTIVA_AUTOMATICO", True)
    yield


def _crear():
    return reclamos.crear_reclamo("c1", "due@x.com", "La Pichanga",
                                  telefono_contacto="987654321",
                                  lat=LAT, lng=LNG)


def test_reclamo_nace_pendiente_triage_y_no_activa():
    r = _crear()
    assert r["ok"] and r["estado"] == "pendiente_triage"
    assert len(r["codigo"]) == 6
    # No reservable: la cancha no está verificada todavía.
    assert not stores.cancha("c1").verificada
    est = reclamos.estado("c1")
    assert est["estado"] == "pendiente_triage"
    assert est["panel_desbloqueado"] is False


def test_triage_aprueba_desbloquea_panel_pero_no_activa():
    r = _crear()
    reclamos.triage(r["reclamo_id"], aprobado=True, revisor="dennis")
    est = reclamos.estado("c1")
    assert est["estado"] == "aprobado_triage"
    assert est["panel_desbloqueado"] is True
    assert est["verificada"] is False  # aún falta validar en sitio


def test_validacion_en_sitio_con_gps_coincidente_activa_y_marca_en_persona():
    r = _crear()
    reclamos.triage(r["reclamo_id"], aprobado=True)
    reclamos.listo_para_validar(r["reclamo_id"])
    # Motorizado a ~30 m de la cancha → coincide.
    out = reclamos.validar_en_sitio(r["codigo"], LAT + 0.0003, LNG, "moto1")
    assert out["ok"] and out["estado"] == "activada"
    c = stores.cancha("c1")
    assert c.verificada is True and c.verificada_en_persona is True
    assert c.metodo_verificacion == "en_sitio"


def test_validacion_lejos_no_activa():
    r = _crear()
    reclamos.triage(r["reclamo_id"], aprobado=True)
    reclamos.listo_para_validar(r["reclamo_id"])
    # Motorizado a varios km → NO coincide.
    out = reclamos.validar_en_sitio(r["codigo"], LAT + 0.05, LNG, "moto1")
    assert not out["ok"] and out["error"] == "ubicacion_no_coincide"
    assert stores.cancha("c1").verificada is False


def test_codigo_invalido_no_valida():
    _crear()
    out = reclamos.validar_en_sitio("000000", LAT, LNG, "moto1")
    assert not out["ok"] and out["error"] == "codigo_invalido"


def test_modo_manual_no_activa_hasta_admin(monkeypatch):
    monkeypatch.setattr(config, "VALIDADOR_ACTIVA_AUTOMATICO", False)
    r = _crear()
    reclamos.triage(r["reclamo_id"], aprobado=True)
    reclamos.listo_para_validar(r["reclamo_id"])
    out = reclamos.validar_en_sitio(r["codigo"], LAT, LNG, "moto1")
    assert out["estado"] == "validada_pendiente_admin"
    assert stores.cancha("c1").verificada is False
    # El admin activa.
    reclamos.activar_admin(r["reclamo_id"])
    assert stores.cancha("c1").verificada is True


def test_crear_reclamo_duplicado_reutiliza_el_pendiente():
    """No debe ser posible tener dos reclamos pendientes para la misma cancha
    (p. ej. por 'reenviar solicitud' o un reintento de red)."""
    r1 = _crear()
    r2 = _crear()
    assert r2["reclamo_id"] == r1["reclamo_id"]
    assert r2["codigo"] == r1["codigo"]
    assert r2.get("reenviado") is True
    assert len([r for r in stores.reclamos if r.cancha_id == "c1"]) == 1


def test_aprobar_uno_cierra_duplicados_preexistentes():
    """Si ya existían dos reclamos pendientes para la misma cancha (datos de
    antes de la idempotencia), aprobar uno rechaza automáticamente al otro."""
    r1 = _crear()
    duplicado = ReclamoPropiedad(
        id=stores.next_id("reclamo"), cancha_id="c1", solicitante_id="due@x.com",
        nombre_local="La Pichanga", codigo="999999", estado="pendiente_triage",
        creado_en=ahora())
    stores.reclamos.append(duplicado)

    reclamos.aprobar_directo(r1["reclamo_id"], revisor="dennis")

    dup_actualizado = next(r for r in stores.reclamos if r.id == duplicado.id)
    assert dup_actualizado.estado == "rechazada"
    assert "Duplicado" in (dup_actualizado.nota or "")


def test_reclamo_se_persiste_en_snapshot():
    _crear()
    estado = stores.to_state()
    assert "reclamos" in estado and len(estado["reclamos"]) == 1
    # Roundtrip.
    stores.load_state(estado)
    assert len(stores.reclamos) == 1
