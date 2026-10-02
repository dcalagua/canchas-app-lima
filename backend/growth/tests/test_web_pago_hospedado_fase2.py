"""COBRO WEB EN USD / BOB · FASE 2 PARTE 2 (oct-2026): matrícula de academia
(carrito familiar), cuotas de Mis clases, marketplace y bonos por la MISMA
capa de órdenes de `web/pago_hospedado.py`, con PayPhone / Libélula
simuladas (sus APIs) y la pasarela de prueba de QAS. Se prueba: total
recalculado por el servidor, lo mismo que hace Culqi tras el cargo (filas,
contabilidad en la moneda real, cobro_web, push), mes a mes SIN débito
automático, stock apartado mientras la orden vive, rechazo / vencimiento,
pago tardío (saldo o manual), cuotas que se pagaron por otro lado mientras
tanto (todo o nada con FOR UPDATE) y confirmación doble idempotente."""

import copy
import os
import sys
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import pagos.router as pr  # noqa: E402
from db import pg  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from web import datos, pago_hospedado as ph  # noqa: E402
from web import jugador_clases as jc  # noqa: E402
from web import jugador_market as jm  # noqa: E402
from test_web_pago_hospedado import BASE, _cli, _pagos, db, gw  # noqa: E402,F401  (fixtures)

AC_EC = {"nombre": "Academia Quito", "deporte": "tenis", "dueno": "profe.ec@gmail.com", "lat": -0.2, "lng": -78.5,
         "whatsapp": "991234567", "descuentoPrepago": 10, "mesesMinPrepago": 3, "descuentoHermano2": 10, "descuentoHermano3": 20,
         "planes": [{"id": "adultos", "nombre": "Adultos · 2x/sem", "programa": "Adultos", "precioMes": 60, "frecuenciaSemana": 2},
                    {"id": "ninos", "nombre": "Niños · 2x/sem", "programa": "Niños", "precioMes": 40, "frecuenciaSemana": 2}]}
AC_BO = {"nombre": "Escuela La Paz", "deporte": "futbol", "dueno": "dt.bo@gmail.com", "lat": -16.5, "lng": -68.15, "moneda": "Bs",
         "planes": [{"id": "p1", "nombre": "Mensual", "precioMes": 200}]}


@pytest.fixture
def acad(db, monkeypatch):
    """Academias y matrículas en memoria (por instancia: nada se filtra)."""
    db.academias = {"ac_ec": copy.deepcopy(AC_EC), "ac_bo": copy.deepcopy(AC_BO)}
    db.matriculas = []
    for fn in ("academia", "insertar_matricula", "matricula", "matriculas_de_pagador"):
        monkeypatch.setattr(datos, fn, getattr(db, fn))
    pushes, susc = [], []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: pushes.append(a))
    monkeypatch.setattr(pr, "post_suscripcion_alumno", lambda req: susc.append(req) or {"ok": True})
    stores.config.pop("cargo_activo_academias", None)
    yield {"db": db, "pushes": pushes, "susc": susc}
    stores.config.pop("cargo_activo_academias", None)


PERSONAS = [{"plan_id": "adultos", "nombre": "Dennis Calagua", "celular": "0991234567", "quien": "yo", "cantidad": 6, "mes_a_mes": True},
            {"plan_id": "ninos", "nombre": "Lucas Calagua", "celular": "0991234567", "quien": "hijo", "edad": 9, "cantidad": 3}]


def _volver_ec(o, tx="TX1"):
    return TestClient(app, base_url="https://testserver").get(
        f"/web/pago/{o['id']}/retorno?id={tx}&clientTransactionId={o['ref_pasarela']}", follow_redirects=False)


# ── 1) matrícula ──────────────────────────────────────────────────────────────

