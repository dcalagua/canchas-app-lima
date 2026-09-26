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
    # Torneo por equipos CON costo: sin pozos completos, la web pregunta (409)
    # y el organizador decide generar con todos.
    r = cli.post(f"/anfitrion/campeonatos/{cid}/fixture")
    assert r.status_code == 409 and r.json()["error"] == "pozos_incompletos" and len(r.json()["equipos"]) == 4
    r = cli.post(f"/anfitrion/campeonatos/{cid}/fixture", json={"con_todos": True})
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


def test_grupos_garantiza_minimo_de_partidos_y_llave_cruzada(db, monkeypatch):
    """Formato "Grupos + eliminatoria" (pedido del director, 25-sep-2026: "quiero
    asegurar que al menos cada equipo juegue 2 partidos a más"): fase de grupos
    con tamaño mínimo minPartidos+1 y luego llave con los 2 primeros de cada grupo."""
    # Garantía pura: para cualquier cantidad razonable de equipos, cada uno juega ≥ mínimo.
    for minp in (2, 3):
        for n in range(minp + 1, 41):  # con menos de minp+1 equipos no hay cómo garantizarlo (se juega solo la final)
            ps = [{"id": f"p{i}", "nombre": f"E{i}"} for i in range(n)]
            c = {"formato": "grupos", "minPartidos": minp, "participantes": ps, "partidos": []}
            c["partidos"] = L.generar_fixture(c)
            tams = L.armar_grupos(n, minp)
            assert sum(tams) == n and max(tams) - min(tams) <= 1 and min(tams) >= minp + 1, (n, minp, tams)
            assert min(L.partidos_de(c, p["id"]) for p in ps) >= minp, (n, minp)
            assert len([m for m in L.partidos_llave(c) if int(m["ronda"]) == 0]) * 2 >= 2 * len(tams)
    assert L.armar_grupos(8, 2) == [4, 4] and L.armar_grupos(6, 2) == [3, 3] and L.armar_grupos(12, 2) == [4, 4, 4] and L.armar_grupos(2, 2) == []

    cli = TestClient(app, base_url="https://testserver")
    fake = _preparar(monkeypatch)
    _entrar_como(cli, monkeypatch, "orga@gmail.com", "Orga")
    r = cli.get("/anfitrion/campeonatos/nuevo")
    assert "Grupos + eliminatoria" in r.text and "minPartBox" in r.text and "Al menos 2" in r.text
    cid = L.nuevo_id()
    r = cli.post("/anfitrion/campeonatos/guardar", json={"id": cid, "nombre": "Copa Grupos", "deporte": "futbol", "formato": "grupos", "minPartidos": 2})
    assert r.status_code == 200, r.text
    assert fake.rows[cid]["formato"] == "grupos" and fake.rows[cid]["minPartidos"] == 2
    ids = [cli.post(f"/anfitrion/campeonatos/{cid}/participante", json={"nombre": n}).json()["id"]
           for n in ("Tigres", "Leones", "Pumas", "Lobos", "Osos", "Halcones", "Toros", "Zorros")]
    assert cli.post(f"/anfitrion/campeonatos/{cid}/fixture").json()["ok"]
    c = fake.rows[cid]
    assert L.grupos_de(c) == ["A", "B"] and len(L.partidos_grupo(c)) == 12 and len(L.partidos_llave(c)) == 3
    det = cli.get(f"/anfitrion/campeonatos/{cid}").text
    assert "Grupo A" in det and "Grupo B" in det and "Fase final" in det and "Grupos y fase final" in det
    assert "cada equipo juega al menos 2 partidos" in det and "2 grupos de 4/4" in det
    assert "Los cruces se definen solos" in det
    # Empate PERMITIDO en fase de grupos; los cruces de la llave siguen sin definir.
    g = L.partidos_grupo(c)
    r = cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": g[0]["id"], "a": 1, "b": 1})
    assert r.status_code == 200, r.text
    assert all(m.get("aId") is None for m in L.partidos_llave(fake.rows[cid]))
    # El resto: gana el de menor índice → 1.º y 2.º claros en cada grupo.
    for m in L.partidos_grupo(fake.rows[cid]):
        if L.jugado(m):
            continue
        ia, ib = ids.index(m["aId"]), ids.index(m["bId"])
        assert cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": m["id"], "a": 3 if ia < ib else 0, "b": 0 if ia < ib else 3}).status_code == 200
    c = fake.rows[cid]
    assert L.grupos_completos(c)
    semis = [m for m in L.partidos_llave(c) if int(m["ronda"]) == 0]
    # Siembra cruzada: 1.º de un grupo contra 2.º del otro, nunca dos del mismo grupo.
    grupo_de = {m[k]: m["grupo"] for m in L.partidos_grupo(c) for k in ("aId", "bId")}
    assert all(m["aId"] and m["bId"] and grupo_de[m["aId"]] != grupo_de[m["bId"]] for m in semis)
    # Empate RECHAZADO en la llave; ganador avanza a la final.
    assert cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": semis[0]["id"], "a": 2, "b": 2}).status_code == 400
    for m in semis:
        assert cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": m["id"], "a": 2, "b": 0}).status_code == 200
    c = fake.rows[cid]
    final = [m for m in L.partidos_llave(c) if int(m["ronda"]) == 1][0]
    assert final["aId"] == semis[0]["aId"] and final["bId"] == semis[1]["aId"] and not L.terminado(c)
    assert cli.post(f"/anfitrion/campeonatos/{cid}/resultado", json={"partido": final["id"], "a": 1, "b": 0}).status_code == 200
    c = fake.rows[cid]
    assert L.terminado(c) and L.campeon_y_subcampeon(c) == (final["aId"], final["bId"])
    det = cli.get(f"/anfitrion/campeonatos/{cid}").text
    assert "TORNEO FINALIZADO" in det and "🥇 " in det
    # Página pública (la misma que abre el app) muestra grupos y fase final.
    from marketing import campeonato_web
    html = campeonato_web.html_campeonato(c, c["id"])
    assert "Grupo A" in html and "Fase final" in html and "Grupos + eliminatoria" in html
    stores.membresias_pro.pop("orga@gmail.com", None)


