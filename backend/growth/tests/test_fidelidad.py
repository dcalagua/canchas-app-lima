"""FIDELIDAD DEL LOCAL: cada N reservas pagadas, una hora gratis o un descuento
(pedido del director, 28-sep-2026). Ficha web, checkout, canje, reversa al
cancelar y editor del local."""
import os
import sys
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import fidelidad as fid  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402
from web import datos, sesion  # noqa: E402
from test_web_reservas import FakeDB, LIMA, _manana  # noqa: E402

FID = {"activa": True, "meta": 3, "premio": "hora_gratis", "descuentoPct": 20, "ventanaDias": 180, "aplica": "todas"}
C1 = {**LIMA, "id": "c_f1", "nombre": "Cancha 1", "club": "Club Fiel", "dueno": "dueno@gmail.com", "precio_hora": 60.0,
      "descuento_valle": 0, "servicios_extra": [{"clave": "pelotero", "precio": 10}], "fidelidad": dict(FID)}
C2 = {**C1, "id": "c_f2", "nombre": "Cancha 2", "precio_hora": 80.0}


class FakeDBFid(FakeDB):
    def __init__(self):
        super().__init__()
        self.canchas["c_f1"] = dict(C1)
        self.canchas["c_f2"] = dict(C2)
        self.canjes: dict[str, dict] = {}

    def col_fidelidad_disponible(self):
        return True

    def permite_boleadores(self, cancha_id):
        return True

    def reservas_pagadas_en(self, email, cancha_ids, limite=400):
        out = [dict(r) for r in self.reservas.values()
               if (r.get("usuario") or "").lower() == email.lower() and r["cancha_id"] in cancha_ids and r.get("pagado")
               and r.get("estado") not in ("cancelada", "no_show", "nueva")]
        return sorted(out, key=lambda r: (r["fecha"], r["hora_inicio"]))

    def insertar_canje(self, c):
        from datetime import datetime, timezone
        c = dict(c); c["creado"] = datetime.now(timezone.utc).isoformat()
        self.canjes[c["id"]] = c
        return True

    def canjes_de(self, email, local_key):
        return [dict(c) for c in self.canjes.values() if c["email"] == email and c["local_key"] == local_key]

    def canje_por_ref(self, ref):
        c = [x for x in self.canjes.values() if x["reserva_ref"] == ref and x["estado"] != "devuelto"]
        return dict(c[-1]) if c else None

    def canje_por_ids(self, ids):
        c = [x for x in self.canjes.values() if x["estado"] != "devuelto" and set(x["reserva_ids"]) & set(ids)]
        return dict(c[-1]) if c else None

    def actualizar_canje(self, cid, estado, solo_si=()):
        c = self.canjes.get(cid)
        if not c or (solo_si and c["estado"] not in solo_si):
            return False
        c["estado"] = estado
        return True


_FNS = ("canchas_publicas", "canchas_verificadas", "cancha", "ocupados", "descuentos", "liberar_holds_vencidos",
        "insertar_reservas", "confirmar_reservas", "borrar_reservas", "reservas_de", "reservas_por_grupo", "reservas_de_usuario",
        "eliminar_reservas", "canchas_de_dueno", "actualizar_cancha", "col_fidelidad_disponible", "permite_boleadores",
        "reservas_pagadas_en", "insertar_canje", "canjes_de", "canje_por_ref", "canje_por_ids", "actualizar_canje")


@pytest.fixture
def db(monkeypatch):
    fake = FakeDBFid()
    for fn in _FNS:
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    stores.config.pop("cargo_activo_reservas", None)
    return fake


def _sesion(cli, monkeypatch, email, nombre):
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": email, "email_verified": "true", "aud": "cid-web", "name": nombre, "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})


def _pagar(cli, monkeypatch, cancha="c_f1", hora=15, turnos=1, fidelidad=False, extras=None, dia=None):
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": True, "charge_id": f"chr_{hora}_{cancha}"})
    f = dia or _manana()
    horas = [{"fecha": f, "hora": f"{hora + i:02d}:00"} for i in range(turnos)]
    r = cli.post("/web/asegurar", json={"cancha_id": cancha, "horas": horas, "extras": extras or [], "fidelidad": fidelidad,
                                        "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r["ok"], r
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "" if r["sin_pago"] else "tkn",
                                     "medio": "fidelidad" if r["sin_pago"] else "tarjeta"}).json()
    assert p["ok"], p
    return r


