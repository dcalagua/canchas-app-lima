"""PANEL WEB de administración (piloto): protegido por token y con aprobación
DIRECTA (al aprobar, la cancha queda activa sin validación en sitio)."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from propiedad import reclamos  # noqa: E402

TOKEN = "secreto-piloto"


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", "")  # no envía nada
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", TOKEN)
    yield


@pytest.fixture
def client():
    import main  # importa la app ya con routers incluidos
    return TestClient(main.app)


def _reclamo():
    return reclamos.crear_reclamo("c1", "due@x.com", "La Pichanga",
                                  telefono_contacto="987654321",
                                  dni="12345678", relacion="dueño")


def test_aprobar_directo_activa_la_cancha_sin_validacion_en_sitio():
    r = _reclamo()
    out = reclamos.aprobar_directo(r["reclamo_id"], revisor="dennis")
    assert out["ok"] and out["estado"] == "activada"
    c = stores.cancha("c1")
    assert c.verificada is True
    assert c.metodo_verificacion == "panel_admin"
    # Aprobación directa NO es verificación en persona.
    assert c.verificada_en_persona is False


def test_panel_requiere_token(client):
    _reclamo()
    # Sin token -> 401.
    assert client.get("/admin/api/reclamos").status_code == 401
    # Token equivocado -> 401.
    r = client.get("/admin/api/reclamos", headers={"X-Admin-Token": "malo"})
    assert r.status_code == 401
    # Token correcto -> 200.
    r = client.get("/admin/api/reclamos", headers={"X-Admin-Token": TOKEN})
    assert r.status_code == 200 and len(r.json()) == 1


def test_panel_sin_token_configurado_responde_503(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "")
    r = client.get("/admin/api/reclamos", headers={"X-Admin-Token": "loquesea"})
    assert r.status_code == 503


def test_decidir_aprobar_por_http_activa(client):
    r = _reclamo()
    res = client.post(f"/admin/api/reclamo/{r['reclamo_id']}/decidir",
                      json={"aprobado": True, "revisor": "panel"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "activada"
    assert stores.cancha("c1").verificada is True


def test_decidir_rechazar_por_http(client):
    r = _reclamo()
    res = client.post(f"/admin/api/reclamo/{r['reclamo_id']}/decidir",
                      json={"aprobado": False, "revisor": "panel"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "rechazada"
    assert stores.cancha("c1").verificada is False


def test_pagina_panel_se_sirve(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Pichangol" in r.text and "Panel de administración" in r.text


def test_endpoint_aprobar_directo_de_la_app_activa(client):
    """El boton 'Aprobar' del panel admin DENTRO de la app activa la cancha
    (verificada=True), igual que el panel web. Sin token (uso interno app)."""
    r = _reclamo()
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/aprobar",
                      json={"aprobado": True, "revisor": "dennis"})
    assert res.status_code == 200 and res.json()["estado"] == "activada"
    assert stores.cancha("c1").verificada is True
    # Y el estado que consulta la app refleja verificada=True.
    est = client.get("/propiedad/reclamo/c1")
    assert est.status_code == 200 and est.json()["verificada"] is True


def test_triage_solo_no_activa(client):
    """Contraste: el triage clasico aprueba pero NO activa (verificada sigue
    False). Por eso el boton de la app ahora usa /aprobar, no /triage."""
    r = _reclamo()
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/triage",
                      json={"aprobado": True, "revisor": "dennis"})
    assert res.status_code == 200 and res.json()["estado"] == "aprobado_triage"
    assert stores.cancha("c1").verificada is False
