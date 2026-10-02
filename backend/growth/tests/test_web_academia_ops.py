"""Operación de la academia en la web (lado DUEÑO): asistencia,
evaluación, ranking, reportes, chats y sedes, espejo de `mi_academia_screen`,
`asistencia_screen`, `evaluar_alumno_screen`, `ranking_academia_screen`,
`reporte_academia_screen`, `chats_academia_screen` y la sección de sedes de
`crear_academia_screen`."""
import copy

import pytest
from fastapi.testclient import TestClient

import config
from main import app
from web import anfitrion_academia_ops as ops
from web import sesion

DUENO = "profe@gmail.com"
ACAD = {"id": "ac_1", "nombre": "Academia Raqueta", "deporte": "tenis", "dueno": DUENO, "lat": -12.1, "lng": -77.0,
        "moneda": "S/", "recargoInvitado": 50, "descuentoHermano2": 10, "descuentoHermano3": 20, "descuentoPrepago": 5,
        "planes": [{"id": "Bola Roja | 2x", "nombre": "Bola Roja · 2x/sem", "tipo": "mensual", "precioMes": 200, "meses": 1, "programa": "Bola Roja"},
                   {"id": "pk", "nombre": "Paquete trimestral", "tipo": "prepago", "precioMes": 180, "meses": 3},
                   {"id": "suelta", "nombre": "Clase particular", "tipo": "porClase", "precioMes": 60, "meses": 1}],
        "sedes": [], "horarios": {}, "preciosSede": {}, "partidos": [], "categorias": {}}
MATS = [
    {"id": "al_1", "academiaId": "ac_1", "nombre": "Lucía", "email": "mama@gmail.com", "apoderadoNombre": "Rosa",
     "apoderadoWhatsapp": "987654321", "edad": 8, "esSocioSede": True, "ordenHermano": 1,
     "cuotas": [{"id": "cu_a", "academiaId": "ac_1", "alumnoId": "al_1", "concepto": "Bola Roja · 2x/sem · Enero 2026", "monto": 200,
                 "vencimiento": "2026-01-05T10:00:00.000", "pagada": False},
                {"id": "cu_b", "academiaId": "ac_1", "alumnoId": "al_1", "concepto": "Bola Roja · 2x/sem · Diciembre 2025", "monto": 200,
                 "vencimiento": "2025-12-05T10:00:00.000", "pagada": True, "fechaPago": "2025-12-05T10:00:00.000", "operacionId": "chr_1"}]},
    {"id": "al_2", "academiaId": "ac_1", "nombre": "Pedro", "email": "", "whatsapp": "912345678", "esSocioSede": False, "ordenHermano": 2,
     "cuotas": []},
]


