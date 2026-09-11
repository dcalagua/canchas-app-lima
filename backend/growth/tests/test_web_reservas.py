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
PEND = {**LIMA, "id": "c_pend", "nombre": "Loza Pendiente", "verificada": False, "dueno": ""}


class FakeDB:
    def __init__(self):
        self.canchas = {c["id"]: c for c in (LIMA, GYE, NOCHE, PEND)}
        self.reservas: dict[str, dict] = {}
        self.bloqueos: set = set()
        self.desc: dict = {}

    def canchas_publicas(self):
        return sorted(self.canchas.values(), key=lambda c: not (c["verificada"] and c["dueno"]))

    def canchas_verificadas(self):
        return [c for c in self.canchas.values() if c["verificada"] and c["dueno"]]

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
    for fn in ("canchas_publicas", "canchas_verificadas", "cancha", "ocupados", "descuentos", "liberar_holds_vencidos",
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
    # El último turno EMPIEZA a la hora de cierre (decisión del director, sep-2026).
    assert horarios.slots("07:00", "23:00", 60)[-1] == "23:00"     # 23:00–00:00
    assert horarios.slots("07:00", "23:00", 90)[-1] == "22:00"     # 22:00–23:30 (23:30 ya pasa del cierre)
    assert horarios.slots("07:00", "00:00", 60)[-1] == "00:00"     # hasta medianoche → 00:00–01:00 (madrugada)
    assert horarios.slots("18:00", "02:00", 60) == ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00", "02:00"]
    assert len(horarios.slots("00:00", "00:00", 60)) == 24         # 24 h, sin repetir medianoche
    assert horarios.fecha_real("2026-09-11", "07:00", "00:00", "00:00") == "2026-09-12"  # el turno de las 00:00 es del día siguiente
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
    assert "S/ 60" in r.text and "$ 10" in r.text and "Mostrar mapa" in r.text
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


def test_raiz_es_el_explorador_tipo_airbnb(db):
    """La raíz del dominio ES el explorador (buscador en pastilla, categorías,
    tarjetas con foto/corazón, "Mostrar mapa") y debajo van las secciones de
    marca/comercio que revisan Culqi e INDECOPI (servicios con precio y
    botón, términos, cancelaciones, Libro de Reclamaciones integrado)."""
    home = client.get("/").text
    for t in ("id='sQ'", "id='sF'", "id='sH'", "id='panCuando'", "id='panHora'", "class='cat sel'", "Cancha Central", "class='corazon'",
              "Mostrar mapa", 'id="servicios"', "Servicios y precios", "/canchas?deporte=futbol",
              'id="terminos"', 'id="devoluciones"', 'id="reclamaciones"', "lr-form", "/reclamaciones",
              'href="/canchas"', 'href="/legal/terminos"', 'href="/legal/privacidad"',
              "20602517986", "contacto@ebim.pe", ".marca .prods{"):
        assert t in home, t
    # El CSS de la home vieja va anidado bajo .marca: no pisa el sistema de diseño.
    assert "\n  .card{" not in home and ".marca .card{" in home
    # Categoría y fecha desde el buscador: el deporte lo filtra el servidor y la
    # fecha viaja a la ficha y preselecciona el día.
    f = _manana()
    r = client.get(f"/?deporte=futbol&fecha={f}").text
    assert "class='cat sel' href='/canchas?deporte=futbol'" in r and f"/reservar/c_gye?fecha={f}" in r
    r = client.get("/?deporte=tenis").text
    assert "Cancha Central" not in r and "Todavía no hay canchas de este deporte" in r
    ficha = client.get(f"/reservar/c_lima?fecha={f}").text
    assert f'"fecha": "{f}"' in ficha
    assert '"fecha": ""' in client.get("/reservar/c_lima?fecha=2020-01-01").text


def test_buscador_por_fecha_y_hora_como_airbnb(db, monkeypatch):
    fake = db
    """"Cuándo" abre un calendario y "Hora" un panel de horas; con ambos, el
    servidor dice qué canchas tienen un turno LIBRE que cubra esa hora
    (`/web/libres`, una consulta para todas) y la ficha preselecciona el
    turno (`?hora=`)."""
    from web import datos as _d
    f = _manana()
    fake.canchas["c_lima"]["amenidades"] = ["estacionamiento", "vestuarios"]
    home = client.get(f"/?fecha={f}&hora=19:00").text
    assert f'"fecha": "{f}"' in home and '"hora": "19:00"' in home
    assert "data-ap='" in home and "data-paso='" in home and "data-hora='19:00'" in home
    # Modal de filtros tipo Airbnb (amenidades reales de las canchas, tipo, precio) + chips rápidos.
    for t in ("id='modalFiltros'", "id='btnFiltros'", "Recomendado para ti", "Rango de precios", "id='rMin'", "id='mostrarFiltros'",
              "class='tile' data-am='estacionamiento'", "class='chip qam' data-am='estacionamiento'", "data-am='estacionamiento vestuarios'",
              "data-mon='S/'", "Limpiar filtros"):
        assert t in home, t
    assert '"hora": ""' in client.get("/?hora=25:99").text
    # Sin reservas: la 19:00 está libre en todas las reservables.
    monkeypatch.setattr(_d, "ocupados_varias", lambda ids, fechas: {})
    j = client.get(f"/web/libres?fecha={f}&hora=19:00").json()
    assert j["ok"] and j["libres"]["c_lima"] is True and "c_gye" in j["libres"]
    # Ocupada a las 19:00 → ya no está libre; a las 20:00 sí. La 03:00 no
    # cae en ningún turno (cierra 23:00) → no libre. La 23:00 SÍ (último turno 23:00–00:00).
    monkeypatch.setattr(_d, "ocupados_varias", lambda ids, fechas: {"c_lima": {(f, "19:00")}})
    j = client.get(f"/web/libres?fecha={f}&hora=19:00").json()
    assert j["libres"]["c_lima"] is False
    assert client.get(f"/web/libres?fecha={f}&hora=20:00").json()["libres"]["c_lima"] is True
    assert client.get(f"/web/libres?fecha={f}&hora=03:00").json()["libres"]["c_lima"] is False
    assert client.get(f"/web/libres?fecha={f}&hora=23:00").json()["libres"]["c_lima"] is True
    assert client.get(f"/web/libres?fecha={f}&hora=23:30").json()["libres"]["c_lima"] is True
    # Hora dentro de un turno de 90 min (19:30 cae en el turno 19:00-20:30).
    fake.canchas["c_lima"]["duracion_slot_min"] = 90
    assert client.get(f"/web/libres?fecha={f}&hora=19:30").json()["libres"]["c_lima"] is False
    fake.canchas["c_lima"]["duracion_slot_min"] = 60
    assert client.get("/web/libres?fecha=2020-01-01&hora=19:00").json()["ok"] is False
    assert client.get(f"/web/libres?fecha={f}&hora=x").json()["ok"] is False
    # La ficha recibe la hora buscada y la valida.
    assert '"hora": "19:00"' in client.get(f"/reservar/c_lima?fecha={f}&hora=19:00").text
    assert '"hora": ""' in client.get(f"/reservar/c_lima?fecha={f}&hora=99:00").text


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
    assert "Pichang" in html and "DM Sans" in html  # identidad del app
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


def test_no_verificadas_salen_con_reservar_en_la_app(db):
    html = client.get("/canchas").text
    assert "Loza Pendiente" in html and "Reservar en la app" in html and "Aún sin verificar" in html
    # Las reservables van primero; la pendiente no tiene sello.
    assert html.index("Cancha Central") < html.index("Loza Pendiente")
    ficha = client.get("/reservar/c_pend").text
    assert "proceso de verificación" in ficha and "checkout.culqi.com" not in ficha and "play.google.com" in ficha
    r = _asegurar(_manana(), horas=("15:00",), extras=(), cancha="c_pend")
    assert r["ok"] is False and r["error"] == "no_verificada"


def test_primera_foto_siempre_como_el_app(db, monkeypatch):
    """Regla del director: la web muestra SIEMPRE la primera foto, como el app.
    Las canchas sembradas desde el app no guardan las fotos de Google; la web
    las resuelve en vivo por nombre + cercanía con la misma Edge Function."""
    from web import descubrir as d
    d.limpiar_cache()
    llamadas = []
    crudos = [
        {"id": "P1", "displayName": {"text": "Sabor Golazo Futbol 7"}, "types": ["sports_complex"],
         "location": {"latitude": -12.0901, "longitude": -77.0001}, "fotos": ["https://f/golazo1.jpg", "https://f/golazo2.jpg"]},
        {"id": "P2", "displayName": {"text": "Bodega Doña Rosa"}, "types": ["store"],
         "location": {"latitude": -12.0900, "longitude": -77.0000}, "fotos": ["https://f/bodega.jpg"]},
        {"id": "P3", "displayName": {"text": "Lejos FC"}, "types": [],
         "location": {"latitude": -12.20, "longitude": -77.10}, "fotos": ["https://f/lejos.jpg"]},
    ]
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: (llamadas.append(a) or crudos))
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    # Coincidencia por nombre/club gana sobre el más cercano (la bodega).
    assert d._elegir_lugar(crudos, "Cancha 1", "Sabor Golazo - Futbol 7", -12.09, -77.0) == ["https://f/golazo1.jpg", "https://f/golazo2.jpg"]
    # Sin coincidencia de nombre: el lugar con fotos más cercano dentro del radio.
    assert d._elegir_lugar(crudos, "Loza", "", -12.09, -77.0) == ["https://f/bodega.jpg"]
    # Fuera del radio → nada.
    assert d._elegir_lugar(crudos[2:], "Loza", "", -12.09, -77.0) == []
    # Endpoint: cancha registrada sin fotos → fotos de Google; con fotos propias → las propias.
    db.canchas["c_lima"]["club"] = "Sabor Golazo - Futbol 7"
    j = client.get("/web/foto?id=c_lima").json()
    assert j["ok"] and j["origen"] == "google" and j["fotos"][0] == "https://f/golazo1.jpg"
    assert len(llamadas) == 1 and llamadas[0][2] == d.RADIO_FOTO_M and llamadas[0][4] is True
    client.get("/web/foto?id=c_lima")
    assert len(llamadas) == 1  # caché por lugar
    db.canchas["c_gye"]["fotos"] = ["https://propia/1.jpg"]
    j = client.get("/web/foto?id=c_gye").json()
    assert j["origen"] == "propias" and j["fotos"] == ["https://propia/1.jpg"]
    # Lugar descubierto (gp_…): por nombre + coordenadas.
    j = client.get("/web/foto?id=gp_P1&nombre=Sabor%20Golazo&lat=-12.09&lng=-77.0").json()
    assert j["fotos"][0] == "https://f/golazo1.jpg"
    assert client.get("/web/foto").json()["ok"] is False
    # La portada marca las tarjetas sin foto para que el navegador pida la primera
    # foto, y la ficha hace lo mismo con su galería.
    html = client.get("/").text
    assert "data-buscar='1'" in html and "/web/foto?" in html and "data-club='Sabor Golazo - Futbol 7'" in html
    ficha = client.get("/reservar/c_lima").text
    assert "id='galeria'" in ficha and "/web/foto?id=c_lima" in ficha
    # Sin Edge Function → [] sin romper.
    d.limpiar_cache()
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("red")))
    assert client.get("/web/foto?id=c_lima").json()["fotos"] == []
    # RESPALDO directo con PLACES_API_KEY: la Edge no trae fotos → el backend
    # habla con Google (Place Details por place_id; Text Search por nombre).
    d.limpiar_cache()
    monkeypatch.setattr(config, "PLACES_API_KEY", "k")
    pedidas = []

    def fake_http(url, headers, body=None, timeout=12):
        pedidas.append(url)
        if "/media" in url:
            return {"photoUri": "https://lh3/" + url.split("/photos/")[1].split("/")[0]}
        if url.endswith("/places/P1"):
            return {"photos": [{"name": "places/P1/photos/a"}, {"name": "places/P1/photos/b"}]}
        if url.endswith("searchText"):
            assert body["textQuery"] == "Sabor Golazo" and body["locationBias"]["circle"]["radius"] == 300
            return {"places": [{"id": "X", "location": {"latitude": -12.0901, "longitude": -77.0001},
                                "photos": [{"name": "places/X/photos/z"}]}]}
        raise AssertionError(url)
    monkeypatch.setattr(d, "_http_json", fake_http)
    assert client.get("/web/foto?id=gp_P1&nombre=Lo%20que%20sea&lat=-12.09&lng=-77.0").json()["fotos"] == ["https://lh3/a", "https://lh3/b"]
    assert client.get("/web/foto?id=c_lima").json()["fotos"] == ["https://lh3/z"]
    assert any(u.endswith("/places/P1") for u in pedidas) and any(u.endswith("searchText") for u in pedidas)
    # CUOTA: un 429 de Google pausa las resoluciones 60 s y NO cachea el vacío.
    import urllib.error
    d.limpiar_cache()
    def http_429(url, headers, body=None, timeout=12):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(d, "_http_json", http_429)
    assert client.get("/web/foto?id=gp_P9&nombre=X&lat=-12.09&lng=-77.0").json()["fotos"] == []
    assert d._en_pausa()
    monkeypatch.setattr(d, "_http_json", fake_http)
    assert client.get("/web/foto?id=gp_P1&nombre=X&lat=-12.09&lng=-77.0").json()["fotos"] == []  # en pausa
    monkeypatch.setattr(d, "_pausa_hasta", 0.0)
    assert client.get("/web/foto?id=gp_P1&nombre=X&lat=-12.09&lng=-77.0").json()["fotos"] == ["https://lh3/a", "https://lh3/b"]
    # COSECHA en Supabase: lo guardado y vigente se usa sin tocar Google; lo
    # resuelto se guarda (clave = place_id, o cancha:<id> para registradas).
    d.limpiar_cache()
    guardadas = {}
    monkeypatch.setattr(datos, "guardar_fotos_lugar", lambda clave, nombre, lat, lng, fotos: guardadas.__setitem__(clave, fotos) or True)
    monkeypatch.setattr(datos, "leer_fotos_lugar", lambda clave: (["https://db/vieja.jpg"], True) if clave == "P7" else None)
    pedidas.clear()
    assert client.get("/web/foto?id=gp_P7&nombre=X&lat=-12.09&lng=-77.0").json()["fotos"] == ["https://db/vieja.jpg"]
    assert pedidas == []  # ni una llamada a Google
    assert client.get("/web/foto?id=gp_P1&nombre=X&lat=-12.09&lng=-77.0").json()["fotos"] == ["https://lh3/a", "https://lh3/b"]
    assert guardadas["P1"] == ["https://lh3/a", "https://lh3/b"]
    assert client.get("/web/foto?id=c_lima").json()["fotos"] == ["https://lh3/z"] and guardadas["cancha:c_lima"] == ["https://lh3/z"]
    # Vencida (>30 días) → se refresca con Google; si Google falla, vale la vieja.
    d.limpiar_cache()
    monkeypatch.setattr(datos, "leer_fotos_lugar", lambda clave: (["https://db/vieja.jpg"], False))
    monkeypatch.setattr(d, "_http_json", http_429)
    monkeypatch.setattr(d, "_pausa_hasta", 0.0)
    assert client.get("/web/foto?id=gp_P8&nombre=X&lat=-12.09&lng=-77.0").json()["fotos"] == ["https://db/vieja.jpg"]
    monkeypatch.setattr(d, "_http_json", fake_http)
    monkeypatch.setattr(datos, "leer_fotos_lugar", lambda clave: None)
    # Dedup de descubiertas también por CLUB: "Fútbol 1" del club "Sabor Golazo -
    # Futbol 7" ES el lugar "Sabor Golazo" de Google → no sale duplicado.
    d.limpiar_cache()
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: [
        {"id": "G1", "displayName": {"text": "Sabor Golazo Futbol 7"}, "types": ["sports_complex"],
         "location": {"latitude": -12.0901, "longitude": -77.0001}}])
    assert [c["nombre"] for c in d.descubrir_cerca(-12.09, -77.0, registradas=[])] == ["Sabor Golazo Futbol 7"]
    d.limpiar_cache()
    assert d.descubrir_cerca(-12.09, -77.0, registradas=[{"nombre": "Fútbol 1", "club": "Sabor Golazo - Futbol 7",
                                                            "lat": -12.0901, "lng": -77.0001}]) == []


