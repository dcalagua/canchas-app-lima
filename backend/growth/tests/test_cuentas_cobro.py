"""CUENTA DE COBRO del dueño + LIQUIDACIÓN POR LOTE con archivo Telecrédito
BCP (pedido del director, 26-sep-2026, tras el primer cobro live: "¿puedo
transferir desde la torre o automático?"). Culqi no dispersa: la torre agrupa
lo pendiente por dueño, genera la planilla del BCP y marca todo pagado."""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import cuentas_cobro as cc  # noqa: E402

client = TestClient(app, headers={"X-Admin-Token": "adm_test"})


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm_test")
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "0")
    stores.pagos = []
    stores.cuentas_cobro = {}
    stores.lotes_liquidacion = []
    stores.config.pop("liq_bcp_cuenta", None)
    stores.config.pop("liq_bcp_tipo", None)
    yield


def _liq(dueno, soles, rid, moneda="PEN"):
    r = client.post("/pagos/liquidacion-online", json={"dueno_id": dueno, "monto_soles": soles, "reserva_id": rid,
                                                       "concepto": f"Local {dueno} · Cancha 1 · Juan · lun 10:00", "moneda": moneda}).json()
    assert r["ok"]


def test_validacion_de_cuenta_de_cobro_por_pais():
    """Todo por selección (tipo, banco, documento); solo números y titular libres."""
    base = {"pais": "PE", "titular": "Juan Pérez Quispe", "doc_tipo": "DNI", "doc_numero": "12345678"}
    # Yape: celular de 9 dígitos que empieza en 9.
    c, err, campo = cc.validar({**base, "tipo": "yape", "numero": "987 654 321"})
    assert err == "" and c["numero"] == "987654321" and c["moneda"] == "PEN" and c["banco"] == ""
    assert cc.validar({**base, "tipo": "yape", "numero": "12345"})[2] == "numero"
    # Banco distinto de BCP exige CCI de 20 dígitos.
    c, err, campo = cc.validar({**base, "tipo": "banco", "banco": "INTERBANK", "tipo_cuenta": "ahorros", "numero": "8983123456789"})
    assert campo == "cci", err
    c, err, campo = cc.validar({**base, "tipo": "banco", "banco": "INTERBANK", "tipo_cuenta": "ahorros", "numero": "8983123456789",
                                "cci": "003-898-013123456789-45"})
    assert err == "" and c["cci"] == "00389801312345678945" and c["banco_nombre"] == "Interbank"
    # Cuenta BCP: 13/14 dígitos, sin CCI obligatorio.
    c, err, campo = cc.validar({**base, "tipo": "banco", "banco": "BCP", "tipo_cuenta": "corriente", "numero": "19112345678012"})
    assert err == "" and c["cci"] == "" and c["tipo_cuenta"] == "corriente"
    assert cc.validar({**base, "tipo": "banco", "banco": "BCP", "numero": "123"})[2] == "numero"
    # Documento con largo por tipo y por país; titular obligatorio.
    assert cc.validar({**base, "tipo": "yape", "numero": "987654321", "doc_numero": "1234"})[2] == "doc_numero"
    assert cc.validar({**base, "tipo": "yape", "numero": "987654321", "titular": "J"})[2] == "titular"
    # Bolivia y Ecuador: solo banco, sin CCI, moneda del país.
    c, err, _ = cc.validar({"pais": "BO", "tipo": "banco", "banco": "UNION", "numero": "1000123456", "titular": "María López",
                            "doc_tipo": "CI", "doc_numero": "7654321"})
    assert err == "" and c["moneda"] == "BOB" and cc.resumen(c)["canal"] == "manual"
    assert cc.validar({"pais": "EC", "tipo": "yape", "numero": "987654321", "titular": "X Y", "doc_tipo": "CEDULA", "doc_numero": "0102030405"})[2] == "tipo"
    c, err, _ = cc.validar({"pais": "EC", "tipo": "banco", "banco": "PICHINCHA_EC", "tipo_cuenta": "ahorros", "numero": "2200123456",
                            "titular": "Ana Ruiz", "doc_tipo": "CEDULA", "doc_numero": "0102030405"})
    assert err == "" and c["moneda"] == "USD"
    # Catálogo público para el formulario.
    cat = client.get("/pagos/cuenta-cobro/catalogo").json()["paises"]
    assert cat["PE"]["cci"] is True and cat["BO"]["cci"] is False and {b["codigo"] for b in cat["PE"]["bancos"]} >= {"BCP", "INTERBANK", "BBVA"}


