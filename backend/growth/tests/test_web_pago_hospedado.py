"""COBRO WEB EN USD / BOB por pasarela HOSPEDADA (`web/pago_hospedado.py`):
Ecuador por la fachada `pagos.pasarela_ec` (hoy PayPhone) y Bolivia por
Libélula, con las llamadas HTTP de las pasarelas SIMULADAS. Lo que se prueba:
reserva total / seña con cargo por servicio, extras + boleador, recargas con
bono, rechazo y cancelación que sueltan el horario y lo apartado, retorno
doble idempotente, apartado que no vence mientras la orden está en curso,
barrido de órdenes vencidas (y pago tardío devuelto), cancelación con
devolución `manual`, PRD sin credenciales = "hazlo en la app" y la pasarela
simulada de QAS."""

import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import fidelidad  # noqa: E402
from db import pg  # noqa: E402
from db.store import stores, Stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi, libelula, payphone  # noqa: E402
import pagos.router as pr  # noqa: E402
from web import beneficios, datos, pago_hospedado as ph  # noqa: E402
from web import router as web  # noqa: E402
from test_boleadores import FakeDBBol, TENIS, _FNS, _perfil, _sesion  # noqa: E402
from test_web_reservas import _manana  # noqa: E402

BASE = "https://pg.example.com"
LAPAZ = {**TENIS, "id": "c_lp", "nombre": "Cancha La Paz", "club": "Club Altura", "lat": -16.5, "lng": -68.15,
         "moneda": "Bs", "precio_hora": 40.0, "servicios_extra": [{"clave": "pelotero", "precio": 10}]}


class FakeDBPw(FakeDBBol):
    def __init__(self):
        super().__init__()
        self.canchas["c_lp"] = dict(LAPAZ)

    def marcar_hold_pasarela(self, ids):
        filas = [self.reservas.get(i) for i in ids]
        if any(f is None or f["estado"] != "nueva" or f.get("pagado") for f in filas):
            return False
        for f in filas:
            f["medio_pago"] = datos.MEDIO_HOLD_PASARELA
        return True


class Pasarelas:
    """PayPhone y Libélula simuladas (lo que harían sus APIs)."""

    def __init__(self):
        self.preparados, self.confirmaciones, self.deudas = [], [], []
        self.aprobar = True
        self.lib_pagadas: set[str] = set()

    def preparar(self, **kw):
        self.preparados.append(kw)
        return {"ok": True, "payment_id": 77, "url_tarjeta": "https://pay.payphone/card/x", "url_payphone": "https://pay.payphone/app/x"}

    def confirmar(self, **kw):
        self.confirmaciones.append(kw)
        d = stores.payphone_pagos[kw["client_tx_id"]]
        return {"ok": True, "aprobado": self.aprobar, "estado": "Approved" if self.aprobar else "Canceled",
                "transaction_id": kw["transaction_id"], "autorizacion": "A1",
                "monto_centavos": payphone.centavos(d["monto_usd"])}

    def registrar(self, **kw):
        self.deudas.append(kw)
        return {"ok": True, "url_pasarela": f"https://pay.libelula.bo/{kw['identificador']}",
                "id_transaccion": f"T{kw['identificador'][:6]}", "qr_url": ""}

    def consultar(self, ident):
        return {"ok": True, "pagado": ident in self.lib_pagadas}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDBPw()
    for fn in _FNS + ("marcar_hold_pasarela",):
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    for k, v in {"CULQI_PUBLIC_KEY": "pk_test_x", "CULQI_SECRET_KEY": "sk_test_x", "ADMIN_PANEL_TOKEN": "adm",
                 "APP_API_KEY": "", "GOOGLE_WEB_CLIENT_ID": "cid-web", "PUBLIC_BASE_URL": BASE,
                 "PAYPHONE_TOKEN": "tok", "PAYPHONE_STORE_ID": "st1", "LIBELULA_APPKEY": "app", "PICHANGOL_ENTORNO": ""}.items():
        monkeypatch.setattr(config, k, v)
    for k in ("cargo_activo_reservas", "boleadores_activo", "promo_bono_recarga_pct", "promo_bono_recarga_min", "promo_bono_recarga_tope"):
        stores.config.pop(k, None)
    stores.pagos_web.clear(); stores.payphone_pagos.clear(); stores.libelula_deudas.clear()
    stores.cancelaciones_web.clear()
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    yield fake
    # Nada de esta prueba se filtra a las siguientes (config, órdenes, pagos en curso).
    for k in ("cargo_activo_reservas", "boleadores_activo", "promo_bono_recarga_pct", "promo_bono_recarga_min", "promo_bono_recarga_tope"):
        stores.config.pop(k, None)
    stores.pagos_web.clear(); stores.payphone_pagos.clear(); stores.libelula_deudas.clear()
    stores.cancelaciones_web.clear()


