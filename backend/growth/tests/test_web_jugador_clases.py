"""Mis clases y pagos en la web = `mis_clases_screen.dart` del APK (pedido del
director, 29-sep-2026: "en la web implementa las mismas funcionalidades que
existen actualmente en el app")."""
import copy
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import config
import pagos.router as pr
from db import pg
from db.store import stores
from main import app
from pagos import culqi
from web import jugador_clases as jc
from web import sesion



def _cli(monkeypatch, email="dennis@gmail.com", nombre="Dennis Calagua"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre, "foto": ""}))
    return cli


def _cuota(cid, al, ac, concepto, monto, venc, pagada=False, **kw):
    c = {"id": cid, "academiaId": ac, "alumnoId": al, "concepto": concepto, "monto": monto,
         "vencimiento": venc + "T10:00:00.000", "pagada": pagada}
    if pagada:
        c["fechaPago"] = venc + "T10:05:00.000"
        c["operacionId"] = "chr_viejo"
    c.update(kw)
    return c


ACADEMIAS = {
    "ac_a": {"id": "ac_a", "nombre": "Academia Tenis Surco", "deporte": "tenis", "dueno": "profe@gmail.com", "lat": -12.1, "lng": -77.0,
             "whatsapp": "999888777", "logoUrl": "https://x/logo.jpg", "sedeClub": "Club X", "zona": "Surco",
             "planes": [{"id": "p1", "nombre": "Adultos · 2x/sem", "horario": "Lun y Mié 19:00", "precioMes": 120}]},
    "ac_b": {"id": "ac_b", "nombre": "Academia Natación", "deporte": "natacion", "dueno": "nado@gmail.com", "lat": -12.1, "lng": -77.0},
    "ac_ec": {"id": "ac_ec", "nombre": "Academia Quito", "deporte": "tenis", "dueno": "quito@gmail.com", "lat": -0.2, "lng": -78.5},
}


def _base():
    return {
        # Yo (paga Dennis): 1 pagada + 2 pendientes (una vencida).
        "al_1": {"id": "al_1", "academiaId": "ac_a", "email": "dennis@gmail.com", "nombre": "Dennis Calagua", "cuotas": [
            _cuota("cu_1_0", "al_1", "ac_a", "Adultos · 2x/sem · Agosto", 120, "2026-08-01", pagada=True),
            _cuota("cu_1_1", "al_1", "ac_a", "Adultos · 2x/sem · Setiembre", 120, "2026-09-01"),
            _cuota("cu_1_2", "al_1", "ac_a", "Adultos · 2x/sem · Octubre", 120, "2026-10-01")]},
        # Mi hijo (paga Dennis), misma academia.
        "al_2": {"id": "al_2", "academiaId": "ac_a", "email": "dennis@gmail.com", "nombre": "Lucas Calagua", "parentesco": "hijo",
                 "apoderadoNombre": "Dennis", "ordenHermano": 2, "cuotas": [
                     _cuota("cu_2_0", "al_2", "ac_a", "Adultos · 2x/sem · Octubre (−10% familiar)", 108, "2026-10-01")]},
        # Mi esposa con correo propio (paga Dennis), otra academia.
        "al_3": {"id": "al_3", "academiaId": "ac_b", "email": "dennis@gmail.com", "emailAlumno": "maria@gmail.com", "nombre": "María López",
                 "parentesco": "familiar", "cuotas": [_cuota("cu_3_0", "al_3", "ac_b", "Natación · Octubre", 80, "2026-10-05")]},
        # Mes a mes con débito automático activo: la 2.ª ya la cobró el cron.
        "al_4": {"id": "al_4", "academiaId": "ac_a", "email": "dennis@gmail.com", "nombre": "Ana Calagua", "parentesco": "hijo", "cuotas": [
            _cuota("cu_4_0", "al_4", "ac_a", "Adultos · 2x/sem · Agosto", 120, "2026-08-10", pagada=True, autoDebito=True),
            _cuota("cu_4_1", "al_4", "ac_a", "Adultos · 2x/sem · Setiembre", 120, "2026-09-10", autoDebito=True),
            _cuota("cu_4_2", "al_4", "ac_a", "Adultos · 2x/sem · Octubre", 120, "2026-10-10", autoDebito=True)]},
        # Academia en dólares: se ve, pero se paga en la app.
        "al_5": {"id": "al_5", "academiaId": "ac_ec", "email": "dennis@gmail.com", "nombre": "Dennis Calagua", "cuotas": [
            _cuota("cu_5_0", "al_5", "ac_ec", "Tenis · Octubre", 50, "2026-10-01")]},
        # De OTRA cuenta: nunca se lista ni se toca.
        "al_x": {"id": "al_x", "academiaId": "ac_a", "email": "otro@gmail.com", "nombre": "Otro", "cuotas": [
            _cuota("cu_x_0", "al_x", "ac_a", "Adultos · Octubre", 120, "2026-10-01")]},
    }