def test_config_normalizada_y_descuentos():
    cfg = fid.normalizar({"activa": True, "meta": 99, "premio": "raro", "descuentoPct": 7, "ventanaDias": 12, "aplica": "x"})
    assert cfg == {"activa": True, "meta": 5, "premio": "hora_gratis", "descuentoPct": 20, "ventanaDias": 180, "aplica": "todas"}
    assert fid.validar({"activa": True, "meta": 99})[0] == "meta_invalida"
    assert fid.validar({"activa": True, "meta": 3, "premio": "descuento", "descuentoPct": 7})[0] == "descuento_invalido"
    assert fid.validar({"activa": False})[0] is None
    # Hora gratis = el turno más barato del bloque; descuento = % por turno.
    assert fid.descuento_para(fid.normalizar({"premio": "hora_gratis"}), [60, 45, 60]) == (45, [0, 45, 0])
    assert fid.descuento_para(fid.normalizar({"premio": "descuento", "descuentoPct": 20}), [60, 45]) == (21, [12, 9])
    assert fid.descuento_para(fid.normalizar({}), []) == (0, [])


def test_progreso_por_local_premio_en_el_checkout_y_ciclo(db, monkeypatch):
    """3 reservas pagadas en cualquier cancha del local → hora gratis: la 4.ª
    de un turno sale a 0 sin pasar por Culqi; el ciclo vuelve a cero."""
    stores.config["cargo_activo_reservas"] = "1"
    cli = TestClient(app, base_url="https://testserver")
    # Sin sesión: la ficha explica la promo; el estado no cuenta nada.
    html = cli.get("/reservar/c_f1").text
    assert "Tarjeta de fidelidad de Club Fiel" in html and "Cada 3 reservas pagadas, una hora gratis" in html
    assert cli.get("/web/fidelidad?cancha_id=c_f1").json()["conteo"] == 0
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    cargos = []
    for i in range(3):
        _pagar(cli, monkeypatch, cancha="c_f1" if i < 2 else "c_f2", hora=10 + i)
    est = cli.get("/web/fidelidad?cancha_id=c_f1").json()
    assert est["ok"] and est["conteo"] == 3 and est["disponible"] and est["faltan"] == 0 and est["nombrePremio"] == "una hora gratis"
    # Pedir el premio sin tenerlo (otra cuenta) → sin_premio.
    _sesion(cli, monkeypatch, "otro@gmail.com", "Otro")
    j = cli.post("/web/asegurar", json={"cancha_id": "c_f1", "horas": [{"fecha": _manana(), "hora": "20:00"}], "extras": [], "fidelidad": True,
                                        "nombre": "Otro Más", "celular": "999888777", "email": "otro@gmail.com"}).json()
    assert j == {"ok": False, "error": "sin_premio"}
    # Ana usa su hora gratis en un turno de S/ 60: sin cargo, sin Culqi, sin liquidación.
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_no"})
    pushes = []
    import pagos.router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo, cuerpo)))
    r = cli.post("/web/asegurar", json={"cancha_id": "c_f1", "horas": [{"fecha": _manana(), "hora": "20:00"}], "extras": [], "fidelidad": True,
                                        "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r["ok"] and r["total"] == 0 and r["total_centimos"] == 0 and r["sin_pago"] and r["cargo_centimos"] == 0
    assert r["fidelidad"] == {"descuento": 60, "premio": "hora_gratis", "texto": "Hora gratis"}
    cj = db.canje_por_ref(r["ids"][0])
    assert cj["estado"] == "reservado" and cj["descuento"] == 60 and len(cj["reservas_contadas"]) == 3
    # Mientras el hold vive, el premio ya no está disponible para otra pestaña.
    assert not cli.get("/web/fidelidad?cancha_id=c_f1").json()["disponible"]
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "", "medio": "fidelidad"}).json()
    assert p["ok"] and cargos == []
    fila = db.reservas[r["ids"][0]]
    assert fila["pagado"] and fila["medio_pago"] == "fidelidad" and fila["precio"] == 0
    assert db.canje_por_ref(r["ids"][0])["estado"] == "usado"
    assert any(e == "dueno@gmail.com" and "🎁" in t and "hora gratis" in c for e, t, c in pushes)
    assert stores.pago_por_charge("chr_no") is None
    # Comprobante con la línea del premio y "pagado con tu premio".
    comp = cli.get(f"/reserva/{r['ids'][0]}").text
    assert "Premio de fidelidad" in comp and "tu premio de fidelidad" in comp and "Total pagado</span><span>S/ 0.00" in comp
    # Ciclo nuevo: la gratis no cuenta; conteo 0 de 3.
    est = cli.get("/web/fidelidad?cancha_id=c_f1").json()
    assert est["conteo"] == 0 and not est["disponible"] and est["usados"] == 1
    # El dueño lo ve en el editor del local (chips) y lo puede cambiar.
    _sesion(cli, monkeypatch, "dueno@gmail.com", "Dueño")
    ed = cli.get("/anfitrion/local/c_f1/editar").text
    assert "Tarjeta de fidelidad" in ed and "data-g='fid_meta' data-v='3'" in ed.replace('"', "'")
    j = cli.post("/anfitrion/local/c_f1/editar", json={"nombre_local": "Club Fiel", "direccion": "", "amenidades": [], "servicios_extra": [],
                                                        "fidelidad": {"activa": True, "meta": 5, "premio": "descuento", "descuentoPct": 25, "ventanaDias": 90, "aplica": "online"}}).json()
    assert j["ok"] and j["canchas"] == 2
    assert db.canchas["c_f2"]["fidelidad"] == {"activa": True, "meta": 5, "premio": "descuento", "descuentoPct": 25, "ventanaDias": 90, "aplica": "online"}
    assert cli.post("/anfitrion/local/c_f1/editar", json={"nombre_local": "Club Fiel", "fidelidad": {"activa": True, "meta": 7}}).json()["error"].startswith("Elige cada")


