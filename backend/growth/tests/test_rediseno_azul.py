"""REDISEÑO AZUL de la web (PDF "Soluciones EBIM", nov-2026).

Fija lo que el rediseño decidió para que un cambio futuro no lo deshaga sin
querer: paleta y contraste, cabecera en tres franjas, logo de CanchaLibre (con
respaldo para otra marca), textos multi-país de la portada, precio de Pro
desde la torre y el Libro de Reclamaciones con pastillas.
"""

import os
import re
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402
from web import iconos, marca, ui  # noqa: E402

cli = TestClient(main.app)


def _lum(hexa: str) -> float:
    c = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contraste(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_paleta_del_disenador_y_contraste_aa():
    tok = {k: v for k, v in re.findall(r"--([a-z-]+):#([0-9A-Fa-f]{6})", ui.TOKENS)}
    assert tok["azul"].upper() == "3056ED" and tok["azul-claro"].upper() == "7E98FF"
    assert tok["azul-tinte"].upper() == "E3E8FF" and tok["carbon"] == "333333"
    # los nombres históricos apuntan a la paleta nueva (CTA, texto, fondo suave)
    assert tok["esmeralda"].upper() == "3056ED" and tok["noche"] == "333333" and tok["tinte"].upper() == "E3E8FF"
    assert _contraste("FFFFFF", tok["azul"]) >= 4.5          # texto blanco en botones, barra y pie
    assert _contraste("FFFFFF", tok["azul-osc"]) >= 4.5
    assert _contraste(tok["azul"], tok["azul-tinte"]) >= 4.5  # texto azul en la franja celeste
    assert _contraste("FFFFFF", tok["azul-claro"]) < 3        # por eso #7E98FF es SOLO decoración
    assert _contraste(tok["tenue"], "FFFFFF") >= 4.5
    # el CSS del rediseño va al final y gana en la cascada
    from web import estilos_rediseno
    assert ui.CSS.endswith(estilos_rediseno.CSS)


def test_cabecera_en_tres_franjas_en_la_portada():
    html = cli.get("/").text
    assert "<header class='nav abnb cl'>" in html and "class='cl-barra'" in html
    assert "class='cab-links'" in html and ">Cómo funciona<" in html and ">Centro de ayuda<" in html
    assert "class='cl-fila-tabs'" in html and "cab-tabs cl-pills" in html
    assert "class='cl-banda grande'" in html and "class='barra-filtros'" in html
    # las amenidades y "Filtros" viven en la franja (antes del contenido)
    assert html.index("id='btnFiltros'") < html.index("id='expl'")
    # pastillas con ícono de línea, no emoji
    assert "<span class='ico'><svg class='ic-l'" in html
    # sin sesión: pastilla "Iniciar sesión o registrarse"
    assert "class='entrar-pill'" in html and "Iniciar sesión o registrarse" in html


def test_paginas_interiores_llevan_el_buscador_chico_en_la_franja():
    html = cli.get("/libro-de-reclamaciones").text
    assert "class='cl-banda'" in html and "class='busq-mini'" in html
    assert "class='cl-fila-tabs'" not in html


def test_modo_anfitrion_sin_franja_y_con_pestanas_en_la_barra():
    html = ui.cabecera(tabs="<a class='cat sel' href='/anfitrion'>Hoy</a>", modo="anfitrion")
    assert "cl-anf" in html and "class='cl-banda" not in html and "class='cab-links'" not in html
    assert "class='cab-tabs'" in html


def test_logo_canchalibre_y_respaldo_con_otra_marca(monkeypatch):
    import marca_logo
    # La suite corre con la marca vieja (conftest): logo de la torre + nombre, como antes.
    assert "wm-cl" not in ui.wordmark()
    assert "/marca/logo.png" in ui.wordmark() or "/marca/logo" in ui.wordmark()
    monkeypatch.setattr(ui, "MARCA", "CanchaLibre")
    monkeypatch.setattr(marca_logo, "personalizado", lambda: False)
    w = ui.wordmark()
    assert "wm-cl blanco" in w and "/static/brand/cl_icono_blanco.png" in w and "/static/brand/cl_wordmark_blanco.png" in w
    assert "cl_wordmark_azul.png" in ui.wordmark(color="azul")
    assert "cl_apilado_blanco.png" in ui.logo_apilado()
    # un logo subido en la torre SIEMPRE manda
    monkeypatch.setattr(marca_logo, "personalizado", lambda: True)
    assert "wm-cl" not in ui.wordmark()
    # los archivos existen
    base = os.path.join(os.path.dirname(__file__), "..", "static", "brand")
    for f in ("cl_icono_blanco", "cl_icono_azul", "cl_wordmark_blanco", "cl_wordmark_azul", "cl_apilado_blanco",
              "cl_ilustracion_login", "logo_canchalibre", "logo_canchalibre_og"):
        assert os.path.getsize(os.path.join(base, f + ".png")) > 1000, f


def test_logo_por_defecto_es_el_de_canchalibre():
    import marca_logo
    assert marca_logo.LOGO_DEFECTO.endswith("logo_canchalibre.png")
    assert marca_logo.LOGO_OG_DEFECTO.endswith("logo_canchalibre_og.png")


def test_portada_multipais_y_precio_pro_de_la_torre():
    from db.store import stores
    _css, html, _js = marca.secciones()
    assert "signo S/" not in html and "moneda de tu país" in html
    assert "precios se muestran en Soles (S/)" not in html and "dólares $ en Ecuador" in html
    assert "{{PRO_PRECIO}}" not in html
    viejo = stores.config.get("pro_precio_soles")
    try:
        stores.config["pro_precio_soles"] = "15"
        assert "S/ 15 <small>al mes</small>" in marca.secciones()[1]
        stores.config["pro_precio_soles"] = "12.5"
        assert "S/ 12.50 <small>al mes</small>" in marca.secciones()[1]
    finally:
        if viejo is None:
            stores.config.pop("pro_precio_soles", None)
        else:
            stores.config["pro_precio_soles"] = viejo
    # secciones con las franjas del diseño y los 6 servicios (Culqi pide ≥ 5)
    for c in ('id="servicio" class="banda-azul"', 'id="como" class="banda-azul"', 'class="banda-gris"',
              'class="oscura legal-bloque"', 'class="card tienes-cancha"', 'class="legal-grid"'):
        assert c in html, c
    assert html.count('class="prod"') == 6


def test_libro_con_pastillas_y_datos_del_proveedor():
    t = cli.get("/libro-de-reclamaciones").text
    assert "class='prov-caja'" in t and "name='b_tipo' value='Servicio' checked" in t
    assert "<select id='b_tipo'" not in t
    assert t.count("class='radio-row pastillas'") == 2
    assert "Queja:</b> malestar" in t  # la definición legal de reclamo y queja sigue a la vista
    hoja = cli.post("/reclamaciones", json={"c_nombre": "Ana", "c_doc": "12345678", "c_tel": "999", "c_email": "a@x.com",
                                              "b_tipo": "Producto", "d_tipo": "Queja", "d_detalle": "x", "d_pedido": "y"}).json()
    assert hoja["ok"]


def test_iconos_de_linea():
    for k in ("todas", "futbol", "tenis", "padel", "pickleball", "voley", "basquet", "academias", "pin", "calendario",
              "reloj", "filtros", "chat", "bodega", "libro", "cafeteria", "parking"):
        s = iconos.svg(k)
        assert s.startswith("<svg") and "currentColor" in s and "aria-hidden='true'" in s, k
    assert iconos.svg("no-existe") == ""
