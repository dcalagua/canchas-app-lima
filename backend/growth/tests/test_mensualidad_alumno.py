"""Suscripción MENSUAL del alumno (pago mes a mes): el cron cobra la mensualidad
a la tarjeta guardada y acredita el neto (menos comisión POS) a la academia."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import stores  # noqa: E402
import pagos.culqi as culqi_mod  # noqa: E402
from pagos.router import procesar_renovaciones_alumnos  # noqa: E402

VENCIDA = "2020-01-01T00:00:00+00:00"  # próximo cobro en el pasado


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    yield


def _sub(alumno="al1", aca="a1", monto=25000, pais="pe", prox=VENCIDA):
    stores.suscripciones_alumno[alumno] = {
        "alumno_id": alumno, "academia_id": aca, "email": "alu@x",
        "card_id": "crd_1", "marca": "visa", "ultimos4": "1111",
        "monto_centimos": monto, "pais": pais, "estado": "activa",
        "concepto": "Mensualidad", "proximo_cobro": prox}


def test_cobra_mensualidad_y_acredita_neto(monkeypatch):
    stores.config["comision_matricula_pct_pe"] = "5"
    monkeypatch.setattr(culqi_mod, "disponible", lambda: True)
    monkeypatch.setattr(culqi_mod, "crear_cargo",
                        lambda **k: {"ok": True, "charge_id": "chg_m1"})
    _sub(monto=25000)  # S/ 250
    r = procesar_renovaciones_alumnos()
    assert r["cobradas"] == 1
    s = stores.suscripciones_alumno["al1"]
    assert s["estado"] == "activa"
    assert s["proximo_cobro"] != VENCIDA
    assert s["cobros_hechos"] == 1  # para la reconciliación de cuotas en la app
    # Se registró como matricula_online con comisión 5% para la academia.
    pagos = [p for p in stores.pagos
             if p.tipo == "matricula_online" and p.dueno_id == "a1"]
    assert len(pagos) == 1
    assert pagos[0].monto_centimos == 25000
    assert pagos[0].comision_centimos == 1250  # 5% de 250


def test_pendiente_si_culqi_declina(monkeypatch):
    monkeypatch.setattr(culqi_mod, "disponible", lambda: True)
    monkeypatch.setattr(culqi_mod, "crear_cargo",
                        lambda **k: {"ok": False, "error": "declinada"})
    _sub()
    r = procesar_renovaciones_alumnos()
    assert r["pendientes"] == 1
    assert stores.suscripciones_alumno["al1"]["estado"] == "pendiente_pago"


def test_no_cobra_si_no_vencio(monkeypatch):
    monkeypatch.setattr(culqi_mod, "disponible", lambda: True)
    _sub(prox="2999-01-01T00:00:00+00:00")
    r = procesar_renovaciones_alumnos()
    assert r["cobradas"] == 0 and r["pendientes"] == 0


def test_cobros_restantes_completa_la_suscripcion(monkeypatch):
    monkeypatch.setattr(culqi_mod, "disponible", lambda: True)
    monkeypatch.setattr(culqi_mod, "crear_cargo",
                        lambda **k: {"ok": True, "charge_id": "chg_x"})
    _sub()
    stores.suscripciones_alumno["al1"]["cobros_restantes"] = 2
    # 1.er cobro automático: quedan 1, sigue activa.
    procesar_renovaciones_alumnos()
    s = stores.suscripciones_alumno["al1"]
    assert s["cobros_restantes"] == 1 and s["estado"] == "activa"
    # Vence de nuevo → 2.º cobro: quedan 0 → completada (deja de cobrar).
    s["proximo_cobro"] = VENCIDA
    procesar_renovaciones_alumnos()
    assert s["cobros_restantes"] == 0 and s["estado"] == "completada"
    # Ya completada: no cobra más.
    s["proximo_cobro"] = VENCIDA
    r = procesar_renovaciones_alumnos()
    assert r["cobradas"] == 0


def test_persistencia_incluye_suscripciones_alumno():
    _sub()
    estado = stores.to_state()
    stores.reset()
    assert not stores.suscripciones_alumno
    stores.load_state(estado)
    assert "al1" in stores.suscripciones_alumno
    assert stores.suscripciones_alumno["al1"]["academia_id"] == "a1"