@pytest.fixture()
def fake(monkeypatch):
    filas = _base()

    def mats(email):
        e = email.strip().lower()
        return [copy.deepcopy(m) for m in filas.values() if m["email"] == e or (m.get("emailAlumno") or "") == e]

    def marcar(alumno_id, email, marcas, reconciliadas=None):
        m = filas.get(alumno_id)
        e = email.strip().lower()
        if not m or not (m["email"] == e or (m.get("emailAlumno") or "") == e):
            return []
        return jc.aplicar_marcas(m, marcas, reconciliadas)

    monkeypatch.setattr(jc, "matriculas_de_usuario", mats)
    monkeypatch.setattr(jc, "academias_por_id", lambda ids: {i: copy.deepcopy(ACADEMIAS[i]) for i in ids if i in ACADEMIAS})
    monkeypatch.setattr(jc, "marcar_cuotas_pagadas", marcar)
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    antes_sus = dict(stores.suscripciones_alumno)
    stores.suscripciones_alumno["al_4"] = {"alumno_id": "al_4", "academia_id": "ac_a", "email": "dennis@gmail.com", "card_id": "crd_1",
                                           "estado": "activa", "monto_centimos": 12000, "proximo_cobro": "2026-10-10T10:00:00+00:00",
                                           "cobros_hechos": 1}
    antes_cfg = stores.config.get("cargo_activo_academias")
    yield filas
    stores.suscripciones_alumno.clear()
    stores.suscripciones_alumno.update(antes_sus)
    stores.config["cargo_activo_academias"] = antes_cfg if antes_cfg is not None else "0"


def _espias(monkeypatch, charge="chr_web_1"):
    cargos, conta, pushes = [], [], []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": charge})
    monkeypatch.setattr(pr, "post_matricula", lambda req: conta.append(req) or {"ok": True})
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: pushes.append(a))
    return cargos, conta, pushes


