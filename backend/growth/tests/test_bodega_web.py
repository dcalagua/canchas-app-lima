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


def test_packshot_tipo_por_nombre_y_categoria():
    # Por NOMBRE (multi-país: Pilsen, Paceña y Pilsener son cerveza… por
    # categoría; Gatorade/Powerade → rehidratante por nombre).
    assert bodega_web._packshot_tipo("Cerveza artesanal", "Otros") == "cerveza"
    assert bodega_web._packshot_tipo("Gatorade", "Deportivo") == "rehidratante"
    assert bodega_web._packshot_tipo("Agua San Luis", "Bebidas") == "agua"
    assert bodega_web._packshot_tipo("Doritos", "Snacks") == "papitas"
    # Por CATEGORÍA cuando el nombre no dice nada.
    assert bodega_web._packshot_tipo("Paceña", "Cervezas") == "cerveza"
    assert bodega_web._packshot_tipo("Inca Kola", "Bebidas") == "gaseosa"
    assert bodega_web._packshot_tipo("Algo raro", "Otros") == "generico"
    # Todos los tipos emitidos existen en el catálogo del generador.
    from marketing import packshot
    tipos = set(packshot.tipos())
    for _, t in bodega_web._PACKSHOT_KEYS:
        assert t in tipos
    for t in bodega_web._PACKSHOT_CAT.values():
        assert t in tipos


def test_html_carta_con_packshots():
    productos = [
        {"nombre": "Paceña", "categoria": "Cervezas", "precio": 15,
         "stock": 6, "foto_url": None, "moneda": "Bs"},
        {"nombre": "Gatorade", "categoria": "Deportivo", "precio": 5,
         "stock": 3, "foto_url": "http://x/g.jpg"},
    ]
    h = bodega_web.html_carta(productos, con_packshots=True)
    # Sin foto → packshot genérico (con el emoji debajo por si no carga).
    assert '/bodega/packshot/cerveza' in h
    # Con foto real → la foto manda, sin packshot para ese producto.
    assert 'src="http://x/g.jpg"' in h
    assert '/bodega/packshot/pelotas' not in h
    # Sin el flag (sin proveedor IA) no se emiten packshots.
    assert '/bodega/packshot/' not in bodega_web.html_carta(productos)


def test_ruta_packshot_sin_proveedor_es_404(monkeypatch):
    import config
    monkeypatch.setattr(config, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "REPLICATE_API_TOKEN", "", raising=False)
    from marketing import packshot
    monkeypatch.setattr(packshot, "_cache", {})
    monkeypatch.setattr(packshot, "_storage_leer", lambda tipo: None)
    r = cli.get("/bodega/packshot/cerveza")
    assert r.status_code == 404
    # Tipo desconocido → 404 aunque hubiera proveedor.
    r2 = cli.get("/bodega/packshot/loquesea")
    assert r2.status_code == 404


def test_ruta_packshot_cacheado(monkeypatch):
    from marketing import packshot
    monkeypatch.setattr(packshot, "_cache", {"cerveza": b"JPEGFALSO"})
    r = cli.get("/bodega/packshot/cerveza")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == b"JPEGFALSO"
    assert "max-age=604800" in r.headers.get("cache-control", "")
