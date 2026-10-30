"""APP = WEB en bono, puntos y pozo (1-oct-2026, "alinea el APK y el backend
compartido para que app y web se comporten igual"):

* Una reserva con BONO hecha en el APK que se cancela DESDE EL APK
  (`/pagos/reserva/cancelar`, el mismo motor `_cancelar_reserva` de la web)
  devuelve las horas a tiempo; los servicios extra que el APK ahora cobra en
  línea vuelven como plata y la liquidación del dueño se anula. Un APK viejo
  que dejó los extras SIN cobrar no recibe plata que nunca pagó.
* Puntos canjeados en el APK (escritos directo en `pichangol_puntos_canjes`
  con `<cancha>_<fecha>_<hora>`): la devolución nunca supera lo pagado y los
  100 puntos vuelven (fila −100) solo si la cancelación tiene devolución.
* Pozo del equipo: el saldo en otra moneda no paga la cuota (`moneda_distinta`,
  nada cobrado), igual por el APK que por la web.
"""
import os
import sys
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi, devoluciones, pozos  # noqa: E402
import pagos.router as pr  # noqa: E402
from web import datos, router as web  # noqa: E402
from test_web_bono_puntos import FakeDBBen, _FNS  # noqa: E402

DUENO = "duenobono@gmail.com"


class FakeDBAlin(FakeDBBen):
    def puntos_canje_neto(self, email, refs, desde=None):
        devs = {"devolucion:" + r for r in refs}
        filas = [x for x in self.puntos_canjes if x["email"] == email.lower()
                 and (x["referencia"] in refs or x["referencia"] in devs)
                 and (desde is None or x.get("creado", time.time()) >= desde)]
        return max(sum(x["puntos"] for x in filas), 0), max(sum(x["soles"] for x in filas), 0.0)

    def puntos_devolver_neto(self, email, refs, ref_dev, desde=None):
        pts, soles = self.puntos_canje_neto(email, refs, desde)
        if pts <= 0:
            return 0
        self.puntos_canjes.append({"email": email.lower(), "puntos": -pts, "soles": -soles,
                                   "referencia": "devolucion:" + ref_dev, "creado": time.time()})
        return pts


@pytest.fixture
def db(monkeypatch):
    fake = FakeDBAlin()
    for fn in _FNS + ("puntos_canje_neto", "puntos_devolver_neto"):
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    stores.config.pop("cargo_activo_reservas", None)
    yield fake


def _lejos() -> str:
    d_min, _ = web._fechas_validas("PE")
    return (date.fromisoformat(d_min) + timedelta(days=3)).isoformat()


def _fila(db, rid, email, hora="15:00", medio="bono", extras=None, grupo="", fecha=None):
    fin = f"{int(hora[:2]) + 1:02d}:00"
    db.reservas[rid] = {"id": rid, "cancha_id": "c_b1", "fecha": fecha or _lejos(), "hora_inicio": hora, "hora_fin": fin,
                        "estado": "confirmada", "pagado": True, "usuario": email, "medio_pago": medio, "precio": 60,
                        "grupo_reserva_id": grupo, "extras": list(extras or []), "sena": 0, "moneda": "S/",
                        "jugador": "Ana", "cargo_servicio": 0, "cargo_desglose": []}


def _id_app() -> str:
    return f"jug_{int(time.time() * 1000)}"


