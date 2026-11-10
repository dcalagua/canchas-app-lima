"""Noche WEB · W3: rendimiento y seguridad de la web pública
(`web/seguridad_web.py`): CSS/JS versionados con caché larga, gzip,
anti-iframe, CSP en modo reporte, CSRF por origen, límites por IP y tokens
de diseño sin variables indefinidas."""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web import seguridad_web, sesion, ui  # noqa: E402
from tests.test_web_reservas import client, db  # noqa: E402,F401


def test_css_y_js_versionados_con_cache_larga_y_gzip(db):
    r = client.get("/")
    html = r.text
    css = re.search(r"/web/a/estilo\.[0-9a-f]{12}\.css", html).group(0)
    nav = re.search(r"/web/a/nav\.[0-9a-f]{12}\.js", html).group(0)
    # El CSS del sistema de diseño ya NO viaja dentro de cada página.
    assert ui.CSS[:200] not in html
    a = client.get(css)
    assert a.status_code == 200 and "immutable" in a.headers["cache-control"] and a.text == ui.CSS
    assert client.get(nav).text == ui.JS_NAV
    # Una huella vieja (página en caché) recibe el contenido actual, sin caché larga.
    assert client.get("/web/a/estilo.000000000000.css").headers["cache-control"] == "no-cache"
    assert client.get("/web/a/otra.css").status_code == 404
    # Comprimido y sin no-store (el botón atrás puede usar su copia).
    z = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert z.headers.get("content-encoding") == "gzip"
    assert "no-store" not in r.headers["cache-control"]


def test_cabeceras_anti_iframe_y_csp_en_modo_bloqueo_por_defecto(db, monkeypatch):
    monkeypatch.delenv("WEB_CSP_MODO", raising=False)
    h = client.get("/reservar/c_lima").headers
    assert h["x-frame-options"] == "SAMEORIGIN"
    # Por defecto la CSP BLOQUEA (y sigue reportando).
    assert "content-security-policy-report-only" not in h
    csp = h["content-security-policy"]
    assert "frame-ancestors 'self'" in csp and "checkout.culqi.com" in csp and "report-uri /web/csp-reporte" in csp
    # Lo que la política cierra aunque siga con 'unsafe-inline'.
    for d in ("object-src 'none'", "base-uri 'self'", "default-src 'self'"):
        assert d in csp, d
    assert " * " not in f" {csp} " and "'unsafe-eval'" not in csp
    # Nada de comodines por directiva de scripts/marcos: dominios concretos.
    script = next(p for p in csp.split(";") if p.strip().startswith("script-src"))
    assert "https:" not in script.split() and "*" not in script.replace("*.culqi.com", "")
    assert client.post("/web/csp-reporte", content=b'{"csp-report":{}}').status_code == 204
    # Los JSON no llevan CSP (solo el HTML) y la torre conserva su DENY.
    assert "content-security-policy" not in client.get("/web/disponibilidad/c_lima").headers
    assert client.get("/admin").headers["x-frame-options"] == "DENY"


def test_csp_en_modo_reporte_como_corte_de_emergencia(db, monkeypatch, capsys):
    monkeypatch.setenv("WEB_CSP_MODO", "reporte")
    h = client.get("/reservar/c_lima").headers
    assert "content-security-policy" not in h
    assert h["content-security-policy-report-only"] == seguridad_web.CSP
    # El endpoint de reportes funciona igual y anota el modo en el log.
    assert client.post("/web/csp-reporte", content=b'{"csp-report":{"blocked-uri":"https://malo.example/x.js"}}').status_code == 204
    assert "[csp] (reporte)" in capsys.readouterr().out
    # Un valor desconocido no apaga la protección: vuelve a bloqueo.
    monkeypatch.setenv("WEB_CSP_MODO", "nada")
    assert "content-security-policy" in client.get("/reservar/c_lima").headers


def test_favicon_ico_ya_no_es_404(db):
    r = client.get("/favicon.ico", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/marca/logo.png"


def test_pagina_inexistente_responde_404_no_soft_404(db):
    r = client.get("/reservar/no-existe-123")
    assert r.status_code == 404 and "Cancha no disponible" in r.text


def test_csrf_escritura_con_cookie_desde_otro_sitio_se_rechaza(db, monkeypatch):
    import config
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    client.cookies.set(sesion.COOKIE, sesion.emitir({"email": "ana@x.com"}))
    try:
        r = client.post("/web/liberar", json={"ids": [], "firma": ""}, headers={"Origin": "https://malo.example"})
        assert r.status_code == 403 and r.json()["error"] == "origen_no_permitido"
        r = client.post("/web/liberar", json={"ids": [], "firma": ""}, headers={"Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403
        # Mismo sitio: pasa al endpoint.
        r = client.post("/web/liberar", json={"ids": [], "firma": ""}, headers={"Origin": "http://testserver"})
        assert r.status_code == 200
    finally:
        client.cookies.clear()
    # Sin cookie de sesión (webhooks, callbacks de pasarela) nunca se bloquea por origen.
    r = client.post("/web/liberar", json={"ids": [], "firma": ""}, headers={"Origin": "https://pasarela.example"})
    assert r.status_code == 200


def test_limite_por_ip_real_en_endpoints_caros(db, monkeypatch):
    monkeypatch.setattr(seguridad_web, "ACTIVO", True)
    monkeypatch.setitem(seguridad_web.LIMITES, "/web/lugares", (3, 60))
    seguridad_web._golpes.clear()
    ok = [client.get("/web/lugares?q=x&lat=0&lng=0", headers={"X-Forwarded-For": "6.6.6.6, 1.1.1.1"}).status_code for _ in range(3)]
    assert 429 not in ok
    r = client.get("/web/lugares?q=y&lat=0&lng=0", headers={"X-Forwarded-For": "7.7.7.7, 1.1.1.1"})
    # El primer valor de X-Forwarded-For lo pone el cliente: cambiarlo no evade el límite.
    assert r.status_code == 429 and r.json()["error"] == "demasiadas_solicitudes"
    assert client.get("/web/lugares?q=z&lat=0&lng=0", headers={"X-Forwarded-For": "2.2.2.2"}).status_code != 429


def test_tokens_css_definidos_y_cta_con_contraste_aa():
    usados = set(re.findall(r"var\(--([a-z0-9-]+)", ui.CSS))
    definidos = set(re.findall(r"--([a-z0-9-]+):", ui.TOKENS))
    assert not (usados - definidos - {"mj-vh", "mj-top", "cab-h"}), usados - definidos

    def lum(hexa):
        c = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    cta = re.search(r"--esmeralda:#([0-9A-Fa-f]{6})", ui.TOKENS).group(1)
    assert (1.05) / (lum(cta) + 0.05) >= 4.5   # texto blanco sobre el botón principal


def test_portada_liviana(db):
    assert len(client.get("/").content) < 150_000
