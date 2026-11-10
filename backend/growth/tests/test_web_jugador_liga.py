"""Nivel de jugador, Liga de tenis, Configuración de la cuenta y Verificar
identidad en la web = mismas pantallas y reglas del app (pedido del director,
29-sep-2026: "en la web implementa las mismas funcionalidades que existen
actualmente en el app")."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
import propiedad.router as prop_router
from db.store import Reto, stores
from main import app
from web import almacen, datos, jugador_cuenta as JC, jugador_liga as JL, sesion


def _cli(monkeypatch, email="ana@gmail.com", nombre="Ana Pérez"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre, "foto": ""}))
    return cli


def _mio(html: str) -> str:
    """Solo el contenido de estas páginas (sin la cabecera/pie compartidos)."""
    return html.split("class='lg-wrap'", 1)[1].split("</main>", 1)[0]


def _sin_popups_nativos(txt: str) -> bool:
    return re.search(r"(?<![\w])(?:window\.)?(confirm|alert|prompt)\(", txt) is None


@pytest.fixture
def aislado(monkeypatch):
    """Retos, circuito y Pro en memoria, sin tocar el estado de otros tests; sin
    pushes ni mensajes reales."""
    antes = (list(stores.retos), dict(stores.jugadores_circuito), dict(stores.membresias_pro), dict(stores.config))
    stores.retos[:] = []
    stores.jugadores_circuito.clear()
    avisos, mensajes = [], []
    monkeypatch.setattr(JL, "aviso_push", lambda email, titulo, cuerpo, tipo="aviso", data=None: avisos.append((email, titulo, cuerpo, data)))
    monkeypatch.setattr(JL, "_mensaje_directo", lambda *a: mensajes.append(a))
    monkeypatch.setattr(JL, "perfiles", lambda emails: {})
    monkeypatch.setattr(JL, "niveles_de_varios", lambda emails: {})
    yield {"avisos": avisos, "mensajes": mensajes}
    stores.retos[:] = antes[0]
    stores.jugadores_circuito.clear(); stores.jugadores_circuito.update(antes[1])
    stores.membresias_pro.clear(); stores.membresias_pro.update(antes[2])
    stores.config.clear(); stores.config.update(antes[3])


# ── Nivel ─────────────────────────────────────────────────────────────────────

def test_mi_nivel_misma_formula_y_upsert_sin_pisar_historial(monkeypatch):
    # `Nivel.seedDesde`: 2 + años·0.25 + frecuencia·0.2 + 1 si compite (1..7).
    assert JL.seed_desde(0, 0, False) == 2.0
    assert JL.seed_desde(2, 2, False) == pytest.approx(2.9)
    assert JL.seed_desde(10, 5, True) == pytest.approx(6.5)
    assert JL.seed_desde(99, 99, True) == pytest.approx(6.5)  # topes 10 años / 5 por semana

    guardados = []
    monkeypatch.setattr(JL, "guardar_nivel", lambda email, dep, n: guardados.append((email, dep, round(n, 2))) or True)
    monkeypatch.setattr(JL, "niveles_completos", lambda e: [{"deporte": "tenis", "nivel": 4.2, "partidos": 9, "victorias": 6, "confiabilidad": 1.0}])
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app, base_url="https://testserver").post("/web/mi-nivel", json={"deporte": "tenis", "anios": 2, "frecuencia": 2})
    assert r.status_code == 401
    cli = _cli(monkeypatch)
    html = cli.get("/mi-nivel").text
    assert "Autoevalúate" in html and "¿Cuántos años llevas jugando?" in html and "9 partidos · 6 victorias" in html
    assert "Fútbol" in html and "Tenis" in html and "Pickleball" in html and "Vóley" in html and "Básquet" in html
    assert _sin_popups_nativos(_mio(html))
    j = cli.post("/web/mi-nivel", json={"deporte": "tenis", "anios": 4, "frecuencia": 3, "compite": True}).json()
    assert j["ok"] and j["nivel"] == pytest.approx(4.6) and "4.6" in j["chip"]
    assert guardados == [("ana@gmail.com", "tenis", 4.6)]  # siempre el correo de la SESIÓN
    assert cli.post("/web/mi-nivel", json={"deporte": "golf", "anios": 1, "frecuencia": 1}).status_code == 400
    assert cli.post("/web/mi-nivel", json={"deporte": "tenis", "anios": 11, "frecuencia": 1}).status_code == 400


def test_guardar_nivel_upsert_conserva_partidos_victorias_y_confiabilidad(monkeypatch):
    sqls = []

    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params): sqls.append((sql, params))

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return Cur()
        def commit(self): pass
    monkeypatch.setattr(JL.pg, "habilitado", True)
    monkeypatch.setattr(JL.pg, "conexion", lambda: Conn())
    assert JL.guardar_nivel("Ana@Gmail.com", "tenis", 4.6)
    sql, params = sqls[0]
    assert "ON CONFLICT (email, deporte) DO UPDATE SET nivel = EXCLUDED.nivel, actualizado = now()" in sql
    assert "partidos = " not in sql.split("DO UPDATE")[1] and params[0] == "ana@gmail.com"


# ── Ranking (port de AppState.rankingGlobal / rankingDobles) ───────────────────

def _datos_ranking():
    return {
        "academias": [
            {"id": "ac1", "nombre": "Academia Sur", "deporte": "tenis", "zona": "Surco", "categorias": {"a1": "4ta"},
             "partidos": [{"id": "p1", "fecha": "2026-08-10T10:00:00", "jugadorAId": "a1", "jugadorANombre": "Luis", "jugadorAEmail": "luis@x.com",
                           "jugadorBId": "a2", "jugadorBNombre": "Eva", "ganadorId": "a1"}]},
            {"id": "ac2", "nombre": "Club Norte", "deporte": "tenis", "zona": "Los Olivos", "categorias": {},
             "partidos": [{"id": "p2", "fecha": "2026-08-12T10:00:00", "jugadorAId": "b1", "jugadorANombre": "Luis R.", "jugadorAEmail": "LUIS@x.com",
                           "jugadorBId": "b2", "jugadorBNombre": "Ana", "jugadorBEmail": "ana@gmail.com", "ganadorId": "b1"}]},
        ],
        "campeonatos": [
            {"id": "cmp1", "academiaId": "", "nombre": "Relámpago", "deporte": "tenis", "inicio": "2026-08-20T09:00:00",
             "participantes": [{"id": "x", "nombre": "Ana", "email": "ana@gmail.com"}, {"id": "y", "nombre": "Rocío", "email": "rocio@x.com"}],
             "partidos": [{"id": "m1", "ronda": 0, "aId": "x", "bId": "y", "marcadorA": 2, "marcadorB": 0}]},
        ],
        "retos": [
            {"id": 1, "deporte": "tenis", "zona": "Surco", "estado": "jugado", "modalidad": "singles", "retador_email": "ana@gmail.com",
             "retador_nombre": "Ana", "retado_email": "luis@x.com", "retado_nombre": "Luis", "ganador_email": "ana@gmail.com",
             "jugado_en": "2026-09-01T15:00:00+00:00", "creado_en": "2026-08-30T15:00:00+00:00"},
            {"id": 2, "deporte": "tenis", "zona": "", "estado": "jugado", "modalidad": "dobles", "retador_email": "ana@gmail.com",
             "retador_nombre": "Ana", "retador2_email": "eva@x.com", "retador2_nombre": "Eva", "retado_email": "luis@x.com",
             "retado_nombre": "Luis", "retado2_email": "rocio@x.com", "retado2_nombre": "Rocío", "ganador_email": "eva@x.com",
             "jugado_en": "2026-09-02T15:00:00+00:00"},
        ],
    }


def test_ranking_global_igual_que_el_app():
    d = _datos_ranking()
    t = JL.ranking_global(d, "tenis")
    por = {f["key"]: f for f in t}
    # Luis: dedupe por correo entre academias (mayúsculas incluidas) + reto singles.
    luis = por["e:luis@x.com"]
    assert (luis["pj"], luis["pg"], luis["pp"], luis["puntos"], luis["academias"]) == (3, 2, 1, 7, 2)
    ana = por["e:ana@gmail.com"]
    assert (ana["pj"], ana["pg"], ana["pp"], ana["puntos"]) == (3, 2, 1, 7)  # academia + reto + campeonato independiente
    assert por["a:ac1|a2"]["nombre"] == "Eva" and por["a:ac1|a2"]["puntos"] == 1  # alumna manual sin correo
    assert t[0]["puntos"] >= t[-1]["puntos"]
    # El reto de DOBLES no entra al singles; va a su tabla de parejas.
    assert "e:eva@x.com" not in por and "e:rocio@x.com" in por  # Rocío sí, por el campeonato
    dob = JL.ranking_dobles(d, "tenis")
    assert [f["key"] for f in dob] == ["d:ana@gmail.com|eva@x.com", "d:luis@x.com|rocio@x.com"]
    assert dob[0]["nombre"] == "Ana / Eva" and dob[0]["pg"] == 1 and dob[1]["pp"] == 1
    # Filtro de categoría: solo academias (los retos no tienen categoría).
    cat = JL.ranking_global(d, "tenis", categoria="4ta")
    assert [(f["key"], f["pj"]) for f in cat] == [("e:luis@x.com", 1)]
    # Zona: el campeonato independiente no tiene zona; el reto de Surco sí cuenta.
    sur = {f["key"]: f for f in JL.ranking_global(d, "tenis", zona="Surco")}
    assert sur["e:luis@x.com"]["pj"] == 2 and sur["e:ana@gmail.com"]["pj"] == 1
    # Temporadas (trimestres): ago = T3, set = T3 también → T2 vacía.
    assert JL.ranking_global(d, "tenis", temporada=(2026, 2)) == []
    assert JL.categorias_de(d, "tenis") == ["4ta"] and JL.zonas_de(d, "tenis") == ["Los Olivos", "Surco"]
    assert JL.deportes_con_ranking(d) == ["tenis"] and JL.hay_dobles(d, "tenis")
    assert (2026, 3) in JL.temporadas_de(d, "tenis")


def test_pagina_liga_ranking_sin_correos_con_mi_posicion_y_retar(monkeypatch, aislado):
    d = _datos_ranking()
    monkeypatch.setattr(JL, "datos_ranking", lambda: d)
    stores.membresias_pro["luis@x.com"] = {"hasta": (datetime.now(timezone.utc) + timedelta(days=9)).isoformat()}
    html = _cli(monkeypatch).get("/liga").text
    assert "Liga de tenis Pichangol" in html and "Tu posición" in html and "Ranking cruzado de todas las academias" in html
    assert "lg-pro" in html and "Singles" in html and "Dobles" in html and "Histórico" in html and "4ta" in html
    cuerpo = _mio(html)
    assert "luis@x.com" not in cuerpo and "rocio@x.com" not in cuerpo  # nunca correos ajenos en la página
    ref = cuerpo.split("data-retar='", 1)[1].split("'", 1)[0]
    assert JL.email_de_ref(ref) in ("luis@x.com", "rocio@x.com")
    assert JL.email_de_ref("basura") == ""
    dob = _cli(monkeypatch).get("/liga?modalidad=dobles").text
    assert "Ana / Eva" in dob and "data-retar='" not in _mio(dob).split("<script>", 1)[0]
    assert _sin_popups_nativos(_mio(html)) and _sin_popups_nativos(JL._JS_LIGA)


# ── Retos (acciones con el correo de la SESIÓN) ────────────────────────────────

def test_retar_responder_reportar_y_confirmar_como_el_app(monkeypatch, aislado):
    ana, luis = _cli(monkeypatch), _cli(monkeypatch, "luis@x.com", "Luis")
    j = ana.post("/web/liga/retar", json={"ref": JL.ref_de("luis@x.com"), "nombre": "Luis", "deporte": "tenis", "zona": "Surco"}).json()
    assert j["ok"] and "Reto enviado a Luis" in j["mensaje"]
    r = stores.retos[-1]
    assert (r.retador_email, r.retado_email, r.deporte, r.zona, r.estado) == ("ana@gmail.com", "luis@x.com", "tenis", "Surco", "pendiente")
    assert aislado["avisos"][-1][:2] == ("luis@x.com", "¡Te retaron! 🎾")
    assert aislado["mensajes"][-1][2] == "luis@x.com" and "(tenis)" in aislado["mensajes"][-1][3]
    assert ana.post("/web/liga/retar", json={"ref": JL.ref_de("ana@gmail.com"), "deporte": "tenis"}).status_code == 400
    # Solo el lado RETADO responde.
    assert ana.post(f"/web/liga/reto/{r.id}/responder", json={"aceptar": True}).status_code == 404
    assert luis.post(f"/web/liga/reto/{r.id}/responder", json={"aceptar": True}).json()["ok"]
    assert r.estado == "aceptado" and aislado["avisos"][-1][:2] == ("ana@gmail.com", "¡Reto aceptado! 🔥")
    assert luis.post(f"/web/liga/reto/{r.id}/responder", json={"aceptar": False}).status_code == 409
    # Un tercero no toca el reto.
    eva = _cli(monkeypatch, "eva@x.com", "Eva")
    assert eva.post(f"/web/liga/reto/{r.id}/resultado", json={"ganador": "retador"}).status_code == 404
    # Reporta Ana (marcador por selección) → por confirmar, aviso a Luis.
    assert ana.post(f"/web/liga/reto/{r.id}/resultado", json={"ganador": "retador", "marcador": "6-<b>"}).status_code == 400
    j = ana.post(f"/web/liga/reto/{r.id}/resultado", json={"ganador": "retador", "marcador": "6-3 6-4"}).json()
    assert j["ok"] and r.estado == "por_confirmar" and r.ganador_email == "ana@gmail.com" and r.reportado_por == "ana@gmail.com"
    assert "Falta que Luis lo confirme" in j["mensaje"] and aislado["avisos"][-1][:2] == ("luis@x.com", "Confirma el resultado 🎾")
    html = luis.get("/liga?tab=retos").text
    assert "Reportaron que ganó Ana" in html and "data-acc='confirmar'" in html and "6-3 6-4" in html
    assert "Esperando que Luis confirme" in ana.get("/liga?tab=retos").text
    # Quien reportó no confirma; el otro sí → jugado + push del desenlace.
    assert ana.post(f"/web/liga/reto/{r.id}/confirmar", json={"acepta": True}).status_code == 400
    j = luis.post(f"/web/liga/reto/{r.id}/confirmar", json={"acepta": True}).json()
    assert j["ok"] and j["ganador"] == "Ana Pérez" and r.estado == "jugado"
    assert aislado["avisos"][-1][:2] == ("ana@gmail.com", "¡Ganaste! 🏆")


def test_disputa_y_tope_semanal_sin_pro(monkeypatch, aislado):
    ana, luis = _cli(monkeypatch), _cli(monkeypatch, "luis@x.com", "Luis")
    stores.config["retos_free_limite_semana"] = "2"
    for _ in range(2):
        assert ana.post("/web/liga/retar", json={"ref": JL.ref_de("luis@x.com"), "deporte": "tenis"}).json()["ok"]
    j = ana.post("/web/liga/retar", json={"ref": JL.ref_de("luis@x.com"), "deporte": "tenis"}).json()
    assert j["error"] == "limite_retos_free" and j["limite"] == 2 and "Pichangol Pro" in j["mensaje"]
    stores.membresias_pro["ana@gmail.com"] = {"hasta": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()}
    assert ana.post("/web/liga/retar", json={"ref": JL.ref_de("luis@x.com"), "deporte": "tenis"}).json()["ok"]  # Pro = sin tope
    r = stores.retos[0]
    luis.post(f"/web/liga/reto/{r.id}/responder", json={"aceptar": True})
    luis.post(f"/web/liga/reto/{r.id}/resultado", json={"ganador": "retado"})
    j = ana.post(f"/web/liga/reto/{r.id}/confirmar", json={"acepta": False}).json()
    assert j["ok"] and r.estado == "disputado" and aislado["avisos"][-1][:2] == ("luis@x.com", "Resultado en disputa ⚠️")
    assert "Reportar de nuevo" in ana.get("/liga?tab=retos").text
    assert ana.post(f"/web/liga/reto/{r.id}/resultado", json={"ganador": "retador"}).json()["ok"]


def test_reto_de_dobles_cuatro_distintos(monkeypatch, aislado):
    ana = _cli(monkeypatch)
    monkeypatch.setattr(JL, "perfiles", lambda emails: {x: {"nombre": x.split("@")[0].capitalize(), "foto_url": ""} for x in emails})
    ref = JL.ref_de
    j = ana.post("/web/liga/retar-dobles", json={"companero": ref("eva@x.com"), "rival1": ref("luis@x.com"), "rival2": ref("eva@x.com")}).json()
    assert not j["ok"] and "cuatro jugadores deben ser distintos" in j["mensaje"]
    j = ana.post("/web/liga/retar-dobles", json={"companero": ref("eva@x.com"), "rival1": ref("luis@x.com"), "rival2": ref("rocio@x.com")}).json()
    assert j["ok"]
    r = stores.retos[-1]
    assert r.modalidad == "dobles" and (r.retador2_email, r.retado_email, r.retado2_email) == ("eva@x.com", "luis@x.com", "rocio@x.com")
    assert {a[0] for a in aislado["avisos"]} == {"luis@x.com", "rocio@x.com"}
    # Rocío (retado2) también puede aceptar y ve el reto como recibido.
    rocio = _cli(monkeypatch, "rocio@x.com", "Rocío")
    assert "Te retó Ana / Eva" in rocio.get("/liga?tab=retos").text
    assert rocio.post(f"/web/liga/reto/{r.id}/responder", json={"aceptar": True}).json()["ok"]


def test_unirse_al_circuito_categoria_obligatoria_y_zona_del_catalogo(monkeypatch, aislado):
    ana = _cli(monkeypatch)
    assert "Unirme al circuito" in ana.get("/liga?tab=retar").text
    assert ana.post("/web/liga/unirse", json={"deporte": "tenis", "zona": "Miraflores", "categoria": ""}).status_code == 400
    assert ana.post("/web/liga/unirse", json={"deporte": "tenis", "zona": "Mi casa", "categoria": "4ta"}).status_code == 400
    assert ana.post("/web/liga/unirse", json={"deporte": "futbol", "zona": "Miraflores", "categoria": "4ta"}).status_code == 400
    assert ana.post("/web/liga/unirse", json={"deporte": "tenis", "zona": "Miraflores", "categoria": "4ta"}).json()["ok"]
    assert stores.jugadores_circuito["ana@gmail.com"]["categoria"] == "4ta"
    stores.jugadores_circuito["luis@x.com"] = {"nombre": "Luis", "deporte": "tenis", "zona": "Surco", "categoria": "3ra", "actualizado": "2026-09-01"}
    html = ana.get("/liga?tab=retar").text
    assert "Estás en el circuito" in html and "Luis" in html and "Tenis · Surco · 3ra" in html and "data-retar" in html
    assert ana.post("/web/liga/salir").json()["ok"] and "ana@gmail.com" not in stores.jugadores_circuito


# ── Configuración de la cuenta ────────────────────────────────────────────────

def test_configuracion_de_la_cuenta_como_editar_perfil_del_app(monkeypatch):
    monkeypatch.setattr(JC, "perfil_completo", lambda e: {"nombre": "Ana P.", "foto_url": "", "celular": "51987654321",
                                                         "bio": {"estilo": "Ofensivo"}})
    monkeypatch.setattr(JC, "niveles_completos", lambda e: [{"deporte": "tenis", "nivel": 3.5, "partidos": 0, "victorias": 0, "confiabilidad": 1}])
    monkeypatch.setattr(datos, "esta_verificado", lambda e: False)
    guardados = []
    monkeypatch.setattr(JC, "guardar_perfil", lambda email, nombre, cel, bio: guardados.append((email, nombre, cel, bio)) or True)
    cli = _cli(monkeypatch)
    html = cli.get("/cuenta/configuracion").text
    assert "Edita el perfil" in html and "value='Ana P.'" in html and "value='987654321'" in html and "+51" in html
    assert "Mi estilo de juego: Ofensivo" in html and "Idiomas que hablo" in html and "Edita tus deportes" in html
    assert "Verifica tu identidad" in html and "href='/cuenta/identidad'" in html and "/legal/eliminar-cuenta" in html
    # Validación del celular POR PAÍS y nombre obligatorio.
    assert cli.post("/web/cuenta/perfil", json={"nombre": "", "pais": "PE", "celular": ""}).json()["campo"] == "nombre"
    assert cli.post("/web/cuenta/perfil", json={"nombre": "Ana", "pais": "PE", "celular": "98765432"}).json()["campo"] == "celular"
    assert cli.post("/web/cuenta/perfil", json={"nombre": "Ana", "pais": "BO", "celular": "51234567"}).json()["campo"] == "celular"
    r = cli.post("/web/cuenta/perfil", json={"nombre": "Ana Pérez G.", "pais": "BO", "celular": "71234567",
                                             "bio": {"estilo": "Defensivo", "idiomas": "Inglés · Español", "logro": "Inventado", "hack": "x"}})
    assert r.json()["ok"]
    assert guardados[-1] == ("ana@gmail.com", "Ana Pérez G.", "59171234567", {"estilo": "Defensivo", "idiomas": "Español · Inglés"})
    assert sesion.leer(r.cookies.get(sesion.COOKIE))["nombre"] == "Ana Pérez G."  # la cabecera ya muestra el nombre nuevo
    assert cli.post("/web/cuenta/perfil", json={"nombre": "Ana", "pais": "PE", "celular": ""}).json()["ok"]
    assert guardados[-1][2] == ""  # borrar el celular (opcional, como el app)
    assert JC.partir_celular("593987654321") == ("EC", "987654321") and JC.partir_celular("") == ("PE", "")
    assert _sin_popups_nativos(_mio(html)) and _sin_popups_nativos(JC._JS_CONFIG) and _sin_popups_nativos(JC._JS_IDENTIDAD)


def test_foto_de_perfil_va_al_bucket_chat_de_su_carpeta(monkeypatch):
    subidas, fotos, borradas = [], [], []
    monkeypatch.setattr(almacen, "disponible", lambda: True)
    monkeypatch.setattr(almacen, "subir", lambda b, ruta, d, ct="image/jpeg", **k: subidas.append((b, ruta)) or f"https://sb/storage/v1/object/public/{b}/{ruta}?v=1")
    monkeypatch.setattr(JC, "perfil_completo", lambda e: {"nombre": "Ana", "foto_url": "https://sb/old.jpg"})
    monkeypatch.setattr(JC, "guardar_foto", lambda email, nombre, url: fotos.append((email, url)) or True)
    monkeypatch.setattr(JC, "_borrar_foto_vieja", lambda email, url: borradas.append(url))
    cli = _cli(monkeypatch)
    assert cli.post("/web/cuenta/foto", content=b"no-es-imagen").status_code == 400
    r = cli.post("/web/cuenta/foto", content=b"\xff\xd8\xff\xe0" + b"0" * 100, headers={"Content-Type": "image/jpeg"})
    j = r.json()
    assert j["ok"] and subidas[0][0] == "chat" and subidas[0][1].startswith("perfiles/ana_gmail_com/") and "?" not in j["foto"]
    assert fotos == [("ana@gmail.com", j["foto"])] and borradas == ["https://sb/old.jpg"]
    assert sesion.leer(r.cookies.get(sesion.COOKIE))["foto"] == j["foto"]


# ── Verificar identidad ───────────────────────────────────────────────────────

def test_verificar_identidad_por_documento_sin_guardar_ni_mostrar_el_numero(monkeypatch):
    llamadas, verif = [], []

    def falso(req):
        llamadas.append((req.dni, req.email, req.pais))
        if req.dni == "11111111":
            return {"ok": False, "error": "dni_en_uso"}
        if req.dni == "22222222":
            return {"ok": False, "error": "no_encontrado"}
        return {"ok": True, "nombre_completo": "ANA PEREZ", "fecha_nacimiento": "15/03/1995"}
    monkeypatch.setattr(prop_router, "post_verificar_dni", falso)
    monkeypatch.setattr(JC, "registrar_verificado", lambda email, nombre: verif.append((email, nombre)) or True)
    monkeypatch.setattr(JC, "perfil_completo", lambda e: {})
    monkeypatch.setattr(JL, "perfiles", lambda emails: {})
    monkeypatch.setattr(datos, "esta_verificado", lambda e: False)
    JC._INTENTOS.clear()
    cli = _cli(monkeypatch)
    html = cli.get("/cuenta/identidad").text
    assert "Número de DNI" in html and "RENIEC" in html and "No guardamos foto de tu documento" in html
    assert "Registro Civil" in cli.get("/cuenta/identidad?pais=EC").text
    assert "Verificar en la app" in cli.get("/cuenta/identidad?pais=BO").text
    assert cli.post("/web/cuenta/identidad", json={"pais": "BO", "numero": "1234567"}).status_code == 400
    assert "8 dígitos" in cli.post("/web/cuenta/identidad", json={"pais": "PE", "numero": "123"}).json()["mensaje"]
    assert "otra cuenta" in cli.post("/web/cuenta/identidad", json={"pais": "PE", "numero": "11111111"}).json()["mensaje"]
    assert "no figura" in cli.post("/web/cuenta/identidad", json={"pais": "PE", "numero": "22222222"}).json()["mensaje"]
    r = cli.post("/web/cuenta/identidad", json={"pais": "PE", "numero": "45678901"})
    j = r.json()
    assert j["ok"] and isinstance(j["edad"], int) and "45678901" not in r.text
    assert llamadas[-1] == ("45678901", "ana@gmail.com", "PE") and verif == [("ana@gmail.com", "Ana Pérez")]
    # Tope anti abuso: 5 consultas cada 15 min por cuenta.
    for _ in range(2):
        assert cli.post("/web/cuenta/identidad", json={"pais": "PE", "numero": "45678901"}).status_code == 200
    assert cli.post("/web/cuenta/identidad", json={"pais": "PE", "numero": "45678901"}).status_code == 429
    JC._INTENTOS.clear()
    monkeypatch.setattr(datos, "esta_verificado", lambda e: True)
    assert "Identidad verificada" in cli.get("/cuenta/identidad").text
    assert JC.edad_desde("1990-01-01") is not None and JC.edad_desde("xx") is None


def test_sin_sesion_va_a_entrar_y_volver(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    for ruta, volver in (("/mi-nivel", "%2Fmi-nivel"), ("/liga", "%2Fliga"), ("/cuenta/configuracion", "%2Fcuenta%2Fconfiguracion"),
                         ("/cuenta/identidad", "%2Fcuenta%2Fidentidad")):
        r = cli.get(ruta, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=" + volver
    for url in ("/web/liga/retar", "/web/liga/unirse", "/web/cuenta/perfil", "/web/cuenta/identidad"):
        assert cli.post(url, json={}).status_code == 401