@pytest.fixture
def gw(monkeypatch):
    g = Pasarelas()
    monkeypatch.setattr(payphone, "preparar", g.preparar)
    monkeypatch.setattr(payphone, "confirmar", g.confirmar)
    monkeypatch.setattr(libelula, "registrar_deuda", g.registrar)
    monkeypatch.setattr(libelula, "consultar_por_identificador", g.consultar)
    return g


def _cli(monkeypatch, email="ana@gmail.com"):
    cli = TestClient(app, base_url="https://testserver")
    _sesion(cli, monkeypatch, email, "Ana Pérez")
    return cli


def _asegurar(cli, cancha, horas, **kw):
    f = _manana()
    body = {"cancha_id": cancha, "horas": [{"fecha": f, "hora": h} for h in horas], "extras": kw.pop("extras", []),
            "nombre": "Ana Pérez", "celular": "0991234567", "email": "ana@gmail.com", **kw}
    return cli.post("/web/asegurar", json=body).json()


def _pagos(tipo, **kw):
    return [p for p in stores.pagos if p.tipo == tipo and all(getattr(p, k) == v for k, v in kw.items())]


# ── Ecuador ───────────────────────────────────────────────────────────────────

def test_ecuador_reserva_total_con_cargo_por_servicio(db, gw, monkeypatch):
    stores.config["cargo_activo_reservas"] = "1"
    cli = _cli(monkeypatch)
    html = cli.get("/reservar/c_gye").text
    # La ficha cobra en $ con la pasarela de Ecuador (sin Culqi en la página).
    assert "Reserva desde la app" not in html and "checkout.culqi.com" not in html
    assert '"pasarela": "payphone"' in html and "PayPhone · tarjeta" in html and "data-medio='payphone'" in html
    assert "fetch('/web/pago/reserva'" in html and "medioNombre: hosp ? C.pasarelaNombre" in html
    r = _asegurar(cli, "c_gye", ["15:00", "16:00"], extras=["arbitro"])
    assert r["ok"] and r["total"] == 50 and r["cargo_centimos"] > 0 and r["total_centimos"] == 5000 + r["cargo_centimos"]
    # Culqi no cobra dólares: /web/pagar lo rechaza.
    assert cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn"}).json()["error"] == "usa_pasarela"
    p = cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()
    assert p["ok"] and p["pasarela"] == "payphone" and p["url"].startswith(f"{BASE}/pagos/ec/ir/")
    oid = p["orden"]
    o = stores.pagos_web[oid]
    assert o["moneda"] == "USD" and o["monto_centimos"] == r["total_centimos"] and o["estado"] == "pendiente"
    prep = gw.preparados[0]
    assert prep["monto_usd"] == r["total_centimos"] / 100 and prep["response_url"] == f"{BASE}/web/pago/{oid}/retorno"
    assert prep["cancel_url"] == f"{BASE}/web/pago/{oid}/cancelado"
    # El apartado quedó "en pasarela" (no vence a los 10 min) y el navegador no lo puede soltar.
    assert all(db.reservas[i]["medio_pago"] == "web_pasarela" for i in r["ids"])
    assert cli.post("/web/liberar", json={"ids": r["ids"], "firma": r["firma"]}).json()["error"] == "pago_en_curso"
    # Un segundo clic devuelve la MISMA orden (no se crea otra).
    assert cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()["orden"] == oid
    # Vuelve de PayPhone: se CONFIRMA al instante, sin depender de la cookie.
    ident = o["ref_pasarela"]
    anon = TestClient(app, base_url="https://testserver")
    rr = anon.get(f"/web/pago/{oid}/retorno?id=TX9&clientTransactionId={ident}", follow_redirects=False)
    assert rr.status_code == 303 and rr.headers["location"] == f"/web/pago/{oid}"
    assert gw.confirmaciones == [{"transaction_id": "TX9", "client_tx_id": ident}]
    assert o["estado"] == "aprobado" and o["accion_hecha"] and o["url_resultado"].startswith("/reserva/grp_web_")
    for i in r["ids"]:
        assert db.reservas[i]["estado"] == "confirmada" and db.reservas[i]["pagado"] is True and db.reservas[i]["medio_pago"] == "tarjeta"
    cobros = _pagos("cobro_web", culqi_charge_id=f"payphone:{ident}")
    assert len(cobros) == 1 and cobros[0].moneda == "USD" and cobros[0].monto_centimos == r["total_centimos"]
    assert cobros[0].cargo_servicio_centimos == r["cargo_centimos"] and cobros[0].concepto == f"web:{r['grupo']}"
    liq = stores.pago_por_charge(r["ids"][0])
    assert liq.tipo in ("liquidacion_online", "liquidacion_full") and liq.moneda == "USD" and liq.monto_centimos == 5000
    assert liq.cargo_id == f"payphone:{ident}" and liq.cargo_servicio_centimos == r["cargo_centimos"]
    # La página de la orden (dueño) lleva al comprobante; un extraño no ve nada.
    assert cli.get(f"/web/pago/{oid}", follow_redirects=False).headers["location"] == o["url_resultado"]
    assert "inicia sesión con la misma cuenta" in anon.get(f"/web/pago/{oid}").text
    assert anon.get(f"/web/pago/{oid}/estado").status_code == 404
    # Retorno DOBLE (o con datos falsos): ni otra confirmación ni otra liquidación.
    anon.get(f"/web/pago/{oid}/retorno?id=TX9&clientTransactionId={ident}", follow_redirects=False)
    anon.get(f"/web/pago/{oid}/retorno?id=OTRO&clientTransactionId=falso", follow_redirects=False)
    assert len(gw.confirmaciones) == 1 and len(_pagos("cobro_web", culqi_charge_id=f"payphone:{ident}")) == 1
    assert len([p for p in stores.pagos if p.culqi_charge_id == r["ids"][0]]) == 1
    assert "pagos_web" in stores.to_state() and oid in stores.to_state()["pagos_web"]


