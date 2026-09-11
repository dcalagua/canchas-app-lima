"""RESERVA WEB (fase 1): catálogo, disponibilidad, hold, pago Culqi y
comprobante, con la base de Supabase SIMULADA en memoria (mismas reglas que el
APK: UNIQUE por slot, no-show no ocupa, hora feliz, madrugada al día siguiente)."""

import os
import sys

import pytest
from datetime import datetime, timezone
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
        self.canchas = {c["id"]: dict(c) for c in (LIMA, GYE, NOCHE, PEND)}  # copias: un test no debe mutar las fixtures de otro
        self.academias, self.matriculas, self.productos, self.verificados = {}, [], {}, set()
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

    def eliminar_reservas(self, ids):
        for i in ids:
            self.reservas.pop(i, None)
        return True

    def canchas_de_dueno(self, email):
        return [c for c in self.canchas.values() if (c.get("dueno") or "").lower() == email.lower() and not c.get("eliminada")]

    def reservas_de_canchas(self, ids, desde, hasta):
        return sorted([dict(r) for r in self.reservas.values() if r["cancha_id"] in ids and desde <= r["fecha"] <= hasta
                       and not (r["estado"] == "nueva" and not r.get("pagado")) and r["estado"] != "cancelada"],
                      key=lambda r: (r["fecha"], r["hora_inicio"]))

    def bloqueos_de(self, ids, fechas):
        return {(c, f, h) for (c, f, h) in self.bloqueos if c in ids and f in fechas}

    def bloquear(self, cid, fecha, hora, bloquear=True):
        if bloquear:
            self.bloqueos.add((cid, fecha, hora))
        else:
            self.bloqueos.discard((cid, fecha, hora))
        return True

    def reserva_de_dueno(self, rid, ids):
        r = self.reservas.get(rid)
        return dict(r) if r and r["cancha_id"] in ids else None

    def marcar_pagado(self, rid, ids, pagado):
        r = self.reservas.get(rid)
        if not r or r["cancha_id"] not in ids:
            return False
        r["pagado"] = pagado
        return True

    def borrar_reserva_manual(self, rid, ids):
        r = self.reservas.get(rid)
        if not r or r["cancha_id"] not in ids or r.get("medio_pago") != "manual":
            return False
        del self.reservas[rid]
        return True

    # ── academias / matrículas / tienda / verificación ──
    academias: dict = {}
    matriculas: list = []
    productos: dict = {}
    verificados: set = set()

    def academias_de_dueno(self, email):
        return [dict(a, id=k) for k, a in self.academias.items() if (a.get("dueno") or "").lower() == email.lower() and not a.get("_eliminada")]

    def academia_existe(self, aid):
        return aid in self.academias

    def guardar_academia(self, aid, dueno, data):
        a = self.academias.get(aid)
        if a is not None and (a.get("dueno") or "").lower() != dueno.lower():
            return False
        self.academias[aid] = dict(data, dueno=dueno)
        return True

    def eliminar_academia(self, aid, dueno):
        a = self.academias.get(aid)
        if a is None or (a.get("dueno") or "").lower() != dueno.lower():
            return False
        a["_eliminada"] = True
        return True

    def matriculas_de_academias(self, ids):
        return [dict(m) for m in self.matriculas if m.get("academiaId") in ids]

    def productos_de_vendedor(self, email):
        return [dict(p) for p in self.productos.values() if p["vendedor_email"].lower() == email.lower()]

    def producto_por_id(self, pid):
        p = self.productos.get(pid)
        return dict(p) if p else None

    def guardar_producto(self, fila):
        p = self.productos.get(fila["id"])
        if p is not None and p["vendedor_email"].lower() != fila["vendedor_email"].lower():
            return False
        self.productos[fila["id"]] = dict(fila)
        return True

    def eliminar_producto(self, pid, email):
        p = self.productos.get(pid)
        if p is None or p["vendedor_email"].lower() != email.lower():
            return False
        del self.productos[pid]
        return True

    def esta_verificado(self, email):
        return email.lower() in self.verificados

    def actualizar_cancha(self, cancha_id, dueno, campos):
        c = self.canchas.get(cancha_id)
        if not c or (c.get("dueno") or "").lower() != dueno.lower() or c.get("eliminada"):
            return False
        c.update({k: v for k, v in campos.items() if k in datos.COLS_EDITABLES})
        return True

    def reservas_de_usuario(self, email, limite=200):
        return sorted([dict(r) for r in self.reservas.values()
                       if (r.get("usuario") or "").lower() == email.lower() and not (r["estado"] == "nueva" and not r.get("pagado"))],
                      key=lambda r: (r["fecha"], r["hora_inicio"]), reverse=True)

    def reservas_por_grupo(self, g):
        return sorted([dict(r) for r in self.reservas.values() if r["grupo_reserva_id"] == g],
                      key=lambda r: (r["fecha"], r["hora_inicio"]))


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    for fn in ("canchas_publicas", "canchas_verificadas", "cancha", "ocupados", "descuentos", "liberar_holds_vencidos",
               "insertar_reservas", "confirmar_reservas", "borrar_reservas", "reservas_de",
               "reservas_por_grupo", "reservas_de_usuario", "eliminar_reservas", "canchas_de_dueno", "reservas_de_canchas", "bloqueos_de",
               "actualizar_cancha", "bloquear", "reserva_de_dueno", "marcar_pagado", "borrar_reserva_manual",
               "academias_de_dueno", "academia_existe", "guardar_academia", "eliminar_academia", "matriculas_de_academias",
               "productos_de_vendedor", "producto_por_id", "guardar_producto", "eliminar_producto", "esta_verificado"):
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    return fake


