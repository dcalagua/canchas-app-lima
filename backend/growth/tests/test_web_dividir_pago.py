"""CADA UNO PAGA SU PARTE (pago dividido de una reserva web, dinero directo al
club): reparto en céntimos, hold largo, partes con Culqi del club o voucher,
confirmación única, vencimiento con devoluciones, cancelación posterior,
concurrencia de la última parte y moneda de la cancha."""

import os
import sys
import threading
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from pagos import cobro_directo as cd  # noqa: E402
from pagos import culqi  # noqa: E402
from pagos import division as dv  # noqa: E402
from web import datos  # noqa: E402
from web import router as web  # noqa: E402
from tests.test_cobro_directo import DUENO, PK, SK, _png, directo  # noqa: E402,F401
from tests.test_web_reservas import _manana, client, db  # noqa: E402,F401
from tests.conftest_pg import pg_local  # noqa: E402,F401

ANA = {"X-User-Token": "tok-ana"}      # organiza
BETO = {"X-User-Token": "tok-beto"}
CARO = {"X-User-Token": "tok-caro"}


@pytest.fixture
def div(directo, monkeypatch):
    from pagos import router as pr
    monkeypatch.setattr(pr, "_email_de_token", lambda t: {"tok-dueno": "dueno@x.com", "tok-ana": "ana@x.com",
                                                         "tok-beto": "beto@x.com", "tok-caro": "caro@x.com",
                                                         "tok-otro": "otro@x.com"}.get(t))
    repo = dv.RepoMemoria()
    dv.usar_repo(repo)
    cargos, reembolsos = [], []

    def cargo(**kw):
        cargos.append(kw)
        return {"ok": True, "charge_id": f"chr_{len(cargos)}"}

    def reembolso(**kw):
        reembolsos.append(kw)
        return {"ok": True, "refund_id": f"ref_{len(reembolsos)}"}
    monkeypatch.setattr(culqi, "crear_cargo", cargo)
    monkeypatch.setattr(culqi, "reembolsar", reembolso)
    yield {**directo, "div": repo, "cargos": cargos, "reembolsos": reembolsos}
    dv.usar_repo(dv.RepoPG())


def _medios():
    return client.put("/club/pagos/medios", headers=DUENO, json={"medios": [
        {"tipo": "yape", "titular": "Club Raqueta SAC", "numero": "987654321"}]})


def _culqi_club():
    return client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})


def _dividir(n=3, horas=("18:00", "19:00", "20:00"), cancha="c_lima", headers=ANA, **extra):
    return client.post("/web/asegurar", headers=headers, json={
        "cancha_id": cancha, "nombre": "Ana Pérez", "email": "ana@x.com", "celular": "987654321",
        "horas": [{"fecha": _manana(), "hora": h} for h in horas], "dividir": n, **extra}).json()


def _token(r):
    return r["division"]["url"].rsplit("/", 1)[-1]


def _tomar(tok, h, falta=False):
    return client.post(f"/web/dividir/{tok}/tomar", headers=h, json={"lo_que_falta": falta}).json()


def _png_distinto(seed: int) -> str:
    import base64
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (seed * 37 % 255, 40, 200)).save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _pagar_voucher(tok, h, op, seed):
    t = _tomar(tok, h)
    assert t["ok"], t
    v = client.post(f"/web/dividir/{tok}/voucher", headers=h, json={
        "partes": t["partes"], "medio": "yape", "operacion": op, "imagen": _png_distinto(seed)}).json()
    assert v["ok"], v
    return t, v


def _aprobar(pid):
    return client.post(f"/club/pagos/vouchers/{pid}/aprobar", headers=DUENO).json()


def _info_cargo(d, partes, monto, email="beto@x.com", **raw):
    """Lo que devuelve `culqi.obtener_cargo` para un cargo de una parte."""
    return {"ok": True, "capturado": True, "moneda": "PEN", "monto_centimos": monto, "reembolsado_centimos": 0,
            "metadata": {"canal": "division", "division_id": d["id"], "partes": ",".join(partes), "email": email},
            "raw": {"capture": True, "currency_code": "PEN", "outcome": {"type": "venta_exitosa"}, **raw}}


# ── reglas puras ─────────────────────────────────────────────────────────────

def test_reparto_en_centimos_exactos_y_plazo():
    assert dv.calcular_partes(10000, 3) == [3334, 3333, 3333]
    assert dv.calcular_partes(18000, 7) == [2574] + [2571] * 6 and sum(dv.calcular_partes(18000, 7)) == 18000
    for total in (301, 999, 12345, 600000):
        for n in range(2, 13):
            p = dv.calcular_partes(total, n)
            assert sum(p) == total and p[0] >= p[1] and p[0] - p[1] < n
    assert dv.max_partes(6000) == 12 and dv.max_partes(900) == 3 and dv.max_partes(500) == 1
    ahora = dv._ahora()
    assert dv.vence_para(ahora + timedelta(hours=10), ahora) == ahora + timedelta(hours=2)
    assert dv.vence_para(ahora + timedelta(hours=2), ahora) == ahora + timedelta(hours=1)   # 1 h antes del turno
    assert dv.vence_para(ahora + timedelta(minutes=80), ahora) is None                       # quedan < 30 min de plazo
    assert dv.es_ref("div_1_ab#2") and not dv.es_ref("grp_web_1") and dv.id_de_cobro("div:div_1") == "div_1"


def test_sql_del_hold_dividido_tiene_su_propio_tope():
    import re
    assert "'division' THEN %s" in datos._SQL_HOLD_VENCIDO
    assert len(re.findall(r"(?<!%)%s", datos._SQL_HOLD_VENCIDO)) == len(datos._cortes_hold()) == 4
    assert datos.HOLD_DIVISION_MAX_SEGUNDOS > dv.horas_plazo() * 3600


# ── ficha ────────────────────────────────────────────────────────────────────

def test_ficha_ofrece_dividir_solo_con_cobro_directo_y_tablas(div):
    assert "id='divBox'" not in client.get("/reservar/c_lima").text     # sin cobro directo
    _medios()
    html = client.get("/reservar/c_lima").text
    assert "id='divBox'" in html and "pcgDividirN" in html and "data-mon='S/'" in html
    dv.usar_repo(dv.RepoPG())   # sin la migración 0006 → la opción no existe
    assert "id='divBox'" not in client.get("/reservar/c_lima").text
    r = _dividir()
    assert r["ok"] is False and r["error"] == "dividir_no_disponible"


def test_no_se_combina_y_valida_partes_y_plazo(div, monkeypatch):
    _medios()
    assert _dividir(n=1)["error"] == "dividir_partes" and _dividir(n=13)["error"] == "dividir_partes"
    assert _dividir(n=12, horas=("10:00",))["error"] == "dividir_monto"     # S/ 30 entre 12 < S/ 3 c/u
    r = _dividir(extras=[{"clave": "arbitro"}], fidelidad=False, puntos=True)
    assert r["ok"] is False   # puntos no aplican con cobro directo (regla previa) ni se dividen
    monkeypatch.setitem(stores.config, "dividir_margen_min", "240")
    monkeypatch.setattr(dv, "vence_para", lambda inicio, ahora=None: None)
    assert _dividir()["error"] == "dividir_muy_tarde"
    assert not div["db"].reservas   # nada quedó apartado


