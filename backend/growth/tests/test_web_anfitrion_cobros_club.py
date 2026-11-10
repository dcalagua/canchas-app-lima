"""Cobros del club, Pagos por confirmar y Reglas de reserva en la web del
anfitrión (`web/anfitrion_cobros_club.py`): envoltorios con la cookie de
sesión sobre las MISMAS funciones que los endpoints del APK, y el calendario
/ reserva manual / bloqueo / Disponibilidad respetando las reglas del club."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from pagos import cobro_directo as cd
from pagos import culqi
from reservas import reglas as _reglas
from web import datos, sesion
from tests.test_cobro_directo import JUGADOR, PK, SK, _asegurar, directo  # noqa: F401
from tests.test_web_reservas import _manana, db  # noqa: F401

JSON = {"Content-Type": "application/json"}


def _cli(email="dueno@x.com", monkeypatch=None):
    c = TestClient(app, base_url="https://testserver")
    c.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Don Dueño", "foto": ""}))
    return c


@pytest.fixture
def web(directo, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    return directo


def _png_de(n: int) -> str:
    import base64
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (n * 37 % 255, 40, 200)).save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _voucher(hora="10:00"):
    a = _asegurar(hora)
    v = TestClient(app).post("/web/voucher", headers=JUGADOR, json={
        "ids": a["ids"], "firma": a["firma"], "medio": "yape", "operacion": "OP" + hora.replace(":", ""), "imagen": _png_de(int(hora[:2]))}).json()
    assert v["ok"], v
    return a, v["pago_id"]


# ── W1.5 Cobros del club ─────────────────────────────────────────────────────

def test_conectar_culqi_desde_la_web_verifica_la_llave(web, monkeypatch):
    cli = _cli()
    html = cli.get("/anfitrion/cobros-club").text
    assert "Cobros de tu club" in html and "Conectar Culqi" in html and "Pagos manuales" in html
    # Sin JSON → 415; de otro origen → 403; sin sesión → 401.
    assert cli.post("/anfitrion/cobros-club/culqi", content="x", headers={"Content-Type": "text/plain"}).status_code == 415
    assert cli.post("/anfitrion/cobros-club/culqi", json={}, headers={"Origin": "https://malo.com"}).status_code == 403
    assert cli.post("/anfitrion/cobros-club/culqi", json={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert TestClient(app).post("/anfitrion/cobros-club/culqi", json={}).status_code == 401
    # Culqi rechaza la llave → no se guarda nada.
    monkeypatch.setattr(culqi, "verificar_llave", lambda llave: {"ok": True, "valida": False})
    r = cli.post("/anfitrion/cobros-club/culqi", json={"public_key": PK, "secret_key": SK})
    assert r.status_code == 400 and r.json()["error"] == "llave_rechazada_por_culqi" and "Culqi rechazó" in r.json()["mensaje"]
    assert web["repo"].pasarelas == {}
    monkeypatch.setattr(culqi, "verificar_llave", lambda llave: {"ok": True, "valida": True})
    r = cli.post("/anfitrion/cobros-club/culqi", json={"public_key": PK, "secret_key": SK},
                 headers={"Origin": "https://testserver"}).json()
    assert r["ok"] and SK not in str(r)
    html = cli.get("/anfitrion/cobros-club").text
    assert "Culqi conectado" in html and "/pagos/culqi/webhook/club/wh_" in html and SK not in html
    # Desconectar.
    assert cli.post("/anfitrion/cobros-club/culqi/desconectar", json={}).json()["ok"]
    assert web["repo"].pasarelas == {}
    # Una cuenta sin canchas no conecta nada.
    assert _cli("otro@x.com").post("/anfitrion/cobros-club/culqi", json={"public_key": PK, "secret_key": SK}).status_code == 403


def test_medios_manuales_por_pais_desde_la_web(web):
    cli = _cli()
    r = cli.post("/anfitrion/cobros-club/medios", json={"medios": [{"tipo": "yape", "titular": "Club", "numero": "123"}]})
    assert r.status_code == 400 and r.json()["error"] == "celular_invalido"
    r = cli.post("/anfitrion/cobros-club/medios", json={"medios": [{"tipo": "qr", "titular": "Club", "numero": "1"}]})
    assert r.json()["error"].startswith("medio_no_permitido")
    r = cli.post("/anfitrion/cobros-club/medios", json={"medios": [
        {"tipo": "yape", "titular": "Club Raqueta SAC", "numero": "987 654 321"},
        {"tipo": "transferencia", "titular": "Club Raqueta SAC", "banco": "BCP", "cuenta": "19312345678012"}]}).json()
    assert r["ok"] and [m["tipo"] for m in r["medios"]] == ["yape", "transferencia"]
    assert cd.medios_publicos("dueno@x.com")[0]["numero"] == "987654321"
    assert "Comisión" in cli.get("/anfitrion/cobros-club").text


# ── W1.6 Pagos por confirmar ─────────────────────────────────────────────────

def test_aprobar_y_rechazar_voucher_desde_la_web(web):
    cli = _cli()
    web["repo"].reemplazar_medios("dueno@x.com", [{"tipo": "yape", "titular": "Club", "numero": "987654321", "banco": "",
                                                    "cuenta": "", "cci": "", "qr_url": "", "nota": ""}])
    a, pid = _voucher("10:00")
    b, pid2 = _voucher("15:00")
    html = cli.get("/anfitrion/pagos-por-confirmar").text
    assert "Pagos por confirmar" in html and f"/anfitrion/pagos-por-confirmar/{pid}/imagen" in html and "S/ 30.00" in html
    assert "Por revisar <small>(2)</small>" in html and "No llegó el pago" in html
    # Insignias en el menú y banner en Hoy.
    assert "aria-label='2 por revisar'" in cli.get("/anfitrion").text
    assert "2 pagos por confirmar" in cli.get("/anfitrion/mis-canchas").text
    assert cli.get(f"/anfitrion/pagos-por-confirmar/{pid}/imagen").headers["content-type"] == "image/jpeg"
    # Dueño ajeno: 404 en todo.
    otro = _cli("otro@x.com")
    assert otro.get(f"/anfitrion/pagos-por-confirmar/{pid}/imagen").status_code == 404
    assert otro.post(f"/anfitrion/pagos-por-confirmar/{pid}/aprobar", json={}).status_code == 404
    assert otro.post(f"/anfitrion/pagos-por-confirmar/{pid}/rechazar", json={"motivo": "monto"}).status_code == 404
    # Aprobar → reserva confirmada + comisión como deuda (sin saldo).
    r = cli.post(f"/anfitrion/pagos-por-confirmar/{pid}/aprobar", json={}).json()
    assert r["ok"] and r["comision"]["deuda_centimos"] == 200
    assert web["db"].reservas[a["ids"][0]]["estado"] == "confirmada"
    assert cli.post(f"/anfitrion/pagos-por-confirmar/{pid}/aprobar", json={}).json()["error"] == "ya_resuelto"
    # Rechazar exige un motivo del catálogo; se guarda la CLAVE.
    assert cli.post(f"/anfitrion/pagos-por-confirmar/{pid2}/rechazar", json={"motivo": "lo que sea"}).status_code == 400
    assert cli.post(f"/anfitrion/pagos-por-confirmar/{pid2}/rechazar", json={"motivo": "monto"}).json()["ok"]
    assert web["repo"].pagos[pid2]["motivo_rechazo"] == "monto"
    assert b["ids"][0] not in web["db"].reservas
    assert any("monto distinto" in p[2].lower() for p in web["pushes"])
    hist = cli.get("/anfitrion/pagos-por-confirmar?estado=historial").text
    assert "Aprobado" in hist and "Rechazado" in hist and "Monto distinto" in hist
    # Ingresos: la deuda de comisión con signo "−" y la tarjeta de comisión.
    ing = cli.get("/anfitrion/ingresos").text
    assert "Comisiones por pagar" in ing and "−S/ 2.00" in ing


def test_hoy_avisa_cobros_suspendidos(web, monkeypatch):
    monkeypatch.setitem(stores.config, "comision_deuda_tope_PEN", "1")
    stores.registrar_pago(tipo="comision_deuda", monto_centimos=500, moneda="PEN", estado="pendiente",
                          dueno_id="dueno@x.com", culqi_charge_id="deuda:x")
    hoy = _cli().get("/anfitrion/mis-canchas").text
    assert "Tus cobros en línea están pausados" in hoy and "/mi-billetera#recargar" in hoy


# ── W1.7 Reglas de reserva + W0.7 calendario con reglas ──────────────────────

@pytest.fixture
def reglas_db(web, monkeypatch):
    guardadas = {}

    def guardar(ids, dueno, reglas):
        n = 0
        for i in ids:
            c = web["db"].canchas.get(i)
            if c and (c.get("dueno") or "").lower() == dueno:
                c["reglas_reserva"] = reglas
                guardadas[i] = reglas
                n += 1
        return n
    monkeypatch.setattr(datos, "col_reglas_disponible", lambda: True)
    monkeypatch.setattr(datos, "guardar_reglas", guardar)
    return guardadas


def test_guardar_reglas_y_aplicar_a_hermanas(web, reglas_db):
    cli = _cli()
    html = cli.get("/anfitrion/reglas/c_lima").text
    assert "Reglas de Cancha Central" in html and "Aplicar también a" in html and "Nocturna" in html
    assert _cli("otro@x.com").get("/anfitrion/reglas/c_lima").status_code == 404
    r = cli.post("/anfitrion/reglas/guardar", json={"cancha_ids": ["c_lima", "c_noche"],
                                                    "reglas": {"max_turnos": 2, "franjas": [{"nombre": "Hora punta", "dias": ["lun"],
                                                               "desde": "18:00", "hasta": "23:00", "precio_hora": 90}]}}).json()
    assert r["ok"] and r["canchas"] == 2 and set(reglas_db) == {"c_lima", "c_noche"}
    assert reglas_db["c_noche"]["max_turnos"] == 2
    # Una cancha ajena en la lista → no se guarda ninguna.
    r = cli.post("/anfitrion/reglas/guardar", json={"cancha_ids": ["c_lima", "no_es_mia"], "reglas": {}})
    assert r.status_code == 404
    assert _cli("otro@x.com").post("/anfitrion/reglas/guardar", json={"cancha_ids": ["c_lima"], "reglas": {}}).status_code == 404


def _proximo(dia_semana: int) -> str:
    """Próximo día (después de mañana) con ese weekday (0 = lunes)."""
    d = date.fromisoformat(_manana()) + timedelta(days=1)
    while d.weekday() != dia_semana:
        d += timedelta(days=1)
    return d.isoformat()


def test_calendario_y_manual_respetan_dia_cerrado_y_franja(web, reglas_db):
    cli = _cli()
    lunes = _proximo(0)
    martes = (date.fromisoformat(lunes) + timedelta(days=1)).isoformat()
    web["db"].canchas["c_lima"]["reglas_reserva"] = {
        "cierres": [{"fecha": martes, "motivo": "Feriado"}],
        "franjas": [{"nombre": "Hora punta", "dias": ["lun"], "desde": "18:00", "hasta": "23:00", "precio_hora": 90}],
        "recargo_luz": {"desde": "20:00", "monto": 5}}
    cal = cli.get(f"/anfitrion/calendario?cancha=c_lima&desde={lunes}").text
    assert "Cerrado · Feriado" in cal
    assert f"data-b='{martes}'" not in cal  # el día cerrado no ofrece turnos
    assert f"data-b='{lunes}' data-f='{lunes}' data-h='19:00' data-fin='20:00' data-p='90'" in cal  # franja
    assert f"data-b='{lunes}' data-f='{lunes}' data-h='21:00' data-fin='22:00' data-p='95'" in cal  # franja + luz
    assert "data-dia=" in cal and "cal-dias" in cal  # vista por día en móvil
    # Reserva manual: día cerrado rechazado; precio sugerido con franja + luz.
    r = cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": martes, "hora": "19:00", "nombre": "X"})
    assert r.status_code == 400 and "cerrado" in r.json()["error"]
    r = cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": lunes, "hora": "21:00", "nombre": "Juan"}).json()
    assert r["ok"] and r["precio"] == 95
    # Bloquear un turno de un día cerrado: no existe.
    r = cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": martes, "hora": "19:00"})
    assert r.status_code == 400 and "cerrado" in r.json()["error"]
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": lunes, "hora": "19:00"}).json()["ok"]
    # Disponibilidad del día cerrado: sin turnos y con el motivo.
    dispo = cli.get(f"/anfitrion/disponibilidad?cancha=c_lima&fecha={martes}").text
    assert "Cerrado · Feriado" in dispo and "data-h=" not in dispo
    # Vista previa del editor (reglas sin guardar) = misma cancha efectiva.
    v = cli.post("/anfitrion/reglas/c_lima/vista", json={"fecha": martes, "reglas": {}}).json()
    assert v["ok"] and not v["cerrado"] and v["turnos"]
    v = cli.post("/anfitrion/reglas/c_lima/vista", json={"fecha": lunes, "reglas": web["db"].canchas["c_lima"]["reglas_reserva"]}).json()
    assert next(t for t in v["turnos"] if t["hora"] == "21:00")["precio"] == 95
    assert _reglas.cancha_del_dia(web["db"].canchas["c_lima"], martes)["_cerrado"] == "Feriado"


def test_horario_por_dia_cambia_las_filas_del_calendario(web):
    lunes = _proximo(0)
    web["db"].canchas["c_lima"]["reglas_reserva"] = {"horario_semana": {"lun": {"apertura": "09:00", "cierre": "12:00"}}}
    cal = _cli().get(f"/anfitrion/calendario?cancha=c_lima&desde={lunes}").text
    assert f"data-b='{lunes}' data-f='{lunes}' data-h='09:00'" in cal
    assert f"data-b='{lunes}' data-f='{lunes}' data-h='15:00'" not in cal  # fuera del horario del lunes
    martes = (date.fromisoformat(lunes) + timedelta(days=1)).isoformat()
    assert f"data-b='{martes}' data-f='{martes}' data-h='15:00'" in cal  # el martes sigue con el horario general
    assert "Fuera de horario" in cal
