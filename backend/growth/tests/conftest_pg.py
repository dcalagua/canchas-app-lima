"""Fixture `pg_local`: conecta `db.pg` a un Postgres REAL (Docker local,
`docker-compose.dev.yml`) cuando existe `TEST_DATABASE_URL`; si no, el test
se salta. Así los tests de integración (UNIQUE, triggers, transacciones)
corren en la máquina del desarrollador y en CI con un servicio postgres, y la
suite normal sigue sin base de datos."""

import os

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
def pg_local(monkeypatch):
    if not TEST_DATABASE_URL:
        pytest.skip("sin TEST_DATABASE_URL (Postgres local)")
    from urllib.parse import urlparse
    assert (urlparse(TEST_DATABASE_URL).hostname or "") in ("localhost", "127.0.0.1"), \
        "los tests de integración SOLO corren contra un Postgres local"
    from db import pg
    from web import datos
    monkeypatch.setattr(pg, "DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(pg, "habilitado", True)
    with pg._pool_lock:
        pg._pool.clear()
    datos._col_fid_cache.clear()
    yield pg
    with pg._pool_lock:
        pg._pool.clear()
    datos._col_fid_cache.clear()
