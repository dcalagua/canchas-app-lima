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

# Header del operador (torre de control) para endpoints admin de liquidaciones.
# Va por defecto en el cliente; los endpoints app-key simplemente lo ignoran.
_ADM = {"X-Admin-Token": "adm_test"}
client = TestClient(app, headers=_ADM)


class _FakeCulqi:
    """Simula la API de Culqi en memoria: crea cargos y los devuelve al
    consultarlos (para el webhook)."""

    def __init__(self):
        self.cargos = {}
        self.n = 0
        self.forzar_error = False
        self.ultimo_customer = None  # último body enviado a /customers

    def request(self, metodo, path, body=None):
        if self.forzar_error:
            return {"ok": False, "status": 402, "error": "Tarjeta rechazada"}
        if metodo == "POST" and path == "/customers":
            self.n += 1
            self.ultimo_customer = body
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
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm_test")  # operador
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


def test_consolidar_mueve_saldo_de_academia_a_correo():
    # El dueño recargó S/ 170 en su billetera (correo) y S/ 71 quedaron bajo la
    # llave de la academia. Consolidar los junta en el correo → S/ 241.
    client.post("/pagos/recarga", json={
        "token": "t1", "dueno_id": "due@x.com", "email": "due@x.com",
        "monto_soles": 170})
    client.post("/pagos/recarga", json={
        "token": "t2", "dueno_id": "aca_1", "email": "due@x.com",
        "monto_soles": 71})
    r = client.post("/pagos/consolidar", json={
        "desde_id": "aca_1", "hacia_id": "due@x.com"}).json()
    assert r["ok"] is True
    assert r["saldo_centimos"] == 24100 and r["saldo_soles"] == 241.0
    assert stores.saldo_centimos("due@x.com") == 24100
    assert stores.saldo_centimos("aca_1") == 0  # la academia queda en 0


def test_consolidar_es_idempotente():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "aca_1", "email": "d@x.com",
        "monto_soles": 50})
    body = {"desde_id": "aca_1", "hacia_id": "d@x.com"}
    client.post("/pagos/consolidar", json=body)
    r2 = client.post("/pagos/consolidar", json=body).json()  # segundo golpe
    assert r2["saldo_centimos"] == 5000  # no duplica
    assert stores.saldo_centimos("d@x.com") == 5000


def test_consolidar_misma_llave_no_hace_nada():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d@x.com", "email": "d@x.com",
        "monto_soles": 30})
    r = client.post("/pagos/consolidar", json={
        "desde_id": "d@x.com", "hacia_id": "d@x.com"}).json()
    assert r["saldo_centimos"] == 3000
    assert stores.saldo_centimos("d@x.com") == 3000


def test_consolidar_no_altera_libro_de_recargas():
    # Consolidar mueve saldo pero NO crea/borra recargas: el reporte de márgenes
    # (que suma recargas) no debe cambiar.
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "aca_1", "email": "d@x.com",
        "monto_soles": 40})
    recargas_antes = sum(1 for p in stores.pagos if p.tipo == "recarga")
    client.post("/pagos/consolidar", json={
        "desde_id": "aca_1", "hacia_id": "d@x.com"})
    recargas_despues = sum(1 for p in stores.pagos if p.tipo == "recarga")
    assert recargas_antes == recargas_despues


def test_consolidar_reapunta_suscripciones_al_correo():
    # Suscripción que cobraba de la academia; tras consolidar debe cobrar del
    # correo del dueño (para que el cron de servicios no falle por falta_saldo).
    stores.suscripciones["aca_1:landing"] = {
        "academia_id": "aca_1", "dueno_id": "aca_1", "servicio": "landing",
        "estado": "activa"}
    client.post("/pagos/consolidar", json={
        "desde_id": "aca_1", "hacia_id": "d@x.com"})
    assert stores.suscripciones["aca_1:landing"]["dueno_id"] == "d@x.com"


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


