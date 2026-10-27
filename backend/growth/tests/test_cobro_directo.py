"""COBRO DIRECTO AL CLUB (plan nocturno A4 + A5 + A6): cuenta Culqi propia
del club (llave secreta cifrada), pagos manuales con voucher anti-fraude y
comisión de la plataforma desde el saldo del dueño o como deuda."""

import base64
import io
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from pagos import cobro_directo as cd  # noqa: E402
from pagos import culqi  # noqa: E402
from web import cobro_directo_web as cdw  # noqa: E402
from web import datos  # noqa: E402
from tests.test_web_reservas import LIMA, _manana, client, db  # noqa: E402,F401

DUENO = {"X-User-Token": "tok-dueno"}
JUGADOR = {"X-User-Token": "tok-ana"}
PK, SK = "pk_test_abcdefgh1234", "sk_test_zyxwvuts9876"


@pytest.fixture
def directo(db, monkeypatch):
    from cryptography.fernet import Fernet
    from pagos import router as pr
    repo = cd.RepoMemoria()
    cd.usar_repo(repo)
    monkeypatch.setattr(config, "PAGOS_ENC_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(pr, "_email_de_token", lambda t: {"tok-dueno": "dueno@x.com", "tok-ana": "ana@x.com",
                                                         "tok-otro": "otro@x.com"}.get(t))
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: pushes.append(a))
    monkeypatch.setattr(culqi, "verificar_llave", lambda llave: {"ok": True, "valida": True})

    def marcar(ids):
        for i in ids:
            db.reservas[i]["medio_pago"] = "voucher"
        return True
    monkeypatch.setattr(datos, "marcar_hold_voucher", marcar)
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [c for c in db.canchas.values() if c["dueno"] == e])
    monkeypatch.setitem(stores.saldos, "dueno@x.com", 0)
    monkeypatch.setattr(stores, "pagos", [])
    yield {"repo": repo, "pushes": pushes, "db": db}
    cd.usar_repo(cd.RepoPG())


def _png() -> str:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (120, 40, 200)).save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _asegurar(hora="10:00", headers=JUGADOR):
    return client.post("/web/asegurar", headers=headers, json={
        "cancha_id": "c_lima", "nombre": "Ana Pérez", "email": "ana@x.com", "celular": "987654321",
        "horas": [{"fecha": _manana(), "hora": hora}]}).json()


# ── A4: cuenta Culqi del club ────────────────────────────────────────────────

def test_llaves_validadas_cifradas_y_nunca_devueltas(directo, monkeypatch):
    r = client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": "pk_live_x", "secret_key": SK})
    assert r.status_code == 400
    r = client.put("/club/pagos/culqi", headers=DUENO,
                   json={"public_key": PK.replace("test", "live"), "secret_key": SK})
    assert r.json()["detail"] == "llaves_de_distinto_modo"
    monkeypatch.setattr(culqi, "verificar_llave", lambda llave: {"ok": True, "valida": False})
    assert client.put("/club/pagos/culqi", headers=DUENO,
                      json={"public_key": PK, "secret_key": SK}).json()["detail"] == "llave_rechazada_por_culqi"
    monkeypatch.setattr(culqi, "verificar_llave", lambda llave: {"ok": True, "valida": True})
    r = client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK}).json()
    assert r["ok"] and r["secret_key"] == "sk_test_••••9876" and SK not in str(r)
    guardado = directo["repo"].pasarelas["dueno@x.com"]
    assert SK not in str(guardado) and cd.llave_secreta("dueno@x.com") == SK
    cfg = client.get("/club/pagos", headers=DUENO).json()
    assert cfg["culqi"]["configurada"] and SK not in str(cfg)
    # Otro usuario no ve ni toca la cuenta del club.
    assert client.get("/club/pagos", headers={"X-User-Token": "tok-otro"}).json()["culqi"] == {"configurada": False}
    assert client.put("/club/pagos/culqi", headers={"X-User-Token": "tok-otro"},
                      json={"public_key": PK, "secret_key": SK}).status_code == 403
    assert client.get("/club/pagos").status_code == 401


def test_sin_clave_de_cifrado_no_se_guarda_nada(directo, monkeypatch):
    monkeypatch.setattr(config, "PAGOS_ENC_KEY", "")
    r = client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})
    assert r.status_code == 503 and r.json()["detail"] == "cifrado_no_configurado"
    assert directo["repo"].pasarelas == {}