def test_sena_no_se_divide(div, db):
    db.canchas["c_lima"]["sena_pct"] = 30
    _medios()
    r = _dividir(pago="sena")
    assert r["ok"] is False and r["error"] == "dividir_no_combinable" and "seña" in r["mensaje"]


# ── camino feliz ─────────────────────────────────────────────────────────────

def test_dos_amigos_con_voucher_y_el_organizador_con_culqi_confirma_una_vez(div):
    _medios()
    _culqi_club()
    r = _dividir()
    assert r["ok"], r
    tok = _token(r)
    assert r["division"]["partes"] == [6000, 6000, 6000]
    filas = [div["db"].reservas[i] for i in r["ids"]]
    assert all(f["medio_pago"] == "division" and f["estado"] == "nueva" for f in filas)
    # El navegador del organizador no suelta el horario al salir de la ficha.
    assert client.post("/web/liberar", json={"ids": r["ids"], "firma": web._firma(r["ids"])}).json()["error"] == "pago_en_curso"
    # Dos amigos pagan con comprobante; el club aprueba.
    _pagar_voucher(tok, BETO, "OP-B1", 1)
    _pagar_voucher(tok, CARO, "OP-C2", 2)
    est = client.get(f"/web/dividir/{tok}/estado", headers=ANA).json()
    assert est["pagadas"] == 0 and est["en_revision"] == 2 and est["organizador"]
    assert "beto@x.com" not in str(est) and "caro@x.com" not in str(est)   # nunca correos ajenos
    bandeja = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"]
    assert len(bandeja) == 2 and {p["monto_centimos"] for p in bandeja} == {6000}
    assert all("pago dividido" in p["jugador_nombre"] for p in bandeja)
    for p in bandeja:
        assert _aprobar(p["id"])["ok"]
    assert all(div["db"].reservas[i]["estado"] == "nueva" for i in r["ids"])    # aún falta la parte del organizador
    # Un voucher en revisión NO cuenta: la reserva solo se confirma con todo pagado.
    t = _tomar(tok, ANA)
    assert t["ok"] and t["monto_centimos"] == 6000
    p = client.post(f"/web/dividir/{tok}/pagar", headers=ANA, json={"partes": t["partes"], "token": "tkn_1", "medio": "yape"}).json()
    assert p["ok"] and p["estado"] == "completa", p
    assert div["cargos"][0]["llave"] == SK and div["cargos"][0]["monto_centimos"] == 6000
    assert div["cargos"][0]["metadata"]["canal"] == "division"
    filas = [div["db"].reservas[i] for i in r["ids"]]
    assert all(f["estado"] == "confirmada" and f["pagado"] and f["medio_pago"] == "dividido" and f["usuario"] == "ana@x.com"
               for f in filas)
    cobros = [x for x in stores.pagos if x.tipo == "cobro_directo"]
    assert len(cobros) == 1 and cobros[0].monto_centimos == 18000 and cobros[0].culqi_charge_id.startswith("div:")
    # UNA comisión sobre el total (5 % de S/ 180), como deuda porque el saldo es 0.
    assert cd.deuda_centimos("dueno@x.com", "PEN") == 900
    assert dv.repo().por_id(dv.id_de_cobro(cobros[0].culqi_charge_id))["estado"] == "confirmada"
    dv.barrer()   # el barrido no vuelve a confirmar ni a cobrar
    assert len([x for x in stores.pagos if x.tipo == "cobro_directo"]) == 1 and cd.deuda_centimos("dueno@x.com", "PEN") == 900
    assert any(a[0] == "beto@x.com" and "confirmada" in a[1].lower() for a in div["pushes"])
    est = client.get(f"/web/dividir/{tok}/estado", headers=ANA).json()
    assert est["estado"] == "confirmada" and est["pagadas"] == 3 and est["comprobante"].startswith("/reserva/")


def test_organizador_paga_lo_que_falta_en_un_solo_cargo(div):
    _medios()
    _culqi_club()
    r = _dividir(n=4, horas=("18:00", "19:00"))    # S/ 120 entre 4 = 30 c/u
    tok = _token(r)
    _pagar_voucher(tok, BETO, "OP-111", 3)
    assert _tomar(tok, CARO, falta=True)["error"] == "solo_organizador"
    t = _tomar(tok, ANA, falta=True)
    assert t["ok"] and t["monto_centimos"] == 9000 and sorted(t["n"]) == [0, 2, 3]
    p = client.post(f"/web/dividir/{tok}/pagar", headers=ANA, json={"partes": t["partes"], "token": "tkn", "medio": "tarjeta"}).json()
    assert p["ok"] and p["estado"] == "ok"   # el voucher de Beto sigue en revisión
    partes = {x["n"]: x for x in div["div"].partes(div["div"].por_token(tok)["id"])}
    assert partes[2]["cobro_id"] == "chr_1#2" and partes[2]["por_organizador"] and partes[0]["cobro_id"] == "chr_1#0"
    pid = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"][0]["id"]
    assert _aprobar(pid)["ok"]
    assert all(div["db"].reservas[i]["estado"] == "confirmada" for i in r["ids"])


# ── voucher rechazado / doble pago / concurrencia ────────────────────────────

def test_voucher_rechazado_deja_la_parte_libre(div):
    _medios()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    t, _v = _pagar_voucher(tok, BETO, "OP-9", 4)
    pid = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"][0]["id"]
    assert client.post(f"/club/pagos/vouchers/{pid}/rechazar", headers=DUENO, json={"motivo": "monto"}).json()["ok"]
    est = client.get(f"/web/dividir/{tok}/estado", headers=BETO).json()
    assert est["estado"] == "abierta" and est["partes"][1]["estado"] == "libre"
    assert div["db"].reservas   # el horario sigue apartado
    t2 = _tomar(tok, CARO)
    assert t2["ok"] and t2["partes"] == t["partes"]


