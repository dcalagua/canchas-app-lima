"""Barra del modo anfitrión con los cinco desplegables (rediseño del
diseñador, 16-nov-2026, `docs/plan/REDISENO_ANFITRION.md` fase F0)."""
import re

import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from web import nav_anfitrion as nav
from web import ui
from web.anfitrion import GRUPOS_MENU

SES = {"email": "dueno@x.com", "nombre": "Don Dueño"}
ITEMS = [it for _g, its in GRUPOS_MENU for it in its]


def _con_ruta(ruta, fn):
    tok = ui.RUTA_REQUEST.set(ruta)
    try:
        return fn()
    finally:
        ui.RUTA_REQUEST.reset(tok)


def test_cada_modulo_tiene_icono_de_color_y_el_menu_es_el_del_disenador(monkeypatch):
    from web import iconos
    assert set(nav.ICONOS) == {it[0] for it in ITEMS}
    assert all(iconos.existe(ico) and re.fullmatch(r"#[0-9A-F]{6}", col) for col, ico in nav.ICONOS.values())
    assert [g for g, _ in GRUPOS_MENU] == ["Mi club", "Negocio", "Academia", "Comercio", "Roles"]
    assert [len(i) for _, i in GRUPOS_MENU] == [7, 7, 3, 2, 2]
    # Textos del desplegable sin jerga de un solo país (Culqi/Yape/Plin solo en Perú).
    assert not any(re.search(r"Culqi|Yape|Plin", d) for d in nav.DESC.values())


def test_marca_el_modulo_de_la_pagina_y_su_grupo(monkeypatch):
    monkeypatch.setitem(stores.config, "acad_modelo", "suscripcion")
    html = _con_ruta("/anfitrion/academia/plan", lambda: nav.menu_html(SES, "/anfitrion/academia/plan"))
    sel = re.findall(r"<details class='anf-dd sel'[^>]*><summary class='anf-dd-btn'><span>([^<]+)", html)
    assert sel == ["Academia"]
    assert "aria-current='page'" in html and html.count("aria-current='page'") == 1
    assert re.search(r"class='anf-dd-it sel'[^>]*href='/anfitrion/academia/plan'", html)
    for ruta, clave in (("/anfitrion/calendario", "mis-canchas"), ("/anfitrion/ocupacion", "reportes"),
                        ("/anfitrion/cobros-club/devoluciones", "cobros-club"), ("/anfitrion/cobros/agregar", "cobros"),
                        ("/anfitrion", "")):
        assert nav.clave_actual(ruta, ITEMS) == clave, ruta


def test_recepcion_solo_ve_lo_que_su_rol_puede_abrir(monkeypatch):
    from web import encargados, permisos
    monkeypatch.setattr(encargados, "disponible", lambda: True)
    monkeypatch.setattr(permisos, "es_solo_encargado", lambda email: True)
    html = nav.menu_html(SES, "/anfitrion")
    for k in permisos.MENU_SOLO_DUENO | {"encargados"}:
        href = next(it[5] for it in ITEMS if it[0] == k)
        assert f"href='{href}'" not in html, k
    assert "href='/anfitrion/mis-canchas'" in html and "href='/anfitrion/pagos-por-confirmar'" in html
    # Plan Academia solo con el modelo de suscripción.
    monkeypatch.setitem(stores.config, "acad_modelo", "comision")
    assert "/anfitrion/academia/plan" not in nav.menu_html(SES, "/anfitrion")


def test_barra_blanca_con_pastilla_avatar_y_boton_de_menu_para_el_celular():
    html = _con_ruta("/anfitrion/tienda", lambda: ui.cabecera(ses=SES, modo="anfitrion", volver="/anfitrion"))
    assert "class='nav anf-cab'" in html and "cl-barra" not in html
    assert "class='anf-modo' href='/'" in html and "Modo anfitrión" in html
    # El avatar abre el menú de la cuenta (sin ☰ aparte) y ahí sigue "Cambiar a modo jugador".
    assert "id='btnMenu' aria-label='Tu cuenta'" in html and "M4 7h16M4 12h16M4 17h16'/></svg></button>" not in html.split("anf-nav-btn")[0]
    assert "Cambiar a modo jugador" in html
    assert "id='anfNavBtn' aria-controls='anfNav'" in html
    assert "anf-dd-it sel" in html and "href='/anfitrion/tienda'" in html


@pytest.fixture
def cli(monkeypatch):
    from web import sesion
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "dueno@x.com", "email_verified": "true", "aud": "cid-web",
                                                         "name": "Don Dueño", "exp": "9999999999"})
    c = TestClient(app, base_url="https://testserver")
    c.post("/web/sesion", json={"credential": "x"})
    return c


def test_toda_pagina_del_anfitrion_lleva_la_barra_y_el_jugador_no(cli):
    for ruta in ("/anfitrion", "/anfitrion/mis-canchas", "/anfitrion/tienda", "/anfitrion/academia", "/anfitrion/campeonatos",
                 "/anfitrion/boleador", "/anfitrion/verificador", "/anfitrion/bodega", "/anfitrion/reportes", "/anfitrion/cobros-club"):
        h = cli.get(ruta, follow_redirects=False)
        assert h.status_code == 200, ruta
        assert "class='nav anf-cab'" in h.text and "class='pcg-anf'" in h.text, ruta
        assert "class='cl-banda" not in h.text, ruta   # nada de la cabecera del jugador
    perfil = cli.get("/perfil").text
    assert "anf-cab" not in perfil and "pcg-anf" not in perfil
