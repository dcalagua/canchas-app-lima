"""PLAN ACADEMIA en la WEB (10-oct-2026): matrícula DIRECTA (sin cobro), pago
directo del alumno a la academia por Yape con el código de seguridad
(reportar en la web, confirmar en Cobros), candado de gestión con el plan
vencido, ficha sin matrícula y, con el modelo "comision", todo como antes."""
import copy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import academia_plan as ap
import config
from db.store import stores
from main import app
from web import datos

DUENO = "profe@academia.pe"
PAPA = "papa@gmail.com"


class FakeDB:
    def __init__(self):
        self.academias = {"ac_1": {
            "nombre": "Academia Ace", "deporte": "tenis", "dueno": DUENO, "sedeClub": "Club Lawn", "zona": "San Borja",
            "lat": -12.09, "lng": -77.03, "whatsapp": "999888777", "moneda": "S/", "descuentoPrepago": 10, "mesesMinPrepago": 3,
            "descuentoHermano2": 10, "cobroDirecto": {"yape": "987654321", "titular": "Ace SAC"},
            "planes": [{"id": "Bola Roja | 2x", "nombre": "Bola Roja · 2x/sem", "programa": "Bola Roja", "precioMes": 250, "frecuenciaSemana": 2},
                       {"id": "pl_clase", "nombre": "Clase particular", "tipo": "porClase", "precioMes": 80, "meses": 0}]}}
        self.matriculas: dict[str, dict] = {}

    def academia(self, aid):
        a = self.academias.get(aid)
        return dict(copy.deepcopy(a), id=aid) if a else None

    def academias_publicas(self):
        return [self.academia(k) for k in self.academias]

    def academias_de_dueno(self, email):
        return [self.academia(k) for k, a in self.academias.items() if a["dueno"] == (email or "").lower()]

    def guardar_academia(self, aid, dueno, data):
        self.academias[aid] = dict(data, dueno=dueno)
        return True

    def insertar_matricula(self, alumno_id, academia_id, email, data):
        if alumno_id in self.matriculas:
            return False
        self.matriculas[alumno_id] = dict(copy.deepcopy(data), id=alumno_id, academiaId=academia_id, email=email)
        return True

    def matricula(self, alumno_id):
        m = self.matriculas.get(alumno_id)
        return copy.deepcopy(m) if m else None

    def matriculas_de_pagador(self, academia_id, email):
        return [copy.deepcopy(m) for m in self.matriculas.values() if m["academiaId"] == academia_id and m["email"] == email]

    def matriculas_de_academias(self, ids):
        return [copy.deepcopy(m) for m in self.matriculas.values() if m["academiaId"] in ids]

    def mutar_matricula(self, alumno_id, fn, academia_id=""):
        m = self.matriculas.get(alumno_id)
        if not m or (academia_id and m["academiaId"] != academia_id):
            return None
        data = copy.deepcopy(m)
        res = fn(data)
        if res is None:
            return None
        self.matriculas[alumno_id] = data
        return res


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    for fn in ("academia", "academias_publicas", "academias_de_dueno", "guardar_academia", "insertar_matricula", "matricula",
               "matriculas_de_pagador", "matriculas_de_academias", "mutar_matricula"):
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    from web import jugador_clases as jc
    monkeypatch.setattr(jc, "matriculas_de_usuario", lambda em: [m for m in fake.matriculas.values()
                                                                 if em in (m["email"], m.get("emailAlumno"))])
    monkeypatch.setattr(jc, "academias_por_id", lambda ids: {i: fake.academia(i) for i in ids if fake.academia(i)})
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    for k, v in (("acad_modelo", "suscripcion"), ("acad_plan_precio_PEN", "11.50"), ("acad_plan_prueba_dias", "30")):
        monkeypatch.setitem(stores.config, k, v)
    stores.planes_academia.clear()
    import pagos.router as pr
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, t, c, tipo="aviso": pushes.append((email, t, c)))
    monkeypatch.setattr(pr, "moneda_billetera", lambda email: "PEN")
    import correos
    monkeypatch.setattr(correos, "encolar", lambda *a, **k: None)
    from pagos import culqi

    def _no_cobrar(**kw):
        raise AssertionError("En el Plan Academia Pichangol NO cobra matrículas ni cuotas")
    monkeypatch.setattr(culqi, "crear_cargo", _no_cobrar)
    fake.pushes = pushes
    yield fake
    stores.planes_academia.clear()


def _entrar_como(cli, monkeypatch, email, nombre="Alguien"):
    from web import sesion
    cli.post("/web/salir")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": email, "email_verified": "true", "aud": "cid-web", "name": nombre, "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})


