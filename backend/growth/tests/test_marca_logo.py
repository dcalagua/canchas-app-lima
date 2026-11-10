"""Logo de la marca configurable desde la torre (pedido del director,
20-oct-2026: "¿y si quiero cambiar de logo? quiero que sea configurable")."""
from __future__ import annotations

import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import config
import marca_logo
from db.store import stores
from main import app
from web import almacen

cli = TestClient(app)
ADM = {"X-Admin-Token": "adm"}
_CLAVES = ("marca_logo_url", "marca_logo_b64", "marca_logo_v")


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(almacen, "disponible", lambda: False)
    for k in _CLAVES:
        stores.config.pop(k, None)
    marca_logo._cache.clear()
    yield
    for k in _CLAVES:
        stores.config.pop(k, None)
    marca_logo._cache.clear()


def _png(w: int, h: int, color=(200, 30, 30, 255)) -> str:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (w // 2, h // 2), color), (w // 4, h // 4))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _defecto() -> bytes:
    return open(marca_logo.LOGO_DEFECTO, "rb").read()


def test_sin_logo_propio_sale_el_de_siempre():
    r = cli.get("/marca/logo.png")
    assert r.status_code == 200 and r.content == _defecto()
    assert cli.get("/config/canal").json()["marca_logo_url"] == ""
    assert "/marca/logo.png?v=" in cli.get("/libro-de-reclamaciones").text  # cabecera + favicon


def test_subir_logo_lo_normaliza_y_lo_usa_toda_la_web():
    r = cli.post("/admin/api/marca/logo", json={"imagen": _png(800, 400)}, headers=ADM)
    assert r.status_code == 200 and r.json()["personalizado"] is True
    v = r.json()["version"]
    png = cli.get("/marca/logo.png").content
    im = Image.open(io.BytesIO(png))
    assert im.size == (512, 512) and im.mode == "RGBA"
    assert im.getpixel((0, 0))[3] == 0          # fondo transparente conservado
    assert im.getpixel((256, 256))[:3] == (200, 30, 30)  # el logo, centrado
    assert png != _defecto()
    assert cli.get("/marca/logo-og.png").content == png
    canal = cli.get("/config/canal").json()
    assert canal["marca_logo_url"].endswith(f"/marca/logo.png?v={v}")
    assert f"/marca/logo.png?v={v}" in cli.get("/libro-de-reclamaciones").text
    # Las piezas compuestas (redes, videos) usan el mismo logo.
    assert marca_logo.abrir().size == (512, 512)


def test_volver_al_logo_original():
    cli.post("/admin/api/marca/logo", json={"imagen": _png(600, 600)}, headers=ADM)
    r = cli.post("/admin/api/marca/logo/quitar", headers=ADM)
    assert r.status_code == 200 and r.json()["personalizado"] is False
    assert cli.get("/marca/logo.png").content == _defecto()
    assert cli.get("/config/canal").json()["marca_logo_url"] == ""


def test_rechaza_lo_que_no_sirve():
    assert cli.post("/admin/api/marca/logo", json={"imagen": _png(600, 600)}).status_code in (401, 422)
    r = cli.post("/admin/api/marca/logo", json={"imagen": "data:image/png;base64,aG9sYQ=="}, headers=ADM)
    assert r.status_code == 400 and "imagen" in r.json()["detail"]
    r = cli.post("/admin/api/marca/logo", json={"imagen": _png(60, 60)}, headers=ADM)
    assert r.status_code == 400 and "chica" in r.json()["detail"]
    assert marca_logo.personalizado() is False


def test_con_storage_sube_el_png_y_guarda_solo_la_url(monkeypatch):
    subidas = []
    monkeypatch.setattr(almacen, "disponible", lambda: True)
    monkeypatch.setattr(almacen, "subir", lambda b, ruta, datos, ct="", **k: subidas.append((b, ruta, ct, datos))
                        or f"https://x.supabase.co/storage/v1/object/public/{b}/{ruta}?v=1")
    monkeypatch.setattr(almacen, "borrar_foto", lambda url: True)
    r = cli.post("/admin/api/marca/logo", json={"imagen": _png(512, 512)}, headers=ADM)
    assert r.status_code == 200
    assert subidas and subidas[0][0] == "canchas" and subidas[0][1].startswith("marca/logo_") and subidas[0][2] == "image/png"
    assert stores.config["marca_logo_url"].startswith("https://x.supabase.co/") and "marca_logo_b64" not in stores.config
    # Sirve desde la caché sin volver a descargar.
    assert cli.get("/marca/logo.png").content == subidas[0][3]
