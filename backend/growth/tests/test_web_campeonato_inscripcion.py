"""INSCRIPCIÓN A CAMPEONATOS DESDE LA WEB pagando con el SALDO (pedido del
director, 1-oct-2026): lo mismo que el jugador hace en
`campeonato_detalle_screen` — inscripción individual (`/pagos/torneo/inscribir`)
y, en fútbol, crear equipo / unirse / completar el pozo (`pagos/pozos.py`) —,
con las mismas reglas (`puedeInscribirse`, `plantelAbierto`, `equipoLleno`,
`exigeDni` + edad) y el MISMO JSON del campeonato que escribe el app."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
from db.store import stores  # noqa: E402
from main import app  # noqa: E402
from pagos import router as pr  # noqa: E402
from web import campeonatos_logica as L  # noqa: E402
from web import datos  # noqa: E402
from tests.test_web_campeonatos import _preparar  # noqa: E402
from tests.test_web_reservas import _entrar_como, db  # noqa: E402,F401


@pytest.fixture
def entorno(db, monkeypatch):
    fake = _preparar(monkeypatch)

    def mutar(cid, fn):
        r = fake.rows.get(cid)
        if r is None or r.get("_elim"):
            return False, None
        import copy
        c = copy.deepcopy(r)
        guardar, res = fn(c)
        if guardar:
            fake.rows[cid] = c
        return True, res

    monkeypatch.setattr(datos, "mutar_campeonato", mutar)
    avisos = []
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda *a, **k: avisos.append(a))
    stores.pagos = []
    stores.saldos = {}
    stores.pozos_equipo = {}
    fake.avisos = avisos
    return fake


def _camp(fake, **kw):
    cid = L.nuevo_id()
    base = {"id": cid, "dueno": "orga@gmail.com", "nombre": "Copa Test", "deporte": "tenis", "formato": "eliminacion",
            "inscripcionAbierta": True, "participantes": [], "partidos": [], "costoInscripcion": 30.0, "moneda": "S/",
            "sedeLat": -12.09, "sedeLng": -77.0, "exigeDni": False}
    base.update(kw)
    fake.rows[cid] = base
    return cid


def _cli():
    return TestClient(app, base_url="https://testserver")


def _de(tipo):
    return [p for p in stores.pagos if p.tipo == tipo]


def test_sin_sesion_va_a_entrar(entorno, monkeypatch):
    cid = _camp(entorno)
    cli = _cli()
    r = cli.get(f"/torneo/{cid}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/entrar?volver=")
    assert cli.post(f"/web/torneo/{cid}/inscribir", json={}).status_code == 401
    assert cli.post(f"/web/torneo/{cid}/equipo/crear", json={"nombre": "X"}).status_code == 401
    assert cli.post(f"/web/torneo/{cid}/equipo/unirme", json={"codigo": "ABC"}).status_code == 401


def test_inscripcion_individual_debita_saldo_como_el_apk(entorno, monkeypatch):
    cid = _camp(entorno)
    cli = _cli()
    _entrar_como(cli, monkeypatch, "ana@gmail.com", "Ana Pérez")
    # La página pública lleva a la web (con la app como opción secundaria).
    monkeypatch.setattr("marketing.campeonato_web.obtener_campeonato", lambda _id: entorno.rows[cid])
    pub = cli.get(f"/c/{cid}").text
    assert f"/torneo/{cid}" in pub and "Inscribirme aquí" in pub and "Unirme en la app" in pub
    html = cli.get(f"/torneo/{cid}").text
    assert "Inscribirme · S/ 30" in html and "Tu saldo Pichangol" in html
    # Sin saldo → 402 con enlace a recargar; no se inscribe ni se cobra.
    r = cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "yo"})
    assert r.status_code == 402 and r.json()["falta_saldo"] and r.json()["recargar"] == "/mi-billetera#recargar"
    assert entorno.rows[cid]["participantes"] == [] and stores.pagos == []
    stores.acreditar("ana@gmail.com", 6000)
    r = cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "yo"})
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert stores.saldo_centimos("ana@gmail.com") == 3000
    # Los MISMOS pagos que `/pagos/torneo/inscribir` del APK.
    deb, ing = _de("inscripcion_torneo"), _de("inscripcion_torneo_ingreso")
    assert len(deb) == 1 and deb[0].dueno_id == "ana@gmail.com" and deb[0].monto_centimos == 3000
    assert len(ing) == 1 and ing[0].dueno_id == "orga@gmail.com" and ing[0].culqi_charge_id == f"torneo:{ing[0].id}"
    p = entorno.rows[cid]["participantes"][0]
    assert p["email"] == "ana@gmail.com" and p["apoderadoNombre"] == "" and p["id"].startswith("part_")
    # Ya inscrito: no cobra dos veces.
    r = cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "yo"})
    assert r.status_code == 409 and len(_de("inscripcion_torneo")) == 1
    assert "Ya estás inscrito" in cli.get(f"/torneo/{cid}").text
    # Un hijo: nombre + consentimiento (como el app), con ella de apoderada.
    assert cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "hijo", "nombre": "Luchito"}).status_code == 400
    r = cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "hijo", "nombre": "Luchito", "consiente": True, "whatsapp": "999888777", "edad": "9"})
    assert r.status_code == 200, r.text
    h = entorno.rows[cid]["participantes"][1]
    assert h["nombre"] == "Luchito" and h["apoderadoNombre"] == "Ana Pérez" and h["edad"] == 9 and h["contacto"] == "999888777"
    assert stores.saldo_centimos("ana@gmail.com") == 0
    # El organizador no se inscribe a su propio torneo.
    _entrar_como(cli, monkeypatch, "orga@gmail.com", "Orga")
    assert cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "yo"}).status_code == 403


def test_inscripcion_cerrada_y_moneda_distinta(entorno, monkeypatch):
    cli = _cli()
    _entrar_como(cli, monkeypatch, "beto@gmail.com", "Beto")
    stores.acreditar("beto@gmail.com", 10000)
    cerrado = _camp(entorno, inscripcionAbierta=False)
    assert cli.post(f"/web/torneo/{cerrado}/inscribir", json={"quien": "yo"}).status_code == 409
    vencido = _camp(entorno, inscripcionHasta="2020-01-01T00:00:00")
    assert cli.post(f"/web/torneo/{vencido}/inscribir", json={"quien": "yo"}).status_code == 409
    assert stores.pagos == []
    # Torneo en Ecuador ($) con billetera en soles: no se mezcla la moneda.
    ec = _camp(entorno, sedeLat=-2.17, sedeLng=-79.92, moneda="$")
    r = cli.post(f"/web/torneo/{ec}/inscribir", json={"quien": "yo"})
    assert r.status_code == 409 and r.json()["error"] == "moneda_distinta" and stores.pagos == []


def test_exige_documento_y_edad(entorno, db, monkeypatch):
    from propiedad import identidad
    import propiedad.router as prop
    cid = _camp(entorno, exigeDni=True, edadMin=10, edadMax=14, costoInscripcion=0)
    cli = _cli()
    _entrar_como(cli, monkeypatch, "papa@gmail.com", "Papá")
    # Yo sin verificar → hay que verificar el documento primero.
    r = cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "yo"})
    assert r.status_code == 403 and r.json()["error"] == "documento_requerido"
    monkeypatch.setattr(prop, "post_verificar_dni", lambda req: {"ok": True, "nombre_completo": "JUAN PEREZ", "fecha_nacimiento": "01/01/1980"})
    r = cli.post(f"/web/torneo/{cid}/documento", json={"para": "yo", "numero": "12345678"})
    assert r.status_code == 400 and "categoría es hasta 14" in r.json()["mensaje"]
    # El hijo: su DNI contra el registro trae nombre y edad (12 años → entra).
    monkeypatch.setattr(identidad, "consultar_dni", lambda d: {"ok": True, "nombre_completo": "LUIS PEREZ", "fecha_nacimiento": "2014-03-01"})
    r = cli.post(f"/web/torneo/{cid}/documento", json={"para": "hijo", "numero": "87654321"})
    assert r.status_code == 200 and r.json()["nombre"] == "LUIS PEREZ"
    tok = r.json()["token"]
    # Sin token del hijo no pasa; el token de OTRO campeonato tampoco.
    assert cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "hijo", "consiente": True}).status_code == 403
    r = cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "hijo", "consiente": True, "doc_token": tok})
    assert r.status_code == 200, r.text
    p = entorno.rows[cid]["participantes"][0]
    from web.jugador_cuenta import edad_desde
    assert p["nombre"] == "LUIS PEREZ" and p["apoderadoNombre"] == "Papá" and p["edad"] == edad_desde("2014-03-01")
    # Jugador ya verificado: la identidad basta (como `jugadorVerificado` del app).
    entorno.rows[cid]["edadMin"] = None
    entorno.rows[cid]["edadMax"] = None
    _entrar_como(cli, monkeypatch, "vero@gmail.com", "Vero")
    db.verificados.add("vero@gmail.com")
    assert cli.post(f"/web/torneo/{cid}/inscribir", json={"quien": "yo"}).status_code == 200


def _futbol(fake, **kw):
    return _camp(fake, deporte="futbol", formato="liga", costoInscripcion=100.0, maxJugadoresEquipo=10, **kw)


def test_futbol_crear_unirse_y_completar_el_pozo(entorno, monkeypatch):
    cid = _futbol(entorno)
    cli = _cli()
    _entrar_como(cli, monkeypatch, "capi@gmail.com", "Capi")
    assert "Crear mi equipo · pones S/ 10" in cli.get(f"/torneo/{cid}").text
    # Sin saldo: no se crea el equipo.
    r = cli.post(f"/web/torneo/{cid}/equipo/crear", json={"nombre": "Los Tigres"})
    assert r.status_code == 402 and entorno.rows[cid]["participantes"] == []
    stores.acreditar("capi@gmail.com", 10000)
    r = cli.post(f"/web/torneo/{cid}/equipo/crear", json={"nombre": "Los Tigres"})
    assert r.status_code == 200, r.text
    j = r.json()
    eq = entorno.rows[cid]["participantes"][0]
    assert eq["id"] == j["equipo_id"] and eq["capitanEmail"] == "capi@gmail.com" and len(eq["codigo"]) == 6
    assert eq["roster"][0]["email"] == "capi@gmail.com" and eq["roster"][0]["aporteCentimos"] == 1000
    assert stores.saldo_centimos("capi@gmail.com") == 9000 and len(_de("aporte_equipo")) == 1
    pozo = stores.pozos_equipo[f"{cid}|{eq['id']}"]
    assert pozo["organizador"] == "orga@gmail.com" and pozo["moneda"] == "PEN" and pozo["cupo"] == 10
    # Un jugador se une por el código: pone su parte; el capitán recibe aviso.
    _entrar_como(cli, monkeypatch, "juan@gmail.com", "Juan")
    stores.acreditar("juan@gmail.com", 5000)
    html = cli.get(f"/torneo/{cid}?equipo={eq['codigo']}").text
    assert "Te invitaron al equipo «Los Tigres»" in html and "Unirme · pones S/ 10" in html
    r = cli.post(f"/web/torneo/{cid}/equipo/unirme", json={"codigo": eq["codigo"].lower()})
    assert r.status_code == 200, r.text
    eq = entorno.rows[cid]["participantes"][0]
    assert [i["email"] for i in eq["roster"]] == ["capi@gmail.com", "juan@gmail.com"] and eq["roster"][1]["aporteCentimos"] == 1000
    assert stores.saldo_centimos("juan@gmail.com") == 4000
    assert any(a[0] == "capi@gmail.com" for a in entorno.avisos)
    # Repetir no cobra.
    r = cli.post(f"/web/torneo/{cid}/equipo/unirme", json={"codigo": eq["codigo"]})
    assert r.status_code == 200 and r.json().get("ya") and len(_de("aporte_equipo")) == 2
    # Código inválido.
    assert cli.post(f"/web/torneo/{cid}/equipo/unirme", json={"codigo": "ZZZZZZ"}).status_code == 404
    # Completar lo que falta (80) desde el saldo de Juan: le falta → modal de recarga.
    r = cli.post(f"/web/torneo/{cid}/equipo/{eq['id']}/completar")
    assert r.status_code == 402 and r.json()["requerido_centimos"] == 8000
    stores.acreditar("juan@gmail.com", 10000)
    r = cli.post(f"/web/torneo/{cid}/equipo/{eq['id']}/completar")
    assert r.status_code == 200, r.text
    eq = entorno.rows[cid]["participantes"][0]
    assert L.pozo_centimos(eq) == 10000 and L.pozo_completo(entorno.rows[cid], eq)
    # Pozo completo → liquidación POR RECIBIR al organizador (comisión una vez).
    ing = _de("inscripcion_torneo_ingreso")
    assert len(ing) == 1 and ing[0].dueno_id == "orga@gmail.com" and ing[0].monto_centimos == 10000
    assert ing[0].culqi_charge_id == f"pozo:{cid}|{eq['id']}"
    # Quien entra con el pozo lleno, entra gratis.
    _entrar_como(cli, monkeypatch, "suple@gmail.com", "Suple")
    r = cli.post(f"/web/torneo/{cid}/equipo/unirme", json={"equipo_id": eq["id"]})
    assert r.status_code == 200 and r.json()["aporte_centimos"] == 0
    assert len(entorno.rows[cid]["participantes"][0]["roster"]) == 3 and stores.saldo_centimos("suple@gmail.com") == 0
    # Ajeno al equipo no puede "completar".
    _entrar_como(cli, monkeypatch, "otro@gmail.com", "Otro")
    assert cli.post(f"/web/torneo/{cid}/equipo/{eq['id']}/completar").status_code == 403


def test_plantel_cerrado_lleno_y_fixture(entorno, monkeypatch):
    cli = _cli()
    # Plantel lleno (máximo 2).
    cid = _camp(entorno, deporte="futbol", formato="liga", costoInscripcion=0, maxJugadoresEquipo=2,
                participantes=[{"id": "e1", "nombre": "Kinder 01", "codigo": "K1NDER", "capitanEmail": "a@gmail.com",
                                "roster": [{"id": "i1", "nombre": "A", "email": "a@gmail.com"}, {"id": "i2", "nombre": "B", "email": "b@gmail.com"}]}])
    _entrar_como(cli, monkeypatch, "c@gmail.com", "C")
    r = cli.post(f"/web/torneo/{cid}/equipo/unirme", json={"codigo": "K1NDER"})
    assert r.status_code == 409 and "plantel completo" in r.json()["mensaje"]
    assert "Plantel completo (2 jugadores)." in cli.get(f"/torneo/{cid}").text
    # Fixture publicado: ya no se crean equipos, pero el plantel sigue abierto.
    entorno.rows[cid]["maxJugadoresEquipo"] = 0
    entorno.rows[cid]["partidos"] = [{"id": "m1", "aId": "e1", "bId": "e2", "ronda": 0}]
    assert cli.post(f"/web/torneo/{cid}/equipo/crear", json={"nombre": "Nuevo"}).status_code == 409
    assert cli.post(f"/web/torneo/{cid}/equipo/unirme", json={"codigo": "K1NDER"}).status_code == 200
    # El organizador cerró las inscripciones → el motivo del app.
    cid2 = _camp(entorno, deporte="futbol", formato="liga", costoInscripcion=0, inscripcionAbierta=False,
                 participantes=[{"id": "e1", "nombre": "Kinder 02", "codigo": "K2NDER", "capitanEmail": "", "roster": []}])
    r = cli.post(f"/web/torneo/{cid2}/equipo/unirme", json={"codigo": "K2NDER"})
    assert r.status_code == 409 and r.json()["mensaje"] == "El organizador cerró las inscripciones."


def test_si_no_se_puede_guardar_se_devuelve_la_plata(entorno, monkeypatch):
    cid = _futbol(entorno)
    cli = _cli()
    _entrar_como(cli, monkeypatch, "capi@gmail.com", "Capi")
    stores.acreditar("capi@gmail.com", 5000)
    orig = datos.mutar_campeonato

    def roto(c, fn):
        orig(c, fn)
        raise RuntimeError("se cayó la base al guardar")

    monkeypatch.setattr(datos, "mutar_campeonato", roto)
    r = cli.post(f"/web/torneo/{cid}/equipo/crear", json={"nombre": "Los Tigres"})
    assert r.status_code == 503
    assert stores.saldo_centimos("capi@gmail.com") == 5000
    assert all(p.estado == "anulado" for p in _de("aporte_equipo"))
    ind = _camp(entorno)
    r = cli.post(f"/web/torneo/{ind}/inscribir", json={"quien": "yo"})
    assert r.status_code == 503 and stores.saldo_centimos("capi@gmail.com") == 5000
    assert all(p.estado == "anulado" for p in _de("inscripcion_torneo") + _de("inscripcion_torneo_ingreso"))


def test_existencia_ia_al_registrar_cancha_desde_la_web(monkeypatch):
    """Tras registrar/adoptar una cancha desde la web corre en segundo plano
    `verificacion_fisica.service.evaluar` (como `verificarVenue` del APK);
    nunca hace fallar el registro."""
    from verificacion_fisica import service as vf
    from web import anfitrion as anf
    llamadas = []
    monkeypatch.setattr(vf, "evaluar", lambda *a, **k: llamadas.append(a) or {"score": 90, "via": "ia"})
    assert anf.verificar_existencia("u123", "Av. Siempre Viva 742", -12.1, -77.0)["via"] == "ia"
    assert llamadas[0][0] == "u123" and llamadas[0][3] == -12.1 and llamadas[0][-1] == "sin_documentos"

    def falla(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(vf, "evaluar", falla)
    assert anf.verificar_existencia("u124", "", None, None) is None