def test_enlaces_publicos_sin_espacios_aunque_la_variable_los_traiga(db, monkeypatch):
    """Caso real en QAS (25-sep-2026): `LANDING_BASE_URL` quedó en Railway con un
    espacio al final y "Ver afiche" llevaba a `https://dominio%20/c/<id>/afiche.png`
    (ERR_NAME_NOT_RESOLVED). La base se normaliza al leer el entorno y, por si
    alguien la monkeypatchea sucia, también al armar cada enlace."""
    monkeypatch.setenv("LANDING_BASE_URL", " https://pg.test / ")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.test/ ")
    assert config._url_env("LANDING_BASE_URL") == "https://pg.test"
    assert config._url_env("PUBLIC_BASE_URL") == "https://api.test"
    assert config._url_env("NO_EXISTE_ESTA_VARIABLE") == ""

    cli = TestClient(app, base_url="https://testserver")
    fake = _preparar(monkeypatch)
    monkeypatch.setattr(config, "LANDING_BASE_URL", "https://pg.test ")
    _entrar_como(cli, monkeypatch, "orga@gmail.com", "Orga")
    cid = L.nuevo_id()
    fake.rows[cid] = {"id": cid, "dueno": "orga@gmail.com", "nombre": "Beata 2026", "deporte": "futbol", "formato": "eliminacion", "participantes": [], "partidos": [],
                      "inscripcionAbierta": True, "codigo": "ABC123", "fechas": "", "costoInscripcion": 0}
    r = cli.get(f"/anfitrion/campeonatos/{cid}")
    assert r.status_code == 200
    assert f"https://pg.test/c/{cid}/afiche.png" in r.text
    assert f"https://pg.test/c/{cid}" in r.text
    # Ni con espacio literal ni codificado (así salía en QAS: `pichangol.app%20/c/...`).
    assert "pg.test /" not in r.text and "pg.test%20" not in r.text and "pg.test%20/" not in r.text


