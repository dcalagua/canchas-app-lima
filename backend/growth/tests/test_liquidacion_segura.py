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


def test_reembolso_del_apk_lo_hace_el_servidor(monkeypatch):
    from pagos import culqi
    from pagos import router as pr
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(stores, "pagos", [])
    monkeypatch.setattr(pr, "_email_de_token", lambda t: {"tok-ana": "ana@x.com"}.get(t))
    devueltos = []
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: devueltos.append(kw) or {"ok": True, "refund_id": "ref_9"})
    stores.registrar_pago(tipo="fee_reserva", monto_centimos=6000, moneda="PEN", estado="aprobado",
                          culqi_charge_id="chr_ana", email="ana@x.com")
    stores.registrar_pago(tipo="fee_reserva", monto_centimos=6000, moneda="PEN", estado="aprobado",
                          culqi_charge_id="chr_beto", email="beto@x.com")
    H = {"X-User-Token": "tok-ana"}
    assert client.post("/pagos/reembolso-app", json={"charge_id": "chr_ana"}).status_code == 401
    # Cargo AJENO: no se devuelve; queda para el operador.
    j = client.post("/pagos/reembolso-app", json={"charge_id": "chr_beto", "monto_soles": 60}, headers=H).json()
    assert j["manual"] and devueltos == []
    # El propio: Culqi devuelve todo, una sola vez.
    assert client.post("/pagos/reembolso-app", json={"charge_id": "chr_ana"}, headers=H).json()["reembolsado"]
    assert client.post("/pagos/reembolso-app", json={"charge_id": "chr_ana"}, headers=H).json()["duplicado"]
    assert devueltos == [{"charge_id": "chr_ana", "monto_centimos": 6000}]