def test_matricula_familiar_en_dolares_por_payphone_sin_debito_automatico(acad, gw, monkeypatch):
    stores.config["cargo_activo_academias"] = "1"
    cli = _cli(monkeypatch, "dennis@gmail.com")
    html = cli.get("/academia/ac_ec").text
    # Ficha en $: la pasarela de Ecuador, sin Culqi; el mismo carrito.
    assert "Matricúlate desde la app" not in html and "checkout.culqi.com" not in html
    assert "PayPhone · tarjeta" in html and "data-medio='payphone'" in html and '"pasarela": "payphone"' in html
    assert "/web/matricular-pasarela" in html and "pcgIrPasarela" in html and "medioNombre: HOSP ? C.pasarelaNombre" in html
    assert "sin débito automático" in html
    # Culqi no cobra dólares.
    r = cli.post("/web/matricular-varios", json={"academia_id": "ac_ec", "token": "t", "personas": PERSONAS}).json()
    assert r["error"] == "usa_pasarela"
    # Validación por persona ANTES de crear la orden.
    mal = [PERSONAS[0], dict(PERSONAS[1], edad=None)]
    r = cli.post("/web/matricular-pasarela", json={"academia_id": "ac_ec", "personas": mal}).json()
    assert r["error"] == "edad" and r["persona"] == 1 and not stores.pagos_web
    p = cli.post("/web/matricular-pasarela", json={"academia_id": "ac_ec", "personas": PERSONAS}).json()
    assert p["ok"] and p["pasarela"] == "payphone" and p["url"].startswith(f"{BASE}/pagos/ec/ir/")
    o = stores.pagos_web[p["orden"]]
    # Total del servidor: 60 (mes a mes, 1.º) + 40×3 −10 % prepago −10 % familiar (2.º) = 96 → 156 + cargo.
    cg = o["accion"]["cg"]
    assert o["moneda"] == "USD" and cg["cargo_centimos"] > 0 and o["monto_centimos"] == 15600 + cg["cargo_centimos"]
    assert gw.preparados[-1]["monto_usd"] == o["monto_centimos"] / 100
    # Doble clic: la MISMA orden.
    assert cli.post("/web/matricular-pasarela", json={"academia_id": "ac_ec", "personas": PERSONAS}).json()["orden"] == o["id"]
    assert len(gw.preparados) == 1
    rr = _volver_ec(o)
    assert rr.headers["location"] == f"/web/pago/{o['id']}"
    ref = f"payphone:{o['ref_pasarela']}"
    assert o["estado"] == "aprobado" and o["accion_hecha"] and o["url_resultado"].startswith("/academia/ac_ec/matriculas?ids=")
    ms = acad["db"].matriculas
    assert len(ms) == 2 and {m["nombre"] for m in ms} == {"Dennis Calagua", "Lucas Calagua"}
    yo = next(m for m in ms if m["nombre"] == "Dennis Calagua")
    # Mes a mes SIN débito automático: 1.ª pagada, las 5 siguientes pendientes y sin autoDebito.
    assert len(yo["cuotas"]) == 6 and yo["cuotas"][0]["pagada"] and yo["cuotas"][0]["operacionId"] == ref
    assert not any(c.get("autoDebito") for c in yo["cuotas"]) and not any(c["pagada"] for c in yo["cuotas"][1:])
    assert yo["pagoWeb"]["pasarela"] == "payphone" and yo["pagoWeb"]["cargo"] == cg["cargo_centimos"] / 100
    hijo = next(m for m in ms if m["nombre"] == "Lucas Calagua")
    assert hijo["ordenHermano"] == 2 and all(c["pagada"] for c in hijo["cuotas"]) and hijo["pagoWeb"]["monto"] == 96
    assert not acad["susc"]  # nada de suscripción: no hay tarjeta guardada
    # Contabilidad en la moneda REAL (comisión de Ecuador) y cobro_web con la pasarela.
    mat = [p_ for p_ in stores.pagos if p_.tipo == "matricula_online" and p_.culqi_charge_id == ref]
    assert len(mat) == 1 and mat[0].moneda == "USD" and mat[0].monto_centimos == 15600 and mat[0].cargo_servicio_centimos == cg["cargo_centimos"]
    cobro = _pagos("cobro_web", culqi_charge_id=ref)
    assert len(cobro) == 1 and cobro[0].moneda == "USD" and cobro[0].monto_centimos == o["monto_centimos"]
    assert any(a[0] == "profe.ec@gmail.com" and "alumnos nuevos" in a[1] for a in acad["pushes"])
    # Confirmación DOBLE (retorno repetido / sondeo): nada se duplica.
    _volver_ec(o)
    ph.finalizar(o["id"])
    assert len(acad["db"].matriculas) == 2 and len(_pagos("cobro_web", culqi_charge_id=ref)) == 1
    assert len([p_ for p_ in stores.pagos if p_.tipo == "matricula_online" and p_.culqi_charge_id == ref]) == 1
    # Comprobante familiar con la pasarela y la nota de las cuotas pendientes.
    comp = cli.get(o["url_resultado"]).text
    assert "Pagado con PayPhone" in comp and "no hay débito automático" in comp and "$ " in comp