def test_no_se_paga_dos_veces_la_misma_parte(div):
    _medios()
    _culqi_club()
    tok = _token(_dividir())
    t = _tomar(tok, BETO)
    assert _tomar(tok, BETO)["partes"] == t["partes"]        # retomar = la MISMA parte
    # Otro no puede pagar la parte que tomó Beto.
    assert client.post(f"/web/dividir/{tok}/pagar", headers=CARO, json={"partes": t["partes"], "token": "x"}).json()["error"] == "no_tomada"
    assert client.post(f"/web/dividir/{tok}/pagar", headers=BETO, json={"partes": t["partes"], "token": "x"}).json()["ok"]
    assert _tomar(tok, BETO)["error"] == "ya_pagaste"
    assert client.post(f"/web/dividir/{tok}/pagar", headers=BETO, json={"partes": t["partes"], "token": "x"}).json()["error"] == "no_tomada"
    assert len(div["cargos"]) == 1
    # El webhook del MISMO cargo no la cuenta otra vez (idempotente por cobro).
    d = div["div"].por_token(tok)
    r = dv.conciliar_cargo(_info_cargo(d, t["partes"], 6000), "chr_1", SK, "dueno@x.com")
    assert r == {"ok": True, "duplicado": True} and not div["reembolsos"]
    # El organizador no puede tomar la parte de un amigo como "suya".
    assert _tomar(tok, ANA)["ok"] and _tomar(tok, ANA)["n"] == [0]


def test_dos_amigos_por_la_ultima_parte_y_ultima_parte_concurrente(div, monkeypatch):
    _medios()
    _culqi_club()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    d = div["div"].por_token(tok)
    res = []
    hilos = [threading.Thread(target=lambda e=e: res.append(dv.tomar(d, e, e))) for e in ("beto@x.com", "caro@x.com")]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(bool(x["ok"]) for x in res) == [False, True]
    assert next(x for x in res if not x["ok"])["error"] == "sin_partes"
    # Las dos últimas partes se pagan a la vez: UNA sola confirmación.
    llamadas = []
    real = dv.confirmar
    monkeypatch.setattr(dv, "confirmar", lambda i: llamadas.append(i) or real(i))
    ganador = next(x for x in res if x["ok"])
    quien = "beto@x.com" if div["div"].partes(d["id"])[1]["pagador_email"] == "beto@x.com" else "caro@x.com"
    t0 = dv.tomar(d, "ana@x.com", "Ana")
    out = []
    hs = [threading.Thread(target=lambda: out.append(dv.pagar_culqi(d, quien, "", ganador["partes"], "t1", "yape"))),
          threading.Thread(target=lambda: out.append(dv.pagar_culqi(d, "ana@x.com", "", t0["partes"], "t2", "yape")))]
    [h.start() for h in hs]
    [h.join() for h in hs]
    assert all(x["ok"] for x in out) and sorted(x["estado"] for x in out) == ["completa", "ok"]
    assert llamadas == [d["id"]]
    assert len([x for x in stores.pagos if x.tipo == "cobro_directo"]) == 1


# ── vencimiento ──────────────────────────────────────────────────────────────

def test_vence_incompleta_avisa_y_devuelve_cada_parte(div, monkeypatch):
    _medios()
    _culqi_club()
    r = _dividir()
    tok = _token(r)
    d = div["div"].por_token(tok)
    t = _tomar(tok, BETO)
    client.post(f"/web/dividir/{tok}/pagar", headers=BETO, json={"partes": t["partes"], "token": "t", "medio": "tarjeta"})
    _pagar_voucher(tok, CARO, "OP-CARO", 5)
    pid_caro = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"][0]["id"]
    assert _aprobar(pid_caro)["ok"]
    # El organizador también reporta un voucher que el club nunca revisa.
    _pagar_voucher(tok, ANA, "OP-ANA", 6)
    # 30 min antes del vencimiento: aviso al organizador (una vez).
    antes = d["vence_en"] - timedelta(minutes=20)
    monkeypatch.setattr(dv, "_ahora", lambda: antes)
    assert dv.barrer(antes)["avisos"] == 1 and dv.barrer(antes)["avisos"] == 0
    assert any(a[0] == "ana@x.com" and "Faltan" in a[1] for a in div["pushes"])
    # Vence: el horario se suelta y se devuelve todo.
    despues = d["vence_en"] + timedelta(seconds=5)
    monkeypatch.setattr(dv, "_ahora", lambda: despues)
    assert dv.barrer(despues)["vencidas"] == 1
    assert not any(i in div["db"].reservas for i in r["ids"])
    partes = {p["n"]: p for p in div["div"].partes(d["id"])}
    assert partes[1]["estado"] == "reembolsada" and div["reembolsos"][0] == {
        "charge_id": "chr_1", "monto_centimos": 6000, "motivo": "solicitud_comprador", "llave": SK}
    assert partes[2]["estado"] == "devolver" and partes[2]["devolver_centimos"] == 6000          # voucher aprobado
    assert partes[0]["estado"] == "devolver" and partes[0]["nota"] == "sin_revisar"            # voucher sin revisar
    assert cd.repo().pagos[partes[0]["pago_manual_id"]]["estado"] == "vencido"
    assert not [x for x in stores.pagos if x.tipo == "cobro_directo"] and cd.deuda_centimos("dueno@x.com") == 0
    assert any(a[0] == "dueno@x.com" and "Devuelve" in a[1] for a in div["pushes"])
    # El club ve y resuelve sus devoluciones.
    pend = dv.devoluciones_pendientes("dueno@x.com")
    assert {p["n"] for p in pend} == {0, 2}
    assert dv.resolver_devolucion(partes[2]["id"], "dueno@x.com", "no_recibido")["error"] == "accion"
    assert dv.resolver_devolucion(partes[2]["id"], "dueno@x.com", "devuelta")["ok"]
    assert dv.resolver_devolucion(partes[0]["id"], "dueno@x.com", "no_recibido")["ok"]
    assert dv.resolver_devolucion(partes[0]["id"], "otro@x.com", "devuelta")["error"] == "no_encontrado"
    assert not dv.devoluciones_pendientes("dueno@x.com")
    # Tarde ya no se puede tomar ni pagar.
    assert _tomar(tok, BETO)["error"] in ("cerrada", "ya_pagaste")


def test_pago_que_entra_con_la_division_cerrada_se_devuelve(div):
    _medios()
    _culqi_club()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    d = div["div"].por_token(tok)
    t = dv.tomar(d, "beto@x.com", "Beto")
    dv.cancelar(d, "ana@x.com")      # el organizador cancela mientras Beto paga
    r = dv.pagar_culqi(d, "beto@x.com", "", t["partes"], "t", "yape")
    assert r["ok"] is False   # la parte ya se soltó al cerrar
    out = dv._registrar_cargo(d, div["div"].partes(d["id"])[1:], "beto@x.com", "chr_tarde", 6000, "yape", SK)
    assert out["ok"] is False and div["reembolsos"][-1]["charge_id"] == "chr_tarde"


def test_voucher_aprobado_tarde_queda_para_devolver(div, monkeypatch):
    _medios()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    d = div["div"].por_token(tok)
    _pagar_voucher(tok, BETO, "OP-T", 7)
    pid = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"][0]["id"]
    div["div"].transicion(d["id"], ("abierta",), "vencida", "vencida")   # cerró en ese instante
    out = _aprobar(pid)
    assert out["ok"] and out.get("aviso") == "division_cerrada"
    assert div["div"].partes(d["id"])[1]["estado"] == "devolver"


# ── cancelación de la reserva ya confirmada ──────────────────────────────────