def test_descubrir_canchas_de_google_como_el_apk(db, monkeypatch):
    from web import descubrir as d
    d.limpiar_cache()
    llamadas = []
    crudos = [
        {"id": "A1", "displayName": {"text": "Complejo Deportivo San Borja"}, "types": ["sports_complex"],
         "location": {"latitude": -12.10, "longitude": -77.00}, "formattedAddress": "Av. X 100"},
        {"id": "A2", "displayName": {"text": "Tenis Americanos"}, "types": ["shoe_store"],
         "location": {"latitude": -12.10, "longitude": -77.00}},               # zapatería → fuera
        {"id": "A3", "displayName": {"text": "Burn Fitness Center"}, "types": ["gym"],
         "location": {"latitude": -12.10, "longitude": -77.00}},               # gimnasio → fuera
        {"id": "A4", "displayName": {"text": "Cancha Central"}, "types": [],
         "location": {"latitude": -12.0901, "longitude": -77.0001}},          # ya registrada → fuera
        {"id": "A5", "displayName": {"text": "Club de Tenis Las Terrazas"}, "types": ["sports_club"],
         "location": {"latitude": -12.12, "longitude": -77.02}, "fotos": ["https://f/1.jpg"]},
    ]
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: (llamadas.append(a) or crudos))
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    j = client.get("/web/descubrir?lat=-12.09&lng=-77.0").json()
    assert j["ok"] and j["region"] == "PE"
    nombres = [c["nombre"] for c in j["canchas"]]
    assert nombres == ["Complejo Deportivo San Borja", "Club de Tenis Las Terrazas"]
    assert j["canchas"][0]["deporte"] == "futbol" and j["canchas"][1]["deporte"] == "tenis"
    assert j["canchas"][0]["id"] == "gp_A1" and j["canchas"][0]["km"] < 2
    assert j["canchas"][1]["fotos"] == ["https://f/1.jpg"] and j["canchas"][1]["deporte_nombre"] == "Tenis"
    # Caché por zona: la segunda consulta de la misma celda no vuelve a Google.
    client.get("/web/descubrir?lat=-12.089&lng=-76.999")
    assert len(llamadas) == 1
    # El explorador trae la sección y el JS que la llena.
    html = client.get("/canchas").text
    assert "id='descubiertas'" in html and "/web/descubrir" in html and "Reclámala" in html
    # Heurística directa.
    assert d.deporte_de("Pista de skate Miraflores", []) is None
    assert d.deporte_de("Campo Deportivo Edu Jr", []) == "futbol"
    assert d.deporte_de("EquiBolivia", ["sports_activity_location"]) is None
    assert d.deporte_de("Cancha de Pádel Sur", []) == "padel"
    # Sin Supabase configurado → vacío, sin romper.
    d.limpiar_cache()
    monkeypatch.setattr(d, "_llamar_edge", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("red")))
    assert client.get("/web/descubrir?lat=-12.09&lng=-77.0").json()["canchas"] == []


