"""Billetera del JUGADOR en la web = pantallas Mi billetera, Mis pagos, Mis
puntos y Mi país del APK (pedido del director, 29-sep-2026: "en la web
implementa las mismas funcionalidades que existen en el app")."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from db.store import Venta, stores
from main import app
from pagos import culqi
from pagos import router as pagos_router
from web import datos, sesion
from web import jugador_billetera as jb

EMAIL = "ana@gmail.com"


@pytest.fixture(autouse=True)
def _estado(monkeypatch):
    antes = stores.to_state()
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    # Sin base: cada consulta propia se simula por test.
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [])
    monkeypatch.setattr(datos, "puntos_de", lambda e: {"ganados": 0, "canjeados": 0, "disponibles": 0})
    monkeypatch.setattr(datos, "reservas_de_usuario", lambda e, limite=200: [])
    monkeypatch.setattr(datos, "celular_de_perfil", lambda e: "987654321")
    for f in ("bonos_comprados", "matriculas_que_pago", "reservas_para_puntos", "bodega_para_puntos", "canjes_de_puntos"):
        monkeypatch.setattr(jb, f, lambda e: [])
    monkeypatch.setattr(jb, "monedas_de_clubes", lambda c: {})
    monkeypatch.setattr(jb, "nombres_de_canchas", lambda ids: {})
    yield
    stores.load_state(antes)


def _cli(email=EMAIL):
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Ana Pérez", "foto": ""}))
    return cli


def test_paginas_exigen_sesion():
    cli = TestClient(app, base_url="https://testserver")
    for ruta, volver in (("/mi-billetera", "%2Fmi-billetera"), ("/mis-pagos", "%2Fmis-pagos"),
                         ("/mis-puntos", "%2Fmis-puntos"), ("/mi-pais", "%2Fmi-pais")):
        r = cli.get(ruta, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == f"/entrar?volver={volver}"
    assert cli.post("/web/billetera/recargar", json={"monto": 20, "token": "tkn"}).status_code == 401
    assert cli.post("/web/billetera/cupon", json={"codigo": "X"}).status_code == 401
    assert cli.post("/web/mi-pais", json={"iso": "BO"}).status_code == 401


def test_movimientos_web_son_los_mismos_del_apk(monkeypatch):
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "")
    stores.acreditar(EMAIL, 5000)
    stores.registrar_pago(tipo="recarga", monto_centimos=5000, moneda="PEN", estado="aprobado", dueno_id=EMAIL,
                          culqi_charge_id="chr_r1", concepto="Recarga de saldo")
    stores.registrar_pago(tipo="suscripcion_pro", monto_centimos=1990, moneda="PEN", estado="aprobado", dueno_id=EMAIL,
                          concepto="Pichangol Pro")
    stores.registrar_pago(tipo="liquidacion_online", monto_centimos=6000, moneda="PEN", estado="aprobado",
                          dueno_id=EMAIL, culqi_charge_id="res_1", concepto="Reserva · Club Sol")
    stores.registrar_pago(tipo="bodega_pago", monto_centimos=800, moneda="PEN", estado="aprobado", dueno_id=EMAIL)
    api = pagos_router.get_movimientos(EMAIL, None)["movimientos"]
    web = jb.movimientos(EMAIL)
    assert [m["comprobante"] for m in web] == [m["comprobante"] for m in api]
    assert [round(m["monto"], 2) for m in web] == [round(abs(m["monto_soles"]), 2) for m in api]
    clases = {m["tipo"]: m["clase"] for m in web}
    assert clases == {"recarga": "recarga", "suscripcion_pro": "consumo",
                      "liquidacion_online": "liquidacion", "bodega_pago": "consumo"}
    liq = next(m for m in web if m["tipo"] == "liquidacion_online")
    assert liq["bruto"] == 60 and liq["comision"] == 3 and liq["monto"] == 57 and not liq["liquidado"]
    assert jb.por_recibir(web) == {"S/": 57.0}
    # La API ahora informa la moneda de cada fila (aditivo).
    assert all(m["moneda"] == "PEN" for m in api)

    html = _cli().get("/mi-billetera").text
    assert "Mi billetera" in html and "S/ 50.00" in html and "⭐ Destacado" in html
    assert "Por recibir" in html and "S/ 57.00" in html and "Registra tu cuenta de cobro" in html
    assert "href='/anfitrion/ingresos'" in html
    assert "Cobrado al cliente" in html and "Comisión Pichangol" in html
    assert "Mi saldo" in html and "Pichangol Pro" in html
    assert "¿Tienes un cupón?" in html and "href='/mis-puntos'" in html and "/mi-billetera/estado-de-cuenta" in html
    import re
    assert not re.search(r"(?<![A-Za-z])(confirm|alert|prompt)\(", jb._JS_BILLETERA)
    est = _cli().get("/mi-billetera/estado-de-cuenta").text
    assert "Estado de cuenta" in est and "Imprimir / guardar PDF" in est and "Pichangol Pro" in est


def test_regalo_bono_y_recarga_culqi_solo_soles(monkeypatch):
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(config, "CULQI_SECRET_KEY", "sk_test_x")
    stores.acreditar_promo(EMAIL, 2000)
    stores.config.update({"promo_bono_recarga_pct": "10", "promo_bono_recarga_min": "50", "promo_bono_recarga_tope": "20"})
    html = _cli().get("/mi-billetera").text
    assert "de saldo de REGALO" in html and "S/ 20.00" in html
    assert "te regalamos 10% extra" in html
    # Chips por país (Perú: 20/50/100/200) + Otro monto 10-1000, Yape primero y Culqi v4.
    for m in (20, 50, 100, 200):
        assert f"data-monto='{m}'" in html
    assert "min='10' max='1000'" in html and "checkout.culqi.com/js/v4" in html and "id='medioPago'" in html

    cargos = []
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: (cargos.append(kw) or {"ok": True, "charge_id": "chr_rw1"}))
    cli = _cli()
    # Monto fuera de rango o con decimales → 400 sin cobrar.
    assert cli.post("/web/billetera/recargar", json={"monto": 5, "token": "tkn_1"}).status_code == 400
    assert cli.post("/web/billetera/recargar", json={"monto": 20.5, "token": "tkn_1"}).status_code == 400
    assert not cargos
    r = cli.post("/web/billetera/recargar", json={"monto": 100, "token": "tkn_1", "medio": "yape"}).json()
    assert r["ok"] and r["bono_soles"] == 10 and r["saldo_soles"] == 110
    assert cargos[0]["monto_centimos"] == 10000 and cargos[0]["email"] == EMAIL
    assert cargos[0]["cliente"]["telefono"] == "987654321" and cargos[0]["cliente"]["nombre"] == "Ana Pérez"
    # Idempotente por cargo: el mismo chr_ no acredita dos veces.
    r2 = cli.post("/web/billetera/recargar", json={"monto": 100, "token": "tkn_2"}).json()
    assert r2["ok"] and r2["saldo_soles"] == 110
    assert stores.saldo_centimos(EMAIL) == 11000
    # Culqi rechaza → nada se acredita.
    monkeypatch.setattr(culqi, "crear_cargo", lambda **kw: {"ok": False, "error": "tarjeta_rechazada"})
    r3 = cli.post("/web/billetera/recargar", json={"monto": 50, "token": "tkn_3"}).json()
    assert not r3["ok"] and stores.saldo_centimos(EMAIL) == 11000

    # Billetera en bolivianos (cancha en La Paz): la web no cobra, manda a la app.
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [{"id": "c1", "lat": -16.5, "lng": -68.15}])
    otro = "bo@gmail.com"
    html = _cli(otro).get("/mi-billetera").text
    assert "Bs 0.00" in html and "Libélula" in html and "Recargar en la app" in html and "data-monto='" not in html
    r = _cli(otro).post("/web/billetera/recargar", json={"monto": 100, "token": "tkn_x"})
    assert r.status_code == 409 and r.json()["error"] == "pais_no_soportado"


def test_cupon_web_misma_logica_que_el_apk(monkeypatch):
    stores.cupones["PCG-HOLA"] = {"valor_soles": 15, "usos_max": 1, "usados": [], "activo": True}
    cli = _cli()
    r = cli.post("/web/billetera/cupon", json={"codigo": "pcg-hola"}).json()
    assert r["ok"] and r["valor_soles"] == 15 and stores.saldo_centimos(EMAIL) == 1500
    assert cli.post("/web/billetera/cupon", json={"codigo": "PCG-HOLA"}).json()["error"] == "ya_lo_canjeaste"
    assert _cli("otro@gmail.com").post("/web/billetera/cupon", json={"codigo": "PCG-HOLA"}).json()["error"] == "cupon_agotado"
    assert cli.post("/web/billetera/cupon", json={"codigo": "NO-EXISTE"}).json()["error"] == "cupon_invalido"
    # Cupón en soles no entra a una billetera en $ (Ecuador).
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [{"id": "c1", "lat": -2.17, "lng": -79.92}])
    stores.cupones["PCG-DOS"] = {"valor_soles": 5, "usos_max": 10, "usados": [], "activo": True}
    assert _cli("ec@gmail.com").post("/web/billetera/cupon", json={"codigo": "PCG-DOS"}).json()["error"] == "cupon_solo_soles"


def test_mi_pais_solo_con_saldo_cero_y_descongela_la_moneda(monkeypatch):
    cli = _cli()
    html = cli.get("/mi-pais").text
    assert "Perú · S/" in html and "Aún no lo has elegido." in html and "data-iso='BO'" in html
    assert cli.post("/web/mi-pais", json={"iso": "XX"}).status_code == 400
    r = cli.post("/web/mi-pais", json={"iso": "BO"}).json()
    assert r["ok"] and r["efectivo"] == "BO" and "Bolivia (Bs)" in r["mensaje"]
    assert stores.clientes_pago[EMAIL]["pais_casa"] == "BO"
    assert jb.pais_billetera(EMAIL) == ("BO", "elegido")
    # La ficha del cliente para Culqi no se contamina con el país de casa.
    assert "pais_casa" not in stores.cliente_de(EMAIL)
    # Una recarga (en soles) CONGELA la moneda del saldo por encima del país elegido.
    stores.acreditar(EMAIL, 2000)
    stores.registrar_pago(tipo="recarga", monto_centimos=2000, moneda="PEN", estado="aprobado", dueno_id=EMAIL,
                          culqi_charge_id="chr_x")
    assert jb.pais_billetera(EMAIL) == ("PE", "recarga")
    # Con saldo no se puede cambiar (misma regla del APK).
    r = cli.post("/web/mi-pais", json={"iso": "EC"})
    assert r.status_code == 409 and r.json()["error"] == "tiene_saldo"
    assert "Tu billetera tiene saldo" in cli.get("/mi-pais").text
    # Con saldo 0 se cambia y la moneda se DESCONGELA (la próxima recarga la fija).
    stores.saldos[EMAIL] = 0
    assert cli.post("/web/mi-pais", json={"iso": "EC"}).json()["efectivo"] == "EC"
    assert jb.pais_billetera(EMAIL) == ("EC", "elegido")
    # El regalo también bloquea el cambio.
    stores.acreditar_promo(EMAIL, 100)
    assert cli.post("/web/mi-pais", json={"iso": "PE"}).status_code == 409


def test_mis_pagos_como_el_app_con_comprobantes(monkeypatch):
    hoy = datetime.now(timezone.utc)
    monkeypatch.setattr(jb, "bonos_comprados", lambda e: [
        {"id": "b1", "club": "Club Sol", "horas_total": 5, "horas_usadas": 1, "precio": 200.0, "creado": hoy - timedelta(days=3)}])
    monkeypatch.setattr(jb, "monedas_de_clubes", lambda c: {"Club Sol": "S/"})
    monkeypatch.setattr(jb, "nombres_de_canchas", lambda ids: {"c1": {"nombre": "Cancha 1", "club": "Club Sol"},
                                                                "c2": {"nombre": "Pádel 1", "club": "Club La Paz"}})
    f = (hoy - timedelta(days=1)).date().isoformat()
    monkeypatch.setattr(datos, "reservas_de_usuario", lambda e, limite=200: [
        {"id": "r1", "cancha_id": "c1", "fecha": f, "hora_inicio": "19:00", "hora_fin": "20:00", "precio": 60, "extras": [],
         "pagado": True, "estado": "confirmada", "moneda": "S/", "grupo_reserva_id": "grp_1", "medio_pago": "yape",
         "cargo_servicio": 3},
        {"id": "r2", "cancha_id": "c1", "fecha": f, "hora_inicio": "20:00", "hora_fin": "21:00", "precio": 60,
         "extras": [{"clave": "arbitro", "precio": 10}], "pagado": True, "estado": "confirmada", "moneda": "S/",
         "grupo_reserva_id": "grp_1", "medio_pago": "yape"},
        {"id": "r3", "cancha_id": "c2", "fecha": f, "hora_inicio": "09:00", "hora_fin": "10:00", "precio": 80, "extras": [],
         "pagado": False, "estado": "confirmada", "moneda": "Bs", "grupo_reserva_id": "", "medio_pago": "efectivo"},
        {"id": "r4", "cancha_id": "c1", "fecha": f, "hora_inicio": "07:00", "hora_fin": "08:00", "precio": 60, "extras": [],
         "pagado": True, "estado": "confirmada", "moneda": "S/", "grupo_reserva_id": "", "medio_pago": "bono"},
        {"id": "r5", "cancha_id": "c1", "fecha": f, "hora_inicio": "06:00", "hora_fin": "07:00", "precio": 60, "extras": [],
         "pagado": False, "estado": "noShow", "moneda": "S/", "grupo_reserva_id": "", "medio_pago": ""},
    ])
    monkeypatch.setattr(jb, "matriculas_que_pago", lambda e: [{"id": "al_1", "academia_id": "ac_1", "data": {
        "nombre": "Lucas", "cuotas": [{"concepto": "Plan 2x · Septiembre", "monto": 250, "pagada": True,
                                        "fechaPago": hoy.isoformat(), "vencimiento": hoy.isoformat()}]}}])
    monkeypatch.setattr(datos, "academia", lambda i: {"nombre": "Tenis Kids", "lat": -12.1, "lng": -77.0})
    stores.ventas.append(Venta(id=1, producto_id="p1", producto_nombre="Raqueta Pro", comprador_email=EMAIL,
                               comprador_nombre="Ana", vendedor_email="v@x.com", vendedor_nombre="Tienda Beto",
                               monto_soles=150.0, creado_en=hoy))
    stores.registrar_pago(tipo="recarga", monto_centimos=5000, moneda="PEN", estado="aprobado", dueno_id=EMAIL)

    pagos = jb.armar_pagos(EMAIL)
    titulos = [p["titulo"] for p in pagos]
    assert "Bono de 5 horas" in titulos and "Compra · Raqueta Pro" in titulos and "Recarga de saldo" in titulos
    assert "Tenis Kids · Plan 2x · Septiembre" in titulos
    res = [p for p in pagos if p["titulo"] == "Reserva · Club Sol"]
    # Los 2 turnos del grupo son UNA tarjeta: 60 + 60 + árbitro 10 + cargo 3; el bono va aparte; el no-show no sale.
    assert sorted(p["monto"] for p in res) == [0.0, 133.0]
    grupo = next(p for p in res if p["monto"] == 133.0)
    assert grupo["estado"] == "pagado" and grupo["href"] == "/reserva/grp_1" and "2 turnos" in grupo["sub"]
    bol = next(p for p in pagos if p["titulo"] == "Reserva · Club La Paz")
    assert bol["estado"] == "pendiente" and bol["moneda"] == "Bs"
    assert len([p for p in pagos if p["titulo"].startswith("Reserva")]) == 3

    html = _cli().get("/mis-pagos").text
    assert "Mis pagos" in html and "href='/reserva/grp_1'" in html and "href='/academia/ac_1/matricula/al_1'" in html
    assert "Con bono" in html and "por pagar en la cancha" in html and "Bs 80.00" in html
    assert "S/ 133.00" in html and "Imprimir / guardar PDF" in html
    # Total pagado por moneda (sin lo cubierto con bono ni lo pendiente).
    assert "S/ 783.00" in html  # 200 bono + 133 reserva + 250 cuota + 150 compra + 50 recarga
    assert "Ayer" in html and "Hoy" in html


def test_mis_puntos_como_el_app(monkeypatch):
    hoy = datetime.now(timezone.utc)
    monkeypatch.setattr(datos, "puntos_de", lambda e: {"ganados": 215, "canjeados": 100, "disponibles": 115})
    monkeypatch.setattr(jb, "reservas_para_puntos", lambda e: [
        {"id": "r1", "cancha_id": "c1", "fecha": hoy.date().isoformat(), "hora_inicio": "19:00", "puntos": 70, "pagado": True},
        {"id": "r2", "cancha_id": "c1", "fecha": hoy.date().isoformat(), "hora_inicio": "21:00", "puntos": 60, "pagado": False}])
    monkeypatch.setattr(jb, "bodega_para_puntos", lambda e: [{"id": "p1", "resumen": "2 Gatorade", "puntos": 12, "creado": hoy}])
    monkeypatch.setattr(jb, "canjes_de_puntos", lambda e: [{"puntos": 100, "soles": 3.0, "referencia": "x", "creado": hoy}])
    monkeypatch.setattr(jb, "nombres_de_canchas", lambda ids: {"c1": {"nombre": "Cancha 1", "club": "Club Sol"}})
    html = _cli().get("/mis-puntos").text
    assert ">115<" in html and "Valen S/ 3.45" in html and "Ya canjeaste 100 puntos" in html
    assert "+60 por confirmar" in html and "Club Sol" in html and "+70" in html
    assert "Bodega · 2 Gatorade" in html and "Canje · S/ 3.00 de descuento" in html and "−100" in html
    assert "100 puntos = S/ 3" in html and "href='/mi-billetera'" in html


def test_fecha_de_juego_es_dia_de_lima():
    """Una fecha sola (día de juego) no se corre al día anterior por la zona horaria."""
    from datetime import date
    assert jb._parse("2026-09-29").astimezone(jb._LIMA).date() == date(2026, 9, 29)


def test_puntos_disponibles_coinciden_con_el_perfil():
    """Mis puntos usa la MISMA cuenta que el Perfil web (`datos.puntos_de`)."""
    import inspect
    src = inspect.getsource(jb.pagina_mis_puntos)
    assert "datos.puntos_de(email)" in src
