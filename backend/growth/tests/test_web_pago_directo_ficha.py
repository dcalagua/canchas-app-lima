"""Noche WEB (W0 + W1 del lado jugador): la ficha web cobra con el Culqi DEL
CLUB o con comprobante, muestra las reglas y la política del club, y el
jugador ve el estado de su pago en Mis reservas y en el comprobante. Además:
JSON incrustado sin XSS, clave de sesión sin constante y tope diario sin
contar canceladas."""

import json
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402
from web import sesion, ui  # noqa: E402
from tests.test_cobro_directo import DUENO, JUGADOR, PK, SK, _asegurar, _medios_yape, _png, directo  # noqa: E402,F401
from tests.test_web_reservas import _entrar_como, _manana, client, db  # noqa: E402,F401


def _cfg(html: str) -> dict:
    ini = html.index("window.__cancha=") + len("window.__cancha=")
    return json.loads(html[ini:html.index(";var CORREO_SOPORTE", ini)])


# ── W0.1 / W0.4: Culqi del club ──────────────────────────────────────────────

def test_ficha_usa_la_llave_publica_del_club_sin_cargo_ni_puntos(directo):
    client.put("/club/pagos/culqi", headers=DUENO, json={"public_key": PK, "secret_key": SK})
    html = client.get("/reservar/c_lima").text
    cfg = _cfg(html)
    # El token se crea con la llave DEL CLUB: el servidor lo cobra con SU llave secreta.
    assert cfg["pk"] == PK and cfg["pk"] != config.CULQI_PUBLIC_KEY
    assert cfg["directo"]["culqi"] is True and cfg["cargo"] is False
    assert "Pagas directo al club" in html and "checkout.culqi.com" in html


def test_ficha_sin_culqi_del_club_solo_ofrece_comprobante(directo):
    _medios_yape()
    html = client.get("/reservar/c_lima").text
    cfg = _cfg(html)
    assert cfg["pk"] == "" and cfg["pasarela"] == "directo"
    assert cfg["directo"]["medios"][0]["tipo"] == "yape" and cfg["directo"]["culqi"] is False
    assert "data-medio='voucher'" in html and "Pagar con comprobante" in html
    # No se carga Culqi (no hay cómo cobrar con tarjeta).
    assert "checkout.culqi.com" not in html


def test_pasarela_de_la_plataforma_no_cobra_reservas_de_un_club_directo(directo):
    _medios_yape()
    a = _asegurar()
    r = client.post("/web/pago/reserva", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"]}).json()
    assert r["ok"] is False and r["error"] == "usa_directo"


# ── W1.1 / W1.2: comprobante en revisión visible ─────────────────────────────

def test_voucher_en_revision_no_se_suelta_y_se_ve_en_el_comprobante(directo):
    _medios_yape()
    a = _asegurar()
    v = client.post("/web/voucher", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "medio": "yape",
                                                           "operacion": "OP-7788", "imagen": _png()}).json()
    assert v["ok"], v
    # El navegador ya no puede soltar el horario (beforeunload): espera al club.
    assert client.post("/web/liberar", json={"ids": a["ids"], "firma": a["firma"]}).json()["error"] == "pago_en_revision"
    assert a["ids"][0] in directo["db"].reservas
    ref = a["grupo"] or a["ids"][0]
    html = client.get(f"/reserva/{ref}?enviado=1").text
    assert "Pago en revisión del club" in html and "Recibimos tu comprobante" in html
    assert "¡Reserva confirmada!" not in html


def test_mis_reservas_muestra_en_revision_y_los_rechazados(directo, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    _medios_yape()
    a = _asegurar()
    client.post("/web/voucher", headers=JUGADOR, json={"ids": a["ids"], "firma": a["firma"], "medio": "yape",
                                                       "operacion": "111", "imagen": _png()})
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, "ana@x.com", "Ana Pérez")
    mr = cli.get("/mis-reservas").text
    assert "Pago en revisión del club" in mr
    # El club lo rechaza: la reserva se suelta, pero el jugador ve qué pasó.
    pid = client.get("/club/pagos/vouchers", headers=DUENO).json()["pagos"][0]["id"]
    assert client.post(f"/club/pagos/vouchers/{pid}/rechazar", headers=DUENO, json={"motivo": "monto"}).json()["ok"]
    mr = cli.get("/mis-reservas").text
    assert "Pagos que el club no confirmó" in mr and "El monto no coincide" in mr
    ref = a["grupo"] or a["ids"][0]
    caido = cli.get(f"/reserva/{ref}").text
    assert "El club no confirmó tu pago" in caido and "111" in caido


