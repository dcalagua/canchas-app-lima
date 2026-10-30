"""BONO DE HORAS y PUNTOS PICHANGOL en la reserva web (pedido del director,
1-oct-2026: "el jugador debe poder usar en la web los mismos beneficios que
en el app"). Espejo de `club_detalle._reservar`: el bono cubre todos los
turnos (1 h = 1 turno) sin cobrar ni liquidar; los puntos restan S/ 3 al
cobro pero el dueño liquida el precio completo. Ambos se apartan con el hold
y vuelven si no se paga o si se cancela a tiempo."""
import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402
from web import beneficios, datos, sesion  # noqa: E402
from test_web_reservas import LIMA, _manana  # noqa: E402
from test_fidelidad import FakeDBFid, _FNS as _FNS_FID  # noqa: E402

B1 = {**LIMA, "id": "c_b1", "nombre": "Cancha Bono", "club": "Club Bono", "dueno": "duenobono@gmail.com", "precio_hora": 60.0,
      "descuento_valle": 0, "servicios_extra": [{"clave": "pelotero", "precio": 10}], "sena_pct": 0}
B2 = {**B1, "id": "c_b2", "nombre": "Cancha Seña", "sena_pct": 50}


class FakeDBBen(FakeDBFid):
    def __init__(self):
        super().__init__()
        self.canchas["c_b1"] = dict(B1)
        self.canchas["c_b2"] = dict(B2)
        self.creditos: dict[str, dict] = {}
        self.cw: dict[str, dict] = {}
        self.puntos_canjes: list[dict] = []
        self.ganados: dict[str, int] = {}

    # ── bono ──
    def credito(self, cid, email, horas, usadas=0, club="Club Bono", dueno="duenobono@gmail.com", creado="2026-09-01"):
        self.creditos[cid] = {"id": cid, "comprador": email, "club": club, "dueno": dueno, "horas_total": horas,
                              "horas_usadas": usadas, "creado": creado}

    def _mios(self, email, club, dueno):
        return sorted([c for c in self.creditos.values() if c["comprador"] == email.lower() and c["club"] == club
                       and c["dueno"] == dueno.lower()], key=lambda c: (c["creado"], c["id"]))

    def canjes_web_disponible(self):
        return True

    def saldo_bono(self, email, club, dueno):
        return sum(max(c["horas_total"] - c["horas_usadas"], 0) for c in self._mios(email, club, dueno))

    def bono_apartar(self, canje):
        restan, det = canje["horas"], {}
        for c in self._mios(canje["email"], canje["club"], canje["dueno"]):
            g = min(restan, c["horas_total"] - c["horas_usadas"])
            if g > 0:
                det[c["id"]] = g
                restan -= g
        if restan > 0:
            return "sin_bono"
        for cid, n in det.items():
            self.creditos[cid]["horas_usadas"] += n
        self.cw[canje["id"]] = {**canje, "detalle": det, "estado": "reservado"}
        canje["detalle"] = det
        return ""

    def bono_devolver_horas(self, email, club, dueno, horas):
        restan = horas
        for c in reversed(self._mios(email, club, dueno)):
            n = min(restan, c["horas_usadas"])
            c["horas_usadas"] -= n
            restan -= n
        return horas - restan

    # ── puntos ──
    def puntos_de(self, email):
        g = self.ganados.get(email, 0)
        can = sum(x["puntos"] for x in self.puntos_canjes if x["email"] == email)
        return {"ganados": g, "canjeados": can, "disponibles": max(0, g - can)}

    def puntos_apartados(self, email):
        return sum(c["puntos"] for c in self.cw.values() if c["email"] == email and c["tipo"] == "puntos" and c["estado"] == "reservado")

    def puntos_apartar(self, canje, ganados, minimo):
        can = sum(x["puntos"] for x in self.puntos_canjes if x["email"] == canje["email"])
        if ganados - can - self.puntos_apartados(canje["email"]) < minimo:
            return "sin_puntos"
        self.cw[canje["id"]] = {**canje, "detalle": {}, "estado": "reservado"}
        return ""

    # ── libro de canjes web ──
    def canjes_web_de_ref(self, ref):
        return [dict(c) for c in self.cw.values() if c["reserva_ref"] == ref and c["estado"] != "devuelto"]

    def canjes_web_por_ids(self, ids):
        return [dict(c) for c in self.cw.values() if c["estado"] != "devuelto" and set(c["reserva_ids"]) & set(ids)]

    def canjes_web_reservados_viejos(self, segundos):
        return [dict(c) for c in self.cw.values() if c["estado"] == "reservado"]

    def canje_web_usar(self, cid, referencia=""):
        c = self.cw.get(cid)
        if not c or c["estado"] != "reservado":
            return False
        c["estado"] = "usado"
        if c["tipo"] == "puntos":
            self.puntos_canjes.append({"email": c["email"], "puntos": c["puntos"], "soles": float(c["descuento"]), "referencia": referencia})
        return True

    def canje_web_devolver(self, cid, referencia=""):
        c = self.cw.get(cid)
        if not c or c["estado"] == "devuelto":
            return None
        prev = dict(c)
        if c["tipo"] == "bono":
            for k, n in c["detalle"].items():
                self.creditos[k]["horas_usadas"] = max(self.creditos[k]["horas_usadas"] - n, 0)
        elif c["estado"] == "usado":
            self.puntos_canjes.append({"email": c["email"], "puntos": -c["puntos"], "soles": -float(c["descuento"]), "referencia": referencia})
        c["estado"] = "devuelto"
        return prev


