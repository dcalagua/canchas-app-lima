"""Torneos con la marca del ORGANIZADOR + portada `/tenis` (pedido del director,
20-oct-2026: los del tenis quieren hacer SU torneo y alquilar canchas aquí,
y "Pichangol suena a fútbol")."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from config import MARCA
from main import app
from marketing import afiche_campeonato, campeonato_web
from web import datos

client = TestClient(app)

TORNEO = {"id": "camp_1", "nombre": "Open de Primavera", "deporte": "tenis", "formato": "llave",
          "categoria": "4ta", "fechas": "8 – 9 nov", "sede": "Club Lawn Tennis", "inscripcionAbierta": True,
          "participantes": [], "partidos": [], "organizador": "Club Lawn Tennis de la Exposición",
          "logoUrl": "https://x.supabase.co/storage/v1/object/public/canchas/campeonatos/camp_1.jpg"}

TENIS = {"id": "c_ten", "nombre": "Tenis 1", "club": "Club Raqueta", "deporte": "tenis", "deportes": ["tenis"],
         "verificada": True, "registrada": True, "dueno": "duena@x.com", "precio_hora": 60.0,
         "lat": -12.09, "lng": -77.03, "barrio": "San Isidro", "direccion": "Av. 1"}
FUTBOL = dict(TENIS, id="c_fut", nombre="Fútbol 1", club="Sabor Golazo", deporte="futbol", deportes=["futbol"])


def test_pagina_del_torneo_lleva_la_marca_del_organizador_primero():
    h = campeonato_web.html_campeonato(TORNEO, "camp_1")
    assert "<title>Open de Primavera · Club Lawn Tennis de la Exposición</title>" in h
    assert "Organiza <b>Club Lawn Tennis de la Exposición</b>" in h
    assert "class=\"orglogo\"" in h and TORNEO["logoUrl"] in h
    # la plataforma sale chica, al pie
    assert f"con la tecnología de {MARCA}" in h
    assert "Organizado con" not in h


def test_sin_organizador_la_pagina_sigue_como_antes():
    c = dict(TORNEO, organizador="", logoUrl="")
    h = campeonato_web.html_campeonato(c, "camp_1")
    assert f"· {MARCA}</title>" in h and f"Organizado con <b>{MARCA}</b>" in h
    assert "orglogo" not in h.split("</style>", 1)[1]


def test_auspiciador_hace_de_organizador_si_no_hay_otro():
    o = campeonato_web.organizador_de(dict(TORNEO, organizador="", auspiciador="JORDI MEAT"))
    assert o["nombre"] == "JORDI MEAT"


def test_afiche_con_organizador_se_genera():
    png = afiche_campeonato.generar_afiche(dict(TORNEO, logoUrl=""), esperar_ia=False)
    assert Image.open(io.BytesIO(png)).size == (1080, 1350)


def test_portada_de_tenis_muestra_solo_raqueta_y_torneos(monkeypatch):
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [TENIS, FUTBOL])
    monkeypatch.setattr(datos, "campeonatos_publicos", lambda deps, limite=12: [dict(TORNEO)] if "tenis" in deps else [])
    r = client.get("/tenis")
    assert r.status_code == 200
    t = r.text
    # El título sale de los deportes prendidos en la torre (pádel está retirado).
    assert "Tenis y pickleball, en un solo lugar" in t and "Reservar pádel" not in t
    assert "Club Raqueta" in t and "Sabor Golazo" not in t
    assert "/c/camp_1" in t and "Organiza Club Lawn Tennis de la Exposición" in t
    assert "/partidos?tab=partner" in t and "/liga" in t and "/anfitrion/campeonatos" in t


def test_portada_de_tenis_vacia_no_se_rompe(monkeypatch):
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [])
    monkeypatch.setattr(datos, "campeonatos_publicos", lambda deps, limite=12: [])
    r = client.get("/tenis")
    assert r.status_code == 200 and "No hay torneos abiertos ahora" in r.text


def test_pestanas_y_titulos_siguen_los_deportes_activos(monkeypatch):
    from db.store import stores
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [])
    monkeypatch.setitem(stores.config, "deportes_activos", "futbol,tenis,pickleball,voley,basquet")
    t = client.get("/").text
    assert "data-dep='padel'" not in t and "data-dep='futsal'" not in t and "data-dep='voley'" in t
    assert "Reserva canchas de fútbol, tenis, pickleball, vóley y básquet" in t
    assert "href='/canchas?deporte=padel'" not in t   # pie
    # Si la torre prende pádel, vuelve solo.
    monkeypatch.setitem(stores.config, "deportes_activos", "futbol,tenis,padel")
    t = client.get("/").text
    assert "data-dep='padel'" in t and "Tenis y pádel, en un solo lugar" in client.get("/tenis").text