# ── W1.3 / W1.4: reglas y política del club ─────────────────────────────────

def test_politica_del_club_y_limites_de_turnos_en_la_ficha(db):
    db.canchas["c_lima"]["reglas_reserva"] = {
        "cancelacion_horas": 24, "min_turnos": 2, "max_turnos": 3, "max_reservas_dia_jugador": 1,
        "recargo_luz": {"desde": "18:00", "monto": 10},
        "franjas": [{"nombre": "Prime", "dias": ["lun", "mar", "mie", "jue", "vie"], "desde": "18:00", "hasta": "22:00",
                     "precio_hora": 150}],
        "cierres": [{"fecha": _manana(), "motivo": "Feriado"}],
    }
    html = client.get("/reservar/c_lima").text
    cfg = _cfg(html)
    assert cfg["maxSlots"] == 3 and cfg["minSlots"] == 2
    assert "Política del club" in html and "24 h de anticipación" in html and "Prime" in html
    assert "Entre 2 y 3 turnos seguidos" in html and "iluminación" in html and "Feriado" in html
    assert "más de 6 horas" not in html
    d = client.get(f"/web/disponibilidad/c_lima?fecha={_manana()}").json()
    assert d["cerrado"] and d["slots"] == []
    # Los errores de reglas tienen mensaje propio en el navegador.
    assert "ERR_REGLAS" in html and "min_turnos:" in html


def test_tope_diario_no_cuenta_lo_cancelado(db):
    db.canchas["c_lima"]["reglas_reserva"] = {"max_reservas_dia_jugador": 1}
    db.reservas["r_cancelada"] = {"id": "r_cancelada", "cancha_id": "c_lima", "fecha": _manana(), "hora_inicio": "08:00",
                                  "hora_fin": "09:00", "estado": "cancelada", "pagado": True, "usuario": "ana@x.com",
                                  "grupo_reserva_id": "", "precio": 60, "extras": []}
    j = client.post("/web/asegurar", json={"cancha_id": "c_lima", "nombre": "Ana Pérez", "email": "ana@x.com",
                                          "celular": "987654321", "horas": [{"fecha": _manana(), "hora": "10:00"}]}).json()
    assert j["ok"], j


# ── W0.5: JSON incrustado sin XSS ────────────────────────────────────────────

def test_json_ld_y_config_no_pueden_cerrar_el_script(db):
    db.canchas["c_lima"]["club"] = "Club </script><script>alert(1)</script>"
    html = client.get("/reservar/c_lima").text
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script\\u003e" in html
    assert ui.json_js({"x": "<&>"}) == '{"x": "\\u003c\\u0026\\u003e"}'


# ── W0.6: la cookie de sesión nunca se firma con una constante ──────────────

def test_sesion_sin_secretos_no_usa_constante_y_rota_sin_cerrar_sesiones(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.delenv("WEB_SESION_SECRETO", raising=False)
    import base64
    import hashlib
    import hmac
    cuerpo = base64.urlsafe_b64encode(json.dumps({"email": "x@y.com", "exp": 9999999999}).encode()).decode().rstrip("=")
    falsa = cuerpo + "." + hmac.new(b"pichangol-web", cuerpo.encode(), hashlib.sha256).hexdigest()[:40]
    assert sesion.leer(falsa) is None
    # Con la clave de siempre se firma; al agregar WEB_SESION_SECRETO la cookie vieja sigue valiendo.
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    vieja = sesion.emitir({"email": "ana@x.com"})
    monkeypatch.setenv("WEB_SESION_SECRETO", "nuevo-secreto-largo")
    assert sesion.leer(vieja)["email"] == "ana@x.com"
    nueva = sesion.emitir({"email": "ana@x.com"})
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "otra")
    assert sesion.leer(nueva)["email"] == "ana@x.com"


def test_turnos_son_botones_accesibles(db):
    from tests.conftest import con_assets
    html = con_assets(client, client.get("/reservar/c_lima").text)
    assert '<button type="button" class="slot' in html and "aria-pressed" in html and "button.slot{" in html
