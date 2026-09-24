"""Publicar en la página de Facebook de Pichangol desde la torre (sep-2026):
composición con fotos reales (bucket o adjuntas), plantillas rellenadas con el
local, vista previa, publicación por Graph (multipart) e historial."""
import base64
import io
import json
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
    stores.config.pop("fb_page_token_cifrado", None); stores.config.pop("fb_page_token_meta", None)
    pr._token_cache.update(clave="", hasta=0.0)
    yield
    stores.config.pop("fb_page_token_cifrado", None); stores.config.pop("fb_page_token_meta", None)
    pr._token_cache.update(clave="", hasta=0.0)


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
                  "token_tipo": "pagina", "usuario": "", "faltan": [], "advertencia": "", "origen": "railway", "vence": 0, "guardado": True}
    assert client.post("/admin/api/redes/pichangol/publicar", json={**cuerpo, "texto": " "}, headers=H).status_code == 400
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).json()
    assert r["ok"] and r["url"] == "https://www.facebook.com/123_999"
    path, campos, archivo = llamadas[0]
    assert path == "123/photos" and campos["message"] == "Hola Facebook" and campos["access_token"] == "EAAB" and archivo[2] == "image/jpeg" and archivo[0] == "pichangol.jpg"
    assert Image.open(io.BytesIO(archivo[1])).size == (1080, 1080)
    h = client.get("/admin/api/redes/pichangol", headers=H).json()["historial"]
    assert len(h) == 1 and h[0]["ok"] and h[0]["post_id"] == "123_999" and h[0]["fotos"] == 2
    # Se publica LA VISTA PREVIA tal cual aunque ya no queden fotos elegidas (caso real: cambió
    # de local y salía "Elige al menos una foto"); una imagen inválida → 400; sin nada → 400.
    vista = client.post("/admin/api/redes/pichangol/previsualizar", json=cuerpo, headers=H).json()["imagen"]
    llamadas.clear()
    r = client.post("/admin/api/redes/pichangol/publicar", json={**cuerpo, "fotos": [], "imagen": vista}, headers=H)
    assert r.status_code == 200, r.text
    assert llamadas[0][2][1] == base64.b64decode(vista.split(",", 1)[1]) and Image.open(io.BytesIO(llamadas[0][2][1])).size == (1080, 1080)
    assert client.post("/admin/api/redes/pichangol/publicar", json={**cuerpo, "fotos": [], "imagen": "data:image/png;base64,AAAA"}, headers=H).status_code == 400
    r = client.post("/admin/api/redes/pichangol/publicar", json={**cuerpo, "fotos": []}, headers=H)
    assert r.status_code == 400 and "vista previa" in r.json()["detail"]
    # Facebook rechaza → 502 y queda en el historial con el error.
    monkeypatch.setattr(pr, "_graph_multipart", lambda *a, **k: {"ok": False, "error": "(#200) Permissions error"})
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 502
    h = client.get("/admin/api/redes/pichangol", headers=H).json()["historial"]
    assert h[0]["ok"] is False and "Permissions" in h[0]["error"] and "token de PÁGINA" in h[0]["error"]
    # El snapshot persiste el historial.
    from db.store import stores
    assert len(stores.to_state()["publicaciones_redes"]) == 3


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
    assert fb["token_tipo"] == "usuario" and fb["usuario"] == "Dennis" and fb["faltan"] == [] and "derivó y guardó" in fb["advertencia"]
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
    assert "no entregó" in fb["error"] and "pages_show_list" in fb["error"] and fb["nombre"] == ""
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