def test_whatsapp_desde_la_web_sin_emojis_de_4_bytes(db, monkeypatch):
    """Queja del director (26-sep-2026, captura): el resumen compartido desde
    Mis campeonatos llegaba a WhatsApp Windows con "��" en vez de 🏆 📊 👉.
    WhatsApp para Windows rompe los caracteres fuera del plano básico que
    viajan por `wa.me/?text=`; el enlace se arma con `ui.enlace_whatsapp`,
    que los traduce a emojis de 2 bytes (⭐ ▶ ➡) y nunca deja astrales."""
    from web import ui
    seguro = ui.texto_whatsapp("🏆⚽ *COPA*\n📊 Grupo A:\n👉 https://x.test/c/1\n🎾 tenis 🤷")
    assert seguro == "⭐⚽ *COPA*\n▶ Grupo A:\n➡ https://x.test/c/1\n⭐ tenis"
    assert all(ord(ch) <= 0xFFFF for ch in seguro)
    assert ui.enlace_whatsapp("hola ⭐", "+51 999 888 777") == "https://wa.me/51999888777?text=hola%20%E2%AD%90"

    cli = TestClient(app, base_url="https://testserver")
    fake = _preparar(monkeypatch)
    _entrar_como(cli, monkeypatch, "orga@gmail.com", "Orga")
    cid = L.nuevo_id()
    c = {"id": cid, "dueno": "orga@gmail.com", "nombre": "Beata Imelda 2026", "deporte": "futbol", "formato": "grupos", "minPartidos": 2,
         "participantes": [{"id": f"p{i}", "nombre": f"Equipo {i}", "contacto": "", "email": ""} for i in range(6)],
         "partidos": [], "inscripcionAbierta": True, "codigo": "ABC123", "fechas": "", "costoInscripcion": 0}
    c["partidos"] = L.generar_fixture(c)
    fake.rows[cid] = c
    r = cli.get(f"/anfitrion/campeonatos/{cid}")
    assert r.status_code == 200
    import re
    import urllib.parse
    # href = ESCRITORIO (solo Latin-1: WhatsApp Windows rompió hasta ⚽ en la
    # 2.ª captura) · data-wa-movil = móvil con emojis de 2 bytes.
    m = re.search(r"href='(https://wa\.me/\?text=[^']+)' data-wa-movil='(https://wa\.me/\?text=[^']+)'", r.text)
    assert m, "el botón de WhatsApp debe salir de ui.boton_whatsapp"
    pc = urllib.parse.unquote(m.group(1).split("text=", 1)[1])
    movil = urllib.parse.unquote(m.group(2).split("text=", 1)[1])
    for texto in (pc, movil):
        assert "Grupo A" in texto and "Beata Imelda 2026" in texto and "https://pg.test/c/" in texto
    assert all(ord(ch) <= 0xFF for ch in pc), pc
    assert "*Pichangol*" in pc and "Grupo A:" in pc.replace("  ", " ")
    assert all(ord(ch) <= 0xFFFF for ch in movil) and "⚽" in movil and "⭐" in movil
    assert "%F0%9F" not in m.group(2)
    assert ui.texto_whatsapp_pc("🏆⚽ *COPA* – hoy…\n👉 https://x.test") == "*COPA* - hoy...\n> https://x.test"
    assert "data-wa-movil" in ui.JS_NAV


