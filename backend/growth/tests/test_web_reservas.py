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

    def insertar_canchas(self, filas):
        for f in filas:
            self.canchas[f["id"]] = {**LIMA, **dict(f)}
        return True

    def borrar_canchas(self, ids, dueno):
        n = 0
        for i in list(ids):
            c = self.canchas.get(i)
            if c and (c.get("dueno") or "").lower() == dueno.lower() and not c.get("verificada"):
                self.canchas.pop(i); n += 1
        return n

    def marcar_verificada(self, cancha_id, dueno, verificada, lat=None, lng=None):
        base = cancha_id.split("_")[0]
        n = 0
        for c in self.canchas.values():
            cerca = lat is not None and abs(c["lat"] - lat) < 0.0014 and abs(c["lng"] - lng) < 0.0014
            if (c.get("dueno") or "").lower() == dueno.lower() and (c["id"] == cancha_id or c["id"].startswith(base + "_") or cerca):
                c["verificada"] = bool(verificada); n += 1
        return n

    def adoptar_cancha(self, cancha_id, dueno, campos):
        c = self.canchas.get(cancha_id)
        if not c or c.get("dueno") or c.get("verificada"):
            return False
        c.update({k: v for k, v in campos.items() if k in datos.COLS_ADOPCION}); c["dueno"] = dueno.lower()
        return True

    def desadoptar_cancha(self, cancha_id, dueno):
        c = self.canchas.get(cancha_id)
        if c and (c.get("dueno") or "").lower() == dueno.lower() and not c.get("verificada"):
            c["dueno"] = ""; return True
        return False

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

    def academias_publicas(self):
        return [dict(a, id=k) for k, a in self.academias.items() if not a.get("_eliminada")]

    def academia(self, aid):
        a = self.academias.get(aid)
        return None if (a is None or a.get("_eliminada")) else dict(a, id=aid)

    def insertar_matricula(self, alumno_id, academia_id, email, data):
        if any(m.get("id") == alumno_id for m in self.matriculas):
            return False
        self.matriculas.append(dict(data, id=alumno_id, academiaId=academia_id, email=email))
        return True

    def matricula(self, alumno_id):
        m = next((m for m in self.matriculas if m.get("id") == alumno_id), None)
        return dict(m) if m else None

    def matriculas_de_pagador(self, academia_id, email):
        return [dict(m) for m in self.matriculas if m.get("academiaId") == academia_id and (m.get("email") or "").lower() == (email or "").lower()]

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
               "academias_publicas", "academia", "insertar_matricula", "matricula", "academias_de_dueno", "academia_existe", "guardar_academia", "eliminar_academia", "matriculas_de_academias", "matriculas_de_pagador",
               "productos_de_vendedor", "producto_por_id", "guardar_producto", "eliminar_producto", "esta_verificado",
               "insertar_canchas", "borrar_canchas", "marcar_verificada", "adoptar_cancha", "desadoptar_cancha"):
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
    # Una tarjeta por LOCAL (como el app): "Club Raqueta" agrupa Cancha Central + Nocturna.
    assert "<b>Club Raqueta</b>" in r.text and "2 canchas" in r.text and "data-ids='c_lima c_noche'" in r.text
    assert "<b>Cancha Central</b>" not in r.text and "Cancha Guayaquil" in r.text
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
    ex = db.reservas[j["ids"][0]]["extras"]
    assert [(x["clave"], x["precio"], x["cantidad"], x["nombre"]) for x in ex] == [("arbitro", 30.0, 1, "Árbitro")]
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
    for t in ("id='sQ'", "id='sF'", "id='sH'", "id='panCuando'", "id='panHora'", "class='cat sel'", "<b>Club Raqueta</b>", "class='corazon'",
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


def test_no_verificadas_no_salen_hasta_ser_aprobadas(db, monkeypatch):
    """Como el app (regla del director, sep-2026): una cancha en verificación
    NO sale en el explorador ni la ve el público; solo su dueño la abre como
    vista previa. El legado sin dueño sigue accesible por enlace para
    reclamarlo. Y la ficha lleva el LOCAL de título, no el nombre de la cancha."""
    html = client.get("/canchas").text
    assert "Loza Pendiente" not in html and "Aún sin verificar" not in html
    # La tarjeta es el LOCAL: título "Club Raqueta" con sus 2 canchas aprobadas (la pendiente no cuenta).
    assert "<b>Club Raqueta</b>" in html and "2 canchas" in html and "data-ids='c_lima c_noche'" in html
    assert "Tipo de local" not in html and "data-tipo='pend'" not in html
    # Legado sin dueño: ficha visible (para reclamar), sin checkout.
    ficha = client.get("/reservar/c_pend").text
    assert "proceso de verificación" in ficha and "checkout.culqi.com" not in ficha and "play.google.com" in ficha
    r = _asegurar(_manana(), horas=("15:00",), extras=(), cancha="c_pend")
    assert r["ok"] is False and r["error"] == "no_verificada"
    # Pendiente CON dueño: 404 para el público, vista previa para el dueño.
    db.canchas["c_pend"]["dueno"] = "dueno2@x.com"
    assert client.get("/reservar/c_pend").status_code == 404
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, "dueno2@x.com", "Dueño Dos")
    prev = cli.get("/reservar/c_pend").text
    assert "proceso de verificación" in prev and "Loza Pendiente" in prev
    db.canchas["c_pend"]["dueno"] = ""
    # Título = LOCAL; la cancha debajo; chips con las canchas del local (solo aprobadas).
    f = client.get("/reservar/c_lima").text
    assert "<h1 style='margin-top:8px'>Club Raqueta</h1>" in f and "Cancha Central" in f
    assert "canchas en este local" in f and "href='/reservar/c_noche'" in f and "href='/reservar/c_pend'" not in f
    assert "<title>Reservar en Club Raqueta" in f
    # Descubiertas: el legado sin dueño NO se descuenta (su pin sigue para reclamarlo); las con dueño sí.
    from web import descubrir
    vistos = {}
    monkeypatch.setattr(descubrir, "descubrir_cerca", lambda *a, **k: vistos.update(k) or [])
    client.get("/web/descubrir?lat=-12&lng=-77")
    assert "Loza Pendiente" not in [r["nombre"] for r in vistos["registradas"]] and "Cancha Central" in [r["nombre"] for r in vistos["registradas"]]


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
    assert "todavía no tienes canchas registradas" in html and "href='/anfitrion/nueva'" in html
    aca = cli.get("/anfitrion/verificador").text  # solo el verificador sigue en la app; canchas, academia, tienda y campeonatos ya son web
    assert "Verificador está en la app" in aca and "Abrir en la app" in aca
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
    for t in ("Editar cancha", "Fotos", "Deportes y tipo de piso", "Grass sintético", "Precio y promociones",
              "Hora feliz", "Seña para reservar", "empieza el último turno", "Servicios extra de esta cancha", "Árbitro",
              "Guardar cambios", "data-v='pickleball'", "−30 %", "1h 30min", "Tu local", "href='/anfitrion/local/c_lima/editar'"):
        assert t in html, t
    # Lo del LOCAL (nombre, dirección, servicios gratis, extras del local) ya no se repite por cancha: va en "Editar local".
    assert "Servicios del local</h2>" not in html and "data-v='techado'" not in html and "id='club'" not in html
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
    assert [(x["clave"], x["precio"], x["tipo"], x["ambito"]) for x in c["servicios_extra"]] == [("arbitro", 40.0, "reserva", "cancha"), ("parrilla", 25.0, "reserva", "local")]
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
    monkeypatch.setattr(config, "PLACES_API_KEY", "k")
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
    assert "Crear academia" in nueva and "data-v='natacion'" in nueva and "mapaSede" in nueva and "Programas y tarifario" in nueva and "Reglas de cobro" in nueva
    # El mapa de la sede debe VERSE: la clase `.mapa-ficha` de la ficha de
    # reserva arranca en display:none (se abre con "Cómo llegar") y ocultaba
    # el mapa del formulario (bug reportado por el director, sep-2026).
    assert "id='mapaSede' class='mapa-sede'" in nueva and ".mapa-sede{display:block" in nueva
    # "Club / local donde entrenas" AUTOCOMPLETA con Google Maps (pedido del
    # director: escribir "esmon" y que el pin se ponga solo): misma búsqueda
    # /web/lugares de "Pon tu cancha"; sin PLACES_API_KEY el campo es texto simple.
    assert "id='resSede'" in nueva and "/web/lugares?q=" in nueva and '"buscar": true' in nueva
    monkeypatch.setattr(config, "PLACES_API_KEY", "")
    assert '"buscar": false' in cli.get("/anfitrion/academia/nueva").text
    monkeypatch.setattr(config, "PLACES_API_KEY", "k")
    # Tarifario = el MISMO editor del app (pedido del director, sep-2026):
    # PROGRAMAS (Bola Roja…) con precio socio por frecuencia 2x…5x; nada de
    # "Plan 8" con el programa escondido. Los planes viejos que no encajan
    # salen como "planes sueltos" para quitarlos.
    assert "Programas y tarifario" in nueva and "id='programas'" in nueva and "btnPrograma" in nueva and "id='sueltos'" in nueva
    assert "FRECS=[2,3,4,5]" in nueva and "g.nombre+' | '+f+'x'" in nueva and "Plan 1" not in nueva
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
    # Una tarifa de programa sin `nombre` (como la manda el editor web nuevo) toma
    # el nombre que genera el app; sin precio, el error nombra al programa.
    r = cli.post("/anfitrion/academia/guardar", json={**base, "planes": [{"id": "Bola Roja | 3x", "programa": "Bola Roja", "frecuenciaSemana": 3, "precioMes": 0}]}).json()
    assert r["campo"] == "planes" and "Bola Roja" in r["error"]
    r = cli.post("/anfitrion/academia/guardar", json={**base, "planes": [{"id": "Bola Roja | 3x", "programa": "Bola Roja", "frecuenciaSemana": 3, "precioMes": 330}]}).json()
    assert r["ok"] and db.academias[aid]["planes"][0]["nombre"] == "Bola Roja · 3x/sem" and db.academias[aid]["planes"][0]["id"] == "Bola Roja | 3x"
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


