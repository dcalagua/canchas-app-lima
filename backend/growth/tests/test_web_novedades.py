"""Novedades (estados/historias) y Canales en la web = los del APK (pedido del
director, 29-sep-2026: "en la web implementa las mismas funcionalidades que
existen en el app")."""
import json
import re
import struct
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import config
from main import app
from web import almacen, sesion
from web import jugador_novedades as nv

AHORA = datetime.now(timezone.utc)


def _cli(monkeypatch, email="ana@gmail.com"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Ana Pérez", "foto": "https://lh3/ana.jpg"}))
    return cli


def _est(id_, autor, tipo="texto", texto="Hola", media="", hace_h=1, **extra):
    return {"id": id_, "autor_email": autor, "autor_nombre": autor.split("@")[0].title(), "tipo": tipo, "texto": texto,
            "foto_url": media, "bg": 0xFF7B61FF, "creado_en": AHORA - timedelta(hours=hace_h), **extra}


def _mp4(segundos: float) -> bytes:
    """MP4 mínimo (ftyp + moov/mvhd v0) para probar el tope de duración."""
    ftyp = struct.pack(">I4s4sI", 16, b"ftyp", b"isom", 0)
    cuerpo = bytes([0, 0, 0, 0]) + struct.pack(">IIII", 0, 0, 1000, int(segundos * 1000)) + b"\0" * 80
    mvhd = struct.pack(">I4s", 8 + len(cuerpo), b"mvhd") + cuerpo
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    return ftyp + moov + b"\0" * 64


def _datos_script(html: str, var: str) -> dict:
    m = re.search(r"window\." + var + r" = (\{.*?\});</script>", html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def _base(monkeypatch):
    agenda = {"apodos": {"luis@x.com": "Lucho"}, "contactos": ["luis@x.com", "bloq@x.com"], "bloqueados": ["bloq@x.com"]}
    monkeypatch.setattr(nv, "agenda_de", lambda e: agenda)
    monkeypatch.setattr(nv, "perfiles", lambda es: {"luis@x.com": {"nombre": "Luis Soto", "foto_url": "https://f/luis.jpg"},
                                                    "eva@x.com": {"nombre": "Eva", "foto_url": ""}})
    monkeypatch.setattr(nv, "_limpiar_en_segundo_plano", lambda e: None)
    monkeypatch.setattr(nv, "canales_todos", lambda limite=500: [])
    monkeypatch.setattr(nv, "seguidos_de", lambda e: set())
    monkeypatch.setattr(nv, "posts_agrupados", lambda ids, limite=400: {})
    monkeypatch.setattr(nv, "ultimas_de", lambda ids: {})


def test_novedades_solo_contactos_sin_correos_y_con_visto(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app, base_url="https://testserver").get("/novedades", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fnovedades"

    _base(monkeypatch)
    pedidos = {}

    def vig(autores):
        pedidos["autores"] = autores
        todos = [_est("st_1000000000001", "luis@x.com", hace_h=3), _est("st_1000000000002", "luis@x.com", tipo="foto",
                 media="https://s/estados/st_1000000000002.jpg", texto="Golazo", hace_h=1,
                 musica_preview="https://audio-ssl.itunes.apple.com/x.m4a", musica_titulo="Tema", musica_artista="Banda", musica_inicio_ms=5000),
                 _est("st_1000000000003", "ana@gmail.com", hace_h=2)]
        return [f for f in todos if f["autor_email"] in autores]
    monkeypatch.setattr(nv, "estados_vigentes", vig)
    monkeypatch.setattr(nv, "vistos_por", lambda e, ids: {"st_1000000000001"})
    monkeypatch.setattr(nv, "vistas_de", lambda ids: {"st_1000000000003": [("luis@x.com", AHORA)]})
    html = _cli(monkeypatch).get("/novedades").text
    # Privacidad del app (`_conocidos`): solo mis contactos no bloqueados (+ yo).
    assert sorted(pedidos["autores"]) == ["ana@gmail.com", "luis@x.com"]
    d = _datos_script(html, "NV_CFG")["inicial"]
    assert [a["nombre"] for a in d["autores"]] == ["Lucho"]           # apodo manda
    a = d["autores"][0]
    assert [i["visto"] for i in a["items"]] == [True, False]
    assert a["items"][0]["bg"] == "#7B61FF"
    assert a["items"][1]["musica"]["inicio"] == 5000 and a["items"][1]["musica"]["titulo"] == "Tema"
    assert d["mi"]["items"][0]["vistas"] == 1
    assert "luis@x.com" not in html and "bloq@x.com" not in html      # nunca correos ajenos
    assert "Actualizaciones recientes" in html and "Canales" in html
    js = html.split("window.NV_CFG")[1]
    assert " confirm(" not in js and "alert(" not in js and "prompt(" not in js


def test_visto_responder_y_eliminar_validan_en_el_servidor(monkeypatch):
    _base(monkeypatch)
    ests = {"st_1000000000001": _est("st_1000000000001", "luis@x.com", tipo="foto", media="https://s/l.jpg", texto=""),
            "st_1000000000009": _est("st_1000000000009", "eva@x.com"),
            "st_1000000000010": _est("st_1000000000010", "luis@x.com", hace_h=30)}
    monkeypatch.setattr(nv, "estado", lambda i: ests.get(i))
    vistos = []
    monkeypatch.setattr(nv, "marcar_visto", lambda i, e: vistos.append((i, e)) or True)
    cli = _cli(monkeypatch)
    assert cli.post("/web/novedades/visto", json={"id": "st_1000000000001"}).json()["ok"]
    assert vistos == [("st_1000000000001", "ana@gmail.com")]
    # De alguien que NO es mi contacto, o vencida (>24 h) → no.
    assert cli.post("/web/novedades/visto", json={"id": "st_1000000000009"}).status_code == 404
    assert cli.post("/web/novedades/visto", json={"id": "st_1000000000010"}).status_code == 404
    enviados = []
    monkeypatch.setattr(nv, "insertar_mensaje", lambda f: enviados.append(f) or {**f})
    r = cli.post("/web/novedades/responder", json={"id": "st_1000000000001", "texto": "¡Qué golazo!"})
    assert r.json()["ok"]
    f = enviados[0]
    assert f["hilo"] == "directo_ana@gmail.com|luis@x.com" and f["tipo"] == "directo" and f["cuenta_email"] == "luis@x.com"
    assert f["resp_texto"] == "📷 Foto" and f["resp_media"] == "https://s/l.jpg" and f["resp_autor"] == "Lucho"
    assert cli.post("/web/novedades/responder", json={"id": "st_1000000000009", "texto": "x"}).status_code == 404
    # Eliminar: solo lo mío.
    borrados = []
    monkeypatch.setattr(nv, "borrar_estado", lambda i, a: borrados.append((i, a)) or (a == "ana@gmail.com" and i == "st_mio"))
    assert cli.post("/web/novedades/estado/st_mio/eliminar").json()["ok"]
    assert cli.post("/web/novedades/estado/st_1000000000001/eliminar").status_code == 404
    assert borrados[-1] == ("st_1000000000001", "ana@gmail.com")
    # Quién vio: solo el autor.
    assert cli.get("/web/novedades/estado/st_1000000000001/vistas").status_code == 404


def test_publicar_estado_texto_foto_y_video_como_el_app(monkeypatch):
    _base(monkeypatch)
    guardados = []
    monkeypatch.setattr(nv, "insertar_estado", lambda f: guardados.append(f) or True)
    cli = _cli(monkeypatch)
    html = cli.get("/novedades/estado/nuevo?tipo=texto").text
    for v in nv.FONDOS:
        assert f"data-bg='{v}'" in html                               # los 8 fondos del app
    assert "Publicar estado" in html and "nvMusBox" in html
    # Texto: fondo fuera del catálogo → el de siempre; >280 → no.
    r = cli.post("/web/novedades/estado", json={"tipo": "texto", "texto": "Hoy pichanga 8pm", "bg": 123,
                                                "musica": {"preview": "https://evil.com/a.m4a", "titulo": "x"}})
    assert r.json()["ok"]
    g = guardados[-1]
    assert g["bg"] == nv.BG_DEFECTO and g["tipo"] == "texto" and g["autor_email"] == "ana@gmail.com"
    assert g["id"].startswith("st_") and "musica_preview" not in g                  # música solo de Apple
    assert cli.post("/web/novedades/estado", json={"tipo": "texto", "texto": "x" * 281}).status_code == 400
    r = cli.post("/web/novedades/estado", json={"tipo": "texto", "texto": "Con música", "bg": nv.FONDOS[3],
                                                "musica": {"preview": "https://audio-ssl.itunes.apple.com/p.m4a", "titulo": "T",
                                                           "artista": "A", "inicio": 7000, "track": "https://music.apple.com/t"}})
    assert r.json()["ok"] and guardados[-1]["musica_inicio_ms"] == 7000 and guardados[-1]["bg"] == nv.FONDOS[3]
    # Foto: sube a estados/<id>.jpg y publica con la firma de ESTA cuenta.
    subidas = []
    monkeypatch.setattr(almacen, "disponible", lambda: True)
    monkeypatch.setattr(almacen, "subir", lambda b, ruta, d, ct="", max_bytes=None: subidas.append((b, ruta, ct)) or almacen.url_publica(ruta, b) + "?v=1")
    s = cli.post("/web/novedades/estado/subir?tipo=foto", content=b"\xff\xd8\xff" + b"0" * 100).json()
    assert s["ok"] and subidas[-1] == ("estados", s["id"] + ".jpg", "image/jpeg")
    assert cli.post("/web/novedades/estado/subir?tipo=foto", content=b"GIF89a").status_code == 400
    otro = _cli(monkeypatch, "eva@x.com")
    assert otro.post("/web/novedades/estado", json={"tipo": "foto", **{k: s[k] for k in ("id", "url", "tk")}}).status_code == 400
    r = cli.post("/web/novedades/estado", json={"tipo": "foto", "texto": "Golazo", **{k: s[k] for k in ("id", "url", "tk")}})
    assert r.json()["ok"] and guardados[-1]["foto_url"] == s["url"] and guardados[-1]["texto"] == "Golazo"
    # Video: tope de 30 s leído del propio MP4.
    assert nv.duracion_mp4(_mp4(12.5)) == 12.5 and nv.duracion_mp4(b"no es video") is None
    assert cli.post("/web/novedades/estado/subir?tipo=video", content=_mp4(45)).status_code == 400
    v = cli.post("/web/novedades/estado/subir?tipo=video", content=_mp4(20)).json()
    assert v["ok"] and subidas[-1] == ("estados", v["id"] + ".mp4", "video/mp4")
    assert cli.post("/web/novedades/estado", json={"tipo": "video", **{k: v[k] for k in ("id", "url", "tk")}}).json()["ok"]


def _canales(monkeypatch):
    cs = {"ch_1000000000001": {"id": "ch_1000000000001", "nombre": "Pichangol San Borja", "descripcion": "Novedades del club",
                               "foto_url": "", "owner_email": "ana@gmail.com", "creado": AHORA - timedelta(days=3), "seguidores": 4},
          "ch_1000000000002": {"id": "ch_1000000000002", "nombre": "Tenis Lima", "descripcion": "", "foto_url": "https://f/c.jpg",
                               "owner_email": "luis@x.com", "creado": AHORA - timedelta(days=2), "seguidores": 10},
          "ch_1000000000003": {"id": "ch_1000000000003", "nombre": "Fulbito", "descripcion": "", "foto_url": "",
                               "owner_email": "eva@x.com", "creado": AHORA - timedelta(days=1), "seguidores": 0}}
    monkeypatch.setattr(nv, "canales_todos", lambda limite=500: list(cs.values()))
    monkeypatch.setattr(nv, "canal", lambda i: cs.get(i))
    monkeypatch.setattr(nv, "seguidos_de", lambda e: {"ch_1000000000002"})
    post = {"id": "cp_1000000000005", "canal_id": "ch_1000000000002", "autor_email": "luis@x.com", "autor_nombre": "Luis",
            "tipo": "texto", "texto": "Torneo el sábado www.pichangol.app", "media_url": "", "creado": AHORA}
    monkeypatch.setattr(nv, "ultimas_de", lambda ids: {"ch_1000000000002": post})
    monkeypatch.setattr(nv, "posts_agrupados", lambda ids, limite=400: {"ch_1000000000002": [post]})
    monkeypatch.setattr(nv, "posts_de", lambda i, limite=50: [post] if i == "ch_1000000000002" else [])
    monkeypatch.setattr(nv, "reacciones_de", lambda i: {"cp_1000000000005": {"eva@x.com": "🔥", "ana@gmail.com": "⚽"}})
    monkeypatch.setattr(nv, "perfiles", lambda es: {"luis@x.com": {"nombre": "Luis Soto", "foto_url": ""}})
    return cs


def test_canales_seguir_crear_editar_y_publicar_como_el_app(monkeypatch):
    _base(monkeypatch)
    _canales(monkeypatch)
    cli = _cli(monkeypatch)
    html = cli.get("/canales").text
    d = _datos_script(html, "NV_CAN")["inicial"]
    por = {c["nombre"]: c for c in d["canales"]}
    assert por["Pichangol San Borja"]["mio"] and por["Tenis Lima"]["sigo"] and not por["Fulbito"]["sigo"]
    assert por["Tenis Lima"]["ultima"].startswith("🔗 ")
    assert "luis@x.com" not in html and "eva@x.com" not in html
    # Novedades muestra solo los que sigo + los míos (con los no leídos de otros).
    nov = _datos_script(cli.get("/novedades").text, "NV_CFG")["inicial"]["canales"]
    assert [c["nombre"] for c in nov] == ["Tenis Lima", "Pichangol San Borja"] and len(nov[0]["nuevos"]) == 1
    # Ficha del canal: reacciones agregadas (sin quién), la mía marcada; sin "Generar con IA".
    h = cli.get("/canales/ch_1000000000002").text
    cd = _datos_script(h, "NV_CD")["inicial"]
    assert cd["posts"][0]["reacc"] == {"emojis": ["🔥", "⚽"], "total": 2, "mia": "⚽"}
    assert "Generar con IA" not in h and "id='nvPubTxt'" not in h                       # no soy el dueño
    assert "id='nvPubTxt'" in cli.get("/canales/ch_1000000000001").text                  # sí soy el dueño
    assert cli.get("/canales/ch_9999999999999").status_code == 404
    # Seguir / dejar.
    seg = []
    monkeypatch.setattr(nv, "seguir", lambda i, e, si: seg.append((i, e, si)) or True)
    assert cli.post("/web/canales/ch_1000000000003/seguir", json={"seguir": True}).json()["ok"]
    assert seg[-1] == ("ch_1000000000003", "ana@gmail.com", True)
    assert cli.post("/web/canales/ch_1000000000001/seguir", json={"seguir": True}).status_code == 400
    # Crear: nombre obligatorio ≤50, dueño = sesión.
    creados = []
    monkeypatch.setattr(nv, "crear_canal", lambda f: creados.append(f) or True)
    assert cli.post("/web/canales/crear", json={"nombre": " "}).status_code == 400
    assert cli.post("/web/canales/crear", json={"nombre": "x" * 51}).status_code == 400
    r = cli.post("/web/canales/crear", json={"nombre": "Pádel Miraflores", "descripcion": "Turnos y torneos",
                                             "owner_email": "otro@x.com"}).json()
    assert r["ok"] and creados[-1]["owner_email"] == "ana@gmail.com" and r["id"].startswith("ch_")
    # Editar / publicar en canal ajeno → 404.
    monkeypatch.setattr(nv, "actualizar_canal", lambda i, o, c: True)
    assert cli.post("/web/canales/ch_1000000000002/editar", json={"nombre": "Mío"}).status_code == 404
    assert cli.post("/web/canales/ch_1000000000001/editar", json={"nombre": "Nuevo nombre"}).json()["ok"]
    assert cli.get("/canales/ch_1000000000002/editar", follow_redirects=False).status_code == 303
    assert "Guardar cambios" in cli.get("/canales/ch_1000000000001/editar").text
    posts = []
    monkeypatch.setattr(nv, "insertar_post", lambda f: posts.append(f) or True)
    assert cli.post("/web/canales/ch_1000000000002/publicar", json={"tipo": "texto", "texto": "hola"}).status_code == 404
    r = cli.post("/web/canales/ch_1000000000001/publicar", json={"tipo": "texto", "texto": "Cancha libre hoy 7pm"}).json()
    assert r["ok"] and r["post"]["texto"] == "Cancha libre hoy 7pm" and posts[-1]["autor_email"] == "ana@gmail.com"
    # Video del canal: hasta 60 s (no 30) en canales/<canal>/<post>.mp4.
    monkeypatch.setattr(almacen, "disponible", lambda: True)
    monkeypatch.setattr(almacen, "subir", lambda b, ruta, d, ct="", max_bytes=None: almacen.url_publica(ruta, b) + "?v=1")
    assert cli.post("/web/canales/ch_1000000000001/media?tipo=video", content=_mp4(75)).status_code == 400
    m = cli.post("/web/canales/ch_1000000000001/media?tipo=video", content=_mp4(45)).json()
    assert m["ok"] and "/canales/ch_1000000000001/" + m["id"] + ".mp4" in m["url"]
    assert cli.post("/web/canales/ch_1000000000001/publicar", json={"tipo": "video", "id": m["id"], "url": m["url"], "tk": "x"}).status_code == 400
    assert cli.post("/web/canales/ch_1000000000001/publicar", json={"tipo": "video", "id": m["id"], "url": m["url"], "tk": m["tk"]}).json()["ok"]
    # Reacciones: solo el catálogo del app.
    monkeypatch.setattr(nv, "post_existe", lambda c, p: True)
    alt = []
    monkeypatch.setattr(nv, "alternar_reaccion", lambda c, p, e, em: alt.append((c, p, e, em)) or True)
    assert cli.post("/web/canales/ch_1000000000002/post/cp_1000000000005/reaccion", json={"emoji": "💩"}).status_code == 400
    r = cli.post("/web/canales/ch_1000000000002/post/cp_1000000000005/reaccion", json={"emoji": "🔥"}).json()
    assert r["ok"] and alt[-1] == ("ch_1000000000002", "cp_1000000000005", "ana@gmail.com", "🔥")
    # Borrar post: solo el dueño.
    monkeypatch.setattr(nv, "borrar_post", lambda p, c: {"media_url": ""})
    assert cli.post("/web/canales/ch_1000000000002/post/cp_1000000000005/eliminar").status_code == 404
    assert cli.post("/web/canales/ch_1000000000001/post/cp_1/eliminar").json()["ok"]
