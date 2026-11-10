"""PLAN ACADEMIA (suscripción tipo Spotify, 10-oct-2026): prueba gratis, pago
con saldo, renovación, avisos, pago DIRECTO del alumno a la academia con el
código de seguridad de Yape y recordatorios de cuota (`academia_plan.py`)."""
from datetime import datetime, timedelta, timezone

import pytest

import academia_plan as ap
from db.store import stores
from web import datos


DUENO = "profe@academia.pe"
ALUMNO = "papa@correo.pe"


def _acad(**kw):
    a = {"id": "ac_1", "nombre": "Academia Ace", "dueno": DUENO, "lat": -12.1, "lng": -77.0,
         "moneda": "S/", "cobroDirecto": {"yape": "987654321", "titular": "Ace SAC"}}
    a.update(kw)
    return a


class FakeMatriculas:
    def __init__(self, filas):
        self.filas = {f["id"]: f for f in filas}

    def matricula(self, alumno_id):
        f = self.filas.get(alumno_id)
        return dict(f) if f else None

    def mutar(self, alumno_id, fn, academia_id=""):
        f = self.filas.get(alumno_id)
        if not f or (academia_id and f["academiaId"] != academia_id):
            return None
        import copy
        data = copy.deepcopy(f)
        res = fn(data)
        if res is None:
            return None
        self.filas[alumno_id] = data
        return res

    def de_academias(self, ids):
        return [dict(f) for f in self.filas.values() if f["academiaId"] in ids]


@pytest.fixture
def entorno(monkeypatch):
    stores.planes_academia.clear()
    stores.recordatorios_cuotas.clear()
    if stores.saldo_centimos(DUENO) > 0:
        stores.debitar(DUENO, stores.saldo_centimos(DUENO))
    for k in ("acad_modelo", "acad_plan_precio_PEN", "acad_plan_prueba_dias"):
        stores.config.pop(k, None)
    stores.config.update({"acad_modelo": "suscripcion", "acad_plan_precio_PEN": "11.50", "acad_plan_prueba_dias": "30"})
    a = _acad()
    hoy = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
    fm = FakeMatriculas([{
        "id": "al_1", "academiaId": "ac_1", "email": ALUMNO, "nombre": "Juanito",
        "cuotas": [
            {"id": "cu_1", "concepto": "Bola verde · Octubre", "monto": 300.0, "vencimiento": "2026-10-13T10:00:00", "pagada": False},
            {"id": "cu_2", "concepto": "Bola verde · Noviembre", "monto": 300.0, "vencimiento": "2026-11-13T10:00:00", "pagada": False},
        ]}])
    monkeypatch.setattr(datos, "academia", lambda aid: dict(a) if aid == "ac_1" else None)
    monkeypatch.setattr(datos, "academias_publicas", lambda: [dict(a)])
    monkeypatch.setattr(datos, "academias_de_dueno", lambda em: [dict(a)] if em == DUENO else [])
    monkeypatch.setattr(datos, "matricula", fm.matricula)
    monkeypatch.setattr(datos, "mutar_matricula", fm.mutar)
    monkeypatch.setattr(datos, "matriculas_de_academias", fm.de_academias)
    import pagos.router as pr
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, t, c, tipo="aviso": pushes.append((email, t, c)))
    monkeypatch.setattr(pr, "moneda_billetera", lambda email: "PEN")
    import correos
    correos_ = []
    monkeypatch.setattr(correos, "encolar", lambda tipo, pago_id=None, datos=None: correos_.append((tipo, datos)))
    return {"a": a, "hoy": hoy, "fm": fm, "pushes": pushes, "correos": correos_}


def test_prueba_gratis_pago_con_saldo_y_vencimiento(entorno):
    a, hoy = entorno["a"], entorno["hoy"]
    e = ap.estado(a, hoy)
    assert e["estado"] == "prueba" and e["beneficios"] and e["precio"] == 11.5 and e["simbolo"] == "S/"
    assert e["dias_restantes"] == 30
    # Sin saldo no se puede pagar.
    r = ap.pagar(a, DUENO, hoy)
    assert not r["ok"] and r["error"] == "falta_saldo"
    # Otro correo no paga el plan de la academia.
    assert ap.pagar(a, "otro@x.pe", hoy)["error"] == "no_dueno"
    stores.acreditar(DUENO, 2000)
    r = ap.pagar(a, DUENO, hoy)
    assert r["ok"]
    # Pagar durante la prueba NO pierde los días gratis: suma 30 al fin de la prueba.
    assert r["hasta"][:10] == (hoy + timedelta(days=60)).date().isoformat()
    assert stores.saldo_centimos(DUENO) == 2000 - 1150
    p = stores.pagos[-1]
    assert p.tipo == "suscripcion_academia" and p.monto_centimos == 1150 and p.moneda == "PEN"
    assert ap.estado(a, hoy + timedelta(days=40))["estado"] == "activa"
    # Vence, sin saldo → vencida, sin beneficios.
    stores.debitar(DUENO, stores.saldo_centimos(DUENO))
    mas = hoy + timedelta(days=61)
    ap.procesar(mas, academias=[a])
    assert ap.estado(a, mas)["estado"] == "vencida"
    assert not ap.estado(a, mas)["beneficios"]


