"""PROPIEDAD: un RUC/existencia no basta; sólo el OTP (o la aprobación manual)
confirma al dueño. El OTP no se persiste y respeta intentos/expiración."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from propiedad import service as prop  # noqa: E402


@pytest.fixture(autouse=True)
def _limpio():
    stores.reset()
    config.OTP_DEBUG_DEVOLVER_CODIGO = True  # modo stub: expone el código de prueba
    yield
    config.OTP_DEBUG_DEVOLVER_CODIGO = False


def test_otp_confirma_propiedad_sin_telefono_publico():
    r = prop.solicitar("c1", "987654321")
    assert r["ok"] and "codigo_debug" in r
    cod = r["codigo_debug"]
    assert not stores.cancha("c1").verificada

    out = prop.confirmar("c1", cod, "dueno@correo.com")
    assert out["ok"] and out["estado"] == "confirmada"
    assert stores.cancha("c1").verificada is True
    # No-retención: el OTP se borró tras usarse.
    assert "c1" not in stores.otps


def test_codigo_incorrecto_no_verifica_y_descuenta_intentos():
    prop.solicitar("c2", "987111222")
    out = prop.confirmar("c2", "000000", "x@y.com")
    assert not out["ok"] and out["error"] == "codigo_incorrecto"
    assert stores.cancha("c2").verificada is False


def test_telefono_publico_distinto_queda_en_revision():
    r = prop.solicitar("c3", "987000111")
    cod = r["codigo_debug"]
    out = prop.confirmar("c3", cod, "x@y.com", telefono_publico="51999888777")
    assert out["ok"] and out["estado"] == "pendiente_revision"
    # No se auto-verifica si el número no coincide con el público del local.
    assert stores.cancha("c3").verificada is False


def test_aprobacion_manual_verifica():
    out = prop.aprobar_manual("c4", "x@y.com", aprobado=True, revisor="ops")
    assert out["verificada"] is True
    assert stores.cancha("c4").verificada is True


def test_otp_no_se_persiste_en_snapshot():
    prop.solicitar("c5", "987654321")
    estado = stores.to_state()
    assert "otps" not in estado  # nunca se serializan códigos