def test_cancelar_reserva_dividida_devuelve_a_cada_uno(div):
    _medios()
    _culqi_club()
    r = _dividir()
    tok = _token(r)
    for h in (BETO, ANA):
        t = _tomar(tok, h)
        client.post(f"/web/dividir/{tok}/pagar", headers=h, json={"partes": t["partes"], "token": "t", "medio": "yape"})
    t, _v = _pagar_voucher(tok, CARO, "OP-CC", 8)
    pid = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"][0]["id"]
    assert _aprobar(pid)["ok"]
    assert cd.deuda_centimos("dueno@x.com", "PEN") == 900
    filas = web._filas_de_ref(r["grupo"])
    c = datos.cancha("c_lima")
    est = web.estado_cancelacion(filas, c, "ana@x.com")
    assert est["puede"] and "cada uno recibe su parte" in str(est["politica"])
    out = web._cancelar_reserva(filas, c, "ana@x.com")
    assert out["ok"] and out["reembolso"] == "manual"          # la parte con voucher la devuelve el club
    assert sorted(x["charge_id"] for x in div["reembolsos"]) == ["chr_1", "chr_2"]
    assert all(x["monto_centimos"] == 6000 and x["llave"] == SK for x in div["reembolsos"])
    partes = {p["n"]: p for p in div["div"].partes(div["div"].por_token(tok)["id"])}
    assert partes[2]["estado"] == "devolver" and partes[2]["nota"] == "reserva_cancelada"
    assert div["div"].por_token(tok)["estado"] == "cancelada"
    assert cd.deuda_centimos("dueno@x.com", "PEN") == 0          # la comisión se revierte
    assert not any(i in div["db"].reservas for i in r["ids"])


# ── moneda ───────────────────────────────────────────────────────────────────

def test_division_en_dolares_solo_con_comprobante(div, db):
    div["repo"].reemplazar_medios("dueno@x.com", [{"tipo": "qr", "titular": "Club Sur", "numero": "0991234567", "banco": "",
                                                   "cuenta": "", "cci": "", "qr_url": "", "nota": ""}])
    html = client.get("/reservar/c_gye").text
    assert "id='divBox'" in html and "data-mon='$'" in html
    r = _dividir(n=3, horas=("18:00", "19:00"), cancha="c_gye")     # $ 20 entre 3
    assert r["ok"], r
    assert r["division"]["moneda"] == "USD" and r["division"]["partes"] == [668, 666, 666]
    tok = _token(r)
    t = _tomar(tok, BETO)
    assert client.post(f"/web/dividir/{tok}/pagar", headers=BETO, json={"partes": t["partes"], "token": "x"}).json()["error"] == "pago_no_disponible"
    v = client.post(f"/web/dividir/{tok}/voucher", headers=BETO, json={"partes": t["partes"], "medio": "qr", "operacion": "QR-1",
                                                                       "imagen": _png_distinto(9)}).json()
    assert v["ok"], v
    assert cd.repo().pagos[v["pago_id"]]["moneda"] == "USD" and cd.repo().pagos[v["pago_id"]]["monto_centimos"] == 666


def test_pagina_del_enlace_pide_sesion_y_muestra_el_progreso(div, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from tests.test_web_reservas import _entrar_como
    _medios()
    tok = _token(_dividir())
    assert client.get(f"/dividir/{tok}", follow_redirects=False).headers["location"].startswith("/entrar?volver=")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, "beto@x.com", "Beto Ruiz")
    html = cli.get(f"/dividir/{tok}").text
    assert "Cada uno paga su parte" in html and "window.__div=" in html and "Club Raqueta" in html
    assert "ana@x.com" not in html and "S/ 180.00" in html
    assert "Este enlace no existe" in cli.get("/dividir/zzz").text
    # Mis reservas del amigo: "Jugada con …" tras pagar su parte.
    _pagar_voucher(tok, BETO, "OP-MR", 11)
    mr = cli.get("/mis-reservas").text
    assert "Pagos divididos" in mr and "Jugada con Ana P." in mr


# ── revisión independiente (oct-2026): regresiones ───────────────────────────

def _pagar_culqi(tok, h, falta=False, medio="yape"):
    t = _tomar(tok, h, falta=falta)
    assert t["ok"], t
    p = client.post(f"/web/dividir/{tok}/pagar", headers=h, json={"partes": t["partes"], "token": "tkn", "medio": medio}).json()
    assert p["ok"], p
    return t, p


def test_lectura_fallida_al_confirmar_no_devuelve_y_se_reintenta(div, monkeypatch):
    """Un error de la base al leer el apartado NO es "apartado perdido": nadie
    recibe devolución, el horario sigue apartado y el barrido vuelve a confirmar."""
    _medios()
    _culqi_club()
    r = _dividir(n=2, horas=("18:00",))
    tok = _token(r)
    _pagar_culqi(tok, BETO)
    real = datos.reservas_de
    caida = {"on": True}

    def rd(ids, estricto=False):
        if estricto and caida["on"]:
            raise RuntimeError("postgres no responde")
        return real(ids)
    monkeypatch.setattr(datos, "reservas_de", rd)
    _t, p = _pagar_culqi(tok, ANA)
    assert p["estado"] == "completa"
    d = div["div"].por_token(tok)
    assert d["estado"] == "completa" and not div["reembolsos"]
    assert all(div["db"].reservas[i]["estado"] == "nueva" for i in r["ids"])     # el turno sigue apartado
    assert not [x for x in stores.pagos if x.tipo == "cobro_directo"]
    assert dv.barrer()["confirmadas"] == 0                                         # la base sigue caída: reintenta luego
    caida["on"] = False
    assert dv.barrer()["confirmadas"] == 1
    assert div["div"].por_token(tok)["estado"] == "confirmada" and not div["reembolsos"]
    assert all(div["db"].reservas[i]["estado"] == "confirmada" for i in r["ids"])
    # Y cuando la lectura SÍ funciona y las filas ya no están, recién ahí se devuelve.
    r2 = _dividir(n=2, horas=("21:00",))
    tok2 = _token(r2)
    _pagar_culqi(tok2, BETO)
    for i in r2["ids"]:
        div["db"].reservas.pop(i)
    _pagar_culqi(tok2, ANA)
    d2 = div["div"].por_token(tok2)
    assert d2["estado"] == "vencida" and d2["motivo"] == "apartado_perdido" and len(div["reembolsos"]) == 2