@pytest.fixture
def mundo(monkeypatch):
    st = {"acad": copy.deepcopy(ACAD), "mats": copy.deepcopy(MATS), "pushes": [], "asis": {}, "evals": {}, "notas": [], "msgs": [],
          "planes": []}
    monkeypatch.setattr(ops, "planes_de", lambda aid: [p for p in (ops._plan_normal(copy.deepcopy(d), aid) for d in st["planes"]) if p]
                        if aid == "ac_1" else [])
    monkeypatch.setattr(config, "GOOGLE_WEB_CLIENT_ID", "cid-web")
    monkeypatch.setattr(ops, "academias_de", lambda email: [copy.deepcopy(st["acad"])] if email.lower() == DUENO else [])
    monkeypatch.setattr(ops, "matriculas_de", lambda aid: copy.deepcopy(st["mats"]) if aid == "ac_1" else [])

    def mutar_matricula(alumno_id, dueno, fn):
        if dueno.lower() != DUENO:
            return None
        for i, m in enumerate(st["mats"]):
            if m["id"] == alumno_id:
                data = copy.deepcopy(m)
                res = fn(data)
                if res is not None:
                    st["mats"][i] = data
                return res
        return None

    def mutar_academia(aid, dueno, fn):
        if dueno.lower() != DUENO or aid != "ac_1":
            return None
        data = copy.deepcopy(st["acad"])
        res = fn(data)
        if res is not None:
            st["acad"] = data
        return res

    monkeypatch.setattr(ops, "mutar_matricula", mutar_matricula)
    monkeypatch.setattr(ops, "mutar_academia", mutar_academia)
    monkeypatch.setattr(ops, "tabla_existe", lambda n: True)
    monkeypatch.setattr(ops, "asistencias_de", lambda aid, dia: {k[0]: v for k, v in st["asis"].items() if k[1] == dia})
    monkeypatch.setattr(ops, "clases_asistidas", lambda aid: {})

    def guardar_asistencia(aid, ids, dia, presente):
        for x in ids:
            st["asis"].setdefault((x, dia), {"presente": presente, "avisado": False})["presente"] = presente
        return True

    def marcar_avisados(aid, ids, dia):
        for x in ids:
            st["asis"].setdefault((x, dia), {"presente": False, "avisado": False})["avisado"] = True

    monkeypatch.setattr(ops, "guardar_asistencia", guardar_asistencia)
    monkeypatch.setattr(ops, "marcar_avisados", marcar_avisados)
    monkeypatch.setattr(ops, "evaluaciones_de", lambda aid, pid: {(k[0], k[2]): v for k, v in st["evals"].items() if k[1] == pid})
    monkeypatch.setattr(ops, "guardar_evaluacion", lambda aid, al, pid, h, n: st["evals"].__setitem__((al, pid, h), n) or True)
    monkeypatch.setattr(ops, "notas_de", lambda aid, al: [n for n in st["notas"] if n["alumnoId"] == al])
    monkeypatch.setattr(ops, "guardar_nota", lambda aid, n: st["notas"].append(n) or True)
    monkeypatch.setattr(ops, "mensajes_de_academia", lambda aid: list(st["msgs"]))

    def enviar_mensaje(aid, cuenta, autor, nombre, texto, sufijo=""):
        st["msgs"].append({"id": f"m{len(st['msgs'])}", "hilo": f"{aid}|{cuenta}", "cuenta": cuenta, "autor": autor,
                           "autorNombre": nombre, "esProfe": True, "texto": texto, "media": "", "creado": None})
        return True

    monkeypatch.setattr(ops, "enviar_mensaje", enviar_mensaje)
    return st


def _cli(email=DUENO):
    c = TestClient(app, base_url="https://testserver")
    c.cookies.set(sesion.COOKIE, sesion.emitir({"email": email, "nombre": "Profe Juan"}))
    return c