def test_ecuador_sena_con_cargo(db, gw, monkeypatch):
    stores.config["cargo_activo_reservas"] = "1"
    db.canchas["c_gye"]["sena_pct"] = 50
    cli = _cli(monkeypatch)
    r = _asegurar(cli, "c_gye", ["15:00"], pago="sena")
    assert r["ok"] and r["pago"] == "sena" and r["sena"] == 5 and r["resto"] == 5
    p = cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()
    o = stores.pagos_web[p["orden"]]
    assert o["monto_centimos"] == r["total_centimos"] == 500 + r["cargo_centimos"]
    TestClient(app).get(f"/web/pago/{o['id']}/retorno?id=TX1&clientTransactionId={o['ref_pasarela']}", follow_redirects=False)
    fila = db.reservas[r["ids"][0]]
    assert fila["estado"] == "confirmada" and fila["pagado"] is False and fila["medio_pago"] == "sena"
    liq = stores.pago_por_charge(r["ids"][0])
    assert liq.monto_centimos == 500 and liq.medio == "sena" and liq.moneda == "USD"


def test_rechazo_y_cancelacion_sueltan_horario_y_lo_apartado(db, gw, monkeypatch):
    devueltos = {"fid": [], "ben": []}
    monkeypatch.setattr(fidelidad, "revertir_canje", lambda ref="", ids=None: devueltos["fid"].append((ref, ids)) or False)
    monkeypatch.setattr(beneficios, "soltar", lambda ref="", ids=None: devueltos["ben"].append((ref, ids)) or 0)
    cli = _cli(monkeypatch)
    r = _asegurar(cli, "c_gye", ["15:00"])
    o = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()["orden"]]
    gw.aprobar = False
    cli.get(f"/web/pago/{o['id']}/retorno?id=TX2&clientTransactionId={o['ref_pasarela']}", follow_redirects=False)
    assert o["estado"] == "rechazado" and not o["pagado"] and r["ids"][0] not in db.reservas
    assert devueltos["ben"] and devueltos["fid"]
    assert "no aprobó el cobro" in cli.get(f"/web/pago/{o['id']}").text and "No se te cobró nada" in cli.get(f"/web/pago/{o['id']}").text
    assert not _pagos("cobro_web", culqi_charge_id=f"payphone:{o['ref_pasarela']}")
    # Cancelar en la pasarela también suelta el horario.
    r2 = _asegurar(cli, "c_gye", ["17:00"])
    o2 = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r2["ids"], "firma": r2["firma"]}).json()["orden"]]
    cli.get(f"/web/pago/{o2['id']}/cancelado", follow_redirects=False)
    assert o2["estado"] == "cancelado" and r2["ids"][0] not in db.reservas
    # Y desde nuestra página de espera ("Cancelar este pago").
    r3 = _asegurar(cli, "c_gye", ["18:00"])
    o3 = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r3["ids"], "firma": r3["firma"]}).json()["orden"]]
    pag = cli.get(f"/web/pago/{o3['id']}").text
    assert "Confirmando tu pago" in pag and "btnCancelarOrden" in pag and "pcgConfirmar({titulo: '¿Cancelar este pago?'" in pag
    assert TestClient(app).post(f"/web/pago/{o3['id']}/cancelar").status_code == 404  # solo el dueño de la orden
    assert cli.post(f"/web/pago/{o3['id']}/cancelar").json()["estado"] == "cancelado" and r3["ids"][0] not in db.reservas
    # Un rechazo nunca toca una orden ya pagada.
    gw.aprobar = True
    r4 = _asegurar(cli, "c_gye", ["19:00"])
    o4 = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r4["ids"], "firma": r4["firma"]}).json()["orden"]]
    cli.get(f"/web/pago/{o4['id']}/retorno?id=TX4&clientTransactionId={o4['ref_pasarela']}", follow_redirects=False)
    assert ph.rechazar(o4["id"], "cancelado")["estado"] == "aprobado" and db.reservas[r4["ids"][0]]["estado"] == "confirmada"