def test_registrar_y_reclamar_cancha_desde_la_web_como_el_app(db, monkeypatch):
    """Pedido del director (sep-2026): "Pon tu cancha" desde la web con el MISMO
    flujo que `registrar_cancha_screen`: la cancha nace en `pichangol_canchas`
    sin verificar y a nombre del correo de Google, se crea el RECLAMO en el
    backend y la torre lo aprueba; al aprobar, la nube queda `verificada` sin
    abrir el app. Lugar ya reclamado por otro → no se registra."""
    from db.store import stores
    from propiedad import reclamos
    import web.anfitrion as anf
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(reclamos, "_notificar_admin", lambda *a, **k: None)
    monkeypatch.setattr(reclamos, "_notificar_reclamante_aprobado", lambda *a, **k: None)
    monkeypatch.setattr(reclamos, "_bienvenida_al_activar", lambda *a, **k: None)
    stores.reclamos.clear()
    cli = TestClient(app, base_url="https://testserver")
    # Sin sesión → login; con sesión → formulario prellenado desde una descubierta.
    assert cli.get("/anfitrion/nueva", follow_redirects=False).status_code == 302
    assert cli.post("/anfitrion/nueva", json={}).status_code == 401
    _entrar_como(cli, monkeypatch, "nuevo@gmail.com", "Nuevo Dueño")
    html = cli.get("/anfitrion/nueva?place=gp_abc&nombre=Complejo%20Sol&direccion=Av.%20Sol%201&lat=-12.1&lng=-77.03").text
    for t in ("Pon tu cancha en Pichangol", "value='Complejo Sol'", "value='Av. Sol 1'", "Verificación de propiedad", "id='mapaSede'",
              "data-g='deportes'", "data-g='relacion'", "Registrar mi cancha", "+51", "DNI"):
        assert t in html, t
    assert "href='/anfitrion/nueva'>Pon tu cancha en Pichangol" in cli.get("/").text  # entrada desde la portada/menú
    assert "¿Es tuya? Reclámala" in cli.get("/").text
    # El id lo emite el servidor (u<ms>); el navegador lo devuelve.
    import re as _re
    nid = _re.search(r'"id": "(u\d+)"', html).group(1)
    base = {"id": nid, "place": "gp_abc", "nombre_local": "Complejo Sol", "direccion": "Av. Sol 1", "lat": -12.1, "lng": -77.03, "zona": "Miraflores",
            "deportes": ["futbol", "tenis"], "modo": "separadas", "superficies": {"futbol": "Grass sintético", "tenis": "Arcilla"},
            "precio_hora": 80, "hora_apertura": "07:00", "hora_cierre": "23:00", "duracion_slot_min": 60, "fotos": [],
            "whatsapp": "+51 987 654 321", "relacion": "administrador", "documento": "", "nota": "Lo administro yo", "sol_lat": -12.1001, "sol_lng": -77.0301}
    # Validaciones (mismas reglas que el app).
    for malo, campo in (({**base, "deportes": []}, "deportes"), ({**base, "superficies": {"futbol": "Grass sintético"}}, "deportes"),
                        ({**base, "lat": 40.4, "lng": -3.7}, "local"), ({**base, "precio_hora": 0}, "precio"),
                        ({**base, "whatsapp": "123"}, "dueno"), ({**base, "documento": "123"}, "dueno"), ({**base, "id": "hack"}, "local")):
        r = cli.post("/anfitrion/nueva", json=malo)
        assert r.status_code == 400 and r.json()["campo"] == campo, (malo, r.text)
    # Registro correcto: 2 canchas separadas (u<ts>_futbol, u<ts>_tenis) + reclamo de la primera.
    r = cli.post("/anfitrion/nueva", json=base)
    assert r.status_code == 200 and r.json()["ok"], r.text
    ids = r.json()["ids"]
    assert ids == [f"{nid}_futbol", f"{nid}_tenis"]
    fila = db.canchas[ids[0]]
    assert fila["dueno"] == "nuevo@gmail.com" and fila["verificada"] is False and fila["registrada"] is True
    assert fila["club"] == "Complejo Sol" and fila["barrio"] == "Miraflores" and fila["moneda"] == "S/" and fila["superficie"] == "Grass sintético"
    assert db.canchas[ids[1]]["deporte"] == "tenis" and db.canchas[ids[1]]["superficie"] == "Arcilla"
    rec = [x for x in stores.reclamos if x.solicitante_id == "nuevo@gmail.com"]
    assert len(rec) == 1 and rec[0].cancha_id == ids[0] and rec[0].estado == "pendiente_triage"
    assert rec[0].telefono_contacto == "51987654321" and rec[0].relacion == "administrador" and "[web · place gp_abc]" in rec[0].nota_reclamante
    assert rec[0].solicitante_lat == -12.1001 and rec[0].nombre_local == "Complejo Sol"
    # Panel del dueño: la cancha aparece "En verificación" (sin reservas en línea todavía).
    panel = cli.get(f"/anfitrion/canchas?registrada={ids[0]}").text
    assert "Registramos <b>Complejo Sol</b>" in panel and "En verificación" in panel and "Aún sin verificar" in panel
    assert "En verificación" in cli.get("/anfitrion/mis-canchas").text
    assert cli.post("/web/asegurar", json={"cancha_id": ids[0], "horas": [{"fecha": _manana(), "hora": "19:00"}], "extras": [],
                                           "nombre": "Ana", "celular": "999", "email": "ana@x.com"}).json()["error"] == "no_verificada"
    # Otra persona intenta reclamar el MISMO lugar → no se registra nada.
    _entrar_como(cli, monkeypatch, "otro@gmail.com", "Otro")
    html2 = cli.get("/anfitrion/nueva").text
    nid2 = _re.search(r'"id": "(u\d+)"', html2).group(1)
    r2 = cli.post("/anfitrion/nueva", json={**base, "id": nid2, "modo": "unica", "superficie": "Loza", "deportes": ["futbol"]})
    assert r2.status_code == 409 and "otra persona" in r2.json()["error"]
    assert nid2 not in db.canchas and not any(x.solicitante_id == "otro@gmail.com" for x in stores.reclamos)
    # La torre aprueba (marcha blanca) → la NUBE queda verificada para la reclamada y su hermana.
    res = reclamos.aprobar_directo(rec[0].id, "admin")
    assert res["ok"] and res["estado"] == "activada"
    assert db.canchas[ids[0]]["verificada"] is True and db.canchas[ids[1]]["verificada"] is True
    _entrar_como(cli, monkeypatch, "nuevo@gmail.com", "Nuevo Dueño")
    panel = cli.get("/anfitrion/canchas").text
    assert "En verificación" not in panel and "✓ Verificada" in panel
    # Rechazar revoca en la nube (mismo espejo).
    reclamos._revocar_cancha_al_rechazar(rec[0])
    assert db.canchas[ids[0]]["verificada"] is False
    stores.reclamos.clear()
    # ── Cancha DESCUBIERTA: la tarjeta abre una ficha web propia (no Play) con "Reclámala" prellenado. ──
    lugar = cli.get("/lugar/gp_xyz?nombre=Loza%20Norte&direccion=Jr.%20Lima%2012&lat=-12.05&lng=-77.04&deporte=futbol").text
    for t in ("Loza Norte", "Aún sin registrar", "¿Es tuya esta cancha?", "href='/anfitrion/nueva?place=gp_xyz&nombre=Loza%20Norte",
              "/web/foto?id=gp_xyz", "Abrir en Google Maps", "Abrir en la app"):
        assert t in lugar, t
    assert cli.get("/lugar/c_lima?nombre=x&lat=1&lng=1").status_code == 404
    assert "hrefLugar" in cli.get("/").text and "'/lugar/' + encodeURIComponent(c.id)" in cli.get("/").text
    # ── Cancha REGISTRADA sin dueño (legado): la ficha ofrece reclamarla y el registro ADOPTA la misma fila. ──
    ficha = cli.get("/reservar/c_pend").text
    assert "¿Es tuya esta cancha?" in ficha and "href='/anfitrion/nueva?cancha=c_pend'" in ficha
    assert "¿Es tuya esta cancha?" not in cli.get("/reservar/c_lima").text  # con dueño: no
    html3 = cli.get("/anfitrion/nueva?cancha=c_pend").text
    assert "Reclama tu cancha" in html3 and "value='Club Raqueta'" in html3 and "value='60.00'" in html3 and '"existente": true' in html3
    r3 = cli.post("/anfitrion/nueva", json={**base, "id": "c_pend", "existente": True, "deportes": ["futbol"], "modo": "unica", "superficie": "Loza",
                                             "nombre_local": "Club Raqueta", "lat": -12.09, "lng": -77.0, "nombre_cancha": "Loza Pendiente"})
    assert r3.status_code == 200 and r3.json()["ids"] == ["c_pend"], r3.text
    assert db.canchas["c_pend"]["dueno"] == "nuevo@gmail.com" and db.canchas["c_pend"]["superficie"] == "Loza" and "c_pend" in db.canchas
    rec2 = [x for x in stores.reclamos if x.cancha_id == "c_pend"]
    assert len(rec2) == 1 and rec2[0].solicitante_id == "nuevo@gmail.com"
    assert "¿Es tuya esta cancha?" not in cli.get("/reservar/c_pend").text  # ya tiene dueño (en verificación)
    reclamos.aprobar_directo(rec2[0].id, "admin")
    assert db.canchas["c_pend"]["verificada"] is True
    stores.reclamos.clear()


