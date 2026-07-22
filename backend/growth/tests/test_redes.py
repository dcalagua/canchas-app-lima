"""Gestión de redes (Nivel 2): conexión OAuth + publicación.

En modo sandbox (sin App Review de Meta) el flujo completo debe funcionar:
conectar → estado → publicar → desconectar, sin tocar ninguna red real y sin
exponer nunca el token del dueño.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from marketing import redes  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    # Sin credenciales de Meta → modo sandbox forzado (nunca OAuth a medias).
    monkeypatch.setattr(config, "META_MODO", "sandbox")
    monkeypatch.setattr(config, "META_APP_ID", "")
    monkeypatch.setattr(config, "META_APP_SECRET", "")
    monkeypatch.setattr(config, "APP_API_KEY", "")  # público en tests
    yield


@pytest.fixture
def client():
    import main
    return TestClient(main.app)


def test_modo_sandbox_sin_credenciales():
    assert config.meta_modo() == "sandbox"
    assert redes.modo() == "sandbox"


def test_produccion_requiere_credenciales(monkeypatch):
    # Aunque se pida producción, sin app_id/secret se cae a sandbox.
    monkeypatch.setattr(config, "META_MODO", "produccion")
    assert redes.modo() == "sandbox"


def test_login_url_usa_config_id_si_esta(monkeypatch):
    monkeypatch.setattr(config, "META_APP_ID", "123")
    monkeypatch.setattr(config, "META_REDIRECT_URI", "https://x/cb")
    # Con config_id (Facebook Login for Business): va config_id, no scope.
    monkeypatch.setattr(config, "META_LOGIN_CONFIG_ID", "cfg999")
    url = redes.login_url("acad-1")
    assert "config_id=cfg999" in url and "scope=" not in url
    # Sin config_id: cae al clásico con scope.
    monkeypatch.setattr(config, "META_LOGIN_CONFIG_ID", "")
    url2 = redes.login_url("acad-1")
    assert "scope=" in url2 and "config_id" not in url2


def test_cifrado_ida_vuelta():
    enc = redes.cifrar("token-secreto")
    assert "token-secreto" not in enc          # no queda en claro
    assert redes.descifrar(enc) == "token-secreto"


def test_conectar_estado_publicar_desconectar(client):
    aid = "acad-1"
    # 1) Estado inicial: desconectado.
    r = client.get(f"/marketing/redes/estado/{aid}")
    assert r.status_code == 200
    assert r.json()["conectado"] is False

    # 2) Conectar (sandbox simula la conexión).
    r = client.post("/marketing/redes/conectar",
                    json={"academia_id": aid, "dueno_id": "due@x.com"})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["modo"] == "sandbox"
    assert j["conexion"]["conectado"] is True

    # 3) Estado ahora conectado; NUNCA expone el token.
    r = client.get(f"/marketing/redes/estado/{aid}")
    body = r.json()
    assert body["conectado"] is True
    assert "token" not in body and "token_enc" not in body

    # 4) Publicar (simulado): FB ok; IG requiere imagen.
    r = client.post("/marketing/redes/publicar",
                    json={"academia_id": aid, "texto": "¡Inscripciones abiertas!"})
    assert r.status_code == 200
    pub = r.json()
    assert pub["ok"] is True
    assert pub["resultados"]["facebook"]["ok"] is True
    assert pub["resultados"]["instagram"]["ok"] is False  # sin imagen

    # con imagen, IG también publica.
    r = client.post("/marketing/redes/publicar",
                    json={"academia_id": aid, "texto": "Con foto",
                          "imagen_url": "https://x/y.jpg"})
    assert r.json()["resultados"]["instagram"]["ok"] is True

    # contador de publicaciones sube.
    assert stores.conexiones_redes[aid]["publicaciones"] == 2

    # 5) Desconectar.
    r = client.post("/marketing/redes/desconectar", json={"academia_id": aid})
    assert r.json()["ok"] is True
    assert client.get(f"/marketing/redes/estado/{aid}").json()["conectado"] is False


def test_publicar_sin_conexion_falla(client):
    r = client.post("/marketing/redes/publicar",
                    json={"academia_id": "x", "texto": "hola"})
    assert r.json()["ok"] is False
    assert r.json()["error"] == "no_conectado"


def test_catalogo_unificado(client):
    # "Gestión de redes" se unificó dentro de "Manejo de redes": ya no se ofrece
    # "gestion" en el catálogo, pero sí "redes".
    r = client.get("/pagos/servicios/planes")
    claves = {p["clave"] for p in r.json()["planes"]}
    assert "redes" in claves
    assert "gestion" not in claves


def test_subir_imagen_y_servirla(client):
    import base64
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n-demo").decode()
    r = client.post("/marketing/img",
                    json={"academia_id": "a1", "data_b64": png,
                          "content_type": "image/png"})
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.endswith(".png")
    # la sirve públicamente para el fetch de Meta.
    path = "/marketing/img/" + url.split("/marketing/img/")[1]
    rv = client.get(path)
    assert rv.status_code == 200
    assert rv.headers["content-type"].startswith("image/png")


def test_imagen_invalida_rechazada(client):
    r = client.post("/marketing/img",
                    json={"academia_id": "a1", "data_b64": "no-es-base64!!"})
    assert r.status_code == 400


def test_publicar_con_imagen_en_instagram(client):
    aid = "acad-ig"
    client.post("/marketing/redes/conectar", json={"academia_id": aid})
    import base64
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n-x").decode()
    url = client.post("/marketing/img",
                      json={"academia_id": aid, "data_b64": png,
                            "content_type": "image/png"}).json()["url"]
    r = client.post("/marketing/redes/publicar",
                    json={"academia_id": aid, "texto": "Con foto",
                          "imagen_url": url})
    res = r.json()["resultados"]
    assert res["facebook"]["ok"] is True
    assert res["instagram"]["ok"] is True
