"""REGLAS DE RESERVA por cancha (plan nocturno A2): horario por día de la
semana, cierres, franjas de precio, recargo de luz, ventana de anticipación,
turnos mín./máx., tope por jugador y cancelación del club. Una cancha SIN
reglas se comporta exactamente como antes."""

import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from reservas import reglas  # noqa: E402
from web import horarios  # noqa: E402
from web import router as web  # noqa: E402
from tests.test_web_reservas import LIMA, client, db  # noqa: E402,F401

CASOS = os.path.join(os.path.dirname(__file__), "fixtures", "reglas_casos.json")


def _proximo(dia: int) -> str:
    """Próxima fecha (desde pasado mañana) que cae en `dia` (0 = lunes)."""
    d = date.today() + timedelta(days=2)
    while d.weekday() != dia:
        d += timedelta(days=1)
    return d.isoformat()


# ── normalización ────────────────────────────────────────────────────────────

def test_normalizar_descarta_lo_invalido_y_recorta():
    r = reglas.normalizar({
        "horario_semana": {"lun": {"apertura": "08:00", "cierre": "22:00"}, "dom": None,
                           "mar": {"apertura": "25:00", "cierre": "x"}, "xxx": {}},
        "cierres": [{"fecha": "2026-12-25", "motivo": "Navidad"}, {"fecha": "no"}],
        "franjas": [{"dias": ["sab", "dom"], "desde": "08:00", "hasta": "14:00", "precio_hora": 150},
                    {"desde": "10:00", "hasta": "10:00", "precio_hora": 1},   # rango vacío
                    {"desde": "10:00", "hasta": "12:00"}],                    # sin precio
        "anticipacion_min_horas": 999, "min_turnos": 3, "max_turnos": 2,
        "cancelacion_horas": "12", "basura": 1,
    })
    assert r["horario_semana"] == {"lun": {"apertura": "08:00", "cierre": "22:00"}, "dom": None}
    assert r["cierres"] == [{"fecha": "2026-12-25", "motivo": "Navidad"}]
    assert len(r["franjas"]) == 1 and r["franjas"][0]["dias"] == ["sab", "dom"]
    assert r["anticipacion_min_horas"] == 72          # tope
    assert r["min_turnos"] == 3 and r["max_turnos"] == 3  # max nunca menor que min
    assert r["cancelacion_horas"] == 12.0
    assert "basura" not in r
    assert reglas.normalizar("no es json") == {} and reglas.normalizar(None) == {}


def test_sin_reglas_es_la_misma_cancha():
    assert reglas.cancha_del_dia(LIMA, "2026-11-02") is LIMA
    assert horarios.precio_turno_de(LIMA, "18:00") == 60


# ── horario por día y cierres ────────────────────────────────────────────────

def test_horario_por_dia_y_cierres_especiales():
    c = {**LIMA, "reglas_reserva": {
        "horario_semana": {"sab": {"apertura": "09:00", "cierre": "13:00"}, "dom": None},
        "cierres": [{"fecha": _proximo(0), "motivo": "Mantenimiento"}]}}
    sab = reglas.cancha_del_dia(c, _proximo(5))
    assert horarios.slots_de(sab) == ["09:00", "10:00", "11:00", "12:00", "13:00"]
    dom = reglas.cancha_del_dia(c, _proximo(6))
    assert dom["_cerrado"] == "cerrado" and horarios.slots_de(dom) == []
    lun = reglas.cancha_del_dia(c, _proximo(0))
    assert lun["_cerrado"] == "Mantenimiento"
    mar = reglas.cancha_del_dia(c, _proximo(1))   # día no configurado → horario general
    assert horarios.slots_de(mar)[0] == "07:00" and horarios.slots_de(mar)[-1] == "23:00"


# ── precios ──────────────────────────────────────────────────────────────────

def test_franja_manda_sobre_hora_feliz_y_luz_suma():
    c = {**LIMA, "reglas_reserva": {
        "franjas": [{"nombre": "Punta", "dias": ["lun", "mar", "mie", "jue", "vie"],
                     "desde": "18:00", "hasta": "23:59", "precio_hora": 100},
                    {"nombre": "Finde", "dias": ["sab", "dom"], "desde": "07:00", "hasta": "23:59",
                     "precio_turno": 90}],
        "recargo_luz": {"desde": "18:30", "monto": 10}}}
    lun = reglas.cancha_del_dia(c, _proximo(0))
    assert horarios.precio_turno_de(lun, "10:00") == 30        # hora feliz del 50 % sigue (sin franja)
    assert horarios.precio_turno_de(lun, "18:00") == 100       # franja punta, sin luz (antes de 18:30)
    assert horarios.precio_turno_de(lun, "19:00") == 110       # punta + luz
    assert horarios.precio_turno_de(lun, "19:00", 20) == 90    # promo puntual sobre la franja + luz
    sab = reglas.cancha_del_dia(c, _proximo(5))
    assert horarios.precio_turno_de(sab, "08:00") == 90        # por turno, la franja anula la hora feliz


