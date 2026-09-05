"""Comisión por cobro digital de matrícula (tarifa "tipo POS", por país).

El alumno paga limpio; la academia absorbe la comisión configurable por país.
Efectivo = 0% (no pasa por el endpoint). El neto queda como 'por recibir'.
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
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok")
    yield


@pytest.fixture
def client():
    import main
    return TestClient(main.app)


def test_defaults_por_pais(client):
    # Perú arranca en 5%; Ecuador y Bolivia en 0 hasta configurarse.
    assert client.get("/pagos/comision-matricula?pais=pe").json()["pct"] == 5.0
    assert client.get("/pagos/comision-matricula?pais=ec").json()["pct"] == 0.0
    assert client.get("/pagos/comision-matricula?pais=bo").json()["pct"] == 0.0


def test_comision_por_pais_y_neto(client):
    # El operador fija 5% en Perú desde la torre de control.
    r = client.post("/admin/api/comision", json={"pe": 5},
                    headers={"X-Admin-Token": "tok"})
    assert r.status_code == 200 and r.json()["pe"] == 5.0
    assert client.get("/pagos/comision-matricula?pais=pe").json()["pct"] == 5.0

    # Cobro digital de S/250 → comisión 12.5, neto 237.5.
    r = client.post("/pagos/matricula", json={
        "academia_id": "ac1", "monto_soles": 250, "matricula_id": "m1",
        "pais": "pe"})
    j = r.json()
    assert j["comision_centimos"] == 1250
    assert j["neto_centimos"] == 23750

    # Idempotente: mismo matricula_id no cobra de nuevo.
    j2 = client.post("/pagos/matricula", json={
        "academia_id": "ac1", "monto_soles": 250, "matricula_id": "m1",
        "pais": "pe"}).json()
    assert j2["duplicada"] is True

    # Resumen para el reporte del profe.
    res = client.get("/pagos/matricula/resumen/ac1").json()
    assert res["cobros"] == 1
    assert res["bruto_soles"] == 250.0
    assert res["comision_soles"] == 12.5
    assert res["neto_soles"] == 237.5

    # Filtro por fecha (para cuadrar con el período del reporte): un rango que NO
    # incluye hoy deja el resumen en cero; uno que sí lo incluye, lo mantiene.
    fuera = client.get(
        "/pagos/matricula/resumen/ac1?hasta=2000-01-01T00:00:00").json()
    assert fuera["cobros"] == 0 and fuera["bruto_soles"] == 0.0
    dentro = client.get(
        "/pagos/matricula/resumen/ac1?desde=2000-01-01T00:00:00").json()
    assert dentro["cobros"] == 1 and dentro["bruto_soles"] == 250.0


def test_comision_congelada_no_se_recalcula(client):
    client.post("/admin/api/comision", json={"pe": 10},
                headers={"X-Admin-Token": "tok"})
    client.post("/pagos/matricula", json={
        "academia_id": "ac2", "monto_soles": 100, "matricula_id": "mx",
        "pais": "pe"})
    # Cambia la tarifa después del cobro.
    client.post("/admin/api/comision", json={"pe": 20},
                headers={"X-Admin-Token": "tok"})
    # El resumen sigue con la comisión congelada (10%, no 20%).
    res = client.get("/pagos/matricula/resumen/ac2").json()
    assert res["comision_soles"] == 10.0
