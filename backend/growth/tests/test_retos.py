"""Retos P2P: crear, listar (recibidos/enviados), responder y reportar
resultado; los jugados se exponen para el ranking."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "")
    yield


def _crear(retador="ana@x.com", retado="luis@x.com", deporte="tenis", zona="San Borja"):
    return client.post("/retos/crear", json={
        "retador_email": retador, "retador_nombre": "Ana",
        "retado_email": retado, "retado_nombre": "Luis",
        "deporte": deporte, "zona": zona}).json()


def test_crear_lista_recibidos_y_enviados():
    r = _crear()
    assert r["ok"] is True and r["reto"]["estado"] == "pendiente"
    # Retado ve el reto en recibidos; retador en enviados.
    del_retado = client.get("/retos/luis@x.com").json()
    assert len(del_retado["recibidos"]) == 1 and del_retado["enviados"] == []
    del_retador = client.get("/retos/ana@x.com").json()
    assert len(del_retador["enviados"]) == 1 and del_retador["recibidos"] == []


def test_no_puedes_retarte_a_ti_mismo():
    r = _crear(retador="ana@x.com", retado="ANA@x.com")
    assert r["ok"] is False and r["error"] == "no_puedes_retarte"


def test_free_tiene_tope_semanal_pro_ilimitado():
    from datetime import timedelta

    from db.store import ahora
    # Sin Pro: 3 retos pasan, el 4º corta.
    for _ in range(3):
        assert _crear()["ok"] is True
    bloqueado = _crear()
    assert bloqueado["ok"] is False and bloqueado["error"] == "limite_retos_free"
    assert bloqueado["limite"] == 3
    # Con Pro vigente: ilimitado.
    stores.membresias_pro["ana@x.com"] = {
        "hasta": (ahora() + timedelta(days=30)).isoformat()}
    assert _crear()["ok"] is True


def test_reporte_queda_por_confirmar_y_confirmacion_suma():
    rid = _crear()["reto"]["id"]
    client.post(f"/retos/{rid}/responder", json={"aceptar": True})
    # Ana reporta que ganó ella → queda POR CONFIRMAR (aún no cuenta).
    r2 = client.post(f"/retos/{rid}/resultado", json={
        "ganador_email": "ana@x.com", "marcador": "6-3 6-4",
        "reportado_por": "ana@x.com"}).json()
    assert r2["ok"] is True and r2["reto"]["estado"] == "por_confirmar"
    assert r2["reto"]["jugado_en"] is None
    # No aparece en el ranking mientras no se confirme.
    assert client.get("/retos?deporte=tenis").json()["resultados"] == []
    # El reportador NO puede confirmar su propio reporte.
    malo = client.post(f"/retos/{rid}/confirmar", json={
        "por_email": "ana@x.com", "acepta": True}).json()
    assert malo["ok"] is False and malo["error"] == "reportador_no_confirma"
    # Luis (el otro) confirma → jugado; ahora sí suma al ranking.
    ok = client.post(f"/retos/{rid}/confirmar", json={
        "por_email": "luis@x.com", "acepta": True}).json()
    assert ok["ok"] is True and ok["reto"]["estado"] == "jugado"
    assert ok["reto"]["jugado_en"]
    res = client.get("/retos?deporte=tenis").json()["resultados"]
    assert len(res) == 1 and res[0]["ganador_email"] == "ana@x.com"
    assert client.get("/retos?deporte=futbol").json()["resultados"] == []


def test_disputa_no_suma_al_ranking():
    rid = _crear()["reto"]["id"]
    client.post(f"/retos/{rid}/responder", json={"aceptar": True})
    client.post(f"/retos/{rid}/resultado", json={
        "ganador_email": "ana@x.com", "reportado_por": "ana@x.com"})
    r = client.post(f"/retos/{rid}/confirmar", json={
        "por_email": "luis@x.com", "acepta": False}).json()
    assert r["ok"] is True and r["reto"]["estado"] == "disputado"
    assert client.get("/retos?deporte=tenis").json()["resultados"] == []


def test_auto_confirmacion_al_vencer_el_plazo():
    from datetime import timedelta

    from db.store import ahora
    rid = _crear()["reto"]["id"]
    client.post(f"/retos/{rid}/responder", json={"aceptar": True})
    client.post(f"/retos/{rid}/resultado", json={
        "ganador_email": "ana@x.com", "reportado_por": "ana@x.com"})
    # Simula que el reporte fue hace 48 h (mayor al plazo por defecto de 24 h).
    reto = next(x for x in stores.retos if x.id == rid)
    reto.reportado_en = ahora() - timedelta(hours=48)
    # Al leer, se auto-confirma a favor del reportado.
    res = client.get("/retos?deporte=tenis").json()["resultados"]
    assert len(res) == 1 and res[0]["ganador_email"] == "ana@x.com"
    assert res[0]["auto_confirmado"] is True


def test_plazo_cero_confirma_al_instante():
    stores.config["retos_confirmacion_horas"] = "0"
    rid = _crear()["reto"]["id"]
    client.post(f"/retos/{rid}/responder", json={"aceptar": True})
    r = client.post(f"/retos/{rid}/resultado", json={
        "ganador_email": "ana@x.com", "reportado_por": "ana@x.com"}).json()
    assert r["reto"]["estado"] == "jugado"
    assert client.get("/retos?deporte=tenis").json()["resultados"] != []


def test_ganador_invalido_no_marca_jugado():
    rid = _crear()["reto"]["id"]
    r = client.post(f"/retos/{rid}/resultado", json={
        "ganador_email": "otro@x.com"}).json()
    assert r["ok"] is False and r["error"] == "ganador_invalido"


def test_rechazar_reto():
    rid = _crear()["reto"]["id"]
    r = client.post(f"/retos/{rid}/responder", json={"aceptar": False}).json()
    assert r["reto"]["estado"] == "rechazado"


def test_resultado_reto_inexistente_404():
    assert client.post("/retos/999/resultado",
                       json={"ganador_email": "a@x.com"}).status_code == 404