def test_sin_sesion_va_a_entrar_y_ajeno_no_toca_nada(mundo):
    r = TestClient(app, base_url="https://testserver").get("/anfitrion/academia/asistencia?academia=ac_1", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/entrar?volver=%2Fanfitrion%2Facademia%2Fasistencia")
    # Un correo que no es dueño: sin academia → a Mi academia; el JSON responde 404 y no escribe.
    assert _cli("otro@x.com").get("/anfitrion/academia/ranking", follow_redirects=False).headers["location"] == "/anfitrion/academia"
    r = _cli("otro@x.com").post("/anfitrion/academia/ranking/categoria", json={"academia_id": "ac_1", "alumno_id": "al_2", "categoria": "4ta"})
    assert r.status_code == 404 and mundo["acad"]["categorias"] == {}
    assert TestClient(app).post("/anfitrion/academia/ranking/partido", json={}).status_code == 401
    # Cobros NO se duplican aquí: la pestaña lleva al módulo de cobros existente.
    html = _cli().get("/anfitrion/academia/asistencia?academia=ac_1").text
    assert "href='/anfitrion/cobros?academia=ac_1'" in html
    for js in (ops._JS_BASE, ops._JS_ASIS, ops._JS_EVAL, ops._JS_RANK, ops._JS_CHAT, ops._JS_SEDES):
        assert " confirm(" not in js and "alert(" not in js and "prompt(" not in js


def test_asistencia_marca_y_avisa_por_app_y_whatsapp(mundo):
    html = _cli().get("/anfitrion/academia/asistencia?academia=ac_1&dia=2026-03-02").text
    assert "Todos presentes" in html and "Avisar a los padres" in html and "Lun 2 mar 2026" in html
    assert _cli().post("/anfitrion/academia/asistencia/marcar", json={"academia_id": "ac_1", "dia": "2026-03-02", "alumno_ids": ["al_1"], "presente": True}).json()["ok"]
    # Un alumno ajeno no se marca.
    assert _cli().post("/anfitrion/academia/asistencia/marcar", json={"academia_id": "ac_1", "dia": "2026-03-02", "alumno_ids": ["al_x"], "presente": True}).status_code == 400
    j = _cli().post("/anfitrion/academia/asistencia/avisar", json={"academia_id": "ac_1", "dia": "2026-03-02"}).json()
    assert j["ok"] and j["enviados"] == 1
    assert mundo["msgs"][0]["hilo"] == "ac_1|mama@gmail.com" and mundo["msgs"][0]["texto"] == "✅ Lucía asistió hoy a Academia Raqueta."
    assert j["whatsapp"][0]["nombre"] == "Pedro" and "wa.me/51912345678" in j["whatsapp"][0]["url"]
    # Reenviar no duplica a quien ya se avisó.
    j2 = _cli().post("/anfitrion/academia/asistencia/avisar", json={"academia_id": "ac_1", "dia": "2026-03-02"}).json()
    assert j2["enviados"] == 0 and len(mundo["msgs"]) == 1


def test_evaluacion_rubrica_y_bitacora_con_la_plantilla_del_deporte(mundo):
    html = _cli().get("/anfitrion/academia/evaluaciones?academia=ac_1").text
    assert "Plan de tenis · Iniciación" in html and "Lucía" in html
    assert _cli().post("/anfitrion/academia/evaluaciones/evaluar", json={"academia_id": "ac_1", "alumno_id": "al_1", "habilidad": "Revés", "nivel": "logrado"}).json()["ok"]
    assert _cli().post("/anfitrion/academia/evaluaciones/evaluar", json={"academia_id": "ac_1", "alumno_id": "al_1", "habilidad": "Inventada", "nivel": "logrado"}).status_code == 400
    r = _cli().post("/anfitrion/academia/evaluaciones/nota", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "plantilla_tenis", "sesion": 1,
                                                                 "desempeno": "muyBien", "observaciones": ["Buena actitud", "texto libre no"]})
    assert r.json()["ok"] and mundo["notas"][0]["nota"] == "Buena actitud" and mundo["notas"][0]["sesionNumero"] == 1
    html = _cli().get("/anfitrion/academia/evaluaciones?academia=ac_1&alumno=al_1").text
    # 1 habilidad lograda de 8 → 2/16 = 12.5 % ≈ 12 %; bitácora con la clase 1.
    assert "12%" in html and "Familiarización con la raqueta" in html and "1/12 clases del plan" in html
    p = ops.progreso(ops.plan_de({"deporte": "tenis"}), {"Revés": "logrado", "Saque": "enProceso"})
    assert p["logrado"] == 1 and p["enProceso"] == 1 and p["sinEvaluar"] == 6 and round(p["pct"], 2) == 18.75


