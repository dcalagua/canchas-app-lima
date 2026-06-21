"""Priorización por zona: la cancha más pedida sale primero en la cola del
verificador, y el ranking refleja la demanda."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import stores  # noqa: E402
from solicitudes import service as solic  # noqa: E402
from verificacion_fisica import service as vf  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    yield


def _pedir(usuario, nombre, lat, lng):
    return solic.crear(usuario, nombre, f"{nombre} s/n", distrito="ate",
                       lat=lat, lng=lng)["solicitud"]["id"]


def test_cancha_mas_pedida_sale_primero():
    # Cancha A: pedida 3 veces; Cancha B: 1 vez (misma zona lima_este).
    ids_a = [_pedir(f"u{i}", "Cancha A", -12.020, -76.900) for i in range(3)]
    id_b = _pedir("ux", "Cancha B", -12.050, -76.800)

    # Ranking de demanda: A (3) antes que B (1).
    rank = solic.ranking("lima_este")
    assert rank[0]["nombre_cancha"] == "Cancha A"
    assert rank[0]["solicitudes"] == 3
    assert rank[1]["solicitudes"] == 1

    # Se registran y van a verificación (IA no concluye → agendada).
    solic.marcar_registrada(ids_a[0], "cA")
    solic.marcar_registrada(id_b, "cB")
    vf.evaluar("cA", "Cancha A sn", None, -12.020, -76.900, "lima_este", None,
               None, "sin_documentos")
    vf.evaluar("cB", "Cancha B sn", None, -12.050, -76.800, "lima_este", None,
               None, "sin_documentos")

    visitas = vf.visitas(zona="lima_este")
    assert visitas[0]["cancha_id"] == "cA"
    assert visitas[0]["demanda"] == 3
    assert visitas[1]["cancha_id"] == "cB"
    assert visitas[1]["demanda"] == 1
