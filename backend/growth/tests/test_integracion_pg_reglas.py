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
