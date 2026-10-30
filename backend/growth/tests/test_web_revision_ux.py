"""Arreglos de la revisión visual de QAS (29-oct-2026): textos sin repetir,
montos con separador de miles, título de /entrar según el destino, extras
con la cantidad solo al marcarlos y canchas de Google con "Ver más"."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from web import router, ui  # noqa: E402
from tests.test_web_reservas import client, db  # noqa: E402,F401


def test_unir_lugar_no_repite_la_zona():
    assert ui.unir_lugar("Calle Los Laureles 365, San Isidro", "San Isidro") == "Calle Los Laureles 365, San Isidro"
    assert ui.unir_lugar("Club Raqueta San Isidro", "san isidro", sep=" · ") == "Club Raqueta San Isidro"
    assert ui.unir_lugar("Av. Larco 1150", "Miraflores") == "Av. Larco 1150, Miraflores"
    assert ui.unir_lugar("", "Surco", None) == "Surco"


def test_monto_con_separador_de_miles():
    assert ui.monto(56070, "S/", 0) == "S/ 56 070"
    assert ui.monto(1580, "S/") == "S/ 1 580.00"
    assert ui.monto(None, "$") == "$ 0.00"


def test_entrar_dice_para_que_es(db, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    client.cookies.clear()
    assert "Inicia sesión para entrar al modo anfitrión" in client.get("/entrar?volver=/anfitrion/reservas").text
    assert "Inicia sesión para jugar" in client.get("/entrar?volver=/partidos").text
    assert "Inicia sesión para reservar" in client.get("/entrar?volver=/reservar/c_lima").text
    assert router._motivo_entrar("/anfitrionx")[0] == "Inicia sesión para reservar"   # solo rutas exactas o hijas


def test_explorador_limita_las_canchas_de_google_con_ver_mas(db):
    html = client.get("/").text
    assert "id='btnDescMas'" in html and "DESC_MAX = 8" in html


def test_cache_de_canchas_publicas_y_se_borra_al_escribir(monkeypatch):
    from db import pg
    from web import datos
    llamadas = []

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, args=None):
            llamadas.append(sql)
            self.rowcount = 1

        def fetchall(self):
            return []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return Cur()

    monkeypatch.setattr(pg, "habilitado", True)
    monkeypatch.setattr(pg, "conexion", lambda: Conn())
    monkeypatch.setattr(datos, "CANCHAS_TTL", 30)
    monkeypatch.setattr(datos, "_cols_cancha", lambda: ["id"])
    monkeypatch.setattr(datos, "_sel_cancha", lambda: "id")
    datos.invalidar_canchas()
    datos.canchas_publicas()
    datos.canchas_publicas()
    listado = lambda: sum(1 for q in llamadas if "ORDER BY (coalesce(verificada" in q)  # noqa: E731
    assert listado() == 1                           # la 2.ª sale de la caché
    datos.guardar_reglas(["c1"], "d@x.com", {})     # escribir la borra
    datos.canchas_publicas()
    assert listado() == 2


def test_404_con_la_marca_para_el_navegador_y_json_para_la_api(db):
    r = client.get("/esto-no-existe", headers={"Accept": "text/html,application/xhtml+xml"})
    assert r.status_code == 404 and "No encontramos esta página" in r.text and "Ver canchas" in r.text
    # El APK y los fetch siguen recibiendo JSON.
    assert client.get("/esto-no-existe").json() == {"detail": "Not Found"}
    assert client.get("/web/no-existe", headers={"Accept": "text/html"}).json() == {"detail": "Not Found"}


def test_favoritos_en_la_cuenta(db, monkeypatch):
    from db.store import stores
    from web import sesion
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    client.cookies.clear()
    assert client.get("/web/favoritos").json()["ok"] is False                     # sin sesión: 200 y nada
    assert client.post("/web/favoritos", json={"id": "c_lima"}).status_code == 401
    client.cookies.set(sesion.COOKIE, sesion.emitir({"email": "fan@x.com", "nombre": "Fan"}))
    try:
        assert client.post("/web/favoritos", json={"id": "c_lima", "on": True}).json()["ids"] == ["c_lima"]
        # Lo que el navegador tenía guardado antes de iniciar sesión se suma sin duplicar.
        assert client.post("/web/favoritos/unir", json={"ids": ["c_lima", "c_otra"]}).json()["ids"] == ["c_lima", "c_otra"]
        assert stores.to_state()["favoritos_web"]["fan@x.com"]["ids"] == ["c_lima", "c_otra"]   # viaja en el snapshot
        html = client.get("/mis-favoritos").text
        assert "Mis favoritos" in html and "/reservar/c_lima" in html
        client.post("/web/favoritos", json={"id": "c_lima", "on": False})
        client.post("/web/favoritos", json={"id": "c_otra", "on": False})
        assert "Aún no guardas canchas" in client.get("/mis-favoritos").text
    finally:
        client.cookies.clear()
        stores.favoritos_web.pop("fan@x.com", None)


def test_calificar_solo_si_jugaste_y_sin_texto_libre(monkeypatch):
    from web import datos, jugador_resenas as jr, sesion
    cancha = {"id": "c9", "club": "Club Nueve", "dueno": "dueno@x.com", "nombre": "Fútbol 1"}
    guardadas = []
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(datos, "cancha", lambda cid: dict(cancha) if cid == "c9" else None)
    monkeypatch.setattr(datos, "canchas_publicas", lambda: [dict(cancha)])
    reservas = []
    monkeypatch.setattr(datos, "reservas_de_usuario", lambda email: list(reservas))
    monkeypatch.setattr(datos, "guardar_resena", lambda *a: guardadas.append(a) or True)
    client.cookies.set(sesion.COOKIE, sesion.emitir({"email": "ana@x.com", "nombre": "Ana"}))
    try:
        cuerpo = {"cancha_id": "c9", "estrellas": 5, "etiquetas": ["Buena atención", "texto inventado <b>"]}
        assert client.post("/web/resena", json=cuerpo).json()["error"] == "sin_reserva"     # nunca jugó ahí
        reservas.append({"cancha_id": "c9", "fecha": "2026-01-10", "estado": "confirmada"})
        assert client.post("/web/resena", json=dict(cuerpo, estrellas=0)).json()["error"] == "estrellas"
        assert client.post("/web/resena", json=cuerpo).json()["ok"] is True
        # Solo etiquetas del catálogo (lo inventado se descarta) y en el formato que el APK muestra.
        assert guardadas[-1] == ("c9", "ana@x.com", "Ana", 5, "Buena atención")
        client.cookies.set(sesion.COOKIE, sesion.emitir({"email": "dueno@x.com", "nombre": "Dueño"}))
        assert client.post("/web/resena", json=cuerpo).json()["error"] == "propia"
    finally:
        client.cookies.clear()
    monkeypatch.setattr(datos, "resenas_de", lambda ids, limite=6: [
        {"cancha_id": "c9", "autor_nombre": "Ana Pérez", "estrellas": 4, "comentario": "Buena atención", "creado": None}])
    html = jr.seccion_ficha(["c9"])
    assert "★ 4.0" in html and "Ana" in html and "Pérez" not in html and "Buena atención" in html
