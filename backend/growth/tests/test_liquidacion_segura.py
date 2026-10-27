"""Seguridad C2: una liquidación online (el "por recibir" que el lote BCP le
paga al dueño) solo se acepta respaldada por un COBRO REAL del backend."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def _liq(reserva_id, monto, charge_id=""):
    return client.post("/pagos/liquidacion-online", json={
        "dueno_id": "dueno@x.com", "monto_soles": monto, "reserva_id": reserva_id,
        "charge_id": charge_id, "moneda": "PEN"}).json()


def test_sin_cobro_real_no_hay_por_recibir(monkeypatch):
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(stores, "pagos", [])
    # Cargo inventado: rechazado, nada queda por pagar.
    assert _liq("r_falsa", 500, "chr_inventado") == {"ok": False, "error": "cargo_no_verificado"}
    assert stores.liquidaciones(solo_pendientes=True) == []
    # Cargo real de S/ 60: no respalda una liquidación de S/ 500.
    stores.registrar_pago(tipo="fee_reserva", monto_centimos=6000, moneda="PEN", estado="aprobado",
                          culqi_charge_id="chr_real", email="ana@x.com")
    assert _liq("r1", 500, "chr_real")["error"] == "monto_mayor_al_cargo"
    # El mismo cargo sí respalda SU reserva…
    assert _liq("r1", 60, "chr_real")["ok"]
    assert len(stores.liquidaciones(solo_pendientes=True)) == 1
    # …pero no una segunda.
    assert _liq("r2", 60, "chr_real")["error"] == "cargo_ya_liquidado"
    # Una liquidación tampoco respalda otra.
    assert _liq("r3", 10, "r1")["error"] == "cargo_no_verificado"


def test_apk_viejo_sin_cargo_queda_en_revision_hasta_que_el_operador_aprueba(monkeypatch):
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(stores, "pagos", [])
    j = _liq("r_viejo", 60)
    assert j["ok"] and j["en_revision"]
    assert stores.liquidaciones(solo_pendientes=True) == []          # el lote no la paga
    assert client.post("/pagos/liquidacion/r_viejo/aprobar-revision").status_code in (401, 403)
    r = client.post("/pagos/liquidacion/r_viejo/aprobar-revision", headers={"X-Admin-Token": "adm"})
    assert r.json() == {"ok": True, "aprobadas": 1}
    assert len(stores.liquidaciones(solo_pendientes=True)) == 1
