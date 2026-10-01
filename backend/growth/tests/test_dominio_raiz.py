"""pichangol.app (sin www) debe llevar a www.pichangol.app (pedido del
director, 1-oct-2026), salvo /.well-known/ (App Links de Android)."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402

cli = TestClient(main.app)


def test_raiz_redirige_a_www_con_ruta_y_query():
    r = cli.get("/reservar/u1?fecha=2026-10-02", headers={"host": "pichangol.app"}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "https://www.pichangol.app/reservar/u1?fecha=2026-10-02"
    r = cli.post("/web/sesion", headers={"host": "PICHANGOL.APP:443"}, json={}, follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "https://www.pichangol.app/web/sesion"


def test_well_known_y_otros_hosts_no_se_redirigen():
    r = cli.get("/.well-known/assetlinks.json", headers={"host": "pichangol.app"}, follow_redirects=False)
    assert r.status_code != 301 and r.status_code != 308
    r = cli.get("/legal/terminos", headers={"host": "www.pichangol.app"}, follow_redirects=False)
    assert r.status_code == 200