def test_cobro_con_la_llave_del_club_y_comision_como_deuda(directo, monkeypatch):
    client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})
    a = _asegurar()
    assert a["ok"] and a["directo"]["culqi_public_key"] == PK
    assert a["total_centimos"] == 3000 and a["cargo_centimos"] == 0   # 10:00 = hora feliz 50 %
    cargos = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_club"})
    p = client.post("/web/pagar", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "token": "tkn_1"}).json()
    assert p["ok"], p
    assert cargos[0]["llave"] == SK and cargos[0]["monto_centimos"] == 3000
    fila = directo["db"].reservas[a["ids"][0]]
    assert fila["estado"] == "confirmada" and fila["pagado"]
    cobro = next(x for x in stores.pagos if x.tipo == "cobro_directo")
    assert cobro.culqi_charge_id == "chr_club" and cobro.dueno_id == "dueno@x.com"
    # Sin saldo: la comisión (5 %, mínimo S/ 2) queda como DEUDA.
    assert cd.deuda_centimos("dueno@x.com", "PEN") == 200
    # La siguiente recarga la salda sola.
    stores.acreditar("dueno@x.com", 1000)
    assert cd.deuda_centimos("dueno@x.com", "PEN") == 0 and stores.saldo_centimos("dueno@x.com") == 800


def test_comision_sale_del_saldo_si_alcanza(directo, monkeypatch):
    stores.saldos["dueno@x.com"] = 5000
    client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})
    a = _asegurar("18:00")
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": True, "charge_id": "chr_2"})
    assert client.post("/web/pagar", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "token": "t"}).json()["ok"]
    assert stores.saldo_centimos("dueno@x.com") == 5000 - 300   # 5 % de S/ 60
    assert cd.deuda_centimos("dueno@x.com") == 0


def test_club_suspendido_con_deuda_sobre_el_tope(directo, monkeypatch):
    client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})
    monkeypatch.setitem(stores.config, "comision_deuda_tope_PEN", "1")
    stores.registrar_pago(tipo="comision_deuda", monto_centimos=500, moneda="PEN", estado="pendiente",
                          dueno_id="dueno@x.com", culqi_charge_id="deuda:x")
    assert cd.suspendido("dueno@x.com", "PEN")
    assert cd.checkout(LIMA, "PEN") == {"directo": False, "suspendido": True}


# ── A5: voucher ──────────────────────────────────────────────────────────────

def _medios_yape():
    return client.put("/club/pagos/medios", headers=DUENO, json={"medios": [
        {"tipo": "yape", "titular": "Club Raqueta SAC", "numero": "987 654 321"}]})


def test_medios_validados_por_pais(directo):
    r = client.put("/club/pagos/medios", headers=DUENO, json={"medios": [{"tipo": "yape", "titular": "Club", "numero": "123"}]})
    assert r.json()["detail"] == "celular_invalido"
    r = client.put("/club/pagos/medios", headers=DUENO, json={"medios": [{"tipo": "qr", "titular": "Club", "numero": "1"}]})
    assert r.json()["detail"].startswith("medio_no_permitido")   # QR genérico es para EC/BO
    assert _medios_yape().json()["medios"][0]["numero"] == "987654321"


