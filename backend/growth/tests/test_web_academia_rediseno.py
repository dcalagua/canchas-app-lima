"""Rediseño del modo anfitrión (16-nov-2026) · frente academia: Mi academia,
Plan Academia, Soy boleador y Verificador con el kit de vistas. Prueban las
piezas NUEVAS (resumen de cobros por academia, accesos de gestión con candado,
banner con la barra "Día X de N", beneficios por país, verificación de
identidad dentro de "Soy boleador", controles del verificador)."""
from fastapi.testclient import TestClient

import academia_plan as ap
from db.store import stores
from main import app
from tests.test_web_academia_plan import DUENO, _entrar_como, _vencer, db  # noqa: F401
from web import academia_plan_web as apw
from web import anfitrion_academia as aa
from web import datos


def _main(html: str) -> str:
    return html.split("<main", 1)[1] if "<main" in html else html


def test_resumen_de_cobros_suma_lo_pendiente_y_lo_vencido():
    mats = [{"cuotas": [{"monto": 250, "pagada": True, "vencimiento": "2020-01-05"},
                        {"monto": 250, "pagada": False, "vencimiento": "2020-02-05"},
                        {"monto": 100, "pagada": False, "vencimiento": "2999-01-01"}, "basura"]},
            {"cuotas": None}]
    assert aa.resumen_cobros(mats) == (350.0, 250.0)
    assert aa._m(1580, "S/") == "S/ 1 580" and aa._m(12.5, "$") == "$ 12.50"


def test_mi_academia_tarjeta_con_cifras_reales_y_accesos(db, monkeypatch):
    db.matriculas["al_1"] = {"id": "al_1", "academiaId": "ac_1", "email": "papa@gmail.com", "nombre": "Lucas",
                             "cuotas": [{"id": "c1", "monto": 250, "pagada": False, "vencimiento": "2020-01-01"}]}
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    html = _main(cli.get("/anfitrion/academia").text)
    assert "1 academia · 1 alumno. Edita aquí o en la app" in html and "＋ Otra academia" in html
    # Banner de prueba con la barra del día y su fecha de término.
    assert "Te quedan 30 días de prueba gratis del Plan Academia" in html and "Día 1 de 30" in html and "role='progressbar'" in html
    # Cifras de la tarjeta (moneda de la academia) y los 10 accesos.
    assert "<small>Alumnos</small><b>1</b>" in html and "<small>Desde</small><b>S/ 80/mes</b>" in html
    assert "S/ 250 por cobrar" in html and "href='/anfitrion/cobros?academia=ac_1'" in html
    for ruta in ("alumnos", "asistencia", "evaluaciones", "ranking", "reportes", "chats", "sedes"):
        assert f"href='/anfitrion/academia/{ruta}?academia=ac_1'" in html, ruta
    assert "href='/anfitrion/academia/plan?academia=ac_1'" in html and "Prueba · 30 días" in html
    # Sin landing generada: ni "Ver landing" ni /l/; sí la ficha pública.
    assert "Ver landing" not in html and "/l/ac_1" not in html and "href='/academia/ac_1'" in html
    monkeypatch.setattr(stores, "landings", {"ac_1": {}})
    html = _main(cli.get("/anfitrion/academia").text)
    assert "Ver landing" in html and "href='/l/ac_1'" in html
    # Plan vencido: banner rojo y candado en la gestión; Cobros sigue abierto.
    _vencer()
    html = _main(cli.get("/anfitrion/academia").text)
    assert "Tu plan venció" in html and "Activar por S/ 11.50" in html
    assert html.count("Requiere Plan Academia") == 7 and "S/ 250 por cobrar" in html and "Vencido · actívalo" in html


def test_mi_academia_oculta_en_un_pais_no_habilitado(db, monkeypatch):
    monkeypatch.setitem(stores.config, "acad_paises", "PE")
    db.academias["ac_1"].update({"lat": -2.17, "lng": -79.92, "moneda": "$"})
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    assert "Oculta al público en Ecuador" in _main(cli.get("/anfitrion/academia").text)


def test_progreso_y_beneficios_por_pais(db):
    a = db.academia("ac_1")
    est = ap.estado(a)
    assert apw._progreso(a, est) == (1, 30, 3.3)
    from datetime import datetime, timedelta
    r = stores.planes_academia["ac_1"]
    r["prueba_desde"] = (datetime.fromisoformat(r["prueba_hasta"]) - timedelta(days=40)).isoformat()  # prueba de 40 días
    assert apw._progreso(a, ap.estado(a))[:2] == (11, 40)
    textos = {t: d for _i, t, d in apw.beneficios_de(a)}
    directo = textos["Tus alumnos te pagan directo · 0 % de comisión"]
    assert "Yape" in directo and "QR" not in directo and "Android" in directo
    bo = dict(a, lat=-16.5, lng=-68.15, moneda="Bs")
    directo_bo = {t: d for _i, t, d in apw.beneficios_de(bo)}["Tus alumnos te pagan directo · 0 % de comisión"]
    assert "Bolivia" in directo_bo and "QR de cobro" in directo_bo and "Yape" not in directo_bo
    assert len(apw.beneficios_de(None)) == 4


