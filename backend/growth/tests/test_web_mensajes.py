"""MENSAJES en la web = mensajería del APK (bandeja, chat, grupos, nuevo chat).
Base simulada en memoria con la MISMA semántica que las consultas reales."""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

import pytest
from fastapi.testclient import TestClient

import config
from main import app
from web import almacen, datos, sesion, ui
from web import jugador_mensajes as M

YO = "ana@gmail.com"
T0 = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)


class FakeChat:
    """Tablas `pichangol_mensajes`, `_lecturas`, `_chat_prefs`, `_grupos`,
    `_grupo_miembros`, `_agenda`, `_perfiles`, `_academias` en memoria."""

    def __init__(self):
        self.msgs: list[dict] = []
        self.lect: dict[tuple, dict] = {}
        self.prefs: dict[tuple, dict] = {}
        self.grupos: dict[str, dict] = {}
        self.miembros: dict[str, list[str]] = {}
        self.agendas: dict[str, dict] = {}
        self.perfiles = {
            "luis@x.com": {"nombre": "Luis Rojas", "foto_url": "https://f/luis.jpg", "celular": ""},
            "dueno@x.com": {"nombre": "Pedro Dueño", "foto_url": "", "celular": ""},
            "profe@x.com": {"nombre": "Profe Carla", "foto_url": "", "celular": ""},
            YO: {"nombre": "Ana Pérez", "foto_url": "https://f/ana.jpg", "celular": ""},
            "eva@x.com": {"nombre": "Eva Solís", "foto_url": "", "celular": ""},
        }
        self.academias = {"ac_1": {"nombre": "Academia Top Spin", "dueno": "profe@x.com", "logo": "https://f/logo.png"},
                          "ac_mia": {"nombre": "Mi Academia", "dueno": YO, "logo": ""}}
        self.locales = {"dueno@x.com": {"nombre": "Club Sabor Golazo", "foto": "https://f/cancha.jpg"}}
        self.canchas = {"c1": {"id": "c1", "dueno": "Dueno@X.com", "club": "Club Sabor Golazo", "nombre": "Fútbol 1"},
                        "c_mia": {"id": "c_mia", "dueno": YO, "club": "Mi local", "nombre": "F1"},
                        "c_sin": {"id": "c_sin", "dueno": "", "club": "Legado", "nombre": "F1"}}
        self.n = 0

    def add(self, hilo, autor, texto="hola", minutos=0, **kw):
        self.n += 1
        p = M.partir_hilo(hilo)
        fila = {"id": f"m{self.n}", "hilo": hilo, "tipo": p["tipo"], "ref_id": "", "academia_id": "", "cuenta_email": "",
                "autor_email": autor, "autor_nombre": (self.perfiles.get(autor) or {}).get("nombre", ""), "es_profe": False,
                "texto": texto, "media_url": "", "resp_texto": "", "resp_autor": "", "resp_media": "", "reenviado": False,
                "creado": T0 + timedelta(minutes=minutos)}
        if p["tipo"] == "cancha":
            fila.update(ref_id=p["dueno"], cuenta_email=p["jugador"], es_profe=autor == p["dueno"])
        elif p["tipo"] == "academia":
            fila.update(ref_id=p["academia"], academia_id=p["academia"], cuenta_email=p["cuenta"])
        elif p["tipo"] == "grupo":
            fila.update(ref_id=p["grupo"])
        else:
            fila.update(cuenta_email=p["b"] if autor == p["a"] else p["a"])
        fila.update(kw)
        self.msgs.append(fila)
        return fila

    # ── espejo de las consultas ──
    def resumen_hilos(self, email, acs, gids):
        e = email.lower()
        mis = [m for m in self.msgs if
               (m["tipo"] == "academia" and (m["academia_id"] in acs or m["cuenta_email"] == e))
               or (m["tipo"] == "cancha" and (m["ref_id"] == e or m["cuenta_email"] == e))
               or (m["tipo"] == "grupo" and m["ref_id"] in gids)
               or (m["tipo"] == "directo" and (m["autor_email"] == e or m["cuenta_email"] == e))]
        out = {}
        for m in sorted(mis, key=lambda x: x["creado"]):
            leido = (self.lect.get((m["hilo"], e)) or {}).get("l")
            r = out.setdefault(m["hilo"], {"n": 0, "nom": ""})
            r.update(ult=m)
            if m["autor_email"].lower() != e:
                if leido is None or m["creado"] > leido:
                    r["n"] += 1
                if m["autor_nombre"]:
                    r["nom"] = m["autor_nombre"]
        return [{"hilo": h, "tipo": r["ult"]["tipo"], "ref_id": r["ult"]["ref_id"], "academia_id": r["ult"]["academia_id"],
                 "cuenta_email": r["ult"]["cuenta_email"], "autor_email": r["ult"]["autor_email"],
                 "autor_nombre": r["ult"]["autor_nombre"], "texto": r["ult"]["texto"], "media_url": r["ult"]["media_url"],
                 "creado": r["ult"]["creado"], "no_leidos": r["n"], "otro_nombre": r["nom"]} for h, r in out.items()]

    def mensajes_de(self, hilos, antes=None, desde=None, limite=50):
        mm = sorted([m for m in self.msgs if m["hilo"] in hilos], key=lambda x: x["creado"])
        if desde is not None:
            return [m for m in mm if m["creado"] >= desde][:200]
        if antes is not None:
            mm = [m for m in mm if m["creado"] < antes]
        return mm[-limite:]

    def insertar(self, fila):
        f = dict(fila)
        f["creado"] = T0 + timedelta(hours=5, seconds=len(self.msgs))
        for c in ("resp_texto", "resp_autor", "resp_media", "media_url", "academia_id"):
            f.setdefault(c, "")
        f.setdefault("reenviado", False)
        self.msgs.append(f)
        return f

    def marcar_leido(self, hilos, email):
        for h in hilos:
            self.lect[(h, email.lower())] = {"e": T0 + timedelta(days=1), "l": T0 + timedelta(days=1)}

    def instalar(self, mp):
        mp.setattr(M, "academias_de_dueno", lambda e: [a for a, v in self.academias.items() if v["dueno"] == e.lower()])
        mp.setattr(M, "academias_info", lambda ids: {i: self.academias[i] for i in ids if i in self.academias})
        mp.setattr(M, "nombres_alumnos", lambda pares: {})
        mp.setattr(M, "locales_de", lambda ds: {d: self.locales[d] for d in ds if d in self.locales})
        mp.setattr(M, "grupos_de", lambda e: [dict(g, miembros=list(self.miembros[g["id"]])) for g in self.grupos.values()
                                               if e.lower() in self.miembros.get(g["id"], [])])
        mp.setattr(M, "grupo", lambda gid: dict(self.grupos[gid], miembros=list(self.miembros[gid])) if gid in self.grupos else None)
        mp.setattr(M, "es_miembro", lambda gid, e: e.lower() in self.miembros.get(gid, []))

        def crear(gid, nombre, creador, miembros):
            self.grupos[gid] = {"id": gid, "nombre": nombre, "creador": creador, "foto": "", "creado": T0}
            self.miembros[gid] = [m for m, _ in miembros]
            return True
        mp.setattr(M, "crear_grupo", crear)
        mp.setattr(M, "agregar_miembro", lambda gid, e, n: self.miembros[gid].append(e) or True)
        mp.setattr(M, "salir_grupo", lambda gid, e: self.miembros[gid].remove(e.lower()) or True)
        mp.setattr(M, "actualizar_grupo", lambda gid, nombre=None, foto=None: self.grupos[gid].update(
            {k: v for k, v in (("nombre", nombre), ("foto", foto)) if v}) or True)
        mp.setattr(M, "resumen_hilos", self.resumen_hilos)
        mp.setattr(M, "prefs_de", lambda e: {h: dict(p) for (em, h), p in self.prefs.items() if em == e.lower()})

        def guardar(e, filas):
            for h, p in filas.items():
                self.prefs[(e.lower(), h)] = dict(p)
            return True
        mp.setattr(M, "guardar_prefs", guardar)
        mp.setattr(M, "agenda_de", lambda e: self.agendas.get(e.lower(), {"apodos": {}, "contactos": [], "bloqueados": []}))
        mp.setattr(M, "mensajes_de", self.mensajes_de)
        mp.setattr(M, "mensaje", lambda i: next((m for m in self.msgs if m["id"] == i), None))
        mp.setattr(M, "insertar_mensaje", self.insertar)
        mp.setattr(M, "marcar_leido", self.marcar_leido)
        mp.setattr(M, "marcar_entregados", lambda hilos, e: None)
        mp.setattr(M, "lecturas_ajenas", lambda hilos, e: {})
        mp.setattr(M, "buscar_perfiles", lambda q, yo: [{"email": k, "nombre": v["nombre"], "foto": v["foto_url"]}
                                                        for k, v in self.perfiles.items() if q.lower() in v["nombre"].lower() and k != yo])
        mp.setattr(M, "perfiles", lambda ems: {e.lower(): self.perfiles[e.lower()] for e in ems if e and e.lower() in self.perfiles})
        mp.setattr(datos, "cancha", lambda i: self.canchas.get(i))
        mp.setattr(datos, "academia", lambda i: dict(self.academias[i], id=i) if i in self.academias else None)