def _hoy_iso(cancha=LIMA):
    return horarios.ahora_local(web._pais_de(cancha)).date().isoformat()


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
    # "Mis reservas" en la web (layout "Viajes" de Airbnb): las reservas del correo de Google.
    from datetime import timedelta
    from db.store import stores
    mr = cli.get("/mis-reservas").text
    ref1 = db.reservas[r['ids'][0]].get('grupo_reserva_id') or r['ids'][0]
    assert "Mis reservas" in mr and "ana@gmail.com" in mr and "Cancha Central" in mr and "Pagada" in mr
    assert f"/reserva/{ref1}" in mr and "id='mapaViajes'" in mr and "Reservaciones canceladas" in mr
    assert "href='/mis-reservas'" in mr  # enlace del menú ☰
    assert f"data-cancelar='{ref1}'" in mr and "data-reembolsable='1'" in mr
    # Dos turnos seguidos de la misma reserva = una sola tarjeta 20:00–22:00 · 2 turnos.
    r2 = cli.post("/web/asegurar", json={**body, "horas": [{"fecha": f, "hora": "20:00"}, {"fecha": f, "hora": "21:00"}]}).json()
    cli.post("/web/pagar", json={"ids": r2["ids"], "firma": r2["firma"], "token": "tkn", "medio": "yape", "email": "x@x.com"})
    mr = cli.get("/mis-reservas").text
    assert "20:00–22:00 · 2 turnos" in mr
    # El cargo web quedó en el libro, ligado a la reserva (es lo que se reembolsa).
    ref2 = db.reservas[r2["ids"][0]].get("grupo_reserva_id") or r2["ids"][0]
    cobro = next(x for x in stores.pagos if x.tipo == "cobro_web" and x.concepto == f"web:{ref2}")
    assert cobro.monto_centimos == 12000 and cobro.culqi_charge_id == "chr_g"
    liq = stores.pago_por_charge(r2["ids"][0]); assert liq is not None and liq.estado == "aprobado"
    # CANCELAR desde la web con más de 6 h: reembolso Culqi + reversa de la liquidación del dueño.
    reembolsos = []
    monkeypatch.setattr(culqi, "reembolsar", lambda **kw: (reembolsos.append(kw) or {"ok": True, "refund_id": "ref_1"}))
    assert cli.post("/web/cancelar", json={"ref": "grp_nada"}).json()["error"] == "sin_reserva"
    j = cli.post("/web/cancelar", json={"ref": ref2}).json()
    assert j["ok"] and j["reembolso"] == "reembolsado" and j["monto"] == 120 and j["refund_id"] == "ref_1"
    assert reembolsos == [{"charge_id": "chr_g", "monto_centimos": 12000}]
    assert all(i not in db.reservas for i in r2["ids"])              # horario liberado (como el app)
    assert liq.estado == "anulado" and cobro.estado == "reembolsado"  # el dueño ya no tiene ese "por recibir"
    reg = stores.cancelaciones_web[-1]
    assert reg["usuario"] == "ana@gmail.com" and reg["turnos"] == 2 and reg["reembolso"] == "reembolsado" and reg["deuda_dueno_centimos"] == 0
    assert cli.post("/web/cancelar", json={"ref": ref2}).json()["error"] == "sin_reserva"  # ya no existe
    mr = cli.get("/mis-reservas").text
    assert "20:00–22:00" not in mr.split("Reservaciones canceladas")[0] and "Devolución en camino" in mr
    # Menos de 6 h antes: se cancela pero SIN devolución y el dueño conserva su liquidación.
    from web import horarios as _h
    pronto = _h.ahora_local("PE") + timedelta(hours=2)
    db.reservas["r_hoy"] = {**db.reservas[r["ids"][0]], "id": "r_hoy", "grupo_reserva_id": "", "fecha": pronto.date().isoformat(),
                            "hora_inicio": f"{pronto.hour:02d}:00", "hora_fin": f"{(pronto.hour + 1) % 24:02d}:00", "medio_pago": "tarjeta"}
    stores.registrar_pago(tipo="liquidacion_full", monto_centimos=6000, moneda="PEN", estado="aprobado", dueno_id="dueno@x.com", culqi_charge_id="r_hoy")
    j = cli.post("/web/cancelar", json={"ref": "r_hoy"}).json()
    assert j["ok"] and j["reembolso"] == "sin_reembolso" and "r_hoy" not in db.reservas
    assert stores.pago_por_charge("r_hoy").estado == "aprobado" and len(reembolsos) == 1
    # Reserva de OTRA persona: no se puede tocar.
    db.reservas["r_ajena"] = {**db.reservas[r["ids"][0]], "id": "r_ajena", "grupo_reserva_id": "", "usuario": "otro@gmail.com"}
    assert cli.post("/web/cancelar", json={"ref": "r_ajena"}).json()["error"] == "ajena"
    # Torre: listado de cancelaciones web.
    adm = cli.get("/pagos/cancelaciones-web", headers={"X-Admin-Token": "adm"}).json()
    assert adm["total"] >= 2 and adm["cancelaciones"][0]["reembolso"] in ("sin_reembolso", "reembolsado") and adm["pendientes"] == 0
    assert cli.get("/pagos/cancelaciones-web").status_code in (401, 503)
    # Pagó en el APP (sin cargo web) y el dueño YA había cobrado: queda manual + deuda; la torre lo cierra.
    db.reservas["r_app"] = {**db.reservas[r["ids"][0]], "id": "r_app", "grupo_reserva_id": "", "medio_pago": "tarjeta"}
    stores.registrar_pago(tipo="liquidacion_online", monto_centimos=6000, moneda="PEN", estado="aprobado", dueno_id="dueno@x.com",
                          culqi_charge_id="r_app", liquidado=True)
    j = cli.post("/web/cancelar", json={"ref": "r_app"}).json()
    assert j["ok"] and j["reembolso"] == "manual"
    reg = stores.cancelaciones_web[-1]
    assert reg["deuda_dueno_centimos"] == 6000 - 300 and stores.pago_por_charge("r_app_ajuste").estado == "pendiente"
    adm = cli.get("/pagos/cancelaciones-web?pendientes=1", headers={"X-Admin-Token": "adm"}).json()
    assert adm["pendientes"] == 1 and adm["cancelaciones"][0]["id"] == reg["id"]
    hdr = {"X-Admin-Token": "adm"}
    assert cli.post(f"/pagos/cancelaciones-web/{reg['id']}/resolver", json={"accion": "devuelto", "referencia": "Yape 123"}, headers=hdr).json()["ok"]
    assert reg["reembolso"] == "reembolsado_manual" and reg["referencia"] == "Yape 123"
    assert cli.post(f"/pagos/cancelaciones-web/{reg['id']}/resolver", json={"accion": "devuelto"}, headers=hdr).json()["error"] == "no_pendiente"
    assert cli.post(f"/pagos/cancelaciones-web/{reg['id']}/resolver", json={"accion": "descontado"}, headers=hdr).json()["ok"]
    assert reg["deuda_resuelta"] and stores.pago_por_charge("r_app_ajuste").estado == "aplicado"
    assert cli.get("/pagos/cancelaciones-web?pendientes=1", headers=hdr).json()["pendientes"] == 0
    # La torre trae el pane.
    torre = cli.get("/admin", headers=hdr).text if cli.get("/admin", headers=hdr).status_code == 200 else cli.get("/admin").text
    assert "cancelacionesPanel" in torre and "cargarCancelacionesWeb" in torre
    # Salir: sin cookie vuelve a exigir sesión.
    cli.post("/web/salir")
    assert cli.get("/mis-reservas", follow_redirects=False).status_code == 302
    assert cli.post("/web/asegurar", json=body).json()["error"] == "sesion_requerida"
    # Sin client id configurado, la web sigue con el formulario de invitado.
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "")
    assert "id='loginBox'" not in client.get("/reservar/c_lima").text and '"login": false' in client.get("/reservar/c_lima").text


