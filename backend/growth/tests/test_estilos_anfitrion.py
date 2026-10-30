"""Las páginas del modo anfitrión no repiten estilos en línea (Reservas pesaba
~480 KB con más de 3 000 `style=`): las reglas viven en
`web/estilos_anfitrion.py` y viajan en el CSS versionado del sitio."""
from datetime import date

from web import estilos_anfitrion, ui
from web.anfitrion import _tarjeta_res


def test_tarjeta_de_reserva_sin_estilos_en_linea():
    r = {"id": "r1", "cancha_id": "c1", "jugador": "Ana Torres", "usuario": "ana@demo.pe", "telefono": "987654321",
         "fecha": "2026-10-30", "hora_inicio": "08:00", "hora_fin": "09:00", "precio": 60, "pagado": False,
         "medio_pago": "efectivo", "moneda": "S/"}
    html = _tarjeta_res(r, {"id": "c1", "nombre": "Tenis 1", "moneda": "PEN", "lat": -12.1, "lng": -77.0}, date(2026, 10, 30))
    assert "style=" not in html
    assert "anf-res-cab" in html and "aria-label='WhatsApp a Ana Torres'" in html


def test_estilos_del_anfitrion_van_en_el_css_del_sitio():
    assert ui.CSS.endswith(estilos_anfitrion.CSS)
    css = estilos_anfitrion.CSS
    # clases genéricas de la hoja de "Tu negocio" acotadas a sus páginas
    assert ":where(.anf-ng) .kpis{" in css and "\n.kpis{" not in css
    # mapa de calor por clase, con la misma escala de antes
    for i, c in enumerate(estilos_anfitrion.RAMPA[1:], start=1):
        assert f".hm-c.n{i},.hm-ley i.n{i}{{background:{c}}}" in css
    # táctil: 44 px solo en pantallas de puntero grueso
    assert "@media (pointer:coarse){" in css and ".anf-pag" in css
    # sin texto bajo 12 px
    import re
    assert not [m for m in re.findall(r"font-size:(\d+(?:\.\d+)?)px", css) if float(m) < 12]
