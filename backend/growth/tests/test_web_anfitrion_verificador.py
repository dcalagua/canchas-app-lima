"""Verificador (rol de campo) y verificación de propiedad del dueño en la web,
espejo de verificador_screen / validar_reclamo_screen / verificar_propiedad_screen
y del panel "pendiente" de la ficha del app."""
import pytest
from fastapi.testclient import TestClient

import config
from db.store import VerificacionFisica, ahora, stores
from main import app
from propiedad import reclamos
from web import almacen, anfitrion_verificador as av, datos, sesion

LAT, LNG = -12.0432, -76.9540


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    stores.reset()
    av._reset_limites()
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "PICHANGOL_ADMIN_WHATSAPP", "")
    monkeypatch.setattr(config, "VALIDADOR_ACTIVA_AUTOMATICO", True)
    monkeypatch.setattr(config, "OTP_DEBUG_DEVOLVER_CODIGO", True)
    monkeypatch.setattr(config, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(datos, "cancha", lambda cid: {"id": cid, "nombre": "Fútbol 1", "club": "La Pichanga",
                                                      "direccion": "Av. Siempre Viva 123", "barrio": "Ate", "lat": LAT, "lng": LNG})
    monkeypatch.setattr(datos, "marcar_verificada", lambda *a, **k: 0)
    yield
    av._reset_limites()


def _cli(email="due@x.com", nombre="Dueño Uno"):
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre, "foto": ""}))
    return cli


def _mis_canchas(monkeypatch, verificada=False):
    fila = {"id": "u1", "nombre": "Fútbol 1", "club": "La Pichanga", "dueno": "due@x.com",
            "verificada": verificada, "lat": LAT, "lng": LNG}
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [fila] if e.lower() == "due@x.com" else [])
    return fila


def test_verificador_cola_por_cercania_y_captura_con_fotos(monkeypatch):
    r = TestClient(app, base_url="https://testserver").get("/anfitrion/verificador", follow_redirects=False)
    assert r.status_code == 302 and "volver=%2Fanfitrion%2Fverificador" in r.headers["location"]
    html = _cli().get("/anfitrion/verificador").text
    # La página funcional reemplaza a la de "está en la app" del comodín.
    assert "Visitas pendientes" in html and "Validar reclamo por código" in html and "está en la app" not in html
    for js in (av._JS_BASE, av._JS_VERIFICADOR, av._JS_ESTADO):  # nunca diálogos nativos
        assert " confirm(" not in js and "alert(" not in js and "prompt(" not in js

    c = stores.cancha("u1"); c.lat_declarada, c.lng_declarada = LAT, LNG
    lejos = stores.cancha("u2"); lejos.lat_declarada, lejos.lng_declarada = -16.5, -68.15  # La Paz
    for i, cid in ((1, "u1"), (2, "u2")):
        stores.verificaciones_fisicas.append(VerificacionFisica(
            id=i, cancha_id=cid, solicitud_id=None, motivo="ia_no_concluyente", verificador_id=None,
            estado="agendada", fotos_geo_urls=[], lat_sitio=None, lng_sitio=None, firma_verificador=None,
            observaciones=None, metodo=None, creado_en=ahora()))
    cli = _cli("moto@x.com", "Moto Rider")
    vs = cli.get(f"/anfitrion/verificador/visitas?lat={LAT}&lng={LNG}&radio_km=50").json()["visitas"]
    assert [v["id"] for v in vs] == [1] and vs[0]["nombre"] == "La Pichanga" and vs[0]["distancia_m"] == 0
    assert len(cli.get("/anfitrion/verificador/visitas").json()["visitas"]) == 2  # sin GPS = todas

    # Foto del sitio → misma carpeta que el app (canchas/verif/<vf>_<i>_<ms>.jpg).
    subidas = []
    monkeypatch.setattr(almacen, "subir", lambda b, ruta, d, ct="image/jpeg", **k: subidas.append(ruta) or almacen.url_publica(ruta) + "?v=1")
    j = cli.post("/anfitrion/verificador/foto?carpeta=verif&ref=1&i=0&ts=123", content=b"jpg", headers={"Content-Type": "image/jpeg"}).json()
    assert j["ok"] and subidas == ["verif/1_0_123.jpg"]
    assert cli.post("/anfitrion/verificador/foto?carpeta=../x&ref=1", content=b"j", headers={"Content-Type": "image/jpeg"}).status_code == 400

    # Sin fotos propias → rechazo; fotos ajenas no cuentan.
    r = cli.post("/anfitrion/verificador/visita/1/captura", json={"fotos": ["https://evil/x.jpg"], "lat": LAT, "lng": LNG, "firma": "Moto"}).json()
    assert not r["ok"] and "foto" in r["mensaje"]
    # GPS lejos → rechazada (misma regla que el app).
    r = cli.post("/anfitrion/verificador/visita/1/captura", json={"fotos": [j["url"]], "lat": -12.2, "lng": -77.1, "firma": "Moto Rider"}).json()
    assert not r["ok"] and r["estado"] == "rechazada"
    # Visita 2 en el sitio → confirmada y la cancha verificada en persona.
    lejos_url = cli.post("/anfitrion/verificador/foto?carpeta=verif&ref=2&i=0&ts=5", content=b"jpg", headers={"Content-Type": "image/jpeg"}).json()["url"]
    r = cli.post("/anfitrion/verificador/visita/2/captura", json={"fotos": [lejos_url], "lat": -16.5, "lng": -68.15, "firma": "Moto Rider"}).json()
    assert r["ok"] and r["estado"] == "confirmada" and stores.cancha("u2").verificada_en_persona
    vf = stores.verificaciones_fisicas[1]
    assert vf.fotos_geo_urls == [lejos_url] and "moto@x.com" in vf.firma_verificador
    # Ya no está pendiente.
    assert not cli.post("/anfitrion/verificador/visita/2/captura", json={"fotos": [lejos_url], "lat": -16.5, "lng": -68.15, "firma": "Moto"}).json()["ok"]