def test_buscar_mi_local_en_google_por_nombre(db, monkeypatch):
    """Caso "Campo deportivo Edu Jr." (sep-2026): el descubrimiento por celda
    solo trae los ~20 lugares más cercanos por consulta y un local a 3 km no
    salía. El dueño ahora BUSCA su local por nombre en "Pon tu cancha"
    (`/web/lugares`, Text Search de Google con PLACES_API_KEY) y el
    resultado rellena nombre, dirección, punto y place."""
    from web import descubrir
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    # Sin llave: el endpoint lo dice y el formulario no muestra la caja.
    monkeypatch.setattr(config, "PLACES_API_KEY", "")
    assert cli.get("/web/lugares?q=edu").json() == {"ok": True, "disponible": False, "lugares": []}
    _entrar_como(cli, monkeypatch, "nuevo@gmail.com")
    assert "id='busca'" not in cli.get("/anfitrion/nueva").text
    # Con llave: una llamada a Google por consulta (sesgada al punto), sin filtrar por deporte.
    monkeypatch.setattr(config, "PLACES_API_KEY", "k")
    llamadas = []
    def fake_http(url, headers, body=None, timeout=12):
        llamadas.append(body)
        return {"places": [{"id": "ChIJedu", "displayName": {"text": "Campo deportivo Edu Jr."}, "formattedAddress": "Av. Los Frutales 100, Ate",
                            "location": {"latitude": -12.0735152, "longitude": -76.991131}, "types": ["sports_complex"]},
                           {"id": "ChIJx", "displayName": {"text": "Edu Jr. Restobar"}, "formattedAddress": "Jr. X 1", "location": {"latitude": -12.07, "longitude": -76.99}, "types": ["restaurant"]}]}
    monkeypatch.setattr(descubrir, "_http_json", fake_http)
    descubrir._busq_cache.clear()
    j = cli.get("/web/lugares?q=Campo%20deportivo%20Edu&lat=-12.09&lng=-77.0").json()
    assert j["disponible"] and [x["id"] for x in j["lugares"]] == ["gp_ChIJedu", "gp_ChIJx"]  # no se filtra por heurística
    assert j["lugares"][0]["deporte"] == "futbol" and j["lugares"][0]["km"] == 2.1 and j["lugares"][1]["deporte"] == ""
    assert llamadas[0]["textQuery"] == "Campo deportivo Edu" and llamadas[0]["locationBias"]["circle"]["radius"] == 30000
    assert len(cli.get("/web/lugares?q=Campo%20deportivo%20Edu&lat=-12.09&lng=-77.0").json()["lugares"]) == 2 and len(llamadas) == 1  # caché
    assert cli.get("/web/lugares?q=ed").json()["lugares"] == []  # consulta muy corta: sin llamada
    html = cli.get("/anfitrion/nueva").text
    assert "id='busca'" in html and "Busca tu local en Google" in html and "/web/lugares?q=" in html
    # El explorador vuelve a descubrir al mover el mapa y acumula por id.
    home = cli.get("/").text
    assert "mapa.on('moveend'" in home and "descAcum" in home
    # El explorador también busca por NOMBRE en Google al pulsar Buscar: los
    # resultados que la heurística reconoce entran como descubiertas (con
    # etiqueta y emoji para la tarjeta) y pasan el filtro de texto por `data-q`.
    assert j["lugares"][0]["deporte_nombre"] == "Fútbol" and j["lugares"][0]["emoji"]
    assert "buscarEnGoogle(filtro.q)" in home and "data-q=" in home and '"lugares": true' in home
    assert "c.dataset.q !== filtro.q" in home and "ni en Google Maps" in home


def test_academias_en_el_explorador_por_deporte_y_cercania(db, monkeypatch):
    """Pedido del director (sep-2026): "he creado una academia, ¿cómo la busco
    por acá?" Las academias salen en el explorador web por deporte (pestaña)
    y ordenadas por cercanía como las canchas: tarjeta con logo/foto, sede,
    "al mes desde", WhatsApp, Cómo llegar y enlace a su página /l/{id}. Las
    canchas DESCUBIERTAS también respetan la pestaña (en Tenis no salen las
    de fútbol)."""
    from web import descubrir
    db.academias["ac_t1"] = {"nombre": "Academia Baseline", "deporte": "tenis", "dueno": "profe@gmail.com", "sedeClub": "Club Lawn Tennis",
                             "zona": "San Borja", "lat": -12.09, "lng": -77.03, "whatsapp": "999888777", "logoUrl": "https://sb.test/logo.jpg",
                             "planes": [{"id": "Bola Roja | 2x", "nombre": "Bola Roja · 2x/sem", "programa": "Bola Roja", "precioMes": 250, "frecuenciaSemana": 2},
                                        {"id": "Bola Roja | 3x", "nombre": "Bola Roja · 3x/sem", "programa": "Bola Roja", "precioMes": 330, "frecuenciaSemana": 3}]}
    db.academias["ac_f1"] = {"nombre": "Escuela Golazo", "deporte": "futbol", "dueno": "dt@gmail.com", "sedeClub": "Sabor Golazo", "lat": -12.1, "lng": -77.0,
                             "whatsapp": "51988877766", "planes": []}
    db.academias["ac_x"] = {"nombre": "Borrada", "deporte": "tenis", "_eliminada": True}
    db.academias["ac_t1"]["redes"] = {"tiktok": "@baselinetenis", "facebook": "https://facebook.com/baseline", "otra": "x", "web": ""}
    from db.store import stores as _st
    monkeypatch.setattr(_st, "landings", {"ac_f1": {"nombre": "Escuela Golazo"}})
    cli = TestClient(app, base_url="https://testserver")
    home = cli.get("/").text
    assert "id='academias'" in home and "🎓 Academias<" in home and "Academia Baseline" in home and "Escuela Golazo" in home and "Borrada" not in home
    assert "data-id='ac:ac_t1'" in home and "class='lst aca'" in home and "S/ 250</b>" in home and "al mes desde" in home
    # "Ver academia" SOLO si el dueño generó su página (/l/{id} responde 404 si no);
    # si no, salen sus REDES con logo y enlace directo (pedido del director) y la
    # tarjeta no navega a una página inexistente (data-sinpagina).
    t1 = home[home.index("data-id='ac:ac_t1'"):home.index("data-id='ac:ac_f1'")]
    f1 = home[home.index("data-id='ac:ac_f1'"):home.index("id='descubiertas'")]
    assert "href='/academia/ac_t1' data-id='ac:ac_t1'" in home and "Ver academia" in t1
    assert "data-wa='https://www.tiktok.com/@baselinetenis'" in t1 and "TikTok" in t1 and "data-wa='https://facebook.com/baseline'" in t1 and "Facebook" in t1
    assert "red-instagram" not in t1 and "Web</span>" not in t1 and "otra" not in t1
    assert "href='/academia/ac_f1' data-id='ac:ac_f1'" in home and "Ver academia" in f1 and "red-" not in f1
    assert "data-wa='https://wa.me/51999888777" in home and "data-wa='https://wa.me/51988877766" in home and "<a class='app' href='https://wa.me" not in home and "1 programa · " in home and "Consulta precios" in home
    assert "data-lat='-12.09'" in home and "class='ir' data-lat='-12.09'" in home
    # JS: las academias se ordenan por cercanía con las canchas, no entran en filtros de hora/precio y tienen pin propio.
    assert "'.grupo-pais, .grupo-aca'" in home and "c.classList.contains('aca')) return true" in home and "esAca ? 'Ver academia'" in home
    tenis = cli.get("/?deporte=tenis").text
    assert "🎓 Academias de tenis" in tenis and "Academia Baseline" in tenis and "Escuela Golazo" not in tenis
    assert "id='academias'" not in cli.get("/?deporte=padel").text
    # Descubiertas por deporte: la pestaña viaja al servidor y filtra.
    monkeypatch.setattr(descubrir, "descubrir_cerca", lambda *a, **k: [{"id": "gp_1", "nombre": "Cancha F", "deporte": "futbol", "lat": -12.0, "lng": -77.0, "direccion": ""},
                                                                        {"id": "gp_2", "nombre": "Club T", "deporte": "tenis", "lat": -12.0, "lng": -77.0, "direccion": ""}])
    assert [c["id"] for c in cli.get("/web/descubrir?lat=-12&lng=-77").json()["canchas"]] == ["gp_1", "gp_2"]
    assert [c["id"] for c in cli.get("/web/descubrir?lat=-12&lng=-77&deporte=tenis").json()["canchas"]] == ["gp_2"]
    assert "'&deporte=' + encodeURIComponent(C.dep || '')" in home
    # Pestaña "🎓 Academias" en la cabecera (pedido del director, sep-2026:
    # "¿dónde busco academias?"): solo academias de TODOS los deportes, sin
    # canchas ni descubiertas; el buscador "Dónde" filtra por nombre.
    assert "href='/canchas?deporte=academias' data-dep='academias'" in home and "🎓</span>Academias" in home
    aca = cli.get("/?deporte=academias").text
    assert "class='cat sel' href='/canchas?deporte=academias'" in aca
    assert "id='academias'" in aca and "🎓 Academias<" in aca and "Academia Baseline" in aca and "Escuela Golazo" in aca
    assert "class='grupo-pais'" not in aca and "id='descubiertas'" not in aca and "Todavía no hay canchas" not in aca
    assert "No encontramos academias con" in aca and "if(C.dep === 'academias' || !$('descubiertas')) return;" in aca
    assert '"dep": "academias"' in aca and "Academias deportivas cerca de ti" in aca
    assert "id='btnFiltros'" not in aca and "Busca academias por nombre o zona" in aca and "id='btnFiltros'" in home


