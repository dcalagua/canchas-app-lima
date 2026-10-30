"""Velocidad = MENOS VIAJES A LA BASE (oct-2026). Con PRD en Virginia y la base
en São Paulo (~115 ms por ida y vuelta) lo que manda es cuántas consultas
seguidas hace una página. Aquí: el medidor por request (`[perf] … sql=N
viajes`), la memoria de lecturas de la request, la escritura sin BEGIN/COMMIT
y —contra un Postgres REAL (`TEST_DATABASE_URL`)— que cada consulta unida o
precargada devuelve EXACTAMENTE lo mismo que las consultas sueltas de antes."""

import contextvars
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db import pg  # noqa: E402
from tests.conftest_pg import pg_local  # noqa: E402,F401


# ── medidor + memoria (sin base) ─────────────────────────────────────────────

class _Crudo:
    def __init__(self):
        self.log, self.closed, self.autocommit = [], False, True

    def execute(self, sql, params=None):
        self.log.append(sql)

    def cursor(self):
        crudo = self

        class C:
            rowcount = 0

            def execute(self, sql, params=None):
                crudo.log.append(sql)

            def fetchall(self):
                return []

            def close(self):
                pass
        return C()

    def close(self):
        self.closed = True


@pytest.fixture
def crudo(monkeypatch):
    c = _Crudo()
    monkeypatch.setattr(pg, "_tomar", lambda: c)
    monkeypatch.setattr(pg, "_devolver", lambda conn: None)
    return c


def _en_request(fn, memo=True):
    """Corre [fn] como dentro de una request (contexto propio, como Starlette)."""
    def dentro():
        m = pg.medir_request(memo=memo)
        return fn(), m
    return contextvars.copy_context().run(dentro)


def test_medidor_cuenta_cada_viaje_y_la_escritura_sin_transaccion_es_uno(crudo):
    def trabajo():
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO t VALUES (1)")  # BEGIN + INSERT + COMMIT
        with pg.conexion(atomica=False) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO t SELECT x FROM unnest(%s) x")  # se confirma sola
    _, m = _en_request(trabajo)
    assert m.viajes == 5 and "sql=5 viajes" in m.resumen()
    assert crudo.log == ["SELECT 1", "BEGIN", "INSERT INTO t VALUES (1)", "COMMIT", "INSERT INTO t SELECT x FROM unnest(%s) x"]


def test_memoria_de_la_request_solo_en_get_y_se_vacia_al_escribir(crudo):
    llamadas = []

    def leer():
        llamadas.append(1)
        return {"v": [1, 2]}

    def trabajo():
        a = pg.memo_leer(("k",), leer)
        a["v"].append(99)                      # quien la recibe puede mutarla: no ensucia la memoria
        b = pg.memo_leer(("k",), leer)
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE t SET v = 1")  # escribir olvida lo leído
        c = pg.memo_leer(("k",), leer)
        return a, b, c
    (a, b, c), _ = _en_request(trabajo)
    assert b == {"v": [1, 2]} and c == {"v": [1, 2]} and len(llamadas) == 2
    # Sin memoria (POST, crons, tests directos): siempre lee.
    llamadas.clear()
    _en_request(lambda: (pg.memo_leer(("k",), leer), pg.memo_leer(("k",), leer)), memo=False)
    assert len(llamadas) == 2
    pg.memo_leer(("k",), leer)
    assert len(llamadas) == 3


def test_memoria_por_clave_solo_pide_lo_que_falta():
    pedidos = []

    def leer(ks):
        pedidos.append(list(ks))
        return {k: {"n": k.upper()} for k in ks if k != "nadie"}

    def trabajo():
        a = pg.memo_por_clave("p", ["ana", "bea", "nadie"], leer)
        b = pg.memo_por_clave("p", ["bea", "nadie", "cid"], leer)
        return a, b
    (a, b), _ = _en_request(trabajo)
    assert a == {"ana": {"n": "ANA"}, "bea": {"n": "BEA"}} and b == {"bea": {"n": "BEA"}, "cid": {"n": "CID"}}
    assert pedidos == [["ana", "bea", "nadie"], ["cid"]]   # "nadie" (no existe) tampoco se vuelve a pedir


