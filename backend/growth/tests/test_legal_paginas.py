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
    # Play exige que exista un camino DENTRO de la app, no sólo por correo.
    assert "perfil → eliminar mi cuenta" in html


def test_el_callback_de_meta_sigue_vivo():
    """La página de redes y su callback no se rompieron al agregar la de cuenta."""
    assert cli.get("/legal/eliminacion-datos").status_code == 200
    # Sin firma válida, el callback responde igual (no revienta).
    assert cli.post("/legal/eliminacion-datos").status_code in (200, 400)


def test_home_de_marca_en_la_raiz():
    """La raíz del dominio sirve la home de marketing: es la URL del comercio
    que revisan las pasarelas (Culqi) al afiliar, y debe tener razón social,
    RUC, contacto, términos, cancelaciones y Libro de Reclamaciones, además de
    enlaces a las páginas legales oficiales."""
    r = cli.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    for texto in ("GRUPO EBIM S.A.C.", "20602517986", "contacto@ebim.pe",
                  'id="terminos"', 'id="devoluciones"', 'id="reclamaciones"',
                  'href="/legal/terminos"', 'href="/legal/privacidad"',
                  'href="/legal/eliminar-cuenta"'):
        assert texto in r.text, texto


def test_libro_de_reclamaciones_integrado():
    """INDECOPI / Culqi: el Libro de Reclamaciones vive en el backend (no en un
    correo ni formulario externo): registra con número correlativo, la torre lo
    lista y lo marca atendido."""
    from db.store import stores
    hoja = {"c_nombre": "Ana Pérez", "c_doc": "12345678", "c_tel": "999",
            "c_email": "Ana@x.com", "b_tipo": "Servicio", "b_monto": "60",
            "b_desc": "Reserva 12/07", "d_tipo": "Reclamo",
            "d_detalle": "La cancha estaba ocupada.", "d_pedido": "Devolución."}
    r = cli.post("/reclamaciones", json=hoja).json()
    assert r["ok"] and r["numero"].startswith("PICH-")
    assert any(h["numero"] == r["numero"] and h["consumidor"]["email"] == "ana@x.com"
               for h in stores.reclamaciones)
    # Campos obligatorios: sin detalle no se registra.
    assert cli.post("/reclamaciones", json={**hoja, "d_detalle": ""}).json()["ok"] is False
    # La home muestra el formulario apuntando al backend y el catálogo con precios.
    home = cli.get("/").text
    assert "fetch('/reclamaciones'" in home and 'id="servicios"' in home
    assert home.count('class="prod"') >= 5 and "Desde S/" in home
    assert "play.google.com/store/apps/details?id=pe.ebim.pichangol" in home
    # Torre: listar y atender (exige token admin).
    import config
    assert cli.get("/admin/api/reclamaciones").status_code in (401, 503)
    tok = config.ADMIN_PANEL_TOKEN or "x"
    prev = config.ADMIN_PANEL_TOKEN
    config.ADMIN_PANEL_TOKEN = tok
    try:
        j = cli.get("/admin/api/reclamaciones", headers={"X-Admin-Token": tok}).json()
        mine = [h for h in j["reclamaciones"] if h["numero"] == r["numero"]][0]
        assert mine["estado"] == "pendiente"
        a = cli.post(f"/admin/api/reclamaciones/{mine['id']}/atender",
                     headers={"X-Admin-Token": tok},
                     json={"respuesta": "Se devolvió el monto."}).json()
        assert a["ok"]
        j2 = cli.get("/admin/api/reclamaciones", headers={"X-Admin-Token": tok}).json()
        assert [h for h in j2["reclamaciones"] if h["id"] == mine["id"]][0]["estado"] == "atendida"
    finally:
        config.ADMIN_PANEL_TOKEN = prev
    # Sobrevive al snapshot.
    from db.store import Stores
    s2 = Stores(); s2.load_state(stores.to_state())
    assert any(h["numero"] == r["numero"] for h in s2.reclamaciones)