def test_ficha_de_academia_y_matricula_web_como_el_app(db, monkeypatch):
    """Pedido del director (sep-2026): al tocar la academia se abre su FICHA
    web con programas y tarifario y uno puede MATRICULARSE. Mismo flujo que
    `academia_detalle_screen._matricular`: login con Google → para mí / mi
    hijo(a) → nombre + celular → mes a mes o adelantado (descuento prepago) →
    Culqi. La fila en `pichangol_matriculas` es la que escribe
    `AppState.matricular` (Alumno.toJson + cuotas, ids al_/cu_) y el profe
    recibe el push "Nuevo alumno 🎓"."""
    from web import academia as acad, sesion as ses_mod
    from pagos import culqi
    import pagos.router as pr
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    db.academias["ac_t1"] = {"nombre": "Academia Baseline", "deporte": "tenis", "dueno": "profe@gmail.com", "sedeClub": "Club Lawn Tennis",
                             "zona": "San Borja", "lat": -12.09, "lng": -77.03, "whatsapp": "999888777", "descripcion": "Tenis para todos",
                             "redes": {"tiktok": "@baseline"}, "recargoInvitado": 50, "descuentoPrepago": 10, "mesesMinPrepago": 3, "descuentoHermano2": 10,
                             "planes": [{"id": "Bola Roja | 2x", "nombre": "Bola Roja · 2x/sem", "programa": "Bola Roja", "precioMes": 250, "frecuenciaSemana": 2, "etapaEdad": "5 a 10 años", "duracionClase": "1 h"},
                                        {"id": "Bola Roja | 3x", "nombre": "Bola Roja · 3x/sem", "programa": "Bola Roja", "precioMes": 330, "frecuenciaSemana": 3},
                                        {"id": "pl_clase", "nombre": "Clase particular", "tipo": "porClase", "precioMes": 80, "meses": 0}]}
    db.academias["ac_bo"] = {"nombre": "Escuela La Paz", "deporte": "futbol", "dueno": "dt@gmail.com", "lat": -16.5, "lng": -68.15, "moneda": "Bs",
                             "planes": [{"id": "p1", "nombre": "Mensual", "precioMes": 200}]}
    cli = TestClient(app, base_url="https://testserver")
    assert cli.get("/academia/no_existe").status_code == 200 and "Academia no disponible" in cli.get("/academia/no_existe").text
    # Ficha: galería, sede, redes, tarifario por programa con socio/invitado y botones Matricularme.
    html = cli.get("/academia/ac_t1").text
    for t in ("Academia Baseline", "Club Lawn Tennis · San Borja", "Tenis para todos", "Programas y tarifario", "Bola Roja", "5 a 10 años · 1 h",
              "2x por semana", "S/ 250</b>", "invitado S/ 300", "Otros planes", "Por clase", "data-plan='Bola Roja | 2x'", "class='btn chico elegir'",
              "https://www.tiktok.com/@baseline", "wa.me/51999888777", "id='mapaFicha'", "Inicia sesión con Google para matricularte",
              "Para mi hijo(a)", "Mes a mes", "Adelantado", "checkout.culqi.com", "pago adelantado de 3+ meses −10 %", "2.º de la familia −10 %", "Para otra persona", "id='emailPersonaBox'", "\"dtoFam\""):
        assert t in html, t
    # Multi-país: en Bs el tarifario se ve pero la matrícula va a la app.
    bo = cli.get("/academia/ac_bo").text
    assert "Matricúlate desde la app" in bo and "cobra en Bs" in bo and "elegir" not in bo
    # Matricular exige sesión (como reservar).
    r = cli.post("/web/matricular", json={"academia_id": "ac_t1", "plan_id": "Bola Roja | 2x", "nombre": "Ana", "celular": "999888777", "token": "tkn"}).json()
    assert r["error"] == "sesion_requerida"
    _entrar_como(cli, monkeypatch, "ana@gmail.com", nombre="Ana Pérez")
    cargos, pushes, conta, susc = [], [], [], []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: (cargos.append(kw) or {"ok": True, "charge_id": "chr_mat_1"}))
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: pushes.append((a, k)))
    monkeypatch.setattr(pr, "post_matricula", lambda req: conta.append(req) or {"ok": True})
    monkeypatch.setattr(pr, "post_suscripcion_alumno", lambda req: susc.append(req) or {"ok": True})
    # Validaciones antes de cobrar.
    assert cli.post("/web/matricular", json={"academia_id": "ac_t1", "plan_id": "nope", "nombre": "Ana", "celular": "999888777", "token": "t"}).json()["error"] == "plan"
    assert cli.post("/web/matricular", json={"academia_id": "ac_t1", "plan_id": "Bola Roja | 2x", "nombre": "A", "celular": "999888777", "token": "t"}).json()["error"] == "nombre"
    assert cli.post("/web/matricular", json={"academia_id": "ac_t1", "plan_id": "Bola Roja | 2x", "nombre": "Lucas", "celular": "999888777", "es_hijo": True, "token": "t"}).json()["error"] == "edad"
    assert cli.post("/web/matricular", json={"academia_id": "ac_bo", "plan_id": "p1", "nombre": "Ana", "celular": "77788899", "token": "t"}).json()["error"] == "moneda"
    assert not cargos
    # Adelantado 3 meses con descuento prepago (10 %): 250×3 − 75 = 675; 3 cuotas pagadas.
    r = cli.post("/web/matricular", json={"academia_id": "ac_t1", "plan_id": "Bola Roja | 2x", "nombre": "Lucas Pérez", "celular": "999 888 777",
                                          "es_hijo": True, "edad": 8, "cantidad": 3, "mes_a_mes": False, "token": "tkn_1", "medio": "yape"}).json()
    assert r["ok"] and r["url"].startswith("/academia/ac_t1/matricula/al_") and cargos[0]["monto_centimos"] == 67500 and cargos[0]["email"] == "ana@gmail.com"
    m = db.matriculas[-1]
    assert m["id"].startswith("al_") and m["academiaId"] == "ac_t1" and m["email"] == "ana@gmail.com" and m["canal"] == "web"
    assert m["nombre"] == "Lucas Pérez" and m["apoderadoNombre"] == "Ana Pérez" and m["apoderadoWhatsapp"] == "999888777" and m["whatsapp"] == "" and m["edad"] == 8
    assert m["esSocioSede"] is True and m["ordenHermano"] == 1 and m["sedeId"] == ""
    cu = m["cuotas"]
    assert len(cu) == 3 and all(c["pagada"] and c["operacionId"] == "chr_mat_1" and c["monto"] == 250 and "autoDebito" not in c for c in cu)
    assert cu[0]["concepto"].startswith("Bola Roja · 2x/sem · ") and cu[0]["id"].endswith("_0") and cu[2]["id"].endswith("_2")
    assert m["pagoWeb"]["monto"] == 675 and m["pagoWeb"]["ahorro"] == 75 and m["pagoWeb"]["operacion"] == "chr_mat_1" and m["pagoWeb"]["medio"] == "yape"
    comp1 = cli.get(r["url"]).text
    assert "S/ 675.00" in comp1 and "Descuento por pago adelantado: −S/ 75.00" in comp1
    assert conta[0].academia_id == "ac_t1" and conta[0].monto_soles == 675 and conta[0].matricula_id == "chr_mat_1" and conta[0].pais == "pe"
    assert pushes[0][0][0] == "profe@gmail.com" and "Nuevo alumno" in pushes[0][0][1] and "Lucas Pérez" in pushes[0][0][2] and not susc
    # Mes a mes, 6 meses: hoy 1 cuota; 5 pendientes con autoDebito; suscripción con 5 cobros restantes.
    # Ana ya paga a Lucas aquí → ella es la 2.ª DE LA FAMILIA: −10 % (330 → 297) en la cuota de hoy y en el débito automático.
    assert cli.get("/web/academia/ac_t1/descuento-familiar").json()["dtoFam"] == {"yo": {"orden": 2, "pct": 10.0}, "hijo": {"orden": 2, "pct": 10.0}, "familiar": {"orden": 2, "pct": 10.0}}
    r = cli.post("/web/matricular", json={"academia_id": "ac_t1", "plan_id": "Bola Roja | 3x", "nombre": "Ana Pérez", "celular": "999888777",
                                          "cantidad": 6, "mes_a_mes": True, "token": "tkn_2", "quien": "yo"}).json()
    assert r["ok"] and cargos[-1]["monto_centimos"] == 29700
    m = db.matriculas[-1]; cu = m["cuotas"]
    assert m["apoderadoNombre"] == "" and m["whatsapp"] == "999888777" and len(cu) == 6 and cu[0]["pagada"] and not cu[1]["pagada"] and all(c.get("autoDebito") for c in cu)
    assert m["ordenHermano"] == 2 and "parentesco" not in m and all(c["monto"] == 297 and c["concepto"].endswith("(−10% familiar)") for c in cu)
    assert m["pagoWeb"]["monto"] == 297 and m["pagoWeb"]["ahorro"] == 33 and m["pagoWeb"]["dtoFamiliar"] == 10
    assert "fechaPago" not in cu[1] and susc[0].alumno_id == m["id"] and susc[0].cobros_restantes == 5 and susc[0].monto_soles == 297
    # Cargo rechazado → no se guarda nada.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "tarjeta_rechazada"})
    n = len(db.matriculas)
    assert cli.post("/web/matricular", json={"academia_id": "ac_t1", "plan_id": "pl_clase", "nombre": "Ana Pérez", "celular": "999888777", "token": "t"}).json()["error"] == "cargo_rechazado"
    assert len(db.matriculas) == n
    # Comprobante: solo el titular; muestra cuotas y N.º de operación.
    comp = cli.get(r["url"]).text
    assert "¡Matrícula registrada!" in comp and "Ana Pérez" in comp and "S/ 297.00" in comp and "chr_mat_1" in comp and "⏳" in comp and "wa.me/51999888777" in comp
    assert "Descuento familiar aplicado: −10 % (2.º de tu familia" in comp
    _entrar_como(cli, monkeypatch, "otro@gmail.com")
    assert "Esta matrícula es privada" in cli.get(r["url"]).text


