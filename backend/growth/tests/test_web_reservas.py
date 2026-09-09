"""RESERVA WEB (fase 1): catálogo, disponibilidad, hold, pago Culqi y
comprobante, con la base de Supabase SIMULADA en memoria (mismas reglas que el
APK: UNIQUE por slot, no-show no ocupa, hora feliz, madrugada al día siguiente)."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import culqi  # noqa: E402
from web import datos, horarios  # noqa: E402
from web import router as web  # noqa: E402

client = TestClient(app)

LIMA = {"id": "c_lima", "nombre": "Cancha Central", "club": "Club Raqueta", "distrito": "lima_moderna",
        "barrio": "San Borja", "deporte": "futbol", "deportes": ["futbol"], "precio_hora": 60.0,
        "lat": -12.09, "lng": -77.0, "direccion": "Av. Aviación 123", "foto_url": "", "fotos": [],
        "dueno": "dueno@x.com", "verificada": True, "registrada": True, "eliminada": False,
        "hora_apertura": "07:00", "hora_cierre": "23:00", "duracion_slot_min": 60, "moneda": "S/",
        "servicios_extra": [{"clave": "arbitro", "precio": 30}], "descuento_valle": 50,
        "valle_desde": "07:00", "valle_hasta": "12:00", "sena_pct": 0, "superficie": "grass",
        "amenidades": []}
GYE = {**LIMA, "id": "c_gye", "nombre": "Cancha Guayaquil", "club": "Club Sur", "lat": -2.17,
       "lng": -79.92, "moneda": "$", "precio_hora": 10.0, "descuento_valle": 0}
NOCHE = {**LIMA, "id": "c_noche", "nombre": "Nocturna", "hora_apertura": "18:00",
         "hora_cierre": "02:00", "descuento_valle": 0}


class FakeDB:
    def __init__(self):
        self.canchas = {c["id"]: c for c in (LIMA, GYE, NOCHE)}
        self.reservas: dict[str, dict] = {}
        self.bloqueos: set = set()
        self.desc: dict = {}

    def canchas_verificadas(self):
        return [c for c in self.canchas.values() if c["verificada"]]

    def cancha(self, cid):
        return self.canchas.get(cid)

    def ocupados(self, cid, fechas):
        out = {(r["fecha"], r["hora_inicio"]) for r in self.reservas.values()
               if r["cancha_id"] == cid and r["fecha"] in fechas and r["estado"] != "noShow"}
        out |= {(f, h) for (c, f, h) in self.bloqueos if c == cid and f in fechas}
        return out

    def descuentos(self, cid, fechas):
        return {(f, h): p for (c, f, h), p in self.desc.items() if c == cid and f in fechas}

    def liberar_holds_vencidos(self, cid):
        return 0

    def insertar_reservas(self, filas):
        claves = {(r["cancha_id"], r["fecha"], r["hora_inicio"]) for r in self.reservas.values()}
        for f in filas:
            if (f["cancha_id"], f["fecha"], f["hora_inicio"]) in claves:
                return "ocupado"
        for f in filas:
            self.reservas[f["id"]] = dict(f)
        return ""

    def confirmar_reservas(self, ids, medio):
        for i in ids:
            if i in self.reservas:
                self.reservas[i].update(estado="confirmada", pagado=True, medio_pago=medio)
        return True

    def borrar_reservas(self, ids):
        for i in ids:
            if self.reservas.get(i, {}).get("estado") == "nueva":
                self.reservas.pop(i)
        return True

    def reservas_de(self, ids):
        return sorted([dict(self.reservas[i]) for i in ids if i in self.reservas],
                      key=lambda r: (r["fecha"], r["hora_inicio"]))

    def reservas_por_grupo(self, g):
        return sorted([dict(r) for r in self.reservas.values() if r["grupo_reserva_id"] == g],
                      key=lambda r: (r["fecha"], r["hora_inicio"]))


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    for fn in ("canchas_verificadas", "cancha", "ocupados", "descuentos", "liberar_holds_vencidos",
               "insertar_reservas", "confirmar_reservas", "borrar_reservas", "reservas_de",
               "reservas_por_grupo"):
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    return fake


def _manana(cancha=LIMA):
    d_min, d_max = web._fechas_validas(web._pais_de(cancha))
    from datetime import date, timedelta
    return (date.fromisoformat(d_min) + timedelta(days=1)).isoformat()


# ── lógica pura ──────────────────────────────────────────────────────────────

def test_horarios_espejo_del_apk():
    assert horarios.slots("07:00", "23:00", 60)[:2] == ["07:00", "08:00"]
    assert horarios.slots("07:00", "23:00", 60)[-1] == "22:00"
    assert horarios.slots("07:00", "23:00", 90)[-1] == "20:30"     # cabe completo antes del cierre
    assert horarios.slots("07:00", "00:00", 60)[-1] == "23:00"     # hasta medianoche
    assert horarios.slots("18:00", "02:00", 60) == ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00"]
    assert len(horarios.slots("00:00", "00:00", 60)) == 24         # 24 h
    assert horarios.hora_fin("23:00", 60) == "00:00"
    assert horarios.fecha_real("2026-09-10", "18:00", "02:00", "01:00") == "2026-09-11"
    assert horarios.fecha_real("2026-09-10", "18:00", "02:00", "22:00") == "2026-09-10"
    assert horarios.es_valle("08:00", "07:00", "12:00") and not horarios.es_valle("12:00", "07:00", "12:00")
    assert horarios.es_valle("23:30", "22:00", "06:00") and horarios.es_valle("05:00", "22:00", "06:00")
    assert horarios.precio_hora_en(60, "08:00", 50, "07:00", "12:00") == 30
    assert horarios.precio_slot(60, 90) == 90 and horarios.precio_slot(60, 60, 10) == 54


# ── páginas ──────────────────────────────────────────────────────────────────

def test_catalogo_agrupa_por_pais_y_filtra(db):
    r = client.get("/canchas")
    assert r.status_code == 200
    assert "Perú" in r.text and "Ecuador" in r.text and "data-pais='PE'" in r.text
    assert "leaflet" in r.text and "Usar mi ubicación" in r.text and "data-lat=" in r.text
    assert "Cancha Central" in r.text and "Cancha Guayaquil" in r.text
    assert "S/ 60.00" in r.text and "$ 10.00" in r.text
    assert "/reservar/c_lima" in r.text
    r = client.get("/canchas?deporte=tenis")
    assert "Cancha Central" not in r.text


def test_reservar_peru_muestra_checkout_y_ecuador_manda_a_la_app(db):
    r = client.get("/reservar/c_lima")
    assert r.status_code == 200
    assert "checkout.culqi.com/js/v4" in r.text and "pk_test_x" in r.text
    assert "hora feliz" in r.text and "Árbitro" in r.text
    r = client.get("/reservar/c_gye")
    assert "checkout.culqi.com" not in r.text
    assert "Reserva desde la app" in r.text and "play.google.com" in r.text
    assert "Cancha no disponible" in client.get("/reservar/zzz").text


def test_disponibilidad_marca_ocupados_y_hora_feliz(db):
    f = _manana()
    db.reservas["r1"] = {"id": "r1", "cancha_id": "c_lima", "fecha": f, "hora_inicio": "20:00",
                         "estado": "confirmada", "grupo_reserva_id": ""}
    db.reservas["r2"] = {"id": "r2", "cancha_id": "c_lima", "fecha": f, "hora_inicio": "21:00",
                         "estado": "noShow", "grupo_reserva_id": ""}
    db.bloqueos.add(("c_lima", f, "19:00"))
    db.desc[("c_lima", f, "18:00")] = 20
    j = client.get(f"/web/disponibilidad/c_lima?fecha={f}").json()
    assert j["ok"] and j["moneda"] == "S/"
    por = {s["hora"]: s for s in j["slots"]}
    assert por["20:00"]["ocupado"] and por["19:00"]["ocupado"]
    assert not por["21:00"]["ocupado"]           # no-show no ocupa
    assert por["08:00"]["precio"] == 30 and por["08:00"]["valle"]   # hora feliz 50 %
    assert por["18:00"]["precio"] == 48          # descuento puntual 20 %
    assert por["15:00"]["precio"] == 60
    assert client.get("/web/disponibilidad/c_lima?fecha=2020-01-01").json()["ok"] is False


def test_madrugada_cae_al_dia_siguiente(db):
    f = _manana(NOCHE)
    j = client.get(f"/web/disponibilidad/c_noche?fecha={f}").json()
    por = {s["hora"]: s for s in j["slots"]}
    from datetime import date, timedelta
    assert por["01:00"]["fecha"] == (date.fromisoformat(f) + timedelta(days=1)).isoformat()
    assert por["22:00"]["fecha"] == f


# ── flujo completo ───────────────────────────────────────────────────────────

def _asegurar(f, horas=("15:00", "16:00"), extras=("arbitro",), cancha="c_lima"):
    return client.post("/web/asegurar", json={
        "cancha_id": cancha, "horas": [{"fecha": f, "hora": h} for h in horas],
        "extras": list(extras), "nombre": "Ana Pérez", "celular": "999888777",
        "email": "Ana@x.com"}).json()


def test_reserva_web_completa(db, monkeypatch):
    cargos, pushes = [], []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: (cargos.append(kw) or {"ok": True, "charge_id": "chr_1"}))
    import pagos.router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: pushes.append((a, k)))
    stores.saldos.pop("dueno@x.com", None)
    f = _manana()
    j = _asegurar(f)
    assert j["ok"] and len(j["ids"]) == 2 and j["grupo"].startswith("grp_web_")
    assert j["total"] == 60 + 60 + 30 and j["total_centimos"] == 15000
    # Mientras espera el pago, los slots ya figuran ocupados para otros.
    por = {s["hora"]: s for s in client.get(f"/web/disponibilidad/c_lima?fecha={f}").json()["slots"]}
    assert por["15:00"]["ocupado"] and por["16:00"]["ocupado"]
    assert db.reservas[j["ids"][0]]["estado"] == "nueva" and db.reservas[j["ids"][0]]["pagado"] is False
    assert db.reservas[j["ids"][0]]["usuario"] == "ana@x.com"
    assert db.reservas[j["ids"][0]]["extras"] == [{"clave": "arbitro", "precio": 30.0}]
    assert db.reservas[j["ids"][1]]["extras"] == []
    # Pago.
    p = client.post("/web/pagar", json={"ids": j["ids"], "firma": j["firma"], "token": "tkn_1",
                                        "medio": "yape", "email": "ana@x.com"}).json()
    assert p["ok"] and p["url"] == f"/reserva/{j['grupo']}"
    assert cargos[0]["monto_centimos"] == 15000 and cargos[0]["moneda"] == "PEN"
    for i in j["ids"]:
        r = db.reservas[i]
        assert r["estado"] == "confirmada" and r["pagado"] and r["medio_pago"] == "yape"
        assert r["traida_por_app"] and r["moneda"] == "S/" and r["jugador"] == "Ana Pérez"
    # Contabilidad: liquidación al dueño (por recibir) y push "Nueva reserva".
    liq = stores.pago_por_charge(j["ids"][0])
    assert liq is not None and liq.tipo in ("liquidacion_online", "liquidacion_full")
    assert liq.monto_centimos == 15000 and liq.moneda == "PEN"
    assert pushes and pushes[0][0][1] == "Nueva reserva 📅" and pushes[0][1].get("tipo") == "reserva"
    # Comprobante.
    r = client.get(p["url"])
    assert "Reserva confirmada" in r.text and "S/ 150.00" in r.text and "Ana Pérez" in r.text
    # Pagar de nuevo el mismo bloque no vuelve a cobrar.
    p2 = client.post("/web/pagar", json={"ids": j["ids"], "firma": j["firma"], "token": "tkn_2"}).json()
    assert p2["ok"] and len(cargos) == 1


def test_slot_tomado_y_cargo_rechazado(db, monkeypatch):
    f = _manana()
    db.reservas["r1"] = {"id": "r1", "cancha_id": "c_lima", "fecha": f, "hora_inicio": "15:00",
                         "estado": "confirmada", "grupo_reserva_id": ""}
    assert _asegurar(f, horas=("15:00",), extras=()).get("error") == "ocupado"
    assert _asegurar(f, horas=("03:00",), extras=()).get("error") == "hora_invalida"
    assert _asegurar(f, horas=("16:00",), extras=(), cancha="c_gye").get("error") == "pago_no_disponible"
    # Cargo rechazado → filas liberadas, nada cobrado.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "tarjeta_rechazada"})
    j = _asegurar(f, horas=("17:00",), extras=())
    assert j["ok"]
    p = client.post("/web/pagar", json={"ids": j["ids"], "firma": j["firma"], "token": "tkn_x"}).json()
    assert p["ok"] is False and p["error"] == "cargo_rechazado"
    assert j["ids"][0] not in db.reservas
    # Firma inválida → no toca nada.
    j2 = _asegurar(f, horas=("18:00",), extras=())
    assert client.post("/web/pagar", json={"ids": j2["ids"], "firma": "mala", "token": "t"}).json()["error"] == "firma"
    assert client.post("/web/liberar", json={"ids": j2["ids"], "firma": "mala"}).json()["ok"] is False
    assert client.post("/web/liberar", json={"ids": j2["ids"], "firma": j2["firma"]}).json()["ok"] is True
    assert j2["ids"][0] not in db.reservas


def test_sin_base_de_datos_todo_es_fail_safe(monkeypatch):
    from db import pg
    monkeypatch.setattr(pg, "habilitado", False)
    assert datos.canchas_verificadas() == [] and datos.cancha("x") is None
    assert datos.insertar_reservas([{"id": "a"}]) == "error"
    r = client.get("/canchas")
    assert r.status_code == 200 and "Todavía no hay canchas" in r.text
    assert "Cancha no disponible" in client.get("/reservar/x").text


def test_home_enlaza_al_catalogo():
    home = client.get("/").text
    assert 'href="/canchas"' in home and "/canchas?deporte=futbol" in home


def test_calendario_ics_y_acciones_del_comprobante(db, monkeypatch):
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": True, "charge_id": "chr_2"})
    import pagos.router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    f = _manana()
    j = _asegurar(f, horas=("19:00",), extras=())
    p = client.post("/web/pagar", json={"ids": j["ids"], "firma": j["firma"], "token": "tkn_9"}).json()
    assert p["ok"]
    ref = p["url"].rsplit("/", 1)[-1]
    html = client.get(p["url"]).text
    assert f"/reserva/{ref}.ics" in html and "Cómo llegar" in html and "wa.me/?text=" in html
    assert "Pichang" in html and "Montserrat" in html  # identidad del app
    ics = client.get(f"/reserva/{ref}.ics")
    assert ics.status_code == 200 and "text/calendar" in ics.headers["content-type"]
    assert "BEGIN:VEVENT" in ics.text and "Cancha Central" in ics.text
    assert "DTSTART:" in ics.text and "T000000Z" in ics.text  # 19:00 Lima = 00:00Z del día siguiente
    assert client.get("/reserva/zzz.ics").status_code == 404
    assert "Reserva no encontrada" in client.get("/reserva/zzz").text


def test_pagina_reservar_trae_tira_de_dias_y_resumen(db):
    html = client.get("/reservar/c_lima").text
    assert "Resumen de tu reserva" in html and 'id="dias"' in html.replace("'", '"')
    assert "Hoy" in html and "Mañana" in html and "application/ld+json" in html
    assert "/static/brand/logo_pin.png" in html
