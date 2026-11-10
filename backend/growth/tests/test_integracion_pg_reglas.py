"""Integración REAL (Postgres local) de las reglas de reserva: columna,
guardado solo por el dueño y trigger que impide a `anon` pisarlas."""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.conftest_pg import pg_local  # noqa: E402,F401
from web import datos  # noqa: E402


def _sql(pg, q, args=()):
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute(q, args)
        filas = cur.fetchall() if cur.description else None
        conn.commit()
        return filas


def test_guardar_reglas_solo_del_dueno_y_anon_no_las_pisa(pg_local):
    pg = pg_local
    _sql(pg, "delete from pichangol_canchas where id like 'it_%%'")
    _sql(pg, "insert into pichangol_canchas (id, nombre, club, dueno, verificada, registrada) values "
             "('it_a','A','Club','dueno@x.com',true,true), ('it_b','B','Club','otro@x.com',true,true)")
    assert datos.col_reglas_disponible()
    assert datos.guardar_reglas(["it_a", "it_b"], "dueno@x.com", {"min_turnos": 2}) == 1
    assert datos.cancha("it_a")["reglas_reserva"] == {"min_turnos": 2}
    assert datos.cancha("it_b")["reglas_reserva"] == {}
    # El APK (rol anon) reescribe la fila completa: las reglas sobreviven.
    _sql(pg, "grant select, insert, update on pichangol_canchas to anon")
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute("set local role anon")
        cur.execute("update pichangol_canchas set nombre = 'A2', reglas_reserva = %s where id = 'it_a'",
                    (json.dumps({"hack": True}),))
        conn.commit()
    c = datos.cancha("it_a")
    assert c["nombre"] == "A2" and c["reglas_reserva"] == {"min_turnos": 2}
    _sql(pg, "delete from pichangol_canchas where id like 'it_%%'")


def test_comision_reserva_solo_del_dueno_real(pg_local, monkeypatch):
    """Seguridad C2 con base REAL: /pagos/comision-reserva no descuenta del
    saldo de un dueño que no es el de esa reserva, ni más de lo que vale."""
    from fastapi.testclient import TestClient
    import config
    from main import app
    monkeypatch.setattr(config, "APP_API_KEY", "")
    pg = pg_local
    _sql(pg, "delete from pichangol_reservas where id like 'it_%%'")
    _sql(pg, "delete from pichangol_canchas where id like 'it_%%'")
    _sql(pg, "insert into pichangol_canchas (id, nombre, club, dueno, verificada, registrada) "
             "values ('it_c','C','Club','dueno@x.com',true,true)")
    _sql(pg, "insert into pichangol_reservas (id, cancha_id, jugador, fecha, dia, hora_inicio, hora_fin, estado, "
             "precio, sena, pagado, usuario) values ('it_r1','it_c','Ana','2030-01-01','x','10:00','11:00',"
             "'confirmada',60,0,false,'ana@x.com')")
    cli = TestClient(app)
    def com(rid, dueno, monto):
        return cli.post("/pagos/comision-reserva", json={"dueno_id": dueno, "monto_soles": monto,
                                                         "reserva_id": rid, "moneda": "PEN"}).json()
    assert com("it_no_existe", "dueno@x.com", 60)["error"] == "reserva_no_encontrada"
    assert com("it_r1", "victima@x.com", 60)["error"] == "no_es_el_dueno"
    assert com("it_r1", "dueno@x.com", 5000)["error"] == "monto_mayor_a_la_reserva"
    assert com("it_r1", "dueno@x.com", 60)["ok"]
    _sql(pg, "delete from pichangol_reservas where id like 'it_%%'")
    _sql(pg, "delete from pichangol_canchas where id like 'it_%%'")


def test_anon_no_se_apropia_de_canchas(pg_local):
    """Migración 0004: con la anon key no se sube `verificada` ni se cambia un
    `dueno` ya asignado; el backend (rol postgres) sí."""
    pg = pg_local
    _sql(pg, "delete from pichangol_canchas where id like 'it_%%'")
    _sql(pg, "insert into pichangol_canchas (id, nombre, club, dueno, verificada, registrada) values "
             "('it_p','P','Club','dueno@x.com',false,true), ('it_l','L','Club','',false,true)")
    _sql(pg, "grant select, insert, update on pichangol_canchas to anon")
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute("set local role anon")
        cur.execute("update pichangol_canchas set verificada = true, dueno = 'atacante@x.com', nombre = 'P2' where id = 'it_p'")
        cur.execute("update pichangol_canchas set dueno = 'nuevo@x.com', verificada = true where id = 'it_l'")
        cur.execute("insert into pichangol_canchas (id, nombre, club, dueno, verificada, registrada) "
                    "values ('it_n','N','Club','x@x.com',true,true)")
        conn.commit()
    filas = {r[0]: r[1:] for r in _sql(pg, "select id, dueno, verificada, nombre from pichangol_canchas where id like 'it_%%'")}
    assert filas["it_p"] == ("dueno@x.com", False, "P2")       # edita lo suyo, no se apropia
    assert filas["it_l"] == ("nuevo@x.com", False, "L")        # reclama un legado, sin verificarse solo
    assert filas["it_n"][1] is False                           # nunca nace verificada
    from web import datos
    assert datos.marcar_verificada("it_p", "dueno@x.com", True) == 1   # la torre (backend) sí
    _sql(pg, "delete from pichangol_canchas where id like 'it_%%'")