# ── Bolivia ───────────────────────────────────────────────────────────────────

def test_bolivia_reserva_con_extras_y_boleador_por_callback(db, gw, monkeypatch):
    stores.config["cargo_activo_reservas"] = "1"
    db.verificados.add("juan@gmail.com")
    cli = TestClient(app, base_url="https://testserver")
    assert cli.post("/boleadores/perfil", json=_perfil(canchas=["c_lp"], tarifa=30)).json()["ok"]
    slug = db.boleadores["juan@gmail.com"]["slug"]
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    html = cli.get("/reservar/c_lp").text
    assert "Libélula · QR o tarjeta" in html and "data-medio='libelula'" in html and "checkout.culqi.com" not in html
    r = _asegurar(cli, "c_lp", ["15:00", "16:00"], extras=["pelotero"], boleador=slug)
    assert r["ok"] and r["total"] == 40 + 40 + 10 + 60 and r["moneda"] == "Bs"
    p = cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()
    assert p["ok"] and p["pasarela"] == "libelula" and p["url"].startswith("https://pay.libelula.bo/")
    o = stores.pagos_web[p["orden"]]
    deuda = gw.deudas[0]
    assert deuda["monto_bs"] == r["total_centimos"] / 100 and deuda["url_retorno"] == f"{BASE}/web/pago/{o['id']}/retorno"
    assert deuda["callback_url"] == f"{BASE}/pagos/bo/callback"
    # Libélula avisa por su callback (el cliente cerró la pestaña): se finaliza igual.
    gw.lib_pagadas.add(o["ref_pasarela"])
    tx = stores.libelula_deudas[o["ref_pasarela"]]["id_transaccion"]
    assert TestClient(app).get(f"/pagos/bo/callback?transaction_id={tx}").json() == {"ok": True}
    assert o["estado"] == "aprobado" and all(db.reservas[i]["estado"] == "confirmada" for i in r["ids"])
    liq = stores.pago_por_charge(r["ids"][0])
    assert liq.moneda == "BOB" and liq.monto_centimos == 9000  # 2 turnos + pelotero, sin la parte del boleador
    sol = db.solicitud_por_reserva(r["grupo"])
    assert sol and sol["estado"] == "pendiente" and sol["charge_id"] == f"libelula:{o['ref_pasarela']}" and sol["moneda"] == "BOB"
    assert sol["monto_centimos"] == 6000
    # El callback repetido no vuelve a liquidar ni a abrir otra solicitud.
    TestClient(app).get(f"/pagos/bo/callback?transaction_id={tx}")
    assert len([p for p in stores.pagos if p.culqi_charge_id == r["ids"][0]]) == 1 and len(db.solicitudes) == 1
    # El navegador vuelve después: directo al comprobante.
    rr = cli.get(f"/web/pago/{o['id']}/retorno", follow_redirects=False)
    assert cli.get(rr.headers["location"], follow_redirects=False).headers["location"] == o["url_resultado"]