@pytest.fixture
def fk(monkeypatch):
    f = FakeChat()
    f.instalar(monkeypatch)
    return f


def _cli(monkeypatch, email=YO):
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    cli = TestClient(app, base_url="https://testserver")
    cli.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Ana Pérez", "foto": ""}))
    return cli


def test_hilos_iguales_al_app():
    # `Mensaje.hiloDirecto`: simétrico y en minúsculas; `hiloCancha` en minúsculas.
    assert M.hilo_directo("Luis@X.com", "ana@gmail.com") == M.hilo_directo("ana@gmail.com", "luis@x.com") == "directo_ana@gmail.com|luis@x.com"
    assert M.hilo_cancha("Dueno@X.com", "Ana@Gmail.com") == "cancha_dueno@x.com|ana@gmail.com"
    assert M.hilo_academia("ac_1", "Ana@gmail.com") == "ac_1|ana@gmail.com"
    assert M.partir_hilo("ac_1|ana@gmail.com") == {"tipo": "academia", "academia": "ac_1", "cuenta": "ana@gmail.com"}
    assert M.partir_hilo("grupo_grp_1") == {"tipo": "grupo", "grupo": "grp_1"}
    # Carpeta de la foto = `MensajesRepo.subirFoto`.
    assert M._carpeta_hilo("cancha_dueno@x.com|ana@gmail.com") == "cancha_dueno_x_com_ana_gmail_com"
    # Tipos de adjunto = getters de `Mensaje`.
    assert M.clase_media("https://s/chat/a/1.jpg") == "foto" and M.clase_media("https://s/a.m4a") == "audio"
    assert M.clase_media("https://media.giphy.com/x/giphy.gif") == "gif" and M.clase_media("https://s/doc.pdf") == "doc"
    assert M.clase_media("geo:-12.1,-77.0") == "geo" and M.clase_media("geolive:123") == "geolive"
    assert M.preview("", "https://s/1.jpg") == "📷 Foto" and M.snippet("", "https://s/a.m4a") == "🎤 Nota de voz"
    # Clave opaca, estable y a prueba de manipulación.
    k = M.clave_de(["directo_a@x.com|b@x.com"])
    assert k == M.clave_de(["directo_a@x.com|b@x.com"]) and "@" not in k
    assert M.hilos_de_clave(k) == ["directo_a@x.com|b@x.com"]
    assert M.hilos_de_clave(k[:-3] + ("AAA" if k[-3:] != "AAA" else "BBB")) == []