def test_ranking_partidos_categorias_y_tabla(mundo):
    r = _cli().post("/anfitrion/academia/ranking/partido", json={"academia_id": "ac_1", "jugador_a": "al_1", "jugador_b": "al_2", "ganador": "al_2", "marcador": "6-3 6-4"})
    p = r.json()["partido"]
    assert p["jugadorAEmail"] == "mama@gmail.com" and "jugadorBEmail" not in p and p["ganadorId"] == "al_2" and p["id"].startswith("pr_")
    assert mundo["acad"]["partidos"] == [p]
    assert _cli().post("/anfitrion/academia/ranking/partido", json={"academia_id": "ac_1", "jugador_a": "al_1", "jugador_b": "al_1", "ganador": "al_1"}).status_code == 400
    assert _cli().post("/anfitrion/academia/ranking/partido", json={"academia_id": "ac_1", "jugador_a": "al_1", "jugador_b": "al_2", "ganador": "al_1", "marcador": "<script>"}).status_code == 400
    assert _cli().post("/anfitrion/academia/ranking/categoria", json={"academia_id": "ac_1", "alumno_id": "al_2", "categoria": "4ta"}).json()["ok"]
    assert mundo["acad"]["categorias"] == {"al_2": "4ta"}
    assert _cli().post("/anfitrion/academia/ranking/categoria", json={"academia_id": "ac_1", "alumno_id": "al_2", "categoria": "Cualquiera"}).status_code == 400
    tabla = ops.ranking(mundo["acad"], MATS)
    assert [(t["nombre"], t["puntos"], t["pj"]) for t in tabla] == [("Pedro", 3, 1), ("Lucía", 1, 1)]
    html = _cli().get("/anfitrion/academia/ranking?academia=ac_1").text
    assert "Pedro" in html and "6-3 6-4" in html and "4ta" in html
    assert _cli().post("/anfitrion/academia/ranking/partido/eliminar", json={"academia_id": "ac_1", "partido_id": p["id"]}).json()["ok"]
    assert mundo["acad"]["partidos"] == []


def test_reportes_kpis_morosidad_y_programas(mundo, monkeypatch):
    monkeypatch.setattr(ops, "_comision_digital", lambda a, i, f: (5.0, {"cobros": 1, "bruto_soles": 200, "comision_soles": 10, "neto_soles": 190}))
    html = _cli().get("/anfitrion/academia/reportes?academia=ac_1&rango_sel=todo").text
    assert "Cobrado</small><b>S/ 200.00" in html and "Por cobrar</small><b>S/ 200.00" in html
    assert "Morosidad hoy (1)" in html and "Bola Roja" in html and "B-0001" in html
    assert "Neto para tu academia" in html and "S/ 190.00" in html
    r = ops.rango("pasado", ops.date(2026, 3, 15))
    assert r[0] == ops.datetime(2026, 2, 1) and r[1].date() == ops.date(2026, 2, 28)


def test_chats_lista_enlaza_a_mensajes_y_escribe_el_primero(mundo):
    html = _cli().get("/anfitrion/academia/chats?academia=ac_1").text
    assert "Lucía" in html and "Pedro" not in html  # sin cuenta en la app no hay chat
    assert "mama@gmail.com" not in html  # el correo no viaja en claro
    ref = ops.ref_cuenta("mama@gmail.com")
    assert f"data-escribir='{ref}'" in html
    j = _cli().post("/anfitrion/academia/chats/enviar", json={"academia_id": "ac_1", "cuenta": ref, "texto": "Hola, mañana hay clase"}).json()
    assert j["ok"] and j["url"].startswith("/mensajes/")
    assert mundo["msgs"][-1]["hilo"] == "ac_1|mama@gmail.com" and mundo["msgs"][-1]["texto"] == "Hola, mañana hay clase"
    assert _cli().post("/anfitrion/academia/chats/enviar", json={"academia_id": "ac_1", "cuenta": "cualquiera", "texto": "x"}).status_code == 400
    # Con mensajes, la fila abre la conversación en /mensajes/{clave}.
    html = _cli().get("/anfitrion/academia/chats?academia=ac_1").text
    assert "href='/mensajes/" in html and "Tú: Hola, mañana hay clase" in html


