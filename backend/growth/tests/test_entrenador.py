"""ENTRENADOR VIRTUAL: flujo del análisis, candados y tips al reloj."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from entrenador import router as ent  # noqa: E402
import main  # noqa: E402

cli = TestClient(main.app)

# Funciones REALES capturadas ANTES de que el fixture autouse las mockee
# (para los tests que validan sus candados internos).
_DESCARGAR_REAL = ent._descargar_video
_BORRAR_REAL = ent._borrar_video

_INFORME = {
    "encuadre_ok": True,
    "resumen": "Buen ritmo general; el lanzamiento de pelota queda bajo.",
    "fortalezas": ["Buena flexión de rodillas", "Empuñadura continental"],
    "correcciones": [
        {"titulo": "Lanzamiento bajo", "detalle": "La pelota cae antes del "
         "punto de impacto ideal.", "tip_reloj": "Lanza la pelota más arriba"},
        {"titulo": "Codo caído", "detalle": "El codo baja en la preparación.",
         "tip_reloj": "Sube más el codo al preparar"},
    ],
    "drills": ["20 lanzamientos de pelota sin golpear, que caiga en un aro"],
}


@pytest.fixture(autouse=True)
def _mundo(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "ENTRENADOR_REQUIERE_PRO", False)
    monkeypatch.setattr(config, "SUPABASE_URL", "https://qa.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon_qa")
    # Se mockean las piezas pesadas: descarga, ffmpeg, IA, nube y push.
    monkeypatch.setattr(ent, "_descargar_video", lambda url: b"VIDEOFAKE")
    monkeypatch.setattr(ent, "_extraer_frames", lambda v, max_frames=8: [b"F1", b"F2"])
    monkeypatch.setattr(ent, "_ia_analizar", lambda f, d, g: dict(_INFORME))
    monkeypatch.setattr(ent, "_analisis_del_mes", lambda e: 0)
    guardados = []
    monkeypatch.setattr(ent, "_persistir",
                        lambda *a: guardados.append(a))
    tips = []
    import pagos.router as pr
    monkeypatch.setattr(
        pr, "_aviso_push_usuario",
        lambda email, titulo, cuerpo, tipo="aviso": tips.append(
            (email, titulo, cuerpo, tipo)))
    borrados = []
    monkeypatch.setattr(ent, "_borrar_video", lambda url: borrados.append(url))
    yield {"guardados": guardados, "tips": tips, "borrados": borrados}


def _body(**extra):
    b = {"email": "ana@x.com", "deporte": "tenis", "golpe": "saque",
         "video_url": "https://qa.supabase.co/storage/v1/object/public/"
                      "canchas/entrenador/clip.mp4"}
    b.update(extra)
    return b


def test_analisis_devuelve_informe_y_persiste(_mundo):
    r = cli.post("/entrenador/analizar", json=_body()).json()
    assert r["ok"] is True
    assert r["informe"]["resumen"].startswith("Buen ritmo")
    assert len(r["informe"]["correcciones"]) == 2
    assert r["analisis_restantes_mes"] == 19
    # Se guardó en la nube para el historial.
    assert len(_mundo["guardados"]) == 1
    # Sin tips_reloj: no se mandó ningún push.
    assert r["tips_reloj_enviados"] == 0 and _mundo["tips"] == []


def test_tips_al_reloj_llegan_como_push_cortos(_mundo):
    r = cli.post("/entrenador/analizar",
                 json=_body(tips_reloj=True)).json()
    assert r["tips_reloj_enviados"] == 2
    assert len(_mundo["tips"]) == 2
    email, titulo, cuerpo, tipo = _mundo["tips"][0]
    assert email == "ana@x.com" and tipo == "entrenador"
    assert "🎾" in titulo
    # Tips CORTOS (caben en la pantalla de un smartwatch).
    assert all(len(t[2]) <= 60 for t in _mundo["tips"])


def test_candado_pro_fail_open_y_402(monkeypatch, _mundo):
    monkeypatch.setattr(config, "ENTRENADOR_REQUIERE_PRO", True)
    # Sin Pro → 402 (el APK ofrece "Hazte Pro").
    assert cli.post("/entrenador/analizar",
                    json=_body()).status_code == 402
    # Con Pro vigente → pasa.
    stores.membresias_pro["ana@x.com"] = {
        "hasta": "2099-01-01T00:00:00+00:00"}
    assert cli.post("/entrenador/analizar",
                    json=_body()).json()["ok"] is True


def test_limite_mensual_bloquea(monkeypatch, _mundo):
    monkeypatch.setattr(ent, "_analisis_del_mes", lambda e: 20)
    assert cli.post("/entrenador/analizar",
                    json=_body()).status_code == 429


def test_video_de_otro_host_rechazado(monkeypatch, _mundo):
    # La descarga REAL valida el host: solo el Supabase del proyecto.
    monkeypatch.setattr(ent, "_descargar_video", _DESCARGAR_REAL)
    r = cli.post("/entrenador/analizar",
                 json=_body(video_url="https://malo.com/x.mp4"))
    assert r.status_code == 400


def test_ia_caida_responde_503(monkeypatch, _mundo):
    monkeypatch.setattr(ent, "_ia_analizar", lambda f, d, g: None)
    assert cli.post("/entrenador/analizar",
                    json=_body()).status_code == 503
    # Con la IA caída el video NO se borra (el jugador puede reintentar).
    assert _mundo["borrados"] == []


def test_video_se_borra_tras_analisis_exitoso(_mundo):
    """Pedido del director: los clips no ocupan espacio — informe listo,
    video fuera."""
    r = cli.post("/entrenador/analizar", json=_body()).json()
    assert r["ok"] is True
    assert len(_mundo["borrados"]) == 1


def test_borrar_video_solo_toca_la_carpeta_entrenador(monkeypatch):
    """La función real jamás borra fuera de entrenador/ (candado de ruta)."""
    llamadas = []
    monkeypatch.setattr(config, "SUPABASE_URL", "https://qa.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon_qa")
    monkeypatch.setattr(ent.urllib.request, "urlopen",
                        lambda req, timeout=15: llamadas.append(req) or
                        __import__("io").BytesIO(b""))
    # Ruta fuera de entrenador/ → NO se llama al storage.
    _BORRAR_REAL("https://qa.supabase.co/storage/v1/object/public/"
                 "canchas/ilustraciones/il_x.jpg")
    assert llamadas == []
    # Ruta correcta → sí borra (DELETE a la ruta exacta, sin querystring).
    _BORRAR_REAL("https://qa.supabase.co/storage/v1/object/public/"
                 "canchas/entrenador/clip.mp4?v=123")
    assert len(llamadas) == 1
    assert llamadas[0].get_method() == "DELETE"
    assert llamadas[0].full_url.endswith("/canchas/entrenador/clip.mp4")