def test_renovacion_automatica_y_avisos_al_dueno(entorno):
    a, hoy = entorno["a"], entorno["hoy"]
    stores.acreditar(DUENO, 5000)
    ap.pagar(a, DUENO, hoy)  # hasta = hoy + 60
    fin = hoy + timedelta(days=60)
    # 3 días antes: aviso (una sola vez).
    ap.procesar(fin - timedelta(days=3), academias=[a])
    ap.procesar(fin - timedelta(days=3, hours=-1), academias=[a])
    avisos = [p for p in entorno["pushes"] if "vence" in p[1]]
    assert len(avisos) == 1 and "renovaremos" in avisos[0][2].lower()
    # Al vencer, renueva solo desde el saldo.
    ap.procesar(fin + timedelta(hours=1), academias=[a])
    assert ap.estado(a, fin + timedelta(hours=2))["estado"] == "activa"
    assert stores.saldo_centimos(DUENO) == 5000 - 2 * 1150
    assert any("renovado" in p[1].lower() for p in entorno["pushes"])
    # Con la renovación apagada no se cobra.
    assert ap.cambiar_renovacion(a, DUENO, False)["ok"]
    fin2 = fin + timedelta(days=30)
    ap.procesar(fin2 + timedelta(hours=1), academias=[a])
    assert ap.estado(a, fin2 + timedelta(hours=2))["estado"] == "vencida"
    assert stores.saldo_centimos(DUENO) == 5000 - 2 * 1150


def test_prueba_vencida_no_se_cobra_sola(entorno):
    """Si nunca pagó, al terminar la prueba NO se debita el saldo sin permiso."""
    a, hoy = entorno["a"], entorno["hoy"]
    stores.acreditar(DUENO, 5000)
    ap.estado(a, hoy)
    ap.procesar(hoy + timedelta(days=31), academias=[a])
    assert ap.estado(a, hoy + timedelta(days=31))["estado"] == "vencida"
    assert stores.saldo_centimos(DUENO) == 5000


def test_pago_directo_con_codigo_de_seguridad(entorno):
    fm, pushes = entorno["fm"], entorno["pushes"]
    r = ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "70", "")
    assert not r["ok"] and r["error"] == "codigo"
    assert ap.reportar_pago("al_1", "intruso@x.pe", ["cu_1"], "701")["error"] == "no_encontrado"
    r = ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "701", "05775701")
    assert r["ok"] and r["total"] == 300.0
    c = fm.filas["al_1"]["cuotas"][0]
    assert c["reporte"]["estado"] == "por_confirmar" and c["reporte"]["codigo"] == "701" and not c["pagada"]
    assert any(p[0] == DUENO and "701" in p[2] for p in pushes)
    # No se reporta dos veces la misma cuota.
    assert not ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "701")["ok"]
    pend = ap.por_confirmar([entorno["a"]])
    assert len(pend) == 1 and pend[0]["codigo"] == "701" and pend[0]["total"] == 300.0
    # Solo el dueño confirma.
    assert ap.resolver_pago("ac_1", "al_1", ["cu_1"], ALUMNO, True)["error"] == "no_dueno"
    r = ap.resolver_pago("ac_1", "al_1", ["cu_1"], DUENO, True)
    assert r["ok"] and r["aceptado"]
    c = fm.filas["al_1"]["cuotas"][0]
    assert c["pagada"] and c["operacionId"] == "yape:05775701" and c["medioPago"] == "yape_directo"
    assert c["reporte"]["estado"] == "confirmado"
    assert any(p[0] == ALUMNO and "confirm" in p[1].lower() for p in pushes)
    assert any(t == "aviso" and d["para"] == ALUMNO and "Recibo" in d["titulo"] for t, d in entorno["correos"])
    assert not ap.por_confirmar([entorno["a"]])
    # Rechazo: vuelve a pendiente y se puede reportar otra vez.
    ap.reportar_pago("al_1", ALUMNO, ["cu_2"], "123")
    r = ap.resolver_pago("ac_1", "al_1", ["cu_2"], DUENO, False, "No llegó ese yapeo")
    assert r["ok"] and not r["aceptado"]
    c2 = fm.filas["al_1"]["cuotas"][1]
    assert not c2["pagada"] and c2["reporte"]["estado"] == "rechazado"
    assert ap.reportar_pago("al_1", ALUMNO, ["cu_2"], "124")["ok"]