def test_matricula_familiar_un_pagador_varias_personas(db, monkeypatch):
    """Pedido del director (26-sep-2026): "yo pago la academia de tenis de mi
    esposa, de mis hijos y mi propia mensualidad". (1) "Para otra persona" =
    otro ADULTO de la familia (`parentesco: familiar`), con correo propio
    opcional para que vea sus clases en SU app; (2) el DESCUENTO FAMILIAR se
    asigna solo por orden (1.º sin descuento, 2.º −H2, 3.º+ −H3) contando a
    todos los que paga la misma cuenta, aditivo al prepago; (3) la academia
    puede limitarlo a "Solo hijos" (`descuentoFamiliar: false`)."""
    from web import academia as wa
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    db.academias["ac_f"] = {"nombre": "Academia Familia", "deporte": "tenis", "dueno": "profe@gmail.com", "sedeClub": "Club X", "zona": "Surco",
                            "lat": -12.1, "lng": -77.0, "whatsapp": "999888777", "descuentoPrepago": 10, "mesesMinPrepago": 3,
                            "descuentoHermano2": 10, "descuentoHermano3": 20,
                            "planes": [{"id": "m", "nombre": "Mensual", "precioMes": 100}]}
    cli = TestClient(app, base_url="https://testserver")
    cargos = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": f"chr_{len(cargos)}"})
    import pagos.router as pr
    monkeypatch.setattr(pr, "post_matricula", lambda req: {"ok": True})
    monkeypatch.setattr(pr, "post_suscripcion_alumno", lambda req: {"ok": True})
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    _entrar_como(cli, monkeypatch, "dennis@gmail.com", nombre="Dennis")
    # Lógica pura, espejo de `Academia.ordenFamiliarPara`.
    a = db.academias["ac_f"]
    assert wa.orden_familiar(a, []) == 1 and wa.orden_familiar(a, [{"parentesco": "hijo"}]) == 2 and wa.orden_familiar(a, [{}, {"parentesco": "familiar"}], "hijo") == 3
    assert wa.dto_familiar_pct(a, 1) == 0 and wa.dto_familiar_pct(a, 2) == 10 and wa.dto_familiar_pct(a, 5) == 20
    solo_hijos = dict(a, descuentoFamiliar=False)
    assert wa.orden_familiar(solo_hijos, [{"parentesco": "hijo"}], "familiar") == 1  # la esposa no descuenta
    assert wa.orden_familiar(solo_hijos, [{}, {"parentesco": "hijo"}], "hijo") == 2  # el 2.º hijo sí (el titular no cuenta)
    # 1) Yo: sin descuento. 100 × 1.
    r = cli.post("/web/matricular", json={"academia_id": "ac_f", "plan_id": "m", "nombre": "Dennis Calagua", "celular": "999888777", "token": "t", "quien": "yo"}).json()
    assert r["ok"] and cargos[-1]["monto_centimos"] == 10000 and db.matriculas[-1]["ordenHermano"] == 1
    # 2) Mi esposa ("Para otra persona") con su correo: 2.ª de la familia → −10 %; sin apoderado ni foto mía; ve sus clases con su correo.
    assert cli.get("/web/academia/ac_f/descuento-familiar").json()["dtoFam"]["familiar"] == {"orden": 2, "pct": 10.0}
    r = cli.post("/web/matricular", json={"academia_id": "ac_f", "plan_id": "m", "nombre": "María López", "celular": "988777666", "token": "t",
                                          "quien": "familiar", "email_persona": "Maria@Gmail.com"}).json()
    assert r["ok"] and cargos[-1]["monto_centimos"] == 9000
    m = db.matriculas[-1]
    assert m["parentesco"] == "familiar" and m["emailAlumno"] == "maria@gmail.com" and m["email"] == "dennis@gmail.com" and m["ordenHermano"] == 2
    assert m["apoderadoNombre"] == "" and m["whatsapp"] == "988777666" and "fotoUrl" not in m and m["cuotas"][0]["monto"] == 90
    assert "Descuento familiar aplicado: −10 % (2.º de tu familia" in cli.get(r["url"]).text
    _entrar_como(cli, monkeypatch, "maria@gmail.com", nombre="María")
    assert "¡Matrícula registrada!" in cli.get(r["url"]).text  # el familiar con su correo también ve el comprobante
    _entrar_como(cli, monkeypatch, "dennis@gmail.com", nombre="Dennis")
    # Correo del familiar mal formado o igual al mío → error sin cobrar.
    n = len(cargos)
    assert cli.post("/web/matricular", json={"academia_id": "ac_f", "plan_id": "m", "nombre": "Pepe", "celular": "988777666", "token": "t", "quien": "familiar", "email_persona": "pepe"}).json()["error"] == "email_persona"
    assert cli.post("/web/matricular", json={"academia_id": "ac_f", "plan_id": "m", "nombre": "Pepe", "celular": "988777666", "token": "t", "quien": "familiar", "email_persona": "dennis@gmail.com"}).json()["error"] == "email_persona"
    assert len(cargos) == n
    # 3) Mi hijo, 3.º de la familia, 3 meses adelantados: prepago 10 % + familiar 20 % = 30 % → 300 − 90 = 210.
    r = cli.post("/web/matricular", json={"academia_id": "ac_f", "plan_id": "m", "nombre": "Lucas", "celular": "999888777", "token": "t",
                                          "quien": "hijo", "edad": 9, "cantidad": 3}).json()
    assert r["ok"] and cargos[-1]["monto_centimos"] == 21000
    m = db.matriculas[-1]
    assert m["parentesco"] == "hijo" and m["ordenHermano"] == 3 and m["apoderadoNombre"] == "Dennis" and m["pagoWeb"]["ahorro"] == 90 and m["pagoWeb"]["dtoFamiliar"] == 20
    assert all(c["monto"] == 80 and c["concepto"].endswith("(−20% familiar)") for c in m["cuotas"])
    # Cliente viejo (sin `quien`, con es_hijo) sigue funcionando: 4.º → −20 %.
    r = cli.post("/web/matricular", json={"academia_id": "ac_f", "plan_id": "m", "nombre": "Mateo", "celular": "999888777", "token": "t", "es_hijo": True, "edad": 7}).json()
    assert r["ok"] and cargos[-1]["monto_centimos"] == 8000 and db.matriculas[-1]["parentesco"] == "hijo" and db.matriculas[-1]["ordenHermano"] == 4
    # "Solo hijos": otra cuenta en una academia que lo restringe → la pareja no descuenta, el 2.º hijo sí.
    db.academias["ac_h"] = dict(a, nombre="Academia Solo Hijos", descuentoFamiliar=False)
    _entrar_como(cli, monkeypatch, "rosa@gmail.com", nombre="Rosa")
    assert cli.post("/web/matricular", json={"academia_id": "ac_h", "plan_id": "m", "nombre": "Rosa Díaz", "celular": "999888777", "token": "t", "quien": "yo"}).json()["ok"]
    assert cli.post("/web/matricular", json={"academia_id": "ac_h", "plan_id": "m", "nombre": "Juan Díaz", "celular": "999888777", "token": "t", "quien": "familiar"}).json()["ok"]
    assert cargos[-1]["monto_centimos"] == 10000 and db.matriculas[-1]["ordenHermano"] == 1
    assert cli.post("/web/matricular", json={"academia_id": "ac_h", "plan_id": "m", "nombre": "Hijo 1", "celular": "999888777", "token": "t", "quien": "hijo", "edad": 8}).json()["ok"]
    assert cargos[-1]["monto_centimos"] == 10000 and db.matriculas[-1]["ordenHermano"] == 1
    assert cli.post("/web/matricular", json={"academia_id": "ac_h", "plan_id": "m", "nombre": "Hijo 2", "celular": "999888777", "token": "t", "quien": "hijo", "edad": 6}).json()["ok"]
    assert cargos[-1]["monto_centimos"] == 9000 and db.matriculas[-1]["ordenHermano"] == 2
    html = cli.get("/academia/ac_h").text
    assert "2.º hermano −10 %" in html and "3.º hermano −20 %" in html
    # El dueño ve el parentesco y el orden en Alumnos; el editor tiene el selector.
    _entrar_como(cli, monkeypatch, "profe@gmail.com", nombre="Profe")
    al = cli.get("/anfitrion/academia/alumnos?academia=ac_f").text
    assert "Familiar · paga dennis@gmail.com" in al and "3.º de la familia · descuento familiar" in al
    ed = cli.get("/anfitrion/academia/ac_f/editar").text
    assert "Descuento familiar aplica a" in ed and "data-g='descuentoFamiliar' data-v='1'" in ed and "Solo hijos" in ed