def test_cancelar_bono_desde_el_app_devuelve_horas(db):
    cli = TestClient(app, base_url="https://testserver")
    email = "apkbono@gmail.com"
    db.credito("bono_x", email, 5, usadas=2)
    a, b = _id_app() + "_1", _id_app() + "_2"
    _fila(db, a, email, "15:00", grupo="grp_apk1"); _fila(db, b, email, "16:00", grupo="grp_apk1")
    est = cli.get("/pagos/reserva/cancelacion/grp_apk1", params={"email": email}).json()
    assert est["puede"] and est["reembolsable"] and est["bono_horas"] == 2 and est["monto"] == 0
    assert est["politica"]["opciones"] == []  # sin plata de por medio: solo horas
    j = cli.post("/pagos/reserva/cancelar", json={"ref": "grp_apk1", "email": email, "medio": "saldo"}).json()
    assert j["ok"] and j["reembolso"] == "bono" and j["bono_horas_devueltas"] == 2, j
    assert db.creditos["bono_x"]["horas_usadas"] == 0 and a not in db.reservas and b not in db.reservas
    assert stores.pago_por_charge("dev:grp_apk1") is None  # nada de plata a saldo
    # Tarde: no vuelve nada (misma política que el dinero y que la web).
    c = _id_app() + "_3"
    _fila(db, c, email, "18:00")
    db.creditos["bono_x"]["horas_usadas"] = 1
    import config as _cfg
    try:
        _cfg.WEB_CANCELACION_HORAS, viejo = 10_000, _cfg.WEB_CANCELACION_HORAS
        j = cli.post("/pagos/reserva/cancelar", json={"ref": c, "email": email, "medio": "saldo"}).json()
    finally:
        _cfg.WEB_CANCELACION_HORAS = viejo
    assert j["ok"] and j["reembolso"] == "sin_reembolso" and j["bono_horas_devueltas"] == 0
    assert db.creditos["bono_x"]["horas_usadas"] == 1


def test_bono_con_extras_del_app_cobrados_y_apk_viejo_sin_cobro(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    email = "apkextras@gmail.com"
    db.credito("bono_y", email, 3, usadas=1)
    refunds = []
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: refunds.append(kw) or {"ok": True, "refund_id": "rf_1"})
    monkeypatch.setattr(devoluciones, "ARREPENTIMIENTO_HORAS", -1)
    # (1) APK nuevo: la hora va con el bono, el pelotero (S/ 10) se cobró en
    # línea y se liquidó al dueño SOLO el extra, con el cargo ligado.
    rid = _id_app() + "_1"
    _fila(db, rid, email, "15:00", extras=[{"clave": "pelotero", "precio": 10}])
    stores.registrar_pago(tipo="reserva", monto_centimos=1000, moneda="PEN", estado="aprobado", email=email,
                          culqi_charge_id="chr_bono_x", concepto="Servicios extra (bono)")
    pr.post_liquidacion_online(pr.LiquidacionOnlineReq(dueno_id=DUENO, monto_soles=10.0, reserva_id=rid, medio="yape",
                                                       moneda="PEN", charge_id="chr_bono_x"))
    liq = stores.pago_por_charge(rid)
    est = cli.get(f"/pagos/reserva/cancelacion/{rid}", params={"email": email}).json()
    assert est["monto"] == 10 and est["bono_horas"] == 1 and est["reembolso_directo"]
    j = cli.post("/pagos/reserva/cancelar", json={"ref": rid, "email": email, "medio": "original"}).json()
    assert j["ok"] and j["reembolso"] == "reembolsado" and j["monto_devuelto"] == 10.0 and j["bono_horas_devueltas"] == 1, j
    assert refunds[-1] == {"charge_id": "chr_bono_x", "monto_centimos": 1000}
    assert liq.estado == "anulado" and db.creditos["bono_y"]["horas_usadas"] == 0
    # (2) APK viejo: el extra quedó en la fila SIN cobrarse (no hay cargo ni
    # liquidación) → no hay plata que devolver, solo la hora del bono.
    db.creditos["bono_y"]["horas_usadas"] = 1
    rid2 = _id_app() + "_2"
    _fila(db, rid2, email, "17:00", extras=[{"clave": "pelotero", "precio": 10}])
    saldo0 = stores.saldo_centimos(email)
    est = cli.get(f"/pagos/reserva/cancelacion/{rid2}", params={"email": email}).json()
    assert est["monto"] == 0 and est["total_pagado"] == 0 and est["politica"]["opciones"] == []
    j = cli.post("/pagos/reserva/cancelar", json={"ref": rid2, "email": email, "medio": "saldo"}).json()
    assert j["ok"] and j["reembolso"] == "bono" and j["bono_horas_devueltas"] == 1
    assert stores.saldo_centimos(email) == saldo0 and stores.pago_por_charge(f"dev:{rid2}") is None


