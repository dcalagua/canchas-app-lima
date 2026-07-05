"""Convocatorias ("pichangas" programadas): cupos + lista de espera + los 3
modos de asignación configurables (orden_llegada | sorteo | equidad), cancelación
con auto-promoción, ranking de recurrencia y persistencia por snapshot."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from convocatorias import service  # noqa: E402
from db.store import stores  # noqa: E402

CLUB = "el_bosque"


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    yield


def _crear(cupos=14, modo=None, titulo="Fulbito Máster"):
    out = service.crear(CLUB, titulo, "futbol", cupos, modo_asignacion=modo,
                         categoria="master", creado_por="admin@bosque.pe")
    return out["convocatoria"]["id"]


def _anotar(conv_id, n, prefijo="socio"):
    for k in range(n):
        service.inscribir(conv_id, f"{prefijo}{k}@x.com", f"{prefijo} {k}")


# --- orden_llegada ---------------------------------------------------------
def test_orden_llegada_confirma_hasta_cupos_y_resto_a_espera():
    cid = _crear(cupos=14, modo="orden_llegada")
    _anotar(cid, 16)
    d = service.detalle(cid)
    assert len(d["confirmados"]) == 14
    assert len(d["lista_espera"]) == 2
    assert d["cupos_libres"] == 0
    assert d["total_inscritos"] == 16
    # El primero que se anotó está confirmado; el último, en espera.
    assert d["confirmados"][0]["socio_id"] == "socio0@x.com"
    assert d["lista_espera"][-1]["socio_id"] == "socio15@x.com"


def test_estado_socio_en_vivo_orden_llegada():
    cid = _crear(cupos=1, modo="orden_llegada")
    service.inscribir(cid, "a@x.com", "A")
    service.inscribir(cid, "b@x.com", "B")
    assert service.estado_socio(cid, "a@x.com")["estado_efectivo"] == "confirmado"
    esb = service.estado_socio(cid, "b@x.com")
    assert esb["estado_efectivo"] == "lista_espera" and esb["posicion"] == 1


def test_no_duplica_inscripcion():
    cid = _crear(cupos=5)
    service.inscribir(cid, "a@x.com", "A")
    out = service.inscribir(cid, "a@x.com", "A")
    assert out.get("ya_inscrito") is True
    assert service.detalle(cid)["total_inscritos"] == 1


# --- cancelación / promoción ----------------------------------------------
def test_cancelar_promueve_de_lista_de_espera():
    cid = _crear(cupos=1, modo="orden_llegada")
    service.inscribir(cid, "a@x.com", "A")
    service.inscribir(cid, "b@x.com", "B")
    service.cerrar(cid)
    assert service.estado_socio(cid, "a@x.com")["estado_efectivo"] == "confirmado"
    # Al cancelar el confirmado, sube el de la espera.
    service.cancelar(cid, "a@x.com")
    assert service.estado_socio(cid, "b@x.com")["estado_efectivo"] == "confirmado"
    d = service.detalle(cid)
    assert len(d["confirmados"]) == 1 and d["confirmados"][0]["socio_id"] == "b@x.com"


# --- sorteo ----------------------------------------------------------------
def test_sorteo_no_confirma_en_vivo_y_resuelve_al_cerrar():
    cid = _crear(cupos=2, modo="sorteo")
    _anotar(cid, 5)
    # En vivo, nadie confirmado: todos "en la bolsa".
    d = service.detalle(cid)
    assert d["confirmados"] == []
    assert service.estado_socio(cid, "socio0@x.com")["estado_efectivo"] == "en_bolsa"
    out = service.cerrar(cid, semilla="fija")
    assert out["modo"] == "sorteo"
    assert len(out["confirmados"]) == 2
    assert len(out["lista_espera"]) == 3


def test_sorteo_es_reproducible_con_la_misma_semilla():
    def ganadores():
        stores.reset()
        cid = _crear(cupos=2, modo="sorteo")
        _anotar(cid, 6)
        out = service.cerrar(cid, semilla="misma")
        return [i["socio_id"] for i in out["confirmados"]]
    assert ganadores() == ganadores()


# --- equidad ---------------------------------------------------------------
def test_equidad_prioriza_a_quien_quedo_fuera_antes():
    # Fecha 1 (orden_llegada, 1 cupo): A entra, B queda fuera.
    c1 = _crear(cupos=1, modo="orden_llegada")
    service.inscribir(c1, "a@x.com", "A")
    service.inscribir(c1, "b@x.com", "B")
    service.cerrar(c1)
    service.marcar_asistencia(c1, [{"socio_id": "a@x.com", "asistio": True}])
    assert service.estado_socio(c1, "b@x.com")["estado_efectivo"] == "lista_espera"

    # Fecha 2 (equidad, 1 cupo): aunque A se anote primero, B tiene prioridad
    # por haber quedado fuera (y A ya jugó la fecha anterior).
    c2 = _crear(cupos=1, modo="equidad")
    service.inscribir(c2, "a@x.com", "A")
    service.inscribir(c2, "b@x.com", "B")
    out = service.cerrar(c2)
    assert out["confirmados"][0]["socio_id"] == "b@x.com"


def test_equidad_penaliza_no_show():
    # Fecha 1: A y B confirmados (2 cupos); B no se presenta.
    c1 = _crear(cupos=2, modo="orden_llegada")
    service.inscribir(c1, "a@x.com", "A")
    service.inscribir(c1, "b@x.com", "B")
    service.cerrar(c1)
    service.marcar_asistencia(c1, [
        {"socio_id": "a@x.com", "asistio": True},
        {"socio_id": "b@x.com", "asistio": False}])
    # Fecha 2 (equidad, 1 cupo): C (nuevo, 0) debe ganarle a B (no-show penaliza).
    c2 = _crear(cupos=1, modo="equidad")
    service.inscribir(c2, "b@x.com", "B")
    service.inscribir(c2, "c@x.com", "C")
    out = service.cerrar(c2)
    assert out["confirmados"][0]["socio_id"] == "c@x.com"


# --- modo configurable por el admin ---------------------------------------
def test_default_global_configurable_y_override_por_convocatoria():
    assert service.config_modo()["global"] == "orden_llegada"
    # Cambio el default global a equidad.
    assert service.set_modo_global("equidad")["ok"] is True
    c_default = _crear(cupos=1, modo=None)
    assert service.detalle(c_default)["modo_efectivo"] == "equidad"
    # Override por convocatoria manda sobre el global.
    c_override = _crear(cupos=1, modo="orden_llegada")
    assert service.detalle(c_override)["modo_efectivo"] == "orden_llegada"


def test_modo_global_invalido_se_rechaza():
    assert service.set_modo_global("xxx")["ok"] is False
    assert service.config_modo()["global"] == "orden_llegada"


# --- ranking de recurrencia (trazabilidad) --------------------------------
def test_ranking_recurrencia():
    c1 = _crear(cupos=2, modo="orden_llegada")
    service.inscribir(c1, "a@x.com", "Ana")
    service.inscribir(c1, "b@x.com", "Beto")
    service.cerrar(c1)
    service.marcar_asistencia(c1, [
        {"socio_id": "a@x.com", "asistio": True},
        {"socio_id": "b@x.com", "asistio": True}])
    c2 = _crear(cupos=1, modo="orden_llegada")
    service.inscribir(c2, "a@x.com", "Ana")
    service.inscribir(c2, "b@x.com", "Beto")
    service.cerrar(c2)
    service.marcar_asistencia(c2, [{"socio_id": "a@x.com", "asistio": True}])

    r = service.ranking_socios(CLUB)
    top = r[0]
    assert top["socio_id"] == "a@x.com"
    assert top["inscripciones"] == 2 and top["jugo"] == 2
    beto = next(x for x in r if x["socio_id"] == "b@x.com")
    assert beto["lista_espera"] == 1  # quedó fuera en la fecha 2


# --- persistencia ----------------------------------------------------------
def test_persistencia_snapshot():
    cid = _crear(cupos=1, modo="sorteo")
    service.inscribir(cid, "a@x.com", "A")
    service.cerrar(cid, semilla="s")
    estado = stores.to_state()
    stores.load_state(estado)
    d = service.detalle(cid)
    assert d["convocatoria"]["estado"] == "cerrada"
    assert d["convocatoria"]["semilla"] == "s"
    assert len(d["confirmados"]) == 1
