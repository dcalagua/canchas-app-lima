"""Página pública del campeonato servida por el backend (`GET /c/{id}`)."""

from fastapi.testclient import TestClient

import config
from main import app
from marketing import campeonato_web

client = TestClient(app)


def test_sin_configuracion_avisa(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "")
    r = client.get("/c/camp_x")
    assert r.status_code == 503
    assert "text/html" in r.headers["content-type"]
    assert "no disponible" in r.text


def test_no_encontrado(monkeypatch):
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: None)
    r = client.get("/c/camp_x")
    assert r.status_code == 404
    assert "no existe" in r.text


def test_render_liga_html(monkeypatch):
    data = {
        "nombre": "Liga Este",
        "deporte": "tenis",
        "formato": "liga",
        "categoria": "Abierta",
        "moneda": "S/",
        "inscripcionAbierta": True,
        "costoInscripcion": 0,
        "participantes": [
            {"id": "p1", "nombre": "Ana"},
            {"id": "p2", "nombre": "Luis"},
        ],
        "partidos": [],
    }
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_1")
    assert r.status_code == 200
    # Content-Type correcto: era el bug de la Edge Function (texto plano).
    assert r.headers["content-type"].startswith("text/html")
    assert "charset=utf-8" in r.headers["content-type"]
    assert "Liga Este" in r.text
    assert "Ana" in r.text and "Luis" in r.text
    assert "Inscripciones abiertas" in r.text
    assert "<!doctype html>" in r.text


def test_tabla_ordena_por_puntos():
    c = {
        "participantes": [
            {"id": "a", "nombre": "A"},
            {"id": "b", "nombre": "B"},
        ],
        "partidos": [
            {"aId": "a", "bId": "b", "marcadorA": 2, "marcadorB": 1},
        ],
    }
    filas = campeonato_web._tabla(c)
    assert filas[0]["nombre"] == "A" and filas[0]["g"] == 1
    assert filas[1]["nombre"] == "B" and filas[1]["p"] == 1


def test_cta_unirse_en_la_app(monkeypatch):
    data = {"nombre": "Liga", "deporte": "tenis", "formato": "liga",
            "inscripcionAbierta": True, "participantes": [], "partidos": []}
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_9")
    assert "intent://c/camp_9" in r.text          # abre la app si está
    assert "browser_fallback_url" in r.text        # o lleva a descargarla
    assert "Unirme en la app" in r.text


