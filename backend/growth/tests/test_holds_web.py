"""Apartados web sin pagar (caso real PRD, 1-oct-2026): uno abandonado dejó
las 20:00 "Ocupado" toda la noche porque solo se borraba cuando otro cliente
intentaba reservar esa cancha. Ahora no ocupa el turno y un cron lo borra."""

import os
import re
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db import pg  # noqa: E402
from web import datos  # noqa: E402


class _Cur:
    def __init__(self, log):
        self.log, self.rowcount = log, 0

    def execute(self, sql, params=()):
        self.log.append((sql, params))

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _Cur(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def _falso(monkeypatch):
    log = []

    @contextmanager
    def conexion():
        yield _Conn(log)
    monkeypatch.setattr(pg, "habilitado", True, raising=False)
    monkeypatch.setattr(pg, "conexion", conexion)
    return log


def _placeholders(sql):
    return len(re.findall(r"(?<!%)%s", sql))


def test_ocupacion_ignora_apartados_web_vencidos(monkeypatch):
    log = _falso(monkeypatch)
    datos.ocupados("u1", ["2026-10-01"])
    datos.ocupados_varias(["u1", "u2"], ["2026-10-01"])
    reservas = [(s, p) for s, p in log if "pichangol_reservas" in s]
    assert len(reservas) == 2
    for sql, params in reservas:
        assert "estado,'') = 'nueva'" in sql and "web\\_%%" in sql
        assert _placeholders(sql) == len(params)
        assert isinstance(params[-1], int) and params[-1] > 1_700_000_000_000  # corte en ms


def test_cron_borra_apartados_vencidos_de_todas_las_canchas(monkeypatch):
    log = _falso(monkeypatch)
    assert datos.liberar_holds_vencidos_todos() == []
    sql, params = log[-1]
    assert sql.startswith("DELETE FROM pichangol_reservas") and "cancha_id" not in sql.split("RETURNING")[0]
    assert "NOT coalesce(pagado,false)" in sql and params[0] == "web\\_%"
    assert _placeholders(sql) == len(params)