def test_matricula_bolivia_libelula_rechazo_vencimiento_y_pago_tardio(acad, gw, monkeypatch):
    cli = _cli(monkeypatch, "bo1@gmail.com")
    una = [{"plan_id": "p1", "nombre": "Bo Uno", "celular": "71234567", "quien": "yo", "cantidad": 1}]
    html = cli.get("/academia/ac_bo").text
    assert "Libélula · QR o tarjeta" in html and "checkout.culqi.com" not in html
    # Cancelación en la pasarela: no se matricula nada.
    o = stores.pagos_web[cli.post("/web/matricular-pasarela", json={"academia_id": "ac_bo", "personas": una}).json()["orden"]]
    assert o["moneda"] == "BOB" and o["monto_centimos"] == 20000 and gw.deudas[-1]["monto_bs"] == 200
    cli.get(f"/web/pago/{o['id']}/cancelado", follow_redirects=False)
    assert o["estado"] == "cancelado" and not acad["db"].matriculas
    # Callback de Libélula (el cliente cerró la pestaña): se matricula igual.
    o2 = stores.pagos_web[cli.post("/web/matricular-pasarela", json={"academia_id": "ac_bo", "personas": una}).json()["orden"]]
    assert o2["id"] != o["id"]
    gw.lib_pagadas.add(o2["ref_pasarela"])
    tx = stores.libelula_deudas[o2["ref_pasarela"]]["id_transaccion"]
    assert TestClient(app).get(f"/pagos/bo/callback?transaction_id={tx}").json() == {"ok": True}
    assert o2["estado"] == "aprobado" and len(acad["db"].matriculas) == 1
    mat = [p_ for p_ in stores.pagos if p_.tipo == "matricula_online" and p_.culqi_charge_id == f"libelula:{o2['ref_pasarela']}"]
    assert len(mat) == 1 and mat[0].moneda == "BOB"
    # Vence sin pagar → vencida; Libélula avisa DESPUÉS (pago tardío): nunca se matricula.
    o3 = stores.pagos_web[cli.post("/web/matricular-pasarela", json={"academia_id": "ac_bo", "personas": [dict(una[0], nombre="Bo Tres")]}).json()["orden"]]
    o3["vence_ts"] = time.time() - 1
    ph.barrer()
    assert o3["estado"] == "vencido"
    gw.lib_pagadas.add(o3["ref_pasarela"])
    TestClient(app).get(f"/pagos/bo/callback?transaction_id={stores.libelula_deudas[o3['ref_pasarela']]['id_transaccion']}")
    assert o3["estado"] == "aprobado_sin_reserva" and len(acad["db"].matriculas) == 1
    # Billetera de bo1 en soles (sin país de casa) → devolución MANUAL al operador.
    assert o3["devolucion"] == "manual"
    cw = stores.cancelaciones_web[-1]
    assert cw["tipo"] == "matricula" and cw["motivo"] == "pago_tardio" and cw["moneda_iso"] == "BOB" and cw["reembolso"] == "manual"
    pag = cli.get(f"/web/pago/{o3['id']}").text
    assert "llegó tarde" in pag and "Volver a la academia" in pag
    # No aparece como reserva cancelada en Mis reservas (no es una cancha).
    assert "Matrícula Escuela La Paz" not in cli.get("/mis-reservas").text
    # Con la billetera en Bs, el pago tardío vuelve a su SALDO.
    bo = "bo2@gmail.com"
    stores.clientes_pago[bo] = {"pais_casa": "BO", "pais_casa_en": datetime.now(timezone.utc).isoformat()}
    stores.saldos.pop(bo, None)
    cb = _cli(monkeypatch, bo)
    o4 = stores.pagos_web[cb.post("/web/matricular-pasarela", json={"academia_id": "ac_bo", "personas": [dict(una[0], nombre="Bo Cuatro")]}).json()["orden"]]
    o4["vence_ts"] = time.time() - 1
    ph.barrer()
    gw.lib_pagadas.add(o4["ref_pasarela"])
    o4["ult_consulta"] = 0
    ph.barrer()  # sin callback: el barrido le pregunta a Libélula
    assert o4["estado"] == "aprobado_sin_reserva" and o4["devolucion"] == "saldo" and stores.saldo_centimos(bo) == 20000


def test_prd_sin_credenciales_todo_sigue_en_la_app(acad, gw, monkeypatch):
    monkeypatch.setattr(config, "PAYPHONE_TOKEN", "")
    monkeypatch.setattr(config, "LIBELULA_APPKEY", "")
    monkeypatch.setattr(config, "PICHANGOL_ENTORNO", "PRD")
    cli = _cli(monkeypatch, "dennis@gmail.com")
    assert "Matricúlate desde la app" in cli.get("/academia/ac_ec").text
    r = cli.post("/web/matricular-pasarela", json={"academia_id": "ac_ec", "personas": PERSONAS}).json()
    assert r["ok"] is False and r["error"] == "moneda" and not stores.pagos_web
    monkeypatch.setattr(jm, "producto", lambda pid: _prod())
    html = cli.get("/marketplace/prod_ec").text
    assert "Cómpralo en la app" in html and "comprar-pasarela" not in html
    assert cli.post("/web/marketplace/comprar-pasarela", json={"producto_id": "prod_ec"}).json()["error"] == "moneda"


