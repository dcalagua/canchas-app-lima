"""PROMOCIONES de la billetera: bono de recarga (config en torre) y cupones."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import main  # noqa: E402
from db.store import stores  # noqa: E402

cli = TestClient(main.app)
_ADMIN = {"X-Admin-Token": "tok_admin"}


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok_admin",
                        raising=False)
    yield


def _recarga_qr_aprobada(email="ana@x.com", monto=80.0):
    sid = cli.post("/pagos/recarga-qr",
                   json={"email": email, "monto_soles": monto,
                         "foto_url": "http://x/c.jpg"}).json()["solicitud"]["id"]
    return cli.post(f"/pagos/recarga-qr/{sid}/aprobar", headers=_ADMIN), sid


def test_bono_apagado_por_defecto():
    r, _ = _recarga_qr_aprobada(monto=100.0)
    assert r.json()["bono_soles"] == 0.0
    assert stores.saldo_centimos("ana@x.com") == 10000


def test_bono_aplica_y_es_idempotente():
    ok = cli.post("/pagos/promos/admin",
                  json={"pct": 10, "minimo": 50, "tope": 20},
                  headers=_ADMIN)
    assert ok.status_code == 200
    r, sid = _recarga_qr_aprobada(monto=80.0)
    assert r.json()["bono_soles"] == 8.0
    assert stores.saldo_centimos("ana@x.com") == 8800  # 80 + 8 de bono
    # Re-aprobar (duplicada) no re-acredita ni re-bonifica.
    r2 = cli.post(f"/pagos/recarga-qr/{sid}/aprobar", headers=_ADMIN)
    assert r2.json()["duplicada"] is True
    assert stores.saldo_centimos("ana@x.com") == 8800
    # El bono aparece en los movimientos como ingreso.
    movs = cli.get("/pagos/movimientos/ana@x.com").json()["movimientos"]
    assert any(m["tipo"] == "bono_recarga" and m["monto_soles"] == 8.0
               for m in movs)


def test_bono_respeta_minimo_y_tope():
    cli.post("/pagos/promos/admin",
             json={"pct": 10, "minimo": 50, "tope": 20}, headers=_ADMIN)
    # Bajo el mínimo → sin bono.
    r, _ = _recarga_qr_aprobada(email="min@x.com", monto=20.0)
    assert r.json()["bono_soles"] == 0.0
    # Sobre el tope → bono recortado a 20.
    r2, _ = _recarga_qr_aprobada(email="top@x.com", monto=500.0)
    assert r2.json()["bono_soles"] == 20.0


def test_promos_endpoint_del_apk():
    cli.post("/pagos/promos/admin",
             json={"pct": 10, "minimo": 50, "tope": 20}, headers=_ADMIN)
    j = cli.get("/pagos/promos").json()["bono_recarga"]
    assert j["activo"] is True and j["pct"] == 10.0
    # Valores inválidos rechazados.
    assert cli.post("/pagos/promos/admin", json={"pct": 200},
                    headers=_ADMIN).status_code == 400


def test_cupon_crear_canjear_y_limites():
    c = cli.post("/pagos/cupones",
                 json={"codigo": "BIENVENIDA", "valor_soles": 10,
                       "usos_max": 2}, headers=_ADMIN)
    assert c.status_code == 200 and c.json()["codigo"] == "BIENVENIDA"
    # Canje OK (case-insensitive).
    r = cli.post("/pagos/cupon/canjear",
                 json={"email": "ana@x.com", "codigo": "bienvenida"})
    assert r.json()["ok"] and r.json()["valor_soles"] == 10.0
    assert stores.saldo_centimos("ana@x.com") == 1000
    # Mismo usuario, segunda vez → no.
    r2 = cli.post("/pagos/cupon/canjear",
                  json={"email": "ana@x.com", "codigo": "BIENVENIDA"})
    assert r2.json()["error"] == "ya_lo_canjeaste"
    # Otro usuario agota los usos; el tercero rebota.
    cli.post("/pagos/cupon/canjear",
             json={"email": "b@x.com", "codigo": "BIENVENIDA"})
    r3 = cli.post("/pagos/cupon/canjear",
                  json={"email": "c@x.com", "codigo": "BIENVENIDA"})
    assert r3.json()["error"] == "cupon_agotado"
    # Lista admin con usos.
    lst = cli.get("/pagos/cupones", headers=_ADMIN).json()["cupones"]
    assert lst[0]["usados"] == 2
    # Desactivar → inválido para nuevos canjes.
    cli.post("/pagos/cupones/BIENVENIDA/desactivar", headers=_ADMIN)
    r4 = cli.post("/pagos/cupon/canjear",
                  json={"email": "d@x.com", "codigo": "BIENVENIDA"})
    assert r4.json()["error"] == "cupon_invalido"


def test_cupon_codigo_autogenerado_y_duplicado():
    c = cli.post("/pagos/cupones", json={"valor_soles": 5},
                 headers=_ADMIN).json()
    assert c["codigo"].startswith("PCG-")
    dup = cli.post("/pagos/cupones",
                   json={"codigo": c["codigo"], "valor_soles": 5},
                   headers=_ADMIN)
    assert dup.status_code == 409