def test_server_timing_y_perf_con_viajes(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    monkeypatch.setattr(pg, "PERF_SQL", True)
    r = TestClient(app).get("/robots.txt")
    assert 'db;dur=' in r.headers.get("server-timing", "") and 'viajes"' in r.headers["server-timing"]
    monkeypatch.setattr(pg, "PERF_SQL", False)
    assert "server-timing" not in TestClient(app).get("/robots.txt").headers


def test_portada_no_bloquea_con_leaflet():
    from fastapi.testclient import TestClient
    from main import app
    from web import router
    html = TestClient(app).get("/").text
    assert "<script src='https://unpkg.com/leaflet" not in html and "leaflet.css' crossorigin" not in html
    assert '"leaflet"' in html and "cargarLeaflet" in router._JS_EXPLORAR


def test_canchas_por_ids_sin_base_usa_cancha(monkeypatch):
    from web import datos
    monkeypatch.setattr(pg, "habilitado", False)
    monkeypatch.setattr(datos, "cancha", lambda i: {"id": i} if i != "x" else None)
    assert datos.canchas_por_ids(["a", "x", "a", ""]) == {"a": {"id": "a"}, "x": None}


# ── Postgres REAL: lo unido devuelve lo mismo que lo suelto ─────────────────

_PILOTO = Path(__file__).resolve().parents[3] / "docs" / "piloto"
_TABLAS = ["supabase_perfiles", "supabase_agenda", "supabase_chat_prefs", "supabase_lecturas", "supabase_niveles",
           "supabase_puntos_canjes", "supabase_canjes_web", "supabase_boleadores", "supabase_bodega",
           "supabase_bodega_pedidos", "supabase_bodega_pago", "supabase_matriculas", "supabase_academias",
           "supabase_mensajes", "supabase_grupos_foto"]
E = "it_vel_ana@x.com"
HOY = date.today()


def _consultas(m) -> int:
    """Viajes de CONSULTA (sin contar abrir una conexión nueva: el pool de
    los tests arranca vacío)."""
    return m.viajes - m.conexiones


def _sql(q, args=()):
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute(q, args)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


def _crear_tablas():
    for n in _TABLAS:
        f = _PILOTO / f"{n}.sql"
        if f.exists():
            try:
                with pg.conexion() as conn, conn.cursor() as cur:
                    cur.execute(f.read_text())
                    conn.commit()
            except Exception:  # noqa: BLE001 — políticas / publicaciones de Supabase
                pass
    for q in ("create table if not exists pichangol_verificaciones (email text primary key, nombre text, doc_path text, "
              "selfie_path text, estado text, creado timestamptz default now())",
              "create table if not exists pichangol_grupos (id text primary key, nombre text, creador_email text, "
              "creado timestamptz default now(), foto_url text)",
              "create table if not exists pichangol_grupo_miembros (grupo_id text, email text, nombre text, "
              "creado timestamptz default now(), primary key (grupo_id, email))",
              "create table if not exists pichangol_espera (id text primary key, cancha_id text, fecha text, hora text, "
              "usuario text, nombre text, telefono text, creado timestamptz default now())"):
        try:
            _sql(q)
        except Exception:  # noqa: BLE001
            pass


def _limpiar():
    for q in ("delete from pichangol_reservas where id like 'it_vel_%%'",
              "delete from pichangol_canchas where id like 'it_vel_%%'",
              "delete from pichangol_bloqueos where cancha_id like 'it_vel_%%'",
              "delete from pichangol_descuentos_slot where cancha_id like 'it_vel_%%'",
              "delete from pichangol_niveles where email like 'it_vel_%%'",
              "delete from pichangol_verificaciones where email like 'it_vel_%%'",
              "delete from pichangol_puntos_canjes where email like 'it_vel_%%'",
              "delete from pichangol_canjes_web where id like 'it_vel_%%'",
              "delete from pichangol_agenda where email like 'it_vel_%%'",
              "delete from pichangol_chat_prefs where email like 'it_vel_%%'",
              "delete from pichangol_lecturas where email like 'it_vel_%%'",
              "delete from pichangol_mensajes where id like 'it_vel_%%'",
              "delete from pichangol_grupos where id like 'it_vel_%%'",
              "delete from pichangol_grupo_miembros where grupo_id like 'it_vel_%%'",
              "delete from pichangol_academias where id like 'it_vel_%%'",
              "delete from pichangol_boleadores where email like 'it_vel_%%'",
              "delete from cl_pasarela_club where dueno like 'it_vel_%%'",
              "delete from cl_medios_pago_club where dueno like 'it_vel_%%'"):
        try:
            _sql(q)
        except Exception:  # noqa: BLE001 — tabla ausente en esta base
            pass


@pytest.fixture
def base(pg_local):
    _crear_tablas()
    _limpiar()
    from web import datos
    datos.invalidar_canchas()
    _sql("insert into pichangol_canchas (id, nombre, club, dueno, verificada, registrada, hora_apertura, hora_cierre) values "
         "('it_vel_c1','Fútbol 1','Club Vel','it_vel_dueno@x.com',true,true,'07:00','23:00'), "
         "('it_vel_c2','Tenis 1','Club Vel','it_vel_dueno@x.com',true,true,'07:00','23:00')")
    f1, f2, f0 = (HOY + timedelta(days=3)).isoformat(), (HOY + timedelta(days=4)).isoformat(), (HOY - timedelta(days=30)).isoformat()
    ms = int(time.time() * 1000)
    _sql("insert into pichangol_reservas (id, cancha_id, jugador, fecha, dia, hora_inicio, hora_fin, estado, traida_por_app, precio, "
         "sena, pagado, usuario, medio_pago, grupo_reserva_id, extras) values "
         f"('it_vel_r1','it_vel_c1','Ana','{f1}','x','20:00','21:00','confirmada',true,95,0,true,'{E}','tarjeta','grp_{ms}', '[{{\"precio\": 12.5}}]'), "
         f"('it_vel_r2','it_vel_c1','Ana','{f1}','x','21:00','22:00','confirmada',true,95,0,true,'{E}','tarjeta','grp_{ms}', '[]'), "
         f"('it_vel_r3','it_vel_c2','Ana','{f2}','x','18:00','19:00','confirmada',true,60,0,true,'{E}','bono','', '[]'), "
         f"('it_vel_r4','it_vel_c2','Ana','{f0}','x','08:00','09:00','confirmada',true,70.5,0,true,'{E}','yape','', '[]'), "
         f"('it_vel_r5','it_vel_c2','Ana','{f2}','x','10:00','11:00','nueva',true,60,0,false,'{E}','','', '[]'), "
         f"('it_vel_r6','it_vel_c1','Otro','{f1}','x','10:00','11:00','confirmada',true,95,0,true,'otro@x.com','tarjeta','', '[]')")
    for q in (f"insert into pichangol_niveles (email, deporte, nivel, partidos, victorias) values ('{E}','tenis',3.5,4,2), ('{E}','futbol',4.25,10,7)",
              f"insert into pichangol_verificaciones (email, nombre, estado) values ('{E}','Ana','verificado')",
              f"insert into pichangol_puntos_canjes (email, puntos, soles, referencia) values ('{E}',100,3,'it_vel_c1_{f1}_20:00'), "
              f"('{E}',100,3,'otra'), ('{E}',-100,-3,'devolucion:otra')",
              "insert into pichangol_canjes_web (id, tipo, email, cancha_id, club, dueno, reserva_ref, reserva_ids, horas, puntos, descuento, "
              f"moneda, detalle, estado, canal) values ('it_vel_cw','bono','{E}','it_vel_c2','Club Vel','it_vel_dueno@x.com','it_vel_r3',"
              "'[\"it_vel_r3\"]',1,0,60,'PEN','{}','usado','web')",
              f"insert into pichangol_bloqueos (cancha_id, fecha, hora) values ('it_vel_c1','{f1}','10:00'), ('it_vel_c1','{f1}','11:00')",
              f"insert into pichangol_descuentos_slot (cancha_id, fecha, hora, pct) values ('it_vel_c1','{f1}','15:00',20)",
              f"insert into pichangol_agenda (email, apodos, contactos, bloqueados) values ('{E}','{{\"b@x.com\": \"Bea\"}}','[\"b@x.com\"]','[\"z@x.com\"]')",
              f"insert into pichangol_chat_prefs (email, hilo, oculto_en, fijado, archivado, silenciado) values "
              f"('{E}','cancha_it_vel_dueno@x.com|{E}', now() - interval '1 day', true, false, true)",
              "insert into pichangol_academias (id, dueno, data) values ('it_vel_ac', 'it_vel_dueno@x.com', '{\"nombre\": \"Acad\"}')",
              "insert into pichangol_grupos (id, nombre, creador_email, foto_url) values ('it_vel_g', 'Grupo', 'b@x.com', '')",
              f"insert into pichangol_grupo_miembros (grupo_id, email, nombre) values ('it_vel_g','{E}','Ana'), ('it_vel_g','b@x.com','Bea')",
              "insert into pichangol_mensajes (id, hilo, academia_id, cuenta_email, autor_email, autor_nombre, texto, tipo, ref_id) values "
              f"('it_vel_m1','cancha_it_vel_dueno@x.com|{E}','','{E}','it_vel_dueno@x.com','Club','hola','cancha','it_vel_dueno@x.com'), "
              f"('it_vel_m2','grupo_it_vel_g','','','b@x.com','Bea','grupo','grupo','it_vel_g'), "
              f"('it_vel_m3','it_vel_ac|{E}','it_vel_ac','{E}','it_vel_dueno@x.com','Profe','clase','academia','it_vel_ac')",
              "insert into pichangol_boleadores (email, deporte, categoria, tarifa, moneda, activo, data) values "
              f"('{E}','tenis','4ta',20,'PEN',true,'{{\"nombre\": \"Ana\"}}')",
              "insert into cl_medios_pago_club (dueno, tipo, titular, numero, banco, cuenta, cci, qr_url, nota, activo, orden) values "
              "('it_vel_dueno@x.com','yape','Club','987654321','','','','','',true,0), "
              "('it_vel_dueno@x.com','transferencia','Club','','BCP','191','002','','',true,1)"):
        try:
            _sql(q)
        except Exception as ex:  # noqa: BLE001 — tabla ausente en esta base: esa parte cae al camino de siempre
            print("semilla:", str(ex).splitlines()[0])
    yield datos
    _limpiar()
    datos.invalidar_canchas()


def test_puntos_de_una_consulta_igual_que_por_partes(base):
    datos = base
    from datetime import datetime, timezone
    desde = datetime.now(timezone.utc) - timedelta(days=365)
    (r, m) = _en_request(lambda: datos.puntos_de(E))
    assert r == datos._puntos_de_por_partes(E, desde) and _consultas(m) == 1
    # 95 + 12.5 de extras = 107.5 → 108 y 70.5 → 70: redondeo de Python por reserva, como antes.
    assert r["ganados"] == 108 + 95 + 60 + 70 and r["canjeados"] == 100


def test_precarga_del_perfil_igual_que_cada_funcion(base):
    datos = base
    datos._cols_res()  # ¿columnas de cargo? se pregunta una vez por proceso (no cuenta aquí)
    sueltos = (datos._reservas_de_usuario(E, 200), datos._niveles_de(E), datos._existe(datos._SQL_VERIFICADO, E),
               datos._existe(datos._SQL_TIENE_MATRICULAS, E), datos._boleador(E))

    def pagina():
        datos.precargar_perfil(E)
        return (datos.reservas_de_usuario(E), datos.niveles_de(E), datos.esta_verificado(E),
                datos.tiene_matriculas(E), datos.boleador(E))
    juntos, m = _en_request(pagina)
    assert juntos == sueltos and _consultas(m) == 1
    assert [x["id"] for x in juntos[0]] == ["it_vel_r3", "it_vel_r2", "it_vel_r1", "it_vel_r4"]  # la retención web no sale
    # El boleador registrado SE ENCUENTRA (antes las fechas ISO rompían la normalización y salía None).
    assert juntos[4] and juntos[4]["email"] == E and juntos[4]["creado"]


def test_precarga_de_mis_reservas_igual_que_por_reserva(base):
    datos = base
    from web import beneficios
    filas = datos._reservas_de_usuario(E, 200)
    grupos = {}
    for f in filas:
        grupos.setdefault(f.get("grupo_reserva_id") or f["id"], []).append(f)
    c = datos._cancha("it_vel_c1")
    sueltos = [beneficios.ajustes(sorted(g, key=lambda x: x["hora_inicio"]), c) for g in grupos.values()]

    def pagina():
        datos.precargar_canjes_web(list(grupos))
        datos.precargar_puntos_canjes(E)
        return [beneficios.ajustes(sorted(g, key=lambda x: x["hora_inicio"]), c) for g in grupos.values()]
    juntos, m = _en_request(pagina)
    assert juntos == sueltos and _consultas(m) <= 3   # canjes-web + puntos (+ ¿existe la tabla? una vez por proceso)
    assert any(a["puntos"] == 100 for a in juntos) and any(a["bono_horas"] == 1 for a in juntos)
    ids = ["it_vel_c1", "it_vel_c2", "it_vel_nada"]
    (lote, m2) = _en_request(lambda: (datos.canchas_por_ids(ids), [datos.cancha(i) for i in ids]))
    assert lote[0] == {i: datos._cancha(i) for i in ids} and lote[1] == [datos._cancha(i) for i in ids] and _consultas(m2) == 1


def test_precarga_del_dia_igual_que_ocupados_y_descuentos(base):
    datos = base
    fechas = sorted({(HOY + timedelta(days=3)).isoformat(), (HOY + timedelta(days=4)).isoformat()})
    sueltos = (datos.ocupados("it_vel_c1", fechas), datos.descuentos("it_vel_c1", fechas))

    def pagina():
        datos.precargar_dia("it_vel_c1", fechas)
        return datos.ocupados("it_vel_c1", fechas), datos.descuentos("it_vel_c1", fechas)
    juntos, m = _en_request(pagina)
    assert juntos == sueltos and _consultas(m) == 1 and len(sueltos[0]) >= 4 and sueltos[1]


def test_bandeja_precargada_igual_que_las_consultas_sueltas(base):
    from web import jugador_mensajes as M
    acs, gs = M._academias_de_dueno(E), M.grupos_de(E)
    sueltos = (M._agenda_de(E), M.prefs_de(E), M.resumen_hilos(E, acs, [g["id"] for g in gs]))

    def pagina():
        M.precargar_bandeja(E)
        a2 = M.academias_de_dueno(E)
        g2 = M.grupos_de(E)
        return M.agenda_de(E), M.prefs_de(E), M.resumen_hilos(E, a2, [g["id"] for g in g2]), g2
    (ag, pr, res, g2), m = _en_request(pagina)
    clave = lambda xs: sorted(xs, key=lambda r: r["hilo"])  # noqa: E731
    assert ag == sueltos[0] and pr == sueltos[1] and clave(res) == clave(sueltos[2])
    assert [(g["id"], sorted(g["miembros"])) for g in g2] == [("it_vel_g", ["b@x.com", E])]
    assert _consultas(m) == 2   # precarga + grupos (con sus miembros)
    b, m3 = _en_request(lambda: M.bandeja(E, marcar=True))
    # Una persona = un chat: el hilo de la cancha y el de la academia (mismo dueño) van en UNA fila.
    assert any(len(f["hilos"]) == 2 for f in b["filas"]) and any(f["tipo"] == "grupo" for f in b["filas"]) and _consultas(m3) <= 7
    # El chat oculto con un mensaje más nuevo REAPARECE (una sola escritura de preferencias).
    assert _sql("select oculto_en, fijado, silenciado from pichangol_chat_prefs where email = %s", (E,)) == [(None, True, True)]
    assert {r[0] for r in _sql("select hilo from pichangol_lecturas where email = %s", (E,))} == set(b["entregar"])


def test_pasarela_y_medios_del_club_en_un_viaje(base):
    from pagos import cobro_directo
    repo = cobro_directo.RepoPG()
    sueltos = (repo._pasarela_de("it_vel_dueno@x.com"), repo._medios_de("it_vel_dueno@x.com"))
    juntos, m = _en_request(lambda: (repo.pasarela_de("it_vel_dueno@x.com"), repo.medios_de("it_vel_dueno@x.com")))
    assert juntos == sueltos and _consultas(m) == 1 and [x["tipo"] for x in juntos[1]] == ["yape", "transferencia"]


def test_guardar_prefs_y_marcar_leido_en_una_sentencia(base):
    from web import jugador_mensajes as M
    filas = {"h_a": {"oculto_en": "2026-10-01T10:00:00+00:00", "fijado": True},
             "h_b": {"oculto_en": None, "archivado": True, "silenciado": True}}
    ok, m = _en_request(lambda: M.guardar_prefs(E, filas), memo=False)
    assert ok and _consultas(m) == 1
    pr = M.prefs_de(E)
    assert pr["h_a"]["fijado"] and pr["h_a"]["oculto_en"].isoformat().startswith("2026-10-01T10:00")
    assert pr["h_b"] == {"oculto_en": None, "fijado": False, "archivado": True, "silenciado": True}
    _, m2 = _en_request(lambda: M.marcar_leido(["h_a", "h_b", "h_a"], E), memo=False)
    assert _consultas(m2) == 1
    leidos = _sql("select hilo from pichangol_lecturas where email = %s and leido_hasta is not null", (E,))
    assert sorted(r[0] for r in leidos) == ["h_a", "h_b"]