def test_puntos_del_app_devolucion_tope_y_puntos_de_vuelta(db, monkeypatch):
    stores.config["cargo_activo_reservas"] = "1"
    cli = TestClient(app, base_url="https://testserver")
    email = "apkpuntos@gmail.com"
    monkeypatch.setattr(devoluciones, "ARREPENTIMIENTO_HORAS", -1)
    refunds = []
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: refunds.append(kw) or {"ok": True, "refund_id": "rf_p"})
    f = _lejos()
    # Reserva del APK: S/ 60 de lista, canjeó 100 puntos (−S/ 3) → pagó 57 + cargo 3 = 60.
    rid = _id_app() + "_1"
    _fila(db, rid, email, "15:00", medio="tarjeta", fecha=f)
    db.reservas[rid]["cargo_servicio"] = 3.0
    ref = f"c_b1_{f}_15:00"
    # Un canje VIEJO de otra reserva del mismo turno (semanas antes) no cuenta.
    db.puntos_canjes.append({"email": email, "puntos": 100, "soles": 3.0, "referencia": ref, "creado": time.time() - 40 * 86400})
    db.puntos_canjes.append({"email": email, "puntos": 100, "soles": 3.0, "referencia": ref, "creado": time.time()})
    stores.registrar_pago(tipo="reserva", monto_centimos=6000, moneda="PEN", estado="aprobado", email=email,
                          culqi_charge_id="chr_pts_app", concepto="Reserva app")
    pr.post_liquidacion_online(pr.LiquidacionOnlineReq(dueno_id=DUENO, monto_soles=60.0, reserva_id=rid, medio="tarjeta",
                                                       moneda="PEN", charge_id="chr_pts_app", cargo_servicio_centimos=300))
    est = cli.get(f"/pagos/reserva/cancelacion/{rid}", params={"email": email}).json()
    assert est["puntos"] == 100 and est["monto"] == 57 and est["cargo_centimos"] == 300 and est["total_pagado"] == 60.0, est
    assert [o["monto"] for o in est["politica"]["opciones"]] == [60.0, 57.0]  # nunca los 63 de lista + cargo
    # A saldo: 60 (lo pagado, cargo incluido) y los 100 puntos vuelven UNA vez.
    j = cli.post("/pagos/reserva/cancelar", json={"ref": rid, "email": email, "medio": "saldo"}).json()
    assert j["ok"] and j["reembolso"] == "saldo" and j["monto_devuelto"] == 60.0 and j["puntos_devueltos"] == 100, j
    dev = stores.pago_por_charge(f"dev:{rid}")
    assert dev is not None and dev.monto_centimos == 6000
    assert db.puntos_canjes[-1] == {"email": email, "puntos": -100, "soles": -3.0, "referencia": "devolucion:" + ref,
                                    "creado": db.puntos_canjes[-1]["creado"]}
    assert db.puntos_canje_neto(email, [ref], time.time() - 3600) == (0, 0.0)
    # Al medio original: el precio PAGADO (57), nunca más que el cargo de Culqi.
    rid2 = _id_app() + "_2"
    _fila(db, rid2, email, "17:00", medio="yape", fecha=f)
    ref2 = f"c_b1_{f}_17:00"
    db.puntos_canjes.append({"email": email, "puntos": 100, "soles": 3.0, "referencia": ref2, "creado": time.time()})
    stores.registrar_pago(tipo="reserva", monto_centimos=5700, moneda="PEN", estado="aprobado", email=email,
                          culqi_charge_id="chr_pts_app2", concepto="Reserva app")
    pr.post_liquidacion_online(pr.LiquidacionOnlineReq(dueno_id=DUENO, monto_soles=60.0, reserva_id=rid2, medio="yape",
                                                       moneda="PEN", charge_id="chr_pts_app2"))
    j = cli.post("/pagos/reserva/cancelar", json={"ref": rid2, "email": email, "medio": "original"}).json()
    assert j["ok"] and j["reembolso"] == "reembolsado" and j["monto_devuelto"] == 57.0 and j["puntos_devueltos"] == 100
    assert refunds[-1] == {"charge_id": "chr_pts_app2", "monto_centimos": 5700}
    # Si el canje del APK no llegó a la nube, el tope es el cargo de Culqi: a
    # saldo no se devuelven los 60 de lista sino los 57 cobrados.
    rid3 = _id_app() + "_3"
    _fila(db, rid3, email, "19:00", medio="tarjeta", fecha=f)
    stores.registrar_pago(tipo="reserva", monto_centimos=5700, moneda="PEN", estado="aprobado", email=email,
                          culqi_charge_id="chr_pts_app3", concepto="Reserva app")
    pr.post_liquidacion_online(pr.LiquidacionOnlineReq(dueno_id=DUENO, monto_soles=60.0, reserva_id=rid3, medio="tarjeta",
                                                       moneda="PEN", charge_id="chr_pts_app3"))
    j = cli.post("/pagos/reserva/cancelar", json={"ref": rid3, "email": email, "medio": "saldo"}).json()
    assert j["ok"] and j["monto_devuelto"] == 57.0 and j["puntos_devueltos"] == 0
    # Tarde: ni plata ni puntos.
    rid4 = _id_app() + "_4"
    _fila(db, rid4, email, "20:00", medio="tarjeta", fecha=f)
    ref4 = f"c_b1_{f}_20:00"
    db.puntos_canjes.append({"email": email, "puntos": 100, "soles": 3.0, "referencia": ref4, "creado": time.time()})
    monkeypatch.setattr(config, "WEB_CANCELACION_HORAS", 10_000)
    j = cli.post("/pagos/reserva/cancelar", json={"ref": rid4, "email": email, "medio": "saldo"}).json()
    assert j["ok"] and j["reembolso"] == "sin_reembolso" and j["puntos_devueltos"] == 0
    assert db.puntos_canje_neto(email, [ref4]) == (100, 3.0)
    stores.config.pop("cargo_activo_reservas", None)