def test_modo_anfitrion_en_la_web_como_airbnb(db, monkeypatch):
    """"Modo anfitrión" abre el panel del dueño en la web (como airbnb.com/
    hosting): Hoy, Calendario, Reservas, Ingresos y Canchas con su sesión de
    Google; sin canchas a su nombre → onboarding; sin sesión → login."""
    from web import sesion
    from db.store import stores
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    assert cli.get("/anfitrion", follow_redirects=False).status_code == 302
    assert "href='/anfitrion'" in cli.get("/").text  # el enlace "Modo anfitrión" de la cabecera
    # Jugadora sin canchas → onboarding.
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "ana@gmail.com", "email_verified": "true", "aud": "cid-web", "name": "Ana Pérez", "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})
    # /anfitrion = el MENÚ del app (cabecera verde + 5 tarjetas); "Mis canchas" sin canchas → onboarding.
    menu = cli.get("/anfitrion").text
    for t in ("Modo anfitrión", "Publica tu cancha o academia", "Mis canchas", "Mi academia", "Mis campeonatos", "Mi tienda", "Verificador",
              "href='/anfitrion/mis-canchas'", "href='/anfitrion/academia'"):
        assert t in menu, t
    assert "Cambiar a modo jugador" in menu
    html = cli.get("/anfitrion/mis-canchas").text
    assert "todavía no tienes canchas registradas" in html and "Registrar mi cancha en la app" in html
    aca = cli.get("/anfitrion/campeonatos").text  # campeonatos y verificador siguen en la app; academia y tienda ya son web
    assert "Mis campeonatos está en la app" in aca and "Abrir en la app" in aca
    assert cli.get("/anfitrion/nada").status_code == 404
    # Una reserva web pagada en la cancha del dueño.
    f = _manana()
    r = cli.post("/web/asegurar", json={"cancha_id": "c_lima", "horas": [{"fecha": f, "hora": "19:00"}], "extras": [],
                                        "nombre": "Ana", "celular": "999888777", "email": "ana@gmail.com"}).json()
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": True, "charge_id": "chr_h"})
    import pagos.router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    assert cli.post("/web/pagar", json={"ids": r["ids"], "firma": r["firma"], "token": "t", "medio": "yape"}).json()["ok"]
    # El dueño entra: ve su panel.
    cli.post("/web/salir")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "dueno@x.com", "email_verified": "true", "aud": "cid-web", "name": "Don Dueño", "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})
    hoy = cli.get("/anfitrion/mis-canchas").text
    assert "¡Hola, Don!" in hoy and "href='/anfitrion'" in hoy and "Cambiar a modo jugador" in hoy and "Modo anfitrión" not in hoy.split("cab-der")[1].split("</div>")[0]
    assert "Próximos 7 días <small>(1)</small>" in hoy and "Ana" in hoy and "999888777" in hoy and "Pagada en línea · yape" in hoy
    for k in ("/anfitrion/mis-canchas", "/anfitrion/calendario", "/anfitrion/reservas", "/anfitrion/ingresos", "/anfitrion/canchas"):
        assert f"href='{k}'" in hoy
    cal = cli.get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text
    assert "Calendario" in cal and "pagada" in cal and "Semana siguiente" in cal and "23:00" in cal
    res = cli.get("/anfitrion/reservas").text
    assert "Próximas" in res and "19:00–20:00" in res
    ing = cli.get("/anfitrion/ingresos").text
    assert "Por recibir" in ing and "S/ 60.00" in ing and "Reserva web" in ing
    can = cli.get("/anfitrion/canchas").text
    assert "Cancha Central" in can and "✓ Verificada" in can and "/reservar/c_lima" in can and "Nocturna" in can


