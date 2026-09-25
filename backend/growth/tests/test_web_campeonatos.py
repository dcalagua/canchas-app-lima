"""Mis campeonatos en la web (Modo anfitrión) = el MISMO flujo del app
(`mis_campeonatos_screen`, `crear_campeonato_screen`, `campeonato_detalle_screen`):
misma fila `pichangol_campeonatos`, mismo bucket, misma lógica de fixture."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from db.store import stores  # noqa: E402
from web import almacen, datos  # noqa: E402
from web import campeonatos_logica as L  # noqa: E402
from web import anfitrion as anf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from tests.test_web_reservas import _entrar_como, db  # noqa: E402,F401


class FakeCamps:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def campeonatos_de_dueno(self, email):
        return [dict(r) for k, r in sorted(self.rows.items(), reverse=True) if (r.get("dueno") or "").lower() == email.lower() and not r.get("_elim")]

    def campeonato(self, cid):
        r = self.rows.get(cid)
        return None if (r is None or r.get("_elim")) else dict(r)

    def campeonato_existe(self, cid):
        return cid in self.rows

    def guardar_campeonato(self, cid, dueno, data):
        r = self.rows.get(cid)
        if r is not None and (r.get("dueno") or "").lower() != dueno.lower():
            return False
        self.rows[cid] = dict(data, id=cid, dueno=dueno)
        return True

    def eliminar_campeonato(self, cid, dueno):
        r = self.rows.get(cid)
        if r is None or (r.get("dueno") or "").lower() != dueno.lower():
            return False
        r["_elim"] = True
        return True

    def canchas_para_sede(self):
        return [{"id": "c_lima", "club": "Club Raqueta", "nombre": "Cancha Central", "direccion": "Av. Aviación 123", "lat": -12.09, "lng": -77.0, "barrio": "San Borja"}]


def _preparar(monkeypatch, pro=True, email="orga@gmail.com"):
    fake = FakeCamps()
    for fn in ("campeonatos_de_dueno", "campeonato", "campeonato_existe", "guardar_campeonato", "eliminar_campeonato", "canchas_para_sede"):
        monkeypatch.setattr(datos, fn, getattr(fake, fn))
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(config, "LANDING_BASE_URL", "https://pg.test")
    monkeypatch.setattr(anf, "_en_segundo_plano", lambda fn, *a: fn(*a))
    stores.membresias_pro.pop(email, None)
    if pro:
        stores.membresias_pro[email] = {"hasta": "2099-01-01T00:00:00+00:00"}
    return fake


def test_mis_campeonatos_en_la_web_como_el_app(db, monkeypatch):
    cli = TestClient(app, base_url="https://testserver")
    fake = _preparar(monkeypatch)
    # Sin sesión → a entrar, como todo el Modo anfitrión.
    r = cli.get("/anfitrion/campeonatos", follow_redirects=False)
    assert r.status_code in (302, 303, 307) and "/entrar" in r.headers["location"]
    _entrar_como(cli, monkeypatch, "orga@gmail.com", "Orga")
    # El menú del anfitrión ya no dice "está en la app" para campeonatos.
    menu = cli.get("/anfitrion").text
    assert "/anfitrion/campeonatos" in menu
    r = cli.get("/anfitrion/campeonatos")
    assert r.status_code == 200 and "Aún no organizas campeonatos" in r.text and "href='/anfitrion/campeonatos/nuevo'" in r.text
    # Asistente de 3 pasos con los mismos catálogos del app.
    r = cli.get("/anfitrion/campeonatos/nuevo")
    assert r.status_code == 200
    for txt in ("Fútbol", "Natación", "Liga", "Eliminación", "Por tiempos", "Club Raqueta", "camp_"):
        assert txt in r.text, txt

    # ── Crear (paso 1 exige nombre) ──
    cid = L.nuevo_id()
    r = cli.post("/anfitrion/campeonatos/guardar", json={"id": cid, "deporte": "futbol", "formato": "liga"})
    assert r.status_code == 400 and r.json()["paso"] == 1
    body = {"id": cid, "nombre": "Copa Barrio", "deporte": "futbol", "formato": "liga", "categoria": "Libre", "sede": "Club Raqueta",
            "lat": -12.09, "lng": -77.0, "desde": "2026-11-07", "hasta": "2026-11-28", "cierre": "2026-11-05", "costo": "50", "exigeDni": False,
            "edadMin": 18, "minJugadoresEquipo": 5, "premios": "Trofeo\nMedallas", "auspiciador": "gatorade"}
    r = cli.post("/anfitrion/campeonatos/guardar", json=body)
    assert r.status_code == 200 and r.json()["ok"], r.text
    c = fake.rows[cid]
    assert c["dueno"] == "orga@gmail.com" and c["moneda"] == "S/" and c["fechas"] == L.fmt_rango(L._dt("2026-11-07").date(), L._dt("2026-11-28").date())
    assert len(c["codigo"]) == 6 and c["inscripcionAbierta"] is True and c["participantes"] == [] and c["partidos"] == []
    assert "edadMin" not in c  # solo con exigeDni, como el app
    assert c["auspiciador"] == "GATORADE" and c["minJugadoresEquipo"] == 5 and c["inscripcionHasta"].startswith("2026-11-05")
    assert c["costoInscripcion"] == 50.0 and c["sedeLat"] == -12.09
    # Sede en Ecuador → moneda $ (multi-país).
    cid_ec = L.nuevo_id()
    cli.post("/anfitrion/campeonatos/guardar", json={"id": cid_ec, "nombre": "Copa Guayas", "deporte": "tenis", "formato": "eliminacion", "lat": -2.17, "lng": -79.92})
    assert fake.rows[cid_ec]["moneda"] == "$"

    # ── Lista y detalle ──
    r = cli.get("/anfitrion/campeonatos")
    assert "Copa Barrio" in r.text and "2 campeonatos" in r.text and "Inscripciones abiertas" in r.text
    r = cli.get(f"/anfitrion/campeonatos/{cid}")
    assert r.status_code == 200 and "Copa Barrio" in r.text and c["codigo"] in r.text and f"https://pg.test/c/{cid}" in r.text
    assert "wa.me" in r.text or "whatsapp" in r.text.lower()

    # ── Participantes ──
    ids = []
    for n in ("Los Tigres", "Real Barrio", "Deportivo Sur", "Unión FC"):
        r = cli.post(f"/anfitrion/campeonatos/{cid}/participante", json={"nombre": n, "contacto": "999 111 222"})
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    assert cli.post(f"/anfitrion/campeonatos/{cid}/participante", json={"nombre": "  "}).status_code == 400
    assert len(fake.rows[cid]["participantes"]) == 4 and fake.rows[cid]["participantes"][0]["contacto"] == "999 111 222"
    r = cli.post(f"/anfitrion/campeonatos/{cid}/participante/nope/eliminar")
    assert r.status_code == 404

    # ── Fixture de liga: todos contra todos, 6 partidos en 3 jornadas ──
    r = cli.post(f"/anfitrion/campeonatos/{cid}/fixture")
    assert r.status_code == 200 and r.json()["partidos"] == 6
    partidos = fake.rows[cid]["partidos"]
    assert {int(p["ronda"]) for p in partidos} == {0, 1, 2}
    # Editar con fixture generado NO cambia el formato (como el app lo bloquea).
    cli.post("/anfitrion/campeonatos/guardar", json={**body, "formato": "eliminacion", "nombre": "Copa Barrio 2026"})
    assert fake.rows[cid]["formato"] == "liga" and fake.rows[cid]["nombre"] == "Copa Barrio 2026"
    assert fake.rows[cid]["partidos"] == partidos  # los partidos sobreviven a la edición
    # Resultado de liga (empate permitido) → tabla.
    m = partidos[0]
    r = cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": m["id"], "a": 2, "b": 2})
    assert r.status_code == 200
    r = cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": partidos[1]["id"], "a": 3, "b": 1})
    assert r.status_code == 200
    assert cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": m["id"], "a": -1, "b": 0}).status_code == 400
    tabla = L.tabla(fake.rows[cid])
    assert tabla[0]["g"] == 1 and tabla[0]["g"] * 3 + tabla[0]["e"] == 3
    det = cli.get(f"/anfitrion/campeonatos/{cid}").text
    assert "Jornada 1" in det and "Pts" in det and "2 - 2" in det

    # ── Llave de eliminación con 5 → byes y propagación del ganador ──
    for n in ("Ana", "Bea", "Cai", "Dua", "Eva"):
        cli.post(f"/anfitrion/campeonatos/{cid_ec}/participante", json={"nombre": n})
    assert cli.post(f"/anfitrion/campeonatos/{cid_ec}/fixture").status_code == 200
    ce = fake.rows[cid_ec]
    r0 = [p for p in ce["partidos"] if int(p["ronda"]) == 0]
    assert len(r0) == 4 and len(ce["partidos"]) == 7
    real = next(p for p in r0 if p["aId"] and p["bId"])
    # Empate rechazado en llave.
    assert cli.post(f"/anfitrion/campeonatos/{cid_ec}/resultado", json={"partido": real["id"], "a": 6, "b": 6}).status_code == 400
    assert cli.post(f"/anfitrion/campeonatos/{cid_ec}/resultado", json={"partido": real["id"], "a": 6, "b": 3}).status_code == 200
    ce = fake.rows[cid_ec]
    siguiente = [p for p in ce["partidos"] if int(p["ronda"]) == 1]
    assert any(real["aId"] in (p.get("aId"), p.get("bId")) for p in siguiente)  # el ganador avanzó
    assert cli.get(f"/anfitrion/campeonatos/{cid_ec}").status_code == 200

    # ── Natación: pruebas + tiempos ──
    cid_n = L.nuevo_id()
    cli.post("/anfitrion/campeonatos/guardar", json={"id": cid_n, "nombre": "Open Natación", "deporte": "natacion"})
    assert fake.rows[cid_n]["formato"] == "tiempos"
    assert cli.post(f"/anfitrion/campeonatos/{cid_n}/fixture").status_code == 400
    n1 = cli.post(f"/anfitrion/campeonatos/{cid_n}/participante", json={"nombre": "Nadador 1"}).json()["id"]
    n2 = cli.post(f"/anfitrion/campeonatos/{cid_n}/participante", json={"nombre": "Nadador 2"}).json()["id"]
    assert cli.post(f"/anfitrion/campeonatos/{cid_n}/prueba", json={"distancia": 33, "estilo": "Libre"}).status_code == 400
    pr = cli.post(f"/anfitrion/campeonatos/{cid_n}/prueba", json={"distancia": 50, "estilo": "Libre"}).json()["id"]
    assert fake.rows[cid_n]["pruebas"][0]["nombre"] == "50m Libre"
    assert cli.post(f"/anfitrion/campeonatos/{cid_n}/marca", json={"prueba": pr, "participante": n1, "tiempo": "xx"}).status_code == 400
    assert cli.post(f"/anfitrion/campeonatos/{cid_n}/marca", json={"prueba": pr, "participante": n1, "tiempo": "0:32.15", "serie": 1, "carril": 4}).status_code == 200
    assert cli.post(f"/anfitrion/campeonatos/{cid_n}/marca", json={"prueba": pr, "participante": n2, "tiempo": "0:29.80"}).status_code == 200
    rank = L.ranking_prueba(fake.rows[cid_n]["pruebas"][0])
    assert rank[0]["participanteId"] == n2 and L.fmt_tiempo(rank[1]["centesimas"]) == "0:32.15"
    det = cli.get(f"/anfitrion/campeonatos/{cid_n}").text
    assert "50m Libre" in det and "0:29.80" in det and "🥇" in det
    # Tiempo vacío borra la marca.
    cli.post(f"/anfitrion/campeonatos/{cid_n}/marca", json={"prueba": pr, "participante": n2, "tiempo": ""})
    assert len(fake.rows[cid_n]["pruebas"][0]["marcas"]) == 1
    assert cli.post(f"/anfitrion/campeonatos/{cid_n}/prueba/{pr}/eliminar").status_code == 200 and "pruebas" not in fake.rows[cid_n]

    # ── Imágenes al MISMO bucket/carpeta del app ──
    subidas = []
    monkeypatch.setattr(almacen, "subir", lambda bucket, ruta, b, ct="image/jpeg", **kw: subidas.append((bucket, ruta)) or f"https://sb.test/storage/v1/object/public/{bucket}/{ruta}")
    borradas = []
    monkeypatch.setattr(almacen, "borrar_foto", lambda url: borradas.append(url) or True)
    r = cli.post(f"/anfitrion/campeonatos/{cid}/foto?tipo=logo", content=b"\xff\xd8x", headers={"content-type": "image/jpeg"})
    assert r.status_code == 200 and subidas[-1] == ("canchas", f"campeonatos/{cid}.jpg") and fake.rows[cid]["logoUrl"].startswith(r.json()["url"].split("?")[0])
    r = cli.post(f"/anfitrion/campeonatos/{cid}/foto?tipo=ausp", content=b"\xff\xd8x", headers={"content-type": "image/jpeg"})
    assert subidas[-1][1].startswith(f"campeonatos/{cid}_ausp_") and fake.rows[cid]["auspiciadoresLogos"] == [r.json()["url"]]
    r = cli.post(f"/anfitrion/campeonatos/{cid}/imagen/quitar", json={"tipo": "ausp", "url": r.json()["url"]})
    assert r.status_code == 200 and "auspiciadoresLogos" not in fake.rows[cid] and borradas
    assert cli.post(f"/anfitrion/campeonatos/{cid}/foto?tipo=logo", content=b"x", headers={"content-type": "text/plain"}).status_code == 415
    # Afiche: arte IA por variante / tema; quitar fondo.
    assert cli.post(f"/anfitrion/campeonatos/{cid}/afiche", json={"variante": 3, "tema": "noche de luces"}).status_code == 200
    assert fake.rows[cid]["aficheVariante"] == 3 and fake.rows[cid]["aficheTema"] == "noche de luces"

    # ── Duplicar (nueva edición) y eliminar ──
    r = cli.post(f"/anfitrion/campeonatos/{cid}/duplicar")
    assert r.status_code == 200
    nuevo = fake.rows[r.json()["id"]]
    assert nuevo["nombre"] == "Copa Barrio 2026" and nuevo["participantes"] == [] and nuevo["partidos"] == [] and nuevo["fechas"] == "" and nuevo["codigo"] != c["codigo"]
    assert cli.post(f"/anfitrion/campeonatos/{cid}/eliminar").status_code == 200
    assert fake.rows[cid]["_elim"] and cli.get(f"/anfitrion/campeonatos/{cid}").status_code == 404

    # ── Otro usuario no ve ni toca lo ajeno ──
    _entrar_como(cli, monkeypatch, "otro@gmail.com", "Otro")
    stores.membresias_pro["otro@gmail.com"] = {"hasta": "2099-01-01T00:00:00+00:00"}
    assert cli.get(f"/anfitrion/campeonatos/{cid_ec}").status_code == 404
    assert cli.post(f"/anfitrion/campeonatos/{cid_ec}/participante", json={"nombre": "Colado"}).status_code == 404
    assert cli.post("/anfitrion/campeonatos/guardar", json={"id": cid_ec, "nombre": "Robo", "deporte": "tenis"}).status_code == 404
    assert "Copa Guayas" not in cli.get("/anfitrion/campeonatos").text
    stores.membresias_pro.pop("otro@gmail.com", None)
    stores.membresias_pro.pop("orga@gmail.com", None)


def test_campeonatos_web_candado_pro_como_el_app(db, monkeypatch):
    """Sin Pro: se ve la lista, pero "Organizar" abre el aviso Pro y crear responde 402 (`requiere_pro`)."""
    cli = TestClient(app, base_url="https://testserver")
    fake = _preparar(monkeypatch, pro=False)
    _entrar_como(cli, monkeypatch, "orga@gmail.com", "Orga")
    r = cli.get("/anfitrion/campeonatos")
    assert r.status_code == 200 and "modalPro" in r.text and "Es Pichangol Pro" in r.text and "href='/anfitrion/campeonatos/nuevo'" not in r.text
    r = cli.get("/anfitrion/campeonatos/nuevo", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    r = cli.post("/anfitrion/campeonatos/guardar", json={"id": L.nuevo_id(), "nombre": "Copa", "deporte": "futbol"})
    assert r.status_code == 402 and r.json()["error"] == "requiere_pro"
    assert not fake.rows
    # Un campeonato que YA es suyo se sigue administrando sin Pro (como el app: el candado es para crear).
    cid = L.nuevo_id()
    fake.rows[cid] = {"id": cid, "dueno": "orga@gmail.com", "nombre": "Vieja Copa", "deporte": "tenis", "formato": "eliminacion", "participantes": [], "partidos": [],
                      "inscripcionAbierta": True, "codigo": "ABC123", "fechas": "", "costoInscripcion": 0}
    assert cli.get(f"/anfitrion/campeonatos/{cid}").status_code == 200
    assert cli.post(f"/anfitrion/campeonatos/{cid}/participante", json={"nombre": "Ana"}).status_code == 200
    assert cli.post(f"/anfitrion/campeonatos/{cid}/duplicar").status_code == 402