def test_qas_sin_credenciales_matricula_con_la_pasarela_simulada(acad, monkeypatch):
    monkeypatch.setattr(config, "PAYPHONE_TOKEN", "")
    monkeypatch.setattr(config, "LIBELULA_APPKEY", "")
    monkeypatch.setattr(config, "PICHANGOL_ENTORNO", "QAS")
    cli = _cli(monkeypatch, "dennis@gmail.com")
    assert "Pago de prueba · QAS" in cli.get("/academia/ac_ec").text
    p = cli.post("/web/matricular-pasarela", json={"academia_id": "ac_ec", "personas": PERSONAS[:1]}).json()
    assert p["ok"] and p["url"] == f"/web/pago/{p['orden']}/simulado"
    j = cli.post(f"/web/pago/{p['orden']}/simulado", json={"aprobar": True}).json()
    assert j["estado"] == "aprobado" and j["url"].startswith("/academia/ac_ec/matricula/al_")
    m = acad["db"].matriculas[0]
    assert m["cuotas"][0]["operacionId"] == f"sim:{p['orden']}" and m["pagoWeb"]["pasarela"] == "sim"
    assert "Pagado con la pasarela de prueba (QAS)" in cli.get(j["url"]).text


# ── 2) cuotas de Mis clases ───────────────────────────────────────────────────

def _cuota(cid, al, ac, concepto, monto, venc, **kw):
    return {"id": cid, "academiaId": ac, "alumnoId": al, "concepto": concepto, "monto": monto,
            "vencimiento": venc + "T10:00:00.000", "pagada": False, **kw}


@pytest.fixture
def clases(db, monkeypatch):
    acs = {"ac_ec": dict(AC_EC, id="ac_ec"), "ac_ec2": dict(AC_EC, id="ac_ec2", nombre="Pádel Quito", dueno="padel.ec@gmail.com", deporte="padel")}
    filas = {
        "al_1": {"id": "al_1", "academiaId": "ac_ec", "email": "dennis@gmail.com", "nombre": "Dennis Calagua", "cuotas": [
            _cuota("cu_1_1", "al_1", "ac_ec", "Adultos · Noviembre", 60, "2026-11-01"),
            _cuota("cu_1_2", "al_1", "ac_ec", "Adultos · Diciembre", 60, "2026-12-01")]},
        "al_2": {"id": "al_2", "academiaId": "ac_ec2", "email": "dennis@gmail.com", "nombre": "Lucas Calagua", "parentesco": "hijo",
                 "cuotas": [_cuota("cu_2_1", "al_2", "ac_ec2", "Pádel · Noviembre", 40, "2026-11-05")]},
    }

    def mats(email):
        e = email.strip().lower()
        return [copy.deepcopy(m) for m in filas.values() if m["email"] == e]

    def marcar(alumno_id, email, marcas, reconciliadas=None):
        m = filas.get(alumno_id)
        return jc.aplicar_marcas(m, marcas, reconciliadas) if m else []

    llamadas = []

    def atomico(email, pedidas, sus_activas, operacion, ahora, extras):
        llamadas.append(operacion)
        return jc.aplicar_pago_atomico(filas, pedidas, sus_activas, operacion, ahora, extras)

    monkeypatch.setattr(jc, "matriculas_de_usuario", mats)
    monkeypatch.setattr(jc, "academias_por_id", lambda ids: {i: copy.deepcopy(acs[i]) for i in ids if i in acs})
    monkeypatch.setattr(jc, "marcar_cuotas_pagadas", marcar)
    monkeypatch.setattr(jc, "marcar_cuotas_atomico", atomico)
    conta, pushes = [], []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: pushes.append(a))
    stores.config.pop("cargo_activo_academias", None)
    yield {"filas": filas, "conta": conta, "pushes": pushes, "atomico": llamadas}
    stores.config.pop("cargo_activo_academias", None)


