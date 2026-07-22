"""Servicios de marketing: "Presencia digital" es un PAQUETE que incluye
Landing + Manejo de redes. No debe haber doble cobro ni contratación redundante.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "")
    # Precios conocidos.
    stores.config["servicio_landing_soles"] = "49"
    stores.config["servicio_redes_soles"] = "99"
    stores.config["servicio_presencia_soles"] = "129"
    stores.acreditar("aca:1", 100000)  # saldo de sobra (céntimos)
    yield


@pytest.fixture
def client():
    import main
    return TestClient(main.app)


def _contratar(client, servicio):
    return client.post("/pagos/servicios/contratar", json={
        "dueno_id": "aca:1", "academia_id": "aca:1", "servicio": servicio}).json()


def test_contratar_presencia_cancela_individuales(client):
    assert _contratar(client, "landing")["ok"] is True
    assert _contratar(client, "redes")["ok"] is True
    r = _contratar(client, "presencia")
    assert r["ok"] is True
    assert set(r["reemplaza"]) == {"landing", "redes"}
    # Los individuales quedaron cancelados.
    subs = {s["servicio"]: s["estado"]
            for s in client.get("/pagos/servicios/estado/aca:1").json()["suscripciones"]}
    assert subs["presencia"] == "activa"
    assert subs["landing"] == "cancelada"
    assert subs["redes"] == "cancelada"


def test_no_contratar_individual_si_hay_presencia(client):
    assert _contratar(client, "presencia")["ok"] is True
    r = _contratar(client, "landing")
    assert r["ok"] is False
    assert r["incluido"] is True
    assert r["por"] == "presencia"


def test_resolver_solapamiento_limpia_estado_existente():
    # Estado "sucio": los 3 activos a la vez (como en pruebas).
    stores.reset()
    for serv in ("landing", "redes", "presencia"):
        stores.suscripciones[f"aca:1:{serv}"] = {
            "academia_id": "aca:1", "dueno_id": "d", "servicio": serv,
            "monto_centimos": 100, "estado": "activa"}
    n = stores.resolver_solapamiento_servicios()
    assert n == 2  # cancela landing + redes
    assert stores.suscripciones["aca:1:presencia"]["estado"] == "activa"
    assert stores.suscripciones["aca:1:landing"]["estado"] == "cancelada"
    assert stores.suscripciones["aca:1:redes"]["estado"] == "cancelada"