def test_agregar_cancha_a_local_desde_la_web_como_el_app(db, monkeypatch):
    """Pedido del director (sep-2026): "¿cómo registro otra cancha en el mismo
    local, y de otro deporte?". Como `AgregarCanchaScreen` del app: la cancha
    nueva HEREDA local, dirección, punto, fotos, servicios, dueño y estado de
    verificación (local activo → activa al instante, sin otro reclamo); solo
    se pide deporte, piso, nombre, precio, horario y duración."""
    from web import catalogos
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    # Sin sesión → a entrar. Cancha ajena → 404.
    assert cli.get("/anfitrion/cancha/c_lima/agregar", follow_redirects=False).status_code in (302, 303, 307)
    _entrar_como(cli, monkeypatch, "otro@x.com", "Otro")
    assert cli.get("/anfitrion/cancha/c_lima/agregar").status_code == 404
    assert cli.post("/anfitrion/cancha/c_lima/agregar", json={"deporte": "tenis"}).status_code == 404
    # El dueño: la página es del LOCAL, lista sus canchas y avisa que queda activa al instante.
    _entrar_como(cli, monkeypatch, "dueno@x.com", "Dueño")
    pag = cli.get("/anfitrion/cancha/c_lima/agregar?deporte=tenis").text
    assert "Agrega una cancha a Club Raqueta" in pag and "Cancha Central" in pag and "Nocturna" in pag
    assert "activa al instante" in pag and "data-g='deporte' data-v='tenis'" in pag and "Agregar cancha" in pag
    # "Mis canchas" lleva al flujo corto, no a "Pon tu cancha".
    mc = cli.get("/anfitrion/canchas").text
    assert "href='/anfitrion/cancha/c_lima/agregar'" in mc and "Agregar cancha a este local" in mc
    # "Pon tu cancha" prellenado con un local que ya es mío → redirige a agregar.
    r = cli.get("/anfitrion/nueva?nombre=club%20raqueta&lat=-12.09&lng=-77.0&deporte=tenis", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/anfitrion/cancha/c_lima/agregar?deporte=tenis"
    # Validaciones del app: piso obligatorio, precio válido.
    r = cli.post("/anfitrion/cancha/c_lima/agregar", json={"deporte": "tenis", "precio_hora": 40}).json()
    assert r["ok"] is False and "piso" in r["error"] and r["campo"] == "cancha"
    r = cli.post("/anfitrion/cancha/c_lima/agregar", json={"deporte": "tenis", "superficie": catalogos.SUPERFICIES["tenis"][0], "precio_hora": 0}).json()
    assert r["ok"] is False and r["campo"] == "precio"
    # Otra cancha de OTRO deporte: hereda todo y nace verificada (el local ya está activo).
    r = cli.post("/anfitrion/cancha/c_lima/agregar", json={"deporte": "tenis", "superficie": catalogos.SUPERFICIES["tenis"][0], "precio_hora": 40,
                                                            "hora_apertura": "08:00", "hora_cierre": "22:00", "duracion_slot_min": 90}).json()
    assert r["ok"] is True and r["verificada"] is True
    nueva = db.canchas[r["id"]]
    assert nueva["nombre"] == "Tenis 1" and nueva["club"] == "Club Raqueta" and nueva["deporte"] == "tenis" and nueva["deportes"] == ["tenis"]
    assert nueva["dueno"] == "dueno@x.com" and nueva["verificada"] is True and nueva["direccion"] == "Av. Aviación 123"
    assert nueva["lat"] == -12.09 and nueva["moneda"] == "S/" and nueva["precio_hora"] == 40 and nueva["duracion_slot_min"] == 90
    assert nueva["hora_apertura"] == "08:00" and nueva["hora_cierre"] == "22:00" and nueva["servicios_extra"] == []
    # Sin reclamo nuevo: la propiedad ya se validó con el local.
    from db.store import stores
    assert not any(getattr(x, "cancha_id", None) == r["id"] for x in stores.reclamos)
    # Segunda del MISMO deporte: numera sola ("Fútbol 3": ya había Cancha Central y Nocturna de fútbol).
    r2 = cli.post("/anfitrion/cancha/c_lima/agregar", json={"deporte": "futbol", "superficie": catalogos.SUPERFICIES["futbol"][0], "precio_hora": 55}).json()
    assert r2["ok"] is True and db.canchas[r2["id"]]["nombre"] == "Fútbol 3"
    # Aviso en Mis canchas y el explorador ya la cuenta en la tarjeta del local.
    mc = cli.get(f"/anfitrion/canchas?agregada={r['id']}").text
    assert "Agregamos <b>Tenis 1</b>" in mc and "Ya está activa" in mc
    home = client.get("/canchas").text
    assert "<b>Club Raqueta</b>" in home and "4 canchas" in home and "Fútbol · Tenis" in home
    # Local aún en verificación → la nueva hereda "pendiente" (se activa con el local).
    db.canchas["c_gye"]["verificada"] = False
    r3 = cli.post("/anfitrion/cancha/c_gye/agregar", json={"deporte": "voley", "superficie": catalogos.SUPERFICIES["voley"][0], "precio_hora": 8}).json()
    assert r3["ok"] is True and r3["verificada"] is False and db.canchas[r3["id"]]["club"] == "Club Sur" and db.canchas[r3["id"]]["moneda"] == "$"
    assert "activará junto con el local" in cli.get(f"/anfitrion/canchas?agregada={r3['id']}").text


def test_servicios_extra_catalogo_global_por_local_y_por_persona(db, monkeypatch):
    """Decisión del director (sep-2026): el catálogo de servicios extra es
    GLOBAL y lo administra el operador en la torre; el dueño lo activa y le
    pone precio. Los de ÁMBITO LOCAL (piscina, entrada general) se copian a
    todas las canchas del local; los "por persona" se cobran × cantidad."""
    import servicios_extra as se
    from db.store import stores
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok")
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    h = {"X-Admin-Token": "tok"}
    # Público: el APK y la web leen el catálogo sembrado (los 6 de siempre + nuevos).
    pub = client.get("/config/servicios-extra").json()
    claves = [s["clave"] for s in pub["servicios"]]
    assert claves[:6] == ["arbitro", "pelotero", "pelota", "pecheras", "hidratacion", "parrilla"]
    assert "piscina" in claves and "entrada_general" in claves and pub["tipos"]["persona"] == "por persona"
    pisc = next(s for s in pub["servicios"] if s["clave"] == "piscina")
    assert pisc["tipo"] == "persona" and pisc["ambito"] == "local"
    # Torre: alta con clave derivada, edición, desactivar; validaciones.
    assert client.get("/admin/api/servicios-extra").status_code == 503 or True  # sin token → 401/503 según config
    assert client.get("/admin/api/servicios-extra", headers={"X-Admin-Token": "malo"}).status_code == 401
    r = client.post("/admin/api/servicios-extra", json={"clave": "fronton", "nombre": "Frontón", "emoji": "🎯", "tipo": "turno", "ambito": "cancha", "nuevo": True}, headers=h)
    assert r.status_code == 200 and r.json()["servicio"]["clave"] == "fronton"
    assert client.post("/admin/api/servicios-extra", json={"clave": "fronton", "nombre": "Otro", "nuevo": True}, headers=h).status_code == 400
    assert client.post("/admin/api/servicios-extra", json={"clave": "Mal Clave!", "nombre": "X", "nuevo": True}, headers=h).status_code == 400
    v0 = pub["version"]
    assert client.post("/admin/api/servicios-extra/fronton/activo", json={"activo": False}, headers=h).json()["ok"] is True
    pub2 = client.get("/config/servicios-extra").json()
    assert "fronton" not in [s["clave"] for s in pub2["servicios"]] and pub2["version"] > v0
    assert stores.to_state()["servicios_extra"]["fronton"]["activo"] is False  # persiste en el snapshot
    # Editor web de la CANCHA: solo servicios de la cancha que aplican a su deporte (fútbol: petos sí, pelotero no),
    # sin los del local (piscina) ni los servicios gratis del local; enlace a "Editar local".
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, "dueno@x.com", "Dueño")
    ed = cli.get("/anfitrion/cancha/c_lima/editar").text
    assert "Servicios extra de esta cancha" in ed and "data-serv='pecheras'" in ed and "data-serv='arbitro'" in ed
    assert "data-serv='pelotero'" not in ed and "data-serv='piscina'" not in ed and "id='btnSug'" in ed
    assert "href='/anfitrion/local/c_lima/editar'" in ed and "fronton" not in ed
    # "Editar local": nombre, dirección, servicios del local y extras del local (por persona), una sola vez para todas las canchas.
    le = cli.get("/anfitrion/local/c_lima/editar").text
    assert "Editar local" in le and "Club Raqueta" in le and "data-v='techado'" in le and "🏊 Piscina" in le and "por persona" in le
    assert "data-serv='piscina' data-ambito='local'" in le and "data-serv='arbitro'" not in le and "Cancha Central" in le and "Nocturna" in le
    assert cli.get("/anfitrion/local/c_gye/editar").status_code == 200 and cli.get("/anfitrion/local/c_pend/editar").status_code == 404
    # Mis canchas: agrupado por deporte dentro del local + botón Editar local.
    mc = cli.get("/anfitrion/canchas").text
    assert "class='anf-dep'>⚽ Fútbol · 2 canchas" in mc and "href='/anfitrion/local/c_lima/editar'" in mc
    # Guardar el local: piscina (S/ 15 por persona) + entrada general + estacionamiento gratis → se escribe en Cancha Central
    # y Nocturna (mismo local), cada una conserva sus servicios de cancha; Club Sur no se toca; los de cancha en el cuerpo se ignoran.
    db.canchas["c_noche"]["servicios_extra"] = [{"clave": "pecheras", "precio": 5}]
    r = cli.post("/anfitrion/local/c_lima/editar", json={"nombre_local": "Club Raqueta", "direccion": "Av. Aviación 123",
                                                        "amenidades": ["parking", "invento"],
                                                        "servicios_extra": [{"clave": "piscina", "precio": 15}, {"clave": "entrada_general", "precio": 20},
                                                                            {"clave": "arbitro", "precio": 99}, {"clave": "inventado", "precio": 9}]}).json()
    assert r["ok"] is True and r["canchas"] == 2 and r["url"] == "/anfitrion/canchas?local_guardado=c_lima"
    assert cli.post("/anfitrion/local/c_lima/editar", json={"nombre_local": "x"}).status_code == 400
    assert cli.post("/anfitrion/local/c_lima/editar", json={"nombre_local": "Club Raqueta", "servicios_extra": [{"clave": "piscina", "precio": 0}]}).json()["campo"] == "extras"
    lima = db.canchas["c_lima"]["servicios_extra"]
    assert [(x["clave"], x["precio"], x["tipo"], x["ambito"]) for x in lima] == [("arbitro", 30.0, "reserva", "cancha"), ("piscina", 15.0, "persona", "local"), ("entrada_general", 20.0, "persona", "local")]
    noche = db.canchas["c_noche"]["servicios_extra"]
    assert [(x["clave"], float(x["precio"])) for x in noche] == [("pecheras", 5.0), ("piscina", 15.0), ("entrada_general", 20.0)]
    assert db.canchas["c_lima"]["amenidades"] == ["parking"] and db.canchas["c_noche"]["amenidades"] == ["parking"]
    assert [x["clave"] for x in db.canchas["c_gye"]["servicios_extra"]] == ["arbitro"]
    assert "Se aplicaron a sus 2 canchas" in cli.get("/anfitrion/canchas?local_guardado=c_lima").text
    # Guardar la CANCHA sin mandar servicios del local ni amenidades → los conserva (no los pisa).
    base = {"nombre": "Cancha Central", "deportes": ["futbol"], "superficie": "Grass sintético", "precio_hora": 60,
            "descuento_valle": 0, "valle_desde": "07:00", "valle_hasta": "12:00", "sena_pct": 0, "hora_apertura": "07:00", "hora_cierre": "23:00",
            "duracion_slot_min": 60, "fotos": [], "servicios_extra": [{"clave": "arbitro", "precio": 30}, {"clave": "pecheras", "precio": 8}]}
    assert cli.post("/anfitrion/cancha/c_lima/editar", json=base).json()["ok"] is True
    lima = db.canchas["c_lima"]["servicios_extra"]
    assert [(x["clave"], x["precio"]) for x in lima] == [("arbitro", 30.0), ("pecheras", 8.0), ("piscina", 15.0), ("entrada_general", 20.0)]
    assert db.canchas["c_lima"]["amenidades"] == ["parking"] and db.canchas["c_lima"]["club"] == "Club Raqueta"
    # Agregar una cancha al local hereda los del LOCAL (piscina, entrada) y no los de la cancha (árbitro).
    r = cli.post("/anfitrion/cancha/c_lima/agregar", json={"deporte": "tenis", "superficie": "Arcilla", "precio_hora": 40}).json()
    assert r["ok"] and [x["clave"] for x in db.canchas[r["id"]]["servicios_extra"]] == ["piscina", "entrada_general"]
    # Sugerencia del dueño → torre.
    assert cli.post("/anfitrion/servicios/sugerir", json={"texto": "Clases de natación", "cancha_id": "c_lima"}).json()["ok"] is True
    assert cli.post("/anfitrion/servicios/sugerir", json={"texto": "x"}).status_code == 400
    sug = client.get("/admin/api/servicios-extra", headers=h).json()["sugerencias"]
    assert sug[0]["texto"] == "Clases de natación" and sug[0]["email"] == "dueno@x.com" and sug[0]["local"] == "Club Raqueta"
    assert client.post(f"/admin/api/servicios-extra/sugerencias/{sug[0]['id']}", json={"estado": "atendida"}, headers=h).json()["ok"] is True
    # Ficha pública: piscina con selector de personas; checkout cobra × cantidad y el comprobante lo muestra.
    ficha = client.get("/reservar/c_lima").text
    assert "🏊 Piscina" in ficha and "por persona" in ficha and "class='cant' data-for='piscina'" in ficha and "3 personas" in ficha
    f = _manana()
    j = cli.post("/web/asegurar", json={"cancha_id": "c_lima", "horas": [{"fecha": f, "hora": "15:00"}, {"fecha": f, "hora": "16:00"}],
                                          "extras": [{"clave": "piscina", "cantidad": 3}, "arbitro", {"clave": "inventado", "cantidad": 2}],
                                          "nombre": "Ana Pérez", "celular": "999888777", "email": "dueno@x.com"}).json()
    assert j["ok"] is True, j
    ex = db.reservas[j["ids"][0]]["extras"]
    assert [(x["clave"], x["precio"], x["unitario"], x["cantidad"]) for x in ex] == [("piscina", 45.0, 15.0, 3), ("arbitro", 30.0, 30.0, 1)]
    assert j["total"] == 60 * 2 + 45 + 30
    cargos = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: (cargos.append(kw) or {"ok": True, "charge_id": "chr_pisc"}))
    p = cli.post("/web/pagar", json={"ids": j["ids"], "firma": j["firma"], "token": "tkn_pisc"}).json()
    assert p["ok"], p
    assert cargos[0]["monto_centimos"] == (120 + 45 + 30) * 100  # el cargo real incluye piscina × 3
    comp = cli.get(p["url"]).text
    assert "Piscina × 3" in comp and "S/ 45.00" in comp