def test_validar_reclamo_por_codigo_con_gps_y_anti_fuerza_bruta():
    res = reclamos.crear_reclamo("u1", "due@x.com", "La Pichanga", "51987654321", lat=LAT, lng=LNG)
    reclamos.triage(res["reclamo_id"], True)
    cod = res["codigo"]
    # El dueño no valida su propio reclamo.
    r = _cli().post("/anfitrion/verificador/validar", json={"codigo": cod, "lat": LAT, "lng": LNG}).json()
    assert not r["ok"] and r["error"] == "propio"
    moto = _cli("moto@x.com")
    # Lejos del local → no coincide (RECLAMO_VALIDACION_GPS_MAX_M).
    r = moto.post("/anfitrion/verificador/validar", json={"codigo": cod, "lat": LAT + 0.01, "lng": LNG}).json()
    assert r["error"] == "ubicacion_no_coincide" and r["distancia_m"] > config.RECLAMO_VALIDACION_GPS_MAX_M
    # En el sitio → activada y el validador es el correo de la sesión.
    r = moto.post("/anfitrion/verificador/validar", json={"codigo": cod, "lat": LAT, "lng": LNG}).json()
    assert r["ok"] and r["estado"] == "activada"
    assert stores.reclamos[-1].validador == "moto@x.com" and stores.cancha("u1").verificada_en_persona
    # Códigos equivocados: a los 8 fallos se bloquea (aunque luego acierte).
    otro = _cli("pirata@x.com")
    for n in range(8):
        assert otro.post("/anfitrion/verificador/validar", json={"codigo": f"{n:06d}", "lat": LAT, "lng": LNG}).json()["error"] == "codigo_invalido"
    assert otro.post("/anfitrion/verificador/validar", json={"codigo": cod, "lat": LAT, "lng": LNG}).json()["error"] == "demasiados_intentos"
    # Sin sesión → 401.
    assert TestClient(app, base_url="https://testserver").post("/anfitrion/verificador/validar", json={}).status_code == 401


def test_estado_de_mi_verificacion_verificar_y_reenviar(monkeypatch):
    _mis_canchas(monkeypatch)
    cli = _cli()
    # Cancha ajena → 404.
    assert _cli("otro@x.com").get("/anfitrion/verificacion/u1").status_code == 404
    # Sin reclamo en el servidor (se perdió) → lo dice y ofrece reenviar.
    html = cli.get("/anfitrion/verificacion/u1").text
    assert "Sin solicitud de verificación" in html and "Volver a solicitar" in html
    j = cli.post("/anfitrion/verificacion/u1/estado").json()
    assert "No encontramos tu solicitud" in j["mensaje"]
    # Reenviar = crear_reclamo con la cuenta de la sesión, el punto de la cancha y el GPS del navegador.
    j = cli.post("/anfitrion/verificacion/u1/reenviar", json={"lat": LAT, "lng": LNG}).json()
    assert j["ok"] and j["estado"] == "pendiente_triage"
    r = stores.reclamos[-1]
    assert r.solicitante_id == "due@x.com" and r.nombre_local == "La Pichanga" and r.solicitante_lat == LAT and r.lat == LAT
    # Reenviar otra vez es idempotente (recordatorio al admin, mismo reclamo).
    j2 = cli.post("/anfitrion/verificacion/u1/reenviar", json={}).json()
    assert j2["ok"] and j2["reclamo_id"] == r.id and j2["reenviado"] and len(stores.reclamos) == 1
    html = cli.get("/anfitrion/verificacion/u1").text
    assert "En verificación" in html and "Reenviar solicitud de verificación" in html and f"Solicitud #{r.id}" in html
    assert "sigue en revisión" in cli.post("/anfitrion/verificacion/u1/estado").json()["mensaje"] or \
        "Estamos confirmando" in cli.post("/anfitrion/verificacion/u1/estado").json()["mensaje"]
    # La torre aprueba pero el espejo en la nube falló → "Verificar estado ahora" lo repara.
    llamadas = []
    monkeypatch.setattr(datos, "marcar_verificada", lambda cid, d, v, la=None, ln=None: llamadas.append((cid, d, v)) or 1)
    monkeypatch.setattr(reclamos, "_nube_verificada", lambda r, v: None)
    reclamos.aprobar_directo(r.id, "admin")
    j = cli.post("/anfitrion/verificacion/u1/estado").json()
    assert j["recargar"] and "Aprobada" in j["titulo"] and llamadas == [("u1", "due@x.com", True)]
    # Rechazo → "Volver a solicitar" crea uno nuevo.
    _mis_canchas(monkeypatch)
    reclamos.triage(r.id, False, "admin")
    assert "no aprobada" in cli.post("/anfitrion/verificacion/u1/estado").json()["titulo"].lower()
    assert "Volver a solicitar" in cli.get("/anfitrion/verificacion/u1").text
    j = cli.post("/anfitrion/verificacion/u1/reenviar", json={}).json()
    assert j["ok"] and not j["reenviado"] and len(stores.reclamos) == 2


