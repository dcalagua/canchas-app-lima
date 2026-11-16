"""Pichangol Pro, tarjetas guardadas, búsqueda guiada, recordatorios del dueño
y "Agregar cuota" de academia en la web = hazte_pro_screen, metodos_pago_screen,
busqueda_guiada/asistente, recordar_reservas_screen y mi_academia_screen
(inscribir / clase suelta) del APK."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from pagos import culqi
from pagos import router as pagos_router
from web import anfitrion_negocio as neg
from web import datos, horarios, jugador_mensajes, sesion
from web import jugador_pro as jp

EMAIL = "ana@gmail.com"
DUENO = "dueno@gmail.com"


@pytest.fixture(autouse=True)
def _estado(monkeypatch):
    antes = stores.to_state()
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [])
    monkeypatch.setattr(datos, "celular_de_perfil", lambda e: "987654321")
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [])
    monkeypatch.setattr(datos, "ocupados_varias", lambda ids, fechas: {})
    yield
    stores.load_state(antes)


def _cli(email=EMAIL, nombre="Ana Pérez"):
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre, "foto": ""}))
    return cli


def test_paginas_y_acciones_exigen_sesion():
    cli = TestClient(app, base_url="https://testserver")
    for ruta, volver in (("/pro", "%2Fpro"), ("/cuenta/tarjetas", "%2Fcuenta%2Ftarjetas")):
        r = cli.get(ruta, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == f"/entrar?volver={volver}"
    assert cli.post("/web/pro/suscribir").status_code == 401
    assert cli.post("/web/pro/renovacion", json={"auto": False}).status_code == 401
    assert cli.post("/web/tarjetas/agregar", json={"token": "tkn_x1234"}).status_code == 401
    assert cli.post("/web/tarjetas/eliminar", json={"id": "crd_1"}).status_code == 401
    assert cli.post("/anfitrion/recordatorios/enviar", json={"ids": ["r1"]}).status_code == 401
    assert cli.post("/anfitrion/cobros/agregar", json={}).status_code == 401
    # La búsqueda guiada es pública.
    assert cli.get("/buscar").status_code == 200


def test_pro_se_paga_del_saldo_con_la_misma_funcion_del_app_y_se_puede_cancelar_la_renovacion():
    cli = _cli()
    precio = pagos_router._pro_precio_centimos("PE")
    # Sin saldo: igual que el app → falta saldo (lo manda a recargar), nada se debita.
    j = cli.post("/web/pro/suscribir").json()
    assert j["ok"] is False and j["falta_saldo"] is True and stores.saldo_centimos(EMAIL) == 0
    r = cli.get("/pro")
    assert r.status_code == 200 and "Activar por S/" in r.text and "ACTIVO" not in r.text
    assert "confirm(" not in jp.JS_PRO.replace("pcgConfirmar(", "") and "alert(" not in jp.JS_PRO
    stores.acreditar(EMAIL, precio + 500)
    j = cli.post("/web/pro/suscribir").json()
    assert j["ok"] is True
    assert stores.saldo_centimos(EMAIL) == 500 and stores.pro_activo(EMAIL)
    assert any(p.tipo == "suscripcion_pro" and p.dueno_id == EMAIL for p in stores.pagos)
    r = cli.get("/pro")
    assert "ACTIVO" in r.text and "Renovación automática activada" in r.text and "Renovar 1 mes" in r.text
    # Cancelar la renovación automática: el cron ya no debita al vencer.
    assert cli.post("/web/pro/renovacion", json={"auto": False}).json() == {"ok": True, "auto": False}
    assert "Renovación automática cancelada" in cli.get("/pro").text
    assert pagos_router.get_pro_estado(EMAIL)["renueva"] is False
    stores.acreditar(EMAIL, precio * 3)
    saldo = stores.saldo_centimos(EMAIL)
    stores.membresias_pro[EMAIL]["hasta"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    pagos_router.procesar_renovaciones_pro()
    assert stores.saldo_centimos(EMAIL) == saldo and not stores.pro_activo(EMAIL)
    # Pagar de nuevo a mano la reactiva (misma función del app).
    assert cli.post("/web/pro/suscribir").json()["ok"] is True
    assert pagos_router.get_pro_estado(EMAIL)["renueva"] is True
    # Sin Pro vigente o con cortesía no hay renovación que cancelar.
    stores.membresias_pro[EMAIL]["cortesia"] = True
    assert cli.post("/web/pro/renovacion", json={"auto": False}).status_code == 409
    assert _cli("otro@gmail.com").post("/web/pro/renovacion", json={"auto": False}).status_code == 409


def test_pro_usa_la_moneda_y_el_precio_del_pais_de_la_billetera(monkeypatch):
    from web import jugador_billetera as jb
    monkeypatch.setattr(jb, "pais_billetera", lambda email, canchas=None: ("EC", "recarga"))
    stores.config["pro_precio_soles_ec"] = "4.5"
    r = _cli().get("/pro")
    assert "$ 4.50" in r.text and "S/" not in r.text.split("pr-precio")[1][:80]
    r = _cli().get("/pro/planes")
    assert r.status_code == 200 and "Gratis vs Pro" in r.text and "Sin límite" in r.text


def test_tarjetas_guardadas_con_post_metodo_y_solo_las_propias(monkeypatch):
    monkeypatch.setattr(config, "CULQI_PUBLIC_KEY", "pk_test_x")
    monkeypatch.setattr(culqi, "disponible", lambda: True)
    visto = {}

    def cus(**kw):
        visto["cliente"] = kw
        return {"ok": True, "customer_id": "cus_1"}
    monkeypatch.setattr(culqi, "crear_customer", cus)
    monkeypatch.setattr(culqi, "crear_card", lambda **kw: {"ok": True, "card_id": "crd_1", "marca": "Visa", "ultimos4": "4242"})
    borradas = []
    monkeypatch.setattr(culqi, "eliminar_card", lambda cid: borradas.append(cid) or {"ok": True})
    cli = _cli()
    r = cli.get("/cuenta/tarjetas")
    assert "Aún no tienes tarjetas" in r.text and "checkout.culqi.com/js/v4" in r.text
    assert cli.post("/web/tarjetas/agregar", json={"token": "4111111111111111"}).status_code == 400
    j = cli.post("/web/tarjetas/agregar", json={"token": "tkn_test_abc"}).json()
    assert j["ok"] and j["metodo"] == {"id": "crd_1", "marca": "Visa", "ultimos4": "4242"}
    # Mismo lugar que el app (/pagos/metodos/{correo}); solo marca y últimos 4.
    assert pagos_router.get_metodos(EMAIL)["metodos"] == [{"id": "crd_1", "marca": "Visa", "ultimos4": "4242"}]
    assert visto["cliente"]["nombre"] == "Ana" and visto["cliente"]["telefono"] == "987654321"
    assert "Visa ···· 4242" in cli.get("/cuenta/tarjetas").text
    # Tarjeta ajena: no se toca.
    assert _cli("otro@gmail.com").post("/web/tarjetas/eliminar", json={"id": "crd_1"}).status_code == 404
    assert cli.post("/web/tarjetas/eliminar", json={"id": "crd_1"}).json()["ok"]
    assert borradas == ["crd_1"] and pagos_router.get_metodos(EMAIL)["metodos"] == []


def _cancha(cid, club, dep, precio, ap="07:00", ci="23:00", **kw):
    c = {"id": cid, "nombre": f"Cancha {cid}", "club": club, "deporte": dep, "deportes": [dep], "hora_apertura": ap,
         "hora_cierre": ci, "duracion_slot_min": 60, "precio_hora": precio, "precio_turno": 0, "verificada": True,
         "dueno": DUENO, "lat": -12.1, "lng": -77.0, "barrio": "Surco", "moneda": "S/", "direccion": "Av. 1", "foto_url": ""}
    c.update(kw)
    return c


def test_busqueda_guiada_sugiere_canchas_con_turno_libre_y_lleva_a_la_ficha(monkeypatch):
    manana = (horarios.ahora_local("PE").date() + timedelta(days=1)).isoformat()
    canchas = [_cancha("a1", "Club A", "tenis", 60), _cancha("b1", "Club B", "tenis", 40),
               _cancha("c1", "Club C", "futbol", 80), _cancha("d1", "Club D", "tenis", 30, verificada=False)]
    monkeypatch.setattr(datos, "canchas_publicas", lambda: canchas)
    # Club B ocupado a las 19:00 → no sale a esa hora.
    monkeypatch.setattr(datos, "ocupados_varias", lambda ids, fechas: {"b1": {(manana, "19:00")}})
    cli = TestClient(app, base_url="https://testserver")
    r = cli.get(f"/buscar?ir=1&deporte=tenis&fecha={manana}&hora=19:00&orden=barato")
    assert r.status_code == 200
    assert f"/reservar/a1?fecha={manana}&amp;hora=19%3A00" in r.text
    assert "/reservar/b1" not in r.text and "/reservar/c1" not in r.text and "/reservar/d1" not in r.text
    assert "/?deporte=tenis&amp;fecha=" in r.text  # Ver todas en el explorador
    # Sin hora: ambos tenis, el más barato primero.
    r = cli.get(f"/buscar?ir=1&deporte=tenis&fecha={manana}&orden=barato")
    assert r.text.index("/reservar/b1") < r.text.index("/reservar/a1")
    # Zona sin canchas: mensaje honesto.
    assert "No encontré" in cli.get(f"/buscar?ir=1&deporte=tenis&fecha={manana}&zona=Miraflores").text


def test_recordar_reservas_por_chat_o_whatsapp_solo_del_dueno(monkeypatch):
    canchas = [_cancha("k1", "Club K", "futbol", 80)]
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: canchas if e == DUENO else [])
    manana = (neg._hoy_de(canchas).date() + timedelta(days=1)).isoformat()
    filas = [{"id": "r1", "cancha_id": "k1", "jugador": "Luis", "usuario": "luis@gmail.com", "telefono": "", "fecha": manana,
              "hora_inicio": "19:00", "hora_fin": "20:00", "estado": "confirmada", "grupo_reserva_id": "g1"},
             {"id": "r2", "cancha_id": "k1", "jugador": "Luis", "usuario": "luis@gmail.com", "telefono": "", "fecha": manana,
              "hora_inicio": "20:00", "hora_fin": "21:00", "estado": "confirmada", "grupo_reserva_id": "g1"},
             {"id": "r3", "cancha_id": "k1", "jugador": "Pepe", "usuario": "", "telefono": "999888777", "fecha": manana,
              "hora_inicio": "21:00", "hora_fin": "22:00", "estado": "confirmada", "grupo_reserva_id": ""}]
    monkeypatch.setattr(neg, "reservas_dueno", lambda ids, d, h: [dict(f) for f in filas if d <= f["fecha"] <= h and f["cancha_id"] in ids])
    monkeypatch.setattr(jp, "recordados_por_app", lambda d, ids: set())
    enviados = []
    monkeypatch.setattr(jugador_mensajes, "insertar_mensaje", lambda f: enviados.append(f) or f)
    cli = _cli(DUENO, "Dueño K")
    r = cli.get("/anfitrion/recordatorios?dia=manana")
    assert r.status_code == 200 and "Luis" in r.text and "Pepe" in r.text and "Recordar a todos" in r.text
    assert "wa.me/51999888777" in r.text
    assert "19:00–21:00" in r.text  # los dos turnos del bloque, en una tarjeta
    j = cli.post("/anfitrion/recordatorios/enviar", json={"fecha": manana, "ids": ["r1", "r2", "r3"]}).json()
    assert j == {"ok": True, "enviados": 1}  # un mensaje por bloque; sin cuenta no va por chat
    m = enviados[0]
    assert m["id"].endswith("_r1") and m["hilo"] == f"cancha_{DUENO}|luis@gmail.com" and m["tipo"] == "cancha"
    assert m["ref_id"] == DUENO and m["es_profe"] is True and "mañana 19:00 en Club K · Cancha k1" in m["texto"]
    # WhatsApp: se anota en la nube (snapshot) y la página lo muestra recordado.
    assert cli.post("/anfitrion/recordatorios/marcar", json={"fecha": manana, "ids": ["r3"]}).json()["ok"]
    assert "res:r3" in stores.negocio_web[DUENO]["recordados"]
    # Reservas de canchas ajenas: nada.
    assert _cli("otro@gmail.com").post("/anfitrion/recordatorios/enviar", json={"fecha": manana, "ids": ["r1"]}).status_code == 404


def test_agregar_cuota_de_academia_con_el_formato_del_app(monkeypatch):
    aca = {"id": "ac_1", "nombre": "Academia Uno", "moneda": "S/", "lat": -12.1, "lng": -77.0, "recargoInvitado": 20,
           "descuentoHermano2": 10, "descuentoHermano3": 15, "descuentoPrepago": 5,
           "planes": [{"id": "p1", "nombre": "Bola Roja · 2x/sem", "programa": "Bola Roja", "frecuenciaSemana": 2, "tipo": "mensual", "precioMes": 200},
                      {"id": "p2", "nombre": "Clase particular", "tipo": "porClase", "precioMes": 50}]}
    alumno = {"id": "al_1", "nombre": "Leo", "ordenHermano": 2, "esSocioSede": True, "cuotas": []}
    monkeypatch.setattr(datos, "academias_de_dueno", lambda e: [dict(aca)] if e == DUENO else [])
    monkeypatch.setattr(datos, "matriculas_de_academias", lambda ids: [dict(alumno)])
    guardado = {}

    def db(email, aid, alid, armar):
        if email != DUENO or alid != "al_1":
            return None
        data = dict(alumno)
        nuevas = armar(data)
        guardado.setdefault("cuotas", []).extend(nuevas)
        return nuevas
    monkeypatch.setattr(neg, "agregar_cuotas_db", db)
    cli = _cli(DUENO, "Dueño")
    r = cli.get("/anfitrion/cobros/agregar?academia=ac_1")
    assert r.status_code == 200 and "Leo" in r.text and "2x por semana" in r.text and "Clase suelta" in r.text
    assert "/anfitrion/cobros/agregar?academia=ac_1" in cli.get("/anfitrion/cobros?academia=ac_1").text
    j = cli.post("/anfitrion/cobros/agregar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "p1", "meses": 3}).json()
    assert j["ok"] and j["cuotas"] == 3 and j["total"] == 540.0  # 200 − 10 % (2.º de la familia) × 3
    c0, c2 = guardado["cuotas"][0], guardado["cuotas"][2]
    assert c0["monto"] == 180.0 and c0["pagada"] is False and c0["alumnoId"] == "al_1" and c0["academiaId"] == "ac_1"
    assert c0["id"].startswith("cu_") and c0["id"].endswith("_0") and c0["concepto"].endswith("(−10%)")
    assert c0["vencimiento"].endswith("T00:00:00")
    v0, v2 = datetime.fromisoformat(c0["vencimiento"]), datetime.fromisoformat(c2["vencimiento"])
    assert (v2.year * 12 + v2.month) - (v0.year * 12 + v0.month) == 2
    guardado.clear()
    j = cli.post("/anfitrion/cobros/agregar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "__suelta", "monto": "35.5"}).json()
    assert j["ok"] and guardado["cuotas"][0]["monto"] == 35.5 and guardado["cuotas"][0]["concepto"].startswith("Clase suelta ")
    guardado.clear()
    assert cli.post("/anfitrion/cobros/agregar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "p2"}).json()["total"] == 50.0
    # Validaciones y academia ajena.
    assert cli.post("/anfitrion/cobros/agregar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "p1", "meses": 30}).status_code == 400
    assert cli.post("/anfitrion/cobros/agregar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "__suelta", "monto": "0"}).status_code == 400
    assert cli.post("/anfitrion/cobros/agregar", json={"academia_id": "ac_1", "alumno_id": "al_9", "plan_id": "p1", "meses": 1}).status_code == 409
    assert _cli("otro@gmail.com").post("/anfitrion/cobros/agregar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "p1"}).status_code == 404