def test_vaquita_del_equipo_en_la_web(db, monkeypatch):
    """Pedido del director (26-sep-2026): la cuota es POR EQUIPO y se reparte
    entre el plantel. Web: máximo de jugadores en el asistente, equipos del
    organizador con código, chips con el pozo, aviso al generar el fixture con
    exclusión + devolución, y "cada jugador pone" en publicidad y página pública."""
    import re
    import urllib.parse
    from pagos import pozos as _pz
    stores.pozos_equipo = {}; stores.pagos = []; stores.saldos = {}
    cli = TestClient(app, base_url="https://testserver")
    fake = _preparar(monkeypatch)
    _entrar_como(cli, monkeypatch, "orga@gmail.com", "Orga")
    cid = L.nuevo_id()
    # Asistente: máximo por equipo (nunca por debajo del mínimo).
    r = cli.post("/anfitrion/campeonatos/guardar", json={"id": cid, "nombre": "Beata 2026", "deporte": "futbol", "formato": "liga",
                                                        "costo": 100, "minJugadoresEquipo": 7, "maxJugadoresEquipo": 5, "lat": -12.09, "lng": -77.0})
    assert r.status_code == 200, r.text
    c = fake.rows[cid]
    assert c["minJugadoresEquipo"] == 7 and c["maxJugadoresEquipo"] == 7
    r = cli.post("/anfitrion/campeonatos/guardar", json={"id": cid, "nombre": "Beata 2026", "deporte": "futbol", "formato": "liga",
                                                        "costo": 100, "minJugadoresEquipo": 7, "maxJugadoresEquipo": 10, "lat": -12.09, "lng": -77.0})
    c = fake.rows[cid]
    assert c["maxJugadoresEquipo"] == 10 and L.cuota_jugador_centimos(c) == 1000 and L.cupo_reparto(c) == 10
    # Los equipos que agrega el organizador nacen con CÓDIGO (enlace de equipo).
    ids = []
    for n in ("Kinder 01", "Kinder 02", "PreKinder"):
        r = cli.post(f"/anfitrion/campeonatos/{cid}/participante", json={"nombre": n}).json()
        ids.append(r["id"])
    eqs = fake.rows[cid]["participantes"]
    assert all(len(p["codigo"]) == 6 and L.es_equipo(p) for p in eqs)
    # Dos jugadores ponen su parte en Kinder 01; el capitán completa Kinder 02.
    for em in ("a@x.com", "b@x.com", "capi@x.com"):
        stores.acreditar(em, 10000)
    for em in ("a@x.com", "b@x.com"):
        r = _pz.aportar(email=em, campeonato_id=cid, equipo_id=ids[0], cuota_equipo_soles=100, cupo=10, moneda="PEN",
                        organizador="orga@gmail.com", campeonato_nombre="Beata 2026", equipo_nombre="Kinder 01", monto_soles=None,
                        comision_fn=lambda s, m: 500)
        assert r["ok"] and r["aporte_centimos"] == 1000
    r = _pz.aportar(email="capi@x.com", campeonato_id=cid, equipo_id=ids[1], cuota_equipo_soles=100, cupo=10, moneda="PEN",
                    organizador="orga@gmail.com", campeonato_nombre="Beata 2026", equipo_nombre="Kinder 02", monto_soles=100,
                    comision_fn=lambda s, m: 500)
    assert r["pozo"]["liquidado"] and stores.saldo_centimos("orga@gmail.com") == 9500
    # Detalle: chips con el pozo y CFG con pozos/cuota.
    r = cli.get(f"/anfitrion/campeonatos/{cid}")
    assert r.status_code == 200
    assert "Kinder 01 · 0/10 jug. · S/ 20 de 100" in r.text
    assert "Kinder 02 · 0/10 jug. · S/ 100 ✅ inscrito" in r.text
    assert "PreKinder · 0/10 jug. · S/ 0 de 100" in r.text
    assert '"cuotaJug": 1000' in r.text and '"cuotaEq": 10000' in r.text and '"cupo": 10' in r.text
    # Publicidad de WhatsApp: cuánto pone cada jugador.
    assert "Cada jugador pone S/ 10 al unirse a su equipo (hasta 10 por equipo)" in urllib.parse.unquote(
        re.search(r"data-wa-movil='(https://wa\.me/\?text=[^']+)'", r.text).group(1))
    # Generar fixture: pregunta por los pozos incompletos; excluirlos devuelve la plata.
    r = cli.post(f"/anfitrion/campeonatos/{cid}/fixture")
    assert r.status_code == 409 and {q["nombre"] for q in r.json()["equipos"]} == {"Kinder 01", "PreKinder"}
    r = cli.post(f"/anfitrion/campeonatos/{cid}/fixture", json={"excluir": [ids[0]]})
    assert r.status_code == 200 and r.json()["devueltos"] == 2, r.text
    assert stores.saldo_centimos("a@x.com") == 10000 and stores.saldo_centimos("b@x.com") == 10000
    assert {p["nombre"] for p in fake.rows[cid]["participantes"]} == {"Kinder 02", "PreKinder"}
    assert fake.rows[cid]["partidos"]
    # Quitar un equipo ya liquidado: no hay devolución automática, se avisa.
    r = cli.post(f"/anfitrion/campeonatos/{cid}/participante/{ids[1]}/eliminar").json()
    assert r["ok"] and "ya se te había liquidado" in r["aviso"]
    # Página pública: "por equipo · cada jugador pone".
    from marketing import campeonato_web
    monkeypatch.setattr(campeonato_web, "obtener_campeonato", lambda _id: dict(fake.rows[cid], partidos=[], inscripcionAbierta=True))
    r = cli.get(f"/c/{cid}")
    assert "S/ 100.00 por equipo · cada jugador pone S/ 10" in r.text
