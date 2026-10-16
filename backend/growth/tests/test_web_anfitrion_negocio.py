"""Panel del negocio del dueño en la web (`web/anfitrion_negocio.py`): espejo
de Reportes/Ocupación/Cobros/Cancelaciones, Caja del día, Clientes, Bonos,
Reservas fijas, Disponibilidad y Cobros de academia del app."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from db.store import PagoRegistro, stores
from main import app
from web import anfitrion, anfitrion_negocio as ng, datos, horarios, sesion

YO = "dueno@x.com"
CANCHA = {"id": "c1", "nombre": "Cancha 1", "club": "Club Raqueta", "deporte": "tenis", "deportes": ["tenis"], "precio_hora": 60.0,
          "lat": -12.09, "lng": -77.0, "dueno": YO, "verificada": True, "registrada": True, "eliminada": False,
          "hora_apertura": "07:00", "hora_cierre": "22:00", "duracion_slot_min": 60, "moneda": "S/", "descuento_valle": 0,
          "valle_desde": "", "valle_hasta": "", "sena_pct": 0, "servicios_extra": [], "amenidades": []}
GYE = {**CANCHA, "id": "g1", "nombre": "Cancha GYE", "club": "Club Sur", "lat": -2.17, "lng": -79.92, "moneda": "$", "precio_hora": 10.0}


def _hoy():
    return horarios.ahora_local("PE").date()


def _res(i, fecha, hora="19:00", **kw):
    base = {"id": f"r{i}", "cancha_id": "c1", "jugador": "Luis Ramos", "nivel": "", "fecha": fecha, "hora_inicio": hora,
            "hora_fin": f"{int(hora[:2]) + 1:02d}:00", "estado": "confirmada", "precio": 60, "sena": 0, "pagado": True,
            "usuario": "luis@x.com", "moneda": "S/", "extras": [], "telefono": "987654321", "grupo_reserva_id": "",
            "medio_pago": "yape", "traida_por_app": True}
    base.update(kw)
    return base


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [dict(CANCHA)] if e == YO else [])
    monkeypatch.setattr(anfitrion, "_en_segundo_plano", lambda fn, *a: fn(*a))
    monkeypatch.setattr(ng, "_en_segundo_plano", lambda fn, *a: fn(*a))
    antes = dict(stores.negocio_web)
    stores.negocio_web.clear()
    c = TestClient(app, base_url="https://testserver")
    c.cookies.set(sesion.COOKIE, sesion.emitir({"email": YO, "nombre": "Dennis", "foto": ""}))
    yield c
    stores.negocio_web.clear()
    stores.negocio_web.update(antes)


def test_sin_sesion_va_a_entrar_y_sin_canchas_onboarding(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    c = TestClient(app, base_url="https://testserver")
    for ruta in ("/anfitrion/reportes", "/anfitrion/caja", "/anfitrion/clientes", "/anfitrion/bonos", "/anfitrion/fijas",
                 "/anfitrion/disponibilidad", "/anfitrion/cobros", "/anfitrion/ocupacion", "/anfitrion/cancelaciones"):
        r = c.get(ruta, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].startswith("/entrar?volver="), ruta
    # Los endpoints que escriben exigen sesión.
    for ruta in ("/anfitrion/caja/cerrar", "/anfitrion/bonos/guardar", "/anfitrion/fijas/nueva", "/anfitrion/clientes/nota",
                 "/anfitrion/cobros/cuota", "/anfitrion/reserva/r1/noshow"):
        assert c.post(ruta, json={}).status_code == 401, ruta


def test_resumen_y_cobros_cuadran_con_el_app(cli, monkeypatch):
    hoy = _hoy()
    filas = [_res(1, hoy.isoformat()), _res(2, hoy.isoformat(), "20:00", pagado=False, medio_pago="efectivo"),
             _res(3, hoy.isoformat(), "21:00", estado="noShow", pagado=False, medio_pago="efectivo"),
             _res(4, hoy.isoformat(), "18:00", medio_pago="bono", extras=[{"clave": "arbitro", "precio": 30}])]
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [dict(r) for r in filas if a <= r["fecha"] <= b])
    html = cli.get("/anfitrion/reportes").text
    # Resumen (reportes_screen): cobrado del mes = precios pagados sin no-show (r1 + r4 = 120), por cobrar 60, 3 reservas.
    assert "S/ 120" in html and "Reservas del mes" in html and "<b>3</b>" in html and "S/ 60" in html
    assert "Ocupación de hoy" in html and "3 de 16 turnos" in html and "Ver como tabla" in html
    # Cobros (reporte_canchas_screen): el bono no suma plata; comisión con mínimo por moneda.
    html = cli.get("/anfitrion/reportes/cobros").text
    assert "Cobrado" in html and "S/ 60" in html and "Reporte de cobros" in html
    assert "Comisión Pichangol estimada" in html and "S/ 6.00" in html  # r1 y r2 (5 % de 60 = 3 c/u); el bono no suma
    # "Cuánto vas a recibir" = mismos movimientos que la billetera.
    pagos_antes = list(stores.pagos)
    stores.pagos.append(PagoRegistro(id=99901, tipo="liquidacion_online", monto_centimos=6000, estado="aprobado", dueno_id=YO,
                                     culqi_charge_id="r1", moneda="PEN", concepto="Reserva", creado_en=datetime.now(timezone.utc)))
    try:
        html = cli.get("/anfitrion/reportes/cobros").text
    finally:
        stores.pagos[:] = pagos_antes
    assert "Cuánto vas a recibir de Pichangol" in html and "Reservas online (1)" in html and "S/ 57.00" in html
    csv = cli.get("/anfitrion/reportes/cobros.csv")
    assert csv.status_code == 200 and "text/csv" in csv.headers["content-type"] and "Luis Ramos" in csv.text


def test_ocupacion_mapa_de_calor_y_cancelaciones(cli, monkeypatch):
    hoy = _hoy()
    lunes = hoy - timedelta(days=hoy.weekday())
    filas = [_res(1, lunes.isoformat(), "19:00"), _res(2, (lunes - timedelta(days=7)).isoformat(), "19:00"),
             _res(3, lunes.isoformat(), "08:00", estado="noShow", pagado=False)]
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [dict(r) for r in filas if a <= r["fecha"] <= b])
    monkeypatch.setattr(ng, "_resenas", lambda ids: [{"estrellas": 5, "comentario": "Top", "autor_nombre": "Ana"}])
    html = cli.get("/anfitrion/ocupacion?p=d30").text
    assert "Hora pico" in html and "19:00" in html and "Lunes" in html and "No-show" in html and "33%" in html
    assert "data-tip='Lunes 19:00 · 2 reservas'" in html and "Tu reputación" in html and "5.0" in html
    monkeypatch.setattr(ng, "cancelaciones_de", lambda e: [{"jugador": "Ana", "local": "Club Raqueta", "cancha_nombre": "Cancha 1",
                                                            "fecha": hoy.isoformat(), "hora_inicio": "19:00", "hora_fin": "20:00",
                                                            "precio": 60, "moneda": "S/", "pagado": False, "sena": 20,
                                                            "cancelada_en": datetime.now(timezone.utc).isoformat()}])
    antes = list(stores.cancelaciones_web)
    stores.cancelaciones_web.append({"dueno": YO, "cancha_id": "c1", "cancha": "Cancha 1", "club": "Club Raqueta", "usuario": "eva@x.com",
                                     "fecha": hoy.isoformat(), "hora_inicio": "20:00", "hora_fin": "21:00", "monto": 6000,
                                     "moneda": "S/", "pagado": True, "reembolso": "devuelto_saldo", "creado_en": datetime.now(timezone.utc).isoformat()})
    try:
        html = cli.get("/anfitrion/cancelaciones").text
    finally:
        stores.cancelaciones_web[:] = antes
    assert "Seña S/ 20 a tu favor · resto ya no se debe" in html and "Devuelto al saldo del jugador" in html


def test_caja_del_dia_desglose_cierre_y_auto_cierre(cli, monkeypatch):
    hoy = _hoy()
    ayer = (hoy - timedelta(days=2)).isoformat()
    filas = [_res(1, hoy.isoformat()), _res(2, hoy.isoformat(), "20:00", pagado=False, medio_pago="efectivo", sena=20),
             _res(3, hoy.isoformat(), "18:00", medio_pago="bono"), _res(4, ayer, "19:00", medio_pago="manual", traida_por_app=False)]
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [dict(r) for r in filas if a <= r["fecha"] <= b])
    html = cli.get("/anfitrion/caja").text
    # cajaDia: cobrado = 60 (yape) + 20 (seña); por cobrar 40; bono no suma plata pero ocupa.
    assert "S/ 80" in html and "S/ 40" in html and "📱 Yape/Plin" in html and "🔒 Señas (online)" in html
    assert "Seña S/ 20 pagada · cobra S/ 40.00" in html and "Cerrar caja del día" in html
    # El día anterior sin cierre queda con cierre AUTOMÁTICO (sin confirmar).
    neg = stores.negocio_web[YO]
    assert any(x["fecha"] == ayer and x["automatico"] and x["cobrado"] == 60 for x in neg["cierres"])
    r = cli.post("/anfitrion/caja/cerrar", json={"fecha": hoy.isoformat()})
    assert r.json()["ok"] and r.json()["cobrado"] == 80
    assert any(x["fecha"] == hoy.isoformat() and not x["automatico"] and x["medios"] == {"yape": 60, "sena": 20} for x in neg["cierres"])
    assert cli.post("/anfitrion/caja/reabrir", json={"fecha": hoy.isoformat()}).json()["ok"]
    assert not any(x["fecha"] == hoy.isoformat() for x in neg["cierres"])


def test_clientes_segmentos_ficha_y_notas(cli, monkeypatch):
    hoy = _hoy()
    viejo = (hoy - timedelta(days=60)).isoformat()
    filas = [_res(1, viejo, usuario="ana@x.com", jugador="Ana"), _res(2, (hoy - timedelta(days=40)).isoformat(), usuario="ana@x.com", jugador="Ana"),
             _res(3, (hoy - timedelta(days=45)).isoformat(), usuario="ana@x.com", jugador="Ana"),
             _res(4, hoy.isoformat(), usuario="", jugador="Carlos", telefono="912345678", pagado=False, medio_pago="efectivo")]
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [dict(r) for r in filas])
    import web.jugador_liga as jl
    monkeypatch.setattr(jl, "perfiles", lambda es: {"ana@x.com": {"nombre": "Ana", "foto_url": "https://lh3/ana.jpg"}})
    html = cli.get("/anfitrion/clientes").text
    assert "Base de clientes" in html and "https://lh3/ana.jpg" in html
    assert "VIP · 1" in html and "En riesgo · 1" in html and "Deudores · 1" in html and "Nuevos · 1" in html
    assert "Debe S/ 60.00" in html and '"wa": "912345678"' in html
    html = cli.get("/anfitrion/clientes?seg=riesgo").text
    assert "Ana" in html and "Carlos" not in html.split("id='listaCli'")[1].split("</div><div class='anf-vacio'")[0]
    assert cli.post("/anfitrion/clientes/nota", json={"clave": "ana@x.com", "texto": "Juega martes"}).json()["ok"]
    assert stores.negocio_web[YO]["notas"]["ana@x.com"] == "Juega martes"
    assert "Juega martes" in cli.get("/anfitrion/clientes").text


def test_bonos_crear_editar_pausar_y_vendidos(cli, monkeypatch):
    guardados = []
    monkeypatch.setattr(ng, "ofertas_de_dueno", lambda e: [{"id": "bof_1", "dueno": YO, "club": "Club Raqueta", "nombre": "", "horas": 10,
                                                            "precio": 500.0, "activo": True}])
    monkeypatch.setattr(ng, "vendidos_de_dueno", lambda e: [{"id": "v", "club": "Club Raqueta", "comprador": "ana@x.com", "comprador_nombre": "Ana",
                                                             "horas_total": 10, "horas_usadas": 3, "precio": 500.0, "saldo": 7}])
    monkeypatch.setattr(ng, "guardar_oferta", lambda f, e: guardados.append((f, e)) or True)
    monkeypatch.setattr(ng, "activar_oferta", lambda i, e, a: i == "bof_1")
    monkeypatch.setattr(ng, "eliminar_oferta", lambda i, e: i == "bof_1")
    html = cli.get("/anfitrion/bonos").text
    assert "Bonos · Club Raqueta" in html and "10 horas" in html and "S/ 50.00/hora" in html and "3 / 10" in html and "le quedan 7 de 10 h" in html
    r = cli.post("/anfitrion/bonos/guardar", json={"club": "Club Raqueta", "horas": 4, "precio": "220", "nombre": "Pack 4"})
    assert r.json()["ok"] and guardados[-1][0]["horas"] == 4 and guardados[-1][0]["activo"] and guardados[-1][1] == YO
    assert cli.post("/anfitrion/bonos/guardar", json={"club": "Otro local", "horas": 4, "precio": 1}).status_code == 404
    assert cli.post("/anfitrion/bonos/guardar", json={"club": "Club Raqueta", "horas": 0, "precio": 1}).status_code == 400
    assert cli.post("/anfitrion/bonos/guardar", json={"id": "bof_ajeno", "club": "Club Raqueta", "horas": 2, "precio": 1}).status_code == 404
    assert cli.post("/anfitrion/bonos/bof_1/activo", json={"activo": False}).json()["ok"]
    assert cli.post("/anfitrion/bonos/bof_x/eliminar").status_code == 404


def test_reservas_fijas_generan_serie_respetando_ocupados_y_bloqueos(cli, monkeypatch):
    hoy = _hoy()
    insertadas = []
    dia = (hoy + timedelta(days=1)).weekday() + 1  # mañana: ninguna ocurrencia cae en el pasado
    manana = hoy + timedelta(days=1)
    bloqueado = (manana + timedelta(days=7)).isoformat()
    monkeypatch.setattr(datos, "ocupados", lambda cid, fechas: {(bloqueado, "19:00")})
    monkeypatch.setattr(datos, "descuentos", lambda cid, fechas: {})
    monkeypatch.setattr(datos, "insertar_reservas", lambda filas: insertadas.extend(filas) or "")
    avisos = []
    from pagos import router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: avisos.append(a))
    r = cli.post("/anfitrion/fijas/nueva", json={"cancha_id": "c1", "dia": dia, "hora": "19:00", "nombre": "Los Tigres",
                                                  "telefono": "987 654 321", "email": "tigre@x.com"}).json()
    assert r["ok"] and r["creadas"] == 3 and len(r["omitidas"]) == 1
    assert [f["fecha"] for f in insertadas] == [manana.isoformat(), (manana + timedelta(days=14)).isoformat(), (manana + timedelta(days=21)).isoformat()]
    f0 = insertadas[0]
    assert f0["medio_pago"] == "manual" and f0["traida_por_app"] is False and f0["precio"] == 60 and f0["usuario"] == "tigre@x.com"
    assert f0["id"].startswith("man_") and f0["estado"] == "confirmada" and not f0["pagado"]
    assert len(avisos) == 1 and avisos[0][0] == "tigre@x.com"
    # Idempotente: al abrir la página no se duplican (ni reaparece la fecha ocupada).
    html = cli.get("/anfitrion/fijas").text
    assert len(insertadas) == 3 and "Los Tigres" in html
    # Mismo día y hora → rechazado; validaciones.
    assert cli.post("/anfitrion/fijas/nueva", json={"cancha_id": "c1", "dia": dia, "hora": "19:00", "nombre": "X"}).status_code == 409
    assert cli.post("/anfitrion/fijas/nueva", json={"cancha_id": "c1", "dia": dia, "hora": "03:00", "nombre": "X"}).status_code == 400
    assert cli.post("/anfitrion/fijas/nueva", json={"cancha_id": "ajena", "dia": dia, "hora": "19:00", "nombre": "X"}).status_code == 404
    fid = stores.negocio_web[YO]["fijas"][0]["id"]
    assert cli.post(f"/anfitrion/fijas/{fid}/activo", json={"activo": False}).json()["ok"]
    assert stores.negocio_web[YO]["fijas"][0]["activo"] is False
    assert cli.post(f"/anfitrion/fijas/{fid}/quitar").json()["ok"] and not stores.negocio_web[YO]["fijas"]


def test_disponibilidad_real_con_bloqueos(cli, monkeypatch):
    hoy = _hoy()
    manana = (hoy + timedelta(days=1)).isoformat()
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [_res(1, manana, "19:00")])
    monkeypatch.setattr(datos, "bloqueos_de", lambda ids, fechas: {("c1", manana, "15:00")})
    html = cli.get(f"/anfitrion/disponibilidad?cancha=c1&fecha={manana}").text
    assert "Disponibilidad" in html and "Reservada" in html and "Hora valle" in html and "Prioriza abrirla" in html
    assert f"data-f='{manana}' data-h='15:00' " in html  # bloqueado → interruptor apagado
    assert f"data-f='{manana}' data-h='16:00' checked" in html
    assert "14 turnos abiertos" in html  # 16 turnos − 1 reservado − 1 bloqueado


def test_noshow_y_filtro_de_reservas(cli, monkeypatch):
    hoy = _hoy()
    filas = [_res(1, hoy.isoformat(), pagado=False, medio_pago="efectivo"), _res(2, hoy.isoformat(), "20:00")]
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [dict(r) for r in filas])
    monkeypatch.setattr(datos, "reservas_de_canchas", lambda ids, a, b: [dict(r) for r in filas])
    hechos = []
    monkeypatch.setattr(ng, "marcar_noshow", lambda rid, ids: hechos.append(rid) or True)
    html = cli.get("/anfitrion/reservas").text
    assert "id='filMedio'" in html and "data-medio='efectivo'" in html and "data-noshow='r1'" in html and "data-noshow='r2'" not in html
    assert "💵 Efectivo" in html and "📱 Yape" in html
    assert cli.post("/anfitrion/reserva/r1/noshow").json()["ok"] and hechos == ["r1"]
    assert cli.post("/anfitrion/reserva/r2/noshow").status_code == 409  # pagada en línea
    assert cli.post("/anfitrion/reserva/zz/noshow").status_code == 404


def test_cobros_de_academia_recordar_y_cobrar_cuota(cli, monkeypatch):
    hoy = date.today()
    monkeypatch.setattr(datos, "academias_de_dueno", lambda e: [{"id": "ac1", "nombre": "Top Spin", "moneda": "S/", "dueno": YO}] if e == YO else [])
    mats = [{"id": "al1", "nombre": "Mateo", "apoderadoNombre": "Carla", "apoderadoWhatsapp": "987111222", "email": "carla@x.com",
             "cuotas": [{"id": "cu1", "concepto": "Oct", "monto": 180, "vencimiento": (hoy - timedelta(days=3)).isoformat(), "pagada": False},
                        {"id": "cu0", "concepto": "Set", "monto": 180, "pagada": True, "fechaPago": hoy.isoformat()}]},
            {"id": "al2", "nombre": "Sofía", "whatsapp": "999888777", "email": "",
             "cuotas": [{"id": "cu2", "concepto": "Oct", "monto": 240, "vencimiento": (hoy + timedelta(days=4)).isoformat(), "pagada": False}]}]
    monkeypatch.setattr(datos, "matriculas_de_academias", lambda ids: [dict(m) for m in mats])
    html = cli.get("/anfitrion/cobros").text
    assert "Cobros · Top Spin" in html and "S/ 420.00" in html and "S/ 180.00" in html and "Tienes 2 alumnos por recordar" in html
    # Orden: vencido primero.
    assert html.index("data-al='al1'") < html.index("data-al='al2'")
    msgs = []
    monkeypatch.setattr(ng, "mensaje_academia", lambda *a: msgs.append(a) or True)
    r = cli.post("/anfitrion/cobros/recordar", json={"academia_id": "ac1", "alumno_id": "al1"}).json()
    assert r["ok"] and r["canal"] == "app" and "Mis clases y pagos" in msgs[0][4] and "de Mateo" in msgs[0][4]
    r = cli.post("/anfitrion/cobros/recordar", json={"academia_id": "ac1", "alumno_id": "al2", "solo_marcar": True}).json()
    assert r["canal"] == "whatsapp" and set(stores.negocio_web[YO]["recordados"]) == {"al1", "al2"}
    assert "Tienes 2 alumnos por recordar" not in cli.get("/anfitrion/cobros").text
    import web.jugador_liga as jl
    avisos = []
    monkeypatch.setattr(jl, "aviso_push", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(ng, "marcar_cuota_cobrada", lambda a, m, c: {"id": c, "concepto": "Oct", "monto": 180} if c == "cu1" else None)
    assert cli.post("/anfitrion/cobros/cuota", json={"academia_id": "ac1", "alumno_id": "al1", "cuota_id": "cu1"}).json()["ok"]
    assert avisos and avisos[0][0] == "carla@x.com" and avisos[0][1] == "Pago registrado ✓"
    assert cli.post("/anfitrion/cobros/cuota", json={"academia_id": "ac1", "alumno_id": "al1", "cuota_id": "cu0"}).status_code == 409
    assert cli.post("/anfitrion/cobros/cuota", json={"academia_id": "otra", "alumno_id": "al1", "cuota_id": "cu1"}).status_code == 404


def test_multi_moneda_nunca_mezcla_soles_con_dolares(cli, monkeypatch):
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [dict(CANCHA), dict(GYE)])
    hoy = _hoy()
    filas = [_res(1, hoy.isoformat()), _res(2, hoy.isoformat(), cancha_id="g1", precio=10, moneda="$")]
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [dict(r) for r in filas if r["cancha_id"] in ids])
    html = cli.get("/anfitrion/reportes").text
    assert "S/ 60" in html and "href='?m=USD'" in html and "$ 10" not in html
    html = cli.get("/anfitrion/reportes?m=USD").text
    assert "$ 10" in html and "S/ 60" not in html


def test_sin_dialogos_nativos():
    for js in (ng.JS_TIP, ng.JS_CAJA, ng.JS_CLIENTES, ng.JS_BONOS, ng.JS_FIJAS, ng.JS_DISPO, ng.JS_COBROS, ng.JS_FILTRO_RESERVAS):
        assert "confirm(" not in js.replace("pcgConfirmar(", "") and "alert(" not in js and "prompt(" not in js
