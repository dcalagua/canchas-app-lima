"""Community manager autónomo (Fase 0): el post del día = copy + hashtags (IA o
plantilla) + un FLYER de marca (imagen PNG) para publicar en 1 toque."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from marketing.flyer import generar_flyer  # noqa: E402

client = TestClient(app)

_DATOS = {
    "nombre": "Academia Tenis Lima",
    "deporte": "tenis",
    "sede": "San Borja",
    "whatsapp": "51999888777",
}


def test_flyer_genera_png():
    png = generar_flyer(_DATOS, "Clases de tenis para todas las edades. Inscríbete.")
    assert png is not None
    # Firma de un archivo PNG.
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000  # una imagen real, no vacía


def test_post_del_dia_devuelve_texto_e_imagen():
    r = client.post("/marketing/cm/post-del-dia",
                    json={"academia_id": "a1", "datos": _DATOS})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["texto"]  # copy no vacío (plantilla si no hay ANTHROPIC_API_KEY)
    assert isinstance(j["hashtags"], list)
    assert j["imagen_url"].endswith(".png")
    # La imagen se sirve públicamente (para el fetch de Meta / el APK).
    path = "/" + j["imagen_url"].split("/", 3)[3]
    img = client.get(path)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
