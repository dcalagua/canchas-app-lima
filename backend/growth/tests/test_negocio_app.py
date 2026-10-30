"""Negocio del dueño para el APK (`negocio_app.py`, `/negocio/*`): cierres de
caja, reservas fijas, notas de clientes y "ya recordado" viven en UN solo
lugar (`stores.negocio_web`) y el APK y la web ven y escriben lo mismo."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from web import anfitrion, anfitrion_negocio as ng, datos, horarios, sesion

YO = "dueno@x.com"
OTRO = "otro@x.com"
CANCHA = {"id": "c1", "nombre": "Cancha 1", "club": "Club Raqueta", "deporte": "tenis", "deportes": ["tenis"], "precio_hora": 60.0,
          "lat": -12.09, "lng": -77.0, "dueno": YO, "verificada": True, "registrada": True, "eliminada": False,
          "hora_apertura": "07:00", "hora_cierre": "22:00", "duracion_slot_min": 60, "moneda": "S/", "descuento_valle": 0,
          "valle_desde": "", "valle_hasta": "", "sena_pct": 0, "servicios_extra": [], "amenidades": []}
GYE = {**CANCHA, "id": "g1", "nombre": "Cancha GYE", "club": "Club Sur", "lat": -2.17, "lng": -79.92, "moneda": "$", "precio_hora": 10.0}


def _hoy():
    return horarios.ahora_local("PE").date()


def _res(i, fecha, hora="19:00", cancha="c1", **kw):
    base = {"id": f"r{i}", "cancha_id": cancha, "jugador": "Luis Ramos", "nivel": "", "fecha": fecha, "hora_inicio": hora,
            "hora_fin": f"{int(hora[:2]) + 1:02d}:00", "estado": "confirmada", "precio": 60, "sena": 0, "pagado": True,
            "usuario": "luis@x.com", "moneda": "S/", "extras": [], "telefono": "987654321", "grupo_reserva_id": "",
            "medio_pago": "yape", "traida_por_app": True}
    base.update(kw)
    return base


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "APP_API_KEY", "")
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "")
    canchas = {YO: [dict(CANCHA), dict(GYE)]}
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [dict(c) for c in canchas.get(e, [])])
    monkeypatch.setattr(datos, "academias_de_dueno", lambda e: [])
    monkeypatch.setattr(anfitrion, "_en_segundo_plano", lambda fn, *a: fn(*a))
    monkeypatch.setattr(ng, "_en_segundo_plano", lambda fn, *a: fn(*a))
    monkeypatch.setattr(ng, "_persistir", lambda: None)
    antes = dict(stores.negocio_web)
    stores.negocio_web.clear()
    app_cli = TestClient(app, base_url="https://testserver")
    web = TestClient(app, base_url="https://testserver")
    web.cookies.set(sesion.COOKIE, sesion.emitir({"email": YO, "nombre": "Dennis", "foto": ""}))
    yield app_cli, web, canchas
    stores.negocio_web.clear()
    stores.negocio_web.update(antes)


def test_caja_por_moneda_cerrada_en_el_app_se_ve_en_la_web_y_viceversa(entorno, monkeypatch):
    app_cli, web, _ = entorno
    hoy = _hoy()
    hace2 = (hoy - timedelta(days=2)).isoformat()
    filas = [_res(1, hoy.isoformat()), _res(2, hoy.isoformat(), "20:00", pagado=False, medio_pago="efectivo", sena=20),
             _res(3, hoy.isoformat(), "19:00", cancha="g1", precio=10, moneda="$", medio_pago="tarjeta"),
             _res(4, hace2, "19:00", medio_pago="manual", traida_por_app=False)]
    monkeypatch.setattr(ng, "reservas_dueno", lambda ids, a, b: [dict(r) for r in filas if r["cancha_id"] in ids and a <= r["fecha"] <= b])
    # Estado con auto-cierre: el día pasado sin cierre queda AUTOMÁTICO en soles (no en dólares: sin actividad).
    r = app_cli.get("/negocio/estado", params={"email": YO, "autocerrar": 1}).json()
    assert r["ok"] and any(x["fecha"] == hace2 and x["automatico"] and x["moneda"] == "PEN" and x["cobrado"] == 60 for x in r["cierres"])
    assert not any(x["moneda"] == "USD" for x in r["cierres"])
    # El APK cierra hoy en SOLES y en DÓLARES por separado (nunca se suman).
    pen = app_cli.post("/negocio/caja/cerrar", json={"email": YO, "fecha": hoy.isoformat(), "moneda": "S/"}).json()
    assert pen["ok"] and pen["cierre"]["moneda"] == "PEN" and pen["cobrado"] == 80 and pen["cierre"]["medios"] == {"yape": 60, "sena": 20}
    usd = app_cli.post("/negocio/caja/cerrar", json={"email": YO, "fecha": hoy.isoformat(), "moneda": "USD"}).json()
    assert usd["cierre"]["moneda"] == "USD" and usd["cobrado"] == 10 and usd["simbolo"] == "$"
    assert len([x for x in usd["cierres"] if x["fecha"] == hoy.isoformat()]) == 2
    # La web ve el cierre que hizo el app (mismo snapshot).
    html = web.get(f"/anfitrion/caja?fecha={hoy.isoformat()}&m=PEN").text
    assert "🔒 Caja cerrada" in html
    # La web reabre soles → el app deja de verlo; dólares sigue cerrado.
    assert web.post("/anfitrion/caja/reabrir", json={"fecha": hoy.isoformat(), "m": "PEN"}).json()["ok"]
    est = app_cli.get("/negocio/estado", params={"email": YO}).json()
    hoy_c = [x for x in est["cierres"] if x["fecha"] == hoy.isoformat()]
    assert [x["moneda"] for x in hoy_c] == ["USD"]
    # El app reabre dólares.
    assert not [x for x in app_cli.post("/negocio/caja/reabrir", json={"email": YO, "fecha": hoy.isoformat(), "moneda": "$"}).json()["cierres"]
                if x["fecha"] == hoy.isoformat()]
    # Validaciones.
    assert app_cli.post("/negocio/caja/cerrar", json={"email": YO, "fecha": "ayer"}).status_code == 400
    assert app_cli.post("/negocio/caja/cerrar", json={"email": OTRO, "fecha": hoy.isoformat()}).status_code == 404
    assert app_cli.get("/negocio/estado", params={"email": "no-es-correo"}).status_code == 400


def test_fijas_una_sola_serie_entre_app_y_web(entorno, monkeypatch):
    app_cli, web, _ = entorno
    hoy = _hoy()
    dia = (hoy + timedelta(days=1)).weekday() + 1
    manana = hoy + timedelta(days=1)
    bloqueado = (manana + timedelta(days=7)).isoformat()
    insertadas = []
    monkeypatch.setattr(datos, "ocupados", lambda cid, fechas: {(bloqueado, "19:00")} | {(f["fecha"], f["hora_inicio"]) for f in insertadas})
    monkeypatch.setattr(datos, "descuentos", lambda cid, fechas: {})
    monkeypatch.setattr(datos, "insertar_reservas", lambda filas: insertadas.extend(filas) or "")
    from pagos import router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    body = {"email": YO, "id": "fija_123", "cancha_id": "c1", "dia": dia, "hora": "19:00", "nombre": "Los Tigres",
            "telefono": "987 654 321", "cliente_email": "tigre@x.com"}
    r = app_cli.post("/negocio/fijas", json=body).json()
    assert r["ok"] and r["id"] == "fija_123" and r["creadas"] == 3 and len(r["omitidas"]) == 1
    assert r["fijas"][0]["clienteEmail"] == "tigre@x.com" and "hechas" not in r["fijas"][0]
    # Reintento desde la cola del APK: idempotente.
    r2 = app_cli.post("/negocio/fijas", json=body).json()
    assert r2["ok"] and r2["creadas"] == 0 and len(r2["fijas"]) == 1 and len(insertadas) == 3
    # La web la ve y genera la MISMA serie (no duplica).
    html = web.get("/anfitrion/fijas").text
    assert "Los Tigres" in html and len(insertadas) == 3
    # El APK pide generar: tampoco duplica.
    assert app_cli.post("/negocio/fijas/generar", json={"email": YO}).json()["creadas"] == 0
    # Mismo turno desde la web → 409; cancha ajena desde el app → 404.
    assert web.post("/anfitrion/fijas/nueva", json={"cancha_id": "c1", "dia": dia, "hora": "19:00", "nombre": "X"}).status_code == 409
    assert app_cli.post("/negocio/fijas", json={**body, "id": "fija_9", "cancha_id": "ajena"}).status_code == 404
    assert app_cli.post("/negocio/fijas", json={**body, "id": "fija_9", "hora": "03:00"}).status_code == 400
    # Pausar en la web → el app lo ve; reactivar en el app.
    assert web.post("/anfitrion/fijas/fija_123/activo", json={"activo": False}).json()["ok"]
    assert app_cli.get("/negocio/estado", params={"email": YO}).json()["fijas"][0]["activo"] is False
    assert app_cli.post("/negocio/fijas/fija_123/activo", json={"email": YO, "activo": True}).json()["fijas"][0]["activo"] is True
    assert app_cli.post("/negocio/fijas/nada/activo", json={"email": YO, "activo": True}).status_code == 404
    # Quitar en el app → la web no la muestra; quitarla otra vez es ok (cola).
    r = app_cli.post("/negocio/fijas/fija_123/quitar", json={"email": YO}).json()
    assert r["ok"] and r["quitada"] and not r["fijas"]
    assert "Los Tigres" not in web.get("/anfitrion/fijas").text
    assert app_cli.post("/negocio/fijas/fija_123/quitar", json={"email": YO}).json()["quitada"] is False
    # Una fija quitada no se resucita con el mismo id.
    assert app_cli.post("/negocio/fijas", json=body).status_code == 410


def test_notas_y_recordados_compartidos(entorno, monkeypatch):
    app_cli, web, _ = entorno
    # Nota escrita en el app → la web la usa; borrada en la web → el app la pierde.
    r = app_cli.post("/negocio/notas", json={"email": YO, "clave": "Ana@X.com", "texto": "  Juega   martes "}).json()
    assert r["ok"] and r["notas"] == {"ana@x.com": "Juega martes"}
    assert web.post("/anfitrion/clientes/nota", json={"clave": "ana@x.com", "texto": ""}).json()["ok"]
    assert app_cli.get("/negocio/estado", params={"email": YO}).json()["notas"] == {}
    assert app_cli.post("/negocio/notas", json={"email": YO, "clave": "", "texto": "x"}).status_code == 400
    # Recordatorio de cobro (id de matrícula) y de reservas (`res:<id>`).
    r = app_cli.post("/negocio/recordados", json={"email": YO, "claves": ["al1", "res:r7"]}).json()
    assert set(r["recordados"]) == {"al1", "res:r7"}
    # Una marca vieja (cola offline) no pisa una más nueva y las de reservas de >10 días se limpian.
    nueva = r["recordados"]["al1"]
    r = app_cli.post("/negocio/recordados", json={"email": YO, "clave": "al1", "cuando": "2020-01-01T00:00:00Z"}).json()
    assert r["recordados"]["al1"] == nueva
    r = app_cli.post("/negocio/recordados", json={"email": YO, "clave": "res:viejo", "cuando": "2020-01-01T00:00:00Z"}).json()
    assert "res:viejo" not in r["recordados"]
    # Lo que marca la web (recordatorios por WhatsApp) lo ve el app.
    import web.jugador_pro as jp
    hoy = horarios.ahora_local("PE").date().isoformat()
    monkeypatch.setattr(jp, "_validar_reservas", lambda email, fecha, ids: ([dict(CANCHA)], [_res(9, hoy)]))
    assert web.post("/anfitrion/recordatorios/marcar", json={"fecha": hoy, "ids": ["r9"]}).json()["ok"]
    assert "res:r9" in app_cli.get("/negocio/estado", params={"email": YO}).json()["recordados"]
    assert app_cli.post("/negocio/recordados", json={"email": YO}).status_code == 400


def test_migracion_una_vez_por_equipo_y_el_servidor_gana(entorno, monkeypatch):
    app_cli, web, canchas = entorno
    hoy = _hoy()
    insertadas = []
    monkeypatch.setattr(datos, "ocupados", lambda cid, fechas: {(f["fecha"], f["hora_inicio"]) for f in insertadas})
    monkeypatch.setattr(datos, "descuentos", lambda cid, fechas: {})
    monkeypatch.setattr(datos, "insertar_reservas", lambda filas: insertadas.extend(filas) or "")
    from pagos import router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: None)
    ayer = (hoy - timedelta(days=1)).isoformat()
    # El servidor ya tiene una nota y un cierre de ayer (hechos en la web).
    ng.guardar_nota_de(YO, "ana@x.com", "Del servidor")
    ng._negocio(YO)["cierres"].append({"fecha": ayer, "moneda": "PEN", "cobrado": 99, "porCobrar": 0, "reservas": 1,
                                        "cerradaEn": "x", "automatico": False, "medios": {}})
    dia = (hoy + timedelta(days=1)).weekday() + 1
    local = {"email": YO, "dispositivo": "dev_abc",
             "cierres": [{"fecha": ayer, "cobrado": 1, "porCobrar": 0, "reservas": 1, "cerradaEn": "2026-01-01T00:00:00", "automatico": False},
                         {"fecha": "2026-01-05", "cobrado": 120, "porCobrar": 30, "reservas": 3, "cerradaEn": "2026-01-05T23:00:00",
                          "automatico": True},
                         {"fecha": "malo"}],
             "fijas": [{"id": "fija_1", "canchaId": "c1", "diaSemana": dia, "hora": "19:00", "clienteNombre": "Pensión",
                        "clienteEmail": "", "clienteTelefono": "999", "activo": True},
                       {"id": "fija_2", "canchaId": "ajena", "diaSemana": 1, "hora": "19:00", "clienteNombre": "X", "activo": True}],
             "notas": {"ana@x.com": "Del teléfono", "n:carlos": "Paga en efectivo"},
             "recordados": {"al1": "2026-01-02T00:00:00Z"}}
    r = app_cli.post("/negocio/migrar", json=local).json()
    m = r["migracion"]
    assert r["ok"] and m["migrado"] and m == {"migrado": True, "ya": False, "cierres": 1, "fijas": 1, "notas": 1, "recordados": 1}
    # El servidor gana: el cierre de ayer y la nota de Ana se quedan como estaban.
    assert next(x for x in r["cierres"] if x["fecha"] == ayer)["cobrado"] == 99
    assert r["notas"] == {"ana@x.com": "Del servidor", "n:carlos": "Paga en efectivo"}
    jan = next(x for x in r["cierres"] if x["fecha"] == "2026-01-05")
    assert jan["moneda"] == "PEN" and jan["automatico"] and jan["origen"] == "app"
    assert [f["id"] for f in r["fijas"]] == ["fija_1"] and len(insertadas) == 4  # serie generada en el servidor
    # Idempotente: el mismo equipo no vuelve a subir (aunque mande otra cosa).
    r = app_cli.post("/negocio/migrar", json={**local, "notas": {"z@x.com": "nuevo"}}).json()
    assert r["migracion"]["ya"] and "z@x.com" not in r["notas"] and len(insertadas) == 4
    # Lo quitado en la web no lo resucita otro teléfono con la copia vieja.
    assert web.post("/anfitrion/fijas/fija_1/quitar").json()["ok"]
    r = app_cli.post("/negocio/migrar", json={**local, "dispositivo": "dev_otro"}).json()
    assert r["migracion"]["migrado"] and not r["fijas"]
    # Una cuenta sin canchas ni academias NO migra (lo del teléfono puede ser de otra cuenta).
    r = app_cli.post("/negocio/migrar", json={**local, "email": OTRO}).json()
    assert r["migracion"] == {"migrado": False, "motivo": "sin_negocio", "cierres": 0, "fijas": 0, "notas": 0, "recordados": 0}
    assert OTRO not in [k for k, v in stores.negocio_web.items() if v.get("migraciones")]
    assert app_cli.post("/negocio/migrar", json={**local, "dispositivo": ""}).status_code == 400


def test_app_key_y_token_de_usuario(entorno, monkeypatch):
    app_cli, _web, _ = entorno
    monkeypatch.setattr(config, "APP_API_KEY", "secreta")
    assert app_cli.get("/negocio/estado", params={"email": YO}).status_code == 401
    assert app_cli.get("/negocio/estado", params={"email": YO}, headers={"X-App-Key": "secreta"}).status_code == 200
    monkeypatch.setattr(config, "PAGOS_AUTH_USUARIO", "1")
    from pagos import router as pr
    monkeypatch.setattr(pr, "_email_de_token", lambda t: OTRO if t == "tok-otro" else (YO if t == "tok-yo" else None))
    h = {"X-App-Key": "secreta"}
    assert app_cli.post("/negocio/notas", json={"email": YO, "clave": "a@x.com", "texto": "x"},
                        headers={**h, "X-User-Token": "tok-otro"}).status_code == 403
    assert app_cli.post("/negocio/notas", json={"email": YO, "clave": "a@x.com", "texto": "x"},
                        headers={**h, "X-User-Token": "tok-yo"}).json()["ok"]


def test_borrar_negocio_dejar_en_virgen(entorno):
    app_cli, _web, _ = entorno
    assert app_cli.post("/negocio/notas", json={"email": YO, "clave": "a@x.com", "texto": "x"}).json()["ok"]
    assert app_cli.post("/negocio/borrar", json={"email": YO}).json()["ok"]
    assert YO not in stores.negocio_web
    assert app_cli.get("/negocio/estado", params={"email": YO}).json()["notas"] == {}