def test_guardar_y_leer_cuenta_de_cobro_del_usuario(monkeypatch):
    r = client.post("/pagos/cuenta-cobro", json={"email": "Due@X.com", "pais": "PE", "tipo": "banco", "banco": "BBVA", "tipo_cuenta": "ahorros",
                                                 "numero": "001112345678901234", "cci": "01111200012345678901", "titular": "Dueño Uno",
                                                 "doc_tipo": "DNI", "doc_numero": "45678912"}).json()
    assert r["ok"] and r["resumen"]["canal"] == "archivo" and "CCI 01111200012345678901" in r["resumen"]["etiqueta"]
    g = client.get("/pagos/cuenta-cobro/due@x.com").json()
    assert g["cuenta"]["banco"] == "BBVA" and g["cuenta"]["email"] == "due@x.com" and g["resumen"]["tiene"]
    # Error de validación → ok False con el campo, sin pisar la guardada.
    r = client.post("/pagos/cuenta-cobro", json={"email": "due@x.com", "pais": "PE", "tipo": "yape", "numero": "12", "titular": "Dueño Uno",
                                                 "doc_tipo": "DNI", "doc_numero": "45678912"}).json()
    assert r["ok"] is False and r["campo"] == "numero" and stores.cuenta_cobro("due@x.com")["banco"] == "BBVA"
    # Con auth por usuario, otro correo no la ve ni la cambia.
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "1")
    import pagos.router as pr
    monkeypatch.setattr(pr, "_email_de_token", lambda t: "otro@x.com" if t == "tok_otro" else None)
    assert client.get("/pagos/cuenta-cobro/due@x.com", headers={"X-User-Token": "tok_otro"}).status_code == 403
    assert client.post("/pagos/cuenta-cobro", json={"email": "due@x.com", "pais": "PE", "tipo": "yape", "numero": "987654321", "titular": "Otro",
                                                    "doc_tipo": "DNI", "doc_numero": "11111111"}, headers={"X-User-Token": "tok_otro"}).status_code == 403
    assert client.delete("/pagos/cuenta-cobro/due@x.com", headers={"X-User-Token": "tok_otro"}).status_code == 403
    assert stores.cuenta_cobro("due@x.com")["banco"] == "BBVA"


def test_pendientes_muestran_la_cuenta_y_el_lote_agrupa_por_dueno_con_umbral():
    # 3 dueños: uno con cuenta Interbank (archivo), uno con Yape (manual), uno sin cuenta.
    _liq("inter@x.com", 100, "r1"); _liq("inter@x.com", 60, "r2"); _liq("inter@x.com", 15, "r3")
    _liq("yape@x.com", 15, "r4")
    _liq("nadie@x.com", 200, "r5")
    _liq("usd@x.com", 50, "r6", moneda="USD")  # otra moneda: fuera del lote en soles
    client.post("/pagos/cuenta-cobro", json={"email": "inter@x.com", "pais": "PE", "tipo": "banco", "banco": "INTERBANK", "tipo_cuenta": "ahorros",
                                             "numero": "8983123456789", "cci": "00389801312345678945", "titular": "Inter Dueño", "doc_tipo": "DNI", "doc_numero": "12345678"})
    client.post("/pagos/cuenta-cobro", json={"email": "yape@x.com", "pais": "PE", "tipo": "yape", "numero": "987654321", "titular": "Yape Dueño",
                                             "doc_tipo": "DNI", "doc_numero": "87654321"})
    pend = client.get("/pagos/liquidaciones/pendientes").json()
    assert pend["cuentas"]["inter@x.com"]["canal"] == "archivo" and pend["cuentas"]["yape@x.com"]["canal"] == "manual"
    assert pend["cuentas"]["nadie@x.com"]["tiene"] is False and pend["bcp"]["cuenta"] == "" and pend["lotes"] == []
    assert all("moneda" in x for x in pend["pendientes"])
    # Lote en soles con umbral S/ 20: Interbank entra (166.25 neto), Yape queda bajo umbral (13), nadie sin cuenta.
    lote = client.post("/pagos/liquidaciones/lote/preparar", json={"moneda": "PEN", "umbral_soles": 20}).json()["lote"]
    por = {f["dueno"]: f for f in lote["filas"]}
    assert set(por) == {"inter@x.com", "yape@x.com", "nadie@x.com"}
    assert por["inter@x.com"]["canal"] == "archivo" and por["inter@x.com"]["n"] == 3 and por["inter@x.com"]["neto_centimos"] == 9500 + 5700 + 1300
    assert por["yape@x.com"]["canal"] == "bajo_umbral" and por["nadie@x.com"]["canal"] == "sin_cuenta"
    assert lote["n_archivo"] == 1 and lote["total_archivo_centimos"] == 16500 and lote["estado"] == "preparado"
    assert stores.lote(lote["id"])["id"] == lote["id"]
    # Sin umbral el Yape pasa a "manual".
    lote2 = client.post("/pagos/liquidaciones/lote/preparar", json={"moneda": "PEN", "umbral_soles": 0}).json()["lote"]
    assert {f["dueno"]: f["canal"] for f in lote2["filas"]}["yape@x.com"] == "manual"
    # Lote en dólares solo trae al de USD.
    lote3 = client.post("/pagos/liquidaciones/lote/preparar", json={"moneda": "USD"}).json()["lote"]
    assert [f["dueno"] for f in lote3["filas"]] == ["usd@x.com"]