def test_si_la_base_no_confirma_las_filas_no_se_cobra_comision_y_se_reintenta(div, monkeypatch):
    _medios()
    _culqi_club()
    r = _dividir(n=2, horas=("18:00",))
    tok = _token(r)
    real = datos.confirmar_reservas
    monkeypatch.setattr(datos, "confirmar_reservas", lambda *a, **k: False)   # error de Postgres tragado
    _pagar_culqi(tok, BETO)
    _pagar_culqi(tok, ANA)
    d = div["div"].por_token(tok)
    fila = div["db"].reservas[r["ids"][0]]
    assert d["estado"] == "completa" and fila["estado"] == "nueva" and fila["medio_pago"] == "division"
    assert cd.deuda_centimos("dueno@x.com", "PEN") == 0 and not [x for x in stores.pagos if x.tipo == "cobro_directo"]
    monkeypatch.setattr(datos, "confirmar_reservas", real)   # la base vuelve
    assert dv.barrer()["confirmadas"] == 1
    assert div["div"].por_token(tok)["estado"] == "confirmada" and fila is not None
    assert div["db"].reservas[r["ids"][0]]["estado"] == "confirmada"
    assert len([x for x in stores.pagos if x.tipo == "cobro_directo"]) == 1 and cd.deuda_centimos("dueno@x.com", "PEN") == 300


def test_cobro_directo_normal_si_la_base_no_confirma_devuelve_y_no_cobra_comision(div, monkeypatch):
    _culqi_club()
    a = client.post("/web/asegurar", headers=ANA, json={
        "cancha_id": "c_lima", "nombre": "Ana Pérez", "email": "ana@x.com", "celular": "987654321",
        "horas": [{"fecha": _manana(), "hora": "18:00"}]}).json()
    assert a["ok"], a
    monkeypatch.setattr(datos, "confirmar_reservas", lambda *a, **k: False)
    p = client.post("/web/pagar", headers=ANA, json={"ids": a["ids"], "firma": a["firma"], "token": "tkn_1"}).json()
    assert p["ok"] is False and p["error"] == "confirmar_fallo" and "devolvimos" in p["mensaje"]
    assert div["reembolsos"] == [{"charge_id": "chr_1", "monto_centimos": 6000, "motivo": "solicitud_comprador", "llave": SK}]
    assert not [x for x in stores.pagos if x.tipo == "cobro_directo"] and cd.deuda_centimos("dueno@x.com", "PEN") == 0
    assert a["ids"][0] not in div["db"].reservas      # el horario quedó libre
    # El webhook de ese cargo (ya devuelto) no confirma nada.
    ref_wh = div["repo"].pasarelas["dueno@x.com"]["webhook_ref"]
    monkeypatch.setattr(culqi, "obtener_cargo", lambda cid, llave=None: {
        "ok": True, "monto_centimos": 6000, "reembolsado_centimos": 6000,
        "metadata": {"canal": "directo", "reserva_ref": a["ids"][0]}})
    assert client.post(f"/pagos/culqi/webhook/club/{ref_wh}", json={"data": {"id": "chr_1"}}).json()["ignorado"] == "reembolsado"


def test_voucher_normal_aprobado_con_la_base_caida_vuelve_a_la_bandeja(div, monkeypatch):
    _medios()
    a = client.post("/web/asegurar", headers=ANA, json={
        "cancha_id": "c_lima", "nombre": "Ana Pérez", "email": "ana@x.com", "celular": "987654321",
        "horas": [{"fecha": _manana(), "hora": "18:00"}]}).json()
    v = client.post("/web/voucher", headers=ANA, json={"ids": a["ids"], "firma": a["firma"], "medio": "yape",
                                                       "operacion": "OP-777", "imagen": _png()}).json()
    assert v["ok"], v
    real = datos.confirmar_reservas
    monkeypatch.setattr(datos, "confirmar_reservas", lambda *a, **k: False)
    out = _aprobar(v["pago_id"])
    assert out["ok"] is False and out["error"] == "confirmar_fallo"
    assert cd.repo().pagos[v["pago_id"]]["estado"] == "en_revision" and cd.deuda_centimos("dueno@x.com", "PEN") == 0
    monkeypatch.setattr(datos, "confirmar_reservas", real)
    assert _aprobar(v["pago_id"])["ok"]
    assert div["db"].reservas[a["ids"][0]]["estado"] == "confirmada" and cd.deuda_centimos("dueno@x.com", "PEN") == 300


def test_webhook_de_la_division_exige_el_mismo_club_moneda_y_cargo_capturado(div, monkeypatch):
    _medios()
    _culqi_club()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    d = div["div"].por_token(tok)
    t = _tomar(tok, BETO)
    info = _info_cargo(d, t["partes"], 3000)
    # Cargo creado en la cuenta Culqi de OTRO club con la metadata copiada.
    assert dv.conciliar_cargo(info, "chr_ajeno", "sk_otro", "otro@x.com")["ignorado"] == "otro_club"
    assert dv.conciliar_cargo(info, "chr_ajeno", "sk_otro")["ignorado"] == "otro_club"
    assert dv.conciliar_cargo({**info, "moneda": "USD"}, "chr_x", SK, "dueno@x.com")["ignorado"] == "moneda"
    assert dv.conciliar_cargo({**info, "moneda": ""}, "chr_x", SK, "dueno@x.com")["ignorado"] == "moneda"
    assert dv.conciliar_cargo(_info_cargo(d, t["partes"], 3000, capture=False), "chr_x", SK,
                              "dueno@x.com")["ignorado"] == "no_capturado"
    assert dv.conciliar_cargo(_info_cargo(d, t["partes"], 3000, outcome={"type": "venta_denegada"}), "chr_x", SK,
                              "dueno@x.com")["ignorado"] == "no_capturado"
    assert dv.conciliar_cargo({**info, "reembolsado_centimos": 3000}, "chr_x", SK, "dueno@x.com")["ignorado"] == "reembolsado"
    assert div["div"].partes(d["id"])[1]["estado"] == "cobrando" and not div["reembolsos"]
    # El webhook real del club (por su ref) sí la registra.
    ref_wh = div["repo"].pasarelas["dueno@x.com"]["webhook_ref"]
    llaves = []
    monkeypatch.setattr(culqi, "obtener_cargo", lambda cid, llave=None: llaves.append(llave) or info)
    out = client.post(f"/pagos/culqi/webhook/club/{ref_wh}", json={"data": {"id": "chr_bueno"}}).json()
    assert out == {"ok": True, "registrado": True} and llaves == [SK]
    parte = div["div"].partes(d["id"])[1]
    assert parte["estado"] == "pagada" and parte["cobro_id"] == "chr_bueno#1"