def test_redactor_ia_varia_el_enfoque_y_no_repite_lo_publicado(monkeypatch):
    """Pedido del director (24-sep-2026): "todos los posts dicen lo mismo… la IA debe
    interactuar para que sea más natural". El redactor elige un enfoque distinto a los
    recientes, recibe los posts ya publicados para no repetir ganchos y respeta los
    topes de la pieza; sin llave cae al banco de variantes."""
    from web import datos
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [
        {"id": "u1", "nombre": "Cancha 1", "club": "CEANDE Tennis Club", "barrio": "Lurigancho", "deporte": "tenis", "deportes": ["tenis"],
         "precio_hora": 15, "moneda": "S/", "verificada": True, "fotos": ["https://x.supabase.co/a.jpg"], "hora_apertura": "07:00", "hora_cierre": "22:00",
         "lat": -11.98, "lng": -76.9}])
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    j = client.get("/admin/api/redes/pichangol", headers=H).json()
    assert j["ia"]["disponible"] is False and "tip" in j["ia"]["enfoques"] and "cercano" in j["ia"]["tonos"]
    # Sin IA: banco de variantes, con hechos del local y hashtag de marca; distintos enfoques al pedir "otra versión".
    vistos, enfoques = [], set()
    for _ in range(6):
        r = client.post("/admin/api/redes/pichangol/redactar", json={"cancha_id": "u1", "tono": "cercano", "enfoque": "auto", "evitar": vistos}, headers=H).json()
        assert r["ok"] and r["fuente"] == "banco" and "#pichangol" in r["texto"] and len(r["titulo"]) <= 36 and len(r["etiqueta"]) <= 14
        vistos.append(r["texto"]); enfoques.add(r["enfoque"])
    assert len(enfoques) >= 3 and len(set(vistos)) == 6   # "otra versión" nunca repite mientras queden variantes
    r = client.post("/admin/api/redes/pichangol/redactar", json={"cancha_id": "u1", "enfoque": "duenos", "tema": "Feriado largo: agenda llena"}, headers=H).json()
    assert r["enfoque"] == "duenos" and "Modo anfitrión" in r["texto"] and "Feriado largo" in r["texto"]
    r = client.post("/admin/api/redes/pichangol/redactar", json={"cancha_id": "u1", "enfoque": "humor"}, headers=H).json()
    assert "dentro o fuera" in r["texto"]   # humor del deporte del local (tenis), no el del arquero
    # Con IA: se le pasan el local (país/moneda/horario), el tono, el enfoque y lo reciente; se recortan los topes.
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
    capturado = {}

    def falso_claude(payload):
        capturado.update(payload)
        return {"titulo": "Un título larguísimo que se pasa de los treinta y seis caracteres", "subtitulo": "Sub", "etiqueta": "Este finde ya",
                "texto": "Hola Lurigancho, ¿este sábado se juega? Turnos libres en CEANDE.\n\n#tenis", "enfoque": "finde"}
    monkeypatch.setattr(pr, "_con_claude_redactor", falso_claude)
    from db.store import stores
    stores.publicaciones_redes.clear()
    stores.publicaciones_redes.insert(0, {"id": "pub_1", "creado_en": 1, "titulo": "¡Llegó Pichangol!", "texto": "🎾⚽ ¡Llegó Pichangol! Reserva canchas…", "enfoque": "beneficio", "ok": True})
    r = client.post("/admin/api/redes/pichangol/redactar", json={"cancha_id": "u1", "tono": "divertido", "enfoque": "auto", "evitar": ["Texto de la sesión"]}, headers=H).json()
    assert r["fuente"] == "ia" and r["enfoque"] == "finde" and 30 <= len(r["titulo"]) <= 36 and r["etiqueta"] == "Este finde ya"
    assert r["texto"].endswith("#tenis\n\n#pichangol")   # el hashtag de marca se asegura
    assert capturado["local"]["local"] == "CEANDE Tennis Club" and capturado["local"]["pais"] == "Perú" and capturado["local"]["precio"] == "S/ 15 la hora" and capturado["local"]["horario"] == "07:00–22:00"
    assert capturado["tono"].startswith("divertido") and capturado["enfoque"]["clave"] != "beneficio"   # no repite el enfoque recién usado
    assert any("¡Llegó Pichangol!" in x for x in capturado["recientes_no_repetir"]) and "Texto de la sesión" in capturado["recientes_no_repetir"]
    # El enfoque y la fuente viajan al historial al publicar, para la rotación siguiente.
    monkeypatch.setattr(config, "FB_PAGE_ID", "1257"); monkeypatch.setattr(config, "FB_PAGE_TOKEN", "EAAPAGE")
    monkeypatch.setattr(pr, "_graph_get", lambda path, params: {"ok": True, "data": {"id": "1257", "name": "Pichangol", "link": "l"}})
    monkeypatch.setattr(pr, "_graph_multipart", lambda *a, **k: {"ok": True, "data": {"post_id": "1257_9"}})
    monkeypatch.setattr(pr, "_abrir_url", lambda u: base64.b64decode(u.split(",", 1)[1]))
    pr._token_cache.update(clave="", hasta=0.0)
    cuerpo = {"fotos": [_data_url((30, 90, 30))], "titulo": r["titulo"], "subtitulo": "", "etiqueta": "", "formato": "cuadrado", "texto": r["texto"],
              "plantilla": "ia", "cancha_id": "u1", "enfoque": r["enfoque"], "fuente": r["fuente"]}
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 200
    h = client.get("/admin/api/redes/pichangol", headers=H).json()["historial"]
    assert h[0]["enfoque"] == "finde" and h[0]["fuente"] == "ia"
    assert pr._enfoques_usados()[:2] == ["finde", "beneficio"]