# ── recargas ──────────────────────────────────────────────────────────────────

def test_recargas_usd_y_bob_con_bono(db, gw, monkeypatch):
    stores.config.update({"promo_bono_recarga_pct": "10", "promo_bono_recarga_min": "5", "promo_bono_recarga_tope": "50"})
    ec = "ec@gmail.com"
    stores.clientes_pago[ec] = {"pais_casa": "EC", "pais_casa_en": datetime.now(timezone.utc).isoformat()}
    stores.saldos.pop(ec, None)
    cli = _cli(monkeypatch, ec)
    html = cli.get("/mi-billetera").text
    assert "data-monto='10'" in html and "PayPhone · tarjeta" in html and "Recargar en la app" not in html
    assert "checkout.culqi.com" not in html and "recargarPasarela" in html
    assert cli.post("/web/billetera/recargar-pasarela", json={"monto": 0.5}).status_code == 400
    p = cli.post("/web/billetera/recargar-pasarela", json={"monto": 10}).json()
    assert p["ok"] and p["url"].startswith(f"{BASE}/pagos/ec/ir/")
    o = stores.pagos_web[p["orden"]]
    assert gw.preparados[-1]["monto_usd"] == 10
    rr = cli.get(f"/web/pago/{o['id']}/retorno?id=TXR&clientTransactionId={o['ref_pasarela']}", follow_redirects=False)
    assert stores.saldo_centimos(ec) == 1000 + 100  # recarga + 10 % de bono
    assert cli.get(rr.headers["location"], follow_redirects=False).headers["location"] == f"/mi-billetera?recarga={o['id']}"
    aviso = cli.get(f"/mi-billetera?recarga={o['id']}").text
    assert '"recargaOk": {"monto": 10.0, "bono": 1.0' in aviso
    # Retorno doble: no acredita de nuevo.
    cli.get(f"/web/pago/{o['id']}/retorno?id=TXR&clientTransactionId={o['ref_pasarela']}", follow_redirects=False)
    assert stores.saldo_centimos(ec) == 1100 and len(_pagos("recarga", dueno_id=ec)) == 1
    # Bolivia: la acredita el callback de Libélula.
    bo = "bo@gmail.com"
    stores.clientes_pago[bo] = {"pais_casa": "BO", "pais_casa_en": datetime.now(timezone.utc).isoformat()}
    stores.saldos.pop(bo, None)
    cb = _cli(monkeypatch, bo)
    assert "Libélula · QR o tarjeta" in cb.get("/mi-billetera").text
    ob = stores.pagos_web[cb.post("/web/billetera/recargar-pasarela", json={"monto": 100}).json()["orden"]]
    gw.lib_pagadas.add(ob["ref_pasarela"])
    tx = stores.libelula_deudas[ob["ref_pasarela"]]["id_transaccion"]
    for _ in range(2):
        TestClient(app).get(f"/pagos/bo/callback?transaction_id={tx}")
    assert stores.saldo_centimos(bo) == 10000 + 1000 and ob["estado"] == "aprobado"
    assert _pagos("recarga", dueno_id=bo)[0].moneda == "BOB"
    # Una billetera en soles no recarga por aquí (va con Culqi).
    assert _cli(monkeypatch, "pe@gmail.com").post("/web/billetera/recargar-pasarela", json={"monto": 20}).status_code == 409



# ── apartado, barrido y pago tardío ───────────────────────────────────────────

_REALES = {fn: getattr(datos, fn) for fn in ("ocupados", "ocupados_varias", "liberar_holds_vencidos",
                                             "liberar_holds_vencidos_todos", "marcar_hold_pasarela")}


