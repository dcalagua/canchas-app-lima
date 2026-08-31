"""PÁGINAS LEGALES: Google Play exige una política de privacidad y una URL
pública de eliminación de cuenta, ambas accesibles SIN instalar la app."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402

cli = TestClient(main.app)


def test_las_dos_paginas_son_publicas():
    """Sin token ni sesión: Play las revisa desde fuera."""
    for ruta in ("/legal/privacidad", "/legal/eliminar-cuenta", "/legal/terminos"):
        r = cli.get(ruta)
        assert r.status_code == 200, ruta
        assert "text/html" in r.headers["content-type"]


def test_la_privacidad_declara_lo_que_la_app_hace_hoy():
    """Una política que no menciona un dato que sí se recoge es peor que no
    tenerla: Play la rechaza y ante la ley no cubre nada."""
    html = cli.get("/legal/privacidad").text.lower()
    for tema in ("ubicación", "culqi", "notificaciones", "entrenador",
                 "documento", "menores", "transferencia internacional",
                 "29733"):
        assert tema in html, f"la política no menciona: {tema}"
    # Debe enlazar la eliminación de cuenta (Play lo revisa).
    assert "/legal/eliminar-cuenta" in cli.get("/legal/privacidad").text


def test_eliminar_cuenta_dice_que_se_borra_y_que_se_conserva():
    """Play exige ambas listas explícitas, no sólo el 'cómo pedirlo'."""
    html = cli.get("/legal/eliminar-cuenta").text.lower()
    assert "qué se elimina" in html
    assert "qué se conserva" in html
    assert "30 días" in html          # plazo comprometido
    assert "dcalagua@ebim.pe" in html  # vía de contacto


def test_el_callback_de_meta_sigue_vivo():
    """La página de redes y su callback no se rompieron al agregar la de cuenta."""
    assert cli.get("/legal/eliminacion-datos").status_code == 200
    # Sin firma válida, el callback responde igual (no revienta).
    assert cli.post("/legal/eliminacion-datos").status_code in (200, 400)
