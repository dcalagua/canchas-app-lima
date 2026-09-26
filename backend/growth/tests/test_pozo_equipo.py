"""POZO DEL EQUIPO ("la vaquita", decisión del director 26-sep-2026): la cuota
de inscripción por equipo se reparte entre el plantel; cada jugador pone su
parte al unirse; el equipo queda inscrito cuando el pozo cubre la cuota; la
comisión se cobra UNA vez sobre la cuota del equipo; si queda fuera, cada
jugador recupera su parte."""
import os

import pytest
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import pozos  # noqa: E402

client = TestClient(app, headers={"X-Admin-Token": "adm_test"})


@pytest.fixture(autouse=True)
def _token_admin(monkeypatch):
    # La torre marca liquidaciones pagadas: token por test (otros tests lo
    # cambian a nivel de módulo y contaminaban la suite completa).
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm_test")


def _limpio():
    stores.pozos_equipo = {}
    stores.pagos = []
    stores.saldos = {}


def _recargar(email, soles):
    stores.acreditar(email, int(round(soles * 100)))


def _aporte(email, monto=None, **kw):
    body = {"email": email, "campeonato_id": "camp_1", "equipo_id": "eq_1", "cuota_equipo_soles": 100,
            "cupo": 10, "moneda": "S/", "organizador": "org@x.com", "campeonato_nombre": "Copa", "equipo_nombre": "Kinder 01"}
    body.update(kw)
    if monto is not None:
        body["monto_soles"] = monto
        return client.post("/pagos/torneo/equipo/completar", json=body).json()
    return client.post("/pagos/torneo/equipo/aportar", json=body).json()


def test_cuota_por_jugador_redondea_a_50_centimos():
    assert pozos.cuota_jugador_centimos(10000, 10) == 1000     # S/ 100 / 10 = S/ 10
    assert pozos.cuota_jugador_centimos(10000, 7) == 1450      # 14.29 → 14.50
    assert pozos.cuota_jugador_centimos(10000, 3) == 3350      # 33.33 → 33.50
    assert pozos.cuota_jugador_centimos(10000, 0) == 10000     # sin cupo: la cuota entera
    assert pozos.cuota_jugador_centimos(0, 10) == 0


def test_cada_jugador_pone_su_parte_y_el_ultimo_solo_lo_que_falta():
    _limpio()
    # Cuota S/ 100 entre 7 (S/ 14.50 c/u): 6 aportan 87.00; el 7.º paga 13.00.
    for i in range(7):
        _recargar(f"j{i}@x.com", 20)
    for i in range(6):
        r = _aporte(f"j{i}@x.com", cupo=7)
        assert r["ok"] and r["aporte_centimos"] == 1450 and not r["pozo"]["completo"], r
    assert stores.saldo_centimos("j0@x.com") == 550
    assert stores.saldo_centimos("org@x.com") == 0            # retenido: nada al organizador aún
    r = _aporte("j6@x.com", cupo=7)
    assert r["ok"] and r["aporte_centimos"] == 1300 and r["pozo"]["completo"] and r["pozo"]["liquidado"]
    # Comisión UNA vez sobre los S/ 100 (5 % = S/ 5) → neto 95 POR RECIBIR para el
    # organizador (misma cola que una reserva online), NO a su saldo (decisión
    # del director, 26-sep-2026: "PCG le debe transferir como a los dueños").
    assert r["pozo"]["comision_centimos"] == 500 and r["pozo"]["neto_centimos"] == 9500
    assert stores.saldo_centimos("org@x.com") == 0
    ingresos = [p for p in stores.pagos if p.tipo == "inscripcion_torneo_ingreso"]
    assert len(ingresos) == 1 and ingresos[0].comision_centimos == 500 and not ingresos[0].liquidado
    assert ingresos[0].culqi_charge_id == "pozo:camp_1|eq_1"
    pend = stores.liquidaciones("org@x.com", solo_pendientes=True)
    assert [q.id for q in pend] == [ingresos[0].id]
    # Torre: aparece en pendientes agrupada por torneo · equipo y se marca pagada.
    j = client.get("/pagos/liquidaciones/pendientes", headers={"X-Admin-Token": "adm_test"}).json()
    fila = next(x for x in j["pendientes"] if x["reserva_id"] == "pozo:camp_1|eq_1")
    assert fila["neto_soles"] == 95.0 and fila["comision_soles"] == 5.0 and fila["concepto"].startswith("🏆 ")
    assert client.get("/pagos/por-recibir/org@x.com").json()["por_recibir_soles"] == 95.0
    # Idempotente: un 2.º toque del mismo jugador no cobra; un 8.º jugador (suplente) ya no paga.
    antes = stores.saldo_centimos("j0@x.com")
    r = _aporte("j0@x.com", cupo=7)
    assert r["ok"] and r["aporte_centimos"] == 0 and stores.saldo_centimos("j0@x.com") == antes
    _recargar("j7@x.com", 20)
    r = _aporte("j7@x.com", cupo=7)
    assert r["ok"] and r["aporte_centimos"] == 0 and r.get("ya_completo") and stores.saldo_centimos("j7@x.com") == 2000
    # Historial del jugador: su parte sale como egreso; el organizador ve el ingreso neto.
    movs = client.get("/pagos/movimientos/j0@x.com").json()["movimientos"]
    assert any(m["tipo"] == "aporte_equipo" and m["monto_soles"] == -14.5 for m in movs)
    movs = client.get("/pagos/movimientos/org@x.com").json()["movimientos"]
    assert any(m["tipo"] == "inscripcion_torneo_ingreso" and m["neto_soles"] == 95.0 and m["liquidado"] is False for m in movs)
    r = client.post("/pagos/liquidaciones/pozo:camp_1%7Ceq_1/pagar", json={"metodo": "yape", "referencia": "op-1"},
                    headers={"X-Admin-Token": "adm_test"})
    assert r.status_code == 200 and r.json()["liquidado"], r.text
    assert client.get("/pagos/por-recibir/org@x.com").json()["por_recibir_soles"] == 0
    assert pozos.liquidacion_pagada(stores.pozos_equipo["camp_1|eq_1"])


