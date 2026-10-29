"""Arreglos de la revisión visual de QAS (29-oct-2026): textos sin repetir,
montos con separador de miles, título de /entrar según el destino, extras
con la cantidad solo al marcarlos y canchas de Google con "Ver más"."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from web import router, ui  # noqa: E402
from tests.test_web_reservas import client, db  # noqa: E402,F401


def test_unir_lugar_no_repite_la_zona():
    assert ui.unir_lugar("Calle Los Laureles 365, San Isidro", "San Isidro") == "Calle Los Laureles 365, San Isidro"
    assert ui.unir_lugar("Club Raqueta San Isidro", "san isidro", sep=" · ") == "Club Raqueta San Isidro"
    assert ui.unir_lugar("Av. Larco 1150", "Miraflores") == "Av. Larco 1150, Miraflores"
    assert ui.unir_lugar("", "Surco", None) == "Surco"


def test_monto_con_separador_de_miles():
    assert ui.monto(56070, "S/", 0) == "S/ 56 070"
    assert ui.monto(1580, "S/") == "S/ 1 580.00"
    assert ui.monto(None, "$") == "$ 0.00"


def test_entrar_dice_para_que_es(db, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    client.cookies.clear()
    assert "Inicia sesión para entrar al modo anfitrión" in client.get("/entrar?volver=/anfitrion/reservas").text
    assert "Inicia sesión para jugar" in client.get("/entrar?volver=/partidos").text
    assert "Inicia sesión para reservar" in client.get("/entrar?volver=/reservar/c_lima").text
    assert router._motivo_entrar("/anfitrionx")[0] == "Inicia sesión para reservar"   # solo rutas exactas o hijas


def test_explorador_limita_las_canchas_de_google_con_ver_mas(db):
    html = client.get("/").text
    assert "id='btnDescMas'" in html and "DESC_MAX = 8" in html
