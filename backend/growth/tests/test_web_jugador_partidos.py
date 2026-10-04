"""Partidos, pichangas de club, Invita y gana, carnet del jugador y Llenar
cancha en la web = mismas pantallas y reglas del app (pedido del director:
"en la web implementa las mismas funcionalidades que existen en el app")."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from db.store import stores
from main import app
from web import datos, horarios, sesion
from web import jugador_partidos as JP


def _cli(monkeypatch, email="ana@gmail.com", nombre="Ana Pérez"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre, "foto": ""}))
    return cli


def _sin_popups_nativos(txt: str) -> bool:
    """Solo en el contenido de estas páginas (el shell compartido lo cubren sus tests)."""
    mio = txt.split("jp-wrap", 1)[-1]
    return re.search(r"(?<![\w.])(?:window\.)?(confirm|alert|prompt)\(", mio) is None


@pytest.fixture
def aislado(monkeypatch):
    antes = (list(stores.convocatorias), list(stores.inscripciones), dict(stores.config))
    stores.convocatorias[:] = []
    stores.inscripciones[:] = []
    avisos = []
    monkeypatch.setattr(JP, "aviso_push", lambda em, t, c, tipo="aviso", data=None: avisos.append((em, t)))
    monkeypatch.setattr(JP, "mi_nombre", lambda ses: ses.get("nombre") or ses["email"])
    monkeypatch.setattr(JP, "_pais_usuario", lambda email: "PE")
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [
        {"id": "c1", "club": "Sabor Golazo", "nombre": "Fútbol 1", "lat": -12.1, "lng": -77.0},
    ])
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [])
    yield avisos
    stores.convocatorias[:] = antes[0]
    stores.inscripciones[:] = antes[1]
    stores.config.clear(); stores.config.update(antes[2])


# ═══════════════════════════════ PARTIDOS ═════════════════════════════════════

def _partido(pid="p_1700000000000001", creador="luis@x.com", jugadores=("luis@x.com",), cupos=4, lat=None, lng=None, fecha=None):
    return {"id": pid, "creador_email": creador, "creador_nombre": "Luis", "deporte": "futbol",
            "titulo": "Fulbito de los viernes", "fecha": fecha or horarios.ahora_local("PE").date().isoformat(), "hora": "20:00",
            "sede": "Sabor Golazo", "lat": lat, "lng": lng, "cupos": cupos, "nota": "Traer pechera",
            "jugadores": list(jugadores), "nombres": ["Luis Rojas"] * len(jugadores)}


def test_partidos_como_el_app(monkeypatch, aislado):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app, base_url="https://testserver").get("/partidos", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fpartidos"

    ps = [_partido(),  # sin ubicación → sale en cualquier país
          _partido("p_1700000000000002", creador="ana@gmail.com", jugadores=("ana@gmail.com",), lat=-12.1, lng=-77.0),
          _partido("p_1700000000000003", lat=-0.18, lng=-78.48)]  # Quito → no sale en Perú
    monkeypatch.setattr(JP, "partidos_desde", lambda hoy: ps)
    monkeypatch.setattr(JP, "datos_ranking", lambda: {"academias": [], "retos": [], "campeonatos": []})
    html = _cli(monkeypatch).get("/partidos").text
    assert "Fulbito de los viernes" in html and "Faltan 3" in html and "Traer pechera" in html
    assert "p_1700000000000003" not in html                         # filtro por país
    assert "data-apuntar='p_1700000000000001'" in html               # no estoy → Me apunto
    assert "data-cupo='p_1700000000000002'" in html and "data-eliminar='p_1700000000000002'" in html  # soy creadora
    assert "href='/mensajes/" in html                                # Coordinar = chat del grupo
    assert "href='/pichangas'" in html and "Crear partido" in html
    assert _sin_popups_nativos(html)
    assert "luis@x.com" not in html                                  # los correos de otros no viajan

    # Crear: validación como `_publicar` (sede obligatoria, fecha/hora, 2-40).
    creados = []
    monkeypatch.setattr(JP, "crear_partido", lambda p: creados.append(p) or True)
    cli = _cli(monkeypatch)
    hoy = horarios.ahora_local("PE").date().isoformat()
    r = cli.post("/web/partidos/crear", json={"deporte": "futbol", "sede": "", "fecha": hoy, "hora": "20:00", "cupos": 10})
    assert r.status_code == 400 and "¿Dónde se juega?" in r.json()["mensaje"]
    r = cli.post("/web/partidos/crear", json={"deporte": "futbol", "sede": "Sabor Golazo", "fecha": hoy, "hora": "25:00", "cupos": 10})
    assert r.status_code == 400
    r = cli.post("/web/partidos/crear", json={"deporte": "futbol", "sede": "Sabor Golazo", "fecha": hoy, "hora": "20:00", "cupos": 50})
    assert r.status_code == 400
    r = cli.post("/web/partidos/crear", json={"deporte": "futbol", "sede": "Sabor Golazo", "fecha": hoy, "hora": "20:30", "cupos": 10})
    assert r.json()["ok"] is True
    p = creados[0]
    assert p["creador_email"] == "ana@gmail.com" and p["titulo"] == "Fútbol · Sabor Golazo"  # título por defecto del app
    assert (p["lat"], p["lng"]) == (-12.1, -77.0) and p["id"].startswith("p_")                # ubicación del local conocido

    # Apuntarse lleno → 409 con el texto del app; salir siendo creador → no.
    monkeypatch.setattr(JP, "apuntarse", lambda pid, em, nom: "lleno")
    r = cli.post("/web/partidos/p_1700000000000001/apuntarse")
    assert r.status_code == 409 and r.json()["error"] == "lleno"
    monkeypatch.setattr(JP, "partido", lambda pid: ps[1])
    assert cli.post("/web/partidos/p_1700000000000002/salir").status_code == 400
    # +1 cupo: solo el creador.
    monkeypatch.setattr(JP, "partido", lambda pid: ps[0])
    assert cli.post("/web/partidos/p_1700000000000001/cupo", json={"cupos": 5}).status_code == 404
    monkeypatch.setattr(JP, "partido", lambda pid: ps[1])
    monkeypatch.setattr(JP, "cambiar_cupos", lambda pid, em, n: em == "ana@gmail.com")
    assert cli.post("/web/partidos/p_1700000000000002/cupo", json={"cupos": 99}).json() == {"ok": True, "cupos": 40}
    # Sin sesión, las acciones responden 401.
    anon = TestClient(app, base_url="https://testserver")
    assert anon.post("/web/partidos/p_1700000000000001/apuntarse").status_code == 401


# ═══════════════════════════════ PICHANGAS ════════════════════════════════════

def test_pichangas_de_club_con_cupos_espera_y_modos(monkeypatch, aislado):
    dueno = [{"id": "c1", "club": "Sabor Golazo", "nombre": "Fútbol 1", "deporte": "futbol", "deportes": ["futbol"]}]
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: dueno if e == "dueno@x.com" else [])
    jugador = _cli(monkeypatch)
    # Un jugador sin local no convoca.
    assert "Las pichangas las organiza el club" in jugador.get("/pichangas/nueva").text
    r = jugador.post("/web/pichangas/crear", json={"club": "sabor_golazo", "titulo": "Fulbito", "cupos": 2, "modo": "orden_llegada"})
    assert r.status_code == 403

    admin = _cli(monkeypatch, "dueno@x.com", "Dueño")
    html = admin.get("/pichangas/nueva").text
    assert "Orden de llegada" in html and "Sorteo" in html and "Equidad" in html and _sin_popups_nativos(html)
    r = admin.post("/web/pichangas/crear", json={"club": "sabor_golazo", "titulo": "Fulbito Máster", "deporte": "futbol",
                                                "categoria": "master", "cupos": 2, "modo": "orden_llegada", "fecha": "2026-10-01"})
    assert r.json()["ok"] is True
    cid = r.json()["id"]
    c = stores.convocatorias[-1]
    assert c.club_id == "sabor_golazo" and c.creado_por == "dueno@x.com" and c.fecha_partido == "Jue 1 oct"

    # Orden de llegada: dos entran, el tercero a la espera.
    assert jugador.post(f"/web/pichangas/{cid}/inscribir").json()["estado"] == "confirmado"
    beto = _cli(monkeypatch, "beto@x.com", "Beto")
    assert beto.post(f"/web/pichangas/{cid}/inscribir").json()["estado"] == "confirmado"
    caro = _cli(monkeypatch, "caro@x.com", "Caro")
    r = caro.post(f"/web/pichangas/{cid}/inscribir").json()
    assert r["estado"] == "lista_espera" and "puesto 1" in r["mensaje"]
    html = caro.get(f"/pichangas/{cid}").text
    assert "En lista de espera" in html and "Caro (tú)" in html and "caro@x.com" not in html.split("<main", 1)[-1].split("menu", 1)[0]
    assert "Panel del organizador" not in html                      # el jugador no administra
    assert "Sabor Golazo" in jugador.get("/pichangas").text

    # Solo el organizador cierra; al cerrar llegan los pushes.
    assert jugador.post(f"/web/pichangas/{cid}/cerrar").status_code == 403
    assert admin.post(f"/web/pichangas/{cid}/cerrar").json()["ok"] is True
    assert ("caro@x.com", "Quedaste en lista de espera ⏳") in aislado
    html = admin.get(f"/pichangas/{cid}").text
    assert "Panel del organizador" in html and "Marcar asistencia" in html
    # Asistencia por índice (el navegador no ve correos): Beto no vino.
    r = admin.post(f"/web/pichangas/{cid}/asistencia", json={"marcas": [{"i": 0, "asistio": True}, {"i": 1, "asistio": False}]})
    assert r.json()["ok"] is True
    rk = admin.get("/pichangas/ranking?club=sabor_golazo").text
    assert "1 no-show" in rk and "Ranking de socios" in rk
    # El ranking de socios es del organizador.
    assert jugador.get("/pichangas/ranking?club=sabor_golazo", follow_redirects=False).status_code == 302


def test_pichanga_sorteo_queda_en_la_bolsa_hasta_cerrar(monkeypatch, aislado):
    dueno = [{"id": "c1", "club": "Club Ñandú", "nombre": "Cancha", "deporte": "futbol", "deportes": []}]
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: dueno if e == "dueno@x.com" else [])
    assert JP.slug_club("Club Ñandú Álamos") == "club_nandu_alamos"
    admin = _cli(monkeypatch, "dueno@x.com", "Dueño")
    cid = admin.post("/web/pichangas/crear", json={"club": "club_nandu", "titulo": "Sorteo", "cupos": 1, "modo": "sorteo", "categoria": "libre"}).json()["id"]
    r = _cli(monkeypatch).post(f"/web/pichangas/{cid}/inscribir").json()
    assert r["estado"] == "en_bolsa" and "al cerrar" in r["mensaje"]
    assert "Anotado — en la bolsa" in _cli(monkeypatch).get(f"/pichangas/{cid}").text


# ═══════════════════════════════ REFERIDOS ════════════════════════════════════

def _codigo_ref(email):
    h = 7
    for ch in email:
        h = (h * 31 + ord(ch)) & 0x7FFFFFFF
    n, s = h, ""
    while True:
        n, r = divmod(n, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
        if not n:
            break
    return "PCG" + s.upper().rjust(6, "0")[-6:]


def test_invita_y_gana_como_el_app(monkeypatch, aislado):
    assert JP.codigo_referido(" Ana@Gmail.com ") == _codigo_ref("ana@gmail.com")
    cod = JP.codigo_referido("ana@gmail.com")
    monkeypatch.setattr(JP._ref, "estado", lambda e: {
        "ok": True, "codigo": cod, "invitados": 3, "ganado_centimos": 3000, "moneda": "PEN",
        "simbolo": "S/", "bono_centimos": 1000, "canjeado": "", "tope_alcanzado": False})
    html = _cli(monkeypatch).get("/referidos").text
    assert cod in html and "3 personas ya usaron tu código." in html and "S/ 30 ganados" in html
    assert "wa.me" in html and "S/ 10 para cada uno" in html and "rfCanjear" in html and _sin_popups_nativos(html)


# ═══════════════════════════════ CARNET ═══════════════════════════════════════

def test_carnet_del_jugador_como_perfil_global(monkeypatch, aislado):
    d = {"academias": [{"id": "a1", "nombre": "Academia Sol", "deporte": "tenis", "categorias": {"j1": "4ta"}, "partidos": [
            {"jugadorAId": "j1", "jugadorANombre": "Eva Díaz", "jugadorAEmail": "eva@x.com", "jugadorBId": "j2",
             "jugadorBNombre": "Rita", "jugadorBEmail": "", "ganadorId": "j1", "marcador": "6-3 6-4", "fecha": "2026-09-01T10:00:00"},
            {"jugadorAId": "j2", "jugadorANombre": "Rita", "jugadorBId": "j1", "jugadorBNombre": "Eva Díaz",
             "jugadorBEmail": "eva@x.com", "ganadorId": "j2", "fecha": "2026-09-10T10:00:00"}]}],
         "retos": [{"id": 5, "retador_email": "eva@x.com", "retador_nombre": "Eva Díaz", "retado_email": "ana@gmail.com",
                    "retado_nombre": "Ana", "ganador_email": "eva@x.com", "deporte": "tenis", "creado_en": "2026-09-20T10:00:00+00:00"}],
         "campeonatos": []}
    p = JP.perfil_global("eva@x.com", d)
    assert (p["pj"], p["pg"], p["pp"], p["puntos"]) == (3, 2, 1, 7) and p["categoria"] == "4ta"
    assert [r["academia"] for r in p["por_academia"]] == ["Academia Sol", "Retos"]
    assert p["partidos"][0]["academia"] == "Reto"                   # el más reciente primero
    monkeypatch.setattr(JP, "datos_ranking", lambda: d)
    monkeypatch.setattr(JP, "bio_de", lambda e: {"estilo": "Revés a una mano"})
    monkeypatch.setattr(JP, "perfiles", lambda es: {})
    ref = JP.ref_de("eva@x.com")
    html = _cli(monkeypatch).get(f"/jugador/{ref}").text
    assert "Eva Díaz" in html and "Puesto #1 · Tenis" in html and "Retar a Eva" in html
    assert "Revés a una mano" in html and "6-3 6-4" in html and "eva@x.com" not in html
    assert _sin_popups_nativos(html)
    assert "Jugador no encontrado" in _cli(monkeypatch).get("/jugador/basura").text


# ═══════════════════════════════ LLENAR CANCHA ════════════════════════════════

def test_llenar_cancha_descuento_real_y_avisos(monkeypatch, aislado):
    c = {"id": "c1", "club": "Sabor Golazo", "nombre": "Fútbol 1", "hora_apertura": "18:00", "hora_cierre": "22:00",
         "duracion_slot_min": 60, "precio_hora": 100, "lat": -12.1, "lng": -77.0, "moneda": "S/", "deporte": "futbol"}
    monkeypatch.setattr(datos, "canchas_de_dueno", lambda e: [c] if e == "dueno@x.com" else [])
    mañana = horarios.ahora_local("PE").date() + timedelta(days=1)
    monkeypatch.setattr(datos, "ocupados", lambda cid, fs: {(mañana.isoformat(), "19:00")})
    monkeypatch.setattr(datos, "descuentos", lambda cid, fs: {})
    monkeypatch.setattr(datos, "reservas_de_canchas", lambda ids, a, b: [
        {"usuario": "Juan@x.com", "jugador": "Juan", "telefono": ""},
        {"usuario": "", "jugador": "Pepe", "telefono": "987 654 321"},
        {"usuario": "juan@x.com", "jugador": "Juan P", "telefono": ""}])
    aplicados, msgs = [], []
    monkeypatch.setattr(JP, "aplicar_descuento_slot", lambda cid, f, h, p: aplicados.append((f, h, p)) or True)
    import web.jugador_mensajes as JM
    monkeypatch.setattr(JM, "insertar_mensaje", lambda fila: msgs.append(fila) or fila)
    cli = _cli(monkeypatch, "dueno@x.com", "Dueño")
    html = cli.get("/anfitrion/llenar?dia=1").text
    assert "Llenar cancha" in html and '"h": "18:00"' in html and '"h": "19:00"' not in html and '"n": 2' in html
    assert _sin_popups_nativos(html)
    r = cli.post("/anfitrion/llenar/avisar", json={"cancha_id": "c1", "dia": 1, "horas": ["18:00", "19:00", "21:00"], "descuento": 20, "promo": "Trae a tu equipo"})
    j = r.json()
    assert j["ok"] and j["horas"] == ["18:00", "21:00"] and j["enviados"] == 1   # 19:00 ya estaba ocupada
    assert aplicados == [(mañana.isoformat(), "18:00", 20), (mañana.isoformat(), "21:00", 20)]
    assert msgs[0]["hilo"] == "cancha_dueno@x.com|juan@x.com" and "20% OFF" in msgs[0]["texto"] and "S/ 80" in msgs[0]["texto"]
    assert j["whatsapp"][0]["nombre"] == "Pepe" and "wa.me/51987654321" in j["whatsapp"][0]["url"]
    # Descuento fuera de los chips o cancha ajena → rechazo.
    assert cli.post("/anfitrion/llenar/avisar", json={"cancha_id": "c1", "dia": 1, "horas": ["18:00"], "descuento": 50}).status_code == 400
    assert _cli(monkeypatch).post("/anfitrion/llenar/avisar", json={"cancha_id": "c1", "horas": ["18:00"]}).status_code == 404