def test_bandeja_una_persona_un_chat_y_no_leidos(monkeypatch, fk):
    # Sin sesión → a iniciar sesión y volver.
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    r = TestClient(app, base_url="https://testserver").get("/mensajes", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fmensajes"

    hc, hd = M.hilo_cancha("dueno@x.com", YO), M.hilo_directo(YO, "dueno@x.com")
    fk.add(hc, YO, "¿Tienen turno el sábado?", 0)
    fk.add(hc, "dueno@x.com", "Sí, a las 7", 5)
    fk.add(hd, "dueno@x.com", "Te escribo por aquí también", 10)       # misma persona → misma fila
    fk.add("ac_1|" + YO, "profe@x.com", "Bienvenida a la academia", 2)
    fk.add("ac_1|otro@x.com", "profe@x.com", "privado de otro alumno", 3)  # hilo AJENO: nunca sale
    fk.add("ac_mia|eva@x.com", "eva@x.com", "Profe, ¿hay clase?", 1)     # soy la profe
    fk.grupos["grp_1"] = {"id": "grp_1", "nombre": "Pichanga jueves", "creador": "luis@x.com", "foto": "", "creado": T0}
    fk.miembros["grp_1"] = ["luis@x.com", YO]                           # grupo sin mensajes también sale
    b = M.bandeja(YO)
    titulos = [f["titulo"] for f in b["filas"]]
    assert "Club Sabor Golazo" in titulos and "Academia Top Spin" in titulos and "Eva Solís" in titulos and "Pichanga jueves" in titulos
    assert all("privado" not in f["preview"] for f in b["filas"])
    club = next(f for f in b["filas"] if f["titulo"] == "Club Sabor Golazo")
    # Fundida: título = el LOCAL (soy el cliente), principal = el hilo más reciente, no leídos sumados.
    assert club["hilos"][0] == hd and set(club["hilos"]) == {hc, hd} and club["no_leidos"] == 2
    assert club["preview"] == "Te escribo por aquí también" and club["foto"] == "https://f/cancha.jpg"
    grp = next(f for f in b["filas"] if f["tipo"] == "grupo")
    assert grp["preview"] == "2 miembros · toca para escribir"

    # Leer: tras abrir, 0 no leídos.
    fk.marcar_leido([hc, hd], YO)
    assert next(f for f in M.bandeja(YO)["filas"] if f["titulo"] == "Club Sabor Golazo")["no_leidos"] == 0

    # La página pinta todo del servidor (sin spinner) y sin correos ajenos en el HTML.
    html = _cli(monkeypatch).get("/mensajes").text
    assert "Club Sabor Golazo" in html and "Pichanga jueves" in html and "dueno@x.com" not in html and "otro@x.com" not in html
    import inspect, re
    fuente = inspect.getsource(M)
    assert not re.search(r"(?<![A-Za-z])(confirm|alert|prompt)\(", fuente)  # solo pcgConfirmar/pcgAvisar


def test_eliminar_reaparece_con_mensaje_nuevo_y_acciones_en_la_nube(monkeypatch, fk):
    hc, hd = M.hilo_cancha("dueno@x.com", YO), M.hilo_directo(YO, "dueno@x.com")
    fk.add(hc, "dueno@x.com", "hola", 0)
    fk.add(hd, "dueno@x.com", "hola 2", 1)
    cli = _cli(monkeypatch)
    k = M.fila_json(M.bandeja(YO)["filas"][0])["k"]
    # Archivar también desfija; aplica a TODOS los hilos de la fila.
    assert cli.post("/web/mensajes/accion", json={"k": k, "accion": "fijar"}).json()["ok"]
    assert all(fk.prefs[(YO, h)]["fijado"] for h in (hc, hd))
    cli.post("/web/mensajes/accion", json={"k": k, "accion": "archivar"})
    assert all(fk.prefs[(YO, h)]["archivado"] and not fk.prefs[(YO, h)]["fijado"] for h in (hc, hd))
    b = M.bandeja(YO)
    assert not b["filas"] and len(b["archivadas"]) == 1
    cli.post("/web/mensajes/accion", json={"k": k, "accion": "desarchivar"})
    cli.post("/web/mensajes/accion", json={"k": k, "accion": "silenciar"})
    assert M.bandeja(YO)["filas"][0]["silenciado"]
    # Eliminar: oculto desde ahora en la nube (sin borrar nada para el otro).
    cli.post("/web/mensajes/accion", json={"k": k, "accion": "eliminar"})
    assert all(fk.prefs[(YO, h)]["oculto_en"] for h in (hc, hd)) and M.bandeja(YO)["filas"] == []
    assert len(fk.msgs) == 2
    # Llega algo más nuevo → reaparece SOLO ese hilo y la nube se limpia (como `chatOculto`).
    fk.add(hc, "dueno@x.com", "¿Sigues interesada?", 60 * 24 * 30)
    filas = M.bandeja(YO)["filas"]
    assert len(filas) == 1 and filas[0]["hilos"] == [hc] and filas[0]["preview"] == "¿Sigues interesada?"
    assert fk.prefs[(YO, hc)]["oculto_en"] is None and fk.prefs[(YO, hd)]["oculto_en"] is not None
    # Acción inválida o clave ajena.
    assert cli.post("/web/mensajes/accion", json={"k": k, "accion": "borrar_todo"}).status_code == 400
    ajena = M.clave_de([M.hilo_directo("luis@x.com", "eva@x.com")])
    assert cli.post("/web/mensajes/accion", json={"k": ajena, "accion": "fijar"}).status_code == 403


def test_chat_historial_enviar_y_citar_como_el_app(monkeypatch, fk):
    hc, hd = M.hilo_cancha("dueno@x.com", YO), M.hilo_directo(YO, "dueno@x.com")
    fk.add(hc, YO, "¿Tienen turno?", 0)
    otro = fk.add(hd, "dueno@x.com", "Sí, a las 7", 5)
    ajeno = fk.add(M.hilo_directo("luis@x.com", "eva@x.com"), "luis@x.com", "secreto", 6)
    cli = _cli(monkeypatch)
    k = M.clave_de([hd, hc])
    html = cli.get(f"/mensajes/{quote(k, safe='')}").text
    # Historial de los DOS hilos, "mío" por correo, sin correos en el HTML.
    assert "¿Tienen turno?" in html and "Sí, a las 7" in html and "secreto" not in html
    assert '"mio": true' in html and '"mio": false' in html and "dueno@x.com" not in html
    assert "Club Sabor Golazo" in html and "mjLlamadas()" in html  # llamadas: solo en la app
    assert (hc, YO) in fk.lect and (hd, YO) in fk.lect             # marcó leído
    # Enviar: al hilo PRINCIPAL con la fila del app (directo → cuenta_email = el otro).
    r = cli.post("/web/mensajes/enviar", json={"k": k, "texto": "  Perfecto, voy  ", "resp": otro["id"]}).json()
    assert r["ok"] and r["mensaje"]["mio"] and r["mensaje"]["texto"] == "Perfecto, voy"
    nuevo = fk.msgs[-1]
    assert nuevo["hilo"] == hd and nuevo["tipo"] == "directo" and nuevo["cuenta_email"] == "dueno@x.com"
    assert nuevo["autor_email"] == YO and nuevo["autor_nombre"] == "Ana Pérez" and nuevo["es_profe"] is False
    assert nuevo["id"].startswith("msg_") and nuevo["resp_texto"] == "Sí, a las 7" and nuevo["resp_autor"] == "Pedro Dueño"
    # Citar un mensaje de OTRA conversación no se permite (se ignora la cita).
    cli.post("/web/mensajes/enviar", json={"k": k, "texto": "hola", "resp": ajeno["id"]})
    assert fk.msgs[-1]["resp_texto"] == ""
    # Cancha como jugador: ref_id = dueño, cuenta_email = yo, es_profe false.
    kc = M.clave_de([hc])
    cli.post("/web/mensajes/enviar", json={"k": kc, "texto": "Gracias"})
    f = fk.msgs[-1]
    assert (f["hilo"], f["tipo"], f["ref_id"], f["cuenta_email"], f["es_profe"]) == (hc, "cancha", "dueno@x.com", YO, False)
    # Academia como PROFE: es_profe true + academia_id.
    fk.add("ac_mia|eva@x.com", "eva@x.com", "Profe?", 1)
    cli.post("/web/mensajes/enviar", json={"k": M.clave_de(["ac_mia|eva@x.com"]), "texto": "Sí hay clase"})
    f = fk.msgs[-1]
    assert (f["tipo"], f["academia_id"], f["ref_id"], f["cuenta_email"], f["es_profe"]) == ("academia", "ac_mia", "ac_mia", "eva@x.com", True)
    # Vacío, muy largo, clave ajena o manipulada.
    assert cli.post("/web/mensajes/enviar", json={"k": k, "texto": "   "}).status_code == 400
    assert cli.post("/web/mensajes/enviar", json={"k": k, "texto": "x" * 4001}).status_code == 400
    ajena = M.clave_de([M.hilo_directo("luis@x.com", "eva@x.com")])
    assert cli.post("/web/mensajes/enviar", json={"k": ajena, "texto": "hola"}).status_code == 403
    assert "Chat no disponible" in cli.get(f"/mensajes/{quote(ajena, safe='')}").text
    assert cli.post("/web/mensajes/enviar", json={"k": "basura", "texto": "hola"}).status_code == 403
    # Hilo de academia de OTRO alumno: ni siquiera el correo en la clave da acceso.
    assert cli.post("/web/mensajes/enviar", json={"k": M.clave_de(["ac_1|otro@x.com"]), "texto": "x"}).status_code == 403
    # Contacto bloqueado en MI agenda → no se le escribe.
    fk.agendas[YO] = {"apodos": {}, "contactos": [], "bloqueados": ["dueno@x.com"]}
    r = cli.post("/web/mensajes/enviar", json={"k": k, "texto": "hola"})
    assert r.status_code == 403 and r.json()["error"] == "bloqueado"
    assert "Bloqueaste a este contacto" in cli.get(f"/mensajes/{quote(k, safe='')}").text


def test_sondeo_trae_solo_lo_nuevo(monkeypatch, fk):
    hd = M.hilo_directo(YO, "luis@x.com")
    for i in range(60):
        fk.add(hd, "luis@x.com" if i % 2 else YO, f"m{i}", i)
    cli = _cli(monkeypatch)
    k = M.clave_de([hd])
    j = cli.get("/web/mensajes/hilo", params={"k": k}).json()
    assert j["ok"] and len(j["mensajes"]) == 50 and j["mensajes"][-1]["texto"] == "m59"
    assert "luis@x.com" not in str(j) and j["mensajes"][0]["h"] == "h0"
    # Anteriores a la ventana.
    j2 = cli.get("/web/mensajes/hilo", params={"k": k, "antes": j["mensajes"][0]["t"]}).json()
    assert [m["texto"] for m in j2["mensajes"]] == [f"m{i}" for i in range(10)]
    # Solo lo posterior al cursor (incluye el último, el navegador deduplica por id).
    fk.add(hd, "luis@x.com", "nuevo!", 200)
    j3 = cli.get("/web/mensajes/hilo", params={"k": k, "desde": j["mensajes"][-1]["t"], "leer": 1}).json()
    assert [m["texto"] for m in j3["mensajes"]] == ["m59", "nuevo!"] and (hd, YO) in fk.lect


def test_enviar_foto_al_bucket_chat_como_el_app(monkeypatch, fk):
    hd = M.hilo_directo(YO, "luis@x.com")
    subidas = []
    monkeypatch.setattr(almacen, "disponible", lambda: True)
    monkeypatch.setattr(almacen, "subir", lambda b, ruta, d, ct, max_bytes=None: subidas.append((b, ruta, ct)) or f"https://s/{b}/{ruta}?x=1")
    cli = _cli(monkeypatch)
    k = M.clave_de([hd])
    r = cli.post(f"/web/mensajes/foto?k={quote(k, safe='')}", content=b"\xff\xd8\xff" + b"0" * 100,
                 headers={"Content-Type": "image/jpeg"}).json()
    assert r["ok"] and r["mensaje"]["c"] == "foto"
    b, ruta, ct = subidas[0]
    assert b == "chat" and ruta.startswith("directo_ana_gmail_com_luis_x_com/") and ruta.endswith(".jpg") and ct == "image/jpeg"
    assert fk.msgs[-1]["texto"] == "📷 Foto" and fk.msgs[-1]["media_url"] == f"https://s/chat/{ruta}"
    assert cli.post(f"/web/mensajes/foto?k={quote(k, safe='')}", content=b"no es foto").status_code == 400


def test_nuevo_chat_con_cancha_academia_y_persona(monkeypatch, fk):
    cli = _cli(monkeypatch)
    # Desde la ficha de la cancha: hilo cancha_<dueño>|<yo> en minúsculas.
    r = cli.get("/mensajes/nuevo?cancha=c1", follow_redirects=False)
    assert r.status_code == 303
    k = unquote(r.headers["location"].split("/mensajes/")[1])
    assert M.hilos_de_clave(k) == ["cancha_dueno@x.com|ana@gmail.com"]
    # Si ya había chat directo con ese dueño, el historial viene con la conversación (principal = cancha).
    fk.add(M.hilo_directo(YO, "dueno@x.com"), "dueno@x.com", "hola", 0)
    k = unquote(cli.get("/mensajes/nuevo?cancha=c1", follow_redirects=False).headers["location"].split("/mensajes/")[1])
    assert M.hilos_de_clave(k) == ["cancha_dueno@x.com|ana@gmail.com", "directo_ana@gmail.com|dueno@x.com"]
    # Mi propia cancha / sin dueño.
    assert "Es tu cancha" in cli.get("/mensajes/nuevo?cancha=c_mia").text
    assert "Aún sin dueño" in cli.get("/mensajes/nuevo?cancha=c_sin").text
    # Academia: `<id>|<yo>`.
    k = unquote(cli.get("/mensajes/nuevo?academia=ac_1", follow_redirects=False).headers["location"].split("/mensajes/")[1])
    assert M.hilos_de_clave(k) == ["ac_1|ana@gmail.com"]
    assert "Es tu academia" in cli.get("/mensajes/nuevo?academia=ac_mia").text
    # Buscador → persona (ref opaco) → directo con correos ordenados.
    j = cli.get("/web/mensajes/buscar", params={"q": "eva"}).json()
    assert j["jugadores"][0]["nombre"] == "Eva Solís" and "eva@x.com" not in str(j)
    k = unquote(cli.get("/mensajes/nuevo", params={"persona": j["jugadores"][0]["ref"]}, follow_redirects=False)
                .headers["location"].split("/mensajes/")[1])
    assert M.hilos_de_clave(k) == ["directo_ana@gmail.com|eva@x.com"]
    # Sin sesión → login y volver a la misma ficha.
    r = TestClient(app, base_url="https://testserver").get("/mensajes/nuevo?cancha=c1", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/entrar?volver=%2Fmensajes%2Fnuevo%3Fcancha%3Dc1"


def test_grupos_crear_info_anadir_y_salir(monkeypatch, fk):
    cli = _cli(monkeypatch)
    refs = [p["ref"] for p in cli.get("/web/mensajes/buscar", params={"q": "s"}).json()["jugadores"]]  # Luis Rojas, Eva Solís
    assert cli.post("/web/mensajes/grupos", json={"nombre": "", "miembros": refs}).status_code == 400
    assert cli.post("/web/mensajes/grupos", json={"nombre": "Pichanga", "miembros": []}).status_code == 400
    r = cli.post("/web/mensajes/grupos", json={"nombre": "Pichanga jueves", "miembros": refs + refs}).json()
    assert r["ok"]
    gid = next(iter(fk.grupos))
    assert gid.startswith("grp_") and fk.grupos[gid]["creador"] == YO
    assert sorted(fk.miembros[gid]) == sorted([YO, "luis@x.com", "eva@x.com"])
    k = unquote(r["url"].split("/mensajes/")[1])
    assert M.hilos_de_clave(k) == [f"grupo_{gid}"]
    # Mensaje de grupo: tipo grupo, ref_id = id, sin cuenta.
    cli.post("/web/mensajes/enviar", json={"k": k, "texto": "¿Quién va?"})
    f = fk.msgs[-1]
    assert (f["hilo"], f["tipo"], f["ref_id"], f["cuenta_email"]) == (f"grupo_{gid}", "grupo", gid, "")
    assert "Tú: ¿Quién va?" in [x["preview"] for x in M.bandeja(YO)["filas"]]
    # Info: renombrar y añadir integrante.
    html = cli.get(f"/mensajes/grupo/{gid}").text
    assert "3 integrantes" in html and "Creador del grupo" in html
    assert cli.post(f"/web/mensajes/grupos/{gid}/nombre", json={"nombre": "Jueves 8pm"}).json()["ok"]
    assert fk.grupos[gid]["nombre"] == "Jueves 8pm"
    fk.perfiles["zoe@x.com"] = {"nombre": "Zoe", "foto_url": "", "celular": ""}
    ref = cli.get("/web/mensajes/buscar", params={"q": "zoe"}).json()["jugadores"][0]["ref"]
    assert cli.post(f"/web/mensajes/grupos/{gid}/miembros", json={"ref": ref}).json()["ok"]
    assert "zoe@x.com" in fk.miembros[gid]
    # Salir: ya no ve el grupo ni puede escribir.
    assert cli.post(f"/web/mensajes/grupos/{gid}/salir").json()["ok"]
    assert YO not in fk.miembros[gid]
    assert cli.post("/web/mensajes/enviar", json={"k": k, "texto": "hola"}).status_code == 403
    assert "Grupo no disponible" in cli.get(f"/mensajes/grupo/{gid}").text
    assert cli.post(f"/web/mensajes/grupos/{gid}/nombre", json={"nombre": "x"}).status_code == 404


def test_badge_de_no_leidos(monkeypatch, fk):
    fk.add(M.hilo_directo(YO, "luis@x.com"), "luis@x.com", "hola", 0)
    fk.add(M.hilo_directo(YO, "eva@x.com"), "eva@x.com", "hola", 1)
    assert _cli(monkeypatch).get("/web/mensajes/no-leidos").json() == {"ok": True, "n": 2}
    assert TestClient(app, base_url="https://testserver").get("/web/mensajes/no-leidos").json()["n"] == 0


def test_chat_web_pantalla_completa_en_movil_como_whatsapp(monkeypatch, fk):
    """Queja del director (1-oct-2026, celular): la cabecera pegajosa del sitio tapaba el chat
    y el pie quedaba debajo del compositor. El chat va con shell(pantalla="chat"): sin pie, y en
    móvil sin cabecera del sitio (la conversación ocupa 100dvh con su cabecera ‹ + contacto)."""
    hc = M.hilo_cancha("dueno@x.com", YO)
    fk.add(hc, YO, "¿Tienen turno?", 0)
    cli = _cli(monkeypatch)
    html = cli.get(f"/mensajes/{quote(M.clave_de([hc]), safe='')}").text
    assert "class='pcg-chat'" in html and "interactive-widget=resizes-content" in html
    assert "<footer class='pie'>" not in html                       # sin pie del sitio
    assert "class='vol' href='/mensajes'" in html and "Club Sabor Golazo" in html  # ‹ + contacto
    assert "--mj-vh" in html and "visualViewport" in html            # el teclado no tapa el compositor
    assert "body.pcg-chat header.nav" in html                        # cabecera del sitio fuera en móvil
    # Bandeja / nuevo: cabecera en una fila sin la pastilla en móvil; el pie se queda.
    for ruta in ("/mensajes", "/mensajes/nuevo"):
        h = cli.get(ruta).text
        assert "class='pcg-msj'" in h and "<footer class='pie'>" in h
    # El resto de la web no cambia.
    assert "<body>" in ui.shell("x", "y").body.decode()