def test_comision_reserva_descuenta_saldo_del_dueno():
    # El dueño recarga; una reserva en efectivo descuenta su comisión (5% mín 2).
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "due@x.com", "email": "due@x.com",
        "monto_soles": 30})
    r = client.post("/pagos/comision-reserva", json={
        "dueno_id": "due@x.com", "monto_soles": 60, "reserva_id": "jug_1",
        "concepto": "Comisión · Joga Bonito"}).json()
    assert r["ok"] is True and r["duplicada"] is False
    assert r["comision_centimos"] == 300           # 5% de 60
    assert r["saldo_centimos"] == 2700             # 3000 - 300
    assert stores.saldo_centimos("due@x.com") == 2700


def test_comision_reserva_es_idempotente_por_reserva():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 30})
    body = {"dueno_id": "d", "monto_soles": 60, "reserva_id": "jug_9"}
    r1 = client.post("/pagos/comision-reserva", json=body).json()
    r2 = client.post("/pagos/comision-reserva", json=body).json()
    assert r1["duplicada"] is False and r2["duplicada"] is True
    # Solo se cobró UNA vez: saldo 3000 - 300 = 2700 (no 2400).
    assert stores.saldo_centimos("d") == 2700


def test_comision_reserva_nunca_deja_saldo_negativo():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 1})
    r = client.post("/pagos/comision-reserva", json={
        "dueno_id": "d", "monto_soles": 200, "reserva_id": "jug_x"}).json()
    assert r["ok"] is True
    assert r["saldo_centimos"] == 0                 # clamp en 0, no negativo


def test_comision_aparece_en_movimientos_como_egreso():
    client.post("/pagos/recarga", json={
        "token": "t", "dueno_id": "d", "email": "d@x.com", "monto_soles": 30})
    client.post("/pagos/comision-reserva", json={
        "dueno_id": "d", "monto_soles": 60, "reserva_id": "jug_2"})
    movs = client.get("/pagos/movimientos/d").json()["movimientos"]
    tipos = {m["tipo"] for m in movs}
    assert "comision_reserva" in tipos and "recarga" in tipos
    com = next(m for m in movs if m["tipo"] == "comision_reserva")
    assert com["monto_soles"] == -3.0             # egreso en negativo


def test_liquidacion_online_no_toca_saldo_y_desglosa():
    # Dueño SIN saldo: reserva online → registra bruto/comisión/neto, sin tocar
    # el saldo prepago.
    r = client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "jug_5",
        "concepto": "Reserva online · Fútbol 1"}).json()
    assert r["ok"] is True and r["duplicada"] is False
    assert r["bruto_centimos"] == 12000
    assert r["comision_centimos"] == 600          # 5% de 120
    assert r["neto_centimos"] == 11400            # 120 - 6
    assert stores.saldo_centimos("due@x.com") == 0  # NO toca el saldo


def test_liquidacion_online_idempotente():
    body = {"dueno_id": "d", "monto_soles": 120, "reserva_id": "jug_7"}
    client.post("/pagos/liquidacion-online", json=body)
    client.post("/pagos/liquidacion-online", json=body)
    # Solo una fila de liquidación para esa reserva.
    n = sum(1 for p in stores.pagos
            if p.tipo == "liquidacion_online" and p.culqi_charge_id == "jug_7")
    assert n == 1


def test_liquidacion_aparece_en_movimientos_con_neto():
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "d", "monto_soles": 120, "reserva_id": "jug_8",
        "concepto": "Reserva online · Fútbol 1"})
    movs = client.get("/pagos/movimientos/d").json()["movimientos"]
    liq = next(m for m in movs if m["tipo"] == "liquidacion_online")
    assert liq["bruto_soles"] == 120.0
    assert liq["comision_soles"] == 6.0
    assert liq["neto_soles"] == 114.0
    assert liq["monto_soles"] == 114.0            # el neto es lo que verá "+"


