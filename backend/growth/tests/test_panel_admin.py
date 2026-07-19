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
    from propiedad import router as _router
    stores.reset()
    _router._rate_hits.clear()  # aísla el rate-limit entre tests
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
    # Fase 2: el panel incluye la sección de liquidaciones a dueños.
    assert "cargarLiquidaciones" in r.text
    assert "Liquidaciones por pagar a dueños" in r.text
    assert "/pagos/liquidaciones/pendientes" in r.text


def test_flujo_liquidacion_desde_panel(client):
    # El operador (panel) usa los endpoints de pagos con X-Admin-Token.
    h = {"X-Admin-Token": TOKEN}
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "r_panel"})
    pend = client.get("/pagos/liquidaciones/pendientes", headers=h).json()
    assert len(pend["pendientes"]) == 1
    ok = client.post("/pagos/liquidaciones/r_panel/pagar", headers=h,
                     json={"metodo": "yape", "referencia": "OP9"}).json()
    assert ok["liquidado"] is True
    # Sin token → 401 (protegido).
    assert client.get("/pagos/liquidaciones/pendientes").status_code == 401


def test_aprobar_por_http_exige_token_admin(client):
    """La administración vive en la torre de control web (no en el APK): aprobar
    por /propiedad exige X-Admin-Token. Sin token NO activa (era un hueco de
    seguridad: cualquiera se auto-aprobaba)."""
    r = _reclamo()
    # Sin token -> 401 y la cancha NO se activa.
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/aprobar",
                      json={"aprobado": True, "revisor": "x"})
    assert res.status_code == 401
    assert stores.cancha("c1").verificada is False
    # Con token -> activa.
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/aprobar",
                      json={"aprobado": True, "revisor": "dennis"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "activada"
    assert stores.cancha("c1").verificada is True
    # El GET de estado que consulta la app SIGUE público.
    est = client.get("/propiedad/reclamo/c1")
    assert est.status_code == 200 and est.json()["verificada"] is True


def test_reclamos_con_datos_personales_exige_token(client):
    """GET /propiedad/reclamos expone DNI/teléfono/GPS: debe exigir token
    (Ley 29733). Sin token -> 401."""
    _reclamo()
    assert client.get("/propiedad/reclamos").status_code == 401
    r = client.get("/propiedad/reclamos", headers={"X-Admin-Token": TOKEN})
    assert r.status_code == 200 and len(r.json()) == 1


def test_app_key_gatea_endpoints_publicos(client, monkeypatch):
    """Con APP_API_KEY configurada, los endpoints públicos exigen X-App-Key
    (solo el APK oficial): un cliente externo sin la clave recibe 401."""
    monkeypatch.setattr(config, "APP_API_KEY", "clave-app")
    body = {"cancha_id": "cX", "solicitante_id": "d@x.com", "nombre_local": "L"}
    # Sin clave -> 401.
    assert client.post("/propiedad/reclamo", json=body).status_code == 401
    # Con clave -> 200.
    r = client.post("/propiedad/reclamo", json=body,
                    headers={"X-App-Key": "clave-app"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_sin_app_key_configurada_no_se_exige(client, monkeypatch):
    """Rollout gradual: si APP_API_KEY está vacía, no se exige (no rompe apps
    ya instaladas que aún no mandan la clave)."""
    monkeypatch.setattr(config, "APP_API_KEY", "")
    body = {"cancha_id": "cY", "solicitante_id": "d@x.com", "nombre_local": "L"}
    assert client.post("/propiedad/reclamo", json=body).status_code == 200


def test_rate_limit_corta_el_spam_de_reclamos(client, monkeypatch):
    """Con un límite bajo, tras N reclamos desde la misma IP el siguiente da 429."""
    monkeypatch.setattr(config, "RECLAMO_RATE_LIMIT", 3)
    monkeypatch.setattr(config, "APP_API_KEY", "")  # no exige clave en este test
    body = {"cancha_id": "c", "solicitante_id": "d@x.com", "nombre_local": "L"}
    codes = [client.post("/propiedad/reclamo", json={**body, "cancha_id": f"c{i}"})
             .status_code for i in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_triage_solo_no_activa(client):
    """Contraste: el triage clásico aprueba pero NO activa. Ahora exige token."""
    r = _reclamo()
    res = client.post(f"/propiedad/reclamo/{r['reclamo_id']}/triage",
                      json={"aprobado": True, "revisor": "dennis"},
                      headers={"X-Admin-Token": TOKEN})
    assert res.status_code == 200 and res.json()["estado"] == "aprobado_triage"
    assert stores.cancha("c1").verificada is False