def test_pozo_rechaza_saldo_en_otra_moneda_desde_el_app(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    email = "bolivia@gmail.com"
    stores.acreditar(email, 50_000)
    monkeypatch.setattr(pr, "moneda_billetera", lambda e: "BOB")
    n0 = len(stores.pagos)
    body = {"email": email, "campeonato_id": "camp_mon", "equipo_id": "eq_1", "cuota_equipo_soles": 100,
            "cupo": 10, "moneda": "S/", "organizador": "org@gmail.com", "campeonato_nombre": "Copa", "equipo_nombre": "Kinder"}
    for ruta in ("aportar", "completar"):
        r = cli.post(f"/pagos/torneo/equipo/{ruta}", json=body).json()
        assert r["ok"] is False and r["error"] == "moneda_distinta" and r["moneda"] == "PEN" and r["moneda_billetera"] == "BOB", r
    assert stores.saldo_centimos(email) == 50_000 and len(stores.pagos) == n0
    assert pozos.clave("camp_mon", "eq_1") not in stores.pozos_equipo  # ni siquiera se creó el pozo
    # Misma moneda: sí aporta su parte.
    monkeypatch.setattr(pr, "moneda_billetera", lambda e: "PEN")
    r = cli.post("/pagos/torneo/equipo/aportar", json=body).json()
    assert r["ok"] and r["aporte_centimos"] == 1000
    assert pozos.de_equipo("camp_mon", "eq_1", 100, 10)["pozo_centimos"] == 1000
