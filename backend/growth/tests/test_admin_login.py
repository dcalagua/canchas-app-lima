"""Login usuario+contraseña de la torre de control (/admin/api/login)."""

import time

from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from propiedad import admin_auth
from propiedad import panel as panel_mod

client = TestClient(app)


def _config_panel(monkeypatch, usuarios="admin@ebim.pe:clave123", dos_pasos="0"):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok-secreto")
    monkeypatch.setattr(config, "ADMIN_PANEL_USUARIOS", usuarios)
    monkeypatch.setattr(config, "ADMIN_2FA", dos_pasos)
    panel_mod._intentos.clear()
    admin_auth._ultimo_contador.clear()
    admin_auth._enrolando.clear()
    for k in [k for k in list(stores.config) if k.startswith("admin_2fa_") or k.startswith("admin_disp_")]:
        stores.config.pop(k, None)
    stores.admin_accesos.clear()


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


# ── Verificación en dos pasos (TOTP) ─────────────────────────────────────────
def _login(usuario="admin@ebim.pe", clave="clave123", **extra):
    return client.post("/admin/api/login", json={"usuario": usuario, "clave": clave, **extra})


def test_dos_pasos_enrola_con_qr_y_entra_con_codigo_de_la_app(monkeypatch):
    """Primer ingreso: contraseña OK → QR + secreto → código de la app → sesión +
    8 códigos de recuperación. Segundo ingreso: contraseña → pide código → sesión."""
    _config_panel(monkeypatch, dos_pasos="1")
    r = _login()
    assert r.status_code == 200
    j = r.json()
    assert j["paso"] == "enrolar" and "token" not in j
    assert j["otpauth"].startswith("otpauth://totp/") and "secret=" + j["secreto"] in j["otpauth"]
    assert j["qr"].startswith("data:image/png;base64,")
    pre, secreto = j["pre"], j["secreto"]
    # El pre-token NO sirve como sesión.
    assert client.get("/admin/api/sesion", headers={"X-Admin-Token": pre}).status_code == 401
    # Código incorrecto → 401 y sigue sin enrolar.
    assert client.post("/admin/api/login/2fa", json={"pre": pre, "codigo": "000000"}).status_code == 401
    assert not admin_auth.enrolado("admin@ebim.pe")
    # Código correcto (el que mostraría la app) → sesión + códigos de recuperación.
    codigo = admin_auth.totp_codigo(secreto, int(time.time() // admin_auth.TOTP_PASO))
    r2 = client.post("/admin/api/login/2fa", json={"pre": pre, "codigo": codigo, "recordar": True})
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert j2["paso"] == "ok" and j2["token"].startswith("s1.") and j2["dispositivo"].startswith("d1.")
    assert len(j2["recuperacion"]) == admin_auth.RECUPERACION_N and all("-" in c for c in j2["recuperacion"])
    assert client.get("/admin/api/sesion", headers={"X-Admin-Token": j2["token"]}).status_code == 200
    assert admin_auth.enrolado("admin@ebim.pe")
    # El secreto queda CIFRADO/ofuscado en el snapshot, nunca en claro.
    assert secreto not in (stores.config.get("admin_2fa_admin@ebim.pe") or "")
    # Segundo ingreso desde otro navegador: pide el código (ya no el QR).
    r3 = _login()
    assert r3.json()["paso"] == "codigo" and "secreto" not in r3.json()
    # El mismo código no se acepta dos veces (anti-reuso); el siguiente paso sí.
    admin_auth._ultimo_contador.clear()
    pre3 = r3.json()["pre"]
    assert client.post("/admin/api/login/2fa", json={"pre": pre3, "codigo": codigo}).status_code == 200
    assert client.post("/admin/api/login/2fa", json={"pre": pre3, "codigo": codigo}).status_code == 401
    # Dispositivo de confianza: entra directo sin código.
    r4 = _login(dispositivo=j2["dispositivo"])
    assert r4.json()["paso"] == "ok" and "token" in r4.json()
    # Código de recuperación: vale UNA vez.
    rec = j2["recuperacion"][0]
    pre5 = _login().json()["pre"]
    r5 = client.post("/admin/api/login/2fa", json={"pre": pre5, "codigo": rec.lower()})
    assert r5.status_code == 200 and r5.json()["recuperacion_usada"] and r5.json()["recuperacion_restantes"] == 7
    pre6 = _login().json()["pre"]
    assert client.post("/admin/api/login/2fa", json={"pre": pre6, "codigo": rec}).status_code == 401
    # Bitácora de accesos visible en Seguridad; olvidar dispositivos invalida el d1.
    seg = client.get("/admin/api/seguridad", headers={"X-Admin-Token": j2["token"]}).json()
    assert seg["yo"] == "admin@ebim.pe" and seg["usuarios"][0]["enrolado"] and seg["usuarios"][0]["recuperacion_restantes"] == 7
    assert any(a["evento"] == "enrolado" for a in seg["accesos"]) and any(a["evento"] == "2fa_mal" for a in seg["accesos"])
    assert client.post("/admin/api/seguridad/dispositivos/olvidar", headers={"X-Admin-Token": j2["token"]}).status_code == 200
    assert _login(dispositivo=j2["dispositivo"]).json()["paso"] == "codigo"
    # Restablecer (otro operador o el token clásico): vuelve a pedir el QR.
    r7 = client.post("/admin/api/seguridad/2fa/restablecer", json={"correo": "admin@ebim.pe"},
                     headers={"X-Admin-Token": "tok-secreto"})
    assert r7.status_code == 200
    assert _login().json()["paso"] == "enrolar"


def test_fuerza_bruta_por_ip_real_y_por_usuario(monkeypatch):
    """Railway pone la IP real en X-Forwarded-For (request.client es el proxy):
    el bloqueo es por esa IP y TAMBIÉN por usuario (rotar IPs no sirve)."""
    _config_panel(monkeypatch)
    for i in range(panel_mod.MAX_INTENTOS):
        r = client.post("/admin/api/login", json={"usuario": "admin@ebim.pe", "clave": "mala"},
                        headers={"X-Forwarded-For": f"200.1.1.{i}, 10.0.0.1"})
        assert r.status_code == 401
    # Otra IP, mismo usuario → bloqueado por usuario.
    r = client.post("/admin/api/login", json={"usuario": "admin@ebim.pe", "clave": "clave123"},
                    headers={"X-Forwarded-For": "200.9.9.9"})
    assert r.status_code == 429
    # Otro usuario desde una IP que ya falló 1 vez → sigue permitido (la IP no llegó al tope).
    r = client.post("/admin/api/login", json={"usuario": "otro@ebim.pe", "clave": "x"},
                    headers={"X-Forwarded-For": "200.1.1.0"})
    assert r.status_code == 401
    # El bloqueo se duplica en cada racha (60 s → 120 s …) hasta el tope.
    _, hasta, bloqueo = panel_mod._intentos["usr:admin@ebim.pe"]
    assert bloqueo == panel_mod.BLOQUEO_S and hasta > time.time()


def test_cabeceras_de_seguridad_y_token_solo_por_cabecera(monkeypatch):
    _config_panel(monkeypatch)
    r = client.get("/admin")
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Strict-Transport-Security"].startswith("max-age=")
    assert client.get("/admin/api/gate").headers["Cache-Control"] == "no-store"
    assert client.get("/admin/api/gate").json() == {"configurado": True, "usuarios": True, "dos_pasos": False}
    # /web/foto ya no acepta el token de admin en la URL (queda en logs e historial).
    from web import router as web_router
    import inspect
    assert " token: str" not in inspect.getsource(web_router.foto_web) and "x_admin_token" in inspect.getsource(web_router.foto_web)
