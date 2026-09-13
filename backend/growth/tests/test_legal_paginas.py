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


def test_datos_de_la_empresa_configurables_desde_la_torre():
    """Pedido del director (sep-2026): razón social, RUC, dirección, WhatsApp,
    correo y horario se cambian desde la torre (`/admin/api/empresa`) y salen
    al instante en la portada, el pie de TODA la web, las páginas legales y el
    Libro de Reclamaciones — sin publicar código y por ambiente (snapshot)."""
    import config
    import empresa
    from db.store import CONFIG_DEFAULT, Stores, stores

    prev_tok, prev_cfg = config.ADMIN_PANEL_TOKEN, dict(stores.config)
    tok = prev_tok or "x"
    config.ADMIN_PANEL_TOKEN = tok
    h = {"X-Admin-Token": tok}
    try:
        # Sin token, nada.
        assert cli.get("/admin/api/empresa").status_code == 401
        assert cli.post("/admin/api/empresa", json={"datos": {}}).status_code == 401
        j = cli.get("/admin/api/empresa", headers=h).json()
        assert j["datos"]["empresa_ruc"] == CONFIG_DEFAULT["empresa_ruc"]
        assert {c["clave"] for c in j["campos"]} == set(empresa.CAMPOS)

        nuevos = {"empresa_razon_social": "PICHANGOL LATAM S.A.C.", "empresa_ruc": "20999999991",
                  "empresa_direccion": "Av. Javier Prado 123, Of. 4, Surco, Lima, Perú",
                  "empresa_ciudad": "Surco, Lima, Perú", "contacto_whatsapp_pe": "+51 911 222 333",
                  "contacto_whatsapp_ec": "0991234567", "contacto_whatsapp_bo": "",
                  "empresa_correo": "Hola@Pichangol.app", "empresa_correo_privacidad": "",
                  "empresa_horario": "Lun a Dom, 8:00 a 22:00", "empresa_doc_etiqueta": "RUC"}
        r = cli.post("/admin/api/empresa", headers=h, json={"datos": nuevos})
        assert r.status_code == 200 and r.json()["ok"], r.text
        d = r.json()["datos"]
        assert d["contacto_whatsapp_pe"] == "911222333"      # se normaliza: solo el local, sin +51
        assert d["contacto_whatsapp_ec"] == "0991234567"
        assert d["empresa_correo"] == "hola@pichangol.app"   # minúsculas
        assert r.json()["vista"]["whatsapp_bonito"] == "+51 911 222 333 (Perú) · +593 0991 234 567 (Ecuador)"
        assert [w["iso"] for w in r.json()["vista"]["whatsapps"]] == ["pe", "ec"]  # Bolivia sin número no sale
        # Una sola fuente con el APK: el endpoint del app lee las mismas claves.
        from propiedad import reclamos
        assert reclamos.contacto_whatsapp("pe") == "51911222333" and reclamos.contacto_whatsapp("ec") == "5930991234567"
        assert r.json()["vista"]["correo_privacidad"] == "hola@pichangol.app"  # vacío → el de contacto

        # Portada (Contacto + Términos + pie) y una página interior (pie).
        home = cli.get("/").text
        for t in ("PICHANGOL LATAM S.A.C.", "20999999991", "Av. Javier Prado 123", "https://wa.me/51911222333",
                  "+51 911 222 333", "https://wa.me/5930991234567", "WhatsApp Ecuador", "WhatsApp Perú",
                  "hola@pichangol.app", "Lun a Dom, 8:00 a 22:00", "Surco, Lima, Perú"):
            assert t in home, t
        for viejo in ("GRUPO EBIM", "20602517986", "contacto@ebim.pe", "967923419", "Basadre"):
            assert viejo not in home, viejo
        assert "PICHANGOL LATAM S.A.C." in cli.get("/canchas").text  # pie de todas las páginas
        # Páginas legales (Play) y Libro de Reclamaciones.
        for ruta in ("/legal/privacidad", "/legal/terminos", "/legal/eliminar-cuenta"):
            html = cli.get(ruta).text
            assert "PICHANGOL LATAM S.A.C." in html and "20999999991" in html and "hola@pichangol.app" in html, ruta
            assert "EBIM" not in html, ruta
        hoja = cli.post("/reclamaciones", json={"c_nombre": "Ana", "c_doc": "1", "c_tel": "9", "c_email": "a@x.com",
                                                "b_tipo": "Servicio", "d_tipo": "Reclamo", "d_detalle": "x", "d_pedido": "y"}).json()
        assert hoja["contacto"] == "hola@pichangol.app"

        # Validaciones: correo inválido, WhatsApp corto, razón social vacía → 400 con motivo.
        for malo, motivo in (({"empresa_correo": "no-es-correo"}, "correo inválido"),
                             ({"contacto_whatsapp_pe": "123"}, "WhatsApp Perú"),
                             ({"empresa_razon_social": "  "}, "obligatorio")):
            r = cli.post("/admin/api/empresa", headers=h, json={"datos": malo})
            assert r.status_code == 400 and motivo in r.json()["detail"], (malo, r.text)
        assert stores.config["empresa_correo"] == "hola@pichangol.app"  # lo inválido no pisó nada

        # El HTML que escribe el operador se escapa (no se inyecta en la web).
        cli.post("/admin/api/empresa", headers=h, json={"datos": {"empresa_horario": "<script>x</script>"}})
        assert "<script>x</script>" not in cli.get("/").text and "&lt;script&gt;x" in cli.get("/").text

        # Sobrevive al snapshot (así viaja a Postgres y vuelve tras un reinicio).
        s2 = Stores(); s2.load_state(stores.to_state())
        assert s2.config["empresa_razon_social"] == "PICHANGOL LATAM S.A.C."
        # Migración única: un snapshot VIEJO con Perú vacío recibe el número que ya
        # estaba publicado en la web; uno ya migrado y vaciado a propósito se respeta.
        viejo = Stores(); viejo.load_state({"config": {"contacto_whatsapp_pe": ""}})
        assert viejo.config["contacto_whatsapp_pe"] == CONFIG_DEFAULT["contacto_whatsapp_pe"] == "967923419"
        vaciado = Stores(); vaciado.load_state({"config": {"contacto_whatsapp_pe": "", "empresa_wa_migrado": "1"}})
        assert vaciado.config["contacto_whatsapp_pe"] == ""
    finally:
        config.ADMIN_PANEL_TOKEN = prev_tok
        stores.config.clear(); stores.config.update(prev_cfg)