def test_madrugada_usa_la_franja_del_dia_siguiente():
    c = {**LIMA, "hora_apertura": "18:00", "hora_cierre": "02:00", "descuento_valle": 0,
         "reglas_reserva": {"franjas": [{"dias": ["sab"], "desde": "00:00", "hasta": "03:00",
                                         "precio_hora": 200}]}}
    vie = reglas.cancha_del_dia(c, _proximo(4))
    assert horarios.precio_turno_de(vie, "01:00") == 200   # 01:00 del viernes = sábado de madrugada
    assert horarios.precio_turno_de(vie, "20:00") == 60


# ── ventana y bloque ─────────────────────────────────────────────────────────

def test_anticipacion_minima_y_maxima():
    c = {**LIMA, "reglas_reserva": {"anticipacion_min_horas": 3, "anticipacion_max_dias": 7}}
    ahora = datetime(2026, 11, 2, 10, 0)
    assert reglas.validar_inicio(c, "2026-11-02", "12:00", ahora) == "anticipacion_minima"
    assert reglas.validar_inicio(c, "2026-11-02", "13:00", ahora) == ""
    assert reglas.validar_inicio(c, "2026-11-10", "09:00", ahora) == "anticipacion_maxima"
    assert reglas.validar_bloque({**LIMA, "reglas_reserva": {"min_turnos": 2}}, 1) == "min_turnos"
    assert reglas.validar_bloque({**LIMA, "reglas_reserva": {"max_turnos": 2}}, 3) == "max_turnos"
    assert reglas.validar_bloque(LIMA, 9) == ""


def test_cancelacion_del_club_reemplaza_la_global():
    assert reglas.cancelacion_horas(LIMA, 6) == 6
    assert reglas.cancelacion_horas({**LIMA, "reglas_reserva": {"cancelacion_horas": 24}}, 6) == 24
    assert reglas.cancelacion_horas({**LIMA, "reglas_reserva": {"cancelacion_horas": 0}}, 6) == 0


# ── espejo con el APK: mismos casos en Dart ──────────────────────────────────

def test_casos_compartidos_con_el_apk():
    with open(CASOS, encoding="utf-8") as f:
        casos = json.load(f)
    assert len(casos) >= 8
    for caso in casos:
        c = {**LIMA, **caso.get("cancha", {}), "reglas_reserva": caso["reglas"]}
        cd = reglas.cancha_del_dia(c, caso["fecha"])
        if "slots" in caso:
            assert horarios.slots_de(cd) == caso["slots"], caso["nombre"]
        for hora, precio in (caso.get("precios") or {}).items():
            assert horarios.precio_turno_de(cd, hora) == precio, (caso["nombre"], hora)


# ── integración web ──────────────────────────────────────────────────────────

def test_disponibilidad_web_respeta_dia_cerrado_y_franja(db):
    dom, sab = _proximo(6), _proximo(5)
    db.canchas["c_lima"]["reglas_reserva"] = {
        "horario_semana": {"dom": None},
        "franjas": [{"dias": ["sab"], "desde": "07:00", "hasta": "23:59", "precio_hora": 80}],
        "cancelacion_horas": 24}
    j = client.get(f"/web/disponibilidad/c_lima?fecha={dom}").json()
    assert j["ok"] and j["slots"] == [] and j["cerrado"] == "cerrado"
    j = client.get(f"/web/disponibilidad/c_lima?fecha={sab}").json()
    assert {s["precio"] for s in j["slots"]} == {80}
    assert j["politica"]["cancelacion_horas"] == 24


def test_asegurar_web_valida_turnos_minimos(db):
    sab = _proximo(5)
    db.canchas["c_lima"]["reglas_reserva"] = {"min_turnos": 2}
    base = {"cancha_id": "c_lima", "nombre": "Ana Pérez", "email": "ana@x.com", "celular": "987654321"}
    r = client.post("/web/asegurar", json={**base, "horas": [{"fecha": sab, "hora": "10:00"}]}).json()
    assert r == {"ok": False, "error": "min_turnos"}
    r = client.post("/web/asegurar", json={**base, "horas": [{"fecha": sab, "hora": "10:00"},
                                                             {"fecha": sab, "hora": "11:00"}]}).json()
    assert r["ok"], r