def test_descuento_porcentual_liquida_el_precio_descontado_y_cancelar_devuelve_el_premio(db, monkeypatch):
    """Con premio `descuento` 20 % el bloque de 2 turnos (60+60) queda en 96:
    Culqi cobra 96 (+cargo), el dueño liquida 96 y el canje queda usado. Al
    cancelar esa reserva el premio vuelve al jugador."""
    db.canchas["c_f1"]["fidelidad"] = db.canchas["c_f2"]["fidelidad"] = {**FID, "premio": "descuento", "descuentoPct": 20, "aplica": "online"}
    cli = TestClient(app, base_url="https://testserver")
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    for i in range(3):
        _pagar(cli, monkeypatch, hora=9 + i)
    cargos = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_desc"})
    f = _manana()
    r = cli.post("/web/asegurar", json={"cancha_id": "c_f1", "horas": [{"fecha": f, "hora": "18:00"}, {"fecha": f, "hora": "19:00"}], "extras": ["pelotero"],
                                        "fidelidad": True, "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r["ok"] and r["total"] == 106 and r["fidelidad"]["descuento"] == 24 and not r["sin_pago"]  # 120 − 24 + pelotero 10
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "yape"}).json()
    assert p["ok"] and cargos[0]["monto_centimos"] == 10600
    liqs = [x for x in stores.pagos if x.tipo in ("liquidacion_online", "liquidacion_full") and x.dueno_id == "dueno@gmail.com" and x.monto_centimos == 10600]
    assert liqs, "la liquidación al dueño va por el precio ya descontado"
    assert all(db.reservas[i]["precio"] == 48 for i in r["ids"])
    ref = r["grupo"]
    assert db.canje_por_ref(ref)["estado"] == "usado"
    assert cli.get("/web/fidelidad?cancha_id=c_f1").json()["conteo"] == 0
    # Cancela la reserva premiada → el premio vuelve (conteo 3 de nuevo).
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: {"ok": True, "refund_id": "rf_x"})
    j = cli.post("/web/cancelar", json={"ref": ref, "medio": "original"}).json()
    assert j["ok"], j
    assert db.canje_por_ref(ref) is None
    est = cli.get("/web/fidelidad?cancha_id=c_f1").json()
    assert est["conteo"] == 3 and est["disponible"]
    # `aplica: online`: una reserva pagada en la cancha (medio efectivo) no suma.
    db.reservas["man1"] = {"id": "man1", "cancha_id": "c_f1", "fecha": f, "hora_inicio": "07:00", "hora_fin": "08:00", "estado": "confirmada",
                           "pagado": True, "usuario": "ana@gmail.com", "medio_pago": "efectivo", "precio": 60, "grupo_reserva_id": "", "extras": []}
    assert cli.get("/web/fidelidad?cancha_id=c_f1").json()["conteoTotal"] == 3
    db.canchas["c_f1"]["fidelidad"]["aplica"] = "todas"
    assert cli.get("/web/fidelidad?cancha_id=c_f1").json()["conteoTotal"] == 4


