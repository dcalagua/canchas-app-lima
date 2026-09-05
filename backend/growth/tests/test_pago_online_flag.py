"""INTERRUPTOR DE PAGO ONLINE: el APK no debe ofrecer cobrar si no se puede.

Sin llaves LIVE de Culqi, un jugador que toca "Pagar ahora" se topa con un
cobro imposible. La regla es que el ambiente lo declare y el APK esconda esa
opción — nunca mostrar una pantalla de pago que no se puede completar, y menos
simular un cobro que no ocurrió.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import main  # noqa: E402
from propiedad import panel  # noqa: E402

cli = TestClient(main.app)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    monkeypatch.delenv("PAGO_ONLINE_ACTIVO", raising=False)
    yield


def test_sin_llaves_no_hay_pago_online(monkeypatch):
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "")
    assert panel.pago_online_disponible() is False


def test_llave_de_PRUEBA_no_habilita_el_cobro(monkeypatch):
    """El caso peligroso: sk_test cobra "bien" en la consola de Culqi pero
    rechaza tarjetas reales. Para un jugador real es un pago roto."""
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_abc123")
    assert panel.pago_online_disponible() is False


def test_llave_live_habilita_el_cobro(monkeypatch):
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_live_abc123")
    assert panel.pago_online_disponible() is True


def test_se_puede_forzar_por_env_para_probar_en_qas(monkeypatch):
    """En QAS se quiere probar el flujo completo con llaves de prueba."""
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_abc123")
    monkeypatch.setenv("PAGO_ONLINE_ACTIVO", "1")
    assert panel.pago_online_disponible() is True
    # Y al revés: apagarlo aunque haya llaves reales (corte de emergencia).
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_live_abc123")
    monkeypatch.setenv("PAGO_ONLINE_ACTIVO", "0")
    assert panel.pago_online_disponible() is False


def test_el_apk_lo_recibe_en_la_config_publica(monkeypatch):
    """El endpoint que el APK ya consultaba ahora trae también el interruptor,
    así que no hace falta una llamada nueva ni un APK nuevo para encenderlo."""
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_live_abc123")
    r = cli.get("/config/canal")
    assert r.status_code == 200
    j = r.json()
    assert j["pago_online"] is True
    assert "canal" in j  # sigue sirviendo lo de antes

    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "")
    assert cli.get("/config/canal").json()["pago_online"] is False