def test_editar_cancha_desde_la_web_como_el_app(db, monkeypatch):
    """Modo anfitrión → Canchas → Editar: el dueño edita su cancha en la web
    con el MISMO formulario y validaciones que el app (fotos, nombre, deportes
    + piso, precio + hora feliz + seña, horario, servicios). Solo el dueño;
    lo guardado lo lee el app tal cual."""
    from web import almacen, anfitrion as anf, sesion
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    cli = TestClient(app, base_url="https://testserver")
    url = "/anfitrion/cancha/c_lima/editar"
    assert cli.get(url, follow_redirects=False).status_code == 302
    assert cli.post(url, json={}).status_code == 401
    # Otra persona con sesión: la cancha no está a su nombre → 404 (ni ve ni guarda).
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "ana@gmail.com", "email_verified": "true", "aud": "cid-web", "name": "Ana", "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})
    assert cli.get(url).status_code == 404
    assert cli.post(url, json={"nombre": "Hackeada"}).status_code == 404
    assert db.canchas["c_lima"]["nombre"] == "Cancha Central"
    # El dueño: ve el formulario con los catálogos del app.
    cli.post("/web/salir")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "Dueno@x.com", "email_verified": "true", "aud": "cid-web", "name": "Don Dueño", "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})
    assert "href='/anfitrion/cancha/c_lima/editar'" in cli.get("/anfitrion/canchas").text
    html = cli.get(url).text
    for t in ("Editar cancha", "Fotos", "Nombre y local", "Deportes y tipo de piso", "Grass sintético", "Precio y promociones",
              "Hora feliz", "Seña para reservar", "empieza el último turno", "Servicios del local", "Estacionamiento",
              "Servicios extra", "Árbitro", "Guardar cambios", "data-v='pickleball'", "data-v='techado'", "−30 %", "1h 30min"):
        assert t in html, t
    # Validaciones = las del app.
    base = {"nombre": "Cancha 1 · Grass", "club": "Complejo Central", "deportes": ["futbol", "voley"], "superficie": "Grass sintético",
            "precio_hora": 75.5, "descuento_valle": 20, "valle_desde": "07:00", "valle_hasta": "12:00", "sena_pct": 30,
            "hora_apertura": "06:00", "hora_cierre": "00:00", "duracion_slot_min": 90, "amenidades": ["parking", "luces", "invento"],
            "servicios_extra": [{"clave": "arbitro", "precio": 40}, {"clave": "parrilla", "precio": 25}], "fotos": []}
    r = cli.post(url, json={**base, "nombre": "  "}); assert r.status_code == 400 and r.json()["campo"] == "nombre"
    r = cli.post(url, json={**base, "deportes": []}); assert r.status_code == 400 and r.json()["campo"] == "deportes"
    r = cli.post(url, json={**base, "superficie": "Arcilla"}); assert r.status_code == 400 and "piso" in r.json()["error"]
    r = cli.post(url, json={**base, "precio_hora": 0}); assert r.status_code == 400 and r.json()["campo"] == "precio"
    r = cli.post(url, json={**base, "sena_pct": 45}); assert r.status_code == 400
    r = cli.post(url, json={**base, "duracion_slot_min": 45}); assert r.status_code == 400 and r.json()["campo"] == "horario"
    r = cli.post(url, json={**base, "hora_cierre": "23:30"}); assert r.status_code == 400
    r = cli.post(url, json={**base, "servicios_extra": [{"clave": "arbitro", "precio": 0}]}); assert r.status_code == 400 and r.json()["campo"] == "extras"
    # Foto: se sube al bucket `canchas` del app (carpeta de la cancha) y vuelve la URL.
    subidas = []
    monkeypatch.setattr(almacen, "subir_foto", lambda cid, b, ct="image/jpeg": subidas.append((cid, len(b), ct)) or f"https://sb.test/storage/v1/object/public/canchas/{cid}/web_1.jpg?v=1")
    r = cli.post("/anfitrion/cancha/c_lima/foto", content=b"\xff\xd8\xff" * 100, headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200 and r.json()["ok"] and subidas == [("c_lima", 300, "image/jpeg")]
    nueva = r.json()["url"]
    assert cli.post("/anfitrion/cancha/c_lima/foto", content=b"x", headers={"Content-Type": "text/plain"}).status_code == 415
    assert cli.post("/anfitrion/cancha/c_gye/foto", content=b"x", headers={"Content-Type": "image/jpeg"}).status_code == 200  # también suya
    assert cli.post("/anfitrion/cancha/c_pend/foto", content=b"x", headers={"Content-Type": "image/jpeg"}).status_code == 404  # sin dueño
    # Guardar: entra al fake con las claves/columnas del app; la foto ajena se descarta y la vieja quitada se borra del bucket.
    db.canchas["c_lima"]["fotos"] = ["https://sb.test/storage/v1/object/public/canchas/c_lima/vieja.jpg"]
    borradas = []
    monkeypatch.setattr(almacen, "borrar_foto", lambda u: borradas.append(u) or True)
    monkeypatch.setattr(anf, "_en_segundo_plano", lambda fn, *a: fn(*a))
    r = cli.post(url, json={**base, "fotos": [nueva, "https://evil.example/x.jpg"]})
    assert r.status_code == 200 and r.json()["ok"], r.text
    c = db.canchas["c_lima"]
    assert c["nombre"] == "Cancha 1 · Grass" and c["club"] == "Complejo Central" and c["precio_hora"] == 75.5
    assert c["deporte"] == "futbol" and c["deportes"] == ["futbol", "voley"] and c["superficie"] == "Grass sintético"
    assert c["descuento_valle"] == 20 and c["valle_desde"] == "07:00" and c["valle_hasta"] == "12:00" and c["sena_pct"] == 30
    assert c["hora_apertura"] == "06:00" and c["hora_cierre"] == "00:00" and c["duracion_slot_min"] == 90
    assert c["amenidades"] == ["parking", "luces"]  # "invento" no existe en el catálogo del app
    assert c["servicios_extra"] == [{"clave": "arbitro", "precio": 40.0}, {"clave": "parrilla", "precio": 25.0}]
    assert c["fotos"] == [nueva] and c["foto_url"] == nueva
    assert borradas == ["https://sb.test/storage/v1/object/public/canchas/c_lima/vieja.jpg"]
    # Vuelve a Canchas con el aviso; la ficha pública y el explorador ya muestran lo nuevo.
    can = cli.get("/anfitrion/canchas?guardado=c_lima").text
    assert "Guardamos los cambios de <b>Cancha 1 · Grass</b>" in can and "06:00–00:00 · 90 min" in can
    ficha = cli.get("/reservar/c_lima").text
    assert "Cancha 1 · Grass" in ficha and "Árbitro" in ficha and "Parrilla" in ficha
    assert "🅿️ Estacionamiento" in cli.get("/").text  # el chip del explorador reconoce la clave del app


def test_calendario_web_reserva_manual_bloqueo_y_marcar_pagado(db, monkeypatch):
    """Calendario del anfitrión (como el de Airbnb): al tocar un turno el dueño
    registra una reserva MANUAL (misma fila que el app: confirmada, sin
    comisión, medio 'manual', push al jugador), BLOQUEA/desbloquea horas y
    MARCA PAGADA una reserva en efectivo (push de puntos como el app). Solo
    sobre sus canchas; candado Pro por env (fail-open)."""
    from web import sesion
    import pagos.router as pr
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    from web import anfitrion as anf
    pushes = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, titulo, cuerpo, tipo="aviso": pushes.append((email, titulo, tipo)))
    monkeypatch.setattr(anf, "_en_segundo_plano", lambda fn, *a: fn(*a))  # en el server va en hilo; aquí síncrono
    cli = TestClient(app, base_url="https://testserver")
    f = _manana()
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00"}).status_code == 401
    # Una jugadora reserva y paga en la cancha (efectivo) → el dueño la verá "por cobrar".
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "ana@gmail.com", "email_verified": "true", "aud": "cid-web", "name": "Ana", "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})
    r = cli.post("/web/asegurar", json={"cancha_id": "c_lima", "horas": [{"fecha": f, "hora": "19:00"}], "extras": [],
                                        "nombre": "Ana", "celular": "999888777", "email": "ana@gmail.com"}).json()
    assert r.get("ok"), r
    rid = r["ids"][0]
    db.reservas[rid].update({"estado": "confirmada", "medio_pago": "efectivo", "pagado": False})
    # Ana NO es dueña: 404 en todo.
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00"}).status_code == 404
    assert cli.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": True}).status_code == 404
    assert cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00", "nombre": "X"}).status_code == 404
    cli.post("/web/salir")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": "dueno@x.com", "email_verified": "true", "aud": "cid-web", "name": "Don Dueño", "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})
    cal = cli.get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text
    assert "data-t='libre'" in cal and f"data-rid='{rid}'" in cal and "Reserva manual" in cal and "Bloquear turno" in cal and "Marcar pagada" in cal
    assert "parte de <b>Pichangol Pro</b>" not in cal  # candado apagado por defecto (fail-open)
    # Bloquear / desbloquear.
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00"}).json()["ok"]
    assert ("c_lima", f, "10:00") in db.bloqueos
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "19:00"}).status_code == 409  # ya reservado
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:30"}).status_code == 400  # no es turno
    assert "Bloqueado" in cli.get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text
    assert "ocupado" == cli.post("/web/asegurar", json={"cancha_id": "c_lima", "horas": [{"fecha": f, "hora": "10:00"}], "extras": [],
                                                        "nombre": "Beto", "celular": "999000111", "email": "b@x.com"}).json()["error"]
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00", "bloquear": False}).json()["ok"]
    assert ("c_lima", f, "10:00") not in db.bloqueos
    # Reserva manual: misma fila que el app; precio sugerido (hora feliz 50 % antes de las 12) si no mandan monto; push al cliente con cuenta.
    r = cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00", "nombre": "  Juan  Pérez ", "telefono": "988 777 666",
                                                    "email": "Juan@Gmail.com", "pagado": False}).json()
    assert r["ok"] and r["precio"] == 30, r
    fila = db.reservas[r["id"]]
    assert fila["estado"] == "confirmada" and fila["traida_por_app"] is False and fila["medio_pago"] == "manual" and fila["pagado"] is False
    assert fila["jugador"] == "Juan Pérez" and fila["usuario"] == "juan@gmail.com" and fila["telefono"] == "988 777 666" and fila["hora_fin"] == "11:00"
    assert pushes[-1] == ("juan@gmail.com", "Reserva confirmada 🎾", "reserva_manual")
    assert cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "10:00", "nombre": "Otro"}).status_code == 409
    assert cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": "2020-01-01", "hora": "10:00", "nombre": "Otro"}).status_code == 400
    assert cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "11:00", "email": "no-es-correo"}).status_code == 400
    r2 = cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "11:00", "precio": 45.4, "pagado": True}).json()
    assert r2["ok"] and db.reservas[r2["id"]]["precio"] == 45 and db.reservas[r2["id"]]["jugador"] == "Cliente" and db.reservas[r2["id"]]["pagado"] is True
    # Madrugada: la cancha nocturna (18:00→02:00) liga el turno de 01:00 al día siguiente.
    r3 = cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_noche", "fecha": f, "hora": "01:00", "nombre": "N"}).json()
    from datetime import date, timedelta
    assert r3["ok"] and db.reservas[r3["id"]]["fecha"] == (date.fromisoformat(f) + timedelta(days=1)).isoformat()
    # Marcar pagada la reserva en efectivo de Ana → push de puntos; volver a "por cobrar"; una pagada en línea no se revierte.
    assert cli.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": True}).json()["ok"]
    assert db.reservas[rid]["pagado"] is True and pushes[-1] == ("ana@gmail.com", "¡Te llegaron puntos! ⭐", "puntos")
    n = len(pushes)
    assert cli.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": True}).json().get("sin_cambio")
    assert cli.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": False}).json()["ok"] and db.reservas[rid]["pagado"] is False and len(pushes) == n
    db.reservas[rid].update({"pagado": True, "medio_pago": "yape"})
    assert cli.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": False}).status_code == 400
    assert cli.post("/anfitrion/reserva/no_existe/pagado", json={}).status_code == 404
    # Quitar: solo manuales (la de Ana, pagada por la web, no).
    assert cli.post(f"/anfitrion/reserva/{rid}/quitar").status_code == 400
    assert cli.post(f"/anfitrion/reserva/{r['id']}/quitar").json()["ok"] and r["id"] not in db.reservas
    assert pushes[-1] == ("juan@gmail.com", "Reserva cancelada 📅", "reserva_manual")
    # "Hoy" muestra el botón para cobrar en efectivo.
    db.reservas[rid].update({"pagado": False, "medio_pago": "efectivo", "fecha": _hoy_iso()})
    hoy = cli.get("/anfitrion/mis-canchas").text
    assert f"data-pagar='{rid}'" in hoy and "Marcar pagada" in hoy
    # Candado Pro (env): sin Pro → 402 y aviso en el calendario; con Pro → pasa.
    monkeypatch.setattr(config, "WEB_MANUAL_REQUIERE_PRO", True)
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "12:00"}).status_code == 402
    assert cli.post("/anfitrion/reserva-manual", json={"cancha_id": "c_lima", "fecha": f, "hora": "12:00"}).json()["error"] == "requiere_pro"
    assert "parte de <b>Pichangol Pro</b>" in cli.get(f"/anfitrion/calendario?cancha=c_lima&desde={f}").text
    assert cli.post(f"/anfitrion/reserva/{rid}/pagado", json={"pagado": True}).json()["ok"]  # marcar pagado NO es Pro
    from datetime import datetime, timezone
    stores.membresias_pro["dueno@x.com"] = {"hasta": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()}
    assert cli.post("/anfitrion/bloqueo", json={"cancha_id": "c_lima", "fecha": f, "hora": "12:00"}).json()["ok"]
    stores.membresias_pro.pop("dueno@x.com", None)