def test_falta_saldo_y_completar_lo_que_falta():
    _limpio()
    r = _aporte("pobre@x.com")
    assert r["ok"] is False and r["falta_saldo"] is True and r["requerido_soles"] == 10.0
    _recargar("capi@x.com", 100)
    _recargar("j1@x.com", 10)
    assert _aporte("capi@x.com")["aporte_centimos"] == 1000
    assert _aporte("j1@x.com")["aporte_centimos"] == 1000
    st = client.get("/pagos/torneo/equipo/camp_1/eq_1").json()["pozo"]
    assert st["pozo_centimos"] == 2000 and st["faltante_centimos"] == 8000 and len(st["aportes"]) == 2
    # El capitán completa los S/ 80 que faltan → inscrito y liquidado.
    r = _aporte("capi@x.com", monto=999)   # tope: lo que falta
    assert r["ok"] and r["aporte_centimos"] == 8000 and r["pozo"]["completo"]
    assert stores.saldo_centimos("capi@x.com") == 1000
    assert stores.saldo_centimos("org@x.com") == 0  # por recibir, no saldo
    assert client.get("/pagos/por-recibir/org@x.com").json()["por_recibir_soles"] == 95.0
    lista = client.get("/pagos/torneo/pozos/camp_1").json()["pozos"]
    assert len(lista) == 1 and lista[0]["equipo_id"] == "eq_1" and lista[0]["liquidado"]


def test_devolver_antes_de_completar_y_nunca_despues():
    _limpio()
    _recargar("a@x.com", 10); _recargar("b@x.com", 10)
    _aporte("a@x.com"); _aporte("b@x.com")
    assert stores.saldo_centimos("a@x.com") == 0
    # Solo el organizador puede devolver.
    r = client.post("/pagos/torneo/equipo/devolver", json={"campeonato_id": "camp_1", "equipo_id": "eq_1", "solicitante": "a@x.com"}).json()
    assert r["ok"] is False and r["error"] == "solo_organizador"
    r = client.post("/pagos/torneo/equipo/devolver", json={"campeonato_id": "camp_1", "equipo_id": "eq_1", "solicitante": "org@x.com"}).json()
    assert r["ok"] and r["devueltos"] == 2 and r["pozo"]["devuelto"] and r["pozo"]["pozo_centimos"] == 0
    assert stores.saldo_centimos("a@x.com") == 1000 and stores.saldo_centimos("b@x.com") == 1000
    movs = client.get("/pagos/movimientos/a@x.com").json()["movimientos"]
    assert any(m["tipo"] == "aporte_equipo_devolucion" and m["monto_soles"] == 10.0 for m in movs)
    # Reinscrito: el pozo vuelve a cero y acepta aportes nuevos.
    assert _aporte("a@x.com")["pozo"]["pozo_centimos"] == 1000
    # Pozo completo pero Pichangol AÚN no le pagó al organizador: se anula la
    # liquidación pendiente y cada jugador recupera su parte.
    _recargar("capi@x.com", 100)
    _aporte("capi@x.com", monto=90)
    assert client.get("/pagos/por-recibir/org@x.com").json()["por_recibir_soles"] == 95.0
    r = client.post("/pagos/torneo/equipo/devolver", json={"campeonato_id": "camp_1", "equipo_id": "eq_1", "solicitante": "org@x.com"}).json()
    assert r["ok"] and r["devueltos"] == 2 and stores.saldo_centimos("capi@x.com") == 10000 and stores.saldo_centimos("a@x.com") == 1000
    assert client.get("/pagos/por-recibir/org@x.com").json()["por_recibir_soles"] == 0
    # Reinscrito, completo y esta vez la torre YA le pagó → ya no hay devolución automática.
    _aporte("capi@x.com", monto=100)
    pid = stores.pozos_equipo["camp_1|eq_1"]["liquidacion_pago_id"]
    pg = next(q for q in stores.pagos if q.id == pid)
    client.post("/pagos/liquidaciones/" + pg.culqi_charge_id.replace("|", "%7C") + "/pagar", json={"metodo": "yape"}, headers={"X-Admin-Token": "adm_test"})
    r = client.post("/pagos/torneo/equipo/devolver", json={"campeonato_id": "camp_1", "equipo_id": "eq_1", "solicitante": "org@x.com"}).json()
    assert r["ok"] is False and r["error"] == "ya_liquidado"