_FNS = _FNS_FID + ("canjes_web_disponible", "saldo_bono", "bono_apartar", "bono_devolver_horas", "puntos_de", "puntos_apartados",
                   "puntos_apartar", "canjes_web_de_ref", "canjes_web_por_ids", "canjes_web_reservados_viejos",
                   "canje_web_usar", "canje_web_devolver")


@pytest.fixture
def db(monkeypatch):
    fake = FakeDBBen()
    for fn in _FNS:
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    stores.config.pop("cargo_activo_reservas", None)
    yield fake
    stores.config.pop("cargo_activo_reservas", None)


def _sesion(cli, monkeypatch, email, nombre="Ana Pérez"):
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": email, "email_verified": "true", "aud": "cid-web", "name": nombre, "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})


def _asegurar(cli, email, horas, cancha="c_b1", **kw):
    f = _manana()
    body = {"cancha_id": cancha, "horas": [{"fecha": f, "hora": h} for h in horas], "extras": [], "nombre": "Ana Pérez",
            "celular": "999888777", "email": email}
    body.update(kw)
    return cli.post("/web/asegurar", json=body).json()


def _liqs(dueno, ids):
    return [p for p in stores.pagos if p.tipo in ("liquidacion_online", "liquidacion_full") and p.dueno_id == dueno
            and p.culqi_charge_id in ids]