def test_sedes_horarios_y_precios_por_sede(mundo):
    assert "Guardar cambios" in _cli().get("/anfitrion/academia/sedes?academia=ac_1").text
    r = _cli().post("/anfitrion/academia/sedes/guardar", json={
        "academia_id": "ac_1",
        "sedes": [{"id": "sede_1", "nombre": "Club Las Palmas", "direccion": "Av. 1", "lat": -12.2, "lng": -77.01},
                  {"id": "sede_2", "nombre": "Country El Bosque"}],
        "horarios": {"sede_1|Bola Roja": "Lun-Mié 4-6pm", "sede_9|Bola Roja": "huérfano", "sede_2|Bola Roja": ""},
        "precios": {"sede_1|Bola Roja | 2x": 220, "sede_2|pk": 0, "sede_1|no_existe": 99}})
    assert r.json()["ok"]
    a = mundo["acad"]
    assert [s["id"] for s in a["sedes"]] == ["sede_1", "sede_2"] and a["sedes"][0]["lat"] == -12.2 and "lat" not in a["sedes"][1]
    assert a["horarios"] == {"sede_1|Bola Roja": "Lun-Mié 4-6pm"}
    assert a["preciosSede"] == {"sede_1|Bola Roja | 2x": 220}
    assert a["planes"] == ACAD["planes"] and a["nombre"] == "Academia Raqueta"  # el resto se conserva
    assert _cli().post("/anfitrion/academia/sedes/guardar", json={"academia_id": "ac_1", "sedes": [{"id": "sede_1", "nombre": ""}]}).status_code == 400


def test_evaluacion_usa_el_plan_propio_del_app_y_la_plantilla_solo_si_ya_tiene_notas(mundo):
    """El plan de trabajo que el profe armó en el APK (`PlanTrabajo.toJson` en
    `pichangol_academia_planes`) es el que evalúa la web: mismas habilidades,
    mismas clases y el MISMO plan_id, así el app ve las filas de la web."""
    mundo["planes"].append({"id": "plan_123", "academiaId": "ac_1", "deporte": "tenis", "nombre": "Mi plan avanzado",
                            "nivel": "Avanzado", "habilidades": ["Slice", "Drop shot"], "esPlantilla": False,
                            "sesiones": [{"numero": 2, "titulo": "Slice de revés", "objetivo": "", "contenidos": []},
                                         {"numero": 1, "titulo": "Calentamiento", "objetivo": "", "contenidos": ["Trote"]}]})
    html = _cli().get("/anfitrion/academia/evaluaciones?academia=ac_1").text
    assert "Mi plan avanzado" in html and "2 habilidades · 2 clases" in html
    assert "Plan de tenis · Iniciación" not in html  # sin evaluaciones en la plantilla, no se ofrece
    j = _cli().post("/anfitrion/academia/evaluaciones/evaluar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "plan_123",
                                                                      "habilidad": "Slice", "nivel": "enProceso"}).json()
    assert j["ok"] and mundo["evals"][("al_1", "plan_123", "Slice")] == "enProceso"
    # Sin plan_id (JS viejo) va al plan por defecto (el propio); una habilidad de la plantilla no vale.
    assert _cli().post("/anfitrion/academia/evaluaciones/evaluar", json={"academia_id": "ac_1", "alumno_id": "al_1", "habilidad": "Revés", "nivel": "logrado"}).status_code == 400
    # Un plan ajeno o inexistente no se acepta.
    assert _cli().post("/anfitrion/academia/evaluaciones/evaluar", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "plan_x",
                                                                         "habilidad": "Slice", "nivel": "logrado"}).status_code == 400
    r = _cli().post("/anfitrion/academia/evaluaciones/nota", json={"academia_id": "ac_1", "alumno_id": "al_1", "plan_id": "plan_123", "sesion": 2,
                                                                 "desempeno": "bien", "observaciones": []})
    assert r.json()["ok"] and mundo["notas"][-1]["planId"] == "plan_123" and mundo["notas"][-1]["sesionNumero"] == 2
    html = _cli().get("/anfitrion/academia/evaluaciones?academia=ac_1&alumno=al_1&plan=plan_123").text
    assert "Clase 2: Slice de revés" in html and "1/2 clases del plan" in html and "25%" in html
    # Con evaluaciones guardadas en la plantilla (antes del plan propio), ambas se ofrecen como chips.
    mundo["evals"][("al_2", "plantilla_tenis", "Revés")] = "logrado"
    html = _cli().get("/anfitrion/academia/evaluaciones?academia=ac_1&plan=plantilla_tenis").text
    assert "Plan de tenis · Iniciación" in html and "&plan=plan_123" in html and "Mi plan avanzado" in html
    assert ops._plan_normal({"nombre": "sin id"}) is None
