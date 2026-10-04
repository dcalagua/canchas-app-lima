"""SEGURIDAD anti-apropiación de canchas (bug crítico del piloto).

Reclamar un lugar que YA tiene un reclamo APROBADO de otra persona NUNCA debe
devolverle "activada"/es_mio al nuevo reclamante: el estado se resuelve por
LUGAR y, antes del fix, un impostor que reclamaba un local activo recibía la
aprobación ajena y su app activaba la copia al instante, sin pasar por la torre.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from propiedad import reclamos  # noqa: E402

LAT, LNG = -12.0432, -76.9540


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", "")  # no envía nada
    yield


def _reclamar(cancha_id, correo):
    return reclamos.crear_reclamo(cancha_id, correo, "Sabor Golazo",
                                  telefono_contacto="987654321",
                                  lat=LAT, lng=LNG)


def test_impostor_no_recibe_la_aprobacion_ajena():
    # El dueño real reclama y el admin aprueba (piloto: activa al instante).
    r = _reclamar("c_dueno", "real@x.com")
    reclamos.aprobar_directo(r["reclamo_id"], "admin")
    est = reclamos.estado("c_dueno", "real@x.com")
    assert est["estado"] == "activada" and est["es_mio"] is True

    # Un impostor reclama el MISMO lugar/id (la cancha descubierta comparte id):
    # el backend lo rechaza y NO crea nada (por eso tampoco aparece en la torre).
    r2 = _reclamar("c_dueno", "otro@x.com")
    assert r2["ok"] is False and r2["error"] == "ya_reclamada"

    # Al consultar el estado identificándose, el impostor NUNCA recibe
    # "activada"/verificada (protege incluso a APKs viejos): se le responde
    # "reclamada_por_otro", sin panel y sin es_mio.
    est2 = reclamos.estado("c_dueno", "otro@x.com")
    assert est2["existe"] is True
    assert est2["estado"] == "reclamada_por_otro"
    assert est2["verificada"] is False
    assert est2["panel_desbloqueado"] is False
    assert est2["es_mio"] is False


def test_estado_prefiere_el_reclamo_propio_del_solicitante():
    # B reclama primero y el admin lo RECHAZA; luego A reclama el mismo lugar
    # y queda APROBADO. B, identificándose, debe ver SU rechazo — no la
    # aprobación de A (antes del fix veía "activada" del lugar).
    rb = _reclamar("c_b", "b@x.com")
    reclamos.triage(rb["reclamo_id"], False, "admin")
    ra = _reclamar("c_a", "a@x.com")
    assert ra["ok"] is True
    reclamos.aprobar_directo(ra["reclamo_id"], "admin")

    est_b = reclamos.estado("c_b", "b@x.com")
    assert est_b["estado"] == "rechazada"
    assert est_b["es_mio"] is True
    assert est_b["verificada"] is False

    # A sigue viendo su aprobación normal.
    est_a = reclamos.estado("c_a", "a@x.com")
    assert est_a["estado"] == "activada" and est_a["es_mio"] is True

    # Un tercero SIN reclamo (sin identificarse) ve el estado representativo
    # del lugar (activada), como siempre — solo lectura, sin es_mio.
    est_pub = reclamos.estado("c_a")
    assert est_pub["estado"] == "activada"
    assert est_pub["es_mio"] is False