def _vencer(aid="ac_1"):
    r = stores.planes_academia[aid]
    r["prueba_hasta"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    r["hasta"] = None


def test_matricula_directa_crea_cuotas_pendientes_sin_cobrar(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    html = cli.get("/academia/ac_1").text
    # Ficha con el MISMO formulario pero sin Culqi, sin pasarela y sin cargo por servicio.
    assert "class='btn chico elegir'" in html and '"directo": true' in html and "checkout.culqi.com" not in html
    assert "Aquí no pagas nada" in html and "A pagar a la academia" in html and '"cargo": false' in html
    # El cobro en línea de academias queda cerrado en el servidor.
    r = cli.post("/web/matricular", json={"academia_id": "ac_1", "plan_id": "Bola Roja | 2x", "nombre": "Ana", "celular": "999888777", "token": "t"}).json()
    assert r["error"] == "pago_directo"
    persona = {"plan_id": "Bola Roja | 2x", "nombre": "Lucas Pérez", "celular": "999888777", "quien": "hijo", "es_hijo": True, "edad": 8,
               "cantidad": 3, "mes_a_mes": True}
    assert cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [persona]}).json()["error"] == "sesion_requerida"
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    n_pagos = len(stores.pagos)
    # Mes a mes por 3 meses: 3 cuotas PENDIENTES (la 1.ª vence hoy), sin débito automático.
    r = cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [persona]}).json()
    assert r["ok"] and r["url"].startswith("/academia/ac_1/matricula/al_")
    m = db.matriculas[r["alumno_id"]]
    assert m["email"] == PAPA and m["apoderadoNombre"] == "Papá Pérez" and m["canal"] == "web" and "pagoWeb" not in m
    cu = m["cuotas"]
    assert len(cu) == 3 and not any(c["pagada"] or c.get("autoDebito") or c.get("operacionId") for c in cu)
    assert cu[0]["vencimiento"][:10] == datetime.now().date().isoformat() and all(c["monto"] == 250 for c in cu)
    assert len(stores.pagos) == n_pagos  # sin post_matricula, sin cobro_web, sin comisión
    assert any(p[0] == DUENO and "Nuevo alumno" in p[1] and "pago pendiente" in p[2] for p in db.pushes)
    # Adelantado 3 meses: UNA cuota que vence hoy con el total con descuento (prepago 10 % + 2.º de la familia 10 %).
    r2 = cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [
        {"plan_id": "Bola Roja | 2x", "nombre": "Papá Pérez", "celular": "999888777", "quien": "yo", "cantidad": 3}]}).json()
    m2 = db.matriculas[r2["alumno_id"]]
    assert len(m2["cuotas"]) == 1 and m2["cuotas"][0]["monto"] == 600.0 and m2["cuotas"][0]["concepto"] == "Bola Roja · 2x/sem · 3 meses (adelantado)"
    assert not m2["cuotas"][0]["pagada"] and m2["pagoDirecto"]["dtoFamiliar"] == 10
    # Comprobante: "Paga a la academia" con el Yape, pasos y el formulario del código de seguridad.
    comp = cli.get(r["url"]).text
    for t in ("¡Matrícula registrada!", "Paga a la academia", "987 654 321", "Ace SAC", "código de seguridad", "pd-cod", "Ya yapeé",
              "data-pd-copiar='987654321'", "<span class='pill gris'>Pendiente</span>"):
        assert t in comp, t
    assert "Pagado hoy" not in comp
    # Familiar (carrito): un solo comprobante con el bloque para las dos personas.
    rf = cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [
        {"plan_id": "pl_clase", "nombre": "Ana Pérez", "celular": "999888777", "quien": "familiar"},
        {"plan_id": "pl_clase", "nombre": "Leo Pérez", "celular": "999888777", "quien": "hijo", "es_hijo": True, "edad": 6}]}).json()
    assert rf["ok"] and "matriculas?ids=" in rf["url"]
    compf = cli.get(rf["url"]).text
    assert "¡Matrícula familiar registrada!" in compf and compf.count("data-pdc=") >= 2
    # Sin Yape registrado: "Coordina el pago con la academia" + WhatsApp.
    db.academias["ac_1"].pop("cobroDirecto")
    assert "Coordina el pago con la academia" in cli.get(r["url"]).text


