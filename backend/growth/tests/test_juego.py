"""JUEGA YA (fases 1 y 2, 10-oct-2026): buscar u organizar un partido, buscar
partner de tenis/pickleball, jugadores disponibles cerca y avisos por push de
partidos nuevos cerca (`juego.py` + `web/jugador_partidos.py`)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
import juego
from db.store import stores
from main import app
from web import datos, horarios, sesion
from web import jugador_liga as JL
from web import jugador_partidos as JP

AHORA = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)      # lunes 10:00 en Lima
LIMA = (-12.10, -77.03)


@pytest.fixture
def jy(monkeypatch):
    antes = (dict(stores.juego_prefs), dict(stores.juego_avisos), dict(stores.juego_avisos_dia), dict(stores.config))
    stores.juego_prefs.clear()
    stores.juego_avisos.clear()
    stores.juego_avisos_dia.clear()
    stores.config["juego_avisos_activo"] = "1"
    stores.config["juego_avisos_tope_dia"] = "3"
    pushes = []
    monkeypatch.setattr(JL, "aviso_push", lambda em, t, c, tipo="aviso", data=None: pushes.append((em, t, c, tipo, data)))
    monkeypatch.setattr(JL, "perfiles", lambda emails: {e: {"nombre": e.split("@")[0].capitalize(), "foto_url": ""} for e in emails})
    monkeypatch.setattr(juego, "niveles_de_varios", lambda emails: {})
    yield pushes
    stores.juego_prefs.clear(); stores.juego_prefs.update(antes[0])
    stores.juego_avisos.clear(); stores.juego_avisos.update(antes[1])
    stores.juego_avisos_dia.clear(); stores.juego_avisos_dia.update(antes[2])
    stores.config.clear(); stores.config.update(antes[3])


def _pref(email, deportes=("futbol",), lat=LIMA[0], lng=LIMA[1], radio=10, franjas=(), dias="todos",
          avisos=True, disponible=False, actualizado=AHORA):
    stores.juego_prefs[email] = {"deportes": list(deportes), "radio_km": radio, "franjas": list(franjas), "dias": dias,
                                 "avisos": avisos, "disponible": disponible, "lat": lat, "lng": lng, "pais": "PE",
                                 "actualizado": actualizado.isoformat()}


def _partido(pid="p_1760000000000001", dep="futbol", lat=LIMA[0], lng=LIMA[1], fecha="2026-10-12", hora="20:00",
             cupos=10, jugadores=("org@x.com",), tipo="partido", modalidad="", nivel=""):
    return {"id": pid, "creador_email": "org@x.com", "creador_nombre": "Org", "deporte": dep, "titulo": "Fut 5 · Sabor Golazo",
            "fecha": fecha, "hora": hora, "sede": "Sabor Golazo", "lat": lat, "lng": lng, "cupos": cupos, "nota": "",
            "tipo": tipo, "modalidad": modalidad, "nivel": nivel, "etiquetas": [], "cancha_id": "",
            "jugadores": list(jugadores), "nombres": ["Org"] * len(jugadores)}


def _cli(monkeypatch, email="ana@gmail.com", nombre="Ana Pérez"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre, "foto": ""}))
    return cli


# ── Catálogos y validación de lo que se publica ─────────────────────────────

def test_publicar_partner_y_partido_solo_por_seleccion(monkeypatch, jy):
    monkeypatch.setattr(JP, "mi_nombre", lambda ses: ses.get("nombre") or ses["email"])
    monkeypatch.setattr(JP, "_pais_usuario", lambda email: "PE")
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [
        {"id": "c1", "club": "Sabor Golazo", "nombre": "Fútbol 1", "lat": -12.1, "lng": -77.0, "verificada": True, "dueno": "d@x.com"},
        {"id": "c9", "club": "Sin Dueño", "nombre": "Tenis 1", "lat": -12.2, "lng": -77.1, "verificada": False, "dueno": ""},
    ])
    creados = []
    monkeypatch.setattr(JP, "crear_partido", lambda p: creados.append(p) or True)
    cli = _cli(monkeypatch)
    hoy = horarios.ahora_local("PE").date().isoformat()
    base = {"sede": "Sabor Golazo", "fecha": hoy, "hora": "20:00"}
    # Partner: solo tenis/pickleball y con modalidad.
    r = cli.post("/web/partidos/crear", json={**base, "tipo": "partner", "deporte": "futbol", "modalidad": "singles"})
    assert r.status_code == 400 and "tenis" in r.json()["mensaje"]
    r = cli.post("/web/partidos/crear", json={**base, "tipo": "partner", "deporte": "tenis", "modalidad": ""})
    assert r.status_code == 400
    r = cli.post("/web/partidos/crear", json={**base, "tipo": "partner", "deporte": "tenis", "modalidad": "dobles",
                                              "nivel": "intermedio", "etiquetas": ["llevo_pelotas", "traer_pechera", "x"], "cupos": 30})
    assert r.json()["ok"]
    p = creados[-1]
    assert p["cupos"] == 4 and p["titulo"] == "Dobles de tenis · Sabor Golazo"          # cupos de la modalidad
    assert p["etiquetas"] == ["llevo_pelotas"]                                            # pechera no es de tenis
    assert p["cancha_id"] == "c1" and (p["lat"], p["lng"]) == (-12.1, -77.0)              # local reservable
    assert p["nota"] == ""
    # Mixto y Solo mujeres juntos, nivel inventado, más de 4 detalles → no.
    r = cli.post("/web/partidos/crear", json={**base, "deporte": "futbol", "cupos": 10, "etiquetas": ["mixto", "solo_mujeres"]})
    assert r.status_code == 400
    r = cli.post("/web/partidos/crear", json={**base, "deporte": "futbol", "cupos": 10, "nivel": "pro"})
    assert r.status_code == 400
    r = cli.post("/web/partidos/crear", json={**base, "deporte": "futbol", "cupos": 10,
                                              "etiquetas": ["cancha_reservada", "se_divide", "amistoso", "traer_pechera", "falta_arquero"]})
    assert r.status_code == 400
    # Otro lugar: se ubica con la posición del organizador; local sin dueño no da "Ver cancha".
    r = cli.post("/web/partidos/crear", json={**base, "sede": "Parque Kennedy", "deporte": "futbol", "cupos": 14,
                                              "lat": -12.1211, "lng": -77.0297})
    p = creados[-1]
    assert r.json()["ok"] and p["titulo"] == "Fut 7 · Parque Kennedy" and p["lat"] == -12.1211 and not p.get("cancha_id")
    r = cli.post("/web/partidos/crear", json={**base, "sede": "Sin Dueño", "deporte": "futbol", "cupos": 10})
    assert creados[-1]["cancha_id"] == ""


# ── Preferencias ─────────────────────────────────────────────────────────────

def test_preferencias_exigen_deporte_y_ubicacion_y_no_exponen_coordenadas(jy):
    with pytest.raises(ValueError, match="deporte"):
        juego.guardar_prefs("ana@x.com", {"avisos": True, "lat": -12.1, "lng": -77.0})
    with pytest.raises(ValueError, match="ubicación"):
        juego.guardar_prefs("ana@x.com", {"avisos": True, "deportes": ["futbol"]})
    with pytest.raises(ValueError, match="radio"):
        juego.guardar_prefs("ana@x.com", {"deportes": ["futbol"], "radio_km": 7})
    p = juego.guardar_prefs("Ana@X.com", {"avisos": True, "disponible": True, "deportes": ["tenis", "nado", "tenis"],
                                          "radio_km": 20, "franjas": ["noche", "x"], "dias": "finde",
                                          "lat": -12.123456, "lng": -77.031234})
    assert p["deportes"] == ["tenis"] and p["franjas"] == ["noche"] and p["radio_km"] == 20 and p["pais"] == "PE"
    assert stores.juego_prefs["ana@x.com"]["lat"] == -12.123                               # ubicación aproximada
    assert "lat" not in juego.publicas(p)
    # Apagar avisos sin mandar ubicación conserva la guardada.
    p = juego.guardar_prefs("ana@x.com", {"deportes": ["tenis"], "avisos": False, "disponible": False})
    assert stores.juego_prefs["ana@x.com"]["lat"] == -12.123
    # Eliminar mi cuenta / dejar en virgen borra las preferencias.
    stores.reset_billetera_de("ana@x.com")
    assert "ana@x.com" not in stores.juego_prefs


# ── Jugadores disponibles (partner) ──────────────────────────────────────────

def test_jugadores_disponibles_cerca_por_deporte_y_radio(monkeypatch, jy):
    _pref("cerca@x.com", ("tenis",), lat=-12.11, lng=-77.03, disponible=True, avisos=False)          # ~1 km
    _pref("lejos@x.com", ("tenis",), lat=-12.30, lng=-77.03, disponible=True, radio=30)              # ~22 km
    _pref("chico@x.com", ("tenis",), lat=-12.16, lng=-77.03, disponible=True, radio=5)               # ~6.7 km, su radio 5
    _pref("futbol@x.com", ("futbol",), disponible=True)
    _pref("oculto@x.com", ("tenis",), disponible=False)
    _pref("viejo@x.com", ("tenis",), disponible=True, actualizado=AHORA - timedelta(days=90))
    _pref("yo@x.com", ("tenis",), disponible=True)
    js = juego.disponibles("yo@x.com", "tenis", LIMA[0], LIMA[1], 10, ahora=AHORA)
    assert [j["email"] for j in js] == ["cerca@x.com"]
    js = juego.disponibles("yo@x.com", "tenis", LIMA[0], LIMA[1], 30, ahora=AHORA)
    assert [j["email"] for j in js] == ["cerca@x.com", "lejos@x.com"]
    assert js[0]["km"] == 1.0 and "lat" not in js[0] and js[0]["banda"] == "intermedio"
    # La web cambia correos por refs opacos.
    monkeypatch.setattr(juego, "disponibles", lambda em, dep, la, ln, r: [
        {"email": "cerca@x.com", "nombre": "Cerca", "foto": "", "nivel": 4.2, "banda": "avanzado", "km": 1.0,
         "franjas": ["noche"], "dias": "todos"}])
    r = _cli(monkeypatch).get("/web/juego/disponibles", params={"deporte": "tenis", "lat": -12.1, "lng": -77.0}).json()
    assert r["jugadores"][0]["ref"] and "cerca@x.com" not in str(r)
    assert JL.email_de_ref(r["jugadores"][0]["ref"]) == "cerca@x.com"
    assert "Avanzado · 4.2" in r["jugadores"][0]["nivel_txt"]


# ── Avisos de partidos cerca (fase 2) ────────────────────────────────────────

def test_aviso_a_quien_le_calza_deporte_distancia_hora_dia_y_nivel(jy):
    _pref("si@x.com")                                                       # fútbol, 10 km, cualquier hora
    _pref("tenis@x.com", ("tenis",))
    _pref("lejos@x.com", lat=-12.40, lng=-77.03)                            # ~33 km
    _pref("manana@x.com", franjas=("manana",))                              # el partido es de noche
    _pref("finde@x.com", dias="finde")                                      # el partido es lunes
    _pref("sinaviso@x.com", avisos=False)
    _pref("org@x.com")                                                      # el creador
    _pref("dentro@x.com")
    p = _partido(jugadores=("org@x.com", "dentro@x.com"))
    assert [c[0] for c in juego.candidatos(p, AHORA)] == ["si@x.com"]
    # Nivel: solo a quien está en esa banda (sin dato = intermedio).
    _pref("pro@x.com")
    p2 = {**_partido(), "nivel": "avanzado"}
    assert [c[0] for c in juego.candidatos(p2, AHORA, {("pro@x.com", "futbol"): 4.6})] == ["pro@x.com"]
    # Lleno, sin ubicación o empieza en menos de 30 min → nadie.
    assert juego.candidatos(_partido(cupos=1), AHORA) == []
    assert juego.candidatos(_partido(lat=None, lng=None), AHORA) == []
    assert juego.candidatos(_partido(hora="10:20"), AHORA) == []
    # Avisar: una sola vez por partido, con datos para abrir la pantalla.
    del stores.juego_prefs["pro@x.com"]
    assert juego.avisar_partido(p, AHORA) == 1
    em, titulo, cuerpo, tipo, data = jy[-1]
    assert em == "si@x.com" and tipo == "partido" and data["partido_id"] == p["id"]
    assert "Faltan 8" in titulo.replace("falta", "Falta") and "a 0.5 km" in cuerpo
    assert juego.avisar_partido(p, AHORA) == 0 and len(jy) == 1


def test_tope_diario_y_corte_de_emergencia(jy):
    _pref("si@x.com")
    for i in range(5):
        juego.avisar_partido(_partido(pid=f"p_17600000000000{i:02d}"), AHORA)
    assert len(jy) == 3                                                      # tope 3 por día
    stores.config["juego_avisos_activo"] = "0"
    stores.juego_avisos_dia.clear()
    assert juego.avisar_partido(_partido(pid="p_1760000000000099"), AHORA) == 0
    assert stores.juego_avisos["p_1760000000000099"]["nota"] == "apagado"


def test_barrido_avisa_partidos_nuevos_de_app_y_web_y_partner(monkeypatch, jy):
    _pref("tenista@x.com", ("tenis",))
    nuevos = [_partido(pid="p_1760000000000001", dep="tenis", tipo="partner", modalidad="singles", cupos=2),
              _partido(pid="p_1760000000000002")]
    monkeypatch.setattr(juego, "partidos_nuevos", lambda ahora: nuevos)
    assert juego.avisar_nuevos(AHORA) == 1
    assert "partner de tenis" in jy[0][1] and "Singles" in jy[0][2]
    assert set(stores.juego_avisos) == {"p_1760000000000001", "p_1760000000000002"}
    assert juego.avisar_nuevos(AHORA) == 0
    # Se podan a los 7 días.
    juego._podar(AHORA + timedelta(days=8))
    assert not stores.juego_avisos


# ── API del APK y página web ─────────────────────────────────────────────────

def test_api_del_apk_y_snapshot(monkeypatch, jy):
    cli = TestClient(app)
    c = cli.get("/juego/config").json()
    assert c["deportes_partner"] == ["tenis", "pickleball"] and c["radios"] == [5, 10, 20, 30]
    assert any(x["clave"] == "llevo_pelotas" for x in c["etiquetas"])
    r = cli.post("/juego/prefs", json={"email": "luis@x.com", "avisos": True, "deportes": ["futbol"]})
    assert r.status_code == 400 and "ubicación" in r.json()["mensaje"]
    r = cli.post("/juego/prefs", json={"email": "luis@x.com", "avisos": True, "deportes": ["futbol"], "lat": -12.1, "lng": -77.0})
    assert r.json()["ok"] and r.json()["prefs"]["avisos"] and "lat" not in r.json()["prefs"]
    assert cli.get("/juego/prefs", params={"email": "luis@x.com"}).json()["prefs"]["tiene_ubicacion"]
    _pref("ana@x.com", ("tenis",), disponible=True, actualizado=datetime.now(timezone.utc))
    js = cli.get("/juego/disponibles", params={"email": "luis@x.com", "deporte": "tenis", "lat": LIMA[0], "lng": LIMA[1]}).json()
    assert [j["email"] for j in js["jugadores"]] == ["ana@x.com"]
    estado = stores.to_state()
    assert estado["juego_prefs"]["luis@x.com"]["avisos"] is True
    stores.juego_prefs.clear()
    stores.load_state(estado)
    assert stores.juego_prefs["luis@x.com"]["deportes"] == ["futbol"]


def test_pagina_juega_ya_con_partner_y_avisos(monkeypatch, jy):
    monkeypatch.setattr(JP, "_pais_usuario", lambda email: "PE")
    monkeypatch.setattr(JP, "datos_ranking", lambda: {"academias": [], "retos": [], "campeonatos": []})
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [])
    monkeypatch.setattr(datos, "niveles_de", lambda em: [{"deporte": "tenis", "nivel": 4.5, "partidos": 0, "victorias": 0}])
    hoy = horarios.ahora_local("PE").date().isoformat()
    ps = [{**_partido(pid="p_1760000000000001", fecha=hoy), "etiquetas": ["cancha_reservada"], "nivel": "intermedio"},
          {**_partido(pid="p_1760000000000002", dep="tenis", tipo="partner", modalidad="singles", cupos=2, fecha=hoy),
           "titulo": "Singles de tenis · Club X"}]
    monkeypatch.setattr(JP, "partidos_desde", lambda h: ps)
    cli = _cli(monkeypatch)
    html = cli.get("/partidos").text
    assert "Juega ya" in html and "Busco partner" in html and "Organizo un partido" in html
    assert "p_1760000000000001" in html and "p_1760000000000002" not in html            # pestaña Partidos
    assert "✅ Cancha ya reservada" in html and "Nivel ⚡ Intermedio" in html
    assert "data-lat='-12.1'" in html and "Avísame partidos cerca" in html
    html = cli.get("/partidos?tab=partner").text
    assert "p_1760000000000002" in html and "p_1760000000000001" not in html
    assert "Jugadores disponibles cerca" in html and "🎾 Juego contigo" in html
    assert '"misNiveles": {"tenis": "avanzado"}' in html
    assert "org@x.com" not in html
    r = cli.post("/web/juego/prefs", json={"avisos": True, "deportes": ["tenis"], "radio_km": 20, "lat": -12.1, "lng": -77.0})
    assert r.json()["ok"] and "Avisos encendidos" in r.json()["texto"] and "a 20 km" in r.json()["texto"]