def test_asegurar_web_tope_de_reservas_por_dia(db):
    sab = _proximo(5)
    db.canchas["c_lima"]["reglas_reserva"] = {"max_reservas_dia_jugador": 1}
    base = {"cancha_id": "c_lima", "nombre": "Ana Pérez", "email": "ana@x.com", "celular": "987654321"}
    assert client.post("/web/asegurar", json={**base, "horas": [{"fecha": sab, "hora": "10:00"}]}).json()["ok"]
    # Un apartado sin pagar no cuenta (vence solo); una reserva confirmada sí.
    assert client.post("/web/asegurar", json={**base, "horas": [{"fecha": sab, "hora": "12:00"}]}).json()["ok"]
    for r in db.reservas.values():
        r.update(estado="confirmada", pagado=True)
    r = client.post("/web/asegurar", json={**base, "horas": [{"fecha": sab, "hora": "15:00"}]}).json()
    assert r == {"ok": False, "error": "tope_reservas_dia"}


# ── endpoints del dueño (identidad verificada, nunca un correo en el cuerpo) ──

def _token_de(monkeypatch, mapa: dict):
    from pagos import router as pr
    monkeypatch.setattr(pr, "_email_de_token", lambda t: mapa.get(t))


def _con_columna(monkeypatch, db):
    from web import datos as _d
    monkeypatch.setattr(_d, "col_reglas_disponible", lambda: True)

    def guardar(ids, dueno, r):
        n = 0
        for cid in ids:
            c = db.canchas.get(cid)
            if c and c["dueno"].lower() == dueno.lower():
                c["reglas_reserva"] = r
                n += 1
        return n
    monkeypatch.setattr(_d, "guardar_reglas", guardar)


def test_reglas_exigen_sesion_y_ser_el_dueno(db, monkeypatch):
    _con_columna(monkeypatch, db)
    _token_de(monkeypatch, {"tok-dueno": "dueno@x.com", "tok-otro": "otro@x.com"})
    body = {"cancha_ids": ["c_lima"], "reglas": {"cancelacion_horas": 24}}
    assert client.put("/reservas/reglas", json=body).status_code == 401
    assert client.put("/reservas/reglas", json=body, headers={"X-User-Token": "falso"}).status_code == 401
    assert client.put("/reservas/reglas", json=body, headers={"X-User-Token": "tok-otro"}).status_code == 403
    assert client.get("/reservas/reglas/c_lima", headers={"X-User-Token": "tok-otro"}).status_code == 403
    r = client.put("/reservas/reglas", json=body, headers={"X-User-Token": "tok-dueno"})
    assert r.status_code == 200 and r.json()["reglas"] == {"cancelacion_horas": 24.0}
    j = client.get("/reservas/reglas/c_lima", headers={"X-User-Token": "tok-dueno"}).json()
    assert j["reglas"]["cancelacion_horas"] == 24.0 and j["base"]["hora_apertura"] == "07:00"
    pol = client.get("/reservas/politica/c_lima").json()
    assert pol["cancelacion_horas"] == 24.0


def test_reglas_varias_canchas_todas_deben_ser_suyas(db, monkeypatch):
    _con_columna(monkeypatch, db)
    _token_de(monkeypatch, {"tok-dueno": "dueno@x.com"})
    db.canchas["c_ajena"] = {**LIMA, "id": "c_ajena", "dueno": "otro@x.com"}
    r = client.put("/reservas/reglas", json={"cancha_ids": ["c_lima", "c_ajena"], "reglas": {"min_turnos": 2}},
                   headers={"X-User-Token": "tok-dueno"})
    assert r.status_code == 403
    assert "reglas_reserva" not in db.canchas["c_lima"] or not db.canchas["c_lima"]["reglas_reserva"]


def test_reglas_sin_columna_responde_503(db, monkeypatch):
    from web import datos as _d
    monkeypatch.setattr(_d, "col_reglas_disponible", lambda: False)
    _token_de(monkeypatch, {"tok-dueno": "dueno@x.com"})
    r = client.put("/reservas/reglas", json={"cancha_ids": ["c_lima"], "reglas": {}},
                   headers={"X-User-Token": "tok-dueno"})
    assert r.status_code == 503


# ── A1: deportes activables desde la torre ───────────────────────────────────

def test_deportes_activos_configurables_en_la_torre(monkeypatch):
    from db.store import stores
    j = client.get("/config/canal").json()
    assert j["deportes_activos"] == ["futbol", "tenis", "pickleball", "voley", "basquet"]
    monkeypatch.setitem(stores.config, "deportes_activos", "padel, futbol,xxx,padel")
    assert client.get("/config/canal").json()["deportes_activos"] == ["padel", "futbol"]
    monkeypatch.setitem(stores.config, "deportes_activos", "nada")
    assert client.get("/config/canal").json()["deportes_activos"] == ["futbol"]