def _entrar_como(cli, monkeypatch, email, nombre="Alguien"):
    from web import sesion
    cli.post("/web/salir")
    monkeypatch.setattr(sesion, "_tokeninfo", lambda t: {"email": email, "email_verified": "true", "aud": "cid-web", "name": nombre, "exp": "9999999999"})
    cli.post("/web/sesion", json={"credential": "x"})


def test_mi_tienda_en_la_web_como_el_app(db, monkeypatch):
    """Modo anfitrión → Mi tienda: publicar/editar/pausar/eliminar productos del
    Marketplace desde la web con el candado del app (verificado o dueño),
    misma tabla `pichangol_productos` y bucket `productos`; ventas del backend."""
    from web import almacen, anfitrion as anf
    from db.store import Venta, stores
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(anf, "_en_segundo_plano", lambda fn, *a: fn(*a))
    cli = TestClient(app, base_url="https://testserver")
    assert cli.get("/anfitrion/tienda", follow_redirects=False).status_code == 302
    # El menú del anfitrión ya lleva a la web (no a "está en la app").
    _entrar_como(cli, monkeypatch, "nadie@gmail.com", "Nadie")
    assert "href='/anfitrion/tienda'" in cli.get("/anfitrion").text
    # Sin verificación ni canchas → candado (igual que `puedeVender`).
    html = cli.get("/anfitrion/tienda").text
    assert "Verifica tu identidad para vender" in html
    assert cli.post("/anfitrion/tienda/guardar", json={"id": "prod_123456_w", "nombre": "X"}).status_code == 403
    # Verificado → puede vender.
    db.verificados.add("nadie@gmail.com")
    html = cli.get("/anfitrion/tienda").text
    assert "Publicar producto" in html and "Aún no publicas productos" in html
    nuevo = cli.get("/anfitrion/tienda/nuevo").text
    assert "Publicar producto" in nuevo and "data-v='raquetas'" in nuevo and "data-v='S/'" in nuevo and "Publicado" in nuevo
    pid = nuevo.split('"id": "')[1].split('"')[0]
    assert pid.startswith("prod_") and pid.endswith("_w")
    # Foto → bucket `productos/<id>.jpg` (misma ruta que el app).
    subidas = []
    monkeypatch.setattr(almacen, "subir", lambda bucket, ruta, b, ct="image/jpeg": subidas.append((bucket, ruta)) or f"https://sb.test/storage/v1/object/public/{bucket}/{ruta}?v=1")
    r = cli.post(f"/anfitrion/tienda/{pid}/foto", content=b"\xff\xd8" * 10, headers={"Content-Type": "image/jpeg"}).json()
    assert r["ok"] and subidas == [("productos", f"{pid}.jpg")]
    base = {"id": pid, "nombre": "Raqueta Wilson Pro Staff", "categoria": "raquetas", "descripcion": "Usada, buen estado", "moneda": "S/",
            "precio": 350, "stock": 1, "activo": True, "foto_url": r["url"]}
    assert cli.post("/anfitrion/tienda/guardar", json={**base, "nombre": "x"}).json()["campo"] == "datos"
    assert cli.post("/anfitrion/tienda/guardar", json={**base, "precio": 0}).status_code == 400
    assert cli.post("/anfitrion/tienda/guardar", json={**base, "categoria": "drones"}).status_code == 400
    assert cli.post("/anfitrion/tienda/guardar", json={**base, "id": "hack"}).status_code == 400
    ok = cli.post("/anfitrion/tienda/guardar", json={**base, "foto_url": "https://evil/x.jpg"}).json()
    assert ok["ok"]
    p = db.productos[pid]
    assert p["vendedor_email"] == "nadie@gmail.com" and p["vendedor_nombre"] == "Nadie" and p["precio"] == 350.0 and p["stock"] == 1
    assert p["foto_url"] == "" and p["activo"] is True and p["categoria"] == "raquetas" and p["creado_en"]
    assert cli.post("/anfitrion/tienda/guardar", json=base).json()["ok"] and db.productos[pid]["foto_url"] == r["url"]
    lista = cli.get("/anfitrion/tienda?guardado=1").text
    assert "Raqueta Wilson Pro Staff" in lista and "Publicado" in lista and "S/ 350.00" in lista and "Producto guardado" in lista
    # Editar: la moneda queda fija; pausar; otra persona no lo ve ni lo toca.
    assert "Editar producto" in cli.get(f"/anfitrion/tienda/{pid}/editar").text
    assert cli.post("/anfitrion/tienda/guardar", json={**base, "moneda": "$", "precio": 99}).json()["ok"] and db.productos[pid]["moneda"] == "S/"
    assert cli.post(f"/anfitrion/tienda/{pid}/activo", json={"activo": False}).json()["ok"] and db.productos[pid]["activo"] is False
    assert "Pausado" in cli.get("/anfitrion/tienda").text
    stores.ventas.append(Venta(id=1, producto_id=pid, producto_nombre="Raqueta Wilson Pro Staff", comprador_email="ana@gmail.com", comprador_nombre="Ana",
                               vendedor_email="nadie@gmail.com", vendedor_nombre="Nadie", monto_soles=99.0, creado_en=datetime.now(timezone.utc), estado="pagado"))
    v = cli.get("/anfitrion/tienda").text
    assert "1 venta" in v and "ana@gmail.com" in v and "S/ 99.00" in v
    stores.ventas.clear()
    _entrar_como(cli, monkeypatch, "otro@gmail.com", "Otro")
    db.verificados.add("otro@gmail.com")
    assert cli.get(f"/anfitrion/tienda/{pid}/editar").status_code == 404
    assert cli.post("/anfitrion/tienda/guardar", json=base).status_code == 404
    assert cli.post(f"/anfitrion/tienda/{pid}/foto", content=b"x", headers={"Content-Type": "image/jpeg"}).status_code == 404
    assert cli.post(f"/anfitrion/tienda/{pid}/eliminar").status_code == 404
    # Dueño de canchas (sin verificación) también vende; eliminar borra fila y foto.
    _entrar_como(cli, monkeypatch, "dueno@x.com", "Don Dueño")
    assert "Publicar producto" in cli.get("/anfitrion/tienda").text
    _entrar_como(cli, monkeypatch, "nadie@gmail.com", "Nadie")
    borradas = []
    monkeypatch.setattr(almacen, "borrar_foto", lambda u: borradas.append(u) or True)
    assert cli.post(f"/anfitrion/tienda/{pid}/eliminar").json()["ok"] and pid not in db.productos and borradas == [r["url"]]