def _clip(ruta: str, con_audio: bool = True, seg: float = 2.0) -> str:
    from marketing import video_pulido as vp
    ff = vp.ffmpeg_exe()
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=24"]
    if con_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    cmd += ["-t", str(seg), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast"] + (["-c:a", "aac", "-shortest"] if con_audio else []) + [ruta]
    import subprocess
    subprocess.run(cmd, check=True, capture_output=True)
    return ruta


def test_pulido_estilo_pichangol_con_subtitulos_whisper(monkeypatch, tmp_path):
    """Punto 1 y 2 del plan (24-sep-2026): el video subido se pule en casa con FFmpeg
    (intro + marca de agua + rótulo + cierre + audio normalizado, fondo desenfocado
    si el encuadre no calza) y los subtítulos salen de Whisper, editables en la torre;
    publicar usa la versión pulida salvo que el operador elija el original."""
    import subprocess
    from marketing import video_pulido as vp
    assert vp.disponible()
    monkeypatch.setattr(pr, "_VIDEO_DIR", str(tmp_path / "videos"))
    pr._videos.clear(); vp._trabajos.clear()
    # Segmentación para la caja de subtítulos: ≤6 palabras, con y sin tiempos por palabra; ASS con karaoke.
    seg = [{"inicio": 0.0, "fin": 3.0, "texto": "uno dos tres cuatro cinco seis siete ocho", "palabras": [{"p": w, "inicio": i * 0.35, "fin": i * 0.35 + 0.3} for i, w in enumerate("uno dos tres cuatro cinco seis siete ocho".split())]},
           {"inicio": 3.2, "fin": 6.0, "texto": "a b c d e f g h i j k l m n", "palabras": []}]
    partes = vp.partir_segmentos(seg)
    assert [p["texto"] for p in partes][:2] == ["uno dos tres cuatro cinco seis", "siete ocho"] and len(partes) == 5 and all(p["fin"] > p["inicio"] for p in partes)
    ass = vp.escribir_ass(partes, 1080, 1920, str(tmp_path / "s.ass"))
    txt = open(ass, encoding="utf-8").read()
    assert "DM Sans" in txt and "{\\k" in txt and "Style: Pichangol" in txt and txt.count("Dialogue:") == 5
    # Sube un clip horizontal con audio → vertical con todo; Whisper simulado.
    clip = _clip(str(tmp_path / "clip.mp4"))
    r = client.post("/admin/api/redes/pichangol/video?nombre=clip.mp4", content=open(clip, "rb").read(), headers=H)
    vid = r.json()["video_id"]
    j = client.get("/admin/api/redes/pichangol", headers=H).json()
    assert j["pulido"]["disponible"] is True and "vertical" in j["pulido"]["formatos"]
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    llamadas = []
    def falso_whisper(ruta_audio, idioma="es"):
        llamadas.append(os.path.getsize(ruta_audio))
        return {"language": "spanish", "duration": 2.0, "text": "Reserva tu cancha en Pichangol",
                "segments": [{"start": 0.1, "end": 1.9, "text": " Reserva tu cancha en Pichangol"}],
                "words": [{"word": "Reserva", "start": 0.1, "end": 0.5}, {"word": "tu", "start": 0.5, "end": 0.7}, {"word": "cancha", "start": 0.7, "end": 1.1},
                          {"word": "en", "start": 1.1, "end": 1.3}, {"word": "Pichangol", "start": 1.3, "end": 1.9}]}
    monkeypatch.setattr(vp, "_whisper_api", falso_whisper)
    r = client.post(f"/admin/api/redes/pichangol/video/{vid}/pulir", json={"formato": "vertical", "titulo": "Este sábado sí se juega", "subtitulos": True}, headers=H)
    assert r.status_code == 200, r.text
    assert client.post(f"/admin/api/redes/pichangol/video/{vid}/pulir", json={"formato": "vertical"}, headers=H).status_code == 409  # ya en curso
    import time as _t
    fin = _t.time() + 90
    while _t.time() < fin:
        e = client.get(f"/admin/api/redes/pichangol/video/{vid}/estado", headers=H).json()
        if e["estado"] in ("listo", "error"):
            break
        _t.sleep(0.5)
    assert e["estado"] == "listo", e
    assert e["pulido"] is True and e["pulido_info"]["ancho"] == 1080 and e["pulido_info"]["alto"] == 1920 and e["pulido_info"]["segmentos"] == 1
    assert abs(e["pulido_info"]["duracion"] - (2.0 + vp.INTRO_S + vp.CIERRE_S)) < 0.6
    assert llamadas and llamadas[0] > 1000   # se extrajo el audio y se mandó a Whisper
    assert e["transcripcion"]["segmentos"][0]["texto"] == "Reserva tu cancha en Pichangol" and len(e["transcripcion"]["segmentos"][0]["palabras"]) == 5
    # El archivo pulido se sirve para la vista previa; el original también.
    r = client.get(f"/admin/api/redes/pichangol/video/{vid}/archivo?cual=pulido", headers=H)
    assert r.status_code == 200 and r.headers["content-type"].startswith("video/mp4") and len(r.content) > 10000
    assert client.get(f"/admin/api/redes/pichangol/video/{vid}/archivo?cual=original", headers=H).status_code == 200
    salida = vp.sondear(pr.video(vid)["pulido"])
    assert salida["ancho"] == 1080 and salida["alto"] == 1920 and salida["audio"]
    # Regenerar con subtítulos corregidos (sin tiempos por palabra) NO vuelve a llamar a Whisper.
    n = len(llamadas)
    r = client.post(f"/admin/api/redes/pichangol/video/{vid}/pulir", json={"formato": "cuadrado", "titulo": "Otro", "subtitulos": True, "intro": False,
                    "segmentos": [{"inicio": 0.1, "fin": 1.9, "texto": "Reserva tu cancha en Pichangol app", "palabras": []}]}, headers=H)
    assert r.status_code == 200, r.text
    fin = _t.time() + 90
    while _t.time() < fin:
        e = client.get(f"/admin/api/redes/pichangol/video/{vid}/estado", headers=H).json()
        if e["estado"] in ("listo", "error"):
            break
        _t.sleep(0.5)
    assert e["estado"] == "listo" and e["pulido_info"]["ancho"] == 1080 and e["pulido_info"]["alto"] == 1080 and len(llamadas) == n
    # Publicar usa la versión PULIDA (y el historial lo marca); con usar_pulido=false va el original.
    monkeypatch.setattr(config, "FB_PAGE_ID", "1257"); monkeypatch.setattr(config, "FB_PAGE_TOKEN", "EAAPAGE")
    rutas = []
    monkeypatch.setattr(pr, "publicar_video_facebook", lambda texto, titulo, ruta: (rutas.append(ruta) or {"ok": True, "post_id": "77", "url": "u"}))
    cuerpo = {"fotos": [], "titulo": "Otro", "texto": "Mira el video", "plantilla": "libre", "video_id": vid, "usar_pulido": False}
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 200
    assert not os.path.basename(rutas[-1]).endswith("_pulido.mp4")   # el original
    # (el video se descarta al publicar; se sube otro para el caso pulido)
    r = client.post("/admin/api/redes/pichangol/video?nombre=clip2.mp4", content=open(clip, "rb").read(), headers=H); vid2 = r.json()["video_id"]
    r = client.post(f"/admin/api/redes/pichangol/video/{vid2}/pulir", json={"formato": "original", "subtitulos": False, "intro": False, "cierre": False, "rotulo": False}, headers=H)
    assert r.status_code == 200
    fin = _t.time() + 90
    while _t.time() < fin:
        e = client.get(f"/admin/api/redes/pichangol/video/{vid2}/estado", headers=H).json()
        if e["estado"] in ("listo", "error"):
            break
        _t.sleep(0.5)
    assert e["estado"] == "listo" and e["pulido_info"]["segmentos"] == 0 and e["pulido_info"]["ancho"] == 640
    assert client.post("/admin/api/redes/pichangol/publicar", json={**cuerpo, "video_id": vid2, "usar_pulido": True}, headers=H).status_code == 200
    assert os.path.basename(rutas[-1]).endswith("_pulido.mp4")
    h = client.get("/admin/api/redes/pichangol", headers=H).json()["historial"]
    assert h[0]["pulido"] is True and h[1]["pulido"] is False
    assert pr.video(vid2) is None and not os.path.exists(rutas[-1])   # temporal y pulido borrados al publicar
    # Sin llave de OpenAI y sin transcripción previa → 409 claro al pedir subtítulos; sin audio → sin subtítulos + música.
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    mudo = _clip(str(tmp_path / "mudo.mp4"), con_audio=False)
    r = client.post("/admin/api/redes/pichangol/video?nombre=mudo.mp4", content=open(mudo, "rb").read(), headers=H); vid3 = r.json()["video_id"]
    assert client.post(f"/admin/api/redes/pichangol/video/{vid3}/pulir", json={"subtitulos": True}, headers=H).status_code == 409
    assert client.post(f"/admin/api/redes/pichangol/video/{vid3}/pulir", json={"subtitulos": False, "formato": "vertical"}, headers=H).status_code == 200
    fin = _t.time() + 90
    while _t.time() < fin:
        e = client.get(f"/admin/api/redes/pichangol/video/{vid3}/estado", headers=H).json()
        if e["estado"] in ("listo", "error"):
            break
        _t.sleep(0.5)
    assert e["estado"] == "listo" and vp.sondear(pr.video(vid3)["pulido"])["audio"]   # música original de fondo


def test_token_vencido_se_reemplaza_desde_la_torre_sin_tocar_railway(monkeypatch):
    """Caso real (24-sep-2026, 22:00 PDT): el token de usuario del Explorador dura 1-2 h y
    Facebook respondió "(#190) Session has expired". Ahora: (1) la torre deriva el token de
    PÁGINA (que no vence) y lo guarda cifrado en el snapshot; (2) el operador puede pegar un
    token nuevo en la torre sin redesplegar Railway; (3) si el guardado muere, se descarta
    solo y se vuelve al de Railway."""
    from db.store import stores
    monkeypatch.setattr(config, "FB_PAGE_ID", "1257")
    monkeypatch.setattr(config, "FB_PAGE_TOKEN", "EAAUSER_CORTO")
    monkeypatch.setattr(config, "META_APP_ID", "app1"); monkeypatch.setattr(config, "META_APP_SECRET", "sec1")
    vivos = {"EAAUSER_CORTO", "EAAUSER_LARGO", "EAAPAGE1", "EAAPAGE2", "EAAUSER2_XXXXXXXXXXXXXXXXXX"}
    llamadas = []

    def graph_get(path, params):
        tok = params.get("access_token", "")
        llamadas.append((path, tok))
        if path == "oauth/access_token":
            assert params["grant_type"] == "fb_exchange_token" and params["client_secret"] == "sec1"
            return {"ok": True, "data": {"access_token": "EAAUSER_LARGO", "expires_in": 5183944}} if params["fb_exchange_token"] in vivos else {"ok": False, "error": "(#190) expired"}
        if path == "debug_token":
            t = params["input_token"]
            if t not in vivos:
                return {"ok": False, "error": "(#190) Session has expired"}
            es_pag = t.startswith("EAAPAGE")
            return {"ok": True, "data": {"data": {"scopes": ["pages_manage_posts", "pages_read_engagement", "pages_show_list"], "expires_at": 0 if es_pag else 1790000000, "type": "PAGE" if es_pag else "USER"}}}
        if tok not in vivos:
            return {"ok": False, "error": "HTTP 400: Error validating access token: Session has expired on Wednesday, 23-Sep-26 22:00:00 PDT."}
        if path == "me":
            return {"ok": True, "data": {"id": "1257", "name": "Pichangol"}} if tok.startswith("EAAPAGE") else {"ok": True, "data": {"id": "77", "name": "Dennis"}}
        if path == "1257" and params.get("fields") == "access_token":
            return {"ok": True, "data": {"access_token": "EAAPAGE1" if tok == "EAAUSER_LARGO" else "EAAPAGE2"}}
        if path == "1257":
            return {"ok": True, "data": {"name": "Pichangol", "link": "https://facebook.com/pichangol"}}
        return {"ok": False, "error": "ruta inesperada " + path}
    monkeypatch.setattr(pr, "_graph_get", graph_get)
    # 1) Token corto de usuario en Railway → se extiende (60 d) → token de página permanente, GUARDADO cifrado.
    fb = client.get("/admin/api/redes/pichangol", headers=H).json()["facebook"]
    assert fb["nombre"] == "Pichangol" and fb["token_tipo"] == "usuario" and fb["guardado"] is True and fb["vence"] == 0
    assert stores.config["fb_page_token_cifrado"].startswith(("f:", "b:")) and "EAAPAGE1" not in stores.config["fb_page_token_cifrado"]
    assert pr._token_guardado() == "EAAPAGE1" and "no vence" in fb["advertencia"]
    assert any(p == "oauth/access_token" for p, _ in llamadas)
    # 2) Railway vence (como pasó a las 22:00) → la torre sigue publicando con el guardado.
    vivos.discard("EAAUSER_CORTO"); pr._token_cache.update(clave="", hasta=0.0)
    fb = client.get("/admin/api/redes/pichangol", headers=H).json()["facebook"]
    assert fb["nombre"] == "Pichangol" and fb["origen"] == "torre"
    monkeypatch.setattr(pr, "_abrir_url", lambda u: base64.b64decode(u.split(",", 1)[1]))
    posts = []
    monkeypatch.setattr(pr, "_graph_multipart", lambda path, campos, archivo, **k: (posts.append(campos["access_token"]) or {"ok": True, "data": {"post_id": "1257_5"}}))
    cuerpo = {"fotos": [_data_url((30, 90, 30))], "titulo": "Hola", "texto": "Publicación", "plantilla": "libre"}
    assert client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H).status_code == 200 and posts == ["EAAPAGE1"]
    # 3) El operador pega un token NUEVO en la torre (de usuario) → se guarda el de página derivado; el texto pegado no se devuelve.
    r = client.post("/admin/api/redes/pichangol/token", json={"token": "EAAUSER2_XXXXXXXXXXXXXXXXXX"}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] and j["tipo"] == "usuario" and j["derivado"] is True and j["extendido"] is True and j["vence"] == 0 and "EAA" not in json.dumps(j["facebook"])
    assert pr._token_guardado() == "EAAPAGE1"   # EAAUSER2 se extiende a EAAUSER_LARGO → EAAPAGE1
    assert client.post("/admin/api/redes/pichangol/token", json={"token": "basura"}, headers=H).status_code == 400
    assert client.post("/admin/api/redes/pichangol/token", json={"token": "EAAMUERTO_XXXXXXXXXXXXXXXX"}, headers=H).status_code == 400
    # 4) El guardado muere y Railway sigue muerto → error claro con la pista de pegar uno nuevo; al publicar con (#190) se olvida el guardado.
    vivos.discard("EAAPAGE1"); pr._token_cache.update(clave="", hasta=0.0)
    fb = client.get("/admin/api/redes/pichangol", headers=H).json()["facebook"]
    assert fb["nombre"] == "" and "expired" in fb["error"].lower() and "fb_page_token_cifrado" not in stores.config
    r = client.post("/admin/api/redes/pichangol/publicar", json=cuerpo, headers=H)
    assert r.status_code == 502 and "pégalo en la torre" in r.json()["detail"]
    # Olvidar desde la torre.
    stores.config["fb_page_token_cifrado"] = "b:xx"
    assert client.post("/admin/api/redes/pichangol/token/olvidar", headers=H).json()["ok"] and "fb_page_token_cifrado" not in stores.config