def test_cuotas_en_dolares_familia_un_solo_pago_por_payphone(clases, gw, monkeypatch):
    stores.config["cargo_activo_academias"] = "1"
    cli = _cli(monkeypatch, "dennis@gmail.com")
    html = cli.get("/mis-clases").text
    assert "Pagar en la app" not in html and "data-pasarela='payphone'" in html and "Pagas con PayPhone · tarjeta" in html
    assert "checkout.culqi.com" not in html and "id='medioPago'" not in html and "pcgIrPasarela" in html
    sel = [{"alumno_id": "al_1", "cuota_id": "cu_1_1"}, {"alumno_id": "al_1", "cuota_id": "cu_1_2"}, {"alumno_id": "al_2", "cuota_id": "cu_2_1"}]
    # Culqi no cobra dólares.
    assert cli.post("/web/mis-clases/pagar", json={"token": "t", "cuotas": sel}).json()["error"] == "usa_pasarela"
    # El total lo recalcula el servidor.
    assert cli.post("/web/mis-clases/pagar-pasarela", json={"cuotas": sel, "total_centimos": 5}).json()["error"] == "cambio"
    p = cli.post("/web/mis-clases/pagar-pasarela", json={"cuotas": sel}).json()
    assert p["ok"] and p["pasarela"] == "payphone"
    o = stores.pagos_web[p["orden"]]
    cg = o["accion"]["cg"]
    assert o["moneda"] == "USD" and cg["cargo_centimos"] > 0 and o["monto_centimos"] == 16000 + cg["cargo_centimos"]
    # Otra orden con una cuota que ya está en un pago en curso: no.
    r = cli.post("/web/mis-clases/pagar-pasarela", json={"cuotas": sel[:1]}).json()
    assert r["error"] == "en_curso" and r["url"] == f"/web/pago/{o['id']}"
    # La misma selección: la misma orden.
    assert cli.post("/web/mis-clases/pagar-pasarela", json={"cuotas": sel}).json()["orden"] == o["id"]
    _volver_ec(o)
    ref = f"payphone:{o['ref_pasarela']}"
    assert o["estado"] == "aprobado" and o["url_resultado"] == f"/mis-clases?pagado={o['id']}"
    f = clases["filas"]
    c11, c12, c21 = f["al_1"]["cuotas"][0], f["al_1"]["cuotas"][1], f["al_2"]["cuotas"][0]
    assert c11["pagada"] and c12["pagada"] and c21["pagada"] and c11["operacionId"] == c21["operacionId"] == ref
    # El cargo, uno por todo el pago, en la 1.ª cuota (= marcarCuotaPagada).
    assert c11["cargoServicio"] == cg["cargo_centimos"] / 100 and c11["cargoPersonas"] == 2 and "cargoServicio" not in c21
    # Contabilidad por academia en USD con su parte del cargo.
    mats = [p_ for p_ in stores.pagos if p_.tipo == "matricula_online" and p_.cargo_id == ref]
    assert {m.dueno_id for m in mats} == {"ac_ec", "ac_ec2"} and all(m.moneda == "USD" for m in mats)
    assert sum(m.monto_centimos for m in mats) == 16000 and sum(m.cargo_servicio_centimos for m in mats) == cg["cargo_centimos"]
    assert len(_pagos("cobro_web", culqi_charge_id=ref)) == 1
    assert sum(1 for a in clases["pushes"] if a[1] == "Cuota pagada 💰") == 3
    # Aviso al volver.
    assert "3 cuotas de 2 personas pagadas" in cli.get(o["url_resultado"]).text
    # Doble confirmación: nada se duplica.
    _volver_ec(o)
    ph.finalizar(o["id"])
    assert len([p_ for p_ in stores.pagos if p_.tipo == "matricula_online" and p_.cargo_id == ref]) == 2
    assert len(_pagos("cobro_web", culqi_charge_id=ref)) == 1


def test_cuotas_pagadas_por_otro_lado_mientras_paga_se_devuelven(clases, gw, monkeypatch):
    cli = _cli(monkeypatch, "dennis@gmail.com")
    sel = [{"alumno_id": "al_1", "cuota_id": "cu_1_1"}, {"alumno_id": "al_1", "cuota_id": "cu_1_2"}]
    o = stores.pagos_web[cli.post("/web/mis-clases/pagar-pasarela", json={"cuotas": sel}).json()["orden"]]
    # Mientras paga en PayPhone, el profe (o la app) marcó la de diciembre como pagada.
    clases["filas"]["al_1"]["cuotas"][1].update(pagada=True, operacionId="efectivo_profe")
    _volver_ec(o)
    # TODO O NADA: la de noviembre NO quedó pagada con este cobro; el pago se devuelve.
    assert not clases["filas"]["al_1"]["cuotas"][0]["pagada"]
    assert o["estado"] == "aprobado_sin_reserva" and o["devolucion_motivo"] == "cuotas_ya_pagadas" and o["devolucion"] == "manual"
    cw = stores.cancelaciones_web[-1]
    assert cw["tipo"] == "cuotas" and cw["moneda_iso"] == "USD" and cw["monto_devuelto_centimos"] == o["monto_centimos"]
    assert not [p_ for p_ in stores.pagos if p_.tipo == "matricula_online" and p_.cargo_id == f"payphone:{o['ref_pasarela']}"]
    pag = cli.get(f"/web/pago/{o['id']}").text
    assert "esas cuotas ya estaban pagadas" in pag and "Volver a Mis clases" in pag
    # Rechazo de PayPhone: nada se marca y la cuota queda libre para otro pago.
    gw.aprobar = False
    o2 = stores.pagos_web[cli.post("/web/mis-clases/pagar-pasarela", json={"cuotas": sel[:1]}).json()["orden"]]
    _volver_ec(o2, "TXR")
    assert o2["estado"] == "rechazado" and not clases["filas"]["al_1"]["cuotas"][0]["pagada"]
    gw.aprobar = True
    assert cli.post("/web/mis-clases/pagar-pasarela", json={"cuotas": sel[:1]}).json()["ok"]