def test_sin_sesion_va_a_entrar(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app, base_url="https://testserver").get("/mis-clases", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fmis-clases"
    r = TestClient(app, base_url="https://testserver").post("/web/mis-clases/pagar", json={"token": "t", "cuotas": [{"alumno_id": "al_1", "cuota_id": "cu_1_1"}]})
    assert r.json()["error"] == "sesion_requerida"


def test_pagina_como_el_app(fake, monkeypatch):
    html = _cli(monkeypatch).get("/mis-clases").text
    # Todas mis matrículas (las que pago y la de mi esposa), nunca la de otra cuenta.
    for t in ("Academia Tenis Surco", "Academia Natación", "Academia Quito", "Alumno: Lucas Calagua · hijo(a) · 2.º de la familia",
              "Alumno: María López · familiar", "Total pagado: S/ 120.00", "Próximos pagos", "Marca las que quieres pagar.",
              "Comprobantes de pago", "https://x/logo.jpg", "📚 Adultos · 2x/sem", "🕒 Lun y Mié 19:00", "Mi familia · un solo pago"):
        assert t in html, t
    assert "Otro" not in html and "cu_x_0" not in html
    # Vencida (setiembre) y débito automático (Mes a mes activo + la cuota del cron ya figura pagada).
    assert "Vencida · venció el 1 set 2026" in html
    assert "Mes a mes activo: S/ 120.00 automático cada mes." in html and "data-cancelar-sus='al_4'" in html
    assert "Se cobra automático el 10 oct 2026" in html
    assert fake["al_4"]["cuotas"][1]["pagada"] is True  # reconciliado (1 + cobros_hechos) y guardado
    # Dólares: se ve el dato y se paga desde la app (nunca "S/" fijo).
    assert "$ 50.00" in html and "cobra en $" in html and "Pagar en la app" in html
    # Pago con Yape/tarjeta, Culqi, resumen y comprobante con modal (sin diálogos nativos).
    assert "id='medioPago'" in html and "checkout.culqi.com/js/v4" in html and "pcgResumenPago(" in html
    assert "/mis-clases/comprobante/al_1/cu_1_0" in html and "/academia/ac_a/matricula/al_1" in html
    js = html.split("window.__misClases")[1]
    assert " confirm(" not in js and "alert(" not in js and "prompt(" not in js


def test_pagar_cuotas_de_una_persona(fake, monkeypatch):
    cargos, conta, pushes = _espias(monkeypatch)
    cli = _cli(monkeypatch)
    sel = [{"alumno_id": "al_1", "cuota_id": "cu_1_1"}, {"alumno_id": "al_1", "cuota_id": "cu_1_2"}]
    # El total lo recalcula el servidor: si el navegador vio otro, no cobra.
    r = cli.post("/web/mis-clases/pagar", json={"token": "tkn_1", "cuotas": sel, "total_centimos": 1000}).json()
    assert r["error"] == "cambio" and not cargos
    r = cli.post("/web/mis-clases/pagar", json={"token": "tkn_1", "medio": "yape", "cuotas": sel, "total_centimos": 24000}).json()
    assert r["ok"] and r["charge_id"] == "chr_web_1" and "2 cuotas pagadas" in r["mensaje"]
    assert len(cargos) == 1 and cargos[0]["monto_centimos"] == 24000 and cargos[0]["moneda"] == "PEN"
    assert cargos[0]["descripcion"] == "2 cuotas · Academia Tenis Surco" and cargos[0]["cliente"]
    # = PagosService.registrarMatricula: por academia, con charge_id.
    assert len(conta) == 1 and conta[0].academia_id == "ac_a" and conta[0].monto_soles == 240
    assert conta[0].matricula_id.startswith("cuo_ac_a_") and conta[0].charge_id == "chr_web_1"
    assert conta[0].concepto == "Cuotas Academia Tenis Surco" and conta[0].cargo_servicio_centimos == 0
    # = AppState.marcarCuotaPagada.
    c1, c2 = fake["al_1"]["cuotas"][1], fake["al_1"]["cuotas"][2]
    assert c1["pagada"] and c2["pagada"] and c1["operacionId"] == c2["operacionId"] == "chr_web_1" and c1["fechaPago"]
    assert "cargoServicio" not in c1
    assert pushes and pushes[0][0] == "profe@gmail.com" and pushes[0][1] == "Cuota pagada 💰"
    pago = next(p for p in stores.pagos if p.tipo == "cobro_web" and p.culqi_charge_id == "chr_web_1")
    assert pago.concepto == "cuotas:cu_1_1,cu_1_2" and pago.monto_centimos == 24000
    # Nunca se cobra dos veces la misma cuota.
    n = len(cargos)
    r = cli.post("/web/mis-clases/pagar", json={"token": "tkn_2", "cuotas": sel}).json()
    assert r["error"] == "cambio" and "ya está pagada" in r["mensaje"] and len(cargos) == n


def test_no_se_toca_lo_ajeno_ni_otra_moneda_ni_el_debito(fake, monkeypatch):
    cargos, _conta, _p = _espias(monkeypatch)
    cli = _cli(monkeypatch)
    r = cli.post("/web/mis-clases/pagar", json={"token": "t", "cuotas": [{"alumno_id": "al_x", "cuota_id": "cu_x_0"}]}).json()
    assert r["error"] == "cambio"
    r = cli.post("/web/mis-clases/pagar", json={"token": "t", "cuotas": [{"alumno_id": "al_5", "cuota_id": "cu_5_0"}]}).json()
    assert r["error"] == "moneda" and "$" in r["mensaje"]
    r = cli.post("/web/mis-clases/pagar", json={"token": "t", "cuotas": [{"alumno_id": "al_1", "cuota_id": "cu_1_1"}, {"alumno_id": "al_5", "cuota_id": "cu_5_0"}]}).json()
    assert r["error"] == "moneda"
    r = cli.post("/web/mis-clases/pagar", json={"token": "t", "cuotas": [{"alumno_id": "al_4", "cuota_id": "cu_4_2"}]}).json()
    assert r["error"] == "cambio" and "automático" in r["mensaje"]
    assert not cargos and not fake["al_x"]["cuotas"][0]["pagada"]
    # Rechazo de la pasarela: nada queda pagado.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "fondos"})
    r = cli.post("/web/mis-clases/pagar", json={"token": "t", "cuotas": [{"alumno_id": "al_1", "cuota_id": "cu_1_1"}]}).json()
    assert r["error"] == "cargo_rechazado" and not fake["al_1"]["cuotas"][1]["pagada"]


def test_mi_familia_un_solo_pago_con_cargo_por_servicio(fake, monkeypatch):
    stores.config["cargo_activo_academias"] = "1"
    cargos, conta, _p = _espias(monkeypatch, charge="chr_fam_9")
    cli = _cli(monkeypatch)
    sel = [{"alumno_id": "al_3", "cuota_id": "cu_3_0"}, {"alumno_id": "al_2", "cuota_id": "cu_2_0"}]
    base = 10800 + 8000
    cot = pr.cotizacion_para("academias", "PEN", base, partes=[10800, 8000])
    assert cot.cargo_centimos > 0
    r = cli.post("/web/mis-clases/pagar", json={"token": "tkn_f", "cuotas": sel, "total_centimos": base + cot.cargo_centimos}).json()
    assert r["ok"] and "2 cuotas de 2 personas pagadas en un solo pago" in r["mensaje"]
    assert len(cargos) == 1 and cargos[0]["monto_centimos"] == base + cot.cargo_centimos
    assert cargos[0]["descripcion"].startswith("2 cuotas · 2 personas · Mi familia")
    # Contabilidad POR ACADEMIA con el cargo repartido (desglose/ajuste solo en la 1.ª).
    assert sorted(c.academia_id for c in conta) == ["ac_a", "ac_b"]
    assert sum(c.cargo_servicio_centimos for c in conta) == cot.cargo_centimos
    assert all(c.charge_id == "chr_fam_9" and c.concepto.endswith("· pago familiar") for c in conta)
    assert sum(1 for c in conta if c.cargo_desglose) == 1
    assert len({c.matricula_id for c in conta}) == 2
    # El cargo (uno por todo el pago) queda en la 1.ª cuota con las personas.
    c_hijo, c_esposa = fake["al_2"]["cuotas"][0], fake["al_3"]["cuotas"][0]
    assert c_hijo["pagada"] and c_esposa["pagada"] and c_hijo["operacionId"] == c_esposa["operacionId"] == "chr_fam_9"
    assert c_hijo["cargoServicio"] == round(cot.cargo_centimos / 100, 2) and c_hijo["cargoPersonas"] == 2
    assert "cargoServicio" not in c_esposa


def test_la_esposa_ve_lo_suyo_y_solo_el_pagador_corta_el_debito(fake, monkeypatch):
    html = _cli(monkeypatch, "maria@gmail.com", "María").get("/mis-clases").text
    assert "Academia Natación" in html and "Academia Tenis Surco" not in html
    r = _cli(monkeypatch, "maria@gmail.com", "María").post("/web/mis-clases/suscripcion/al_4/cancelar").json()
    assert r["ok"] is False and "al_4" in stores.suscripciones_alumno
    borradas = []
    monkeypatch.setattr(culqi, "eliminar_card", lambda c: borradas.append(c))
    r = _cli(monkeypatch).post("/web/mis-clases/suscripcion/al_4/cancelar").json()
    assert r["ok"] and "al_4" not in stores.suscripciones_alumno and borradas == ["crd_1"]


def test_comprobante_imprimible(fake, monkeypatch):
    cli = _cli(monkeypatch)
    html = cli.get("/mis-clases/comprobante/al_1/cu_1_0").text
    assert "Comprobante de pago" in html and "chr_viejo" in html and "S/ 120.00" in html and "window.print()" in html
    assert "no encontrado" in cli.get("/mis-clases/comprobante/al_x/cu_x_0").text
    assert "no encontrado" in cli.get("/mis-clases/comprobante/al_1/cu_1_1").text  # pendiente: no hay comprobante


def test_marcar_cuotas_en_la_base_solo_del_propio_correo(monkeypatch):
    """La escritura real: SELECT … FOR UPDATE filtrado por el correo y UPDATE
    del jsonb con el formato de Cuota; sin fila (ajena) no se escribe nada."""
    fila = {"id": "al_1", "cuotas": [_cuota("c0", "al_1", "ac", "Oct", 100, "2026-10-01"), _cuota("c1", "al_1", "ac", "Nov", 100, "2026-11-01", pagada=True)]}
    llamadas = []

    class Cur:
        def __init__(self):
            self.row = None

        def execute(self, sql, params):
            llamadas.append((sql, params))
            if sql.startswith("SELECT"):
                self.row = (copy.deepcopy(fila),) if params[1] == "dennis@gmail.com" else None

        def fetchone(self):
            return self.row

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            llamadas.append(("COMMIT", None))

        def rollback(self):
            llamadas.append(("ROLLBACK", None))

    @contextmanager
    def conexion():
        yield Conn()

    monkeypatch.setattr(pg, "habilitado", True)
    monkeypatch.setattr(pg, "conexion", conexion)
    marca = {"c0": {"operacionId": "chr_1", "fechaPago": "2026-09-29T10:00:00", "cargoServicio": 2, "cargoPersonas": 1},
             "c1": {"operacionId": "chr_1", "fechaPago": "x"}}
    assert jc.marcar_cuotas_pagadas("al_1", "otro@gmail.com", marca) == []
    assert not any(s.startswith("UPDATE") for s, _ in llamadas)
    assert "FOR UPDATE" in llamadas[0][0] and "emailAlumno" in llamadas[0][0]
    assert jc.marcar_cuotas_pagadas("al_1", "Dennis@Gmail.com", marca) == ["c0"]
    import json
    upd = next(p for s, p in llamadas if s.startswith("UPDATE"))
    data = json.loads(upd[0])
    assert data["cuotas"][0] == {**fila["cuotas"][0], "pagada": True, "fechaPago": "2026-09-29T10:00:00", "operacionId": "chr_1", "cargoServicio": 2.0}
    assert data["cuotas"][1]["operacionId"] == "chr_viejo"  # la ya pagada no se toca
    assert ("COMMIT", None) in llamadas