def test_recordatorios_a_los_alumnos_una_vez_por_etapa(entorno):
    a = entorno["a"]
    # 13-oct vence cu_1: el 10-oct (3 días antes) a las 10:00 de Lima.
    t = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
    r = ap.recordatorios_alumnos(t, academias=[a])
    assert r["enviados"] == 1
    assert any(p[0] == ALUMNO and "3 días" in p[1] for p in entorno["pushes"])
    assert any(d.get("para") == ALUMNO and "987654321" in str(d.get("datos")) for _, d in entorno["correos"])
    assert ap.recordatorios_alumnos(t + timedelta(hours=1), academias=[a])["enviados"] == 0
    # Antes de las 9:00 de Lima no se manda nada.
    assert ap.recordatorios_alumnos(datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc), academias=[a])["enviados"] == 0
    assert ap.recordatorios_alumnos(datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc), academias=[a])["enviados"] == 1
    # Por confirmar → no se le recuerda.
    ap.reportar_pago("al_1", ALUMNO, ["cu_1"], "701")
    assert ap.recordatorios_alumnos(datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc), academias=[a])["enviados"] == 0
    # Sin plan vigente no hay recordatorios (beneficio del plan).
    stores.planes_academia["ac_1"]["prueba_hasta"] = "2026-10-01T00:00:00+00:00"
    entorno["fm"].filas["al_1"]["cuotas"][1]["vencimiento"] = "2026-10-17T10:00:00"
    assert ap.recordatorios_alumnos(datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc), academias=[a])["enviados"] == 0


def test_config_desde_la_torre_y_endpoints(entorno):
    from fastapi.testclient import TestClient
    import config
    import main
    c = TestClient(main.app)
    cfg = c.get("/config/academias").json()
    assert cfg["modelo"] == "suscripcion" and cfg["precios"]["PEN"] == 11.5 and cfg["prueba_dias"] == 30
    with pytest.raises(ValueError):
        ap.set_config(precios={"PEN": -1})
    ap.set_config(precios={"USD": 3, "BOB": 21}, prueba=15)
    assert ap.config_publica()["precios"]["USD"] == 3.0 and ap.prueba_dias() == 15
    import pagos.router as pr
    old = config.APP_API_KEY
    config.APP_API_KEY = ""
    try:
        e = c.get("/academias/plan/ac_1").json()
        assert e["estado"] == "prueba" and e["cobro_directo"]["yape"] == "987654321"
        r = c.post("/academias/pago-directo/reportar", json={"alumno_id": "al_1", "email": ALUMNO, "cuota_ids": ["cu_1"], "codigo": "701"}).json()
        assert r["ok"]
        p = c.get("/academias/pago-directo/pendientes", params={"email": DUENO}).json()
        assert len(p["pagos"]) == 1
        r = c.post("/academias/pago-directo/resolver", json={"academia_id": "ac_1", "alumno_id": "al_1", "email": DUENO,
                                                             "cuota_ids": ["cu_1"], "aceptar": True}).json()
        assert r["ok"]
    finally:
        config.APP_API_KEY = old
    # Modelo comisión: todo libre, como antes.
    ap.set_config(modelo_nuevo="comision")
    assert ap.estado(entorno["a"])["estado"] == "libre" and ap.beneficios(entorno["a"])
    ap.set_config(modelo_nuevo="suscripcion")
    assert pr is not None


def test_validar_yape_de_la_academia():
    assert ap.validar_cobro_directo({}) == {}
    assert ap.validar_cobro_directo({"yape": "987 654 321", "titular": "Ace SAC"}) == {"yape": "987654321", "titular": "Ace SAC"}
    with pytest.raises(ValueError):
        ap.validar_cobro_directo({"yape": "12345", "titular": "Ace"})
    with pytest.raises(ValueError):
        ap.validar_cobro_directo({"yape": "987654321", "titular": ""})
    assert ap.cobro_directo({"cobroDirecto": {"yape": "887654321"}}) is None
