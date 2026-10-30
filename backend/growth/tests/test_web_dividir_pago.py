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
    r = dv.conciliar_cargo({"metadata": {"division_id": d["id"], "partes": ",".join(t["partes"]), "email": "beto@x.com"},
                            "monto_centimos": 6000}, "chr_1", SK)
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


# ── Postgres real (Docker local) ─────────────────────────────────────────────

def _esquema(pg):
    raiz = os.path.join(os.path.dirname(__file__), "..", "migraciones")
    with pg.conexion() as conn, conn.cursor() as cur:
        for f in ("0001_control_migraciones.sql", "0006_dividir_pago.sql"):
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