def test_archivo_telecredito_bcp_ancho_fijo_y_marcar_lote_pagado():
    _liq("inter@x.com", 100, "r1"); _liq("inter@x.com", 60, "r2")
    _liq("bcp@x.com", 40, "r3")
    _liq("yape@x.com", 30, "r4")
    client.post("/pagos/cuenta-cobro", json={"email": "inter@x.com", "pais": "PE", "tipo": "banco", "banco": "INTERBANK", "tipo_cuenta": "ahorros",
                                             "numero": "8983123456789", "cci": "00389801312345678945", "titular": "José Ñañez", "doc_tipo": "DNI", "doc_numero": "12345678"})
    client.post("/pagos/cuenta-cobro", json={"email": "bcp@x.com", "pais": "PE", "tipo": "banco", "banco": "BCP", "tipo_cuenta": "corriente",
                                             "numero": "19112345678012", "titular": "Empresa Cancha SAC", "doc_tipo": "RUC", "doc_numero": "20123456789"})
    client.post("/pagos/cuenta-cobro", json={"email": "yape@x.com", "pais": "PE", "tipo": "yape", "numero": "987654321", "titular": "Yape Dueño",
                                             "doc_tipo": "DNI", "doc_numero": "87654321"})
    lote = client.post("/pagos/liquidaciones/lote/preparar", json={"moneda": "PEN"}).json()["lote"]
    # Sin cuenta de cargo configurada no se genera el archivo.
    assert client.get(f"/pagos/liquidaciones/lote/{lote['id']}/telecredito.txt").status_code == 409
    assert client.post("/pagos/liquidaciones/config-bcp", json={"cuenta": "123"}).status_code == 400
    assert client.post("/pagos/liquidaciones/config-bcp", json={"cuenta": "194-1234567-0-12", "tipo": "C"}).json()["cuenta"] == "1941234567012"
    r = client.get(f"/pagos/liquidaciones/lote/{lote['id']}/telecredito.txt")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    lineas = r.text.split("\r\n")
    assert lineas[-1] == "" and len(lineas) == 4  # cabecera + 2 abonos + final
    cab, d1, d2 = lineas[0], lineas[1], lineas[2]
    assert len(cab) == sum(l for _, l, _, _ in cc._CABECERA) == 112
    assert all(len(d) == sum(l for _, l, _, _ in cc._DETALLE) == 225 for d in (d1, d2))
    # Cabecera: tipo 1, 2 abonos, cuenta de cargo, importe total = 152 + 38 = 190.00.
    assert cab[0] == "1" and cab[1:7] == "000002" and cab[16:20] == "0001" and cab[20:40].strip() == "1941234567012"
    assert cab[40:57] == "00000000000019000"
    # Detalle Interbank: tipo B con CCI; sin tildes ni eñes; importe 152.00 (100+60 − 5 % ).
    assert d1[0] == "2" and d1[1] == "B" and d1[6:26].strip() == "00389801312345678945" and d1[26] == "1" and d1[27:39].strip() == "12345678"
    assert d1[39:114].strip() == "Jose Nanez" and d1[178:195] == "00000000000015200" and d1[195] == "S"
    # Detalle BCP: cuenta propia, corriente, RUC.
    assert d2[1] == "C" and d2[6:26].strip() == "19112345678012" and d2[26] == "6" and d2[178:195] == "00000000000003800"
    # El CSV lista también al de Yape (manual).
    csv = client.get(f"/pagos/liquidaciones/lote/{lote['id']}/detalle.csv").text
    assert "yape@x.com;manual" in csv and "inter@x.com;archivo" in csv and "S/ 152.00" in csv
    # Marcar el lote pagado: solo los del archivo; Yape sigue pendiente.
    r = client.post(f"/pagos/liquidaciones/lote/{lote['id']}/pagado", json={"referencia": "PLANILLA 778899"}).json()
    assert r["ok"] and r["marcadas"] == 3 and r["duenos"] == 2 and r["lote"]["estado"] == "pagado"
    pend = client.get("/pagos/liquidaciones/pendientes").json()
    assert [x["dueno_id"] for x in pend["pendientes"]] == ["yape@x.com"]
    pagada = next(p for p in stores.pagos if p.culqi_charge_id == "r1")
    assert pagada.liquidado and pagada.metodo_liquidacion == "transferencia" and pagada.referencia_liquidacion == "PLANILLA 778899"
    assert pend["lotes"][0]["id"] == lote["id"] and pend["lotes"][0]["estado"] == "pagado" and pend["lotes"][0]["total_archivo_soles"] == 190.0
    # Idempotente; con incluir_manuales también cierra el de Yape.
    r = client.post(f"/pagos/liquidaciones/lote/{lote['id']}/pagado", json={"referencia": "PLANILLA 778899", "incluir_manuales": True}).json()
    assert r["ok"] and r["marcadas"] == 4
    assert client.get("/pagos/liquidaciones/pendientes").json()["pendientes"] == []
    assert next(p for p in stores.pagos if p.culqi_charge_id == "r4").metodo_liquidacion == "yape"
    # Persistencia: la cuenta y el lote viajan en el snapshot.
    st = stores.to_state()
    assert st["cuentas_cobro"]["bcp@x.com"]["banco"] == "BCP" and st["lotes_liquidacion"][-1]["estado"] == "pagado"