def test_sql_del_apartado_respeta_la_orden_en_curso(monkeypatch):
    """El apartado "en pasarela" (`medio_pago = 'web_pasarela'`) usa el tope
    largo (50 min); el normal, los 10 min. Se revisa el SQL que llega a la base."""
    log = []

    class _Cur:
        rowcount = 2

        def execute(self, sql, params=()):
            log.append((sql, params))

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            pass

        def rollback(self):
            pass

    @contextmanager
    def conexion():
        yield _Conn()
    monkeypatch.setattr(pg, "habilitado", True, raising=False)
    monkeypatch.setattr(pg, "conexion", conexion)
    _REALES["ocupados"]("u1", ["2026-10-01"])
    _REALES["ocupados_varias"](["u1"], ["2026-10-01"])
    _REALES["liberar_holds_vencidos"]("u1")
    _REALES["liberar_holds_vencidos_todos"]()
    log = [(q, prm) for q, prm in log if "pichangol_reservas" in q]
    assert len(log) == 4
    for sql, params in log:
        assert "coalesce(medio_pago,'') = 'web_pasarela'" in sql and len(re.findall(r"(?<!%)%s", sql)) == len(params), sql
        largo, normal = [x for x in params if isinstance(x, int)][-2:]
        assert normal - largo == (datos.HOLD_PASARELA_MAX_SEGUNDOS - datos.HOLD_SEGUNDOS) * 1000 or abs(normal - largo - 2_400_000) < 5000
    assert _REALES["marcar_hold_pasarela"](["a", "b"]) is True
    sql, params = log[-1]
    assert sql.startswith("UPDATE pichangol_reservas SET medio_pago = %s") and params[0] == "web_pasarela"
    assert "estado = 'nueva'" in sql and "NOT coalesce(pagado,false)" in sql


def test_lo_apartado_sigue_apartado_mientras_paga(db, gw, monkeypatch):
    cli = _cli(monkeypatch)
    r = _asegurar(cli, "c_gye", ["15:00"])
    o = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()["orden"]]
    ref = r["grupo"] or r["ids"][0]
    assert ph.ref_pendiente(ref) and ph.ref_pendiente("", r["ids"])
    viejo = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
    # Premio de fidelidad apartado hace 40 min: sigue "vigente" mientras la orden está en curso.
    assert fidelidad._vigente({"estado": "reservado", "creado": viejo, "reserva_ref": ref, "reserva_ids": r["ids"]})
    assert not fidelidad._vigente({"estado": "reservado", "creado": viejo, "reserva_ref": "otra", "reserva_ids": ["x"]})
    # El barrido de bono/puntos no lo devuelve.
    devueltos = []
    monkeypatch.setattr(datos, "canjes_web_reservados_viejos", lambda seg: [{"id": "cw1", "reserva_ref": ref, "reserva_ids": r["ids"]}])
    monkeypatch.setattr(datos, "canje_web_devolver", lambda cid: devueltos.append(cid) or True)
    assert beneficios.barrer_vencidos() == 0 and devueltos == []
    ph.rechazar(o["id"], "cancelado")
    assert not ph.ref_pendiente(ref)


def test_barrido_vence_ordenes_y_devuelve_el_pago_tardio(db, gw, monkeypatch):
    cli = _cli(monkeypatch)
    # Ecuador: sin retorno (cerró la pestaña sin pagar) → vence y suelta el horario.
    r = _asegurar(cli, "c_gye", ["15:00"])
    o = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()["orden"]]
    assert ph.barrer()["vencidas"] == 0 and o["estado"] == "pendiente"
    o["vence_ts"] = time.time() - 1
    assert ph.barrer()["vencidas"] == 1 and o["estado"] == "vencido" and r["ids"][0] not in db.reservas
    # Bolivia: antes de vencer se consulta a Libélula; si ya pagó, se finaliza.
    r2 = _asegurar(cli, "c_lp", ["15:00"])
    o2 = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r2["ids"], "firma": r2["firma"]}).json()["orden"]]
    gw.lib_pagadas.add(o2["ref_pasarela"])
    o2["vence_ts"] = time.time() - 1
    ph.barrer()
    assert o2["estado"] == "aprobado" and db.reservas[r2["ids"][0]]["estado"] == "confirmada"
    # Pago TARDÍO: la orden venció (horario suelto) y Libélula avisa después.
    r3 = _asegurar(cli, "c_lp", ["17:00"])
    o3 = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r3["ids"], "firma": r3["firma"]}).json()["orden"]]
    o3["vence_ts"] = time.time() - 1
    ph.barrer()
    assert o3["estado"] == "vencido" and r3["ids"][0] not in db.reservas
    gw.lib_pagadas.add(o3["ref_pasarela"])
    tx = stores.libelula_deudas[o3["ref_pasarela"]]["id_transaccion"]
    TestClient(app).get(f"/pagos/bo/callback?transaction_id={tx}")
    # Billetera de Ana en soles ≠ Bs: devolución MANUAL a la vista del operador.
    assert o3["estado"] == "aprobado_sin_reserva" and o3["devolucion"] == "manual"
    cw = stores.cancelaciones_web[-1]
    assert cw["reembolso"] == "manual" and cw["motivo"] == "pago_sin_reserva" and cw["moneda_iso"] == "BOB"
    assert cw["monto_devuelto_centimos"] == o3["monto_centimos"] and cw["pasarela"] == "libelula"
    assert "el horario ya se había liberado" in cli.get(f"/web/pago/{o3['id']}").text
    # Callback repetido: no duplica nada.
    TestClient(app).get(f"/pagos/bo/callback?transaction_id={tx}")
    assert len([c for c in stores.cancelaciones_web if c.get("orden_web") == o3["id"]]) == 1
    # Con la billetera en Bs, el pago tardío vuelve a su SALDO al instante.
    bo = "bo2@gmail.com"
    stores.clientes_pago[bo] = {"pais_casa": "BO", "pais_casa_en": datetime.now(timezone.utc).isoformat()}
    stores.saldos.pop(bo, None)
    cb = _cli(monkeypatch, bo)
    f = _manana()
    r4 = cb.post("/web/asegurar", json={"cancha_id": "c_lp", "horas": [{"fecha": f, "hora": "19:00"}], "extras": [],
                                         "nombre": "Bo Dos", "celular": "71234567", "email": bo}).json()
    o4 = stores.pagos_web[cb.post("/web/pago/reserva", json={"ids": r4["ids"], "firma": r4["firma"]}).json()["orden"]]
    o4["vence_ts"] = time.time() - 1
    ph.barrer()
    gw.lib_pagadas.add(o4["ref_pasarela"])
    o4["ult_consulta"] = 0
    ph.barrer()  # sin callback: el barrido le pregunta a Libélula por los vencidos de las últimas 24 h
    assert o4["estado"] == "aprobado_sin_reserva" and o4["devolucion"] == "saldo" and stores.saldo_centimos(bo) == o4["monto_centimos"]


