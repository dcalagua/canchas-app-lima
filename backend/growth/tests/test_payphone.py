"""Pasarela de Ecuador (PayPhone): preparar → pagar → CONFIRMAR.
Se mockean las llamadas HTTP a PayPhone (preparar/confirmar) para probar todo
el flujo del backend sin red ni token real. Lo que se verifica de verdad:
  · sin token el módulo se declara no configurado (fail-safe);
  · un GET al retorno con datos falsos NO aprueba nada (Confirm es la verdad);
  · el estado reconcilia si el APK trae el transaction_id;
  · la recarga acredita saldo UNA sola vez; un monto que no cuadra no aprueba;
  · el pago sobrevive al snapshot.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores, Stores  # noqa: E402
from main import app  # noqa: E402
from pagos import payphone  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "APP_API_KEY", "")  # endpoints públicos en tests
    monkeypatch.setattr(config, "PAYPHONE_TOKEN", "test-token")
    monkeypatch.setattr(config, "PAYPHONE_STORE_ID", "store-1")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://pg.example.com")
    stores.payphone_pagos.clear()
    yield
    stores.payphone_pagos.clear()


def _preparar_ok(**kw):
    assert kw["response_url"] == "https://pg.example.com/pagos/ec/retorno"
    assert kw["cancel_url"] == "https://pg.example.com/pagos/ec/cancelado"
    assert kw["monto_usd"] > 0
    return {"ok": True, "payment_id": 777,
            "url_tarjeta": "https://pay.payphone/card/x",
            "url_payphone": "https://pay.payphone/app/x"}


def test_no_configurado(monkeypatch):
    monkeypatch.setattr(config, "PAYPHONE_TOKEN", "")
    r = client.get("/pagos/ec/config")
    assert r.json() == {"disponible": False, "moneda": "USD"}
    r = client.post("/pagos/ec/pago", json={"email": "a@b.com", "monto_usd": 5})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"] == "no_configurado"


def test_flujo_pago(monkeypatch):
    confirmaciones: list[dict] = []
    aprobar = {"si": False}

    def fake_confirmar(**kw):
        confirmaciones.append(kw)
        if kw["transaction_id"] == "NOPE":
            return {"ok": True, "aprobado": False, "estado": "Canceled"}
        return {"ok": True, "aprobado": aprobar["si"],
                "estado": "Approved" if aprobar["si"] else "Canceled",
                "transaction_id": kw["transaction_id"],
                "autorizacion": "AUTH1", "monto_centavos": 1250}

    monkeypatch.setattr(payphone, "preparar", _preparar_ok)
    monkeypatch.setattr(payphone, "confirmar", fake_confirmar)

    # 1) Preparar (el correo se normaliza; la URL principal es la de tarjeta).
    r = client.post("/pagos/ec/pago", json={
        "email": "Cli@B.com", "monto_usd": 12.5,
        "concepto": "Reserva", "tipo": "reserva"})
    j = r.json()
    assert j["ok"] and j["url_pasarela"] == "https://pay.payphone/card/x"
    assert j["url_payphone"] == "https://pay.payphone/app/x"
    ident = j["identificador"]
    assert stores.payphone_pagos[ident]["pagado"] is False
    assert stores.payphone_pagos[ident]["email"] == "cli@b.com"

    # 2) Estado: pendiente, y SIN transaction_id no llama a Confirm.
    assert client.get(f"/pagos/ec/pago/{ident}").json()["pagado"] is False
    assert confirmaciones == []

    # 3) Retorno con identificador desconocido → no encontrado, nada cambia.
    r = client.get("/pagos/ec/retorno",
                   params={"id": "1", "clientTransactionId": "zzz"})
    assert "no encontrado" in r.text.lower()

    # 4) Retorno real pero PayPhone NO aprueba → sigue sin pagar.
    r = client.get("/pagos/ec/retorno",
                   params={"id": "NOPE", "clientTransactionId": ident})
    assert "no aprobado" in r.text.lower()
    assert stores.payphone_pagos[ident]["pagado"] is False

    # 5) PayPhone aprueba → el retorno confirma y marca pagado.
    aprobar["si"] = True
    r = client.get("/pagos/ec/retorno",
                   params={"id": "555", "clientTransactionId": ident})
    assert "recibido" in r.text.lower()
    d = stores.payphone_pagos[ident]
    assert d["pagado"] is True and d["transaction_id"] == "555"
    assert d["autorizacion"] == "AUTH1"

    # 6) El estado refleja pagado y ya NO vuelve a confirmar (idempotente).
    n = len(confirmaciones)
    assert client.get(f"/pagos/ec/pago/{ident}").json()["pagado"] is True
    assert len(confirmaciones) == n


def test_pagina_puente_navega_a_payphone(monkeypatch):
    """El APK abre /ec/ir/{id} (nuestro dominio) y esa página navega a la URL
    hospedada de PayPhone; así la pasarela recibe un origen autorizado."""
    monkeypatch.setattr(payphone, "preparar", _preparar_ok)
    j = client.post("/pagos/ec/pago", json={"email": "a@b.com", "monto_usd": 5}).json()
    assert j["url_lanzador"] == f"https://pg.example.com/pagos/ec/ir/{j['identificador']}"
    r = client.get(f"/pagos/ec/ir/{j['identificador']}")
    assert r.status_code == 200
    assert "https://pay.payphone/card/x" in r.text
    assert "window.location.href" in r.text
    assert r.headers["cache-control"] == "no-store"
    # medio=payphone → la URL del saldo PayPhone.
    r2 = client.get(f"/pagos/ec/ir/{j['identificador']}", params={"medio": "payphone"})
    assert "https://pay.payphone/app/x" in r2.text
    # Id desconocido o pago ya pagado → no redirige a nada.
    assert "no disponible" in client.get("/pagos/ec/ir/zzz").text.lower()
    stores.payphone_pagos[j["identificador"]]["pagado"] = True
    assert "no disponible" in client.get(f"/pagos/ec/ir/{j['identificador']}").text.lower()


def test_estado_confirma_con_transaction_id(monkeypatch):
    """Si el retorno nunca llegó al backend, el APK manda el transaction_id que
    vio en la URL y el estado confirma ahí mismo (antes de los 5 minutos)."""
    monkeypatch.setattr(payphone, "preparar", _preparar_ok)
    monkeypatch.setattr(payphone, "confirmar", lambda **kw: {
        "ok": True, "aprobado": True, "estado": "Approved",
        "transaction_id": kw["transaction_id"], "monto_centavos": 1000})
    ident = client.post("/pagos/ec/pago", json={
        "email": "a@b.com", "monto_usd": 10}).json()["identificador"]
    j = client.get(f"/pagos/ec/pago/{ident}",
                   params={"transaction_id": "9001"}).json()
    assert j["pagado"] is True
    assert stores.payphone_pagos[ident]["transaction_id"] == "9001"


def test_monto_que_no_cuadra_no_aprueba(monkeypatch):
    """Defensa: PayPhone dice Approved pero por OTRO monto → no se da por pagado."""
    monkeypatch.setattr(payphone, "preparar", _preparar_ok)
    monkeypatch.setattr(payphone, "confirmar", lambda **kw: {
        "ok": True, "aprobado": True, "estado": "Approved",
        "transaction_id": "1", "monto_centavos": 100})  # $1 en vez de $10
    ident = client.post("/pagos/ec/pago", json={
        "email": "a@b.com", "monto_usd": 10}).json()["identificador"]
    j = client.get(f"/pagos/ec/pago/{ident}", params={"transaction_id": "1"}).json()
    assert j["pagado"] is False
    assert j["estado"] == "monto_no_cuadra"


def test_recarga_acredita_saldo_una_vez(monkeypatch):
    monkeypatch.setattr(payphone, "preparar", _preparar_ok)
    monkeypatch.setattr(payphone, "confirmar", lambda **kw: {
        "ok": True, "aprobado": True, "estado": "Approved",
        "transaction_id": "42", "monto_centavos": 2000})
    stores.saldos.clear()
    ident = client.post("/pagos/ec/pago", json={
        "email": "duo@b.com", "monto_usd": 20, "tipo": "recarga",
        "dueno_id": "Duo@B.com"}).json()["identificador"]
    client.get("/pagos/ec/retorno", params={"id": "42", "clientTransactionId": ident})
    assert stores.saldo_centimos("duo@b.com") == 2000
    # Reconfirmar por cualquier vía no duplica.
    client.get("/pagos/ec/retorno", params={"id": "42", "clientTransactionId": ident})
    client.get(f"/pagos/ec/pago/{ident}", params={"transaction_id": "42"})
    assert stores.saldo_centimos("duo@b.com") == 2000


def test_cancelado_marca_estado(monkeypatch):
    monkeypatch.setattr(payphone, "preparar", _preparar_ok)
    ident = client.post("/pagos/ec/pago", json={
        "email": "a@b.com", "monto_usd": 3}).json()["identificador"]
    r = client.get("/pagos/ec/cancelado", params={"clientTransactionId": ident})
    assert "cancelado" in r.text.lower()
    assert stores.payphone_pagos[ident]["estado"] == "cancelado"
    assert stores.payphone_pagos[ident]["pagado"] is False


def test_adaptador_parsea_respuestas(monkeypatch):
    """El adaptador traduce las respuestas crudas de PayPhone sin red."""
    llamadas: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        llamadas.append((path, payload))
        if path == payphone.PREPARE_PATH:
            return {"paymentId": 1, "payWithCard": "c", "payWithPayPhone": "p"}
        return {"transactionStatus": "Approved", "statusCode": 3,
                "transactionId": 99, "authorizationCode": "A1",
                "amount": 1500, "cardBrand": "Visa", "lastDigits": "4242"}

    monkeypatch.setattr(payphone, "_post", fake_post)
    r = payphone.preparar(client_tx_id="abc", monto_usd=15, concepto="Reserva",
                          response_url="r", cancel_url="c", email="a@b.com")
    assert r == {"ok": True, "payment_id": 1, "url_tarjeta": "c", "url_payphone": "p"}
    payload = llamadas[0][1]
    assert payload["amount"] == 1500 and payload["amountWithoutTax"] == 1500
    assert payload["tax"] == 0 and payload["currency"] == "USD"
    assert payload["storeId"] == "store-1" and payload["clientTransactionId"] == "abc"
    assert "phoneNumber" not in payload  # opcional vacío: no se manda

    c = payphone.confirmar(transaction_id="99", client_tx_id="abc")
    assert c["ok"] and c["aprobado"] and c["estado"] == "Approved"
    assert c["autorizacion"] == "A1" and c["monto_centavos"] == 1500
    assert llamadas[1][1] == {"id": 99, "clientTxId": "abc"}


def test_snapshot_roundtrip():
    stores.payphone_pagos["abc"] = {
        "identificador": "abc", "payment_id": 1, "transaction_id": "9",
        "email": "x@y.com", "monto_usd": 10.0, "concepto": "c", "tipo": "reserva",
        "ref": "", "dueno_id": "", "pagado": True, "estado": "Approved",
        "autorizacion": "A", "fecha_pago": "2026-01-01", "creado_en": "2026-01-01"}
    state = stores.to_state()
    s2 = Stores()
    s2.load_state(state)
    assert s2.payphone_pagos["abc"]["pagado"] is True
    assert s2.payphone_pagos["abc"]["monto_usd"] == 10.0


def test_retorno_por_get_persiste_al_instante(monkeypatch):
    """El retorno de PayPhone llega por GET y el middleware solo persiste en
    POST/PUT/DELETE: el saldo acreditado debe guardarse AHÍ MISMO o se pierde
    en el siguiente redeploy (pasó con la primera recarga real, 5-sep-2026)."""
    from db import pg
    guardados: list[str] = []
    monkeypatch.setattr(pg, "habilitado", True)
    monkeypatch.setattr(pg, "guardar", lambda state: guardados.append("snap"))
    monkeypatch.setattr(pg, "guardar_normalizado", lambda st: guardados.append("norm"))
    monkeypatch.setattr(payphone, "preparar", _preparar_ok)
    monkeypatch.setattr(payphone, "confirmar", lambda **kw: {
        "ok": True, "aprobado": True, "estado": "Approved",
        "transaction_id": "77", "monto_centavos": 100})
    ident = client.post("/pagos/ec/pago", json={
        "email": "g@b.com", "monto_usd": 1, "tipo": "recarga",
        "dueno_id": "g@b.com"}).json()["identificador"]
    guardados.clear()  # el POST ya persistió por middleware; lo que importa es el GET
    client.get("/pagos/ec/retorno", params={"id": "77", "clientTransactionId": ident})
    assert "snap" in guardados and "norm" in guardados
    assert stores.saldo_centimos("g@b.com") == 100
    # Cancelar por GET también deja rastro persistido.
    ident2 = client.post("/pagos/ec/pago", json={"email": "g@b.com", "monto_usd": 2}).json()["identificador"]
    guardados.clear()
    client.get("/pagos/ec/cancelado", params={"clientTransactionId": ident2})
    assert "snap" in guardados