def test_voucher_tras_vencer_la_toma_retoma_la_parte(div, monkeypatch):
    _medios()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    d = div["div"].por_token(tok)
    t = _tomar(tok, BETO)
    dv.barrer(dv._ahora() + timedelta(minutes=16))      # la toma de 15 min venció mientras yapeaba
    assert div["div"].partes(d["id"])[1]["estado"] == "libre"
    v = client.post(f"/web/dividir/{tok}/voucher", headers=BETO, json={
        "partes": t["partes"], "medio": "yape", "operacion": "OP-1234", "imagen": _png()}).json()
    assert v["ok"] and not v.get("tardio"), v
    parte = div["div"].partes(d["id"])[1]
    assert parte["estado"] == "en_revision" and parte["pagador_email"] == "beto@x.com"
    assert cd.repo().pagos[v["pago_id"]]["estado"] == "en_revision"
    # Si otro ya la tomó, el comprobante igual se guarda para que el club lo devuelva.
    tok2 = _token(_dividir(n=2, horas=("21:00",)))
    t2 = _tomar(tok2, BETO)
    dv.barrer(dv._ahora() + timedelta(minutes=16))
    assert _tomar(tok2, CARO)["partes"] == t2["partes"]
    v2 = client.post(f"/web/dividir/{tok2}/voucher", headers=BETO, json={
        "partes": t2["partes"], "medio": "yape", "operacion": "OP-5678", "imagen": _png_distinto(21)}).json()
    assert v2["ok"] and v2["tardio"] and "no cuenta" in v2["mensaje"] and "devolverá" in v2["mensaje"]
    assert div["div"].partes(div["div"].por_token(tok2)["id"])[1]["pagador_email"] == "caro@x.com"   # Caro no pierde su parte


