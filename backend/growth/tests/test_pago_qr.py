"""PAGO POR QR CON MONTO ÚNICO (Ecuador y Bolivia, 11-oct-2026, pedido del
director: "el usuario escanea el código, paga y el sistema lo registra
automáticamente"). El alumno inicia el pago en Pichangol y recibe un monto
único (cuota + centavos); el celular de la academia lee la notificación de su
app de cobros y `yape_auto.conciliar_qr` confirma la cuota."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import academia_plan as ap
import yape_auto
from db.store import stores
from tests.test_academia_plan import ALUMNO, DUENO, FakeMatriculas, entorno  # noqa: F401
from web import datos

QR = "https://x.supabase.co/storage/v1/object/public/canchas/academia_ac_1/qr_cobro_1.jpg"
DEUNA = "com.deuna.app"


@pytest.fixture
def ec(entorno, monkeypatch):  # noqa: F811
    import config
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    stores.qr_intenciones.clear()
    stores.yape_dispositivos.clear()
    stores.yape_notificaciones.clear()
    for k in yape_auto.DEFAULTS:
        stores.config[k] = yape_auto.DEFAULTS[k]
    monkeypatch.setattr(yape_auto, "_SINCRONO", True)
    a = {"id": "ac_1", "nombre": "Academia Quito", "dueno": DUENO, "lat": -0.18, "lng": -78.48, "moneda": "$",
         "cobroDirecto": {"tipo": "qr", "qr_url": QR, "app": "deuna", "titular": "Ace Quito"}}
    fm = FakeMatriculas([
        {"id": "al_1", "academiaId": "ac_1", "email": ALUMNO, "nombre": "Juanito",
         "cuotas": [{"id": "cu_1", "concepto": "Octubre", "monto": 25.0, "vencimiento": "2026-10-13T10:00:00", "pagada": False},
                    {"id": "cu_2", "concepto": "Noviembre", "monto": 25.0, "vencimiento": "2026-11-13T10:00:00", "pagada": False}]},
        {"id": "al_2", "academiaId": "ac_1", "email": ALUMNO, "nombre": "Pepita",
         "cuotas": [{"id": "cu_3", "concepto": "Octubre", "monto": 25.0, "vencimiento": "2026-10-13T10:00:00", "pagada": False}]},
        {"id": "al_3", "academiaId": "ac_1", "email": "otra@correo.ec", "nombre": "Lucas",
         "cuotas": [{"id": "cu_4", "concepto": "Octubre", "monto": 25.0, "vencimiento": "2026-10-13T10:00:00", "pagada": False}]},
    ])
    monkeypatch.setattr(datos, "academia", lambda aid: dict(a) if aid == "ac_1" else None)
    monkeypatch.setattr(datos, "academias_publicas", lambda: [dict(a)])
    monkeypatch.setattr(datos, "academias_de_dueno", lambda em: [dict(a)] if em == DUENO else [])
    monkeypatch.setattr(datos, "matricula", fm.matricula)
    monkeypatch.setattr(datos, "mutar_matricula", fm.mutar)
    monkeypatch.setattr(datos, "matriculas_de_academias", fm.de_academias)
    yape_auto.vincular(DUENO)
    assert yape_auto.elegir_apps(DUENO, [DEUNA])["ok"]
    return {**entorno, "a": a, "fm": fm}


def _c(fm, al, cid):
    return next(c for c in fm.filas[al]["cuotas"] if c["id"] == cid)


def test_cobro_directo_por_pais_qr_en_ecuador_y_yape_en_peru(ec):
    cd = ap.cobro_directo(ec["a"])
    assert cd["tipo"] == "qr" and cd["app_nombre"] == "DeUna!" and cd["titular"] == "Ace Quito"
    # Un QR de afuera (no subido a nuestro Storage) no vale.
    assert ap.cobro_directo({**ec["a"], "cobroDirecto": {**ec["a"]["cobroDirecto"], "qr_url": "https://evil.com/q.png"}}) is None
    with pytest.raises(ValueError):
        ap.validar_cobro_directo({"qr_url": QR, "app": "inventada", "titular": "Ace"}, "EC")
    with pytest.raises(ValueError):
        ap.validar_cobro_directo({"qr_url": "https://evil.com/q.png", "app": "deuna", "titular": "Ace"}, "EC")
    assert ap.validar_cobro_directo({"qr_url": QR, "app": "simple", "titular": "Ace La Paz"}, "BO")["app"] == "simple"
    assert ap.validar_cobro_directo({"yape": "987654321", "titular": "Ace SAC"}, "PE") == {"yape": "987654321", "titular": "Ace SAC"}
    # En Ecuador no se reporta código de Yape: se paga con QR.
    assert ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "123", ahora=ec["hoy"])["error"] == "usa_qr"


def test_monto_unico_se_reusa_y_no_choca_entre_alumnos(ec):
    hoy = ec["hoy"]
    r1 = ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_1", "cuota_ids": ["cu_1"]}], ahora=hoy)
    assert r1["ok"]
    i1 = r1["intencion"]
    assert i1["monto"] == 25.01 and i1["extra_txt"] == "$ 0.01" and i1["qr_url"] == QR and i1["app_nombre"] == "DeUna!"
    # Doble clic / otra pestaña → la MISMA intención.
    r = ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_1", "cuota_ids": ["cu_1"]}], ahora=hoy)
    assert r["reusada"] and r["intencion"]["id"] == i1["id"]
    # Otro alumno de la misma academia con la misma cuota → otro centavo.
    r3 = ap.iniciar_pago_qr("otra@correo.ec", [{"alumno_id": "al_3", "cuota_ids": ["cu_4"]}], ahora=hoy)
    assert r3["intencion"]["monto"] == 25.02
    rep = _c(ec["fm"], "al_1", "cu_1")["reporte"]
    assert rep["estado"] == "esperando_pago" and rep["medio"] == "qr" and rep["intencion"] == i1["id"]
    # Cambia la selección (agrega otra cuota): la anterior se reemplaza.
    r4 = ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_1", "cuota_ids": ["cu_1", "cu_2"]}], ahora=hoy)
    assert r4["intencion"]["monto"] == 50.01
    assert stores.qr_intenciones[i1["id"]]["estado"] == "reemplazado"
    # No se paga una matrícula ajena.
    assert ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_3", "cuota_ids": ["cu_4"]}], ahora=hoy)["error"] == "no_encontrado"


def test_notificacion_de_la_app_de_cobros_confirma_sola_al_monto_exacto(ec):
    fm, hoy = ec["fm"], ec["hoy"]
    # Pago familiar: dos hijos en un solo QR.
    r = ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_1", "cuota_ids": ["cu_1"]},
                                    {"alumno_id": "al_2", "cuota_ids": ["cu_3"]}], ahora=hoy)
    i = r["intencion"]
    assert i["monto"] == 50.01
    # Otro monto, un egreso o una app no elegida: nada.
    assert yape_auto.registrar(DUENO, DEUNA, "DeUna", "Recibiste $ 50.00 de MARIA", ahora=hoy + timedelta(minutes=2))["confirmados"] == []
    assert yape_auto.registrar(DUENO, DEUNA, "DeUna", "Pagaste $ 50.01 a TIENDA", ahora=hoy + timedelta(minutes=3))["confirmados"] == []
    assert yape_auto.registrar(DUENO, "com.otro.banco", "x", "Recibiste $ 50.01", ahora=hoy)["ignorada"] == "paquete"
    r = yape_auto.registrar(DUENO, DEUNA, "DeUna!", "Recibiste US$ 50,01 de JUAN PEREZ", ahora=hoy + timedelta(minutes=4))
    assert len(r["confirmados"]) == 1
    for al, cid in (("al_1", "cu_1"), ("al_2", "cu_3")):
        c = _c(fm, al, cid)
        assert c["pagada"] and c["medioPago"] == "qr_directo" and c["operacionId"] == f"qr:{i['id']}"
        assert c["reporte"]["auto"] == "qr_notificacion"
    assert not _c(fm, "al_1", "cu_2").get("pagada")
    assert stores.qr_intenciones[i["id"]]["estado"] == "confirmado"
    assert any(p[0] == DUENO and "solo" in p[1] for p in ec["pushes"])
    recibos = [d for t, d in ec["correos"] if t == "aviso" and d.get("etiqueta") == "Recibo"]
    assert recibos and any("Centavos" in l[0] for d in recibos for l in d["lineas"])
    # El centavo vuelve a estar libre para el siguiente pago.
    r2 = ap.iniciar_pago_qr("otra@correo.ec", [{"alumno_id": "al_3", "cuota_ids": ["cu_4"]}], ahora=hoy)
    assert r2["intencion"]["monto"] == 25.01


def test_notificacion_antes_de_iniciar_no_cuenta_y_ambiguas_quedan_a_mano(ec, monkeypatch):
    fm, hoy = ec["fm"], ec["hoy"]
    # Llegó ANTES de crear la intención (pago viejo): no la confirma.
    yape_auto.registrar(DUENO, DEUNA, "DeUna", "Recibiste $ 25.01", ahora=hoy - timedelta(hours=2))
    r = ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_1", "cuota_ids": ["cu_1"]}], ahora=hoy)
    assert not _c(fm, "al_1", "cu_1").get("pagada")
    # "Ya pagué" sin notificación: queda por confirmar para la academia.
    assert ap.marcar_pagado_qr(r["intencion"]["id"], ALUMNO, ahora=hoy + timedelta(minutes=1))["ok"]
    grupos = ap.por_confirmar([ec["a"]])
    assert len(grupos) == 1 and grupos[0]["medio"] == "qr" and grupos[0]["monto_unico"] == 25.01
    # Dos notificaciones iguales llegan juntas (p. ej. la base estaba caída) →
    # ambiguas, nada se confirma solo.
    real = yape_auto.conciliar_qr
    monkeypatch.setattr(yape_auto, "conciliar_qr", lambda *a, **k: {"confirmados": []})
    yape_auto.registrar(DUENO, DEUNA, "DeUna", "Recibiste $ 25.01 de ANA", ahora=hoy + timedelta(minutes=2))
    yape_auto.registrar(DUENO, DEUNA, "DeUna", "Recibiste $ 25.01 de LUIS", ahora=hoy + timedelta(minutes=3))
    assert real(DUENO, ahora=hoy + timedelta(minutes=4))["confirmados"] == []
    assert not _c(fm, "al_1", "cu_1").get("pagada")
    assert any(n.get("nota") == "ambigua" for n in stores.yape_notificaciones)
    # La academia confirma a mano desde su lista.
    g = grupos[0]
    assert ap.resolver_pago("ac_1", g["alumno_id"], [c["id"] for c in g["cuotas"]], DUENO, True, ahora=hoy)["ok"]
    assert _c(fm, "al_1", "cu_1")["pagada"] and _c(fm, "al_1", "cu_1")["medioPago"] == "qr_directo"


def test_vence_y_libera_la_cuota_sin_plan_no_confirma(ec, monkeypatch):
    fm, hoy = ec["fm"], ec["hoy"]
    r = ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_1", "cuota_ids": ["cu_1"]}], ahora=hoy)
    assert ap.vencer_qr(hoy + timedelta(hours=49)) == 1
    assert "reporte" not in _c(fm, "al_1", "cu_1")
    assert stores.qr_intenciones[r["intencion"]["id"]]["estado"] == "vencido"
    # Sin el plan vigente la academia no tiene confirmación automática.
    r = ap.iniciar_pago_qr(ALUMNO, [{"alumno_id": "al_1", "cuota_ids": ["cu_1"]}], ahora=hoy + timedelta(hours=50))
    monkeypatch.setattr(ap, "beneficios", lambda a: False)
    yape_auto.registrar(DUENO, DEUNA, "DeUna", f"Recibiste $ {r['intencion']['monto']:.2f}", ahora=hoy + timedelta(hours=50, minutes=2))
    assert not _c(fm, "al_1", "cu_1").get("pagada")


def test_montos_de_bancos_y_apps_elegidas(ec):
    f = yape_auto.monto_flexible
    assert f("1.234,56") == 1234.56 and f("1,234.56") == 1234.56 and f("25,13") == 25.13 and f("150") == 150.0
    assert yape_auto.leer_qr("Banco Unión", "Te transfirieron Bs. 150,07 de CARLOS") == {"monto": 150.07, "moneda": "BOB", "egreso": False}
    assert yape_auto.leer_qr("Pichincha", "Transferencia enviada: enviaste $ 10.00")["egreso"]
    # Mensajería y Pichangol nunca se escuchan.
    assert yape_auto.elegir_apps(DUENO, ["com.whatsapp"])["error"] == "prohibida"
    assert yape_auto.elegir_apps(DUENO, ["no valido"])["error"] == "paquete"
    assert DEUNA in yape_auto.estado_dueno(DUENO)["paquetes"]
    # Cambiar de celular conserva las apps elegidas.
    assert DEUNA in yape_auto.vincular(DUENO)["paquetes"]


def test_endpoints_y_snapshot(ec, monkeypatch):
    from main import app
    cli = TestClient(app)
    r = cli.post("/academias/pago-qr/iniciar", json={"email": ALUMNO, "alumno_id": "al_1", "cuota_ids": ["cu_1"]})
    assert r.status_code == 200 and r.json()["ok"]
    iid = r.json()["intencion"]["id"]
    assert cli.get(f"/academias/pago-qr/{iid}", params={"email": ALUMNO}).json()["intencion"]["estado"] == "esperando"
    assert cli.get(f"/academias/pago-qr/{iid}", params={"email": "intruso@x.ec"}).json()["error"] == "no_encontrado"
    assert cli.post(f"/academias/pago-qr/{iid}/pagado", json={"email": ALUMNO}).json()["intencion"]["estado"] == "reportado"
    r = cli.post("/academias/yape/apps", json={"email": DUENO, "paquetes": [DEUNA, "com.pichincha.app"]})
    assert r.json()["ok"] and "com.pichincha.app" in r.json()["paquetes"]
    assert "qr_apps" in cli.get("/config/academias").json()
    estado = stores.to_state()
    assert iid in estado["qr_intenciones"]
    stores.qr_intenciones.clear()
    stores.load_state(estado)
    assert stores.qr_intenciones[iid]["monto_c"] == 2501
