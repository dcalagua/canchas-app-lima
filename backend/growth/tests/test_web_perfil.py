"""Perfil en la web = pantalla Perfil del app (pedido del director,
29-sep-2026: "esto no lo veo en la web")."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import config
from db.store import Reto, stores
from main import app
from web import datos, sesion


def _cli(monkeypatch, email="ana@gmail.com"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Ana Pérez", "foto": "https://lh3/ana.jpg"}))
    return cli


def test_perfil_web_como_el_app(monkeypatch):
    # Sin sesión → a iniciar sesión y volver al perfil.
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app, base_url="https://testserver").get("/perfil", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fperfil"

    monkeypatch.setattr(datos, "reservas_de_usuario", lambda e, limite=200: [{"id": "r1"}, {"id": "r2"}, {"id": "r3"}])
    monkeypatch.setattr(datos, "niveles_de", lambda e: [{"deporte": "tenis", "nivel": 3.5, "partidos": 4, "victorias": 2}])
    monkeypatch.setattr(datos, "esta_verificado", lambda e: True)
    monkeypatch.setattr(datos, "puntos_de", lambda e: {"ganados": 250, "canjeados": 100, "disponibles": 150})
    monkeypatch.setattr(datos, "tiene_matriculas", lambda e: True)
    monkeypatch.setattr(datos, "boleador", lambda e: None)
    ahora = datetime.now(timezone.utc)
    antes = list(stores.retos)
    stores.retos[:] = [
        Reto(id=901, retador_email="luis@x.com", retador_nombre="Luis", retado_email="ana@gmail.com",
             retado_nombre="Ana", deporte="tenis", creado_en=ahora),  # recibido pendiente → cuenta
        Reto(id=902, retador_email="ana@gmail.com", retador_nombre="Ana", retado_email="eva@x.com",
             retado_nombre="Eva", deporte="tenis", creado_en=ahora, estado="aceptado"),  # enviado aceptado → cuenta
        Reto(id=903, retador_email="ana@gmail.com", retador_nombre="Ana", retado_email="eva@x.com",
             retado_nombre="Eva", deporte="tenis", creado_en=ahora - timedelta(days=1)),  # enviado pendiente → no
    ]
    antes_pro = dict(stores.membresias_pro)
    stores.membresias_pro["ana@gmail.com"] = {"hasta": (ahora + timedelta(days=10)).isoformat()}
    try:
        html = _cli(monkeypatch).get("/perfil").text
    finally:
        stores.retos[:] = antes
        stores.membresias_pro.clear(); stores.membresias_pro.update(antes_pro)
    # Tarjeta de identidad: foto, PRO, verificado y las 3 cifras del app.
    assert "https://lh3/ana.jpg" in html and "👑 PRO" in html and "Identidad verificada" in html
    assert "<b>3</b><small>Reservas</small>" in html
    assert "<b>1</b><small>Deporte con nivel</small>" in html
    assert "<b>2</b><small>Retos pendientes</small>" in html
    # Atajos, banner del anfitrión y nivel.
    assert "href='/mis-reservas'" in html and "NOVEDAD" in html and "Marketplace" in html
    assert "¿Tienes una cancha o academia?" in html and "Tenis · 3.5" in html
    # El MISMO menú del app; lo que vive en la app abre un modal (nunca confirm()).
    for t in ("Mis clases y pagos", "Mis bonos", "Mis pagos", "Mis puntos · 150 ⭐", "Campeonatos",
              "Mundo tenis", "Liga de tenis Pichangol", "Ser boleador", "Mi billetera", "Mi país",
              "Configuración de la cuenta", "Cierra la sesión", "Eliminar mi cuenta", "Cambiar a modo anfitrión"):
        assert t in html, t
    assert "href='/anfitrion/campeonatos'" in html and "href='/anfitrion/boleador'" in html
    assert "href='/legal/eliminar-cuenta'" in html and "pcgConfirmar(" in html
    js = html.split("class='perf-host'")[1]
    assert " confirm(" not in js and "alert(" not in js
    # El avatar y el menú ☰ llevan al perfil.
    assert "href='/perfil'" in html and "👤 Perfil" in html


def test_perfil_sin_matriculas_ni_nivel(monkeypatch):
    monkeypatch.setattr(datos, "reservas_de_usuario", lambda e, limite=200: [])
    monkeypatch.setattr(datos, "niveles_de", lambda e: [])
    monkeypatch.setattr(datos, "esta_verificado", lambda e: False)
    monkeypatch.setattr(datos, "puntos_de", lambda e: {"ganados": 0, "canjeados": 0, "disponibles": 0})
    monkeypatch.setattr(datos, "tiene_matriculas", lambda e: False)
    monkeypatch.setattr(datos, "boleador", lambda e: {"email": "bo@x.com"})
    html = _cli(monkeypatch, "bo@x.com").get("/perfil").text
    assert "Mis clases y pagos" not in html and "👑 PRO" not in html
    assert "<b>0</b><small>Reservas</small>" in html and "Autoevalúate en 30 segundos" in html
    assert "Soy boleador" in html and ">Mis puntos<" in html


def test_puntos_sin_base_son_cero(monkeypatch):
    monkeypatch.setattr(datos.pg, "habilitado", False)
    assert datos.puntos_de("x@x.com") == {"ganados": 0, "canjeados": 0, "disponibles": 0}
    assert datos.niveles_de("x@x.com") == [] and datos.tiene_matriculas("x@x.com") is False
