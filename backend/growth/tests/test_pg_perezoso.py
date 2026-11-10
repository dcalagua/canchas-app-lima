"""Transacción PEREZOSA del pool (1-oct-2026, "cada clic demora mucho"): con
la base lejos (us-west2 ↔ São Paulo, ~180 ms por viaje) una lectura no debe
pagar BEGIN + COMMIT; las escrituras siguen siendo atómicas."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db import pg  # noqa: E402


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
                if "falla" in sql:
                    raise RuntimeError("boom")
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


def test_lecturas_sin_begin_ni_commit(crudo):
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.execute("  WITH x AS (SELECT 1) SELECT * FROM x")
    assert crudo.log == ["SELECT 1", "  WITH x AS (SELECT 1) SELECT * FROM x"]


def test_escrituras_y_for_update_en_una_transaccion(crudo):
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT v FROM t")
        cur.execute("SELECT v FROM t WHERE id = 1 FOR UPDATE")
        cur.execute("UPDATE t SET v = 2")
        cur.execute("WITH d AS (DELETE FROM t RETURNING id) SELECT * FROM d")
    assert crudo.log == ["SELECT v FROM t", "BEGIN", "SELECT v FROM t WHERE id = 1 FOR UPDATE",
                         "UPDATE t SET v = 2", "WITH d AS (DELETE FROM t RETURNING id) SELECT * FROM d", "COMMIT"]


def test_error_deshace_la_transaccion_y_descarta_la_conexion(crudo):
    with pytest.raises(RuntimeError):
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO t VALUES (1)")
            cur.execute("UPDATE falla")
    assert crudo.log == ["BEGIN", "INSERT INTO t VALUES (1)", "ROLLBACK"] and crudo.closed


def test_commit_explicito_a_mitad_abre_otra_transaccion(crudo):
    with pg.conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.rollback()  # sin transacción abierta: no viaja
        cur.execute("DELETE FROM t")
    assert crudo.log == ["BEGIN", "INSERT INTO t VALUES (1)", "COMMIT", "BEGIN", "DELETE FROM t", "COMMIT"]


def test_es_lectura():
    assert pg.es_lectura("select * from x")
    assert not pg.es_lectura("select * from x for update")
    assert not pg.es_lectura("insert into x values (1)")