def test_reporte_y_confirmacion_desde_la_web(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    r = cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [
        {"plan_id": "Bola Roja | 2x", "nombre": "Lucas Pérez", "celular": "999888777", "quien": "hijo", "es_hijo": True, "edad": 8,
         "cantidad": 2, "mes_a_mes": True}]}).json()
    aid = r["alumno_id"]
    c0 = db.matriculas[aid]["cuotas"][0]["id"]
    # Mis clases: caja de pago directo, sin cobro en línea.
    mc = cli.get("/mis-clases").text
    assert "pd-box" in mc and "987 654 321" in mc and "data-pagar='" not in mc and "checkout.culqi.com" not in mc
    assert cli.post("/web/mis-clases/pagar", json={"token": "t", "cuotas": [{"alumno_id": aid, "cuota_id": c0}]}).json()["error"] == "pago_directo"
    # Reportar: código de 3 dígitos obligatorio.
    assert cli.post("/web/academia/pago-directo/reportar", json={"items": [{"alumno_id": aid, "cuota_ids": [c0]}], "codigo": "12"}).json()["error"] == "codigo"
    j = cli.post("/web/academia/pago-directo/reportar", json={"items": [{"alumno_id": aid, "cuota_ids": [c0]}], "codigo": "701", "operacion": "05775701"}).json()
    assert j["ok"] and j["total"] == 250
    c = db.matriculas[aid]["cuotas"][0]
    assert c["reporte"]["estado"] == "por_confirmar" and c["reporte"]["codigo"] == "701" and not c["pagada"]
    assert "Por confirmar por la academia" in cli.get(r["url"]).text
    # Otra cuenta no puede reportar cuotas ajenas.
    _entrar_como(cli, monkeypatch, "intruso@gmail.com")
    assert not cli.post("/web/academia/pago-directo/reportar", json={"alumno_id": aid, "cuota_ids": [c0], "codigo": "701"}).json()["ok"]
    # La academia: "Pagos por confirmar" en Cobros con el código en grande.
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    cob = cli.get("/anfitrion/cobros?academia=ac_1").text
    assert "Pagos por confirmar" in cob and "class='pc-cod'>701<" in cob and "05775701" in cob and "Compara el código" in cob
    # Rechazar exige un motivo de la lista.
    assert cli.post("/anfitrion/academia/pago-directo/resolver", json={"academia_id": "ac_1", "alumno_id": aid, "cuota_ids": [c0],
                                                                       "aceptar": False, "motivo": "otra cosa"}).json()["error"] == "motivo"
    j = cli.post("/anfitrion/academia/pago-directo/resolver", json={"academia_id": "ac_1", "alumno_id": aid, "cuota_ids": [c0], "aceptar": True}).json()
    assert j["ok"] and j["aceptado"]
    c = db.matriculas[aid]["cuotas"][0]
    assert c["pagada"] and c["operacionId"] == "yape:05775701" and c["medioPago"] == "yape_directo"
    assert "Pagos por confirmar" not in cli.get("/anfitrion/cobros?academia=ac_1").text
    assert any(p[0] == PAPA and "confirmado" in p[1].lower() for p in db.pushes)
    # Rechazo: el alumno lo ve y puede volver a reportar.
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    c1 = db.matriculas[aid]["cuotas"][1]["id"]
    assert cli.post("/web/academia/pago-directo/reportar", json={"alumno_id": aid, "cuota_ids": [c1], "codigo": "123"}).json()["ok"]
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    assert cli.post("/anfitrion/academia/pago-directo/resolver", json={"academia_id": "ac_1", "alumno_id": aid, "cuota_ids": [c1],
                                                                       "aceptar": False, "motivo": "El código no coincide"}).json()["ok"]
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    assert "Rechazado: El código no coincide" in cli.get(r["url"]).text
    assert cli.post("/web/academia/pago-directo/reportar", json={"alumno_id": aid, "cuota_ids": [c1], "codigo": "124"}).json()["ok"]