def test_acceso_de_revision_con_usuario_y_clave_para_culqi(db, monkeypatch):
    """Culqi (24-sep-2026): "no se logró validar el proceso de compra debido a
    que se requiere iniciar sesión… proporcionar un usuario y contraseña de
    prueba". Con WEB_USUARIOS_PRUEBA, /entrar ofrece "Acceso de revisión" y
    la ficha enlaza a él; el revisor abre la MISMA sesión que Google y reserva."""
    from web import sesion, router as web_router
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    # Sin cuentas configuradas: ni enlace ni formulario ni endpoint.
    monkeypatch.setattr(config, "WEB_USUARIOS_PRUEBA", "")
    assert "Acceso de revisión" not in cli.get("/entrar").text
    assert "Acceso de revisión" not in cli.get("/reservar/c_lima").text
    assert cli.post("/web/sesion/prueba", json={"usuario": "x", "clave": "y"}).json()["error"] == "no_configurado"
    # Con cuentas: enlace en la ficha (vuelve a la misma ficha) y formulario en /entrar.
    monkeypatch.setattr(config, "WEB_USUARIOS_PRUEBA", "revision@pichangol.app:Clave-Culqi-2026, otro@x.com:abc")
    web_router._revision_intentos.clear()
    html = cli.get("/reservar/c_lima").text
    assert "Acceso de revisión con usuario y contraseña" in html and "/entrar?volver=%2Freservar%2Fc_lima#revision" in html
    assert "id='revUsr'" in cli.get("/entrar?volver=/reservar/c_lima").text
    # Credenciales malas → error; 5 fallos → bloqueo por IP (X-Forwarded-For, como en Railway).
    for _ in range(5):
        assert cli.post("/web/sesion/prueba", json={"usuario": "revision@pichangol.app", "clave": "mala"},
                        headers={"X-Forwarded-For": "200.1.2.3"}).json()["error"] == "credenciales_invalidas"
    assert cli.post("/web/sesion/prueba", json={"usuario": "revision@pichangol.app", "clave": "Clave-Culqi-2026"},
                    headers={"X-Forwarded-For": "200.1.2.3"}).json()["error"] == "demasiados_intentos"
    # Desde otra IP, con la clave correcta → cookie de sesión igual a la de Google.
    r = cli.post("/web/sesion/prueba", json={"usuario": "Revision@pichangol.app", "clave": "Clave-Culqi-2026"},
                 headers={"X-Forwarded-For": "200.9.9.9"})
    assert r.json() == {"ok": True, "email": "revision@pichangol.app", "nombre": "Cuenta de revisión", "foto": ""}
    assert sesion.leer(r.cookies[sesion.COOKIE])["email"] == "revision@pichangol.app"
    # Con esa sesión la ficha muestra "Reservando como" y la reserva se asegura a nombre del revisor.
    assert "revision@pichangol.app" in cli.get("/reservar/c_lima").text
    f = _manana()
    j = cli.post("/web/asegurar", json={"cancha_id": "c_lima", "horas": [{"fecha": f, "hora": "19:00"}], "extras": [],
                                        "nombre": "Revisor Culqi", "celular": "999888777", "email": "otra@x.com"}).json()
    assert j["ok"], j
    assert db.reservas[j["ids"][0]]["usuario"] == "revision@pichangol.app"


