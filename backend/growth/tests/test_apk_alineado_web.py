"""El APK alineado con la web (29-sep-2026): stock del Marketplace apartado
antes de cobrar, cupones solo en la moneda de la billetera y país de casa
compartido app ↔ web."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import main  # noqa: E402
from db import pg  # noqa: E402
from db.store import stores  # noqa: E402
from pagos import stock_productos as sp  # noqa: E402
from web import jugador_billetera as jb  # noqa: E402

cli = TestClient(main.app)
_ADMIN = {"X-Admin-Token": "tok_admin"}


class _Stock:
    """`pichangol_productos` en memoria con el mismo UPDATE atómico."""

    def __init__(self):
        self.p = {"prod_1": {"id": "prod_1", "vendedor_email": "vende@x.com", "activo": True, "stock": 1},
                  "prod_ilim": {"id": "prod_ilim", "vendedor_email": "vende@x.com", "activo": True, "stock": None},
                  "prod_pausa": {"id": "prod_pausa", "vendedor_email": "vende@x.com", "activo": False, "stock": 5}}

    def leer(self, pid):
        f = self.p.get(pid)
        return dict(f) if f else None

    def apartar(self, pid):
        f = self.p.get(pid)
        if not f or not f["activo"] or (f["stock"] is not None and f["stock"] <= 0):
            return False
        if f["stock"] is not None:
            f["stock"] -= 1
        return True

    def devolver(self, pid):
        f = self.p.get(pid)
        if f and f["stock"] is not None:
            f["stock"] += 1


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok_admin", raising=False)
    monkeypatch.setattr(jb.datos, "canchas_de_dueno", lambda email: [])
    yield


@pytest.fixture()
def base(monkeypatch):
    b = _Stock()
    monkeypatch.setattr(pg, "habilitado", True, raising=False)
    monkeypatch.setattr(sp, "leer_producto", b.leer)
    monkeypatch.setattr(sp, "apartar_unidad", b.apartar)
    monkeypatch.setattr(sp, "devolver_unidad", b.devolver)
    return b


def _apartar(aid, pid="prod_1", email="compra@x.com"):
    return cli.post("/pagos/venta/apartar", json={"apartado_id": aid, "producto_id": pid, "email": email}).json()


def test_apk_aparta_la_unidad_antes_de_cobrar_y_no_vende_de_mas(base):
    r = _apartar("ap_1")
    assert r["ok"] and r["estado"] == "apartado" and base.p["prod_1"]["stock"] == 0
    # Reintento del mismo intento: no descuenta dos veces.
    assert _apartar("ap_1")["duplicado"] is True
    assert base.p["prod_1"]["stock"] == 0
    # Otro comprador: se agotó.
    r2 = _apartar("ap_2", email="otro@x.com")
    assert not r2["ok"] and r2["error"] == "agotado" and "Se agotó" in r2["mensaje"]
    # El cobro del primero fue rechazado: vuelve UNA sola vez.
    d = cli.post("/pagos/venta/devolver", json={"apartado_id": "ap_1", "email": "compra@x.com"}).json()
    assert d["ok"] and d["estado"] == "devuelto" and base.p["prod_1"]["stock"] == 1
    assert cli.post("/pagos/venta/devolver", json={"apartado_id": "ap_1", "email": "compra@x.com"}).json()["duplicado"]
    assert base.p["prod_1"]["stock"] == 1
    # Un devuelto no se reusa ni lo puede devolver otro correo.
    assert _apartar("ap_1")["error"] == "cerrado"
    assert cli.post("/pagos/venta/devolver", json={"apartado_id": "ap_1", "email": "otro@x.com"}).json()["ok"] is False


def test_apartar_propio_pausado_e_ilimitado(base):
    assert _apartar("a", email="vende@x.com")["error"] == "propio"
    assert _apartar("b", pid="prod_pausa")["error"] == "no_disponible"
    assert _apartar("c", pid="no_existe")["error"] == "no_disponible"
    r = _apartar("d", pid="prod_ilim")
    assert r["ok"] and base.p["prod_ilim"]["stock"] is None
    cli.post("/pagos/venta/devolver", json={"apartado_id": "d", "email": "compra@x.com"})
    assert base.p["prod_ilim"]["stock"] is None


def test_venta_registrada_marca_vendido_y_los_abandonados_vuelven_al_stock(base):
    base.p["prod_1"]["stock"] = 3
    _apartar("ap_ok")
    r = cli.post("/pagos/venta", json={"vendedor_id": "vende@x.com", "monto_soles": 50, "venta_id": "chr_1",
                                       "producto_id": "prod_1", "comprador_email": "compra@x.com",
                                       "apartado_id": "ap_ok", "moneda": "PEN"}).json()
    assert r["ok"]
    assert stores.apartados_stock["ap_ok"]["estado"] == "vendido"
    # Un APK que apartó y murió: a los 30 min vuelve. Otro que cobró pero no
    # mandó `apartado_id` (venta registrada) queda vendido.
    _apartar("ap_muerto", email="b@x.com")
    _apartar("ap_sin_id", email="c@x.com")
    cli.post("/pagos/venta", json={"vendedor_id": "vende@x.com", "monto_soles": 50, "venta_id": "chr_2",
                                   "producto_id": "prod_1", "comprador_email": "c@x.com", "moneda": "PEN"})
    assert base.p["prod_1"]["stock"] == 0
    assert sp.liberar_vencidos() == 0  # aún no vencen
    n = sp.liberar_vencidos(datetime.now(timezone.utc) + timedelta(minutes=31))
    assert n == 2
    assert stores.apartados_stock["ap_muerto"]["estado"] == "vencido"
    assert stores.apartados_stock["ap_sin_id"]["estado"] == "vendido"
    assert base.p["prod_1"]["stock"] == 1
    # Persiste en el snapshot.
    assert stores.to_state()["apartados_stock"]["ap_ok"]["estado"] == "vendido"


def _cupon(codigo="HOLA", valor=10):
    cli.post("/pagos/cupones", headers=_ADMIN, json={"codigo": codigo, "valor_soles": valor, "usos_max": 10})


def test_cupon_en_soles_no_entra_a_una_billetera_en_dolares_o_bolivianos():
    _cupon()
    # El APK dice que su billetera es en $ → rechazado con el texto de la web.
    r = cli.post("/pagos/cupon/canjear", json={"email": "ec@x.com", "codigo": "HOLA", "moneda": "USD"}).json()
    assert r == {"ok": False, "error": "cupon_solo_soles", "mensaje": jb._MSJ_CUPON["cupon_solo_soles"]}
    assert stores.saldo_centimos("ec@x.com") == 0
    # APK viejo sin moneda: el backend la deduce (país de casa BO).
    stores.clientes_pago["bo@x.com"] = {"pais_casa": "BO", "pais_casa_en": datetime.now(timezone.utc).isoformat()}
    r = cli.post("/pagos/cupon/canjear", json={"email": "bo@x.com", "codigo": "HOLA"}).json()
    assert r["error"] == "cupon_solo_soles"
    # En soles sí entra (una sola vez por usuario, como antes).
    r = cli.post("/pagos/cupon/canjear", json={"email": "pe@x.com", "codigo": "HOLA", "moneda": "PEN"}).json()
    assert r["ok"] and stores.saldo_centimos("pe@x.com") == 1000
    assert "pe@x.com" in stores.cupones["HOLA"]["usados"]
    assert "ec@x.com" not in stores.cupones["HOLA"]["usados"]


def test_pais_de_casa_compartido_entre_app_y_web():
    e = "viaja@x.com"
    g = cli.get(f"/pagos/pais-casa/{e}").json()
    assert g["pais_casa"] == "" and g["puede_cambiar"] is True
    r = cli.post("/pagos/pais-casa", json={"email": e, "iso": "EC"}).json()
    assert r["ok"] and r["iso"] == "EC" and r["pais_casa_en"]
    # La web lee lo mismo que escribió el APK.
    assert jb.pais_billetera(e, canchas=[]) == ("EC", "elegido")
    assert cli.get(f"/pagos/pais-casa/{e}").json()["pais_casa"] == "EC"
    # Con saldo no se cambia.
    stores.acreditar(e, 500)
    r = cli.post("/pagos/pais-casa", json={"email": e, "iso": "PE"}).json()
    assert not r["ok"] and r["error"] == "tiene_saldo"
    assert stores.clientes_pago[e]["pais_casa"] == "EC"
    # El mismo país que ya tiene no es un cambio.
    assert cli.post("/pagos/pais-casa", json={"email": e, "iso": "EC"}).json()["sin_cambio"] is True
    assert cli.post("/pagos/pais-casa", json={"email": e, "iso": "AR"}).status_code == 400
