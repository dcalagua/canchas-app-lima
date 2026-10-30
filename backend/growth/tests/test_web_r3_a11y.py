"""Ronda 3 · accesibilidad y SEO por ambiente: noindex fuera de producción,
og:image/canonical absolutos, h1 del chat, nombres/etiquetas accesibles y
objetivos táctiles + textos de al menos 12px."""

import os
import re
import sys
from urllib.parse import quote, unquote

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from tests.conftest import con_assets  # noqa: E402
from tests.test_web_reservas import client, db  # noqa: E402,F401
from tests.test_web_mensajes import _cli, fk, M, YO  # noqa: E402,F401

NOINDEX = "<meta name='robots' content='noindex,nofollow'>"


def test_produccion_y_sin_entorno_se_indexan(db, monkeypatch):
    for ent in ("", "PRD", "prod"):
        monkeypatch.setattr(config, "PICHANGOL_ENTORNO", ent.upper())
        assert config.sitio_indexable()
        r = client.get("/ayuda")
        assert r.status_code == 200 and "noindex" not in r.text and "x-robots-tag" not in r.headers
        robots = client.get("/robots.txt").text
        assert "Sitemap:" in robots and "Disallow: /web/" in robots and "Disallow: /\n" not in robots


def test_qas_y_dev_no_se_indexan(db, monkeypatch):
    for ent in ("QAS", "DEV"):
        monkeypatch.setattr(config, "PICHANGOL_ENTORNO", ent)
        assert not config.sitio_indexable()
        # Páginas de ui.shell: meta + cabecera.
        for ruta in ("/ayuda", "/canchas", "/reservar/c_lima", "/esto-no-existe"):
            r = client.get(ruta, headers={"accept": "text/html"})
            assert r.headers["x-robots-tag"] == "noindex, nofollow", ruta
            assert r.text.count("name='robots'") == 1, ruta
        # Páginas que NO pasan por ui.shell también llevan el meta (inyectado).
        legal = client.get("/legal/terminos", headers={"accept-encoding": "identity"})
        assert legal.headers["x-robots-tag"] == "noindex, nofollow"
        assert re.search(r"<meta name='robots' content='noindex,nofollow'>", legal.text)
        assert int(legal.headers["content-length"]) == len(legal.content)
        # Lo que no es HTML lleva la cabecera, sin tocar el cuerpo.
        js = client.get("/manifest.webmanifest")
        assert js.headers["x-robots-tag"] == "noindex, nofollow" and js.json()["icons"]
        robots = client.get("/robots.txt").text
        assert robots == "User-agent: *\nDisallow: /\n" and "Sitemap" not in robots


def test_inyeccion_del_meta_en_html_sin_head():
    from main import _SeoAmbiente as S
    assert S.con_meta(b"<!doctype html><meta charset=utf-8><p>hola") == \
        b"<!doctype html><meta charset=utf-8>" + NOINDEX.encode() + b"<p>hola"
    assert S.con_meta(b"<html><head><title>x</title>").startswith(b"<html><head>" + NOINDEX.encode())
    ya = b"<head><meta name=\"robots\" content=\"noindex\"></head>"
    assert S.con_meta(ya) == ya and S.con_meta(b"") == b""


def test_og_image_y_canonical_absolutos(db, monkeypatch):
    from web import ui
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://pg.ebim.pe ")
    html = client.get("/ayuda").text
    assert "<meta property='og:image' content='https://pg.ebim.pe/marca/logo-og.png'>" in html
    assert "<link rel='canonical' href='https://pg.ebim.pe/ayuda'>" in html
    assert "<meta property='og:url' content='https://pg.ebim.pe/ayuda'>" in html
    # Sin PUBLIC_BASE_URL: la base de la request.
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    html = client.get("/tenis").text
    assert "content='http://testserver/marca/logo-og.png'" in html and "href='http://testserver/tenis'" in html
    # Detrás del proxy de Railway manda X-Forwarded-Proto/Host.
    html = client.get("/ayuda", headers={"x-forwarded-proto": "https", "x-forwarded-host": "www.canchalibre.pe"}).text
    assert "content='https://www.canchalibre.pe/marca/logo-og.png'" in html
    # Fuera de una request, el dominio de la marca; lo absoluto no se toca.
    assert ui.url_absoluta("/x.png") == config.MARCA_URL + "/x.png"
    assert ui.url_absoluta("https://f/foto.jpg") == "https://f/foto.jpg"
    assert ui.url_absoluta("data:image/png;base64,AA") == "data:image/png;base64,AA"


def test_el_chat_tiene_h1_con_el_contacto(monkeypatch, fk):
    hc = M.hilo_cancha("dueno@x.com", YO)
    fk.add(hc, YO, "¿Tienen turno?", 0)
    cli = _cli(monkeypatch)
    html = cli.get(f"/mensajes/{quote(M.clave_de([hc]), safe='')}").text
    assert re.search(r"<h1 class='sr-only'>Chat con [^<]+</h1>", html)
    assert "aria-label='Volver a Mensajes'" in html and "aria-label='Mensaje'" in html
    refs = [p["ref"] for p in cli.get("/web/mensajes/buscar", params={"q": "s"}).json()["jugadores"]]
    r = cli.post("/web/mensajes/grupos", json={"nombre": "Pichanga jueves", "miembros": refs}).json()
    html = cli.get(r["url"]).text
    assert "<h1 class='sr-only'>Chat del grupo Pichanga jueves</h1>" in html
    assert unquote(r["url"]).startswith("/mensajes/")


def test_campos_con_etiqueta_accesible(db):
    from web import anfitrion_campeonatos as ac, router
    assert "aria-label='Código del campeonato o del equipo'" in ac._caja_codigo(False)
    html = client.get("/canchas").text
    assert "id='rMin' aria-label='Precio mínimo'" in html and "id='rMax' aria-label='Precio máximo'" in html
    assert router  # el explorador se arma en web/router.py


def test_textos_de_12px_y_objetivos_tactiles(db):
    css = con_assets(client, client.get("/ayuda").text)
    assert "small{font-size:max(12px,.83em)}" in css
    bloque = css.split("@media (pointer:coarse){", 1)[1].split("\n}", 1)[0]
    for sel in (".chip", ".btn", "select", ".mj-chip", ".lst .corazon", ".pie-cols a", ".wm"):
        assert sel in bloque, sel
    assert "min-height:44px" in bloque
    # Ningún tamaño de letra por debajo de 12px en el CSS de la web pública.
    import glob
    base = os.path.join(os.path.dirname(__file__), "..")
    for f in glob.glob(os.path.join(base, "web", "*.py")):
        if f.endswith(("anfitrion.py", "anfitrion_negocio.py")):   # los refactoriza otra rama
            continue
        chicos = re.findall(r"font-size:\s?(?:[0-9]|1[01])(?:\.\d+)?px", open(f, encoding="utf-8").read())
        assert not chicos, (os.path.basename(f), chicos[:3])
    # Las reglas anti scroll horizontal siguen.
    assert "html{-webkit-text-size-adjust:100%;overflow-x:hidden}body{overflow-x:clip" in css