def test_assetlinks(monkeypatch):
    monkeypatch.setattr(config, "ANDROID_CERT_SHA256", "")
    assert client.get("/.well-known/assetlinks.json").status_code == 404
    monkeypatch.setattr(config, "ANDROID_CERT_SHA256", "aa:bb")
    j = client.get("/.well-known/assetlinks.json").json()
    assert j[0]["target"]["package_name"] == "pe.ebim.pichangol"
    assert j[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB"]


def test_premios_y_auspiciador(monkeypatch):
    data = {"nombre": "Rally Challenge", "deporte": "tenis",
            "formato": "eliminacion", "inscripcionAbierta": True,
            "premios": "Trofeos\nTarros de pelotas",
            "auspiciador": "JORDI MEAT BOUTIQUE",
            "participantes": [], "partidos": []}
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_r")
    assert "Premios" in r.text and "Trofeos" in r.text
    assert "JORDI MEAT BOUTIQUE" in r.text
    assert "auspiciador oficial" in r.text
    assert 'property="og:title"' in r.text  # vista previa rica en WhatsApp


def test_enlace_del_capitan_une_directo_al_equipo(monkeypatch):
    """`/c/{id}?equipo=CODIGO` (fútbol): el CTA pasa a "Unirme al equipo X" y
    el intent:// lleva el código para que la app no lo pida. Un código que ya
    no existe avisa y deja el CTA normal."""
    data = {"nombre": "Copa Beata", "deporte": "futbol", "formato": "grupos",
            "inscripcionAbierta": True, "partidos": [],
            "participantes": [{"id": "p1", "nombre": "Los Tigres", "codigo": "4KZ9AB",
                               "capitanEmail": "capi@gmail.com",
                               "roster": [{"nombre": "Capi", "email": "capi@gmail.com"}]}]}
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    r = client.get("/c/camp_9?equipo=4kz9ab")
    assert r.status_code == 200
    assert "Te invitaron al equipo «Los Tigres»" in r.text
    assert "Unirme al equipo en la app" in r.text
    assert "intent://c/camp_9?equipo=4KZ9AB#Intent;scheme=pichangol" in r.text
    assert "1 jugador en el plantel" in r.text and "capitán capi" in r.text
    # Código que no existe → CTA normal + aviso.
    r = client.get("/c/camp_9?equipo=ZZZZZZ")
    assert "Unirme en la app" in r.text and "ya no es válido" in r.text
    assert "intent://c/camp_9#Intent" in r.text
    # Sin ?equipo= nada cambia.
    r = client.get("/c/camp_9")
    assert "Te invitaron" not in r.text and "intent://c/camp_9#Intent" in r.text
    # En tenis no hay equipos: el código se ignora.
    data["deporte"] = "tenis"
    r = client.get("/c/camp_9?equipo=4KZ9AB")
    assert "Te invitaron" not in r.text and "ya no es válido" not in r.text


def test_descarga_va_a_play_en_produccion(monkeypatch):
    """Sin la app, el botón cae a Play Store en PRD y al Release de GitHub en
    dev/QAS (el APK de pruebas no está en la tienda). `APP_DOWNLOAD_URL`
    manda si está."""
    import importlib
    data = {"nombre": "Liga", "deporte": "tenis", "formato": "liga",
            "inscripcionAbierta": True, "participantes": [], "partidos": []}
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: data)
    monkeypatch.setattr(config, "APP_DOWNLOAD_URL", config.PLAY_STORE_URL)
    r = client.get("/c/camp_9")
    assert "play.google.com%2Fstore%2Fapps%2Fdetails%3Fid%3Dpe.ebim.pichangol" in r.text
    assert 'href="https://play.google.com/store/apps/details?id=pe.ebim.pichangol">Descargar la app' in r.text
    monkeypatch.setattr(config, "APP_DOWNLOAD_URL", config.GITHUB_RELEASE_URL)
    r = client.get("/c/camp_9")
    assert "github.com%2Fdcalagua" in r.text and "play.google.com" not in r.text
    # La decisión por ambiente, tal como la calcula config al arrancar.
    monkeypatch.setenv("PICHANGOL_ENTORNO", "PRD"); monkeypatch.delenv("APP_DOWNLOAD_URL", raising=False)
    cfg = importlib.reload(config)
    assert cfg.APP_DOWNLOAD_URL == cfg.PLAY_STORE_URL
    monkeypatch.setenv("PICHANGOL_ENTORNO", "QAS")
    cfg = importlib.reload(config)
    assert cfg.APP_DOWNLOAD_URL == cfg.GITHUB_RELEASE_URL
    monkeypatch.setenv("APP_DOWNLOAD_URL", "https://ejemplo.test/app ")
    cfg = importlib.reload(config)
    assert cfg.APP_DOWNLOAD_URL == "https://ejemplo.test/app"
    monkeypatch.delenv("PICHANGOL_ENTORNO", raising=False); monkeypatch.delenv("APP_DOWNLOAD_URL", raising=False)
    importlib.reload(config)


def test_assetlinks_acepta_huella_sin_dos_puntos(monkeypatch):
    """apksigner imprime la SHA-256 como 64 hex seguidos; Google exige
    `AA:BB:…`. Se normaliza, y se aceptan varias separadas por coma."""
    cruda = "21e5ada0d358f99b742e7c28ac25d68a99ecbc26dca98d5f80f97d73bf38ec28"
    monkeypatch.setattr(config, "ANDROID_CERT_SHA256", f"{cruda}, AA:BB")
    j = client.get("/.well-known/assetlinks.json").json()
    h = j[0]["target"]["sha256_cert_fingerprints"]
    assert h[0].startswith("21:E5:AD:A0:") and h[0].endswith(":EC:28") and h[0].count(":") == 31
    assert h[1] == "AA:BB"