def test_otp_whatsapp_prueba_el_telefono_y_no_activa_sola(monkeypatch):
    _mis_canchas(monkeypatch)
    cli = _cli()
    assert "Confirma el WhatsApp" not in cli.get("/anfitrion/verificacion/u1").text  # sin reclamo, sin OTP
    assert not cli.post("/anfitrion/verificacion/u1/otp/enviar", json={"telefono": "987654321"}).json()["ok"]
    reclamos.crear_reclamo("u1", "due@x.com", "La Pichanga", "51987654321", lat=LAT, lng=LNG)
    html = cli.get("/anfitrion/verificacion/u1").text
    assert "Confirma el WhatsApp del local" in html and "value='987654321'" in html and "+51" in html
    assert "9 dígitos" in cli.post("/anfitrion/verificacion/u1/otp/enviar", json={"telefono": "123"}).json()["mensaje"]
    j = cli.post("/anfitrion/verificacion/u1/otp/enviar", json={"telefono": "987 654 321"}).json()
    assert j["ok"] and j["via"] == "stub" and j["telefono_enmascarado"].endswith("4321") and len(j["codigo_debug"]) == 6
    # Otra cuenta no canjea el código ajeno.
    assert not _cli("otro@x.com").post("/anfitrion/verificacion/u1/otp/confirmar", json={"codigo": j["codigo_debug"]}).json()["ok"]
    malo = cli.post("/anfitrion/verificacion/u1/otp/confirmar", json={"codigo": "000000" if j["codigo_debug"] != "000000" else "111111"}).json()
    assert not malo["ok"] and "incorrecto" in malo["mensaje"]
    ok = cli.post("/anfitrion/verificacion/u1/otp/confirmar", json={"codigo": j["codigo_debug"]}).json()
    assert ok["ok"]
    r = stores.reclamos[-1]
    # Evidencia en el reclamo; la cancha NO queda verificada ni el reclamo activado.
    assert "confirmado por código" in r.nota_reclamante and r.telefono_contacto == "51987654321"
    assert r.estado == "pendiente_triage" and not stores.cancha("u1").verificada
    assert not reclamos.estado("u1", "due@x.com")["verificada"]
    assert "Confirmado por código" in cli.get("/anfitrion/verificacion/u1").text
    # Anti spam de envíos: 5 por hora.
    for _ in range(5):
        cli.post("/anfitrion/verificacion/u1/otp/enviar", json={"telefono": "987654321"})
    assert "varios códigos" in cli.post("/anfitrion/verificacion/u1/otp/enviar", json={"telefono": "987654321"}).json()["mensaje"]


def test_bolivia_usa_su_prefijo_y_largo(monkeypatch):
    fila = {"id": "b1", "nombre": "Cancha", "club": "El Prado", "dueno": "due@x.com", "verificada": False, "lat": -16.5, "lng": -68.15}
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [fila])
    reclamos.crear_reclamo("b1", "due@x.com", "El Prado", "59171234567", lat=-16.5, lng=-68.15)
    cli = _cli()
    html = cli.get("/anfitrion/verificacion/b1").text
    assert "+591" in html and "value='71234567'" in html
    j = cli.post("/anfitrion/verificacion/b1/otp/enviar", json={"telefono": "71234567"}).json()
    assert j["ok"] and stores.otps["b1"].telefono == "59171234567"