def test_reservar_exige_login_con_google_como_el_app(db, monkeypatch):
    """Decisión del director (sep-2026): en la web también se inicia sesión con
    Gmail antes de reservar, igual que en el app. Con GOOGLE_WEB_CLIENT_ID la
    ficha muestra el botón de Google, /web/asegurar y /web/pagar exigen la
    cookie firmada y la reserva queda a nombre del correo de Google."""
    from web import sesion
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    # Sin sesión: la ficha pide iniciar sesión y reservar se rechaza.
    cli = TestClient(app, base_url="https://testserver")
    html = cli.get("/reservar/c_lima").text
    assert "Inicia sesión con Google para reservar" in html and "accounts.google.com/gsi/client" in html
    assert "data-client_id='cid-web'" in html and '"login": true' in html and "Iniciar sesión" in html
    f = _manana()
    body = {"cancha_id": "c_lima", "horas": [{"fecha": f, "hora": "19:00"}], "extras": [],
            "nombre": "Ana", "celular": "999888777", "email": "otra@x.com"}
    assert cli.post("/web/asegurar", json=body).json()["error"] == "sesion_requerida"
    assert cli.get("/entrar?volver=/reservar/c_lima").status_code == 200
    # Token inválido → sin sesión. Token válido (tokeninfo simulado) → cookie.
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "Ana@Gmail.com", "email_verified": "true",
                                                         "aud": "otro-cid", "name": "Ana Pérez", "exp": "9999999999"})
    assert cli.post("/web/sesion", json={"credential": "x"}).json()["error"] == "token_invalido"
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "Ana@Gmail.com", "email_verified": "true",
                                                         "aud": "cid-web", "name": "Ana Pérez",
                                                         "picture": "https://lh3/ana.jpg", "exp": "9999999999"})
    r = cli.post("/web/sesion", json={"credential": "tok"})
    assert r.json() == {"ok": True, "email": "ana@gmail.com", "nombre": "Ana Pérez", "foto": "https://lh3/ana.jpg"}
    assert sesion.COOKIE in r.cookies and sesion.leer(r.cookies[sesion.COOKIE])["email"] == "ana@gmail.com"
    assert sesion.leer(r.cookies[sesion.COOKIE][:-3] + "abc") is None  # firma alterada
    # Con sesión: la ficha muestra "Reservando como" y la reserva es del correo de Google.
    html = cli.get("/reservar/c_lima").text
    assert "Ana Pérez" in html and "ana@gmail.com" in html and "Cambiar cuenta" in html
    assert cli.get("/entrar?volver=/x", follow_redirects=False).status_code == 302
    r = cli.post("/web/asegurar", json=body).json()
    assert r["ok"]
    fila = db.reservas[r["ids"][0]]
    assert fila["usuario"] == "ana@gmail.com" and fila["jugador"] == "Ana"
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": True, "charge_id": "chr_g", "email": kw["email"]})
    import pagos.router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    p = cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "tkn", "medio": "yape",
                                     "email": "otra@x.com"}).json()
    assert p["ok"] and db.reservas[r["ids"][0]]["pagado"]
    # Salir: sin cookie vuelve a exigir sesión.
    cli.post("/web/salir")
    assert cli.post("/web/asegurar", json=body).json()["error"] == "sesion_requerida"
    # Sin client id configurado, la web sigue con el formulario de invitado.
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "")
    assert "id='loginBox'" not in client.get("/reservar/c_lima").text and '"login": false' in client.get("/reservar/c_lima").text