def test_marcado_atomico_de_cuotas_en_la_base(monkeypatch):
    """SQL de `marcar_cuotas_atomico`: bloquea todas las filas (FOR UPDATE,
    en orden), solo del correo, y si una cuota cambió no escribe nada."""
    ejecutadas, estado = [], {"commit": 0, "rollback": 0}
    filas = {"al_a": {"cuotas": [{"id": "c1", "monto": 10, "pagada": False}]},
             "al_b": {"cuotas": [{"id": "c2", "monto": 20, "pagada": False, "autoDebito": True}]}}

    class Cur:
        def execute(self, sql, params):
            ejecutadas.append((" ".join(sql.split()), params))

        def fetchall(self):
            import json
            return [(k, json.dumps(v)) for k, v in sorted(filas.items())]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            estado["commit"] += 1

        def rollback(self):
            estado["rollback"] += 1

    from contextlib import contextmanager

    @contextmanager
    def conexion():
        yield Conn()

    monkeypatch.setattr(pg, "habilitado", True)
    monkeypatch.setattr(pg, "conexion", conexion)
    ped = [{"alumno_id": "al_b", "cuota_id": "c2", "monto": 20}, {"alumno_id": "al_a", "cuota_id": "c1", "monto": 10}]
    # Débito automático ACTIVO en al_b: conflicto, no se escribe nada.
    r = jc.marcar_cuotas_atomico("Dennis@gmail.com", ped, {"al_b"}, "payphone:x", "2026-10-02T10:00:00", {"c1": {"cargoServicio": 1.5}})
    assert r["ok"] is False and r["conflictos"] == [{"cuota": "c2", "motivo": "debito_automatico"}] and estado == {"commit": 0, "rollback": 1}
    sel = ejecutadas[0]
    assert "FOR UPDATE" in sel[0] and "ORDER BY id" in sel[0] and sel[1] == (["al_a", "al_b"], "dennis@gmail.com", "dennis@gmail.com")
    ejecutadas.clear()
    r = jc.marcar_cuotas_atomico("dennis@gmail.com", ped, set(), "payphone:x", "2026-10-02T10:00:00", {"c1": {"cargoServicio": 1.5}})
    assert r["ok"] and sorted(r["hechas"]) == ["c1", "c2"] and estado["commit"] == 1
    upd = [x for x in ejecutadas if x[0].startswith("UPDATE")]
    assert len(upd) == 2 and '"cargoServicio": 1.5' in [u for u in upd if u[1][1] == "al_a"][0][1][0]
    # Base caída → None (la orden se reintenta, nunca se devuelve por un error de red).

    @contextmanager
    def rota():
        raise RuntimeError("sin conexión")
        yield  # noqa

    monkeypatch.setattr(pg, "conexion", rota)
    assert jc.marcar_cuotas_atomico("dennis@gmail.com", ped, set(), "payphone:x", "t", {}) is None
    # Monto distinto al cobrado → conflicto; reintento con la misma operación → ok sin cambios.
    fl = {"al_a": {"cuotas": [{"id": "c1", "monto": 12, "pagada": False}, {"id": "c3", "monto": 5, "pagada": True, "operacionId": "op"}]}}
    assert jc.aplicar_pago_atomico(fl, [{"alumno_id": "al_a", "cuota_id": "c1", "monto": 10}], set(), "op", "t", {})["conflictos"][0]["motivo"] == "monto"
    r = jc.aplicar_pago_atomico(fl, [{"alumno_id": "al_a", "cuota_id": "c3", "monto": 5}], set(), "op", "t", {})
    assert r["ok"] and r["cambiadas"] == []


# ── 3) marketplace ────────────────────────────────────────────────────────────

def _prod(**kw):
    p = {"id": "prod_ec", "vendedor_email": "vende.ec@gmail.com", "vendedor_nombre": "Tienda Quito", "nombre": "Raqueta Head",
         "descripcion": "Nueva", "precio": 80.0, "moneda": "$", "categoria": "raquetas", "foto_url": "", "stock": 1, "activo": True,
         "creado_en": datetime.now(timezone.utc).isoformat()}
    p.update(kw)
    return p