def test_cancelar_reserva_pagada_por_pasarela_deja_devolucion_manual(db, gw, monkeypatch):
    llamadas = []
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: llamadas.append(kw) or {"ok": True, "refund_id": "rf"})
    cli = _cli(monkeypatch)
    r = _asegurar(cli, "c_gye", ["15:00"])
    o = stores.pagos_web[cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()["orden"]]
    cli.get(f"/web/pago/{o['id']}/retorno?id=TXC&clientTransactionId={o['ref_pasarela']}", follow_redirects=False)
    filas = web._filas_de_ref(r["ids"][0])
    est = web.estado_cancelacion(filas, db.canchas["c_gye"], "ana@gmail.com")
    # Billetera en soles: no se ofrece devolver dólares a su saldo; al medio, la coordina el operador.
    assert [x["medio"] for x in est["politica"]["opciones"]] == ["original"] and est["reembolso_directo"] is False
    assert est["politica"]["opciones"][0]["etiqueta"] == "Al mismo medio de pago (tarjeta / QR)"
    j = cli.post("/web/cancelar", json={"ref": r["ids"][0], "medio": "saldo"}).json()
    assert j["ok"] and j["reembolso"] == "manual" and llamadas == [] and stores.saldo_centimos("ana@gmail.com") == 0
    assert stores.cancelaciones_web[-1]["reembolso"] == "manual" and stores.cancelaciones_web[-1]["moneda_iso"] == "USD"
    assert stores.pago_por_charge(r["ids"][0]).estado == "anulado"  # la liquidación del dueño se revirtió


# ── sin credenciales: PRD vs QAS ──────────────────────────────────────────────

def test_prd_sin_credenciales_manda_a_la_app(db, gw, monkeypatch):
    monkeypatch.setattr(config, "PAYPHONE_TOKEN", "")
    monkeypatch.setattr(config, "LIBELULA_APPKEY", "")
    for ent in ("PRD", ""):  # PRD y ambiente sin declarar (fail-closed): nunca se simula
        monkeypatch.setattr(config, "PICHANGOL_ENTORNO", ent)
        cli = _cli(monkeypatch)
        assert "Reserva desde la app" in cli.get("/reservar/c_gye").text
        assert "Reserva desde la app" in cli.get("/reservar/c_lp").text
        assert _asegurar(cli, "c_gye", ["15:00"])["error"] == "pago_no_disponible"
        stores.clientes_pago["ec@gmail.com"] = {"pais_casa": "EC", "pais_casa_en": datetime.now(timezone.utc).isoformat()}
        ce = _cli(monkeypatch, "ec@gmail.com")
        assert "Recargar en la app" in ce.get("/mi-billetera").text
        assert ce.post("/web/billetera/recargar-pasarela", json={"monto": 10}).status_code == 409
    # Ni en QAS se simula con una llave live de Culqi cargada.
    monkeypatch.setattr(config, "PICHANGOL_ENTORNO", "QAS")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_live_x")
    assert ph.pasarela_para("USD") == "" and not ph.simulada_permitida()


