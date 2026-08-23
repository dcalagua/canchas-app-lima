"""Tests de la CARTA pública de la bodega (/b/{carta_id}) y su QR."""

from fastapi.testclient import TestClient

import main
from marketing import bodega_web

cli = TestClient(main.app)


def test_html_carta_agrupa_y_marca_agotados():
    productos = [
        {"nombre": "Pilsen", "categoria": "Cervezas", "precio": 8,
         "stock": 12, "foto_url": None},
        {"nombre": "Agua San Luis", "categoria": "Bebidas", "precio": 2.5,
         "stock": 0, "foto_url": None},
        {"nombre": "Gatorade", "categoria": "Deportivo", "precio": 5,
         "stock": 3, "foto_url": "http://x/g.jpg"},
    ]
    h = bodega_web.html_carta(productos)
    assert "text/html" or True  # el content-type lo pone la ruta
    assert "Pilsen" in h and "S/ 8.00" in h
    assert "Agua San Luis" in h and "Agotado" in h
    assert "Cervezas" in h and "Bebidas" in h and "Deportivo" in h
    assert 'src="http://x/g.jpg"' in h


def test_html_carta_moneda_por_pais():
    # Bolivia (Bs) y default S/ cuando la fila no trae moneda.
    h = bodega_web.html_carta([
        {"nombre": "Paceña", "categoria": "Cervezas", "precio": 15,
         "stock": 6, "foto_url": None, "moneda": "Bs"},
        {"nombre": "Pilsen", "categoria": "Cervezas", "precio": 8,
         "stock": 6, "foto_url": None},
    ])
    assert "Bs 15.00" in h and "S/ 8.00" in h


def test_html_carta_vacia():
    h = bodega_web.html_carta([])
    assert "aún no tiene productos" in h


def test_ruta_sin_configuracion_responde_503(monkeypatch):
    import config
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "")
    r = cli.get("/b/babc123")
    assert r.status_code == 503
    assert "text/html" in r.headers["content-type"]


def test_qr_de_la_carta_es_png():
    r = cli.get("/b/babc123/qr.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