def test_hold_liberado_o_pago_rechazado_devuelven_el_premio_y_endpoints_del_app(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    _sesion(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    for i in range(3):
        _pagar(cli, monkeypatch, hora=9 + i)
    # Hold con premio que el jugador libera → el premio vuelve.
    r = cli.post("/web/asegurar", json={"cancha_id": "c_f1", "horas": [{"fecha": _manana(), "hora": "18:00"}], "extras": ["pelotero"], "fidelidad": True,
                                        "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r["ok"] and r["total"] == 10 and not r["sin_pago"]
    assert cli.post("/web/liberar", json={"ids": r["ids"], "firma": r["firma"]}).json()["ok"]
    assert db.canje_por_ref(r["ids"][0]) is None and cli.get("/web/fidelidad?cancha_id=c_f1").json()["disponible"]
    # Pago rechazado → el premio también vuelve.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "rechazado"})
    r = cli.post("/web/asegurar", json={"cancha_id": "c_f1", "horas": [{"fecha": _manana(), "hora": "18:00"}], "extras": ["pelotero"], "fidelidad": True,
                                        "nombre": "Ana Pérez", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert not cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "yape"}).json()["ok"]
    assert db.canje_por_ref(r["ids"][0]) is None and cli.get("/web/fidelidad?cancha_id=c_f1").json()["disponible"]
    # Endpoints del APK: estado, reservar (hold), confirmar, revertir; y catálogo del editor.
    e = cli.get("/fidelidad/estado?email=ana@gmail.com&cancha_id=c_f2").json()
    assert e["ok"] and e["disponible"] and e["conteo"] == 3 and e["local"] == "Club Fiel"
    j = cli.post("/fidelidad/canje/reservar", json={"email": "ana@gmail.com", "cancha_id": "c_f2", "reserva_ref": "grp_app_1",
                                                    "reserva_ids": ["jug_1", "jug_2"], "descuento": 80}).json()
    assert j["ok"] and j["canje"]["estado"] == "reservado" and j["canje"]["tipo"] == "hora_gratis"
    assert cli.post("/fidelidad/canje/reservar", json={"email": "ana@gmail.com", "cancha_id": "c_f2", "reserva_ref": "grp_app_1", "descuento": 80}).json()["repetido"]
    assert cli.post("/fidelidad/canje/confirmar", json={"reserva_ref": "grp_app_1"}).json()["ok"]
    assert db.canje_por_ref("grp_app_1")["estado"] == "usado"
    assert not cli.get("/fidelidad/estado?email=ana@gmail.com&cancha_id=c_f1").json()["disponible"]
    assert cli.post("/fidelidad/canje/revertir", json={"reserva_ref": "grp_app_1"}).json()["ok"]
    assert cli.get("/fidelidad/estado?email=ana@gmail.com&cancha_id=c_f1").json()["disponible"]
    # Uso directo (efectivo en el app): reservar + confirmar en una llamada.
    j = cli.post("/fidelidad/canje/reservar", json={"email": "ana@gmail.com", "cancha_id": "c_f1", "reserva_ref": "jug_9", "descuento": 60, "confirmar": True}).json()
    assert j["ok"] and j["canje"]["estado"] == "usado"
    assert cli.get("/fidelidad/catalogo").json()["metas"][0] == 2