@pytest.fixture
def market(monkeypatch):
    st = {"prod": _prod(), "apartados": 0, "devueltos": 0}

    def apartar(pid):
        p = st["prod"]
        if not p["activo"] or (p["stock"] is not None and p["stock"] <= 0):
            return False
        if p["stock"] is not None:
            p["stock"] -= 1
        st["apartados"] += 1
        return True

    def devolver(pid):
        if st["prod"]["stock"] is not None:
            st["prod"]["stock"] += 1
        st["devueltos"] += 1

    monkeypatch.setattr(jm, "producto", lambda pid: dict(st["prod"]) if pid == st["prod"]["id"] else None)
    monkeypatch.setattr(jm, "apartar_unidad", apartar)
    monkeypatch.setattr(jm, "devolver_unidad", devolver)
    monkeypatch.setattr(jm, "perfiles", lambda es: {})
    monkeypatch.setattr(datos, "esta_verificado", lambda e: True)
    monkeypatch.setattr(datos, "celular_de_perfil", lambda e: "")
    antes = list(stores.ventas)
    yield st
    stores.ventas[:] = antes


def test_marketplace_en_dolares_aparta_la_unidad_mientras_paga(db, gw, market, monkeypatch):
    cli = _cli(monkeypatch, "compra@gmail.com")
    html = cli.get("/marketplace/prod_ec").text
    assert "Cómpralo en la app" not in html and "PayPhone · tarjeta" in html and "checkout.culqi.com" not in html
    assert "/web/marketplace/comprar-pasarela" in html and "pcgIrPasarela" in html
    assert cli.post("/web/marketplace/comprar", json={"producto_id": "prod_ec", "token": "t"}).json()["error"] == "usa_pasarela"
    p = cli.post("/web/marketplace/comprar-pasarela", json={"producto_id": "prod_ec"}).json()
    o = stores.pagos_web[p["orden"]]
    # La unidad quedó APARTADA antes de ir a la pasarela; el doble clic no aparta otra.
    assert market["prod"]["stock"] == 0 and market["apartados"] == 1 and o["monto_centimos"] == 8000 and o["moneda"] == "USD"
    assert cli.post("/web/marketplace/comprar-pasarela", json={"producto_id": "prod_ec"}).json()["orden"] == o["id"]
    assert market["apartados"] == 1
    # Otro comprador ya no la consigue (agotada mientras Ana paga).
    otro = _cli(monkeypatch, "otro@gmail.com")
    assert otro.post("/web/marketplace/comprar-pasarela", json={"producto_id": "prod_ec"}).json()["error"] == "agotado"
    # Ana cancela en PayPhone: la unidad vuelve al stock (una sola vez).
    cli.get(f"/web/pago/{o['id']}/cancelado", follow_redirects=False)
    ph.rechazar(o["id"], "cancelado")
    assert o["estado"] == "cancelado" and market["prod"]["stock"] == 1 and market["devueltos"] == 1
    assert "la unidad volvió a estar disponible" in cli.get(f"/web/pago/{o['id']}").text
    # Compra que vence sin pagar: también vuelve.
    o2 = stores.pagos_web[cli.post("/web/marketplace/comprar-pasarela", json={"producto_id": "prod_ec"}).json()["orden"]]
    assert market["prod"]["stock"] == 0
    o2["vence_ts"] = time.time() - 1
    ph.barrer()
    assert o2["estado"] == "vencido" and market["prod"]["stock"] == 1 and market["devueltos"] == 2
    # Compra aprobada: venta en escrow en USD (comisión con el mínimo del dólar) + cobro_web + push.
    o3 = stores.pagos_web[cli.post("/web/marketplace/comprar-pasarela", json={"producto_id": "prod_ec"}).json()["orden"]]
    _volver_ec(o3, "TXM")
    ref = f"payphone:{o3['ref_pasarela']}"
    venta = stores.pago_por_charge(ref)
    assert o3["estado"] == "aprobado" and venta.tipo == "venta_producto" and venta.moneda == "USD" and venta.monto_centimos == 8000
    assert stores.ventas[-1].producto_id == "prod_ec" and stores.ventas[-1].comprador_email == "compra@gmail.com"
    assert o3["url_resultado"] == f"/mis-ordenes?nueva={stores.ventas[-1].id}"
    assert market["prod"]["stock"] == 0 and market["devueltos"] == 2  # vendida: no vuelve
    assert len(_pagos("cobro_web", culqi_charge_id=ref)) == 1
    # Confirmación doble y un rechazo posterior no tocan nada.
    n = len(stores.ventas)
    _volver_ec(o3, "TXM")
    ph.finalizar(o3["id"])
    ph.rechazar(o3["id"])
    assert len(stores.ventas) == n and market["devueltos"] == 2 and len(_pagos("cobro_web", culqi_charge_id=ref)) == 1