def test_voucher_con_la_division_cerrada_queda_para_devolver(div, monkeypatch):
    _medios()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    d = div["div"].por_token(tok)
    t = _tomar(tok, BETO)
    assert dv.cancelar(d, "ana@x.com")["ok"]            # se cerró mientras Beto yapeaba
    v = client.post(f"/web/dividir/{tok}/voucher", headers=BETO, json={
        "partes": t["partes"], "medio": "yape", "operacion": "OP-TARDE", "imagen": _png()}).json()
    assert v["ok"] and v["tardio"] and "ya se cerró" in v["mensaje"], v
    pm = cd.repo().pagos[v["pago_id"]]
    assert pm["estado"] == "en_revision" and pm["monto_centimos"] == 3000 and "fuera de plazo" in pm["jugador_nombre"]
    assert any(a[0] == "dueno@x.com" and "fuera de plazo" in a[1] for a in div["pushes"])
    assert not dv.devoluciones_pendientes("dueno@x.com")
    # El club confirma que le llegó → queda en Devoluciones (nunca paga la reserva).
    out = _aprobar(v["pago_id"])
    assert out["ok"] and out.get("aviso") == "division_cerrada"
    pend = dv.devoluciones_pendientes("dueno@x.com")
    assert len(pend) == 1 and pend[0]["tardio"] and pend[0]["devolver_centimos"] == 3000
    assert pend[0]["pagador_email"] == "beto@x.com" and pend[0]["nota"] == "aprobado_tarde"
    from fastapi.testclient import TestClient
    from main import app
    from tests.test_web_reservas import _entrar_como
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, "dueno@x.com", "Dueño")
    html = cli.get("/anfitrion/cobros-club/devoluciones").text
    assert "pago fuera de plazo" in html and "Pago fuera de plazo: lo confirmaste" in html
    assert f"/anfitrion/pagos-por-confirmar/{v['pago_id']}/imagen" in html
    assert cli.get(f"/anfitrion/pagos-por-confirmar/{v['pago_id']}/imagen").status_code == 200
    assert dv.resolver_devolucion(pend[0]["id"], "dueno@x.com", "no_recibido")["error"] == "accion"
    assert dv.resolver_devolucion(pend[0]["id"], "dueno@x.com", "devuelta")["ok"]
    assert not dv.devoluciones_pendientes("dueno@x.com")
    # Otro comprobante tardío que el club nunca revisa → "sin revisar" (devuelve solo si lo recibió).
    tok2 = _token(_dividir(n=2, horas=("21:00",)))
    d2 = div["div"].por_token(tok2)
    t2 = _tomar(tok2, CARO)
    dv.cancelar(d2, "ana@x.com")
    v2 = client.post(f"/web/dividir/{tok2}/voucher", headers=CARO, json={
        "partes": t2["partes"], "medio": "yape", "operacion": "OP-NUNCA", "imagen": _png_distinto(33)}).json()
    assert v2["ok"] and v2["tardio"]
    from datetime import datetime, timezone
    cd.repo().pagos[v2["pago_id"]]["vence_en"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    from web import cobro_directo_web as cdw
    assert cdw.vencer() == 1
    pend = dv.devoluciones_pendientes("dueno@x.com")
    assert len(pend) == 1 and pend[0]["nota"] == "sin_revisar" and pend[0]["pagador_email"] == "caro@x.com"
    assert dv.resolver_devolucion(pend[0]["id"], "dueno@x.com", "no_recibido")["ok"]
    # Y uno rechazado no deja nada por devolver.
    tok3 = _token(_dividir(n=2, horas=("20:00",)))
    t3 = _tomar(tok3, BETO)
    dv.cancelar(div["div"].por_token(tok3), "ana@x.com")
    v3 = client.post(f"/web/dividir/{tok3}/voucher", headers=BETO, json={
        "partes": t3["partes"], "medio": "yape", "operacion": "OP-RECH", "imagen": _png_distinto(44)}).json()
    assert client.post(f"/club/pagos/vouchers/{v3['pago_id']}/rechazar", headers=DUENO, json={"motivo": "no_llego"}).json()["ok"]
    assert not dv.devoluciones_pendientes("dueno@x.com")


def test_webhook_tardio_de_un_cargo_ya_devuelto_no_paga_la_parte(div, monkeypatch):
    _medios()
    _culqi_club()
    tok = _token(_dividir(n=2, horas=("18:00",)))
    d = div["div"].por_token(tok)
    t = _tomar(tok, BETO)
    real_cargo = culqi.crear_cargo

    def cargo_lento(**kw):   # la toma se suelta mientras Culqi cobra
        out = real_cargo(**kw)
        dv.barrer(dv._ahora() + timedelta(minutes=16))
        return out
    monkeypatch.setattr(culqi, "crear_cargo", cargo_lento)
    p = client.post(f"/web/dividir/{tok}/pagar", headers=BETO, json={"partes": t["partes"], "token": "a", "medio": "yape"}).json()
    assert p["ok"] is False and div["reembolsos"][-1]["charge_id"] == "chr_1"
    assert dv.repo().cargo_devuelto("chr_1")
    monkeypatch.setattr(culqi, "crear_cargo", real_cargo)
    assert _tomar(tok, BETO)["partes"] == t["partes"]
    out = dv.conciliar_cargo(_info_cargo(d, t["partes"], 3000), "chr_1", SK, "dueno@x.com")
    assert out["ignorado"] == "reembolsado"
    assert div["div"].partes(d["id"])[1]["estado"] == "cobrando"
    # Su pago real sí entra y NO se devuelve.
    _pagar_culqi(tok, BETO)
    parte = div["div"].partes(d["id"])[1]
    assert parte["estado"] == "pagada" and parte["cobro_id"] == "chr_2#1"
    assert [x["charge_id"] for x in div["reembolsos"]] == ["chr_1"]


def test_cierre_cortado_a_mitad_se_retoma_y_un_error_no_frena_el_barrido(div, monkeypatch):
    _medios()
    _culqi_club()
    r = _dividir(n=3)
    tok = _token(r)
    d = div["div"].por_token(tok)
    _pagar_culqi(tok, BETO)
    _pagar_culqi(tok, CARO)
    otra = div["div"].por_token(_token(_dividir(n=2, horas=("21:00",))))
    real = culqi.reembolsar
    n = {"i": 0}

    def boom(**kw):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("se cortó la conexión")
        return real(**kw)
    monkeypatch.setattr(culqi, "reembolsar", boom)
    despues = max(d["vence_en"], otra["vence_en"]) + timedelta(seconds=5)
    monkeypatch.setattr(dv, "_ahora", lambda: despues)
    out = dv.barrer(despues)
    assert out["errores"] == 1
    assert div["div"].por_id(d["id"])["estado"] == "vencida" and div["div"].por_id(otra["id"])["estado"] == "vencida"
    assert "pagada" in {p["estado"] for p in div["div"].partes(d["id"])}
    # El minuto siguiente el barrido retoma lo que quedó y devuelve cada cargo UNA vez.
    out = dv.barrer(despues + timedelta(minutes=1))
    assert out["reanudadas"] == 1
    partes = {p["n"]: p["estado"] for p in div["div"].partes(d["id"])}
    assert partes[1] == partes[2] == "reembolsada"
    assert sorted(x["charge_id"] for x in div["reembolsos"]) == ["chr_1", "chr_2"]
    assert dv.barrer(despues + timedelta(minutes=2))["reanudadas"] == 0
    assert len(div["reembolsos"]) == 2


def test_devolucion_proporcional_nunca_supera_lo_pagado():
    assert dv.repartir_devolucion([334, 333, 333], 999) == [333, 333, 333]
    assert dv.repartir_devolucion([3334, 3333, 3333], 10000) == [3334, 3333, 3333]
    assert dv.repartir_devolucion([3334, 3333, 3333], 5000) == [1667, 1667, 1666]
    assert dv.repartir_devolucion([100, 200], 0) == [0, 0] and dv.repartir_devolucion([100, 200], 999) == [100, 200]
    import random
    rnd = random.Random(7)
    for _ in range(3000):
        montos = [rnd.randint(300, 9000) for _ in range(rnd.randint(2, 12))]
        dev = rnd.randint(0, sum(montos))
        q = dv.repartir_devolucion(montos, dev)
        assert sum(q) == dev and all(0 <= a <= m for a, m in zip(q, montos))


def test_lo_que_falta_en_un_cargo_se_devuelve_en_una_sola_llamada(div):
    _medios()
    _culqi_club()
    # Vence: Beto con voucher sin revisar; el organizador cubrió 3 partes con UN cargo.
    tok = _token(_dividir(n=4, horas=("18:00", "19:00")))     # S/ 120 entre 4
    d = div["div"].por_token(tok)
    _pagar_voucher(tok, BETO, "OP-B", 51)
    _pagar_culqi(tok, ANA, falta=True)
    despues = d["vence_en"] + timedelta(seconds=5)
    dv.barrer(despues)
    assert div["reembolsos"] == [{"charge_id": "chr_1", "monto_centimos": 9000, "motivo": "solicitud_comprador", "llave": SK}]
    partes = {p["n"]: p for p in div["div"].partes(d["id"])}
    assert all(partes[i]["estado"] == "reembolsada" and partes[i]["devolver_centimos"] == 3000 for i in (0, 2, 3))
    assert partes[1]["estado"] == "devolver" and partes[1]["nota"] == "sin_revisar"
    # Cancelación de una reserva confirmada: un reembolso por cargo, con la suma de sus partes.
    r = _dividir(n=3, horas=("20:00",))                       # S/ 60 entre 3
    tok2 = _token(r)
    _pagar_culqi(tok2, BETO)
    _pagar_culqi(tok2, ANA, falta=True)
    assert div["div"].por_token(tok2)["estado"] == "confirmada"
    filas = datos.reservas_de(r["ids"])
    out = web._cancelar_reserva(filas, datos.cancha("c_lima"), "ana@x.com")
    assert out["ok"] and out["reembolso"] == "reembolsado", out
    assert sorted((x["charge_id"], x["monto_centimos"]) for x in div["reembolsos"][1:]) == [("chr_2", 2000), ("chr_3", 4000)]


# ── Postgres real (Docker local) ─────────────────────────────────────────────

def _esquema(pg):
    raiz = os.path.join(os.path.dirname(__file__), "..", "migraciones")
    with pg.conexion() as conn, conn.cursor() as cur:
        for f in ("0001_control_migraciones.sql", "0006_dividir_pago.sql", "0007_dividir_pago_devoluciones.sql"):
            cur.execute(open(os.path.join(raiz, f), encoding="utf-8").read())
        cur.execute("delete from cl_division_pago where id like 'div_it%%'")


def _crear_pg(r, did, n=3, vence_h=2):
    ahora = dv._ahora()
    montos = dv.calcular_partes(9000, n)
    d = {"id": did, "token": "tk_" + did, "reserva_ref": "ref_" + did, "reserva_ids": ["web_1"], "cancha_id": "c1",
         "dueno": "club@x.com", "organizador_email": "ana@x.com", "organizador_nombre": "Ana", "moneda": "PEN",
         "total_centimos": 9000, "partes": n, "parte_centimos": montos[1], "estado": "abierta", "motivo": "",
         "vence_en": ahora + timedelta(hours=vence_h), "aviso_en": None, "creado_en": ahora, "cerrado_en": None}
    ps = [{"id": f"{did}_{i}", "division_id": did, "n": i, "monto_centimos": m} for i, m in enumerate(montos)]
    assert r.crear(d, ps) == ""
    return d


def test_repo_pg_concurrencia_y_unicos(pg_local):
    _esquema(pg_local)
    r = dv.RepoPG()
    assert r.disponible()
    d = _crear_pg(r, "div_it1", n=2)
    assert r.crear({**d, "id": "div_it1b", "token": "tk_otro"}, []) == "ya_existe"   # una viva por reserva
    assert r.por_token("tk_div_it1")["reserva_ids"] == ["web_1"]
    # Dos amigos por la ÚLTIMA parte libre a la vez: solo uno la toma.
    res = []
    hs = [threading.Thread(target=lambda e=e: res.append(r.tomar("div_it1", e, e, False, False, dv._ahora())))
          for e in ("beto@x.com", "caro@x.com", "dani@x.com")]
    [h.start() for h in hs]
    [h.join() for h in hs]
    assert sorted(x[0] for x in res) == ["", "sin_partes", "sin_partes"]
    quien, [parte] = next((x[1][0]["pagador_email"], x[1]) for x in res if not x[0])
    assert r.tomar("div_it1", quien, quien, False, False, dv._ahora())[1][0]["id"] == parte["id"]
    org_err, [p0] = r.tomar("div_it1", "ana@x.com", "Ana", True, False, dv._ahora())
    # Las dos partes se pagan a la vez: exactamente UNA ve la división completa.
    out = []
    hs = [threading.Thread(target=lambda: out.append(r.pagar("div_it1", [parte["id"]], quien, {parte["id"]: "chr_a#1"}, "yape", ("cobrando",)))),
          threading.Thread(target=lambda: out.append(r.pagar("div_it1", [p0["id"]], "ana@x.com", {p0["id"]: "chr_b#0"}, "yape", ("cobrando",))))]
    [h.start() for h in hs]
    [h.join() for h in hs]
    assert sorted(out) == ["completa", "ok"] and r.por_id("div_it1")["estado"] == "completa"
    assert r.pagar("div_it1", [p0["id"]], "ana@x.com", {p0["id"]: "chr_b#0"}, "yape", ("cobrando",)) == "completa"   # idempotente
    # Un mismo cobro no paga dos partes (índice único).
    d2 = _crear_pg(r, "div_it2")
    _e, [q] = r.tomar("div_it2", "beto@x.com", "B", False, False, dv._ahora())
    assert r.pagar("div_it2", [q["id"]], "beto@x.com", {q["id"]: "chr_a#1"}, "yape", ("cobrando",)) == "no_tomada"
    # Vencida: no se toma ni se paga.
    assert r.transicion("div_it2", ("abierta",), "vencida", "vencida")
    assert r.pagar("div_it2", [q["id"]], "beto@x.com", {q["id"]: "chr_z#1"}, "yape", ("cobrando",)) == "cerrada"
    assert r.tomar("div_it2", "caro@x.com", "C", False, False, dv._ahora())[0] == "cerrada"
    assert r.set_parte(q["id"], ("cobrando",), {"estado": "devolver", "devolver_centimos": 3000, "nota": "vencida"})
    assert [p["id"] for p in r.devoluciones_de("club@x.com")] == [q["id"]]
    assert {x["id"] for x in r.de_email("beto@x.com")} == {"div_it1", "div_it2"}
    # Voucher: a revisión y de vuelta a libre si la división sigue abierta.
    d3 = _crear_pg(r, "div_it3")
    _e, [v] = r.tomar("div_it3", "beto@x.com", "B", False, False, dv._ahora())
    assert r.a_revision("div_it3", [v["id"]], "beto@x.com", "pgm_x", "voucher_yape")
    assert [p["id"] for p in r.liberar_revision("pgm_x")] == [v["id"]]
    assert r.partes("div_it3")[1]["estado"] == "libre"
    assert d and d2 and d3
    with pg_local.conexion() as conn, conn.cursor() as cur:
        cur.execute("delete from cl_division_pago where id like 'div_it%%'")


def test_repo_pg_retomar_cargos_devueltos_tardios_y_reanudar(pg_local):
    _esquema(pg_local)
    r = dv.RepoPG()
    assert r.disponible()
    ahora = dv._ahora()
    _crear_pg(r, "div_it4", n=3)
    # Retomar una parte concreta que quedó libre (y solo una por amigo).
    assert r.retomar("div_it4", ["div_it4_1"], "beto@x.com", "Beto", False, ahora)
    assert not r.retomar("div_it4", ["div_it4_2"], "beto@x.com", "Beto", False, ahora)    # ya tiene una viva
    assert not r.retomar("div_it4", ["div_it4_1"], "caro@x.com", "Caro", False, ahora)    # ya no está libre
    assert not r.retomar("div_it4", ["div_it4_0"], "caro@x.com", "Caro", False, ahora)    # la 0 es del organizador
    assert r.retomar("div_it4", ["div_it4_0", "div_it4_2"], "ana@x.com", "Ana", True, ahora)
    ps = {p["n"]: p for p in r.partes("div_it4")}
    assert ps[1]["pagador_email"] == "beto@x.com" and not ps[1]["por_organizador"]
    assert ps[2]["por_organizador"] and not ps[0]["por_organizador"]
    # Registro de cargos devueltos: idempotente.
    assert r.cargo_devuelto("chr_it_x") is None
    assert r.marcar_cargo_devuelto("chr_it_x", "div_it4", 3000, "ref_1", "vencida")
    assert r.marcar_cargo_devuelto("chr_it_x", "div_it4", 9999, "ref_2", "otra")
    assert r.cargo_devuelto("chr_it_x")["refund_id"] == "ref_1"
    # Comprobante tardío → Devoluciones del club.
    r.crear_tardio({"id": "dvt_it1", "division_id": "div_it4", "n": 1, "pagador_email": "dani@x.com",
                    "pagador_nombre": "Dani", "monto_centimos": 3000, "medio": "voucher_yape",
                    "pago_manual_id": "pgm_it_t", "estado": "en_revision", "nota": "division_cerrada"})
    assert r.tardio_por_pm("pgm_it_t")["id"] == "dvt_it1" and r.tardio_por_pm("") is None
    assert not [x for x in r.devoluciones_de("club@x.com") if x.get("tardio")]
    assert r.set_tardio("dvt_it1", ("en_revision",), {"estado": "devolver", "nota": "aprobado_tarde"})
    assert not r.set_tardio("dvt_it1", ("en_revision",), {"estado": "rechazado"})
    dev = [x for x in r.devoluciones_de("club@x.com") if x.get("tardio")]
    assert len(dev) == 1 and dev[0]["devolver_centimos"] == 3000 and dev[0]["division"]["id"] == "div_it4"
    # Cerrada con una parte pagada sin devolver → la retoma el barrido; la de una
    # reserva cancelada solo si tiene monto asignado.
    assert r.pagar("div_it4", ["div_it4_1"], "beto@x.com", {"div_it4_1": "chr_it_b#1"}, "yape", ("cobrando",)) == "ok"
    assert r.transicion("div_it4", ("abierta",), "vencida", "vencida")
    futuro = ahora + timedelta(hours=3)
    assert "div_it4" in {d["id"] for d in r.cerradas_pendientes(futuro)}
    assert "div_it4" not in {d["id"] for d in r.cerradas_pendientes(ahora - timedelta(hours=1))}
    _crear_pg(r, "div_it5", n=2)
    _e, [q] = r.tomar("div_it5", "beto@x.com", "B", False, False, dv._ahora())
    assert r.pagar("div_it5", [q["id"]], "beto@x.com", {q["id"]: "chr_it_c#1"}, "yape", ("cobrando",)) == "ok"
    assert r.transicion("div_it5", ("abierta",), "cancelada", "reserva_cancelada")
    assert "div_it5" not in {d["id"] for d in r.cerradas_pendientes(futuro)}
    assert r.set_parte(q["id"], ("pagada",), {"devolver_centimos": 1500})
    assert "div_it5" in {d["id"] for d in r.cerradas_pendientes(futuro)}
    with pg_local.conexion() as conn, conn.cursor() as cur:
        cur.execute("delete from cl_division_pago where id like 'div_it%%'")
        cur.execute("delete from cl_division_cargos_devueltos where charge_id like 'chr_it%%'")
