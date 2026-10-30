"""BOLEADORES (sparring por turno, docs/diseno-boleadores.md): registro por
selección con identidad verificada, disponibilidad por local/franja/cruces,
contratación al reservar en la web (solo en línea), aceptación con push,
liquidación con comisión FIJA por turno liberada al terminar el turno,
rechazo/vencimiento con devolución parcial, cancelaciones y faltas."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import boleadores as bol  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402
from web import datos, sesion  # noqa: E402
from web import router as web  # noqa: E402
from test_web_reservas import FakeDB, LIMA, _manana  # noqa: E402

TENIS = {**LIMA, "id": "c_tenis", "nombre": "Cancha 1", "club": "Club Raqueta", "deporte": "tenis", "deportes": ["tenis"],
         "precio_hora": 40.0, "descuento_valle": 0, "servicios_extra": [{"clave": "pelotero", "precio": 10}]}
TENIS2 = {**TENIS, "id": "c_tenis2", "nombre": "Cancha 2"}


class FakeDBBol(FakeDB):
    def __init__(self):
        super().__init__()
        self.canchas["c_tenis"] = dict(TENIS)
        self.canchas["c_tenis2"] = dict(TENIS2)
        self.boleadores: dict[str, dict] = {}
        self.solicitudes: dict[str, dict] = {}
        self.permite: dict[str, bool] = {}

    # boleadores
    def boleador(self, email):
        b = self.boleadores.get(email.lower())
        return dict(b) if b else None

    def boleador_por_slug(self, slug):
        return next((dict(b) for b in self.boleadores.values() if b.get("slug") == slug), None)

    def guardar_boleador(self, email, *, deporte, categoria, tarifa, moneda, activo, data):
        self.boleadores[email] = {**data, "email": email, "deporte": deporte, "categoria": categoria, "tarifa": tarifa,
                                  "moneda": moneda, "activo": activo}
        return True

    def actualizar_boleador(self, email, *, activo=None, data_merge=None):
        b = self.boleadores.get(email)
        if not b:
            return False
        if data_merge:
            b.update(data_merge)
        if activo is not None:
            b["activo"] = activo
        return True

    def boleadores_de_cancha(self, cancha_id, deporte=""):
        return [dict(b) for b in self.boleadores.values()
                if b.get("activo") and cancha_id in (b.get("canchas") or []) and (not deporte or b.get("deporte") == deporte)]

    def permite_boleadores(self, cancha_id):
        return self.permite.get(cancha_id, True)

    # solicitudes
    def insertar_solicitud(self, s):
        s = dict(s)
        s["creado"] = datetime.now(timezone.utc).isoformat()
        if hasattr(s.get("vence_en"), "isoformat"):
            s["vence_en"] = s["vence_en"].isoformat()
        self.solicitudes[s["id"]] = s
        return True

    def solicitud(self, sid):
        s = self.solicitudes.get(sid)
        return dict(s) if s else None

    def solicitud_por_reserva(self, ref):
        c = [s for s in self.solicitudes.values() if s["reserva_ref"] == ref]
        c.sort(key=lambda s: (s["estado"] in bol.ESTADOS_VIVOS, s["creado"]), reverse=True)
        return dict(c[0]) if c else None

    def solicitudes_de_boleador(self, email, estados=(), limite=100):
        return [dict(s) for s in self.solicitudes.values() if s["boleador_email"] == email and (not estados or s["estado"] in estados)]

    def solicitudes_de_cliente(self, email, limite=100):
        return [dict(s) for s in self.solicitudes.values() if s["cliente_email"] == email]

    def solicitudes_cruce(self, email, fecha, hi, hf):
        return [dict(s) for s in self.solicitudes.values() if s["boleador_email"] == email and s["fecha"] == fecha
                and s["estado"] in bol.ESTADOS_VIVOS and s["hora_inicio"] < hf and s["hora_fin"] > hi]

    def solicitudes_vencidas(self):
        now = datetime.now(timezone.utc).isoformat()
        return [dict(s) for s in self.solicitudes.values() if s["estado"] == "pendiente" and s.get("vence_en") and s["vence_en"] < now]

    def actualizar_solicitud(self, sid, *, estado=None, data_merge=None, respondida=False, solo_si_estado=()):
        s = self.solicitudes.get(sid)
        if not s or (solo_si_estado and s["estado"] not in solo_si_estado):
            return False
        if estado:
            s["estado"] = estado
        if data_merge:
            s["data"] = {**(s.get("data") or {}), **data_merge}
        if respondida:
            s["respondido_en"] = datetime.now(timezone.utc).isoformat()
        return True

    def marcar_extra_boleador(self, ids, estado):
        for i in ids:
            for x in (self.reservas.get(i, {}).get("extras") or []):
                if x.get("clave") == "boleador":
                    x["estado"] = estado
        return True


_FNS = ("canchas_publicas", "canchas_verificadas", "cancha", "ocupados", "descuentos", "liberar_holds_vencidos",
        "insertar_reservas", "confirmar_reservas", "borrar_reservas", "reservas_de", "reservas_por_grupo", "reservas_de_usuario",
        "eliminar_reservas", "canchas_de_dueno", "esta_verificado",
        "boleador", "boleador_por_slug", "guardar_boleador", "actualizar_boleador", "boleadores_de_cancha", "permite_boleadores",
        "insertar_solicitud", "solicitud", "solicitud_por_reserva", "solicitudes_de_boleador", "solicitudes_de_cliente",
        "solicitudes_cruce", "solicitudes_vencidas", "actualizar_solicitud", "marcar_extra_boleador")


@pytest.fixture
def db(monkeypatch):
    fake = FakeDBBol()
    for fn in _FNS:
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    stores.config.pop("cargo_activo_reservas", None)
    stores.config.pop("boleadores_activo", None)
    return fake


def _perfil(email="juan@gmail.com", **kw):
    base = {"email": email, "nombre": "Juan Pérez", "celular": "999111222", "deporte": "tenis", "categoria": "4ta",
            "tarifa": 20, "canchas": ["c_tenis", "c_tenis2"], "disponibilidad": {"dias": [1, 2, 3, 4, 5, 6, 7], "desde": "07:00", "hasta": "21:00"},
            "etiquetas": ["Peloteo", "Zurdo", "invento"], "activo": True}
    base.update(kw)
    return base


def _sesion(cli, monkeypatch, email, nombre):
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": email, "email_verified": "true", "aud": "cid-web", "name": nombre, "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})


def test_config_y_registro_por_seleccion_con_identidad_verificada(db):
    cli = TestClient(app)
    cfg = cli.get("/boleadores/config?pais=PE").json()
    assert cfg["categorias"] == ["5P", "5A", "5B", "4ta", "3ra", "2da", "1ra"]  # las de la Liga Pichangol
    assert cfg["comision"] == 2.0 and cfg["nombre"] == "Boleador" and cfg["simbolo"] == "S/"
    assert cli.get("/boleadores/config?pais=EC").json()["nombre"] == "Sparring"
    assert cli.get("/boleadores/config?pais=EC").json()["comision"] == 0.5
    # Sin identidad verificada no hay registro.
    assert cli.post("/boleadores/perfil", json=_perfil()).json()["error"] == "verificacion_requerida"
    db.verificados.add("juan@gmail.com")
    assert cli.post("/boleadores/perfil", json=_perfil(categoria="pro")).json()["error"] == "categoria_requerida"
    assert cli.post("/boleadores/perfil", json=_perfil(canchas=[])).json()["error"] == "canchas_requeridas"
    assert cli.post("/boleadores/perfil", json=_perfil(canchas=["c_pend"])).json()["error"] == "cancha_invalida"
    assert cli.post("/boleadores/perfil", json=_perfil(tarifa=0)).json()["error"] == "tarifa_invalida"
    r = cli.post("/boleadores/perfil", json=_perfil()).json()
    assert r["ok"]
    b = db.boleadores["juan@gmail.com"]
    assert b["categoria"] == "4ta" and b["tarifa"] == 20 and b["moneda"] == "PEN" and b["slug"] == bol.slug_de("juan@gmail.com")
    assert b["etiquetas"] == ["Peloteo", "Zurdo"]  # solo del catálogo
    assert [l["club"] for l in b["locales"]] == ["Club Raqueta"] and b["canchas"] == ["c_tenis", "c_tenis2"]
    p = cli.get("/boleadores/perfil/juan@gmail.com").json()
    assert p["boleador"]["categoria"] == "4ta" and p["verificado"] and p["config"]["comision"] == 2.0
    # Pausar / activar.
    assert cli.post("/boleadores/perfil/activo", json={"email": "juan@gmail.com", "activo": False}).json()["ok"]
    assert db.boleadores["juan@gmail.com"]["activo"] is False


def test_disponibles_por_local_franja_cruces_y_local_que_no_permite(db):
    cli = TestClient(app)
    db.verificados.add("juan@gmail.com"); db.verificados.add("lu@gmail.com")
    assert cli.post("/boleadores/perfil", json=_perfil()).json()["ok"]
    assert cli.post("/boleadores/perfil", json=_perfil("lu@gmail.com", nombre="Lucía", categoria="5A", tarifa=15,
                                                       disponibilidad={"dias": [6, 7], "desde": "08:00", "hasta": "12:00"})).json()["ok"]
    f = _manana()
    wd = datetime.fromisoformat(f).isoweekday()

    def disp(hora, turnos=1, cancha="c_tenis", deporte=""):
        j = cli.get(f"/boleadores/disponibles?cancha_id={cancha}&fecha={f}&hora={hora}&turnos={turnos}&deporte={deporte}").json()
        return sorted(b["nombre"] for b in j["boleadores"])

    juan = ["Juan Pérez"]
    esperado_10 = sorted(juan + (["Lucía"] if wd in (6, 7) else []))
    assert disp("10:00") == esperado_10
    assert disp("20:00") == juan            # 20:00–21:00 cabe en la franja de Juan
    assert disp("20:00", turnos=2) == []    # 20:00–22:00 se pasa de las 21:00
    assert disp("10:00", cancha="c_lima") == []  # fútbol: sin boleadores
    for b in cli.get(f"/boleadores/disponibles?cancha_id=c_tenis&fecha={f}&hora=10:00").json()["boleadores"]:
        assert "email" not in b and b["slug"] and b["simbolo"] == "S/"  # el público no ve correos
    # Un boleo ya aceptado a esa hora lo saca de la lista (cruce), aunque sea en otra cancha.
    db.solicitudes["bs_x"] = {"id": "bs_x", "boleador_email": "juan@gmail.com", "cliente_email": "z@z.com", "reserva_ref": "r_z",
                              "fecha": f, "hora_inicio": "10:00", "hora_fin": "11:00", "estado": "aceptada", "creado": "2026",
                              "turnos": 1, "monto_centimos": 2000, "comision_centimos": 200, "moneda": "PEN", "data": {}}
    assert "Juan Pérez" not in disp("10:00") and "Juan Pérez" in disp("11:00")
    assert "Juan Pérez" not in disp("09:00", turnos=2)  # 09:00–11:00 se cruza
    # El local puede no permitir boleadores externos.
    db.permite["c_tenis"] = False
    assert disp("11:00") == []
    db.permite["c_tenis"] = True
    stores.config["boleadores_activo"] = "0"
    assert disp("11:00") == []
    stores.config.pop("boleadores_activo", None)


def test_contratar_al_reservar_en_la_web_aceptar_y_liquidacion_con_comision_fija(db, monkeypatch):
    """Flujo completo web: la ficha ofrece boleador solo en tenis/pádel, la línea
    entra en `extras`, el dueño recibe SIN la parte del boleador, la solicitud
    queda pendiente con push, el boleador acepta desde Modo anfitrión y nace su
    liquidación (20 × 2 turnos − 2 × 2 = 36) liberada al terminar el turno."""
    import pagos.router as pr
    cargos, pushes = [], []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: (cargos.append(kw) or {"ok": True, "charge_id": "chr_b1"}))
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo, tipo)))
    stores.config["cargo_activo_reservas"] = "1"
    stores.saldos.pop("dueno@x.com", None)
    db.verificados.add("juan@gmail.com")
    cli = TestClient(app, base_url="https://testserver")
    assert cli.post("/boleadores/perfil", json=_perfil()).json()["ok"]
    slug = db.boleadores["juan@gmail.com"]["slug"]
    # La ficha de tenis ofrece boleador; la de fútbol no.
    html = cli.get("/reservar/c_tenis").text
    assert "¿Quieres un boleador?" in html and "id='bolBox'" in html and '"boleadores": true' in html
    assert "cargarBoleadores()" in html and "boleador: blSel ? blSel.slug : ''" in html and "/boleadores/disponibles?" in html
    assert "id='bolBox'" not in cli.get("/reservar/c_lima").text
    f = _manana()
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    # Boleador inexistente / no disponible → error claro.
    r = cli.post("/web/asegurar", json={"cancha_id": "c_tenis", "horas": [{"fecha": f, "hora": "22:00"}], "extras": [], "boleador": slug,
                                        "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r["error"] == "boleador_no_disponible"   # 22:00 está fuera de su franja
    r = cli.post("/web/asegurar", json={"cancha_id": "c_tenis", "horas": [{"fecha": f, "hora": "15:00"}, {"fecha": f, "hora": "16:00"}],
                                        "extras": ["pelotero"], "boleador": slug, "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r["ok"] and r["total"] == 40 + 40 + 10 + 40   # 2 turnos + pelotero + boleador 20 × 2
    ex = db.reservas[r["ids"][0]]["extras"]
    linea = next(x for x in ex if x["clave"] == "boleador")
    assert linea["precio"] == 40.0 and linea["cantidad"] == 2 and linea["unitario"] == 20 and linea["boleador"] == slug
    assert linea["nombre"] == "Boleador · Juan Pérez" and linea["estado"] == "pendiente" and linea["tipo"] == "turno"
    cargo_total = r["cargo_centimos"]
    assert cargo_total == 650  # 5 % de 130
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "yape"}).json()
    assert p["ok"]
    assert cargos[0]["monto_centimos"] == 13650
    # El dueño recibe sobre 90 (cancha + pelotero), NO sobre los 40 del boleador.
    liq = stores.pago_por_charge(r["ids"][0])
    assert liq is not None and liq.monto_centimos == 9000
    # Solicitud pendiente con plazo, cargo proporcional y pushes a ambos.
    sol = db.solicitud_por_reserva(r["grupo"])
    assert sol and sol["estado"] == "pendiente" and sol["boleador_email"] == "juan@gmail.com" and sol["canal"] == "web"
    assert sol["monto_centimos"] == 4000 and sol["comision_centimos"] == 400 and sol["turnos"] == 2 and sol["charge_id"] == "chr_b1"
    assert sol["data"]["cargo_centimos"] == 200   # 650 × 40 / 130
    assert sol["hora_inicio"] == "15:00" and sol["hora_fin"] == "17:00" and sol["data"]["reserva_ids"] == r["ids"]
    assert ("juan@gmail.com", "Te contrataron 🎾", "boleador") in pushes and ("ana@gmail.com", "Esperando al boleador ⏳", "boleador") in pushes
    # Comprobante: la línea del boleador con su estado.
    comp = cli.get(p["url"]).text
    assert "Boleador · Juan Pérez" in comp and "Esperando confirmación" in comp
    # Juan entra a Modo anfitrión → "Soy boleador" con la solicitud pendiente y acepta.
    cli.post("/web/salir")
    _sesion(cli, monkeypatch, "juan@gmail.com", "Juan Pérez")
    menu = cli.get("/anfitrion").text
    assert "Soy boleador" in menu and "href='/anfitrion/boleador'" in menu
    pag = cli.get("/anfitrion/boleador").text
    assert "Solicitudes pendientes" in pag and "ganas S/ 36.00" in pag and "data-bol-acc='aceptar'" in pag and "Ana Pérez" in pag
    assert "comisión Pichangol S/ 4.00" in pag
    j = cli.post(f"/anfitrion/boleador/solicitud/{sol['id']}/aceptar").json()
    assert j["ok"] and j["solicitud"]["estado"] == "aceptada"
    lb = stores.pago_por_charge(f"bol:{sol['id']}")
    assert lb is not None and lb.tipo == "liquidacion_boleador" and lb.dueno_id == "juan@gmail.com"
    assert lb.monto_centimos == 4000 and lb.comision_centimos == 400 and lb.cargo_id == "chr_b1" and lb.medio == "yape"
    assert lb.disponible_en is not None and lb.disponible_en > datetime.now(timezone.utc)
    assert lb.concepto.startswith("🎾 Boleador · Juan Pérez · Club Raqueta")
    d = pr._liquidacion_dict(lb)
    assert d["neto_soles"] == 36.0 and d["comision_soles"] == 4.0 and d["liberada"] is False and d["disponible_en"]
    # Está en la cola "por recibir" del boleador y en la torre; el lote la posterga hasta liberarse.
    assert cli.get("/pagos/por-recibir/juan@gmail.com").json()["por_recibir_soles"] == 36.0
    pend = cli.get("/pagos/liquidaciones/pendientes", headers={"X-Admin-Token": "adm"}).json()
    fila = next(x for x in pend["pendientes"] if x["reserva_id"] == f"bol:{sol['id']}")
    assert fila["tipo"] == "liquidacion_boleador" and fila["liberada"] is False
    from pagos import cuentas_cobro as cc
    lote = cc.armar_lote([fila], {}, "PEN", 0)
    assert lote["filas"] == []
    lb.disponible_en = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert cc.armar_lote([pr._liquidacion_dict(lb)], {}, "PEN", 0)["filas"][0]["neto_centimos"] == 3600
    mov = cli.get("/pagos/movimientos/juan@gmail.com").json()["movimientos"]
    assert mov[0]["tipo"] == "liquidacion_boleador" and mov[0]["neto_soles"] == 36.0 and mov[0]["liquidado"] is False
    # Aceptar dos veces es idempotente; la reserva quedó marcada y el cliente avisado.
    assert cli.post(f"/anfitrion/boleador/solicitud/{sol['id']}/aceptar").json().get("ya")
    assert next(x for x in db.reservas[r["ids"][0]]["extras"] if x["clave"] == "boleador")["estado"] == "aceptada"
    assert ("ana@gmail.com", "Boleador confirmado ✅", "boleador") in pushes
    assert db.boleadores["juan@gmail.com"]["stats"]["aceptadas"] == 1
    assert "Confirmado ✅" in cli.get(p["url"]).text
    # Mientras está aceptada, otro cliente no lo ve a esa hora.
    assert cli.get(f"/boleadores/disponibles?cancha_id=c_tenis2&fecha={f}&hora=16:00").json()["boleadores"] == []
    stores.config.pop("cargo_activo_reservas", None)


def _reserva_con_boleador(db, cli, monkeypatch, hora="15:00", turnos=2, charge="chr_b2"):
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": True, "charge_id": charge})
    f = _manana()
    horas = [{"fecha": f, "hora": f"{int(hora[:2]) + i:02d}:00"} for i in range(turnos)]
    slug = db.boleadores["juan@gmail.com"]["slug"]
    r = cli.post("/web/asegurar", json={"cancha_id": "c_tenis", "horas": horas, "extras": [], "boleador": slug,
                                        "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r["ok"], r
    assert cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "tarjeta"}).json()["ok"]
    return r, db.solicitud_por_reserva(r["grupo"] or r["ids"][0])


def test_rechazo_vencimiento_y_devolucion_parcial_al_cliente(db, monkeypatch):
    """Si el boleador rechaza o no responde, la reserva sigue SIN boleador y
    se devuelve su parte + el cargo proporcional al medio original (reembolso
    parcial de Culqi); si Culqi falla queda `manual` en Cancelaciones web."""
    import pagos.router as pr
    pushes, reembolsos = [], []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo, cuerpo)))
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: (reembolsos.append(kw) or {"ok": True, "refund_id": "rf_1"}))
    stores.config["cargo_activo_reservas"] = "1"
    db.verificados.add("juan@gmail.com")
    cli = TestClient(app, base_url="https://testserver")
    assert cli.post("/boleadores/perfil", json=_perfil()).json()["ok"]
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    r, sol = _reserva_con_boleador(db, cli, monkeypatch)
    assert sol["monto_centimos"] == 4000 and sol["data"]["cargo_centimos"] == 200  # cargo 600 × 40/120
    # Rechaza (APK).
    j = cli.post(f"/boleadores/solicitudes/{sol['id']}/rechazar", json={"email": "juan@gmail.com", "motivo": "ocupado"}).json()
    assert j["ok"] and j["estado"] == "rechazada" and j["devolucion"]["estado"] == "reembolsado"
    assert reembolsos[0] == {"charge_id": "chr_b2", "monto_centimos": 4200, "motivo": "solicitud_comprador"}
    dev = stores.pago_por_charge(f"devbol:{sol['id']}")
    assert dev is not None and dev.tipo == "devolucion_boleador" and dev.monto_centimos == 4200 and dev.estado == "reembolsado"
    assert next(x for x in db.reservas[r["ids"][0]]["extras"] if x["clave"] == "boleador")["estado"] == "rechazada"
    assert any(e == "ana@gmail.com" and "no puede ese día" in c and "S/ 42.00" in c for e, _t, c in pushes)
    assert db.boleadores["juan@gmail.com"]["stats"]["rechazadas"] == 1
    assert stores.pago_por_charge(f"bol:{sol['id']}") is None  # nunca hubo liquidación
    assert "No disponible · devuelto" in cli.get(f"/reserva/{r['grupo']}").text
    # Rechazar de nuevo no devuelve dos veces.
    assert cli.post(f"/boleadores/solicitudes/{sol['id']}/rechazar", json={"email": "juan@gmail.com"}).json()["error"] == "rechazada"
    assert len(reembolsos) == 1
    # Vencimiento por el cron: sin respuesta a tiempo → `vencida` + devolución; Culqi falla → manual para la torre.
    r2, sol2 = _reserva_con_boleador(db, cli, monkeypatch, hora="18:00", turnos=1, charge="chr_b3")
    assert bol.vencer_pendientes() == 0
    db.solicitudes[sol2["id"]]["vence_en"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: {"ok": False, "error": "sin_fondos_culqi"})
    antes = len(stores.cancelaciones_web)
    assert bol.vencer_pendientes() == 1
    assert db.solicitudes[sol2["id"]]["estado"] == "vencida"
    reg = stores.cancelaciones_web[-1]
    assert len(stores.cancelaciones_web) == antes + 1 and reg["reembolso"] == "fallo" and reg["boleador"] and reg["monto"] == 21.33
    assert cli.post(f"/boleadores/solicitudes/{sol2['id']}/aceptar", json={"email": "juan@gmail.com"}).json()["error"] == "vencida"
    # Un cliente ajeno no puede responder.
    assert cli.post(f"/boleadores/solicitudes/{sol2['id']}/aceptar", json={"email": "otro@gmail.com"}).json()["error"] == "ajena"
    stores.config.pop("cargo_activo_reservas", None)


def test_cancelaciones_del_cliente_y_del_boleador_con_faltas(db, monkeypatch):
    """Cliente cancela → la solicitud se cancela y la liquidación del boleador
    se anula (o deja deuda si ya se pagó). Boleador cancela tras aceptar →
    devolución al cliente, falta; 2 faltas en 90 días pausan el perfil."""
    import pagos.router as pr
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo)))
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: {"ok": True, "refund_id": "rf"})
    db.verificados.add("juan@gmail.com")
    cli = TestClient(app, base_url="https://testserver")
    assert cli.post("/boleadores/perfil", json=_perfil()).json()["ok"]
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    # 1) Aceptada y luego el CLIENTE cancela desde la web (política de la reserva).
    r, sol = _reserva_con_boleador(db, cli, monkeypatch, hora="15:00", turnos=1, charge="chr_c1")
    assert cli.post(f"/boleadores/solicitudes/{sol['id']}/aceptar", json={"email": "juan@gmail.com"}).json()["ok"]
    lb = stores.pago_por_charge(f"bol:{sol['id']}")
    assert lb.estado == "aprobado"
    c = cli.post("/web/cancelar", json={"ref": r["grupo"] or r["ids"][0], "medio": "original"}).json()
    assert c["ok"]
    assert db.solicitudes[sol["id"]]["estado"] == "cancelada" and lb.estado == "anulado"
    assert ("juan@gmail.com", "Boleo cancelado 📅") in pushes
    # 2) Ya liquidada al boleador → deuda (`ajuste_cancelacion`).
    r2, sol2 = _reserva_con_boleador(db, cli, monkeypatch, hora="17:00", turnos=1, charge="chr_c2")
    assert cli.post(f"/boleadores/solicitudes/{sol2['id']}/aceptar", json={"email": "juan@gmail.com"}).json()["ok"]
    stores.marcar_liquidacion_pagada(f"bol:{sol2['id']}", "yape", "op1")
    assert cli.post("/web/cancelar", json={"ref": r2["grupo"] or r2["ids"][0], "medio": "original"}).json()["ok"]
    aj = stores.pago_por_charge(f"bol:{sol2['id']}_ajuste")
    assert aj is not None and aj.tipo == "ajuste_cancelacion" and aj.monto_centimos == 1800 and aj.dueno_id == "juan@gmail.com"
    # 3) El BOLEADOR cancela dos boleos aceptados → dos faltas → perfil pausado.
    r3, sol3 = _reserva_con_boleador(db, cli, monkeypatch, hora="19:00", turnos=1, charge="chr_c3")
    assert cli.post(f"/boleadores/solicitudes/{sol3['id']}/aceptar", json={"email": "juan@gmail.com"}).json()["ok"]
    j = cli.post(f"/boleadores/solicitudes/{sol3['id']}/cancelar", json={"email": "juan@gmail.com", "motivo": "lesión"}).json()
    assert j["ok"] and j["estado"] == "cancelada_boleador" and j["devolucion"]["estado"] == "reembolsado" and j["pausado"] is False
    assert stores.pago_por_charge(f"bol:{sol3['id']}").estado == "anulado"
    assert db.boleadores["juan@gmail.com"]["stats"]["faltas"] == 1 and db.boleadores["juan@gmail.com"]["activo"]
    r4, sol4 = _reserva_con_boleador(db, cli, monkeypatch, hora="20:00", turnos=1, charge="chr_c4")
    assert cli.post(f"/boleadores/solicitudes/{sol4['id']}/aceptar", json={"email": "juan@gmail.com"}).json()["ok"]
    j = cli.post(f"/boleadores/solicitudes/{sol4['id']}/cancelar", json={"email": "juan@gmail.com"}).json()
    assert j["ok"] and j["pausado"] is True
    assert db.boleadores["juan@gmail.com"]["activo"] is False and db.boleadores["juan@gmail.com"]["stats"]["faltas"] == 2
    assert ("juan@gmail.com", "Tu perfil de boleador quedó pausado ⏸️") in pushes
    # Mis solicitudes (APK): como boleador y como cliente, con estado visible y neto.
    m = cli.get("/boleadores/solicitudes?email=juan@gmail.com").json()
    assert m["ok"] and len(m["como_boleador"]) == 4 and m["pendientes"] == 0 and m["como_boleador"][0]["neto_centimos"] == 1800
    assert {s["estado_visible"] for s in m["como_boleador"]} >= {"Cancelado", "Canceló · devuelto"}
    assert len(cli.get("/boleadores/solicitudes?email=ana@gmail.com").json()["como_cliente"]) == 4


def test_solicitar_desde_el_app_tras_pagar(db, monkeypatch):
    """El APK cobra la reserva (Culqi en el celular) y luego registra la
    solicitud con `POST /boleadores/solicitar` (idempotente por reserva)."""
    import pagos.router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    db.verificados.add("juan@gmail.com")
    cli = TestClient(app)
    assert cli.post("/boleadores/perfil", json=_perfil()).json()["ok"]
    slug = db.boleadores["juan@gmail.com"]["slug"]
    f = _manana()
    body = {"slug": slug, "cliente_email": "ana@gmail.com", "cliente_nombre": "Ana", "reserva_ids": ["app_a", "app_b"], "reserva_ref": "grp_app",
            "cancha_id": "c_tenis", "fecha": f, "hora_inicio": "15:00", "hora_fin": "17:00", "turnos": 2, "charge_id": "chr_app", "cargo_centimos": 200, "medio": "yape"}
    j = cli.post("/boleadores/solicitar", json=body).json()
    assert j["ok"] and j["solicitud"]["estado"] == "pendiente" and j["solicitud"]["canal"] == "app" and j["solicitud"]["monto_centimos"] == 4000
    j2 = cli.post("/boleadores/solicitar", json=body).json()
    assert j2["ok"] and j2.get("ya") and len(db.solicitudes) == 1
    assert cli.post("/boleadores/solicitar", json={**body, "slug": "nadie"}).json()["error"] == "boleador_no_disponible"
    sid = j["solicitud"]["id"]
    assert cli.post(f"/boleadores/solicitudes/{sid}/aceptar", json={"email": "juan@gmail.com"}).json()["ok"]
    lb = stores.pago_por_charge(f"bol:{sid}")
    assert lb.monto_centimos == 4000 and lb.comision_centimos == 400 and lb.cargo_id == "chr_app"


def test_comision_fija_por_moneda_y_tarifa_menor_que_la_comision(db):
    assert bol.comision_centimos("PEN") == 200 and bol.comision_centimos("USD") == 50 and bol.comision_centimos("BOB") == 300
    stores.config["boleador_comision_PEN"] = "1.5"
    assert bol.comision_centimos("S/") == 150
    stores.config.pop("boleador_comision_PEN", None)
    # Solicitud con tarifa ridícula: el neto nunca queda negativo.
    b = {"email": "x@x.com", "nombre": "X", "tarifa": 1.0, "moneda": "PEN", "slug": "s"}
    sol = bol.crear_solicitud(boleador=b, cliente_email="", cliente_nombre="", reserva_ids=["r"], reserva_ref="r", cancha=None,
                              fecha=_manana(), hora_inicio="10:00", hora_fin="11:00", turnos=1)
    assert sol and sol["monto_centimos"] == 100 and sol["comision_centimos"] == 99