def test_plan_academia_tarjeta_y_que_incluye(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    html = _main(cli.get("/anfitrion/academia/plan").text)
    assert "Prueba gratis · quedan 30 días" in html and "S/ 11.50</b><span>al mes" in html and "Activar ya · S/ 11.50" in html
    assert "Si activas ahora, el mes se suma al final de la prueba" in html and "Tu saldo: S/" in html
    assert "data-plan-renovar='ac_1'" in html and " checked" in html and "role='switch'" in html
    assert "Qué incluye" in html and "Precio fijo, sin comisión por alumno." in html and "Yape" in html
    # Sin cobro directo registrado: aviso según el país (Perú → Yape).
    db.academias["ac_1"].pop("cobroDirecto")
    assert "Registrar mi Yape ›" in _main(cli.get("/anfitrion/academia/plan").text)
    db.academias["ac_1"].update({"lat": -2.17, "lng": -79.92, "moneda": "$"})
    html = _main(cli.get("/anfitrion/academia/plan").text)
    assert "Subir mi QR ›" in html and "Registrar mi Yape" not in html and "$ " in html


def test_operacion_de_academia_con_encabezado_del_kit(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    _entrar_como(cli, monkeypatch, DUENO, "Profe")
    for ruta, titulo in (("alumnos", "Alumnos"), ("ranking", "Ranking"), ("sedes", "Sedes y horarios")):
        html = _main(cli.get(f"/anfitrion/academia/{ruta}?academia=ac_1").text)
        assert f"<a class='va-volver' href='/anfitrion/academia' aria-label='Volver'>‹</a>{titulo}</h1>" in html, ruta
        assert "Academia Ace · " in html and "aria-label='Secciones de la academia'" in html
        assert "anf-back" not in html and "Mis academias" not in html, ruta


def test_boleador_sin_identidad_verifica_en_la_misma_pagina(monkeypatch):
    from web import sesion
    monkeypatch.setattr(datos, "boleador", lambda email: None)
    monkeypatch.setattr(datos, "esta_verificado", lambda email: False)
    from web import jugador_cuenta
    monkeypatch.setattr(jugador_cuenta, "perfil_completo", lambda email: {"celular": ""})
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": "juan@gmail.com", "nombre": "Juan"}))
    html = _main(cli.get("/anfitrion/boleador").text)
    assert "‹ Roles" in html and "Soy boleador" in html and "Tu identidad, verificada" in html
    assert "1. Verifica tu identidad" in html and "2. Arma tu perfil" in html and "3. Recibe turnos" in html
    assert "data-bol-pais='PE'" in html and "data-bol-pais='BO'" in html and "data-bol-pais='EC'" in html
    # El formulario llama al MISMO endpoint de /cuenta/identidad (sus reglas y su tope de intentos).
    assert "fetch('/web/cuenta/identidad'" in html and "Verificar DNI" in html and "No guardamos foto de tu documento" in html
    assert '"BO": {"doc": "CI", "largo": 0, "registro": "", "web": false' in html and "Verificar en la app" in html
    assert '"EC": {"doc": "Cédula", "largo": 10' in html
    from web import anfitrion_boleadores as ab
    assert " confirm(" not in ab._JS_ID and "alert(" not in ab._JS_ID
    # Con Bolivia como país del celular el título dice "sparring".
    monkeypatch.setattr(jugador_cuenta, "perfil_completo", lambda email: {"celular": "+59171234567"})
    assert "Soy sparring" in _main(cli.get("/anfitrion/boleador").text)


def test_boleador_verificado_ve_su_perfil_con_el_paso_2(monkeypatch):
    from web import sesion
    monkeypatch.setattr(datos, "boleador", lambda email: None)
    monkeypatch.setattr(datos, "esta_verificado", lambda email: True)
    monkeypatch.setattr(datos, "solicitudes_de_boleador", lambda email: [])
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": "juan@gmail.com", "nombre": "Juan"}))
    html = _main(cli.get("/anfitrion/boleador").text)
    assert "<li class='ok'>" in html and "<li class='sel' aria-current='step'>" in html and "Aún no registrado" in html
    assert "Mi perfil" in html and "id='btnGuardar'" in html and "Sin solicitudes por ahora" in html
    assert "id='bolVer'" not in html


def test_verificador_con_segmentado_distancia_y_orden(monkeypatch):
    from web import anfitrion_verificador as av
    from web import sesion
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": "vf@x.com", "nombre": "Vera"}))
    html = _main(cli.get("/anfitrion/verificador").text)
    assert "‹ Roles" in html and "data-vtab='visitas'" in html and "data-vtab='codigo'" in html
    assert "1. Vas a la cancha" in html and "2. Tomas fotos y GPS" in html and "3. Confirmas y firmas" in html
    assert "Ubicación desactivada" in html and "id='btnGps'" in html and "id='radios'" in html
    assert "<option value='cerca'>La más cercana primero</option>" in html and "id='cntVisitas'" in html
    assert "id='valCodigo'" in html and "id='capEnviar'" in html and "id='capFotoIn'" in html
    assert "Ver todas las visitas" in av._JS_VERIFICADOR and "verTodas" in av._JS_VERIFICADOR
