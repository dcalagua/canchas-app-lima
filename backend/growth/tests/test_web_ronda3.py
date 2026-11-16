"""Plan de mejoras ronda 2 (resto): lista de espera, notificaciones, ayuda,
SEO (sitemap, páginas por zona, manifest), mover el pin del local, agenda
iCal del anfitrión, reprogramar y errores de JavaScript."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from web import datos, sesion  # noqa: E402
from tests.test_web_reservas import client, db  # noqa: E402,F401


def _login(monkeypatch, email="ana@x.com", nombre="Ana"):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    client.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": nombre}))


def _reserva(db, rid, fecha, hora, fin, usuario="ana@x.com", precio=60, grupo=None, cancha="c_lima"):
    db.reservas[rid] = {"id": rid, "cancha_id": cancha, "jugador": "Ana", "fecha": fecha, "dia": "", "hora_inicio": hora,
                        "hora_fin": fin, "estado": "confirmada", "traida_por_app": True, "precio": precio, "pagado": True,
                        "usuario": usuario, "deporte": "futbol", "extras": [], "telefono": "987654321",
                        "grupo_reserva_id": grupo, "moneda": "S/", "medio_pago": "tarjeta"}


def test_lista_de_espera_en_turnos_ocupados(db, monkeypatch):
    from web import jugador_espera as je
    anotados = []
    monkeypatch.setattr(je, "_db_unirse", lambda e: anotados.append(e) or True)
    monkeypatch.setattr(je, "mias", lambda email, cancha_id="", fecha="": [{"cancha_id": x["cancha_id"], "fecha": x["fecha"], "hora": x["hora"]}
                                                                             for x in anotados if x["usuario"] == email])
    manana = (date.today() + timedelta(days=1)).isoformat()
    _reserva(db, "r_otro", manana, "20:00", "21:00", usuario="otro@x.com")
    try:
        client.cookies.clear()
        assert client.post("/web/espera", json={"cancha_id": "c_lima", "fecha": manana, "hora": "20:00"}).status_code == 401
        _login(monkeypatch)
        # Un turno LIBRE no entra a la lista: se reserva.
        assert client.post("/web/espera", json={"cancha_id": "c_lima", "fecha": manana, "hora": "18:00"}).json()["error"] == "libre"
        assert client.post("/web/espera", json={"cancha_id": "c_lima", "fecha": manana, "hora": "20:00"}).json()["ok"] is True
        assert anotados[-1]["usuario"] == "ana@x.com" and anotados[-1]["hora"] == "20:00"
        # La ficha marca el turno ocupado como "en espera" para este jugador.
        assert client.get(f"/web/disponibilidad/c_lima?fecha={manana}").json()["espera"] == ["20:00"]
        # Su PROPIO turno no entra a la lista de espera.
        _reserva(db, "r_mia", manana, "21:00", "22:00")
        assert client.post("/web/espera", json={"cancha_id": "c_lima", "fecha": manana, "hora": "21:00"}).json()["error"] == "es_tuya"
        assert client.get(f"/web/disponibilidad/c_lima?fecha={manana}").json()["propias"] == ["21:00"]
    finally:
        client.cookies.clear()


def test_al_cancelar_se_avisa_a_la_lista_de_espera(db, monkeypatch):
    from web import jugador_espera as je
    avisos = []
    monkeypatch.setattr(je, "esperan", lambda cid, f, h: ["luis@x.com", "ana@x.com"])
    from pagos import router as pr
    monkeypatch.setattr(pr, "_aviso_push_usuario", lambda email, t, c, tipo="aviso": avisos.append((email, t, tipo)))
    import threading
    monkeypatch.setattr(threading, "Thread", lambda target, **k: type("T", (), {"start": lambda self: target()})())
    je.avisar_liberados([("c_lima", "2026-12-01", "20:00")], salvo="ana@x.com")
    assert avisos == [("luis@x.com", "¡Se liberó tu hora! ⏰", "espera")]


def test_notificaciones_y_ayuda(db, monkeypatch):
    from web import jugador_avisos as ja
    monkeypatch.setattr(ja, "avisos_de", lambda email, limite=50: [
        {"id": 7, "titulo": "Reserva confirmada 📅", "cuerpo": "Tu reserva del sáb", "tipo": "reserva", "creado": None}])
    monkeypatch.setattr(ja, "nuevos", lambda email, desde: 1 if desde < 7 else 0)
    _login(monkeypatch)
    try:
        html = client.get("/notificaciones").text
        assert "Reserva confirmada" in html and "href='/mis-reservas'" in html
        assert client.get("/web/avisos/nuevos?desde=0").json()["n"] == 1
        assert "data-badge-avisos" in client.get("/perfil").text
    finally:
        client.cookies.clear()
    ayuda = client.get("/ayuda").text
    assert "Centro de ayuda" in ayuda and "FAQPage" in ayuda and "lista de espera" in ayuda


def test_sitemap_paginas_por_zona_y_manifest(db):
    xml = client.get("/sitemap.xml").text
    assert "<urlset" in xml and "/reservar/c_lima" in xml and "/canchas/futbol/san-borja" in xml and "/ayuda" in xml
    assert "Sitemap:" in client.get("/robots.txt").text
    z = client.get("/canchas/futbol/san-borja")
    assert z.status_code == 200 and "Canchas de fútbol en San Borja" in z.text and "c_lima" in z.text
    assert client.get("/canchas/futbol/zona-que-no-existe").status_code == 404
    assert "class='sr-only'" in client.get("/").text   # la portada tiene h1
    m = client.get("/manifest.webmanifest").json()
    assert m["display"] == "standalone" and m["icons"]


def test_mover_pin_del_local_hasta_300_m(db, monkeypatch):
    _login(monkeypatch, "dueno@x.com", "Dueño")
    try:
        base = {"nombre_local": "Club Raqueta", "direccion": "Av. Aviación 123", "amenidades": [], "servicios_extra": []}
        lejos = client.post("/anfitrion/local/c_lima/editar", json=dict(base, lat=-12.10, lng=-77.0)).json()   # ~1,1 km
        assert lejos["ok"] is False and lejos["campo"] == "ubicacion"
        ok = client.post("/anfitrion/local/c_lima/editar", json=dict(base, lat=-12.0905, lng=-77.0005)).json()
        assert ok["ok"] is True and db.canchas["c_lima"]["lat"] == -12.0905
    finally:
        client.cookies.clear()


def test_agenda_ical_privada_del_anfitrion(db, monkeypatch):
    from web import anfitrion_agenda as ag
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "adm")
    hoy = date.today().isoformat()
    _reserva(db, "r1", hoy, "19:00", "20:00", usuario="cliente@x.com")
    tok = ag.token("dueno@x.com")
    r = client.get(f"/anfitrion/agenda/{tok}.ics")
    assert r.status_code == 200 and "BEGIN:VCALENDAR" in r.text and "Cancha Central" in r.text
    assert client.get("/anfitrion/agenda/" + tok[:-3] + "xyz.ics").status_code == 404   # firma alterada


def test_reprogramar_mismo_precio_y_con_anticipacion(db, monkeypatch):
    movidas = []

    def mover(cambios, email):
        for rid, f, hi, hf in cambios:
            db.reservas[rid].update(fecha=f, hora_inicio=hi, hora_fin=hf)
        movidas.append(cambios)
        return True
    monkeypatch.setattr(datos, "mover_reservas", mover)
    en3 = (date.today() + timedelta(days=3)).isoformat()
    _reserva(db, "r_ana", en3, "15:00", "16:00", precio=60)
    _login(monkeypatch)
    try:
        assert "Cambiar horario" in client.get("/reserva/r_ana").text
        assert "Ahora:" in client.get("/reserva/r_ana/cambiar").text
        # 08:00 tiene hora feliz (otro precio) → no; 16:00 mismo precio → sí.
        assert client.post("/web/reprogramar", json={"ref": "r_ana", "fecha": en3, "hora": "08:00"}).json()["error"] == "precio_distinto"
        r = client.post("/web/reprogramar", json={"ref": "r_ana", "fecha": en3, "hora": "16:00"}).json()
        assert r["ok"] is True and db.reservas["r_ana"]["hora_inicio"] == "16:00"
        # Sin la anticipación del club (aquí 200 h): no se puede.
        from pagos import devoluciones
        monkeypatch.setattr(devoluciones, "horas_minimas", lambda c=None: 200.0)
        hoy = (date.today() + timedelta(days=2)).isoformat()
        _reserva(db, "r_hoy", hoy, "21:00", "22:00", precio=60)
        assert client.post("/web/reprogramar", json={"ref": "r_hoy", "fecha": en3, "hora": "17:00"}).json()["error"] == "no_permitido"
        # De otro jugador: no.
        _reserva(db, "r_luis", en3, "18:00", "19:00", usuario="luis@x.com")
        assert client.post("/web/reprogramar", json={"ref": "r_luis", "fecha": en3, "hora": "17:00"}).json()["error"] == "no_permitido"
    finally:
        client.cookies.clear()


def test_errores_de_javascript_van_a_los_logs(db, capsys):
    assert client.post("/web/js-error", content=b'{"m":"x is undefined","u":"/"}').status_code == 204
    assert "[js]" in capsys.readouterr().out
