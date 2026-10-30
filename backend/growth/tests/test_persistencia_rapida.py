"""Persistencia que no frena las requests (queja del director, 25-sep-2026:
"mucho se demora para agregar un simple equipo, y lo mismo sucede en todo el
sistema"): el snapshot se escribe solo si cambió, las tablas normalizadas solo
reciben filas nuevas o cambiadas, y el middleware ya no espera a Supabase."""

import os
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import pg  # noqa: E402


class _Cursor:
    def __init__(self, reg):
        self.reg = reg

    def execute(self, sql, params=None):
        self.reg.append(("execute", sql.split("(")[0].strip(), 1))

    def executemany(self, sql, filas):
        self.reg.append(("executemany", sql.split("(")[0].strip(), len(list(filas))))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, reg):
        self.reg = reg
        self.closed = False

    def cursor(self):
        return _Cursor(self.reg)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class _Stores:
    def __init__(self):
        self.saldos = {"a@x.com": 100}
        self.pagos = [{"id": "p1", "tipo": "recarga", "monto_centimos": 100, "moneda": "PEN", "estado": "ok", "dueno_id": "a@x.com",
                       "culqi_charge_id": "", "email": "a@x.com", "concepto": "", "creado_en": "2026-09-25T00:00:00"}]
        self.vistas = {"c1": {"2026-09-25": 3}}
        self.reclamos = []
        self.estado = {"n": 1}

    def saldos_rows(self):
        return list(self.saldos.items())

    def pagos_rows(self):
        return [dict(p) for p in self.pagos]

    def vistas_rows(self):
        return [(k, d, n) for k, v in self.vistas.items() for d, n in v.items()]

    def reclamos_rows(self):
        return [dict(r) for r in self.reclamos]

    def to_state(self):
        return dict(self.estado)


def _con_bd(monkeypatch):
    reg = []

    @contextmanager
    def conexion():
        yield _Conn(reg)

    monkeypatch.setattr(pg, "habilitado", True)
    monkeypatch.setattr(pg, "conexion", conexion)
    monkeypatch.setattr(pg, "_ultimo_hash", None)
    for d in pg._norm_huellas.values():
        d.clear()
    return reg


def test_snapshot_solo_se_escribe_si_cambio(monkeypatch):
    reg = _con_bd(monkeypatch)
    assert pg.guardar({"a": 1}) is True
    assert pg.guardar({"a": 1}) is False          # mismo contenido → no viaja a Supabase
    assert pg.guardar({"a": 2}) is True           # cambió → se escribe
    assert pg.guardar({"a": 2}, forzar=True) is True
    assert [r for r in reg if "growth_state" in r[1]] and len(reg) == 3


def test_tablas_normalizadas_incrementales(monkeypatch):
    reg = _con_bd(monkeypatch)
    st = _Stores()
    pg.guardar_normalizado(st)                    # primera pasada = backfill de todo
    escritas = {r[1]: r[2] for r in reg}
    assert escritas["insert into growth_saldos"] == 1 and escritas["insert into growth_pagos"] == 1 and escritas["insert into growth_vistas"] == 1
    reg.clear()
    pg.guardar_normalizado(st)                    # nada cambió → cero consultas
    assert reg == []
    st.pagos[0]["estado"] = "anulado"             # cambia UNA fila → viaja solo esa
    st.saldos["b@x.com"] = 50
    pg.guardar_normalizado(st)
    assert sorted((r[1], r[2]) for r in reg) == [("insert into growth_pagos", 1), ("insert into growth_saldos", 1)]


def test_persistencia_en_segundo_plano_agrupa_varios_post(monkeypatch):
    reg = _con_bd(monkeypatch)
    monkeypatch.setattr(pg, "PERSISTIR_REBOTE_SEG", 0.05)
    st = _Stores()
    t0 = time.time()
    for i in range(5):                            # 5 POST seguidos
        st.estado["n"] = i
        pg.persistir_en_segundo_plano(st)
    assert time.time() - t0 < 0.05                # la request no espera a la BD
    for _ in range(100):
        if not pg.hay_persistencia_pendiente() and any("growth_state" in r[1] for r in reg):
            break
        time.sleep(0.02)
    time.sleep(0.05)
    snaps = [r for r in reg if "growth_state" in r[1]]
    assert 1 <= len(snaps) <= 2                   # una (o dos) escrituras, no cinco