def test_bono_cubre_los_turnos_sin_cobro_ni_liquidacion_y_devuelve_las_horas(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    email = "anabono@gmail.com"
    db.credito("bono_a", email, 3, creado="2026-08-01")
    db.credito("bono_b", email, 2, creado="2026-09-01")
    db.credito("bono_otro", email, 9, club="Otro Local")  # otro local: no cuenta
    # Sin sesión no hay beneficios; con sesión, horas del local y la caja en la ficha.
    assert cli.get("/web/beneficios?cancha_id=c_b1").json()["ok"] is False
    _sesion(cli, monkeypatch, email)
    b = cli.get("/web/beneficios?cancha_id=c_b1").json()
    assert b["ok"] and b["activo"] and b["bono"]["horas"] == 5 and b["local"] == "Club Bono"
    html = cli.get("/reservar/c_b1").text
    assert "id='benBox'" in html and '"beneficios": true' in html and "Usar mi bono" in html
    # Hold con bono: 2 turnos de S/ 60 → nada que cobrar; horas apartadas FIFO.
    r = _asegurar(cli, email, ["15:00", "16:00"], bono=True)
    assert r["ok"] and r["sin_pago"] and r["total_centimos"] == 0 and r["a_pagar"] == 0, r
    assert r["bono"] == {"horas": 2, "cubre": 120, "quedan": 3}
    assert db.creditos["bono_a"]["horas_usadas"] == 2 and db.creditos["bono_b"]["horas_usadas"] == 0
    assert cli.get("/web/beneficios?cancha_id=c_b1").json()["bono"]["horas"] == 3  # otra pestaña ya no las ve
    # Liberar el horario devuelve las horas.
    assert cli.post("/web/liberar", json={"ids": r["ids"], "firma": r["firma"]}).json()["ok"]
    assert db.creditos["bono_a"]["horas_usadas"] == 0 and not db.canjes_web_de_ref(r["grupo"])
    # Ahora sí: reserva con bono confirmada sin Culqi ni liquidación (el dueño cobró al vender el pack).
    cargos, pushes = [], []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_no"})
    import pagos.router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda e_, t, c, tipo="aviso": pushes.append((e_, t, c)))
    r = _asegurar(cli, email, ["15:00", "16:00", "17:00"], bono=True)
    assert r["ok"] and r["sin_pago"] and r["bono"]["quedan"] == 2
    assert db.creditos["bono_a"]["horas_usadas"] == 3 and db.creditos["bono_b"]["horas_usadas"] == 0
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "", "medio": "bono"}).json()
    assert p["ok"] and cargos == []
    for i in r["ids"]:
        f = db.reservas[i]
        assert f["pagado"] and f["medio_pago"] == "bono" and f["precio"] == 60 and f["estado"] == "confirmada"
    assert db.canjes_web_de_ref(r["grupo"])[0]["estado"] == "usado"
    assert not _liqs("duenobono@gmail.com", r["ids"])
    assert any(e_ == "duenobono@gmail.com" and "🎟️" in t and "bono de horas (3 h)" in c for e_, t, c in pushes)
    # Comprobante y Mis reservas.
    comp = cli.get(f"/reserva/{r['grupo']}").text
    assert "Pagado con tu bono · 3 horas" in comp and "tu bono de horas" in comp and "Total pagado</span><span>S/ 0.00" in comp
    assert "data-bono='3'" in comp
    assert "Pagada con bono" in cli.get("/mis-reservas").text
    # Cancelar a tiempo: las 3 horas vuelven a los MISMOS créditos.
    j = cli.post("/web/cancelar", json={"ref": r["grupo"], "medio": "saldo"}).json()
    assert j["ok"] and j["reembolso"] == "bono" and j["bono_horas_devueltas"] == 3, j
    assert db.creditos["bono_a"]["horas_usadas"] == 0 and all(i not in db.reservas for i in r["ids"])
    assert stores.pago_por_charge(f"dev:{r['grupo']}") is None  # sin plata de por medio, nada a saldo


def test_bono_rechazos_extras_cobrados_y_cancelacion_tardia(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    email = "bonodos@gmail.com"
    db.credito("bono_c", email, 1)
    # Sin sesión (login activo) no se reserva.
    j = _asegurar(cli, email, ["15:00"], bono=True)
    assert j["error"] == "sesion_requerida"
    _sesion(cli, monkeypatch, email)
    # No alcanza para 2 turnos; con boleador tampoco (camino distinto, como el app).
    assert _asegurar(cli, email, ["15:00", "16:00"], bono=True) == {"ok": False, "error": "sin_bono"}
    assert _asegurar(cli, email, ["15:00"], bono=True, boleador="alguien") == {"ok": False, "error": "bono_con_boleador"}
    # Otra cuenta sin bono en el local.
    _sesion(cli, monkeypatch, "sinbono@gmail.com")
    assert _asegurar(cli, "sinbono@gmail.com", ["15:00"], bono=True) == {"ok": False, "error": "sin_bono"}
    _sesion(cli, monkeypatch, email)
    # Bono + servicio extra: el turno va con el bono y SOLO el extra se cobra en línea y se liquida al dueño.
    r = _asegurar(cli, email, ["18:00"], bono=True, extras=["pelotero"])
    assert r["ok"] and not r["sin_pago"] and r["a_pagar"] == 10 and r["total_centimos"] == 1000, r
    # Pago rechazado → la hora vuelve al bono y el horario queda libre.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "rechazado"})
    assert not cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "yape"}).json()["ok"]
    assert db.creditos["bono_c"]["horas_usadas"] == 0 and r["ids"][0] not in db.reservas
    cargos = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_bono_extra"})
    r = _asegurar(cli, email, ["18:00"], bono=True, extras=["pelotero"])
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "yape"}).json()
    assert p["ok"] and cargos[0]["monto_centimos"] == 1000
    fila = db.reservas[r["ids"][0]]
    assert fila["medio_pago"] == "bono" and fila["pagado"] and fila["precio"] == 60
    liq = _liqs("duenobono@gmail.com", r["ids"])
    assert len(liq) == 1 and liq[0].monto_centimos == 1000  # solo el extra
    comp = cli.get(f"/reserva/{r['ids'][0]}").text
    assert "Pagado con tu bono · 1 hora" in comp and "Total pagado</span><span>S/ 10.00" in comp
    # Cancelación TARDE (política con 100 h mínimas): ni plata ni horas vuelven.
    monkeypatch.setattr(config, "WEB_CANCELACION_HORAS", 100)
    from pagos import devoluciones
    monkeypatch.setattr(devoluciones, "ARREPENTIMIENTO_HORAS", -1)  # sin ventana de arrepentimiento
    j = cli.post("/web/cancelar", json={"ref": r["ids"][0], "medio": "original"}).json()
    assert j["ok"] and j["reembolso"] == "sin_reembolso" and j["bono_horas_devueltas"] == 0
    assert db.creditos["bono_c"]["horas_usadas"] == 1