def test_qas_sin_credenciales_usa_la_pasarela_simulada(db, monkeypatch):
    monkeypatch.setattr(config, "PAYPHONE_TOKEN", "")
    monkeypatch.setattr(config, "LIBELULA_APPKEY", "")
    monkeypatch.setattr(config, "PICHANGOL_ENTORNO", "QAS")
    stores.config["cargo_activo_reservas"] = "1"
    cli = _cli(monkeypatch)
    html = cli.get("/reservar/c_gye").text
    assert "Pago de prueba · QAS" in html and '"pasarela": "sim"' in html
    r = _asegurar(cli, "c_gye", ["15:00"], extras=["arbitro"])
    p = cli.post("/web/pago/reserva", json={"ids": r["ids"], "firma": r["firma"]}).json()
    assert p["ok"] and p["url"] == f"/web/pago/{p['orden']}/simulado"
    sim = cli.get(p["url"]).text
    assert "PAGO DE PRUEBA · QAS" in sim and "No se cobra dinero real" in sim and "window.alert(" not in sim
    # Otra cuenta no puede aprobar la orden de Ana.
    otro = _cli(monkeypatch, "otro@gmail.com")
    assert otro.post(f"/web/pago/{p['orden']}/simulado", json={"aprobar": True}).status_code == 404
    cli = _cli(monkeypatch)
    j = cli.post(f"/web/pago/{p['orden']}/simulado", json={"aprobar": True}).json()
    assert j["estado"] == "aprobado" and j["url"].startswith("/reserva/")
    assert db.reservas[r["ids"][0]]["estado"] == "confirmada"
    cobro = _pagos("cobro_web", culqi_charge_id=f"sim:{p['orden']}")
    assert len(cobro) == 1 and cobro[0].moneda == "USD" and cobro[0].monto_centimos == r["total_centimos"]
    # Recarga de prueba en Bs con bono.
    stores.config.update({"promo_bono_recarga_pct": "10", "promo_bono_recarga_min": "5", "promo_bono_recarga_tope": "50"})
    bo = "bosim@gmail.com"
    stores.clientes_pago[bo] = {"pais_casa": "BO", "pais_casa_en": datetime.now(timezone.utc).isoformat()}
    stores.saldos.pop(bo, None)
    cb = _cli(monkeypatch, bo)
    pr_ = cb.post("/web/billetera/recargar-pasarela", json={"monto": 50}).json()
    assert cb.post(f"/web/pago/{pr_['orden']}/simulado", json={"aprobar": True}).json()["url"] == f"/mi-billetera?recarga={pr_['orden']}"
    cb.post(f"/web/pago/{pr_['orden']}/simulado", json={"aprobar": True})
    assert stores.saldo_centimos(bo) == 5000 + 500
    # Rechazo simulado: suelta el horario.
    cli = _cli(monkeypatch)
    r2 = _asegurar(cli, "c_gye", ["17:00"])
    p2 = cli.post("/web/pago/reserva", json={"ids": r2["ids"], "firma": r2["firma"]}).json()
    assert cli.post(f"/web/pago/{p2['orden']}/simulado", json={"aprobar": False}).json()["estado"] == "rechazado"
    assert r2["ids"][0] not in db.reservas


def test_fachada_ec_despacha_a_payphone(monkeypatch):
    from pagos import pasarela_ec
    monkeypatch.delenv("PASARELA_EC", raising=False)
    assert pasarela_ec.clave() == "payphone" and pasarela_ec.nombre() == "PayPhone"
    monkeypatch.setenv("PASARELA_EC", "desconocida")
    assert pasarela_ec.clave() == "payphone"  # fail-safe
    assert pasarela_ec.reembolsar(transaction_id="1", client_tx_id="x", monto_centavos=1) == {"ok": False, "error": "no_soportado"}
    s = Stores()
    s.pagos_web["pw_x"] = {"id": "pw_x", "estado": "pendiente"}
    t = Stores()
    t.load_state(s.to_state())
    assert t.pagos_web == {"pw_x": {"id": "pw_x", "estado": "pendiente"}}