def test_cuenta_de_cobro_en_ingresos_de_la_web(monkeypatch):
    """Modo anfitrión → Ingresos: tarjeta "Cuenta de cobro" con el mismo
    formulario por selección y la misma validación que el app."""
    from web import datos, sesion
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cancha = {"id": "c1", "nombre": "Cancha 1", "club": "Local X", "dueno": "due@gmail.com", "lat": -12.09, "lng": -77.03, "moneda": "S/",
              "verificada": True, "deporte": "futbol", "hora_apertura": "07:00", "hora_cierre": "23:00", "duracion_slot_min": 60, "precio_hora": 80}
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [dict(cancha)] if e == "due@gmail.com" else [])
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "due@gmail.com", "email_verified": "true", "aud": "cid-web", "name": "Dueño Web", "exp": "9999999999"})
    cli = TestClient(app, base_url="https://testserver")
    # Sin sesión no se guarda.
    assert cli.post("/anfitrion/cuenta-cobro", json={"pais": "PE"}).status_code == 401
    cli.post("/web/sesion", json={"credential": "x"})
    html = cli.get("/anfitrion/ingresos").text
    assert "Cuenta de cobro" in html and "Aún no registraste dónde cobrar" in html and 'id="ccForm"' in html.replace("'", '"') and '"INTERBANK"' in html
    r = cli.post("/anfitrion/cuenta-cobro", json={"pais": "PE", "tipo": "banco", "banco": "INTERBANK", "tipo_cuenta": "ahorros", "numero": "8983123456789",
                                                  "titular": "Dueño Web", "doc_tipo": "DNI", "doc_numero": "12345678"}).json()
    assert r["ok"] is False and r["campo"] == "cci"
    r = cli.post("/anfitrion/cuenta-cobro", json={"pais": "PE", "tipo": "plin", "numero": "999888777", "titular": "Dueño Web", "doc_tipo": "DNI", "doc_numero": "12345678"}).json()
    assert r["ok"] and r["resumen"]["canal"] == "manual"
    assert stores.cuenta_cobro("due@gmail.com")["tipo"] == "plin"
    html = cli.get("/anfitrion/ingresos").text
    assert "Plin 999888777 · Dueño Web" in html and "Cambiar" in html and "lote automático" in html