def test_agente_marketing_24x7_publica_a_las_7_y_alterna_audiencias(monkeypatch):
    """Pedido del director (24-sep-2026): "agentes de marketing 24×7 (creativo + community
    manager, estratega comercial) que publiquen todos los días a las 7:00 am promocionando
    Pichangol (descargar la app / reservar en la web) e incitando a los dueños a administrar
    sus canchas". El cron llama `tick()` cada minuto: solo publica a la hora, una vez al día,
    siguiendo el plan semanal; en modo "aprobar" deja borradores que el operador revisa."""
    from datetime import datetime, timezone as _tz
    from db.store import stores
    from marketing import agente_redes as ag
    from web import datos
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [
        {"id": "u1", "nombre": "Cancha 1", "club": "CEANDE Tennis Club", "barrio": "Lurigancho", "deporte": "tenis", "deportes": ["tenis"], "precio_hora": 15,
         "moneda": "S/", "verificada": True, "fotos": ["https://x.supabase.co/a.jpg"], "lat": -11.98, "lng": -76.9, "dueno": "ceande@gmail.com"},
        {"id": "u2", "nombre": "Fútbol 1", "club": "Sabor Golazo", "barrio": "Ate", "deporte": "futbol", "deportes": ["futbol"], "precio_hora": 60,
         "moneda": "S/", "verificada": True, "fotos": ["https://x.supabase.co/b.jpg"], "lat": -12.0, "lng": -76.9, "dueno": "golazo@gmail.com"}])
    monkeypatch.setattr(ag, "_arte_disponible", lambda: False)   # sin proveedor de imágenes: portada de marca
    monkeypatch.setattr(pr, "_abrir_url", lambda u: _jpeg((40, 120, 60)) if u.startswith("https://") else base64.b64decode(u.split(",", 1)[1]))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "FB_PAGE_ID", "1257"); monkeypatch.setattr(config, "FB_PAGE_TOKEN", "EAAPAGE")
    monkeypatch.setattr(ag, "_persistir", lambda: None)
    publicados = []
    monkeypatch.setattr(pr, "publicar_facebook", lambda texto, png: (publicados.append((texto, len(png))) or {"ok": True, "post_id": f"1257_{len(publicados)}", "url": "https://www.facebook.com/x"}))
    for k in ag.CFG.values():
        stores.config.pop(k, None)
    stores.agente_fb = {"borradores": [], "corridas": []}
    reloj = {"utc": datetime(2026, 9, 29, 11, 30, tzinfo=_tz.utc)}   # martes 06:30 Lima
    monkeypatch.setattr(ag, "_ahora", lambda: reloj["utc"])
    # Configuración por defecto: pausado, 07:00 Lima, plan 5 días jugadores / 2 dueños.
    j = client.get("/admin/api/redes/agente", headers=H).json()
    assert j["config"]["activo"] is False and j["config"]["hora"] == "07:00" and j["config"]["zona"] == "America/Lima"
    assert j["config"]["plan"]["1"]["audiencia"] == "duenos" and j["config"]["plan"]["0"] == {"audiencia": "jugadores", "enfoque": "beneficio"}
    assert j["proxima"]["dia"] == "martes" and j["proxima"]["audiencia"] == "duenos"
    assert j["locales_pro"] == 0 and j["config"]["destacar_pro"] is False   # ningún local es Pro → nadie sale en la publicidad
    # Pausado → el tick no hace nada aunque sea la hora.
    reloj["utc"] = datetime(2026, 9, 29, 12, 1, tzinfo=_tz.utc)
    assert ag.tick() is False and publicados == []
    # Activar desde la torre (validaciones incluidas).
    assert client.post("/admin/api/redes/agente", json={"hora": "7am"}, headers=H).status_code == 400
    assert client.post("/admin/api/redes/agente", json={"zona": "Europe/Madrid"}, headers=H).status_code == 400
    r = client.post("/admin/api/redes/agente", json={"activo": True, "hora": "07:00", "modo": "auto", "tono": "cercano",
                    "plan": {"3": {"audiencia": "jugadores", "enfoque": "humor"}, "6": {"audiencia": "duenos", "enfoque": "lo_que_sea"}}}, headers=H)
    assert r.status_code == 200 and r.json()["config"]["activo"] is True and r.json()["config"]["plan"]["3"]["enfoque"] == "humor" and r.json()["config"]["plan"]["6"]["enfoque"] == "duenos"
    # 06:59 → nada; 07:00 → publica UNA vez (martes = dueños); 07:01 y 09:00 → nada más ese día.
    reloj["utc"] = datetime(2026, 9, 29, 11, 59, tzinfo=_tz.utc)
    assert ag.tick() is False and publicados == []
    reloj["utc"] = datetime(2026, 9, 29, 12, 0, tzinfo=_tz.utc)
    assert ag.tick() is True and len(publicados) == 1
    texto, tam = publicados[0]
    assert tam > 10000 and "#pichangol" in texto.lower()
    h = stores.publicaciones_redes[0]
    assert h["fuente"] == "agente" and h["audiencia"] == "duenos" and h["enfoque"] == "duenos" and h["origen"] == "agente_auto" and h["ok"]
    assert "cancha" in texto.lower() and ("anfitrión" in texto.lower() or "pichangol.app" in texto.lower())
    assert h["local"] == "" and "CEANDE" not in texto and "Golazo" not in texto   # publicidad de la MARCA, no de un local
    for utc in ((2026, 9, 29, 12, 1), (2026, 9, 29, 14, 0), (2026, 9, 30, 11, 0)):
        reloj["utc"] = datetime(*utc, tzinfo=_tz.utc)
        assert ag.tick() is False
    assert len(publicados) == 1 and stores.config["agente_fb_ultimo_dia"] == "2026-09-29"
    j = client.get("/admin/api/redes/agente", headers=H).json()
    assert j["proxima"]["hoy_publicado"] is False and j["proxima"]["dia"] == "miércoles" and j["proxima"]["audiencia"] == "jugadores" and j["corridas"][0]["resultado"] == "publicado"
    # Miércoles 07:00 → jugadores, pieza de MARCA (historia de Pichangol): sin local, imagen de marca, empuja app/web.
    reloj["utc"] = datetime(2026, 9, 30, 12, 0, tzinfo=_tz.utc)
    assert ag.tick() is True and len(publicados) == 2
    h2 = stores.publicaciones_redes[0]
    assert h2["audiencia"] == "jugadores" and h2["enfoque"] == "historia" and h2["local"] == ""
    assert "pichangol" in publicados[1][0].lower() and "CEANDE" not in publicados[1][0] and "Golazo" not in publicados[1][0]
    # Aunque el plan pida "local", sin locales Pro cae a "beneficio"; con un dueño PRO + "destacar Pro" activo, sí se destaca ESE local.
    brief = ag.planificar(ag.ahora_local(), audiencia="jugadores", enfoque="local")
    assert brief["enfoque"] == "beneficio" and brief["local"] is None and "no menciones ningún local" in brief["tema"]
    stores.membresias_pro["golazo@gmail.com"] = {"hasta": "2099-01-01T00:00:00+00:00", "plan": "pro"}
    assert client.get("/admin/api/redes/agente", headers=H).json()["locales_pro"] == 1
    brief = ag.planificar(ag.ahora_local(), audiencia="jugadores", enfoque="local")
    assert brief["local"] is None                       # destacar_pro sigue apagado
    client.post("/admin/api/redes/agente", json={"destacar_pro": True}, headers=H)
    brief = ag.planificar(ag.ahora_local(), audiencia="jugadores", enfoque="local")
    assert brief["local"]["local"] == "Sabor Golazo" and "Local Pro destacado" in brief["tema"]
    pieza = ag.crear_pieza(brief)
    assert pieza["fotos"] == ["https://x.supabase.co/b.jpg"] and pieza["local"] == "Sabor Golazo"
    brief = ag.planificar(ag.ahora_local(), audiencia="jugadores", enfoque="tip")
    assert brief["local"] is None and pieza["local"]    # con "destacar Pro" el local solo entra en el enfoque "local"
    client.post("/admin/api/redes/agente", json={"destacar_pro": False}, headers=H)
    stores.membresias_pro.pop("golazo@gmail.com", None)
    # Si el backend estuvo caído a las 07:00, publica al volver (misma fecha): jueves 10:15 → humor.
    reloj["utc"] = datetime(2026, 10, 1, 15, 15, tzinfo=_tz.utc)
    assert client.get("/admin/api/redes/agente", headers=H).json()["proxima"]["pendiente_hoy"] is True
    assert ag.tick() is True and stores.publicaciones_redes[0]["enfoque"] == "humor"
    # Modo "aprobar": el viernes deja BORRADOR (no publica); el operador ve la pieza, edita, regenera y aprueba.
    client.post("/admin/api/redes/agente", json={"modo": "aprobar"}, headers=H)
    reloj["utc"] = datetime(2026, 10, 2, 12, 0, tzinfo=_tz.utc)
    n = len(publicados)
    assert ag.tick() is True and len(publicados) == n
    j = client.get("/admin/api/redes/agente", headers=H).json()
    assert len(j["borradores"]) == 1 and j["borradores"][0]["audiencia"] == "jugadores" and j["borradores"][0]["enfoque"] == "finde" and j["corridas"][0]["resultado"] == "borrador"
    bid = j["borradores"][0]["id"]
    assert stores.to_state()["agente_fb"]["borradores"][0]["id"] == bid   # sobrevive al redeploy
    img = client.get(f"/admin/api/redes/agente/borrador/{bid}/imagen", headers=H).json()["imagen"]
    assert img.startswith("data:image/jpeg;base64,") and Image.open(io.BytesIO(base64.b64decode(img.split(",", 1)[1]))).size == (1080, 1080)
    r = client.post(f"/admin/api/redes/agente/borrador/{bid}/editar", json={"texto": "Texto corregido por el operador #pichangol", "titulo": "Sábado de partido"}, headers=H)
    assert r.json()["borrador"]["titulo"] == "Sábado de partido"
    r = client.post(f"/admin/api/redes/agente/borrador/{bid}/regenerar", headers=H).json()
    assert r["ok"] and r["borrador"]["id"] == bid and r["borrador"]["texto"] != "Texto corregido por el operador #pichangol" and r["borrador"]["audiencia"] == "jugadores"
    r = client.post(f"/admin/api/redes/agente/borrador/{bid}/aprobar", headers=H).json()
    assert r["ok"] and len(publicados) == n + 1 and r["borradores"] == [] and stores.publicaciones_redes[0]["origen"] == "aprobado"
    # "Publicar ahora" desde la torre (fuerza, aunque hoy ya se corrió) y "generar borrador ahora" + descartar.
    r = client.post("/admin/api/redes/agente/correr", json={"publicar": True, "audiencia": "duenos"}, headers=H).json()
    assert r["ok"] and r["publicado"] is True and len(publicados) == n + 2 and stores.publicaciones_redes[0]["audiencia"] == "duenos"
    r = client.post("/admin/api/redes/agente/correr", json={"publicar": False}, headers=H).json()
    assert r["ok"] and r["publicado"] is False and len(r["borradores"]) == 1
    assert client.post(f"/admin/api/redes/agente/borrador/{r['borradores'][0]['id']}/descartar", headers=H).json()["borradores"] == []
    # Facebook rechaza en modo auto → queda como borrador con el motivo y en la bitácora; no rompe el cron.
    client.post("/admin/api/redes/agente", json={"modo": "auto"}, headers=H)
    monkeypatch.setattr(pr, "publicar_facebook", lambda texto, png: {"ok": False, "error": "HTTP 400: (#190) Session has expired"})
    reloj["utc"] = datetime(2026, 10, 3, 12, 0, tzinfo=_tz.utc)
    assert ag.tick() is True
    j = client.get("/admin/api/redes/agente", headers=H).json()
    assert j["corridas"][0]["resultado"] == "error_facebook" and len(j["borradores"]) == 1 and "rechazó" in j["borradores"][0]["motivo"]
    assert stores.config["agente_fb_ultimo_dia"] == "2026-10-02"   # no cuenta como publicado: lo reintenta si el operador aprueba
    # Sin proveedor de imágenes IA → portada de marca; la receta guarda "brand:arte" y se recompone.
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [])
    brief = ag.planificar(ag.ahora_local(), audiencia="jugadores")
    pieza = ag.crear_pieza(brief)
    assert pieza["fotos"] and pieza["fotos"][0].startswith("data:image/png") and ag._receta(pieza)["fotos"] == ["brand:arte"] and len(pieza["png"]) > 10000
    assert len(ag.componer_receta({**ag._receta(pieza), "fecha": "2026-10-03"})) > 10000
    # Con proveedor de imágenes IA → arte fotorrealista del deporte del día (simulado), JPEG.
    from PIL import Image as _Im
    from marketing import arte_ia
    monkeypatch.setattr(ag, "_arte_disponible", lambda: True)
    monkeypatch.setattr(arte_ia, "disponible", lambda: True)
    pedidos = []
    monkeypatch.setattr(arte_ia, "fondo_para", lambda deporte, variante=0, tema="": (pedidos.append((deporte, variante, tema)) or _Im.new("RGB", (1024, 1280), (30, 120, 60))))
    pieza = ag.crear_pieza(ag.planificar(ag.ahora_local(), audiencia="jugadores"))
    assert pieza["fotos"][0].startswith("data:image/jpeg") and pedidos and pedidos[0][0] in ("futbol", "tenis", "padel", "pickleball")
    for k in ag.CFG.values():
        stores.config.pop(k, None)
    stores.agente_fb = {"borradores": [], "corridas": []}
