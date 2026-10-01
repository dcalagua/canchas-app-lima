"""Invita y gana con el bono en el BACKEND (`referidos.py`): canje del APK y
de la web, un canje por cuenta, bono por moneda de la billetera de cada lado,
tope por referidor, idempotencia y migración de los canjes del APK viejo."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import referidos as R  # noqa: E402
from db.store import stores  # noqa: E402

ANA, BETO, CARLA = "ana@gmail.com", "beto@gmail.com", "carla@gmail.com"


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    monkeypatch.setattr(config, "APP_API_KEY", "", raising=False)
    avisos = []
    import pagos.router as PR
    monkeypatch.setattr(PR, "_aviso_push_usuario", lambda *a, **k: avisos.append(a))
    yield avisos


def _cli():
    import main
    return TestClient(main.app)


def _bonos(email):
    return [p for p in stores.pagos if p.dueno_id == email and p.tipo == "bono_referido"]


def test_canje_acredita_a_ambos_en_la_billetera_y_una_sola_vez(_limpio):
    cod = R.registrar_codigo(ANA)  # Ana abrió "Invita y gana"
    cli = _cli()
    r = cli.post("/referidos/canjear", json={"email": BETO, "codigo": cod.lower()}).json()
    assert r["ok"] and r["bono_centimos"] == 1000 and r["moneda"] == "PEN"
    assert stores.saldos[BETO] == 1000 and stores.saldos[ANA] == 1000
    assert len(_bonos(BETO)) == 1 and len(_bonos(ANA)) == 1
    assert any("usó tu código" in a[1] for a in _limpio)
    # Segundo canje de la misma cuenta: rechazado y sin plata nueva.
    otra = R.registrar_codigo(CARLA)
    r2 = cli.post("/referidos/canjear", json={"email": BETO, "codigo": otra}).json()
    assert not r2["ok"] and r2["error"] == "ya_canjeaste"
    assert stores.saldos[BETO] == 1000 and CARLA not in stores.saldos
    # Sale en Mi billetera (movimientos del APK) como bono.
    movs = cli.get(f"/pagos/movimientos/{BETO}").json()["movimientos"]
    assert any(m["tipo"] == "bono_referido" for m in movs)
    # Estado del referidor.
    est = cli.get("/referidos/estado", params={"email": ANA}).json()
    assert est["codigo"] == cod and est["invitados"] == 1 and est["ganado_centimos"] == 1000


def test_codigo_propio_inexistente_o_mal_formado():
    cod_ana = R.codigo_referido(ANA)
    assert R.canjear(ANA, cod_ana)["error"] == "codigo_propio"
    assert R.canjear(BETO, "HOLA")["error"] == "codigo_invalido"
    assert R.canjear(BETO, "PCGZZZZZZ")["error"] == "codigo_invalido"  # no es de nadie
    # Un código de alguien conocido por el backend (tiene saldo) sí se resuelve
    # aunque nunca haya abierto "Invita y gana".
    stores.acreditar(CARLA, 0)
    assert R.canjear(BETO, R.codigo_referido(CARLA))["ok"]
    assert stores.saldos == {CARLA: 1000, BETO: 1000}


def test_bono_en_la_moneda_de_la_billetera_de_cada_lado(monkeypatch):
    monedas = {ANA: "USD", BETO: "BOB"}
    monkeypatch.setattr(R, "_moneda_billetera", lambda e: monedas.get(e, "PEN"))
    cod = R.registrar_codigo(ANA)
    r = R.canjear(BETO, cod)
    assert r["ok"] and r["moneda"] == "BOB" and r["bono_centimos"] == 1500
    assert stores.saldos[BETO] == 1500 and stores.saldos[ANA] == 250
    assert _bonos(ANA)[0].moneda == "USD" and _bonos(BETO)[0].moneda == "BOB"
    # Bono en 0 = apagado para esa moneda (no se crea pago vacío).
    stores.config["referido_bono_soles"] = "0"
    R.registrar_codigo(CARLA)
    assert R.canjear("dani@gmail.com", R.codigo_referido(CARLA))["bono_centimos"] == 0
    assert "dani@gmail.com" not in stores.saldos


def test_tope_por_referidor_el_invitado_igual_recibe():
    stores.config["referido_tope_referidor"] = "2"
    cod = R.registrar_codigo(ANA)
    for i in range(3):
        assert R.canjear(f"amigo{i}@gmail.com", cod)["ok"]
    assert stores.saldos[ANA] == 2000                       # solo 2 le pagan
    assert all(stores.saldos[f"amigo{i}@gmail.com"] == 1000 for i in range(3))
    assert R.estado(ANA)["tope_alcanzado"] is True


def test_migra_los_canjes_que_el_apk_viejo_dejo_sin_bono(monkeypatch):
    cod = R.codigo_referido(ANA)
    filas = [{"invitado": BETO, "codigo": cod}]
    monkeypatch.setattr(R, "_filas_pg", lambda codigo="", invitado="": [
        f for f in filas if (codigo and f["codigo"] == codigo) or (invitado and f["invitado"] == invitado)])
    guardados = []
    monkeypatch.setattr(R, "_guardar_pg", lambda i, c: guardados.append((i, c)))
    est = R.estado(ANA)                      # Ana abre "Invita y gana"
    assert est["importados"] == 1 and est["invitados"] == 1
    assert stores.saldos[ANA] == 1000 and stores.saldos[BETO] == 1000
    assert stores.referidos[BETO]["origen"] == "app_anterior" and guardados == [(BETO, cod)]
    # Idempotente: volver a abrir no paga otra vez, y Beto ya "canjeó".
    assert R.estado(ANA)["importados"] == 0 and R.estado(BETO)["canjeado"] == cod
    assert stores.saldos[ANA] == 1000 and stores.saldos[BETO] == 1000
    assert R.canjear(BETO, R.registrar_codigo(CARLA))["error"] == "ya_canjeaste"


def test_canje_desde_la_web_con_sesion(monkeypatch):
    from web import sesion
    cod = R.registrar_codigo(ANA)
    monkeypatch.setattr(sesion, "de_request", lambda req: {"email": BETO, "nombre": "Beto"})
    r = _cli().post("/web/referidos/canjear", json={"codigo": cod}).json()
    assert r["ok"] and stores.saldos[BETO] == 1000 and stores.referidos[BETO]["origen"] == "web"


def test_snapshot_conserva_los_canjes():
    cod = R.registrar_codigo(ANA)
    R.canjear(BETO, cod)
    estado = stores.to_state()
    stores.reset()
    stores.load_state(estado)
    assert stores.referidos[BETO]["referidor"] == ANA and stores.referidos_codigos[cod] == ANA
