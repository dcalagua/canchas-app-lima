"""C1: identidad verificada en endpoints legados que recibían el correo del
cliente (boleadores). Token válido manda; token inválido o de otro → rechazo;
sin token, legado solo fuera del modo estricto."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def _tokens(monkeypatch):
    from pagos import router as pr
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(pr, "_email_de_token", lambda t: {"tok-ana": "ana@x.com"}.get(t))


def test_token_de_otro_no_lee_solicitudes_ajenas(monkeypatch):
    _tokens(monkeypatch)
    r = client.get("/boleadores/solicitudes?email=victima@x.com", headers={"X-User-Token": "tok-ana"})
    assert r.status_code == 403
    assert client.get("/boleadores/solicitudes?email=ana@x.com", headers={"X-User-Token": "falso"}).status_code == 401
    assert client.get("/boleadores/solicitudes", headers={"X-User-Token": "tok-ana"}).status_code == 200


def test_modo_estricto_exige_token(monkeypatch):
    _tokens(monkeypatch)
    monkeypatch.setenv("AUTH_USUARIO_ESTRICTO", "1")
    assert client.get("/boleadores/solicitudes?email=ana@x.com").status_code == 401
    r = client.post("/boleadores/solicitudes/x/aceptar", json={"email": "ana@x.com"})
    assert r.status_code == 401
    monkeypatch.setenv("AUTH_USUARIO_ESTRICTO", "0")
    assert client.get("/boleadores/solicitudes?email=ana@x.com").status_code == 200  # legado, transición


def test_es_mio_del_reclamo_con_identidad_verificada(monkeypatch):
    _tokens(monkeypatch)
    # Pedir el estado declarando a OTRO solicitante con mi token → 403.
    r = client.get("/propiedad/reclamo/c_x?solicitante=victima@x.com", headers={"X-User-Token": "tok-ana"})
    assert r.status_code == 403
    assert client.get("/propiedad/reclamo/c_x", headers={"X-User-Token": "tok-ana"}).status_code == 200