def test_torneo_gratis_no_cobra_y_el_pozo_sobrevive_al_snapshot():
    _limpio()
    r = _aporte("a@x.com", cuota_equipo_soles=0)
    assert r["ok"] and r.get("gratis") and r["aporte_centimos"] == 0
    _recargar("a@x.com", 10); _aporte("a@x.com")
    st = stores.to_state()
    assert "camp_1|eq_1" in st["pozos_equipo"]
    stores.pozos_equipo = {}
    stores.load_state(st)
    assert pozos.de_equipo("camp_1", "eq_1")["pozo_centimos"] == 1000
    # Moneda de la sede: la comisión mínima es la de esa moneda ($ 0.50).
    _limpio()
    _recargar("u@x.com", 10)
    r = _aporte("u@x.com", cuota_equipo_soles=5, cupo=1, moneda="$", equipo_id="eq_usd")
    assert r["pozo"]["liquidado"] and r["pozo"]["comision_centimos"] == 50 and r["pozo"]["moneda"] == "USD"


def test_recordatorio_diario_de_liquidaciones_atrasadas(monkeypatch):
    """Anti-olvido (director, 26-sep-2026): una vez al día, desde las 09:00 de
    Lima, se avisa al operador (WhatsApp + logs) lo que lleva ≥ N días sin
    pagarse; sin atrasadas no molesta; no repite el mismo día."""
    from datetime import datetime, timedelta, timezone
    from pagos import router as R
    _limpio()
    R._ultimo_recordatorio_dia = ""
    avisos = []
    import propiedad.reclamos as recl
    monkeypatch.setattr(recl, "_notificar_admin", lambda t: avisos.append(t))
    for i in range(10):
        _recargar(f"j{i}@x.com", 10); _aporte(f"j{i}@x.com")
    pg = next(q for q in stores.pagos if q.tipo == "inscripcion_torneo_ingreso")
    hoy = datetime.now(timezone.utc)
    # Recién creada: pendiente pero no atrasada → sin aviso.
    assert R.recordar_liquidaciones_pendientes(hoy.replace(hour=15))["enviado"] is False
    R._ultimo_recordatorio_dia = ""
    pg.creado_en = hoy - timedelta(days=R.LIQUIDACION_AVISO_DIAS + 1)
    j = client.get("/pagos/liquidaciones/pendientes", headers={"X-Admin-Token": "adm_test"}).json()
    assert j["atrasadas"] == 1 and j["mas_antigua_dias"] >= R.LIQUIDACION_AVISO_DIAS
    # Antes de las 09:00 Lima (14:00 UTC) no manda; después sí, una vez.
    assert R.recordar_liquidaciones_pendientes(hoy.replace(hour=12))["enviado"] is False
    r = R.recordar_liquidaciones_pendientes(hoy.replace(hour=15))
    assert r["enviado"] and r["atrasadas"] == 1 and r["total_soles"] == 95.0 and len(avisos) == 1
    assert "sin pagar" in avisos[0] and "S/ 95.00" in avisos[0]
    assert R.recordar_liquidaciones_pendientes(hoy.replace(hour=16))["enviado"] is False and len(avisos) == 1