def test_mi_academia_en_la_web_como_el_app(db, monkeypatch):
    """Modo anfitrión → Mi academia: crear/editar la academia (misma fila
    `pichangol_academias.data` = `Academia.toJson`), zona por país, planes y
    reglas de cobro; alumnos y cuotas de `pichangol_matriculas`."""
    from web import almacen, anfitrion as anf
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(anf, "_en_segundo_plano", lambda fn, *a: fn(*a))
    cli = TestClient(app, base_url="https://testserver")
    assert cli.get("/anfitrion/academia", follow_redirects=False).status_code == 302
    # Árbol geo por país = el del app.
    g = cli.get("/web/geo/pe").json()
    assert g["ok"] and g["labels"] == ["Departamento", "Provincia", "Distrito"] and "San Borja" in g["arbol"]["Lima"]["Lima"]
    assert cli.get("/web/geo/ar").status_code == 404
    _entrar_como(cli, monkeypatch, "profe@gmail.com", "Profe Luis")
    html = cli.get("/anfitrion/academia").text
    assert "todavía no tienes una academia" in html and "href='/anfitrion/academia/nueva'" in html
    nueva = cli.get("/anfitrion/academia/nueva").text
    assert "Crear academia" in nueva and "data-v='natacion'" in nueva and "mapaSede" in nueva and "Planes y tarifario" in nueva and "Reglas de cobro" in nueva
    aid = nueva.split('"id": "')[1].split('"')[0]
    assert aid.startswith("ac_")
    subidas = []
    monkeypatch.setattr(almacen, "subir", lambda bucket, ruta, b, ct="image/jpeg": subidas.append((bucket, ruta)) or f"https://sb.test/storage/v1/object/public/{bucket}/{ruta}?v=1")
    logo = cli.post(f"/anfitrion/academia/{aid}/foto?tipo=logo", content=b"\xff\xd8" * 10, headers={"Content-Type": "image/jpeg"}).json()["url"]
    foto = cli.post(f"/anfitrion/academia/{aid}/foto", content=b"\xff\xd8" * 10, headers={"Content-Type": "image/jpeg"}).json()["url"]
    assert subidas[0] == ("canchas", f"academia_{aid}/logo_web.jpg") and subidas[1][1].startswith(f"academia_{aid}/web_")
    base = {"id": aid, "nombre": "Academia Baseline", "deporte": "tenis", "descripcion": "Tenis para niños y adultos", "sedeClub": "Club Lawn Tennis",
            "lat": -12.09, "lng": -77.03, "zona": "San Borja", "whatsapp": "999 888 777", "logoUrl": logo, "fotos": [foto, "https://evil/x.jpg"],
            "redes": {"instagram": "@baseline", "otra": "x"},
            "planes": [{"id": "pl_1", "nombre": "Mensualidad", "tipo": "mensual", "precioMes": 250, "programa": "Iniciación", "frecuenciaSemana": 2, "duracionClase": "1 h", "horario": "Lun y Mié 5pm"},
                       {"id": "pl_2", "nombre": "Paquete", "tipo": "prepago", "precioMes": 230, "meses": 3}],
            "recargoInvitado": 50, "descuentoHermano2": 10, "descuentoHermano3": 20, "descuentoPrepago": 5, "mesesMinPrepago": 3, "retribucionClubPct": 11}
    assert cli.post("/anfitrion/academia/guardar", json={**base, "nombre": ""}).json()["campo"] == "identidad"
    assert cli.post("/anfitrion/academia/guardar", json={**base, "sedeClub": ""}).json()["campo"] == "sede"
    assert cli.post("/anfitrion/academia/guardar", json={**base, "whatsapp": "1234"}).json()["campo"] == "sede"
    assert cli.post("/anfitrion/academia/guardar", json={**base, "planes": [{"nombre": "", "precioMes": 0}]}).json()["campo"] == "planes"
    assert cli.post("/anfitrion/academia/guardar", json={**base, "id": "x"}).status_code == 400
    assert cli.post("/anfitrion/academia/guardar", json=base).json()["ok"]
    a = db.academias[aid]
    assert a["dueno"] == "profe@gmail.com" and a["whatsapp"] == "999888777" and a["moneda"] == "S/" and a["zona"] == "San Borja"
    assert a["logoUrl"] == logo and a["fotos"] == [foto] and a["redes"] == {"instagram": "@baseline"}
    assert a["planes"][0]["meses"] == 1 and a["planes"][0]["frecuenciaSemana"] == 2 and a["planes"][1]["meses"] == 3
    assert a["descuentoHermano2"] == 10 and a["retribucionClubPct"] == 11 and a["sedes"] == [] and a["horarios"] == {}
    lista = cli.get("/anfitrion/academia?guardado=1").text
    assert "Academia Baseline" in lista and "Club Lawn Tennis" in lista and f"/anfitrion/academia/{aid}/editar" in lista and f"/l/{aid}" in lista and "Academia guardada" in lista
    # Editar conserva lo que la web no toca (sedes, ranking); la moneda queda fija.
    db.academias[aid]["partidos"] = [{"id": "p1"}]
    db.academias[aid]["sedes"] = [{"id": "s1", "nombre": "Sede 2", "direccion": ""}]
    ed = cli.get(f"/anfitrion/academia/{aid}/editar").text
    assert "Editar academia" in ed and "Academia Baseline" in ed and "Mensualidad" in ed
    assert cli.post("/anfitrion/academia/guardar", json={**base, "nombre": "Baseline Tenis", "lat": -2.17, "lng": -79.92, "whatsapp": "0999888777"}).json()["ok"]
    a = db.academias[aid]
    assert a["nombre"] == "Baseline Tenis" and a["partidos"] == [{"id": "p1"}] and a["sedes"][0]["id"] == "s1" and a["moneda"] == "S/"
    # Alumnos y cuotas (misma tabla del app).
    db.matriculas.append({"id": "m1", "academiaId": aid, "nombre": "Juanito", "edad": 9, "apoderadoNombre": "Rosa", "apoderadoWhatsapp": "988777666", "email": "",
                          "cuotas": [{"id": "c1", "concepto": "Marzo", "monto": 250, "vencimiento": "2020-03-05", "pagada": True, "fechaPago": "2020-03-01"},
                                     {"id": "c2", "concepto": "Abril", "monto": 250, "vencimiento": "2020-04-05", "pagada": False}]})
    al = cli.get(f"/anfitrion/academia/alumnos?academia={aid}").text
    assert "Juanito" in al and "Apoderado: Rosa" in al and "Vencida" in al and "S/ 250.00" in al and "1/2" in al
    assert "1 alumno" in cli.get("/anfitrion/academia").text
    # Otra persona: ni ve ni edita ni sube imágenes a su carpeta.
    _entrar_como(cli, monkeypatch, "otro@gmail.com", "Otro")
    assert cli.get(f"/anfitrion/academia/{aid}/editar").status_code == 404
    assert cli.post("/anfitrion/academia/guardar", json=base).status_code == 400 or db.academias[aid]["dueno"] == "profe@gmail.com"
    assert cli.post(f"/anfitrion/academia/{aid}/foto", content=b"x", headers={"Content-Type": "image/jpeg"}).status_code == 404
    assert cli.post(f"/anfitrion/academia/{aid}/eliminar").status_code == 404
    _entrar_como(cli, monkeypatch, "profe@gmail.com", "Profe Luis")
    assert cli.post(f"/anfitrion/academia/{aid}/eliminar").json()["ok"] and db.academias[aid]["_eliminada"]
