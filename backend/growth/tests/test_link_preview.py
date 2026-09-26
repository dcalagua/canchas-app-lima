"""Previsualización de enlaces (Open Graph) para posts de canales. Prueba el
parser con HTML estático (sin red)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from marketing import link_preview as lp  # noqa: E402


def test_meta_og_ambos_ordenes():
    html = (
        '<meta property="og:title" content="Hola mundo">'
        '<meta content="Una descripción" name="description">'
    )
    assert lp._meta(html, "og:title") == "Hola mundo"
    assert lp._meta(html, "description") == "Una descripción"


def test_meta_desescapa_entidades():
    html = '<meta property="og:title" content="Caf&eacute; &amp; t&eacute;">'
    assert lp._meta(html, "og:title") == "Café & té"


def test_titulo_tag_fallback():
    assert lp._titulo_tag("<title>  Mi página  </title>") == "Mi página"


def test_dominio_sin_www():
    assert lp._dominio("https://www.rpp.pe/nota/123") == "rpp.pe"
    assert lp._dominio("https://acortar.link/abc") == "acortar.link"


def test_obtener_url_vacia_es_failsafe():
    assert lp.obtener("")["ok"] is False


def test_obtener_parsea_con_stub(monkeypatch):
    # Sin red: se stubbea la descarga para que el test sea determinista.
    html = (
        '<meta property="og:title" content="Noticia X">'
        '<meta property="og:description" content="La bajada">'
        '<meta property="og:image" content="/img/foto.jpg">'
    )
    monkeypatch.setattr(
        lp, "_bajar", lambda url: (html, "https://www.rpp.pe/nota/1"))
    lp._CACHE.clear()
    r = lp.obtener("https://rpp.pe/x")
    assert r["ok"] is True
    assert r["title"] == "Noticia X"
    assert r["description"] == "La bajada"
    assert r["image"] == "https://www.rpp.pe/img/foto.jpg"  # urljoin resolvió
    assert r["domain"] == "rpp.pe"


def test_obtener_cachea(monkeypatch):
    llamadas = {"n": 0}

    def _fake(url):
        llamadas["n"] += 1
        return '<meta property="og:title" content="T">', url

    monkeypatch.setattr(lp, "_bajar", _fake)
    lp._CACHE.clear()
    lp.obtener("https://ejemplo.pe/a")
    lp.obtener("https://ejemplo.pe/a")
    assert llamadas["n"] == 1  # la 2da vino de caché