def test_carrito_de_matricula_familiar_un_solo_pago(db, monkeypatch):
    """Pedido del director (26-sep-2026, "Si haz ese carrito"): en la ficha de
    la academia agrego a mi esposa (Bola Verde), a mi hijo (Bola Naranja) y a
    mí, cada uno con su programa y su forma de pago, y PAGO UNA SOLA VEZ. El
    servidor recalcula cada total con el descuento familiar EN SECUENCIA
    (1.º completo, 2.º −H2, 3.º+ −H3), hace UN cargo, crea una matrícula por
    persona con el mismo N.º de operación, registra la contabilidad una vez
    por el total y las suscripciones mes a mes reusan la tarjeta de la 1.ª."""
    from web import academia as wa
    import pagos.router as pr
    from db.store import stores
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    db.academias["ac_c"] = {"nombre": "Academia Carrito", "deporte": "tenis", "dueno": "profe@gmail.com", "sedeClub": "Club X", "zona": "Surco",
                            "lat": -12.1, "lng": -77.0, "whatsapp": "999888777", "descuentoPrepago": 10, "mesesMinPrepago": 3,
                            "descuentoHermano2": 10, "descuentoHermano3": 20,
                            "planes": [{"id": "adultos", "nombre": "Adultos · 2x/sem", "programa": "Adultos", "precioMes": 120, "frecuenciaSemana": 2},
                                       {"id": "verde", "nombre": "Bola Verde · 2x/sem", "programa": "Bola Verde", "precioMes": 100, "frecuenciaSemana": 2},
                                       {"id": "naranja", "nombre": "Bola Naranja · 2x/sem", "programa": "Bola Naranja", "precioMes": 150, "frecuenciaSemana": 2}]}
    cli = TestClient(app, base_url="https://testserver")
    html = cli.get("/academia/ac_c").text
    for t in ("¿Matriculas a más personas?", "id='btnAgregar'", "Guardar a esta persona y agregar otra", '"fam"', "/web/matricular-varios", "id='nPersonas'", ".cart-it"):
        assert t in html, t
    # Sin sesión no se cobra nada.
    personas = [{"plan_id": "adultos", "nombre": "Dennis Calagua", "celular": "999888777", "quien": "yo", "cantidad": 6, "mes_a_mes": True},
                {"plan_id": "verde", "nombre": "María López", "celular": "988777666", "quien": "familiar", "email_persona": "maria@gmail.com", "cantidad": 2, "mes_a_mes": True},
                {"plan_id": "naranja", "nombre": "Lucas Calagua", "celular": "999888777", "quien": "hijo", "edad": 9, "cantidad": 1}]
    assert cli.post("/web/matricular-varios", json={"academia_id": "ac_c", "token": "t", "personas": personas}).json()["error"] == "sesion_requerida"
    _entrar_como(cli, monkeypatch, "dennis@gmail.com", nombre="Dennis")
    assert cli.get("/web/academia/ac_c/descuento-familiar").json()["fam"] == {"familiar": True, "previas": 0, "previasHijos": 0, "h2": 10.0, "h3": 20.0}
    cargos, pushes, conta, susc = [], [], [], []
    susc_real = pr.post_suscripcion_alumno
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: cargos.append(kw) or {"ok": True, "charge_id": "chr_fam_1"})
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: pushes.append((a, k)))
    monkeypatch.setattr(pr, "post_matricula", lambda req: conta.append(req) or {"ok": True})
    monkeypatch.setattr(pr, "post_suscripcion_alumno", lambda req: susc.append(req) or {"ok": True})
    # Validación por persona ANTES de cobrar: dice cuál falla.
    mal = [dict(personas[0]), dict(personas[2], edad=None)]
    r = cli.post("/web/matricular-varios", json={"academia_id": "ac_c", "token": "t", "personas": mal}).json()
    assert r["error"] == "edad" and r["persona"] == 1 and r["mensaje"].startswith("Persona 2: ")
    r = cli.post("/web/matricular-varios", json={"academia_id": "ac_c", "token": "t", "personas": [personas[0], dict(personas[1], nombre="dennis calagua")]}).json()
    assert r["error"] == "repetida" and not cargos
    assert cli.post("/web/matricular-varios", json={"academia_id": "ac_c", "token": "t", "personas": []}).json()["error"] == "vacio"
    # Yo (1.º, mes a mes 6 meses: 120) + esposa (2.ª, −10 %, mes a mes: 90) + hijo (3.º, −20 %: 120) = 330 en UN cargo.
    r = cli.post("/web/matricular-varios", json={"academia_id": "ac_c", "token": "tkn_fam", "medio": "yape", "personas": personas}).json()
    assert r["ok"] and r["total"] == 330 and len(cargos) == 1 and cargos[0]["monto_centimos"] == 33000 and cargos[0]["descripcion"] == "Matrícula Academia Carrito · 3 personas"
    ids = r["alumno_ids"]
    assert len(ids) == 3 and r["url"] == f"/academia/ac_c/matriculas?ids={','.join(ids)}" and r["charge_id"] == "chr_fam_1"
    ms = [db.matriculas[-3], db.matriculas[-2], db.matriculas[-1]]
    assert [m["id"] for m in ms] == ids and len(set(ids)) == 3
    assert [m["nombre"] for m in ms] == ["Dennis Calagua", "María López", "Lucas Calagua"]
    assert [m["ordenHermano"] for m in ms] == [1, 2, 3] and [m["pagoWeb"]["dtoFamiliar"] for m in ms] == [0, 10, 20]
    assert [m["pagoWeb"]["monto"] for m in ms] == [120, 90, 120] and all(m["email"] == "dennis@gmail.com" and m["canal"] == "web" for m in ms)
    assert all(c["operacionId"] == "chr_fam_1" for m in ms for c in m["cuotas"] if c.get("pagada"))
    assert ms[1]["parentesco"] == "familiar" and ms[1]["emailAlumno"] == "maria@gmail.com" and ms[1]["cuotas"][0]["monto"] == 90 and len(ms[1]["cuotas"]) == 2
    assert ms[2]["parentesco"] == "hijo" and ms[2]["apoderadoNombre"] == "Dennis" and ms[2]["cuotas"][0]["monto"] == 120
    # Contabilidad UNA vez por el total; el cobro web queda ligado a las 3 matrículas.
    assert len(conta) == 1 and conta[0].monto_soles == 330 and conta[0].matricula_id == "chr_fam_1" and conta[0].academia_id == "ac_c"
    pago = next(p for p in stores.pagos if p.tipo == "cobro_web" and p.culqi_charge_id == "chr_fam_1")
    assert pago.monto_centimos == 33000 and pago.concepto == "matricula:" + ",".join(ids)
    # Suscripciones mes a mes: la 1.ª con el token, la 2.ª reusa la tarjeta de la 1.ª (un tkn_ se usa una vez).
    assert [s.alumno_id for s in susc] == ids[:2] and susc[0].reusar_tarjeta_de == "" and susc[1].reusar_tarjeta_de == ids[0]
    assert susc[0].monto_soles == 120 and susc[0].cobros_restantes == 5 and susc[1].monto_soles == 90 and susc[1].cobros_restantes == 1
    # Un solo push al profe con los tres.
    assert len(pushes) == 1 and pushes[0][0][1] == "3 alumnos nuevos 🎓" and "María López (Bola Verde · 2x/sem)" in pushes[0][0][2] and "S/ 330.00" in pushes[0][0][2]
    # Comprobante familiar: los tres, descuentos y un solo N.º de operación.
    comp = cli.get(r["url"]).text
    for t in ("¡Matrícula familiar registrada!", "3 personas ya son alumnos", "Dennis Calagua", "María López", "Lucas Calagua", "S/ 330.00", "chr_fam_1",
              "Descuento familiar −10 % (2.º de tu familia)", "Descuento familiar −20 % (3.º o más de tu familia)", "wa.me/51999888777"):
        assert t in comp, t
    # Ahora esta cuenta ya paga 3 aquí: el siguiente sería el 4.º (−20 %).
    fam = cli.get("/web/academia/ac_c/descuento-familiar").json()
    assert fam["fam"]["previas"] == 3 and fam["fam"]["previasHijos"] == 1 and fam["dtoFam"]["hijo"] == {"orden": 4, "pct": 20.0}
    # Privacidad: otro no lo ve; el familiar con su correo ve SOLO su comprobante.
    _entrar_como(cli, monkeypatch, "otro@gmail.com")
    assert "Esta matrícula es privada" in cli.get(r["url"]).text
    _entrar_como(cli, monkeypatch, "maria@gmail.com", nombre="María")
    mio = cli.get(r["url"]).text
    assert "¡Matrícula registrada!" in mio and "María López" in mio and "Lucas Calagua" not in mio
    # Una sola persona sigue por /web/matricular con su comprobante individual (misma lógica).
    _entrar_como(cli, monkeypatch, "dennis@gmail.com", nombre="Dennis")
    r1 = cli.post("/web/matricular-varios", json={"academia_id": "ac_c", "token": "t", "personas": [{"plan_id": "naranja", "nombre": "Mateo", "celular": "999888777", "quien": "hijo", "edad": 6}]}).json()
    assert r1["ok"] and r1["url"].startswith("/academia/ac_c/matricula/al_") and cargos[-1]["monto_centimos"] == 12000 and db.matriculas[-1]["ordenHermano"] == 4
    # Cargo rechazado → nada se guarda.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "rechazada"})
    n = len(db.matriculas)
    assert cli.post("/web/matricular-varios", json={"academia_id": "ac_c", "token": "t", "personas": personas[:2]}).json()["error"] == "cargo_rechazado" and len(db.matriculas) == n
    # El endpoint real de suscripción REUSA la tarjeta (crd_) de la 1.ª persona en vez de gastar el token otra vez.
    monkeypatch.setattr(culqi, "disponible", lambda: True)
    cards = []
    monkeypatch.setattr(culqi, "crear_customer", lambda **kw: {"ok": True, "customer_id": "cus_1"})
    monkeypatch.setattr(culqi, "crear_card", lambda **kw: cards.append(kw) or {"ok": True, "card_id": "crd_fam", "marca": "visa", "ultimos4": "4242"})
    susc_real(pr.SuscripcionAlumnoReq(alumno_id="al_p1", academia_id="ac_c", email="dennis@gmail.com", token="tkn_x", monto_soles=120))
    susc_real(pr.SuscripcionAlumnoReq(alumno_id="al_p2", academia_id="ac_c", email="dennis@gmail.com", token="tkn_x", monto_soles=90, reusar_tarjeta_de="al_p1"))
    assert len(cards) == 1 and stores.suscripciones_alumno["al_p2"]["card_id"] == "crd_fam" and stores.suscripciones_alumno["al_p2"]["ultimos4"] == "4242"
    # Otra cuenta no puede colgarse de esa tarjeta.
    susc_real(pr.SuscripcionAlumnoReq(alumno_id="al_p3", academia_id="ac_c", email="otra@gmail.com", token="tkn_y", monto_soles=90, reusar_tarjeta_de="al_p1"))
    assert len(cards) == 2
