"""Publicar en la página de Facebook de Pichangol desde la torre (sep-2026):
composición con fotos reales (bucket o adjuntas), plantillas rellenadas con el
local, vista previa, publicación por Graph (multipart) e historial."""
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import config
from main import app
from marketing import post_redes as pr

client = TestClient(app)
TOKEN = "adm-test"
H = {"X-Admin-Token": TOKEN}


def _jpeg(color, w=1400, h=900) -> bytes:
    b = io.BytesIO(); Image.new("RGB", (w, h), color).save(b, "JPEG"); return b.getvalue()


def _data_url(color) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(_jpeg(color)).decode()


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", TOKEN)
    monkeypatch.setattr(config, "FB_PAGE_ID", "")
    monkeypatch.setattr(config, "FB_PAGE_TOKEN", "")
    from db.store import stores
    stores.publicaciones_redes.clear()
    yield


def test_componer_con_fotos_reales_y_plantillas(monkeypatch):
    # Fotos https del bucket → se descargan desde el backend; adjuntas → data URL.
    original = pr._abrir_url
    with pytest.raises(ValueError):
        original("http://inseguro/x.jpg")  # solo https o adjuntas
    assert len(original(_data_url((1, 2, 3)))) > 100
    descargas = []
    monkeypatch.setattr(pr, "_abrir_url", lambda u: (descargas.append(u) or _jpeg((30, 90, 50))) if u.startswith("https://") else original(u))
    cancha = {"id": "u1", "club": "CEANDE Tennis Club", "barrio": "Lurigancho", "deporte": "tenis", "deportes": ["tenis"], "precio_hora": 15, "moneda": "S/"}
    assert pr.rellenar("nuevo_local", cancha, "subtitulo") == "CEANDE Tennis Club · Lurigancho"
    txt = pr.rellenar("promo", cancha, "texto")
    assert "CEANDE Tennis Club" in txt and "S/ 15" in txt and "/reservar/u1" in txt and "#Tenis" in txt
    assert pr.rellenar("lanzamiento", None, "titulo") == "¡Llegó Pichangol!"
    for n, (w, h) in ((1, (1080, 1080)), (2, (1080, 1080)), (3, (1080, 1080)), (4, (1080, 1080))):
        png = pr.componer(["https://x.supabase.co/storage/v1/object/public/canchas/u1/a.jpg"] * n, "¡Llegó Pichangol!", "CEANDE · Lurigancho", etiqueta="Nuevo")
        im = Image.open(io.BytesIO(png)); assert im.size == (w, h) and im.format == "JPEG"
    im = Image.open(io.BytesIO(pr.componer([_data_url((200, 80, 40))], "Juega esta semana", formato="horizontal")))
    assert im.size == (1200, 630)
    assert Image.open(io.BytesIO(pr.componer([_data_url((10, 10, 10))], "x", formato="historia"))).size == (1080, 1920)
    with pytest.raises(ValueError):
        pr.componer([], "x")
    assert len(descargas) == 10  # 1+2+3+4 fotos del bucket


