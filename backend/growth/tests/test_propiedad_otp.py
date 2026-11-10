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
    # Desde el 1-oct-2026 el OTP es EVIDENCIA: no activa la cancha por defecto.
    assert out["verificada"] is False
    assert stores.cancha("c1").verificada is False
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


def test_canal_preferido_elige_sms_si_whatsapp_no_disponible(monkeypatch):
    from propiedad import twilio_adapter, whatsapp_adapter

    monkeypatch.setattr(whatsapp_adapter, "disponible", lambda: False)
    monkeypatch.setattr(twilio_adapter, "disponible", lambda: True)
    monkeypatch.setattr(
        twilio_adapter, "enviar_sms", lambda t, c: {"ok": True, "via": "sms"})

    r = prop.solicitar("c6", "987654321")
    assert r["ok"] and r["via"] == "sms"


def test_canal_preferido_whatsapp_gana_cuando_ambos(monkeypatch):
    from propiedad import twilio_adapter, whatsapp_adapter

    monkeypatch.setattr(config, "OTP_CANAL_PREFERIDO", "whatsapp")
    monkeypatch.setattr(whatsapp_adapter, "disponible", lambda: True)
    monkeypatch.setattr(twilio_adapter, "disponible", lambda: True)
    monkeypatch.setattr(
        whatsapp_adapter, "enviar_otp", lambda t, c: {"ok": True, "via": "whatsapp"})

    r = prop.solicitar("c7", "987654321")
    assert r["ok"] and r["via"] == "whatsapp"


def test_canal_twilio_whatsapp_cuando_meta_no_y_es_preferido(monkeypatch):
    from propiedad import twilio_adapter, whatsapp_adapter

    monkeypatch.setattr(config, "OTP_CANAL_PREFERIDO", "twilio_whatsapp")
    monkeypatch.setattr(whatsapp_adapter, "disponible", lambda: False)
    monkeypatch.setattr(twilio_adapter, "disponible", lambda: True)  # SMS también
    monkeypatch.setattr(twilio_adapter, "disponible_whatsapp", lambda: True)
    monkeypatch.setattr(
        twilio_adapter, "enviar_whatsapp",
        lambda t, c: {"ok": True, "via": "twilio_whatsapp"})

    r = prop.solicitar("c8", "987654321")
    assert r["ok"] and r["via"] == "twilio_whatsapp"


def test_otp_del_app_no_activa_y_queda_como_evidencia_en_el_reclamo(monkeypatch):
    """APK (`POST /propiedad/otp/confirmar`): igual que la web, el código del
    WhatsApp del local NO activa la cancha; se suma al reclamo abierto y avisa
    al admin. Responde `pendiente_revision` para que un APK viejo no se
    auto-verifique en local."""
    from fastapi.testclient import TestClient
    import main
    from propiedad import reclamos

    avisos = []
    monkeypatch.setattr(reclamos, "_notificar_admin", lambda t: avisos.append(t))
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    r = reclamos.crear_reclamo(
        cancha_id="c9", nombre_local="Club Prueba", solicitante_id="dueno@correo.com",
        telefono_contacto="987654321")
    cli = TestClient(main.app)
    cod = prop.solicitar("c9", "51987654321")["codigo_debug"]
    out = cli.post("/propiedad/otp/confirmar", json={
        "cancha_id": "c9", "codigo": cod, "solicitante_id": "dueno@correo.com"}).json()
    assert out["ok"] and out["estado"] == "pendiente_revision"
    assert out["verificada"] is False and out["codigo_confirmado"] is True
    assert stores.cancha("c9").verificada is False
    rec = [x for x in stores.reclamos if x.cancha_id == "c9"][-1]
    assert rec.estado in reclamos._RECLAMO_ABIERTO
    assert out["en_reclamo"] is True
    assert "confirmado por código (app)" in (rec.nota_reclamante or "")
    assert avisos and "APROBAR" in avisos[-1]
    # Código incorrecto sigue respondiendo el error tal cual.
    prop.solicitar("c9", "51987654321")
    mal = cli.post("/propiedad/otp/confirmar", json={
        "cancha_id": "c9", "codigo": "000000", "solicitante_id": "dueno@correo.com"}).json()
    assert not mal["ok"] and mal["error"] == "codigo_incorrecto"
