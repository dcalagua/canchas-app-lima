"""Login usuario+contraseña de la torre de control (/admin/api/login)."""

import time

from fastapi.testclient import TestClient

import config
from main import app
from propiedad import admin_auth
from propiedad import panel as panel_mod

client = TestClient(app)


def _config_panel(monkeypatch, usuarios="admin@ebim.pe:clave123"):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok-secreto")
    monkeypatch.setattr(config, "ADMIN_PANEL_USUARIOS", usuarios)
    panel_mod._intentos.clear()


def test_login_ok_y_sesion_valida(monkeypatch):
    _config_panel(monkeypatch)
    r = client.post("/admin/api/login",
                    json={"usuario": "Admin@ebim.pe", "clave": "clave123"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert token.startswith("s1.")
    # La sesión emitida sirve en los endpoints admin (X-Admin-Token).
    r2 = client.get("/admin/api/sesion", headers={"X-Admin-Token": token})
    assert r2.status_code == 200
    r3 = client.get("/propiedad/reclamos", headers={"X-Admin-Token": token})
    assert r3.status_code == 200


def test_login_clave_incorrecta(monkeypatch):
    _config_panel(monkeypatch)
    r = client.post("/admin/api/login",
                    json={"usuario": "admin@ebim.pe", "clave": "mala"})
    assert r.status_code == 401


def test_login_sin_usuarios_configurados(monkeypatch):
    _config_panel(monkeypatch, usuarios="")
    r = client.post("/admin/api/login",
                    json={"usuario": "admin@ebim.pe", "clave": "clave123"})
    assert r.status_code == 503
    assert r.json()["detail"] == "usuarios_no_configurados"


def test_token_clasico_sigue_valido(monkeypatch):
    _config_panel(monkeypatch)
    r = client.get("/admin/api/sesion", headers={"X-Admin-Token": "tok-secreto"})
    assert r.status_code == 200


def test_sesion_expirada_rechazada(monkeypatch):
    _config_panel(monkeypatch)
    token = admin_auth.crear_sesion("admin@ebim.pe")
    # Viaja al futuro: pasada la vigencia, la sesión ya no sirve.
    futuro = time.time() + admin_auth.SESION_HORAS * 3600 + 60
    monkeypatch.setattr(time, "time", lambda: futuro)
    assert not admin_auth.token_admin_valido(token)


def test_sesion_adulterada_rechazada(monkeypatch):
    _config_panel(monkeypatch)
    token = admin_auth.crear_sesion("admin@ebim.pe")
    # Estira la expiración sin re-firmar → la firma deja de cuadrar.
    partes = token.split(".")
    partes[2] = str(int(partes[2]) + 99999)
    assert not admin_auth.token_admin_valido(".".join(partes))


def test_fuerza_bruta_bloquea(monkeypatch):
    _config_panel(monkeypatch)
    for _ in range(panel_mod.MAX_INTENTOS):
        r = client.post("/admin/api/login",
                        json={"usuario": "admin@ebim.pe", "clave": "mala"})
        assert r.status_code == 401
    r = client.post("/admin/api/login",
                    json={"usuario": "admin@ebim.pe", "clave": "clave123"})
    assert r.status_code == 429  # bloqueado aunque la clave ya sea correcta