def test_torre_previsualiza_publica_y_registra(monkeypatch):
    from web import datos
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [
        {"id": "u1", "nombre": "Cancha Nro.01", "club": "CEANDE Tennis Club", "barrio": "Lurigancho", "deporte": "tenis", "deportes": ["tenis"],
         "precio_hora": 15, "moneda": "S/", "verificada": True, "foto_url": "https://x.supabase.co/a.jpg", "fotos": ["https://x.supabase.co/a.jpg", "https://x.supabase.co/b.jpg"]},
        {"id": "u2", "nombre": "Cancha Nro.02", "club": "CEANDE Tennis Club", "barrio": "Lurigancho", "deporte": "tenis", "precio_hora": 15, "moneda": "S/", "verificada": True, "fotos": ["https://x.supabase.co/c.jpg"]},
        {"id": "u3", "nombre": "Sin fotos", "club": "Otro", "fotos": [], "foto_url": ""},
    ])
    monkeypatch.setattr(pr, "_abrir_url", lambda u: _jpeg((40, 120, 60)) if u.startswith("https://") else base64.b64decode(u.split(",", 1)[1]))
    assert client.get("/admin/api/redes/pichangol", headers={"X-Admin-Token": "malo"}).status_code == 401
    j = client.get("/admin/api/redes/pichangol", headers=H).json()
    assert j["facebook"]["configurado"] is False and "lanzamiento" in j["plantillas"] and j["max_fotos"] == 4
    assert [l["local"] for l in j["locales"]] == ["CEANDE Tennis Club"] and j["locales"][0]["fotos"] == ["https://x.supabase.co/a.jpg", "https://x.supabase.co/b.jpg", "https://x.supabase.co/c.jpg"]
    assert [c["id"] for c in j["locales"][0]["canchas"]] == ["u1", "u2"]
    # Plantilla rellenada con el local.
    p = client.post("/admin/api/redes/pichangol/plantilla", json={"plantilla": "nuevo_local", "cancha_id": "u2"}, headers=H).json()
    assert p["subtitulo"] == "CEANDE Tennis Club · Lurigancho" and "desde S/ 15" in p["texto"]
    # Vista previa (fotos del bucket + una adjunta).
    cuerpo = {"fotos": ["https://x.supabase.co/a.jpg", _data_url((90, 30, 30))], "titulo": "¡Llegó Pichangol!", "subtitulo": "CEANDE · Lurigancho",
              "etiqueta": "Nuevo", "formato": "cuadrado", "texto": "Hola Facebook", "plantilla": "lanzamiento", "cancha_id": "u1"}
    r = client.post("/admin/api/redes/pichangol/previsualizar", json=cuerpo, headers=H).json()
    assert r["ok"] and r["imagen"].startswith("data:image/jpeg;base64,") and r["bytes"] > 1000 and r["extension"] == "jpg"
    assert client.post("/admin/api/redes/pichangol/previsualizar", json={**cuerpo, "fotos": []}, headers=H).status_code == 400
    # Publicar sin credenciales → 409 con la guía; con credenciales → multipart a Graph + historial.
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 409
    monkeypatch.setattr(config, "FB_PAGE_ID", "123")
    monkeypatch.setattr(config, "FB_PAGE_TOKEN", "EAAB")
    llamadas = []
    monkeypatch.setattr(pr, "_graph_multipart", lambda path, campos, archivo: (llamadas.append((path, campos, archivo)) or {"ok": True, "data": {"id": "999", "post_id": "123_999"}}))
    def graph_get(path, params):
        if path == "me":
            return {"ok": True, "data": {"id": "123", "name": "Pichangol"}}   # token de PÁGINA
        if path == "debug_token":
            return {"ok": True, "data": {"data": {"scopes": ["pages_manage_posts", "pages_read_engagement", "pages_show_list"]}}}
        return {"ok": True, "data": {"name": "Pichangol", "link": "https://facebook.com/pichangol"}}
    monkeypatch.setattr(pr, "_graph_get", graph_get)
    pr._token_cache.update(clave="", hasta=0.0)
    fb = client.get("/admin/api/redes/pichangol", headers=H).json()["facebook"]
    assert fb == {"configurado": True, "page_id": "123", "nombre": "Pichangol", "link": "https://facebook.com/pichangol",
                  "token_tipo": "pagina", "usuario": "", "faltan": [], "advertencia": ""}
    assert client.post("/admin/api/redes/pichangol/publicar", json={**cuerpo, "texto": " "}, headers=H).status_code == 400
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).json()
    assert r["ok"] and r["url"] == "https://www.facebook.com/123_999"
    path, campos, archivo = llamadas[0]
    assert path == "123/photos" and campos["message"] == "Hola Facebook" and campos["access_token"] == "EAAB" and archivo[2] == "image/jpeg" and archivo[0] == "pichangol.jpg"
    assert Image.open(io.BytesIO(archivo[1])).size == (1080, 1080)
    h = client.get("/admin/api/redes/pichangol", headers=H).json()["historial"]
    assert len(h) == 1 and h[0]["ok"] and h[0]["post_id"] == "123_999" and h[0]["fotos"] == 2
    # Facebook rechaza → 502 y queda en el historial con el error.
    monkeypatch.setattr(pr, "_graph_multipart", lambda *a, **k: {"ok": False, "error": "(#200) Permissions error"})
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 502
    h = client.get("/admin/api/redes/pichangol", headers=H).json()["historial"]
    assert h[0]["ok"] is False and "Permissions" in h[0]["error"] and "token de PÁGINA" in h[0]["error"]
    # El snapshot persiste el historial.
    from db.store import stores
    assert len(stores.to_state()["publicaciones_redes"]) == 2


