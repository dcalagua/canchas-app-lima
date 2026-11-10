"""La API genérica de config NO filtra secretos (fuga hallada el 26-oct-2026:
`GET /config/incentivos` devolvía el 2FA de la torre a cualquiera)."""

import json

from fastapi.testclient import TestClient

import config
import config_publica
from db.store import CONFIG_DEFAULT, stores
from main import app
from propiedad import admin_auth

client = TestClient(app)
ADMIN = {"X-Admin-Token": "tok-secreto"}


def _secretos(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok-secreto")
    monkeypatch.setitem(stores.config, "admin_2fa_ops@x.pe", "b:RUpERTJT")
    monkeypatch.setitem(stores.config, "admin_2fa_rec_ops@x.pe", json.dumps(["abc"]))
    monkeypatch.setitem(stores.config, "liq_bcp_cuenta", "191-1234567-0-12")
    monkeypatch.setitem(stores.config, "marca_logo_b64", "iVBORw0KGgo=")
    monkeypatch.setitem(stores.config, "meta_page_token", "EAAG...")


def test_anonimo_solo_ve_lista_blanca(monkeypatch):
    _secretos(monkeypatch)
    j = client.get("/config/incentivos").json()
    texto = json.dumps(j)
    for fuga in ("admin_2fa", "RUpERTJT", "liq_bcp", "191-1234567", "marca_logo_b64", "EAAG"):
        assert fuga not in texto
    assert set(j) <= set(CONFIG_DEFAULT)
    assert j["puntos_traer_cancha"] == stores.config["puntos_traer_cancha"]


def test_admin_ve_lo_editable_pero_nunca_secretos(monkeypatch):
    _secretos(monkeypatch)
    monkeypatch.setitem(stores.config, "clave_nueva_del_operador", "7")
    j = client.get("/config/incentivos", headers=ADMIN).json()
    assert j["clave_nueva_del_operador"] == "7"
    assert not any(config_publica.es_sensible(k) for k in j)
    assert "admin_2fa_ops@x.pe" not in j and "liq_bcp_cuenta" not in j


def test_put_generico_no_pisa_secretos(monkeypatch):
    _secretos(monkeypatch)
    for clave in ("admin_2fa_ops@x.pe", "liq_bcp_cuenta", "algo_token"):
        r = client.put(f"/config/incentivos/{clave}", json={"valor": "x"}, headers=ADMIN)
        assert r.status_code == 403
    assert stores.config["admin_2fa_ops@x.pe"] == "b:RUpERTJT"


def test_secreto_2fa_sin_meta_key_ya_no_es_base64(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok-secreto")
    monkeypatch.setattr(config, "META_TOKEN_KEY", "")
    enc = admin_auth._cifrar("JBSWY3DPEHPK3PXP")
    assert enc.startswith("a:") and "JBSWY3DP" not in enc
    assert admin_auth._descifrar(enc) == "JBSWY3DPEHPK3PXP"


def test_secreto_legado_base64_se_recifra_al_leer(monkeypatch):
    import base64
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok-secreto")
    monkeypatch.setattr(config, "META_TOKEN_KEY", "")
    k = "admin_2fa_viejo@x.pe"
    monkeypatch.setitem(stores.config, k, "b:" + base64.urlsafe_b64encode(b"JBSWY3DPEHPK3PXP").decode())
    assert admin_auth.secreto_de("viejo@x.pe") == "JBSWY3DPEHPK3PXP"
    assert stores.config[k].startswith("a:")
    assert admin_auth.secreto_de("viejo@x.pe") == "JBSWY3DPEHPK3PXP"


def test_recuperacion_64_bits_con_sal_y_compat_legado(monkeypatch):
    usuario = "rec@x.pe"
    codigos = admin_auth.generar_recuperacion(usuario)
    assert all(len(c.replace("-", "")) == 16 for c in codigos)
    guardados = json.loads(stores.config[f"admin_2fa_rec_{usuario}"])
    assert all(g.startswith("s2$") for g in guardados)
    assert len({g.split("$")[1] for g in guardados}) == len(guardados)  # sal distinta
    assert admin_auth.usar_recuperacion(usuario, codigos[0].lower())
    assert not admin_auth.usar_recuperacion(usuario, codigos[0])  # un solo uso
    # Un código del formato viejo (ya entregado) sigue valiendo una vez.
    stores.config[f"admin_2fa_rec_{usuario}"] = json.dumps([admin_auth._hash_rec_legado("ABCD-1234")])
    assert admin_auth.usar_recuperacion(usuario, "abcd1234")
    stores.config.pop(f"admin_2fa_rec_{usuario}", None)
