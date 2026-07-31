"""Community manager autónomo (Fase 0): el post del día = copy + hashtags (IA o
plantilla) + un FLYER de marca (imagen PNG) para publicar en 1 toque."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from marketing import cm as cm_svc  # noqa: E402
from marketing.flyer import generar_flyer  # noqa: E402
from marketing.reel import generar_reel  # noqa: E402

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


def test_cm_config_activa_y_pre_genera():
    r = client.post("/marketing/cm/config",
                    json={"academia_id": "cm1", "activo": True,
                          "cada_dias": 3, "datos": _DATOS})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["activo"] is True
    assert j["post"] is not None
    assert j["post"]["texto"]
    assert j["post"]["imagen_url"].endswith(".png")

    # El estado devuelve el post ya pre-generado.
    e = client.get("/marketing/cm/estado/cm1").json()
    assert e["activo"] is True
    assert e["post"] is not None


def test_scheduler_regenera_cuando_vence_la_cadencia():
    cm_svc.config_cm("cm2", activo=True, cada_dias=1, datos=_DATOS)
    cm_svc.generar_para("cm2")
    # Simula que el último post es de hace 2 días → toca regenerar.
    viejo = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    stores.cm["cm2"]["ultimo_generado"] = viejo
    n = cm_svc.procesar_cm_pendientes()
    assert n >= 1
    assert stores.cm["cm2"]["ultimo_generado"] != viejo


def test_reel_genera_mp4():
    mp4 = generar_reel(_DATOS, "Ven a jugar tenis este fin de semana.",
                       tipo="promo")
    if mp4 is None:
        pytest.skip("ffmpeg empaquetado no disponible en este entorno")
    # Firma MP4/ISO-BMFF: los bytes 4..8 son el box 'ftyp'.
    assert mp4[4:8] == b"ftyp"
    assert len(mp4) > 5000  # un video real, no vacío


def test_reel_del_dia_endpoint():
    r = client.post("/marketing/cm/reel-del-dia",
                    json={"academia_id": "reel1", "datos": _DATOS,
                          "contexto": "Clases de tenis, cupos abiertos."})
    assert r.status_code == 200
    j = r.json()
    if not j.get("ok"):
        pytest.skip("ffmpeg empaquetado no disponible en este entorno")
    assert j["reel_url"].endswith(".mp4")
    # El reel se sirve públicamente (para el APK / la subida a Meta).
    path = "/" + j["reel_url"].split("/", 3)[3]
    vid = client.get(path)
    assert vid.status_code == 200
    assert vid.headers["content-type"] == "video/mp4"


def test_publicar_reel_sandbox():
    from marketing import redes as redes_svc
    redes_svc.conectar("pubvid")  # conexión simulada (sandbox)
    r = redes_svc.publicar("pubvid", "Mira nuestro reel",
                           video_url="https://x/y.mp4")
    assert r["ok"] is True
    ig = r["resultados"]["instagram"]
    assert ig["ok"] is True and ig["formato"] == "reel"


def test_auto_publicar_en_scheduler(monkeypatch):
    import config as cfg
    from marketing import redes as redes_svc
    monkeypatch.setattr(cfg, "PUBLIC_BASE_URL", "https://test.local")
    datos = {**_DATOS, "fotos": ["https://x/foto1.jpg"]}
    redes_svc.conectar("apub")  # sandbox conectado
    cm_svc.config_cm("apub", activo=True, cada_dias=1, datos=datos,
                     auto_publicar=True)
    post = cm_svc.generar_para("apub", con_reel=True)
    assert post is not None
    cm_svc._auto_publicar("apub", stores.cm["apub"], post)
    up = stores.cm["apub"].get("ultima_publicacion")
    assert up is not None and up["ok"] is True


def test_config_expone_auto_publicar():
    r = client.post("/marketing/cm/config",
                    json={"academia_id": "apx", "activo": True,
                          "datos": _DATOS, "auto_publicar": True})
    j = r.json()
    assert j["ok"] is True
    assert j["auto_publicar"] is True


def test_scheduler_no_genera_si_reciente_o_inactivo():
    cm_svc.config_cm("cm3", activo=True, cada_dias=5, datos=_DATOS)
    cm_svc.generar_para("cm3")  # recién generado → no vence
    cm_svc.config_cm("cm4", activo=False, datos=_DATOS)  # inactivo
    # cm3 reciente y cm4 inactivo → ninguno de estos dos debe generar.
    antes = stores.cm["cm3"]["ultimo_generado"]
    cm_svc.procesar_cm_pendientes()
    assert stores.cm["cm3"]["ultimo_generado"] == antes
    assert stores.cm["cm4"]["ultimo_post"] is None
