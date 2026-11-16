"""MIS CANCHAS UNIFICADO (rediseño del modo anfitrión, Frames 8-13, 16-nov-2026).

- Una sola vista: locales y canchas a la izquierda, tarjeta + calendario
  operativo de la elegida (Semana de una cancha · Día con TODAS las canchas
  del local) y el menú contextual del turno.
- "Bloquear todo el día" (`POST /anfitrion/bloqueo-dia`): solo turnos LIBRES y
  FUTUROS del día, mismas reglas que bloquear un turno (dueño o su recepción,
  Pro del dueño, día cerrado por las reglas del club), y su reverso.
- El asistente "Agregar local" guarda los servicios del local del paso 2.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import config
from main import app
from web import anfitrion as anf, horarios, sesion
from tests.test_web_reservas import LIMA, _manana, db  # noqa: F401

DUENO = "dueno@x.com"


def _cli(email=DUENO):
    c = TestClient(app, base_url="https://testserver")
    c.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": email.split("@")[0].title(), "foto": ""}))
    return c


@pytest.fixture
def web(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(anf, "_en_segundo_plano", lambda fn, *a: fn(*a))
    return db


def test_bloquear_todo_el_dia_solo_libres_y_futuros_y_su_reverso(web):
    cli = _cli()
    f = _manana()
    # Una reserva a las 19:00 y un turno ya bloqueado a las 10:00: no se tocan ni se duplican.
    web.reservas["r1"] = {"id": "r1", "cancha_id": "c_lima", "fecha": f, "hora_inicio": "19:00", "hora_fin": "20:00", "estado": "confirmada",
                          "pagado": False, "precio": 60, "jugador": "Ana", "usuario": "", "grupo_reserva_id": "", "medio_pago": "efectivo"}
    web.bloqueos.add(("c_lima", f, "10:00"))
    j = cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_lima", "fecha": f, "bloquear": True}).json()
    slots = horarios.slots("07:00", "23:00", 60)
    assert j["ok"] and j["n"] == len(slots) - 2 and j["con_reserva"] == 1
    del_dia = {h for (c, fe, h) in web.bloqueos if c == "c_lima" and fe == f}
    assert del_dia == set(slots) - {"19:00"}
    # Otra cancha y otro día quedan igual.
    assert not any(c != "c_lima" or fe != f for (c, fe, _h) in web.bloqueos)
    # Desbloquear todo el día: vuelven a quedar libres (la reserva sigue).
    j = cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_lima", "fecha": f, "bloquear": False}).json()
    assert j["ok"] and j["n"] == len(slots) - 1 and not web.bloqueos and "r1" in web.reservas
    # Nada que cambiar → ok con n = 0.
    assert cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_lima", "fecha": f, "bloquear": False}).json() == {"ok": True, "n": 0, "con_reserva": 0}


def test_bloquear_dia_madrugada_pasado_cerrado_y_permisos(web, monkeypatch):
    cli = _cli()
    f = _manana()
    # Cancha nocturna 18:00→02:00: la madrugada se bloquea con su FECHA REAL (día siguiente).
    assert cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_noche", "fecha": f}).json()["ok"]
    sig = (date.fromisoformat(f) + timedelta(days=1)).isoformat()
    assert ("c_noche", sig, "01:00") in web.bloqueos and ("c_noche", f, "18:00") in web.bloqueos
    # Un día que ya pasó no tiene turnos por delante.
    r = cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_lima", "fecha": "2020-01-01"})
    assert r.status_code == 400 and "turnos por delante" in r.json()["error"]
    # Día cerrado por las reglas del club.
    web.canchas["c_lima"]["reglas_reserva"] = {"cierres": [{"fecha": f, "motivo": "Feriado"}]}
    r = cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_lima", "fecha": f})
    assert r.status_code == 400 and "cerrado" in r.json()["error"]
    # Sin sesión, cancha ajena, fecha inválida.
    assert TestClient(app, base_url="https://testserver").post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_lima", "fecha": f}).status_code == 401
    assert _cli("otro@x.com").post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_gye", "fecha": f}).status_code == 404
    assert cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_gye", "fecha": "mañana"}).status_code == 400
    # Candado Pro del DUEÑO (env), igual que bloquear un turno.
    monkeypatch.setattr(config, "WEB_MANUAL_REQUIERE_PRO", True)
    from db.store import stores
    monkeypatch.setattr(stores, "pro_activo", lambda email: False)
    r = cli.post("/anfitrion/bloqueo-dia", json={"cancha_id": "c_gye", "fecha": f})
    assert r.status_code == 402 and r.json()["error"] == "requiere_pro"


def test_vista_unificada_semana_dia_y_menu(web):
    cli = _cli()
    f = _manana()
    web.reservas["r1"] = {"id": "r1", "cancha_id": "c_noche", "fecha": f, "hora_inicio": "20:00", "hora_fin": "21:00", "estado": "confirmada",
                          "pagado": True, "precio": 60, "jugador": "Luis Torres", "usuario": "luis@x.com", "telefono": "987654321",
                          "grupo_reserva_id": "", "medio_pago": "efectivo"}
    sem = cli.get(f"/anfitrion/mis-canchas?cancha=c_lima&desde={f}").text
    # Columna izquierda por local, con Editar local y Mapa; tarjeta de la cancha elegida con su moneda.
    assert "Club Raqueta" in sem and "Club Sur" in sem and "2 locales · 3 canchas" in sem
    assert "href='/anfitrion/local/c_lima/editar'>Editar local" in sem and ">Mapa</a>" in sem
    assert "Cancha Central" in sem and "S/ 60 /h" in sem and "$ 10 /h" in sem  # cada cancha con SU moneda
    assert "Sincronizar con Google Calendar" in sem and "/anfitrion/agenda/" in sem
    assert "Semana siguiente" in sem and "data-t='libre'" in sem
    # Vista Día: TODAS las canchas del local como columnas, con la reserva de la Nocturna.
    dia = cli.get(f"/anfitrion/mis-canchas?cancha=c_lima&desde={f}&vista=dia").text
    assert "mc-cal dia" in dia and "data-c='c_lima'" in dia and "data-c='c_noche'" in dia and "data-c='c_gye'" not in dia
    assert "data-rid='r1'" in dia and "Luis" in dia and '"wa": "51987654321"' in dia  # WhatsApp con el prefijo del país
    assert "Día siguiente" in dia
    # Menú contextual: textos de las acciones y endpoints existentes + el nuevo.
    for t in ("Registrar reserva manual", "Bloquear este turno", "Bloquear todo el día", "Enviar recordatorio por WhatsApp",
              "Ver detalle de la reserva", "Cancelar reserva", "/anfitrion/bloqueo-dia", "/anfitrion/reserva-manual"):
        assert t in dia, t


def test_agregar_local_guarda_los_servicios_del_paso_2(web, monkeypatch):
    from web import almacen
    from propiedad import fotos_reclamo
    monkeypatch.setattr(almacen, "disponible", lambda: True)
    monkeypatch.setattr(almacen, "prefijo_cancha", lambda cid: f"https://sb.test/storage/v1/object/public/canchas/{cid}/")
    monkeypatch.setattr(fotos_reclamo, "propias", lambda urls, cid: [u for u in urls if f"/canchas/{cid}/" in u])
    monkeypatch.setattr(fotos_reclamo, "minimo", lambda: 1)
    nid = "u1794000000000"
    base = {"id": nid, "nombre_local": "Complejo Nuevo", "lat": -12.1, "lng": -77.03, "deportes": ["futbol"], "superficie": "Grass sintético",
            "precio": 80, "hora_apertura": "08:00", "hora_cierre": "22:00", "duracion_slot_min": 60, "whatsapp": "987654321",
            "fotos": [f"https://sb.test/storage/v1/object/public/canchas/{nid}/a.jpg"], "amenidades": ["parking", "luces", "invento", "parking"]}
    filas, _rec, err, _campo = anf._validar_registro(base, DUENO)
    assert not err, err
    assert filas[0]["amenidades"] == ["parking", "luces"]  # solo del catálogo del app, sin repetir
    filas, _rec, err, _campo = anf._validar_registro({**base, "amenidades": "parking"}, DUENO)
    assert not err and filas[0]["amenidades"] == []
    # La página es el asistente de 4 pasos con vista previa, checklist y borrador.
    html = _cli().get("/anfitrion/nueva").text
    for t in ("data-ir='1'", "data-ir='4'", "Datos y ubicación", "Fotos y servicios", "Revisar y publicar", "¿Qué pasa al publicar?",
              "Así lo verán los jugadores", "Para publicar necesitas", "Guardar borrador", "pcg_borrador_local:", "data-g='amenidades'",
              "Verificación de propiedad", "id='wa'", "id='inEvid'"):
        assert t in html, t
    assert "un verificador lo visita" not in html.lower()