def test_liquidacion_pendiente_y_marcar_pagada():
    # Registrar 2 liquidaciones (una de otro dueño) → pendientes las lista.
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "due@x.com", "monto_soles": 120, "reserva_id": "jug_a"})
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "otro@x.com", "monto_soles": 80, "reserva_id": "jug_b"})
    pend = client.get("/pagos/liquidaciones/pendientes").json()
    assert len(pend["pendientes"]) == 2
    assert pend["total_neto_soles"] == 114.0 + 76.0   # (120-6)+(80-4)

    # Marcar una como pagada.
    r = client.post("/pagos/liquidaciones/jug_a/pagar",
                    json={"metodo": "yape", "referencia": "OP123"}).json()
    assert r["ok"] is True and r["liquidado"] is True
    assert r["metodo_liquidacion"] == "yape"

    # Ahora solo queda una pendiente.
    pend2 = client.get("/pagos/liquidaciones/pendientes").json()
    assert len(pend2["pendientes"]) == 1
    assert pend2["pendientes"][0]["reserva_id"] == "jug_b"


def test_marcar_liquidacion_es_idempotente():
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "d", "monto_soles": 120, "reserva_id": "jug_c"})
    client.post("/pagos/liquidaciones/jug_c/pagar",
                json={"metodo": "yape", "referencia": "OP1"})
    # Segundo marcado: no cambia el método original ni rompe.
    r = client.post("/pagos/liquidaciones/jug_c/pagar",
                    json={"metodo": "transferencia", "referencia": "OP2"}).json()
    assert r["liquidado"] is True
    assert r["metodo_liquidacion"] == "yape"   # conserva el primer pago


def test_marcar_liquidacion_inexistente_404():
    resp = client.post("/pagos/liquidaciones/nope/pagar", json={})
    assert resp.status_code == 404


def test_por_recibir_del_dueno():
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "d", "monto_soles": 120, "reserva_id": "jug_d"})
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "d", "monto_soles": 100, "reserva_id": "jug_e"})
    r = client.get("/pagos/por-recibir/d").json()
    assert r["por_recibir_soles"] == 114.0 + 95.0   # (120-6)+(100-5)
    assert r["reservas"] == 2
    # Tras pagar una, baja el por-recibir.
    client.post("/pagos/liquidaciones/jug_d/pagar", json={"metodo": "yape"})
    r2 = client.get("/pagos/por-recibir/d").json()
    assert r2["por_recibir_soles"] == 95.0 and r2["reservas"] == 1


def test_movimientos_liquidacion_incluye_estado():
    client.post("/pagos/liquidacion-online", json={
        "dueno_id": "d", "monto_soles": 120, "reserva_id": "jug_f"})
    movs = client.get("/pagos/movimientos/d").json()["movimientos"]
    liq = next(m for m in movs if m["tipo"] == "liquidacion_online")
    assert liq["liquidado"] is False
    client.post("/pagos/liquidaciones/jug_f/pagar", json={"metodo": "yape"})
    movs2 = client.get("/pagos/movimientos/d").json()["movimientos"]
    liq2 = next(m for m in movs2 if m["tipo"] == "liquidacion_online")
    assert liq2["liquidado"] is True


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


def test_customer_cumple_minimos_de_culqi(_setup):
    # Culqi valida largos mínimos (address ≥5, nombre/apellido ≥2, phone ≥5). El
    # cliente que enviamos debe cumplirlos aunque el APK mande datos cortos/vacíos.
    client.post("/pagos/metodos", json={
        "token": "t", "user_id": "d@x.com", "email": "d@x.com",
        "nombre": "D", "apellido": ""})  # nombre corto + apellido vacío
    b = _setup.ultimo_customer
    assert b is not None
    assert len(b["address"]) >= 5           # antes "Lima" (4) → parameter_error
    assert len(b["first_name"]) >= 2        # "D" → cae al fallback
    assert len(b["last_name"]) >= 2
    assert len(b["phone_number"]) >= 5
    assert len(b["email"]) <= 50


def test_eliminar_metodo_de_pago():
    client.post("/pagos/metodos", json={
        "token": "t", "user_id": "ana@x.com", "email": "ana@x.com"})
    cid = client.get("/pagos/metodos/ana@x.com").json()["metodos"][0]["id"]
    client.delete("/pagos/metodos/ana@x.com/$cid".replace("$cid", cid))
    lst = client.get("/pagos/metodos/ana@x.com").json()["metodos"]
    assert lst == []