def test_puntos_descuentan_3_soles_el_dueno_liquida_completo_y_el_canje_se_registra_una_vez(db, monkeypatch):
    stores.config["cargo_activo_reservas"] = "1"
    cli = TestClient(app, base_url="https://testserver")
    email = "anapuntos@gmail.com"
    db.ganados[email] = 250
    _sesion(cli, monkeypatch, email)
    b = cli.get("/web/beneficios?cancha_id=c_b1").json()
    assert b["puntos"] == {"disponibles": 250, "canje": 100, "descuento": 3, "aplica": True}
    cargos = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_pts_1"})
    r = _asegurar(cli, email, ["15:00"], puntos=True)
    assert r["ok"] and r["total"] == 60 and r["a_pagar"] == 57 and r["puntos"] == {"puntos": 100, "descuento": 3}, r
    cot = __import__("web.router", fromlist=["x"])._cotizacion_reserva(db.canchas["c_b1"], 57)
    assert r["total_centimos"] == cot.total_centimos and r["cargo_centimos"] == cot.cargo_centimos > 0
    # Apartados: otra pestaña ve 150; aún NO hay canje en la tabla del app.
    assert cli.get("/web/beneficios?cancha_id=c_b1").json()["puntos"]["disponibles"] == 150 and db.puntos_canjes == []
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "tarjeta"}).json()
    assert p["ok"] and cargos[0]["monto_centimos"] == cot.total_centimos
    f = db.reservas[r["ids"][0]]
    assert db.puntos_canjes == [{"email": email, "puntos": 100, "soles": 3.0, "referencia": f"c_b1_{f['fecha']}_15:00"}]
    # El dueño liquida el precio COMPLETO (S/ 60): el descuento lo pone Pichangol.
    liq = _liqs("duenobono@gmail.com", r["ids"])
    assert len(liq) == 1 and liq[0].monto_centimos == 6000
    assert f["precio"] == 60 and f["medio_pago"] == "tarjeta"
    # Pagar dos veces no duplica el canje.
    assert cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "tarjeta"}).json()["ok"]
    assert len(db.puntos_canjes) == 1 and len(cargos) == 1
    comp = cli.get(f"/reserva/{r['ids'][0]}").text
    total_pagado = (5700 + cot.cargo_centimos) / 100
    assert "Canje de 100 puntos Pichangol" in comp and f"Total pagado</span><span>S/ {total_pagado:.2f}" in comp
    assert cli.get("/web/beneficios?cancha_id=c_b1").json()["puntos"]["disponibles"] == 150
    # Cancelar a tiempo al medio original: vuelve lo PAGADO (S/ 57, nunca los S/ 60 de lista) y los 100 puntos.
    refunds = []
    from pagos import devoluciones
    monkeypatch.setattr(devoluciones, "ARREPENTIMIENTO_HORAS", -1)  # plazo normal: al medio original va el precio PAGADO, sin cargo
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: refunds.append(kw) or {"ok": True, "refund_id": "rf_pts"})
    j = cli.post("/web/cancelar", json={"ref": r["ids"][0], "medio": "original"}).json()
    assert j["ok"] and j["reembolso"] == "reembolsado" and j["puntos_devueltos"] == 100, j
    assert refunds[0]["monto_centimos"] == 5700  # S/ 57 pagados, nunca los S/ 60 de lista
    assert db.puntos_canjes[-1]["puntos"] == -100
    assert cli.get("/web/beneficios?cancha_id=c_b1").json()["puntos"]["disponibles"] == 250