def test_voucher_revision_aprobacion_y_antifraude(directo):
    _medios_yape()
    a = _asegurar()
    assert a["directo"]["medios"][0]["tipo"] == "yape" and a["directo"]["culqi_public_key"] == ""
    # Sin Culqi del club, /web/pagar manda al voucher.
    assert client.post("/web/pagar", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "token": "t"}).json()["error"] == "usa_voucher"
    v = client.post("/web/voucher", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "medio": "yape",
                                                           "operacion": "Op 12-345", "imagen": _png()}).json()
    assert v["ok"], v
    assert directo["db"].reservas[a["ids"][0]]["medio_pago"] == "voucher"
    # El MISMO nº de operación no paga otra reserva del club…
    b = _asegurar("15:00")
    r = client.post("/web/voucher", headers=JUGADOR, json={"ids": b["ids"], "firma": b["firma"], "medio": "yape",
                                                           "operacion": "op12345", "imagen": _png()}).json()
    assert r == {"ok": False, "error": "operacion_repetida"}
    # …ni la MISMA imagen con otro número.
    r = client.post("/web/voucher", headers=JUGADOR, json={"ids": b["ids"], "firma": b["firma"], "medio": "yape",
                                                           "operacion": "999", "imagen": _png()}).json()
    assert r == {"ok": False, "error": "voucher_repetido"}
    bandeja = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"]
    assert len(bandeja) == 1 and bandeja[0]["monto_centimos"] == 3000 and "voucher_img" not in bandeja[0]
    pid = bandeja[0]["id"]
    img = client.get(f"/club/pagos/vouchers/{pid}/imagen", headers=DUENO)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    # Otro usuario no ve ni aprueba el voucher.
    assert client.get(f"/club/pagos/vouchers/{pid}/imagen", headers={"X-User-Token": "tok-otro"}).status_code == 404
    assert client.post(f"/club/pagos/vouchers/{pid}/aprobar", headers={"X-User-Token": "tok-otro"}).status_code == 404
    ok = client.post(f"/club/pagos/vouchers/{pid}/aprobar", headers=DUENO).json()
    assert ok["ok"] and ok["comision"]["deuda_centimos"] == 200
    assert directo["db"].reservas[a["ids"][0]]["estado"] == "confirmada"
    assert client.post(f"/club/pagos/vouchers/{pid}/aprobar", headers=DUENO).json()["error"] == "ya_resuelto"
    assert any("confirmada" in p[1].lower() for p in directo["pushes"])


def test_voucher_de_otro_jugador_no_se_acepta(directo):
    _medios_yape()
    a = _asegurar()
    r = client.post("/web/voucher", headers={"X-User-Token": "tok-otro"}, json={
        "ids": a["ids"], "firma": a["firma"], "medio": "yape", "operacion": "777", "imagen": _png()}).json()
    assert r == {"ok": False, "error": "no_es_tu_reserva"}


def test_voucher_rechazado_libera_el_horario(directo):
    _medios_yape()
    a = _asegurar()
    client.post("/web/voucher", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "medio": "yape",
                                                       "operacion": "555", "imagen": _png()})
    pid = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"][0]["id"]
    assert client.post(f"/club/pagos/vouchers/{pid}/rechazar", headers=DUENO, json={"motivo": "No llegó"}).json()["ok"]
    assert a["ids"][0] not in directo["db"].reservas


def test_voucher_sin_revisar_vence_solo(directo):
    _medios_yape()
    a = _asegurar()
    client.post("/web/voucher", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "medio": "yape",
                                                       "operacion": "444", "imagen": _png()})
    p = next(iter(directo["repo"].pagos.values()))
    p["vence_en"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert cdw.vencer() == 1
    assert p["estado"] == "vencido" and a["ids"][0] not in directo["db"].reservas


# ── webhook del club ─────────────────────────────────────────────────────────

def test_webhook_del_club_confirma_un_cobro_que_quedo_sin_confirmar(directo, monkeypatch):
    client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})
    a = _asegurar()
    ref = a["ids"][0]
    ref_wh = directo["repo"].pasarelas["dueno@x.com"]["webhook_ref"]
    assert client.post("/pagos/culqi/webhook/club/wh_falso", json={}).status_code == 404
    llaves = []
    monkeypatch.setattr(culqi, "obtener_cargo", lambda cid, llave=None: llaves.append(llave) or {
        "ok": True, "monto_centimos": 3000, "metadata": {"canal": "directo", "reserva_ref": ref}})
    r = client.post(f"/pagos/culqi/webhook/club/{ref_wh}", json={"data": {"id": "chr_perdido"}}).json()
    assert r.get("confirmado") and llaves == [SK]
    assert directo["db"].reservas[ref]["estado"] == "confirmada"
    # Repetido: idempotente.
    assert client.post(f"/pagos/culqi/webhook/club/{ref_wh}", json={"data": {"id": "chr_perdido"}}).json()["duplicado"]


def test_checkout_publico_del_club(directo):
    assert client.get("/club/pagos/checkout/c_lima").json() == {"ok": True, "directo": False}
    _medios_yape()
    j = client.get("/club/pagos/checkout/c_lima").json()
    assert j["directo"] and j["medios"][0]["etiqueta"] == "Yape" and j["culqi_public_key"] == ""
    client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})
    j = client.get("/club/pagos/checkout/c_lima").json()
    assert j["culqi_public_key"] == PK and SK not in str(j)
    assert client.get("/club/pagos/checkout/no_existe").status_code == 404