def test_marketplace_bolivia_pago_tardio_no_inventa_la_venta(db, gw, market, monkeypatch):
    market["prod"].update(moneda="Bs", precio=300.0, stock=None)  # stock ilimitado
    cli = _cli(monkeypatch, "compra@gmail.com")
    o = stores.pagos_web[cli.post("/web/marketplace/comprar-pasarela", json={"producto_id": "prod_ec"}).json()["orden"]]
    assert o["pasarela"] == "libelula" and o["moneda"] == "BOB"
    o["vence_ts"] = time.time() - 1
    ph.barrer()
    assert o["estado"] == "vencido"
    n = len(stores.ventas)
    gw.lib_pagadas.add(o["ref_pasarela"])
    TestClient(app).get(f"/pagos/bo/callback?transaction_id={stores.libelula_deudas[o['ref_pasarela']]['id_transaccion']}")
    assert o["estado"] == "aprobado_sin_reserva" and len(stores.ventas) == n and stores.pago_por_charge(f"libelula:{o['ref_pasarela']}").tipo == "cobro_web"
    assert stores.cancelaciones_web[-1]["tipo"] == "market" and stores.cancelaciones_web[-1]["reembolso"] == "manual"


# ── 4) bonos ──────────────────────────────────────────────────────────────────

def test_bono_en_bolivianos_con_la_pasarela_simulada_de_qas(db, monkeypatch):
    monkeypatch.setattr(config, "PAYPHONE_TOKEN", "")
    monkeypatch.setattr(config, "LIBELULA_APPKEY", "")
    monkeypatch.setattr(config, "PICHANGOL_ENTORNO", "QAS")
    db.canchas["c_lp"]["dueno"] = "dueno.lp@gmail.com"
    db.canchas["c_lp"]["verificada"] = True
    oferta = {"id": "of_1", "dueno": "dueno.lp@gmail.com", "club": "Club Altura", "nombre": "Pack 5 h", "horas": 5, "precio": 150.0, "activo": True}
    creditos = {}
    monkeypatch.setattr(jm, "oferta", lambda oid: dict(oferta) if oid == "of_1" else None)
    monkeypatch.setattr(jm, "ofertas_de_local", lambda club, dueno: [dict(oferta)])
    monkeypatch.setattr(jm, "bonos_de", lambda e: [])
    monkeypatch.setattr(jm, "registrar_bono", lambda f: creditos.setdefault(f["id"], f) is not None)
    monkeypatch.setattr(datos, "celular_de_perfil", lambda e: "")
    cli = _cli(monkeypatch, "jugador.bo@gmail.com")
    html = cli.get("/bonos/c_lp").text
    assert "Pago de prueba · QAS" in html and "/web/bonos/comprar-pasarela" in html and "checkout.culqi.com" not in html
    assert cli.post("/web/bonos/comprar", json={"cancha_id": "c_lp", "oferta_id": "of_1", "token": "t"}).json()["error"] == "usa_pasarela"
    p = cli.post("/web/bonos/comprar-pasarela", json={"cancha_id": "c_lp", "oferta_id": "of_1"}).json()
    o = stores.pagos_web[p["orden"]]
    assert o["moneda"] == "BOB" and o["monto_centimos"] == 15000 and p["url"] == f"/web/pago/{o['id']}/simulado"
    j = cli.post(f"/web/pago/{o['id']}/simulado", json={"aprobar": True}).json()
    ref = f"sim:{o['id']}"
    assert j["estado"] == "aprobado" and j["url"] == f"/mis-bonos?nuevo=bono_{ref}"
    assert creditos[f"bono_{ref}"]["horas_total"] == 5 and creditos[f"bono_{ref}"]["comprador"] == "jugador.bo@gmail.com"
    venta = stores.pago_por_charge(ref)
    assert venta.tipo == "venta_producto" and venta.moneda == "BOB" and venta.dueno_id == "dueno.lp@gmail.com"
    # Idempotente: otra aprobación / finalización no duplica el crédito ni la venta.
    cli.post(f"/web/pago/{o['id']}/simulado", json={"aprobar": True})
    ph.finalizar(o["id"])
    assert len(creditos) == 1 and len([x for x in stores.pagos if x.culqi_charge_id == ref and x.tipo == "venta_producto"]) == 1
    assert len(_pagos("cobro_web", culqi_charge_id=ref)) == 1