def test_token_de_usuario_se_convierte_en_token_de_pagina_y_avisa_permisos(monkeypatch):
    """Caso real (sep-2026): el director pegó en Railway el token de USUARIO extendido y
    Facebook respondió "(#200) publish_actions … deprecated". La torre detecta el tipo de
    token, consigue sola el de la página y avisa si falta `pages_manage_posts`."""
    monkeypatch.setattr(config, "FB_PAGE_ID", "1257")
    monkeypatch.setattr(config, "FB_PAGE_TOKEN", "EAAUSER")
    monkeypatch.setattr(pr, "_abrir_url", lambda u: base64.b64decode(u.split(",", 1)[1]))
    permisos = ["pages_manage_posts", "pages_read_engagement", "pages_show_list"]
    llamadas = []

    def graph_get(path, params):
        llamadas.append((path, params.get("access_token")))
        if path == "1257" and params.get("fields") == "name,link":
            return {"ok": True, "data": {"name": "Pichangol", "link": "https://facebook.com/pichangol"}}
        if path == "me":
            return {"ok": True, "data": {"id": "77", "name": "Dennis"}}       # token de USUARIO
        if path == "me/permissions":
            return {"ok": True, "data": {"data": [{"permission": p, "status": "granted"} for p in permisos] + [{"permission": "email", "status": "declined"}]}}
        if path == "1257" and params.get("fields") == "access_token":
            return {"ok": True, "data": {"access_token": "EAAPAGE"}}
        return {"ok": False, "error": "ruta inesperada " + path}
    monkeypatch.setattr(pr, "_graph_get", graph_get)
    pr._token_cache.update(clave="", hasta=0.0)
    fb = client.get("/admin/api/redes/pichangol", headers=H).json()["facebook"]
    assert fb["token_tipo"] == "usuario" and fb["usuario"] == "Dennis" and fb["faltan"] == [] and "obtiene sola" in fb["advertencia"]
    # Publicar usa el token de PÁGINA derivado, no el de usuario.
    posts = []
    monkeypatch.setattr(pr, "_graph_multipart", lambda path, campos, archivo: (posts.append(campos) or {"ok": True, "data": {"post_id": "1257_1"}}))
    cuerpo = {"fotos": [_data_url((90, 30, 30))], "titulo": "Hola", "subtitulo": "", "etiqueta": "", "formato": "cuadrado", "texto": "Primera publicación", "plantilla": "libre", "cancha_id": ""}
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).json()
    assert r["ok"] and r["url"] == "https://www.facebook.com/1257_1" and posts[0]["access_token"] == "EAAPAGE"
    # La resolución se cachea: no vuelve a preguntar /me en cada publicación.
    n = len([l for l in llamadas if l[0] == "me"])
    client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H)
    assert len([l for l in llamadas if l[0] == "me"]) == n
    # Sin pages_manage_posts → advertencia roja y la torre NO llama a Graph (error claro en vez del #200 de Meta).
    permisos.remove("pages_manage_posts"); pr._token_cache.update(clave="", hasta=0.0); posts.clear()
    fb = client.get("/admin/api/redes/pichangol", headers=H).json()["facebook"]
    assert fb["faltan"] == ["pages_manage_posts"] and "pages_manage_posts" in fb["advertencia"]
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H)
    assert r.status_code == 502 and "pages_manage_posts" in r.json()["detail"] and posts == []
    # Facebook responde el (#200) de publish_actions → la pista dice qué hacer.
    permisos.append("pages_manage_posts"); pr._token_cache.update(clave="", hasta=0.0)
    monkeypatch.setattr(pr, "_graph_multipart", lambda *a, **k: {"ok": False, "error": "HTTP 403: (#200) The permission(s) publish_actions are not available. It has been deprecated."})
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H)
    assert r.status_code == 502 and "token de PÁGINA" in r.json()["detail"] and "FB_PAGE_TOKEN" in r.json()["detail"]
    # Usuario que no administra la página → error explícito, sin publicar.
    def graph_get2(path, params):
        if path == "1257" and params.get("fields") == "access_token":
            return {"ok": False, "error": "(#100) Unsupported get request"}
        return graph_get(path, params)
    monkeypatch.setattr(pr, "_graph_get", graph_get2); pr._token_cache.update(clave="", hasta=0.0)
    fb = client.get("/admin/api/redes/pichangol", headers=H).json()["facebook"]
    assert "no entregó" in fb["advertencia"] and "pages_show_list" in fb["advertencia"]
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 502