def test_puntos_rechazos_y_pago_fallido_no_registra_canje(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    email = "pocos@gmail.com"
    db.ganados[email] = 90
    _sesion(cli, monkeypatch, email)
    assert _asegurar(cli, email, ["15:00"], puntos=True) == {"ok": False, "error": "sin_puntos"}
    db.ganados[email] = 300
    db.credito("bono_d", email, 4)
    # No con bono, no pagando solo la seña.
    assert _asegurar(cli, email, ["15:00"], puntos=True, bono=True) == {"ok": False, "error": "sin_puntos"}
    assert _asegurar(cli, email, ["15:00"], cancha="c_b2", puntos=True, pago="sena") == {"ok": False, "error": "sin_puntos"}
    # Pagando todo en una cancha con seña sí aplica.
    r = _asegurar(cli, email, ["15:00"], cancha="c_b2", puntos=True, pago="total")
    assert r["ok"] and r["pago"] == "total" and r["a_pagar"] == 57
    # Pago rechazado: los puntos apartados vuelven y no se escribe ningún canje.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "rechazado"})
    assert not cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "yape"}).json()["ok"]
    assert db.puntos_canjes == [] and cli.get("/web/beneficios?cancha_id=c_b2").json()["puntos"]["disponibles"] == 300
    # Dos holds a la vez con 300 puntos: 3 canjes caben, el 4.º no.
    hs = [_asegurar(cli, email, [h], puntos=True) for h in ("09:00", "10:00", "11:00")]
    assert all(h["ok"] for h in hs)
    assert _asegurar(cli, email, ["12:00"], puntos=True) == {"ok": False, "error": "sin_puntos"}
    # El barrido devuelve apartados cuyo hold se borró por otro camino.
    for h in hs:
        db.reservas.pop(h["ids"][0])
    assert beneficios.barrer_vencidos() == 3
    assert cli.get("/web/beneficios?cancha_id=c_b1").json()["puntos"]["disponibles"] == 300
    # Un bono apartado cuyo hold desapareció también vuelve con el barrido.
    r = _asegurar(cli, email, ["13:00"], bono=True)
    assert r["ok"] and db.creditos["bono_d"]["horas_usadas"] == 1
    db.reservas.pop(r["ids"][0])
    assert beneficios.barrer_vencidos() == 1 and db.creditos["bono_d"]["horas_usadas"] == 0


def test_cancelar_reserva_con_bono_hecha_en_el_app_devuelve_horas(db, monkeypatch):
    """Una reserva pagada con bono en el APK (medio 'bono', sin libro web) que
    se cancela a tiempo desde la web devuelve las horas a los créditos del local."""
    cli = TestClient(app, base_url="https://testserver")
    email = "appbono@gmail.com"
    db.credito("bono_e", email, 5, usadas=2)
    f = _manana()
    db.reservas["jug_1"] = {"id": "jug_1", "cancha_id": "c_b1", "fecha": f, "hora_inicio": "15:00", "hora_fin": "16:00",
                            "estado": "confirmada", "pagado": True, "usuario": email, "medio_pago": "bono", "precio": 60,
                            "grupo_reserva_id": "", "extras": [], "sena": 0, "moneda": "S/", "jugador": "Ana"}
    _sesion(cli, monkeypatch, email)
    comp = cli.get("/reserva/jug_1").text
    assert "Pagado con tu bono · 1 hora" in comp and "Total pagado</span><span>S/ 0.00" in comp
    j = cli.post("/web/cancelar", json={"ref": "jug_1", "medio": "saldo"}).json()
    assert j["ok"] and j["reembolso"] == "bono" and j["bono_horas_devueltas"] == 1
    assert db.creditos["bono_e"]["horas_usadas"] == 1