def test_paywall_y_ficha_sin_matricula_cuando_vence_el_plan(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    r = cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [
        {"plan_id": "pl_clase", "nombre": "Lucas Pérez", "celular": "999888777", "quien": "hijo", "es_hijo": True, "edad": 8}]}).json()
    aid = r["alumno_id"]
    assert cli.post("/web/academia/pago-directo/reportar", json={"alumno_id": aid, "cuota_ids": [db.matriculas[aid]["cuotas"][0]["id"]],
                                                                 "codigo": "555"}).json()["ok"]
    # Dueño en prueba: banner con los días, menú con el Plan Academia.
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    assert "días de prueba gratis" in cli.get("/anfitrion/academia").text
    assert "/anfitrion/academia/plan" in cli.get("/anfitrion").text
    assert "Activa tu Plan Academia" not in cli.get("/anfitrion/academia/sedes?academia=ac_1").text
    _vencer()
    # Ficha pública: sin matrícula ni mención del plan vencido; matrícula por WhatsApp.
    ficha = cli.get("/academia/ac_1").text
    assert "recibe matrículas por WhatsApp" in ficha and "elegir" not in ficha and "venció" not in ficha and "wa.me/51999888777" in ficha
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    assert cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [
        {"plan_id": "pl_clase", "nombre": "Leo Pérez", "celular": "999888777", "quien": "hijo", "es_hijo": True, "edad": 6}]}).json()["error"] == "sin_plan"
    # Gestión con candado; los pagos reportados SIEMPRE se confirman.
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    assert "Tu plan venció" in cli.get("/anfitrion/academia").text
    for ruta in ("/anfitrion/academia/alumnos?academia=ac_1", "/anfitrion/academia/sedes?academia=ac_1", "/anfitrion/academia/ranking?academia=ac_1"):
        assert "Activa tu Plan Academia" in cli.get(ruta).text, ruta
    cob = cli.get("/anfitrion/cobros?academia=ac_1").text
    assert "Activa tu Plan Academia" in cob and "Pagos por confirmar" in cob and "Quién debe" not in cob
    assert cli.post("/anfitrion/academia/pago-directo/resolver", json={"academia_id": "ac_1", "alumno_id": aid, "aceptar": True}).json()["ok"]
    # Plan: vencido → sin saldo pide recargar → con saldo queda activo; renovación automática.
    plan = cli.get("/anfitrion/academia/plan?academia=ac_1").text
    assert "Vencido" in plan and "S/ 11.50" in plan and "Recordatorios automáticos" in plan and "data-plan-pagar='ac_1'" in plan
    if stores.saldo_centimos(DUENO) > 0:
        stores.debitar(DUENO, stores.saldo_centimos(DUENO))
    assert cli.post("/anfitrion/academia/plan/pagar", json={"academia_id": "ac_1"}).json()["error"] == "falta_saldo"
    stores.acreditar(DUENO, 2000)
    j = cli.post("/anfitrion/academia/plan/pagar", json={"academia_id": "ac_1"}).json()
    assert j["ok"] and j["vence_txt"] and stores.saldo_centimos(DUENO) == 850
    assert "Activo hasta" in cli.get("/anfitrion/academia/plan").text
    assert "Activa tu Plan Academia" not in cli.get("/anfitrion/academia/alumnos?academia=ac_1").text
    assert cli.post("/anfitrion/academia/plan/renovacion", json={"academia_id": "ac_1", "renovar": False}).json()["auto_renovar"] is False
    assert stores.planes_academia["ac_1"]["auto_renovar"] is False
    # Otra cuenta no paga ni toca el plan ajeno.
    _entrar_como(cli, monkeypatch, PAPA)
    assert cli.post("/anfitrion/academia/plan/pagar", json={"academia_id": "ac_1"}).status_code == 404
    stores.debitar(DUENO, stores.saldo_centimos(DUENO))


def test_editor_guarda_el_yape_de_la_academia(db, monkeypatch):
    db.academias["ac_1000001"] = copy.deepcopy(db.academias.pop("ac_1"))
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    ed = cli.get("/anfitrion/academia/ac_1000001/editar").text
    assert "Cobro directo a tu academia" in ed and "id='cdYape'" in ed and "987654321" in ed
    base = {"id": "ac_1000001", "nombre": "Academia Ace", "deporte": "tenis", "sedeClub": "Club Lawn", "lat": -12.09, "lng": -77.03,
            "whatsapp": "999888777", "planes": [{"id": "p1", "nombre": "Mensual", "precioMes": 200}]}
    r = cli.post("/anfitrion/academia/guardar", json=dict(base, cobroDirecto={"yape": "12345", "titular": "Ace"}))
    assert r.status_code == 400 and r.json()["campo"] == "cobro"
    assert cli.post("/anfitrion/academia/guardar", json=dict(base, cobroDirecto={"yape": "912 345 678", "titular": "Ace SAC"})).json()["ok"]
    assert db.academias["ac_1000001"]["cobroDirecto"] == {"yape": "912345678", "titular": "Ace SAC"}
    # Sin la clave en el cuerpo (cliente viejo) se conserva; vacío lo quita.
    assert cli.post("/anfitrion/academia/guardar", json=base).json()["ok"] and db.academias["ac_1000001"]["cobroDirecto"]["yape"] == "912345678"
    assert cli.post("/anfitrion/academia/guardar", json=dict(base, cobroDirecto={"yape": "", "titular": ""})).json()["ok"]
    assert "cobroDirecto" not in db.academias["ac_1000001"]


