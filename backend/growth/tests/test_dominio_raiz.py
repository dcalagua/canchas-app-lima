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


def test_dominio_viejo_salta_al_nuevo_solo_en_get(monkeypatch):
    """Cambio de marca (21-oct-2026): con DOMINIOS_VIEJOS activo, pichangol.app
    y www.pichangol.app llevan a la MISMA ruta de la marca nueva en un salto;
    los POST (webhooks, callbacks de pasarela) se atienden ahí mismo; el
    /.well-known/ sigue sirviendo los App Links del dominio viejo; y el apex
    nuevo va a www."""
    import config
    monkeypatch.setattr(config, "DOMINIOS_VIEJOS", {"pichangol.app", "www.pichangol.app"})
    monkeypatch.setattr(config, "MARCA_URL", "https://www.canchalibre.pe")
    monkeypatch.setattr(config, "MARCA_DOMINIO", "www.canchalibre.pe")
    for host in ("pichangol.app", "www.pichangol.app"):
        r = cli.get("/reservar/u1?fecha=2026-10-02", headers={"host": host}, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "https://www.canchalibre.pe/reservar/u1?fecha=2026-10-02", host
    r = cli.post("/web/sesion", headers={"host": "www.pichangol.app"}, json={}, follow_redirects=False)
    assert r.status_code not in (301, 308)
    r = cli.get("/.well-known/assetlinks.json", headers={"host": "www.pichangol.app"}, follow_redirects=False)
    assert r.status_code not in (301, 308)
    r = cli.get("/canchas", headers={"host": "canchalibre.pe"}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "https://www.canchalibre.pe/canchas"
    assert cli.get("/legal/terminos", headers={"host": "www.canchalibre.pe"}, follow_redirects=False).status_code == 200
