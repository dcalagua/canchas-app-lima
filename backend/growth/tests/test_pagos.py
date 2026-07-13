"""Pagos con Culqi (modelo inDrive): recarga del dueño, fee de reserva, saldo,
webhook idempotente. Se mockea la llamada HTTP a Culqi (culqi._request) para
probar todo el flujo sin red ni llaves reales.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402

client = TestClient(app)


class _FakeCulqi:
    """Simula la API de Culqi en memoria: crea cargos y los devuelve al
    consultarlos (para el webhook)."""

    def __init__(self):
        self.cargos = {}
        self.n = 0
        self.forzar_error = False

    def request(self, metodo, path, body=None):
        if self.forzar_error:
            return {"ok": False, "status": 402, "error": "Tarjeta rechazada"}
        if metodo == "POST" and path == "/customers":
            self.n += 1
            return {"ok": True, "data": {"id": f"cus_test_{self.n}"}}
        if metodo == "POST" and path == "/cards":
            self.n += 1
            return {"ok": True, "data": {
                "id": f"crd_test_{self.n}",
                "source": {"last_four": "1111", "iin": {"card_brand": "Visa"}},
            }}
        if metodo == "DELETE" and path.startswith("/cards/"):
            return {"ok": True, "data": {}}
        if metodo == "POST" and path == "/charges":
            self.n += 1
            cid = f"chr_test_{self.n}"
            data = {
                "id": cid,
                "amount": body["amount"],
                "currency_code": body["currency_code"],
                "captured": True,
                "metadata": body.get("metadata", {}),
            }
            self.cargos[cid] = data
            return {"ok": True, "data": data}
        if metodo == "GET" and path.startswith("/charges/"):
            cid = path.split("/charges/")[1]
            if cid in self.cargos:
                return {"ok": True, "data": self.cargos[cid]}
            return {"ok": False, "status": 404, "error": "no encontrado"}
        return {"ok": False, "error": "ruta_desconocida"}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_xxx")
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_xxx")
    monkeypatch.setattr(config, "APP_API_KEY", "")  # sin app-key en tests
    fake = _FakeCulqi()
    monkeypatch.setattr(culqi, "_request", fake.request)
    yield fake


def test_config_expone_pk_y_modo():
    r = client.get("/pagos/config").json()
    assert r["disponible"] is True
    assert r["modo"] == "test"
    assert r["public_key"] == "pk_test_xxx"


def test_recarga_acredita_saldo():
    r = client.post("/pagos/recarga", json={
        "token": "tkn_1", "dueno_id": "due@x.com",
        "email": "due@x.com", "monto_soles": 30,
    }).json()
    assert r["ok"] is True
    assert r["saldo_centimos"] == 3000
    assert r["saldo_soles"] == 30.0
    assert stores.saldo_centimos("due@x.com") == 3000


def test_recarga_suma_sobre_saldo_existente():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 20})
    r = client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 10}).json()
    assert r["saldo_centimos"] == 3000


def test_recarga_monto_minimo():
    resp = client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 0.5})
    assert resp.status_code == 400


def test_recarga_rechazada_no_acredita(_setup):
    _setup.forzar_error = True
    r = client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 30}).json()
    assert r["ok"] is False
    assert stores.saldo_centimos("d") == 0


def test_fee_reserva_no_acredita_saldo():
    r = client.post("/pagos/fee-reserva", json={
        "token": "t", "email": "j@x.com", "monto_soles": 2,
        "concepto": "Fee reserva", "reserva_id": "r1"}).json()
    assert r["ok"] is True
    assert stores.saldo_centimos("j@x.com") == 0
    assert any(p.tipo == "fee_reserva" for p in stores.pagos)


def test_movimientos_lista_recargas_recientes_primero():
    # Dos recargas del mismo dueño → el historial las devuelve, la última primero.
    client.post("/pagos/recarga", json={
        "token": "tkn_a", "dueno_id": "due@x.com",
        "email": "due@x.com", "monto_soles": 30,
    })
    client.post("/pagos/recarga", json={
        "token": "tkn_b", "dueno_id": "due@x.com",
        "email": "due@x.com", "monto_soles": 50,
    })
    # Recarga de OTRO dueño: no debe aparecer en el historial del primero.
    client.post("/pagos/recarga", json={
        "token": "tkn_c", "dueno_id": "otro@x.com",
        "email": "otro@x.com", "monto_soles": 20,
    })
    r = client.get("/pagos/movimientos/due@x.com").json()
    movs = r["movimientos"]
    assert len(movs) == 2
    assert movs[0]["monto_soles"] == 50.0  # la más reciente, primero
    assert movs[1]["monto_soles"] == 30.0
    assert all(m["tipo"] == "recarga" for m in movs)


def test_movimientos_vacio_si_no_hay_recargas():
    r = client.get("/pagos/movimientos/nadie@x.com").json()
    assert r["movimientos"] == []


def test_destacados_lista_duenos_con_saldo_y_nivel():
    # Tres dueños con distinto saldo → distintos niveles; uno con 0 no aparece.
    client.post("/pagos/recarga", json={
        "token": "t1", "dueno_id": "base@x.com", "email": "base@x.com",
        "monto_soles": 20,   # nivel 1
    })
    client.post("/pagos/recarga", json={
        "token": "t2", "dueno_id": "medio@x.com", "email": "medio@x.com",
        "monto_soles": 80,   # nivel 2
    })
    client.post("/pagos/recarga", json={
        "token": "t3", "dueno_id": "premium@x.com", "email": "premium@x.com",
        "monto_soles": 300,  # nivel 3
    })
    r = client.get("/pagos/destacados").json()
    porDueno = {d["dueno_id"]: d["nivel"] for d in r["destacados"]}
    assert porDueno == {
        "base@x.com": 1,
        "medio@x.com": 2,
        "premium@x.com": 3,
    }
    # No se expone el saldo exacto, solo el nivel.
    assert all("saldo_soles" not in d and "saldo_centimos" not in d
               for d in r["destacados"])


def test_destacados_vacio_sin_saldos():
    assert client.get("/pagos/destacados").json()["destacados"] == []


def test_vistas_registra_y_consulta():
    # Registrar 3 impresiones para un dueño y 1 para otro.
    client.post("/pagos/vistas/registrar",
                json={"ids": ["due@x.com", "due@x.com", "otro@x.com"]})
    client.post("/pagos/vistas/registrar", json={"ids": ["due@x.com"]})
    r = client.post("/pagos/vistas/consultar",
                    json={"ids": ["due@x.com"]}).json()
    assert r["ok"] is True
    assert r["total"] == 3  # 2 + 1
    assert r["semana"] == 3  # todas hoy → entran en los últimos 7 días
    # Consulta agregada de varios ids (p. ej. las canchas de un dueño).
    r2 = client.post("/pagos/vistas/consultar",
                     json={"ids": ["due@x.com", "otro@x.com"]}).json()
    assert r2["total"] == 4


def test_vistas_semana_excluye_dias_viejos():
    from db.store import stores as _st
    # Una impresión de hace 30 días (fuera de la ventana) + una de hoy.
    _st.registrar_vista("club@x.com", dia="2020-01-01")
    _st.registrar_vista("club@x.com")
    r = client.post("/pagos/vistas/consultar",
                    json={"ids": ["club@x.com"]}).json()
    assert r["total"] == 2
    assert r["semana"] == 1  # solo la de hoy


def test_vistas_vacio():
    r = client.post("/pagos/vistas/consultar", json={"ids": ["nadie"]}).json()
    assert r["total"] == 0 and r["semana"] == 0


def test_saldo_endpoint():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 15})
    r = client.get("/pagos/saldo/d").json()
    assert r["saldo_centimos"] == 1500 and r["saldo_soles"] == 15.0


def test_webhook_es_idempotente(_setup):
    # Cargo directo en Culqi (como si el APK hubiera cobrado) sin pasar por el
    # endpoint, para que el webhook sea quien acredite.
    culqi.crear_cargo(token="t", monto_centimos=5000, email="d@x.com",
                      descripcion="x",
                      metadata={"tipo": "recarga", "dueno_id": "d"})
    cid = list(_setup.cargos.keys())[0]
    ev = {"data": {"id": cid}}
    r1 = client.post("/pagos/webhook", json=ev).json()
    assert r1["ok"] is True
    assert stores.saldo_centimos("d") == 5000
    # Segundo golpe del mismo cargo: no duplica.
    r2 = client.post("/pagos/webhook", json=ev).json()
    assert r2.get("duplicado") is True
    assert stores.saldo_centimos("d") == 5000


def test_webhook_token_invalido(monkeypatch):
    monkeypatch.setattr(config, "CULQI_WEBHOOK_TOKEN", "secreto")
    resp = client.post("/pagos/webhook?t=malo", json={"data": {"id": "x"}})
    assert resp.status_code == 401


def test_comision_calculo():
    from pagos.router import comision_centimos
    assert comision_centimos(60) == 300     # 5% de 60 = 3.00
    assert comision_centimos(20) == 200      # 5% de 20 = 1.00 → mínimo 2.00


def test_cobrar_generico():
    r = client.post("/pagos/cobrar", json={
        "token": "tkn_1", "email": "j@x.com", "monto_soles": 60,
        "concepto": "Reserva cancha", "tipo": "reserva"}).json()
    assert r["ok"] is True
    assert r["charge_id"].startswith("chr_")
    assert any(p.tipo == "reserva" for p in stores.pagos)


def test_guardar_metodo_de_pago():
    r = client.post("/pagos/metodos", json={
        "token": "tkn_1", "user_id": "juan@x.com", "email": "juan@x.com",
        "nombre": "Juan", "apellido": "Perez"}).json()
    assert r["ok"] is True
    assert r["metodo"]["ultimos4"] == "1111"
    assert r["metodo"]["marca"] == "Visa"
    assert r["metodo"]["id"].startswith("crd_")
    # Reusa el mismo customer en la 2da tarjeta.
    client.post("/pagos/metodos", json={
        "token": "tkn_2", "user_id": "juan@x.com", "email": "juan@x.com"})
    lst = client.get("/pagos/metodos/juan@x.com").json()["metodos"]
    assert len(lst) == 2
    assert len(stores.customers) == 1  # un solo customer


def test_eliminar_metodo_de_pago():
    client.post("/pagos/metodos", json={
        "token": "t", "user_id": "ana@x.com", "email": "ana@x.com"})
    cid = client.get("/pagos/metodos/ana@x.com").json()["metodos"][0]["id"]
    client.delete("/pagos/metodos/ana@x.com/$cid".replace("$cid", cid))
    lst = client.get("/pagos/metodos/ana@x.com").json()["metodos"]
    assert lst == []
