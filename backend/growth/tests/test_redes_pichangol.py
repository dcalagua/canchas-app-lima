"""Publicar en la página de Facebook de Pichangol desde la torre (sep-2026):
composición con fotos reales (bucket o adjuntas), plantillas rellenadas con el
local, vista previa, publicación por Graph (multipart) e historial."""
import base64
import io
import os

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


def test_video_se_sube_a_la_torre_y_se_publica_por_trozos(monkeypatch, tmp_path):
    """Pedido del director (24-sep-2026): "este módulo también debe permitir subir videos
    y que haga el post para Facebook". El video entra por streaming a disco (con tope),
    queda temporal 2 h y al publicar viaja a la página con la subida REANUDABLE de Graph
    (start → transfer por trozos → finish con `description` = texto)."""
    monkeypatch.setattr(pr, "_VIDEO_DIR", str(tmp_path / "videos"))
    monkeypatch.setattr(pr, "VIDEO_MAX_MB", 1)
    pr._videos.clear()
    # Formato no admitido → 400; tope → 413 (por Content-Length y también por streaming).
    assert client.post("/admin/api/redes/pichangol/video?nombre=foto.jpg", content=b"x" * 10, headers=H).status_code == 400
    r = client.post("/admin/api/redes/pichangol/video?nombre=grande.mp4", content=b"x" * (1024 * 1024 + 1), headers=H)
    assert r.status_code == 413 and "máximo" in r.json()["detail"]
    assert pr._videos == {} and not any((tmp_path / "videos").glob("*")) if (tmp_path / "videos").exists() else True
    # Subida correcta: 300 KB → id temporal, archivo en disco.
    datos = bytes(range(256)) * 1200
    r = client.post("/admin/api/redes/pichangol/video?nombre=Mi%20cancha.MP4", content=datos, headers=H)
    assert r.status_code == 200, r.text
    vid = r.json()["video_id"]
    assert r.json()["bytes"] == len(datos) and r.json()["nombre"] == "Mi cancha.MP4" and vid.startswith("vid_")
    v = pr.video(vid)
    assert v and v["ext"] == "mp4" and open(v["ruta"], "rb").read() == datos
    j = client.get("/admin/api/redes/pichangol", headers=H).json()
    assert j["video_max_mb"] == 1 and "mp4" in j["video_extensiones"]
    cuerpo = {"fotos": [], "titulo": "Nuestra cancha", "subtitulo": "", "etiqueta": "", "formato": "cuadrado",
              "texto": "🎬 Mira nuestra cancha en Pichangol", "plantilla": "libre", "cancha_id": "", "video_id": vid}
    # Sin credenciales → 409 (el video sigue guardado para reintentar).
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 409
    assert pr.video(vid)
    # Con credenciales (token de página) → start / transfer×N / finish.
    monkeypatch.setattr(config, "FB_PAGE_ID", "1257")
    monkeypatch.setattr(config, "FB_PAGE_TOKEN", "EAAPAGE")
    monkeypatch.setattr(pr, "_graph_get", lambda path, params: {"ok": True, "data": {"id": "1257", "name": "Pichangol"}} if path == "me"
                        else {"ok": False, "error": "x"} if path == "debug_token" else {"ok": True, "data": {"name": "Pichangol", "link": "l"}})
    pr._token_cache.update(clave="", hasta=0.0)
    llamadas, recibido = [], bytearray()
    TROZO = 100_000

    def graph_multipart(path, campos, archivo, campo_archivo="source", timeout=60):
        llamadas.append((path, dict(campos), archivo and (archivo[0], len(archivo[1]), archivo[2]), campo_archivo, timeout))
        fase = campos["upload_phase"]
        if fase == "start":
            assert campos["file_size"] == str(len(datos)) and archivo is None
            return {"ok": True, "data": {"upload_session_id": "ses1", "video_id": "777", "start_offset": "0", "end_offset": str(min(TROZO, len(datos)))}}
        if fase == "transfer":
            assert campo_archivo == "video_file_chunk" and campos["upload_session_id"] == "ses1" and timeout >= 300
            ini = int(campos["start_offset"]); assert ini == len(recibido)
            recibido.extend(archivo[1])
            fin = min(len(recibido) + TROZO, len(datos))
            return {"ok": True, "data": {"start_offset": str(len(recibido)), "end_offset": str(fin)}}
        assert fase == "finish" and campos["description"] == "🎬 Mira nuestra cancha en Pichangol" and campos["title"] == "Nuestra cancha" and campos["published"] == "true"
        return {"ok": True, "data": {"success": True}}
    monkeypatch.setattr(pr, "_graph_multipart", graph_multipart)
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["video"] is True and r.json()["url"] == "https://www.facebook.com/777"
    fases = [c[1]["upload_phase"] for c in llamadas]
    assert fases == ["start"] + ["transfer"] * 4 + ["finish"] and bytes(recibido) == datos
    assert all(c[0] == "1257/videos" and c[1]["access_token"] == "EAAPAGE" for c in llamadas)
    # El archivo temporal se borra al publicar y el historial lo registra como video.
    assert pr.video(vid) is None and not os.path.exists(v["ruta"])
    h = client.get("/admin/api/redes/pichangol", headers=H).json()["historial"]
    assert h[0]["tipo"] == "video" and h[0]["post_id"] == "777" and h[0]["video_nombre"] == "Mi cancha.MP4" and h[0]["fotos"] == 0
    # Video vencido / inexistente → 404 claro.
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H)
    assert r.status_code == 404 and "Súbelo de nuevo" in r.json()["detail"]
    # Facebook corta un trozo → 502 con el trozo y el video se conserva para reintentar.
    r = client.post("/admin/api/redes/pichangol/video?nombre=otro.mov", content=datos[:150_000], headers=H); vid2 = r.json()["video_id"]
    monkeypatch.setattr(pr, "_graph_multipart", lambda path, campos, archivo, **k: {"ok": True, "data": {"upload_session_id": "s", "video_id": "1", "start_offset": "0", "end_offset": "150000"}}
                        if campos["upload_phase"] == "start" else {"ok": False, "error": "HTTP 500: (#6000) transient"})
    r = client.post("/admin/api/redes/pichangol/publicar", json={**cuerpo, "video_id": vid2}, headers=H)
    assert r.status_code == 502 and "trozo 1" in r.json()["detail"] and pr.video(vid2)
    # Descartar desde la torre y limpieza por vencimiento.
    assert client.post(f"/admin/api/redes/pichangol/video/{vid2}/descartar", headers=H).json()["ok"] and pr.video(vid2) is None
    r = client.post("/admin/api/redes/pichangol/video?nombre=viejo.mp4", content=b"v" * 10, headers=H); vid3 = r.json()["video_id"]
    pr._videos[vid3]["creado_en"] -= pr.VIDEO_TTL + 1
    pr._limpiar_videos()
    assert pr.video(vid3) is None