def test_modelo_comision_sigue_como_siempre(db, monkeypatch):
    monkeypatch.setitem(stores.config, "acad_modelo", "comision")
    cli = TestClient(app, base_url="https://testserver")
    html = cli.get("/academia/ac_1").text
    assert "checkout.culqi.com" in html and '"directo": false' in html and "Aquí no pagas nada" not in html
    _entrar_como(cli, monkeypatch, PAPA)
    r = cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [
        {"plan_id": "pl_clase", "nombre": "Leo Pérez", "celular": "999888777"}]}).json()
    assert r["error"] == "modelo" and not db.matriculas
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    assert "/anfitrion/academia/plan" not in cli.get("/anfitrion").text
    mi = cli.get("/anfitrion/academia").text
    assert "prueba gratis" not in mi and "Plan Academia" not in mi
    assert "Cobro directo por Yape" not in cli.get("/anfitrion/academia/ac_1/editar").text
    assert ap.beneficios(db.academia("ac_1"))


def test_pago_por_qr_con_monto_unico_en_la_web(db, monkeypatch):
    """Ecuador: el editor pide el QR + app; el alumno ve «Pagar con QR», recibe
    un monto único y la notificación de la app de cobros lo confirma sola."""
    import yape_auto
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(yape_auto, "_SINCRONO", True)
    stores.qr_intenciones.clear()
    stores.yape_notificaciones.clear()
    stores.yape_dispositivos.clear()
    qr = "https://x.supabase.co/storage/v1/object/public/canchas/academia_ac_1/qr_cobro_1.jpg"
    db.academias["ac_1"].update({"lat": -0.18, "lng": -78.48, "moneda": "$",
                                 "cobroDirecto": {"tipo": "qr", "qr_url": qr, "app": "deuna", "titular": "Ace Quito"}})
    cli = TestClient(app, base_url="https://testserver")
    # Editor del dueño: sección QR (no Yape) con las apps de Ecuador.
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    ed = cli.get("/anfitrion/academia/ac_1/editar").text
    assert "Cobro directo a tu academia" in ed and "id='cdQrBox'>" in ed and "id='cdYapeBox' hidden" in ed
    assert "data-g='cdApp_EC' data-v='deuna'" in ed and "Ace Quito" in ed
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    r = cli.post("/web/matricular-directo", json={"academia_id": "ac_1", "personas": [
        {"plan_id": "Bola Roja | 2x", "nombre": "Lucas Pérez", "celular": "0991234567", "quien": "hijo", "es_hijo": True, "edad": 8,
         "cantidad": 2, "mes_a_mes": True}]}).json()
    aid = r["alumno_id"]
    c0 = db.matriculas[aid]["cuotas"][0]["id"]
    mc = cli.get("/mis-clases").text
    assert "pq-iniciar" in mc and "Pagar con QR" in mc and "DeUna!" in mc and "class='pd-cod'" not in mc
    # El código de Yape no aplica en Ecuador.
    assert cli.post("/web/academia/pago-directo/reportar", json={"items": [{"alumno_id": aid, "cuota_ids": [c0]}], "codigo": "123"}).json()["error"] == "usa_qr"
    j = cli.post("/web/academia/pago-qr/iniciar", json={"items": [{"alumno_id": aid, "cuota_ids": [c0]}]}).json()
    assert j["ok"] and j["intencion"]["monto_txt"] == "$ 250.01" and j["intencion"]["qr_url"] == qr
    iid = j["intencion"]["id"]
    # Al volver, el bloque reabre el pago en curso.
    assert f"data-pq-viva='{iid}'" in cli.get("/mis-clases").text
    assert cli.post(f"/web/academia/pago-qr/{iid}/pagado").json()["intencion"]["estado"] == "reportado"
    # La academia lo ve en «Pagos por confirmar» con el monto exacto.
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    cob = cli.get("/anfitrion/cobros?academia=ac_1").text
    assert "Monto exacto por QR" in cob and "$ 250.01" in cob
    # Llega la notificación de DeUna! al celular de la academia → pagada sola.
    yape_auto.vincular(DUENO)
    yape_auto.elegir_apps(DUENO, ["com.deuna.app"])
    yape_auto.registrar(DUENO, "com.deuna.app", "DeUna!", "Recibiste $250.01 de PAPA PEREZ")
    c = db.matriculas[aid]["cuotas"][0]
    assert c["pagada"] and c["medioPago"] == "qr_directo" and c["operacionId"] == f"qr:{iid}"
    _entrar_como(cli, monkeypatch, PAPA, "Papá Pérez")
    assert cli.get(f"/web/academia/pago-qr/{iid}").json()["intencion"]["estado"] == "confirmado"
