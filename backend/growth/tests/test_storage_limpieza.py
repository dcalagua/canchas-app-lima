"""BARRIDO DE STORAGE: candados de seguridad y comportamiento del operador.

Lo crítico aquí no es cuántos archivos borra, sino QUÉ NO borra nunca: las
constancias de recargas (registro contable) y el arte compartido.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import main  # noqa: E402
import storage_limpieza as sl  # noqa: E402

cli = TestClient(main.app)


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PANEL_TOKEN", "tok_admin")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://qa.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon_qa")


def test_recargas_y_arte_compartido_jamas_se_borran():
    """Candado duro: aunque una consulta los devolviera, nunca salen."""
    assert sl._protegido("canchas", "recargas/constancia_1.jpg")
    assert sl._protegido("canchas", "ilustraciones/il_x.jpg")
    assert sl._protegido("canchas", "bodega/packshot_gaseosa.jpg")
    # Lo que sí es barrible.
    assert not sl._protegido("canchas", "entrenador/clip.mp4")
    assert not sl._protegido("canchas", "bodega/prod_9.jpg")
    assert not sl._protegido("estados", "e123.jpg")


def test_borrar_objeto_respeta_el_candado(monkeypatch):
    llamadas = []
    monkeypatch.setattr(sl.urllib.request, "urlopen",
                        lambda req, timeout=20: llamadas.append(req) or
                        __import__("io").BytesIO(b""))
    # Protegido: ni siquiera se llama al storage.
    assert sl._borrar_objeto("canchas", "recargas/x.jpg") is False
    assert llamadas == []
    # Normal: DELETE a la ruta exacta.
    assert sl._borrar_objeto("estados", "e1.jpg") is True
    assert len(llamadas) == 1
    assert llamadas[0].get_method() == "DELETE"
    assert llamadas[0].full_url.endswith("/estados/e1.jpg")


def test_sin_base_de_datos_no_rompe(monkeypatch):
    """Sin DATABASE_URL el barrido informa, no explota."""
    monkeypatch.setattr(sl.pg, "habilitado", False)
    r = sl.analizar()
    assert r["ok"] is False and r["error"] == "sin_base_de_datos"


def test_una_tabla_faltante_no_tumba_el_barrido(monkeypatch):
    """Si un ambiente no tiene alguna tabla (p. ej. bodega), esa familia se
    reporta con su error y las demás siguen contándose."""
    class _Cur:
        def execute(self, sql):
            if "pichangol_bodega_productos" in sql:
                raise RuntimeError('relation "pichangol_bodega_productos" does not exist')
        def fetchall(self):
            return [("estados", "viejo.jpg")]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def cursor(self): return _Cur()
        def rollback(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(sl.pg, "habilitado", True)
    monkeypatch.setattr(sl.pg, "_conn", lambda: _Conn())
    r = sl.analizar()
    assert r["ok"] is True
    assert r["familias"]["bodega"]["n"] == 0
    assert "does not exist" in r["familias"]["bodega"]["error"]
    assert r["familias"]["estados"]["n"] == 1
    assert r["total"] > 0


def test_endpoints_exigen_token_admin(monkeypatch):
    monkeypatch.setattr(sl, "analizar", lambda: {"ok": True, "total": 0,
                                                 "familias": {}})
    assert cli.get("/admin/api/storage/huerfanos").status_code == 401
    assert cli.post("/admin/api/storage/limpiar").status_code == 401
    r = cli.get("/admin/api/storage/huerfanos",
                headers={"X-Admin-Token": "tok_admin"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_limpiar_no_borra_lo_protegido_aunque_la_consulta_lo_traiga(monkeypatch):
    """Simula una consulta mal escrita que devuelve una constancia de recarga:
    el barrido debe saltarla igual."""
    filas = [("canchas", "recargas/constancia.jpg"), ("estados", "e9.jpg")]

    class _Cur:
        def execute(self, sql): pass
        def fetchall(self): return list(filas)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def cursor(self): return _Cur()
        def rollback(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    borrados = []
    monkeypatch.setattr(sl.pg, "habilitado", True)
    monkeypatch.setattr(sl.pg, "_conn", lambda: _Conn())
    monkeypatch.setattr(sl, "_borrar_objeto",
                        lambda b, n: (borrados.append(f"{b}/{n}"), True)[1]
                        if not sl._protegido(b, n) else False)
    r = sl.limpiar()
    assert r["ok"] is True
    assert all("recargas/" not in x for x in borrados)
    assert "estados/e9.jpg" in borrados
